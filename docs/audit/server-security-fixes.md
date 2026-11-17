# Server security fixes (SEC-01 … SEC-05)

Scope: `server.py`, the password-change path in `commitmaster/database.py`, and the three password
forms (`user_dashboard.py`, `admin_app.py`, `commitmaster/admin_portal.py`).
Evidence: `tests/test_server_security_fixes.py` (16 tests) and the updated
`tests/test_tailscale_network.py::test_02`. Against the previous `server.py`, 11 of the 13 server
scenarios fail (the other two are positive controls that must pass both before and after).

This is a list of the specific defects found by reading the code and fixed here. It is not a claim
that the server is free of vulnerabilities; it has not had an independent review or penetration test.

| ID | Finding | Fix | Test |
|----|---------|-----|------|
| SEC-01 | `require_auth` accepted any peer whose address started with `100.` or any request carrying `X-Tailscale-Auth: 1`, then trusted the `Tailscale-User-Login` header. A remote client could sign in as any user by sending a header. | Identity now comes only from `trusted_tailscale_identity()`: (1) the TCP peer is inside the tailnet ranges (`100.64.0.0/10`, `fd7a:115c:a1e0::/48`) **and** the local Tailscale daemon's `whois` names it; (2) peer is loopback **and** `COMMITMASTER_TRUST_TAILSCALE_SERVE` is set (header written by `tailscale serve`); (3) peer is loopback **and** `COMMITMASTER_TRUST_LOOPBACK_OWNER` is set. Client headers from any other peer are ignored. | 01, 02, 04 |
| SEC-02 | `/api/network/join` trusted a `tailscale_login` from the request body. Claiming the administrator's email produced an approved, permanent admin member; `node_ip` was also client-supplied and rows were merged by IP. | Login is the proven identity or a throw-away placeholder. Claimed values are ignored; `node_ip` is the observed peer; unverified callers are never linked to an account and no account is created for them; rows match on login only. | 05, 06, 07 |
| SEC-03 | `POST /api/users/<id>/password` skipped the current-password check when the field was omitted, and skipped it for every admin. A stolen session, or a network identity, could take over an account. | Self-service change always requires the current password (missing → 400, wrong → 401, audited). The administrator account additionally requires a valid authenticator code. A privileged admin session may still reset *another* user (audited as `password_reset_by_admin`). Sessions are revoked on change. | 08, 09, 10, 11 |
| SEC-04 | The server compared Python local time against SQLite's UTC `datetime('now')`, so session / invite / token expiry was wrong by the UTC offset (this is why `test_09_impersonation_has_no_admin_power` failed). The client's local session cache had the same mix. | `_utcnow()` used for every server timestamp; `_save_local_session` writes UTC. | 12, 13, `test_09` |
| SEC-05 | A Tailscale-authenticated request returned the user's stored row, including its stored `role` and API keys. | Network identity never confers admin: role forced to `user`, scope `tailscale`, secret columns removed. | 03 |
| (hardening) | Legacy `sha256$` password hashes were compared with `==`. | `hmac.compare_digest`. | – |

## Client behaviour change

`db.change_password_ex(user_id, new, current_password, totp_code, admin_reset)` returns `(ok, message)`.
A server rejection is shown to the user and nothing changes locally. All three password forms now ask
for the current password; the two admin forms also ask for the authenticator code. The old
`db.change_password(...)` still exists as a boolean wrapper. If the server is unreachable the local
rules apply (current password verified against the local hash), as before.

## Operator-facing settings

| Variable | Default | Meaning |
|----------|---------|---------|
| `COMMITMASTER_TRUST_TAILSCALE_SERVE` | off (set automatically by `python server.py --serve`) | Trust `Tailscale-User-Login` on **loopback** connections only. Any local process can reach loopback, so leave it off unless `tailscale serve` fronts the server. |
| `COMMITMASTER_TRUST_LOOPBACK_OWNER` | off | Treat loopback connections as the machine's own tailnet user. For single-user machines only. |

Behaviour change to be aware of: deployments that relied on the old `100.` prefix check now need the
local Tailscale daemon to answer `whois` for the peer. I did not run any real Tailscale / `tailscale serve`
command; the tests use a fake daemon. Verifying against a real tailnet is part of the isolated-environment
plan and needs your go-ahead.

## Known gaps (not fixed here)

* TOTP codes have no replay protection (the same code is accepted again within its 90-second window).
* `/api/auth/register` and the anonymous branch of `/api/network/join` are unauthenticated and can be
  used to create rows; there is only a login rate limit. A per-IP limit / cap is still to do.
* `python server.py --serve` runs `tailscale serve --bg`, which changes tailnet exposure. It is
  operator-invoked and unchanged; I did not run it.
* The client's local SQLite file is not encrypted; stored GitHub tokens are covered by a separate task
  (OS credential store).
