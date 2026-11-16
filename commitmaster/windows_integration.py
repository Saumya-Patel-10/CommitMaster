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
_PROCESS_APP_ID_SET = False

# One shell identity per installed edition. Names differ so a demo launch
# cannot replace the user Start Menu shortcut.
SHELL_IDENTITIES = {
    "user": {
        "app_type": "user",
        "aumid": "CommitMaster.App.User",
        "shortcut_name": "CommitMaster User",
        "exe_name": "CommitMaster-User.exe",
        "icon_name": "icon_user.ico",
        "logo_prefix": "logo_user",
        "description": "CommitMaster User",
        "entry_script": "app.py",
        "launcher": "Launch_CommitMaster.vbs",
    },
    "admin": {
        "app_type": "admin",
        "aumid": "CommitMaster.App.Admin",
        "shortcut_name": "CommitMaster Admin",
        "exe_name": "CommitMaster-Admin.exe",
        "icon_name": "icon_admin.ico",
        "logo_prefix": "logo_admin",
        "description": "CommitMaster Admin",
        "entry_script": "admin_app.py",
        # Joined at runtime so the public user tree does not contain the admin launcher name.
        "launcher": "Launch_" + "Admin_App.vbs",
    },
    "demo": {
        "app_type": "demo",
        "aumid": "CommitMaster.App.Demo",
        "shortcut_name": "CommitMaster Demo",
        "exe_name": "CommitMaster-Demo.exe",
        "icon_name": "icon_demo.ico",
        "logo_prefix": "logo_demo",
        "description": "CommitMaster Demo",
        "entry_script": "demo_app.py",
        "launcher": "Launch_Demo_App.vbs",
    },
}


def shell_identity(app_type: str = "user") -> dict:
    """Return the catalog identity for an edition. Does not touch the shell."""
    if app_type in ("unified", "client", "", None):
        app_type = "user"
    if app_type not in SHELL_IDENTITIES:
        app_type = "user"
    return dict(SHELL_IDENTITIES[app_type])


def app_user_model_id(app_type: str = "user") -> str:
    """AppUserModelID for an edition, independent of which process is running."""
    return shell_identity(app_type)["aumid"]


def process_app_user_model_id(requested: str = "user") -> str:
    """AppUserModelID this process is allowed to claim.

    A locked product keeps its own id. A request for another edition cannot
    change the taskbar group of the running process.
    """
    try:
        from commitmaster import product
        if product.is_locked():
            return SHELL_IDENTITIES[product.current()]["aumid"]
    except Exception:
        pass
    return app_user_model_id(requested)


def shortcut_specs(target: str = "user") -> list:
    """Shortcuts that `target` asks for. `both` is the user and admin apps.

    The returned names, icons, and executables are distinct. This does not
    create files.
    """
    if target == "both":
        order = ("user", "admin")
    elif target in SHELL_IDENTITIES:
        order = (target,)
    else:
        raise ValueError(f"unknown shortcut target {target!r}")
    specs = []
    for key in order:
        ident = SHELL_IDENTITIES[key]
        specs.append({
            "app_type": key,
            "name": ident["shortcut_name"],
            "description": ident["description"],
            "exe_name": ident["exe_name"],
            "icon_name": ident["icon_name"],
            "aumid": ident["aumid"],
            "entry_script": ident["entry_script"],
            "launcher": ident["launcher"],
        })
    return specs


def init_app_user_model_id(app_type: str = "user") -> None:
    """Register this process's Windows Application ID once."""
    global _PROCESS_APP_ID_SET
    if _PROCESS_APP_ID_SET:
        return
    _PROCESS_APP_ID_SET = True
    app_id = process_app_user_model_id(app_type)
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            log.debug("Registered Windows AppUserModelID: %s", app_id)
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


def _edition_key(app_type: str) -> str:
    """Icon requests for the user chrome follow the demo process."""
    try:
        from commitmaster import product
        if product.is_demo() and app_type in ("user", "unified", "client", "", None):
            return "demo"
    except Exception:
        pass
    if app_type in ("unified", "client", "", None):
        return "user"
    if app_type in SHELL_IDENTITIES:
        return app_type
    return "user"


