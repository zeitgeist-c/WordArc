"""Vector tray icons drawn with QPainter — no icon theme on Windows."""

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

# Linux icon-name → semantic state, used by dikte.py's _set_icon(name).
_IDLE = "audio-input-microphone"
_REC = "media-record"
_BUSY = "view-refresh"

BG = QColor(30, 32, 38)
MIC = QColor(220, 226, 234)
REC_DOT = QColor(240, 78, 82)
BUSY = QColor(120, 170, 255)

_cache = {}


def icon(name):
    """Return a QIcon for a Linux theme-name, drawing it on first use."""
    if name not in _cache:
        _cache[name] = _draw(name)
    return _cache[name]


def _draw(name):
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if name == _REC:
        _mic(p, MIC)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(REC_DOT)
        p.drawEllipse(QPointF(46, 18), 11, 11)
    elif name == _BUSY:
        _mic(p, MIC)
        pen = QPen(BUSY, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(34, 8, 22, 22), 0, 270 * 16)
    else:  # idle / unknown
        _mic(p, MIC)
    p.end()
    return QIcon(pix)


def _mic(p, colour):
    p.setPen(QPen(colour, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    # capsule body
    rect = QRectF(26, 12, 14, 24)
    path = QPainterPath()
    path.addRoundedRect(rect, 7, 7)
    p.drawPath(path)
    # stand
    p.drawLine(QPointF(33, 40), QPointF(33, 48))
    p.drawArc(QRectF(22, 28, 22, 22), 0, 180 * 16)
    p.drawLine(QPointF(22, 50), QPointF(44, 50))


def clear_cache():
    _cache.clear()