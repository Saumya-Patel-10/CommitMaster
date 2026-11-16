# Priority 1 Audit: Three Windows Applications Verification

**Date:** 2026-11-16  
**Auditor:** Independent Principal QA & Security Auditor  
**Repository:** [CommitMaster](file:///C:/Data/Saumya/AI-Projects/CommitMaster)  
**Target Commit:** `4c70715 Give each edition its own data directory and shell identity`  
**Overall Verdict:** **FAIL / NOT VERIFIED (Windows Installation Not Satisfied)**

---

## 1. Executive Summary

The specification requires verifying that the target PC can install and launch three distinct Windows applications:
1. **CommitMaster User**
2. **CommitMaster Admin**
3. **CommitMaster Demo**

These must be independent installed applications, not merely tabs or runtime flags of a single binary.

**Auditor Findings:**
- **At the Python Process Level:** The architectural split has been implemented with separate entrypoints ([app.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/app.py), [admin_app.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/admin_app.py), [demo_app.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/demo_app.py)), independent product locking via [commitmaster/product.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/commitmaster/product.py), distinct data directories in `%LOCALAPPDATA%`, and separate database files. They can execute concurrently without database lock contention.
- **At the Windows Installation & Packaging Level:** **FAILED / NOT VERIFIED**. The three applications **are not installed** on the Windows machine. Only one legacy MSIX package (`SaumyaPatel.CommitMaster_3.0.1.0_x64__3wg4h8y0g6jct`) is installed on the system. There are no installed Windows packages or Inno Setup installations for CommitMaster Admin or CommitMaster Demo. Furthermore, the Inno Setup script ([installer.iss](file:///C:/Data/Saumya/AI-Projects/CommitMaster/installer.iss)) and builder ([build_installer.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_installer.py)) still expect a single unified `dist/CommitMaster.exe` and fail completely when executed against the new three-app build layout.

---

## 2. Independent Dimension Verification Matrix

| Dimension | User App | Admin App | Demo App | Independent? | Verification Status | Evidence / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Executable Name** | `CommitMaster-User.exe` | `CommitMaster-Admin.exe` | `CommitMaster-Demo.exe` | Yes (in [build_exe.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_exe.py)) | **PARTIAL** | Binaries not pre-built in `dist/`. `installer.iss` hardcodes legacy `CommitMaster.exe`. |
| **Source Entrypoint** | `app.py` | `admin_app.py` | `demo_app.py` | Yes | **PASS** | Distinct entry points verified. |
| **Package Identity** | `SaumyaPatel.CommitMaster` | `SaumyaPatel.CommitMaster.Admin` | `SaumyaPatel.CommitMaster.Demo` | Planned | **FAIL** | Defined in `package_layout/identities.json`, but only `SaumyaPatel.CommitMaster` is installed in WindowsApps. |
| **Windows AppUserModelID** | `CommitMaster.App.User` | `CommitMaster.App.Admin` | `CommitMaster.App.Demo` | Yes | **PASS** | Initialized via `windows_integration.process_app_user_model_id()` and locked to process. |
| **Start Menu Entries** | None installed | `CommitMaster Admin.lnk` (pointing to unbuilt path) | None installed | No | **FAIL** | Only Admin shortcut existed in `%APPDATA%\...\Start Menu\Programs`, pointing to missing `dist/CommitMaster-Admin.exe`. |
| **Desktop Shortcuts** | `CommitMaster User.lnk` | `CommitMaster Admin.lnk` | `CommitMaster Demo.lnk` | Yes | **PASS** | Supported in `.vbs` launchers and `windows_integration.py`. |
| **Icons** | `icon_user.ico` (Cyan) | `icon_admin.ico` (Gold) | `icon_demo.ico` (Orange) | Yes | **PASS** | Distinct icon files present in root and `assets/`. |
| **Application Directories** | `%LOCALAPPDATA%\CommitMaster` | `%LOCALAPPDATA%\CommitMaster-Admin` | `%LOCALAPPDATA%\CommitMaster-Demo` | Yes | **PASS** | Verified via `paths.get_data_dir()`. |
| **Configuration Files** | `...\CommitMaster\config.json` | `...\CommitMaster-Admin\config.json` | `...\CommitMaster-Demo\config.json` | Yes | **PASS** | Fully decoupled config paths. |
| **Database Access** | `...\CommitMaster\commitmaster.db` | `...\CommitMaster-Admin\commitmaster.db` | `...\CommitMaster-Demo\commitmaster.db` | Yes | **PASS** | Verified isolated SQLite databases. |
| **Startup Behavior** | User login / dashboard | Admin portal / auth / TOTP | Staging verification / demo session | Yes | **PASS** | Verified via individual module execution. |
| **Simultaneous Execution** | Verified | Verified | Verified | Yes | **PASS** | Tested concurrently writing heartbeats; zero lock errors. |

---

## 3. Deep Dive Verification Results

### 3.1 Process Locking & Escalation Immunity
Audited [commitmaster/product.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/commitmaster/product.py):
```python
def activate(name: str) -> None:
    global _PRODUCT
    if name not in _ALL:
        raise ProductError(f"unknown product {name!r}")
    if _PRODUCT is None:
        _PRODUCT = name
        return
    if _PRODUCT == name:
        return
    raise ProductError(f"product is locked to {_PRODUCT}; refusing to become {name}")
```
**Test Performed:**
1. Activated `"user"`: `product.activate('user')`. Current product returned `'user'`.
2. Attempted to escalate to `'admin'`: `product.activate('admin')`.
3. **Result:** Raised `product.ProductError: product is locked to user; refusing to become admin`.
4. Command line flags `--admin` and `--admin-edition` passed to `app.py` are stripped before execution in [app.py:246-248](file:///C:/Data/Saumya/AI-Projects/CommitMaster/app.py#L246-L248).

### 3.2 Directory Cross-Contamination Prevention
Audited [commitmaster/paths.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/commitmaster/paths.py):
```python
def resolve_data_dir(env_dir: str, own_name: str) -> str:
    foreign = _foreign_folder(env_dir, own_name)
    if foreign:
        raise DataDirectoryError(
            f"This product stores data in {own_name} and refuses {foreign}."
        )
```
**Test Performed:**
1. Activated User product.
2. Set `COMMITMASTER_DATA_DIR` pointing to `%LOCALAPPDATA%\CommitMaster-Admin`.
3. Invoked `paths.get_data_dir()`.
4. **Result:** Blocked with `paths.DataDirectoryError: This product stores data in CommitMaster and refuses CommitMaster-Admin.`

### 3.3 Simultaneous Concurrency Test
**Test Setup:**
Spawned three concurrent Python processes in disposable test directories representing `user`, `admin`, and `demo`. Each process initialized its schema and executed 10 atomic transactions against its respective SQLite database over 1 second.
**Result:**
- User process: 10 transactions completed cleanly.
- Admin process: 10 transactions completed cleanly.
- Demo process: 10 transactions completed cleanly.
- No SQLite `database is locked` (`busy_timeout`) errors occurred.

### 3.4 Windows Packaging & Installation Defect Analysis
Running PowerShell command `Get-AppxPackage -Name "*CommitMaster*"` returned:
```powershell
Name            : SaumyaPatel.CommitMaster
PackageFullName : SaumyaPatel.CommitMaster_3.0.1.0_x64__3wg4h8y0g6jct
InstallLocation : C:\Program Files\WindowsApps\SaumyaPatel.CommitMaster_3.0.1.0_x64__3wg4h8y0g6jct
```
- There are **no packages** installed for `SaumyaPatel.CommitMaster.Admin` or `SaumyaPatel.CommitMaster.Demo`.
- In `package_layout/stage_packages.py`, trees are only staged into `dist/staged/`. No MSIX installer or `.appx` bundle is created or installed.
- In `build_msix.py`, the build target is hardcoded only for `CommitMaster.msix` using `store_identity.json`. Admin and Demo MSIX packaging is entirely unimplemented.
- In `installer.iss` (Inno Setup), line 8 specifies `#define MyAppExeName "CommitMaster.exe"`. Line 46 specifies `Source: "dist\{#MyAppExeName}"`. It has no support for staging or installing the three independent applications.
- Running `python build_installer.py` failed with:
  `[ERROR] Required executable not found at: C:\Data\Saumya\AI-Projects\CommitMaster\dist\CommitMaster.exe`

---

## 4. Verdict & Recommendations

### Acceptance Criteria Verdict:
- **Three independent Python processes:** **PASS**
- **Three independent data & config directories:** **PASS**
- **Three independent Windows installed applications:** **NOT VERIFIED / FAIL**

### Required Remediation for Cursor:
1. Update [installer.iss](file:///C:/Data/Saumya/AI-Projects/CommitMaster/installer.iss) to either provide component-based installation of all three executables or create three distinct Inno Setup scripts (`installer_user.iss`, `installer_admin.iss`, `installer_demo.iss`).
2. Update [build_installer.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_installer.py) to target `CommitMaster-User.exe`, `CommitMaster-Admin.exe`, and `CommitMaster-Demo.exe`.
3. Provide MSIX generation targets for Admin and Demo in [build_msix.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_msix.py) using the respective identities in [package_layout/identities.json](file:///C:/Data/Saumya/AI-Projects/CommitMaster/package_layout/identities.json).
