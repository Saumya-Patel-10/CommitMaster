@echo off
cd /d "%~dp0"
if exist "%~dp0dist\CommitMaster.exe" (
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


