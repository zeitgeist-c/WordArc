import unittest
import array
import os
import pathlib
import shutil
import tempfile
from unittest import mock
import wave

import api
import meeting
from i18n import t


def _write_stereo(path, seconds=1.0, rate=16000):
    frames = int(seconds * rate)
    samples = array.array("h")
    for _ in range(frames):
        samples.append(0)
        samples.append(0)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())


class _FakeConf(dict):
    def meeting_hint(self):
        return ""

    def speaker_names(self):
        return ("Me", "Them")

    # --- rotation doubles (mirror Config.claim/record semantics) ---
    def claim_api_slot(self, n_keys):
        total = max(int(n_keys), 0)
        if total <= 0:
            return 0
        try:
            slot = int(self.get("gemini_next_slot", 0))
        except (TypeError, ValueError):
            slot = 0
        return slot if 0 <= slot < total else 0

    def record_api_success(self, used_slot, n_keys):
        stamps = self.setdefault("gemini_last_used", [""] * n_keys)
        while len(stamps) < n_keys:
            stamps.append("")
        stamps[used_slot] = "used"
        self["gemini_next_slot"] = (used_slot + 1) % n_keys

    def record_api_attempt(self, used_slot, n_keys):
        self.setdefault("gemini_last_used", [""] * n_keys)
        self["gemini_next_slot"] = (used_slot + 1) % n_keys


class _FakeClient:
    def transcribe(self, model, path, language="", prompt=""):
        if "mine" in os.path.basename(path):
            return "mine words"
        return "theirs words"


class TestSummaryFailure(unittest.TestCase):
    """A summary that fails must not cost the transcript the run already paid for."""

    def _pipeline(self, updates, client):
        conf = _FakeConf({
            "meeting_model": "test-model", "meeting_reasoning": "",
            "meeting_cleanup": False, "meeting_keep_audio": True,
        })
        conf.gemini_keys = lambda: ["key"]
        conf.meeting_prompt = lambda: ""
        pipe = meeting.MeetingPipeline(conf)
        self._patches = [
            mock.patch.object(meeting.api, "GeminiClient", return_value=client),
            mock.patch.object(meeting.cfg, "update_meeting",
                              side_effect=lambda base, **kw: updates.append(kw)),
        ]
        return pipe

    def test_a_failed_summary_keeps_the_transcript_ready_status(self):
        """Marking the row failed threw away the stage that was already done:
        the next try transcribed the whole meeting again."""
        workdir = tempfile.mkdtemp(prefix="wordarc-test-meeting-")
        self.addCleanup(shutil.rmtree, workdir, True)
        updates = []
        client = mock.Mock()
        client.active_slot = 0
        client.cleanup.side_effect = api.ApiError("summary failed")
        pipe = self._pipeline(updates, client)
        paths = (pathlib.Path(workdir) / "doc.md", pathlib.Path(workdir) / "rec.wav")
        paths[1].write_bytes(b"RIFF")
        for patch in self._patches:
            patch.start()
            self.addCleanup(patch.stop)
        with mock.patch.object(meeting.cfg, "meeting_paths", return_value=paths), \
             mock.patch.object(meeting.MeetingPipeline, "_transcribe",
                               return_value="fresh transcript"):
            pipe._work({"base": "2026-01-01-1200", "status": ""})

        self.assertEqual(updates[0], {"status": "transcribed", "error": ""})
        self.assertEqual(updates[-1],
                         {"status": "transcribed", "error": "summary failed"})

    def test_a_failure_before_any_transcript_still_marks_the_row_failed(self):
        workdir = tempfile.mkdtemp(prefix="wordarc-test-meeting-")
        self.addCleanup(shutil.rmtree, workdir, True)
        updates = []
        client = mock.Mock()
        client.active_slot = 0
        pipe = self._pipeline(updates, client)
        wav = pathlib.Path(workdir) / "rec.wav"
        wav.write_bytes(b"RIFF")
        paths = (pathlib.Path(workdir) / "doc.md", wav)
        for patch in self._patches:
            patch.start()
            self.addCleanup(patch.stop)
        with mock.patch.object(meeting.cfg, "meeting_paths", return_value=paths), \
             mock.patch.object(meeting.MeetingPipeline, "_transcribe",
                               side_effect=api.ApiError("no audio")):
            pipe._work({"base": "2026-01-01-1200", "status": ""})

        self.assertEqual(updates, [{"status": "failed", "error": "no audio"}])


