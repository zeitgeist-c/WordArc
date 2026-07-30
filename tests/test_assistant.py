import unittest, os, json, tempfile, pathlib
import config as cfg

class TestAssistantSession(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data = cfg.DATA_DIR
        cfg.DATA_DIR = pathlib.Path(self.tmp.name)
        cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
        import assistant
        self.assistant = assistant
        assistant.SESSION_FILE = cfg.DATA_DIR / "assistant.json"
    def tearDown(self):
        self.tmp.cleanup()
        cfg.DATA_DIR = self.old_data
    def test_write_then_read_session(self):
        self.assistant.write_session("claude", session="abc-123")
        self.assertEqual(self.assistant.read_session("claude", 3600), "abc-123")
    def test_provider_filter(self):
        self.assistant.write_session("claude", session="abc")
        self.assertEqual(self.assistant.read_session("codex", 3600), "")
    def test_expiry(self):
        self.assistant.write_session("claude", session="abc")
        self.assertEqual(self.assistant.read_session("claude", -1), "")
    def test_clear(self):
        self.assistant.write_session("claude", session="abc")
        self.assistant.clear_session()
        self.assertEqual(self.assistant.read_session("claude", 3600), "")

class TestProviderHelpers(unittest.TestCase):
    def test_provider_default(self):
        import assistant, config as cfg
        c = cfg.Config()
        self.assertIn(assistant.provider(c), ("claude", "codex"))
    def test_executable_mapping(self):
        import assistant
        self.assertEqual(assistant.executable("claude"), "claude")
        self.assertEqual(assistant.executable("codex"), "codex")

if __name__ == "__main__":
    unittest.main()
