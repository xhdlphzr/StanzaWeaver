# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

# -*- mode: python ; coding: utf-8 -*-

import sys

if sys.platform == 'win32':
    icon_file = 'assets/Franx.ico'
elif sys.platform == 'darwin':
    icon_file = 'assets/Franx.icns'
else:
    icon_file = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('templates', 'templates'), ('static', 'static'), ('src/knowledge/schema.sql', 'src/knowledge')],
    hiddenimports=['engineio.async_drivers.threading', 'gevent'],
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
    [],
    exclude_binaries=True,
    name='StanzaWeaver',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[icon_file],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StanzaWeaver',
)
