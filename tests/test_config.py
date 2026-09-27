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

    def test_plaintext_key_is_migrated_to_credential_store_on_load(self):
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_text(json.dumps({"gemini_api_key": "legacy-plain"}), encoding="utf-8")
        stored = {"value": ""}
        with mock.patch.object(cfg.credential_store, "write",
                               side_effect=lambda value: stored.update(value=value)):
            c = cfg.Config()
        self.assertEqual(stored["value"], "legacy-plain")
        self.assertEqual(c["gemini_api_key"], "")
        payload = json.loads(cfg.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual(payload["gemini_api_key"], "")

    def test_plaintext_key_stays_when_credential_store_unavailable(self):
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_text(json.dumps({"gemini_api_key": "legacy-plain"}), encoding="utf-8")
        with mock.patch.object(cfg.credential_store, "write",
                               side_effect=cfg.credential_store.CredentialError("unavailable")):
            c = cfg.Config()
        self.assertEqual(c["gemini_api_key"], "legacy-plain")
        payload = json.loads(cfg.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual(payload["gemini_api_key"], "legacy-plain")

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

    def test_a_settings_file_in_another_encoding_does_not_stop_the_app(self):
        """A UnicodeDecodeError is not a JSONDecodeError.

        It escaped load() and reached main(), which meant no window and no log:
        the file is now read as far as it can be, and a copy is kept.
        """
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_bytes(
            '{"cleanup_prompt": "açıklama"}'.encode("cp1254"))
        c = cfg.Config()
        self.assertEqual(c["cleanup_prompt"], cfg.DEFAULTS["cleanup_prompt"])
        kept = cfg.CONFIG_FILE.parent / (cfg.CONFIG_FILE.name + ".corrupt")
        self.assertTrue(kept.exists(), "okunamayan ayar dosyası saklanmalı")

    def test_a_setting_of_the_wrong_type_falls_back_to_its_default(self):
        """A hand-edited file can hold a number where a string belongs, and the
        strip()/int() calls that read it took the app down before it opened."""
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_text(
            json.dumps({"cleanup_prompt": None, "history_limit": "many"}),
            encoding="utf-8")
        c = cfg.Config()
        self.assertEqual(c["cleanup_prompt"], cfg.DEFAULTS["cleanup_prompt"])
        self.assertEqual(c["history_limit"], cfg.DEFAULTS["history_limit"])
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
    def test_participants_dedupe_turkish_case_variants(self):
        c = cfg.Config()
        c.data["meeting_self_name"] = "İSMAİL"
        c.data["meeting_other_name"] = ""
        c.data["meeting_participants"] = "İsmail, ALEX, alex"
        self.assertEqual(c.participants(), "İSMAİL\nALEX")
    def test_participants_keep_distinct_names(self):
        c = cfg.Config()
        c.data["meeting_self_name"] = "Alex"
        c.data["meeting_other_name"] = "Ayşe"
        c.data["meeting_participants"] = ""
        self.assertEqual(c.participants(), "Alex\nAyşe")

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

class TestApiRotation(unittest.TestCase):
    def test_rotation_defaults_exist(self):
        self.assertIn("gemini_next_slot", cfg.DEFAULTS)
        self.assertIn("gemini_last_used", cfg.DEFAULTS)
        self.assertEqual(cfg.DEFAULTS["gemini_next_slot"], 0)
        self.assertEqual(cfg.DEFAULTS["gemini_last_used"], [])

    def _fresh_conf(self, n_keys, next_slot=0):
        conf = cfg.Config.__new__(cfg.Config)
        conf.data = dict(cfg.DEFAULTS)
        conf.data["gemini_next_slot"] = next_slot
        conf.data["gemini_last_used"] = [""] * n_keys
        return conf

    def test_claim_returns_next_slot_without_advancing(self):
        conf = self._fresh_conf(n_keys=3, next_slot=2)
        self.assertEqual(conf.claim_api_slot(3), 2)
        self.assertEqual(conf.claim_api_slot(3), 2)

    def test_claim_wraps_and_clamps(self):
        self.assertEqual(self._fresh_conf(1).claim_api_slot(1), 0)
        self.assertEqual(self._fresh_conf(2, next_slot=99).claim_api_slot(2), 0)
        self.assertEqual(self._fresh_conf(2, next_slot=-1).claim_api_slot(2), 0)
        self.assertEqual(self._fresh_conf(0).claim_api_slot(0), 0)

    def test_record_success_advances_and_stamps(self):
        conf = self._fresh_conf(n_keys=3, next_slot=2)
        with mock.patch.object(cfg.Config, "save"):
            conf.record_api_success(2, n_keys=3)
        self.assertEqual(conf["gemini_next_slot"], 0)
        self.assertRegex(conf["gemini_last_used"][2],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertEqual(conf["gemini_last_used"][:2], ["", ""])

    def test_record_attempt_advances_without_stamp(self):
        conf = self._fresh_conf(n_keys=2, next_slot=0)
        with mock.patch.object(cfg.Config, "save"):
            conf.record_api_attempt(0, n_keys=2)
        self.assertEqual(conf["gemini_next_slot"], 1)
        self.assertEqual(conf["gemini_last_used"], ["", ""])

    def test_record_normalises_shorter_stamp_list(self):
        conf = self._fresh_conf(n_keys=1, next_slot=0)
        with mock.patch.object(cfg.Config, "save"):
            conf.record_api_success(1, n_keys=2)
        self.assertEqual(len(conf["gemini_last_used"]), 2)
        self.assertEqual(conf["gemini_last_used"][0], "")
        self.assertEqual(conf["gemini_next_slot"], 0)

    def test_record_save_failure_does_not_raise(self):
        conf = self._fresh_conf(n_keys=2, next_slot=0)
        with mock.patch.object(cfg.Config, "save", side_effect=OSError("disk full")):
            conf.record_api_success(0, n_keys=2)
        self.assertEqual(conf["gemini_next_slot"], 1)

if __name__ == "__main__":
    unittest.main()
