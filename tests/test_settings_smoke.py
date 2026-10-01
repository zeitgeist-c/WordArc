import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import tempfile
import unittest
from unittest import mock

from PyQt6.QtCore import QPoint, QRect, QEvent
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import QApplication, QComboBox

import audio
import config as cfg
import localspeech
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
            mock.patch.object(settings_ui.audio, "refresh_devices"),
            mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]),
            mock.patch.object(settings_ui.startup, "is_enabled", return_value=False),
            mock.patch.object(localspeech.vulkan_speech, "available", return_value=False),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.window = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
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

    def test_dictation_frequent_controls_are_visible_and_advanced_is_closed(self):
        window = self.window
        window.show()
        self.app.processEvents()
        for control in (window.mic, window.language, window.shortcut,
                        window.cleanup_enabled, window.auto_paste,
                        window.dictation_output):
            self.assertTrue(control.isVisibleTo(window))
        self.assertFalse(window.max_seconds.isVisibleTo(window))
        window.dictation_details.setCurrentIndex(0)
        window.dictation_advanced.setCurrentIndex(0)
        self.assertTrue(window.max_seconds.isVisibleTo(window))

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

    def test_saved_microphone_survives_the_merged_device_rows(self):
        """A microphone saved as its MME copy still selects the kept row."""
        window = self.window
        full = "Mikrofon (3- USBGH8-Plus-7.1-ENC)"
        window._fill_device_combo(
            window.mic, [("sd:2:" + full, full)], t("Default microphone"),
            "sd:0:" + full[:settings_ui.audio.MME_NAME_LIMIT])
        self.assertEqual(window.mic.currentData(), "sd:2:" + full)

    def test_saved_hands_free_target_matches_its_row(self):
        """A saved target still matches when the driver line break was lost."""
        window = self.window
        broken = ("Kulaklık (@System32\\drivers\\bthhfenum.sys,#2;%1 "
                  "Hands-Free%0\r\n;(REDMI Buds 8 Lite))")
        window._fill_device_combo(
            window.mic, [("sd:2:" + broken,
                          "Kulaklık (REDMI Buds 8 Lite) — Hands-Free")],
            t("Default microphone"), "sd:2:" + " ".join(broken.split()))
        self.assertEqual(window.mic.currentData(), "sd:2:" + broken)

    def test_reload_lists_devices_that_appeared_later(self):
        """A device plugged in after the window opened shows up on Reload."""
        window = self.window
        with mock.patch.object(settings_ui.audio, "list_sources",
                               return_value=[("sd:2:Bluetooth Mic",
                                              "Bluetooth Mic")]):
            window._refresh_audio_devices()
        texts = [window.mic.itemText(index)
                 for index in range(window.mic.count())]
        self.assertEqual(texts, [t("Default microphone"), "Bluetooth Mic"])
        self.assertEqual(window.mic.itemData(1), "sd:2:Bluetooth Mic")

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
        page = window.tabs.widget(3)
        titles = [box.title() for box in page.findChildren(settings_ui.QGroupBox)]
        for expected in ("Keys", "Speech to text", "Transcript cleanup",
                         "Names and terms", "Interface", "Startup", "Support"):
            self.assertIn(t(expected), titles)
        self.assertFalse(window.ui_language.isVisibleTo(window))
        window.settings_section_menu.setCurrentRow(3)
        self.app.processEvents()
        for control in (window.ui_language, window.corner,
                        window.start_with_windows, window.close_to_tray):
            self.assertTrue(control.isVisibleTo(window), control)

    def test_api_keys_card_layout_and_button_styles(self):
        window = self.window
        self.assertEqual(window.gemini_keys_list.minimumHeight(), 120)
        self.assertEqual(window.gemini_add_button.objectName(), "accentButton")
        self.assertEqual(window.gemini_remove_button.objectName(), "dangerButton")
        card = window.gemini_keys_list.parentWidget()
        self.assertEqual(len(card.findChildren(settings_ui.QPushButton)), 6)
        names = [b.objectName() for b in window.findChildren(settings_ui.QPushButton)]
        self.assertGreaterEqual(names.count("dangerButton"), 4)
        src = pathlib.Path(settings_ui.__file__).read_text(encoding="utf-8")
        self.assertNotIn("Keys are tried from top to bottom and stored only", src)

    def test_key_list_shows_last_used_times(self):
        window = self.window
        window._gemini_keys = ["first-key-aaaa", "second-key-bbbb"]
        window.conf.data["gemini_last_used"] = ["2026-09-27T14:32:11+03:00", ""]
        window._refresh_gemini_keys()
        first = window.gemini_keys_list.item(0).text()
        second = window.gemini_keys_list.item(1).text()
        self.assertIn("API 1", first)
        self.assertNotIn("Varsayılan", first)
        self.assertNotIn("Default", first)
        self.assertIn("27.09.2026 14:32:11", first)
        self.assertIn("API 2", second)
        self.assertIn(t("not used yet"), second)

    def test_showing_window_refreshes_key_usage(self):
        window = self.window
        window._gemini_keys = ["key-1-aaaa"]
        window._refresh_gemini_keys()
        before = window.gemini_keys_list.item(0).text()
        window.conf.data["gemini_last_used"] = ["2026-09-27T14:32:11+03:00"]
        window.show()
        self.app.processEvents()
        after = window.gemini_keys_list.item(0).text()
        window.hide()
        self.assertNotEqual(before, after)
        self.assertIn("27.09.2026 14:32:11", after)

    def test_key_usage_refreshes_while_window_stays_open(self):
        """Açık kalan pencerede damgalar 5 sn'lik tikle tazelenir."""
        window = self.window
        window._gemini_keys = ["key-1-aaaa"]
        window._refresh_gemini_keys()
        before = window.gemini_keys_list.item(0).text()
        window.show()
        self.app.processEvents()
        self.assertTrue(window._usage_timer.isActive())
        window.conf.data["gemini_last_used"] = ["2026-09-27T14:32:11+03:00"]
        window._on_usage_tick()
        after = window.gemini_keys_list.item(0).text()
        window.hide()
        self.assertFalse(window._usage_timer.isActive())
        self.assertNotEqual(before, after)
        self.assertIn("27.09.2026 14:32:11", after)

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

    def test_the_engine_box_starts_on_the_cloud_and_says_what_is_installed(self):
        """Cloud is the default, and the local row only exists when it is chosen."""
        window = self.window
        window.navigate_to("settings")
        self.app.processEvents()
        self.assertEqual(window.transcribe_engine.currentData(), "cloud")
        # A model box the chosen engine ignores is a control that does nothing.
        self.assertFalse(window.local_row.isVisibleTo(window))
        self.assertFalse(window.local_status.isVisibleTo(window))
        self.assertTrue(window.cloud_row.isVisibleTo(window))
        self.assertTrue(window.transcribe_model.isVisibleTo(window))

        window.transcribe_engine.setCurrentIndex(
            window.transcribe_engine.findData("local"))
        self.app.processEvents()
        self.assertTrue(window.local_row.isVisibleTo(window))
        self.assertTrue(window.local_status.isVisibleTo(window))
        self.assertFalse(window.cloud_row.isVisibleTo(window))
        self.assertFalse(window.transcribe_model.isVisibleTo(window))
        # Nothing is downloaded in a test run, so the button is offered.
        self.assertTrue(window.local_download_button.isEnabled())
        self.assertFalse(window.local_remove_button.isEnabled())

    def test_the_box_and_the_status_line_agree_on_the_download_size(self):
        """One number for one file: a user who reads both must not see two."""
        window = self.window
        window.navigate_to("settings")
        window.transcribe_engine.setCurrentIndex(
            window.transcribe_engine.findData("local"))
        for index in range(window.local_stt_model.count()):
            name = window.local_stt_model.itemData(index)
            shown = localspeech.human_size(localspeech.state(name).expected)
            window.local_stt_model.setCurrentIndex(index)
            self.app.processEvents()
            self.assertIn(shown, window.local_stt_model.itemText(index), name)
            # The line under the box is about the model that is selected, so it
            # has to quote the same figure that model carries in the list.
            self.assertIn(shown, window.local_status.text(), name)

    def test_switching_engine_survives_a_save_and_reload(self):
        window = self.window
        window.transcribe_engine.setCurrentIndex(
            window.transcribe_engine.findData("local"))
        window.local_stt_model.setCurrentIndex(
            window.local_stt_model.findData("small"))
        with mock.patch.object(settings_ui.startup, "set_enabled"):
            window._save()
        self.assertEqual(window.conf["transcribe_engine"], "local")
        self.assertEqual(window.conf["local_stt_model"], "small")
        window._load()
        self.assertEqual(window.transcribe_engine.currentData(), "local")
        self.assertEqual(window.local_stt_model.currentData(), "small")

    def test_the_device_box_offers_four_choices_and_survives_a_save(self):
        window = self.window
        self.assertEqual(
            [window.local_stt_device.itemData(index)
             for index in range(window.local_stt_device.count())],
            ["auto", "cuda", "vulkan", "cpu"])
        self.assertEqual(window.local_stt_device.currentData(), "auto")
        window.navigate_to("settings")
        self.app.processEvents()
        self.assertFalse(window.device_row.isVisibleTo(window))
        window.transcribe_engine.setCurrentIndex(
            window.transcribe_engine.findData("local"))
        window.local_stt_device.setCurrentIndex(
            window.local_stt_device.findData("cpu"))
        self.app.processEvents()
        self.assertTrue(window.device_row.isVisibleTo(window))
        self.assertIn("CPU", window.local_device_note.text())
        with mock.patch.object(settings_ui.startup, "set_enabled"):
            window._save()
        self.assertEqual(window.conf["local_stt_device"], "cpu")
        window._load()
        self.assertEqual(window.local_stt_device.currentData(), "cpu")

    def test_the_local_box_names_every_model_and_its_cost(self):
        window = self.window
        self.assertEqual(window.local_stt_model.count(), 3)
        # Each row carries the model's name and what that size costs, so the
        # box answers "which one should I take" without a second look.
        for index, name in enumerate(localspeech.model_names()):
            text = window.local_stt_model.itemText(index)
            note = t(localspeech.MODEL_NOTES[name])
            self.assertIn(f"Whisper {name}", text)
            self.assertIn(note, text)
            self.assertEqual(window.local_stt_model.itemData(index), name)

    def test_saving_a_new_language_rebuilds_the_window(self):
        """The box on the Settings tab does what the header button does.

        Saving a new language used to leave the window standing in the old one
        while the tray menu and the dialogs already spoke the new one.
        """
        import i18n
        window = self.window
        previous = i18n.language()
        fired = []
        window.language_changed.connect(lambda: fired.append(True))
        window._select_data(window.ui_language, "en")
        try:
            with mock.patch.object(settings_ui.startup, "set_enabled"), \
                 mock.patch.object(settings_ui.sounds, "play"), \
                 mock.patch.object(settings_ui.QTimer, "singleShot") as later:
                window._save()
            later.assert_called_once()
            self.assertEqual(later.call_args[0][0], 0)
            self.assertFalse(fired, "the rebuild must not run inside the save")
            later.call_args[0][1]()          # the queued emit
            self.assertTrue(fired)
            self.assertEqual(window.conf["ui_language"], "en")
        finally:
            i18n.set_language(previous)

    def test_a_failed_rescan_keeps_the_devices_already_listed(self):
        """A rescan that cannot read anything must not empty the boxes.

        An emptied box would write the default back over a saved microphone
        the next time Save is pressed.
        """
        window = self.window
        window._fill_device_combo(window.mic, [("sd:2:USB Mic", "USB Mic")],
                                  t("Default microphone"), "sd:2:USB Mic")
        with mock.patch.object(settings_ui.audio, "describe_sources",
                               side_effect=RuntimeError("device list failed")):
            window._refresh_audio_devices()
        self.assertEqual(window.mic.currentData(), "sd:2:USB Mic")
        self.assertEqual(window.mic.count(), 2)

    def test_a_rebuild_lands_on_the_same_page_and_place(self):
        """The language change rebuilds the window; the user should not be able
        to tell beyond the words."""
        window = self.window
        window.resize(900, 620)
        window.move(120, 80)
        window.navigate_to("application")
        self.app.processEvents()
        view = settings_ui.WindowView(window)
        fresh = settings_ui.SettingsWindow(window.conf, "wordarc toggle")
        try:
            view.apply(fresh)
            self.assertEqual(fresh.tabs.currentIndex(), window.tabs.currentIndex())
            self.assertEqual((fresh.width(), fresh.height()), (900, 620))
            self.assertEqual(fresh.settings_section_menu.currentRow(), 3)
        finally:
            fresh.close()
            fresh.deleteLater()

    def test_switching_tabs_keeps_a_maximized_window_maximized(self):
        """The placement check slides the window inside its screen. A maximized
        window is already inside it, and moving it there clears the state, so
        the window fell back to its old size on a tab switch."""
        window = self.window
        window.showMaximized()
        self.app.processEvents()
        window.navigate_to("meeting")
        self.app.processEvents()
        self.assertTrue(window.isMaximized())

    def test_the_placement_check_does_not_grow_a_decorated_window(self):
        """Like must be compared with like.

        The check measured frameGeometry() — title bar and borders included —
        and compared it against width()/x(), which leave the frame out, so a
        decorated window never looked like it was already in place: every tab
        switch called setGeometry() with the frame's size and grew the window
        by the frame.
        """
        window = self.window
        window.show()
        self.app.processEvents()
        window.move(120, 90)
        self.app.processEvents()
        before = window.geometry()
        decorated = before.adjusted(-8, -31, 8, 8)  # frame around the client
        with mock.patch.object(settings_ui.SettingsWindow, "frameGeometry",
                               return_value=decorated):
            window._fit_on_screen(QRect(0, 0, 4000, 3000))
        self.app.processEvents()
        self.assertEqual(window.geometry(), before)

    def test_a_window_off_the_bottom_is_pulled_back_in(self):
        window = self.window
        window.show()
        self.app.processEvents()
        avail = QRect(0, 0, 1200, 800)
        window.resize(700, 900)
        window.move(100, 400)
        self.app.processEvents()
        window._fit_on_screen(avail)
        self.app.processEvents()
        self.assertLessEqual(window.geometry().bottom(), avail.bottom())
        self.assertGreaterEqual(window.geometry().height(), window.minimumHeight())

    def test_a_maximized_rebuild_comes_back_maximized(self):
        window = self.window
        window.showMaximized()
        self.app.processEvents()
        window.navigate_to("meeting")
        self.app.processEvents()
        view = settings_ui.WindowView(window)
        fresh = settings_ui.SettingsWindow(window.conf, "wordarc toggle")
        try:
            view.apply(fresh)
            fresh.show()
            self.app.processEvents()
            self.assertTrue(fresh.isMaximized())
            self.assertEqual(fresh.tabs.currentIndex(), window.tabs.currentIndex())
        finally:
            fresh.close()
            fresh.deleteLater()


