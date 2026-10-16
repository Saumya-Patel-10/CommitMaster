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

# App identity details for Microsoft Store (Defaults; can be overridden via store_identity.json)
STORE_IDENTITY_FILE = os.path.join(APP_DIR, "store_identity.json")

DEFAULT_IDENTITY = {
    "package_name": "CommitMaster",
    "package_display_name": "CommitMaster",
    "publisher_name": "CN=SaumyaPatel",
    "publisher_display_name": "Saumya Patel",
    "version": "3.0.0.0",
}


def load_store_identity() -> dict:
    """Load package identity details from store_identity.json if present."""
    identity = dict(DEFAULT_IDENTITY)
    if os.path.exists(STORE_IDENTITY_FILE):
        try:
            import json
            with open(STORE_IDENTITY_FILE, "r", encoding="utf-8") as f:
                user_id = json.load(f)
                identity.update({k: v for k, v in user_id.items() if v})
            print(f"[CONFIG] Loaded Store Identity from {STORE_IDENTITY_FILE}")
        except Exception as e:
            print(f"[WARN] Failed to read store_identity.json: {e}")
    else:
        # Create a template file so the user can easily adjust Partner Center values
        try:
            import json
            with open(STORE_IDENTITY_FILE, "w", encoding="utf-8") as f:
                json.dump(identity, f, indent=2)
            print(f"[INFO] Created template identity configuration: {STORE_IDENTITY_FILE}")
        except Exception:
            pass
    return identity


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


def generate_appx_manifest(identity: dict = None):
    """Write standard AppxManifest.xml for Windows 10/11 Desktop Bridge."""
    if identity is None:
        identity = load_store_identity()

    pkg_name = identity.get("package_name", "CommitMaster")
    pkg_display = identity.get("package_display_name", "CommitMaster")
    pub_name = identity.get("publisher_name", "CN=SaumyaPatel")
    pub_display = identity.get("publisher_display_name", "Saumya Patel")
    ver = identity.get("version", "3.0.0.0")

    manifest_path = os.path.join(LAYOUT_DIR, "AppxManifest.xml")
    content = f"""<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap rescap">

  <Identity
    Name="{pkg_name}"
    Publisher="{pub_name}"
    Version="{ver}"
    ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>{pkg_display}</DisplayName>
    <PublisherDisplayName>{pub_display}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <Description>CommitMaster — Developer session companion for intelligent Git commits, reminders, and repository monitoring.</Description>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>

  <Resources>
    <Resource Language="en-us" />
  </Resources>

  <Applications>
    <Application Id="App"
      Executable="CommitMaster.exe"
      EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="{pkg_display}"
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
    print("[OK] AppxManifest.xml generated successfully (Language: en-us).")


def build_msix_package():
    print("=" * 65)
    print("      CommitMaster — MSIX Packaging Engine")
    print("=" * 65)

    exe_src = os.path.join(DIST_DIR, "CommitMaster.exe")
    if not os.path.exists(exe_src):
        print(f"[INFO] '{exe_src}' not found. Compiling CommitMaster.exe first...")
        from build_exe import build_single
        build_single("app.py", "CommitMaster", "Public User App", "icon_user.ico", "version_info.txt")

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

    # 6. Digitally Sign MSIX for local sideloading / testing
    identity = load_store_identity()
    publisher_dn = identity.get("publisher_name", "CN=7522A476-A1F1-4D1A-80FA-BEFE0A4BF5F8")
    sign_msix_package(OUTPUT_MSIX, publisher_dn)

    print("=" * 65)
    print("Ready for upload to Microsoft Partner Center Store submission,")
    print("OR direct installation via Install_Test_Certificate.bat!")
    return True


TEST_CERT_PFX = os.path.join(DIST_DIR, "CommitMaster-TestCert.pfx")
TEST_CERT_CER = os.path.join(DIST_DIR, "CommitMaster-TestCert.cer")
TEST_CERT_PWD = "CommitMaster2026!"


def ensure_test_certificate(publisher_dn: str) -> bool:
    """Ensure a matching self-signed code-signing certificate exists for local testing/sideloading."""
    os.makedirs(DIST_DIR, exist_ok=True)
    signtool = find_windows_kit_tool("signtool.exe")

    # If cert exists and signtool can sign with it, keep it
    if os.path.exists(TEST_CERT_PFX) and signtool:
        test_cmd = [signtool, "verify", "/pa", OUTPUT_MSIX]

    # Generate fresh certificate via temporary PowerShell script file
    ps_file = os.path.join(APP_DIR, "_gen_cert.ps1")
    escaped_pfx = TEST_CERT_PFX.replace("\\", "\\\\")
    escaped_cer = TEST_CERT_CER.replace("\\", "\\\\")
    script = f"""$subject = '{publisher_dn}'
$pfxPath = '{escaped_pfx}'
$cerPath = '{escaped_cer}'
$pwd = ConvertTo-SecureString -String '{TEST_CERT_PWD}' -Force -AsPlainText

$cert = New-SelfSignedCertificate -Type Custom -Subject $subject `
    -KeyUsage DigitalSignature `
    -FriendlyName 'CommitMaster Development Certificate' `
    -CertStoreLocation 'Cert:\\CurrentUser\\My' `
    -TextExtension @('2.5.29.37={{text}}1.3.6.1.5.5.7.3.3')

Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $pwd -Force | Out-Null
Export-Certificate -Cert $cert -FilePath $cerPath -Force | Out-Null
"""
    try:
        with open(ps_file, "w", encoding="utf-8") as f:
            f.write(script)
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_file],
            capture_output=True,
            text=True,
        )
        if os.path.exists(ps_file):
            try:
                os.remove(ps_file)
            except Exception:
                pass
        if res.returncode == 0 and os.path.exists(TEST_CERT_PFX) and os.path.exists(TEST_CERT_CER):
            print(f"[CERT] Development Code Signing Certificate active: {TEST_CERT_PFX}")
            return True
        else:
            print(f"[WARN] Failed to generate test cert via PowerShell: {res.stderr}")
            return False
    except Exception as e:
        if os.path.exists(ps_file):
            try:
                os.remove(ps_file)
            except Exception:
                pass
        print(f"[WARN] Error creating certificate: {e}")
        return False


def sign_msix_package(msix_path: str, publisher_dn: str) -> bool:
    """Digitally sign MSIX package for local testing and sideloading."""
    signtool = find_windows_kit_tool("signtool.exe")
    if not signtool:
        print("[WARN] 'signtool.exe' not found. MSIX remains unsigned (still 100% valid for Microsoft Store).")
        return False

    ensure_test_certificate(publisher_dn)
    if not os.path.exists(TEST_CERT_PFX):
        print("[WARN] Test PFX certificate not available for signing.")
        return False

    print(f"[SIGN] Signing MSIX with {TEST_CERT_PFX}...")
    cmd = [
        signtool,
        "sign",
        "/fd",
        "SHA256",
        "/a",
        "/f",
        TEST_CERT_PFX,
        "/p",
        TEST_CERT_PWD,
        msix_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print("[SUCCESS] CommitMaster.msix is digitally signed and ready for sideloading!")
        return True
    else:
        print(f"[WARN] signtool sign returned warning/error: {res.stderr or res.stdout}")
        return False


if __name__ == "__main__":
    build_msix_package()

