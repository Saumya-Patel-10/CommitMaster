"""
Tests for recent fixes:
1. Customize Interface canvas expansion.
2. Activity log alignment structure.
3. Tailscale admin ownership (saumya.patel.dev@gmail.com) and temporary access periods / invite passes.
4. Repo analyzer events query (app_events / analytics_events).
5. NotificationToast resilience when main thread not in main loop.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import database as db
from commitmaster import repo_analyzer
from commitmaster import notification_toast
import server


class TestFixesAndInsights(unittest.TestCase):

    def setUp(self):
        self.app = server.app.test_client()
        self.app.testing = True

    def test_admin_identity_locked_to_saumya(self):
        """Admin identity must strictly default to saumya.patel.dev@gmail.com and cannot be hijacked."""
        self.assertTrue(db.is_admin_username("saumya.patel.dev@gmail.com"))
        self.assertTrue(db.is_admin_username("saumya"))
        # Arbitrary local PC accounts or names containing 'admin' must not be granted admin rights
        self.assertFalse(db.is_admin_username("admin_local_pc"))
        self.assertFalse(db.is_admin_username("random_developer"))

    def test_temporary_network_invite_creation_and_redemption(self):
        """Admin can create a temporary invite pass for a specific period and users can redeem it."""
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM network_invites WHERE invite_code LIKE 'CM-PASS-TEST%'")
        cur.execute("DELETE FROM network_members WHERE tailscale_login = 'testguest@tailnet.ts.net'")
        conn.commit()

        # Admin generates a 24-hour pass
        invite_code = "CM-PASS-TEST24H"
        exp_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO network_invites (invite_code, duration_hours, expires_at, max_uses, uses_count, status, created_by, notes)
            VALUES (?, 24, ?, 1, 0, 'active', 'saumya.patel.dev@gmail.com', 'QA Test Pass')
        """, (invite_code, exp_date))
        conn.commit()
        conn.close()

        # Guest joins using this temporary pass
        resp = self.app.post("/api/network/join", json={
            "tailscale_login": "testguest@tailnet.ts.net",
            "display_name": "Test Guest",
            "node_hostname": "guest-laptop",
            "node_ip": "100.99.88.77",
            "invite_code": invite_code
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["access_type"], "temporary")
        self.assertIsNotNone(data["expires_at"])

        # Joining without invite code defaults to pending
        resp_pending = self.app.post("/api/network/join", json={
            "tailscale_login": "unapproved@tailnet.ts.net",
            "display_name": "Unapproved Node",
            "node_hostname": "unapproved-pc",
            "node_ip": "100.11.22.33",
        })
        self.assertEqual(resp_pending.status_code, 202)
        p_data = resp_pending.get_json()
        self.assertFalse(p_data["ok"])
        self.assertEqual(p_data["status"], "pending")

    def test_admin_grant_temporary_access_endpoint(self):
        """Admin can update member access to temporary with specific duration."""
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM network_members WHERE tailscale_login = 'tempuser@tailnet.ts.net'")
        cur.execute("""
            INSERT INTO network_members (tailscale_login, display_name, status, access_type)
            VALUES ('tempuser@tailnet.ts.net', 'Temp Node', 'pending', 'temporary')
        """)
        mid = cur.lastrowid

        # Get active admin user
        cur.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        admin_row = cur.fetchone()
        admin_uid = admin_row[0] if admin_row else 1

        import secrets
        tok = secrets.token_urlsafe(32)
        cur.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, datetime('now', '+1 day'))", (tok, admin_uid))
        conn.commit()
        conn.close()

        resp = self.app.post(f"/api/network/members/{mid}/access", headers={
            "Authorization": f"Bearer {tok}"
        }, json={
            "status": "approved",
            "access_type": "temporary",
            "duration_hours": 6
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["access_type"], "temporary")
        self.assertIsNotNone(data["expires_at"])

    def test_repo_analyzer_app_events_query(self):
        """repo_analyzer must query app_events without raising missing table exception."""
        issues = repo_analyzer.scan_repo_status_and_logs(APP_DIR, user_id=1)
        self.assertIn("failed_commits", issues)
        self.assertIn("error_events", issues)
        self.assertIn("disk_logs", issues)
        self.assertIn("total_bug_count", issues)

    def test_notification_toast_non_blocking_fallback(self):
        """notification_toast.show_toast must not raise RuntimeError even without an active Tk mainloop."""
        try:
            notification_toast.show_toast(
                title="Resilience Test",
                message="Testing graceful notification dispatching without Tk mainloop",
            )
        except RuntimeError:
            self.fail("show_toast raised RuntimeError when Tk mainloop was inactive")


if __name__ == "__main__":
    unittest.main()
