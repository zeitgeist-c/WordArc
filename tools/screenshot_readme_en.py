"""English README screenshots for WordArc (1950x1400, light/dark).

Fresh-profile captures: a temp config dir, no real microphones, an empty
credential store. Nothing personal ever reaches the images.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("QT_QPA_PLATFORM", None)

import config as cfg  # noqa: E402
import settings_ui  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"

SHOTS = [
    # (file, page id, settings section, theme)
    ("01-dictation.png", "dictation", None, "light"),
    ("02-meeting.png", "meeting", None, "light"),
    ("03-audio-file.png", "audio_file", None, "light"),
    ("04-speak.png", "speak", None, "light"),
    ("05-screenshot.png", "screenshot", None, "light"),
    ("06-settings.png", "settings", None, "light"),
    ("07-dictation-dark.png", "dictation", None, "dark"),
    ("08-meeting-dark.png", "meeting", None, "dark"),
    ("09-api-keys.png", "settings", "api_keys", "dark"),
]


def shoot(which=None):
    app = QApplication.instance() or QApplication([])
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    with mock.patch.object(cfg, "CONFIG_DIR", root / "cfg"), \
         mock.patch.object(cfg, "CONFIG_FILE", root / "cfg" / "config.json"), \
         mock.patch.object(cfg, "DATA_DIR", root / "data"), \
         mock.patch.object(cfg, "MEETINGS_FILE", root / "data" / "meetings.jsonl"), \
         mock.patch.object(cfg, "MEETINGS_DIR", root / "data" / "meetings"), \
         mock.patch.object(cfg, "HISTORY_FILE", root / "data" / "history.jsonl"), \
         mock.patch.object(cfg, "RECORDINGS_DIR", root / "data" / "recordings"), \
         mock.patch.object(cfg.credential_store, "read_all", return_value=[]), \
         mock.patch.object(settings_ui.audio, "list_sources", return_value=[]), \
         mock.patch.object(settings_ui.audio, "refresh_devices"), \
         mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]), \
         mock.patch.object(settings_ui.startup, "is_enabled", return_value=True), \
         mock.patch.object(settings_ui.startup, "set_enabled"):
        conf = cfg.Config()
        conf["ui_language"] = "en"
        import i18n
        import theme
        i18n.set_language("en")
        for name, page, section, theme_name in SHOTS:
            if which and name != which:
                continue
            conf["theme_mode"] = theme_name
            theme.ThemeManager.apply(theme_name, app)
            window = settings_ui.SettingsWindow(conf, "wordarc toggle")
            window.resize(1950, 1400)
            window.navigate_to(page, section)
            window.setAttribute(
                __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            window.show()
            app.processEvents()
            window.grab().save(str(OUT / name))
            print(f"wrote {name}", flush=True)
            window.close()
            app.processEvents()


if __name__ == "__main__":
    shoot(sys.argv[1] if len(sys.argv) > 1 else None)