class TestTheWindowSurvivesABadAudioLibrary(unittest.TestCase):
    """The device rescan runs while the settings window is being built.

    PortAudio answers a stale pointer with an error for a stream that is
    already over (error -9988). That error came out of the rescan, out of the
    window's constructor, and the language change — which closes the window it
    has before building the new one — left nothing on screen at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_a_rescan_that_raises_still_gives_a_whole_window(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        with mock.patch.object(cfg, "CONFIG_DIR", root / "cfg"), \
             mock.patch.object(cfg, "CONFIG_FILE", root / "cfg" / "config.json"), \
             mock.patch.object(cfg, "DATA_DIR", root / "data"), \
             mock.patch.object(cfg, "HISTORY_FILE", root / "data" / "h.jsonl"), \
             mock.patch.object(cfg, "MEETINGS_DIR", root / "data" / "m"), \
             mock.patch.object(cfg, "MEETINGS_FILE", root / "data" / "m.jsonl"), \
             mock.patch.object(cfg.credential_store, "read", return_value=""), \
             mock.patch.object(cfg.credential_store, "read_all", return_value=[]), \
             mock.patch.object(cfg.credential_store, "write_all"), \
             mock.patch.object(settings_ui.audio, "refresh_devices",
                               side_effect=audio.sd.PortAudioError(
                                   "Invalid stream pointer [PaErrorCode -9988]")), \
             mock.patch.object(settings_ui.audio, "list_sources", return_value=[]), \
             mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]), \
             mock.patch.object(settings_ui.startup, "is_enabled", return_value=False):
            window = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")
        try:
            self.assertEqual(window.tabs.count(), 4)
            self.assertEqual(window.mic.count(), 1)
            self.assertEqual(window.mic.currentData(), "")
            self.assertTrue(window.dictation_output.isReadOnly())
        finally:
            window.close()
            window.deleteLater()


class TestDeviceCards(unittest.TestCase):
    """Long device lists draw as cards: the name, and under it how the device is
    connected. A short list stays a plain row.

    The split exists because a machine with a headset, a USB interface and a
    laptop array shows three near-identical names, and one line each left the
    user opening every row to find out which was which. Two lines say it once.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _devices(count, kinds=None):
        kinds = kinds or ["usb", "built-in", "bluetooth"]
        return [(f"t{i}", f"Mikrofon ({i})", kinds[i % len(kinds)])
                for i in range(count)]

    def _filled(self, items, default="Varsayılan mikrofon", selected="t1"):
        box = settings_ui.FitsOnScreenCombo()
        settings_ui.SettingsWindow._fill_device_combo(
            box, items, default, selected)
        return box

    def test_a_long_device_list_draws_as_cards(self):
        box = self._filled(self._devices(6))
        delegate = box.view().itemDelegate()
        self.assertIsInstance(delegate, settings_ui.DeviceCardDelegate,
                              "a 7-row device list stayed a plain list")

    def test_a_short_list_is_left_plain(self):
        """Two rows have nothing to tell apart, and a card would double the
        height of every such box in the app to say less."""
        box = self._filled([("t0", "Bulut (Gemini)", ""),
                            ("t1", "Yerel (bu bilgisayar)", "")])
        self.assertNotIsInstance(box.view().itemDelegate(),
                                 settings_ui.DeviceCardDelegate)

    def test_the_card_keeps_its_delegate_across_a_rescan(self):
        """Devices are rescanned on every hot-plug. If the delegate did not
        survive the refill, the list would silently fall back to one line and
        the second line would vanish with no error."""
        box = self._filled(self._devices(6))
        settings_ui.SettingsWindow._fill_device_combo(
            box, self._devices(7, ["bluetooth"]), "Varsayılan mikrofon", "t2")
        self.app.processEvents()
        self.assertIsInstance(box.view().itemDelegate(),
                              settings_ui.DeviceCardDelegate)

    def test_the_second_line_is_the_connection_not_the_row_number(self):
        box = self._filled(self._devices(6))
        delegate = box.view().itemDelegate()
        # Row 0 is the "default" entry and carries no connection; row 1 is the
        # first device, and its sub-line is that device's kind.
        self.assertEqual(delegate.connection_text(0), "")
        self.assertEqual(delegate.connection_text(1), "USB")
        self.assertNotIn(",", delegate.connection_text(1),
                         "the (row, text) pair leaked through as the text")

    def test_a_card_row_is_taller_than_a_plain_one(self):
        long_box = self._filled(self._devices(6))
        short_box = self._filled([("t0", "Bulut (Gemini)", ""),
                                  ("t1", "Yerel (bu bilgisayar)", "")])
        self.app.processEvents()
        self.assertGreater(long_box._row_height(), short_box._row_height() + 5,
                           "a card row is the same height as a plain one")

    def test_a_card_row_is_tall_enough_for_both_of_its_lines(self):
        """The height has to fit the name and the label under it. Measuring
        with one font's line spacing left every second line sitting on the
        row below it."""
        from PyQt6.QtWidgets import QStyleOptionViewItem
        box = self._filled(self._devices(6))
        self.app.processEvents()
        delegate = box.view().itemDelegate()
        view = box.view()
        opt = QStyleOptionViewItem()
        opt.font = view.font()
        opt.fontMetrics = view.fontMetrics()
        opt.rect = QRect(0, 0, 300, 100)
        index = view.model().index(1, 0)
        hint = delegate.sizeHint(opt, index)
        small = QFont(view.font())
        small.setPointSizeF(max(8.0, view.font().pointSizeF() - 1.5))
        needed = (QFontMetrics(view.font()).lineSpacing()
                  + QFontMetrics(small).lineSpacing()
                  + settings_ui.DeviceCardDelegate.PAINT_PADDING_TOP
                  + settings_ui.DeviceCardDelegate.PAINT_PADDING_BOTTOM)
        self.assertGreaterEqual(hint.height(), needed,
                                f"card is {hint.height()}px, needs {needed}px")


