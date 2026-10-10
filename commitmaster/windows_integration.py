"""
Windows integration for CommitMaster:
  • Native Windows 10/11 Immersive Dark Titlebars (DWM API)
  • Explicit AppUserModelID for Windows Taskbar grouping & pinning
  • Multi-resolution icon.ico & PhotoImage branding for titlebars and task switcher
  • High-DPI awareness on Windows screens
"""
import ctypes
import os
import sys
import tkinter as tk
from typing import Dict, Optional
from PIL import Image, ImageTk

from commitmaster.logger import get

log = get("windows_integration")

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PHOTO_CACHE: Dict[tuple, ImageTk.PhotoImage] = {}
_INITIALIZED_APP_ID: Dict[str, bool] = {}


def init_app_user_model_id(app_type: str = "user") -> None:
    """Register custom Windows Application ID so taskbar shows proper app icon & grouping."""
    if _INITIALIZED_APP_ID.get(app_type):
        return
    _INITIALIZED_APP_ID[app_type] = True
    if sys.platform == "win32":
        try:
            if app_type == "admin":
                app_id = "CommitMaster.App.Admin.3.0"
            else:
                app_id = "CommitMaster.App.Client.3.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            log.debug("Registered Windows AppUserModelID: %s (%s)", app_id, app_type)
        except Exception as exc:
            log.debug("Could not set AppUserModelID: %s", exc)


def set_dark_titlebar(window: tk.Misc) -> None:
    """Enable Windows 10 (20H1+) / Windows 11 native immersive dark titlebar."""
    if sys.platform != "win32":
        return

    try:
        window.update_idletasks()
        hwnd = window.winfo_id()
        # On Tk toplevels, winfo_id is an inner container; get root frame hwnd
        parent_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2) or ctypes.windll.user32.GetParent(hwnd)
        target_hwnd = parent_hwnd if parent_hwnd else hwnd

        # DWMWA_USE_IMMERSIVE_DARK_MODE: 20 on Win 11 / modern Win 10, 19 on older Win 10 builds
        value = ctypes.c_int(1)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            target_hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
        )
        if res != 0:
            # Fallback for earlier Windows 10 builds (builds 17763–18985 used attribute 19)
            value_old = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                target_hwnd, 19, ctypes.byref(value_old), ctypes.sizeof(value_old)
            )
    except Exception as exc:
        log.debug("Could not set dark title bar: %s", exc)


def get_icon_path(app_type: str = "user") -> Optional[str]:
    """Find appropriate .ico in workspace, bundle or assets directory."""
    if app_type == "admin":
        candidates = [
            os.path.join(APP_DIR, "assets", "icon_admin.ico"),
            os.path.join(APP_DIR, "icon_admin.ico"),
            os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "assets", "icon_admin.ico"),
            os.path.join(APP_DIR, "assets", "icon.ico"),
            os.path.join(APP_DIR, "icon.ico"),
        ]
    else:
        candidates = [
            os.path.join(APP_DIR, "assets", "icon_user.ico"),
            os.path.join(APP_DIR, "icon_user.ico"),
            os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "assets", "icon_user.ico"),
            os.path.join(APP_DIR, "assets", "icon.ico"),
            os.path.join(APP_DIR, "icon.ico"),
        ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def set_dpi_awareness() -> None:
    """Enable per-monitor v2 DPI awareness on Windows to prevent blurry text."""
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass


_IMAGE_CACHE: Dict[tuple, Image.Image] = {}


