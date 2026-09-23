"""Clipboard and key injection through Win32 (ctypes, no third-party libs)."""

import ctypes
import ctypes.wintypes as w
import time

from i18n import t

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = w.BOOL
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.restype = ctypes.c_void_p
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [w.UINT, ctypes.c_void_p]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = [w.UINT]
user32.OpenClipboard.restype = w.BOOL
user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.EmptyClipboard.restype = w.BOOL
user32.CloseClipboard.restype = w.BOOL

# Virtual-key codes for the names that appear in paste shortcuts.
VKEYS = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
    "menu": 0x12, "super": 0x5B, "meta": 0x5B, "win": 0x5B,
    "v": 0x56, "insert": 0x2D, "enter": 0x0D, "return": 0x0D,
}


class PasteError(Exception):
    pass


def read_clipboard():
    """bytes | None; None if the clipboard is empty or unavailable."""
    if not user32.OpenClipboard(0):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            text = ctypes.cast(ptr, ctypes.c_wchar_p).value
            return text.encode("utf-8") if text is not None else None
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def copy(text):
    """Put UTF-16 text on the clipboard; PasteError on failure."""
    data = (text + "\0").encode("utf-16-le")
    if not user32.OpenClipboard(0):
        raise PasteError(t("Could not open the clipboard."))
    try:
        if not user32.EmptyClipboard():
            raise PasteError(t("Could not copy to the clipboard."))
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise PasteError(t("Could not copy to the clipboard."))
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            raise PasteError(t("Could not copy to the clipboard."))
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise PasteError(t("Could not copy to the clipboard."))
    finally:
        user32.CloseClipboard()


def copy_bytes(data):
    """Best-effort restore of raw previous clipboard bytes; swallows errors."""
    if data is None:
        return
    if not user32.OpenClipboard(0):
        return
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data) + 2)
        if not handle:
            return
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return
        # Treat as a string sent in via copy earlier: simplest correct case is
        # to re-copy the UTF-8 bytes as UTF-16 text when they were text. We keep
        # the prior bytes only when they decode as UTF-8 (the common case).
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(handle)
            user32.SetClipboardData(CF_UNICODETEXT, handle)
            return
        payload = (text + "\0").encode("utf-16-le")
        kernel32.GlobalUnlock(handle)
        kernel32.GlobalFree(handle)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(CF_UNICODETEXT, handle)
    except Exception:
        pass
    finally:
        user32.CloseClipboard()


def press(shortcut="ctrl+v", delay=0.12):
    """Send a key combination via SendInput. Raises PasteError on bad key."""
    codes = []
    for key in (k.strip().lower() for k in shortcut.split("+")):
        code = VKEYS.get(key)
        if code is None:
            raise PasteError(t("Unknown key: {key}", key=key))
        codes.append(code)

    time.sleep(delay)  # let focus settle, as on Linux

    inputs = []
    for code in codes:        # key down for each
        inputs.append(_keyinput(code, 0))
    for code in reversed(codes):  # key up in reverse
        inputs.append(_keyinput(code, 0x0002))  # KEYEVENTF_KEYUP

    n = len(inputs)
    arr_type = _INPUT * n
    arr = arr_type(*inputs)
    sent = user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(_INPUT))
    if sent != n:
        raise PasteError(t("Could not send the paste keystroke."))


# --- SendInput structure plumbing -----------------------------------------

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]

class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", w.DWORD), ("u", _INPUT_UNION)]


def _keyinput(vk, flags):
    inp = _INPUT()
    inp.type = 1  # INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.wScan = 0
    inp.ki.dwFlags = flags
    inp.ki.time = 0
    inp.ki.dwExtraInfo = 0
    return inp