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
    # Data-file layout prefix used by the TTS and CUDA checks below.
    toc_slashes = {name.replace('\\', '/') for name in reader.toc}
    if '--cuda' in sys.argv:
        import cuda_runtime
        # CUDA is on-demand since 0.10: the frozen app must NOT carry the
        # 2 GB NVIDIA tree; the download pins ride along instead.
        nvidia = [name for name in reader.toc
                  if name.replace('\\', '/').startswith('nvidia/')]
        assert not nvidia, f'CUDA runtime must be on-demand: {nvidia[:3]}'
        assert 'models/cuda/cuda-libs.json' in toc_slashes, 'missing cuda pins'
        assert 'models/cuda/cuda-manifest.json' in toc_slashes, 'missing cuda manifest'
        import json as _json
        def _data(name):
            key = next((entry for entry in reader.toc
                        if entry.replace('\\', '/') == name), None)
            assert key is not None, f'missing {name}'
            return key
        manifest = _json.loads(reader.extract(_data('models/cuda/cuda-manifest.json')))
        source_pins = _json.loads((root / 'assets' / 'cuda' / 'cuda-libs.json').read_text())
        assert 'models/cuda/cuda-libs.json' in toc_slashes, 'missing cuda pins'
        assert manifest['tag'] == source_pins['tag'], 'cuda manifest tag drifted'
        assert manifest['wheels'] == source_pins['wheels'], 'cuda manifest wheels drifted'
        assert len(manifest.get('sha256', '')) == 64, 'cuda manifest has no sha256'
        bundled = {Path(name.replace('\\', '/')).name.lower() for name in reader.toc}
        missing = {name.lower() for name in cuda_runtime.LIBRARIES} - bundled
        assert missing == {name.lower() for name in cuda_runtime.LIBRARIES}, \
            'unexpected CUDA DLLs bundled'
    assert not any(Path(name).name.lower() in {"icuuc.dll", "icuin.dll"} for name in reader.toc), "OS ICU shadowed"
    # TTS weights ride inside the frozen app; first Speak use is offline.
    for name in ("text.onnx", "sound.onnx", "decoder.onnx", "meta.json"):
        assert f"models/ema-onnx/{name}" in toc_slashes, f'missing bundled TTS weight: {name}'
    archive = reader.open_embedded_archive("PYZ.pyz")
    entry_source = compile((root / 'wordarc.py').read_bytes(), 'wordarc.py',
                           'exec', dont_inherit=True)
    assert normalized(entry_source) == normalized(marshal.loads(reader.extract('wordarc'))), 'outdated bundled entry point'
    assert any(name.replace('\\', '/') == 'PyQt6/QtSvg.pyd'
               for name in reader.toc), 'missing vector splash renderer'
    assert BRAND.version in list(constants(archive.extract("brand"))), "wrong embedded version"
    assert "brand_icon" in list(constants(archive.extract("brand"))), "missing resilient application icon"
    # The screenshot editor hides OCR/Speak when the stack is absent, so a
    # bundle without it ships a silent feature loss: fail loudly instead.
    assert "rapidocr" in archive.toc, "missing RapidOCR engine"
    assert "cv2" in archive.toc, "missing OpenCV runtime"
    assert any("winrt" in name for name in archive.toc), "missing WinRT OCR fallback"
    assert "vulkan_runtime" in archive.toc, "missing engine discovery/repair module"
    for name in ("engine_discovery", "engine_scan_ui", "speech_sources", "engine_scan_diagnostic", "update_protocol", "installation_check"):
        assert name in archive.toc, f"missing engine scan module: {name}"
        source = compile((root / (name + '.py')).read_bytes(), name + '.py', 'exec', dont_inherit=True)
        assert normalized(source) == normalized(archive.extract(name)), f'outdated engine scan source: {name}'
    helper_data = reader.extract(next(name for name in reader.toc
                         if name.replace('\\', '/') == 'helpers/WordArcUpdate.exe'))
    helper_manifest = json.loads(reader.extract(next(name for name in reader.toc
                         if name.replace('\\', '/') == 'helpers/manifest.json')))
    assert hashlib.sha256(helper_data).hexdigest() == helper_manifest['sha256'], 'changed update supervisor'
    for name, digest in helper_manifest['sources'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, f'outdated supervisor input: {name}'
    with tempfile.TemporaryDirectory(prefix='wordarc-helper-source-') as scratch:
        helper_exe = Path(scratch) / 'WordArcUpdate.exe'
        helper_exe.write_bytes(helper_data)
        helper_reader = CArchiveReader(str(helper_exe))
        helper_source = compile((root / 'update_helper.py').read_bytes(), 'update_helper.py', 'exec', dont_inherit=True)
        assert normalized(helper_source) == normalized(marshal.loads(helper_reader.extract('update_helper'))), 'outdated supervisor executable'
        shared = helper_reader.open_embedded_archive('PYZ.pyz').extract('update_protocol')
        expected = compile((root / 'update_protocol.py').read_bytes(), 'update_protocol.py', 'exec', dont_inherit=True)
        assert normalized(shared) == normalized(expected), 'outdated shared update protocol'
    assert "update_diagnostic" in archive.toc, "missing frozen updater acceptance"
    assert "assets/vulkan/runtime.json" in toc_slashes, "missing pinned Vulkan repair asset"
    pins = json.loads(reader.extract(next(name for name in reader.toc
                      if name.replace('\\', '/') == 'assets/vulkan/runtime.json')))
    repair = root / 'dist' / pins['file']
    assert repair.stat().st_size == pins['size'], 'wrong Vulkan repair asset size'
    with repair.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == pins['sha256'], 'wrong Vulkan repair asset hash'
    for asset in ("wordarc.ico", "wordarc-app.svg"):
        key = next(name for name in reader.toc
                   if name.replace('\\', '/') == 'assets/brand/' + asset)
        assert reader.extract(key) == (root / 'assets' / 'brand' / asset).read_bytes(), 'changed brand asset'
    assert "set_recording_state" in list(constants(archive.extract("settings_ui")))
    assert "PanelTabs" in list(constants(archive.extract("settings_ui"))), "old workspace layout bundled"
    for name in ("settings_ui", "screenshot_capture", "screenshot_editor", "ocr", "update", "theme", "worker", "localspeech", "livespeech", "cuda_runtime", "cuda_libs", "faster_whisper", "vulkan_speech", "local_stt_diagnostic"):
        assert name in archive.toc, f"missing bundled module: {name}"
    for name in ("brand", "hotkey", "paste", "settings_ui", "screenshot_capture", "screenshot_editor", "ocr", "update", "update_diagnostic", "overlay", "localspeech", "livespeech", "vulkan_speech", "vulkan_runtime", "config", "i18n", "cuda_recovery", "cuda_runtime", "cuda_libs", "local_stt_diagnostic"):
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
        report = Path(scratch) / 'updater.json'
        result = subprocess.run([str(inner), '--update-check', '--output', str(report)],
                                env=env, capture_output=True, timeout=60)
        assert report.is_file(), f'packaged updater produced no result: {result.returncode}'
        payload = json.loads(report.read_text(encoding='utf-8'))
        assert result.returncode == 0 and payload['ok'] and payload['tls_verified'], payload
        assert payload['state'] != 'checking', payload
        print(f"Packaged updater GUI + HTTPS OK: {payload['state']}, {payload['elapsed']:.3f} s")
    print(f"PACKAGE OK: {setup.name} (setup) + inner WordArc.exe")
    with setup.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    print(f"SHA256: {digest}")

if __name__ == "__main__":
    main()
