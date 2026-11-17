"""Regression tests for the server security findings SEC-01 .. SEC-05.

Every scenario runs against a throw-away server database in a subprocess. A faked Tailscale
daemon replaces the real one, so nothing here touches a live tailnet.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PREAMBLE = """
import os, sys
os.environ["SERVER_DB_PATH"] = os.environ["DB"]
os.environ["APP_ENVIRONMENT"] = "production"
os.environ["ADMIN_USERNAME"] = "sec-admin"
os.environ["ADMIN_EMAIL"] = "sec-admin@example.com"
os.environ["ADMIN_PASSWORD"] = "Sec-Admin-Pass-1"
os.environ["ADMIN_TOTP_SECRET"] = "JBSWY3DPEHPK3PXP"
import server
from commitmaster.totp import totp_at
client = server.app.test_client()

class FakeTailscale:
    \"\"\"Stands in for the local Tailscale daemon.\"\"\"
    identities = {}
    def whois(self, addr):
        return self.identities.get(addr)
    def get_tailnet_user(self):
        return {"LoginName": "owner@example.com", "DisplayName": "Owner"}
    def get_device_hostname(self):
        return "owner-pc"
    def get_tailscale_ip(self):
        return "100.64.0.1"
    def get_magic_dns_name(self):
        return "hub.tailnet.test"
server.tailscale_service = FakeTailscale()

def register(name, email, password="victim-password-1"):  # nosec - test credential fixture
    r = client.post("/api/auth/register", json={"username": name, "email": email,
                    "full_name": name, "password": password})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["user"]["id"], r.get_json()["token"]

def at(addr, **headers):
    return dict(environ_base={"REMOTE_ADDR": addr}, headers=headers)

def admin_login():
    r = client.post("/api/admin/login", json={"username_or_email": "sec-admin",
                    "password": "Sec-Admin-Pass-1", "totp_code": totp_at("JBSWY3DPEHPK3PXP")},
                    headers={"X-CommitMaster-Product": "admin"})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["user"]["id"], {"Authorization": "Bearer " + r.get_json()["token"]}
