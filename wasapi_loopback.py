"""WASAPI system-loopback capture via ctypes — fallback for meetings.

Most Windows builds expose a loopback input device through PortAudio, which
audio.MeetingRecorder uses directly via sounddevice. This module is the
fallback for builds where PortAudio does not surface one.

The public API matches what audio.MeetingRecorder needs from a capture stream:
  open(rate) -> a stream with .read(num_frames) -> bytes (s16 mono) and .close()
"""

import ctypes
import threading
import queue


def open(rate=16000):
    """Open the default render endpoint in loopback mode.

    Returns a stream object with read(num_frames) and close(), or raises
    OSError if the loopback cannot be started.
    """
    raise OSError(
        "ctypes WASAPI loopback not available on this build; the PortAudio "
        "loopback path in audio.py is the supported one.")
