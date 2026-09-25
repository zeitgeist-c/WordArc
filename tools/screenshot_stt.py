"""Grab the Speech to text card, both engines, in the real theme.

The point of the picture is the state a user has never seen: the local engine
chosen with nothing downloaded yet. A screenshot is the only way to tell that
the row reads as a fact rather than as an error.
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The real platform plugin, not offscreen: offscreen has no font database, so
# every label renders as an empty box and the picture verifies nothing but
# geometry. The window is told not to show, so nothing flashes on the desktop.
os.environ.pop("QT_QPA_PLATFORM", None)

import pathlib  # noqa: E402
import tempfile  # noqa: E402

import config as cfg  # noqa: E402
import localspeech  # noqa: E402
import settings_ui  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                   else r"C:\Users\user\AppData\Local\hermes\cache\scratch\wa-bench")


def grab(window, app, name, scroller=None, value=0):
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    app.processEvents()
    if scroller is not None:
        # The card lives inside a scroller, so a grab only shows it once it is
        # on screen. Scroll to a fraction of the way down, where the speech to
        # text card sits under the API keys card.
        bar = scroller.verticalScrollBar()
        bar.setValue(int(bar.maximum() * value))
        app.processEvents()
    window.grab().save(str(OUT / f"{name}.png"))
    print(f"wrote {OUT / name}.png", flush=True)


def main():
    app = QApplication.instance() or QApplication([])
    tmp = tempfile.TemporaryDirectory()
    root = pathlib.Path(tmp.name)
    with mock.patch.object(cfg, "CONFIG_DIR", root / "cfg"), \
         mock.patch.object(cfg, "CONFIG_FILE", root / "cfg" / "config.json"), \
         mock.patch.object(cfg, "DATA_DIR", root / "data"), \
         mock.patch.object(cfg, "HISTORY_FILE", root / "data" / "history.jsonl"), \
         mock.patch.object(cfg, "MEETINGS_DIR", root / "data" / "m"), \
         mock.patch.object(cfg, "MEETINGS_FILE", root / "data" / "m.jsonl"), \
         mock.patch.object(cfg.credential_store, "read", return_value=""), \
         mock.patch.object(cfg.credential_store, "read_all", return_value=[]), \
         mock.patch.object(cfg.credential_store, "write_all"), \
         mock.patch.object(settings_ui.audio, "list_sources", return_value=[]), \
         mock.patch.object(settings_ui.audio, "refresh_devices"), \
         mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]), \
         mock.patch.object(settings_ui.startup, "is_enabled", return_value=False), \
         mock.patch.object(localspeech, "models_dir",
                           return_value=pathlib.Path(tempfile.gettempdir()) / "wa-nothing"):
        conf = cfg.Config()
        window = settings_ui.SettingsWindow(conf, "wordarc toggle")
        window.resize(980, 820)
        window.navigate_to("settings")
        app.processEvents()
        scroller = window.tabs.widget(3).findChild(settings_ui.QScrollArea)
        grab(window, app, "stt-cloud", scroller, 0.22)

        window.transcribe_engine.setCurrentIndex(
            window.transcribe_engine.findData("local"))
        app.processEvents()
        grab(window, app, "stt-local-empty", scroller, 0.22)

        # And with a model on disk, so both states of the same row are seen.
        models = pathlib.Path(tempfile.mkdtemp()) / "whisper"
        root_dir = localspeech._root("large-v3-turbo", str(models))
        os.makedirs(root_dir, exist_ok=True)
        # A megabyte of filler, so the size on screen looks like a model rather
        # than like the stub files the unit tests use.
        for part in localspeech.REQUIRED_FILES:
            with open(os.path.join(root_dir, part), "wb") as fh:
                fh.write(b"x" * (1_048_576 if part == "model.bin" else 4096))
        with mock.patch.object(localspeech, "models_dir", return_value=models):
            window._refresh_local_controls()
            app.processEvents()
            grab(window, app, "stt-local-installed", scroller, 0.22)
        window.close()
    tmp.cleanup()
    print("done", flush=True)


if __name__ == "__main__":
    main()