class TestConnectionGuess(unittest.TestCase):
    """What the card says under a device name, and what it refuses to guess.

    Windows has no field for this, so it is read out of the names PortAudio
    reports. A wrong "USB" on a Bluetooth headset is worse than no second
    line at all, so the guess is only made when something actually matches.
    """

    def test_the_kinds_a_device_can_be(self):
        self.assertEqual(audio._connection_kind("Kulaklık (REDMI Buds 8 Lite) "
                                                "- Hands-Free"),
                         "bluetooth")
        self.assertEqual(audio._connection_kind(
            "Mikrofon (3- USBGH8-Plus-7.1-ENC)"), "usb")
        self.assertEqual(audio._connection_kind(
            "Mikrofon (Realtek HD Audio Mic input)"), "built-in")
        self.assertEqual(audio._connection_kind(
            "Microsoft Ses Eşleştiricisi - Input"), "built-in")

    def test_a_name_that_says_nothing_gets_no_second_line(self):
        self.assertEqual(audio._connection_kind("Karaoke mikrofonu"), "")

    def test_bluetooth_wins_over_a_usb_word_in_the_name(self):
        """A Bluetooth headset can be plugged into a USB port and say so in
        its name; the transport is what matters when choosing where it is."""
        self.assertEqual(
            audio._connection_kind("Kulaklık (USB Kulaklık) Hands-Free"),
            "bluetooth")

    def test_describe_sources_agrees_with_list_sources(self):
        """The card's second line must come from the same device list the
        recording code uses, or the two can name different devices."""
        with mock.patch.object(audio, "list_sources",
                               return_value=[("a", "Mikrofon (USBGH8)"),
                                             ("b", "Kulaklık Hands-Free"),
                                             ("c", "Karaoke")]):
            described = audio.describe_sources()
        self.assertEqual([row[0] for row in described], ["a", "b", "c"])
        self.assertEqual([row[2] for row in described],
                         ["usb", "bluetooth", ""])

    def test_describe_monitors_agrees_with_list_monitors(self):
        with mock.patch.object(audio, "list_monitors",
                               return_value=[("a", "Stereo Karışımı (Realtek)"),
                                             ("b", "Kulaklık Hands-Free")]):
            described = audio.describe_monitors()
        self.assertEqual([row[2] for row in described],
                         ["built-in", "bluetooth"])


