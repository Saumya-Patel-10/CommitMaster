@echo off
title CommitMaster — Automated Build System
cd /d "%~dp0"
echo ========================================================
echo        CommitMaster — Standalone Packaging Tool
echo ========================================================
echo.
echo 1/2. Compiling Windows EXEs (CommitMaster.exe & CommitMaster-Admin.exe)...
python build_exe.py
if errorlevel 1 (
    echo [ERROR] EXE build failed.
    pause
    exit /b 1
)
echo.
echo 2/2. Building Microsoft Store MSIX Package (CommitMaster.msix)...
python build_msix.py
echo.
echo ========================================================
echo All Builds complete! Check the 'dist' directory.
echo ========================================================
echo.
pause

