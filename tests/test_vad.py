import unittest
import vad

class TestAnalyse(unittest.TestCase):
    def test_empty_returns_floor(self):
        s = vad.analyse([], 0.064)
        self.assertEqual(s["noise_db"], -120.0)
    def test_silence_detected_when_quiet(self):
        rms = [0.0001] * 100
        s = vad.analyse(rms, 0.064)
        self.assertTrue(vad.is_silent(s, silence_db=-55, margin_db=10, min_voiced_seconds=0.3))
    def test_speech_detected_when_loud(self):
        rms = [0.0001] * 50 + [0.5] * 50
        s = vad.analyse(rms, 0.064)
        self.assertFalse(vad.is_silent(s, silence_db=-55, margin_db=10, min_voiced_seconds=0.3))

class TestHallucination(unittest.TestCase):
    def test_short_known_phrase(self):
        self.assertTrue(vad.looks_like_hallucination("Thanks for watching", 3.0))
    def test_long_not_hallucination(self):
        self.assertFalse(vad.looks_like_hallucination("Thanks for watching", 10.0))
    def test_normal_text_not_hallucination(self):
        self.assertFalse(vad.looks_like_hallucination("bugün toplantı vardı", 2.0))
    def test_repeated_phrase(self):
        self.assertTrue(vad.looks_like_hallucination("altyazı mk altyazı mk", 2.0))

if __name__ == "__main__":
    unittest.main()