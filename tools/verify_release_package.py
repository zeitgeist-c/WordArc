"""Verify the setup delivery and the frozen app inside it.

Layout since the Inno Setup migration:
  dist/WordArc-X.Y.Z.exe  -- the Inno installer (the only release asset)
  dist/inner/WordArc.exe  -- the frozen app, fixed name, packed by Inno

No versioned portable exe and no BAT launcher may remain in dist/.
User data (%APPDATA%/WordArc, %LOCALAPPDATA%/WordArc: recordings,
meetings, models) is outside the installer and is asserted as preserved
by tests/test_install_migration.py on the .iss source.
"""
import hashlib
import marshal
import time
import sys
import types
import subprocess
import os
import tempfile
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


def normalized(code):
    return code.replace(co_filename="", co_consts=tuple(
        normalized(value) if isinstance(value, types.CodeType) else value
        for value in code.co_consts))


def main():
    root = Path(__file__).resolve().parents[1]
    setup = root / "dist" / f"{BRAND.name}-{BRAND.version}.exe"
    inner = root / "dist" / "inner" / "WordArc.exe"
    assert setup.is_file(), "missing setup delivery"
    assert inner.is_file(), "missing inner frozen app"
    leftover_bats = sorted((root / "dist").glob(f"{BRAND.name}-*.bat"))
    assert not leftover_bats, f"portable launcher remains: {leftover_bats}"
    leftover_portables = [p for p in (root / "dist").glob(f"{BRAND.name}-*.exe")
                          if p != setup]
    assert not leftover_portables, f"portable exe remains: {leftover_portables}"
    # The installer must carry the app, not an empty shell: Inno compresses
    # ~1.5 GB down, but never below a third of the inner size.
    ratio = setup.stat().st_size / inner.stat().st_size
    assert 0.3 <= ratio <= 1.2, f"suspicious setup/inner size ratio: {ratio:.2f}"
    reader = CArchiveReader(str(inner))
    assert any(Path(name).name.lower() == 'unicodedata.pyd' for name in reader.toc), 'missing unicodedata extension'
    assert any(Path(name).name.lower() == 'ctranslate2.dll' for name in reader.toc), 'missing CTranslate2 runtime'
    import json
    import tools.build_vulkan as native
    assert native.verify(), 'unverified native Vulkan payload'
    manifest = json.loads((native.DEST / 'manifest.json').read_text())
    for name in native.FILES:
        key = next((key for key in reader.toc
                    if key.replace('\\', '/') == 'native/whisper-vulkan/' + name), None)
        assert key is not None, f'missing native Vulkan file: {name}'
        assert hashlib.sha256(reader.extract(key)).hexdigest() == manifest['files'][name], f'changed bundled native file: {name}'
    import pefile
    for name in native.FILES:
        if name.startswith('cpu/') and name.endswith(('.exe', '.dll')):
            dependencies = {row.dll.decode().lower() for row in pefile.PE(str(native.DEST / name)).DIRECTORY_ENTRY_IMPORT}
            assert 'vulkan-1.dll' not in dependencies and 'ggml-vulkan.dll' not in dependencies, 'CPU rescue depends on Vulkan'
    if '--cuda' in sys.argv:
        import cuda_runtime
        bundled = {Path(name.replace('\\', '/')).name.lower() for name in reader.toc}
        missing = {name.lower() for name in cuda_runtime.LIBRARIES} - bundled
        assert not missing, f'missing bundled CUDA DLLs: {sorted(missing)}'
    assert not any(Path(name).name.lower() in {"icuuc.dll", "icuin.dll"} for name in reader.toc), "OS ICU shadowed"
    # TTS weights ride inside the frozen app; first Speak use is offline.
    toc_slashes = {name.replace('\\', '/') for name in reader.toc}
    for name in ("text.onnx", "sound.onnx", "decoder.onnx", "meta.json"):
        assert f"models/ema-onnx/{name}" in toc_slashes, f'missing bundled TTS weight: {name}'
    archive = reader.open_embedded_archive("PYZ.pyz")
    entry_source = compile((root / 'wordarc.py').read_bytes(), 'wordarc.py',
                           'exec', dont_inherit=True)
    assert normalized(entry_source) == normalized(marshal.loads(reader.extract('wordarc'))), 'outdated bundled entry point'
    assert any(name.replace('\\', '/') == 'PyQt6/QtSvg.pyd'
               for name in reader.toc), 'missing vector splash renderer'
    assert BRAND.version in list(constants(archive.extract("brand"))), "wrong embedded version"
    assert "set_recording_state" in list(constants(archive.extract("settings_ui")))
    assert "PanelTabs" in list(constants(archive.extract("settings_ui"))), "old workspace layout bundled"
    for name in ("settings_ui", "screenshot_capture", "screenshot_editor", "ocr", "update", "theme", "worker", "localspeech", "livespeech", "cuda_runtime", "faster_whisper", "vulkan_speech", "local_stt_diagnostic"):
        assert name in archive.toc, f"missing bundled module: {name}"
    for name in ("brand", "hotkey", "paste", "settings_ui", "screenshot_capture", "screenshot_editor", "ocr", "update", "overlay", "localspeech", "livespeech", "vulkan_speech", "config", "i18n", "cuda_recovery", "local_stt_diagnostic"):
        source = compile((root / (name + '.py')).read_bytes(), name + '.py', 'exec', dont_inherit=True)
        # Code equality compares bytecode/constants recursively. marshal bytes
        # also encode incidental string interning/shared-reference identities,
        # which can differ after modules have been imported by this verifier.
        assert normalized(source) == normalized(archive.extract(name)), f'outdated bundled source: {name}'
    # Exercise the inner app in the actual delivery, with isolated data.
    # A GUI import-error dialog also fails this gate via the bounded timeout.
    with tempfile.TemporaryDirectory(prefix='wordarc-package-check-') as scratch:
        env = dict(os.environ, APPDATA=scratch, LOCALAPPDATA=scratch,
                   QT_QPA_PLATFORM='offscreen')
        started = time.perf_counter()
        result = subprocess.run([str(inner), '--version'], env=env,
                                capture_output=True, timeout=120)
        assert result.returncode == 0, f'packaged startup failed: {result.returncode}'
        print(f"Packaged --version wall time: {time.perf_counter() - started:.3f} s (includes extraction)")
    print(f"PACKAGE OK: {setup.name} (setup) + inner WordArc.exe")
    with setup.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    print(f"SHA256: {digest}")

if __name__ == "__main__":
    main()
