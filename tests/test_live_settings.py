"""Settings tests for the live engine (Task 13)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import tempfile
import unittest
from unittest import mock

from PyQt6.QtWidgets import QApplication

import config as cfg
import localspeech
import settings_ui


class TestLiveEngineSettings(unittest.TestCase):
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
            mock.patch.object(localspeech.vulkan_speech, "available",
                              return_value=False),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._stop_patchers)
        self.window = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")
        self.window.show()

    def _stop_patchers(self):
        for patcher in self.patchers:
            patcher.stop()

    def _select_engine(self, value):
        index = self.window.transcribe_engine.findData(value)
        self.assertGreaterEqual(index, 0, f"motor yok: {value}")
        self.assertTrue(self.window.navigate_to("shared_ai"))
        self.window.show()
        self.app.processEvents()
        self.window.transcribe_engine.setCurrentIndex(index)
        self.app.processEvents()

    def test_engine_box_offers_cloud_live_and_local(self):
        values = [self.window.transcribe_engine.itemData(i)
                  for i in range(self.window.transcribe_engine.count())]
        self.assertEqual(values, ["cloud", "live", "local"])

    def test_live_engine_shows_live_row_only(self):
        self._select_engine("live")
        self.assertTrue(self.window.live_row.isVisibleTo(self.window))
        self.assertFalse(self.window.cloud_row.isVisibleTo(self.window))
        self.assertFalse(self.window.local_row.isVisibleTo(self.window))

    def test_cloud_engine_hides_live_row(self):
        self._select_engine("cloud")
        self.assertFalse(self.window.live_row.isVisibleTo(self.window))
        self.assertTrue(self.window.cloud_row.isVisibleTo(self.window))

    def test_live_settings_roundtrip_through_save_and_load(self):
        conf = self.window.conf
        self._select_engine("live")
        mode_index = self.window.live_transcription_mode.findData("verbatim")
        self.window.live_transcription_mode.setCurrentIndex(mode_index)
        self.window._save()
        self.assertEqual(conf["transcribe_engine"], "live")
        self.assertEqual(conf["live_transcription_mode"], "verbatim")
        fresh = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")
        fresh._load()
        self.assertEqual(fresh.transcribe_engine.currentData(), "live")
        self.assertEqual(fresh.live_transcription_mode.currentData(),
                         "verbatim")
        fresh.close()

    def tearDown(self):
        self.window.close()
