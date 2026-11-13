@echo off
rem Checks for a newer Yatesium release and installs it.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
echo.
pause
