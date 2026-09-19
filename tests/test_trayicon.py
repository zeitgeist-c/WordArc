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

    def test_states_have_high_contrast_at_windows_tray_sizes(self):
        for state in ("audio-input-microphone", "media-record", "view-refresh"):
            current = trayicon.icon(state)
            for size in (16, 20, 24):
                image = current.pixmap(size, size).toImage()
                luminance = []
                colors = set()
                for y in range(size):
                    for x in range(size):
                        color = image.pixelColor(x, y)
                        if color.alpha() == 0:
                            continue
                        colors.add(color.rgba())
                        luminance.append(
                            0.2126 * color.red()
                            + 0.7152 * color.green()
                            + 0.0722 * color.blue()
                        )
                self.assertGreater(len(colors), 4, (state, size))
                self.assertLess(min(luminance), 70, (state, size))
                self.assertGreater(max(luminance), 180, (state, size))

if __name__ == "__main__":
    unittest.main()
