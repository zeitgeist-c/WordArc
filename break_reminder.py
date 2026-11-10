"""Break reminder: a small, separate helper that reminds the user to stand up.

Work stays in the background. The panel offers start, snooze and cancel
when work ends, and shows a countdown with controls during the break.

Rules the module follows:

- The break only ever starts through the user's own click. A finished timer,
  a locked screen or an idle computer never counts as "stood up".
- QTimer is only a waker (1 s). Every duration is an absolute ``time.monotonic``
  deadline, so a late tick fires a transition exactly once instead of
  fast-forwarding through phases.
- Sleep and screen lock pause the countdown; the remaining time is kept and
  restored on return. Sleep is never inferred from a delayed tick alone:
  Windows power/session events drive it (``WM_POWERBROADCAST``,
  ``WM_WTSSESSION_CHANGE``).
- The window never takes keyboard focus
  (``WindowDoesNotAcceptFocus`` + ``WA_ShowWithoutActivating`` + ``NoFocus``);
  the buttons stay clickable with the mouse.
- No sound, camera, phone notification, web call or new dependency.
"""

from __future__ import annotations

import logging
import math
import os
import time
from enum import Enum, auto

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, Qt, QAbstractNativeEventFilter, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout,
    QWidget,
)

import theme
from i18n import t

_log = logging.getLogger("wordarc.breaks")

MARGIN = 28
GAP = 10

MIN_WORK_MINUTES = 5
MAX_WORK_MINUTES = 180
MIN_BREAK_MINUTES = 1
MAX_BREAK_MINUTES = 60

VALID_CORNERS = ("bottom-right", "bottom-left")

# Fixed snooze choices offered on the reminder panel (minutes).
SNOOZE_CHOICES = (1, 5, 10)

# How long the finished break shows 00:00 before the next work period.
BREAK_DONE_S = 2


class BreakPhase(Enum):
    """The break reminder's state machine."""

    OFF = auto()       # feature disabled, nothing shown
    WORKING = auto()   # counting down work (or a chosen snooze), hidden
    REMINDER = auto()  # work period over, panel shown, break NOT started
    BREAK = auto()     # break started by the user, counting down, shown
    BREAK_DONE = auto()  # break over: 00:00 shown briefly, then hidden work
    PAUSED = auto()    # manually paused, or auto-paused by sleep/lock


def clamp_minutes(value, low, high, default):
    """A safe minute count: wrong types and out-of-range values fall back."""
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return default
    if minutes < low or minutes > high:
        return default
    return minutes


