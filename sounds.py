"""WordArc's own notification sounds, so Windows' stock beeps stay out of it.

A confirmation is easier to like than to hear: nothing here ever blocks the
caller, and a missing file is a log line rather than an error. The sounds ship
in ``assets/sounds`` as small 16-bit mono WAVs; ``winsound`` plays them without
pulling in a multimedia dependency.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil

from brand import BRAND, resource_path

_log = logging.getLogger("wordarc.sounds")

# Played when the settings have been written to disk.
SAVED = "settings-saved.wav"


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / BRAND.data_directory / "sounds"


def sound_path(name: str):
    """The playable path: a persistent copy, not the temp extraction.

    The frozen bundle extracts into %TEMP%/_MEI*, and temp cleaners delete
    from there while the app runs — the next chime then finds no file. A
    copy under %LOCALAPPDATA% survives that; it is refreshed from the
    bundle whenever the sizes disagree.
    """
    cached = _cache_dir() / name
    bundled = resource_path("assets", "sounds", name)
    try:
        if bundled.is_file() and (
                not cached.is_file()
                or cached.stat().st_size != bundled.stat().st_size):
            _cache_dir().mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled, cached)
            return cached
    except OSError as exc:
        _log.warning("sound cache refresh failed (%s)", exc)
    return cached if cached.is_file() else bundled


def play(name: str = SAVED) -> bool:
    """Play one of our own sounds asynchronously; True when it was started."""
    # The test and check runs are headless; a suite that beeps at the
    # developer is a suite that gets muted.
    if os.environ.get("QT_QPA_PLATFORM", "").startswith("offscreen"):
        return False
    path = sound_path(name)
    if not path.exists():
        _log.warning("sound file missing: %s", path)
        return False
    try:
        import winsound
    except ImportError:  # not Windows: the interface simply stays quiet
        return False
    try:
        winsound.PlaySound(
            str(path),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
        )
    except (OSError, RuntimeError) as exc:
        _log.warning("could not play %s (%s)", name, exc)
        return False
    return True
