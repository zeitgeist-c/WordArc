"""Screenshot capture: an in-place annotation editor over the frozen screen.

The user drags a region and annotates it right there — arrows, shapes, pen,
highlighter, numbered steps, blur/pixelate patches, text with font options —
then copies or saves the result. Nothing is captured until the toolbar is used.
"""

from __future__ import annotations

from datetime import datetime
import logging
import threading
from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, QSize, QStandardPaths, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QCursor, QFont, QGuiApplication, QIcon, QImage,
                         QPainter, QPen, QPixmap, QScreen)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (QButtonGroup, QColorDialog, QDialog,
                             QFileDialog, QFrame, QHBoxLayout, QToolButton, QSpinBox,
                             QVBoxLayout, QWidget)

import ocr
from i18n import t
from screenshot_editor import (DEFAULT_COLOR, DEFAULT_WIDTH, LINE_TOOLS,
                               REGION_TOOLS, STEP_RADIUS, TOOLS,
                               AnnotationModel, TextDialog, clone_item)


def _tool_icon(name, color="#e9edf5"):
    """Small vector glyphs, rendered at 2x for crisp toolbar buttons on HiDPI."""
    paths = {
        "select": '<path d="M5 3v16l4-5 4 7 3-2-4-6h7z"/>',
        "pen": '<path d="m4 16-1 5 5-1L20 8l-4-4zM14 6l4 4"/>',
        "line": '<path d="m4 20 16-16"/>',
        "arrow": '<path d="M4 20 20 4M9 4h11v11"/>',
        "rect": '<rect x="4" y="5" width="16" height="14" rx="1"/>',
        "ellipse": '<ellipse cx="12" cy="12" rx="9" ry="7"/>',
        "highlight": '<path d="m5 13 8-9 6 5-8 9zM3 21h13M5 14l-2 5 6-2"/>',
        "text": '<path d="M4 6V4h16v2M12 4v16M8 20h8"/>',
        "step": '<circle cx="12" cy="12" r="9"/><path d="m9 9 3-2v10M9 17h6"/>',
        "blur": '<path d="M12 3C9 8 5 11 5 15a7 7 0 0 0 14 0c0-4-4-7-7-12zM9 14v3M12 12v6M15 14v3"/>',
        "pixelate": '<path d="M4 4h16v16H4zM4 10h16M4 15h16M10 4v16M15 4v16"/>',
        "undo": '<path d="m8 4-5 5 5 5M3 9h11a6 6 0 0 1 0 12"/>',
        "redo": '<path d="m16 4 5 5-5 5M21 9H10a6 6 0 0 0 0 12"/>',
        "copy": '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M15 8V3H3v13h5"/>',
        "ocr": '<path d="M4 7V4h16v3M4 17v3h16v-3M8 9h9M8 13h6"/>',
        "speak": '<path d="M4 9v6h4l5 4V5L8 9H4zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/>',
        "save": '<path d="M4 3h13l4 4v14H3V3zM7 3v6h10V3M7 21v-8h10v8"/>',
        "cancel": '<path d="m6 6 12 12M18 6 6 18"/>',
        "color": f'<circle cx="12" cy="12" r="8" fill="{color}" stroke="#ffffff"/>',
        "fill": f'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 12h16v8H4z" fill="{color}"/>',
    }
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
           f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
           f'{paths[name]}</svg>')
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(svg.encode())
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


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
    """Lightshot-style overlay: select an area and annotate it right there.

    The desktop is frozen behind a dim layer; inside the selection the
    original pixels plus every annotation are shown, and the toolbar under
    the selection edits them in place. Copy/Save export the annotated crop.
    """

    copy_requested = pyqtSignal(QImage)
    save_requested = pyqtSignal(QImage)
    ocr_requested = pyqtSignal(QImage)
    speak_requested = pyqtSignal(QImage)
    cancelled = pyqtSignal()
    activated = pyqtSignal()

    HANDLE = 10
    MIN_SIDE = 6
    _HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
    TOOL_LABELS = {
        "select": "Select", "pen": "Pen", "line": "Line", "arrow": "Arrow",
        "rect": "Rectangle", "ellipse": "Ellipse", "highlight": "Highlight",
        "text": "Text", "step": "Step", "blur": "Blur", "pixelate": "Pixelate",
    }
    TOOL_KEYS = {"select": "V", "pen": "P", "line": "L", "arrow": "A",
                 "rect": "R", "ellipse": "E", "highlight": "H",
                 "text": "T", "step": "N", "blur": "B", "pixelate": "M"}

    def __init__(self, screen, screenshot, selection=None):
        super().__init__(None, Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.screen = screen
        self.screenshot = screenshot
        self._screen_size = screen.geometry().size()
        width = self._screen_size.width() or 1
        self._scale = (screenshot.width() / width
                       if screenshot.width() else 1.0)
        self.selection = QRect(selection) if selection is not None else QRect()
        self.selection = self.selection.intersected(self._screen_rect())
        self.model = AnnotationModel()
        self.tool = "select"
        self.color = QColor(DEFAULT_COLOR)
        self.stroke_width = DEFAULT_WIDTH

        self.origin = None
        self._drag_mode = None
        self._drag_offset = QPoint()
        self._drag_start = QRect()
        self._press_point = QPoint()
        self._previous_selection = QRect()
        self._current = None
        self._moving_index = None
        self._item_start = None
        self._handle_item = None
        self._rendered = None

        if isinstance(screen, QScreen):
            self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle(t("Select screenshot area"))
        self._build_toolbar()
        self._rebuild(refresh=False)
        self._position_toolbar()

    # ---- chrome ----------------------------------------------------------

    def _screen_rect(self):
        return QRect(QPoint(0, 0), self._screen_size)

    def _toolbar_sep(self, row):
        sep = QFrame(self.toolbar)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedWidth(3)
        sep.setFixedHeight(18)
        sep.setStyleSheet("color: #4a5266;")
        row.addWidget(sep)

    def _build_toolbar(self):
        self.toolbar = QFrame(self)
        self.toolbar.setObjectName("captureToolbar")
        self.toolbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.toolbar.setStyleSheet("""
            QFrame#captureToolbar {
                background: #20242e; border: 1px solid #444b5c;
                border-radius: 10px;
            }
            QToolButton {
                background: transparent; border: 1px solid transparent;
                border-radius: 6px; padding: 0; color: #e9edf5;
            }
            QToolButton:hover { background: #383f50; border-color: #59647b; }
            QToolButton:checked { background: #554477; border-color: #ae91ef; }
            QToolButton:pressed { background: #63518a; }
            QToolButton:disabled { background: transparent; border-color: transparent; }
            QToolButton#screenshotOverlayCopy,
            QToolButton#screenshotOverlayOcr,
            QToolButton#screenshotOverlaySpeak { background: #665096; }
            QToolButton#screenshotOverlayCopy:hover,
            QToolButton#screenshotOverlayOcr:hover,
            QToolButton#screenshotOverlaySpeak:hover { background: #8064b8; }
            QToolButton#screenshotOverlayCancel:hover { background: #823d4c; }
            QSpinBox {
                background: #2d3341; color: #e9edf5; border: 1px solid #444b5c;
                border-radius: 5px; padding: 1px; min-width: 28px;
            }
            QToolTip { background: #20242e; color: #ffffff; border: 1px solid #59647b; }
        """)
        layout = QVBoxLayout(self.toolbar)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)

        # Tools sit in meaning groups behind thin separators: navigation and
        # freehand, shapes with the Fill switch that belongs to them,
        # annotation, and the pixel effects. Grouping reads at a glance where
        # the old flat run of eleven icons did not.
        self.tool_buttons = {}
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        for name in TOOLS:
            button = self._toolbar_button(name, self.TOOL_LABELS[name],
                                          self.TOOL_KEYS[name])
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, tool=name: self._set_tool(tool))
            self._tool_group.addButton(button)
            self.tool_buttons[name] = button

        self.fill_check = self._toolbar_button("fill", "Fill")
        self.fill_check.setCheckable(True)

        tools = QHBoxLayout()
        tools.setSpacing(2)
        groups = (
            ("select", "pen", "line", "arrow"),
            ("rect", "ellipse"),
            ("highlight", "text", "step"),
            ("blur", "pixelate"),
        )
        for index, group in enumerate(groups):
            if index:
                self._toolbar_sep(tools)
            for name in group:
                tools.addWidget(self.tool_buttons[name])
            if group[-1] == "ellipse":
                # Fill only ever paints the shape tools' interiors, so the
                # switch lives inside their group instead of a far row.
                tools.addWidget(self.fill_check)
        layout.addLayout(tools)

        options = QHBoxLayout()
        options.setSpacing(2)
        self.color_button = self._toolbar_button("color", "Color")
        self.color_button.setIcon(_tool_icon("color", self.color.name()))
        self.color_button.clicked.connect(self._choose_color)
        options.addWidget(self.color_button)
        self.width_box = QSpinBox()
        self.width_box.setRange(1, 40)
        self.width_box.setValue(DEFAULT_WIDTH)
        self.width_box.setToolTip(t("Width"))
        self.width_box.setAccessibleName(t("Width"))
        self.width_box.setFixedWidth(40)
        self.width_box.setFixedHeight(26)
        self.width_box.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.width_box.valueChanged.connect(self._set_width)
        options.addWidget(self.width_box)
        self._toolbar_sep(options)
        self.undo_button = self._toolbar_button("undo", "Undo", "Ctrl+Z")
        self.undo_button.clicked.connect(self._undo)
        options.addWidget(self.undo_button)
        self.redo_button = self._toolbar_button("redo", "Redo", "Ctrl+Y")
        self.redo_button.clicked.connect(self._redo)
        options.addWidget(self.redo_button)
        self._toolbar_sep(options)
        self.copy_button = self._toolbar_button("copy", "Copy", "Ctrl+C")
        self.copy_button.setObjectName("screenshotOverlayCopy")
        self.copy_button.clicked.connect(self._quick_copy)
        options.addWidget(self.copy_button)
        self.ocr_button = self._toolbar_button("ocr", "Extract text (OCR)")
        self.ocr_button.setObjectName("screenshotOverlayOcr")
        self.ocr_button.clicked.connect(self._quick_ocr)
        # A machine without the WinRT projections or an OCR language pack
        # still captures; it just never sees a button that cannot work.
        self.ocr_button.setVisible(ocr.is_available())
        options.addWidget(self.ocr_button)
        self.speak_button = self._toolbar_button("speak", "Read aloud")
        self.speak_button.setObjectName("screenshotOverlaySpeak")
        self.speak_button.clicked.connect(self._quick_speak)
        # Reading needs the same OCR engine, so it shares its visibility.
        self.speak_button.setVisible(ocr.is_available())
        options.addWidget(self.speak_button)
        self.save_button = self._toolbar_button("save", "Save", "Ctrl+S")
        self.save_button.setObjectName("screenshotOverlaySave")
        self.save_button.clicked.connect(self._quick_save)
        options.addWidget(self.save_button)
        self.cancel_button = self._toolbar_button("cancel", "Cancel", "Esc")
        self.cancel_button.setObjectName("screenshotOverlayCancel")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        options.addWidget(self.cancel_button)
        layout.addLayout(options)
        self.toolbar.hide()
        self._set_tool("select")

    def _toolbar_button(self, icon, label, shortcut=""):
        button = QToolButton(self.toolbar)
        button.setIcon(_tool_icon(icon))
        button.setIconSize(QSize(17, 17))
        button.setFixedSize(26, 26)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(t(label) + (f" ({shortcut})" if shortcut else ""))
        button.setAccessibleName(t(label))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _set_tool(self, name):
        if name not in TOOLS:
            return
        self.tool = name
        button = self.tool_buttons.get(name)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        if name != "select":
            self.model.selected = None
        self.fill_check.setEnabled(name in ("rect", "ellipse"))
        self.update()

    def _choose_color(self):
        color = QColorDialog.getColor(self.color, self, t("Color"))
        if color.isValid():
            self.color = color
            self.color_button.setIcon(_tool_icon("color", color.name()))

    def _set_width(self, value):
        self.stroke_width = max(1, int(value))

    def _position_toolbar(self):
        if self.selection.isNull():
            self.toolbar.hide()
            return
        self.toolbar.adjustSize()
        size = self.toolbar.sizeHint()
        x = min(max(self.selection.left(), 0),
                max(self.width() - size.width(), 0))
        y = self.selection.bottom() + 8
        if y + size.height() > self.height():
            y = self.selection.top() - 8 - size.height()
        self.toolbar.move(x, max(y, 0))
        self.toolbar.show()
        self.toolbar.raise_()

    # ---- rendering -------------------------------------------------------

    def _rebuild(self, refresh=True):
        image = self.model.render(self.screenshot.toImage(), self._scale)
        self._rendered = QPixmap.fromImage(image)
        self.undo_button.setEnabled(bool(self.model._undo))
        self.redo_button.setEnabled(bool(self.model._redo))
        if refresh:
            self.update()

    def _export_image(self):
        if self.selection.isNull():
            return None
        rendered = self.model.render(self.screenshot.toImage(), self._scale)
        try:
            return crop_screen_image(rendered, self.selection,
                                     self._screen_size)
        except ValueError:
            return None

    def _quick_copy(self):
        image = self._export_image()
        if image is None:
            return
        self.copy_requested.emit(image)

    def _quick_save(self):
        image = self._export_image()
        if image is None:
            return
        self.save_requested.emit(image)

    def _quick_ocr(self):
        image = self._export_image()
        if image is None:
            return
        self.ocr_requested.emit(image)

    def _quick_speak(self):
        image = self._export_image()
        if image is None:
            return
        self.speak_requested.emit(image)

    def _undo(self):
        if self.model.undo():
            self._rebuild()

    def _redo(self):
        if self.model.redo():
            self._rebuild()

    # ---- geometry helpers ------------------------------------------------

    def _handle_rects(self):
        selection = self.selection
        if selection.isNull():
            return {}
        half = self.HANDLE // 2
        cx = selection.left() + selection.width() // 2
        cy = selection.top() + selection.height() // 2
        points = {"nw": (selection.left(), selection.top()),
                  "n": (cx, selection.top()),
                  "ne": (selection.right(), selection.top()),
                  "e": (selection.right(), cy),
                  "se": (selection.right(), selection.bottom()),
                  "s": (cx, selection.bottom()),
                  "sw": (selection.left(), selection.bottom()),
                  "w": (selection.left(), cy)}
        return {key: QRect(x - half, y - half, self.HANDLE, self.HANDLE)
                for key, (x, y) in points.items()}

    @staticmethod
    def _point_handle(point):
        half = RegionOverlay.HANDLE // 2
        return QRect(point.x() - half, point.y() - half,
                     RegionOverlay.HANDLE, RegionOverlay.HANDLE)

    def _item_handle_rects(self):
        index = self.model.selected
        if index is None or not (0 <= index < len(self.model.items)):
            return {}
        item = self.model.items[index]
        if item["type"] in REGION_TOOLS:
            rect = item["rect"]
            half = self.HANDLE // 2
            cx = rect.left() + rect.width() // 2
            cy = rect.top() + rect.height() // 2
            points = {"nw": (rect.left(), rect.top()),
                      "n": (cx, rect.top()),
                      "ne": (rect.right(), rect.top()),
                      "e": (rect.right(), cy),
                      "se": (rect.right(), rect.bottom()),
                      "s": (cx, rect.bottom()),
                      "sw": (rect.left(), rect.bottom()),
                      "w": (rect.left(), cy)}
            return {key: QRect(x - half, y - half, self.HANDLE, self.HANDLE)
                    for key, (x, y) in points.items()}
        if item["type"] in LINE_TOOLS:
            return {"start": self._point_handle(item["start"]),
                    "end": self._point_handle(item["end"])}
        return {}

    def _resized_rect(self, start, pos, mode):
        delta = pos - self._press_point
        left, top, right, bottom = (start.left(), start.top(),
                                    start.right(), start.bottom())
        if "w" in mode:
            left = min(left + delta.x(), right - self.MIN_SIDE + 1)
        if "e" in mode:
            right = max(right + delta.x(), left + self.MIN_SIDE - 1)
        if "n" in mode:
            top = min(top + delta.y(), bottom - self.MIN_SIDE + 1)
        if "s" in mode:
            bottom = max(bottom + delta.y(), top + self.MIN_SIDE - 1)
        return QRect(QPoint(left, top), QPoint(right, bottom)).normalized()

    @staticmethod
    def _translate_item(item, source, delta):
        for key in ("rect", "start", "end", "pos"):
            if key in source:
                value = source[key]
                item[key] = (QRect(value).translated(delta)
                             if isinstance(value, QRect)
                             else QPoint(value) + delta)
        if "points" in source:
            item["points"] = [QPoint(point) + delta for point in source["points"]]

    def _clamp_item(self, item):
        rect = AnnotationModel.item_rect(item)
        dx = dy = 0
        if rect.left() < 0:
            dx = -rect.left()
        elif rect.right() > self.width():
            dx = self.width() - rect.right()
        if rect.top() < 0:
            dy = -rect.top()
        elif rect.bottom() > self.height():
            dy = self.height() - rect.bottom()
        if dx or dy:
            self._translate_item(item, item, QPoint(dx, dy))

    def _update_hover_cursor(self, pos):
        for key, rect in self._handle_rects().items():
            if rect.contains(pos):
                self._set_resize_cursor(key)
                return
        if self.tool == "select":
            for key, rect in self._item_handle_rects().items():
                if rect.contains(pos):
                    self._set_resize_cursor(
                        key if key in self._HANDLES else "nw")
                    return
            if (self.model.hit_test(pos) is not None
                    or (not self.selection.isNull()
                        and self.selection.contains(pos))):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _set_resize_cursor(self, key):
        if key in ("nw", "se"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif key in ("ne", "sw"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif key in ("n", "s"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeHorCursor)

    # ---- painting --------------------------------------------------------

    def paintEvent(self, _event):
        painter = QPainter(self)
        target = self.rect()
        painter.drawPixmap(target, self.screenshot)
        painter.fillRect(target, QColor(0, 0, 0, 110))
        if self.selection.isNull():
            painter.setPen(QColor("white"))
            painter.drawText(target, int(Qt.AlignmentFlag.AlignCenter),
                             t("Drag to select · Esc to cancel"))
            painter.end()
            return
        painter.save()
        painter.setClipRect(self.selection)
        if self._rendered is not None:
            painter.drawPixmap(target, self._rendered)
        if self._current is not None:
            AnnotationModel.draw_item(painter, self._current)
        painter.restore()
        if self.tool == "select":
            index = self.model.selected
            if index is not None and 0 <= index < len(self.model.items):
                AnnotationModel.draw_selection(
                    painter, self.model.items[index])
        painter.setPen(QPen(QColor("#9475EC"), 2))
        painter.drawRect(self.selection.adjusted(0, 0, -1, -1))
        painter.setPen(QColor("white"))
        painter.drawText(self.selection.adjusted(8, 6, -8, -6),
                         int(Qt.AlignmentFlag.AlignLeft
                             | Qt.AlignmentFlag.AlignTop),
                         f"{self.selection.width()} × {self.selection.height()}")
        painter.setPen(QPen(QColor("white"), 2))
        painter.setBrush(QColor("white"))
        for rect in self._handle_rects().values():
            painter.drawRect(rect)
        if self.tool == "select":
            painter.setPen(QPen(QColor("#9475EC"), 2))
            painter.setBrush(QColor("#9475EC"))
            for rect in self._item_handle_rects().values():
                painter.drawRect(rect)
        painter.end()

    # ---- interaction -----------------------------------------------------

    def _start_selection(self, pos):
        self._previous_selection = QRect(self.selection)
        self.origin = pos
        self._drag_mode = "draw"
        self.selection = QRect(pos, pos)
        self.model.selected = None
        self.toolbar.hide()
        self.update()

    def _press_inside(self, pos):
        if self.tool == "select":
            for key, rect in self._item_handle_rects().items():
                if rect.contains(pos):
                    index = self.model.selected
                    self.model.begin()
                    self._drag_mode = "item-handle"
                    self._handle_item = key
                    self._moving_index = index
                    self._item_start = clone_item(self.model.items[index])
                    self._press_point = pos
                    return
            index = self.model.hit_test(pos)
            if index is not None:
                self.model.selected = index
                self.model.begin()
                self._drag_mode = "item"
                self._moving_index = index
                self._item_start = clone_item(self.model.items[index])
                self._press_point = pos
                self.update()
                return
            self.model.selected = None
            self._drag_mode = "move"
            self._press_point = pos
            self._drag_start = QRect(self.selection)
            self._drag_offset = pos - self.selection.topLeft()
            self.update()
            return
        if self.tool == "text":
            self._ask_text(pos)
            return
        if self.tool == "step":
            self.model.add({"type": "step", "pos": QPoint(pos),
                            "number": self.model.next_step(),
                            "color": QColor(self.color),
                            "radius": STEP_RADIUS})
            self._rebuild()
            return
        self._start_item(pos)

    def _start_item(self, pos):
        if self.tool == "pen":
            self._current = {"type": "pen", "points": [QPoint(pos)],
                             "color": QColor(self.color),
                             "width": self.stroke_width}
        elif self.tool in ("line", "arrow", "highlight"):
            self._current = {"type": self.tool, "start": QPoint(pos),
                             "end": QPoint(pos), "color": QColor(self.color),
                             "width": self.stroke_width}
        elif self.tool in REGION_TOOLS:
            self._current = {"type": self.tool, "start": QPoint(pos),
                             "end": QPoint(pos), "color": QColor(self.color),
                             "width": self.stroke_width,
                             "fill": self.fill_check.isChecked()}
        self.update()

    def _commit_current(self):
        item, self._current = self._current, None
        if item is None:
            return
        kind = item["type"]
        if kind in REGION_TOOLS:
            rect = QRect(item["start"], item["end"]).normalized()
            if rect.width() < 3 or rect.height() < 3:
                self.update()
                return
            item["rect"] = rect
            item.pop("start", None)
            item.pop("end", None)
        elif kind in ("line", "arrow", "highlight"):
            if (item["start"] - item["end"]).manhattanLength() < 3:
                self.update()
                return
        elif kind == "pen":
            if len(item.get("points", [])) < 2:
                self.update()
                return
        self.model.add(item)
        self._rebuild()

    def _place_text(self, pos, text, font, color):
        if not str(text).strip():
            return
        item = {"type": "text", "pos": QPoint(pos), "text": text,
                "font": font, "color": color}
        self.model.add(item)
        self._clamp_item(item)
        self._rebuild()

    def _ask_text(self, pos):
        dialog = TextDialog(self, "", QFont(), QColor(self.color))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text, font, color = dialog.values()
        self._place_text(pos, text, font, color)

    def mouseDoubleClickEvent(self, event):
        if (event.button() != Qt.MouseButton.LeftButton
                or self.selection.isNull()
                or not self.selection.contains(event.position().toPoint())):
            return
        index = self.model.hit_test(event.position().toPoint())
        if index is None:
            return
        item = self.model.items[index]
        if item["type"] != "text":
            return
        dialog = TextDialog(self, item.get("text", ""), item.get("font"),
                            item.get("color"))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text, font, color = dialog.values()
        if not text.strip():
            return
        self.model.begin()
        item["text"], item["font"], item["color"] = text, font, color
        self.model.selected = index
        self._rebuild()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.activated.emit()
        pos = event.position().toPoint()
        if not self.selection.isNull():
            for key, rect in self._handle_rects().items():
                if rect.contains(pos):
                    self._drag_mode = key
                    self._press_point = pos
                    self._drag_start = QRect(self.selection)
                    self._drag_offset = pos - self.selection.topLeft()
                    return
            if self.selection.contains(pos):
                self._press_inside(pos)
                return
        self._start_selection(pos)

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
            self.selection = self._resized_rect(
                self._drag_start, pos, self._drag_mode)
            self._position_toolbar()
            self.update()
            return
        if self._drag_mode == "item" and self._moving_index is not None:
            item = self.model.items[self._moving_index]
            self._translate_item(item, self._item_start,
                                 pos - self._press_point)
            self._clamp_item(item)
            self._rebuild()
            return
        if self._drag_mode == "item-handle" and self._moving_index is not None:
            item = self.model.items[self._moving_index]
            source = self._item_start
            if item["type"] in REGION_TOOLS:
                item["rect"] = self._resized_rect(
                    source["rect"], pos, self._handle_item)
            elif self._handle_item == "start":
                item["start"] = QPoint(pos)
            else:
                item["end"] = QPoint(pos)
            self._clamp_item(item)
            self._rebuild()
            return
        if self._current is not None:
            if self._current["type"] == "pen":
                self._current["points"].append(QPoint(pos))
            else:
                self._current["end"] = QPoint(pos)
            self.update()
            return
        self._update_hover_cursor(pos)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        mode = self._drag_mode
        if mode == "draw":
            self.selection = QRect(self.origin,
                                   event.position().toPoint()).normalized()
            self.selection = self.selection.intersected(self._screen_rect())
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
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # Lightshot habit: Ctrl held while dragging copies at once.
                self._quick_copy()
        elif mode in ("item", "item-handle"):
            self._drag_mode = None
            self._moving_index = None
            self._item_start = None
            self._handle_item = None
            self._position_toolbar()
            self.update()
        elif mode is not None:
            self._drag_mode = None
            self._position_toolbar()
            self.update()
        if self._current is not None:
            self._commit_current()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        control = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if key == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._quick_copy()
            return
        if control and key == Qt.Key.Key_C:
            self._quick_copy()
            return
        if control and key == Qt.Key.Key_A:
            self.selection = self._screen_rect()
            self._position_toolbar()
            self.update()
            return
        if control and key == Qt.Key.Key_S:
            self._quick_save()
            return
        if control and key == Qt.Key.Key_Z:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self._redo()
            else:
                self._undo()
            return
        if control and key == Qt.Key.Key_Y:
            self._redo()
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not mods:
            if self.model.remove_selected():
                self._rebuild()
            return
        if key == Qt.Key.Key_Delete and mods == Qt.KeyboardModifier.ShiftModifier:
            if self.model.clear():
                self._rebuild()
            return
        if not mods:
            for tool, letter in self.TOOL_KEYS.items():
                if key == ord(letter):
                    self._set_tool(tool)
                    return
        if (key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up,
                    Qt.Key.Key_Down)
                and self.model.selected is not None):
            step = 10 if mods & Qt.KeyboardModifier.ShiftModifier else 1
            delta = {Qt.Key.Key_Left: QPoint(-step, 0),
                     Qt.Key.Key_Right: QPoint(step, 0),
                     Qt.Key.Key_Up: QPoint(0, -step),
                     Qt.Key.Key_Down: QPoint(0, step)}[key]
            index = self.model.selected
            self.model.begin()
            self._translate_item(self.model.items[index],
                                 self.model.items[index], delta)
            self._clamp_item(self.model.items[index])
            self._rebuild()
            return
        if (key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up,
                    Qt.Key.Key_Down) and not self.selection.isNull()):
            step = 10 if mods & Qt.KeyboardModifier.ShiftModifier else 1
            delta = {Qt.Key.Key_Left: QPoint(-step, 0),
                     Qt.Key.Key_Right: QPoint(step, 0),
                     Qt.Key.Key_Up: QPoint(0, -step),
                     Qt.Key.Key_Down: QPoint(0, step)}[key]
            moved = self.selection.translated(delta)
            moved.moveLeft(max(0, min(moved.left(), self.width() - moved.width())))
            moved.moveTop(max(0, min(moved.top(), self.height() - moved.height())))
            self.selection = moved
            self._position_toolbar()
            self.update()
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
    if selected_format == "JPEG" and image.hasAlphaChannel():
        opaque = QImage(image.size(), QImage.Format.Format_RGB32)
        opaque.fill(Qt.GlobalColor.white)
        painter = QPainter(opaque)
        painter.drawImage(0, 0, image)
        painter.end()
        image = opaque
    if not image.save(str(target), selected_format,
                      95 if selected_format == "JPEG" else -1):
        raise OSError(t("Could not write the image file."))
    return str(target.parent), selected_format, target.name


