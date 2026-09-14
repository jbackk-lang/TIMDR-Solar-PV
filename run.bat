@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo TIMDR-Solar-PV -- pelny przebieg: testy + REST API
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
    echo [BLAD] Nie znaleziono "python" w PATH. Zainstaluj Python 3.10+ z python.org
    echo        i zaznacz "Add python.exe to PATH" podczas instalacji.
    pause
    exit /b 1
)

echo.
echo [1/4] Tworze srodowisko wirtualne (.venv), jesli nie istnieje...
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo.
echo [2/4] Instaluje zaleznosci (numpy, pandas, pvlib, flask, pytest)...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt -q

echo.
echo [3/4] Uruchamiam testy jednostkowe (test_demo_scenarios.py + test_pv_battery_coupling.py)...
rem --- basetemp we wlasnym folderze projektu omija zablokowany/uszkodzony
rem     C:\Users\<user>\AppData\Local\Temp\pytest-of-<user> na Windows ---
python -m pytest -q --basetemp=".pytest_tmp"
if errorlevel 1 (
    echo [UWAGA] Niektore testy nie przeszly -- API ponizej i tak wystartuje,
    echo         ale sprawdz wynik testow powyzej, zanim zaufasz wynikom analizy.
)

echo.
echo [4/4] Startuje REST API (Flask, http://127.0.0.1:5001) w osobnym oknie
echo       i otwieram je w przegladarce...
start "TIMDR-Solar-PV API" cmd /k ".venv\Scripts\python.exe api.py"
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5001"

echo.
echo ============================================================
echo Gotowe. API dziala w osobnym oknie konsoli (zamknij je, zeby
echo zatrzymac serwer). Endpointy:
echo   GET  /api/health
echo   GET  /api/scenarios
echo   GET  /api/demo?scenario=normal_operation
echo   POST /api/analyze
echo ============================================================
pause
