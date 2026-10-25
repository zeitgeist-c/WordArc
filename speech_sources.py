"""Explicit links to existing speech models. Never move or delete shared files."""
import json
import os
from pathlib import Path
import threading

_lock = threading.RLock()


def registry_file():
    import config
    return config.DATA_DIR / "engines" / "speech-sources.json"


def _read():
    try:
        value = json.loads(registry_file().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def selected(kind, name):
    with _lock:
        value = _read().get(f"{kind}:{name}")
    return Path(value) if isinstance(value, str) and value else None


def link(kind, name, path):
    if kind not in ("ct2", "ggml") or name not in ("base", "small", "large-v3-turbo"):
        raise ValueError("Unsupported speech source")
    with _lock:
        data = _read()
        previous = dict(data)
        if path is None:
            data.pop(f"{kind}:{name}", None)
        else:
            path = Path(path).resolve(strict=True)
            data[f"{kind}:{name}"] = str(path)
        data.pop(f"{'ggml' if kind == 'ct2' else 'ct2'}:{name}", None)
        if data == previous:
            return
        target = registry_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, target)


def valid_ct2(path):
    path = Path(path)
    try:
        required = ("config.json", "model.bin", "tokenizer.json")
        return (all((path / name).is_file() and (path / name).stat().st_size > 0
                    for name in required)
                and any((path / name).is_file() for name in ("vocabulary.txt", "vocabulary.json")))
    except OSError:
        return False


def valid_ggml(path):
    try:
        with Path(path).open("rb") as stream:
            return Path(path).stat().st_size > 1024 and stream.read(4) == b"lmgg"
    except OSError:
        return False
