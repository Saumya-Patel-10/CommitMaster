"""Security boundaries for the user, admin, and demo products.

These tests do not weaken authentication. A failure here is a product failure.
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from commitmaster.totp import totp_at


def _python(code: str, env: dict, timeout: int = 60) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    merged.update(env)
    merged["PYTHONPATH"] = ROOT
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=merged,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestSecurityBoundaries(unittest.TestCase):
    def test_01_standard_user_cannot_authenticate_to_admin(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _python(textwrap.dedent("""
                import os
                os.environ["SERVER_DB_PATH"] = os.environ["DB"]
                os.environ["APP_ENVIRONMENT"] = "production"
                os.environ["ADMIN_USERNAME"] = "boundary-admin"
                os.environ["ADMIN_EMAIL"] = "boundary-admin@example.com"
                os.environ["ADMIN_PASSWORD"] = "Boundary-Admin-Pass-1"
                os.environ["ADMIN_TOTP_SECRET"] = os.environ["TOTP"]
                import server
                client = server.app.test_client()
                reg = client.post("/api/auth/register", json={
                    "username": "plain-user", "email": "plain@example.com",
                    "full_name": "Plain", "password": "plain-password-1", "role": "admin",
                })
                assert reg.status_code == 201, reg.get_json()
                assert reg.get_json()["user"]["role"] == "user"
                token = reg.get_json()["token"]
                denied = client.get("/api/admin/users", headers={"Authorization": "Bearer " + token})
                assert denied.status_code == 403, denied.get_json()
                bad = client.post("/api/admin/login", json={
                    "username_or_email": "plain-user",
                    "password": "plain-password-1",
                    "totp_code": "000000",
                })
                assert bad.status_code in (401, 403), bad.get_json()
                print("ok")
            """), {"DB": os.path.join(directory, "prod.db"), "TOTP": "JBSWY3DPEHPK3PXP"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)

    def test_02_user_entry_does_not_launch_admin(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _python(textwrap.dedent("""
                import os
                os.environ["COMMITMASTER_DATA_DIR"] = os.environ["DATA"]
                from commitmaster import product
                product.activate("user")
                import app
                assert product.current() == "user"
                try:
                    import admin_app
                except RuntimeError as exc:
                    print(type(exc).__name__)
                else:
                    raise SystemExit("admin entry imported inside the user product")
                source = open("app.py", encoding="utf-8").read()
                assert "admin_app" not in source
                assert "_open_admin_window" not in source
                print("blocked")
            """), {"DATA": directory})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("blocked", result.stdout)

    def test_03_user_package_has_no_admin_entry_or_secret(self):
        from packaging.stage_packages import stage_all
        with tempfile.TemporaryDirectory() as directory:
            built = stage_all(directory)
            user_root = built["user"]
            forbidden_names = {
                "admin_app.py", "admin_portal.py", "demo_app.py", "server.py",
                "Launch_Admin_App.bat", "Launch_Admin_App.vbs",
            }
            found = []
            secret_hits = []
            for dirpath, _dirs, files in os.walk(user_root):
                for name in files:
                    if name in forbidden_names:
                        found.append(os.path.join(dirpath, name))
                    path = os.path.join(dirpath, name)
                    if name.endswith((".py", ".bat", ".vbs", ".json", ".txt")):
                        text = open(path, encoding="utf-8", errors="ignore").read()
                        for needle in ("JBSWY3DPEHPK3PXP", "CommitMaster2026!", "_open_admin_window", "Launch_Admin_App", "BEGIN PRIVATE KEY"):
                            if needle in text:
                                secret_hits.append(f"{path}: {needle}")
            self.assertEqual(found, [])
            self.assertEqual(secret_hits, [])
            self.assertTrue(os.path.isfile(os.path.join(user_root, "app.py")))

    def test_04_user_token_rejected_by_admin_service(self):
        self.test_01_standard_user_cannot_authenticate_to_admin()

    def test_05_user_database_access_is_owner_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _python(textwrap.dedent("""
                import os
                os.environ["COMMITMASTER_DATA_DIR"] = os.environ["DATA"]
                os.environ["COMMITMASTER_LOCAL_ADMIN_DB"] = "0"
                from commitmaster import product
                product.activate("user")
                from commitmaster import database as db
                db.init_db()
                alice = db.create_user("alice", "alice@example.com", "Alice", "secret-alice")
                bob = db.create_user("bob", "bob@example.com", "Bob", "secret-bob")
                token = db.create_session_token(alice)
                db.set_active_session_token(token)
                assert db.get_user(alice)["username"] == "alice"
                assert db.get_user(bob) is None
                assert db.get_github_accounts(bob) == []
                print("scoped")
            """), {"DATA": directory})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("scoped", result.stdout)

    def test_06_demo_credentials_rejected_by_production(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _python(textwrap.dedent("""
                import os
                os.environ["SERVER_DB_PATH"] = os.environ["DB"]
                os.environ["APP_ENVIRONMENT"] = "production"
                os.environ["ADMIN_USERNAME"] = "boundary-admin"
                os.environ["ADMIN_EMAIL"] = "boundary-admin@example.com"
                os.environ["ADMIN_PASSWORD"] = "Boundary-Admin-Pass-1"
                os.environ["ADMIN_TOTP_SECRET"] = os.environ["TOTP"]
                import server
                client = server.app.test_client()
                denied = client.post("/api/auth/login", json={
                    "username_or_email": "demo-user", "password": "demo-password-1",
                }, headers={"X-CommitMaster-Product": "demo"})
                assert denied.status_code == 403, denied.get_json()
                print("rejected")
            """), {"DB": os.path.join(directory, "prod.db"), "TOTP": "JBSWY3DPEHPK3PXP"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rejected", result.stdout)

    def test_07_production_credentials_do_not_grant_demo_or_admin(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _python(textwrap.dedent("""
                import os
                os.environ["SERVER_DB_PATH"] = os.environ["DB"]
                os.environ["APP_ENVIRONMENT"] = "staging"
                os.environ["ADMIN_USERNAME"] = "stage-admin"
                os.environ["ADMIN_EMAIL"] = "stage-admin@example.com"
                os.environ["ADMIN_PASSWORD"] = "Stage-Admin-Pass-1"
                os.environ["ADMIN_TOTP_SECRET"] = os.environ["TOTP"]
                import server
                client = server.app.test_client()
                denied = client.post("/api/auth/login", json={
                    "username_or_email": "prod-user", "password": "prod-password-1",
                }, headers={"X-CommitMaster-Product": "user"})
                assert denied.status_code == 403, denied.get_json()
                reg = client.post("/api/auth/register", json={
                    "username": "demo-user", "email": "demo@example.com",
                    "full_name": "Demo", "password": "demo-password-1",
                }, headers={"X-CommitMaster-Product": "demo"})
                assert reg.status_code == 201, reg.get_json()
                token = reg.get_json()["token"]
                admin = client.get("/api/admin/users", headers={
                    "Authorization": "Bearer " + token, "X-CommitMaster-Product": "demo",
                })
                assert admin.status_code == 403, admin.get_json()
                print("separated")
            """), {"DB": os.path.join(directory, "stage.db"), "TOTP": "JBSWY3DPEHPK3PXP"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("separated", result.stdout)

    def test_08_admin_user_data_requires_audited_api(self):
        with tempfile.TemporaryDirectory() as directory:
            code = totp_at("JBSWY3DPEHPK3PXP")
            result = _python(textwrap.dedent("""
                import os
                os.environ["SERVER_DB_PATH"] = os.environ["DB"]
                os.environ["APP_ENVIRONMENT"] = "production"
                os.environ["ADMIN_USERNAME"] = "boundary-admin"
                os.environ["ADMIN_EMAIL"] = "boundary-admin@example.com"
                os.environ["ADMIN_PASSWORD"] = "Boundary-Admin-Pass-1"
                os.environ["ADMIN_TOTP_SECRET"] = os.environ["TOTP"]
                import server
                client = server.app.test_client()
                client.post("/api/auth/register", json={
                    "username": "subject", "email": "subject@example.com",
                    "full_name": "Subject", "password": "subject-password-1",
                })
                missing = client.get("/api/admin/users")
                assert missing.status_code == 401
                login = client.post("/api/admin/login", json={
                    "username_or_email": "boundary-admin",
                    "password": "Boundary-Admin-Pass-1",
                    "totp_code": os.environ["CODE"],
                }, headers={"X-CommitMaster-Product": "admin"})
                assert login.status_code == 200, login.get_json()
                token = login.get_json()["token"]
                listed = client.get("/api/admin/users", headers={"Authorization": "Bearer " + token})
                assert listed.status_code == 200, listed.get_json()
                blob = str(listed.get_json())
                assert "password_hash" not in blob
                assert "github_token" not in blob
                conn = server.get_db()
                row = conn.execute("SELECT action FROM audit_log WHERE action = 'admin_login'").fetchone()
                conn.close()
                assert row is not None
                print("audited")
            """), {"DB": os.path.join(directory, "prod.db"), "TOTP": "JBSWY3DPEHPK3PXP", "CODE": code})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("audited", result.stdout)

    def test_09_impersonation_has_no_admin_power(self):
        with tempfile.TemporaryDirectory() as directory:
            code = totp_at("JBSWY3DPEHPK3PXP")
            result = _python(textwrap.dedent("""
                import os
                os.environ["SERVER_DB_PATH"] = os.environ["DB"]
                os.environ["APP_ENVIRONMENT"] = "production"
                os.environ["ADMIN_USERNAME"] = "boundary-admin"
                os.environ["ADMIN_EMAIL"] = "boundary-admin@example.com"
                os.environ["ADMIN_PASSWORD"] = "Boundary-Admin-Pass-1"
                os.environ["ADMIN_TOTP_SECRET"] = os.environ["TOTP"]
                import server
                client = server.app.test_client()
                login = client.post("/api/admin/login", json={
                    "username_or_email": "boundary-admin",
                    "password": "Boundary-Admin-Pass-1",
                    "totp_code": os.environ["CODE"],
                }, headers={"X-CommitMaster-Product": "admin"})
                assert login.status_code == 200, login.get_json()
                admin_token = login.get_json()["token"]
                admin_id = login.get_json()["user"]["id"]
                headers = {"Authorization": "Bearer " + admin_token}
                refused = client.post("/api/admin/impersonate", json={
                    "user_id": admin_id, "justification": "too short", "confirm": False,
                }, headers=headers)
                assert refused.status_code == 400
                started = client.post("/api/admin/impersonate", json={
                    "user_id": admin_id,
                    "justification": "support request 1042 needs a look",
                    "confirm": True,
                }, headers=headers)
                assert started.status_code == 200, started.get_json()
                body = started.get_json()
                assert body["user"]["role"] == "user"
                assert body["scope"] == "impersonation"
                assert body["read_only"] is True
                assert "password" not in body["user"]
                impersonated = {"Authorization": "Bearer " + body["token"]}
                admin_call = client.get("/api/admin/users", headers=impersonated)
                assert admin_call.status_code == 403, admin_call.get_json()
                write = client.put("/api/users/%s" % admin_id, json={"full_name": "Changed"}, headers=impersonated)
                assert write.status_code == 403, write.get_json()
                print("contained")
            """), {"DB": os.path.join(directory, "prod.db"), "TOTP": "JBSWY3DPEHPK3PXP", "CODE": code})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("contained", result.stdout)

    def test_10_unauthorized_role_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            code = totp_at("JBSWY3DPEHPK3PXP")
            result = _python(textwrap.dedent("""
                import os
                os.environ["SERVER_DB_PATH"] = os.environ["DB"]
                os.environ["APP_ENVIRONMENT"] = "production"
                os.environ["ADMIN_USERNAME"] = "boundary-admin"
                os.environ["ADMIN_EMAIL"] = "boundary-admin@example.com"
                os.environ["ADMIN_PASSWORD"] = "Boundary-Admin-Pass-1"
                os.environ["ADMIN_TOTP_SECRET"] = os.environ["TOTP"]
                import server
                client = server.app.test_client()
                reg = client.post("/api/auth/register", json={
                    "username": "member", "email": "member@example.com",
                    "full_name": "Member", "password": "member-password-1", "role": "admin",
                })
                user_id = reg.get_json()["user"]["id"]
                token = reg.get_json()["token"]
                headers = {"Authorization": "Bearer " + token}
                own = client.put("/api/users/%s" % user_id, json={"role": "admin"}, headers=headers)
                assert own.status_code == 403, own.get_json()
                login = client.post("/api/admin/login", json={
                    "username_or_email": "boundary-admin",
                    "password": "Boundary-Admin-Pass-1",
                    "totp_code": os.environ["CODE"],
                }, headers={"X-CommitMaster-Product": "admin"})
                admin_headers = {"Authorization": "Bearer " + login.get_json()["token"]}
                promoted = client.post("/api/admin/users/%s/role" % user_id, json={"role": "admin"}, headers=admin_headers)
                assert promoted.status_code == 403, promoted.get_json()
                print("rejected")
            """), {"DB": os.path.join(directory, "prod.db"), "TOTP": "JBSWY3DPEHPK3PXP", "CODE": code})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rejected", result.stdout)

    def test_handoff_cannot_carry_admin_scope(self):
        from commitmaster.user_mode import HandoffError, consume_handoff, write_handoff
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(HandoffError):
                write_handoff({"mode": "workspace", "token": "t", "scope": "admin", "user": {"role": "admin"}}, directory)
            path = write_handoff({
                "mode": "impersonation",
                "token": "user-token",
                "read_only": True,
                "user": {"id": 3, "username": "ada", "role": "admin", "github_token": "secret", "password": "nope"},
            }, directory)
            payload = consume_handoff(["--admin", "--handoff", path])
            self.assertFalse(os.path.exists(path))
            self.assertEqual(payload["user"]["role"], "user")
            self.assertNotIn("github_token", payload["user"])
            self.assertNotIn("password", payload["user"])


if __name__ == "__main__":
    unittest.main()
