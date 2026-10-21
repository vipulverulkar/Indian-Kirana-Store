# -*- mode: python ; coding: utf-8 -*-
# Build a single-file desktop app:
#   python -m pip install pyinstaller
#   python -m PyInstaller --clean --noconfirm kirana.spec
# Output: dist/KiranaPro (Linux/macOS) or dist/KiranaPro.exe (Windows).
# Build on the OS you want to ship: PyInstaller is not a cross-compiler.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("init_db.sql", "."),
    ("init_db_sqlite.sql", "."),
]
hiddenimports = ["dotenv", "werkzeug.serving"]

try:
    import webview  # noqa: F401
    hiddenimports += collect_submodules("webview")
    datas += collect_data_files("webview")
except ImportError:
    pass

try:
    import psycopg2  # noqa: F401
    hiddenimports += ["psycopg2", "psycopg2.errors", "psycopg2.extras"]
except ImportError:
    pass

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
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
    name="KiranaPro",
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
