@echo off
title CommitMaster Launcher
cd /d "%~dp0"

:: Auto-unblock executable from Mark of the Web if downloaded via browser/zip
if exist "%~dp0CommitMaster.exe" (
    powershell -NoProfile -Command "Unblock-File -Path '%~dp0CommitMaster.exe' -ErrorAction SilentlyContinue" >nul 2>&1
    start "" "%~dp0CommitMaster.exe"
    exit /b 0
)

if exist "%~dp0dist\CommitMaster.exe" (
    powershell -NoProfile -Command "Unblock-File -Path '%~dp0dist\CommitMaster.exe' -ErrorAction SilentlyContinue" >nul 2>&1
    start "" "%~dp0dist\CommitMaster.exe"
    exit /b 0
)

if exist "%LOCALAPPDATA%\Programs\CommitMaster\CommitMaster.exe" (
    start "" "%LOCALAPPDATA%\Programs\CommitMaster\CommitMaster.exe"
    exit /b 0
)

if exist "C:\Python314\pythonw.exe" (
    start "" "C:\Python314\pythonw.exe" "%~dp0app.py"
    exit /b 0
)

start "" pythonw app.py


