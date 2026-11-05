@echo off
title CommitMaster Central Server (Private Mesh Hub)
cd /d "%~dp0"
echo ========================================================
echo   CommitMaster Central Server (Private Tailnet Hub)
echo ========================================================
echo.

where tailscale >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [Tailscale Mesh Detected]
    for /f "tokens=*" %%i in ('tailscale ip -4') do echo    Mesh IP:   %%i
    for /f "tokens=*" %%i in ('powershell -NoProfile -Command "try { (tailscale status --json | ConvertFrom-Json).Self.DNSName.TrimEnd('.') } catch { '' }"') do if not "%%i"=="" echo    MagicDNS:  http://%%i:8000
    echo.
    echo    Tailscale Whois SSO: Active (Passwordless for 100.x.y.z nodes)
    echo.
) else (
    echo [Tip] Install Tailscale to connect remote laptops securely without public IPs.
    echo.
)

echo Starting server on port 8000...
echo Accessible on localhost, LAN, and all Tailnet mesh devices.
echo.
python server.py --host 0.0.0.0 --port 8000
pause
