@echo off
cd /d "%~dp0"
if exist "C:\Python314\pythonw.exe" (
    start "" "C:\Python314\pythonw.exe" "%~dp0app.py"
    exit /b 0
)
start "" pythonw app.py

