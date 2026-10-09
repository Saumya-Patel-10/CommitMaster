"""
CommitMaster — Windows Auto-Startup Manager.
=============================================
Manages automatic startup on Windows boot via:
1. Windows Registry: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\CommitMaster
2. Windows Startup Folder shortcut fallback.
"""
import os
import sys
import winreg
from commitmaster.logger import get

log = get("startup_manager")

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "CommitMaster"


def get_startup_command() -> str:
    """Return the exact command line to launch CommitMaster on Windows boot."""
    app_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
    py_dir = os.path.dirname(sys.executable)
    # Check if pythonw.exe exists for silent/background window startup without console popup
    pythonw = os.path.join(py_dir, "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{exe}" "{app_py}"'


def is_auto_startup_enabled() -> bool:
    """Check if CommitMaster is set to launch at Windows startup."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception as e:
        log.debug("is_auto_startup_enabled error: %s", e)
        return False


def set_auto_startup(enable: bool) -> bool:
    """Enable or disable CommitMaster auto-startup via Windows registry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                cmd = get_startup_command()
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                log.info("Auto-startup enabled in registry: %s", cmd)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    log.info("Auto-startup disabled in registry.")
                except FileNotFoundError:
                    pass
        return True
    except Exception as exc:
        log.warning("Failed to configure auto-startup: %s", exc)
        return False
