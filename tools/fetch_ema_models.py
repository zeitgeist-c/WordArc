"""Vendor the EMA Lightning TTS weight set for frozen packaging.

Build-time helper: puts the 4 model files under tools/vendor/ema-onnx so
wordarc.spec can bundle them into the exe. Prefers the copy the user may
already have under %LOCALAPPDATA%/WordArc/models/ema-onnx (same files the
app downloads on first Speak use); falls back to a Hugging Face download.

Usage: python tools/fetch_ema_models.py
Exits non-zero when the set is incomplete.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

REPO = "ozcancelik/ema-lightning-onnx"
FILES = ("text.onnx", "sound.onnx", "decoder.onnx", "meta.json")

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "tools" / "vendor" / "ema-onnx"


def _localappdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home())


def models_ready(where: Path) -> bool:
    return all((where / name).is_file() for name in FILES)


def from_existing_download() -> bool:
    """Copy the app's own downloaded set when it is complete."""
    src = _localappdata() / "WordArc" / "models" / "ema-onnx"
    if not models_ready(src):
        return False
    DEST.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = DEST / name
        if target.is_file():
            continue
        shutil.copyfile(src / name, target)
    return True


def from_huggingface() -> None:
    try:
        from huggingface_hub import snapshot_download
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "neither a local TTS model copy nor huggingface_hub is "
            f"available: {exc}"
        ) from exc
    DEST.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=REPO, local_dir=str(DEST),
                      allow_patterns=list(FILES))


def main() -> None:
    if models_ready(DEST):
        print(f"ema-onnx vendored already: {DEST}")
        return
    if from_existing_download() and models_ready(DEST):
        print(f"ema-onnx vendored from local download: {DEST}")
        return
    from_huggingface()
    if not models_ready(DEST):
        raise SystemExit(f"incomplete model set in {DEST}")
    print(f"ema-onnx vendored from Hugging Face: {DEST}")


if __name__ == "__main__":
    main()
