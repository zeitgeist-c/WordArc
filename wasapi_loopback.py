"""Windows WASAPI loopback fallback backed by the SoundCard package.

sounddevice/PortAudio exposes loopback inputs on many machines.  On machines
where it does not, SoundCard talks to Windows Core Audio directly and supplies
the same mono int16 blocks MeetingRecorder expects.
"""

from __future__ import annotations

import threading


class LoopbackStream:
    def __init__(self, rate, callback, target="", blocksize=1024):
        try:
            import numpy as np
            import soundcard as sc
        except ImportError as exc:
            raise OSError("SoundCard WASAPI fallback is not installed") from exc
        self._np = np
        self._callback = callback
        self._blocksize = blocksize
        self._stop = threading.Event()
        speakers = sc.all_speakers()
        wanted = target.casefold().replace("(loopback)", "").strip()
        speaker = next((s for s in speakers if wanted and wanted in s.name.casefold()),
                       None)
        if wanted and speaker is None:
            raise OSError(f"Selected output device not found: {target}")
        speaker = speaker or sc.default_speaker()
        if speaker is None:
            raise OSError("No Windows output device is available")
        microphone = sc.get_microphone(speaker.id, include_loopback=True)
        self._recorder = microphone.recorder(
            samplerate=rate, channels=1, blocksize=blocksize)
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="wordarc-wasapi-loopback")
        self._thread.start()

    def _run(self):
        try:
            with self._recorder as recorder:
                while not self._stop.is_set():
                    frames = recorder.record(numframes=self._blocksize)
                    mono = self._np.asarray(frames).reshape(-1)
                    pcm = (self._np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2")
                    self._callback(pcm.tobytes())
        except Exception as exc:
            if not self._stop.is_set():
                self._callback(None, exc)

    def stop(self):
        self._stop.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=3)

    close = stop


def open(rate=16000, callback=None, target=""):
    if callback is None:
        raise OSError("A loopback callback is required")
    return LoopbackStream(rate, callback, target)
