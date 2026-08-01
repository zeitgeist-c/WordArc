import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import tempfile
import unittest
from unittest import mock

from PyQt6.QtWidgets import QApplication, QLineEdit

import config as cfg
import settings_ui


class TestSettingsSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_settings_construct_with_secure_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with mock.patch.object(cfg, "CONFIG_DIR", root / "cfg"), \
                 mock.patch.object(cfg, "CONFIG_FILE", root / "cfg" / "config.json"), \
                 mock.patch.object(cfg, "DATA_DIR", root / "data"), \
                 mock.patch.object(cfg, "HISTORY_FILE", root / "data" / "history.jsonl"), \
                 mock.patch.object(cfg, "MEETINGS_DIR", root / "data" / "meetings"), \
                 mock.patch.object(cfg, "MEETINGS_FILE", root / "data" / "meetings.jsonl"), \
                 mock.patch.object(cfg.credential_store, "read", return_value=""), \
                 mock.patch.object(settings_ui.audio, "list_sources", return_value=[]), \
                 mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]):
                window = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")
                try:
                    self.assertTrue(window.windowTitle().startswith("WordArc"))
                    self.assertGreaterEqual(window.width(), 920)
                    self.assertGreaterEqual(window.height(), 700)
                    self.assertEqual(window.tabs.count(), 9)
                    self.assertFalse(window.history_enabled.isChecked())
                    self.assertEqual(window.gemini_key.echoMode(),
                                     QLineEdit.EchoMode.Password)
                    self.assertEqual(window.transcribe_model.currentText(),
                                     "gemini-3.5-flash-lite")
                    window.header_theme.setCurrentIndex(
                        window.header_theme.findData("light"))
                    self.assertEqual(window.conf["theme_mode"], "light")
                    self.assertEqual(self.app.property("wordarcTheme"), "light")
                    self.assertEqual(window.general_theme.currentData(), "light")
                finally:
                    window.close()
