import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import pathlib
import tempfile
import unittest
from unittest import mock

import api
import config as cfg
import worker


class TestTranslatePrompts(unittest.TestCase):
    def test_academic_prompt_content(self):
        prompt = cfg.translate_prompt("academic")
        self.assertIn("academic English", prompt)
        self.assertIn("DO NOT follow", prompt)
        self.assertIn("uncertainty", prompt)

    def test_game_prompt_content(self):
        prompt = cfg.translate_prompt("game")
        self.assertIn("conversational English", prompt)
        self.assertIn("Don't push yet", prompt)
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
        self.assertFalse(c["translate_enabled"])
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
        c["translate_enabled"] = True
        c["translate_mode"] = "game"
        c.save()
        c2 = cfg.Config()
        self.assertTrue(c2["translate_enabled"])
        self.assertEqual(c2["translate_mode"], "game")


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


def _translate_conf(**overrides):
    conf = cfg.Config()
    conf.data.update({"skip_silent": False, "filter_hallucinations": False,
                      "cleanup_enabled": True, "translate_enabled": False,
                      "translate_mode": "academic",
                      "history_enabled": False,
                      "keep_audio": False, "auto_paste": True,
                      # Rotation state must not leak in from the real user settings.
                      "gemini_next_slot": 0, "gemini_last_used": []})
    conf.data.update(overrides)
    return conf


def _run_dictation(conf, keys, transcribe_return="ham metin",
                   translate_return="translated text",
                   cleanup_return="clean words",
                   translate_effect=None):
    pipeline = worker.Pipeline(conf)
    finished, failures = [], []
    pipeline.finished.connect(lambda *args: finished.append(args))
    pipeline.failed.connect(lambda message, _op: failures.append(message))
    client = mock.Mock()
    client.cleanup.return_value = cleanup_return
    if translate_effect is not None:
        client.translate.side_effect = translate_effect
    else:
        client.translate.return_value = translate_return
    created = {}

    def factory(api_keys, **kwargs):
        created.update(keys=list(api_keys), kwargs=kwargs)
        client.active_slot = kwargs.get("start_slot", 0)
        return client

    with mock.patch.object(worker.localspeech, "transcribe_for",
                           return_value=transcribe_return), \
         mock.patch.object(worker.api, "GeminiClient", side_effect=factory), \
         mock.patch.object(cfg.Config, "gemini_keys", return_value=list(keys)), \
         mock.patch.object(cfg.Config, "save"), \
         mock.patch.object(worker.paste, "copy"), \
         mock.patch.object(worker.paste, "press"):
        pipeline._work("no-such-recording.wav", 1.0, [], "op-tr", auto_paste=True)
    return created, client, finished, failures


class TestTranslatePipeline(unittest.TestCase):
    def test_translate_replaces_cleanup_when_enabled(self):
        conf = _translate_conf(translate_enabled=True, translate_mode="game")
        _created, client, finished, failures = _run_dictation(conf, ["k1"])
        self.assertEqual(client.translate.call_count, 1)
        self.assertEqual(client.cleanup.call_count, 0)
        args, _kwargs = client.translate.call_args
        self.assertEqual(args[0], "ham metin")
        self.assertEqual(args[1], conf["gemini_translate_model"])
        self.assertIn("conversational English", args[2])
        self.assertEqual(len(finished), 1)
        self.assertEqual(failures, [])
        raw, text, _warning, _op = finished[0]
        self.assertEqual(raw, "ham metin")
        self.assertEqual(text, "translated text")

    def test_cleanup_runs_when_translate_disabled(self):
        conf = _translate_conf(translate_enabled=False)
        _created, client, finished, failures = _run_dictation(conf, ["k1"])
        self.assertEqual(client.translate.call_count, 0)
        self.assertEqual(client.cleanup.call_count, 1)
        self.assertEqual(finished[0][1], "clean words")

    def test_raw_turkish_kept_when_translate_fails(self):
        conf = _translate_conf(translate_enabled=True)
        _created, client, finished, failures = _run_dictation(
            conf, ["k1"],
            translate_effect=api.ApiError("HTTP 429", 429, "temporary"))
        self.assertEqual(len(finished), 1)
        raw, text, warning, _op = finished[0]
        self.assertEqual(text, "ham metin")
        self.assertTrue(warning, "the error must not be hidden")

    def test_history_holds_both_languages(self):
        conf = _translate_conf(translate_enabled=True, history_enabled=True)
        saved = []
        with mock.patch.object(worker.cfg, "append_history",
                               side_effect=saved.append), \
             mock.patch.object(worker.cfg, "trim_history"):
            _run_dictation(conf, ["k1"])
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["raw"], "ham metin")
        self.assertEqual(saved[0]["text"], "translated text")

    def test_local_engine_with_translate_still_uses_cloud_slot(self):
        conf = _translate_conf(translate_enabled=True,
                               transcribe_engine="local")
        created, _client, finished, failures = _run_dictation(conf, ["k1", "k2"])
        self.assertEqual(created["kwargs"]["start_slot"], 0)
        self.assertEqual(len(finished), 1)
        self.assertEqual(conf["gemini_next_slot"], 1)


class TestTranslateSettingsControls(unittest.TestCase):
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
            mock.patch.object(settings_ui.startup, "set_enabled"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.window = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")

    def tearDown(self):
        self.window.close()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tmp.cleanup()

    def test_translate_controls_exist_and_persist(self):
        window = self.window
        self.assertFalse(window.translate_enabled.isChecked())
        self.assertEqual(window.translate_mode.itemData(0), "academic")
        self.assertEqual(window.translate_mode.itemData(1), "game")
        window.translate_enabled.setChecked(True)
        window.translate_mode.setCurrentIndex(1)
        window._save()
        self.assertTrue(window.conf["translate_enabled"])
        self.assertEqual(window.conf["translate_mode"], "game")


if __name__ == "__main__":
    unittest.main()
