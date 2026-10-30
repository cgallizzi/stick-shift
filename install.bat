@echo off
REM Stick Shift - one-time setup.
setlocal
cd /d "%~dp0"

echo ============================================
echo  Stick Shift - install
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [error] Python not found on PATH. Install Python 3.10+ from python.org
  echo         and tick "Add python.exe to PATH" during setup.
  pause
  exit /b 1
)

echo Creating virtual environment (.venv)...
python -m venv .venv
if errorlevel 1 ( echo [error] venv creation failed & pause & exit /b 1 )

call .venv\Scripts\activate.bat
echo Upgrading pip...
python -m pip install --upgrade pip
echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 ( echo [error] dependency install failed & pause & exit /b 1 )

echo.
echo Done. ViGEmBus driver installs automatically on first run of Stick Shift.
echo If Stick Shift reports a ViGEmBus error, install it from:
echo   https://github.com/nefarius/ViGEmBus/releases
echo.
echo Next:
echo   run.bat --calibrate  (measure your game once)
echo   edit config.json   (your DPI + cm/360)
echo   run.bat              (play - F8 toggles)
echo.
pause
