"""
Build CommitMaster as standalone Windows .exe applications using PyInstaller:
  1. CommitMaster.exe       → Public release for Microsoft Store / users (from app.py)
  2. CommitMaster-Admin.exe → Saumya's private personal administrative tool (from admin_app.py)

Can be launched directly or by double-clicking 'Build_All_Packages.bat'.
"""
import os
import subprocess
import sys
import zipfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def build_single(target_script: str, exe_name: str, description: str, icon_file: str = "icon_user.ico", version_file: Optional[str] = None) -> str:
    print(f"\n[{description}] Compiling {exe_name}...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--onefile",
        "--noconsole",
        "--name", exe_name,
        "--add-data", f"{APP_DIR}/commitmaster;commitmaster",
        "--add-data", f"{APP_DIR}/assets;assets",
        "--hidden-import", "pystray",
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageTk",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "winreg",
        "--hidden-import", "commitmaster.paths",
        "--hidden-import", "commitmaster.tray_manager",
        "--hidden-import", "commitmaster.startup_manager",
        "--hidden-import", "commitmaster.social_auth",
        "--hidden-import", "commitmaster.forgot_password_dialog",
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
