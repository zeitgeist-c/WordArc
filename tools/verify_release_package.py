"""Verify delivery names and the version embedded in the actual executable."""
import hashlib
import sys
import types
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brand import BRAND


def constants(code):
    yield code.co_name
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            yield from constants(value)
        else:
            yield value


def main():
    root = Path(__file__).resolve().parents[1]
    exe = root / "dist" / f"{BRAND.name}-{BRAND.version}.exe"
    bat = exe.with_suffix(".bat")
    assert exe.is_file() and bat.is_file(), "missing delivery files"
    launcher = bat.read_text(encoding="utf-8")
    assert f'%~dp0{exe.name}' in launcher and "%*" in launcher
    reader = CArchiveReader(str(exe))
    assert not any(Path(name).name.lower() in {"icuuc.dll", "icuin.dll"} for name in reader.toc), "OS ICU shadowed"
    archive = reader.open_embedded_archive("PYZ.pyz")
    assert BRAND.version in list(constants(archive.extract("brand"))), "wrong embedded version"
    assert "set_recording_state" in list(constants(archive.extract("settings_ui")))
    for name in ("settings_ui", "theme", "worker", "localspeech", "faster_whisper"):
        assert name in archive.toc, f"missing bundled module: {name}"
    print(f"PACKAGE OK: {exe.name} + {bat.name}")
    with exe.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    print(f"SHA256: {digest}")

if __name__ == "__main__":
    main()
