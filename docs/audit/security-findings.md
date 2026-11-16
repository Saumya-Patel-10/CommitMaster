# Priority 7 Audit: Database, Authentication, and Security Audit

**Date:** 2026-11-16  
**Auditor:** Independent Principal Security Auditor & Penetration Tester  
**Repository:** [CommitMaster](file:///C:/Data/Saumya/AI-Projects/CommitMaster)  
**Overall Verdict:** **FAIL — CRITICAL VULNERABILITIES IDENTIFIED**

---

## 1. Security Evaluation Summary

Our security and penetration audit evaluated the complete attack surface across both the desktop client architecture and the backend server ([server.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py)).

### Threat Assessment:
- **Client Desktop Sandbox:** Strong. The desktop layer uses distinct local data directories, separate SQLite databases, and strict process-level locks that resist tampering via command-line flags or configuration manipulation.
- **Backend Server Security:** **CRITICAL RISK**. The server implementation contains critical logic flaws in its header parsing and password reset flows that permit remote, unauthenticated complete account takeover of any user and administrator.

---

## 2. Vulnerability Register

| Finding ID | Severity | Category | Affected Component | Summary | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **SEC-01** | **CRITICAL** | Auth Bypass | `server.py:380-383` | Tailscale header spoofing grants arbitrary user auth | **CONFIRMED** |
| **SEC-02** | **CRITICAL** | Auth Bypass | `server.py:1851` | Password reset without `current_password` | **CONFIRMED** |
| **SEC-03** | **CRITICAL** | Priv Escalation | `server.py:1844` | Admin password overwrite via spoofed session | **CONFIRMED** |
| **SEC-04** | **HIGH** | Session / DOS | `server.py:283` | Local time vs UTC causes immediate token expiration | **CONFIRMED** |
| **SEC-05** | **MEDIUM** | Information Leak | `server.py:360` | Tailscale whois lookup preserves admin role in unverified dict | **CONFIRMED** |
| **SEC-06** | **MEDIUM** | Data Leakage | `commitmaster/paths.py:88` | Unprompted copy of workspace db into local user folder | **CONFIRMED** |
| **SEC-07** | **LOW** | Injection Risk | `server.py:1801, 1911` | Dynamic SQL column set construction | **SUSPECTED RISK** |
| **SEC-08** | **LOW** | AI Prompt Injection| `commitmaster/ai_messages.py` | Unsanitized git diff passed directly to LLM prompt | **SUSPECTED RISK** |

---

## 3. Detailed Finding Reports

### FINDING-SEC-01: Unauthenticated Remote Account Takeover via Spoofed Tailscale Headers
- **Finding ID:** `SEC-01`
- **Severity:** **CRITICAL (CVSS 9.8)**
- **Affected Application:** CommitMaster Cloud Server (`server.py`)
- **Affected File & Line:** [server.py:380-383, 331-366](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py#L380-L383)
- **Reproduction Steps:**
  1. Target any user account on the CommitMaster server (e.g. `alice@example.com`, `user_id=13`).
  2. Execute an HTTP request without providing a Bearer token:
     ```http
     GET /api/users/13 HTTP/1.1
     Host: target-server.com
     X-Tailscale-Auth: 1
     Tailscale-User-Login: alice@example.com
     ```
  3. Server inspects `request.headers.get("X-Tailscale-Auth") == "1"`.
  4. Server calls `get_user_from_tailscale_whois` which pulls `headers.get("Tailscale-User-Login")`.
  5. Server executes `SELECT * FROM users WHERE LOWER(email) = LOWER(?)`, finds Alice, and authenticates the connection as Alice.
  6. Response returns HTTP 200 with Alice's user profile.
- **Expected Result:** Unauthenticated requests must return HTTP 401 Unauthorized. Untrusted client headers must never be accepted as proof of identity.
- **Actual Result:** Server authenticates the caller as the victim user immediately.
- **Root Cause:** Trusting client-supplied HTTP request headers (`X-Tailscale-Auth: 1` and `Tailscale-User-Login`) without validating that the request was relayed through an authenticated local Tailscale reverse proxy.
- **Impact:** Remote unauthenticated attackers can access and modify any user's profile, preferences, watched repos, and commit records.
- **Recommended Correction:**
  Remove client header checking. Tailscale identity must only be accepted if `request.remote_addr` falls within `100.64.0.0/10` and is validated locally via the Tailscale daemon (`tailscale whois <remote_addr>`).
- **Suggested Regression Test:** Send unauthenticated HTTP request with `X-Tailscale-Auth: 1` from non-Tailscale IP; verify HTTP 401 is returned.

---

### FINDING-SEC-02: Password Reset Without Current Password Verification
- **Finding ID:** `SEC-02`
- **Severity:** **CRITICAL (CVSS 9.1)**
- **Affected Application:** CommitMaster Cloud Server (`server.py`)
- **Affected File & Line:** [server.py:1851](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py#L1851)
- **Reproduction Steps:**
  1. Authenticate as any user (or combine with `SEC-01`).
  2. Send `POST /api/users/<user_id>/password` with payload:
     ```json
     {"new_password": "AttackerControlledPassword123!"}
     ```
     (Notice `current_password` is omitted).
  3. Server processes request and returns `{"ok": true}`.
  4. The victim account password is now updated.
- **Expected Result:** The endpoint must require `current_password` and reject the request with HTTP 401/400 if missing or incorrect.
- **Actual Result:** Password was successfully changed without supplying the old password.
- **Root Cause:**
  Line 1851 tests:
  ```python
  if cur_pw and not verify_password(cur_pw, u_row["password_hash"]):
      conn.close()
      return jsonify({"error": "Current password is incorrect."}), 401
  ```
  When `cur_pw` is omitted or empty, `cur_pw` evaluates to `False`, bypassing the check entirely!
- **Impact:** Any user or attacker with temporary session access can permanently lock out the legitimate account owner by setting a new password without knowing the current one.
- **Recommended Correction:**
  Change line 1851 to:
  ```python
  cur_pw = (data.get("current_password") or "").strip()
  if not cur_pw or not verify_password(cur_pw, u_row["password_hash"]):
      conn.close()
      return jsonify({"error": "Current password is required and incorrect."}), 401
  ```
- **Suggested Regression Test:** Send `POST /api/users/<id>/password` omitting `current_password`; verify HTTP 401.

---

### FINDING-SEC-03: Complete Administrator Account Takeover via Spoofed Headers
- **Finding ID:** `SEC-03`
- **Severity:** **CRITICAL (CVSS 9.8)**
- **Affected Application:** CommitMaster Cloud Server (`server.py`)
- **Affected File & Line:** [server.py:1844-1856](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py#L1844-L1856)
- **Reproduction Steps:**
  1. Send `POST /api/users/<admin_id>/password` with headers:
     ```http
     X-Tailscale-Auth: 1
     Tailscale-User-Login: admin
     ```
     and body:
     ```json
     {"new_password": "NewAdminPassword999!"}
     ```
  2. Line 1844 tests `if g.current_user.get("role") != "admin":`. Since the spoofed user has `role == "admin"`, the entire current-password verification is skipped.
  3. Admin's `password_hash` in the database is overwritten with the new hash.
- **Expected Result:** Administrator password reset must require existing password and TOTP verification; untrusted requests must be rejected.
- **Actual Result:** Administrator account password overwritten with HTTP 200.
- **Root Cause:** Logic flaw skipping password verification when caller role is admin, combined with unverified header spoofing.
- **Impact:** Permanent hostile takeover of the primary administrative account.
- **Recommended Correction:** Admin password changes must require TOTP verification and knowledge of the current admin password.

---

### FINDING-SEC-04: Local Time vs UTC Desynchronization Causing Premature Token Expiration
- **Finding ID:** `SEC-04`
- **Severity:** **HIGH**
- **Affected Application:** Server & Database Layer
- **Affected File & Line:** [server.py:283, 257](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py#L283) and [commitmaster/database.py:937, 2413](file:///C:/Data/Saumya/AI-Projects/CommitMaster/commitmaster/database.py#L937)
- **Reproduction Steps:**
  1. Run server on a machine located in any timezone behind UTC (e.g. UTC-6).
  2. Issue a short-lived token (such as a 15-minute impersonation token: `hours=0.25`).
  3. Validate token immediately: `GET /api/admin/users` with `Authorization: Bearer <token>`.
  4. Request returns `401 Unauthorized: valid session token required.`
- **Expected Result:** Token is valid for 15 minutes.
- **Actual Result:** Token is rejected as expired immediately. Causes `test_09_impersonation_has_no_admin_power` to fail in pytest.
- **Root Cause:** `insert_session` uses Python `datetime.now()` (local time), while SQLite compares against `datetime('now')` (UTC).
- **Impact:** Impersonation and OTP tokens are dead on arrival in Western timezones.
- **Recommended Correction:** Use `datetime.now(timezone.utc)` for all database timestamp generation.

---

### FINDING-SEC-05: Preserved Admin Role in Unverified Tailscale Lookup
- **Finding ID:** `SEC-05`
- **Severity:** **MEDIUM**
- **Affected Application:** Server (`server.py`)
- **Affected File & Line:** [server.py:360-363](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py#L360-L363)
- **Root Cause:** `get_user_from_tailscale_whois` returns `dict(row)` directly from the database without downgrading `role` to `"user"`, unlike `get_current_user_from_token` which enforces `if scope != "admin": u_dict["role"] = "user"`.
- **Impact:** Any endpoint relying on `g.current_user.get("role") == "admin"` treats the connection as fully privileged.

---

### FINDING-SEC-06: Automatic Copy of Workspace Database in Source Runs
- **Finding ID:** `SEC-06`
- **Severity:** **MEDIUM**
- **Affected Application:** Client Paths (`commitmaster/paths.py`)
- **Affected File & Line:** [commitmaster/paths.py:88-100](file:///C:/Data/Saumya/AI-Projects/CommitMaster/commitmaster/paths.py#L88-L100)
- **Root Cause:** In non-frozen mode, `_copy_user_workspace_once` automatically copies `commitmaster.db`, `config.json`, and `.commitmaster_accounts.json` from the repository root into `%LOCALAPPDATA%\CommitMaster` if the destination has no database.
- **Impact:** If a developer or tester leaves a test database with test tokens in the repository root, it silently seeds the user's local profile without consent.
- **Recommended Correction:** Disable automatic copying or require an explicit command-line flag `--import-workspace-db`.

---

## 4. Summary Verdict

Because three **CRITICAL** severity vulnerabilities (`SEC-01`, `SEC-02`, `SEC-03`) and one **HIGH** severity flaw (`SEC-04`) were confirmed through live execution, **the system fails the security audit and must NOT be released to production until remediated.**
