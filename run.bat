@echo off
REM Stick Shift launcher. Passes all args through.
REM Examples:  run.bat            run.bat --calibrate        run.bat --mode ds4
setlocal
cd /d "%~dp0"

echo ============================================
echo  Stick Shift - keyboard+mouse as a controller
echo ============================================
echo.

if not exist ".venv\Scripts\activate.bat" (
  echo [error] Not installed yet. Double-click install.bat first, then try again.
  echo.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat

echo Starting Stick Shift... ^(this window must stay open while you play^)
echo If it exits immediately, read the message below.
echo.

REM -u = unbuffered, so status messages appear immediately.
python -u -m src.app %*
set EXITCODE=%ERRORLEVEL%

echo.
echo ============================================
if "%EXITCODE%"=="0" (
  echo  Stopped normally.
) else (
  echo  Exited with an error ^(code %EXITCODE%^). See messages above.
)
echo ============================================
echo.
echo This window stayed open so you can read the output.
echo Close it, or press a key to exit.
pause >nul