def get_logo_photo(size: int = 32, master: Optional[tk.Misc] = None,
                   app_type: str = "user") -> Optional[ImageTk.PhotoImage]:
    """Return high-resolution PhotoImage for in-app headers and dialogs bound to active master."""
    if master is None:
        try:
            master = tk._default_root
        except Exception:
            pass

    cache_key = (size, str(master) if master else "root", app_type)
    if cache_key in _PHOTO_CACHE:
        try:
            photo = _PHOTO_CACHE[cache_key]
            if master:
                master.tk.call("image", "type", str(photo))
            return photo
        except Exception:
            _PHOTO_CACHE.pop(cache_key, None)

    img_key = (size, app_type)
    if img_key not in _IMAGE_CACHE:
        if app_type == "admin":
            candidates = [
                os.path.join(APP_DIR, "assets", f"logo_admin_{size}.png"),
                os.path.join(APP_DIR, "assets", "logo_admin.png"),
                os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "assets", "logo_admin.png"),
                os.path.join(APP_DIR, "assets", f"logo_{size}.png"),
                os.path.join(APP_DIR, "assets", "logo.png"),
            ]
        else:
            candidates = [
                os.path.join(APP_DIR, "assets", f"logo_user_{size}.png"),
                os.path.join(APP_DIR, "assets", "logo_user.png"),
                os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "assets", "logo_user.png"),
                os.path.join(APP_DIR, "assets", f"logo_{size}.png"),
                os.path.join(APP_DIR, "assets", "logo.png"),
            ]
        for c in candidates:
            if os.path.exists(c):
                try:
                    im = Image.open(c).convert("RGBA")
                    if im.size != (size, size):
                        im = im.resize((size, size), Image.Resampling.LANCZOS)
                    _IMAGE_CACHE[img_key] = im
                    break
                except Exception as exc:
                    log.debug("Could not load logo from %s: %s", c, exc)

    if img_key in _IMAGE_CACHE:
        try:
            photo = ImageTk.PhotoImage(_IMAGE_CACHE[img_key], master=master)
            _PHOTO_CACHE[cache_key] = photo
            return photo
        except Exception:
            return None
    return None


def apply_windows_theme(window: tk.Misc, title: Optional[str] = None,
                        app_type: str = "user") -> None:
    """
    Complete professional Windows treatment:
      1. Sets AppUserModelID on process
      2. Enables immersive dark title bar matching app theme
      3. Sets multi-res window icons for title bar and Alt+Tab switcher
    """
    set_dpi_awareness()
    init_app_user_model_id(app_type)

    if title and hasattr(window, "title"):
        try:
            window.title(title)
        except Exception:
            pass

    # Window icons
    icon_path = get_icon_path(app_type)
    if icon_path and hasattr(window, "iconbitmap"):
        try:
            window.iconbitmap(icon_path)
        except Exception:
            pass

    photo = get_logo_photo(64, master=window, app_type=app_type) or get_logo_photo(32, master=window, app_type=app_type)
    if photo and hasattr(window, "iconphoto"):
        try:
            window.iconphoto(True, photo)
            # Retain reference on window object so Tkinter never garbage collects it
            setattr(window, "_app_logo_img", photo)
        except Exception:
            pass

    # Windows 10/11 dark title bar
    window.after(10, lambda: set_dark_titlebar(window))


