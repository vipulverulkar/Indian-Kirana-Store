@echo off
cd /d "%~dp0"
set PY=python
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
"%PY%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo PyInstaller is required: python -m pip install pyinstaller
  exit /b 1
)
"%PY%" -m PyInstaller --clean --noconfirm kirana.spec
if errorlevel 1 exit /b 1
echo Built dist\KiranaPro.exe
