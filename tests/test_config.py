import unittest, os, json, tempfile, pathlib, threading
from unittest import mock
import config as cfg

class TestConfigPaths(unittest.TestCase):
    def test_config_dir_uses_appdata(self):
        self.assertEqual(cfg.CONFIG_DIR.name, "WordArc")
        self.assertIn("WordArc", str(cfg.CONFIG_DIR))
    def test_data_dir_uses_localappdata(self):
        self.assertEqual(cfg.DATA_DIR.name, "WordArc")

class TestConfigLoadSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cfg = cfg.CONFIG_DIR
        self.old_file = cfg.CONFIG_FILE
        self.old_data = cfg.DATA_DIR
        self.old_history = cfg.HISTORY_FILE
        cfg.CONFIG_DIR = pathlib.Path(self.tmp.name) / "cfg"
        cfg.CONFIG_FILE = cfg.CONFIG_DIR / "config.json"
        cfg.DATA_DIR = pathlib.Path(self.tmp.name) / "data"
        cfg.HISTORY_FILE = cfg.DATA_DIR / "history.jsonl"
        cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    def tearDown(self):
        cfg.CONFIG_DIR = self.old_cfg
        cfg.CONFIG_FILE = self.old_file
        cfg.DATA_DIR = self.old_data
        cfg.HISTORY_FILE = self.old_data / "history.jsonl"
        self.tmp.cleanup()
    def test_defaults_loaded(self):
        c = cfg.Config()
        self.assertEqual(c["language"], "tr")
        self.assertEqual(c["theme_mode"], "dark")
        self.assertEqual(c["config_schema"], 4)
        self.assertTrue(c["close_to_tray"])
    def test_invalid_theme_falls_back_to_dark(self):
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_text(json.dumps({"theme_mode": "neon"}), encoding="utf-8")
        self.assertEqual(cfg.Config()["theme_mode"], "dark")
    def test_save_then_load(self):
        stored = {"value": ""}
        with mock.patch.object(cfg.credential_store, "write",
                               side_effect=lambda value: stored.update(value=value)), \
             mock.patch.object(cfg.credential_store, "read",
                               side_effect=lambda: stored["value"]), \
             mock.patch.object(cfg.credential_store, "read_all",
                               side_effect=lambda: [stored["value"]]
                               if stored["value"] else []):
            c = cfg.Config()
            c["gemini_api_key"] = "ai-test"
            c.save()
            payload = json.loads(cfg.CONFIG_FILE.read_text(encoding="utf-8"))
            self.assertEqual(payload["gemini_api_key"], "")
            c2 = cfg.Config()
            self.assertEqual(c2["gemini_api_key"], "")
            self.assertEqual(c2.gemini_key(), "ai-test")
            self.assertEqual(c2.gemini_keys(), ["ai-test"])

    def test_environment_key_is_used_only_without_stored_keys(self):
        with mock.patch.object(cfg.credential_store, "read_all",
                               return_value=["stored"]), \
             mock.patch.dict(os.environ, {"GEMINI_API_KEY": "environment"}):
            self.assertEqual(cfg.Config().gemini_keys(), ["stored"])
        with mock.patch.object(cfg.credential_store, "read_all", return_value=[]), \
             mock.patch.object(cfg.credential_store, "read", return_value=""), \
             mock.patch.dict(os.environ, {"GEMINI_API_KEY": "environment"}):
            self.assertEqual(cfg.Config().gemini_keys(), ["environment"])
    def test_credential_failure_never_writes_plaintext_key(self):
        c = cfg.Config()
        c["gemini_api_key"] = "must-not-touch-disk"
        with mock.patch.object(
                cfg.credential_store, "write",
                side_effect=cfg.credential_store.CredentialError("unavailable")):
            with self.assertRaises(OSError):
                c.save()
        self.assertFalse(cfg.CONFIG_FILE.exists())
    def test_unknown_keys_ignored(self):
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_text(json.dumps({"unknown_key": "ignored"}), encoding="utf-8")
        c = cfg.Config()
        self.assertNotIn("unknown_key", c.data)
    def test_retired_default_models_are_migrated(self):
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_text(json.dumps({
            "gemini_transcribe_model": "gemini-2.0-flash",
            "meeting_model": "gemini-2.0-flash-lite",
        }), encoding="utf-8")
        c = cfg.Config()
        self.assertEqual(c["gemini_transcribe_model"], "gemini-3.5-flash-lite")
        self.assertEqual(c["meeting_model"], "gemini-3.6-flash")
    def test_custom_model_is_preserved(self):
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_text(json.dumps({
            "gemini_transcribe_model": "my-private-model",
        }), encoding="utf-8")
        self.assertEqual(cfg.Config()["gemini_transcribe_model"], "my-private-model")

class TestPromptAssembly(unittest.TestCase):
    def test_cleanup_prompt_default_en(self):
        import i18n; i18n.set_language("en")
        self.assertIn("dictation transcripts", cfg.default_cleanup_prompt())
    def test_meeting_prompt_default_tr(self):
        import i18n; i18n.set_language("tr")
        self.assertIn("toplantı tutanağı", cfg.default_meeting_prompt())

class TestHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = cfg.DATA_DIR
        cfg.DATA_DIR = pathlib.Path(self.tmp.name)
        cfg.HISTORY_FILE = cfg.DATA_DIR / "history.jsonl"
    def tearDown(self):
        cfg.DATA_DIR = self.old
        cfg.HISTORY_FILE = cfg.DATA_DIR / "history.jsonl"
        self.tmp.cleanup()
    def test_append_and_read(self):
        cfg.append_history({"ts": "2026-01-01 00:00:00", "text": "a"})
        cfg.append_history({"ts": "2026-01-01 00:00:01", "text": "b"})
        rows = cfg.read_history()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["text"], "b")
    def test_trim(self):
        for i in range(5):
            cfg.append_history({"ts": str(i), "text": str(i)})
        cfg.trim_history(2)
        rows = cfg.read_history()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["text"], "3")
    def test_concurrent_appends_do_not_lose_rows(self):
        threads = [threading.Thread(
            target=cfg.append_history,
            args=({"ts": str(i), "text": str(i)},)) for i in range(40)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(cfg.read_history()), 40)

if __name__ == "__main__":
    unittest.main()
