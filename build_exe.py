"""
Build CommitMaster as a standalone Windows .exe using PyInstaller.
Run:  python build_exe.py
"""
import subprocess
import sys
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    print("=== CommitMaster — Build EXE ===")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",           # single .exe
        "--noconsole",         # no terminal window
        "--name", "CommitMaster",
        "--icon", os.path.join(APP_DIR, "icon.ico"),  # optional icon
        "--add-data", f"{APP_DIR}/commitmaster;commitmaster",
        "app.py",
    ]

    # Remove icon flag if no icon file exists
    if not os.path.exists(os.path.join(APP_DIR, "icon.ico")):
        cmd = [c for c in cmd if c not in ["--icon",
               os.path.join(APP_DIR, "icon.ico")]]

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=APP_DIR)
    if result.returncode == 0:
        print("\n[OK] Build succeeded!")
        exe_path = os.path.join(APP_DIR, "dist", "CommitMaster.exe")
        print(f"   Executable: {exe_path}")

        # Package into a release ZIP archive ready to share with friends
        zip_path = os.path.join(APP_DIR, "dist", "CommitMaster-v2.0-Windows.zip")
        try:
            import zipfile
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(exe_path, "CommitMaster.exe")
                readme_path = os.path.join(APP_DIR, "README.md")
                if os.path.exists(readme_path):
                    zf.write(readme_path, "README.md")
            print(f"   Release ZIP: {zip_path}")
            print("\n[INFO] Ready to distribute! You can upload CommitMaster.exe or CommitMaster-v2.0-Windows.zip.")
        except Exception as e:
            print(f"   Could not create zip: {e}")
    else:
        print("\n[ERROR] Build failed. Check the output above for errors.")
        sys.exit(1)


if __name__ == "__main__":
    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    build()
