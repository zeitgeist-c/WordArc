import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import screenshot_capture
import screenshot_editor


class ScreenshotConfig(dict):
    def __init__(self, **kwargs):
        super().__init__(screenshot_directory="", screenshot_format="PNG",
                         **kwargs)
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

    # ---- overlay editor --------------------------------------------------

    def _make_overlay(self, fill="#123456", scale=2, selection=None):
        screen = self.app.primaryScreen()
        if screen is None:
            self.skipTest("Qt reports no screen")
        geometry = screen.geometry()
        image = QImage(geometry.width() * scale, geometry.height() * scale,
                       QImage.Format.Format_RGB32)
        image.fill(QColor(fill))
        pixmap = screenshot_capture.QPixmap.fromImage(image)
        overlay = screenshot_capture.RegionOverlay(screen, pixmap, selection)
        overlay.show()
        self.addCleanup(overlay.close)
        self.addCleanup(overlay.deleteLater)
        return overlay

    def _drag(self, overlay, start, end):
        QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(overlay, end)
        QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()

    def test_dragging_selects_a_region_and_shows_the_toolbar(self):
        overlay = self._make_overlay()
        self._drag(overlay, QPoint(20, 20), QPoint(60, 60))
        self.assertEqual(
            (overlay.selection.width(), overlay.selection.height()), (41, 41))
        self.assertTrue(overlay.toolbar.isVisible())
        self.assertEqual(overlay.tool, "select")

    def test_preselected_region_shows_the_toolbar_at_once(self):
        overlay = self._make_overlay(selection=QRect(10, 10, 120, 80))
        self.assertEqual(overlay.selection, QRect(10, 10, 120, 80))
        self.assertTrue(overlay.toolbar.isVisible())

    def test_toolbar_stays_compact_and_every_tool_has_an_accessible_icon(self):
        overlay = self._make_overlay(selection=QRect(40, 40, 220, 160))
        self.app.processEvents()
        self.assertLessEqual(overlay.toolbar.width(), 400)
        self.assertLessEqual(overlay.toolbar.height(), 90)
        for button in (*overlay.tool_buttons.values(), overlay.color_button,
                       overlay.undo_button, overlay.redo_button,
                       overlay.copy_button, overlay.save_button,
                       overlay.cancel_button):
            self.assertFalse(button.icon().isNull())
            self.assertTrue(button.toolTip())
            self.assertTrue(button.accessibleName())
            self.assertLessEqual(button.width(), 32)

    def test_toolbar_fits_at_each_screen_corner(self):
        overlay = self._make_overlay()
        for x in (0, overlay.width() - 60):
            for y in (0, overlay.height() - 60):
                overlay.selection = QRect(x, y, 60, 60)
                overlay._position_toolbar()
                self.assertTrue(overlay.rect().contains(overlay.toolbar.geometry()))

    def test_color_button_previews_the_selected_color(self):
        overlay = self._make_overlay(selection=QRect(20, 20, 200, 120))
        before = overlay.color_button.icon().cacheKey()
        with mock.patch.object(screenshot_capture.QColorDialog, "getColor",
                               return_value=QColor("#12abcd")):
            overlay._choose_color()
        self.assertEqual(overlay.color.name(), "#12abcd")
        self.assertNotEqual(overlay.color_button.icon().cacheKey(), before)

    def test_resize_handle_changes_selection(self):
        overlay = self._make_overlay()
        self._drag(overlay, QPoint(20, 20), QPoint(60, 60))
        before = QRect(overlay.selection)
        corner = overlay._handle_rects()["se"].center()
        self._drag(overlay, corner, corner + QPoint(20, 10))
        self.assertGreater(overlay.selection.width(), before.width())
        self.assertGreater(overlay.selection.height(), before.height())

    def test_inside_drag_moves_selection(self):
        overlay = self._make_overlay()
        self._drag(overlay, QPoint(20, 20), QPoint(60, 60))
        before = QRect(overlay.selection)
        self._drag(overlay, QPoint(30, 30), QPoint(50, 40))
        self.assertEqual(
            (overlay.selection.width(), overlay.selection.height()),
            (before.width(), before.height()))
        self.assertEqual(overlay.selection.topLeft(),
                         before.topLeft() + QPoint(20, 10))

    def _draw_rect(self, overlay, start=QPoint(25, 25), end=QPoint(55, 55)):
        overlay._set_tool("rect")
        overlay.color = QColor("#ff0000")
        overlay.stroke_width = 4
        self._drag(overlay, start, end)

    def test_drawing_a_rectangle_adds_an_annotation(self):
        overlay = self._make_overlay()
        self._drag(overlay, QPoint(20, 20), QPoint(80, 80))
        self._draw_rect(overlay)
        self.assertEqual(len(overlay.model.items), 1)
        item = overlay.model.items[0]
        self.assertEqual(item["type"], "rect")
        self.assertEqual(item["color"].name(), "#ff0000")
        self.assertEqual(item["rect"], QRect(25, 25, 31, 31))

    def test_copy_includes_the_annotations(self):
        overlay = self._make_overlay()
        copied = []
        overlay.copy_requested.connect(copied.append)
        self._drag(overlay, QPoint(20, 20), QPoint(80, 80))
        self._draw_rect(overlay)
        QTest.mouseClick(overlay.copy_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(len(copied), 1)
        image = copied[0]
        # The crop keeps the screen's pixel density: a 2× screen gives 2× pixels.
        self.assertEqual((image.width(), image.height()), (122, 122))
        # The rectangle's edge sits 5 logical pixels inside the crop.
        self.assertEqual(image.pixelColor(10, 10).name(), "#ff0000")

    def test_undo_and_redo_walk_the_annotations(self):
        overlay = self._make_overlay()
        self._drag(overlay, QPoint(20, 20), QPoint(80, 80))
        self._draw_rect(overlay)
        self.assertEqual(len(overlay.model.items), 1)
        overlay._undo()
        self.assertEqual(len(overlay.model.items), 0)
        overlay._redo()
        self.assertEqual(len(overlay.model.items), 1)

    def test_select_tool_moves_an_annotation(self):
        overlay = self._make_overlay()
        self._drag(overlay, QPoint(20, 20), QPoint(120, 120))
        self._draw_rect(overlay)
        overlay._set_tool("select")
        item = overlay.model.items[0]
        before = QRect(item["rect"])
        self._drag(overlay, QPoint(40, 40), QPoint(60, 55))
        self.assertEqual(item["rect"], before.translated(QPoint(20, 15)))

    def test_delete_removes_the_selected_annotation(self):
        overlay = self._make_overlay()
        self._drag(overlay, QPoint(20, 20), QPoint(120, 120))
        self._draw_rect(overlay)
        overlay._set_tool("select")
        self._drag(overlay, QPoint(40, 40), QPoint(41, 41))
        self.assertIsNotNone(overlay.model.selected)
        QTest.keyClick(overlay, Qt.Key.Key_Delete)
        self.app.processEvents()
        self.assertEqual(overlay.model.items, [])

    def test_text_placement_keeps_the_font_options(self):
        overlay = self._make_overlay()
        self._drag(overlay, QPoint(20, 20), QPoint(200, 200))
        font = QFont("Arial")
        font.setPointSize(24)
        font.setBold(True)
        font.setItalic(True)
        font.setUnderline(True)
        overlay._place_text(QPoint(40, 40), "WordArc", font, QColor("#00ff00"))
        self.assertEqual(len(overlay.model.items), 1)
        item = overlay.model.items[0]
        self.assertEqual(item["text"], "WordArc")
        self.assertTrue(item["font"].bold())
        self.assertTrue(item["font"].italic())
        self.assertTrue(item["font"].underline())
        self.assertEqual(item["font"].pointSize(), 24)
        self.assertEqual(item["color"].name(), "#00ff00")
        self.assertFalse(screenshot_editor.AnnotationModel.item_rect(item).isNull())

    def test_text_dialog_reports_the_chosen_values(self):
        dialog = screenshot_editor.TextDialog(None, "", QFont(), QColor("#111111"))
        dialog.edit.setText("Merhaba")
        dialog.size_box.setValue(30)
        dialog.bold.setChecked(True)
        dialog.color = QColor("#0000ff")
        text, font, color = dialog.values()
        self.assertEqual(text, "Merhaba")
        self.assertEqual(font.pointSize(), 30)
        self.assertTrue(font.bold())
        self.assertFalse(font.italic())
        self.assertEqual(color.name(), "#0000ff")
        dialog.close()

    def test_pixelate_patch_changes_the_exported_pixels(self):
        overlay = self._make_overlay(fill="#f0f0f0")
        self._drag(overlay, QPoint(20, 20), QPoint(200, 120))
        # A chequerboard under the patch makes the mosaic measurable.
        image = overlay.screenshot.toImage()
        for x in range(image.width()):
            for y in range(0, image.height(), 2):
                if x % 2:
                    image.setPixelColor(x, y, QColor("#202020"))
        overlay.screenshot = screenshot_capture.QPixmap.fromImage(image)
        overlay._set_tool("pixelate")
        self._drag(overlay, QPoint(40, 40), QPoint(120, 90))
        self.assertEqual(len(overlay.model.items), 1)
        self.assertEqual(overlay.model.items[0]["type"], "pixelate")
        exported = overlay._export_image()
        self.assertIsNotNone(exported)

    def test_ctrl_drag_copies_at_once(self):
        overlay = self._make_overlay()
        copied = []
        overlay.copy_requested.connect(copied.append)
        QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
        QTest.mouseMove(overlay, QPoint(60, 60))
        QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.ControlModifier,
                           QPoint(60, 60))
        self.app.processEvents()
        self.assertEqual(len(copied), 1)

    def test_escape_cancels(self):
        overlay = self._make_overlay()
        cancelled = []
        overlay.cancelled.connect(lambda: cancelled.append(True))
        QTest.keyClick(overlay, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertEqual(cancelled, [True])

    def test_tool_keys_and_select_all_do_not_export_early(self):
        overlay = self._make_overlay()
        copied = []
        overlay.copy_requested.connect(copied.append)
        for tool, letter in overlay.TOOL_KEYS.items():
            QTest.keyClick(overlay, Qt.Key(ord(letter)))
            self.assertEqual(overlay.tool, tool)
        QTest.keyClick(overlay, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(overlay.selection, overlay.rect())
        self.assertTrue(overlay.toolbar.isVisible())
        self.assertEqual(copied, [])

    def test_arrow_keys_move_the_region_and_stay_on_screen(self):
        overlay = self._make_overlay(selection=QRect(0, 0, 100, 80))
        QTest.keyClick(overlay, Qt.Key.Key_Left)
        self.assertEqual(overlay.selection.left(), 0)
        QTest.keyClick(overlay, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(overlay.selection.left(), 10)

    def test_clear_all_is_undoable_and_history_buttons_track_changes(self):
        overlay = self._make_overlay(selection=QRect(20, 20, 120, 120))
        self.assertFalse(overlay.undo_button.isEnabled())
        self.assertFalse(overlay.redo_button.isEnabled())
        self._draw_rect(overlay)
        self.assertTrue(overlay.undo_button.isEnabled())
        QTest.keyClick(overlay, Qt.Key.Key_Delete, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(overlay.model.items, [])
        overlay._undo()
        self.assertEqual(len(overlay.model.items), 1)
        self.assertTrue(overlay.redo_button.isEnabled())

    def test_blur_does_not_blend_original_detail_back_into_result(self):
        image = QImage(36, 36, QImage.Format.Format_RGB32)
        for x in range(36):
            for y in range(36):
                image.setPixelColor(x, y, QColor("white" if (x + y) % 2 else "black"))
        model = screenshot_editor.AnnotationModel()
        model.add({"type": "blur", "rect": image.rect()})
        result = model.render(image)
        self.assertLess(abs(result.pixelColor(16, 16).red()
                            - result.pixelColor(16, 17).red()), 3)

    def test_later_blur_covers_earlier_annotations(self):
        image = QImage(36, 36, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        model = screenshot_editor.AnnotationModel()
        model.add({"type": "rect", "rect": QRect(10, 10, 16, 16),
                   "color": QColor("black"), "width": 1, "fill": True})
        model.add({"type": "blur", "rect": image.rect()})
        result = model.render(image)
        self.assertGreater(result.pixelColor(16, 16).red(), 30)

    # ---- controller ------------------------------------------------------

    def _multi_screen_controller(self, count=4):
        controller = screenshot_capture.ScreenshotController(ScreenshotConfig())
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        screens = []
        events = []
        for index in range(count):
            scale = (1, 1.25, 1.5, 2)[index]
            geometry = QRect((index - 1) * 640, -120 if index == 2 else 0, 640, 480)
            image = QImage(round(640 * scale), round(480 * scale),
                           QImage.Format.Format_RGB32)
            image.fill(QColor(("#123456", "#abcdef", "#128912", "#bb4488")[index]))
            pixmap = screenshot_capture.QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(scale)
            screen = mock.Mock()
            screen.geometry.return_value = geometry
            def grab(_window, current=index, snapshot=pixmap):
                events.append(("grab", current))
                return snapshot
            screen.grabWindow.side_effect = grab
            screens.append(screen)
        controller._screen = screens[0]
        controller._mode = "region"
        base = screenshot_capture.RegionOverlay
        class TrackedOverlay(base):
            def show(self):
                events.append(("show", self.screen))
                super().show()
        with mock.patch.object(screenshot_capture.QGuiApplication, "screens",
                               return_value=screens), \
             mock.patch.object(screenshot_capture, "RegionOverlay", TrackedOverlay):
            controller._capture_screen()
        self.app.processEvents()
        return controller, screens, events

    def test_every_display_is_frozen_before_any_overlay_is_shown(self):
        for count in (2, 3, 4):
            with self.subTest(displays=count):
                controller, screens, events = self._multi_screen_controller(count)
                self.assertEqual(len(controller._overlays), count)
                self.assertEqual([kind for kind, _ in events],
                                 ["grab"] * count + ["show"] * count)
                self.assertTrue(all(window.isVisible() for window in controller._overlays))
                controller.shutdown()

    def test_can_select_a_different_display_without_restarting_and_keep_its_scale(self):
        controller, screens, _ = self._multi_screen_controller()
        first, second, third, fourth = controller._overlays
        self._drag(first, QPoint(20, 20), QPoint(119, 99))
        self.assertTrue(first.toolbar.isVisible())
        for index, overlay in enumerate((second, third, fourth), 1):
            self._drag(overlay, QPoint(20, 20), QPoint(119, 99))
            self.assertIs(controller._overlay, overlay)
            self.assertTrue(first.selection.isNull())
            image = overlay._export_image()
            scale = (1, 1.25, 1.5, 2)[index]
            self.assertEqual((image.width(), image.height()),
                             (round(100 * scale), round(80 * scale)))
            self.assertEqual(image.pixelColor(5, 5).name(),
                             ("#abcdef", "#128912", "#bb4488")[index - 1])
            self.assertTrue(all(s.grabWindow.call_count == 1 for s in screens))

    def test_escape_on_any_display_closes_all_capture_windows(self):
        controller, _, _ = self._multi_screen_controller()
        windows = list(controller._overlays)
        QTest.keyClick(windows[-1], Qt.Key.Key_Escape)
        self.assertEqual(controller._overlays, [])
        self.assertIsNone(controller._overlay)
        self.assertTrue(all(not window.isVisible() for window in windows))

    def test_failed_second_screen_leaves_no_partial_capture_windows(self):
        controller = screenshot_capture.ScreenshotController(ScreenshotConfig())
        self.addCleanup(controller.deleteLater)
        owner = screenshot_capture.QWidget()
        owner.show()
        self.addCleanup(owner.close)
        controller._hidden_owner = owner
        owner.hide()
        good, bad = mock.Mock(), mock.Mock()
        good.grabWindow.return_value = screenshot_capture.QPixmap(100, 100)
        bad.grabWindow.return_value = screenshot_capture.QPixmap()
        controller._screen = good
        errors = []
        controller.failed.connect(errors.append)
        with mock.patch.object(screenshot_capture.QGuiApplication, "screens",
                               return_value=[good, bad]):
            controller._capture_screen()
        self.assertEqual(len(errors), 1)
        self.assertEqual(controller._overlays, [])
        self.assertIsNone(controller._overlay)
        self.assertTrue(owner.isVisible())

    def test_monitor_disconnect_cancels_the_entire_session(self):
        controller, screens, _ = self._multi_screen_controller()
        controller._screen_removed(screens[-1])
        self.assertEqual(controller._overlays, [])
        self.assertIsNone(controller._overlay)

    def test_copy_from_other_display_closes_all_windows(self):
        controller, _, _ = self._multi_screen_controller()
        last = controller._overlays[-1]
        self._drag(last, QPoint(20, 20), QPoint(119, 99))
        with mock.patch.object(screenshot_capture, "copy_image_to_clipboard") as copy:
            last._quick_copy()
        self.assertEqual(copy.call_args.args[0].size(), QSize(200, 160))
        self.assertIsNone(controller._overlay)
        self.assertEqual(controller._overlays, [])

    def test_native_dpr_snapshots_do_not_scale_annotations_twice(self):
        for scale in (1.25, 1.5, 2):
            with self.subTest(scale=scale):
                image = QImage(round(100 * scale), round(100 * scale),
                               QImage.Format.Format_RGB32)
                image.fill(QColor("white"))
                image.setDevicePixelRatio(scale)
                model = screenshot_editor.AnnotationModel()
                model.add({"type": "rect", "rect": QRect(10, 10, 10, 10),
                           "color": QColor("black"), "width": 1, "fill": True})
                result = model.render(image, scale)
                self.assertEqual(result.devicePixelRatio(), 1)
                self.assertLess(result.pixelColor(round(14 * scale),
                                                   round(14 * scale)).red(), 200)
                self.assertEqual(result.pixelColor(round(24 * scale),
                                                    round(24 * scale)).name(), "#ffffff")

    def test_save_dialog_is_parented_to_overlay_and_cancel_preserves_it(self):
        overlay = self._make_overlay(selection=QRect(10, 10, 100, 80))
        controller = screenshot_capture.ScreenshotController(ScreenshotConfig())
        self.addCleanup(controller.shutdown)
        controller._overlay = overlay
        with mock.patch.object(screenshot_capture, "save_image_to_file",
                               return_value=None) as save:
            controller._on_overlay_save(overlay._export_image())
        self.assertIs(save.call_args.args[2], overlay)
        self.assertIs(controller._overlay, overlay)

    def test_transparent_jpeg_uses_white_background(self):
        image = QImage(12, 12, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "white.jpg")
            with mock.patch.object(screenshot_capture.QFileDialog, "getSaveFileName",
                                   return_value=(target, "JPEG image (*.jpg *.jpeg)")):
                screenshot_capture.save_image_to_file(image, ScreenshotConfig())
            self.assertGreater(QImage(target).pixelColor(5, 5).red(), 250)

    def test_controller_copy_puts_the_image_on_the_clipboard(self):
        image = QImage(32, 18, QImage.Format.Format_RGB32)
        image.fill(QColor("#abcdef"))
        controller = screenshot_capture.ScreenshotController(ScreenshotConfig())
        self.addCleanup(controller.deleteLater)
        controller._on_overlay_copy(image)
        clipboard = QApplication.clipboard().pixmap()
        self.assertEqual((clipboard.width(), clipboard.height()), (32, 18))
        self.assertEqual(clipboard.toImage().pixelColor(0, 0).name(), "#abcdef")

    def test_controller_save_writes_the_file_and_remembers_preferences(self):
        image = QImage(20, 10, QImage.Format.Format_RGB32)
        image.fill(QColor("#abcdef"))
        conf = ScreenshotConfig()
        controller = screenshot_capture.ScreenshotController(conf)
        self.addCleanup(controller.deleteLater)
        saved = []
        controller.preferences_saved.connect(
            lambda directory, fmt: saved.append((directory, fmt)))
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "capture.png")
            with mock.patch.object(screenshot_capture.QFileDialog,
                                   "getSaveFileName",
                                   return_value=(target, "PNG image (*.png)")):
                controller._on_overlay_save(image)
            self.app.processEvents()
            self.assertTrue(Path(target).is_file())
            self.assertEqual(saved, [(folder, "PNG")])
            self.assertEqual(conf["screenshot_directory"], folder)
            self.assertEqual(conf["screenshot_format"], "PNG")
            self.assertEqual(conf.saved, 1)
            loaded = QImage(target)
            self.assertEqual((loaded.width(), loaded.height()), (20, 10))

    def test_controller_save_uses_the_jpeg_extension_when_the_user_types_one(self):
        image = QImage(20, 10, QImage.Format.Format_RGB32)
        image.fill(QColor("#abcdef"))
        conf = ScreenshotConfig()
        controller = screenshot_capture.ScreenshotController(conf)
        self.addCleanup(controller.deleteLater)
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "capture.jpg")
            with mock.patch.object(screenshot_capture.QFileDialog,
                                   "getSaveFileName",
                                   return_value=(target, "PNG image (*.png)")):
                controller._on_overlay_save(image)
            self.app.processEvents()
            self.app.processEvents()
            loaded = QImage(target)
            self.assertFalse(loaded.isNull())
            self.assertEqual((loaded.width(), loaded.height()), (20, 10))
            self.assertEqual(conf["screenshot_format"], "JPEG")


class TestOcrExtraction(unittest.TestCase):
    """The editor's Extract text button, its worker hop, and the module gate."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _overlay(self, ocr_available=True):
        screen = self.app.primaryScreen()
        if screen is None:
            self.skipTest("Qt reports no screen")
        size = screen.geometry().size()
        image = QImage(size.width(), size.height(),
                       QImage.Format.Format_RGB32)
        image.fill(QColor("#123456"))
        pixmap = screenshot_capture.QPixmap.fromImage(image)
        patcher = None
        if not ocr_available:
            patcher = mock.patch.object(screenshot_capture.ocr, "is_available",
                                        return_value=False)
            patcher.start()
        try:
            overlay = screenshot_capture.RegionOverlay(
                screen, pixmap, QRect(10, 10, 120, 80))
            overlay.show()
            self.app.processEvents()
        finally:
            if patcher is not None:
                patcher.stop()
        self.addCleanup(overlay.close)
        self.addCleanup(overlay.deleteLater)
        return overlay

    def test_ocr_button_emits_the_crop(self):
        overlay = self._overlay()
        got = []
        overlay.ocr_requested.connect(got.append)
        QTest.mouseClick(overlay.ocr_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(len(got), 1)
        self.assertLessEqual(got[0].width(), overlay.screenshot.width())

    def test_button_hidden_without_windows_ocr(self):
        overlay = self._overlay(ocr_available=False)
        self.assertFalse(overlay.ocr_button.isVisible())
        self.assertTrue(overlay.copy_button.isVisible())

    def test_controller_hands_the_image_to_ocr_off_the_gui_thread(self):
        controller = screenshot_capture.ScreenshotController(ScreenshotConfig())
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        done = []
        controller.ocr_done.connect(done.append)
        image = QImage(20, 10, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        joined = []
        real_start = screenshot_capture.threading.Thread.start

        def track_start(thread):
            joined.append(thread)
            real_start(thread)
        with mock.patch.object(screenshot_capture.ocr, "extract_text",
                               return_value="merhaba"), \
             mock.patch.object(screenshot_capture.threading.Thread, "start",
                               track_start):
            controller._on_overlay_ocr(image)
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
        self.assertEqual(done, ["merhaba"])

    def test_ocr_failure_travels_the_failed_signal(self):
        controller = screenshot_capture.ScreenshotController(ScreenshotConfig())
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        errors = []
        controller.failed.connect(errors.append)
        image = QImage(20, 10, QImage.Format.Format_RGB32)
        real_start = screenshot_capture.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)
        with mock.patch.object(
                screenshot_capture.ocr, "extract_text",
                side_effect=screenshot_capture.ocr.OcrUnavailable("yok")), \
             mock.patch.object(screenshot_capture.threading.Thread, "start",
                               track_start):
            controller._on_overlay_ocr(image)
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
        self.assertEqual(errors, ["yok"])


if __name__ == "__main__":
    unittest.main()
