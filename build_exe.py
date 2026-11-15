"""
Build three standalone Windows executables with PyInstaller:

  1. CommitMaster-User.exe  from app.py, product "user"
  2. CommitMaster-Admin.exe from admin_app.py, product "admin"
  3. CommitMaster-Demo.exe  from demo_app.py, product "demo"

The user build excludes the admin and demo modules. Signing and MSIX packaging
are separate steps and are not performed unless the Windows signing tools and
MSIX_TEST_CERT_PASSWORD are present. This module does not publish to the Store.
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
        import stat
        def _err(func, path, exc):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass
        shutil.rmtree(dest, onerror=_err)
    if not os.path.exists(dest):
        shutil.copytree(os.path.join(APP_DIR, "assets"), dest,
                    ignore=shutil.ignore_patterns("avatars"))
    return dest


def build_single(target_script: str, exe_name: str, description: str, icon_file: str = "icon_user.ico", version_file: Optional[str] = None, product: str = "user") -> str:
    print(f"\n[{description}] Compiling {exe_name}...")
    is_admin_build = product == "admin"
    assets_src = os.path.join(APP_DIR, "assets") if is_admin_build else _stage_public_assets()
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--noconsole",
        "--name", exe_name,
        "--add-data", f"{assets_src};assets",
    ]
    if product == "admin":
        cmd += ["--hidden-import", "admin_app",
                "--hidden-import", "commitmaster.admin_portal",
                "--hidden-import", "commitmaster.admin_client",
                "--exclude-module", "demo_app",
                "--exclude-module", "server"]
    elif product == "demo":
        cmd += ["--hidden-import", "demo_app",
                "--exclude-module", "admin_app",
                "--exclude-module", "commitmaster.admin_portal",
                "--exclude-module", "commitmaster.admin_client",
                "--exclude-module", "server"]
    else:
        cmd += ["--exclude-module", "admin_app",
                "--exclude-module", "commitmaster.admin_portal",
                "--exclude-module", "commitmaster.admin_client",
                "--exclude-module", "demo_app",
                "--exclude-module", "server"]
    cmd += ["--hidden-import", "commitmaster.product",
            "--hidden-import", "commitmaster.git_safety",
            "--hidden-import", "commitmaster.user_mode",
            "--hidden-import", "commitmaster.totp"]
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
        "--hidden-import", "commitmaster.repo_analyzer",
        "--hidden-import", "commitmaster.session_monitor",
        "--hidden-import", "commitmaster.settings_ui",
        "--hidden-import", "commitmaster.social_auth",
        "--hidden-import", "commitmaster.startup_manager",
        "--hidden-import", "commitmaster.tailscale_service",
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
        exe_name="CommitMaster-User",
        description="1/3: Public User Application",
        icon_file="icon_user.ico",
        version_file="version_info.txt",
        product="user",
    )

    # Digitally sign user_exe with Authenticode cert to prevent SmartScreen/AV blocks
    _sign_executable(user_exe)

    # 2. Build Private Admin Application for Saumya
    admin_exe = build_single(
        target_script="admin_app.py",
        exe_name="CommitMaster-Admin",
        description="2/3: Private Admin App",
        icon_file="icon_admin.ico",
        version_file="version_info_admin.txt",
        product="admin",
    )
    demo_exe = build_single(
        target_script="demo_app.py",
        exe_name="CommitMaster-Demo",
        description="3/3: Demo / Staging App",
        icon_file="icon_user.ico",
        version_file="version_info.txt",
        product="demo",
    )
    _sign_executable(admin_exe)

    # 3. Create public release ZIP archives (with anti-block launcher and cert helper)
    _create_release_zips(user_exe)

    print("\n" + "=" * 65)
    print("BUILD SUMMARY:")
    print(f"  • Public user binary : {user_exe}")
    print(f"  • Private admin binary : {admin_exe}")
    print(f"  • Demo binary : {demo_exe}")
    print("=" * 65)
    print("Store publication uses only the user package. Admin and demo are separate identities.")


def _sign_executable(exe_path: str) -> None:
    """Digitally sign an executable with Authenticode certificate if signtool is present."""
    if not os.path.exists(exe_path):
        return
    from build_msix import find_windows_kit_tool, TEST_CERT_PFX, TEST_CERT_PWD, ensure_test_certificate
    if not TEST_CERT_PWD:
        print(f"[WARN] MSIX_TEST_CERT_PASSWORD is unset. {os.path.basename(exe_path)} was not signed.")
        return
    signtool = find_windows_kit_tool("signtool.exe")
    if not signtool:
        return
    ensure_test_certificate("CN=7522A476-A1F1-4D1A-80FA-BEFE0A4BF5F8")
    if not os.path.exists(TEST_CERT_PFX):
        return
    cmd = [signtool, "sign", "/fd", "SHA256", "/a", "/f", TEST_CERT_PFX, "/p", TEST_CERT_PWD, exe_path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"[SIGN] Digitally signed {os.path.basename(exe_path)} with Authenticode certificate.")
    else:
        print(f"[WARN] Could not sign {os.path.basename(exe_path)}: {res.stderr or res.stdout}")


def _create_release_zips(user_exe: str) -> None:
    """Pack clean, virus-shielded zip archives containing the executable and helper launchers."""
    dist_dir = os.path.join(APP_DIR, "dist")
    readme_txt_path = os.path.join(dist_dir, "README.txt")
    with open(readme_txt_path, "w", encoding="utf-8") as f:
        f.write(
"""========================================================================
CommitMaster v1.0 — Intelligent Git Companion & Session Monitor
========================================================================

HOW TO RUN:
1. Extract this entire zip file to any folder on your PC.
2. Double-click the user executable in this zip (stored here as CommitMaster.exe).
   It is the public user app and does not open an admin portal.
3. Sign in or create an account to start tracking repositories.

WINDOWS DEFENDER & SMARTSCREEN NOTE:
Because CommitMaster is an independently published open-source developer tool,
Windows Defender SmartScreen may display:
"Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting."

TO RUN:
- Click "More info"
- Click "Run anyway"
(Or right-click 'Install_Certificate.bat' and select 'Run as administrator' once to permanently trust the application certificate).

PRIVACY & SECURITY GUARANTEE:
- 100% Offline Local AI & local SQLite database.
- Zero telemetry, no spyware, no secret data harvesting.
- MIT Licensed.
========================================================================
"""
        )

    # Staged files to include in zip
    files_to_pack = [
        (user_exe, "CommitMaster.exe"),
        (readme_txt_path, "README.txt"),
    ]
    for src_name, zip_name in [
        ("README.md", "README.md"),
        ("Install_Certificate.bat", "Install_Certificate.bat"),
        ("Launch_CommitMaster.bat", "Launch_CommitMaster.bat"),
        ("dist/CommitMaster-TestCert.cer", "CommitMaster-TestCert.cer"),
    ]:
        full_src = os.path.join(APP_DIR, src_name)
        if os.path.exists(full_src):
            files_to_pack.append((full_src, zip_name))

    zip_v1 = os.path.join(dist_dir, "CommitMaster-v1.0-Windows.zip")
    zip_gen = os.path.join(dist_dir, "CommitMaster.zip")

    for target_zip in (zip_v1, zip_gen):
        try:
            with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for f_src, f_arc in files_to_pack:
                    zf.write(f_src, f_arc)
            print(f"[OK] Release ZIP archive created: {target_zip}")
        except Exception as exc:
            print(f"[WARN] Failed to write {target_zip}: {exc}")


if __name__ == "__main__":
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not detected. Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    main()
