"""
CommitMaster — Official Windows Setup & Installation Engine.
=============================================================
Installs CommitMaster onto the user's PC:
  • Copies binary files into %LOCALAPPDATA%\\Programs\\CommitMaster
  • Creates Start Menu shortcut (%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\CommitMaster.lnk)
  • Creates Desktop shortcut (%USERPROFILE%\\Desktop\\CommitMaster.lnk)
  • Registers in Windows Search App Paths (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\CommitMaster.exe)
  • Registers in Windows "Installed Apps" / Control Panel (Uninstall entry)
  • Auto-generates clean uninstaller (Uninstall.bat)
"""
import os
import sys
import shutil
import subprocess
import winreg
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional

APP_NAME = "CommitMaster"
APP_VERSION = "3.0.0"
APP_PUBLISHER = "Saumya Patel"
APP_DESCRIPTION = "CommitMaster — Intelligent Git Companion & Developer Session Monitor"

BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INSTALL_DIR = os.path.expandvars(r"%LOCALAPPDATA%\Programs\CommitMaster")


def perform_installation(
    target_dir: str,
    create_desktop: bool = True,
    create_start_menu: bool = True,
    auto_start: bool = False,
    progress_callback=None
) -> tuple[bool, str]:
    """Execute installation files copy, shortcut creation and Windows registry registrations."""
    try:
        if progress_callback:
            progress_callback(10, "Preparing installation directory...")
        os.makedirs(target_dir, exist_ok=True)

        # 1. Locate source payload files (CommitMaster.exe, assets, icons)
        exe_src = os.path.join(BUNDLE_DIR, "CommitMaster.exe")
        if not os.path.exists(exe_src):
            # Check dist or root
            for c in [
                os.path.join(BUNDLE_DIR, "dist", "CommitMaster.exe"),
                os.path.join(os.path.dirname(BUNDLE_DIR), "dist", "CommitMaster.exe")
            ]:
                if os.path.exists(c):
                    exe_src = c
                    break

        if progress_callback:
            progress_callback(30, "Copying application binaries and resources...")

        dest_exe = os.path.join(target_dir, "CommitMaster.exe")
        if os.path.exists(exe_src):
            shutil.copy2(exe_src, dest_exe)

        # Copy icons
        for icon_name in ["icon_user.ico", "icon.ico", "icon_admin.ico"]:
            src_ico = os.path.join(BUNDLE_DIR, icon_name)
            if not os.path.exists(src_ico):
                src_ico = os.path.join(os.path.dirname(BUNDLE_DIR), icon_name)
            if os.path.exists(src_ico):
                shutil.copy2(src_ico, os.path.join(target_dir, icon_name))

        # Copy assets folder if present
        assets_src = os.path.join(BUNDLE_DIR, "assets")
        if not os.path.exists(assets_src):
            assets_src = os.path.join(os.path.dirname(BUNDLE_DIR), "assets")
        if os.path.exists(assets_src):
            dest_assets = os.path.join(target_dir, "assets")
            if os.path.exists(dest_assets):
                shutil.rmtree(dest_assets, ignore_errors=True)
            shutil.copytree(assets_src, dest_assets, dirs_exist_ok=True)

        # Copy docs
        for doc in ["README.md", "LICENSE.txt"]:
            src_doc = os.path.join(BUNDLE_DIR, doc)
            if not os.path.exists(src_doc):
                src_doc = os.path.join(os.path.dirname(BUNDLE_DIR), doc)
            if os.path.exists(src_doc):
                shutil.copy2(src_doc, os.path.join(target_dir, doc))

        if progress_callback:
            progress_callback(60, "Configuring Windows shortcuts and Search Index...")

        # 2. Shortcuts creation via PowerShell
        ico_dest = os.path.join(target_dir, "icon_user.ico")
        if not os.path.exists(ico_dest):
            ico_dest = os.path.join(target_dir, "icon.ico")
        icon_arg = dest_exe if os.path.exists(dest_exe) else ico_dest

        ps_cmds = ["$ws = New-Object -ComObject WScript.Shell"]

        if create_desktop:
            desktop = os.path.expandvars(r"%USERPROFILE%\Desktop\CommitMaster.lnk").replace("\\", "/")
            ps_cmds.append(f"$lnk = $ws.CreateShortcut('{desktop}')")
            ps_cmds.append(f"$lnk.TargetPath = '{dest_exe.replace(chr(92), '/')}'")
            ps_cmds.append(f"$lnk.WorkingDirectory = '{target_dir.replace(chr(92), '/')}'")
            ps_cmds.append(f"$lnk.Description = '{APP_DESCRIPTION}'")
            ps_cmds.append(f"$lnk.IconLocation = '{icon_arg.replace(chr(92), '/')},0'")
            ps_cmds.append("$lnk.Save()")

        if create_start_menu:
            start_menu_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")
            os.makedirs(start_menu_dir, exist_ok=True)
            start_lnk = os.path.join(start_menu_dir, "CommitMaster.lnk").replace("\\", "/")
            ps_cmds.append(f"$lnk2 = $ws.CreateShortcut('{start_lnk}')")
            ps_cmds.append(f"$lnk2.TargetPath = '{dest_exe.replace(chr(92), '/')}'")
            ps_cmds.append(f"$lnk2.WorkingDirectory = '{target_dir.replace(chr(92), '/')}'")
            ps_cmds.append(f"$lnk2.Description = '{APP_DESCRIPTION}'")
            ps_cmds.append(f"$lnk2.IconLocation = '{icon_arg.replace(chr(92), '/')},0'")
            ps_cmds.append("$lnk2.Save()")

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "; ".join(ps_cmds)],
            capture_output=True,
            timeout=10,
            creationflags=flags
        )

        if progress_callback:
            progress_callback(80, "Registering application with Windows OS...")

        # 3. Register in Windows App Paths (so Win+R and Windows Search Bar find it immediately)
        try:
            ap_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\CommitMaster.exe")
            winreg.SetValueEx(ap_key, "", 0, winreg.REG_SZ, dest_exe)
            winreg.SetValueEx(ap_key, "Path", 0, winreg.REG_SZ, target_dir)
            winreg.CloseKey(ap_key)
        except Exception:
            pass

        # 4. Register in Windows Classes Applications
        try:
            cls_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\Applications\CommitMaster.exe")
            winreg.SetValueEx(cls_key, "FriendlyAppName", 0, winreg.REG_SZ, "CommitMaster")
            winreg.SetValueEx(cls_key, "ApplicationCompany", 0, winreg.REG_SZ, "CommitMaster")
            winreg.CloseKey(cls_key)
        except Exception:
            pass

        # 5. Create Uninstaller Script (Uninstall.bat)
        uninstaller_path = os.path.join(target_dir, "Uninstall.bat")
        uninstall_content = f"""@echo off
title CommitMaster Uninstaller
echo Uninstalling CommitMaster from your PC...
taskkill /f /im CommitMaster.exe >nul 2>&1
timeout /t 1 /nobreak >nul
del /f /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\CommitMaster.lnk" >nul 2>&1
del /f /q "%USERPROFILE%\\Desktop\\CommitMaster.lnk" >nul 2>&1
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\CommitMaster.exe" /f >nul 2>&1
reg delete "HKCU\\Software\\Classes\\Applications\\CommitMaster.exe" /f >nul 2>&1
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\CommitMaster" /f >nul 2>&1
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v CommitMaster /f >nul 2>&1
cd "%TEMP%"
rmdir /s /q "{target_dir}" >nul 2>&1
echo.
echo CommitMaster has been successfully uninstalled.
pause
"""
        with open(uninstaller_path, "w", encoding="utf-8") as f:
            f.write(uninstall_content)

        # 6. Register in Windows "Installed Apps" / Control Panel
        try:
            un_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CommitMaster")
            winreg.SetValueEx(un_key, "DisplayName", 0, winreg.REG_SZ, "CommitMaster")
            winreg.SetValueEx(un_key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(un_key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
            winreg.SetValueEx(un_key, "DisplayIcon", 0, winreg.REG_SZ, f"{dest_exe},0")
            winreg.SetValueEx(un_key, "InstallLocation", 0, winreg.REG_SZ, target_dir)
            winreg.SetValueEx(un_key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller_path}"')
            winreg.SetValueEx(un_key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(un_key, "NoRepair", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(un_key)
        except Exception:
            pass

        # 7. Auto startup toggle if selected
        if auto_start:
            try:
                run_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(run_key, "CommitMaster", 0, winreg.REG_SZ, f'"{dest_exe}"')
                winreg.CloseKey(run_key)
            except Exception:
                pass

        if progress_callback:
            progress_callback(100, "Installation completed successfully!")

        return True, "Installation complete!"
    except Exception as exc:
        return False, str(exc)


class InstallerGUI:
    """Modern dark-mode Windows installation wizard for CommitMaster."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("CommitMaster Setup — v3.0.0")
        self.root.geometry("540x440")
        self.root.resizable(False, False)
        self.root.configure(bg="#0d1117")

        # Center on screen
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - 540) // 2
        y = (sh - 440) // 2
        self.root.geometry(f"540x440+{x}+{y}")

        # Set icon
        ico_candidates = [
            os.path.join(BUNDLE_DIR, "icon_user.ico"),
            os.path.join(BUNDLE_DIR, "icon.ico"),
        ]
        for c in ico_candidates:
            if os.path.exists(c):
                try:
                    self.root.iconbitmap(c)
                    break
                except Exception:
                    pass

        self._install_dir_var = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self._desktop_var = tk.BooleanVar(value=True)
        self._start_menu_var = tk.BooleanVar(value=True)
        self._startup_var = tk.BooleanVar(value=False)
        self._launch_now_var = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self):
        # Header banner
        hdr = tk.Frame(self.root, bg="#161b22", height=80, padx=20, pady=12)
        hdr.pack(fill="x")

        tk.Label(
            hdr, text="CommitMaster Setup",
            font=("Segoe UI", 16, "bold"), fg="#ffffff", bg="#161b22"
        ).pack(anchor="w")

        tk.Label(
            hdr, text="Intelligent Git Companion & Developer Session Monitor — v3.0",
            font=("Segoe UI", 9), fg="#8b949e", bg="#161b22"
        ).pack(anchor="w", pady=(2, 0))

        tk.Frame(self.root, height=2, bg="#3fb950").pack(fill="x")

        # Main body container
        body = tk.Frame(self.root, bg="#0d1117", padx=24, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text="Install CommitMaster as a native Windows application on your computer:",
            font=("Segoe UI", 10), fg="#c9d1d9", bg="#0d1117"
        ).pack(anchor="w", pady=(0, 10))

        # Destination Folder Card
        dest_card = tk.Frame(body, bg="#161b22", padx=14, pady=10, highlightthickness=1, highlightbackground="#30363d")
        dest_card.pack(fill="x", pady=(0, 12))

        tk.Label(
            dest_card, text="Destination Folder:",
            font=("Segoe UI", 9, "bold"), fg="#8b949e", bg="#161b22"
        ).pack(anchor="w")

        dir_row = tk.Frame(dest_card, bg="#161b22")
        dir_row.pack(fill="x", pady=(4, 0))

        dir_ent = tk.Entry(
            dir_row, textvariable=self._install_dir_var, font=("Segoe UI", 9),
            bg="#0d1117", fg="#ffffff", relief="flat", highlightthickness=1, highlightbackground="#30363d"
        )
        dir_ent.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 8))

        browse_btn = tk.Button(
            dir_row, text="Browse...", font=("Segoe UI", 9),
            bg="#21262d", fg="#c9d1d9", relief="flat", bd=0, cursor="hand2", padx=10, pady=3,
            command=self._browse_dir
        )
        browse_btn.pack(side="right")

        # Shortcuts Options Card
        opt_card = tk.Frame(body, bg="#161b22", padx=14, pady=10, highlightthickness=1, highlightbackground="#30363d")
        opt_card.pack(fill="x", pady=(0, 14))

        tk.Label(
            opt_card, text="Windows Integration Options:",
            font=("Segoe UI", 9, "bold"), fg="#8b949e", bg="#161b22"
        ).pack(anchor="w", pady=(0, 4))

        for text, var in [
            ("Create Desktop Shortcut", self._desktop_var),
            ("Add to Start Menu & Windows Search Bar", self._start_menu_var),
            ("Launch automatically when Windows starts", self._startup_var),
        ]:
            cb = tk.Checkbutton(
                opt_card, text=text, variable=var,
                font=("Segoe UI", 9), fg="#c9d1d9", bg="#161b22",
                selectcolor="#0d1117", activebackground="#161b22", activeforeground="#ffffff"
            )
            cb.pack(anchor="w", pady=2)

        # Progress bar (hidden initially)
        self._prog_frame = tk.Frame(body, bg="#0d1117")
        self._prog_bar = ttk.Progressbar(self._prog_frame, orient="horizontal", mode="determinate")
        self._prog_bar.pack(fill="x", pady=(0, 4))
        self._status_lbl = tk.Label(self._prog_frame, text="", font=("Segoe UI", 9), fg="#3fb950", bg="#0d1117")
        self._status_lbl.pack(anchor="w")

        # Footer Buttons
        footer = tk.Frame(self.root, bg="#161b22", height=56, padx=20, pady=10)
        footer.pack(side="bottom", fill="x")

        cancel_btn = tk.Button(
            footer, text="Cancel", font=("Segoe UI", 9),
            bg="#21262d", fg="#8b949e", relief="flat", bd=0, cursor="hand2", padx=16, pady=6,
            command=self.root.destroy
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        self._install_btn = tk.Button(
            footer, text="🚀 Install CommitMaster", font=("Segoe UI", 9, "bold"),
            bg="#238636", fg="#ffffff", activebackground="#2ea043", activeforeground="#ffffff",
            relief="flat", bd=0, cursor="hand2", padx=20, pady=6,
            command=self._start_install
        )
        self._install_btn.pack(side="right")

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self._install_dir_var.get(), title="Select Install Folder")
        if d:
            self._install_dir_var.set(os.path.join(d, "CommitMaster"))

    def _start_install(self):
        self._install_btn.config(state="disabled", text="Installing...")
        self._prog_frame.pack(fill="x", pady=(0, 10))

        def _update_prog(percent, msg):
            self._prog_bar["value"] = percent
            self._status_lbl.config(text=msg)
            self.root.update_idletasks()

        target = self._install_dir_var.get().strip()
        ok, msg = perform_installation(
            target_dir=target,
            create_desktop=self._desktop_var.get(),
            create_start_menu=self._start_menu_var.get(),
            auto_start=self._startup_var.get(),
            progress_callback=_update_prog
        )

        if ok:
            dest_exe = os.path.join(target, "CommitMaster.exe")
            # Show completed screen
            self._show_finish_screen(dest_exe)
        else:
            messagebox.showerror("Installation Error", f"Installation failed:\n{msg}", parent=self.root)
            self._install_btn.config(state="normal", text="🚀 Install CommitMaster")

    def _show_finish_screen(self, dest_exe: str):
        for w in self.root.winfo_children():
            w.destroy()

        hdr = tk.Frame(self.root, bg="#161b22", height=80, padx=20, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="✔ CommitMaster Installed!", font=("Segoe UI", 16, "bold"), fg="#3fb950", bg="#161b22").pack(anchor="w")
        tk.Label(hdr, text="CommitMaster is now installed and indexed in your Windows Search Bar.", font=("Segoe UI", 9), fg="#8b949e", bg="#161b22").pack(anchor="w", pady=(2, 0))
        tk.Frame(self.root, height=2, bg="#3fb950").pack(fill="x")

        body = tk.Frame(self.root, bg="#0d1117", padx=24, pady=24)
        body.pack(fill="both", expand=True)

        card = tk.Frame(body, bg="#161b22", padx=16, pady=16, highlightthickness=1, highlightbackground="#30363d")
        card.pack(fill="x", pady=(0, 16))

        tk.Label(card, text="Ready for use:", font=("Segoe UI", 11, "bold"), fg="#ffffff", bg="#161b22").pack(anchor="w")
        tk.Label(card, text="• Available in Start Menu and Windows Search Bar (Type 'CommitMaster')\n"
                            "• Taskbar Notification panel & System Tray enabled\n"
                            "• Native Windows process registered (shows as CommitMaster in Task Manager)",
                 font=("Segoe UI", 9), fg="#8b949e", bg="#161b22", justify="left").pack(anchor="w", pady=(8, 0))

        launch_cb = tk.Checkbutton(
            body, text="Launch CommitMaster now", variable=self._launch_now_var,
            font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#0d1117",
            selectcolor="#161b22", activebackground="#0d1117", activeforeground="#ffffff"
        )
        launch_cb.pack(anchor="w", pady=(0, 16))

        footer = tk.Frame(self.root, bg="#161b22", height=56, padx=20, pady=10)
        footer.pack(side="bottom", fill="x")

        def _finish():
            if self._launch_now_var.get() and os.path.exists(dest_exe):
                try:
                    subprocess.Popen([dest_exe], cwd=os.path.dirname(dest_exe))
                except Exception:
                    pass
            self.root.destroy()

        fin_btn = tk.Button(
            footer, text="Finish", font=("Segoe UI", 9, "bold"),
            bg="#238636", fg="#ffffff", activebackground="#2ea043", activeforeground="#ffffff",
            relief="flat", bd=0, cursor="hand2", padx=24, pady=6,
            command=_finish
        )
        fin_btn.pack(side="right")

    def run(self):
        self.root.mainloop()


def main():
    if "/S" in sys.argv or "--silent" in sys.argv:
        target = DEFAULT_INSTALL_DIR
        for arg in sys.argv:
            if arg.startswith("/D="):
                target = arg.split("=", 1)[1]
        perform_installation(target)
        sys.exit(0)

    app = InstallerGUI()
    app.run()


if __name__ == "__main__":
    main()
