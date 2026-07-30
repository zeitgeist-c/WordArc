import unittest, os, sys, tempfile
import ffmpeg_path

class TestFfmpegPath(unittest.TestCase):
    def test_raises_when_missing(self):
        # No _MEIPASS, and ensure PATH has no ffmpeg by patching shutil.which
        import shutil
        orig = shutil.which
        shutil.which = lambda name: None
        try:
            self.assertNotIn("_MEIPASS", sys.__dict__)  # sanity
            with self.assertRaises(FileNotFoundError):
                ffmpeg_path.ffmpeg()
        finally:
            shutil.which = orig
    def test_meipass_wins(self):
        import shutil
        orig_which = shutil.which
        tmp = tempfile.mkdtemp()
        fake = os.path.join(tmp, "ffmpeg.exe")
        open(fake, "wb").close()
        shutil.which = lambda name: None
        try:
            # Simulate PyInstaller by monkeypatching sys._MEIPASS via a module attr
            class S: pass
            backup = sys._MEIPASS if hasattr(sys, "_MEIPASS") else None
            sys._MEIPASS = tmp
            try:
                self.assertEqual(ffmpeg_path.ffmpeg(), fake)
            finally:
                if backup is None:
                    del sys._MEIPASS
                else:
                    sys._MEIPASS = backup
        finally:
            shutil.which = orig_which

if __name__ == "__main__":
    unittest.main()