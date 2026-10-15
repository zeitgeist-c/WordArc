"""Canlı dikte şeridi: ara metin gerçekten çiziliyor mu?

0.7.0'da kayıt sürerken metin hiçbir yere çizilmiyordu: overlay yalnızca
seviye çubuklarını çiziyor, show_live_text() ile gelen yazı yalnızca "busy"
durumunda görünen mesaj alanına yazılıyordu.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

import overlay
import theme

_APP = QApplication.instance() or QApplication([])


def _render(box):
    """Şeridi bir görüntüye çiz; metin bölgesindeki parlak pikselleri say."""
    image = QImage(box.width(), box.height(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    box.render(painter)
    painter.end()
    bright = 0
    for y in range(box.height()):
        for x in range(56, max(57, box.width() - 80)):
            colour = image.pixelColor(x, y)
            if min(colour.red(), colour.green(), colour.blue()) > 170:
                bright += 1
    return bright


def _box():
    box = overlay.Overlay()
    box.setStyleSheet(theme.stylesheet(theme.palette(theme.ThemeMode.DARK)))
    return box


def test_live_text_is_painted_while_recording():
    box = _box()
    box.show_recording()
    box.push_level(0.6)
    box.push_level(0.4)
    before = _render(box)
    box.show_live_text("merhaba dünya bu bir canlı yazıdır")
    after = _render(box)
    assert after > before + 100, (before, after)


def test_live_text_widens_the_ribbon_for_long_speech():
    box = _box()
    box.show_recording()
    box.show_live_text("kısa")
    narrow = box.width()
    box.show_live_text("çok daha uzun bir cümle, şeridin büyümesi gereken yer")
    assert box.width() > narrow
    assert box.width() <= overlay.MAX_WIDTH


def test_meeting_keeps_its_dual_meter():
    box = _box()
    box.show_meeting()
    box.push_levels(0.6, 0.3)
    box.show_live_text("toplantı metni")
    assert box.state == "meeting"
    assert box.width() >= overlay.MIN_WIDTH


def test_clearing_live_text_returns_to_the_plain_meter():
    box = _box()
    box.show_recording()
    box.show_live_text("merhaba")
    with_text = _render(box)
    box.show_live_text("")
    assert box.message == ""
    without = _render(box)
    assert without < with_text
