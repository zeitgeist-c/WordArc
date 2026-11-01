"""The chime survives temp cleaners: it plays from a persistent cache copy."""
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import sounds


def _isolated(monkeypatch):
    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setenv("LOCALAPPDATA", str(Path(tmp.name)))
    monkeypatch.setenv("QT_QPA_PLATFORM", "")
    return tmp


def test_first_play_caches_the_bundle_copy(monkeypatch):
    tmp = _isolated(monkeypatch)
    try:
        path = sounds.sound_path(sounds.SAVED)
        assert path.parent == sounds._cache_dir()
        assert path.is_file()
        bundled = Path(sounds.__file__).resolve().parent / "assets" / "sounds" / sounds.SAVED
        assert path.read_bytes() == bundled.read_bytes()
    finally:
        tmp.cleanup()


def test_stale_cache_is_used_when_the_bundle_is_gone(monkeypatch):
    tmp = _isolated(monkeypatch)
    try:
        cached = sounds._cache_dir() / "old.wav"
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(b"stale")
        assert sounds.sound_path("old.wav") == cached
    finally:
        tmp.cleanup()


def test_play_warns_and_stays_quiet_when_nothing_exists(monkeypatch):
    tmp = _isolated(monkeypatch)
    fake = mock.MagicMock()
    fake.SND_FILENAME = 1
    fake.SND_ASYNC = 2
    fake.SND_NODEFAULT = 4
    monkeypatch.setitem(sys.modules, "winsound", fake)
    try:
        assert sounds.play("no-such-sound.wav") is False
        fake.PlaySound.assert_not_called()
    finally:
        tmp.cleanup()


def test_play_goes_through_the_cached_copy(monkeypatch):
    tmp = _isolated(monkeypatch)
    fake = mock.MagicMock()
    fake.SND_FILENAME = 1
    fake.SND_ASYNC = 2
    fake.SND_NODEFAULT = 4
    monkeypatch.setitem(sys.modules, "winsound", fake)
    try:
        assert sounds.play() is True
        played = fake.PlaySound.call_args.args[0]
        assert Path(played).parent == sounds._cache_dir()
    finally:
        tmp.cleanup()
