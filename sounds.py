"""WordArc's own notification sounds, so Windows' stock beeps stay out of it.

A confirmation is easier to like than to hear: nothing here ever blocks the
caller, and a missing file is a log line rather than an error. The sounds ship
in ``assets/sounds`` as small 16-bit mono WAVs; ``winsound`` plays them without
pulling in a multimedia dependency.
"""

from __future__ import annotations

import logging
import os

from brand import resource_path

_log = logging.getLogger("wordarc.sounds")

# Played when the settings have been written to disk.
SAVED = "settings-saved.wav"


def sound_path(name: str):
    return resource_path("assets", "sounds", name)


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
