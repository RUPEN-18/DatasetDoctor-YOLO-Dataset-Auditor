@echo off
setlocal
cd /d "%~dp0"
echo.
echo   DATASET DOCTOR - First-time setup
 echo   Python 3.10 or newer is required. Python 3.11 or 3.12 is recommended.
echo.
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click run_app.bat to start Dataset Doctor.
pause
exit /b 0
:failed
echo.
echo Setup failed. Read the error above. Install Python from python.org,
echo enable Add Python to PATH, then run this script again.
pause
exit /b 1
