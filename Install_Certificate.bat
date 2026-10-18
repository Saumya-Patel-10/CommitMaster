@echo off
title CommitMaster Certificate Setup
echo ========================================================
echo   CommitMaster — Windows Security Certificate Setup
echo ========================================================
echo.
echo Installing CommitMaster security certificate to Trusted People...
echo This ensures Windows Defender, SmartScreen, and App Installer
echo recognize CommitMaster as a trusted, verified application.
echo.

set CERT_FILE=%~dp0CommitMaster-TestCert.cer
if not exist "%CERT_FILE%" set CERT_FILE=%~dp0dist\CommitMaster-TestCert.cer

if not exist "%CERT_FILE%" (
    echo [ERROR] Certificate file not found: %CERT_FILE%
    echo Please make sure CommitMaster-TestCert.cer is in the same folder.
    pause
    exit /b 1
)

:: Test if running as administrator
net session >nul 2>&1
if %errorlevel% == 0 (
    certutil -addstore -f "TrustedPeople" "%CERT_FILE%"
    certutil -addstore -f "Root" "%CERT_FILE%"
    echo.
    echo ========================================================
    echo [SUCCESS] Certificate installed into Trusted Stores!
    echo You can now run CommitMaster.exe or install CommitMaster.msix
    echo without any Windows Defender or SmartScreen warnings.
    echo ========================================================
) else (
    echo Requesting Administrator privileges to install certificate...
    powershell -Command "Start-Process cmd -ArgumentList '/c certutil -addstore -f TrustedPeople \"%CERT_FILE%\" & certutil -addstore -f Root \"%CERT_FILE%\" & echo. & echo ======================================================== & echo [SUCCESS] Certificate installed into Trusted Stores! & echo You can now run CommitMaster.exe or install CommitMaster.msix! & echo ======================================================== & pause' -Verb RunAs"
)
pause
