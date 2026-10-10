"""
Build CommitMaster Official Windows Setup Installer (CommitMaster-Setup.exe)
"""
import os
import sys
import subprocess

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(APP_DIR, "dist")


def build_installer():
    print("=" * 65)
    print("      Building CommitMaster Windows Setup Installer")
    print("=" * 65)

    exe_src = os.path.join(DIST_DIR, "CommitMaster.exe")
    if not os.path.exists(exe_src):
        print(f"[INFO] '{exe_src}' not found. Compiling CommitMaster.exe first...")
        from build_exe import build_single
        build_single("app.py", "CommitMaster", "Public User App", "icon_user.ico", "version_info.txt")

    installer_name = "CommitMaster-Setup-v3.0"
    icon_path = os.path.join(APP_DIR, "icon_user.ico")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(APP_DIR, "icon.ico")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--onefile",
        "--noconsole",
        "--name", installer_name,
        "--add-data", f"{DIST_DIR}/CommitMaster.exe;.",
        "--add-data", f"{APP_DIR}/assets;assets",
        "--add-data", f"{APP_DIR}/icon_user.ico;.",
        "--add-data", f"{APP_DIR}/icon.ico;.",
    ]

    ver_path = os.path.join(APP_DIR, "version_info.txt")
    if os.path.exists(ver_path):
        cmd.extend(["--version-file", ver_path])

    if os.path.exists(icon_path):
        cmd.extend(["--icon", icon_path])

    cmd.append("installer.py")

    print(f"\n[Packaging] Compiling {installer_name}.exe...")
    res = subprocess.run(cmd, cwd=APP_DIR)
    if res.returncode != 0:
        print("[ERROR] Failed to compile installer.")
        sys.exit(1)

    out_installer = os.path.join(DIST_DIR, f"{installer_name}.exe")
    generic_installer = os.path.join(DIST_DIR, "CommitMaster-Setup.exe")
    import shutil
    shutil.copy2(out_installer, generic_installer)

    print("\n" + "=" * 65)
    print("SETUP INSTALLER READY:")
    print(f"  • Versioned Installer: {out_installer}")
    print(f"  • Standard Installer : {generic_installer}")
    print("=" * 65)
    return out_installer


if __name__ == "__main__":
    build_installer()
