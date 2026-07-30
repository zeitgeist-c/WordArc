import unittest
import meeting

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
