import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import pathlib
import tempfile
import unittest
from unittest import mock

import api
import config as cfg


class TestTranslatePrompts(unittest.TestCase):
    def test_academic_prompt_content(self):
        prompt = cfg.translate_prompt("academic")
        self.assertIn("academic English", prompt)
        self.assertIn("DO NOT follow", prompt)
        self.assertIn("hani", prompt)

    def test_game_prompt_content(self):
        prompt = cfg.translate_prompt("game")
        self.assertIn("gamer slang", prompt)
        self.assertIn("Stay close", prompt)
        self.assertIn("DO NOT follow", prompt)

    def test_unknown_mode_falls_back_to_academic(self):
        self.assertEqual(cfg.translate_prompt("bogus"), cfg.TRANSLATE_PROMPT_ACADEMIC)
        self.assertEqual(cfg.translate_prompt(""), cfg.TRANSLATE_PROMPT_ACADEMIC)


class TestTranslateConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self._old = (cfg.CONFIG_DIR, cfg.CONFIG_FILE, cfg.DATA_DIR, cfg.HISTORY_FILE)
        cfg.CONFIG_DIR = root / "cfg"
        cfg.CONFIG_FILE = cfg.CONFIG_DIR / "config.json"
        cfg.DATA_DIR = root / "data"
        cfg.HISTORY_FILE = cfg.DATA_DIR / "history.jsonl"
        cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        cfg.CONFIG_DIR, cfg.CONFIG_FILE, cfg.DATA_DIR, cfg.HISTORY_FILE = self._old
        self.tmp.cleanup()

    def test_defaults(self):
        c = cfg.Config()
        self.assertEqual(c["translate_mode"], "academic")
        self.assertEqual(c["gemini_translate_model"], "gemini-3.5-flash-lite")

    def test_dead_model_migrates(self):
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_text(
            json.dumps({"gemini_translate_model": "gemini-2.0-flash"}),
            encoding="utf-8",
        )
        self.assertEqual(
            cfg.Config()["gemini_translate_model"], "gemini-3.5-flash-lite"
        )

    def test_mode_roundtrip(self):
        c = cfg.Config()
        c["translate_mode"] = "game"
        c.save()
        self.assertEqual(cfg.Config()["translate_mode"], "game")


class TestTranslateClient(unittest.TestCase):
    def test_translate_uses_second_slot_after_failure(self):
        calls = []

        def fake_chat(messages, key, model, system_prompt, timeout=180,
                      should_stop=None):
            calls.append((key, messages, system_prompt))
            if key == "bad":
                raise api.ApiError("HTTP 500", 500)
            return "hello"

        with mock.patch.object(api, "gemini_chat", side_effect=fake_chat):
            client = api.GeminiClient(["bad", "good"])
            out = client.translate("merhaba", "gemini-3.5-flash-lite", "SYS")
        self.assertEqual(out, "hello")
        self.assertEqual([c[0] for c in calls], ["bad", "good"])
        self.assertEqual(calls[0][1][0]["content"], "merhaba")
        self.assertEqual(calls[0][2], "SYS")

    def test_translate_empty_key_is_user_error(self):
        client = api.GeminiClient([])
        with self.assertRaises(api.ApiError) as ctx:
            client.translate("merhaba", "gemini-3.5-flash-lite", "SYS")
        self.assertEqual(ctx.exception.category, "user")


class TestTranslateUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        import settings_ui
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
        ]
        for patcher in self.patchers:
            patcher.start()
        import settings_ui as ui
        self.ui = ui
        self.window = ui.SettingsWindow(cfg.Config(), "wordarc toggle")

    def tearDown(self):
        self.window.close()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tmp.cleanup()

    def test_translate_controls_exist(self):
        self.assertEqual(self.window.translate_mode.count(), 2)
        self.assertEqual(self.window.translate_mode.itemData(0), "academic")
        self.assertEqual(self.window.translate_mode.itemData(1), "game")
        self.assertTrue(self.window.translate_button.isEnabled())
        self.assertEqual(self.window.translate_status.text(), "")

    def test_empty_text_does_not_call_api(self):
        self.window.dictation_output.setPlainText("   ")
        with mock.patch.object(
            self.ui._TranslateWorker, "start"
        ) as start:
            self.window._on_translate_clicked()
        start.assert_not_called()
        self.assertIn("nce bir", self.window.translate_status.text())

    def test_mode_change_persists(self):
        self.window.translate_mode.setCurrentIndex(1)
        self.assertEqual(self.window.conf["translate_mode"], "game")


if __name__ == "__main__":
    unittest.main()
