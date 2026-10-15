"""Native Windows screenshot capture primitives used by the screenshot tab."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, QStandardPaths, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from i18n import t


def default_save_folder() -> Path:
    """Known user Pictures folder, with a home-directory fallback."""
    pictures = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.PicturesLocation)
    return (Path(pictures) if pictures else Path.home()) / "WordArc"


def crop_screen_image(image: QImage, selection: QRect, screen_size) -> QImage:
    """Crop a logical-pixel selection while retaining the screen's pixel density."""
    if screen_size.width() <= 0 or screen_size.height() <= 0:
        raise ValueError("Screen has an invalid size.")
    scale_x = image.width() / screen_size.width()
    scale_y = image.height() / screen_size.height()
    rect = selection.normalized()
    left = round(rect.left() * scale_x)
    top = round(rect.top() * scale_y)
    right = round((rect.right() + 1) * scale_x)
    bottom = round((rect.bottom() + 1) * scale_y)
    pixels = QRect(left, top, right - left, bottom - top).intersected(
        QRect(0, 0, image.width(), image.height()))
    if pixels.width() < 2 or pixels.height() < 2:
        raise ValueError("Select an area at least 2 × 2 pixels.")
    return image.copy(pixels)


class RegionOverlay(QWidget):
    """Lightshot-style overlay: drag to select, adjust, then copy/save."""

    selected = pyqtSignal(QImage)
    copy_requested = pyqtSignal(QImage)
    save_requested = pyqtSignal(QImage)
    cancelled = pyqtSignal()

    HANDLE = 10
    MIN_SIDE = 6
    _HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")

    def __init__(self, screen, screenshot):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.screen = screen
        self.screenshot = screenshot
        self._global_origin = QPoint(0, 0)
        self._region_only = True
        self._screen_size = screen.geometry().size()
        self.origin = None
        self.selection = QRect()
        self._drag_mode = None
        self._drag_offset = QPoint()
        self._drag_start = QRect()
        self._press_point = QPoint()
        self._previous_selection = QRect()
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle(t("Select screenshot area"))
        self.toolbar = QWidget(self)
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(4)
        self.copy_button = QPushButton(t("Copy"), self.toolbar)
        self.copy_button.setObjectName("screenshotOverlayCopy")
        self.copy_button.clicked.connect(self._quick_copy)
        self.save_button = QPushButton(t("Save"), self.toolbar)
        self.save_button.setObjectName("screenshotOverlaySave")
        self.save_button.clicked.connect(self._quick_save)
        self.cancel_button = QPushButton(t("Cancel"), self.toolbar)
        self.cancel_button.setObjectName("screenshotOverlayCancel")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        toolbar_layout.addWidget(self.copy_button)
        toolbar_layout.addWidget(self.save_button)
        toolbar_layout.addWidget(self.cancel_button)
        self.toolbar.hide()

    def _handle_rects(self):
        sel = self.selection
        half = self.HANDLE // 2
        cx = sel.left() + sel.width() // 2
        cy = sel.top() + sel.height() // 2
        points = {"nw": (sel.left(), sel.top()), "n": (cx, sel.top()),
                  "ne": (sel.right(), sel.top()), "e": (sel.right(), cy),
                  "se": (sel.right(), sel.bottom()), "s": (cx, sel.bottom()),
                  "sw": (sel.left(), sel.bottom()), "w": (sel.left(), cy)}
        return {key: QRect(x - half, y - half, self.HANDLE, self.HANDLE)
                for key, (x, y) in points.items()}

    def _hit_test(self, pos):
        if self.selection.isNull():
            return None
        for key, rect in self._handle_rects().items():
            if rect.contains(pos):
                return key
        if self.selection.contains(pos):
            return "move"
        return None

    def _adjusting(self):
        return not self.selection.isNull() and self._drag_mode != "draw"

    def _position_toolbar(self):
        if self.selection.isNull():
            self.toolbar.hide()
            return
        self.toolbar.adjustSize()
        size = self.toolbar.sizeHint()
        x = min(max(self.selection.left(), 0), max(self.width() - size.width(), 0))
        y = self.selection.bottom() + 8
        if y + size.height() > self.height():
            y = self.selection.top() - 8 - size.height()
        self.toolbar.move(x, max(y, 0))
        self.toolbar.show()
        self.toolbar.raise_()

    def _crop_selection(self):
        try:
            return crop_screen_image(self.screenshot.toImage(), self.selection,
                                     self._screen_size)
        except ValueError:
            return None

    def _confirm(self):
        if self.selection.isNull():
            return
        image = self._crop_selection()
        if image is None:
            return
        self.selected.emit(image)

    def _quick_copy(self):
        if self.selection.isNull():
            return
        image = self._crop_selection()
        if image is None:
            return
        self.copy_requested.emit(image)

    def _quick_save(self):
        if self.selection.isNull():
            return
        image = self._crop_selection()
        if image is None:
            return
        self.save_requested.emit(image)

    def _update_hover_cursor(self, pos):
        hit = self._hit_test(pos)
        if hit in ("nw", "se"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif hit in ("ne", "sw"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif hit in ("n", "s"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif hit in ("e", "w"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif hit == "move":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, _event):
        painter = QPainter(self)
        target = self.rect()
        painter.drawPixmap(target, self.screenshot)
        painter.fillRect(target, QColor(0, 0, 0, 110))
        if not self.selection.isNull():
            painter.save()
            painter.setClipRect(self.selection)
            painter.drawPixmap(target, self.screenshot)
            painter.restore()
            painter.setPen(QPen(QColor("#9475EC"), 2))
            painter.drawRect(self.selection.adjusted(0, 0, -1, -1))
            painter.setPen(QColor("white"))
            painter.drawText(self.selection.adjusted(8, 6, -8, -6),
                             int(Qt.AlignmentFlag.AlignLeft
                                 | Qt.AlignmentFlag.AlignTop),
                             f"{self.selection.width()} × {self.selection.height()}")
            if self._adjusting():
                painter.setPen(QPen(QColor("white"), 2))
                painter.setBrush(QColor("white"))
                for rect in self._handle_rects().values():
                    painter.drawRect(rect)
                painter.setPen(QColor("white"))
                hint = t("Drag handles to adjust · double-click to confirm")
                painter.drawText(target.adjusted(0, 8, 0, 0),
                                 int(Qt.AlignmentFlag.AlignHCenter
                                     | Qt.AlignmentFlag.AlignTop), hint)
        elif self.origin is None:
            painter.setPen(QColor("white"))
            painter.drawText(target, int(Qt.AlignmentFlag.AlignCenter),
                             t("Drag to select · Esc to cancel"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        if self._adjusting():
            hit = self._hit_test(pos)
            if hit is not None:
                self._drag_mode = hit
                self._press_point = pos
                self._drag_start = QRect(self.selection)
                self._drag_offset = pos - self.selection.topLeft()
                return
        self._previous_selection = QRect(self.selection)
        self.origin = pos
        self._drag_mode = "draw"
        self.selection = QRect(pos, pos)
        self.toolbar.hide()
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._drag_mode == "draw" and self.origin is not None:
            self.selection = QRect(self.origin, pos).normalized()
            self.update()
            return
        if self._drag_mode == "move":
            target = pos - self._drag_offset
            target.setX(min(max(target.x(), 0),
                            max(self.width() - self.selection.width(), 0)))
            target.setY(min(max(target.y(), 0),
                            max(self.height() - self.selection.height(), 0)))
            self.selection.moveTopLeft(target)
            self._position_toolbar()
            self.update()
            return
        if self._drag_mode in self._HANDLES:
            self._resize_from_handle(pos)
            self._position_toolbar()
            self.update()
            return
        self._update_hover_cursor(pos)

    def _resize_from_handle(self, pos):
        start = self._drag_start
        delta = pos - self._press_point
        left, top, right, bottom = (start.left(), start.top(),
                                   start.right(), start.bottom())
        mode = self._drag_mode
        if "w" in mode:
            left = min(left + delta.x(), right - self.MIN_SIDE + 1)
        if "e" in mode:
            right = max(right + delta.x(), left + self.MIN_SIDE - 1)
        if "n" in mode:
            top = min(top + delta.y(), bottom - self.MIN_SIDE + 1)
        if "s" in mode:
            bottom = max(bottom + delta.y(), top + self.MIN_SIDE - 1)
        left = max(left, 0)
        top = max(top, 0)
        right = min(right, self.width() - 1)
        bottom = min(bottom, self.height() - 1)
        self.selection = QRect(QPoint(left, top), QPoint(right, bottom)).normalized()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._drag_mode == "draw":
            self.selection = QRect(self.origin, event.position().toPoint()).normalized()
            self.selection = self.selection.intersected(self.rect())
            self.origin = None
            self._drag_mode = None
            if (self.selection.width() < self.MIN_SIDE
                    or self.selection.height() < self.MIN_SIDE):
                self.selection = QRect(self._previous_selection)
                if self.selection.isNull():
                    self.toolbar.hide()
                else:
                    self._position_toolbar()
                self.update()
                return
            self._position_toolbar()
            self.update()
            return
        if self._drag_mode is not None:
            self._drag_mode = None
            self._position_toolbar()
            self.update()

    def mouseDoubleClickEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and not self.selection.isNull()
                and self.selection.contains(event.position().toPoint())):
            self._confirm()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm()
            return
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and event.key() == Qt.Key.Key_C):
            self._quick_copy()
            return
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and event.key() == Qt.Key.Key_S):
            self._quick_save()
            return
        super().keyPressEvent(event)


def save_image_to_file(image, conf, parent=None):
    """Ask for a path and write the image; returns (folder, format, name)."""
    image_format = conf.get("screenshot_format", "PNG") or "PNG"
    suffix = image_format.lower()
    configured = conf.get("screenshot_directory", "")
    folder = (Path(configured).expanduser() if configured else
              default_save_folder())
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = f"WordArc_{stamp}.{suffix}"
    initial_filter = (t("JPEG image (*.jpg *.jpeg)") if image_format == "JPEG"
                      else t("PNG image (*.png)"))
    path, _selected_filter = QFileDialog.getSaveFileName(
        parent, t("Save screenshot"), str(folder / name),
        t("PNG image (*.png);;JPEG image (*.jpg *.jpeg)"), initial_filter)
    if not path:
        return None
    target = Path(path)
    selected_format = ("JPEG" if _selected_filter.startswith("JPEG")
                       else "PNG")
    if target.suffix.lower() in (".jpg", ".jpeg"):
        selected_format = "JPEG"
    elif target.suffix.lower() == ".png":
        selected_format = "PNG"
    else:
        target = target.with_suffix(
            ".jpg" if selected_format == "JPEG" else ".png")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(target), selected_format,
                      95 if selected_format == "JPEG" else -1):
        raise OSError(t("Could not write the image file."))
    return str(target.parent), selected_format, target.name


class ScreenshotPreview(QDialog):
    """Local preview with explicit clipboard and disk actions."""

    failed = pyqtSignal(str)
    saved = pyqtSignal(str, str)

    def __init__(self, image, conf, parent=None):
        super().__init__(parent)
        self.image = image
        self.conf = conf
        self.setWindowTitle(t("Screenshot"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(780, 560)
        layout = QVBoxLayout(self)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)
        self.preview.setMinimumSize(280, 180)
        layout.addWidget(self.preview, 1)
        self.dimensions = QLabel(f"{image.width()} × {image.height()}")
        self.dimensions.setObjectName("muted")
        layout.addWidget(self.dimensions)
        actions = QHBoxLayout()
        self.copy_button = QPushButton(t("Copy image"))
        self.copy_button.clicked.connect(self._copy)
        self.save_button = QPushButton(t("Save image…"))
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._save)
        actions.addWidget(self.copy_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        self._refresh_preview()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_preview()

    def _refresh_preview(self):
        if not hasattr(self, "preview") or self.image.isNull():
            return
        pixmap = QPixmap.fromImage(self.image)
        self.preview.setPixmap(pixmap.scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _copy(self):
        copy_image_to_clipboard(self.image)
        self.copy_button.setText(t("Copied"))

    def _save(self):
        try:
            result = save_image_to_file(self.image, self.conf, self)
        except OSError as exc:
            self.failed.emit(str(exc))
            return
        if result is None:
            return
        directory, selected_format, name = result
        self.saved.emit(directory, selected_format)
        self.save_button.setText(t("Saved: {path}", path=name))


class ScreenshotController(QWidget):
    """Owns capture overlays and previews for WordArc's global hotkey and tab."""

    failed = pyqtSignal(str)
    preferences_saved = pyqtSignal(str, str)

    def __init__(self, conf, parent=None):
        super().__init__(None)
        self.conf = conf
        self._owner = parent
        self._overlay = None
        self._preview = None
        self._screen = None
        self._mode = "region"

        self._hidden_owner = None
        self._capture_owner = None
        self._capture_timer = QTimer(self)
        self._capture_timer.setSingleShot(True)
        self._capture_timer.setInterval(160)
        self._capture_timer.timeout.connect(self._capture_screen)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_preferences)
        self._pending_save_preferences = None
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)

    def start(self, mode="region", parent=None):
        if self._preview is not None and self._preview.isVisible():
            self._preview.raise_()
            self._preview.activateWindow()
            return
        if self._overlay is not None:
            self._cancel_overlay()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            self.failed.emit(t("No screen is available for capture."))
            return
        self._screen = screen
        self._mode = mode
        self._capture_owner = parent or self._owner
        owner = self._capture_owner
        if owner is not None and owner.isVisible():
            self._hidden_owner = owner
            owner.hide()
        else:
            self._hidden_owner = None
        self._capture_timer.start()

    def _capture_screen(self):
        try:
            pixmap = self._screen.grabWindow(0)
            if pixmap.isNull():
                raise OSError(t("Windows could not capture the screen."))
            if self._mode == "screen":
                self._show_preview(pixmap.toImage())
                return
            self._overlay = RegionOverlay(self._screen, pixmap)
            self._overlay.selected.connect(self._on_selected)
            self._overlay.copy_requested.connect(self._on_overlay_copy)
            self._overlay.save_requested.connect(self._on_overlay_save)
            self._overlay.cancelled.connect(self._cancel_overlay)
            self._overlay.show()
            self._overlay.raise_()
            self._overlay.activateWindow()
            self._overlay.setFocus()
        except Exception as exc:
            self._restore_owner()
            self.failed.emit(str(exc))

    def _on_selected(self, image):
        self._close_overlay()
        self._show_preview(image)

    def _on_overlay_copy(self, image):
        copy_image_to_clipboard(image)
        self._close_overlay()
        self._restore_owner()

    def _on_overlay_save(self, image):
        parent = (self._capture_owner
                  if self._capture_owner is not None
                  and self._capture_owner.isVisible() else None)
        try:
            result = save_image_to_file(image, self.conf, parent)
        except OSError as exc:
            self.failed.emit(str(exc))
            return
        if result is None:
            return
        directory, image_format, _name = result
        self._close_overlay()
        self._restore_owner()
        self._queue_save_preferences(directory, image_format)

    def _cancel_overlay(self):
        self._close_overlay()
        self._restore_owner()

    def _close_overlay(self):
        overlay, self._overlay = self._overlay, None
        if overlay is not None:
            overlay.close()
            overlay.deleteLater()

    def _restore_owner(self, *_):
        owner, self._hidden_owner = self._hidden_owner, None
        if owner is not None:
            owner.show()
            owner.raise_()
            owner.activateWindow()

    def _show_preview(self, image):
        if image.isNull():
            self._restore_owner()
            self.failed.emit(t("Windows could not capture the screen."))
            return
        parent = (self._capture_owner
                  if self._capture_owner is not None
                  and self._capture_owner.isVisible() else None)
        if self._preview is not None:
            self._preview.close()
            self._preview.deleteLater()
        self._preview = ScreenshotPreview(image, self.conf, parent)
        self._preview.finished.connect(self._restore_owner)
        self._preview.failed.connect(self.failed)
        self._preview.saved.connect(self._queue_save_preferences)
        self._preview.show()
        self._preview.raise_()
        self._preview.activateWindow()

    def _queue_save_preferences(self, directory, image_format):
        self._pending_save_preferences = (directory, image_format)
        self._save_timer.start(0)

    def _save_preferences(self):
        preferences, self._pending_save_preferences = (
            self._pending_save_preferences, None)
        if preferences is None:
            return
        directory, image_format = preferences
        try:
            self.conf["screenshot_directory"] = directory
            self.conf["screenshot_format"] = image_format
            self.conf.save()
            self.preferences_saved.emit(directory, image_format)
        except OSError as exc:
            logging.getLogger("wordarc.screenshot").warning(
                "could not save screenshot preferences: %s", exc)
            self.failed.emit(str(exc))

    def shutdown(self):
        """Tear down capture UI without reopening its hidden owner on app exit."""
        self._capture_timer.stop()
        self._save_timer.stop()
        self._close_overlay()
        preview, self._preview = self._preview, None
        if preview is not None:
            preview.blockSignals(True)
            preview.close()
        self._hidden_owner = None

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)


def copy_image_to_clipboard(image: QImage) -> None:
    QGuiApplication.clipboard().setPixmap(QPixmap.fromImage(image))