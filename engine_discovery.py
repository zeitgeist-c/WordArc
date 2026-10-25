"""Local speech inventory. Discovery never executes found external programs."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import speech_sources

NAMES = ("base", "small", "large-v3-turbo")
PRUNE = {".git", "node_modules", "site-packages", "__pycache__", "uv",
         "sessions", "session-exports", "logs", "windows", "$recycle.bin",
         "system volume information", "windowsapps", "browser-automation",
         "telemetry", "backups", "_sync-backups", "venv", ".venv", ".cache",
         ".codex", ".npm", "temp", "tmp", "test-temp", "test-tmp",
         "programdata", "recovery", "config.msi"}


class ScanCancelled(Exception):
    pass


@dataclass(frozen=True)
class Model:
    name: str
    kind: str
    path: str
    size: int


@dataclass
class Inventory:
    models: list = field(default_factory=list)
    runtimes: list = field(default_factory=list)
    backends: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    visited: int = 0
    partial: bool = False


def check_stop(stop):
    if stop and stop():
        raise ScanCancelled()


def capture(args, *, timeout=10, stop=None, **options):
    """Bounded child lifetime and file pipes, even when a driver is verbose."""
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(args, stdout=stdout, stderr=stderr, **options)
        try:
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                check_stop(stop)
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(args, timeout)
                time.sleep(0.04)
            stdout.seek(0)
            stderr.seek(0)
            return subprocess.CompletedProcess(args, process.returncode,
                                                stdout.read(256 * 1024), stderr.read(256 * 1024))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def inspect_cli(directory, stop=None, timeout=8):
    """Called only for our hash-verified bundle or an explicitly chosen engine."""
    import vulkan_runtime
    directory = Path(directory)
    result = dict(path=str(directory), compatible=False, devices=[], status="missing", detail="")
    try:
        exe = directory / "whisper-cli.exe"
        if not exe.is_file():
            return result
        completed = capture([str(exe), "--help"], timeout=timeout, stop=stop,
                            **vulkan_runtime.options(directory))
        output = (completed.stdout + completed.stderr).decode("utf-8", "replace").replace("\r", "")
        result["compatible"] = completed.returncode == 0 and all(
            flag in output for flag in ("--output-json", "--device", "--no-gpu", "--no-flash-attn"))
        result["status"] = "ready" if result["compatible"] else "incompatible"
        if not result["compatible"]:
            result["detail"] = output[-500:] or str(completed.returncode)
        for index, name, details in re.findall(
                r"ggml_vulkan:\s+(\d+) = ([^\r\n|]+?)(?:\s*\|([^\r\n]*))?$", output, re.M):
            result["devices"].append(dict(index=int(index), name=name.strip(),
                                           kind=2 if "uma: 1" in details else 1, memory=0))
    except PermissionError as exc:
        result.update(status="denied", detail=str(exc))
    except subprocess.TimeoutExpired:
        result.update(status="timeout")
    except OSError as exc:
        result.update(status="error", detail=str(exc))
    return result


def probe_entry(args):
    """Check our own installed libraries in a disposable child, never a found EXE."""
    kind, destination = args
    result = dict(ready=False, detail="")
    try:
        import localspeech
        if kind == "cpu":
            import faster_whisper  # noqa: F401
            import ctranslate2
            types = ctranslate2.get_supported_compute_types("cpu")
            result.update(ready=bool(types), detail=", ".join(sorted(types)))
        elif kind == "cuda":
            status = localspeech.prerequisite_status()
            result.update(ready=status["gpu_ready"], detail=json.dumps(status))
        else:
            raise ValueError("Unknown backend")
    except Exception as exc:
        result["detail"] = f"{type(exc).__name__}: {exc}"
    Path(destination).write_text(json.dumps(result), encoding="utf-8")
    return 0


def probe_backend(kind, stop=None):
    with tempfile.TemporaryDirectory(prefix="wordarc-engine-check-") as scratch:
        output = Path(scratch) / "result.json"
        entry = ([sys.executable, "--speech-probe"] if getattr(sys, "frozen", False)
                 else [sys.executable, str(Path(__file__).resolve()), "--speech-probe"])
        try:
            done = capture([*entry, kind, str(output)], timeout=18, stop=stop,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if done.returncode != 0 or not output.is_file():
                return dict(ready=False, status="error", detail="Probe exited: " + str(done.returncode))
            result = json.loads(output.read_text(encoding="utf-8"))
            result["status"] = "ready" if result["ready"] else "unavailable"
            return result
        except subprocess.TimeoutExpired:
            return dict(ready=False, status="timeout", detail="")
        except (OSError, ValueError) as exc:
            return dict(ready=False, status="error", detail=str(exc))


def search_roots(extra=()):
    import config
    home = Path.home()
    hermes = Path(os.environ.get("HERMES_HOME", home / "AppData/Local/hermes"))
    hf = Path(os.environ.get("HF_HOME", home / ".cache/huggingface"))
    roots = [config.DATA_DIR / "whisper", config.DATA_DIR / "engines",
             Path(os.environ.get("HF_HUB_CACHE", os.environ.get("HUGGINGFACE_HUB_CACHE", hf / "hub"))),
             *map(Path, extra), hermes / "cache", hermes / "tools", hermes / "runtime", hermes / "models", hermes / "installs",
             home / ".hermes", home / "AppData/Local/WordArc/whisper", home / "Downloads", home / "Documents", home,
             *fixed_drives()]
    return list(dict.fromkeys(roots))


def fixed_drives():
    """Read-only inventory also covers models stored outside the user profile."""
    if os.name != "nt":
        return []
    import ctypes
    kernel = ctypes.windll.kernel32
    mask = kernel.GetLogicalDrives()
    return [Path(root) for index in range(26)
            if mask & (1 << index)
            and kernel.GetDriveTypeW(root := chr(65 + index) + ":\\") == 3]


def _model_name(path):
    text = str(path).lower().replace("_", "-")
    if "large-v3-turbo" in text or "whisper-turbo" in text:
        return "large-v3-turbo"
    for name in ("base", "small"):
        if re.search(rf"(?:ggml-|whisper-|[/\\]){name}(?:\.bin|[/\\]|$)", text):
            return name
    return ""


def _trusted_runtime(directory):
    """A discovered name is not trust. Only the shipped manifest grants auto-probe."""
    import vulkan_runtime
    from brand import resource_path
    try:
        manifest = json.loads(resource_path("native", "whisper-vulkan", "manifest.json").read_text())
        directory = Path(directory)
        expected = {name.replace("\\", "/").lower() for name in manifest["files"]
                    if name.lower().endswith((".dll", ".exe"))}
        actual = {path.relative_to(directory).as_posix().lower() for path in directory.rglob("*")
                  if path.suffix.lower() in (".dll", ".exe") and path.is_file()}
        return actual == expected and vulkan_runtime._verified(directory, manifest)
    except (OSError, ValueError, KeyError):
        return False


def scan(*, roots=None, extra=(), stop=None, progress=None, max_seconds=65, max_entries=1000000):
    import vulkan_runtime
    inventory = Inventory()
    started = time.monotonic()
    seen_dirs, seen_models, cli_dirs = set(), set(), {}

    def report(phase, done=0, total=0, path=""):
        check_stop(stop)
        if progress:
            progress(dict(phase=phase, done=done, total=total, path=str(path),
                          models=len(inventory.models), visited=inventory.visited))

    def add_cli(directory):
        cli_dirs.setdefault(os.path.normcase(os.path.abspath(directory)), Path(directory))

    if roots is None:
        try:
            for directory in vulkan_runtime.candidates():
                try:
                    if (directory / "whisper-cli.exe").is_file():
                        add_cli(directory)
                except OSError as exc:
                    inventory.issues.append((str(directory), "denied", str(exc)))
        except OSError as exc:
            inventory.issues.append(("runtime locations", "error", str(exc)))
    stack = list(reversed(list(roots if roots is not None else search_roots(extra))))
    report("search")
    while stack:
        check_stop(stop)
        if time.monotonic() - started >= max_seconds or inventory.visited >= max_entries:
            inventory.partial = True
            break
        directory = stack.pop()
        key = os.path.normcase(os.path.abspath(directory))
        if key in seen_dirs:
            continue
        seen_dirs.add(key)
        try:
            if directory.is_symlink() or (hasattr(directory, "is_junction") and directory.is_junction()):
                continue
            with os.scandir(directory) as entries:
                entries = list(entries)
            files = {entry.name.lower(): Path(entry.path) for entry in entries if entry.is_file()}
            if "whisper-cli.exe" in files:
                add_cli(directory)
            model_paths = [(path, "ggml") for name, path in files.items()
                           if name.startswith("ggml-") and name.endswith(".bin")]
            if "model.bin" in files:
                model_paths.append((directory, "ct2"))
            for path, kind in model_paths:
                name = _model_name(path)
                valid = speech_sources.valid_ggml(path) if kind == "ggml" else speech_sources.valid_ct2(path)
                identity = (kind, os.path.normcase(str(path.resolve())))
                if name and valid and identity not in seen_models:
                    seen_models.add(identity)
                    size = (path if kind == "ggml" else path / "model.bin").stat().st_size
                    inventory.models.append(Model(name, kind, str(path), size))
            for entry in entries:
                inventory.visited += 1
                if entry.name.lower() not in PRUNE and entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
            if len(seen_dirs) % 32 == 0:
                report("search", path=directory)
        except FileNotFoundError:
            continue
        except OSError as exc:
            inventory.issues.append((str(directory), "denied" if isinstance(exc, PermissionError) else "error", str(exc)))
    total = 2 + len(cli_dirs)
    for index, kind in enumerate(("cpu", "cuda")):
        report("probe", index, total, kind.upper())
        inventory.backends[kind] = probe_backend(kind, stop)
    for index, directory in enumerate(cli_dirs.values(), 2):
        report("probe", index, total, directory)
        if time.monotonic() - started > max_seconds + 40:
            inventory.partial = True
            inventory.runtimes.append(dict(path=str(directory), compatible=False,
                                          devices=[], status="not_checked", detail=""))
            continue
        if _trusted_runtime(directory):
            inventory.runtimes.append(inspect_cli(directory, stop))
        else:
            inventory.runtimes.append(dict(path=str(directory), compatible=False,
                                          devices=[], status="unverified", detail=""))
    report("complete", 1, 1)
    return inventory


def choices(inventory):
    """Rows represent model/backend pairs; external CLIs require explicit validation."""
    rows = []
    # Several installations often contain the identical native engine. Offer
    # one usable runtime per device rather than a model × every-copy cross product.
    runtimes = sorted(inventory.runtimes, key=lambda row: row["status"] == "unverified")
    for model in inventory.models:
        if model.kind == "ct2":
            for device in ("cpu", "cuda"):
                if inventory.backends.get(device, {}).get("ready"):
                    rows.append(dict(model=model, device=device, runtime="", unverified=False))
        else:
            offered = set()
            for runtime in runtimes:
                if not runtime["compatible"] and runtime["status"] != "unverified":
                    continue
                unverified = runtime["status"] == "unverified"
                if "cpu" not in offered:
                    rows.append(dict(model=model, device="cpu", runtime=runtime["path"], unverified=unverified))
                    offered.add("cpu")
                if unverified or any("amd" in row["name"].lower() or "radeon" in row["name"].lower()
                                     for row in runtime["devices"]):
                    if "vulkan" not in offered:
                        rows.append(dict(model=model, device="vulkan", runtime=runtime["path"], unverified=unverified))
                        offered.add("vulkan")
    return rows


def activate(choice, stop=None):
    """Invoked by Use: validate that exact user-selected runtime before linking."""
    model = choice["model"]
    if not (speech_sources.valid_ct2(model.path) if model.kind == "ct2" else speech_sources.valid_ggml(model.path)):
        raise ValueError("The selected model is no longer available.")
    if choice["runtime"]:
        import vulkan_runtime
        result = inspect_cli(choice["runtime"], stop)
        amd = any("amd" in row["name"].lower() or "radeon" in row["name"].lower() for row in result["devices"])
        if not result["compatible"] or (choice["device"] == "vulkan" and not amd):
            raise ValueError(result["status"] + ": " + (result["detail"] or "No compatible device"))
        vulkan_runtime.select(Path(choice["runtime"]) / "whisper-cli.exe", cpu=choice["device"] == "cpu")
    check_stop(stop)
    speech_sources.link(model.kind, model.name, model.path)
    import vulkan_speech
    vulkan_speech._devices_cache = ()
    vulkan_speech._failed = False
    vulkan_speech._failure_note = ""


if __name__ == "__main__":
    sys.exit(probe_entry(sys.argv[2:]))
