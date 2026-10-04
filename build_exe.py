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
        print("\n✅ Build succeeded!")
        print(f"   Executable: {APP_DIR}\\dist\\CommitMaster.exe")
    else:
        print("\n❌ Build failed. Check the output above for errors.")
        sys.exit(1)


if __name__ == "__main__":
    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    build()