class BreakEngine:
    """Testable timing logic with no Qt dependency.

    ``clock`` is injectable (``time.monotonic`` in production, a fake in
    tests), so every transition can be driven deterministically.
    """

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.phase = BreakPhase.OFF
        self.work_s = 25 * 60
        self.break_s = 5 * 60
        self._deadline = 0.0
        self._done_until = 0.0
        self._paused_from = BreakPhase.WORKING
        self._paused_remaining = 0.0
        self._auto_paused = False

    # ---- configuration -------------------------------------------------

    def apply_durations(self, work_s, break_s, now=None):
        """New totals; an active countdown keeps its elapsed progress."""
        now = self._clock() if now is None else now
        if self.phase == BreakPhase.PAUSED:
            # A paused countdown keeps its remainder frozen; shift that
            # remainder by the same delta a running one would get.
            if self._paused_from in (BreakPhase.WORKING, BreakPhase.REMINDER):
                self._paused_remaining = max(
                    0.0, self._paused_remaining + (work_s - self.work_s))
            elif self._paused_from == BreakPhase.BREAK:
                self._paused_remaining = max(
                    0.0, self._paused_remaining + (break_s - self.break_s))
        elif self.phase in (BreakPhase.WORKING, BreakPhase.REMINDER):
            self._deadline += work_s - self.work_s
        elif self.phase == BreakPhase.BREAK:
            self._deadline += break_s - self.break_s
        self.work_s, self.break_s = work_s, break_s

    # ---- state changes --------------------------------------------------

    def set_enabled(self, enabled, now=None):
        now = self._clock() if now is None else now
        if enabled and self.phase == BreakPhase.OFF:
            self.phase = BreakPhase.WORKING
            self._deadline = now + self.work_s
            self._auto_paused = False
            return True
        if not enabled and self.phase != BreakPhase.OFF:
            self.phase = BreakPhase.OFF
            self._auto_paused = False
            return True
        return False

    def refresh(self, now=None):
        """Fire due transitions.

        Returns events: 'reminder', 'break_finished', 'work_started'.
        Absolute deadlines make this idempotent: a transition changes the
        phase, so a late or repeated call cannot replay it.
        """
        now = self._clock() if now is None else now
        events = []
        if self.phase == BreakPhase.WORKING and now >= self._deadline:
            self.phase = BreakPhase.REMINDER
            events.append("reminder")
        elif self.phase == BreakPhase.BREAK and now >= self._deadline:
            self.phase = BreakPhase.BREAK_DONE
            self._done_until = now + BREAK_DONE_S
            # The new 25 minutes start the instant the break ends: 00:00 is
            # only a 2 s visual, never extra work time.
            self._deadline = now + self.work_s
            events.append("break_finished")
        elif self.phase == BreakPhase.BREAK_DONE and now >= self._done_until:
            self.phase = BreakPhase.WORKING
            events.append("work_started")
        return events

    def start_break(self, now=None):
        if self.phase != BreakPhase.REMINDER:
            return False
        now = self._clock() if now is None else now
        self.phase = BreakPhase.BREAK
        self._deadline = now + self.break_s
        return True

    def snooze(self, seconds, now=None):
        """A chosen snooze: hide everything, remind again when it elapses.

        The break never starts on its own.
        """
        if self.phase != BreakPhase.REMINDER:
            return False
        now = self._clock() if now is None else now
        self.phase = BreakPhase.WORKING
        self._deadline = now + max(1.0, float(seconds))
        return True

    def cancel(self, now=None):
        """Drop the reminder: a fresh full work period starts at once.

        Cancelling is not disabling: the feature stays on.
        """
        if self.phase != BreakPhase.REMINDER:
            return False
        now = self._clock() if now is None else now
        self.phase = BreakPhase.WORKING
        self._deadline = now + self.work_s
        return True

    @property
    def break_paused(self):
        return (self.phase == BreakPhase.PAUSED
                and self._paused_from == BreakPhase.BREAK and not self._auto_paused)

    def end_break(self, now=None):
        if self.phase not in (BreakPhase.BREAK, BreakPhase.BREAK_DONE) and not self.break_paused:
            return False
        now = self._clock() if now is None else now
        if self.phase != BreakPhase.BREAK_DONE:
            self._deadline = now + self.work_s
        self.phase = BreakPhase.WORKING
        return True

    def pause(self, now=None):
        if self.phase not in (BreakPhase.WORKING, BreakPhase.REMINDER,
                              BreakPhase.BREAK, BreakPhase.BREAK_DONE):
            return False
        now = self._clock() if now is None else now
        self._paused_from = self.phase
        self._paused_remaining = max(0.0, self._phase_remaining(now))
        self._auto_paused = False
        self.phase = BreakPhase.PAUSED
        return True

    def _phase_remaining(self, now):
        if self._paused_from == BreakPhase.BREAK_DONE:
            return self._done_until - now
        return self._deadline - now

    def resume(self, now=None):
        if self.phase != BreakPhase.PAUSED:
            return False
        now = self._clock() if now is None else now
        self.phase = self._paused_from
        if self.phase == BreakPhase.BREAK_DONE:
            self._done_until = now + self._paused_remaining
        else:
            self._deadline = now + self._paused_remaining
        self._paused_remaining = 0.0
        self._auto_paused = False
        return True

    # ---- sleep / screen lock --------------------------------------------

    def on_suspend(self, now=None):
        """Sleep or lock: freeze the countdown, keep the remainder."""
        if self.phase not in (BreakPhase.WORKING, BreakPhase.REMINDER,
                              BreakPhase.BREAK, BreakPhase.BREAK_DONE):
            return False
        now = self._clock() if now is None else now
        self._paused_from = self.phase
        self._paused_remaining = max(0.0, self._phase_remaining(now))
        self._auto_paused = True
        self.phase = BreakPhase.PAUSED
        return True

    def on_resume(self, now=None):
        """Wake or unlock: continue only where an auto-pause left off.

        A manual pause stays paused; the user resumes it themselves.
        """
        if self.phase != BreakPhase.PAUSED or not self._auto_paused:
            return False
        return self.resume(now)

    # ---- reading ----------------------------------------------------------

    def remaining(self, now=None):
        now = self._clock() if now is None else now
        if self.phase == BreakPhase.PAUSED:
            return (math.ceil(self._paused_remaining) if self.break_paused
                    else int(self._paused_remaining))
        if self.phase == BreakPhase.BREAK:
            return math.ceil(max(0.0, self._deadline - now))
        if self.phase == BreakPhase.WORKING:
            return int(max(0.0, self._deadline - now))
        return 0


