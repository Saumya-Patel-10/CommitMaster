@echo off
title CommitMaster Central Server (Private Cloud Hub)
echo ========================================================
echo   CommitMaster Central Server (Private Cloud Hub)
echo ========================================================
echo.
where tailscale >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo Detected Tailscale on this PC:
    for /f "tokens=*" %%i in ('tailscale ip -4') do echo    Tailscale IP: %%i
    echo.
) else (
    echo [Tip] Install Tailscale to connect remote testers securely.
    echo.
)
echo Binding to 0.0.0.0:8000 (accessible on LAN and Tailscale mesh)...
echo.
python server.py --host 0.0.0.0 --port 8000
pause
