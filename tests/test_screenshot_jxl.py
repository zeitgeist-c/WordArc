import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

import i18n
import screenshot_capture


try:
    import pillow_jxl  # noqa: F401
    from PIL import Image as _PilImage
    _JXL_AVAILABLE = True
except ImportError:
    _PilImage = None
    _JXL_AVAILABLE = False


class JxlConfig(dict):
    def __init__(self, **kwargs):
        super().__init__(screenshot_directory="", screenshot_format="PNG")
        self.update(kwargs)
        self.saved = 0

    def save(self):
        self.saved += 1


def _rgba_test_image(width=24, height=16):
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    for y in range(height):
        for x in range(width):
            image.setPixelColor(
                x, y, QColor((x * 11) % 256, (y * 17) % 256,
                             ((x + y) * 7) % 256, (x * 5 + y * 3) % 256))
    return image


def _qimage_rgba_bytes(image):
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    from PyQt6.QtCore import QBuffer, QIODevice
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.ReadWrite)
    try:
        assert rgba.save(buffer, "PNG")
        shot = _PilImage.open(__import__("io").BytesIO(bytes(buffer.data())))
        return shot.convert("RGBA").tobytes()
    finally:
        buffer.close()


class TestJxlSave(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        if not _JXL_AVAILABLE:
            raise unittest.SkipTest("pillow-jxl-plugin is not installed")

    def test_jxl_roundtrip_is_lossless_with_alpha(self):
        image = _rgba_test_image()
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "shot.jxl")
            with mock.patch.object(
                    screenshot_capture.QFileDialog, "getSaveFileName",
                    return_value=(target, "JPEG XL image (*.jxl)")):
                result = screenshot_capture.save_image_to_file(
                    image, JxlConfig())
            self.assertEqual(result[1], "JXL")
            self.assertTrue(Path(target).is_file())
            back = _PilImage.open(target)
            back.load()
            self.assertEqual(back.size, (image.width(), image.height()))
            self.assertEqual(back.convert("RGBA").tobytes(),
                             _qimage_rgba_bytes(image))

    def test_jxl_suffix_wins_over_the_png_filter(self):
        image = _rgba_test_image()
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "shot.jxl")
            with mock.patch.object(
                    screenshot_capture.QFileDialog, "getSaveFileName",
                    return_value=(target, "PNG image (*.png)")):
                _folder, fmt, _name = screenshot_capture.save_image_to_file(
                    image, JxlConfig())
            self.assertEqual(fmt, "JXL")

    def test_jxl_filter_appends_the_extension(self):
        image = _rgba_test_image()
        with tempfile.TemporaryDirectory() as folder:
            bare = str(Path(folder) / "shot")
            with mock.patch.object(
                    screenshot_capture.QFileDialog, "getSaveFileName",
                    return_value=(bare, "JPEG XL image (*.jxl)")):
                folder_out, fmt, name = screenshot_capture.save_image_to_file(
                    image, JxlConfig())
            self.assertEqual(fmt, "JXL")
            self.assertTrue(name.endswith(".jxl"))
            self.assertTrue(Path(folder_out, name).is_file())

    def test_untouched_suggestion_follows_the_picked_filter(self):
        image = _rgba_test_image()
        seen = {}

        def fake_dialog(*args, **kwargs):
            seen["suggested"] = args[2]
            return (args[2], "JPEG XL image (*.jxl)")

        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(screenshot_capture.QFileDialog,
                                   "getSaveFileName",
                                   side_effect=fake_dialog):
                folder_out, fmt, name = screenshot_capture.save_image_to_file(
                    image, JxlConfig(screenshot_directory=folder))
            self.assertEqual(folder_out, folder)
            self.assertEqual(fmt, "JXL")
            self.assertTrue(name.endswith(".jxl"))
            self.assertTrue(Path(folder_out, name).is_file())
            self.assertTrue(seen["suggested"].endswith(".png"))

    def test_jxl_is_the_default_suggestion_when_configured(self):
        seen = {}

        def fake_dialog(*args, **kwargs):
            seen["initial"] = args[4]
            return ("", "")

        with mock.patch.object(screenshot_capture.QFileDialog,
                               "getSaveFileName", side_effect=fake_dialog):
            out = screenshot_capture.save_image_to_file(
                _rgba_test_image(), JxlConfig(screenshot_format="JXL"))
        self.assertIsNone(out)
        self.assertIn(".jxl", seen["initial"])

    def test_controller_save_remembers_jxl(self):
        image = _rgba_test_image()
        conf = JxlConfig()
        controller = screenshot_capture.ScreenshotController(conf)
        self.addCleanup(controller.deleteLater)
        saved = []
        controller.preferences_saved.connect(
            lambda directory, fmt: saved.append((directory, fmt)))
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "shot.jxl")
            with mock.patch.object(
                    screenshot_capture.QFileDialog, "getSaveFileName",
                    return_value=(target, "JPEG XL image (*.jxl)")):
                controller._on_overlay_save(image)
            self.app.processEvents()
            self.assertTrue(Path(target).is_file())
            self.assertEqual(saved, [(folder, "JXL")])
            self.assertEqual(conf["screenshot_format"], "JXL")

    def test_unknown_configured_format_falls_back_to_png(self):
        image = _rgba_test_image()
        seen = {}

        def fake_dialog(*args, **kwargs):
            seen["initial"] = args[2]
            return ("", "")

        with mock.patch.object(screenshot_capture.QFileDialog,
                               "getSaveFileName", side_effect=fake_dialog):
            screenshot_capture.save_image_to_file(
                image, JxlConfig(screenshot_format="TIFF"))
        self.assertTrue(seen["initial"].endswith(".png"))

    def test_failed_write_is_a_clear_oserror(self):
        image = _rgba_test_image()
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "shot.jxl")
            with mock.patch.object(
                    screenshot_capture.QFileDialog, "getSaveFileName",
                    return_value=(target, "JPEG XL image (*.jxl)")), \
                 mock.patch.object(screenshot_capture, "_write_jxl",
                                   side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    screenshot_capture.save_image_to_file(image, JxlConfig())

    def test_missing_codec_is_a_clear_oserror(self):
        image = _rgba_test_image()
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "shot.jxl")
            with mock.patch.object(
                    screenshot_capture.QFileDialog, "getSaveFileName",
                    return_value=(target, "JPEG XL image (*.jxl)")), \
                 mock.patch.dict(sys.modules, {"pillow_jxl": None}):
                with self.assertRaises(OSError) as ctx:
                    screenshot_capture.save_image_to_file(image, JxlConfig())
            self.assertIn("Could not write", str(ctx.exception))


class TestJxlRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_png_still_saves(self):
        image = QImage(20, 10, QImage.Format.Format_RGB32)
        image.fill(QColor("#abcdef"))
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "shot.png")
            with mock.patch.object(
                    screenshot_capture.QFileDialog, "getSaveFileName",
                    return_value=(target, "PNG image (*.png)")):
                _folder, fmt, _name = screenshot_capture.save_image_to_file(
                    image, JxlConfig())
            self.assertEqual(fmt, "PNG")
            loaded = QImage(target)
            self.assertEqual((loaded.width(), loaded.height()), (20, 10))

    def test_jpeg_still_saves(self):
        image = QImage(20, 10, QImage.Format.Format_RGB32)
        image.fill(QColor("#abcdef"))
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "shot.jpg")
            with mock.patch.object(
                    screenshot_capture.QFileDialog, "getSaveFileName",
                    return_value=(target, "JPEG image (*.jpg *.jpeg)")):
                _folder, fmt, _name = screenshot_capture.save_image_to_file(
                    image, JxlConfig())
            self.assertEqual(fmt, "JPEG")
            loaded = QImage(target)
            self.assertEqual((loaded.width(), loaded.height()), (20, 10))

    def test_settings_combo_offers_jxl(self):
        import ast
        tree = ast.parse((Path(__file__).resolve().parent.parent
                          / "settings_ui.py").read_text(encoding="utf-8"))
        labels = [node.args[0].value
                  for node in ast.walk(tree)
                  if isinstance(node, ast.Call)
                  and getattr(node.func, "attr", "") == "addItem"
                  and node.args
                  and isinstance(node.args[0], ast.Constant)]
        self.assertIn("JPEG XL (.jxl)", labels)


class TestJxlI18n(unittest.TestCase):
    def test_filter_string_in_all_tables(self):
        key = "JPEG XL image (*.jxl)"
        self.assertIn(key, i18n.TR)
        for code, table in i18n.TABLES.items():
            self.assertIn(key, table, f"{code}: {key!r}")

    def test_turkish_label(self):
        i18n.set_language("tr")
        try:
            self.assertEqual(i18n.t("JPEG XL image (*.jxl)"),
                             "JPEG XL görüntüsü (*.jxl)")
        finally:
            i18n.set_language("en")


if __name__ == "__main__":
    unittest.main()
