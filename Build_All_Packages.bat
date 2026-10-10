@echo off
title CommitMaster — Automated Build System
cd /d "%~dp0"
echo ========================================================
echo        CommitMaster — Standalone Packaging Tool
echo ========================================================
echo.
echo 1/3. Compiling Windows EXEs with Native Version Info...
python build_exe.py
if errorlevel 1 (
    echo [ERROR] EXE build failed.
    pause
    exit /b 1
)
echo.
echo 2/3. Building Windows Setup Installer (CommitMaster-Setup.exe)...
python build_installer.py
if errorlevel 1 (
    echo [ERROR] Installer build failed.
    pause
    exit /b 1
)
echo.
echo 3/3. Building Microsoft Store MSIX Package (CommitMaster.msix)...
python build_msix.py
echo.
echo ========================================================
echo All Builds complete! Check the 'dist' directory:
echo   • dist\CommitMaster.exe (Portable Native App)
echo   • dist\CommitMaster-Setup.exe (Windows Installer)
echo   • dist\CommitMaster.msix (Microsoft Store Package)
echo   • dist\CommitMaster-Admin.exe (Saumya's Private Admin App)
echo ========================================================
echo.
pause