class TestPlacementMath(unittest.TestCase):
    """The popup placement decision, without needing a screen.

    _choose_placement is pure arithmetic so the cases a real monitor cannot
    produce on demand — a list taller than both sides — are still pinned down.
    Every result must sit fully inside the screen: a popup pushed off-screen
    is what the user reported as a list showing nothing at all.
    """

    # A plain alias would become a bound method (self counts as an argument);
    # keep it static so the call reads as the arithmetic it is.
    @staticmethod
    def place(*args):
        return settings_ui.FitsOnScreenCombo._choose_placement(*args)

    def assertInside(self, result, screen_top, screen_bottom):
        self.assertIsNotNone(result, "expected a placement, got None")
        top, height = result
        self.assertGreaterEqual(top, screen_top, "hangs off the top")
        self.assertLessEqual(top + height - 1, screen_bottom,
                             "hangs off the bottom")
        self.assertGreater(height, 0, "zero-height popup shows nothing")

    def test_qt_placement_that_fits_is_untouched(self):
        self.assertIsNone(self.place(500, 528, 415, 45, 10, 0, 1031,
                                     528, 943))

    def test_qt_top_overflow_moves_below_the_box(self):
        # Qt lines the selected row up with the box; with a late selection
        # that puts the popup's top above the screen even though the whole
        # list fits below.
        self.assertEqual(self.place(500, 528, 415, 45, 10, 0, 1031,
                                    -100, 315),
                         (528, 415))

    def test_no_room_below_opens_upward_at_full_height(self):
        self.assertEqual(self.place(900, 928, 200, 24, 10, 0, 1031,
                                    928, 1200),
                         (700, 200))

    def test_neither_side_fits_takes_the_roomier_side_shrunk(self):
        # A 415px list, 300px below and 100px above: must come back at most
        # 300 high and fully inside, so it scrolls instead of vanishing.
        result = self.place(100, 128, 415, 45, 10, 0, 399,
                            128, 600)
        self.assertInside(result, 0, 399)
        self.assertLessEqual(result[1], 300 + 1)

    def test_neither_side_fits_above_roomier_opens_upward_shrunk(self):
        result = self.place(300, 328, 415, 45, 10, 0, 399,
                            -200, 215)
        self.assertInside(result, 0, 399)
        self.assertLessEqual(result[1], 300 + 1)

    def test_result_always_inside_across_a_sweep(self):
        for screen_h in (600, 800, 1032, 1392):
            bottom = screen_h - 1
            for box_top in (20, 200, 500, 900, 1200):
                if box_top >= bottom:
                    continue
                for full in (91, 200, 415, 900):
                    result = self.place(box_top, box_top + 28, full, 45, 10,
                                        0, bottom, box_top + 28,
                                        box_top + 28 + full)
                    if result is not None:
                        self.assertInside(result, 0, bottom)


