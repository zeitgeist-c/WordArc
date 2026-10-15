"""Optional in-preview annotation editor for captured screenshots."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QImage, QPainter, QPen, QPixmap,
)
from PyQt6.QtWidgets import QInputDialog, QWidget

from i18n import t


def _display_rect(base: QImage, size: QSize) -> QRect:
    if base.isNull():
        return QRect()
    scaled = base.size().scaled(size, Qt.AspectRatioMode.KeepAspectRatio)
    x = (size.width() - scaled.width()) // 2
    y = (size.height() - scaled.height()) // 2
    return QRect(x, y, scaled.width(), scaled.height())


class AnnotationCanvas(QWidget):
    """Draw arrows, shapes and text on top of a captured image."""

    changed = pyqtSignal()

    TOOLS = ("select", "rect", "ellipse", "arrow", "line", "pen",
             "highlight", "blur", "text", "step")

    def __init__(self, image, parent=None):
        super().__init__(parent)
        self.base = image.copy() if not image.isNull() else QImage()
        self.annotations: list[dict] = []
        self.tool = "rect"
        self.color = QColor("#e53935")
        self.stroke_width = 3
        self._current = None
        self._step_count = 0
        self._text_point = None
        self.setMinimumSize(280, 180)
        self.setSizePolicy(
            self.sizePolicy().Policy.Expanding,
            self.sizePolicy().Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_tool(self, tool: str):
        self.tool = tool if tool in self.TOOLS else self.tool
        self._current = None
        self.update()

    def set_color(self, color: QColor):
        self.color = color
        self.update()

    def set_stroke_width(self, width: int):
        self.stroke_width = max(1, int(width))
        self.update()

    def undo(self):
        if self.annotations:
            item = self.annotations.pop()
            if item.get("type") == "step":
                self._step_count = max(0, self._step_count - 1)
            self.changed.emit()
            self.update()

    def reset(self):
        self.annotations.clear()
        self._step_count = 0
        self.changed.emit()
        self.update()

    def rendered_image(self) -> QImage:
        if self.base.isNull():
            return self.base.copy()
        image = self.base.copy().convertToFormat(
            QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Blurs go first: they modify the underlying pixels.
        for item in self.annotations:
            if item["type"] == "blur":
                self._draw_blur(painter, image, item)
        for item in self.annotations:
            if item["type"] != "blur":
                self._draw_item(painter, item)
        if self._current is not None:
            if self._current["type"] == "blur":
                self._draw_blur(painter, image, self._current)
            else:
                self._draw_item(painter, self._current)
        painter.end()
        return image

    def _draw_blur(self, painter, image, item):
        rect = item["rect"]
        if rect.width() < 4 or rect.height() < 4:
            return
        collapsed = rect.intersected(image.rect())
        if collapsed.width() < 2 or collapsed.height() < 2:
            return
        region = image.copy(collapsed)
        block = max(4, min(collapsed.width(), collapsed.height()) // 12)
        tiny = region.scaled(
            max(1, collapsed.width() // block),
            max(1, collapsed.height() // block),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation)
        pixelated = tiny.scaled(
            collapsed.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation)
        painter.drawImage(collapsed.topLeft(), pixelated)

    def _draw_item(self, painter, item):
        color = item.get("color", self.color)
        width = item.get("width", self.stroke_width)
        kind = item["type"]
        if kind == "rect":
            painter.setPen(QPen(color, width))
            painter.drawRect(item["rect"])
        elif kind == "ellipse":
            painter.setPen(QPen(color, width))
            painter.drawEllipse(item["rect"])
        elif kind == "line":
            painter.setPen(QPen(color, width,
                                Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(item["start"], item["end"])
        elif kind == "arrow":
            pen = QPen(color, width, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(item["start"], item["end"])
            self._draw_arrow_head(painter, item["start"],
                                  item["end"], color)
        elif kind == "pen":
            pen = QPen(color, width, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            points = item.get("points", [])
            for a, b in zip(points, points[1:]):
                painter.drawLine(a, b)
        elif kind == "highlight":
            pen = QPen(QColor(255, 200, 0, 220), 1)
            painter.setPen(pen)
            painter.setBrush(QColor(255, 220, 0, 90))
            painter.drawRect(item["rect"])
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif kind == "step":
            number = item.get("number", 1)
            center = item["pos"]
            radius = 14
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(item.get("color", QColor("#e53935")))
            painter.drawEllipse(center, radius, radius)
            painter.setPen(QPen(QColor("white"), 1))
            font = QFont("Arial", 10, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(QRect(center.x() - radius, center.y() - radius,
                            radius * 2, radius * 2),
                             Qt.AlignmentFlag.AlignCenter, str(number))
        elif kind == "text":
            painter.setPen(QPen(color, 1))
            font = QFont("Arial", item.get("size", 16))
            painter.setFont(font)
            painter.drawText(item["pos"], item.get("text", ""))

    def _draw_arrow_head(self, painter, start, end, color):
        import math
        arrow_size = 12
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux, uy = dx / length, dy / length
        left_x = end.x() - arrow_size * ux + arrow_size * 0.5 * uy
        left_y = end.y() - arrow_size * uy - arrow_size * 0.5 * ux
        right_x = end.x() - arrow_size * ux - arrow_size * 0.5 * uy
        right_y = end.y() - arrow_size * uy + arrow_size * 0.5 * ux
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPoint(int(end.x()), int(end.y())),
                              QPoint(int(left_x), int(left_y)),
                              QPoint(int(right_x), int(right_y)))

    def _display_rect(self) -> QRect:
        return _display_rect(self.base, self.size())

    def _to_image(self, pos: QPoint) -> QPoint | None:
        rect = self._display_rect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return None
        x = rect.left() + int((pos.x() - rect.left()) *
            self.base.width() / rect.width())
        y = rect.top() + int((pos.y() - rect.top()) *
            self.base.height() / rect.height())
        x = max(0, min(self.base.width() - 1, x))
        y = max(0, min(self.base.height() - 1, y))
        return QPoint(x, y)

    def _same_point(self, a, b):
        return abs(a.x() - b.x()) + abs(a.y() - b.y()) <= 2

    def mousePressEvent(self, event):
        if self.base.isNull():
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pt = self._to_image(event.position().toPoint())
        if pt is None:
            return
        if self.tool == "step":
            self._step_count += 1
            self.annotations.append({
                "type": "step", "pos": pt,
                "number": self._step_count, "color": self.color})
            self.changed.emit()
            self.update()
            return
        if self.tool == "text":
            self._text_point = pt
            QTimer.singleShot(0, self._ask_text)
            return
        if self.tool == "pen":
            self._current = {"type": "pen", "points": [pt],
                             "color": self.color, "width": self.stroke_width}
        else:
            self._current = {"type": self.tool, "start": pt, "end": pt,
                             "color": self.color, "width": self.stroke_width}
        if self.tool == "highlight":
            self._current["color"] = QColor(255, 220, 0, 220)
        self.update()

    def mouseMoveEvent(self, event):
        if self.base.isNull():
            return
        if self._current is None:
            return
        pt = self._to_image(event.position().toPoint())
        if pt is None:
            return
        if self._current["type"] == "pen":
            self._current["points"].append(pt)
        else:
            self._current["end"] = pt
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._current is None:
            return
        item = self._current
        self._current = None
        if item["type"] in ("rect", "ellipse", "highlight", "blur"):
            start = item["start"]
            end = item["end"]
            if self._same_point(start, end):
                self.update()
                return
            item["rect"] = QRect(start, end).normalized()
            item.pop("start", None)
            item.pop("end", None)
        elif item["type"] in ("line", "arrow"):
            if self._same_point(item["start"], item["end"]):
                self.update()
                return
        if item["type"] == "pen":
            if len(item.get("points", [])) < 2:
                self.update()
                return
        self.annotations.append(item)
        self.changed.emit()
        self.update()

    def _ask_text(self):
        pt = self._text_point
        self._text_point = None
        if pt is None:
            return
        text, accepted = QInputDialog.getText(
            self, t("Add text"), t("Text:"))
        if not accepted or not text.strip():
            return
        self.annotations.append({
            "type": "text", "pos": pt, "text": text,
            "color": self.color, "size": max(10, self.stroke_width * 5)})
        self.changed.emit()
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e1e1e"))
        image = self.rendered_image()
        if image.isNull():
            painter.end()
            return
        rect = self._display_rect()
        painter.drawImage(rect, image)
        # Tool cursor hint
        painter.setPen(QPen(QColor("white"), 1, Qt.PenStyle.DashLine))
        painter.end()

    def sizeHint(self):
        if self.base.isNull():
            return QSize(320, 200)
        return QSize(max(320, self.base.width() // 2),
                     max(200, self.base.height() // 2))

