import unittest
import trayicon

class TestTrayIcon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        trayicon.clear_cache()

    def test_idle_name_returns_icon(self):
        from PyQt6.QtGui import QIcon
        self.assertFalse(trayicon.icon("audio-input-microphone").isNull())
    def test_rec_name_returns_icon(self):
        self.assertFalse(trayicon.icon("media-record").isNull())
    def test_busy_name_returns_icon(self):
        self.assertFalse(trayicon.icon("view-refresh").isNull())
    def test_unknown_name_still_draws(self):
        self.assertFalse(trayicon.icon("does-not-exist").isNull())
    def test_cached(self):
        trayicon.clear_cache()
        first = trayicon.icon("audio-input-microphone")
        second = trayicon.icon("audio-input-microphone")
        self.assertIs(first, second)

if __name__ == "__main__":
    unittest.main()