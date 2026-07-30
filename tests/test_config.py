import unittest, os, json, tempfile, pathlib
import config as cfg

class TestConfigPaths(unittest.TestCase):
    def test_config_dir_uses_appdata(self):
        self.assertEqual(cfg.CONFIG_DIR.name, "Verbatim")
        self.assertIn("Verbatim", str(cfg.CONFIG_DIR))
    def test_data_dir_uses_localappdata(self):
        self.assertEqual(cfg.DATA_DIR.name, "Verbatim")

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
    def test_save_then_load(self):
        c = cfg.Config()
        c["gemini_api_key"] = "ai-test"
        c.save()
        c2 = cfg.Config()
        self.assertEqual(c2["gemini_api_key"], "ai-test")
    def test_unknown_keys_ignored(self):
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_text(json.dumps({"unknown_key": "ignored"}), encoding="utf-8")
        c = cfg.Config()
        self.assertNotIn("unknown_key", c.data)

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

if __name__ == "__main__":
    unittest.main()