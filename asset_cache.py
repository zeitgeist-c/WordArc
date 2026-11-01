"""Persistent copies of small bundled assets.

The frozen bundle extracts into %TEMP%/_MEI*, and temp cleaners delete from
there while the app runs. Anything read on demand afterwards — the save
chime, the update supervisor, Qt's own translation catalogue, the brand
icons — then silently stops working. A verified copy under %LOCALAPPDATA%
survives that; it is refreshed from the bundle whenever the sizes disagree.

Only for small files (sounds, catalogues, icons). Model weights, runtimes
and executables are versioned artifacts with their own channels, not cache.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

_log = logging.getLogger("wordarc.assets")


def cache_dir():
    import config
    return config.DATA_DIR / ".asset-cache"


def cached_asset(*parts: str) -> Path:
    """Usable path for a small bundled file, persistent across temp wipes."""
    from brand import resource_path
    bundled = resource_path(*parts)
    cached = cache_dir().joinpath(*parts)
    try:
        if bundled.is_file() and (
                not cached.is_file()
                or cached.stat().st_size != bundled.stat().st_size):
            cached.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled, cached)
            return cached
    except OSError as exc:
        _log.warning("asset cache refresh failed (%s)", exc)
    return cached if cached.is_file() else bundled


# Files every bundle ships: present at boot, gone later means a temp
# cleaner deleted the live extraction out from under the running app.
CANARY_PARTS = (
    ("assets", "brand", "wordarc.ico"),
    ("assets", "sounds", "settings-saved.wav"),
    ("helpers", "manifest.json"),
)
_canary = None


def bundle_intact() -> bool:
    """False when files present at boot vanished mid-run (temp wipe).

    Embedding more cannot fix that class: the wiped extraction kills every
    bundled module eventually. The honest answer is telling the user to
    restart so the bundle extracts fresh.
    """
    global _canary
    from brand import resource_path
    now = [resource_path(*parts).is_file() for parts in CANARY_PARTS]
    if _canary is None:
        _canary = now
        return True
    return all(is_now for was, is_now in zip(_canary, now) if was)