class ScreenshotController(QWidget):
    """Owns the capture overlay for WordArc's global hotkey and tab."""

    failed = pyqtSignal(str)
    preferences_saved = pyqtSignal(str, str)
    ocr_done = pyqtSignal(str)
    speak_done = pyqtSignal(str)

    def __init__(self, conf, parent=None):
        super().__init__(None)
        self.conf = conf
        self._owner = parent
        self._overlay = None
        self._overlays = []
        self._screen = None
        self._mode = "region"
        self._speak_next = False

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
        self._ocr_thread = None
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        QGuiApplication.instance().screenRemoved.connect(self._screen_removed)

    def start(self, mode="region", parent=None, speak=False):
        self._capture_timer.stop()
        if self._overlay is not None or self._hidden_owner is not None:
            self._cancel_overlay()
        screen = (QGuiApplication.screenAt(QCursor.pos())
                  or QGuiApplication.primaryScreen())
        if screen is None:
            self.failed.emit(t("No screen is available for capture."))
            return
        self._screen = screen
        self._mode = mode
        self._speak_next = speak
        self._capture_owner = parent or self._owner
        owner = self._capture_owner
        if owner is not None and owner.isVisible():
            self._hidden_owner = owner
            owner.hide()
        else:
            self._hidden_owner = None
        self._capture_timer.start()

    def _active_window_rect(self):
        """The foreground window's geometry, in screen-local coordinates."""
        import ctypes
        from ctypes import wintypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        origin = self._screen.geometry().topLeft()
        window = QRect(rect.left - origin.x(), rect.top - origin.y(),
                       rect.right - rect.left, rect.bottom - rect.top)
        window = window.intersected(
            QRect(QPoint(0, 0), self._screen.geometry().size()))
        if window.width() < 2 or window.height() < 2:
            return None
        return window

    def _capture_screen(self):
        try:
            screens = (QGuiApplication.screens() if self._mode == "region"
                       else [self._screen])
            if not screens:
                raise OSError(t("No screen is available for capture."))
            # Freeze ALL displays before showing any overlay. Otherwise a
            # previous overlay can be captured on a neighbouring display.
            captures = []
            for screen in screens:
                pixmap = screen.grabWindow(0)
                if pixmap.isNull():
                    raise OSError(t("Windows could not capture the screen."))
                captures.append((screen, pixmap))
            selection = None
            if self._mode == "screen":
                selection = QRect(QPoint(0, 0), self._screen.geometry().size())
            elif self._mode == "window":
                selection = self._active_window_rect()
                if selection is None:
                    raise OSError(
                        t("No active window is available for capture."))
            for screen, pixmap in captures:
                overlay = RegionOverlay(screen, pixmap, selection)
                self._overlays.append(overlay)
                overlay.activated.connect(
                    lambda current=overlay: self._activate_overlay(current))
                overlay.copy_requested.connect(self._on_overlay_copy)
                overlay.save_requested.connect(self._on_overlay_save)
                overlay.ocr_requested.connect(self._on_overlay_ocr)
                overlay.speak_requested.connect(self._on_overlay_speak)
                overlay.cancelled.connect(self._cancel_overlay)
                if screen is self._screen or self._overlay is None:
                    self._overlay = overlay
            for overlay in self._overlays:
                overlay.show()
                overlay.raise_()
            self._overlay.activateWindow()
            self._overlay.setFocus()
        except Exception as exc:
            self._close_overlay()
            self._restore_owner()
            self.failed.emit(str(exc))

    def _activate_overlay(self, current):
        """Choose a display without cancelling/restarting the capture session."""
        if current is self._overlay:
            return
        for overlay in self._overlays:
            if overlay is current:
                continue
            overlay.selection = QRect()
            overlay.model.selected = None
            overlay.toolbar.hide()
            overlay.update()
        self._overlay = current
        current.activateWindow()

    def _screen_removed(self, screen):
        if (self._capture_timer.isActive() or self._overlays
                or self._overlay is not None):
            self._capture_timer.stop()
            self._cancel_overlay()

    def _on_overlay_copy(self, image):
        copy_image_to_clipboard(image)
        self._close_overlay()
        self._restore_owner()

    def _on_overlay_ocr(self, image, restore_owner=True):
        # Recognition runs on a worker thread: a full-screen selection keeps
        # the Windows engine busy for a second or two, and the frozen desktop
        # must stay responsive meanwhile. The overlay closes right away —
        # results arrive as a clipboard write plus a tray note.
        if self._ocr_thread is not None and self._ocr_thread.is_alive():
            return
        self._close_overlay()
        if restore_owner:
            self._restore_owner()
        else:
            # The toolbar's Read button keeps working from the tray: drop
            # the hidden window without bringing it back to the front.
            self._hidden_owner = None

        language = ""
        try:
            language = str(self.conf.get("ui_language", ""))
        except Exception:
            pass
        speak = self._speak_next
        self._speak_next = False

        def work():
            try:
                text = ocr.extract_text(image, language)
            except ocr.OcrUnavailable as exc:
                self.failed.emit(str(exc))
                return
            if speak:
                self.speak_done.emit(text)
            else:
                self.ocr_done.emit(text)

        self._ocr_thread = threading.Thread(target=work, daemon=True)
        self._ocr_thread.start()

    def _on_overlay_speak(self, image):
        # The toolbar's Read button always reads: flag the OCR result for
        # speech no matter how the capture was started. The window stays
        # hidden; reading runs from the tray, stopped from its menu.
        self._speak_next = True
        self._on_overlay_ocr(image, restore_owner=False)

    def _on_overlay_save(self, image):
        # Parent the native file dialog to the topmost editor. Otherwise it
        # can appear behind the frozen desktop and look like a hung capture.
        parent = self._overlay or (self._capture_owner
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
        overlays, self._overlays = self._overlays, []
        if overlay is not None and overlay not in overlays:
            overlays.append(overlay)
        for window in overlays:
            window.close()
            window.deleteLater()

    def _restore_owner(self, *_):
        owner, self._hidden_owner = self._hidden_owner, None
        if owner is not None:
            owner.show()
            owner.raise_()
            owner.activateWindow()

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
        self._hidden_owner = None

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)


def copy_image_to_clipboard(image: QImage) -> None:
    QGuiApplication.clipboard().setPixmap(QPixmap.fromImage(image))
