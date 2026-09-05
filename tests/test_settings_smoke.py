import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import tempfile
import unittest
from unittest import mock

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
        window.header_theme.setCurrentIndex(window.header_theme.findData("light"))
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
             mock.patch.object(settings_ui.QMessageBox, "information"):
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
             mock.patch.object(settings_ui.QMessageBox, "information"):
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
        ), mock.patch.object(settings_ui.QMessageBox, "warning") as warning, \
             mock.patch.object(settings_ui.QMessageBox, "information") as information:
            window._save()
        warning.assert_called_once()
        information.assert_not_called()
        applied.assert_not_called()

    def test_minimum_size_has_no_horizontal_or_nested_page_scrollers(self):
        window = self.window
        window.resize(760, 560)
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

    def test_meeting_uses_section_cards(self):
        window = self.window
        window.navigate_to("meeting")
        cards = window.tabs.widget(1).findChildren(settings_ui.QGroupBox)
        titles = [card.title() for card in cards]
        for expected in ("Sound", "Who is talking", "Minutes", "Recording",
                         "Minutes instruction", "Minutes"):
            self.assertIn(t(expected), titles)