def register_windows_app(app_type: str = "user") -> bool:
    """
    Registers CommitMaster into the Windows Shell, Start Menu, and Windows Search:
      1. Creates Start Menu shortcut (.lnk) in %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\CommitMaster.lnk
      2. Registers HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\CommitMaster.exe
      3. Registers HKCU\\Software\\Classes\\Applications\\CommitMaster.exe
    This ensures the Windows Search Bar immediately locates and displays CommitMaster with its official icon.
    """
    if sys.platform != "win32":
        return False

    import winreg
    import subprocess

    try:
        is_admin = (app_type == "admin")
        exe_base = "CommitMaster-Admin.exe" if is_admin else "CommitMaster.exe"
        lnk_title = "CommitMaster Admin" if is_admin else "CommitMaster"
        desc = "CommitMaster Admin Console" if is_admin else "CommitMaster — Intelligent Git Companion"
        ico_file = "icon_admin.ico" if is_admin else "icon_user.ico"

        target_exe = None
        working_dir = APP_DIR

        if getattr(sys, "frozen", False):
            target_exe = sys.executable
            working_dir = os.path.dirname(sys.executable)
        else:
            local_app = os.path.expandvars(rf"%LOCALAPPDATA%\Programs\CommitMaster\{exe_base}")
            dist_app = os.path.join(APP_DIR, "dist", exe_base)
            if os.path.exists(local_app):
                target_exe = local_app
                working_dir = os.path.dirname(local_app)
            elif os.path.exists(dist_app):
                target_exe = dist_app
                working_dir = os.path.dirname(dist_app)

        vbs_fallback = os.path.join(APP_DIR, "Launch_Admin_App.vbs" if is_admin else "Launch_CommitMaster.vbs")
        ico_path = os.path.join(APP_DIR, ico_file)
        if not os.path.exists(ico_path):
            ico_path = os.path.join(APP_DIR, "icon.ico")

        # 1. Start Menu Shortcut (.lnk)
        start_menu_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")
        os.makedirs(start_menu_dir, exist_ok=True)
        lnk_path = os.path.join(start_menu_dir, f"{lnk_title}.lnk")

        ps_commands = [
            "$ws = New-Object -ComObject WScript.Shell",
            f"$lnk = $ws.CreateShortcut('{lnk_path.replace(chr(92), '/')}')",
        ]
        if target_exe and os.path.exists(target_exe):
            ps_commands.append(f"$lnk.TargetPath = '{target_exe.replace(chr(92), '/')}'")
            ps_commands.append(f"$lnk.WorkingDirectory = '{working_dir.replace(chr(92), '/')}'")
            ps_commands.append(f"$lnk.IconLocation = '{target_exe.replace(chr(92), '/')},0'")
        else:
            ps_commands.append("$lnk.TargetPath = 'wscript.exe'")
            ps_commands.append(f"$lnk.Arguments = '\"{vbs_fallback.replace(chr(92), '/')}\"'")
            ps_commands.append(f"$lnk.WorkingDirectory = '{working_dir.replace(chr(92), '/')}'")
            if os.path.exists(ico_path):
                ps_commands.append(f"$lnk.IconLocation = '{ico_path.replace(chr(92), '/')},0'")

        ps_commands.append(f"$lnk.Description = '{desc}'")
        ps_commands.append("$lnk.Save()")

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "; ".join(ps_commands)],
            capture_output=True,
            timeout=8,
            creationflags=flags
        )

        # 2. Register Windows App Paths (so Win+R and Windows Search find it)
        if target_exe and os.path.exists(target_exe):
            try:
                app_paths_key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe_base}"
                )
                winreg.SetValueEx(app_paths_key, "", 0, winreg.REG_SZ, target_exe)
                winreg.SetValueEx(app_paths_key, "Path", 0, winreg.REG_SZ, working_dir)
                winreg.CloseKey(app_paths_key)
            except Exception as e:
                log.debug("App Paths registry write error: %s", e)

            # 3. Register Applications
            try:
                apps_key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    rf"Software\Classes\Applications\{exe_base}"
                )
                winreg.SetValueEx(apps_key, "FriendlyAppName", 0, winreg.REG_SZ, lnk_title)
                winreg.SetValueEx(apps_key, "ApplicationCompany", 0, winreg.REG_SZ, "CommitMaster")
                winreg.CloseKey(apps_key)
            except Exception as e:
                log.debug("Classes Applications registry error: %s", e)

        log.info("Registered CommitMaster in Windows Search and Start Menu.")
        return True
    except Exception as exc:
        log.warning("Could not register Windows app in Start Menu / Search: %s", exc)
        return False


