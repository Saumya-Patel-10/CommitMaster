@echo off
title CommitMaster Admin Launcher
cd /d "%~dp0"

:: 1. Launch via Microsoft-signed Python interpreter to bypass Windows 11 Smart App Control
if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" (
    start "" "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" "%~dp0admin_app.py"
    exit /b 0
)

if exist "C:\Python314\pythonw.exe" (
    start "" "C:\Python314\pythonw.exe" "%~dp0admin_app.py"
    exit /b 0
)

:: 2. Standalone binary fallback
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

start "" pythonw "%~dp0admin_app.py"
