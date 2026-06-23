# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    [str(root / "gui" / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "gui" / "ui" / "web"), "gui/ui/web"),
        (str(root / "gui" / "ui" / "assets"), "gui/ui/assets"),
    ],
    hiddenimports=[
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebChannel",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "heimdall_timewatch",
        "heimdall_timewatch.scan_service",
        "heimdall_timewatch.mft_parser",
        "heimdall_timewatch.detector",
        "heimdall_timewatch.usn_journal",
        "heimdall_timewatch.reporting",
        "heimdall_timewatch.labgen",
        "keyring.backends",
        "keyring.backends.Windows",
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
    [],
    exclude_binaries=True,
    name="heimdall-timewatch-gui",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="heimdall-timewatch-gui",
)
