"""The small recording indicator that appears in a screen corner without taking focus."""

import math

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (QBrush, QColor, QCursor, QFont, QFontMetrics,
                         QLinearGradient, QPainter, QPainterPath, QPen)
from PyQt6.QtWidgets import QWidget, QApplication

BARS = 22
HEIGHT = 56
MIN_WIDTH = 210
MAX_WIDTH = 460
MARGIN = 28
GAP = 10        # between two indicators sharing a corner

BG = QColor(22, 24, 29, 238)
BORDER = QColor(255, 255, 255, 28)
TEXT = QColor(235, 237, 242)
MUTED = QColor(150, 156, 168)
REC = QColor(240, 78, 82)
BUSY = QColor(120, 170, 255)
OK = QColor(80, 205, 140)
ERR = QColor(240, 100, 90)
WARN = QColor(240, 180, 80)
THEM = QColor(110, 190, 255)   # the other side of a meeting

ASK = QColor(150, 140, 255)    # recording a command rather than a dictation

STATE_COLORS = {"recording": REC, "asking": ASK, "meeting": REC, "busy": BUSY,
                "done": OK, "warning": WARN, "error": ERR}
LIVE = ("recording", "asking", "meeting")

# How the live level meter is drawn. Three shapes, one setting: the user picks
# the look in Settings and every overlay follows, because they all read the
# same module value.
METER_BARS = "bars"          # the original: thin bars growing from the centre
METER_SPECTRUM = "spectrum"  # rounded bars, brighter as they get taller
METER_WAVE = "wave"          # one filled wave with a bright crest line
METER_CAPSULE = "capsule"    # thick capsules with a vertical gradient


def meter_styles():
    """The meter choices, as (label, value) for the settings combo."""
    return (("Bars", METER_BARS), ("Spectrum", METER_SPECTRUM),
            ("Wave", METER_WAVE), ("Capsules", METER_CAPSULE))


_METER = METER_BARS


def _draw_meter_into(painter, rect, levels, accent, style=None):
    """Draw one meter of `style` into `rect` with `levels`.

    The single entry point for both the recording ribbon and the settings
    previews: a preview drawn by different code would drift from what the
    user actually gets, which is the whole reason to show one.
    """
    style = style or _METER
    mid = rect.center().y()
    count = len(levels)
    left = rect.left()
    span = max(1.0, rect.width())
    height = rect.height()
    top = rect.top()
    painter.setPen(Qt.PenStyle.NoPen)
    if style == METER_WAVE:
        floor = rect.bottom()
        ceiling = top + 1.0
        points = []
        points_count = count * 2 - 1
        for i in range(points_count):
            src = i / (points_count - 1) * (count - 1)
            low = int(src)
            high = min(count - 1, low + 1)
            frac = src - low
            level = levels[low] * (1 - frac) + levels[high] * frac
            shaped = min(1.0, level ** 0.6)
            x = left + span * i / (points_count - 1)
            points.append(QPointF(x, floor - (floor - ceiling) * shaped))
        path = QPainterPath()
        path.moveTo(points[0].x(), floor)
        path.lineTo(points[0].x(), points[0].y())
        for i in range(1, len(points)):
            prev, cur = points[i - 1], points[i]
            mid_x = (prev.x() + cur.x()) / 2
            path.cubicTo(mid_x, prev.y(), mid_x, cur.y(), cur.x(), cur.y())
        path.lineTo(points[-1].x(), floor)
        path.closeSubpath()
        fill = QLinearGradient(0, ceiling, 0, floor)
        for stop, alpha in ((0.0, 0.98), (0.55, 0.42), (1.0, 0.04)):
            colour = QColor(accent)
            colour.setAlphaF(alpha)
            fill.setColorAt(stop, colour)
        painter.setBrush(QBrush(fill))
        painter.drawPath(path)
        crest = QPainterPath()
        crest.moveTo(points[0].x(), points[0].y())
        for i in range(1, len(points)):
            prev, cur = points[i - 1], points[i]
            mid_x = (prev.x() + cur.x()) / 2
            crest.cubicTo(mid_x, prev.y(), mid_x, cur.y(), cur.x(), cur.y())
        line = QColor(accent).lighter(150)
        pen = QPen(line, 1.6)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(crest)
        return
    if style == METER_SPECTRUM:
        # Fewer, spaced bars: a spectrum analyser reads as separate lines, and
        # spaced bars cannot merge into the solid body the wave draws.
        bar_w = max(1.8, 2.6)
        count_bars = max(8, min(20, int(span / 14)))
        step = (span - bar_w) / max(1, count_bars - 1)
        rail = QColor(MUTED)
        rail.setAlphaF(0.50)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(rail)
        painter.drawRect(QRectF(left, mid - 0.5, span, 1.0))
        for i in range(count_bars):
            level = levels[int(i * (count - 1) / (count_bars - 1))]
            shaped = min(1.0, level ** 0.6)
            half = 1.2 + shaped * (height * 0.44)
            colour = QColor(accent)
            colour.setAlphaF(0.28 + 0.72 * shaped)
            painter.setBrush(colour)
            painter.drawRoundedRect(
                QRectF(left + i * step, mid - half, bar_w, half * 2),
                bar_w / 2, bar_w / 2)
        return
    if style == METER_CAPSULE:
        bars = max(6, min(11, int(span / 26)))
        bar_w = max(7.0, span / (bars * 1.9))
        step = (span - bar_w) / max(1, bars - 1)
        for i in range(bars):
            level = levels[int(i * (count - 1) / (bars - 1))]
            shaped = min(1.0, level ** 0.55)
            h = max(4.0, height * 0.20) + shaped * (height * 0.72)
            x = left + i * step
            y = mid - h / 2
            gradient = QLinearGradient(0, y, 0, y + h)
            head = QColor(accent).lighter(160)
            head.setAlphaF(min(1.0, 0.55 + 0.45 * shaped))
            tail = QColor(accent)
            tail.setAlphaF(0.22 + 0.60 * shaped)
            gradient.setColorAt(0.0, head)
            gradient.setColorAt(1.0, tail)
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(QRectF(x, y, bar_w, h), bar_w / 2, bar_w / 2)
        return
    # Bars: a dense comb of hair-thin picks.
    bar_w = max(1.0, span / (count * 3.4))
    bars = max(18, min(44, int(span / 5.2)))
    step = (span - bar_w) / max(1, bars - 1)
    for i in range(bars):
        level = levels[int(i * (count - 1) / (bars - 1))]
        shaped = min(1.0, level ** 0.55)
        h = max(2.0, height * 0.06) + shaped * (height * 0.90)
        colour = QColor(accent if shaped > 0.04 else MUTED)
        colour.setAlphaF(0.30 + 0.70 * min(1.0, shaped * 2.2))
        painter.setBrush(colour)
        painter.drawRect(QRectF(left + i * step, mid - h / 2, bar_w, h))


