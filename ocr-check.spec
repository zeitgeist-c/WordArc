# -*- mode: python ; coding: utf-8 -*-
# Shadow console twin of wordarc.spec for OCR engine proof only. Same datas /
# hiddenimports as the shipping spec (minus CUDA DLL globs and the Vulkan
# payload, which the OCR probe does not touch). Entry: tools/ocr_probe.py.
import os
import sysconfig
from pathlib import Path

import PyQt6
from PyInstaller.utils.hooks import collect_data_files

_WINRT_BUNDLED_CRT = Path(sysconfig.get_path('purelib')) / 'winrt' / 'msvcp140.dll'
if _WINRT_BUNDLED_CRT.exists():
    _WINRT_BUNDLED_CRT.unlink()

_QT_TRANSLATIONS = os.path.join(os.path.dirname(PyQt6.__file__),
                                "Qt6", "translations")
datas = [('assets/brand', 'assets/brand'),
         *collect_data_files('rapidocr'),
         (os.path.join(_QT_TRANSLATIONS, 'qtbase_tr.qm'),
          'PyQt6/Qt6/translations')]
hiddenimports = ['unicodedata',
                  'ocr', 'rapidocr', 'rapidocr.main',
                  'rapidocr.inference_engine',
                  'rapidocr.inference_engine.base',
                  'rapidocr.inference_engine.onnxruntime', 'cv2', 'shapely',
                  'pyclipper', 'omegaconf', 'yaml',
                  'winrt', 'winrt._winrt', 'winrt.runtime', 'winrt.system',
                  'winrt.windows.foundation', 'winrt.windows.foundation.collections',
                  'winrt.windows.graphics.imaging', 'winrt.windows.media.ocr',
                  'winrt.windows.storage.streams', 'winrt.windows.globalization']

a = Analysis(
    ['tools/ocr_probe.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['ctranslate2', 'faster_whisper', 'soundcard', 'av'],
    noarchive=False,
    optimize=0,
)
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
    name='wafrozen-ocr',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[],
)
