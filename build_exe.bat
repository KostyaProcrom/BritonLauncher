@echo off
setlocal
cd /d "%~dp0"

echo === BritonLauncher: build .exe ===
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create venv.
        pause
        exit /b 1
    )
)

set "PY=.venv\Scripts\python.exe"

echo Installing dependencies...
"%PY%" -m pip install -q --disable-pip-version-check --no-cache-dir --upgrade pip
"%PY%" -m pip install -q --disable-pip-version-check --no-cache-dir -r requirements.txt pyinstaller
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo Building BritonLauncher.exe ...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name BritonLauncher ^
  --collect-all webview ^
  --collect-all minecraft_launcher_lib ^
  --collect-all clr_loader ^
  --hidden-import clr ^
  --hidden-import webview.platforms.edgechromium ^
  main.py
if errorlevel 1 (
    echo Build failed. See output above.
    pause
    exit /b 1
)

echo.
echo Done: dist\BritonLauncher.exe
echo.
pause
endlocal