def set_meter(style):
    """Choose the live meter drawing; unknown values keep the current one."""
    global _METER
    if style in (METER_BARS, METER_SPECTRUM, METER_WAVE, METER_CAPSULE):
        _METER = style


def meter():
    return _METER


def _display_level(peak):
    """Map a PCM peak to a readable meter, without changing recorded audio.

    Microphone gain differs widely across devices. A linear 1% peak looked
    almost silent even though it is -40 dBFS. Use a fixed -60..0 dBFS display
    range; do not auto-amplify background noise or invent motion in silence.
    Drawing/previews consume the resulting normalized display levels.
    """
    if not math.isfinite(peak) or peak <= 0.001:
        return 0.0
    return min(1.0, max(0.0, (20.0 * math.log10(peak) + 60.0) / 60.0))


class MeterPreview(QWidget):
    """Bir stil seçeneğinin gerçek çizimiyle canlı önizlemesi.

    Ayarlar listesinde her satırın yanında o stilin nasıl göründüğü durur;
    seçenek adı tek başına "Dalga" ile "Kapsüller" arasındaki farkı
    anlatamaz. Önizleme, üretimde kullanılan aynı çizim kodunu çağırır, o
    yüzden gördüğü şey çalışırken gördüğü şeydir.
    """

    WIDTH = 148
    HEIGHT = 30

    def __init__(self, style, parent=None):
        super().__init__(parent)
        self.style = style
        self._selected = False
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._phase = 0.0
        self._anim = QTimer(self)
        self._anim.setInterval(60)
        self._anim.timeout.connect(self._advance)

    def showEvent(self, event):
        super().showEvent(event)
        # The animation is only worth running while it can be seen; the
        # settings window stays alive (hidden) for the life of the app.
        self._anim.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._anim.stop()

    def set_selected(self, selected):
        self._selected = bool(selected)
        self.update()

    def _advance(self):
        self._phase += 0.16
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        painter.fillPath(path, BG)
        if self._selected:
            painter.setPen(QPen(QColor(ASK), 2.0))
        else:
            painter.setPen(QPen(BORDER, 1.0))
        painter.drawPath(path)
        levels = [min(1.0, 0.12 + 0.85 * (0.5 + 0.5 * math.sin(
            self._phase + i * 0.7))) for i in range(BARS)]
        # The production drawing code, borrowed rather than duplicated: a
        # preview that drifts from the real thing is worse than none.
        saved = meter()
        set_meter(self.style)
        try:
            _draw_meter_into(painter, self.rect().adjusted(8, 4, -8, -4),
                             levels, STATE_COLORS["recording"])
        finally:
            set_meter(saved)


