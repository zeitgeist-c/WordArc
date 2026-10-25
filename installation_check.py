"""Offline, no-config-write preflight for Inno and the update supervisor."""
import argparse
import json
from pathlib import Path
import sys


def run(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    from brand import BRAND
    result = dict(ok=False, version=BRAND.version, exe=str(Path(sys.executable).resolve()))
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6 import QtSvg  # noqa: F401
        import wordarc  # noqa: F401 - startup imports, without main()/IPC
        app = QApplication.instance() or QApplication([])
        from brand import brand_icon
        if brand_icon().pixmap(32, 32).isNull():
            raise RuntimeError("Application resources could not be loaded")
        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    Path(args.output).write_text(json.dumps(result), encoding="utf-8")
    return 0 if result["ok"] else 1
