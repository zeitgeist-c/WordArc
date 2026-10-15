# -*- mode: python ; coding: utf-8 -*-
import os
import sysconfig
from pathlib import Path

import PyQt6
from PyInstaller.utils.hooks import collect_dynamic_libs

# Qt's own strings (context menus, dialog buttons) come from this catalogue;
# without it a Turkish interface still shows English in those places.
_QT_TRANSLATIONS = os.path.join(os.path.dirname(PyQt6.__file__),
                                "Qt6", "translations")
datas = [('ffmpeg.exe', '.'), ('assets/brand', 'assets/brand'),
         ('assets/sounds', 'assets/sounds'),
         (os.path.join(_QT_TRANSLATIONS, 'qtbase_tr.qm'),
          'PyQt6/Qt6/translations')]
binaries = collect_dynamic_libs('ctranslate2')
# Native process isolation: carry the verified payload as data so PyInstaller
# does not flatten its DLL layout or replace its local CRT dependencies.
from tools.build_vulkan import verify as verify_vulkan
assert verify_vulkan(), 'Build/verify the Vulkan payload before packaging'
datas.append(('native/whisper-vulkan', 'native/whisper-vulkan'))
# Pinned NVIDIA wheels supply Windows DLLs that ordinary import
# analysis cannot see. Preserve their directory layout for cuda_runtime.
_SITE = Path(sysconfig.get_path('purelib'))
for dll in list((_SITE / 'nvidia').glob('*/bin/*.dll')) + list((_SITE / 'nvidia').glob('*/lib/*.dll')):
    binaries.append((str(dll), str(dll.parent.relative_to(_SITE))))
# The local speech engine. faster_whisper pulls in ctranslate2, onnxruntime,
# tokenizers, av and huggingface_hub, and PyInstaller's hooks miss most of them
# because they reach for binaries at runtime rather than importing them.
hiddenimports = ['unicodedata', 'soundcard', 'faster_whisper', 'ctranslate2',
                  'onnxruntime', 'tokenizers', 'huggingface_hub',
                  'av', 'av.audio.resampler', 'screenshot_capture', 'screenshot_editor']


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
