@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo === BritonLauncher: СЃР±РѕСЂРєР° .exe ===
python --version >nul 2>&1
if errorlevel 1 (
    echo Python РЅРµ РЅР°Р№РґРµРЅ. РЈСЃС‚Р°РЅРѕРІРё Python 3.10+ Рё РґРѕР±Р°РІСЊ РµРіРѕ РІ PATH.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo РЎРѕР·РґР°СЋ РІРёСЂС‚СѓР°Р»СЊРЅРѕРµ РѕРєСЂСѓР¶РµРЅРёРµ .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ venv.
        pause
        exit /b 1
    )
)

set "PY=.venv\Scripts\python.exe"

echo РЈСЃС‚Р°РЅР°РІР»РёРІР°СЋ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё...
"%PY%" -m pip install -q --upgrade pip
"%PY%" -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 (
    echo РћС€РёР±РєР° СѓСЃС‚Р°РЅРѕРІРєРё Р·Р°РІРёСЃРёРјРѕСЃС‚РµР№.
    pause
    exit /b 1
)

echo РЎРѕР±РёСЂР°СЋ BritonLauncher.exe ...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name BritonLauncher ^
  --collect-all webview ^
  --collect-all minecraft_launcher_lib ^
  --collect-all clr_loader ^
  --hidden-import clr ^
  --hidden-import webview.platforms.edgechromium ^
  main.py
if errorlevel 1 (
    echo РЎР±РѕСЂРєР° РЅРµ СѓРґР°Р»Р°СЃСЊ. РЎРјРѕС‚СЂРё РІС‹РІРѕРґ РІС‹С€Рµ.
    pause
    exit /b 1
)

echo.
echo Р“РѕС‚РѕРІРѕ: dist\BritonLauncher.exe
echo.
pause
endlocal
