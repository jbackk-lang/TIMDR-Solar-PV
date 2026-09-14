@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title TIMDR Solar PV - REST API

echo ============================================================
echo  TIMDR Solar PV - uruchamianie API
echo ============================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    set PYCMD=python
) else (
    where py >nul 2>nul
    if %ERRORLEVEL%==0 (
        set PYCMD=py
    ) else (
        echo [BLAD] Nie znaleziono Pythona w PATH.
        echo Pobierz z https://www.python.org/downloads/
        echo Przy instalacji zaznacz "Add python.exe to PATH".
        pause
        exit /b 1
    )
)

echo Uzywam: %PYCMD%
echo.
echo Instaluje/aktualizuje zaleznosci (numpy, pandas, pvlib, flask)...
echo (pvlib/pandas moga zajac chwile przy pierwszej instalacji)
%PYCMD% -m pip install --quiet --upgrade pip
%PYCMD% -m pip install --quiet -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [BLAD] Instalacja zaleznosci nie powiodla sie.
    pause
    exit /b 1
)

echo.
echo Uruchamiam API na http://127.0.0.1:5001 ...
echo (zamknij to okno, zeby zatrzymac serwer)
echo.

start "" http://127.0.0.1:5001
%PYCMD% api.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [BLAD] Serwer zakonczyl sie bledem - tresc bledu powyzej.
    pause
)