class TestTranscribeTimeline(unittest.TestCase):
    def test_chunks_become_timestamped_turns(self):
        workdir = tempfile.mkdtemp(prefix="wordarc-test-meeting-")
        self.addCleanup(shutil.rmtree, workdir, True)
        wav_path = os.path.join(workdir, "rec.wav")
        _write_stereo(wav_path)
        self.assertAlmostEqual(meeting.wav_duration(wav_path), 1.0, places=2)
        conf = _FakeConf({
            "gemini_transcribe_model": "test-model",
            "meeting_language": "",
            "language": "tr",
            "skip_silent": False,
        })
        pipe = meeting.MeetingPipeline(conf)
        out = pipe._transcribe(_FakeClient(), wav_path, workdir)
        self.assertEqual(
            out, "[00:00] Me: mine words\n[00:00] Them: theirs words")

    def test_empty_transcript_names_the_silent_side(self):
        import api
        workdir = tempfile.mkdtemp(prefix="wordarc-test-meeting-")
        self.addCleanup(shutil.rmtree, workdir, True)
        wav_path = os.path.join(workdir, "rec.wav")
        _write_stereo(wav_path)
        conf = _FakeConf({
            "gemini_transcribe_model": "test-model",
            "meeting_language": "",
            "language": "tr",
            "skip_silent": False,
        })
        pipe = meeting.MeetingPipeline(conf)

        class _MuteClient:
            def transcribe(self, model, path, language="", prompt=""):
                return "  "

        with self.assertRaises(api.ApiError) as ctx:
            pipe._transcribe(_MuteClient(), wav_path, workdir)
        self.assertIn(
            t("The audio held no recognisable speech. The recording is kept."),
            str(ctx.exception))

    def test_all_silent_chunks_list_both_sides(self):
        import api
        workdir = tempfile.mkdtemp(prefix="wordarc-test-meeting-")
        self.addCleanup(shutil.rmtree, workdir, True)
        wav_path = os.path.join(workdir, "rec.wav")
        _write_stereo(wav_path)
        conf = _FakeConf({
            "gemini_transcribe_model": "test-model",
            "meeting_language": "",
            "language": "tr",
            "skip_silent": True,
            "silence_db": -59.0,
            "speech_margin_db": 10.0,
            "min_voiced_seconds": 0.3,
        })
        pipe = meeting.MeetingPipeline(conf)
        with self.assertRaises(api.ApiError) as ctx:
            pipe._transcribe(_FakeClient(), wav_path, workdir)
        message = str(ctx.exception)
        self.assertIn("Me", message)
        self.assertIn("Them", message)

class TestMergeTurns(unittest.TestCase):
    def test_simple_interleave(self):
        segs = [(0, 2, "a", "mine"), (2, 4, "b", "theirs"), (4, 6, "c", "mine")]
        turns = meeting.merge_turns(segs)
        self.assertEqual([t[1] for t in turns], ["mine", "theirs", "mine"])
        self.assertEqual(turns[0][2], "a")
    def test_join_same_speaker_within_gap(self):
        segs = [(0, 1, "a", "mine"), (2, 3, "b", "mine")]
        turns = meeting.merge_turns(segs, gap=8)
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0][2], "a b")

class TestRenderTurns(unittest.TestCase):
    def test_renders_with_labels(self):
        turns = [(0, "mine", "hello"), (3, "theirs", "world")]
        out = meeting.render_turns(turns, "Me", "Them")
        self.assertEqual(out, "[00:00] Me: hello\n[00:03] Them: world")

class TestBuildDocument(unittest.TestCase):
    def test_document_contains_marker_and_transcript(self):
        doc = meeting.build_document("Title", "2026-01-01 10:00", 120.0,
                                     "## Decisions\nA", "transcript text")
        self.assertIn("# Title", doc)
        self.assertIn(meeting.TRANSCRIPT_MARKER, doc)
        self.assertIn("transcript text", doc)
    def test_read_transcript_round_trip(self):
        doc = meeting.build_document("T", "x", 60.0, "minutes", "transcript")
        self.assertEqual(meeting.read_transcript(doc), "transcript")

class TestSplitTitle(unittest.TestCase):
    def test_heading(self):
        title, rest = meeting.split_title("# My Meeting\nbody")
        self.assertEqual(title, "My Meeting")
        self.assertEqual(rest, "body")
    def test_no_heading(self):
        title, rest = meeting.split_title("no heading")
        self.assertEqual(title, "")
        self.assertEqual(rest, "no heading")

