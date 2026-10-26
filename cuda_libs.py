"""On-demand CUDA runtime for NVIDIA GPUs.

The frozen package carries no CUDA DLLs (2 GB uncompressed). When the user
asks for the GPU, this module fetches a pinned zip from the release depot,
verifies its hash, and extracts it under %LOCALAPPDATA%/WordArc/cuda/<tag>.
``cuda_runtime`` picks that directory up on its next scan, so no restart
and no PATH change is needed. Machines without NVIDIA keep running on CPU
and never download a byte.
"""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

import cuda_runtime
from i18n import t

_log = logging.getLogger("wordarc.cuda_libs")

RELEASE_REPO = "zeitgeist-c/WordArc"


def _pins_path() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        from brand import resource_path
        return resource_path("models", "cuda", "cuda-libs.json")
    return Path(__file__).resolve().parent / "assets" / "cuda" / "cuda-libs.json"


def pins() -> dict:
    """Build pins (tag, file, wheels); sha256 joins after build vendoring."""
    raw = _pins_path().read_text(encoding="utf-8")
    data = json.loads(raw)
    bundled = _bundled_manifest_path()
    if bundled.is_file():
        try:
            extra = json.loads(bundled.read_text(encoding="utf-8"))
            data = {**data, **extra}
        except (OSError, ValueError):
            pass
    return data


def _bundled_manifest_path() -> Path:
    from brand import resource_path
    return resource_path("models", "cuda", "cuda-manifest.json")


def libs_dir() -> Path:
    import config
    return config.DATA_DIR / "cuda" / str(pins().get("tag", "cuda-libs-v1"))


def download_url() -> str:
    data = pins()
    return (f"https://github.com/{RELEASE_REPO}/releases/download/"
            f"{data['tag']}/{data['file']}")


def download_size() -> int:
    try:
        return int(pins().get("size", 0))
    except (TypeError, ValueError):
        return 0


def installed() -> bool:
    """True when the data-dir copy holds every DLL the engine loads."""
    root = libs_dir()
    if not root.is_dir():
        return False
    present = {path.name.lower() for path in root.rglob("*.dll")}
    return all(name.lower() in present for name in cuda_runtime.LIBRARIES)


def available() -> bool:
    """True when the engine can load CUDA right now, from anywhere."""
    return not cuda_runtime.missing_libraries()


def offer(preference: str | None) -> bool:
    """True when offering the GPU download makes sense in Settings."""
    import localspeech
    if (preference or "auto").lower() not in ("auto", "cuda"):
        return False
    if available():
        return False
    return localspeech.cuda_driver_present()


class CudaLibsError(Exception):
    """Anything the user must hear about the GPU support download."""


def ensure(progress=None, should_stop=None) -> Path:
    """Download and extract the runtime; returns its directory.

    ``progress`` takes ``(completed, total)`` bytes. Raises
    ``CudaLibsError`` with a user-readable message on any failure; a
    half-written directory is removed so the next attempt starts clean.
    """
    import update as update_mod

    data = pins()
    try:
        sha256 = data["sha256"]
    except KeyError as exc:
        raise CudaLibsError(
            t("GPU support has no verified build yet.")) from exc
    root = libs_dir()
    if installed():
        return root
    info = update_mod.UpdateInfo(
        version=str(data["tag"]), asset_name=str(data["file"]),
        download_url=download_url(), sha256=sha256,
        size=download_size(), page_url="")
    tmp = Path(tempfile.mkdtemp(prefix="wordarc-cuda-"))
    archive = tmp / data["file"]
    try:
        def _progress(done, total):
            if progress is not None:
                progress(done, total)
            if should_stop is not None and should_stop():
                raise _Cancelled()
        try:
            update_mod.download(info, archive, progress=_progress)
        except update_mod.UpdateError as exc:
            if str(exc) == "cancelled" or isinstance(exc, _Cancelled):
                raise CudaLibsError(t("cancelled"))
            raise CudaLibsError(str(exc)) from exc
        except _Cancelled:
            raise CudaLibsError(t("cancelled"))
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(root)
        except (zipfile.BadZipFile, OSError) as exc:
            shutil.rmtree(root, ignore_errors=True)
            raise CudaLibsError(
                t("The GPU support file is damaged. Try again.")) from exc
        if not installed():
            shutil.rmtree(root, ignore_errors=True)
            raise CudaLibsError(
                t("The GPU support file is incomplete. Try again."))
        _drop_older_tags(root.parent)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    _log.info("cuda libs ready: %s", root)
    return root


class _Cancelled(Exception):
    pass


def _drop_older_tags(base: Path) -> None:
    """Remove superseded tag dirs; the models next door are untouched."""
    keep = libs_dir().name
    with contextlib.suppress(OSError):
        for entry in base.iterdir():
            if entry.is_dir() and entry.name != keep:
                shutil.rmtree(entry, ignore_errors=True)
