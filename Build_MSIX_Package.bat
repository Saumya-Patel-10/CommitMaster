@echo off
title CommitMaster MSIX Packaging Engine
echo =========================================================
echo      CommitMaster — Microsoft Store MSIX Packaging
echo =========================================================
cd /d "%~dp0"
python build_msix.py
if errorlevel 1 (
    echo.
    echo [ERROR] MSIX packaging failed. Check errors above.
    pause
    exit /b 1
)
echo.
echo [DONE] MSIX Package created in dist\CommitMaster.msix!
pause
