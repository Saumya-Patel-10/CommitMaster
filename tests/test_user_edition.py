"""
The public user edition must contain no administrator and never auto-sign-in anyone.
Each check runs in a fresh subprocess with an empty data dir to mimic a first install.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(code: str, data_dir: str, extra_env=None) -> str:
    env = dict(os.environ)
    env["COMMITMASTER_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = ROOT
    # Even if the environment tries to provide admin details, the user edition ignores them.
    env["ADMIN_USERNAME"] = "someone.admin"
    env["ADMIN_PASSWORD"] = "x"
    env.update(extra_env or {})
    res = subprocess.run([sys.executable, "-c", code], env=env, cwd=ROOT,
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


class TestUserEdition(unittest.TestCase):
    def test_fresh_install_has_no_users_and_no_admin(self):
        with tempfile.TemporaryDirectory() as d:
            out = _run(
                "from commitmaster import database as db\n"
                "db.init_db()\n"
                "n = db.get_conn().execute('SELECT COUNT(*) FROM users').fetchone()[0]\n"
                "print(n, repr(db.get_admin_username()), db.is_admin_username('someone.admin'))",
                d)
            self.assertEqual(out, "0 '' False")

    def test_fresh_install_does_not_resume_any_session(self):
        with tempfile.TemporaryDirectory() as d:
            out = _run(
                "import app\n"
                "from commitmaster import database as db\n"
                "db.init_db()\n"
                "print(app._resume_saved_session())\n"
                "from commitmaster import account_manager as am\n"
                "print(am.get_default_account())",
                d)
            self.assertEqual(out.splitlines(), ["None", "None"])

    def test_logout_is_not_resumed_and_accounts_can_be_removed(self):
        with tempfile.TemporaryDirectory() as d:
            out = _run(
                "import app\n"
                "from commitmaster import database as db, account_manager as am\n"
                "db.init_db()\n"
                "uid = db.create_user('alice','alice@example.com','Alice','secret1')\n"
                "u = db.get_user(uid)\n"
                "tok = db.create_session_token(uid)\n"
                "am.save_account(u, tok); app._save_token(tok)\n"
                "print(app._resume_saved_session()['username'])\n"
                "am.clear_active_account()\n"
                "print(app._resume_saved_session())\n"
                "print(len(am.get_saved_accounts()))\n"
                "am.remove_saved_account(uid)\n"
                "print(len(am.get_saved_accounts()), am.get_active_account())",
                d)
            lines = [l for l in out.splitlines() if " [INFO" not in l]
            self.assertEqual(lines, ["alice", "None", "1", "0 None"])

    def test_session_token_not_shared_between_users(self):
        with tempfile.TemporaryDirectory() as d:
            out = _run(
                "from commitmaster import database as db\n"
                "db.init_db()\n"
                "a = db.create_user('alice','alice@example.com','Alice','secret1')\n"
                "b = db.create_user('bobby','bob@example.com','Bob','secret2')\n"
                "ta = db.create_session_token(a)\n"
                "tb = db.create_session_token(b)\n"
                "print(ta != tb, db.validate_session_token(tb)['username'])",
                d)
            self.assertEqual(out, "True bobby")

    def test_user_build_has_no_admin_hardcoding(self):
        for rel in ("app.py", os.path.join("commitmaster", "database.py"), "server.py",
                    os.path.join("commitmaster", "account_manager.py"),
                    os.path.join("commitmaster", "admin_portal.py")):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
                src = f.read()
            self.assertNotIn("saumya.patel", src, rel)
            self.assertNotIn("Admin_#", src, rel)


if __name__ == "__main__":
    unittest.main()
