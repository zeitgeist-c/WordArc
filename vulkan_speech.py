"""Bundled whisper.cpp/Vulkan, run in a cancellable isolated subprocess.

CUDA/CPU keep faster-whisper. GGML weights live in a separate directory;
the same GGML model can also run on the CPU after a Vulkan failure.
"""
from __future__ import annotations
import json
import logging
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time
import wave

from i18n import t

_log = logging.getLogger("wordarc.vulkan")
VERSION = "1.9.2"
MODEL_REPO = "ggerganov/whisper.cpp"
MODEL_FILES = {name: f"ggml-{name}.bin" for name in ("base", "small", "large-v3-turbo")}
MODEL_SIZES = {"base": 147_951_465, "small": 487_601_967, "large-v3-turbo": 1_624_555_275}
_failed = False
_failure_note = ""


class VulkanError(Exception):
    """Driver, native motor or GPU execution failed; audio stays local."""


def runtime_dir():
    import vulkan_runtime
    return vulkan_runtime.resolve()


def process_options(directory=None):
    # Resolve native dependencies from the child directory and Windows,
    # without adding development Python/Qt paths to the child's PATH.
    env = dict(os.environ)
    env.pop("GGML_VK_VISIBLE_DEVICES", None)
    env.pop("WHISPER_DEVICE", None)
    # Steam/RTSS/EOS overlays register implicit Vulkan layers that hook
    # every VkInstance, including this headless compute child. Under a
    # running game they can stall device init; there is nothing to overlay
    # here, so keep them out of every native child (probe and transcribe).
    env["VK_LOADER_LAYERS_DISABLE"] = "~implicit~"
    directory = directory or runtime_dir()
    env["PATH"] = str(directory) + os.pathsep + os.path.join(env.get("SystemRoot", "C:\\Windows"), "System32")
    return dict(env=env, cwd=str(directory),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


_devices_cache: tuple = ()
_devices_cache_time = 0.0
_DEVICES_CACHE_TTL = 300.0  # successes only; a failed probe never sticks
_PROBE_ATTEMPTS = 2
_PROBE_TIMEOUT = 15


def _probe_once():
    """One probe run; () when the backend did not answer this time."""
    try:
        exe = runtime_dir() / "wordarc-vulkan-probe.exe"
        if not exe.is_file():
            import vulkan_runtime
            return vulkan_runtime.inspect(runtime_dir())
        result = subprocess.run([str(exe)], capture_output=True,
                                timeout=_PROBE_TIMEOUT, **process_options())
        if result.returncode:
            _log.warning("Vulkan probe failed: %s", result.stderr.decode("utf-8", "replace")[-1500:])
            return ()
        rows = []
        for line in result.stdout.decode("utf-8", "replace").splitlines():
            index, kind, memory, name = line.split("\t", 3)
            rows.append(dict(index=int(index), kind=int(kind), memory=int(memory), name=name))
        return tuple(rows)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        _log.warning("Vulkan probe unavailable: %s", exc)
        return ()


def devices(refresh=False):
    """The actual Vulkan backend's device order, not Windows registry remnants.

    A failed probe is retried on the next call instead of poisoning the
    whole session: only successful results are cached.
    """
    global _devices_cache, _devices_cache_time
    if (not refresh and _devices_cache
            and time.monotonic() - _devices_cache_time < _DEVICES_CACHE_TTL):
        return _devices_cache
    for _ in range(_PROBE_ATTEMPTS):
        rows = _probe_once()
        if rows:
            _devices_cache = rows
            _devices_cache_time = time.monotonic()
            return rows
    return ()


def best_device():
    # AMD only for automatic routing. GPU=1, IGPU=2 in ggml-backend.h.
    amd = [row for row in devices() if "amd" in row["name"].lower() or "radeon" in row["name"].lower()]
    return max(amd, key=lambda row: (row["kind"] == 1, row["memory"]), default=None)


def available():
    return not _failed and best_device() is not None


def model_root(where=None):
    if where is None:
        import localspeech
        where = localspeech.models_dir()
    return Path(where) / "whisper.cpp"


def model_path(name, where=None):
    if where is None:
        import speech_sources
        selected = speech_sources.selected("ggml", name)
        if selected is not None:
            return selected
    return model_root(where) / MODEL_FILES[name]


def installed(name, where=None):
    if name not in MODEL_FILES:
        return False
    path = model_path(name, where)
    try:
        # A completed verified download is atomically renamed from .part.
        with path.open("rb") as stream:
            return path.stat().st_size > 1024 and stream.read(4) == b"lmgg"
    except OSError:
        return False


def download(name, where=None, should_stop=None, on_progress=None, force=False):
    """Reuse the existing resumable/hash-verified downloader, never convert CT2."""
    import localspeech as stt
    if name not in MODEL_FILES:
        raise stt.LocalSpeechError(t("Unknown local model: {name}", name=name))
    # The shared download lock also protects downloads across both engines.
    while not stt._download_lock.acquire(timeout=0.1):
        stt._check_cancelled(should_stop)
    try:
        return stt._download_model(name, where, should_stop, on_progress,
                                   backend="vulkan", force=force)
    finally:
        stt._download_lock.release()


def fail(reason):
    global _failed, _failure_note
    _failed = True
    _failure_note = t("Vulkan failed; using CPU for this session: {error}", error=reason)
    _log.warning("%s", _failure_note)


def error_details(diagnostics, returncode):
    # Native stdout contains transcript text. Never copy it into persistent logs
    # or failure messages; retain only explicit driver/loader/error lines.
    lines = [line for line in diagnostics.splitlines()
             if line.lower().startswith(("error:", "ggml_vulkan:", "ggml_vulkan_error"))
             or "failed to" in line.lower() and line.startswith("whisper_")]
    return "\n".join(lines[-8:])[-1600:] or f"Native process exit code: {returncode}"


def transcribe(name, wav_path, language="", prompt="", should_stop=None,
               with_segments=False, where=None, use_gpu=True):
    import localspeech as stt
    stt._check_cancelled(should_stop)
    if not installed(name, where):
        raise stt.LocalSpeechError(t("The Vulkan model {name} is not installed yet. Download it in Settings.", name=name))
    directory = runtime_dir() if use_gpu else runtime_dir() / "cpu"
    if not use_gpu and not (directory / "whisper-cli.exe").is_file():
        directory = runtime_dir()  # External engines can run the same CLI with -ng.
    exe = directory / "whisper-cli.exe"
    if not exe.is_file():
        raise VulkanError(t("The Vulkan engine is missing. Scan, select or download it in Settings."))
    device = best_device() if use_gpu else None
    if use_gpu and device is None:
        raise VulkanError(t("No usable AMD Vulkan device was found. Check the AMD driver."))
    # Validate the same recording format and empty-take guard as faster-whisper.
    try:
        with wave.open(str(wav_path), "rb") as wav:
            if wav.getnframes() == 0:
                raise stt.LocalSpeechError(t("The recording was empty."))
            if (wav.getframerate(), wav.getsampwidth()) != (stt.RATE, 2):
                raise stt.LocalSpeechError(t("Vulkan reads 16 kHz, 16-bit WAV audio."))
    except (OSError, wave.Error) as exc:
        raise stt.LocalSpeechError(t("Local transcription failed: {error}", error=exc)) from exc
    with tempfile.TemporaryDirectory(prefix="wordarc-vulkan-") as scratch:
        # whisper.cpp's narrow Windows file APIs cannot reliably open Turkish paths.
        # Pass short ASCII staging paths; the original recording is untouched.
        import shutil
        import ctypes
        if os.name == "nt":
            buffer = ctypes.create_unicode_buffer(32768)
            if ctypes.windll.kernel32.GetShortPathNameW(scratch, buffer, len(buffer)):
                scratch = buffer.value
        audio = Path(scratch) / "audio.wav"
        shutil.copyfile(wav_path, audio)
        # Stage the model via a hard link (no duplicate GB copy) when possible.
        weights = Path(scratch) / "model.bin"
        try:
            os.link(model_path(name, where), weights)
        except OSError:
            shutil.copyfile(model_path(name, where), weights)
        output = str(Path(scratch) / "result")
        args = [str(exe), "-m", str(weights), "-f", str(audio), "-l", language or "auto",
                "-t", str(stt.THREADS), "-bs", "5", "-mc", "0", "-oj", "-of", output,
                "-nfa"]
        if prompt:
            args.extend(["--prompt", prompt])
        args.extend(["-dev", str(device["index"])] if use_gpu else ["-ng"])
        started = time.monotonic()
        try:
            # File-backed diagnostics prevent stdout/stderr pipe deadlocks on meetings.
            with open(Path(scratch) / "native.log", "w+b") as log:
                process = subprocess.Popen(args, stdout=log, stderr=log, **process_options(directory))
                try:
                    while process.poll() is None:
                        stt._check_cancelled(should_stop)
                        time.sleep(0.1)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=10)
                log.seek(0)
                diagnostics = log.read().decode("utf-8", "replace")
            if process.returncode:
                raise VulkanError(t("Vulkan transcription failed: {error}",
                                    error=error_details(diagnostics, process.returncode)))
            # whisper.cpp may silently use CPU even with use_gpu=true. Require proof.
            if use_gpu and ("using Vulkan" not in diagnostics
                            or not re.search(r"whisper_model_load:\s+Vulkan\d+\s+total size", diagnostics)
                            or "failed to initialize Vulkan" in diagnostics):
                raise VulkanError(t("Vulkan did not initialize a GPU backend."))
            payload = json.loads(Path(output + ".json").read_text(encoding="utf-8"))
            segments = [(row["offsets"]["from"] / 1000, row["offsets"]["to"] / 1000,
                         row["text"].strip()) for row in payload["transcription"]]
            _log.info("local speech: whisper.cpp %s, %s, device=%s, model=%s, elapsed=%.2fs",
                      VERSION, "vulkan" if use_gpu else "cpu", device["name"] if device else "CPU",
                      name, time.monotonic() - started)
            return segments if with_segments else " ".join(row[2] for row in segments).strip()
        except stt.Cancelled:
            raise
        except (OSError, ValueError, KeyError) as exc:
            raise VulkanError(t("Vulkan transcription failed: {error}", error=exc)) from exc
