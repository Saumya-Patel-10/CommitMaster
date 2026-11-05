"""
Unit tests for Tailscale Network Hub, Node Registration, Admin Email Privacy, and Setup Services.
"""

import os
import json
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

import server
from commitmaster import database as db
from commitmaster import tailscale_setup
from commitmaster import tailscale_service


class TestTailscaleNetwork(unittest.TestCase):

    def setUp(self):
        self.app = server.app.test_client()
        self.app.testing = True

    def test_01_admin_profile_and_masking(self):
        """Verify admin profile email and masking behavior."""
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local_db_path = os.path.join(root_dir, "commitmaster.db")
        with sqlite3.connect(local_db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT id, username, email, role FROM users WHERE id = 1").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["email"], "saumya.patel.dev@gmail.com")
            self.assertEqual(row["role"], "admin")

        # 2. Check mask_admin_email
        masked = server.mask_admin_email("saumya.patel.dev@gmail.com", is_admin_viewer=False)
        self.assertEqual(masked, "s***v@gmail.com")

        unmasked = server.mask_admin_email("saumya.patel.dev@gmail.com", is_admin_viewer=True)
        self.assertEqual(unmasked, "saumya.patel.dev@gmail.com")

        # 3. Check sanitize_user in server
        sanitized = server.sanitize_user({"username": "Admin#_$aumy@.P@tel_#", "email": "saumya.patel.dev@gmail.com", "role": "admin"}, is_admin_viewer=False)
        self.assertEqual(sanitized["email"], "s***v@gmail.com")

    def test_02_network_join_endpoint(self):
        """Verify friend/node registration via /api/network/join."""
        payload = {
            "tailscale_login": "friend.developer@gmail.com",
            "display_name": "Friend Dev",
            "node_hostname": "friend-thinkpad",
            "node_ip": "100.99.88.77",
            "username": "friend_dev_test"
        }
        resp = self.app.post("/api/network/join", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("status"), "approved")
        self.assertIn("member_id", data)
        self.assertIn("user_id", data)

        # Verify record in server_commitmaster.db
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM network_members WHERE tailscale_login = ?", ("friend.developer@gmail.com",))
        m_row = cur.fetchone()
        self.assertIsNotNone(m_row)
        self.assertEqual(m_row["node_hostname"], "friend-thinkpad")
        self.assertEqual(m_row["node_ip"], "100.99.88.77")
        conn.close()

    def test_03_network_members_endpoint(self):
        """Verify /api/network/members returns registered members."""
        resp = self.app.get("/api/network/members")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("members", data)
        self.assertGreater(data.get("count", 0), 0)

        # If admin is in members, make sure email is masked for unauthenticated callers
        for m in data["members"]:
            if m.get("user_role") == "admin":
                self.assertFalse(m["tailscale_login"] == "saumya.patel.dev@gmail.com")
                self.assertTrue("*" in m["tailscale_login"] or "@" in m["tailscale_login"])

    def test_04_tailscale_setup_constants(self):
        """Verify tailscale_setup URLs and hub addresses."""
        self.assertEqual(tailscale_setup.TAILSCALE_INSTALLER_URL, "https://pkgs.tailscale.com/stable/tailscale-setup-latest.exe")
        self.assertEqual(tailscale_setup.TAILSCALE_START_URL, "https://login.tailscale.com/start")
        self.assertIn("100.64.108.92", tailscale_setup.DEFAULT_HUB_HOST)


if __name__ == "__main__":
    unittest.main()

