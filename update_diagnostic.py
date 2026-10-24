"""Opt-in frozen updater acceptance: real Qt signals/labels, no user state."""
import argparse
import json
from pathlib import Path
import ssl
import sys
import time


def run(argv):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QProgressBar
    from brand import BRAND
    from settings_ui import SettingsWindow
    import update
    from wordarc import WordArc

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication([])

    class TransientState(dict):
        def save(self):
            pass

    class UpdatePanel(QWidget):
        show_update_current = SettingsWindow.show_update_current
        def __init__(self, conf):
            super().__init__()
            self.conf = conf
            self._update_info = None
            self.state = "idle"
            self.update_status = QLabel(self)
            self.update_check_button = QPushButton(self)
            self.update_install_button = QPushButton(self)
            self.update_cancel_button = QPushButton(self)
            self.update_progress = QProgressBar(self)

        def show_update_checking(self):
            self.state = "checking"
            SettingsWindow.show_update_checking(self)

        def show_update_latest(self):
            self.state = "latest"
            SettingsWindow.show_update_latest(self)

        def show_update_available(self, info):
            self.state = "available"
            SettingsWindow.show_update_available(self, info)

        def show_update_error(self, message):
            self.state = "error"
            SettingsWindow.show_update_error(self, message)

    controller = WordArc.__new__(WordArc)
    controller.conf = TransientState(update_last_check="")
    panel = UpdatePanel(controller.conf)
    controller.settings_window = panel
    controller._update_thread = None
    controller._updates_possible = lambda: True  # Explicit diagnostic only.
    started = time.perf_counter()
    controller._run_update_check(tray=False)
    evidence = {}

    def finish():
        if controller._active_update_check is not None:
            return
        evidence.update(version=BRAND.version, frozen=bool(getattr(sys, "frozen", False)),
                        ok=panel.state in ("latest", "available"), state=panel.state,
                        status=panel.update_status.text(),
                        check_enabled=panel.update_check_button.isEnabled(),
                        elapsed=time.perf_counter() - started)
        if evidence["ok"]:
            context = update._https_context()
            evidence["tls_verified"] = context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        app.quit()

    poll = QTimer()
    poll.timeout.connect(finish)
    poll.start(10)
    app.exec()
    poll.stop()
    panel.close()
    Path(args.output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if evidence.get("ok") and evidence.get("tls_verified") else 1
