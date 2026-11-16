@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo === BritonLauncher: Р·Р°РїСѓСЃРє РёР· РёСЃС…РѕРґРЅРёРєРѕРІ ===
python --version >nul 2>&1
if errorlevel 1 (
    echo Python РЅРµ РЅР°Р№РґРµРЅ. РЈСЃС‚Р°РЅРѕРІРё Python 3.10+ Рё РґРѕР±Р°РІСЊ РµРіРѕ РІ PATH.
    pause
    exit /b 1
)

echo РџСЂРѕРІРµСЂСЏСЋ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo РќРµ СѓРґР°Р»РѕСЃСЊ СѓСЃС‚Р°РЅРѕРІРёС‚СЊ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё.
    pause
    exit /b 1
)

echo Р—Р°РїСѓСЃРєР°СЋ Р»Р°СѓРЅС‡РµСЂ...
python main.py
if errorlevel 1 pause
endlocal
