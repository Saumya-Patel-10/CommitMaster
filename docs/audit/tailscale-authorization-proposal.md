# Tailscale authorization: architecture proposal, migration, rollback, isolated test plan

Status: **proposal only.** Nothing in this document has been applied. No `tailscale` command was run,
and your tailnet, ACLs, device approvals, firewall, routing, RDP and file sharing are untouched. Each step
below that would touch live infrastructure is marked **[needs your approval]**.

## 1. What exists today

* `commitmaster/tailscale_service.py` only *reads* the local daemon (`status`, `whois`, peers).
* `commitmaster/tailscale_setup.py` can open the install/sign-up pages and run `tailscale up` from the
  setup dialog (user-initiated, on the user's own machine).
* `server.py` keeps `network_members` (login, node, status `pending/approved/expired`, expiry) and
  `network_invites` (code, duration, max uses). The administrator approves members in the Admin app.
* `python server.py --serve` runs `tailscale serve --bg <port>` (operator-initiated).
* No Tailscale API token exists in any app, and none should ever be added to the User or Demo apps.

The identity-trust defects (spoofable headers, client-claimed login) are fixed in
`server-security-fixes.md`. This proposal is about *who is allowed in*, not *who someone is*.

## 2. Target design

Two separate questions, answered by two separate components:

1. **Identity** (who is this connection?) - answered only by the server asking its local Tailscale daemon
   (`whois` on the TCP peer address). Already implemented (`trusted_tailscale_identity`).
2. **Authorization** (may this identity use CommitMaster?) - answered only from the admin-controlled
   `network_members` table. A tailnet login that is not `approved` gets no session. New members arrive as
   `pending` and appear in the Admin app; only an administrator session (password + authenticator code)
   can approve, set an expiry, or revoke. Revocation takes effect on the next request (sessions for that
   member are deleted at the same time).

Optional, later: if you also want Tailscale *device* authorization controlled from the Admin app, add it as an
**admin-only server-side module** that calls the Tailscale API with a narrowly scoped, short-lived credential
read from the server's environment/secret store. Rules: never present in the User or Demo apps or their
packages (the existing packaging test already scans for secrets and can be extended to check for this);
never written to config files or logs; every call audited; read-only (list devices) first, "authorize device"
only behind an explicit confirmation in the Admin app. Recommended default: **do not build this** until the
read-only design has run for a while, since tailnet ACLs and device approval are best managed in the Tailscale
admin console.

Tailnet-side controls are best expressed as ACL tags/groups (for example `tag:commitmaster-server` reachable
only on the server port from `group:commitmaster-members`). Those are changes to your live tailnet policy and
are therefore proposed as a diff for you to review, not applied.

## 3. Migration plan

| Step | Change | Live impact |
|------|--------|-------------|
| 0 | Review/merge the security fixes already on this branch. | None until deployed |
| 1 | Add an admin-visible "unverified join attempts" count and rate limit on anonymous `/api/network/join`. | None on tailnet |
| 2 | Show verified identity and approval state in the Admin app; add revoke + expiry editing. | None on tailnet |
| 3 | Deploy server with defaults (`COMMITMASTER_TRUST_*` off) and confirm members connect from tailnet addresses and are verified by `whois`. | Server restart **[needs your approval]** |
| 4 | Only if `tailscale serve` is used: enable `COMMITMASTER_TRUST_TAILSCALE_SERVE` (loopback hop only). | Config change **[needs your approval]** |
| 5 | Optional tailnet ACL tightening (diff provided for review). | Policy change **[needs your approval]** |
| 6 | Optional read-only Tailscale API device view in Admin app. | New credential **[needs your approval]** |

## 4. Rollback

* Steps 0-2 are code only; roll back by redeploying the previous server build. Database changes are additive
  (new columns/tables only); old builds ignore them.
* Step 3-4: unset the environment variables and restart; the server then trusts nothing but daemon `whois`.
* Step 5: keep the prior ACL JSON; restoring it is a single paste in the admin console. Keep a copy of the
  current policy before any change.
* Step 6: revoke the API credential in the Tailscale console; the module degrades to "unavailable".
* Throughout: do not remove or alter RDP, SMB/file-sharing, or existing remote-access rules; none of the steps
  above require changing them.

## 5. Isolated test environment (no live tailnet involved)

* **Unit level (already in repo):** a fake Tailscale daemon object replaces `tailscale_service` in
  `tests/test_server_security_fixes.py`; no network and no `tailscale` binary.
* **Integration level (proposed):** a throwaway tailnet or a self-hosted control server (for example Headscale
  in a container) with two disposable nodes, completely separate from your real tailnet, running the server
  and a client against each other. Verify: unapproved login gets 403, approved works, revoked loses access on
  the next request, a spoofed header from a non-tailnet address gets 401, and `tailscale serve` header trust
  only on loopback. **[needs your approval]** to create the disposable tailnet and nodes.
* Not tested and not claimed: behaviour against your real tailnet, MagicDNS/Funnel configurations, or ACL
  interactions.

## 6. Open questions for you

* Is `tailscale serve` actually used in your deployment, or do clients connect straight to the tailnet address?
* Do you want device authorization managed from the Admin app (section 2, optional), or kept in the Tailscale
  console?
* Who besides you needs administrator rights?