class TestDropdownsStayOnScreen(unittest.TestCase):
    """A combo's popup opens where its box is, and Qt clips whatever hangs off
    the screen rather than opening upward. A dropdown in the last row of the
    settings window on a short screen therefore showed its final item sliced in
    half — the report that started this."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _open(self, box, avail_bottom):
        """Open the popup and report how far it hangs off the screen."""
        box.showPopup()
        self.app.processEvents()
        rect = box.view().window().geometry()
        box.hidePopup()
        self.app.processEvents()
        return rect.bottom() - avail_bottom, -rect.top()

    def test_all_lists_use_the_same_picker(self):
        for count in (2, 4, 7, 44):
            box = settings_ui.FitsOnScreenCombo()
            box.addItems([f"item {index}" for index in range(count)])
            with mock.patch.object(box, "_search_picker") as picker, \
                 mock.patch.object(QComboBox, "showPopup") as native:
                box.showPopup()
            self.assertEqual(picker.call_count, 1)
            self.assertEqual(native.call_count, 0)

    def test_every_settings_combo_is_protected(self):
        """Applied everywhere rather than patched per screenshot: which
        dropdown breaks depends on where the window sits and how tall the
        screen is, and neither is knowable until the click."""
        tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(tmp.name)
        with mock.patch.object(cfg, "CONFIG_DIR", root / "cfg"), \
             mock.patch.object(cfg, "CONFIG_FILE", root / "cfg" / "config.json"), \
             mock.patch.object(cfg, "DATA_DIR", root / "data"), \
             mock.patch.object(cfg, "HISTORY_FILE", root / "data" / "h.jsonl"), \
             mock.patch.object(cfg, "MEETINGS_DIR", root / "data" / "m"), \
             mock.patch.object(cfg, "MEETINGS_FILE", root / "data" / "m.jsonl"), \
             mock.patch.object(cfg.credential_store, "read", return_value=""), \
             mock.patch.object(cfg.credential_store, "read_all", return_value=[]), \
             mock.patch.object(cfg.credential_store, "write_all"), \
             mock.patch.object(settings_ui.audio, "list_sources", return_value=[]), \
             mock.patch.object(settings_ui.audio, "refresh_devices"), \
             mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]), \
             mock.patch.object(settings_ui.startup, "is_enabled", return_value=False):
            window = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")
        try:
            protected = window.findChildren(settings_ui.FitsOnScreenCombo)
            plain = [b for b in window.findChildren(QComboBox)
                     if not isinstance(b, settings_ui.FitsOnScreenCombo)]
            self.assertGreater(len(protected), 10, "expected the settings combos")
            self.assertEqual(plain, [], "a plain QComboBox is left unprotected")
        finally:
            window.deleteLater()