"""


def _run(body: str, timeout: int = 90) -> None:
    with tempfile.TemporaryDirectory() as directory:
        env = os.environ.copy()
        env.update({"DB": os.path.join(directory, "sec.db"), "PYTHONPATH": ROOT})
        for name in ("COMMITMASTER_TRUST_TAILSCALE_SERVE", "COMMITMASTER_TRUST_LOOPBACK_OWNER"):
            env.pop(name, None)
        result = subprocess.run([sys.executable, "-c", PREAMBLE + textwrap.dedent(body)],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0 or "ok" not in result.stdout:
            raise AssertionError(f"scenario failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr[-3000:]}")


class TestTailscaleIdentity(unittest.TestCase):
    def test_01_spoofed_headers_from_the_internet_are_rejected(self):
        _run("""
            uid, _ = register("victim", "victim@example.com")
            url = "/api/users/%d/preferences" % uid
            for headers in ({"X-Tailscale-Auth": "1"},
                            {"Tailscale-User-Login": "victim@example.com"},
                            {"X-Tailscale-Auth": "1", "Tailscale-User-Login": "victim@example.com"}):
                r = client.get(url, **at("203.0.113.9", **headers))
                assert r.status_code == 401, (headers, r.status_code, r.get_json())
            r = client.get("/api/auth/tailscale", **at("203.0.113.9", **{"Tailscale-User-Login": "victim@example.com"}))
            assert r.status_code == 403, r.get_json()
            print("ok")
        """)

    def test_02_tailnet_address_without_daemon_proof_is_rejected(self):
        _run("""
            uid, _ = register("victim", "victim@example.com")
            url = "/api/users/%d/preferences" % uid
            # Old code trusted any 100.x peer that sent a header. The daemon knows nothing about this peer.
            r = client.get(url, **at("100.64.0.9", **{"X-Tailscale-Auth": "1", "Tailscale-User-Login": "victim@example.com"}))
            assert r.status_code == 401, r.get_json()
            # A public address that merely starts with "100." is not on the tailnet at all.
            server.tailscale_service.identities["100.200.0.1"] = {"login_name": "victim@example.com"}
            r = client.get(url, **at("100.200.0.1"))
            assert r.status_code == 401, r.get_json()
            print("ok")
        """)

    def test_03_daemon_verified_peer_is_authenticated_but_never_admin(self):
        _run("""
            uid, _ = register("victim", "victim@example.com")
            other, _ = register("someone", "someone@example.com")
            server.tailscale_service.identities["100.64.0.9"] = {"login_name": "victim@example.com"}
            ok = client.get("/api/users/%d/preferences" % uid, **at("100.64.0.9"))
            assert ok.status_code == 200, ok.get_json()
            # Not another user's data, and not admin endpoints.
            assert client.get("/api/users/%d/preferences" % other, **at("100.64.0.9")).status_code == 403
            assert client.get("/api/admin/users", **at("100.64.0.9")).status_code == 403
            # Even the administrator's own tailnet identity yields no admin authority by network alone.
            server.tailscale_service.identities["100.64.0.10"] = {"login_name": "sec-admin@example.com"}
            r = client.get("/api/admin/users", **at("100.64.0.10"))
            assert r.status_code in (401, 403), r.status_code
            print("ok")
        """)

    def test_04_loopback_header_trust_is_opt_in(self):
        _run("""
            uid, _ = register("victim", "victim@example.com")
            url = "/api/users/%d/preferences" % uid
            hdr = {"Tailscale-User-Login": "victim@example.com"}
            assert client.get(url, **at("127.0.0.1", **hdr)).status_code == 401
            os.environ["COMMITMASTER_TRUST_TAILSCALE_SERVE"] = "1"
            assert client.get(url, **at("127.0.0.1", **hdr)).status_code == 200
            # Still not accepted from a non-loopback peer, even with the flag on.
            assert client.get(url, **at("192.168.1.50", **hdr)).status_code == 401
            print("ok")
        """)


class TestNetworkJoin(unittest.TestCase):
    def test_05_claiming_the_admin_email_does_not_grant_membership(self):
        _run("""
            r = client.post("/api/network/join", json={"tailscale_login": "sec-admin@example.com",
                            "node_hostname": "evil", "node_ip": "100.64.0.99"}, **at("203.0.113.9"))
            body = r.get_json()
            assert r.status_code == 202 and body["ok"] is False and body["status"] == "pending", (r.status_code, body)
            conn = server.get_db()
            rows = conn.execute("SELECT tailscale_login, status, access_type, node_ip FROM network_members").fetchall()
            assert all(row["status"] != "approved" for row in rows), [dict(x) for x in rows]
            assert all(row["tailscale_login"].lower() != "sec-admin@example.com" for row in rows)
            assert all(row["node_ip"] != "100.64.0.99" for row in rows), "client-supplied node_ip was stored"
            assert conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND LOWER(email) = 'sec-admin@example.com'"
                                ).fetchone()[0] <= 1
            print("ok")
        """)

    def test_06_verified_identity_overrides_claimed_login(self):
        _run("""
            server.tailscale_service.identities["100.64.0.7"] = {"login_name": "friend@example.com",
                                                                  "display_name": "Friend", "hostname": "friend-pc"}
            r = client.post("/api/network/join", json={"tailscale_login": "sec-admin@example.com"}, **at("100.64.0.7"))
            body = r.get_json()
            assert r.status_code == 202 and body["status"] == "pending", body
            row = server.get_db().execute("SELECT tailscale_login, node_ip FROM network_members").fetchone()
            assert row["tailscale_login"] == "friend@example.com" and row["node_ip"] == "100.64.0.7", dict(row)
            print("ok")
        """)

    def test_07_verified_administrator_is_still_approved(self):
        _run("""
            server.tailscale_service.identities["100.64.0.8"] = {"login_name": "sec-admin@example.com"}
            r = client.post("/api/network/join", json={}, **at("100.64.0.8"))
            body = r.get_json()
            assert r.status_code == 200 and body["ok"] is True and body["status"] == "approved", body
            print("ok")
        """)


class TestPasswordChange(unittest.TestCase):
    def test_08_current_password_is_mandatory_for_self_service(self):
        _run("""
            uid, token = register("victim", "victim@example.com", "victim-password-1")
            auth = {"Authorization": "Bearer " + token}
            url = "/api/users/%d/password" % uid
            r = client.post(url, json={"new_password": "attacker-password"}, headers=auth)
            assert r.status_code == 400, r.get_json()
            r = client.post(url, json={"new_password": "attacker-password", "current_password": "guess"}, headers=auth)
            assert r.status_code == 401, r.get_json()
            # The password was not changed by either attempt.
            login = client.post("/api/auth/login", json={"username_or_email": "victim", "password": "victim-password-1"})
            assert login.status_code == 200, login.get_json()
            fresh = {"Authorization": "Bearer " + login.get_json()["token"]}
            r = client.post(url, json={"new_password": "brand-new-pass", "current_password": "victim-password-1"}, headers=fresh)
            assert r.status_code == 200, r.get_json()
            # Old sessions die, new password works, old one does not.
            assert client.get("/api/users/%d/preferences" % uid, headers=fresh).status_code == 401
            assert client.post("/api/auth/login", json={"username_or_email": "victim", "password": "victim-password-1"}).status_code == 401
            assert client.post("/api/auth/login", json={"username_or_email": "victim", "password": "brand-new-pass"}).status_code == 200
            print("ok")
        """)

    def test_09_tailscale_identity_cannot_reset_a_password(self):
        _run("""
            uid, _ = register("victim", "victim@example.com", "victim-password-1")
            server.tailscale_service.identities["100.64.0.9"] = {"login_name": "victim@example.com"}
            r = client.post("/api/users/%d/password" % uid, json={"new_password": "takeover-pass"}, **at("100.64.0.9"))
            assert r.status_code == 400, r.get_json()
            assert client.post("/api/auth/login", json={"username_or_email": "victim", "password": "victim-password-1"}).status_code == 200
            print("ok")
        """)

    def test_10_admin_self_change_needs_current_password_and_authenticator(self):
        _run("""
            admin_id, headers = admin_login()
            url = "/api/users/%d/password" % admin_id
            r = client.post(url, json={"new_password": "New-Admin-Pass-2"}, headers=headers)
            assert r.status_code == 400, r.get_json()
            r = client.post(url, json={"new_password": "New-Admin-Pass-2", "current_password": "Sec-Admin-Pass-1"}, headers=headers)
            assert r.status_code == 401, r.get_json()
            r = client.post(url, json={"new_password": "New-Admin-Pass-2", "current_password": "Sec-Admin-Pass-1",
                                       "totp_code": "000000"}, headers=headers)
            assert r.status_code == 401, r.get_json()
            r = client.post(url, json={"new_password": "New-Admin-Pass-2", "current_password": "Sec-Admin-Pass-1",
                                       "totp_code": totp_at("JBSWY3DPEHPK3PXP")}, headers=headers)
            assert r.status_code == 200, r.get_json()
            print("ok")
        """)

    def test_11_admin_can_still_reset_another_users_password(self):
        _run("""
            uid, _ = register("victim", "victim@example.com", "victim-password-1")
            _, headers = admin_login()
            r = client.post("/api/users/%d/password" % uid, json={"new_password": "reset-by-admin"}, headers=headers)
            assert r.status_code == 200, r.get_json()
            assert client.post("/api/auth/login", json={"username_or_email": "victim", "password": "reset-by-admin"}).status_code == 200
            audit = server.get_db().execute("SELECT action FROM audit_log WHERE action = 'password_reset_by_admin'").fetchall()
            assert audit, "admin reset was not audited"
            print("ok")
        """)


CLIENT_PREAMBLE = """
import os
os.environ["COMMITMASTER_DATA_DIR"] = os.environ["DATA"]
os.environ["COMMITMASTER_LOCAL_ADMIN_DB"] = "0"
os.environ.pop("COMMITMASTER_SERVER_URL", None)
from commitmaster import product
product.activate("user")
from commitmaster import database as db
db.init_db()
uid = db.create_user("carol", "carol@example.com", "Carol", "old-password-1")
assert uid
def can_login(pw):
    # Checks the local hash directly, so it is unaffected by a mocked server URL.
    row = db.get_conn().execute("SELECT password_hash FROM users WHERE id = ?", (uid,)).fetchone()
    return db._verify_password(pw, row["password_hash"])
