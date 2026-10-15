"""Ses göstergesi biçimleri: seçim, çizim ve birbirinden ayrışma.

0.7.2'de dört biçim vardı ama Spectrum ile Capsules %88 aynı çiziyordu —
ayarlardan seçmenin anlamı kalmamıştı. Ayrıca `set_meter` modül geneli olduğu
için dört Overlay'i aynı anda gösterip tek karede yakalamak imkânsız: hepsi
son stille çizilir. Bu yüzden ölçüm, üretimin kendi çizim fonksiyonuna
doğrudan verilir.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

import overlay
import theme

_APP = QApplication.instance() or QApplication([])


def _render(style, width=240, height=46):
    """Bir stili sabit bir tuvale çiz: üretimin kendi fonksiyonuyla."""
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    levels = [min(1.0, 0.10 + 0.85 * (((i * 13) % 17) / 16.0))
              for i in range(overlay.BARS)]
    overlay._draw_meter_into(painter, QRectF(0, 0, width, height), levels,
                             overlay.REC, style=style)
    painter.end()
    return image


def _features(style, width=240, height=46):
    """(ayrı blok, en geniş blok, renkli sütun) — çizimin yapısal imzası."""
    image = _render(style, width, height)
    columns = {}
    for y in range(height):
        for x in range(width):
            colour = image.pixelColor(x, y)
            if colour.alpha() < 40:
                continue
            r, g, b = colour.red(), colour.green(), colour.blue()
            if r > 60 and r > g + 25 and r > b + 25:
                columns[x] = columns.get(x, 0) + 1
    if not columns:
        return (0, 0, 0)
    runs = []
    previous = None
    for x in sorted(columns):
        if previous is None or x > previous + 1:
            runs.append(1)
        else:
            runs[-1] += 1
        previous = x
    return (len(runs), max(runs), len(columns))


def _box(style, state="recording"):
    overlay.set_meter(style)
    box = overlay.Overlay()
    box.setStyleSheet(theme.stylesheet(theme.palette(theme.ThemeMode.DARK)))
    if state == "meeting":
        box.show_meeting()
    else:
        box.show_recording()
    for i in range(overlay.BARS):
        box.push_level(0.10 + 0.85 * (((i * 13) % 17) / 16.0))
    return box


def _ribbon_counts(box):
    """Gerçek şeritte kırmızı (mikrofon) ve mavi (karşı taraf) piksel sayısı."""
    image = QImage(box.width(), box.height(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    box.render(painter)
    painter.end()
    red = cyan = 0
    for y in range(box.height()):
        for x in range(46, max(47, box.width() - 70)):
            colour = image.pixelColor(x, y)
            if colour.alpha() < 40:
                continue
            r, g, b = colour.red(), colour.green(), colour.blue()
            if r > 60 and r > g + 25 and r > b + 25:
                red += 1
            elif b > 80 and b > r + 25:
                cyan += 1
    return red, cyan


STYLES = ("bars", "spectrum", "wave", "capsule")


@pytest.mark.parametrize("style", STYLES)
def test_every_style_draws_something(style):
    """Çizim var: göze görünür bir iz (dalga tek bloktur, çubuklar çok)."""
    runs, _widest, pixels = _features(style)
    assert runs >= 1 and pixels > 30, (style, runs, pixels)


@pytest.mark.parametrize("style", STYLES)
def test_every_style_draws_on_a_ribbon(style):
    """Şeritte de çiziyor: bu kez gerçek Overlay üzerinden."""
    red, _cyan = _ribbon_counts(_box(style))
    assert red > 40, (style, red)


def test_every_style_has_its_own_signature():
    """Her biçimin yapısal imzası farklı olmalı.

    0.7.2'de Spectrum ile Capsules %88 aynı çiziyordu; seçim hiçbir şey
    değiştirmiyordu. İmzaların eşitliği o hatanın geri geldiğini gösterir.
    """
    signatures = {style: _features(style) for style in STYLES}
    seen = {}
    for style, signature in signatures.items():
        assert signature[2] > 30, (style, signature)
        assert signature not in seen, \
            f"{style} ile {seen.get(signature)} aynı imza: {signature}"
        seen[signature] = style


def test_name_matches_shape():
    """Adı neyse çizimi o: çubuk ince, dalga tek gövde, kapsül kalın."""
    bars_runs, bars_widest, _ = _features("bars")
    wave_runs, wave_widest, _ = _features("wave")
    capsule_runs, capsule_widest, _ = _features("capsule")
    spectrum_runs, spectrum_widest, _ = _features("spectrum")
    assert bars_runs >= 20, bars_runs            # ince tarak: çok blok
    assert wave_runs == 1, wave_runs              # tek gövde
    assert wave_widest >= 100, wave_widest
    assert capsule_widest > bars_widest + 3, (bars_widest, capsule_widest)
    assert 8 <= spectrum_runs <= 24, spectrum_runs
    assert spectrum_runs > wave_runs


def test_signatures_stay_distinct_on_a_narrow_ribbon():
    """Dar şeritte (170 px) de dördü ayrı kalmalı."""
    signatures = {style: _features(style, width=170, height=56)
                  for style in STYLES}
    seen = {}
    for style, signature in signatures.items():
        assert signature[2] > 30, (style, signature)
        assert signature not in seen, \
            f"dar şeritte {style} ile {seen.get(signature)} aynı imza"
        seen[signature] = style


def test_meeting_shows_both_channels():
    """Toplantı görünümü seçilen biçimle, iki kanal hâlinde çizilir."""
    for style in STYLES:
        red, cyan = _ribbon_counts(_box(style, state="meeting"))
        assert red > 20 and cyan > 20, (style, red, cyan)
    overlay.set_meter("spectrum")


def test_unknown_style_keeps_the_current_one():
    overlay.set_meter("spectrum")
    overlay.set_meter("something-else")
    assert overlay.meter() == "spectrum"
    overlay.set_meter("spectrum")


def test_live_text_is_no_longer_painted():
    box = _box("spectrum")
    box.show_live_text("merhaba dünya bu metin çizilmemeli")
    assert box.message == ""


def test_ribbon_stays_compact_in_every_style():
    for style in STYLES:
        box = _box(style)
        box.show_live_text("uzun bir cümle şeridi büyütmemeli")
        assert overlay.MIN_WIDTH <= box.width() <= overlay.MAX_WIDTH
        assert box.height() == overlay.HEIGHT


def test_preview_widget_uses_the_same_drawing():
    """Ayarlardaki önizleme üretim çizimini kullanır (kopya değil)."""
    frames = {}
    for style in STYLES:
        widget = overlay.MeterPreview(style)
        image = QImage(widget.width(), widget.height(),
                       QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        widget.render(painter)
        painter.end()
        painted = 0
        for y in range(image.height()):
            for x in range(image.width()):
                colour = image.pixelColor(x, y)
                if colour.alpha() < 40:
                    continue
                r, g, b = colour.red(), colour.green(), colour.blue()
                if r > 60 and r > g + 25 and r > b + 25:
                    painted += 1
        frames[style] = painted
        assert painted > 20, (style, painted)
        widget.deleteLater()
    assert len(set(frames.values())) >= 3, frames
