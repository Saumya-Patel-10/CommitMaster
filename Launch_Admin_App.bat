@echo off
title CommitMaster Admin Launcher
cd /d "%~dp0"

:: Auto-unblock if downloaded
if exist "%~dp0CommitMaster-Admin.exe" (
    powershell -NoProfile -Command "Unblock-File -Path '%~dp0CommitMaster-Admin.exe' -ErrorAction SilentlyContinue" >nul 2>&1
    start "" "%~dp0CommitMaster-Admin.exe"
    exit /b 0
)

if exist "%~dp0dist\CommitMaster-Admin.exe" (
    powershell -NoProfile -Command "Unblock-File -Path '%~dp0dist\CommitMaster-Admin.exe' -ErrorAction SilentlyContinue" >nul 2>&1
    start "" "%~dp0dist\CommitMaster-Admin.exe"
    exit /b 0
)

if exist "%LOCALAPPDATA%\Programs\CommitMaster\CommitMaster-Admin.exe" (
    start "" "%LOCALAPPDATA%\Programs\CommitMaster\CommitMaster-Admin.exe"
    exit /b 0
)

:: Python launch fallback
if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" (
    start "" "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" "%~dp0admin_app.py"
    exit /b 0
)

if exist "C:\Python314\pythonw.exe" (
    start "" "C:\Python314\pythonw.exe" "%~dp0admin_app.py"
    exit /b 0
)

start "" pythonw "%~dp0admin_app.py"