def _fmt(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class _PowerFilter(QAbstractNativeEventFilter):
    """Windows sleep/lock events, without ever blocking the app.

    Installed once on the QApplication; removed again on shutdown.
    Everything degrades to a no-op off Windows.
    """

    WM_POWERBROADCAST = 0x218
    PBT_APMSUSPEND = 0x4
    PBT_APMRESUMESUSPEND = 0x7
    PBT_APMRESUMEAUTOMATIC = 0x12
    WM_WTSSESSION_CHANGE = 0x2B1
    WTS_SESSION_LOCK = 0x7
    WTS_SESSION_UNLOCK = 0x8

    def __init__(self, hold, release):
        super().__init__()
        self._hold = hold
        self._release = release

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt override)
        try:
            # PyQt6 hands the type over as a QByteArray, not a str.
            if isinstance(event_type, str):
                name = event_type
            else:
                try:
                    name = bytes(event_type).decode("ascii", "ignore")
                except Exception:
                    return False, 0
            if name != "windows_generic_MSG":
                return False, 0
            import ctypes
            from ctypes import wintypes

            class _MSG(ctypes.Structure):
                _fields_ = [("hwnd", wintypes.HWND),
                            ("message", wintypes.UINT),
                            ("wParam", wintypes.WPARAM),
                            ("lParam", wintypes.LPARAM),
                            ("time", wintypes.DWORD),
                            ("pt", wintypes.POINT)]

            msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
            if msg.message == self.WM_POWERBROADCAST:
                if msg.wParam == self.PBT_APMSUSPEND:
                    self._hold("sleep")
                elif msg.wParam in (self.PBT_APMRESUMESUSPEND,
                                    self.PBT_APMRESUMEAUTOMATIC):
                    self._release("sleep")
            elif msg.message == self.WM_WTSSESSION_CHANGE:
                if msg.wParam == self.WTS_SESSION_LOCK:
                    self._hold("lock")
                elif msg.wParam == self.WTS_SESSION_UNLOCK:
                    self._release("lock")
        except Exception:
            _log.exception("break power filter failed")
        return False, 0


class BreakPet(QWidget):
    """Small original companion and a ring that shows the remaining time."""

    def __init__(self, parent=None, *, size=80):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._fraction = 1.0
        self._frame = 0
        self._playing = False
        self._colors = theme.palette()
        self._timer = QTimer(self, interval=40)
        self._timer.timeout.connect(self._advance)

    def _advance(self):
        self._frame = (self._frame + 1) % 100
        self.update()

    def set_progress(self, fraction, playing):
        self._fraction = fraction
        self._playing = playing
        self._sync_timer()
        self.update()

    def _sync_timer(self):
        if self._playing and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.width() / 80, self.height() / 80)
        colors = self._colors
        ring = QRectF(5, 5, 70, 70)
        painter.setPen(QPen(QColor(colors.border), 3))
        painter.drawEllipse(ring)
        if self._fraction:
            pen = QPen(QColor(colors.violet), 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(ring, 90 * 16, -round(360 * 16 * self._fraction))

        # A little violet sprout, gently bobbing as the timer runs.
        dy = 2 * math.sin(self._frame * math.tau / 100)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.surface_alt))
        painter.drawEllipse(QRectF(22, 56, 36, 8))
        painter.setBrush(QColor(colors.violet))
        painter.drawRoundedRect(QRectF(20, 30 + dy, 40, 27), 13, 13)
        painter.setBrush(QColor(colors.success))
        painter.drawEllipse(QRectF(39, 21 + dy, 13, 9))
        painter.setBrush(QColor("#211538"))
        eye_height = 2 if self._frame in (95, 96, 97) else 5
        for x in (31, 45):
            painter.drawRoundedRect(QRectF(x, 39 + dy, 4, eye_height), 2, 2)
        painter.setPen(QPen(QColor("#211538"), 1.4))
        painter.drawArc(QRectF(36, 43 + dy, 8, 6), 180 * 16, 180 * 16)


