#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
PY=python3
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi
if ! "$PY" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "PyInstaller is required: python3 -m pip install pyinstaller" >&2
    exit 1
fi
"$PY" -m PyInstaller --clean --noconfirm kirana.spec
echo "Built dist/KiranaPro"
