# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Peachy Desktop Screen Assistant.

Builds in onedir mode:
- Windowed executable without console window (console=False)
- Crisp multi-resolution icon (resources/peachy.ico)
- Windows version resource (version_info.txt)
- Bundles resources/ folder and dynamic Qt/keyring backends
"""

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

datas = [
    ('resources', 'resources'),
]

hiddenimports = [
    'keyring.backends.Windows',
    'pywin32_ctypes',
    'PySide6.QtSvg',
    'google.genai',
]
hiddenimports += collect_submodules('keyring')

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Peachy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/peachy.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Peachy',
)
