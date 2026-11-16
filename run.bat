@echo off
setlocal
cd /d "%~dp0"

echo === BritonLauncher: run from sources ===
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

echo Checking dependencies...
python -m pip install -q --disable-pip-version-check --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo Starting launcher...
python main.py
if errorlevel 1 pause
endlocal
