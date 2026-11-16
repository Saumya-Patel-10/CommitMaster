# Remediation & Fix Requests for Cursor

**Date:** 2026-11-16  
**Auditor:** Independent Principal QA & Security Specialist  
**Repository:** [CommitMaster](file:///C:/Data/Saumya/AI-Projects/CommitMaster)  
**Target Recipient:** Cursor AI Engineering Team  
**Directive:** You must strictly follow these precise remediation instructions. Do not bypass or introduce alternate security workarounds.

---

## FIX-REQ-01: Remove Untrusted Tailscale Header Spoofing in `server.py`
- **Related Finding:** `SEC-01`
- **Severity:** **CRITICAL**
- **Target File:** [server.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py)
- **Target Lines:** Lines 331–366 (`get_user_from_tailscale_whois`) and lines 380–383 (`require_auth`)
- **Problem:**
  `server.py` trusts `request.headers.get("X-Tailscale-Auth") == "1"` and `request.headers.get("Tailscale-User-Login")` directly from incoming HTTP requests. Any unauthenticated attacker can supply these headers and authenticate as any user.
- **Remediation Instructions:**
  1. In `require_auth` (lines 380–383), remove checking `request.headers.get("X-Tailscale-Auth") == "1"`.
  2. In `get_user_from_tailscale_whois`, do not read `headers.get("Tailscale-User-Login")`. Tailscale identity must be verified strictly using the server host's local Tailscale service:
     - Check `ipaddress.ip_address(remote_addr) in ipaddress.ip_network("100.64.0.0/10")`.
     - Query `tailscale_service.whois(remote_addr)` directly.
     - If `whois` returns a user, query the user in the database.
  3. Ensure that `u_dict["role"] = "user"` is always enforced for any Tailscale-authenticated session unless the session token has been issued with explicit admin scope.
- **Regression Test:**
  Add a test in `tests/test_security_boundaries.py` sending an unauthenticated request from `127.0.0.1` with `X-Tailscale-Auth: 1` and `Tailscale-User-Login: admin`; assert HTTP 401 is returned.

---

## FIX-REQ-02: Enforce Mandatory `current_password` Verification on `/api/users/<id>/password`
- **Related Finding:** `SEC-02`
- **Severity:** **CRITICAL**
- **Target File:** [server.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py)
- **Target Lines:** Lines 1843–1854
- **Problem:**
  Line 1851 checks `if cur_pw and not verify_password(cur_pw, u_row["password_hash"]):`. If `current_password` is omitted from the JSON body, `cur_pw` is falsy, skipping verification and updating the password hash unconditionally.
- **Remediation Instructions:**
  Replace lines 1843–1854 with:
  ```python
  # Require current password verification for self-service password updates
  cur_pw = (data.get("current_password") or "").strip()
  cur.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
  u_row = cur.fetchone()
  if not u_row:
      conn.close()
      return jsonify({"error": "User not found"}), 404
  if not cur_pw or not verify_password(cur_pw, u_row["password_hash"]):
      conn.close()
      return jsonify({"error": "Current password is required and incorrect."}), 401
  ```
- **Regression Test:**
  Add test asserting that `POST /api/users/<user_id>/password` with missing or empty `current_password` returns HTTP 401.

---

## FIX-REQ-03: Require Existing Password and TOTP for Admin Password Changes
- **Related Finding:** `SEC-03`
- **Severity:** **CRITICAL**
- **Target File:** [server.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py)
- **Target Lines:** Lines 1844–1856
- **Problem:**
  Line 1844 skips password verification if `role == 'admin'`, allowing anyone who enters the route with an admin role to overwrite the admin password.
- **Remediation Instructions:**
  Admin accounts must never bypass current password verification. Require both `current_password` and a valid TOTP code (`data.get("totp_code")`) whenever `u_row["role"] == "admin"`.
- **Regression Test:**
  Send request to change admin password without supplying admin's current password; assert HTTP 401.

---

## FIX-REQ-04: Standardize Python Timestamp Generation on UTC
- **Related Finding:** `SEC-04`
- **Severity:** **HIGH**
- **Target Files:**
  - [server.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py) (lines 283, 1171, 1341, 1382, 2347)
  - [commitmaster/database.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/commitmaster/database.py) (lines 937, 2347)
- **Problem:**
  Python computes session and token expirations using `datetime.now()` (local time), but SQLite compares them with `datetime('now')` (UTC). On any system where local time is behind UTC, 15-minute impersonation tokens and OTPs expire immediately upon creation.
- **Remediation Instructions:**
  Import `datetime, timezone` and compute timestamps using UTC:
  ```python
  from datetime import datetime, timezone, timedelta
  expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
  ```
- **Regression Test:**
  Run `pytest tests/test_security_boundaries.py::TestSecurityBoundaries::test_09_impersonation_has_no_admin_power`; assert it passes on Windows systems in any timezone.

---

## FIX-REQ-05: Update Inno Setup Scripts and Installer Builder
- **Related Finding:** `PKG-01`
- **Severity:** **HIGH**
- **Target Files:**
  - [installer.iss](file:///C:/Data/Saumya/AI-Projects/CommitMaster/installer.iss) (lines 8, 46)
  - [build_installer.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/build_installer.py) (lines 18, 60)
- **Problem:**
  `installer.iss` hardcodes `CommitMaster.exe` and `build_installer.py` crashes because `dist/CommitMaster.exe` is no longer produced by `build_exe.py`.
- **Remediation Instructions:**
  1. In `installer.iss`:
     Change `#define MyAppExeName "CommitMaster.exe"` to `#define MyAppExeName "CommitMaster-User.exe"`.
     Update `[Files]` section to package `dist\CommitMaster-User.exe`.
  2. In `build_installer.py`:
     Update line 60 to verify `os.path.join(DIST_DIR, "CommitMaster-User.exe")`.
  3. Optionally create `installer_admin.iss` and `installer_demo.iss` for dedicated installers.
- **Regression Test:**
  Run `python build_installer.py` after building executables; assert exit code is 0 and installer is created.

---

## FIX-REQ-06: Increment MSIX Store Version to Overcome Installed 3.0.1.0 Package
- **Related Finding:** `PKG-02`
- **Severity:** **HIGH**
- **Target Files:**
  - [store_identity.json](file:///C:/Data/Saumya/AI-Projects/CommitMaster/store_identity.json) (line 6)
  - [package_layout/identities.json](file:///C:/Data/Saumya/AI-Projects/CommitMaster/package_layout/identities.json) (line 7)
- **Problem:**
  Windows machine has `SaumyaPatel.CommitMaster` version `3.0.1.0` installed. Attempting to install or upgrade with version `1.1.0.0` fails due to Windows downgrade protection.
- **Remediation Instructions:**
  Change `"version": "1.1.0.0"` to `"version": "3.1.0.0"` in both `store_identity.json` and `package_layout/identities.json`.

---

## FIX-REQ-07: Implement Per-Repository Mutex in `git_safety.py`
- **Related Finding:** `GIT-01`
- **Severity:** **MEDIUM**
- **Target File:** [commitmaster/git_safety.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/commitmaster/git_safety.py)
- **Problem:**
  Concurrent commits to the same git repository collide on `.git/refs/heads/<branch>` and cause `fatal: cannot lock ref 'HEAD'`.
- **Remediation Instructions:**
  Implement a lock context manager `repo_lock(repo_path)` in `git_safety.py` using `msvcrt.locking` on Windows:
  ```python
  import msvcrt
  @contextmanager
  def repo_lock(repo_path: str):
      lock_path = os.path.join(repo_path, ".git", "commitmaster.lock")
      os.makedirs(os.path.dirname(lock_path), exist_ok=True)
      with open(lock_path, "w") as f:
          try:
              msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
              yield
          finally:
              try:
                  msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
              except Exception:
                  pass
  ```
  Wrap `commit_authorized` and `push_authorized` inside `with repo_lock(repo_path):`.
- **Regression Test:**
  Execute concurrent commit test with 5 threads against a single repo; verify all 5 complete successfully without lock errors.

---

## FIX-REQ-08: Implement the 9 Multi-Agent AI System
- **Related Finding:** `AI-01`
- **Severity:** **CRITICAL (Specification Gap)**
- **Target Directory:** `commitmaster/agents/`
- **Problem:**
  The required 9-agent autonomous AI system was not implemented.
- **Remediation Instructions:**
  Build the agent orchestration package implementing:
  1. `GitOperationsAgent`
  2. `SecurityAnalysisAgent`
  3. `CodeReviewAgent`
  4. `DebuggingAgent`
  5. `CodeComparisonAgent`
  6. `RepositoryIntelligenceAgent`
  7. `TestingAgent`
  8. `PerformanceAgent`
  9. `ReleaseValidationAgent`
  Enforce read-only tools for review/analysis agents, human confirmation for git operations, and strict parameterized dispatching (no shell execution).
