@echo off
setlocal
chcp 65001 >nul
title Marginalia - Library Updater
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-update.ps1"
set "UPDATE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UPDATE_EXIT%
