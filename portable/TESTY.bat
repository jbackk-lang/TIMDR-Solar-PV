@echo off
setlocal
cd /d "%~dp0"
set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
"%~dp0python\python.exe" -B -m pytest app -q -p no:cacheprovider --basetemp=runtime\test-temp
pause
