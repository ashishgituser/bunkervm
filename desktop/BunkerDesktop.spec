# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for BunkerDesktop.
Produces a single .exe with embedded HTML/CSS/JS assets.
"""

import os

block_cipher = None
ROOT = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(ROOT, 'app.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # Bundle the UI assets (index.html, styles.css, app.js)
        (os.path.join(ROOT, 'src', 'index.html'), 'src'),
        (os.path.join(ROOT, 'src', 'styles.css'), 'src'),
        (os.path.join(ROOT, 'src', 'app.js'), 'src'),
    ],
    hiddenimports=[
        'webview',
        'webview.platforms.edgechromium',
        'clr_loader',
        'pythonnet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BunkerDesktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # No console window — native GUI only
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, '..', 'installer', 'windows', 'icon.ico')
        if os.path.exists(os.path.join(ROOT, '..', 'installer', 'windows', 'icon.ico'))
        else None,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
