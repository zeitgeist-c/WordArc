# -*- mode: python ; coding: utf-8 -*-
import os

import PyQt6

# Qt's own strings (context menus, dialog buttons) come from this catalogue;
# without it a Turkish interface still shows English in those places.
_QT_TRANSLATIONS = os.path.join(os.path.dirname(PyQt6.__file__),
                                "Qt6", "translations")
datas = [('ffmpeg.exe', '.'), ('assets/brand', 'assets/brand'),
         ('assets/sounds', 'assets/sounds'),
         (os.path.join(_QT_TRANSLATIONS, 'qtbase_tr.qm'),
          'PyQt6/Qt6/translations')]
binaries = []
# The local speech engine. faster_whisper pulls in ctranslate2, onnxruntime,
# tokenizers, av and huggingface_hub, and PyInstaller's hooks miss most of them
# because they reach for binaries at runtime rather than importing them.
hiddenimports = ['soundcard', 'faster_whisper', 'ctranslate2',
                  'onnxruntime', 'tokenizers', 'huggingface_hub',
                  'av', 'av.audio.resampler']


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