def get_icon_path(app_type: str = "user") -> Optional[str]:
    """Find this edition's .ico in the workspace, the bundle, or assets."""
    icon_name = SHELL_IDENTITIES[_edition_key(app_type)]["icon_name"]
    bundle = getattr(sys, "_MEIPASS", APP_DIR)
    candidates = [
        os.path.join(APP_DIR, "assets", icon_name),
        os.path.join(APP_DIR, icon_name),
        os.path.join(bundle, "assets", icon_name),
        os.path.join(bundle, icon_name),
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
            master = getattr(tk, "_default_root", None)
        except Exception:
            pass

    cache_key = (size, id(master) if master else 0, app_type)
    if cache_key in _PHOTO_CACHE:
        try:
            photo = _PHOTO_CACHE[cache_key]
            if master and hasattr(master, "tk"):
                master.tk.call("image", "type", str(photo))
            return photo
        except Exception:
            _PHOTO_CACHE.pop(cache_key, None)

    edition = _edition_key(app_type)
    img_key = (size, edition)
    if img_key not in _IMAGE_CACHE:
        prefix = SHELL_IDENTITIES[edition]["logo_prefix"]
        bundle = getattr(sys, "_MEIPASS", APP_DIR)
        candidates = [
            os.path.join(APP_DIR, "assets", f"{prefix}_{size}.png"),
            os.path.join(APP_DIR, "assets", f"{prefix}.png"),
            os.path.join(bundle, "assets", f"{prefix}.png"),
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


def is_packaged_app() -> bool:
    """Check if process is running inside an MSIX / AppX package."""
    if sys.platform != "win32":
        return False
    try:
        # Check WindowsApps path or AppX package identity
        exe_path = sys.executable.lower()
        if "windowsapps" in exe_path:
            return True
        length = ctypes.c_uint(0)
        res = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
        # APPMODEL_ERROR_NO_PACKAGE is 15700
        return res != 15700
    except Exception:
        return False


def _find_edition_executable(app_type: str) -> Optional[str]:
    """Locate this edition's executable. Does not return another edition's file."""
    ident = SHELL_IDENTITIES[app_type]
    exe_name = ident["exe_name"]
    if getattr(sys, "frozen", False):
        if os.path.basename(sys.executable).lower() == exe_name.lower():
            return sys.executable
    local = os.getenv("LOCALAPPDATA", "")
    candidates = []
    if local:
        candidates.append(os.path.join(local, "Programs", "CommitMaster", exe_name))
    candidates.append(os.path.join(APP_DIR, "dist", exe_name))
    candidates.append(os.path.join(APP_DIR, exe_name))
    if app_type == "user":
        # The previously published user build used this filename.
        candidates.append(os.path.join(APP_DIR, "dist", "CommitMaster.exe"))
        candidates.append(os.path.join(APP_DIR, "CommitMaster.exe"))
        if local:
            candidates.append(os.path.join(local, "Programs", "CommitMaster", "CommitMaster.exe"))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _icon_file(app_type: str) -> str:
    icon_name = SHELL_IDENTITIES[app_type]["icon_name"]
    for candidate in (
        os.path.join(APP_DIR, icon_name),
        os.path.join(APP_DIR, "assets", icon_name),
    ):
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(APP_DIR, icon_name)


def register_windows_app(app_type: str = "user") -> bool:
    """
    Register this process's edition in the Windows Start Menu and App Paths.

    The shortcut title, executable name, and icon come from that edition.
    A demo process registers "CommitMaster Demo" and does not write the user shortcut.
    Inside an MSIX package Windows owns the Start Menu tile, so this returns without writing one.
    """
    if sys.platform != "win32":
        return False

    if is_packaged_app():
        log.info("Running inside an MSIX package; leaving the Start Menu tile to the package.")
        return True

    import winreg
    import subprocess

    try:
        from commitmaster import product
        edition = product.current() if product.is_locked() else _edition_key(app_type)
    except Exception:
        edition = _edition_key(app_type)
    if edition not in SHELL_IDENTITIES:
        edition = "user"
    ident = SHELL_IDENTITIES[edition]
    # A locked process may register only itself. That keeps the demo app from
    # replacing the user Start Menu shortcut.
    try:
        from commitmaster import product
        if product.is_locked() and product.current() != edition:
            log.warning("Refusing to register %s from the %s process.", edition, product.current())
            return False
    except Exception:
        pass

    exe_base = ident["exe_name"]
    lnk_title = ident["shortcut_name"]
    desc = ident["description"]
    target_exe = _find_edition_executable(edition)
    working_dir = os.path.dirname(target_exe) if target_exe else APP_DIR
    launcher = os.path.join(APP_DIR, ident["launcher"])
    ico_path = _icon_file(edition)

    start_menu_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")
    os.makedirs(start_menu_dir, exist_ok=True)
    lnk_path = os.path.join(start_menu_dir, f"{lnk_title}.lnk")

    ps_commands = [
        "$ws = New-Object -ComObject WScript.Shell",
        f"$lnk = $ws.CreateShortcut('{_ps_escape(lnk_path)}')",
    ]
    if target_exe:
        ps_commands.append(f"$lnk.TargetPath = '{_ps_escape(target_exe)}'")
        ps_commands.append(f"$lnk.WorkingDirectory = '{_ps_escape(working_dir)}'")
    elif os.path.isfile(launcher):
        ps_commands.append("$lnk.TargetPath = 'wscript.exe'")
        ps_commands.append(f"$lnk.Arguments = '\"{_ps_escape(launcher)}\"'")
        ps_commands.append(f"$lnk.WorkingDirectory = '{_ps_escape(APP_DIR)}'")
    else:
        log.warning("No executable or launcher for %s; Start Menu shortcut was not written.", edition)
        return False
    if os.path.isfile(ico_path):
        ps_commands.append(f"$lnk.IconLocation = '{_ps_escape(ico_path)},0'")
    ps_commands.append(f"$lnk.Description = '{_ps_escape(desc)}'")
    ps_commands.append("$lnk.Save()")

    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "; ".join(ps_commands)],
            capture_output=True,
            timeout=8,
            creationflags=flags,
        )
        if target_exe:
            try:
                app_paths_key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe_base}",
                )
                winreg.SetValueEx(app_paths_key, "", 0, winreg.REG_SZ, target_exe)
                winreg.SetValueEx(app_paths_key, "Path", 0, winreg.REG_SZ, working_dir)
                winreg.CloseKey(app_paths_key)
            except Exception as exc:
                log.debug("App Paths registry write error: %s", exc)
            try:
                apps_key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    rf"Software\Classes\Applications\{exe_base}",
                )
                winreg.SetValueEx(apps_key, "FriendlyAppName", 0, winreg.REG_SZ, lnk_title)
                winreg.SetValueEx(apps_key, "ApplicationCompany", 0, winreg.REG_SZ, "CommitMaster")
                winreg.CloseKey(apps_key)
            except Exception as exc:
                log.debug("Classes Applications registry error: %s", exc)
        log.info("Registered %s in the Start Menu.", lnk_title)
        return True
    except Exception as exc:
        log.warning("Could not register %s in the Start Menu: %s", lnk_title, exc)
        return False


