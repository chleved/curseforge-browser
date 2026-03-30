# -*- mode: python ; coding: utf-8 -*-

import os

# Candidate system shared-libraries to attempt to bundle. Files that exist
# on the build host will be copied into the bundle root so targets without
# those system packages can still run the application.
_system_lib_candidates = [
    '/lib/libBLT.2.5.so.8.6',
    '/lib/x86_64-linux-gnu/libtk8.6.so',
    '/lib/x86_64-linux-gnu/libtcl8.6.so',
    '/lib/x86_64-linux-gnu/libX11.so.6',
    '/lib/x86_64-linux-gnu/libXft.so.2',
    '/lib/x86_64-linux-gnu/libfontconfig.so.1',
    '/lib/x86_64-linux-gnu/libXss.so.1',
    '/lib/x86_64-linux-gnu/libpng16.so.16',
    '/lib/x86_64-linux-gnu/libjpeg.so.8',
    '/lib/x86_64-linux-gnu/libfreetype.so.6',
    '/lib/x86_64-linux-gnu/libz.so.1',
    '/lib/x86_64-linux-gnu/libxcb.so.1',
    '/lib/x86_64-linux-gnu/libXrender.so.1',
    '/lib/x86_64-linux-gnu/libXext.so.6',
    '/lib/x86_64-linux-gnu/libXau.so.6',
    '/lib/x86_64-linux-gnu/libXdmcp.so.6',
    '/lib/x86_64-linux-gnu/libbz2.so.1.0',
    '/lib/x86_64-linux-gnu/libexpat.so.1',
]

binaries = []
for _lib in _system_lib_candidates:
    if os.path.exists(_lib):
        binaries.append((_lib, '.'))

a = Analysis(
    ['cursepante.py'],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=['PIL._tkinter_finder'],
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
    name='cursepante',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
