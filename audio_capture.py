"""Qt-independent audio device and Windows loopback service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioCapture:
    """Open Core Audio loopback streams without exposing UI dependencies."""

    rate: int = 16000
    blocksize: int = 1024

    def open_loopback(self, callback, target=""):
        import wasapi_loopback
        return wasapi_loopback.open(self.rate, callback, target)

    @staticmethod
    def output_devices():
        """Return stable ``(id, label)`` pairs reported by Windows Core Audio."""
        try:
            import soundcard as sc
            return [(speaker.name, speaker.name) for speaker in sc.all_speakers()]
        except Exception:
            return []

    @staticmethod
    def default_output():
        try:
            import soundcard as sc
            speaker = sc.default_speaker()
            return speaker.name if speaker else ""
        except Exception:
            return ""
