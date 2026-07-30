import unittest
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

if __name__ == "__main__":
    unittest.main()