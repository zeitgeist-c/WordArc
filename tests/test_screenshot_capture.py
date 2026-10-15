import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import screenshot_capture
from i18n import t


class ScreenshotConfig(dict):
    def __init__(self, **kwargs):
        super().__init__(screenshot_directory="", screenshot_format="PNG", **kwargs)
        self.saved = 0

    def save(self):
        self.saved += 1


class TestScreenshotCapture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_crop_uses_physical_pixel_scale_and_normalizes_selection(self):
        image = QImage(200, 100, QImage.Format.Format_RGB32)
        image.fill(QColor("#345678"))
        crop = screenshot_capture.crop_screen_image(
            image, QRect(30, 20, -10, -5), QSize(100, 50))
        self.assertEqual((crop.width(), crop.height()), (20, 10))
        self.assertEqual(crop.pixelColor(0, 0).name(), "#345678")

    def test_crop_rejects_empty_or_invalid_selections(self):
        image = QImage(100, 50, QImage.Format.Format_RGB32)
        with self.assertRaisesRegex(ValueError, "invalid size"):
            screenshot_capture.crop_screen_image(image, QRect(0, 0, 3, 3), QSize())
        with self.assertRaisesRegex(ValueError, "at least 2"):
            screenshot_capture.crop_screen_image(image, QRect(1, 1, 1, 1), QSize(100, 50))


    def test_region_overlay_emits_high_dpi_crop_for_drag_selection(self):
        screen = self.app.primaryScreen()
        if screen is None:
            self.skipTest("Qt reports no screen")
        geometry = screen.geometry()
        image = QImage(geometry.width() * 2, geometry.height() * 2,
                       QImage.Format.Format_RGB32)
        image.fill(QColor("#123456"))
        pixmap = screenshot_capture.QPixmap.fromImage(image)
        overlay = screenshot_capture.RegionOverlay(screen, pixmap)
        selected = []
        overlay.selected.connect(selected.append)
        overlay.show()
        QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
        QTest.mouseMove(overlay, QPoint(40, 40))
        QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
        self.app.processEvents()
        self.assertEqual(len(selected), 1)
        self.assertEqual((selected[0].width(), selected[0].height()), (42, 42))
        overlay.close()
        overlay.deleteLater()

    def test_preview_copy_puts_exact_image_on_clipboard(self):
        image = QImage(32, 18, QImage.Format.Format_RGB32)
        image.fill(QColor("#abcdef"))
        preview = screenshot_capture.ScreenshotPreview(image, ScreenshotConfig())
        preview._copy()
        clipboard = QApplication.clipboard().pixmap()
        self.assertEqual((clipboard.width(), clipboard.height()), (32, 18))
        self.assertEqual(clipboard.toImage().pixelColor(0, 0).name(), "#abcdef")
        preview.close()

    def test_save_uses_selected_format_and_remembers_folder(self):
        image = QImage(20, 10, QImage.Format.Format_RGB32)
        image.fill(QColor("#abcdef"))
        conf = ScreenshotConfig()
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "capture.png")
            preview = screenshot_capture.ScreenshotPreview(image, conf)
            saved = []
            preview.saved.connect(lambda directory, fmt: saved.append((directory, fmt)))
            with mock.patch.object(screenshot_capture.QFileDialog, "getSaveFileName",
                                   return_value=(target, "PNG image (*.png)")):
                preview._save()
            self.assertTrue(Path(target).is_file())
            self.assertEqual(conf["screenshot_directory"], "")
            self.assertEqual(conf.saved, 0)
            self.assertEqual(saved, [(folder, "PNG")])
            loaded = QImage(target)
            self.assertEqual((loaded.width(), loaded.height()), (20, 10))
            preview.close()

    def test_jpeg_extension_selects_jpeg_even_when_dialog_defaults_to_png(self):
        image = QImage(20, 10, QImage.Format.Format_RGB32)
        image.fill(QColor("#abcdef"))
        conf = ScreenshotConfig()
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "capture.jpg")
            preview = screenshot_capture.ScreenshotPreview(image, conf)
            with mock.patch.object(screenshot_capture.QFileDialog, "getSaveFileName",
                                   return_value=(target, "PNG image (*.png)")):
                preview._save()
            loaded = QImage(target)
            self.assertFalse(loaded.isNull())
            self.assertEqual((loaded.width(), loaded.height()), (20, 10))
            self.assertEqual(preview.save_button.text(),
                             t("Saved: {path}", path="capture.jpg"))
            preview.close()


if __name__ == "__main__":
    unittest.main()