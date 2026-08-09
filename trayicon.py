"""WordArc tray icons drawn from the deterministic waveform/arc mark."""

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (QColor, QIcon, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap)

_IDLE = "audio-input-microphone"
_REC = "media-record"
_BUSY = "view-refresh"
SIZES = (16, 20, 24, 32, 48, 64)

VIOLET = QColor("#8B5CF6")
CYAN = QColor("#22D3EE")
REC_DOT = QColor("#F04E52")
BUSY = QColor("#22D3EE")
_cache = {}


def icon(name):
    """Return a cached, scalable WordArc state icon."""
    if name not in _cache:
        result = QIcon()
        for size in SIZES:
            result.addPixmap(_draw(name, size))
        _cache[name] = result
    return _cache[name]


def _draw(name, size=64):
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 64.0, size / 64.0)
    painter.setPen(QPen(QColor("#F8FAFC"), 3))
    painter.setBrush(QColor("#111827"))
    painter.drawRoundedRect(QRectF(2.5, 2.5, 59, 59), 13, 13)
    _mark(painter)
    if name == _REC:
        painter.setPen(QPen(QColor("#0B0E14"), 2))
        painter.setBrush(REC_DOT)
        painter.drawEllipse(QPointF(49, 17), 10, 10)
    elif name == _BUSY:
        pen = QPen(BUSY, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(38, 7, 21, 21), 35 * 16, 270 * 16)
    painter.end()
    return pix


def _mark(painter):
    gradient = QLinearGradient(8, 48, 58, 14)
    gradient.setColorAt(0, VIOLET)
    gradient.setColorAt(1, CYAN)
    pen = QPen(gradient, 6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(8, 22)
    path.lineTo(16, 45)
    path.lineTo(25, 18)
    path.lineTo(34, 45)
    path.lineTo(42, 22)
    path.cubicTo(49, 11, 58, 14, 57, 25)
    painter.drawPath(path)


def set_theme(colors):
    global VIOLET, CYAN, BUSY
    VIOLET = QColor(colors.violet)
    CYAN = QColor(colors.cyan)
    BUSY = QColor(colors.cyan)
    clear_cache()


def clear_cache():
    _cache.clear()