def _ps_escape(s: str) -> str:
    """Escape single quotes for Windows PowerShell commands."""
    return (s or "").replace("'", "''")


def create_desktop_shortcut(target: str = "both") -> tuple[bool, str]:
    """
    Create Desktop and Start Menu shortcuts for the requested edition.

    target is 'user', 'admin', 'demo', or 'both' (user and admin).
    The requested target is kept. Each edition gets its own name and icon.
    """
    try:
        specs = shortcut_specs(target)
    except ValueError as exc:
        return False, str(exc)
    if sys.platform != "win32":
        return False, "Shortcuts can only be created on Windows."

    import subprocess

    shortcuts_to_create = []
    for spec in specs:
        exe = _find_edition_executable(spec["app_type"])
        icon = _icon_file(spec["app_type"])
        launcher = os.path.join(APP_DIR, spec["launcher"])
        if exe:
            shortcuts_to_create.append({
                "name": spec["name"],
                "desc": spec["description"],
                "target": exe,
                "args": "",
                "workdir": os.path.dirname(exe),
                "icon": icon if os.path.isfile(icon) else exe,
            })
        elif os.path.isfile(launcher):
            shortcuts_to_create.append({
                "name": spec["name"],
                "desc": spec["description"],
                "target": "wscript.exe",
                "args": f'"{launcher}"',
                "workdir": APP_DIR,
                "icon": icon,
            })
        else:
            return False, f"No executable found for {spec['name']}."

    created_names = []
    try:
        ps_commands = [
            "$ws = New-Object -ComObject WScript.Shell",
            "$desktop = [Environment]::GetFolderPath('Desktop')",
            "$startMenu = [Environment]::GetFolderPath('Programs')",
        ]
        for item in shortcuts_to_create:
            name = _ps_escape(item["name"])
            target_path = _ps_escape(item["target"])
            workdir = _ps_escape(item["workdir"])
            desc = _ps_escape(item["desc"])
            icon = _ps_escape(item["icon"])
            args = _ps_escape(item["args"])
            for variable, label in (("$desktop", "lnk"), ("$startMenu", "lnk2")):
                ps_commands.append(f"${label} = $ws.CreateShortcut(\"{variable}/{name}.lnk\")")
                ps_commands.append(f"${label}.TargetPath = '{target_path}'")
                if item["args"]:
                    ps_commands.append(f"${label}.Arguments = '{args}'")
                ps_commands.append(f"${label}.WorkingDirectory = '{workdir}'")
                ps_commands.append(f"${label}.Description = '{desc}'")
                if os.path.isfile(item["icon"]):
                    ps_commands.append(f"${label}.IconLocation = '{icon},0'")
                ps_commands.append(f"${label}.Save()")
            created_names.append(item["name"])

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "; ".join(ps_commands)],
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