def create_desktop_shortcut(target: str = "both") -> tuple[bool, str]:
    """
    Create Windows Desktop .lnk shortcut(s) with official CommitMaster icon:
      target: 'admin' (Admin App), 'user' (Main App), or 'both'
    Returns (success, message).
    """
    if sys.platform != "win32":
        return False, "Shortcuts can only be created on Windows."

    import subprocess
    app_dir = APP_DIR.replace("\\", "/")
    user_icon = os.path.join(APP_DIR, "icon_user.ico").replace("\\", "/")
    admin_icon = os.path.join(APP_DIR, "icon_admin.ico").replace("\\", "/")
    fallback_icon = os.path.join(APP_DIR, "icon.ico").replace("\\", "/")

    # Check compiled executable existence
    user_exe = None
    admin_exe = None
    if getattr(sys, "frozen", False):
        user_exe = sys.executable.replace("\\", "/")
    else:
        for candidate in [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\CommitMaster\CommitMaster.exe"),
            os.path.join(APP_DIR, "dist", "CommitMaster.exe"),
        ]:
            if os.path.exists(candidate):
                user_exe = candidate.replace("\\", "/")
                break
        for candidate in [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\CommitMaster\CommitMaster-Admin.exe"),
            os.path.join(APP_DIR, "dist", "CommitMaster-Admin.exe"),
        ]:
            if os.path.exists(candidate):
                admin_exe = candidate.replace("\\", "/")
                break

    shortcuts_to_create = []
    if target in ("admin", "both"):
        ico = admin_icon if os.path.exists(os.path.join(APP_DIR, "icon_admin.ico")) else fallback_icon
        if admin_exe and os.path.exists(admin_exe):
            shortcuts_to_create.append({
                "name": "CommitMaster Admin",
                "desc": "CommitMaster Admin Portal — Saumya's Private Workspace",
                "target": admin_exe,
                "args": "",
                "workdir": os.path.dirname(admin_exe),
                "icon": admin_exe,
            })
        else:
            vbs_target = os.path.join(APP_DIR, "Launch_Admin_App.vbs").replace("\\", "/")
            shortcuts_to_create.append({
                "name": "CommitMaster Admin",
                "desc": "CommitMaster Admin Portal — Saumya's Private Workspace",
                "target": "wscript.exe",
                "args": f'"{vbs_target}"',
                "workdir": app_dir,
                "icon": ico,
            })

    if target in ("user", "both"):
        ico = user_icon if os.path.exists(os.path.join(APP_DIR, "icon_user.ico")) else fallback_icon
        if user_exe and os.path.exists(user_exe):
            shortcuts_to_create.append({
                "name": "CommitMaster",
                "desc": "CommitMaster Desktop Application",
                "target": user_exe,
                "args": "",
                "workdir": os.path.dirname(user_exe),
                "icon": user_exe,
            })
        else:
            vbs_target = os.path.join(APP_DIR, "Launch_CommitMaster.vbs").replace("\\", "/")
            shortcuts_to_create.append({
                "name": "CommitMaster",
                "desc": "CommitMaster Desktop Application",
                "target": "wscript.exe",
                "args": f'"{vbs_target}"',
                "workdir": app_dir,
                "icon": ico,
            })

    created_names = []
    try:
        ps_commands = [
            "$ws = New-Object -ComObject WScript.Shell",
            "$desktop = [Environment]::GetFolderPath('Desktop')",
            "$startMenu = [Environment]::GetFolderPath('Programs')"
        ]
        for s in shortcuts_to_create:
            # Create on Desktop
            ps_commands.append(f"$lnk = $ws.CreateShortcut(\"$desktop/{s['name']}.lnk\")")
            ps_commands.append(f"$lnk.TargetPath = '{s['target']}'")
            if s['args']:
                ps_commands.append(f"$lnk.Arguments = '{s['args']}'")
            ps_commands.append(f"$lnk.WorkingDirectory = '{s['workdir']}'")
            ps_commands.append(f"$lnk.Description = '{s['desc']}'")
            if os.path.exists(s["icon"]):
                ps_commands.append(f"$lnk.IconLocation = '{s['icon']},0'")
            ps_commands.append("$lnk.Save()")

            # Also create in Start Menu for immediate Windows Search indexing
            ps_commands.append(f"$lnk2 = $ws.CreateShortcut(\"$startMenu/{s['name']}.lnk\")")
            ps_commands.append(f"$lnk2.TargetPath = '{s['target']}'")
            if s['args']:
                ps_commands.append(f"$lnk2.Arguments = '{s['args']}'")
            ps_commands.append(f"$lnk2.WorkingDirectory = '{s['workdir']}'")
            ps_commands.append(f"$lnk2.Description = '{s['desc']}'")
            if os.path.exists(s["icon"]):
                ps_commands.append(f"$lnk2.IconLocation = '{s['icon']},0'")
            ps_commands.append("$lnk2.Save()")

            created_names.append(s["name"])

        full_ps = "; ".join(ps_commands)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", full_ps],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=flags,
        )
        if res.returncode == 0:
            return True, f"Created desktop and Start Menu shortcut(s): {', '.join(created_names)}"
        return False, f"PowerShell returned code {res.returncode}: {res.stderr.strip()}"
    except Exception as exc:
        log.error("Failed to create shortcut: %s", exc)
        return False, str(exc)

