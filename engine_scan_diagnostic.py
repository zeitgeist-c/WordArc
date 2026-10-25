"""Opt-in acceptance of the actual scan dialog, selection and transcription."""
import argparse
import json
from pathlib import Path
import sys
import threading
import time


def run(argv):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    from brand import BRAND, resource_path
    from engine_scan_ui import EngineScanDialog
    from settings_ui import SettingsWindow
    import config as cfg
    import localspeech
    import speech_sources

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda", "vulkan"), required=True)
    parser.add_argument("--kind", choices=("ct2", "ggml"), required=True)
    parser.add_argument("--model", choices=localspeech.model_names(), required=True)
    args = parser.parse_args(argv)
    # Explicit diagnostic state, never the running user's settings or models.
    state = Path(args.state_dir).resolve()
    cfg.CONFIG_DIR = state / "config"
    cfg.CONFIG_FILE = cfg.CONFIG_DIR / "config.json"
    cfg.DATA_DIR = state / "data"
    cfg.HISTORY_FILE = cfg.DATA_DIR / "history.jsonl"
    cfg.MEETINGS_DIR = cfg.DATA_DIR / "meetings"
    cfg.MEETINGS_FILE = cfg.DATA_DIR / "meetings.jsonl"
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    conf = cfg.Config()
    conf["transcribe_engine"] = "cloud"
    window = SettingsWindow(conf, "wordarc")
    roots = [*map(Path, args.root), resource_path("native", "whisper-vulkan")]
    dialog = EngineScanDialog(window, scan_options=dict(roots=roots))
    window._engine_scan_dialog = dialog
    dialog.selected.connect(window._on_engine_source_selected)
    progress = []
    dialog._progress.connect(lambda _generation, value: progress.append(value["phase"]))
    started = time.monotonic()
    payload = dict(version=BRAND.version, frozen=bool(getattr(sys, "frozen", False)),
                   device=args.device, kind=args.kind, model=args.model)
    stage = "scan"
    worker_result = {}

    def decode():
        try:
            text = localspeech.transcribe(args.model, args.audio, language="en",
                                         device_preference=args.device)
            worker_result.update(ok=bool(text.strip()), text=text,
                                 fallback=localspeech.last_fallback_note())
        except Exception as exc:
            worker_result.update(ok=False, error=f"{type(exc).__name__}: {exc}")

    def fail(message):
        payload.update(ok=False, error=message)
        app.quit()

    def tick():
        nonlocal stage
        try:
            if time.monotonic() - started > 110:
                fail("Scan/selection/transcription timed out")
            elif stage == "scan" and not dialog._busy:
                if dialog.inventory is None:
                    fail(dialog.status.text())
                    return
                payload.update(models_found=len(dialog.inventory.models), progress_seen=sorted(set(progress)),
                               backends=dialog.inventory.backends)
                for row in range(dialog.results.count()):
                    from PyQt6.QtCore import Qt
                    choice = dialog.results.item(row).data(Qt.ItemDataRole.UserRole)
                    if choice and choice["device"] == args.device and choice["model"].kind == args.kind and choice["model"].name == args.model:
                        dialog.results.setCurrentRow(row)
                        payload["model_path"] = choice["model"].path
                        stage = "select"
                        dialog.use.click()
                        return
                fail("Requested model/backend combination was not discovered")
            elif stage == "select" and not dialog._applying:
                if conf["local_stt_device"] != args.device or conf["transcribe_engine"] != "local":
                    fail(dialog.status.text())
                    return
                linked = speech_sources.selected(args.kind, args.model)
                assert str(linked) == payload["model_path"]
                persisted = json.loads(cfg.CONFIG_FILE.read_text(encoding="utf-8"))
                assert persisted["local_stt_device"] == args.device
                payload.update(selection_saved=True, linked_without_copy=True)
                stage = "decode"
                threading.Thread(target=decode, daemon=True).start()
            elif stage == "decode" and "ok" in worker_result:
                payload.update(worker_result)
                app.quit()
        except Exception as exc:
            fail(f"{type(exc).__name__}: {exc}")

    poll = QTimer()
    poll.timeout.connect(tick)
    poll.start(15)
    dialog.show()
    dialog.start()
    app.exec()
    poll.stop()
    dialog.reject()
    window.close()
    payload["elapsed"] = time.monotonic() - started
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if payload.get("ok") else 1
