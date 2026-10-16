"""Annotation model and the text dialog used by the screenshot overlay.

The captured screen stays where it is: this model draws shapes, arrows, pen
strokes, highlighter marks, numbered steps, blur/pixelate patches and text in
the same coordinates as the frozen screen, so the overlay editor renders it
straight onto the image that gets copied or saved.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen
from PyQt6.QtWidgets import (QColorDialog, QDialog, QDialogButtonBox,
                             QFontComboBox, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QSpinBox, QToolButton, QVBoxLayout)

from i18n import t

TOOLS = ("select", "pen", "line", "arrow", "rect", "ellipse", "highlight",
         "text", "step", "blur", "pixelate")

REGION_TOOLS = ("rect", "ellipse", "blur", "pixelate")
LINE_TOOLS = ("line", "arrow", "highlight")
PIXEL_TOOLS = ("blur", "pixelate")

DEFAULT_COLOR = "#e53935"
DEFAULT_WIDTH = 3
STEP_RADIUS = 15


def clone_item(item):
    """A detached copy; QFont/QColor objects are not deep-copyable."""
    out = {}
    for key, value in item.items():
        if isinstance(value, QRect):
            out[key] = QRect(value)
        elif isinstance(value, QPoint):
            out[key] = QPoint(value)
        elif isinstance(value, QColor):
            out[key] = QColor(value)
        elif isinstance(value, QFont):
            out[key] = QFont(value)
        elif isinstance(value, list):
            out[key] = [QPoint(point) if isinstance(point, QPoint) else point
                        for point in value]
        else:
            out[key] = value
    return out


def _distance_to_segment(point, start, end):
    px, py = point.x(), point.y()
    x1, y1 = start.x(), start.y()
    x2, y2 = end.x(), end.y()
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    position = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy)
                                / (dx * dx + dy * dy)))
    cx, cy = x1 + position * dx, y1 + position * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _draw_arrow_head(painter, start, end, color, width):
    size = max(11.0, width * 3.5)
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = max(1.0, (dx * dx + dy * dy) ** 0.5)
    ux, uy = dx / length, dy / length
    left = QPoint(int(end.x() - size * ux + size * 0.5 * uy),
                  int(end.y() - size * uy - size * 0.5 * ux))
    right = QPoint(int(end.x() - size * ux - size * 0.5 * uy),
                   int(end.y() - size * uy + size * 0.5 * ux))
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(QPoint(end), left, right)


class AnnotationModel:
    """Ordered annotations plus undo/redo, filled by the overlay editor."""

    MAX_HISTORY = 100

    def __init__(self):
        self.items: list[dict] = []
        self.selected = None
        self._undo: list[list[dict]] = []
        self._redo: list[list[dict]] = []

    # ---- history ---------------------------------------------------------

    def _snapshot(self):
        self._undo.append([clone_item(item) for item in self.items])
        if len(self._undo) > self.MAX_HISTORY:
            self._undo.pop(0)
        self._redo.clear()

    def begin(self):
        """Snapshot before an interactive edit (drag, resize, nudge)."""
        self._snapshot()

    def add(self, item: dict):
        self._snapshot()
        self.items.append(item)
        self.selected = len(self.items) - 1

    def remove_selected(self) -> bool:
        if self.selected is None:
            return False
        self._snapshot()
        del self.items[self.selected]
        self.selected = None
        return True

    def _restore(self, source, target) -> bool:
        target.append([clone_item(item) for item in self.items])
        self.items = source.pop()
        self.selected = None
        return True

    def undo(self) -> bool:
        if not self._undo:
            return False
        return self._restore(self._undo, self._redo)

    def redo(self) -> bool:
        if not self._redo:
            return False
        return self._restore(self._redo, self._undo)

    def clear(self) -> bool:
        if not self.items:
            return False
        self._snapshot()
        self.items.clear()
        self.selected = None
        return True

    def next_step(self) -> int:
        numbers = [item.get("number", 0) for item in self.items
                   if item["type"] == "step"]
        return (max(numbers) if numbers else 0) + 1

    # ---- geometry --------------------------------------------------------

    @staticmethod
    def text_rect(item) -> QRect:
        font = item.get("font") or QFont()
        rect = QFontMetrics(font).boundingRect(item.get("text", ""))
        rect.moveTopLeft(item["pos"])
        return rect

    @classmethod
    def item_rect(cls, item) -> QRect:
        kind = item["type"]
        if kind in REGION_TOOLS:
            return QRect(item["rect"])
        if kind in LINE_TOOLS:
            return QRect(item["start"], item["end"]).normalized()
        if kind == "pen":
            points = item.get("points") or []
            if not points:
                return QRect()
            xs = [point.x() for point in points]
            ys = [point.y() for point in points]
            return QRect(min(xs), min(ys), max(xs) - min(xs),
                         max(ys) - min(ys))
        if kind == "text":
            return cls.text_rect(item)
        if kind == "step":
            radius = int(item.get("radius", STEP_RADIUS))
            center = item["pos"]
            return QRect(center.x() - radius, center.y() - radius,
                         radius * 2, radius * 2)
        return QRect()

    def hit_test(self, pos: QPoint, tolerance: int = 6):
        for index in range(len(self.items) - 1, -1, -1):
            item = self.items[index]
            kind = item["type"]
            if kind in LINE_TOOLS:
                reach = max(tolerance, item.get("width", DEFAULT_WIDTH) + 4)
                if _distance_to_segment(pos, item["start"], item["end"]) <= reach:
                    return index
            elif kind == "pen":
                reach = max(tolerance, item.get("width", DEFAULT_WIDTH) + 4)
                points = item.get("points") or []
                if any(_distance_to_segment(pos, a, b) <= reach
                       for a, b in zip(points, points[1:])):
                    return index
                if points and (pos - points[0]).manhattanLength() <= reach:
                    return index
            elif kind == "step":
                center = item["pos"]
                radius = int(item.get("radius", STEP_RADIUS))
                if (pos - center).manhattanLength() <= radius * 1.4:
                    return index
            else:
                if self.item_rect(item).adjusted(-3, -3, 3, 3).contains(pos):
                    return index
        return None

    # ---- painting --------------------------------------------------------

    @staticmethod
    def draw_item(painter, item):
        color = item.get("color", QColor(DEFAULT_COLOR))
        width = max(1, int(item.get("width", DEFAULT_WIDTH)))
        kind = item["type"]
        if kind in ("rect", "ellipse"):
            # A dragged draft still holds start/end; only committed items
            # carry "rect". Reading it straight crashed every paint while a
            # shape was being drawn (KeyError: 'rect' in the 0.8.4 logs).
            rect = item.get("rect") or QRect(item["start"],
                                             item["end"]).normalized()
            painter.setPen(QPen(color, width))
            if item.get("fill"):
                fill = QColor(color)
                fill.setAlpha(90)
                painter.setBrush(fill)
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            if kind == "rect":
                painter.drawRect(rect)
            else:
                painter.drawEllipse(rect)
        elif kind in PIXEL_TOOLS:
            # Blur/pixelate drafts get a dashed outline; the effect itself is
            # applied when the item is committed and rendered.
            rect = item.get("rect") or QRect(item["start"],
                                             item["end"]).normalized()
            pen = QPen(QColor(255, 255, 255, 200), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
        elif kind == "line":
            painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(item["start"], item["end"])
        elif kind == "arrow":
            painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(item["start"], item["end"])
            _draw_arrow_head(painter, item["start"], item["end"], color, width)
        elif kind == "pen":
            painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            points = item.get("points") or []
            for a, b in zip(points, points[1:]):
                painter.drawLine(a, b)
        elif kind == "highlight":
            marker = QColor(color)
            marker.setAlpha(110)
            painter.setPen(QPen(marker, max(12, width * 5),
                                Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(item["start"], item["end"])
        elif kind == "text":
            font = item.get("font") or QFont()
            painter.setPen(QPen(color, 1))
            painter.setFont(font)
            metrics = QFontMetrics(font)
            painter.drawText(item["pos"].x(),
                             item["pos"].y() + metrics.ascent(),
                             item.get("text", ""))
        elif kind == "step":
            center = item["pos"]
            radius = int(item.get("radius", STEP_RADIUS))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(center, radius, radius)
            painter.setPen(QPen(QColor("white"), max(1, radius // 8)))
            font = QFont()
            font.setPixelSize(int(radius * 1.2))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRect(center.x() - radius, center.y() - radius,
                                   radius * 2, radius * 2),
                             int(Qt.AlignmentFlag.AlignCenter),
                             str(item.get("number", 1)))

    @classmethod
    def draw_selection(cls, painter, item, color="#9475EC"):
        painter.save()
        painter.setPen(QPen(QColor(color), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(cls.item_rect(item).adjusted(-3, -3, 3, 3))
        painter.restore()

    # ---- rendering -------------------------------------------------------

    def render(self, image: QImage, scale: float = 1.0) -> QImage:
        out = image.convertToFormat(QImage.Format.Format_ARGB32)
        if out.isNull():
            return out
        # QScreen snapshots carry DPR metadata. Coordinates below already
        # scale explicitly to physical pixels: QPainter must not scale twice.
        out.setDevicePixelRatio(1.0)
        # Preserve drawing order: a later privacy patch must also cover text
        # and shapes added before it. End painting before modifying pixels.
        for item in self.items:
            if item["type"] in PIXEL_TOOLS:
                self._apply_pixel_effect(out, item, scale)
            else:
                painter = QPainter(out)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                painter.scale(scale, scale)
                self.draw_item(painter, item)
                painter.end()
        return out

    @staticmethod
    def _apply_pixel_effect(image, item, scale):
        rect = QRect(item["rect"])
        if scale != 1.0:
            rect = QRect(round(rect.x() * scale), round(rect.y() * scale),
                         round(rect.width() * scale),
                         round(rect.height() * scale))
        rect = rect.intersected(image.rect())
        if rect.isEmpty():
            return
        region = image.copy(rect)
        if item["type"] == "pixelate":
            block = max(4, min(rect.width(), rect.height()) // 12)
            tiny = region.scaled(
                max(1, rect.width() // block), max(1, rect.height() // block),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation)
            patch = tiny.scaled(
                rect.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation)
        else:
            tiny = region.scaled(
                max(1, rect.width() // 18), max(1, rect.height() // 18),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            patch = tiny.scaled(
                rect.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        painter = QPainter(image)
        painter.drawImage(rect.topLeft(), patch)
        painter.end()


class TextDialog(QDialog):
    """Text plus the font options: family, size, style and colour."""

    def __init__(self, parent=None, text="", font=None, color=None):
        super().__init__(parent)
        self.setWindowTitle(t("Edit text") if text else t("Add text"))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("Text")))
        self.edit = QLineEdit(text)
        layout.addWidget(self.edit)
        row = QHBoxLayout()
        self.font_box = QFontComboBox()
        if font is not None:
            self.font_box.setCurrentFont(font)
        row.addWidget(self.font_box, 1)
        self.size_box = QSpinBox()
        self.size_box.setRange(8, 144)
        size = font.pointSize() if font is not None else 0
        self.size_box.setValue(size if size > 0 else 16)
        row.addWidget(self.size_box)
        self.bold = QToolButton()
        self.bold.setText("B")
        self.bold.setCheckable(True)
        self.bold.setToolTip(t("Bold"))
        bold_font = self.bold.font()
        bold_font.setBold(True)
        self.bold.setFont(bold_font)
        self.bold.setChecked(bool(font.bold()) if font is not None else False)
        row.addWidget(self.bold)
        self.italic = QToolButton()
        self.italic.setText("I")
        self.italic.setCheckable(True)
        self.italic.setToolTip(t("Italic"))
        italic_font = self.italic.font()
        italic_font.setItalic(True)
        self.italic.setFont(italic_font)
        self.italic.setChecked(bool(font.italic()) if font is not None else False)
        row.addWidget(self.italic)
        self.underline = QToolButton()
        self.underline.setText("U")
        self.underline.setCheckable(True)
        self.underline.setToolTip(t("Underline"))
        underline_font = self.underline.font()
        underline_font.setUnderline(True)
        self.underline.setFont(underline_font)
        self.underline.setChecked(bool(font.underline()) if font is not None
                                  else False)
        row.addWidget(self.underline)
        self.color = QColor(color) if isinstance(color, QColor) and color.isValid() \
            else QColor(DEFAULT_COLOR)
        self.color_button = QPushButton(t("Color"))
        self.color_button.clicked.connect(self._choose_color)
        row.addWidget(self.color_button)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.edit.setFocus()

    def _choose_color(self):
        color = QColorDialog.getColor(self.color, self, t("Color"))
        if color.isValid():
            self.color = color

    def values(self):
        font = QFont(self.font_box.currentFont())
        font.setPointSize(int(self.size_box.value()))
        font.setBold(self.bold.isChecked())
        font.setItalic(self.italic.isChecked())
        font.setUnderline(self.underline.isChecked())
        return self.edit.text(), font, QColor(self.color)
