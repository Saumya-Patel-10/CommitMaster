"""
Build CommitMaster as standalone Windows .exe applications using PyInstaller:
  1. CommitMaster.exe       → Public release for Microsoft Store / users (from app.py)
  2. CommitMaster-Admin.exe → Saumya's private personal administrative tool (from admin_app.py)

Can be launched directly or by double-clicking 'Build_All_Packages.bat'.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from typing import Optional

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _stage_public_assets() -> str:
    """Copy assets for the public build, excluding per-user avatars (private data)."""
    dest = os.path.join(APP_DIR, "build", "public_assets")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(os.path.join(APP_DIR, "assets"), dest,
                    ignore=shutil.ignore_patterns("avatars"))
    return dest


def build_single(target_script: str, exe_name: str, description: str, icon_file: str = "icon_user.ico", version_file: Optional[str] = None) -> str:
    print(f"\n[{description}] Compiling {exe_name}...")
    is_admin_build = target_script == "admin_app.py"
    assets_src = os.path.join(APP_DIR, "assets") if is_admin_build else _stage_public_assets()
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--onefile",
        "--noconsole",
        "--name", exe_name,
        "--add-data", f"{assets_src};assets",
    ]
    if is_admin_build:
        cmd += ["--hidden-import", "admin_app",
                "--hidden-import", "commitmaster.admin_portal"]
    else:
        # The public/Store build must contain NO admin console code at all.
        cmd += ["--exclude-module", "admin_app",
                "--exclude-module", "commitmaster.admin_portal"]
    cmd += [
        "--hidden-import", "commitmaster.edition",
        "--hidden-import", "commitmaster.ai_setup",
        "--hidden-import", "commitmaster.setup_wizard",
        "--hidden-import", "pystray",
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageTk",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "winreg",
        "--hidden-import", "psutil",
        "--collect-all", "requests",
        "--collect-all", "urllib3",
        "--collect-all", "certifi",
        "--collect-all", "charset_normalizer",
        "--collect-all", "idna",
        "--hidden-import", "sqlite3",
        "--collect-all", "plyer",
        "--hidden-import", "plyer.platforms.win.notification",
        "--hidden-import", "commitmaster",
        "--hidden-import", "commitmaster.account_manager",
        "--hidden-import", "commitmaster.ai_messages",
        "--hidden-import", "commitmaster.app_styles",
        "--hidden-import", "commitmaster.avatar_utils",
        "--hidden-import", "commitmaster.charts",
        "--hidden-import", "commitmaster.commit_composer",
        "--hidden-import", "commitmaster.commit_engine",
        "--hidden-import", "commitmaster.config",
        "--hidden-import", "commitmaster.database",
        "--hidden-import", "commitmaster.file_inspector",
        "--hidden-import", "commitmaster.flow",
        "--hidden-import", "commitmaster.forgot_password_dialog",
        "--hidden-import", "commitmaster.github_account_dialog",
        "--hidden-import", "commitmaster.github_service",
        "--hidden-import", "commitmaster.ide_selector",
        "--hidden-import", "commitmaster.issue_view",
        "--hidden-import", "commitmaster.logger",
        "--hidden-import", "commitmaster.login_window",
        "--hidden-import", "commitmaster.navigation",
        "--hidden-import", "commitmaster.notification_toast",
        "--hidden-import", "commitmaster.otp_service",
        "--hidden-import", "commitmaster.paths",
        "--hidden-import", "commitmaster.pattern_utils",
        "--hidden-import", "commitmaster.reminder_service",
        "--hidden-import", "commitmaster.session_monitor",
        "--hidden-import", "commitmaster.settings_ui",
        "--hidden-import", "commitmaster.social_auth",
        "--hidden-import", "commitmaster.startup_manager",
        "--hidden-import", "commitmaster.tray_manager",
        "--hidden-import", "commitmaster.ui",
        "--hidden-import", "commitmaster.user_dashboard",
        "--hidden-import", "commitmaster.windows_integration",
    ]

    if version_file:
        ver_path = os.path.join(APP_DIR, version_file)
        if os.path.exists(ver_path):
            cmd.extend(["--version-file", ver_path])

    icon_path = os.path.join(APP_DIR, icon_file)
    if not os.path.exists(icon_path):
        icon_path = os.path.join(APP_DIR, "icon.ico")
    if os.path.exists(icon_path):
        cmd.extend(["--icon", icon_path])

    cmd.append(target_script)

    result = subprocess.run(cmd, cwd=APP_DIR)
    if result.returncode != 0:
        print(f"[ERROR] Failed to compile {exe_name}.")
        sys.exit(1)

    out_path = os.path.join(APP_DIR, "dist", f"{exe_name}.exe")
    print(f"[OK] {exe_name} created successfully at: {out_path}")
    return out_path


def main():
    print("=" * 65)
    print("      CommitMaster — Standalone Packaging & Build System")
    print("=" * 65)

    # 1. Build Public User App for Microsoft Store / Public Release
    user_exe = build_single(
        target_script="app.py",
        exe_name="CommitMaster",
        description="1/2: Public User Application (for Microsoft Store / GitHub Releases)",
        icon_file="icon_user.ico",
        version_file="version_info.txt",
    )

    # 2. Build Private Admin Application for Saumya
    admin_exe = build_single(
        target_script="admin_app.py",
        exe_name="CommitMaster-Admin",
        description="2/2: Saumya's Private Admin App (Keep private, DO NOT upload to Store)",
        icon_file="icon_admin.ico",
        version_file="version_info_admin.txt",
    )

    # 3. Create public release ZIP archive
    zip_path = os.path.join(APP_DIR, "dist", "CommitMaster-v3.0-Windows.zip")
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(user_exe, "CommitMaster.exe")
            readme_path = os.path.join(APP_DIR, "README.md")
            if os.path.exists(readme_path):
                zf.write(readme_path, "README.md")
        print(f"\n[OK] Release ZIP archive created: {zip_path}")
    except Exception as exc:
        print(f"[WARN] Could not create zip archive: {exc}")

    print("\n" + "=" * 65)
    print("BUILD SUMMARY:")
    print("  • Public Store/User Binary : dist/CommitMaster.exe")
    print("  • Public Release Archive    : dist/CommitMaster-v3.0-Windows.zip")
    print("  • Saumya's Private Admin App: dist/CommitMaster-Admin.exe")
    print("=" * 65)
    print("NOTE: Only upload 'CommitMaster.exe' to Microsoft Store.")
    print("Keep 'CommitMaster-Admin.exe' for yourself to monitor users & manage data.")


if __name__ == "__main__":
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not detected. Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    main()
