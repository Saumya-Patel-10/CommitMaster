"""
CommitMaster — MSIX Packaging Engine for Microsoft Store & Windows Desktop Bridge.
====================================================================================
Packages CommitMaster into an official .msix installer package ready for:
  1. Direct submission to the Microsoft Partner Center / Microsoft Store
  2. Direct side-loading and installation on Windows 10/11 PCs

Prerequisites:
  - dist/CommitMaster.exe (compiled via build_exe.py)
  - Windows 10/11 SDK tools (makeappx.exe, signtool.exe)
"""
import glob
import os
import subprocess
import sys
from PIL import Image

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(APP_DIR, "dist")
LAYOUT_DIR = os.path.join(APP_DIR, "msix_layout")
ASSETS_DIR = os.path.join(LAYOUT_DIR, "Assets")
OUTPUT_MSIX = os.path.join(DIST_DIR, "CommitMaster.msix")

# App identity details for Microsoft Store
PACKAGE_NAME = "CommitMaster"
PACKAGE_DISPLAY_NAME = "CommitMaster"
PUBLISHER_NAME = "CN=SaumyaPatel"
PUBLISHER_DISPLAY_NAME = "Saumya Patel"
VERSION = "3.0.0.0"


def find_windows_kit_tool(tool_name: str) -> str:
    """Find makeappx.exe or signtool.exe in installed Windows Kits."""
    patterns = [
        rf"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\{tool_name}",
        rf"C:\Program Files\Windows Kits\10\bin\*\x64\{tool_name}",
        rf"C:\Program Files (x86)\Windows Kits\10\App Certification Kit\{tool_name}",
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            # Pick highest version
            matches.sort(reverse=True)
            return matches[0]
    return ""


def generate_store_assets():
    """Generate all required Microsoft Store asset PNGs from icon.ico."""
    os.makedirs(ASSETS_DIR, exist_ok=True)
    ico_path = os.path.join(APP_DIR, "icon_user.ico")
    if not os.path.exists(ico_path):
        ico_path = os.path.join(APP_DIR, "icon.ico")

    base_img = None
    if os.path.exists(ico_path):
        try:
            base_img = Image.open(ico_path).convert("RGBA")
        except Exception:
            pass

    if base_img is None:
        base_img = Image.new("RGBA", (256, 256), (33, 38, 45, 255))

    sizes = {
        "Square150x150Logo.png": (150, 150),
        "Square44x44Logo.png": (44, 44),
        "StoreLogo.png": (50, 50),
        "Wide310x150Logo.png": (310, 150),
        "SplashScreen.png": (620, 300),
    }

    for fname, (w, h) in sizes.items():
        out_file = os.path.join(ASSETS_DIR, fname)
        canvas = Image.new("RGBA", (w, h), (13, 17, 23, 255))
        # Scale icon to fit nicely
        icon_dim = int(min(w, h) * 0.72)
        scaled_icon = base_img.resize((icon_dim, icon_dim), Image.Resampling.LANCZOS)
        offset_x = (w - icon_dim) // 2
        offset_y = (h - icon_dim) // 2
        canvas.paste(scaled_icon, (offset_x, offset_y), scaled_icon)
        canvas.save(out_file, "PNG")

    print("[OK] Microsoft Store visual assets generated in msix_layout/Assets/")


def generate_appx_manifest():
    """Write standard AppxManifest.xml for Windows 10/11 Desktop Bridge."""
    manifest_path = os.path.join(LAYOUT_DIR, "AppxManifest.xml")
    content = f"""<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap rescap">

  <Identity
    Name="{PACKAGE_NAME}"
    Publisher="{PUBLISHER_NAME}"
    Version="{VERSION}"
    ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>{PACKAGE_DISPLAY_NAME}</DisplayName>
    <PublisherDisplayName>{PUBLISHER_DISPLAY_NAME}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <Description>CommitMaster — Developer session companion for intelligent Git commits, reminders, and repository monitoring.</Description>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>

  <Resources>
    <Resource Language="x-generate" />
  </Resources>

  <Applications>
    <Application Id="App"
      Executable="CommitMaster.exe"
      EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="{PACKAGE_DISPLAY_NAME}"
        Description="Developer session companion for intelligent Git commits, reminders, and repository monitoring."
        BackgroundColor="#0d1117"
        Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" />
        <uap:SplashScreen Image="Assets\\SplashScreen.png" BackgroundColor="#0d1117" />
      </uap:VisualElements>
    </Application>
  </Applications>

  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(content.strip())
    print("[OK] AppxManifest.xml generated successfully.")


def build_msix_package():
    print("=" * 65)
    print("      CommitMaster — MSIX Packaging Engine")
    print("=" * 65)

    exe_src = os.path.join(DIST_DIR, "CommitMaster.exe")
    if not os.path.exists(exe_src):
        print(f"[ERROR] '{exe_src}' not found! Run build_exe.py first to compile the binary.")
        sys.exit(1)

    os.makedirs(LAYOUT_DIR, exist_ok=True)
    os.makedirs(DIST_DIR, exist_ok=True)

    # 1. Copy executable into layout directory
    import shutil
    dest_exe = os.path.join(LAYOUT_DIR, "CommitMaster.exe")
    shutil.copy2(exe_src, dest_exe)
    print(f"[OK] Staged CommitMaster.exe into {LAYOUT_DIR}")

    # 2. Generate Store Visual Assets
    generate_store_assets()

    # 3. Generate AppxManifest.xml
    generate_appx_manifest()

    # 4. Find makeappx.exe
    makeappx = find_windows_kit_tool("makeappx.exe")
    if not makeappx:
        print("\n[WARN] 'makeappx.exe' not found in standard Windows SDK directories.")
        print("Staged layout is ready at: " + LAYOUT_DIR)
        print("You can package it using MSIX Packaging Tool or Partner Center.")
        return False

    print(f"[TOOL] Using makeappx: {makeappx}")

    # 5. Pack MSIX
    cmd = [makeappx, "pack", "/d", LAYOUT_DIR, "/p", OUTPUT_MSIX, "/o"]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print("[ERROR] makeappx failed to pack MSIX.")
        return False

    print("\n" + "=" * 65)
    print(f"[SUCCESS] MSIX package compiled successfully!")
    print(f"Location: {OUTPUT_MSIX}")
    print("=" * 65)
    print("Ready for upload to Microsoft Partner Center Store submission.")
    return True


if __name__ == "__main__":
    build_msix_package()