class TestNewEntry(unittest.TestCase):
    def test_new_entry_fields(self):
        e = meeting.new_entry("20260101-100000", 30.0)
        self.assertEqual(e["base"], "20260101-100000")
        self.assertEqual(e["duration"], 30.0)
        self.assertEqual(e["status"], "recorded")
        self.assertEqual(e["ts"], "2026-01-01 10:00")


class TestApiRotation(unittest.TestCase):
    def _run_meeting(self, conf, client):
        workdir = tempfile.mkdtemp(prefix="wordarc-test-rotation-")
        self.addCleanup(shutil.rmtree, workdir, True)
        paths = (pathlib.Path(workdir) / "doc.md",
                 pathlib.Path(workdir) / "rec.wav")
        paths[1].write_bytes(b"RIFF")
        created = {}
        def factory(api_keys, **kwargs):
            created.update(keys=list(api_keys), kwargs=kwargs)
            client.active_slot = kwargs.get("start_slot", 0)
            return client
        finished, failures = [], []
        pipe = meeting.MeetingPipeline(conf)
        pipe.finished.connect(lambda *args: finished.append(args))
        pipe.failed.connect(lambda *args: failures.append(args))
        patches = [
            mock.patch.object(meeting.api, "GeminiClient", side_effect=factory),
            mock.patch.object(meeting.cfg, "update_meeting"),
            mock.patch.object(meeting.cfg, "meeting_paths", return_value=paths),
            mock.patch.object(meeting.MeetingPipeline, "_transcribe",
                              return_value="fresh transcript"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        pipe._work({"base": "2026-01-01-1200", "status": ""})
        return created, finished, failures

    def _rotation_conf(self):
        conf = _FakeConf({
            "meeting_model": "test-model", "meeting_reasoning": "",
            "meeting_cleanup": False, "meeting_keep_audio": True,
            "gemini_next_slot": 1, "gemini_last_used": ["", ""],
        })
        conf.gemini_keys = lambda: ["k1", "k2"]
        conf.meeting_prompt = lambda: ""
        return conf

    def test_meeting_starts_at_claimed_slot_and_records_success(self):
        client = mock.Mock()
        client.cleanup.return_value = "# Title\nminutes body"
        conf = self._rotation_conf()
        created, finished, failures = self._run_meeting(conf, client)
        self.assertEqual(created["kwargs"]["start_slot"], 1)
        self.assertEqual(len(finished), 1)
        self.assertEqual(failures, [])
        self.assertEqual(client.active_slot, 1)
        self.assertEqual(conf["gemini_next_slot"], 0)
        self.assertEqual(conf["gemini_last_used"], ["", "used"])

    def test_meeting_failure_advances_without_a_stamp(self):
        client = mock.Mock()
        client.cleanup.side_effect = api.ApiError("busy", 429, "temporary")
        conf = self._rotation_conf()
        created, finished, failures = self._run_meeting(conf, client)
        self.assertEqual(finished, [])
        self.assertEqual(len(failures), 1)
        self.assertEqual(conf["gemini_next_slot"], 0)
        self.assertEqual(conf["gemini_last_used"], ["", ""])


class TestRmsSeries(unittest.TestCase):
    """The per-block RMS vad.analyse consumes; numpy replaced a Python sum()."""

    def _wav(self, samples, rate=16000):
        workdir = tempfile.mkdtemp(prefix="wordarc-test-rms-")
        self.addCleanup(shutil.rmtree, workdir, True)
        path = os.path.join(workdir, "tone.wav")
        with wave.open(path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(array.array("h", samples).tobytes())
        return path

    def test_constant_tone_has_expected_level(self):
        samples = [16384] * meeting.LEVEL_FRAMES * 2
        out = meeting.rms_series(self._wav(samples))
        self.assertEqual(len(out), 2)
        for level in out:
            self.assertAlmostEqual(level, 0.5, places=6)

    def test_silence_is_zero_and_empty_file_is_empty(self):
        self.assertEqual(meeting.rms_series(self._wav([0] * 2048)), [0.0, 0.0])
        self.assertEqual(meeting.rms_series(self._wav([])), [])

    def test_level_is_clamped_to_one(self):
        # int16 full scale is -32768, whose square root is 1.0 — never above it.
        out = meeting.rms_series(self._wav([-32768] * meeting.LEVEL_FRAMES))
        self.assertEqual(out, [1.0])

if __name__ == "__main__":
    unittest.main()
