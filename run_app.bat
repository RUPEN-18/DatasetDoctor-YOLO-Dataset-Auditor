@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo First run setup_windows.bat to install the application dependencies.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 (
    echo.
    echo The app encountered an error. See the message above and docs/TROUBLESHOOTING.md.
    pause
    exit /b 1
)
