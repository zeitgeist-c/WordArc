"""Resolve the ffmpeg executable: bundled with the frozen .exe, else PATH."""
import os
import shutil
import sys


def ffmpeg():
    """Path to ffmpeg, or raise."""
    if hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, "ffmpeg.exe")
        if os.path.isfile(bundled):
            return bundled
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise FileNotFoundError("ffmpeg not found")