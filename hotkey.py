"""Global shortcut via Win32 RegisterHotKey on a hidden window."""

import ctypes
import ctypes.wintypes as w
import logging

from PyQt6.QtCore import QObject, Qt, QCoreApplication, pyqtSignal
from PyQt6.QtWidgets import QWidget

from i18n import t

_log = logging.getLogger("wordarc.hotkey")

user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

KEYS = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "backspace": 0x08, "insert": 0x2D,
    "delete": 0x2E, "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
MODS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT, "menu": MOD_ALT,
    "super": MOD_WIN, "meta": MOD_WIN, "win": MOD_WIN,
}


def parse_shortcut(text):
    parts = [p.strip().lower() for p in str(text).split("+") if p.strip()]
    if not parts:
        return 0, 0
    mods, vk = 0, 0
    for part in parts:
        if part in MODS:
            mods |= MODS[part]
        elif part in KEYS:
            if vk:
                return 0, 0
            vk = KEYS[part]
        elif len(part) == 1 and part.isalpha():
            if vk:
                return 0, 0
            vk = ord(part.upper())
        elif len(part) == 1 and part.isdigit():
            if vk:
                return 0, 0
            vk = ord(part)
        else:
            return 0, 0
    if not vk:
        return 0, 0
    return mods | MOD_NOREPEAT, vk


class WindowsHotkey(QObject):
    triggered = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ids = {}
        self._widget = None
        self._next_id = 0xC000

    @property
    def running(self):
        return self._widget is not None

    def start(self, bindings):
        self.stop()
        registered = {}
        failed = []
        for name, shortcut in bindings.items():
            if not shortcut:
                continue
            mods, vk = parse_shortcut(shortcut)
            if not vk:
                failed.append(shortcut)
                continue
            registered[name] = (mods, vk, shortcut)
        if not registered:
            for sc in failed[:1]:
                self.failed.emit(t("Could not parse the shortcut: {shortcut}", shortcut=sc))
            return False
        QCoreApplication.processEvents()
        self._widget = _HotkeyWindow(self)
        success = 0
        for name, (mods, vk, sc) in registered.items():
            self._next_id += 1
            id_ = self._next_id
            if not user32.RegisterHotKey(self._widget.hwnd, id_, mods, vk):
                self.failed.emit(
                    t("Could not register the shortcut. Another program may already "
                      "be using it: {shortcut}", shortcut=sc))
                continue
            self._ids[id_] = name
            success += 1
        for sc in failed:
            self.failed.emit(t("Could not parse the shortcut: {shortcut}", shortcut=sc))
        if not success:
            self._widget.close()
            self._widget = None
        return bool(success)

    def stop(self):
        if self._widget is None:
            return
        for id_ in list(self._ids):
            user32.UnregisterHotKey(self._widget.hwnd, id_)
        self._widget.close()
        self._widget = None
        self._ids.clear()


EvdevHotkey = WindowsHotkey


class _HotkeyWindow(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setWindowFlags(Qt.WindowType.Widget)
        self.resize(0, 0)
        self.move(-10000, -10000)
        self.show()
        self.hide()
        self.hwnd = int(self.winId())

    def nativeEvent(self, event_type, message):
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(w.MSG)).contents
            if msg.message == WM_HOTKEY:
                id_ = msg.wParam
                name = self.owner._ids.get(id_)
                if name:
                    self.owner.triggered.emit(name)
                return True, 0
        except Exception:
            # A shortcut that stops arriving leaves the user with nothing to go
            # on: the reason goes to the log.
            _log.exception("could not handle a hotkey message")
        return False, 0
