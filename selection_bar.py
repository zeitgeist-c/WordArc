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
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QPushButton, QTextEdit,
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
    for _ in range(8):
        if element is None:
            return None
        try:
            if element.GetPropertyValue(_IS_PASSWORD):
                return None
        except Exception:
            return None
        try:
            pattern = element.GetTextPattern()
        except Exception:
            return None
        if pattern is not None:
            break
        try:
            element = element.GetParentControl()
        except Exception:
            return None
    else:
        return None
    try:
        ranges = pattern.GetSelection()
    except Exception:
        return None
    for rng in ranges or ():
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
        rect = _union(rects)
        if rect is None:
            try:
                bounds = focused.BoundingRectangle
                rect = QRect(bounds.left, bounds.top,
                             bounds.right - bounds.left,
                             bounds.bottom - bounds.top)
            except Exception:
                continue
            if rect.isNull():
                continue
        return Selection(text=text, rect=rect, pid=int(pid or 0), hwnd=hwnd)
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
    """Small readable window for one AI answer.

    The clipboard is written only when the user presses Copy: showing the
    window never touches it.
    """

    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self._text = str(text or "")
        self.setWindowTitle(title)
        self.setMinimumSize(380, 220)
        layout = QVBoxLayout(self)
        view = QTextEdit(self)
        view.setReadOnly(True)
        view.setPlainText(self._text)
        view.setAccessibleName(title)
        layout.addWidget(view)
        row = QHBoxLayout()
        row.addStretch(1)
        self.copy_button = QPushButton(t("Copy"), self)
        self.copy_button.setDefault(True)
        self.copy_button.clicked.connect(self._copy)
        row.addWidget(self.copy_button)
        close_button = QPushButton(t("Close"), self)
        close_button.clicked.connect(self.reject)
        row.addWidget(close_button)
        layout.addLayout(row)

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
               ("translate", "Translate to Turkish"),
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
        self.hide()

    def show_for(self, selection: Selection):
        self._text = selection.text
        self._place(selection.rect)
        self.show()

    def refresh(self, selection: Selection):
        """Follow a changed selection; the caller re-arms any pending action."""
        self._text = selection.text
        self._place(selection.rect)
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

    def _place(self, rect: QRect):
        self.adjustSize()
        size = self.sizeHint()
        screen = QGuiApplication.screenAt(rect.center())
        area = (screen.availableGeometry() if screen is not None
                else QGuiApplication.primaryScreen().availableGeometry())
        x = min(max(rect.left(), area.left()),
                max(area.right() - size.width(), area.left()))
        y = rect.top() - 8 - size.height()
        if y < area.top():
            y = rect.bottom() + 8
            if y + size.height() > area.bottom():
                y = max(area.top(), area.bottom() - size.height())
        self.move(x, max(y, area.top()))


class SelectionBarController(QObject):
    """Polls the selection, owns the bar, runs the AI actions in background."""

    failed = pyqtSignal(str)
    result_ready = pyqtSignal(str, str)

    PROMPTS = {"translate": (SELECTION_TRANSLATE_PROMPT, "Translate to Turkish"),
               "explain": (SELECTION_EXPLAIN_PROMPT, "Explain"),
               "summarize": (SELECTION_SUMMARIZE_PROMPT, "Summarize")}

    def __init__(self, conf, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.bar = SelectionBar()
        self.bar.copy_requested.connect(self._on_copy)
        self.bar.action_requested.connect(self._on_action)
        self.bar.dismissed.connect(self._on_bar_dismissed)
        self._enabled = False
        self._current: Selection | None = None
        self._gen = 0
        self._polling = False
        self._working = False
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
            self._hide()
            return
        if (not _match(self._current, selection)):
            self._current = selection
            self.bar.refresh(selection)
            self._watch_escape(True)

    # ---- actions --------------------------------------------------------
    # Every button verifies the live selection AND its source window before
    # acting: the worker re-reads, and the answer only lands when the fresh
    # read still matches what the bar shows (text, process and window).

    def _hide(self):
        self._current = None
        self._gen += 1
        self.bar.hide_bar()
        self._watch_escape(False)

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
            log.info("dropping late selection result (%s)", kind)
        elif kind == "stale":
            self._apply_stale(payload)
        elif kind == "fail":
            self.failed.emit(payload)
        elif kind == "done":
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
            self._current = fresh
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
