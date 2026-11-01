"""The chime survives temp cleaners: it plays from a persistent cache copy."""
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import asset_cache
import config
import sounds

import pytest


def _isolated(monkeypatch):
    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setattr(config, "DATA_DIR", Path(tmp.name) / "data")
    monkeypatch.setenv("QT_QPA_PLATFORM", "")
    return tmp


def _cache_file():
    return config.DATA_DIR / ".asset-cache" / "assets" / "sounds" / sounds.SAVED


def test_first_play_caches_the_bundle_copy(monkeypatch):
    tmp = _isolated(monkeypatch)
    try:
        path = sounds.sound_path(sounds.SAVED)
        assert path == _cache_file()
        assert path.is_file()
        bundled = Path(sounds.__file__).resolve().parent / "assets" / "sounds" / sounds.SAVED
        assert path.read_bytes() == bundled.read_bytes()
    finally:
        tmp.cleanup()


def test_stale_cache_is_used_when_the_bundle_is_gone(monkeypatch):
    tmp = _isolated(monkeypatch)
    try:
        cached = (asset_cache.cache_dir() / "assets" / "sounds" / "old.wav")
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
        assert Path(played) == _cache_file()
    finally:
        tmp.cleanup()


def test_translator_falls_back_to_cache_when_bundle_is_wiped(monkeypatch):
    import shutil
    from PyQt6.QtWidgets import QApplication
    import settings_ui
    tmp = _isolated(monkeypatch)
    try:
        real_qm = (Path(sys.modules["PyQt6"].__file__).resolve().parent
                   / "Qt6" / "translations" / "qtbase_tr.qm")
        if not real_qm.is_file():
            pytest.skip("no Qt catalogue in this environment")
        bundle = Path(tmp.name) / "bundle" / "PyQt6" / "Qt6" / "translations"
        bundle.mkdir(parents=True)
        shutil.copy2(real_qm, bundle / "qtbase_tr.qm")
        monkeypatch.setattr(sys, "_MEIPASS", str(Path(tmp.name) / "bundle"),
                            raising=False)
        app = QApplication.instance() or QApplication([])
        assert settings_ui.install_qt_translator(app, "tr") is True
        cached = (config.DATA_DIR / ".asset-cache" / "PyQt6" / "Qt6"
                  / "translations" / "qtbase_tr.qm")
        assert cached.is_file()
        shutil.rmtree(Path(tmp.name) / "bundle")
        assert settings_ui.install_qt_translator(app, "tr") is True
    finally:
        tmp.cleanup()
