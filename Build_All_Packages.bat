@echo off
title CommitMaster — Automated Build System
cd /d "%~dp0"
echo ========================================================
echo        CommitMaster — Standalone Packaging Tool
echo ========================================================
echo.
echo Building CommitMaster.exe (Public User Release)
echo and CommitMaster-Admin.exe (Your Private Admin Tool)...
echo.
python build_exe.py
echo.
echo ========================================================
echo Build complete! Check the 'dist' directory.
echo ========================================================
echo.
pause
