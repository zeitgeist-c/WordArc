"""Verify delivery names and the version embedded in the actual executable."""
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
    exe = root / "dist" / f"{BRAND.name}-{BRAND.version}.exe"
    bat = exe.with_suffix(".bat")
    assert exe.is_file() and bat.is_file(), "missing delivery files"
    launcher = bat.read_text(encoding="utf-8")
    assert f'%~dp0{exe.name}' in launcher and "%*" in launcher
    reader = CArchiveReader(str(exe))
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
    archive = reader.open_embedded_archive("PYZ.pyz")
    entry_source = compile((root / 'wordarc.py').read_bytes(), 'wordarc.py',
                           'exec', dont_inherit=True)
    assert normalized(entry_source) == normalized(marshal.loads(reader.extract('wordarc'))), 'outdated bundled entry point'
    assert any(name.replace('\\', '/') == 'PyQt6/QtSvg.pyd'
               for name in reader.toc), 'missing vector splash renderer'
    assert BRAND.version in list(constants(archive.extract("brand"))), "wrong embedded version"
    assert "set_recording_state" in list(constants(archive.extract("settings_ui")))
    assert "PanelTabs" in list(constants(archive.extract("settings_ui"))), "old workspace layout bundled"
    for name in ("settings_ui", "theme", "worker", "localspeech", "cuda_runtime", "faster_whisper", "vulkan_speech", "local_stt_diagnostic"):
        assert name in archive.toc, f"missing bundled module: {name}"
    for name in ("brand", "settings_ui", "localspeech", "vulkan_speech", "config", "i18n", "cuda_recovery", "local_stt_diagnostic"):
        source = compile((root / (name + '.py')).read_bytes(), name + '.py', 'exec', dont_inherit=True)
        # Code equality compares bytecode/constants recursively. marshal bytes
        # also encode incidental string interning/shared-reference identities,
        # which can differ after modules have been imported by this verifier.
        assert normalized(source) == normalized(archive.extract(name)), f'outdated bundled source: {name}'
    # Exercise imports in the actual delivery executable, with isolated data.
    # A GUI import-error dialog also fails this gate via the bounded timeout.
    with tempfile.TemporaryDirectory(prefix='wordarc-package-check-') as scratch:
        env = dict(os.environ, APPDATA=scratch, LOCALAPPDATA=scratch,
                   QT_QPA_PLATFORM='offscreen')
        started = time.perf_counter()
        result = subprocess.run([str(exe), '--version'], env=env,
                                capture_output=True, timeout=120)
        assert result.returncode == 0, f'packaged startup failed: {result.returncode}'
        print(f"Packaged --version wall time: {time.perf_counter() - started:.3f} s (includes extraction)")
    print(f"PACKAGE OK: {exe.name} + {bat.name}")
    with exe.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    print(f"SHA256: {digest}")

if __name__ == "__main__":
    main()
