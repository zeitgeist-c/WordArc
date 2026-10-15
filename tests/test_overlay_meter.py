"""Ses göstergesi biçimleri: seçim, çizim ve ayar turu.

Kullanıcı kayıt şeridinde akan metin yerine diğer kayıtlardaki gibi ses
göstergesi istedi ve gösterge çiziminin Ayarlar'dan seçilebilmesini istedi.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

import overlay
import theme

_APP = QApplication.instance() or QApplication([])


def _box(style, state="recording"):
    overlay.set_meter(style)
    box = overlay.Overlay()
    box.setStyleSheet(theme.stylesheet(theme.palette(theme.ThemeMode.DARK)))
    if state == "meeting":
        box.show_meeting()
    else:
        box.show_recording()
    for i in range(overlay.BARS):
        box.push_level(0.15 + 0.75 * ((i % 6) / 5))
    return box


def _meter_pixels(box):
    """The ribbon's meter region, as colour values the meter itself painted.

    The whole ribbon is painted (background and border), so counting painted
    pixels says nothing about the meter. A meter pixel is a tinted one: the
    dark theme's surface is grey, and the accents are red/cyan — a pixel whose
    channels disagree is the meter.
    """
    image = QImage(box.width(), box.height(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    box.render(painter)
    painter.end()
    pixels = []
    for y in range(box.height()):
        for x in range(46, max(47, box.width() - 70)):
            colour = image.pixelColor(x, y)
            if colour.alpha() < 40:
                continue
            spread = max(colour.red(), colour.green(), colour.blue()) - \
                min(colour.red(), colour.green(), colour.blue())
            if spread > 24:            # tinted, not grey
                pixels.append((x, y, colour.rgb()))
    return pixels


def _ink(box):
    return len(_meter_pixels(box))


@pytest.mark.parametrize("style", ["bars", "spectrum", "wave", "capsule"])
def test_every_style_draws_something(style):
    box = _box(style)
    assert _ink(box) > 120, style


@pytest.mark.parametrize("style", ["bars", "spectrum", "wave", "capsule"])
def test_every_style_draws_in_a_meeting(style):
    box = _box(style, state="meeting")
    assert _ink(box) > 120, style


def test_styles_look_different_from_each_other():
    """Her biçim gerçekten başka bir şey çiziyor: pikseller birebir aynı olamaz."""
    paintings = {style: tuple(_meter_pixels(_box(style)))
                 for style in ("bars", "spectrum", "wave", "capsule")}
    styles = list(paintings)
    for i in range(len(styles)):
        for j in range(i + 1, len(styles)):
            assert paintings[styles[i]] != paintings[styles[j]], \
                f"{styles[i]} ile {styles[j]} aynı çiziyor"


def test_unknown_style_keeps_the_current_one():
    overlay.set_meter("spectrum")
    overlay.set_meter("something-else")
    assert overlay.meter() == "spectrum"
    overlay.set_meter("bars")


def test_live_text_is_no_longer_painted():
    box = _box("spectrum")
    plain = _ink(box)
    box.show_live_text("merhaba dünya bu metin çizilmemeli")
    assert box.message == ""
    assert _ink(box) == plain


def test_ribbon_stays_compact_in_every_style():
    for style in ("bars", "spectrum", "wave", "capsule"):
        box = _box(style)
        box.show_live_text("uzun bir cümle şeridi büyütmemeli")
        assert box.width() <= overlay.MAX_WIDTH
        assert box.width() >= overlay.MIN_WIDTH
        assert box.height() == overlay.HEIGHT
