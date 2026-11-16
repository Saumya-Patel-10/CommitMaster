# Priority 2 Audit: User/Admin Isolation and Privilege Boundaries

**Date:** 2026-11-16  
**Auditor:** Independent Principal QA & Security Auditor  
**Repository:** [CommitMaster](file:///C:/Data/Saumya/AI-Projects/CommitMaster)  
**Overall Verdict:** **FAIL (Multiple Critical Vulnerabilities Uncovered)**

---

## 1. Executive Summary

The objective of Priority 2 is to attempt to break the boundary between the unprivileged User application and privileged Administrative functionality. We tested UI navigation, hidden shortcuts, handoffs, config tampering, direct API calls, session manipulation, token reuse, database isolation, package contents, and backend authorization.

While the desktop UI layer successfully isolates the admin portal from the user binary, the **backend server layer ([server.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py)) contains critical privilege escalation and authentication bypass vulnerabilities** that allow any client to bypass authentication, access victim accounts, and reset administrator passwords.

---

## 2. Attack Surface Analysis & Test Results

| Attack Vector | Test Performed | Expected Result | Actual Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| **UI Navigation** | Attempted to navigate to admin pages from `UserDashboard`. | Navigation refused or omitted. | Admin nav key rejected in [user_dashboard.py:722](file:///C:/Data/Saumya/AI-Projects/CommitMaster/commitmaster/user_dashboard.py#L722); `self.on_admin` discarded. | **PASS** |
| **Hidden Shortcuts** | Checked key bindings in `UserDashboard` for secret combos (Ctrl+A, F12, etc.). | No hidden developer/admin bindings. | No admin hotkeys exist; only autoscroll, hover, and mousewheel bound. | **PASS** |
| **Deep Links / CLI Flags** | Passed `--admin` and `--admin-edition` to `app.py`. | Flags ignored; no admin access. | Flags stripped in [app.py:246](file:///C:/Data/Saumya/AI-Projects/CommitMaster/app.py#L246). | **PASS** |
| **Handoff Manipulation** | Forged `--handoff` file with `scope="admin"` or admin role. | Handoff refused with error. | [user_mode.py:92](file:///C:/Data/Saumya/AI-Projects/CommitMaster/commitmaster/user_mode.py#L92) raises `HandoffError("user app refuses an admin handoff")`; scrubs credentials. | **PASS** |
| **Config Manipulation** | Edited `config.json` in User folder adding `"role": "admin"`, `"is_admin": true`. | Ignored by process lock. | Runtime product remains `"user"`; process lock ignores config file contents. | **PASS** |
| **Direct Admin API Calls** | User token passed to `GET /api/admin/users` and `POST /api/admin/users/bulk-status`. | Blocked with HTTP 403. | [server.py:386](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py#L386) blocks calls with `403 Forbidden: administrator privileges required.` | **PASS** |
| **Database Access** | User pointing `COMMITMASTER_DATA_DIR` at Admin directory. | Blocked with error. | Blocked by `DataDirectoryError` in `paths.py`. | **PASS** |
| **Public Package Inspection** | Inspected exclusions in [package_layout/stage_packages.py](file:///C:/Data/Saumya/AI-Projects/CommitMaster/package_layout/stage_packages.py) and `build_exe.py`. | No admin scripts or secrets bundled. | `admin_app.py`, `admin_portal.py`, `admin_client.py`, and admin secrets excluded from public user tree. | **PASS** |
| **Tailscale Auth Bypass** | Sent HTTP requests with `X-Tailscale-Auth: 1` and `Tailscale-User-Login`. | Server rejects unverified client headers. | **CRITICAL FAILURE: Server grants authenticated access to any user account!** | **FAIL** |
| **Password Reset Bypass** | Sent `POST /api/users/<id>/password` omitting `current_password`. | Server rejects request with 401/400. | **CRITICAL FAILURE: Server updates password without verification!** | **FAIL** |
| **Admin Account Takeover** | Sent `POST /api/users/<admin_id>/password` with spoofed admin login. | Server rejects request. | **CRITICAL FAILURE: Admin password overwritten without existing password!** | **FAIL** |
| **Impersonation Token Validity** | Generated 15-minute impersonation token on UTC-6 system. | Token valid for 15 minutes. | **HIGH FAILURE: Token immediately expires upon creation due to local/UTC bug!** | **FAIL** |

---

## 3. Detailed Vulnerability Analyses

### 3.1 [FINDING-SEC-01] Unauthenticated Remote Account Takeover via Spoofed Tailscale Headers
- **Affected File:** [server.py:380-383, 331-366](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py#L380-L383)
- **Root Cause:**
  ```python
  # server.py line 380:
  if not user and (request.remote_addr.startswith("100.") or request.headers.get("X-Tailscale-Auth") == "1"):
      user = get_user_from_tailscale_whois(request.remote_addr, request.headers)
  ```
  And in `get_user_from_tailscale_whois`:
  ```python
  # server.py line 336:
  ts_user_login = headers.get("Tailscale-User-Login")
  ```
  Any HTTP client connecting over public TCP can provide `X-Tailscale-Auth: 1` and `Tailscale-User-Login: <victim_username>`. `server.py` queries `users` for `ts_user_login` and returns the user object without verifying that the connection came through an authenticated Tailscale proxy or Unix socket!
- **Proof-of-Concept Execution:**
  ```python
  client = server.app.test_client()
  res = client.get('/api/users/13', headers={
      'X-Tailscale-Auth': '1',
      'Tailscale-User-Login': 'victim_alice_unique'
  })
  # Output: HTTP 200 OK
  # Response: {'user': {'id': 13, 'username': 'victim_alice_unique', 'email': 'alice_unique@example.com', ...}}
  ```
- **Impact:** An attacker on the public internet can impersonate any user on the server without knowing their password or session token.

### 3.2 [FINDING-SEC-02] Broken Password Verification Allowing Arbitrary Password Resets
- **Affected File:** [server.py:1851](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py#L1851)
- **Root Cause:**
  ```python
  # server.py line 1844:
  if g.current_user.get("role") != "admin":
      cur_pw = data.get("current_password") or ""
      cur.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
      u_row = cur.fetchone()
      if not u_row:
          conn.close()
          return jsonify({"error": "User not found"}), 404
      if cur_pw and not verify_password(cur_pw, u_row["password_hash"]):
          conn.close()
          return jsonify({"error": "Current password is incorrect."}), 401

  pw_hash = hash_password(new_pw)
  cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
  ```
  Notice: `if cur_pw and not verify_password(...)`. If the caller omits `current_password`, `cur_pw` is `""` (falsy). The condition evaluates to `False`, skipping verification and directly executing `UPDATE users SET password_hash = ?`!
- **Proof-of-Concept Execution:**
  ```python
  res = client.post(f'/api/users/{bob_id}/password', json={
      'new_password': 'HackedPassword999!'
  }, headers=headers)
  # Output: HTTP 200 OK {'ok': True}
  # Bob's password was successfully changed to 'HackedPassword999!' without knowing Bob's password!
  ```

### 3.3 [FINDING-SEC-03] Complete Admin Account Takeover
- **Affected File:** [server.py:1844-1856](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py#L1844-L1856)
- **Root Cause:**
  In `server.py`, line 1844 states: `if g.current_user.get("role") != "admin":`. When an attacker uses the Tailscale spoofing attack with `Tailscale-User-Login: admin`, `g.current_user.get("role")` is `"admin"`. Line 1844 is completely skipped, and the code immediately executes:
  ```python
  pw_hash = hash_password(new_pw)
  cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
  ```
  The administrator's password is overwritten with the attacker's chosen password!

### 3.4 [FINDING-SEC-04] Timezone Desynchronization (Local Time vs UTC in SQLite)
- **Affected File:** [server.py:283, 257](file:///C:/Data/Saumya/AI-Projects/CommitMaster/server.py#L283) and [commitmaster/database.py:937, 2413](file:///C:/Data/Saumya/AI-Projects/CommitMaster/commitmaster/database.py#L937)
- **Root Cause:**
  Python computes expiration timestamps using local time:
  ```python
  expires = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
  ```
  SQLite evaluates expiration using UTC:
  ```sql
  WHERE s.token = ? AND s.expires_at > datetime('now') AND u.is_active = 1
  ```
  On a Windows machine in US Central Time (UTC-6), `datetime.now()` at 00:45 produces `2026-11-16 01:00:00` for an impersonation token (`hours=0.25`). SQLite `datetime('now')` produces `2026-11-16 06:45:00`. The token is born expired.
  This causes `test_09_impersonation_has_no_admin_power` to fail in pytest.

---

## 4. Verdict & Remediations

### Isolation Verdict:
- **Client-Side Desktop Boundary:** **PASS** (Process lock, UI isolation, handoff scrubbing, directory separation are solid).
- **Server API & Identity Boundary:** **FAIL (CRITICAL DEFECTS)**.

### Immediate Fix Requests for Cursor:
1. **Fix Tailscale Verification:** Do not accept `X-Tailscale-Auth` from untrusted request headers. Tailscale authentication must only occur if `request.remote_addr` is verified via `tailscale whois` CLI on the server host.
2. **Fix Password Verification:** Replace line 1851 with:
   ```python
   cur_pw = data.get("current_password") or ""
   if not cur_pw or not verify_password(cur_pw, u_row["password_hash"]):
       conn.close()
       return jsonify({"error": "Current password is required and incorrect."}), 401
   ```
3. **Protect Admin Password Changes:** Admin password changes on `/api/users/<id>/password` must require existing password verification and TOTP confirmation.
4. **Standardize on UTC:** Replace all instances of `datetime.now()` used for database timestamps with `datetime.now(timezone.utc)`.
