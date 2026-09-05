import unittest
import array
import os
import shutil
import tempfile
import wave

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


class _FakeClient:
    def transcribe(self, model, path, language="", prompt=""):
        if "mine" in os.path.basename(path):
            return "mine words"
        return "theirs words"


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

if __name__ == "__main__":
    unittest.main()
