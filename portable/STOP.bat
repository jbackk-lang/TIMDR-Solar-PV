@echo off
setlocal
cd /d "%~dp0"
"%~dp0python\python.exe" -B "%~dp0launcher.py" stop
if errorlevel 1 pause
