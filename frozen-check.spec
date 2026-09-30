# -*- mode: python ; coding: utf-8 -*-
# A console twin of wordarc.spec, built only to prove the frozen bundle runs
# what it ships: faster-whisper transcription, and the device-card dropdown
# painting. wordarc.spec itself is console=False, which is right for shipping
# and useless for reading a traceback back out of it. The probe is chosen by
# argv[1] so one build proves both.
import os
import sysconfig
from pathlib import Path

import PyQt6
from PyInstaller.utils.hooks import collect_dynamic_libs

_QT_TRANSLATIONS = os.path.join(os.path.dirname(PyQt6.__file__),
                                "Qt6", "translations")
datas = [('ffmpeg.exe', '.'), ('assets/brand', 'assets/brand'),
         ('assets/sounds', 'assets/sounds'),
         (os.path.join(_QT_TRANSLATIONS, 'qtbase_tr.qm'),
          'PyQt6/Qt6/translations')]
binaries = collect_dynamic_libs('ctranslate2')
_SITE = Path(sysconfig.get_path('purelib'))
for dll in (_SITE / 'nvidia').glob('*/bin/*.dll'):
    binaries.append((str(dll), str(dll.parent.relative_to(_SITE))))
hiddenimports = ['unicodedata', 'soundcard', 'faster_whisper', 'ctranslate2',
                  'onnxruntime', 'tokenizers', 'huggingface_hub',
                  'av', 'av.audio.resampler']

a = Analysis(
    ['tools/frozen_probe.py'],
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
    pyz, a.scripts, a.binaries, a.datas, [],
    name='wafrozen',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    upx_exclude=[], runtime_tmpdir=None, console=True,
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
)
