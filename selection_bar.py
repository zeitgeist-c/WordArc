"""Windows text-selection toolbar: copy, translate, explain, summarise.

When the user selects text in an app that exposes it through UI Automation
TextPattern, a small toolbar appears next to the selection with four buttons.
Copy writes straight to the clipboard (offline); the three AI actions send
only the selected text to Gemini and show the answer in a small window whose
own Copy button is the only path to the clipboard.

The selection is read, never synthesised: no Ctrl+C is ever sent to detect
it. The toolbar never takes focus, so the source app keeps its selection.
Password fields, empty selections and apps without TextPattern are skipped
quietly.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import threading

from PyQt6.QtCore import QObject, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QIcon, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit,
                             QToolButton, QVBoxLayout, QWidget)

import api
from config import (SELECTION_EXPLAIN_PROMPT, SELECTION_SUMMARIZE_PROMPT,
                    SELECTION_TRANSLATE_PROMPT)
from i18n import t

log = logging.getLogger("wordarc.selection_bar")

POLL_MS = 300
MAX_CHARS = 12000

# UIA property ids (stable ABI, no typelib import needed).
_IS_PASSWORD = 30019
_PROCESS_ID = 30002
# UIA_TextPatternId: the pattern a readable, selectable text surface offers.
_TEXT_PATTERN_ID = 10014

# Our own process: never offer the bar on our own windows.
_own_pid = os.getpid()

# Lazily imported: machines without the package (or the frozen build before
# its hiddenimport lands) simply never show the bar.
_uia = None
_uia_failed = False


def _backend():
    """The uiautomation package, or None when it cannot be used here."""
    global _uia, _uia_failed
    if _uia is None and not _uia_failed:
        try:
            import uiautomation as module
            _uia = module
        except ImportError as exc:
            _uia_failed = True
            log.info("text selection bar unavailable: %s", exc)
    return None if _uia_failed else _uia


@dataclass
class Selection:
    text: str
    rect: QRect
    pid: int
    hwnd: int = 0
    # One QRect per selected line, in physical pixels; picks the row the
    # bar anchors to. Empty when the engine reported no line geometry.
    lines: tuple = ()
    # Mouse-up point (mouse selection) or caret (keyboard selection), in
    # physical pixels; None when neither is known.
    anchor: QPoint | None = None


def _match(a: Selection | None, b: Selection | None) -> bool:
    """Whether two reads are the same selection in the same window.

    A zero window handle means the host did not provide one: fall back to
    the process id rather than refusing a good read.
    """
    if a is None or b is None:
        return False
    if a.text != b.text or a.pid != b.pid:
        return False
    if a.hwnd and b.hwnd and a.hwnd != b.hwnd:
        return False
    return True


def _text_pattern(element):
    """The element's TextPattern, or None when it offers none.

    The backend raises nothing here: ``GetPattern`` answers None for an
    unsupported pattern, while a missing method (older backend) or a hung
    app raises, and both just mean "not this element".
    """
    try:
        get = element.GetPattern
    except Exception:
        return None
    try:
        return get(_TEXT_PATTERN_ID)
    except Exception:
        return None


def _is_password(element, strict: bool) -> bool | None:
    """True for a password field; None when the answer is unavailable.

    Strict (the focused element itself) refuses on doubt; ancestors only
    veto on a clear True, so one unreadable wrapper never kills the read.
    """
    try:
        if element.GetPropertyValue(_IS_PASSWORD):
            return True
    except Exception:
        return None if strict else False
    return False


def _cursor_pos() -> QPoint | None:
    """The mouse pointer in physical pixels, or None."""
    try:
        import ctypes
        point = ctypes.wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return None
        return QPoint(point.x, point.y)
    except Exception:
        return None


def _caret_raw():
    """Caret owner + client position from the foreground thread, or None.

    Thin WinAPI wrapper (seam for tests). GetCaretPos-style answers are
    client coordinates of the window that owns the caret, so callers must
    resolve them against that window, never as screen pixels.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class _ThreadInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD),
                        ("flags", wintypes.DWORD),
                        ("hwndActive", wintypes.HWND),
                        ("hwndFocus", wintypes.HWND),
                        ("hwndCapture", wintypes.HWND),
                        ("hwndMenuOwner", wintypes.HWND),
                        ("hwndMoveSize", wintypes.HWND),
                        ("hwndCaret", wintypes.HWND),
                        ("rcCaret", wintypes.RECT)]

        info = _ThreadInfo(ctypes.sizeof(_ThreadInfo), 0, 0, 0, 0, 0, 0, 0,
                           wintypes.RECT(0, 0, 0, 0))
        if not ctypes.windll.user32.GetGUIThreadInfo(0, ctypes.byref(info)):
            return None
        if not info.hwndCaret:
            return None
        caret = info.rcCaret
        cx = caret.left + (caret.right - caret.left) // 2
        cy = caret.top + (caret.bottom - caret.top) // 2
        return int(info.hwndCaret), QPoint(cx, cy)
    except Exception:
        return None


