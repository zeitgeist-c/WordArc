"""Speech to text on this computer, with faster-whisper.

The cloud path in api.py is one way to turn speech into text; this is the other.
Both answer the same question and are called the same way, so the caller picks
one and never asks which it got.

Why a separate module rather than a second client inside api.py: everything this
needs is optional. The cloud client is four stdlib modules and an API key; this
one pulls in ctranslate2, onnxruntime and a 1.6 GB model file, and every one of
those is a reason an installation can fail on a machine that does not want it.
So nothing heavy is imported until it is asked for, and every failure to reach
this engine is reported as a plain, actionable message instead of an import
error at start-up.

The audio the app records is already 16 kHz mono s16 WAV, which is exactly what
Whisper wants, so decoding is the stdlib wave module and a float32 array — PyAV
is a faster-whisper dependency but is never called for a WAV we produced
ourselves.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import threading
import wave
import json
import hashlib
import time
import ssl
import urllib.request
import urllib.parse
from dataclasses import dataclass

from i18n import t
import cuda_runtime
import vulkan_speech

_log = logging.getLogger("wordarc.localspeech")

RATE = 16000           # what the app records, and what Whisper is trained on
THREADS = 8

# --- compute device -------------------------------------------------------
# One place decides where the model runs; every load goes through it.
#   Nvidia + working CUDA -> cuda + float16 (any card: GTX 10xx through RTX
#   50xx; no per-model code, ctranslate2.get_cuda_device_count() > 0 is the
#   initial driver check; required CUDA DLLs must also load).
#   AMD + working bundled Vulkan -> whisper.cpp; otherwise cpu + int8.
DEVICE_AUTO, DEVICE_CUDA, DEVICE_CPU, DEVICE_VULKAN = "auto", "cuda", "cpu", "vulkan"
DEVICE_CHOICES = (
    ("Automatic", DEVICE_AUTO),
    ("Nvidia GPU", DEVICE_CUDA),
    ("AMD GPU (Vulkan)", DEVICE_VULKAN),
    ("CPU", DEVICE_CPU),
)
COMPUTE_CPU = "int8"
COMPUTE_CUDA = "float16"

# Python packages the local engine cannot run without.
REQUIRED_PACKAGES = ("faster_whisper", "ctranslate2")

# Fragments of a failed load that mean "the CUDA libraries are missing"
# (cuBLAS/cuDNN/CUDA runtime not found) as opposed to a real run failure.
# Those fall back to CPU; anything else — including "out of memory" — is
# re-raised so a genuine execution error is never hidden.
_CUDA_LIBRARY_HINTS = ("cublas", "cudnn", "cudart", "cuda driver",
                       "cuda runtime", "cublaslt", "libcuda",
                       "no cuda", "cuda is not available")
_OOM_HINTS = ("out of memory", "out-of-memory", "cuda error 2",
              "out of device memory", "alloc_failed")
COMPUTE_TYPE = COMPUTE_CPU  # historic name for the CPU compute type


def _cuda_device_count():
    """Usable Nvidia GPUs, or None when ctranslate2 cannot even be asked."""
    try:
        cuda_runtime.prepare()
        import ctranslate2
    except Exception:
        return None
    get = getattr(ctranslate2, "get_cuda_device_count", None)
    if get is None:
        return None
    try:
        return int(get())
    except Exception:
        return None


def cuda_available():
    """True when any Nvidia card answers through the CUDA runtime."""
    count = _cuda_device_count()
    return (count is not None and count > 0
            and not cuda_runtime.missing_libraries())


def cuda_driver_present():
    """True when the Nvidia driver answers (nvidia-smi runs)."""
    try:
        import subprocess
        subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                       timeout=15, check=True)
    except Exception:
        return False
    return True


def missing_python_packages():
    """Required packages that are not importable right now."""
    import importlib.util
    return [name for name in REQUIRED_PACKAGES
            if importlib.util.find_spec(name) is None]


def prerequisite_status():
    """What the install-time system check found.

    Keys: ``packages_missing`` (list), ``driver`` (bool),
    ``cuda_devices`` (int or None), ``gpu_ready`` (bool).
    """
    missing = missing_python_packages()
    driver = cuda_driver_present()
    devices = _cuda_device_count()
    return {
        "packages_missing": missing,
        "driver": driver,
        "cuda_devices": devices,
        "gpu_ready": bool(devices is not None and devices > 0
                          and not missing
                          and not cuda_runtime.missing_libraries()),
    }


def install_missing_packages(packages=None):
    """pip-install the missing engine packages; LocalSpeechError on failure.

    Frozen builds carry their own packages, so a missing one there means a
    broken install, not something pip could fix.
    """
    missing = list(packages) if packages else missing_python_packages()
    if not missing:
        return ()
    import sys
    if getattr(sys, "frozen", False):
        _fail("The local speech engine is missing. Reinstall WordArc to "
              "get it back.")
    import subprocess
    _log.info("installing local speech packages: %s", ", ".join(missing))
    try:
        # Import names (faster_whisper) are not a versioned installation
        # contract. Use the same tested runtime set as the build instead.
        from pathlib import Path
        requirements = Path(__file__).with_name("requirements-lock.txt")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                        str(requirements)],
                       capture_output=True, timeout=600, check=True)
    except Exception as exc:
        _fail("Could not install the local speech engine: {error}",
              error=exc)
    return tuple(missing)


def get_best_device(preference=DEVICE_AUTO):
    """(device, compute_type) for a WhisperModel load.

    ``preference`` is the Settings choice: auto (default), cuda or cpu.
    Forced cuda with no usable CUDA raises instead of silently landing on
    the CPU; forced cpu always lands on the CPU.
    """
    want = (preference or DEVICE_AUTO).lower()
    if want == DEVICE_CPU:
        return DEVICE_CPU, COMPUTE_CPU
    if want == DEVICE_VULKAN:
        if vulkan_speech.best_device() is not None:
            return DEVICE_VULKAN, "float16"
        raise VulkanUnavailable(t("No usable AMD Vulkan device was found. Check the AMD driver."))
    if want == DEVICE_CUDA:
        if cuda_available():
            return DEVICE_CUDA, COMPUTE_CUDA
        missing = cuda_runtime.missing_libraries()
        if missing:
            if cuda_driver_present():
                raise CudaUnavailable(t("GPU support is not downloaded yet. Install it from Settings, Speech to text, or switch the device to Automatic."))
            raise CudaUnavailable(t("CUDA libraries are missing or cannot load (packaging/dependency problem): {libraries}",
                                    libraries=', '.join(missing)))
        try:
            import ctranslate2
            count = ctranslate2.get_cuda_device_count()
        except Exception as exc:
            raise CudaUnavailable(t("CTranslate2 CUDA initialization failed: {error}", error=exc)) from exc
        raise CudaUnavailable(t("No usable NVIDIA GPU/driver was found (CUDA devices: {count}).", count=count))
    if cuda_available():
        return DEVICE_CUDA, COMPUTE_CUDA
    if vulkan_speech.available():
        return DEVICE_VULKAN, "float16"
    return DEVICE_CPU, COMPUTE_CPU


def describe_device(preference=DEVICE_AUTO, *, resolved=None):
    """Short human line naming the resolved device, for Settings and logs."""
    try:
        device, compute = resolved if resolved is not None else get_best_device(preference)
    except LocalSpeechError as exc:
        return str(exc)
    if device == DEVICE_CUDA:
        return f"Nvidia GPU (cuda, {compute})"
    if device == DEVICE_VULKAN:
        return f"{vulkan_speech.best_device()['name']} (Vulkan, whisper.cpp)"
    return f"CPU ({device}, {compute})"


def log_startup_device(preference=DEVICE_AUTO, enabled=True):
    """Log which device the local engine would use; never raises."""
    try:
        if not enabled:
            _log.info("local speech device: not in use (cloud engine selected)")
        else:
            _log.info("local speech device: %s", describe_device(preference))
    except Exception as exc:  # logging must never break startup
        _log.warning("local speech device: could not be determined (%s)",
                     type(exc).__name__)


def _is_cuda_library_error(exc):
    text = str(exc).lower()
    if any(hint in text for hint in _OOM_HINTS):
        return False
    return any(hint in text for hint in _CUDA_LIBRARY_HINTS)


# The last silent CUDA->CPU fallback, so the UI can say what happened.
_last_fallback_note = ""
_cuda_failed = False


def last_fallback_note():
    return vulkan_speech._failure_note or _last_fallback_note

# The three sizes, and what each is for. Measured on the machine this was
# written on (16 threads, no GPU) on Turkish dictation: base read a noisy take
# without a single error, small added an invented closing sentence,
# large-v3-turbo read it cleanly and invented nothing. The smallest Whisper size
# is not offered because it breaks words apart ("WordArc" -> "4.projesinin"), and
# a dictation the user has to read and fix is worse than no dictation at all.
MODEL_CHOICES = (
    ("base", "Systran/faster-whisper-base"),
    ("small", "Systran/faster-whisper-small"),
    ("large-v3-turbo", "mobiuslabsgmbh/faster-whisper-large-v3-turbo"),
)

# Only these make a model usable. The repository also carries the original
# float16 weights and a PyTorch export, several times the size of the
# CTranslate2 model, and this engine never loads them. The tokenizer comes as
# vocabulary.txt in the Systran repositories and as vocabulary.json in the turbo
# one, so either satisfies the check; listing only one is how a download finishes
# and then reports itself incomplete.
REQUIRED_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
ALSO_ACCEPTED = ("vocabulary.json", "preprocessor_config.json")
REQUIRED_ANY = ("vocabulary.txt", "vocabulary.json")

# One engine per process, shared. Loading a model is seconds of work (measured:
# 2.8 s for large-v3-turbo, 0.9 s for small) and the dictation hotkey can be
# pressed twice in a row, so a per-call load would be felt as a stall on the
# second take. Switching model replaces it and the old one is dropped.
_lock = threading.Lock()
_download_lock = threading.Lock()
_model = None
_model_name = ""
_model_device = ("", "")


class LocalSpeechError(Exception):
    """Anything that keeps the local engine from answering."""


class CudaUnavailable(LocalSpeechError):
    """An explicit CUDA request needs user consent before switching to CPU."""


class VulkanUnavailable(CudaUnavailable):
    """Share the existing GUI consent broker for explicit AMD GPU failures."""


class Cancelled(LocalSpeechError):
    """The user asked to stop; the caller treats it as a stop, not a failure."""


def human_size(num_bytes):
    """A download size as the user would say it: 142 MB, 1,6 GB.

    Rounded to a size anyone can act on — a file count rounded to the megabyte
    reads as false precision next to a figure like "1,6 GB", and this string
    goes in front of a button that starts the download.
    """
    if num_bytes >= 1024 ** 3:
        value = num_bytes / 1024 ** 3
        text = f"{value:.1f}".rstrip("0").rstrip(".")
        return f"{text.replace('.', ',')} GB"
    if num_bytes >= 1024 ** 2:
        return f"{round(num_bytes / 1024 ** 2)} MB"
    if num_bytes:
        return f"{round(num_bytes / 1024)} KB"
    return ""


@dataclass(frozen=True)
class ModelState:
    name: str
    installed: bool
    size: int          # bytes on disk, 0 when absent
    expected: int = 0  # roughly the download, for the label
    path: str = ""


def default_model():
    return "large-v3-turbo"


# The two ways a take can be read. The label is the user's own phrasing: where
# the work happens, not which library does it.
ENGINES = (
    ("Cloud (Gemini)", "cloud"),
    ("Live (Gemini)", "live"),
    ("Local (this computer)", "local"),
)

# What each size costs to download, measured from the files actually fetched.
# The box and the status line quote the same number, so a user who reads
# "1,6 GB" in the list and "1,5 GB" underneath does not stop to wonder which is
# right.
EXPECTED_SIZES = {
    "base": 147_882_941,          # 141 MB
    "small": 486_391_123,         # 464 MB
    "large-v3-turbo": 1_620_000_000,  # 1,5 GB
}

# The same figures as the box writes them, in the interface language's decimal
# comma, so the two places cannot drift apart. The note is what the extra
# megabytes actually buy, measured on one hard Turkish take (50 words: a
# product name, two acronyms, a number spelled in words, a closing question):
#   base 43/50 at 18x realtime, small 42/50 at 9x, large-v3-turbo 43/50 at 4x
# turbo is the safest pick on the hardest audio, not on every take — it is the
# one that never mangled a product name into two words or added a closing
# sentence. base is listed as quick, not as wrong: it scored the same here.
MODEL_NOTES = {
    "base": "quick, 141 MB",
    "small": "middle, 464 MB",
    "large-v3-turbo": "hardest audio, 1,5 GB",
}


def model_label(name):
    """(label, note) for the model box: the name and what it costs."""
    return f"Whisper {name}", MODEL_NOTES.get(name, "")


def model_names():
    return [name for name, _repo in MODEL_CHOICES]


def _repo(name):
    return dict(MODEL_CHOICES).get(name)


def models_dir():
    import config
    return config.DATA_DIR / "whisper"


def _root(name, where=None):
    repo = _repo(name)
    if repo is None:
        return ""
    if where is None:
        import speech_sources
        selected = speech_sources.selected("ct2", name)
        if selected is not None:
            return str(selected)
    return os.path.join(str(where or models_dir()), repo.replace("/", "--"))


def _is_installed(name, where=None):
    if where is None:
        import speech_sources
        if speech_sources.selected("ggml", name) is not None:
            return False  # An explicit shared GGML choice wins over managed CT2.
    root = _root(name, where)
    if not root:
        return False
    if not all(os.path.exists(os.path.join(root, part)) for part in REQUIRED_FILES
               if part not in REQUIRED_ANY):
        return False
    # One tokenizer file is enough; which one depends on the repository.
    return any(os.path.exists(os.path.join(root, part)) for part in REQUIRED_ANY)


def _dir_size(path):
    total = 0
    with contextlib.suppress(OSError):
        for entry in os.scandir(path):
            with contextlib.suppress(OSError):
                total += entry.stat().st_size
    return total


def _expected_size(name):
    return EXPECTED_SIZES.get(name, 0)


def state(name, where=None, device_preference=None):
    """What Settings shows: on disk or not, and how much room it takes."""
    if _repo(name) is None:
        return ModelState(name, False, 0)
    if (model_backend(device_preference) == DEVICE_VULKAN or
            ((device_preference == DEVICE_CPU or device_preference == DEVICE_AUTO and not cuda_available()) and not _is_installed(name, where)
             and vulkan_speech.installed(name, where))):
        path = vulkan_speech.model_path(name, where)
        installed = vulkan_speech.installed(name, where)
        return ModelState(name, installed, path.stat().st_size if installed else 0,
                          vulkan_speech.MODEL_SIZES[name], str(path))
    if not _is_installed(name, where):
        return ModelState(name, False, 0, _expected_size(name))
    return ModelState(name, True, _dir_size(_root(name, where)),
                      _expected_size(name), _root(name, where))


def installed_size(where=None):
    """Bytes the installed models take, for the settings summary."""
    return sum(state(name, where).size for name in model_names()) + _dir_size(vulkan_speech.model_root(where))


def model_backend(preference=None):
    """Storage format selected for Settings; omitted preference preserves CT2 API."""
    if preference is None:
        return DEVICE_CPU
    if preference == DEVICE_VULKAN:
        return DEVICE_VULKAN
    if preference == DEVICE_AUTO and not cuda_available() and vulkan_speech.available():
        return DEVICE_VULKAN
    # Keep downloaded GGML available after a session fallback on AMD.
    if preference == DEVICE_AUTO and vulkan_speech._failed:
        return DEVICE_VULKAN
    return DEVICE_CPU


def _fail(message, **kwargs):
    raise LocalSpeechError(t(message, **kwargs) if kwargs else t(message))


@dataclass(frozen=True)
class DownloadProgress:
    name: str
    completed: int
    total: int
    speed: float
    remaining: float | None
    filename: str = ""
    phase: str = "download"


def _download_manifest(name):
    # Storage names stay unchanged so existing turbo installations still work.
    repo = "dropbox-dash/faster-whisper-large-v3-turbo" if name == "large-v3-turbo" else _repo(name)
    url = f"https://huggingface.co/api/models/{repo}?blobs=true"
    with _download_open(url) as response:
        manifest = json.load(response)
    revision = manifest["sha"]
    wanted = set(REQUIRED_FILES + ALSO_ACCEPTED)
    files = [row for row in manifest["siblings"] if row["rfilename"] in wanted]
    names = {row["rfilename"] for row in files}
    if not set(REQUIRED_FILES).difference(REQUIRED_ANY).issubset(names) or not names.intersection(REQUIRED_ANY):
        raise ValueError("Model repository is missing required files")
    # Commit the weights last, after all support files have been verified.
    files.sort(key=lambda row: row["rfilename"] == "model.bin")
    return repo, revision, files


def _download_open(url, offset=0):
    import certifi
    headers = {"User-Agent": "WordArc", "Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=30,
                                  context=ssl.create_default_context(cafile=certifi.where()))


def _valid_download(path, row):
    if not os.path.isfile(path) or os.path.getsize(path) != row["size"]:
        return False
    lfs = row.get("lfs") or {}
    algorithm = "sha256" if lfs.get("sha256") else "sha1"
    expected = lfs.get("sha256") or row.get("blobId")
    if not expected:
        return False
    digest = hashlib.new(algorithm)
    if algorithm == "sha1":
        digest.update(f"blob {row['size']}\0".encode())
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == expected


def download(name, where=None, should_stop=None, on_progress=None, device_preference=None, force=False):
    if model_backend(device_preference) == DEVICE_VULKAN:
        return vulkan_speech.download(name, where, should_stop, on_progress, force=force)
    # A closed window's worker may still be unwinding an HTTP read. A new
    # window must not append to the same part until that worker has stopped.
    while not _download_lock.acquire(timeout=0.1):
        _check_cancelled(should_stop)
    try:
        _check_cancelled(should_stop)
        return _download_model(name, where, should_stop, on_progress, force=force)
    finally:
        _download_lock.release()


def _download_model(name, where=None, should_stop=None, on_progress=None, backend=None, force=False):
    """Stream verified files with byte progress, cancellation and resumable parts."""
    if _repo(name) is None:
        _fail("Unknown local model: {name}", name=name)
    using_vulkan = backend == DEVICE_VULKAN
    is_installed = lambda: vulkan_speech.installed(name, where) if using_vulkan else _is_installed(name, where)
    if is_installed() and not force:
        return 0
    # Download only into our managed storage, never over a linked shared model.
    root = str(vulkan_speech.model_root(where)) if using_vulkan else _root(name, where or models_dir())
    os.makedirs(root, exist_ok=True)
    started = time.monotonic()
    received = 0
    completed = total = 0
    last_notice = 0.0
    def report(filename="", phase="download", force=False):
        nonlocal last_notice
        now = time.monotonic()
        if on_progress and (force or now - last_notice >= 0.15):
            speed = received / max(now - started, 0.001)
            remaining = (total - completed) / speed if speed > 0 and total else None
            on_progress(DownloadProgress(name, completed, total, speed, remaining, filename, phase))
            last_notice = now
    try:
        _check_cancelled(should_stop)
        report(phase="connecting", force=True)
        if using_vulkan:
            repo = vulkan_speech.MODEL_REPO
            with _download_open(f"https://huggingface.co/api/models/{repo}?blobs=true") as response:
                manifest = json.load(response)
            revision = manifest["sha"]
            files = [row for row in manifest["siblings"]
                     if row["rfilename"] == vulkan_speech.MODEL_FILES[name]]
            if len(files) != 1 or not files[0].get("lfs", {}).get("sha256"):
                raise ValueError("Vulkan model metadata/checksum is missing")
        else:
            repo, revision, files = _download_manifest(name)
        total = sum(row["size"] for row in files)
        for row in files:
            _check_cancelled(should_stop)
            filename = row["rfilename"]
            target = os.path.join(root, filename)
            part = target + f".{revision[:12]}.part"
            if not force and _valid_download(target, row):
                completed += row["size"]
                report(filename, force=True)
                continue
            offset = os.path.getsize(part) if os.path.exists(part) else 0
            if offset > row["size"]:
                offset = 0
                with open(part, "wb"):
                    pass
            if shutil.disk_usage(root).free < row["size"] - offset + 16 * 1024 * 1024:
                _fail("Not enough disk space for the local model.")
            completed += offset
            for attempt in range(3):
                try:
                    if offset < row["size"]:
                        url = f"https://huggingface.co/{repo}/resolve/{revision}/{urllib.parse.quote(filename)}?download=true"
                        with _download_open(url, offset) as response:
                            status = response.status
                            if offset and status == 200:
                                completed -= offset
                                offset = 0
                            elif offset and (status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")):
                                raise ValueError("Invalid resume response")
                            with open(part, "ab" if offset else "wb") as stream:
                                while True:
                                    _check_cancelled(should_stop)
                                    block = response.read(256 * 1024)
                                    if not block:
                                        break
                                    _check_cancelled(should_stop)
                                    stream.write(block)
                                    offset += len(block)
                                    completed += len(block)
                                    received += len(block)
                                    if offset > row["size"]:
                                        raise ValueError("Downloaded file exceeds expected size")
                                    report(filename)
                    report(filename, "verifying", True)
                    if not _valid_download(part, row):
                        if offset >= row["size"]:
                            completed -= offset
                            offset = 0
                            with open(part, "wb"):
                                pass
                        raise ValueError("Download size or checksum mismatch")
                    os.replace(part, target)
                    break
                except Cancelled:
                    raise
                except Exception:
                    if attempt == 2:
                        raise
                    report(filename, "retrying", True)
                    # Wait in small increments so cancellation remains responsive.
                    for _ in range(5 * (attempt + 1)):
                        _check_cancelled(should_stop)
                        time.sleep(0.1)
            report(filename, force=True)
        if where is None:
            import speech_sources
            speech_sources.link("ggml" if using_vulkan else "ct2", name, None)
        if not is_installed():
            _fail("The local model downloaded incompletely. Try again.")
        report(phase="complete", force=True)
        return _dir_size(root)
    except Cancelled:
        raise
    except LocalSpeechError:
        raise
    except Exception as exc:
        # Retain verified files and revision-specific partial files for retry.
        _log.warning("local download failed (%s)", type(exc).__name__)
        _fail("Could not download the local model: {error}", error=str(exc))


def remove(name, where=None, device_preference=None):
    """Delete a model from disk. True when something was there."""
    if where is None:
        import speech_sources
        for kind in ("ct2", "ggml"):
            if speech_sources.selected(kind, name) is not None:
                speech_sources.link(kind, name, None)
                return True  # Disconnect: another application's files stay intact.
    if (model_backend(device_preference) == DEVICE_VULKAN or
            ((device_preference == DEVICE_CPU or device_preference == DEVICE_AUTO and not cuda_available()) and not _is_installed(name, where)
             and vulkan_speech.installed(name, where))):
        if name not in vulkan_speech.MODEL_FILES:
            return False
        path = vulkan_speech.model_path(name, where)
        if path.is_file():
            path.unlink()
            return True
        return False
    root = _root(name, where)
    if not root or not os.path.isdir(root):
        return False
    shutil.rmtree(root, ignore_errors=True)
    return True


def _check_cancelled(should_stop):
    if should_stop is not None and should_stop():
        raise Cancelled(t("Stopped."))


def _load_model(path, device, compute_type):
    from faster_whisper import WhisperModel
    # faster-whisper's own downloader is deliberately bypassed. It
    # would look the model up by name in the huggingface cache, which
    # is a different layout from the one download() writes, so the
    # engine went looking for a snapshot the app never created. Handing
    # it the directory we filled is the whole point of doing the
    # download ourselves.
    return WhisperModel(path, device=device, compute_type=compute_type,
                        cpu_threads=THREADS)


def engine(name, where=None, device_preference=None):
    """The loaded model, or an error saying what the user should do.

    ``where`` is where the models live; the app always uses the default, and a
    test passes its own directory so a run never touches the real one.
    ``device_preference`` is the Settings choice (auto/cuda/cpu); every load
    resolves it through get_best_device(), so there is exactly one place
    that picks a device.
    """
    global _model, _model_name, _model_device, _last_fallback_note, _cuda_failed
    name = name or default_model()
    if _repo(name) is None:
        _fail("Unknown local model: {name}", name=name)
    preference = device_preference or DEVICE_AUTO
    if _cuda_failed and preference == DEVICE_AUTO:
        device, compute_type = DEVICE_CPU, COMPUTE_CPU
    else:
        device, compute_type = get_best_device(preference)
    if device == DEVICE_VULKAN:
        # This function owns the CTranslate2 cache; Vulkan uses an isolated
        # native process through transcribe(), never a CT2 Vulkan device.
        device, compute_type = DEVICE_CPU, COMPUTE_CPU
    with _lock:
        source = _root(name, where)
        if (_model is not None and _model_name == name
                and getattr(engine, "_source", "") == source
                and _model_device == (device, compute_type)):
            return _model
        if not _is_installed(name, where):
            _fail("The local model {name} is not installed yet. Download it "
                  "in Settings.", name=name)
        try:
            _model = _load_model(source, device, compute_type)
        except ImportError as exc:
            _model, _model_name, _model_device = None, "", ("", "")
            if device == DEVICE_CUDA:
                raise CudaUnavailable(t("CTranslate2/local engine could not load: {error}", error=exc)) from exc
            _fail("CTranslate2/local engine could not load: {error}", error=exc)
        except Exception as exc:  # ctranslate2 raises bare RuntimeError
            if device == DEVICE_CUDA and preference == DEVICE_CUDA:
                _model, _model_name, _model_device = None, "", ("", "")
                raise CudaUnavailable(t("CUDA initialization failed: {error}", error=exc)) from exc
            if device == DEVICE_CUDA and _is_cuda_library_error(exc):
                # The CUDA libraries (cuBLAS/cuDNN/runtime) are missing, not
                # the GPU: run on the CPU and say so in the log instead of
                # failing the dictation. Anything else — out of memory
                # included — is a real failure and goes up unchanged.
                _last_fallback_note = (
                    f"CUDA load failed ({exc}); using CPU instead.")
                _cuda_failed = True
                _log.warning("local speech: %s", _last_fallback_note)
                try:
                    _model = _load_model(source, DEVICE_CPU,
                                         COMPUTE_CPU)
                except Exception as cpu_exc:
                    _model, _model_name, _model_device = None, "", ("", "")
                    _fail("Could not load the local model: {error}",
                          error=cpu_exc)
                device, compute_type = DEVICE_CPU, COMPUTE_CPU
            else:
                _model, _model_name, _model_device = None, "", ("", "")
                _fail("Could not load the local model: {error}", error=exc)
        _log.info("local speech device: %s (%s) for model %s",
                  device, compute_type, name)
        _model_name = name
        engine._source = source
        _model_device = (device, compute_type)
        if device == DEVICE_CUDA:
            _last_fallback_note = ""
            _cuda_failed = False
        return _model


def transcribe(name, wav_path, language="", prompt="", should_stop=None,
               with_segments=False, where=None, device_preference=None):
    """The transcript of one WAV file.

    Same arguments as the cloud call, so a caller that already speaks to a
    transcriber can be pointed here by changing one name. ``with_segments``
    asks for [(start, end, text)] instead of a single string, which the callers
    that lay out a timeline need and the dictation path does not.
    """
    preference = device_preference or DEVICE_AUTO
    name = name or default_model()
    if _repo(name) is None:
        _fail("Unknown local model: {name}", name=name)
    use_vulkan = (preference == DEVICE_VULKAN or
                  (preference == DEVICE_AUTO and not cuda_available() and
                   (vulkan_speech.available() or vulkan_speech._failed)))
    if (preference == DEVICE_AUTO and use_vulkan and
            not vulkan_speech.installed(name, where) and _is_installed(name, where)):
        # Upgrading an AMD PC must not break its already-working CPU model.
        use_vulkan = False
        device_preference = DEVICE_CPU
    # A saved CPU choice can use an already downloaded GGML model, so recovery
    # never needs a second multi-GB download in order to retry the same audio.
    ggml_cpu = ((preference == DEVICE_CPU or (preference == DEVICE_AUTO and not cuda_available() and not use_vulkan))
                and not _is_installed(name or default_model(), where)
                and vulkan_speech.installed(name or default_model(), where))
    if use_vulkan or ggml_cpu:
        name = name or default_model()
        gpu = use_vulkan and (preference == DEVICE_VULKAN or not vulkan_speech._failed)
        try:
            return vulkan_speech.transcribe(name, wav_path, language, prompt, should_stop,
                                           with_segments, where, use_gpu=gpu)
        except vulkan_speech.VulkanError as exc:
            if preference == DEVICE_VULKAN:
                raise VulkanUnavailable(str(exc)) from exc
            if not gpu:
                _fail("Local transcription failed: {error}", error=exc)
            vulkan_speech.fail(str(exc))
            _check_cancelled(should_stop)
            try:
                return vulkan_speech.transcribe(name, wav_path, language, prompt, should_stop,
                                               with_segments, where, use_gpu=False)
            except vulkan_speech.VulkanError as cpu_exc:
                _fail("Local transcription failed: {error}", error=cpu_exc)
    model = engine(name, where, device_preference)
    audio = _read_wav(wav_path)
    # A zero-length take makes Whisper answer with something invented, which is
    # the one failure the app's own silence check exists to prevent; fail here
    # rather than hand back a sentence nobody said.
    if not len(audio):
        _fail("The recording was empty.")
    _check_cancelled(should_stop)
    options = dict(beam_size=5,
                   # Whisper feeds its own output back in as context for the
                   # next window, and on a stream of dictation that is how one
                   # take turns into the same closing sentence twice. Nothing
                   # here needs the previous window.
                   condition_on_previous_text=False,
                   initial_prompt=prompt or None)
    if with_segments:
        options["word_timestamps"] = True
    language = None if language in ("", "auto", None) else language
    def decode(instance):
        # A generator, not a list: only the first window is decoded at this
        # point, and the rest happens as it is walked.
        segments, _info = instance.transcribe(audio, language=language, **options)
        if with_segments:
            out = []
            for seg in segments:
                _check_cancelled(should_stop)
                out.append((seg.start, seg.end, seg.text.strip()))
            return out
        out = []
        for seg in segments:
            _check_cancelled(should_stop)
            out.append(seg.text.strip())
        return " ".join(out).strip()

    try:
        return decode(model)
    except LocalSpeechError:
        raise
    except Exception as exc:
        # cuBLAS/cuDNN often load lazily during language detection or while
        # iterating segments, after WhisperModel construction succeeded.
        device = getattr(getattr(model, "model", None), "device", None)
        if model is _model:
            device = _model_device[0]
        if device == DEVICE_CUDA and device_preference == DEVICE_CUDA:
            raise CudaUnavailable(t("CUDA transcription failed: {error}", error=exc)) from exc
        if device == DEVICE_CUDA and _is_cuda_library_error(exc):
            global _last_fallback_note, _cuda_failed
            _last_fallback_note = f"CUDA transcription failed ({exc}); using CPU instead."
            _cuda_failed = True
            _log.warning("local speech: %s", _last_fallback_note)
            _check_cancelled(should_stop)
            cpu = engine(name, where, DEVICE_CPU)
            try:
                # Discard partial GPU output and restart the whole recording.
                return decode(cpu)
            except LocalSpeechError:
                raise
            except Exception as cpu_exc:
                _fail("Local transcription failed: {error}", error=cpu_exc)
        _fail("Local transcription failed: {error}", error=exc)


def _read_wav(path):
    """The file as float32 in -1..1, which is the array Whisper takes."""
    import numpy
    with contextlib.closing(wave.open(path, "rb")) as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        _fail("The local model reads 16-bit audio.")
    if rate != RATE:
        _fail("The local model reads {rate} kHz audio, but this recording is "
              "{actual} kHz.", rate=16, actual=round(rate / 1000))
    samples = numpy.frombuffer(raw, dtype=numpy.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels)[:, 0]
    return samples.astype(numpy.float32) / 32768.0


# --- the bridge the app calls ---------------------------------------------

def transcribe_for(conf, wav_path, language="", prompt="", should_stop=None,
                   with_segments=False, client=None):
    """Transcribe with whichever engine the settings ask for.

    The cloud and the local engine answer the same question, so every caller
    goes through this and switching engines in Settings changes all of them at
    once.

    A local failure never falls through to the cloud. Choosing the local engine
    is the user saying the audio does not leave this computer; quietly
    uploading it after a local error would break that promise without telling
    them, so the error is surfaced instead and the settings say what to do.

    ``client`` is the caller's own GeminiClient, carrying its failover
    callbacks; one is built here when the caller has none.
    """
    if conf.get("transcribe_engine", "cloud") != "local":
        engine = conf.get("transcribe_engine", "cloud")
        if engine == "live":
            # Live streams the microphone; a recording handed over afterwards
            # has no live session, so the cloud REST path transcribes it.
            # Both send audio to Google, so no privacy promise breaks.
            _log.info("live engine chosen for recorded audio; using the cloud")
        return _cloud(conf, wav_path, language, prompt, should_stop,
                      with_segments, client)
    name = conf.get("local_stt_model") or default_model()
    device_preference = conf.get("local_stt_device") or DEVICE_AUTO
    try:
        previous = getattr(conf, '_cuda_failure', None)
        if (device_preference in (DEVICE_CUDA, DEVICE_VULKAN) and previous is not None
                and getattr(conf, '_cuda_failure_device', device_preference) == device_preference):
            raise previous
        return transcribe(name, wav_path, language, prompt, should_stop,
                          with_segments, device_preference=device_preference)
    except Cancelled:
        raise
    except CudaUnavailable as exc:
        conf._cuda_failure = exc
        conf._cuda_failure_device = device_preference
        recovery = getattr(conf, '_cuda_recovery', None)
        if recovery is not None and recovery(str(exc), should_stop):
            _check_cancelled(should_stop)
            return transcribe(name, wav_path, language, prompt, should_stop,
                              with_segments, device_preference=DEVICE_CPU)
        raise
    except LocalSpeechError as exc:
        _log.warning("local engine could not answer (%s); not sending the "
                     "audio to the cloud, because local was chosen", exc)
        raise


def _cloud(conf, wav_path, language, prompt, should_stop, with_segments,
           client=None):
    if client is None:
        import api
        client = api.GeminiClient(conf.gemini_keys(), should_stop=should_stop)
    text = client.transcribe(conf["gemini_transcribe_model"], wav_path,
                             language=language, prompt=prompt)
    if not with_segments:
        return text
    # The cloud engine reports no timings, and a caller that needs a timeline
    # chunks the audio itself and places each chunk at its own offset, so one
    # entry carrying the whole chunk is exactly what it expects.
    return [(0.0, 0.0, text.strip())]
