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
    """Lightshot-style full-screen dimmer and drag-to-select overlay."""

    selected = pyqtSignal(QImage)
    cancelled = pyqtSignal()

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
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle(t("Select screenshot area"))

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
        elif self.origin is None:
            painter.setPen(QColor("white"))
            painter.drawText(target, int(Qt.AlignmentFlag.AlignCenter),
                             t("Drag to select · Esc to cancel"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.selection = QRect(self.origin, self.origin)
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.selection = QRect(self.origin, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.origin is None:
            return
        self.selection = QRect(self.origin, event.position().toPoint()).normalized()
        try:
            image = crop_screen_image(self.screenshot.toImage(), self.selection,
                                      self._screen_size)
        except ValueError:
            self.origin = None
            self.selection = QRect()
            self.update()
            return
        self.selected.emit(image)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)


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
        image_format = self.conf.get("screenshot_format", "PNG") or "PNG"
        suffix = image_format.lower()
        configured = self.conf.get("screenshot_directory", "")
        folder = (Path(configured).expanduser() if configured else
                  default_save_folder())
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name = f"WordArc_{stamp}.{suffix}"
        initial_filter = (t("JPEG image (*.jpg *.jpeg)") if image_format == "JPEG"
                          else t("PNG image (*.png)"))
        path, _selected_filter = QFileDialog.getSaveFileName(
            self, t("Save screenshot"), str(folder / name),
            t("PNG image (*.png);;JPEG image (*.jpg *.jpeg)"), initial_filter)
        if not path:
            return
        try:
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
            if not self.image.save(str(target), selected_format,
                                   95 if selected_format == "JPEG" else -1):
                raise OSError(t("Could not write the image file."))
            self.saved.emit(str(target.parent), selected_format)
            self.save_button.setText(t("Saved: {path}", path=target.name))
        except OSError as exc:
            self.failed.emit(str(exc))


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