def _root_window(hwnd):
    """Top-level ancestor of a window handle, or 0. Thin seam for tests."""
    try:
        import ctypes
        root = ctypes.windll.user32.GetAncestor(int(hwnd), 2)
        return int(root or 0)
    except Exception:
        return 0


def _client_to_screen(hwnd, point):
    """Client QPoint -> screen QPoint via its own window. None on failure."""
    try:
        import ctypes
        pt = ctypes.wintypes.POINT(int(point.x()), int(point.y()))
        if not ctypes.windll.user32.ClientToScreen(int(hwnd),
                                                   ctypes.byref(pt)):
            return None
        return QPoint(int(pt.x), int(pt.y))
    except Exception:
        return None


def _window_frame(hwnd):
    """Top-level window frame in physical pixels, or None. Seam for tests."""
    try:
        import ctypes
        from ctypes import wintypes

        class _Rect(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

        rect = _Rect()
        if not ctypes.windll.user32.GetWindowRect(int(hwnd),
                                                  ctypes.byref(rect)):
            return None
        return QRect(int(rect.left), int(rect.top),
                     int(rect.right - rect.left),
                     int(rect.bottom - rect.top))
    except Exception:
        return None


def _caret_pos(source_hwnd=None):
    """The text caret in physical screen pixels, or None.

    The raw caret position is client coordinates of whatever window owns
    the caret, so it is only usable when ownership by the source window
    and an on-screen position can both be verified. Without a verifiable
    source window (or on any failure) this returns None and the caller
    falls back to the visible selection rows.
    """
    if not source_hwnd:
        return None
    raw = _caret_raw()
    if raw is None:
        return None
    caret_hwnd, client = raw
    try:
        if _root_window(caret_hwnd) != int(source_hwnd):
            return None
    except (TypeError, ValueError):
        return None
    screen = _client_to_screen(caret_hwnd, client)
    if screen is None:
        return None
    if screen.x() == 0 and screen.y() == 0:
        return None
    frame = _window_frame(int(source_hwnd))
    if frame is None or not frame.contains(screen):
        return None
    return screen


def _anchor_for(rect, hwnd=None):
    """Where the user let go: caret for keyboard, pointer for mouse.

    Only a point inside (or just around) the selection counts; anything
    else would anchor the bar to an unrelated spot. The caret is used
    only when it verifies against the source window; otherwise the
    visible selection row decides.
    """
    margin = max(4, rect.height() // 2)
    area = rect.adjusted(-margin, -margin, margin, margin)
    caret = _caret_pos(hwnd)
    if caret is not None and area.contains(caret):
        return caret
    cursor = _cursor_pos()
    if cursor is not None and area.contains(cursor):
        return cursor
    return None


def _line_rects(rects) -> tuple:
    out = []
    for rect in rects:
        try:
            left, top, right, bottom = (int(rect.left), int(rect.top),
                                        int(rect.right), int(rect.bottom))
        except (AttributeError, TypeError, ValueError):
            continue
        if right <= left or bottom <= top:
            continue
        out.append(QRect(left, top, right - left, bottom - top))
    return tuple(out)


def _union(rects) -> QRect | None:
    out = None
    for rect in rects:
        try:
            left, top, right, bottom = (int(rect.left), int(rect.top),
                                        int(rect.right), int(rect.bottom))
        except (AttributeError, TypeError, ValueError):
            continue
        if right <= left or bottom <= top:
            continue
        box = QRect(left, top, right - left, bottom - top)
        out = box if out is None else out.united(box)
    return out


def read_selection(get_focused=None) -> Selection | None:
    """The focused app's current text selection, or None.

    ``get_focused`` injects the focused control for tests; production passes
    nothing and reads the live focus. Every refusal (no backend, no focus,
    our own window, password field, no TextPattern, empty selection,
    unreadable app) is a quiet None — the bar simply stays hidden.
    """
    backend = _backend()
    if backend is None:
        return None
    try:
        focused = get_focused() if get_focused is not None else \
            backend.GetFocusedControl()
    except Exception:
        return None
    if focused is None:
        return None
    try:
        pid = focused.GetPropertyValue(_PROCESS_ID)
    except Exception:
        return None
    if pid == _own_pid:
        return None
    try:
        top = focused.GetTopLevelControl()
        handle = top.NativeWindowHandle if top is not None else 0
        hwnd = int(handle() if callable(handle) else (handle or 0))
    except Exception:
        hwnd = 0
    element = focused
    for level in range(12):
        if element is None:
            break
        if _is_password(element, strict=(level == 0)):
            return None
        pattern = _text_pattern(element)
        if pattern is not None:
            break
        try:
            element = element.GetParentControl()
        except Exception:
            element = None
    else:
        element = None
        pattern = None
    if pattern is not None:
        found = _read_ranges(pattern, int(pid or 0), hwnd)
        if found is not None:
            return found
    # Same foreground window, different focus: the selection may live in a
    # document the focused control's ancestors never reach (a toolbar button
    # holds focus while text stays selected in the pane). Scan the window
    # for the first non-empty, non-password selection instead of naming apps.
    return _read_window_selection(top, int(pid or 0), hwnd)


def _read_ranges(pattern, pid: int, hwnd: int) -> Selection | None:
    for rng in _safe_selection(pattern):
        try:
            text = rng.GetText(-1) or ""
        except Exception:
            continue
        if not text.strip():
            continue
        try:
            rects = rng.GetBoundingRectangles() or ()
        except Exception:
            rects = ()
        lines = _line_rects(rects)
        rect = _union(rects)
        if rect is None or rect.isNull():
            # No line geometry, no reliable position: stay hidden rather
            # than parking the bar on an unrelated spot.
            continue
        anchor = _anchor_for(rect, hwnd)
        return Selection(text=text, rect=rect, pid=pid, hwnd=hwnd,
                         lines=lines, anchor=anchor)
    return None


def _safe_selection(pattern):
    try:
        return pattern.GetSelection() or ()
    except Exception:
        return ()


def _read_window_selection(top, pid: int, hwnd: int) -> Selection | None:
    """First non-empty selection anywhere in the focused window.

    Bounded walk (depth and node caps) so a huge tree cannot stall the
    poll worker. Password fields and unreadable elements are skipped,
    never read. Only elements of this window are visited. The depth
    covers Chromium-style trees where the document sits ~10 levels
    under the top window (measured: reached after ~300 nodes in 0.2s).
    """
    if top is None:
        return None
    try:
        children = list(top.GetChildren() or ())
    except Exception:
        return None
    seen = 0
    stack = [(child, 0) for child in children]
    while stack and seen < 1500:
        element, depth = stack.pop(0)
        seen += 1
        if element is None:
            continue
        if _is_password(element, strict=False):
            continue
        pattern = _text_pattern(element)
        if pattern is not None:
            found = _read_ranges(pattern, pid, hwnd)
            if found is not None:
                return found
        if depth < 12:
            try:
                kids = list(element.GetChildren() or ())
            except Exception:
                continue
            stack.extend((kid, depth + 1) for kid in kids)
    return None


def _bar_icon(name, color="#e9edf5"):
    """Small vector glyphs matching the screenshot toolbar's look."""
    paths = {
        "copy": '<rect x="8" y="8" width="12" height="13" rx="2"/>'
                '<path d="M15 8V3H3v13h5"/>',
        "translate": '<circle cx="12" cy="12" r="8.5"/>'
                     '<path d="M3.5 12h17M12 3.5c3.2 3.6 3.2 13.4 0 17'
                     'M12 3.5c-3.2 3.6-3.2 13.4 0 17"/>',
        "explain": '<circle cx="12" cy="12" r="8.5"/>'
                   '<path d="M9.5 9.3a2.6 2.6 0 1 1 3.6 2.4c-.9.4-1.1 1-1.1 1.9"/>'
                   '<circle cx="12" cy="16.8" r=".4"/>',
        "summarize": '<path d="M4 6h16M4 10h16M4 14h10M4 18h7"/>',
    }
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
           f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
           f'{paths[name]}</svg>')
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(svg.encode())
    from PyQt6.QtGui import QPainter
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class SelectionResultDialog(QDialog):
    """Small readable window for one AI answer, parked by the selection.

    The clipboard is written only when the user presses Copy: showing the
    window never touches it. Copy sits on the left, Close on the right, both
    the same size; the width grows with the text while the height stays put.
    """

    MIN_WIDTH = 380
    MAX_WIDTH = 680
    HEIGHT = 250

    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self._text = str(text or "")
        self.setWindowTitle(title)
        self.setMinimumSize(self.MIN_WIDTH, 220)
        self.setStyleSheet("""
            SelectionResultDialog {
                background: #20242e;
            }
            QTextEdit {
                background: #262c38; color: #e9edf5;
                border: 1px solid #444b5c; border-radius: 8px;
                padding: 10px 12px;
                font-size: 14px;
            }
            QPushButton {
                background: #383f50; color: #e9edf5;
                border: 1px solid #59647b; border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #454d63; }
            QPushButton:default { border-color: #7c8aff; }
        """)
        layout = QVBoxLayout(self)
        self._view = QTextEdit(self)
        self._view.setReadOnly(True)
        self._view.setPlainText(self._text)
        self._view.setAccessibleName(title)
        layout.addWidget(self._view)
        row = QHBoxLayout()
        self.copy_button = QPushButton(t("Copy"), self)
        self.copy_button.setDefault(True)
        self.copy_button.clicked.connect(self._copy)
        row.addWidget(self.copy_button)
        row.addStretch(1)
        close_button = QPushButton(t("Close"), self)
        close_button.clicked.connect(self.reject)
        row.addWidget(close_button)
        layout.addLayout(row)
        self._match_button_sizes(self.copy_button, close_button)
        self._fit_width()

    @staticmethod
    def _match_button_sizes(first, second):
        """Both buttons the same size: the wider hint wins."""
        width = max(first.sizeHint().width(), second.sizeHint().width(),
                    110)
        first.setFixedWidth(width)
        second.setFixedWidth(width)

    def _fit_width(self):
        """Width follows the text; height stays the same."""
        metrics = self._view.fontMetrics()
        longest = 0
        for line in self._text.splitlines():
            advance = metrics.horizontalAdvance(line)
            if advance > longest:
                longest = advance
        width = min(max(longest + 70, self.MIN_WIDTH), self.MAX_WIDTH)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            width = min(width,
                        max(screen.availableGeometry().width() - 40,
                            self.MIN_WIDTH))
        self.resize(int(width), self.HEIGHT)

    def position_near(self, rect):
        """Park the window by the selection instead of the screen centre.

        ``rect`` is the physical-pixel selection frame; below the selection
        when there is room, otherwise above it, always inside the screen.
        A missing rect leaves the default position alone.
        """
        if rect is None:
            return
        logical = _to_logical(rect)
        screen = (QGuiApplication.screenAt(logical.center())
                  or QGuiApplication.primaryScreen())
        if screen is None:
            return
        area = screen.availableGeometry()
        width, height = self.width(), self.height()
        x = min(max(logical.left(), area.left()),
                max(area.right() - width, area.left()))
        y = logical.bottom() + 8
        if y + height > area.bottom():
            y = logical.top() - 8 - height
            if y < area.top():
                y = max(area.top(), area.bottom() - height)
        self.move(x, max(y, area.top()))

    def _copy(self):
        QGuiApplication.clipboard().setText(self._text)
        self.accept()


class SelectionBar(QWidget):
    """Four-button toolbar floating next to the selection.

    Never takes focus (the source app keeps focus and its selection), so it
    cannot receive key events; Escape is watched globally by the controller
    while the bar is visible.
    """

    copy_requested = pyqtSignal(str)
    action_requested = pyqtSignal(str, str)
    dismissed = pyqtSignal()

    ACTIONS = (("copy", "Copy"),
               ("translate", "Translate"),
               ("explain", "Explain"),
               ("summarize", "Summarize"))

    def __init__(self, parent=None):
        super().__init__(None, Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            SelectionBar {
                background: #20242e; border: 1px solid #444b5c;
                border-radius: 10px;
            }
            QToolButton {
                background: transparent; border: 1px solid transparent;
                border-radius: 6px; padding: 0; color: #e9edf5;
            }
            QToolButton:hover { background: #383f50; border-color: #59647b; }
            QToolButton:pressed { background: #63518a; }
            QToolTip { background: #20242e; color: #ffffff;
                       border: 1px solid #59647b; }
        """)
        self._text = ""
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(2)
        self.buttons = {}
        for kind, label in self.ACTIONS:
            button = QToolButton(self)
            button.setIcon(_bar_icon(kind))
            button.setIconSize(QSize(17, 17))
            button.setFixedSize(30, 30)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setToolTip(t(label))
            button.setAccessibleName(t(label))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if kind == "copy":
                button.clicked.connect(
                    lambda _checked=False: self.copy_requested.emit(self._text))
            else:
                button.clicked.connect(
                    lambda _checked=False, action=kind:
                    self.action_requested.emit(action, self._text))
            self.buttons[kind] = button
            row.addWidget(button)
        self._busy_label = QLabel(self)
        self._busy_label.setStyleSheet("color: #e9edf5; padding: 4px 8px;")
        self._busy_label.hide()
        row.addWidget(self._busy_label)
        self.hide()

    def show_busy(self, message):
        """Swap the buttons for a waiting line while the AI answers."""
        for button in self.buttons.values():
            button.hide()
        self._busy_label.setText(message)
        self._busy_label.show()
        self.adjustSize()
        if not self.isVisible():
            self.show()

    def show_idle(self):
        """Bring the buttons back; the bar keeps whatever visibility it has."""
        self._busy_label.hide()
        for button in self.buttons.values():
            button.show()

    def show_for(self, selection: Selection):
        self._text = selection.text
        self.show_idle()
        self._place(selection.rect, selection.lines, selection.anchor)
        self.show()

    def refresh(self, selection: Selection):
        """Follow a changed selection; the caller re-arms any pending action."""
        self._text = selection.text
        self.show_idle()
        self._place(selection.rect, selection.lines, selection.anchor)
        if not self.isVisible():
            self.show()

    def hide_bar(self):
        if self.isVisible():
            self.hide()
            self.dismissed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide_bar()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _place(self, rect: QRect, lines=(), anchor=None):
        self.adjustSize()
        size = self.sizeHint()
        logical = _to_logical(rect)
        rows = [_to_logical(line) for line in lines] or [logical]
        ref = self._anchor_row(rows, logical, anchor)
        screen = QGuiApplication.screenAt(ref.center())
        area = (screen.availableGeometry() if screen is not None
                else QGuiApplication.primaryScreen().availableGeometry())
        x = min(max(ref.left(), area.left()),
                max(area.right() - size.width(), area.left()))
        y = ref.top() - 8 - size.height()
        if y < area.top():
            y = ref.bottom() + 8
            if y + size.height() > area.bottom():
                y = max(area.top(), area.bottom() - size.height())
        self.move(x, max(y, area.top()))

    @staticmethod
    def _anchor_row(rows, fallback, anchor):
        """The visible row the bar attaches to.

        The row holding the release point (or the caret) when one is
        known, else the nearest row to it, else the selection top —
        so a multi-line selection opens the bar by the end the user
        acted on, never by a far edge.
        """
        if not rows:
            return fallback
        if anchor is not None:
            for row in rows:
                if row.contains(anchor):
                    return row
            return min(rows, key=lambda row: abs(
                anchor.y() - (row.y() + row.height() // 2)))
        return rows[0]


def _to_logical_on_screens(rect: QRect, screens) -> QRect:
    """Physical UIA pixels -> Qt logical pixels for the owning screen.

    ``screens`` is [(QRect geometry, float ratio)]. Windows reports UI
    Automation rectangles in physical pixels; Qt lays out in logical ones.
    The owning screen is the one whose physical frame holds the rect's
    centre; unknown layouts fall back to the first screen's scale.
    Qt keeps a monitor's origin fixed and only scales its size, so the
    conversion is origin-relative: logical = origin + (physical - origin)
    / scale. Dividing absolute coordinates by the scale is wrong on any
    monitor whose origin is not (0, 0).
    """
    if rect is None:
        return rect
    cx = rect.x() + rect.width() // 2
    cy = rect.y() + rect.height() // 2

    def convert(box, origin, scale):
        return QRect(int(round(origin.x() + (box.x() - origin.x()) / scale)),
                     int(round(origin.y() + (box.y() - origin.y()) / scale)),
                     max(0, int(round(box.width() / scale))),
                     max(0, int(round(box.height() / scale))))

    for geometry, ratio in screens:
        scale = ratio or 1.0
        origin = QPoint(int(geometry.x()), int(geometry.y()))
        size = QSize(int(round(geometry.width() * scale)),
                     int(round(geometry.height() * scale)))
        if QRect(origin, size).contains(QPoint(cx, cy)):
            return convert(rect, origin, scale)
    if screens:
        geometry, ratio = screens[0]
        return convert(rect, QPoint(int(geometry.x()), int(geometry.y())),
                       ratio or 1.0)
    return rect


def _to_logical(rect: QRect) -> QRect:
    screens = [(screen.geometry(), screen.devicePixelRatio())
               for screen in QGuiApplication.screens()]
    if not screens:
        primary = QGuiApplication.primaryScreen()
        if primary is not None:
            screens = [(primary.geometry(), primary.devicePixelRatio())]
    return _to_logical_on_screens(rect, screens)


class SelectionBarController(QObject):
    """Polls the selection, owns the bar, runs the AI actions in background."""

    failed = pyqtSignal(str)
    result_ready = pyqtSignal(str, str)
    # Fired on the GUI thread the moment an AI job leaves for the network,
    # so the owner can say "waiting" somewhere the bar itself cannot reach
    # (tray balloon). Carries the action kind: translate/explain/summarize.
    action_started = pyqtSignal(str)

    PROMPTS = {"translate": (SELECTION_TRANSLATE_PROMPT, "Translate to Turkish"),
               "explain": (SELECTION_EXPLAIN_PROMPT, "Explain"),
               "summarize": (SELECTION_SUMMARIZE_PROMPT, "Summarize")}

    # Waiting line shown in place of the buttons, per action. Built from the
    # existing button labels so no new translation entry is needed.
    BUSY_TITLES = {"translate": "Translate to Turkish",
                   "explain": "Explain", "summarize": "Summarize"}

    def __init__(self, conf, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.bar = SelectionBar()
        self.bar.copy_requested.connect(self._on_copy)
        self.bar.action_requested.connect(self._on_action)
        self.bar.dismissed.connect(self._on_bar_dismissed)
        self._enabled = False
        self._current: Selection | None = None
        # A selection the user already acted on: the bar stays hidden for it
        # until the selection changes or disappears, instead of popping back
        # up on the next poll while it is still selected.
        self._consumed: Selection | None = None
        self._gen = 0
        self._polling = False
        self._working = False
        # The selection frame a running job belongs to: the answer window
        # parks by it instead of the screen centre.
        self._last_rect = None
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._polled.connect(self._on_polled)
        self._settled.connect(self._on_settled)
        self._esc = None

    # ---- enable ---------------------------------------------------------

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        if self._enabled:
            if _backend() is None:
                log.info("selection bar enabled but UIA backend is missing")
            # A fresh start re-arms for whatever is selected right now.
            self._consumed = None
            self._timer.start()
        else:
            self._timer.stop()
            self._hide()

    def is_enabled(self):
        return self._enabled

    def shutdown(self):
        self._timer.stop()
        self._hide()

    # ---- polling --------------------------------------------------------

    _polled = pyqtSignal(object)

    def _poll(self):
        if self._polling or self._working or not self._enabled:
            return
        self._polling = True

        def work():
            try:
                found = read_selection()
            except Exception as exc:  # noqa: BLE001 - a hung app, skip it
                log.warning("selection read failed: %s", exc)
                found = None
            finally:
                self._polling = False
            # Cross-thread emit: Qt queues it onto the GUI thread.
            self._polled.emit(found)

        threading.Thread(target=work, daemon=True).start()

    def _on_polled(self, selection):
        if not self._enabled:
            self._hide()
            return
        if selection is None:
            self._consumed = None
            self._hide()
            return
        if self._consumed is not None and _match(self._consumed, selection):
            # Already acted on this exact selection: stay hidden until the
            # user selects something else or clears it.
            return
        self._consumed = None
        if not _match(self._current, selection):
            self._current = selection
            self.bar.refresh(selection)
            self._watch_escape(True)
        elif selection.rect != self._current.rect:
            # Same text, moved geometry: the user scrolled or moved the
            # window under a steady selection — follow it, do not hide.
            self._current = selection
            self.bar.refresh(selection)

    # ---- actions --------------------------------------------------------
    # Every button verifies the live selection AND its source window before
    # acting: the worker re-reads, and the answer only lands when the fresh
    # read still matches what the bar shows (text, process and window).

    def _hide(self):
        self._current = None
        self._gen += 1
        self.bar.show_idle()
        self.bar.hide_bar()
        self._watch_escape(False)

    def popup_rect(self):
        """The selection frame the last job was sent from (or None).

        Read by the owner after ``result_ready`` to park the answer window
        by the selection. A defensive copy: the worker thread never touches
        it, both ends run on the GUI thread.
        """
        return QRect(self._last_rect) if self._last_rect is not None else None

    def _on_bar_dismissed(self):
        self._hide()

    def _on_copy(self, text):
        self._on_button("copy", text)

    def _on_action(self, kind, text):
        self._on_button(kind, text)

    def _on_button(self, kind, text):
        if (kind not in ("copy",) + tuple(self.PROMPTS)
                or not text.strip()):
            self._hide()
            return
        if self._working:
            return
        self._working = True
        self._timer.stop()
        gen = self._gen
        shown = self._current
        if shown is not None:
            # The job is taken: stay where the bar is and say what is
            # happening instead of going quiet, and do not come back for
            # this selection. A plain hide keeps the generation intact so
            # the worker's answer is still accepted when it lands.
            self._consumed = shown
            self._last_rect = QRect(shown.rect)
            if kind != "copy":
                self.bar.show_busy(t(self.BUSY_TITLES[kind]) + "…")
                self.action_started.emit(kind)
            else:
                self.bar.hide()

        def work():
            try:
                fresh = read_selection()
            except Exception as exc:  # noqa: BLE001
                log.warning("selection re-read failed: %s", exc)
                fresh = None
            if fresh is None or not fresh.text.strip() \
                    or not _match(fresh, shown):
                self._settled.emit((
                    "stale", fresh if fresh is not None
                    and fresh.text.strip() else None, gen))
                return
            if kind == "copy":
                self._settled.emit(("copy-ok", fresh, gen))
                return
            if len(fresh.text) > MAX_CHARS:
                self._settled.emit(
                    ("fail", t("The selection is too long."), gen))
                return
            keys = (self.conf.gemini_keys()
                    if hasattr(self.conf, "gemini_keys") else [])
            model = str(self.conf.get("gemini_translate_model", "")
                        or "gemini-3.5-flash-lite")
            prompt, _title = self.PROMPTS[kind]
            try:
                client = api.GeminiClient(keys)
                answer = getattr(client, kind)(fresh.text, model, prompt)
            except api.ApiError as exc:
                self._settled.emit(("fail", str(exc), gen))
                return
            except Exception as exc:  # noqa: BLE001 - surfaced, not hidden
                log.warning("selection %s failed: %s", kind, exc)
                self._settled.emit(("fail", str(exc), gen))
                return
            log.info("selection %s answered (%d chars in)", kind,
                     len(fresh.text))
            self._settled.emit(("done", (kind, answer), gen))

        threading.Thread(target=work, daemon=True).start()

    _settled = pyqtSignal(tuple)

    def _on_settled(self, outcome):
        kind, payload, gen = outcome
        self._working = False
        if gen != self._gen:
            # Hidden or replaced while the worker ran: never act on the old.
            # Still restore the buttons so a later show starts clean.
            self._hide()
            log.info("dropping late selection result (%s)", kind)
        elif kind == "stale":
            self._apply_stale(payload)
        elif kind == "fail":
            self._hide()
            self.failed.emit(payload)
        elif kind == "done":
            self._hide()
            self.result_ready.emit(*payload)
        elif kind == "copy-ok":
            QGuiApplication.clipboard().setText(payload.text)
            self._hide()
        if self._enabled:
            self._timer.start()

    def _apply_stale(self, fresh):
        if self._current is None or fresh is None:
            # Dismissed meanwhile, or nothing left: stay hidden.
            self._hide()
        else:
            # The selection moved under us: follow it, do not answer the old.
            self._consumed = None
            self._current = fresh
            self.bar.show_idle()
            self.bar.refresh(fresh)

    # ---- escape ---------------------------------------------------------
    # The bar never has focus, so it cannot see Esc itself. While visible it
    # watches Esc through a global hotkey that only observes: Win32 still
    # delivers the keystroke to the focused app untouched — nothing is
    # swallowed, and the watch starts and stops together with the bar.

    def _watch_escape(self, active: bool):
        if active and self._esc is None:
            try:
                import hotkey
                watcher = hotkey.EvdevHotkey(self)
                watcher.triggered.connect(
                    lambda _name: self.bar.hide_bar())
                if watcher.start({"cancel": "Escape"}):
                    self._esc = watcher
                    return
            except Exception as exc:  # noqa: BLE001 - Esc simply will not work
                log.info("escape watcher unavailable: %s", exc)
        if not active and self._esc is not None:
            try:
                self._esc.stop()
            except Exception:  # noqa: BLE001 - best effort
                pass
            self._esc = None
