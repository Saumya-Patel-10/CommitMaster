"""
CommitMaster — Windows Setup Installer Builder.
=================================================
Compiles Inno Setup script (installer.iss) into a standalone setup wizard executable:
  - dist/CommitMaster-Setup-v1.0.exe
  - dist/CommitMaster-Setup.exe
Digitally signs with Authenticode certificate.
"""
import glob
import os
import shutil
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(APP_DIR, "dist")
ISS_FILE = os.path.join(APP_DIR, "installer.iss")
OUTPUT_SETUP_VERSIONED = os.path.join(DIST_DIR, "CommitMaster-Setup-v1.0.exe")
OUTPUT_SETUP_ALIAS = os.path.join(DIST_DIR, "CommitMaster-Setup.exe")
TEST_CERT_PFX = os.path.join(DIST_DIR, "CommitMaster-TestCert.pfx")
TEST_CERT_PWD = "CommitMaster2026!"


def find_iscc() -> str:
    """Find Inno Setup compiler ISCC.exe."""
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    which = shutil.which("iscc")
    if which:
        return which
    return ""


def find_signtool() -> str:
    """Find Windows SDK signtool.exe."""
    patterns = [
        r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe",
        r"C:\Program Files\Windows Kits\10\bin\*\x64\signtool.exe",
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            matches.sort(reverse=True)
            return matches[0]
    which = shutil.which("signtool")
    return which or ""


def build_installer():
    print("=" * 65)
    print("CommitMaster — Building Inno Setup Installer Package")
    print("=" * 65)

    exe_path = os.path.join(DIST_DIR, "CommitMaster.exe")
    if not os.path.exists(exe_path):
        print(f"[ERROR] Required executable not found at: {exe_path}")
        print("Please run python build_exe.py first.")
        sys.exit(1)

    iscc = find_iscc()
    if not iscc:
        print("[ERROR] Inno Setup compiler (ISCC.exe) not found.")
        print("Please install Inno Setup 6: winget install JRSoftware.InnoSetup")
        sys.exit(1)

    print(f"[TOOL] Using Inno Setup Compiler: {iscc}")
    print(f"[BUILD] Compiling {ISS_FILE} ...")
    res = subprocess.run([iscc, ISS_FILE])
    if res.returncode != 0:
        print("[ERROR] Inno Setup compilation failed.")
        sys.exit(res.returncode)

    if not os.path.exists(OUTPUT_SETUP_VERSIONED):
        print(f"[ERROR] Expected output missing: {OUTPUT_SETUP_VERSIONED}")
        sys.exit(1)

    print(f"[OK] Generated: {OUTPUT_SETUP_VERSIONED}")
    shutil.copyfile(OUTPUT_SETUP_VERSIONED, OUTPUT_SETUP_ALIAS)
    print(f"[OK] Copied alias: {OUTPUT_SETUP_ALIAS}")

    # Sign the installers
    signtool = find_signtool()
    if signtool and os.path.exists(TEST_CERT_PFX):
        print(f"[TOOL] Signing setup packages with: {signtool}")
        for target in [OUTPUT_SETUP_VERSIONED, OUTPUT_SETUP_ALIAS]:
            cmd = [
                signtool,
                "sign",
                "/fd", "SHA256",
                "/a",
                "/f", TEST_CERT_PFX,
                "/p", TEST_CERT_PWD,
                "/tr", "http://timestamp.digicert.com",
                "/td", "SHA256",
                target,
            ]
            sign_res = subprocess.run(cmd)
            if sign_res.returncode == 0:
                print(f"[SIGNED] {os.path.basename(target)}")
            else:
                print(f"[WARN] Failed to sign {os.path.basename(target)}")

    print("\n" + "=" * 65)
    print("[SUCCESS] Windows Setup Installer ready for website distribution!")
    print(f"Location: {OUTPUT_SETUP_VERSIONED}")
    print("=" * 65)


if __name__ == "__main__":
    build_installer()