"""


def _run_client(body: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        env = os.environ.copy()
        env.update({"DATA": directory, "PYTHONPATH": ROOT})
        result = subprocess.run([sys.executable, "-c", CLIENT_PREAMBLE + textwrap.dedent(body)],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
        if result.returncode != 0 or "ok" not in result.stdout:
            raise AssertionError(f"client scenario failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr[-3000:]}")


class TestClientPasswordChange(unittest.TestCase):
    def test_14_local_change_requires_the_current_password(self):
        _run_client("""
            ok, msg = db.change_password_ex(uid, "new-password-2")
            assert not ok and "Current password" in msg, (ok, msg)
            ok, msg = db.change_password_ex(uid, "new-password-2", current_password="wrong")
            assert not ok and "incorrect" in msg, (ok, msg)
            assert can_login("old-password-1") and not can_login("new-password-2")
            ok, msg = db.change_password_ex(uid, "new-password-2", current_password="old-password-1")
            assert ok, msg
            assert can_login("new-password-2") and not can_login("old-password-1")
            # An administrator reset of someone else's account does not need their current password.
            assert db.change_password_ex(uid, "reset-password-3", admin_reset=True)[0]
            assert can_login("reset-password-3")
            print("ok")
        """)

    def test_15_server_rejection_is_reported_and_nothing_changes_locally(self):
        _run_client("""
            class Resp:
                status_code = 401
                def json(self):
                    return {"error": "Current password is incorrect."}
            db.get_server_url = lambda: "http://server.invalid"
            db.requests.post = lambda *a, **k: Resp()
            ok, msg = db.change_password_ex(uid, "new-password-2", current_password="old-password-1")
            assert not ok and msg == "Current password is incorrect.", (ok, msg)
            assert can_login("old-password-1") and not can_login("new-password-2")
            print("ok")
        """)

    def test_16_server_success_is_mirrored_locally(self):
        _run_client("""
            sent = {}
            class Resp:
                status_code = 200
                def json(self):
                    return {"ok": True}
            def fake_post(url, json=None, **kw):
                sent.update(json or {})
                return Resp()
            db.get_server_url = lambda: "http://server.invalid"
            db.requests.post = fake_post
            ok, msg = db.change_password_ex(uid, "new-password-2", current_password="old-password-1", totp_code="123456")
            assert ok, msg
            assert sent == {"new_password": "new-password-2", "current_password": "old-password-1", "totp_code": "123456"}, sent
            db.get_server_url = lambda: ""
            assert can_login("new-password-2")
            print("ok")
        """)


class TestUtcTimestamps(unittest.TestCase):
    def test_12_session_expiry_uses_utc(self):
        _run("""
            from datetime import datetime
            conn = server.get_db()
            cur = conn.cursor()
            uid, _ = register("clock", "clock@example.com")
            tok, expires = server.insert_session(cur, uid, scope="user", hours=1)
            conn.commit()
            sqlite_now = datetime.strptime(conn.execute("SELECT datetime('now')").fetchone()[0], "%Y-%m-%d %H:%M:%S")
            delta = (datetime.strptime(expires, "%Y-%m-%d %H:%M:%S") - sqlite_now).total_seconds()
            assert 3500 < delta < 3700, delta   # exactly one hour ahead of SQLite's UTC clock, in any timezone
            print("ok")
        """)

    def test_13_utcnow_matches_sqlite_utc(self):
        _run("""
            from datetime import datetime
            conn = server.get_db()
            sqlite_now = datetime.strptime(conn.execute("SELECT datetime('now')").fetchone()[0], "%Y-%m-%d %H:%M:%S")
            assert abs((server._utcnow() - sqlite_now).total_seconds()) < 5
            print("ok")
        """)


if __name__ == "__main__":
    unittest.main()
