"""Package the on-demand CUDA runtime zip (operator-run, not every build).

Verifies the venv NVIDIA wheels match assets/cuda/cuda-libs.json, zips the
``nvidia/`` tree preserving its layout, and writes the hash manifest to
tools/vendor/cuda-manifest.json (bundled into the frozen app via
wordarc.spec so cuda_libs.py can verify the download).

The zip itself (~1 GB) is uploaded by hand to the release tag named in the
pins file (default ``cuda-libs-v1``) on the public WordArc repo:

  gh release upload cuda-libs-v1 tools/vendor/WordArc-CudaLibs.zip --clobber

Re-run only when the pinned wheels change; the tag is bumped then too.

Usage: python tools/build_cuda_libs.py
"""

from __future__ import annotations

import hashlib
import json
import sysconfig
import zipfile
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = json.loads((ROOT / "assets" / "cuda" / "cuda-libs.json").read_text())
VENDOR = ROOT / "tools" / "vendor"
ZIP_NAME = PINS["file"]
MANIFEST_NAME = "cuda-manifest.json"


def _wheel_version(dist: str) -> str:
    return metadata.version(dist)


def main() -> None:
    for dist, pinned in PINS["wheels"].items():
        actual = _wheel_version(dist)
        if actual != pinned:
            raise SystemExit(
                f"{dist}=={actual} does not match pins {pinned}; "
                "update assets/cuda/cuda-libs.json (and the tag) first.")
    site = Path(sysconfig.get_path("purelib"))
    src = site / "nvidia"
    if not src.is_dir():
        raise SystemExit(f"no nvidia tree in {site}")
    VENDOR.mkdir(parents=True, exist_ok=True)
    archive = VENDOR / ZIP_NAME
    if archive.is_file():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(src.rglob("*")):
            if path.is_file() and not any(
                    part.endswith(".dist-info") for part in path.parts):
                bundle.write(path, path.relative_to(site))
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    manifest = {"tag": PINS["tag"], "file": ZIP_NAME,
                "sha256": digest.hexdigest(), "size": archive.stat().st_size,
                "wheels": PINS["wheels"]}
    (VENDOR / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")
    size_gb = archive.stat().st_size / 1024 ** 3
    print(f"cuda libs zip: {archive} ({size_gb:.2f} GB)")
    print(f"manifest: {VENDOR / MANIFEST_NAME}")
    print(f"upload: gh release upload {PINS['tag']} {archive} --clobber")


if __name__ == "__main__":
    main()
