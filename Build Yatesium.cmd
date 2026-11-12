@echo off
rem Builds Yatesium on this PC. Downloads the current build script from the
rem Yatesium repository and runs it. Run it again to resume a stopped build.
title Yatesium build
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $s = Join-Path $env:TEMP 'yatesium-local-build.ps1'; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/ScottYates/Yatesium/main/local-build.ps1' -OutFile $s; & $s"
echo.
pause
