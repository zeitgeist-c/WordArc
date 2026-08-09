"""Manage WordArc's per-user Windows startup registration."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from brand import BRAND

try:
    import winreg
except ImportError:  # pragma: no cover - Windows is the supported platform
    winreg = None


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class StartupError(OSError):
    pass


def launch_command() -> str:
    """Return a quoted command suitable for the HKCU Run registry value."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}" background'
    executable = Path(sys.executable).resolve()
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.exists():
        executable = pythonw
    entrypoint = Path(__file__).resolve().with_name("wordarc.py")
    return f'"{executable}" "{entrypoint}" background'


def ensure_current_command() -> bool:
    """Upgrade an existing enabled Run entry without enabling a disabled one."""
    if os.name != "nt" or winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            current, _kind = winreg.QueryValueEx(key, BRAND.name)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StartupError("Windows startup setting could not be read") from exc
    expected = launch_command()
    if str(current).strip() != expected:
        set_enabled(True, expected)
    return True


def is_enabled() -> bool:
    if os.name != "nt" or winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, BRAND.name)
            return bool(str(value).strip())
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StartupError("Windows startup setting could not be read") from exc


def set_enabled(enabled: bool, command: str | None = None) -> None:
    if os.name != "nt" or winreg is None:
        raise StartupError("Windows startup settings are unavailable")
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, BRAND.name, 0, winreg.REG_SZ, command or launch_command()
                )
            else:
                try:
                    winreg.DeleteValue(key, BRAND.name)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        raise StartupError("Windows startup setting could not be changed") from exc
