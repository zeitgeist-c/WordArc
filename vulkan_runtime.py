"""Discover compatible local whisper.cpp engines and repair WordArc's runtime.

Never modify another application's engine. Verified bundled/downloaded files
live in user data so cleanup of a one-file EXE's temp directory is harmless.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile

from brand import resource_path
from i18n import t

_lock = threading.RLock()
_cached = None
_checked = {}


def managed_dir():
    import config
    return config.DATA_DIR / "engines" / "whisper-vulkan"


def _selection_file():
    return managed_dir().parent / "vulkan-selection.json"


def options(directory):
    env = dict(os.environ)
    env.pop("GGML_VK_VISIBLE_DEVICES", None)
    env.pop("WHISPER_DEVICE", None)
    env["VK_LOADER_LAYERS_DISABLE"] = "~implicit~"
    env["PATH"] = str(directory) + os.pathsep + os.path.join(env.get("SystemRoot", "C:\\Windows"), "System32")
    return dict(env=env, cwd=str(directory), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def inspect(directory):
    """Validate CLI switches and Vulkan device output without loading a model."""
    try:
        directory = Path(directory)
        exe = directory / "whisper-cli.exe"
        if not exe.is_file():
            return ()
        signature = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                          for p in (exe, *sorted(directory.glob("*.dll"))))
        key = (str(directory.resolve()), signature)
        if key in _checked:
            return _checked[key]
        result = subprocess.run([str(exe), "--help"], capture_output=True,
                                timeout=20, **options(directory))
        output = (result.stdout + result.stderr).decode("utf-8", "replace").replace("\r", "")
        if result.returncode or not all(flag in output for flag in
                                       ("--output-json", "--device", "--no-gpu", "--no-flash-attn")):
            return ()
        rows = []
        for index, name, details in re.findall(
                r"ggml_vulkan:\s+(\d+) = ([^\r\n|]+?)(?:\s*\|([^\r\n]*))?$", output, re.M):
            rows.append(dict(index=int(index), name=name.strip(),
                             kind=2 if "uma: 1" in details else 1, memory=0))
        if rows:
            _checked[key] = tuple(rows)
        return tuple(rows)
    except (OSError, subprocess.TimeoutExpired):
        return ()


def candidates():
    """Bounded search: saved choice, app data, PATH, common installs and Hermes."""
    try:
        selected = json.loads(_selection_file().read_text(encoding="utf-8"))["directory"]
        yield Path(selected)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    yield managed_dir()
    yield resource_path("native", "whisper-vulkan")
    for item in os.environ.get("PATH", "").split(os.pathsep):
        if item:
            yield Path(item)
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    for base in (Path(os.environ.get("ProgramFiles", "C:/Program Files")), local / "Programs"):
        for name in ("whisper.cpp", "whisper-vulkan", "whisper"):
            yield base / name
            yield base / name / "bin"
    homes = (Path(os.environ.get("HERMES_HOME", local / "hermes")), Path.home() / ".hermes")
    for home in homes:
        for name in ("bin", "cache/whisper.cpp", "tools/whisper.cpp", "whisper.cpp"):
            yield home / name
        # Engine package locations vary between Hermes installations.
        for name in ("installs", "tools", "runtime"):
            base = home / name
            for pattern in ("*whisper*", "*/*whisper*", "*whisper*/*", "*/*whisper*/*"):
                try:
                    for directory in base.glob(pattern):
                        if directory.is_dir():
                            yield directory
                            yield directory / "bin"
                except OSError:
                    continue  # One inaccessible install must not stop discovery.


def _verified(directory, manifest):
    try:
        for name, digest in manifest["files"].items():
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or ":" in name:
                return False
            with (directory / path).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    return False
        return bool(manifest["files"])
    except (OSError, ValueError, KeyError):
        return False


def _install(source, manifest):
    if not _verified(source, manifest):
        raise RuntimeError(t("The GPU support file is damaged. Try again."))
    root = managed_dir()
    root.parent.mkdir(parents=True, exist_ok=True)
    # Copy into a complete staging directory before replacing a broken runtime.
    with tempfile.TemporaryDirectory(prefix="vulkan-stage-", dir=root.parent) as scratch:
        staged = Path(scratch) / "engine"
        shutil.copytree(source, staged)
        backup = Path(scratch) / "previous"
        if root.exists():
            root.rename(backup)
        try:
            staged.rename(root)
        except OSError:
            if backup.exists():
                backup.rename(root)
            raise
    return root


def resolve(refresh=False):
    global _cached
    with _lock:
        if refresh:
            _cached = None
            _checked.clear()
        if _cached is not None:
            try:
                if (_cached / "whisper-cli.exe").is_file():
                    return _cached
            except OSError:
                pass
            _cached = None
        seen = set()
        try:
            selection = json.loads(_selection_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            selection = {}
        for directory in candidates():
            key = str(directory).casefold()
            if key in seen:
                continue
            seen.add(key)
            if not inspect(directory):
                # A previously chosen CPU CLI need not advertise a Vulkan GPU.
                from engine_discovery import inspect_cli
                if not (isinstance(selection, dict) and selection.get("cpu")
                        and str(directory) == selection.get("directory")
                        and inspect_cli(directory)["compatible"]):
                    continue
            if directory == resource_path("native", "whisper-vulkan"):
                try:
                    manifest = json.loads((directory / "manifest.json").read_text())
                    directory = _install(directory, manifest)
                except (OSError, RuntimeError, ValueError, KeyError):
                    pass  # A read-only user-data folder can still use the bundle.
            _cached = directory
            return directory
        return resource_path("native", "whisper-vulkan")


def ready():
    return bool(inspect(resolve()))


def select(executable, *, cpu=False):
    global _cached
    directory = Path(executable).resolve().parent
    from engine_discovery import inspect_cli
    if not (inspect_cli(directory)["compatible"] if cpu else inspect(directory)):
        raise RuntimeError(t("Select a compatible whisper-cli.exe with Vulkan support."))
    with _lock:
        path = _selection_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(dict(directory=str(directory), cpu=cpu)), encoding="utf-8")
        temp.replace(path)
        _cached = directory
    return directory


def ensure(progress=None, should_stop=None):
    """Reuse a compatible installed engine first; otherwise download pinned ZIP."""
    global _cached
    import update
    with _lock:
        if ready():
            return resolve()
        pins = json.loads(resource_path("assets", "vulkan", "runtime.json").read_text())
        info = update.UpdateInfo(version=pins["version"], asset_name=pins["file"],
                                 download_url=pins["url"], sha256=pins["sha256"],
                                 size=pins["size"], page_url="")
        def report(done, total):
            if should_stop and should_stop():
                raise update.UpdateError("cancelled")
            if progress:
                progress(done, total)
        class Cancellation:
            def is_set(self):
                return bool(should_stop and should_stop())
        cancel = Cancellation()
        if cancel.is_set():
            raise update.UpdateError("cancelled")
        with tempfile.TemporaryDirectory(prefix="wordarc-vulkan-download-") as scratch:
            archive = Path(scratch) / pins["file"]
            update.download(info, archive, progress=report, cancel=cancel)
            extracted = Path(scratch) / "engine"
            extracted.mkdir()
            with zipfile.ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    path = Path(name)
                    if path.is_absolute() or ".." in path.parts or ":" in name:
                        raise RuntimeError("Invalid Vulkan archive path")
                bundle.extractall(extracted)
            manifest = json.loads((extracted / "manifest.json").read_text())
            _cached = _install(extracted, manifest)
        if not inspect(_cached):
            raise RuntimeError(t("No usable AMD Vulkan device was found. Check the AMD driver."))
        return _cached