class BreakWindow(QWidget):
    """One panel, two faces.

    The reminder and countdown share a footprint. Work and snoozed
    waiting stay in the background.
    """

    start_requested = pyqtSignal()
    snooze_requested = pyqtSignal(int)  # chosen minutes: 1, 5 or 10
    cancel_requested = pyqtSignal()
    pause_requested = pyqtSignal(bool)
    end_requested = pyqtSignal()

    WIDTH, HEIGHT = 318, 158

    def __init__(self, conf=None, record_overlay=None, parent=None):
        super().__init__(None)
        self._conf = conf
        self._record_overlay = record_overlay
        self._phase = BreakPhase.OFF
        self._remaining = 0
        self._drag_offset = None
        self._bg = QColor("#1C1C20")
        self._border = QColor("#34343C")
        self._text = QColor("#F3F3F5")
        self._muted = QColor("#A1A1AD")

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._stack)

        # -- countdown face: the running break, then the brief 00:00 --
        count_page = QWidget()
        count_layout = QVBoxLayout(count_page)
        count_layout.setContentsMargins(15, 12, 15, 12)
        count_layout.setSpacing(5)
        header = QHBoxLayout()
        self._count_title = QLabel()
        self._count_title.setObjectName("breakTitle")
        header.addWidget(self._count_title, 1)
        self._end_button = QPushButton("×")
        self._end_button.setObjectName("breakEnd")
        self._end_button.setFixedSize(26, 26)
        self._end_button.clicked.connect(self.end_requested.emit)
        header.addWidget(self._end_button)
        count_layout.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(12)
        self._pet = BreakPet()
        content.addWidget(self._pet)
        details = QVBoxLayout()
        details.setSpacing(2)
        self._time_label = QLabel("--:--")
        self._time_label.setObjectName("breakTime")
        details.addWidget(self._time_label)
        self._state_label = QLabel("")
        self._state_label.setObjectName("muted")
        self._state_label.setWordWrap(True)
        details.addWidget(self._state_label)
        self._pause_button = QPushButton()
        self._pause_button.setObjectName("breakPause")
        self._pause_button.clicked.connect(
            lambda: self.pause_requested.emit(self._phase != BreakPhase.PAUSED))
        details.addWidget(self._pause_button, 0, Qt.AlignmentFlag.AlignLeft)
        content.addLayout(details, 1)
        count_layout.addLayout(content, 1)
        for button in (self._end_button, self._pause_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stack.addWidget(count_page)

        # -- reminder face: start, three fixed snoozes, cancel --
        reminder_page = QWidget()
        reminder_layout = QVBoxLayout(reminder_page)
        reminder_layout.setContentsMargins(15, 12, 15, 12)
        reminder_layout.setSpacing(6)
        reminder_header = QHBoxLayout()
        reminder_header.setSpacing(9)
        self._reminder_pet = BreakPet(size=52)
        self._reminder_pet.set_progress(1.0, True)
        reminder_header.addWidget(self._reminder_pet)
        reminder_copy = QVBoxLayout()
        reminder_copy.setSpacing(2)
        reminder_copy.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._title_label = QLabel()
        self._title_label.setObjectName("breakTitle")
        reminder_copy.addWidget(self._title_label)
        self._body_label = QLabel()
        self._body_label.setObjectName("muted")
        self._body_label.setWordWrap(True)
        reminder_copy.addWidget(self._body_label)
        reminder_header.addLayout(reminder_copy, 1)
        self._cancel_button = QPushButton("×")
        self._cancel_button.setObjectName("breakEnd")
        self._cancel_button.setFixedSize(26, 26)
        self._cancel_button.clicked.connect(self.cancel_requested.emit)
        reminder_header.addWidget(self._cancel_button, 0, Qt.AlignmentFlag.AlignTop)
        reminder_layout.addLayout(reminder_header, 1)

        self._start_button = QPushButton()
        self._start_button.setObjectName("breakStart")
        self._start_button.setMinimumHeight(31)
        self._start_button.clicked.connect(self.start_requested.emit)
        reminder_layout.addWidget(self._start_button)
        snooze_row = QHBoxLayout()
        snooze_row.setSpacing(6)
        self._snooze_label = QLabel()
        self._snooze_label.setObjectName("muted")
        snooze_row.addWidget(self._snooze_label)
        self._snooze_buttons = {}
        for minutes in SNOOZE_CHOICES:
            button = QPushButton()
            button.setObjectName("breakSnooze")
            button.clicked.connect(
                lambda _checked=False, m=minutes: self.snooze_requested.emit(m))
            snooze_row.addWidget(button, 1)
            self._snooze_buttons[minutes] = button
        reminder_layout.addLayout(snooze_row)
        for button in (self._start_button, self._cancel_button, *self._snooze_buttons.values()):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._stack.addWidget(reminder_page)

        self.retranslate()
        self.restyle()
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        app = QApplication.instance()
        if app is not None:
            try:
                app.screenRemoved.connect(lambda _s: self._reclamp())
            except Exception:
                _log.exception("break window could not watch screens")

    # ---- content ---------------------------------------------------------

    def retranslate(self):
        self._title_label.setText(t("Time for a break"))
        self._body_label.setText(t("Stand up and walk a little."))
        self._start_button.setText(t("Start the break"))
        self._snooze_label.setText(t("Snooze"))
        for minutes, button in self._snooze_buttons.items():
            button.setText(t("{minutes} min", minutes=minutes))
            button.setToolTip(t(f"Snooze {minutes} min"))
            button.setAccessibleName(button.toolTip())
        self._cancel_button.setToolTip(t("Cancel"))
        self._cancel_button.setAccessibleName(self._cancel_button.toolTip())
        self._count_title.setText(t("Break"))
        self._end_button.setToolTip(t("End the break"))
        self._end_button.setAccessibleName(self._end_button.toolTip())
        self._update_texts()

    def restyle(self):
        colors = theme.palette()
        self._bg = QColor(colors.surface)
        self._border = QColor(colors.border)
        self._text = QColor(colors.text)
        self._muted = QColor(colors.muted)
        start_text = "#211538" if colors.mode == "dark" else "#FFFFFF"
        sheet = (
            f"QLabel {{ color: {self._text.name()}; background: transparent; }}"
            f"QLabel#muted {{ color: {self._muted.name()}; }}"
            f"QPushButton {{ color: {self._text.name()}; }}"
            f"QLabel#breakTitle {{ font-size: 10pt; font-weight: 700; }}"
            f"QLabel#breakTime {{ font-family: 'Consolas'; font-size: 27pt; font-weight: 700; }}"
            f"QPushButton#breakPause, QPushButton#breakEnd, QPushButton#breakSnooze {{"
            f" background: {colors.surface_alt}; border: 1px solid {colors.border};"
            f" border-radius: 8px; min-height: 0px; padding: 3px 10px; }}"
            f"QPushButton#breakEnd {{ padding: 0px; font-size: 15pt; }}"
            f"QPushButton#breakPause:hover, QPushButton#breakEnd:hover, QPushButton#breakSnooze:hover {{"
            f" background: {colors.hover}; border-color: {colors.violet}; }}"
            f"QPushButton#breakStart {{ color: {start_text}; background: {colors.violet};"
            f" border: 0; border-radius: 8px; padding: 4px 10px; font-weight: 700; }}"
            f"QPushButton#breakStart:hover {{ background: {colors.cyan}; }}"
        )
        for pet in (self._pet, self._reminder_pet):
            pet._colors = colors
            pet.update()
        self.setStyleSheet(sheet)
        self.update()

    def set_phase(self, phase, remaining=0, duration=300):
        self._phase = phase
        self._remaining = remaining
        if phase == BreakPhase.OFF:
            self.hide()
            return
        self._pet.set_progress(min(1.0, remaining / duration), phase == BreakPhase.BREAK)
        self._stack.setCurrentIndex(1 if phase == BreakPhase.REMINDER else 0)
        self._reclamp()
        if not self.isVisible():
            self.place()
            self.show()
        self._update_texts()
        self._avoid_record_overlay()
        self.update()

    def _update_texts(self):
        if self._phase in (BreakPhase.BREAK, BreakPhase.BREAK_DONE, BreakPhase.PAUSED):
            self._time_label.setText(_fmt(self._remaining))
            paused = self._phase == BreakPhase.PAUSED
            self._state_label.setText(t("paused") if paused else t("Stand up and walk a little."))
            self._pause_button.setText(t("Resume" if paused else "Pause"))
            self._pause_button.setVisible(self._phase != BreakPhase.BREAK_DONE)

    # ---- placement ---------------------------------------------------------

    def _corner(self):
        try:
            corner = (self._conf.get("break_corner", "bottom-right")
                      if self._conf is not None else "bottom-right")
        except Exception:
            corner = "bottom-right"
        return corner if corner in VALID_CORNERS else "bottom-right"

    def _saved_pos(self):
        try:
            pos = self._conf.get("break_pos", []) if self._conf is not None else []
        except Exception:
            return None
        if (isinstance(pos, list) and len(pos) == 2
                and all(isinstance(v, int) for v in pos)):
            return pos
        return None

    def place(self):
        """Saved drag position wins; otherwise the chosen corner.

        The cursor is never followed: detaching the monitor the window was
        on falls back into an accessible area instead of stranding it.
        """
        app = QApplication.instance()
        screens = app.screens() if app is not None else []
        if not screens:
            return
        saved = self._saved_pos()
        if saved is not None:
            for screen in screens:
                area = screen.availableGeometry()
                if area.contains(saved[0], saved[1]):
                    self.move(saved[0], saved[1])
                    self._reclamp()
                    return
        screen = app.primaryScreen() if app is not None else screens[0]
        area = screen.availableGeometry()
        left = "left" in self._corner()
        width = self.width() or self.COUNTDOWN_W
        height = self.height() or self.COUNTDOWN_H
        x = area.left() + MARGIN if left else area.right() - width - MARGIN
        self.move(int(x), int(area.bottom() - height - MARGIN))
        self._reclamp()

    def _reclamp(self):
        """Keep the whole surface inside some accessible area.

        The monitor holding the window's top-left wins: growing near an
        edge slides the surface within its own monitor instead of jumping
        to the primary one. Only a top-left on no monitor falls back.
        """
        app = QApplication.instance()
        if app is None:
            return
        frame = self.frameGeometry()
        frame.moveTopLeft(self.pos())
        for screen in app.screens():
            if screen.availableGeometry().contains(frame):
                return
        host = QApplication.screenAt(self.pos())
        if host is not None:
            area = host.availableGeometry()
        else:
            primary = app.primaryScreen()
            if primary is None:
                return
            area = primary.availableGeometry()
        x = min(max(self.x(), area.left()), area.right() - self.width())
        y = min(max(self.y(), area.top()), area.bottom() - self.height())
        self.move(int(x), int(y))

    def _avoid_record_overlay(self):
        """Never cover a recording indicator.

        It moves above the indicator; when there is no room above, below
        it instead. Either way the result is re-clamped to its monitor.
        """
        other = (self._record_overlay() if callable(self._record_overlay)
                 else self._record_overlay)
        try:
            if (other is None or not other.isVisible()
                    or not self.isVisible()):
                return
            mine = self.frameGeometry()
            theirs = other.frameGeometry()
            if not mine.intersects(theirs):
                return
            app = QApplication.instance()
            host = QApplication.screenAt(self.pos()) if app is not None else None
            top = (host.availableGeometry().top() if host is not None else 0)
            above = theirs.top() - mine.height() - GAP
            if above >= top:
                self.move(self.x(), above)
            else:
                self.move(self.x(), theirs.bottom() + GAP)
            self._reclamp()
        except RuntimeError:
            pass  # the recording overlay went away mid-move

    # ---- dragging ------------------------------------------------------------

    def mousePressEvent(self, event):
        # Dragging works from any non-button surface, on either face.
        if event.button() == Qt.MouseButton.LeftButton and not isinstance(
                self.childAt(event.position().toPoint()), QPushButton):
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._reclamp()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None:
            self._drag_offset = None
            self._save_pos()
            self.dragged.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _save_pos(self):
        if self._conf is None:
            return
        try:
            self._conf["break_pos"] = [int(self.x()), int(self.y())]
            self._conf.save()
        except OSError:
            _log.warning("break window position could not be saved")

    # ---- painting --------------------------------------------------------------

    def paintEvent(self, _event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect().adjusted(1, 1, -1, -1)), 14, 14)
            painter.fillPath(path, self._bg)
            painter.setPen(self._border)
            painter.drawPath(path)
        except Exception:
            _log.exception("break window paint failed")


