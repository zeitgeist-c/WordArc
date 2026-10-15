"""Hermes dikte tetikleyici — eski AutoHotkey yardımcısının karşılığı.

Eskiden ayrı çalışan ``hermes-dictate-hotkey.ahk`` şunu yapıyordu: genel bir
kısayol Hermes odakta değilken yakalanır, Hermes penceresi öne getirilir ve
Hermes'in kendi dikte açma/kapama tuşuna basılmış olurdu.

Bu modül aynı işi WordArc'ın içinden yapar; ayrı AutoHotkey kurulumuna gerek
kalmaz. WordArc'taki karşılığı ``hermes_shortcut`` ayarıdır (varsayılan
Alt+Space) ve Hermes'in kendi kısayolu da Alt+Space olmalıdır
(Hermes Ayarları → Klavye → "Start / stop dictation"). Başarıda ``""``,
aksilikte ``t()`` ile çevrilecek İngilizce kaynak metin döner.
"""

import ctypes
import ctypes.wintypes as w
import logging
import time

_log = logging.getLogger("wordarc.hermes")

OK = ""
NOT_OPEN = "Hermes is not open."
SEND_FAILED = "Could not press the Hermes dictation key."

VK_MENU = 0x12
VK_SPACE = 0x20
SW_RESTORE = 9
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT),
                ("pad", ctypes.c_ubyte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("u", _INPUT_UNION)]


def _exe_name(user32, hwnd):
    """Pencerenin işlem dosya adı; okunamazsa None (başlık eşleşmesine düşülür)."""
    try:
        pid = w.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return None
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = w.DWORD(260)
            psapi = ctypes.windll.psapi
            if psapi.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return (buf.value or "").split("\\")[-1]
            return None
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return None


def find_hermes_window(user32=None):
    """Görünür Hermes penceresini bul; yoksa None."""
    user32 = user32 or ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def _enum(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if not length:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if "hermes" not in (buf.value or "").lower():
                return True
            exe = _exe_name(user32, hwnd)
            if exe is not None and exe.lower() != "hermes.exe":
                return True
            found.append(hwnd)
        except Exception:
            _log.exception("could not inspect a window handle")
        return True

    try:
        user32.EnumWindows(_enum, 0)
    except Exception:
        _log.exception("could not enumerate windows")
        return None
    return found[0] if found else None


def _send_hermes_key(user32=None):
    """Hermes'in dikte kısayoluna bas (Alt+Space); gönderilen sayısı döner."""
    user32 = user32 or ctypes.windll.user32
    events = []
    for vk, up in ((VK_MENU, False), (VK_SPACE, False),
                   (VK_SPACE, True), (VK_MENU, True)):
        key = _KEYBDINPUT(wVk=vk, wScan=0,
                          dwFlags=KEYEVENTF_KEYUP if up else 0,
                          time=0, dwExtraInfo=None)
        union = _INPUT_UNION(ki=key)
        events.append(_INPUT(type=INPUT_KEYBOARD, u=union))
    array = (_INPUT * len(events))(*events)
    try:
        return user32.SendInput(len(events), array, ctypes.sizeof(_INPUT))
    except Exception:
        _log.exception("could not send Alt+Space")
        return 0


def trigger(user32=None, found=None, sender=None):
    """Hermes'i öne getirip diktesini aç/kapat.

    Başarıda ``OK`` (``""``), Hermes açık değilse ``NOT_OPEN``, tuş
    gönderilemezse ``SEND_FAILED`` döner.
    """
    user32 = user32 or ctypes.windll.user32
    hwnd = found if found is not None else find_hermes_window(user32)
    if hwnd is None:
        return NOT_OPEN
    send = sender or (lambda: _send_hermes_key(user32))
    try:
        try:
            user32.ShowWindow(hwnd, SW_RESTORE)
        except Exception:
            pass
        if not user32.SetForegroundWindow(hwnd):
            _log.warning("could not bring Hermes forward")
        time.sleep(0.2)
    except Exception:
        _log.exception("could not activate the Hermes window")
        return SEND_FAILED
    try:
        sent = send()
    except Exception:
        _log.exception("could not send the Hermes dictation key")
        return SEND_FAILED
    if sent != 4:
        _log.warning("Alt+Space partially sent (%r/4)", sent)
        return SEND_FAILED
    return OK
