# -*- mode: python ; coding: utf-8 -*-
import os
import sysconfig
from pathlib import Path

import PyQt6
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# The winrt wheels ship their own msvcp140.dll copy next to their .pyd files.
# When onnxruntime loads its own copy of the same CRT into the same process,
# the duplicate import crashes the process outright (0xC0000005) — and
# PyInstaller's analysis child imports both, so the build dies before it ever
# packages. Windows keeps a matching copy in System32 and the frozen app
# carries the Qt bundle's copy, so the wheel's duplicate serves no one:
# drop it from the build environment before any analysis subprocess starts.
_WINRT_BUNDLED_CRT = Path(sysconfig.get_path('purelib')) / 'winrt' / 'msvcp140.dll'
if _WINRT_BUNDLED_CRT.exists():
    _WINRT_BUNDLED_CRT.unlink()

# Qt's own strings (context menus, dialog buttons) come from this catalogue;
# without it a Turkish interface still shows English in those places.
_QT_TRANSLATIONS = os.path.join(os.path.dirname(PyQt6.__file__),
                                "Qt6", "translations")
datas = [('ffmpeg.exe', '.'), ('assets/brand', 'assets/brand'),
         ('assets/sounds', 'assets/sounds'),
         # EMA Lightning TTS weights: fetched at build time by
         # tools/fetch_ema_models.py so first Speak use needs no download.
         ('tools/vendor/ema-onnx', 'models/ema-onnx'),
         # CUDA on-demand pins: the DLLs themselves are NOT bundled (2 GB).
         # tools/build_cuda_libs.py verifies the venv wheels and vendors the
         # hash manifest; the zip is uploaded to the cuda-libs release tag.
         ('assets/cuda/cuda-libs.json', 'models/cuda'),
         ('tools/vendor/cuda-manifest.json', 'models/cuda'),
         # RapidOCR reads config.yaml/default_models.yaml and its .onnx models
         # from package data at runtime; import analysis cannot see them.
         *collect_data_files('rapidocr'),
         (os.path.join(_QT_TRANSLATIONS, 'qtbase_tr.qm'),
          'PyQt6/Qt6/translations')]
binaries = [(src, dest) for src, dest in collect_dynamic_libs('ctranslate2')
            # The wheel ships a cudnn stub loader; the real runtime is
            # on-demand (cuda_libs.py). Bundling the stub would fake the
            # engine's DLL load test, so it stays out of the package.
            if os.path.basename(src).lower() not in {"cudnn64_9.dll"}]
# Native process isolation: carry the verified payload as data so PyInstaller
# does not flatten its DLL layout or replace its local CRT dependencies.
from tools.build_vulkan import verify as verify_vulkan
assert verify_vulkan(), 'Build/verify the Vulkan payload before packaging'
datas.append(('native/whisper-vulkan', 'native/whisper-vulkan'))
# The on-demand CUDA runtime lives outside the package (see cuda_libs.py):
# bundling the NVIDIA wheels would add ~2 GB. Build env keeps them for the
# zip in tools/build_cuda_libs.py; the frozen app must not carry them.
# (Previous nvidia DLL loop removed 2026-10-22.)
# The local speech engine. faster_whisper pulls in ctranslate2, onnxruntime,
# tokenizers, av and huggingface_hub, and PyInstaller's hooks miss most of them
# because they reach for binaries at runtime rather than importing them.
hiddenimports = ['unicodedata', 'soundcard', 'faster_whisper', 'ctranslate2',
                  'onnxruntime', 'tokenizers', 'huggingface_hub',
                  # EMA Lightning TTS (tts_ema.py): same ONNX runtime, plus the
                  # Rust Turkish normalizer (native module, import at runtime).
                  'normalizer_tr',
                  # PDF text for the Speak tab (fitz is imported lazily).
                  'fitz',
                  'av', 'av.audio.resampler', 'screenshot_capture', 'screenshot_editor',
                  # RapidOCR (ocr.py primary engine). Its ONNX inference engine
                  # is picked by name at runtime, so plain analysis misses it;
                  # cv2 is the headless wheel (no Qt/GUI conflict).
                  'ocr', 'update', 'rapidocr', 'rapidocr.main',
                  'rapidocr.inference_engine',
                  'rapidocr.inference_engine.base',
                  'rapidocr.inference_engine.onnxruntime', 'cv2', 'shapely',
                  'pyclipper', 'omegaconf', 'yaml',
                  # Windows OCR (ocr.py imports these inside functions; the
                  # compiled projections must ride along explicitly).
                  'winrt', 'winrt._winrt', 'winrt.runtime', 'winrt.system',
                  'winrt.windows.foundation', 'winrt.windows.foundation.collections',
                  'winrt.windows.graphics.imaging', 'winrt.windows.media.ocr',
                  'winrt.windows.storage.streams', 'winrt.windows.globalization']


a = Analysis(
    ['wordarc.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Qt on Windows imports the OS ICU API without version-suffixed exports.
# PATH may contain Poppler's incompatible ICU DLLs from a document runtime.
# Never shadow the Windows ICU implementation inside the frozen bundle.
a.binaries = [entry for entry in a.binaries
              if os.path.basename(entry[0]).lower() not in
              {"icuuc.dll", "icuin.dll"}
              and not os.path.basename(entry[0]).lower().startswith("icudt")]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='wordarc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/brand/wordarc.ico',
)
