"""Sound meter styles: selection, drawing and how they differ.

0.7.2 shipped four styles, but Spectrum and Capsules drew 88% the same — the
choice in Settings no longer meant anything. On top of that, because
`set_meter` is module-wide, showing four Overlays at once and capturing a
single frame is impossible: they all draw with the last style. So the
measurement feeds production's own drawing function directly.
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
    """Draw one style onto a fixed canvas, with production's own function."""
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
    """(separate runs, widest run, coloured columns) — the drawing's structural signature."""
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
    """Pixel counts of red (microphone) and blue (other party) in the real ribbon."""
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


def test_meter_uses_readable_decibels_for_quiet_microphones():
    assert overlay._display_level(0.01) == pytest.approx(1 / 3)
    assert overlay._display_level(0.1) == pytest.approx(2 / 3)
    assert overlay._display_level(1) == 1
    values = [overlay._display_level(p) for p in (0.001, 0.003, 0.01, 0.1, 0.5, 1)]
    assert values == sorted(values)


@pytest.mark.parametrize("value", [0, -1, 0.0001, 0.001, float("nan"), float("inf")])
def test_silence_and_invalid_peaks_do_not_create_false_activity(value):
    assert overlay._display_level(value) == 0


@pytest.mark.parametrize("style", STYLES)
def test_low_gain_voice_is_visible_in_the_actual_ribbon(style):
    overlay.set_meter(style)
    box = overlay.Overlay()
    try:
        box.show_recording()
        silent, _ = _ribbon_counts(box)
        for _ in range(overlay.BARS):
            box.push_level(0.01)
        quiet, _ = _ribbon_counts(box)
        assert quiet > silent + 80, (style, silent, quiet)
        assert max(box.levels) == pytest.approx(1 / 3)
    finally:
        box.close()
        box.deleteLater()
        overlay.set_meter("spectrum")


def test_meeting_channels_share_the_curve_and_start_silent():
    box = overlay.Overlay()
    try:
        box.push_levels(0.01, 0.1)
        assert box.levels[-1] == pytest.approx(1 / 3)
        assert box.levels2[-1] == pytest.approx(2 / 3)
        box.show_meeting()
        assert not any(box.levels) and not any(box.levels2)
    finally:
        box.close()
        box.deleteLater()


@pytest.mark.parametrize("style", STYLES)
def test_every_style_draws_something(style):
    """There is drawing: a visible mark (the wave is one run, the bars are many)."""
    runs, _widest, pixels = _features(style)
    assert runs >= 1 and pixels > 30, (style, runs, pixels)


@pytest.mark.parametrize("style", STYLES)
def test_every_style_draws_on_a_ribbon(style):
    """It draws on the ribbon too: this time through the real Overlay."""
    red, _cyan = _ribbon_counts(_box(style))
    assert red > 40, (style, red)


def test_every_style_has_its_own_signature():
    """Every style must have its own structural signature.

    In 0.7.2 Spectrum and Capsules drew 88% the same; the choice changed
    nothing. Equal signatures mean that bug is back.
    """
    signatures = {style: _features(style) for style in STYLES}
    seen = {}
    for style, signature in signatures.items():
        assert signature[2] > 30, (style, signature)
        assert signature not in seen, \
            f"{style} and {seen.get(signature)} share a signature: {signature}"
        seen[signature] = style


def test_name_matches_shape():
    """The name matches the shape: bars thin, the wave one body, the capsule thick."""
    bars_runs, bars_widest, _ = _features("bars")
    wave_runs, wave_widest, _ = _features("wave")
    capsule_runs, capsule_widest, _ = _features("capsule")
    spectrum_runs, spectrum_widest, _ = _features("spectrum")
    assert bars_runs >= 20, bars_runs            # thin comb: many runs
    assert wave_runs == 1, wave_runs              # a single body
    assert wave_widest >= 100, wave_widest
    assert capsule_widest > bars_widest + 3, (bars_widest, capsule_widest)
    assert 8 <= spectrum_runs <= 24, spectrum_runs
    assert spectrum_runs > wave_runs


def test_signatures_stay_distinct_on_a_narrow_ribbon():
    """All four must stay distinct on a narrow ribbon (170 px) too."""
    signatures = {style: _features(style, width=170, height=56)
                  for style in STYLES}
    seen = {}
    for style, signature in signatures.items():
        assert signature[2] > 30, (style, signature)
        assert signature not in seen, \
            f"on the narrow ribbon {style} and {seen.get(signature)} share a signature"
        seen[signature] = style


def test_meeting_shows_both_channels():
    """The meeting view is drawn in the chosen style, as two channels."""
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
    box.show_live_text("hello world this text must not be painted")
    assert box.message == ""


def test_ribbon_stays_compact_in_every_style():
    for style in STYLES:
        box = _box(style)
        box.show_live_text("a long sentence must not grow the ribbon")
        assert overlay.MIN_WIDTH <= box.width() <= overlay.MAX_WIDTH
        assert box.height() == overlay.HEIGHT


def test_preview_widget_uses_the_same_drawing():
    """The preview in Settings uses the production drawing (not a copy)."""
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