def show_live_text_enabled():
    """Whether the interim transcript is drawn on the recording ribbon."""
    return _SHOW_LIVE_TEXT


_SHOW_LIVE_TEXT = True


def set_show_live_text(enabled):
    global _SHOW_LIVE_TEXT
    _SHOW_LIVE_TEXT = bool(enabled)


def set_theme(colors):
    """Apply the central WordArc palette to existing and future overlays."""
    global BG, BORDER, TEXT, MUTED, BUSY, THEM, ASK, STATE_COLORS
    BG = QColor(colors.surface)
    BG.setAlpha(242 if colors.mode == "dark" else 248)
    BORDER = QColor(colors.border)
    BORDER.setAlpha(210)
    TEXT = QColor(colors.text)
    MUTED = QColor(colors.muted)
    BUSY = QColor(colors.cyan)
    THEM = QColor(colors.cyan)
    ASK = QColor(colors.violet)
    STATE_COLORS = {"recording": REC, "asking": ASK, "meeting": REC,
                    "busy": BUSY, "done": OK, "warning": WARN, "error": ERR}


class Overlay(QWidget):
    """One indicator. Give it `below` and it stacks on top of that one instead
    of covering it, which is what lets a dictation and a command to the agent be
    under way at the same time and still both be visible."""

    def __init__(self, corner="bottom-left", below=None, dismissable=False):
        super().__init__(None)
        self.corner = corner
        self.below = below
        # A job that can run for ten minutes should not have to be watched for
        # ten minutes. Clicking such an indicator puts the progress away; the
        # work carries on and its result still shows up.
        self.dismissable = dismissable
        self.muted = False
        self._stacked = False
        self.state = "idle"
        self.message = ""
        self.levels = [0.0] * BARS
        self.levels2 = [0.0] * BARS   # the other side, while a meeting records
        self.seconds = 0.0
        self._phase = 0.0
        self._concealed = True

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # One that can be clicked away has to receive the click, which means it
        # also swallows one aimed at whatever is underneath it. The rest stay
        # transparent to the mouse, as an indicator should be.
        if dismissable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.resize(MIN_WIDTH, HEIGHT)

        self._anim = QTimer(self)
        self._anim.setInterval(33)
        self._anim.timeout.connect(self._tick)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._conceal)

    # ---- public API --------------------------------------------------

    def show_recording(self, asking=False):
        """The same ribbon either way, in a different colour when what is being
        recorded is a command for Claude rather than something to paste."""
        self.state = "asking" if asking else "recording"
        self.message = ""
        self.seconds = 0.0
        self.levels = [0.0] * BARS
        self.muted = False   # a new run starts visible, whatever the last one did
        self._hide_timer.stop()
        self._appear()

    def show_live_text(self, text):
        """Interim transcript on the recording ribbon: no longer drawn.

        The ribbon shows the level meter in every live state now, so a live
        dictation looks like the other recordings. The words are delivered
        when the recording ends. The call site is kept so a live session
        that still reports a preview does not fail; the text is dropped.
        """
        self.message = ""

    def show_meeting(self):
        """Both channels at once: your voice up, the other side down."""
        self.state = "meeting"
        self.message = ""
        self.seconds = 0.0
        self.levels = [0.0] * BARS
        self.levels2 = [0.0] * BARS
        self._hide_timer.stop()
        self._appear()

    def show_busy(self, message):
        # Muted: the stages keep arriving and are simply not drawn. The state is
        # left alone as well, so nothing repaints the box back onto the screen.
        if self.muted:
            self.message = message
            return
        self.state = "busy"
        self.message = message
        self._hide_timer.stop()
        self._appear()

    def show_done(self, message="", msec=2000):
        self._finish("done", message, msec)

    def show_warning(self, message, msec=9000):
        """Finished, but something the user should know about went wrong."""
        self._finish("warning", message, msec)

    def show_error(self, message, msec=6000):
        self._finish("error", message, msec)

    def _finish(self, state, message, msec):
        """An outcome always shows, even one that was told to be quiet: waving
        the progress away asks not to be watched, not to be kept in the dark."""
        self.muted = False
        self.state = state
        self.message = message
        self._appear()
        self._hide_timer.start(msec)

    def dismiss(self):
        self._hide_timer.stop()
        self._conceal()

    def mousePressEvent(self, event):
        # Only a job in progress can be waved away. A recording is short and
        # ending it by accident would cost the words; an outcome goes on its own.
        if self.dismissable and self.state == "busy":
            self.muted = True
            self.dismiss()
        event.accept()

    @property
    def showing(self):
        """Mapped and actually painting something. The window stays mapped while
        idle, so isVisible() alone would always say yes."""
        return self.isVisible() and not self._concealed

    def push_level(self, level):
        self.levels = self.levels[1:] + [_display_level(level)]

    def push_levels(self, mine, theirs):
        self.levels = self.levels[1:] + [_display_level(mine)]
        self.levels2 = self.levels2[1:] + [_display_level(theirs)]

    def set_seconds(self, seconds):
        self.seconds = seconds

    # ---- internals -----------------------------------------------------

    def _appear(self):
        self._resize_to_content()
        self._reposition()
        if not self.isVisible():
            self.show()
        if self._concealed:
            self.raise_()
            self._concealed = False
        if not self._anim.isActive():
            self._anim.start()

    def _conceal(self):
        """Empty the window out instead of unmapping it.

        Unmapping tears the window down and the next dictation builds a new one,
        which makes the compositor repaint whatever sits underneath: on a tiled
        desktop the terminal behind visibly flinches every time the indicator
        goes away. So the window stays mapped and simply paints nothing. It has
        to be a real repaint, not just zero opacity: with the animation stopped
        nothing else damages the surface, and the stale frame would sit on the
        screen until some other event made the compositor redraw it.
        """
        self._anim.stop()
        self.state = "hidden"
        self._concealed = True
        self.repaint()

    def _resize_to_content(self):
        if self.state in LIVE:
            # A meeting runs long enough to need an hours field.
            width = MIN_WIDTH + (24 if self.state == "meeting" else 0)
        else:
            metrics = QFontMetrics(self._label_font())
            extra = 76 + (18 if self._can_dismiss else 0)
            width = max(MIN_WIDTH,
                        min(MAX_WIDTH, metrics.horizontalAdvance(self.message) + extra))
        self.resize(width, HEIGHT)

    def _reposition(self):
        # On a multi-monitor setup, show up where the user actually is.
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        left = "left" in self.corner
        top = "top" in self.corner
        self._stacked = self.below is not None and self.below.showing
        # Stack away from the edge the corner sits on, so the pair grows into the
        # screen rather than off it.
        step = (self.below.height() + GAP) if self._stacked else 0
        x = area.left() + MARGIN if left else area.right() - self.width() - MARGIN
        y = (area.top() + MARGIN + step if top
             else area.bottom() - self.height() - MARGIN - step)
        self.move(int(x), int(y))

    def _tick(self):
        self._phase += 0.12
        # The one underneath can come and go while this one is up; drop back to
        # the corner when it does rather than leaving a gap where it was.
        if self.below is not None and self.below.showing != self._stacked:
            self._reposition()
        if self.state in LIVE:
            # keep the ribbon moving even through a pause in speech
            self.levels = self.levels[1:] + [self.levels[-1] * 0.72]
        if self.state == "meeting":
            self.levels2 = self.levels2[1:] + [self.levels2[-1] * 0.72]
        self.update()

    def _label_font(self):
        font = QFont(self.font())
        font.setPointSizeF(10.5)
        return font

    # ---- painting --------------------------------------------------

    def paintEvent(self, _event):
        if self.state == "hidden":
            return  # translucent window, nothing drawn means nothing shown

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)

        path = QPainterPath()
        path.addRoundedRect(rect, 15, 15)
        painter.fillPath(path, BG)
        glow = QLinearGradient(rect.topLeft(), rect.topRight())
        glow.setColorAt(0, ASK)
        glow.setColorAt(1, THEM)
        painter.setPen(QPen(QBrush(glow), 1.5))
        painter.drawPath(path)

        accent = STATE_COLORS.get(self.state, MUTED)
        self._draw_indicator(painter, accent)

        if self.state in LIVE:
            self._draw_meter(painter, accent)
            self._draw_time(painter)
        else:
            self._draw_message(painter)
            if self._can_dismiss:
                self._draw_dismiss(painter)

    def _draw_meter(self, painter, accent):
        """The live level meter, in whichever shape Settings asks for.

        Every live state shares this, and the drawing itself lives in
        ``_draw_meter_into`` so the settings previews show exactly what the
        ribbon will show. The interim transcript is not drawn — the words
        arrive when the recording ends, and the ribbon stays a meter.
        """
        if self.state == "meeting":
            self._draw_dual_meter(painter, meter())
            return
        rect = QRectF(46.0, 5.0, max(20.0, self.width() - 46.0 - 58.0),
                      self.height() - 10.0)
        _draw_meter_into(painter, rect, self.levels, accent, style=meter())

    def _draw_dual_meter(self, painter, style):
        """A meeting: your voice above, the other side below.

        Both halves are drawn through ``_draw_meter_into`` with the chosen
        style, so a setting picked once holds everywhere: a Wave meeting shows
        two waves, a Capsules meeting two rows of capsules. The second channel
        keeps the cyan accent that already marks it.
        """
        span = max(20.0, self.width() - 46.0 - 74.0)
        half = (self.height() - 6.0) / 2
        _draw_meter_into(painter, QRectF(46.0, 2.0, span, half),
                         self.levels, REC, style=style)
        _draw_meter_into(painter, QRectF(46.0, 4.0 + half, span, half),
                         self.levels2, THEM, style=style)

    def _draw_live_caption(self, painter, accent):
        """Kept for the record: the interim transcript is no longer drawn.

        Live dictation now shows the same meter as every other recording —
        the words arrive when the recording ends. Nothing calls this; the
        method stays one release so an old call site cannot break a build.
        """
        return

    def _draw_indicator(self, painter, accent):
        cx, cy = 26.0, self.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        if self.state in LIVE:
            pulse = 0.62 + 0.38 * (0.5 + 0.5 * math.sin(self._phase * 1.6))
            glow = QColor(accent)
            glow.setAlphaF(0.22 * pulse)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(cx, cy), 13 * pulse, 13 * pulse)
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(cx, cy), 5.5, 5.5)
        elif self.state == "busy":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(QColor(accent), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            span = 100 * 16
            start = int(-self._phase * 320) % (360 * 16)
            painter.drawArc(QRectF(cx - 8, cy - 8, 16, 16), start, span)
        elif self.state == "done":
            pen = QPen(accent, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(
                QPointF(cx - 7, cy), QPointF(cx - 2, cy + 5.5), QPointF(cx + 7.5, cy - 6)
            )
        elif self.state == "warning":
            pen = QPen(accent, 2.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(cx, cy - 7), QPointF(cx, cy + 1.5))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(cx, cy + 6), 1.5, 1.5)
        else:  # error
            pen = QPen(accent, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(cx - 6, cy - 6), QPointF(cx + 6, cy + 6))
            painter.drawLine(QPointF(cx + 6, cy - 6), QPointF(cx - 6, cy + 6))

    def _draw_time(self, painter):
        font = QFont(self.font())
        font.setPointSizeF(10.0)
        font.setFamilies(["monospace"])
        painter.setFont(font)
        painter.setPen(MUTED)
        mins, secs = divmod(int(self.seconds), 60)
        hours, mins = divmod(mins, 60)
        text = f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"
        width = 62 if hours else 44
        painter.drawText(
            QRectF(self.width() - width - 12, 0, width, self.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
            text,
        )

    @property
    def _can_dismiss(self):
        return self.dismissable and self.state == "busy"

    def _draw_dismiss(self, painter):
        """A faint cross on the right: without it there is nothing to say the
        box can be clicked away, and a feature nobody can see is not one."""
        cx, cy = self.width() - 18.0, self.height() / 2
        pen = QPen(QColor(MUTED), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(cx - 4, cy - 4), QPointF(cx + 4, cy + 4))
        painter.drawLine(QPointF(cx + 4, cy - 4), QPointF(cx - 4, cy + 4))

    def _draw_message(self, painter):
        painter.setFont(self._label_font())
        painter.setPen({"error": ERR, "warning": WARN}.get(self.state, TEXT))
        # Leave the cross its corner rather than running the text under it.
        box = QRectF(46, 0, self.width() - 60 - (18 if self._can_dismiss else 0),
                     self.height())
        metrics = QFontMetrics(self._label_font())
        text = metrics.elidedText(self.message, Qt.TextElideMode.ElideRight, int(box.width()))
        painter.drawText(
            box, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text
        )
