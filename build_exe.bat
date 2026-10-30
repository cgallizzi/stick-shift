@echo off
REM Builds dist\StickShift-portable.zip: StickShift.exe + ViGEmBus driver + quick start.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" ( echo Run install.bat first. & pause & exit /b 1 )
call .venv\Scripts\activate.bat
pip install pyinstaller pillow >nul
python make_icon.py
taskkill /im StickShift.exe /f >nul 2>nul
pyinstaller --noconfirm --onefile --console --name StickShift --icon icon.ico ^
  --collect-all vgamepad --add-data "config.default.json;." stickshift.py
if errorlevel 1 ( echo [error] build failed & pause & exit /b 1 )
python package.py
pause
