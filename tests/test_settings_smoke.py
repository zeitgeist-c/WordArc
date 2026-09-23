import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import tempfile
import unittest
from unittest import mock

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication

import config as cfg
import settings_ui
from i18n import t


class TestSettingsSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.patchers = [
            mock.patch.object(cfg, "CONFIG_DIR", root / "cfg"),
            mock.patch.object(cfg, "CONFIG_FILE", root / "cfg" / "config.json"),
            mock.patch.object(cfg, "DATA_DIR", root / "data"),
            mock.patch.object(cfg, "HISTORY_FILE", root / "data" / "history.jsonl"),
            mock.patch.object(cfg, "MEETINGS_DIR", root / "data" / "meetings"),
            mock.patch.object(cfg, "MEETINGS_FILE", root / "data" / "meetings.jsonl"),
            mock.patch.object(cfg.credential_store, "read", return_value=""),
            mock.patch.object(cfg.credential_store, "read_all", return_value=[]),
            mock.patch.object(cfg.credential_store, "write_all"),
            mock.patch.object(settings_ui.audio, "list_sources", return_value=[]),
            mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]),
            mock.patch.object(settings_ui.startup, "is_enabled", return_value=False),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.window = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")

    def tearDown(self):
        self.window.close()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tmp.cleanup()

    def test_settings_construct_with_secure_defaults(self):
        window = self.window
        self.assertTrue(window.windowTitle().startswith("WordArc"))
        self.assertGreaterEqual(window.width(), 920)
        self.assertGreaterEqual(window.height(), 700)
        self.assertEqual(window.tabs.count(), 4)
        self.assertEqual(tuple(window._tab_index), (
            "dictation", "history", "meeting", "minutes",
            "audio_file", "settings", "shared_ai", "application",
        ))
        self.assertEqual(window.tabs.currentIndex(), 0)
        self.assertFalse(window.history_enabled.isChecked())
        self.assertFalse(window.start_with_windows.isChecked())
        self.assertTrue(window.close_to_tray.isChecked())
        self.assertEqual(window.gemini_keys_list.count(), 0)
        self.assertEqual(window.transcribe_model.currentText(),
                         "gemini-3.5-flash-lite")
        self.assertIs(window.general_theme, window.header_theme)
        window.header_theme.click()
        self.assertEqual(window.conf["theme_mode"], "light")
        self.assertEqual(self.app.property("wordarcTheme"), "light")

    def test_navigation_selects_exact_page(self):
        window = self.window
        self.assertTrue(window.navigate_to("meeting"))
        self.assertEqual(window.tabs.currentIndex(), 1)
        # Absorbed pages land on the tab that holds them.
        self.assertTrue(window.navigate_to("minutes"))
        self.assertEqual(window.tabs.currentIndex(), 1)
        self.assertTrue(window.navigate_to("history"))
        self.assertEqual(window.tabs.currentIndex(), 0)
        self.assertTrue(window.navigate_to("shared_ai"))
        self.assertEqual(window.tabs.currentIndex(), 3)
        self.assertFalse(window.navigate_to("agent"))
        self.assertEqual(
            [window.tabs.tabText(index) for index in range(window.tabs.count())],
            [t("Dictation"), t("Meeting"), t("Audio file"), t("Settings")],
        )

    def test_noop_save_preserves_every_config_key_and_emits_once(self):
        window = self.window
        before = dict(window.conf.data)
        applied = mock.Mock()
        window.applied.connect(applied)
        with mock.patch.object(settings_ui.startup, "set_enabled") as startup_set, \
             mock.patch.object(settings_ui, "info_box"):
            window._save()
        self.assertEqual(window.conf.data, before)
        startup_set.assert_called_once_with(False)
        cfg.credential_store.write_all.assert_called_once_with([])
        applied.assert_called_once_with()

    def test_agent_surface_is_gone_and_legacy_values_survive_save(self):
        window = self.window
        window.conf["assistant_provider"] = "codex"
        window.conf["assistant_prompt"] = "legacy custom prompt"
        self.assertNotIn("agent", window._tab_index)
        with mock.patch.object(settings_ui.startup, "set_enabled"), \
             mock.patch.object(settings_ui, "info_box"):
            window._save()
        self.assertEqual(window.conf["assistant_provider"], "codex")
        self.assertEqual(window.conf["assistant_prompt"], "legacy custom prompt")

    def test_gemini_keys_can_be_reordered_without_showing_secrets(self):
        window = self.window
        window._gemini_keys = ["primary-secret", "backup-secret"]
        window._refresh_gemini_keys(1)
        self.assertNotIn("primary-secret", window.gemini_keys_list.item(0).text())
        window._move_gemini_key(-1)
        self.assertEqual(window._gemini_keys, ["backup-secret", "primary-secret"])

    def test_startup_failure_does_not_report_success_or_apply(self):
        window = self.window
        applied = mock.Mock()
        window.applied.connect(applied)
        with mock.patch.object(
            settings_ui.startup, "set_enabled",
            side_effect=settings_ui.startup.StartupError("registry failed"),
        ), mock.patch.object(settings_ui, "warn_box") as warning, \
             mock.patch.object(settings_ui, "info_box") as information:
            window._save()
        warning.assert_called_once()
        information.assert_not_called()
        applied.assert_not_called()

    def test_confirm_buttons_speak_the_ui_language(self):
        import i18n
        previous = i18n.language()
        i18n.set_language("tr")
        try:
            box = settings_ui.QMessageBox(
                settings_ui.QMessageBox.Icon.Question, "t", "t",
                settings_ui.QMessageBox.StandardButton.Yes
                | settings_ui.QMessageBox.StandardButton.No)
            settings_ui._box_button_texts(box)
            yes = box.button(settings_ui.QMessageBox.StandardButton.Yes)
            no = box.button(settings_ui.QMessageBox.StandardButton.No)
            self.assertEqual(yes.text(), "Evet")
            self.assertEqual(no.text(), "Hayır")
            with mock.patch.object(
                settings_ui.QMessageBox, "exec",
                return_value=settings_ui.QMessageBox.StandardButton.Yes,
            ):
                self.assertTrue(settings_ui.confirm_box(None, "t", "t"))
        finally:
            i18n.set_language(previous)

    def test_minimum_size_has_no_horizontal_or_nested_page_scrollers(self):
        window = self.window
        # The window must shrink to its floor for small screens.
        self.assertLessEqual(window.minimumWidth(), 520)
        self.assertLessEqual(window.minimumHeight(), 400)
        window.resize(520, 400)
        window.show()
        for page_id in window._tab_index:
            window.navigate_to(page_id)
            self.app.processEvents()
        for index in range(window.tabs.count()):
            for scroller in window.tabs.widget(index).findChildren(
                    settings_ui.QScrollArea):
                self.assertEqual(
                    scroller.horizontalScrollBar().maximum(), 0, index
                )

    def test_dictation_uses_section_cards(self):
        window = self.window
        window.navigate_to("dictation")
        cards = window.tabs.widget(0).findChildren(settings_ui.QGroupBox)
        titles = [card.title() for card in cards]
        for expected in ("Start", "Sound", "Output", "Recording",
                         "Cleanup", "History"):
            self.assertIn(t(expected), titles)
        # Every section card explains itself in one muted line.
        main = [card for card in cards
                if card.title() in {t("Start"), t("Sound"), t("Output"),
                                    t("Recording"), t("Cleanup")}]
        self.assertEqual(len(main), 5)
        for card in main:
            muted = [label for label in card.findChildren(settings_ui.QLabel)
                     if label.objectName() == "muted"]
            self.assertTrue(muted, card.title())

    def test_header_buttons_toggle_and_persist(self):
        window = self.window
        fired = []
        window.language_changed.connect(lambda: fired.append(True))
        self.assertEqual(window.header_lang.text(), "Türkçe")
        window.header_lang.click()
        self.assertEqual(window.conf["ui_language"], "en")
        self.assertEqual(window.header_lang.text(), "English")
        self.assertTrue(fired)
        window.header_lang.click()
        self.assertEqual(window.conf["ui_language"], "tr")
        self.assertEqual(window.header_theme.text(), t("Dark"))
        window.header_theme.click()
        self.assertEqual(window.conf["theme_mode"], "light")
        self.assertEqual(window.header_theme.text(), t("Light"))

    def test_file_tab_uses_section_cards(self):
        window = self.window
        window.navigate_to("audio_file")
        cards = window.tabs.widget(2).findChildren(settings_ui.QGroupBox)
        titles = [card.title() for card in cards]
        for expected in ("File", "Options", "Transcript"):
            self.assertIn(t(expected), titles)

    def test_meeting_uses_section_cards(self):
        window = self.window
        window.navigate_to("meeting")
        cards = window.tabs.widget(1).findChildren(settings_ui.QGroupBox)
        titles = [card.title() for card in cards]
        for expected in ("Sound", "Who is talking", "Minutes", "Recording",
                         "Minutes instruction", "Minutes"):
            self.assertIn(t(expected), titles)

    def test_device_names_are_listed_whole(self):
        """A long device name is shown as it is; the list opens wide for it."""
        window = self.window
        long_name = "Mikrofon (3- USBGH8-Plus-7.1-ENC) (Windows DirectSound)"
        # Bluetooth hands-free entries really do carry a line break inside.
        broken = ("Kulaklık (@System32\\drivers\\bthhfenum.sys,#2;%1 "
                  "Hands-Free%0\r\n;(REDMI Buds 8 Lite))")
        window._fill_device_combo(
            window.mic, [("sd:one", long_name), ("sd:two", broken)],
            t("Default microphone"), "")
        texts = [window.mic.itemText(index)
                 for index in range(window.mic.count())]
        self.assertEqual(texts[0], t("Default microphone"))
        self.assertEqual(texts[1], long_name)
        self.assertNotIn("\n", texts[2])
        self.assertNotIn("\r", texts[2])
        self.assertTrue(texts[2].endswith("(REDMI Buds 8 Lite))"))
        metrics = QFontMetrics(window.mic.font())
        widest = max(metrics.horizontalAdvance(text) for text in texts)
        limit = window.mic.screen().availableGeometry().width() - 80
        wanted = widest + settings_ui.SettingsWindow.DEVICE_POPUP_PADDING
        self.assertEqual(window.mic.view().minimumWidth(),
                         wanted if wanted <= limit else limit)

    def test_save_confirms_with_the_banner_and_a_chime(self):
        """A save says so in the window itself; no modal box comes back."""
        window = self.window
        applied = mock.Mock()
        window.applied.connect(applied)
        with mock.patch.object(settings_ui.startup, "set_enabled"), \
             mock.patch.object(settings_ui.sounds, "play") as chime, \
             mock.patch.object(settings_ui, "info_box") as box:
            window._save()
        box.assert_not_called()
        chime.assert_called_once_with(settings_ui.sounds.SAVED)
        self.assertEqual(window.save_banner.label.text(), t("Settings saved"))
        applied.assert_called_once_with()

    def test_save_banner_rides_under_the_header_rule(self):
        window = self.window
        window.resize(920, 700)
        window.show()
        self.app.processEvents()
        banner = window.save_banner
        banner.show_saved(t("Settings saved"))
        self.app.processEvents()
        rule = window._header_rule
        self.assertTrue(banner.isVisible())
        self.assertGreater(banner.y(), rule.mapTo(window, QPoint(0, 0)).y())
        self.assertEqual(banner.x(), 22)
        self.assertEqual(banner.width(), window.width() - 44)
        # Nothing to click, and it leaves on its own.
        self.assertTrue(banner.testAttribute(
            settings_ui.Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertTrue(banner._hold.isActive())
        # A resize while it is up keeps it under the rule.
        window.resize(760, 600)
        self.app.processEvents()
        self.assertEqual(banner.width(), 760 - 44)
        self.assertEqual(banner.y(),
                         rule.mapTo(window, QPoint(0, 0)).y() + 5)
        banner.fade_out()
        self.assertEqual(banner._animation.endValue(), 0.0)

    def test_header_has_no_tagline_and_pages_have_no_duplicate_title(self):
        window = self.window
        labels = window.findChildren(settings_ui.QLabel)
        texts = [label.text() for label in labels]
        self.assertNotIn(t("Dictation and meetings — in one flow."), texts)
        self.assertFalse([text for text in texts if "tek akışta" in text])
        self.assertEqual([l for l in labels if l.objectName() == "pageTitle"], [])
        self.assertEqual(
            len([l for l in labels if l.objectName() == "pageDescription"]), 4)
        self.assertIsNotNone(window.findChild(settings_ui.QFrame, "headerRule"))

    def test_settings_tab_shows_every_section(self):
        window = self.window
        window.resize(920, 700)
        window.show()
        self.app.processEvents()
        window.navigate_to("settings")
        self.app.processEvents()
        page = window.tabs.widget(3).findChild(settings_ui.QScrollArea).widget()
        titles = [box.title() for box in page.findChildren(settings_ui.QGroupBox)]
        for expected in ("Keys", "Speech to text", "Transcript cleanup",
                         "Names and terms", "Interface", "Startup", "Support"):
            self.assertIn(t(expected), titles)
        for control in (window.ui_language, window.corner,
                        window.start_with_windows, window.close_to_tray):
            self.assertTrue(control.isVisibleTo(window), control)

    def test_api_keys_card_layout_and_button_styles(self):
        window = self.window
        self.assertEqual(window.gemini_keys_list.minimumHeight(), 150)
        self.assertEqual(window.gemini_add_button.objectName(), "accentButton")
        self.assertEqual(window.gemini_remove_button.objectName(), "dangerButton")
        card = window.gemini_keys_list.parentWidget()
        self.assertEqual(len(card.findChildren(settings_ui.QPushButton)), 6)
        names = [b.objectName() for b in window.findChildren(settings_ui.QPushButton)]
        self.assertGreaterEqual(names.count("dangerButton"), 4)
        src = pathlib.Path(settings_ui.__file__).read_text(encoding="utf-8")
        self.assertNotIn("Keys are tried from top to bottom and stored only", src)

    def test_key_prompt_speaks_the_ui_language(self):
        import i18n
        previous = i18n.language()
        i18n.set_language("tr")
        try:
            dialog = self.window._key_dialog("Add API", "")
            dialog.show()
            self.app.processEvents()
            texts = [b.text() for b in dialog.findChildren(settings_ui.QPushButton)]
            self.assertIn("Tamam", texts)
            self.assertIn("İptal", texts)
            self.assertEqual(dialog.labelText(), "Gemini API anahtarı")
            dialog.close()
        finally:
            i18n.set_language(previous)

    def test_qt_translator_follows_the_ui_language(self):
        from PyQt6.QtCore import QCoreApplication
        self.assertTrue(settings_ui.install_qt_translator(self.app, "tr"))
        self.assertNotEqual(QCoreApplication.translate("QLineEdit", "&Paste"),
                            "&Paste")
        self.assertFalse(settings_ui.install_qt_translator(self.app, "en"))
        self.assertEqual(QCoreApplication.translate("QLineEdit", "&Paste"),
                         "&Paste")