class BreakController(QObject):
    """Owns the engine, the waker timer, the window and the power listener."""

    state_changed = pyqtSignal(BreakPhase)
    tick = pyqtSignal(int)

    def __init__(self, conf, record_overlay=None, parent=None):
        super().__init__(parent)
        self._conf = conf
        self._record_overlay = record_overlay
        self.engine = BreakEngine()
        self.window = BreakWindow(conf, record_overlay)
        self.window.start_requested.connect(self.start_break_from_ui)
        self.window.snooze_requested.connect(self.snooze_from_ui)
        self.window.cancel_requested.connect(self.cancel_from_ui)
        self.window.pause_requested.connect(self.set_paused)
        self.window.end_requested.connect(self.end_break_from_ui)

        self._waker = QTimer(self)
        self._waker.setInterval(1000)
        self._waker.timeout.connect(self._wake)
        self._power_filter = None
        self._wts_registered = False
        self._suspended = False
        self._holds = set()
        self._capture_hold = False
        self._last_corner = None

    # ---- settings ----------------------------------------------------------

    def sync_from_conf(self):
        """One entry point for boot, save, language and theme changes.

        Calling it twice never creates a second timer, window or listener.
        """
        conf = self._conf
        enabled = bool(conf.get("break_enabled", False))
        work = clamp_minutes(conf.get("break_work_minutes", 25),
                             MIN_WORK_MINUTES, MAX_WORK_MINUTES, 25) * 60
        brk = clamp_minutes(conf.get("break_break_minutes", 5),
                            MIN_BREAK_MINUTES, MAX_BREAK_MINUTES, 5) * 60
        corner = conf.get("break_corner", "bottom-right")
        if corner not in VALID_CORNERS:
            corner = "bottom-right"
        self.engine.apply_durations(work, brk)
        if self.engine.set_enabled(enabled):
            self._announce()
        if enabled and not self._waker.isActive():
            self._waker.start()
        elif not enabled and self._waker.isActive():
            self._waker.stop()
        if enabled and self._power_filter is None:
            self._install_power_filter()
        # A changed corner beats a stale drag position: the window visibly
        # moves there now; the next drag saves a new position over it.
        # Otherwise the saved drag position keeps beating the corner.
        if self._last_corner is not None and corner != self._last_corner:
            try:
                conf["break_pos"] = []
                conf.save()
            except OSError:
                _log.warning("break corner change could not be saved")
            if self.engine.phase != BreakPhase.OFF:
                self.window.place()
        self._last_corner = corner
        self.window.restyle()
        self._push_phase_to_window()

    def _announce(self):
        self.state_changed.emit(self.engine.phase)
        self._push_phase_to_window()

    # Central visibility rule: the panel shows only for the reminder, the
    # running break and the brief 00:00 after it. A manually paused break
    # keeps its controls visible. Work and system suspensions stay hidden.
    _VISIBLE = (BreakPhase.REMINDER, BreakPhase.BREAK, BreakPhase.BREAK_DONE)

    def _push_phase_to_window(self):
        # A capture in progress owns visibility: ticks, transitions and
        # settings resyncs must not re-show the window until it is restored.
        if self._capture_hold:
            return
        if (not self._suspended
                and (self.engine.phase in self._VISIBLE or self.engine.break_paused)):
            self.window.set_phase(self.engine.phase,
                                  self.engine.remaining(), self.engine.break_s)
        else:
            self.window.set_phase(BreakPhase.OFF)

    # ---- waker ---------------------------------------------------------------

    def _wake(self):
        if self._suspended:
            return
        for event in self.engine.refresh():
            if event in ("reminder", "break_finished", "work_started"):
                self._announce()
        self.tick.emit(self.engine.remaining())
        self._push_phase_to_window()

    # ---- UI actions ------------------------------------------------------------

    def start_break_from_ui(self):
        if self.engine.start_break():
            self._announce()

    def snooze_from_ui(self, minutes):
        if self.engine.snooze(int(minutes) * 60):
            self._announce()

    def cancel_from_ui(self):
        if self.engine.cancel():
            self._announce()

    def end_break_from_ui(self):
        if self.engine.end_break():
            self._announce()

    def set_paused(self, paused):
        """Pause from the tray or countdown. Background work stays hidden."""
        if self._suspended:
            return
        if paused:
            if self.engine.pause():
                self._announce()
        else:
            if self.engine.resume():
                self._announce()

    def set_break_enabled(self, enabled):
        self._conf["break_enabled"] = bool(enabled)
        try:
            self._conf.save()
        except OSError:
            _log.warning("break setting could not be saved")
        self.sync_from_conf()

    # ---- screenshot cooperation --------------------------------------------------

    def hide_for_capture(self):
        """Park the window for a capture; True when it was visible.

        The hold stays until ``restore_after_capture``: meanwhile ticks,
        phase transitions and settings resyncs must not re-show it.
        """
        if self.engine.phase == BreakPhase.OFF:
            return False
        was = self.window.isVisible()
        self._capture_hold = True
        if was:
            self.window.hide()
        return was

    def restore_after_capture(self, was_visible):
        self._capture_hold = False
        # The central visibility rule decides: a visible phase re-shows
        # (even one reached mid-capture), everything else — including a
        # feature disabled mid-capture — stays hidden.
        self._push_phase_to_window()

    # ---- power / lock --------------------------------------------------------------

    def _hold(self, kind):
        """Freeze the countdown for one reason (lock or sleep).

        The engine resumes only once every hold is released, so a system
        wake while the screen is still locked never restarts the counter.
        A manual pause stays paused: the engine simply refuses the resume.
        """
        if not self._holds:
            self._suspended = True
            if self.engine.on_suspend():
                self._announce()
            else:
                self._push_phase_to_window()
        self._holds.add(kind)

    def _release(self, kind):
        self._holds.discard(kind)
        if not self._holds:
            self._suspended = False
            if self.engine.on_resume():
                self._announce()
            else:
                self._push_phase_to_window()

    def _install_power_filter(self):
        if os.name != "nt":
            return
        try:
            app = QApplication.instance()
            if app is None:
                return
            self._power_filter = _PowerFilter(self._hold, self._release)
            app.installNativeEventFilter(self._power_filter)
            self._register_session_notification(True)
        except Exception:
            _log.exception("break power listener could not start")
            self._power_filter = None

    def _register_session_notification(self, register):
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = int(self.window.winId())
            wts32 = ctypes.WinDLL("wtsapi32")
            if register:
                ok = wts32.WTSRegisterSessionNotification(
                    wintypes.HWND(hwnd), wintypes.DWORD(0))
                self._wts_registered = bool(ok)
            elif self._wts_registered:
                wts32.WTSUnRegisterSessionNotification(wintypes.HWND(hwnd))
                self._wts_registered = False
        except Exception:
            _log.exception("session notification registration failed")

    def _on_suspend(self):
        self._hold("sleep")

    def _on_resume(self):
        self._release("sleep")

    def retranslate(self):
        self.window.retranslate()

    # ---- teardown --------------------------------------------------------------------

    def shutdown(self):
        try:
            self._waker.stop()
        except RuntimeError:
            pass
        self._holds.clear()
        self._suspended = False
        self._capture_hold = False
        try:
            app = QApplication.instance()
            if app is not None and self._power_filter is not None:
                app.removeNativeEventFilter(self._power_filter)
        except Exception:
            _log.exception("break power listener could not stop")
        self._power_filter = None
        try:
            self._register_session_notification(False)
        except Exception:
            pass
        try:
            self.window.hide()
        except RuntimeError:
            pass
