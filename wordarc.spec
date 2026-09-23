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
hiddenimports = ['soundcard']


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
