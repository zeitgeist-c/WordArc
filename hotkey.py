"""Global shortcut via Win32 RegisterHotKey on a hidden window."""

import ctypes
import ctypes.wintypes as w
import logging
import string
import sys

from PyQt6.QtCore import QObject, Qt, QCoreApplication, pyqtSignal
from PyQt6.QtWidgets import QWidget

from i18n import t

_log = logging.getLogger("wordarc.hotkey")

user32 = ctypes.windll.user32
user32.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
user32.RegisterHotKey.restype = w.BOOL
user32.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = w.BOOL

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

KEYS = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "backspace": 0x08, "insert": 0x2D,
    "ins": 0x2D, "del": 0x2E,
    "delete": 0x2E, "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "print": 0x2C, "printscreen": 0x2C, "prtsc": 0x2C, "snapshot": 0x2C,
    "pause": 0x13, "capslock": 0x14, "caps": 0x14,
    "numlock": 0x90, "scrolllock": 0x91,
    "volume mute": 0xAD, "volume down": 0xAE, "volume up": 0xAF,
    "media next": 0xB0, "media previous": 0xB1, "media stop": 0xB2,
    "media play": 0xB3, "media pause": 0xB3,
    "toggle media play/pause": 0xB3,
    "cancel": 0x03, "sysreq": 0x2C,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
KEYS.update({f"f{number}": 0x6F + number for number in range(13, 25)})
KEYS.update({f"num{number}": 0x60 + number for number in range(10)})
KEYS.update({"num*": 0x6A, "numplus": 0x6B, "num-": 0x6D,
             "num.": 0x6E, "num/": 0x6F})
MODS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT, "menu": MOD_ALT,
    "super": MOD_WIN, "meta": MOD_WIN, "win": MOD_WIN,
}


def _char_vk(char, mods):
    """Virtual-key code for a single printable character, per the layout.

    Letters outside ASCII (ı, ş, é …) and punctuation do not have a fixed
    virtual-key code: the keyboard layout decides. VkKeyScanW tells us both
    the code and the modifiers Windows needs for that character.
    """
    if sys.platform != "win32":
        return 0
    try:
        user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
        user32.VkKeyScanW.restype = ctypes.c_short
        result = user32.VkKeyScanW(char)
    except (AttributeError, OSError, TypeError, ValueError):
        return 0
    if result == -1:
        return 0
    needed = (result >> 8) & 0xFF
    if needed & 1 and not mods & MOD_SHIFT:
        return 0
    if needed & 2 and not mods & MOD_CONTROL:
        return 0
    if needed & 4 and not mods & MOD_ALT:
        return 0
    return result & 0xFF


def parse_shortcut(text):
    text = str(text).strip()
    # QKeySequence serializes the plus key as '+' (or 'Ctrl++').
    if text.endswith("+") and (text == "+" or text.endswith("++")):
        text = text[:-1] + "Plus"
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    if not parts:
        return 0, 0
    mods, vk, char = 0, 0, ""
    for part in parts:
        if part in MODS:
            mods |= MODS[part]
        elif part == "plus" and not char and not vk:
            char = "+"
        elif part in KEYS:
            if vk:
                return 0, 0
            vk = KEYS[part]
        elif len(part) == 1 and part in string.ascii_letters:
            if vk:
                return 0, 0
            vk = ord(part.upper())
        elif len(part) == 1 and part in string.digits:
            if vk:
                return 0, 0
            vk = ord(part)
        elif len(part) == 1 and not char:
            # Punctuation and non-ASCII letters: the layout resolves them.
            if vk:
                return 0, 0
            char = part
        else:
            return 0, 0
    if not vk and char:
        vk = _char_vk(char, mods)
    elif vk and char:
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
        self._next_id = 0

    @property
    def running(self):
        return self._widget is not None

    def start(self, bindings):
        self.stop()
        # Application IDs belong to 0x0000..0xBFFF, and can be reused once
        # unregistered. The old monotonic counter began in the atom range.
        self._next_id = 0
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
