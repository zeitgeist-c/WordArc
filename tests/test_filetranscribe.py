import unittest
from unittest import mock
import api
import config as cfg
import filetranscribe

class TestTimestamps(unittest.TestCase):
    def test_format_timestamp_under_hour(self):
        self.assertEqual(filetranscribe.format_timestamp(75), "01:15")
    def test_format_timestamp_over_hour(self):
        self.assertEqual(filetranscribe.format_timestamp(3661), "1:01:01")
    def test_srt_timestamp(self):
        self.assertEqual(filetranscribe.srt_timestamp(3661.234),
                         "01:01:01,234")

class TestToSrt(unittest.TestCase):
    def test_to_srt_basic(self):
        text = "[00:00] Hello\n[00:03] World\n"
        segs = [(0.0, 3.0, "Hello"), (3.0, 6.0, "World")]
        srt = filetranscribe.to_srt(text, segs)
        self.assertIn("1\n00:00:00,000 --> 00:00:03,000\nHello", srt)
        self.assertIn("2\n00:00:03,000 --> 00:00:06,000\nWorld", srt)
    def test_to_srt_empty(self):
        self.assertEqual(filetranscribe.to_srt("", []), "")

class TestSplitText(unittest.TestCase):
    def test_short_text_single_block(self):
        self.assertEqual(filetranscribe.split_text("short", False), ["short"])
    def test_long_text_splits(self):
        text = "a" * 100 + "\n" + "b" * 100 + "\n" + "c" * 100
        blocks = filetranscribe.split_text(text, True)
        self.assertIsInstance(blocks, list)
        self.assertTrue(all(blocks))

class TestApiRotation(unittest.TestCase):
    def _run_file(self, conf, keys, client, do_cleanup=False):
        worker = filetranscribe.FileTranscriber(conf)
        finished, failures = [], []
        worker.finished.connect(lambda *args: finished.append(args))
        worker.failed.connect(lambda message: failures.append(message))
        created = {}
        def factory(api_keys, **kwargs):
            created.update(keys=list(api_keys), kwargs=kwargs)
            client.active_slot = kwargs.get("start_slot", 0)
            return client
        with mock.patch.object(filetranscribe, "_to_wav",
                               return_value="x.wav"), \
             mock.patch.object(filetranscribe, "split_wav",
                               return_value=[("c.wav", 0.0)]), \
             mock.patch.object(filetranscribe.localspeech, "transcribe_for",
                               return_value=[(0.0, 0.0, "hello")]), \
             mock.patch.object(filetranscribe, "wav_duration",
                               return_value=5.0), \
             mock.patch.object(filetranscribe.api, "GeminiClient",
                               side_effect=factory), \
             mock.patch.object(cfg.Config, "gemini_keys",
                               return_value=list(keys)), \
             mock.patch.object(cfg.Config, "save"):
            worker._work("input.mp3", False, do_cleanup)
        return created, finished, failures

    def _rotation_conf(self):
        conf = cfg.Config()
        conf.data.update({"language": "tr", "transcribe_prompt": "",
                          "transcribe_engine": "cloud",
                          "gemini_next_slot": 1, "gemini_last_used": []})
        return conf

    def test_file_run_starts_at_claimed_slot_and_records_success(self):
        client = mock.Mock()
        conf = self._rotation_conf()
        created, finished, failures = self._run_file(
            conf, ["k1", "k2"], client)
        self.assertEqual(created["kwargs"]["start_slot"], 1)
        self.assertEqual(len(finished), 1)
        self.assertEqual(failures, [])
        self.assertEqual(conf["gemini_next_slot"], 0)
        self.assertEqual(len(conf["gemini_last_used"]), 2)
        self.assertEqual(conf["gemini_last_used"][0], "")
        self.assertRegex(conf["gemini_last_used"][1], r"^\d{4}-\d{2}-\d{2}T")

    def test_local_file_run_without_cleanup_leaves_rotation_alone(self):
        client = mock.Mock()
        conf = self._rotation_conf()
        conf.data["transcribe_engine"] = "local"
        created, finished, failures = self._run_file(
            conf, ["k1", "k2"], client)
        self.assertEqual(len(finished), 1)
        self.assertEqual(failures, [])
        self.assertEqual(created["kwargs"]["start_slot"], 0)
        self.assertEqual(conf["gemini_next_slot"], 1)
        self.assertEqual(conf["gemini_last_used"], [])

    def test_failure_before_the_client_is_reported_not_raised(self):
        """ffmpeg or a broken WAV failed before ``client``/``uses_cloud`` existed.

        The handler read both, so the real error turned into UnboundLocalError
        on the worker thread: the window stayed on "Working…" with no message.
        """
        worker = filetranscribe.FileTranscriber(self._rotation_conf())
        failures, finished = [], []
        worker.failed.connect(failures.append)
        worker.finished.connect(lambda *args: finished.append(args))
        with mock.patch.object(filetranscribe, "_to_wav",
                               side_effect=api.ApiError("ffmpeg not found")):
            worker._work("input.mp3", False, False)
        self.assertEqual(failures, ["ffmpeg not found"])
        self.assertEqual(finished, [])

if __name__ == "__main__":
    unittest.main()