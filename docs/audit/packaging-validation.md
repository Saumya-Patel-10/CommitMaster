# Priority 8 Audit: Windows Packaging, MSIX, and Installer Validation

**Date:** 2026-11-16  
**Auditor:** Independent Principal Windows Packaging Specialist  
**Repository:** [CommitMaster](file:///C:/Data/Saumya/AI-Projects/CommitMaster)  
**Overall Verdict:** **FAIL (Packaging Discrepancies and Incompatible Installer Scripts)**

---

## 1. Executive Summary

This audit evaluates the Windows packaging implementation:
- Executable generation ([build_exe.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_exe.py))
- MSIX generation for Microsoft Store ([build_msix.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_msix.py))
- Inno Setup desktop installer ([installer.iss](file:///C:/Data/Saumya/AI-Projects/CommitMaster/installer.iss), [build_installer.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_installer.py))
- Packaging staging ([package_layout/stage_packages.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/package_layout/stage_packages.py))
- Target identities ([store_identity.json](file:///C:/Data/Saumya/AI-Projects/CommitMaster/store_identity.json), [package_layout/identities.json](file:///C:/Data/Saumya/AI-Projects/CommitMaster/package_layout/identities.json))

### Key Findings:
1. **Broken Desktop Installer Pipeline (FINDING-PKG-01):**
   - [build_installer.py:60](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_installer.py#L60) looks for `dist/CommitMaster.exe`.
   - [installer.iss:8](file:///C:/Data/Saumya/AI-Projects/CommitMaster/installer.iss#L8) hardcodes `#define MyAppExeName "CommitMaster.exe"`.
   - However, [build_exe.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_exe.py) now produces `CommitMaster-User.exe`, `CommitMaster-Admin.exe`, and `CommitMaster-Demo.exe`.
   - As a result, compiling the installer fails immediately with:
     `[ERROR] Required executable not found at: ...\dist\CommitMaster.exe`
2. **Microsoft Store Version Downgrade Incompatibility (FINDING-PKG-02):**
   - The Windows PC has an existing installed AppX package:
     `PackageFullName: SaumyaPatel.CommitMaster_3.0.1.0_x64__3wg4h8y0g6jct`
     `Version: 3.0.1.0`
   - In `store_identity.json`, the version is set to `"version": "1.1.0.0"`.
   - On Windows, attempting to install an MSIX with a lower version number (`1.1.0.0` < `3.0.1.0`) is rejected by the App Installer with error `0x80073CF3 (Package downgrade blocked)`.
3. **Missing Admin & Demo MSIX Packaging:**
   - [build_msix.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_msix.py) only packages the User edition (`CommitMaster.msix`).
   - There are no packaging targets or manifest generators for `CommitMaster-Admin.msix` or `CommitMaster-Demo.msix`.

---

## 2. Packaging Identity & Artifact Verification Matrix

| Property | User Application | Admin Application | Demo Application | Specification Compliance |
| :--- | :--- | :--- | :--- | :--- |
| **Package Identity Name** | `SaumyaPatel.CommitMaster` | `SaumyaPatel.CommitMaster.Admin` | `SaumyaPatel.CommitMaster.Demo` | **PASS (Configured in identities.json)** |
| **Publisher** | `CN=7522A476-A1F1-4D1A-80FA-BEFE0A4BF5F8` | `CN=CommitMaster-Admin-Private` | `CN=CommitMaster-Demo-Staging` | **PASS (Configured in identities.json)** |
| **Configured Version** | `1.1.0.0` | `1.0.0.0` | `1.0.0.0` | **FAIL (Upgrade conflict with 3.0.1.0)** |
| **Executable Name** | `CommitMaster-User.exe` | `CommitMaster-Admin.exe` | `CommitMaster-Demo.exe` | **PASS (Configured in build_exe.py)** |
| **Inno Setup Script** | Hardcoded `CommitMaster.exe` | Unimplemented | Unimplemented | **FAIL (installer.iss out of date)** |
| **MSIX Builder Support** | Implemented (`build_msix.py`) | Unimplemented | Unimplemented | **FAIL (Admin/Demo missing)** |
| **Authenticode Signature** | Supported via `signtool.exe` | Supported via `signtool.exe` | Supported via `signtool.exe` | **PASS (Conditional on PFX)** |

---

## 3. Detailed Packaging Findings

### [FINDING-PKG-01] Broken Desktop Installer Pipeline (Inno Setup)
- **Files Affected:** [installer.iss:8, 46](file:///C:/Data/Saumya/AI-Projects/CommitMaster/installer.iss#L8), [build_installer.py:60](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_installer.py#L60)
- **Root Cause:**
  When Cursor split the binary into three separate executables (`CommitMaster-User.exe`, `CommitMaster-Admin.exe`, `CommitMaster-Demo.exe`), it failed to update the Inno Setup files.
  `installer.iss` still contains:
  ```iss
  #define MyAppExeName "CommitMaster.exe"
  ...
  [Files]
  Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
  ```
  And `build_installer.py` lines 60-64 contain:
  ```python
  exe_path = os.path.join(DIST_DIR, "CommitMaster.exe")
  if not os.path.exists(exe_path):
      print(f"[ERROR] Required executable not found at: {exe_path}")
      sys.exit(1)
  ```
- **Impact:** The automated installer build cannot run. No Windows desktop installer executable can be created.

---

### [FINDING-PKG-02] Windows AppX / MSIX Version Downgrade Rejection
- **Files Affected:** [store_identity.json:6](file:///C:/Data/Saumya/AI-Projects/CommitMaster/store_identity.json#L6), [package_layout/identities.json:7](file:///C:/Data/Saumya/AI-Projects/CommitMaster/package_layout/identities.json#L7)
- **Root Cause:**
  Inspection of the system's AppX registry via `Get-AppxPackage -Name "*CommitMaster*"` reveals that an earlier build was deployed with version `3.0.1.0`.
  `store_identity.json` declares:
  ```json
  "version": "1.1.0.0"
  ```
  In Windows MSIX deployment rules, packages with the same `Identity Name` (`SaumyaPatel.CommitMaster`) and `Publisher` cannot be updated to a lower semantic quadruple version. Windows App Installer explicitly refuses downgrades to prevent roll-back attacks.
- **Impact:** Any user currently having `3.0.1.0` installed will receive an installation failure when attempting to install or update to `1.1.0.0`.
- **Recommended Correction:** Increment `store_identity.json` and `package_layout/identities.json` to version `3.1.0.0` or higher.

---

### [FINDING-PKG-03] MSIX Builder Missing Admin and Demo Generation
- **Files Affected:** [build_msix.py:180-220](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_msix.py#L180-L220)
- **Root Cause:**
  `build_msix.py` is hardcoded to generate only one output file: `dist/CommitMaster.msix`. It does not accept command-line arguments to target the Admin or Demo product profiles defined in [package_layout/identities.json](file:///C:/Data/Saumya/AI-Projects/CommitMaster/package_layout/identities.json).
- **Impact:** Only the User app can be packaged as an MSIX; Admin and Demo are left without MSIX distribution artifacts.

---

## 4. Verdict & Remediations

### Acceptance Criteria Verdict:
- **Executable Identity Isolation:** **PASS**
- **Store Identity Preservation:** **PASS**
- **Desktop Installer Compatibility:** **FAIL**
- **Upgrade Path from Installed App:** **FAIL**

### Required Remediation for Cursor:
1. Update [store_identity.json](file:///C:/Data/Saumya/AI-Projects/CommitMaster/store_identity.json) to `"version": "3.1.0.0"`.
2. Update [installer.iss](file:///C:/Data/Saumya/AI-Projects/CommitMaster/installer.iss) to reference `CommitMaster-User.exe` (or build a multi-app setup wizard).
3. Update [build_installer.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_installer.py) to check for `CommitMaster-User.exe`.
4. Extend [build_msix.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_msix.py) with a `--product` argument supporting `user`, `admin`, and `demo`.
