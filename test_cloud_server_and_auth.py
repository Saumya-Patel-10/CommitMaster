"""
Comprehensive test for:
1. check_user_exists fix in local mode and registration
2. server.py REST endpoints (health, check, register, login, session, admin)
3. End-to-end multi-device workflow simulation (User signs up on device 1, logs in on device 2)
4. Admin account governance
"""
import unittest
import os
import sys
import json
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from commitmaster import database as db
import server

class TestCloudServerAndAuth(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Start server in background thread on a test port
        cls.test_port = 8765
        cls.server_url = f"http://127.0.0.1:{cls.test_port}"
        cls.thread = threading.Thread(
            target=lambda: server.app.run(host="127.0.0.1", port=cls.test_port, debug=False, use_reloader=False),
            daemon=True
        )
        cls.thread.start()
        time.sleep(1)  # wait for server to start

    def test_01_local_check_user_exists(self):
        """Verify check_user_exists works locally and doesn't crash."""
        # Non-existent user
        conflict = db.check_user_exists(f"fake_user_{int(time.time()*1000)}", f"fake_{int(time.time()*1000)}@test.com")
        self.assertIsNone(conflict)

        # Existing user
        conflict_u = db.check_user_exists("saumya.patel@Admin_#", "other@example.com")
        self.assertEqual(conflict_u, "username")

        conflict_e = db.check_user_exists("other_name", "saumya.a.patel@gmail.com")
        self.assertEqual(conflict_e, "email")

    def test_02_server_health(self):
        """Test server healthcheck endpoint."""
        ok, msg = db.test_server_connection(self.server_url)
        self.assertTrue(ok)
        self.assertIn("Connected", msg)

    def test_03_multi_device_flow_simulation(self):
        """
        Simulate the exact user scenario:
        - Device 1: Connects to server, registers account 'device1_user'
        - Device 2: Connects to the same server, successfully signs in with 'device1_user'
        """
        import requests
        ts = int(time.time() * 1000)
        uname = f"device1_user_{ts}"
        email = f"device1_{ts}@example.com"

        # Device 1: Checks user exists
        check_resp = requests.post(f"{self.server_url}/api/auth/check", json={
            "username": uname,
            "email": email
        })
        self.assertEqual(check_resp.status_code, 200)
        self.assertIsNone(check_resp.json().get("conflict"))

        # Device 1: Registers account
        reg_resp = requests.post(f"{self.server_url}/api/auth/register", json={
            "username": uname,
            "email": email,
            "full_name": "Device One User",
            "password": "securepassword123",
            "role": "user"
        })
        self.assertEqual(reg_resp.status_code, 201)
        data = reg_resp.json()
        self.assertIn("user", data)
        self.assertIn("token", data)
        user_id = data["user"]["id"]
        self.assertEqual(data["user"]["username"], uname)

        # Now test check_user_exists detects it's taken
        check_again = requests.post(f"{self.server_url}/api/auth/check", json={
            "username": uname,
            "email": "other@example.com"
        })
        self.assertEqual(check_again.json().get("conflict"), "username")

        # Device 2: User opens app on second device with same server URL
        # and logs in with their credentials!
        login_resp = requests.post(f"{self.server_url}/api/auth/login", json={
            "username_or_email": uname,
            "password": "securepassword123"
        })
        self.assertEqual(login_resp.status_code, 200)
        login_data = login_resp.json()
        self.assertEqual(login_data["user"]["id"], user_id)
        self.assertEqual(login_data["user"]["email"], email)

        # Device 2: Logs in using email instead of username
        login_email = requests.post(f"{self.server_url}/api/auth/login", json={
            "username_or_email": email,
            "password": "securepassword123"
        })
        self.assertEqual(login_email.status_code, 200)

        # Device 2: Wrong password fails cleanly
        bad_login = requests.post(f"{self.server_url}/api/auth/login", json={
            "username_or_email": uname,
            "password": "wrongpassword"
        })
        self.assertEqual(bad_login.status_code, 401)

    def test_04_admin_governance(self):
        """Admin can see registered users, stats, and activity."""
        import requests

        # Fetch admin users list
        resp = requests.get(f"{self.server_url}/api/admin/users")
        self.assertEqual(resp.status_code, 200)
        users = resp.json().get("users", [])
        self.assertTrue(len(users) >= 1)

        # Check stats
        stats_resp = requests.get(f"{self.server_url}/api/admin/stats")
        self.assertEqual(stats_resp.status_code, 200)
        stats = stats_resp.json().get("stats", {})
        self.assertIn("total_users", stats)
        self.assertIn("total_admins", stats)

    def test_05_database_layer_switch_to_server(self):
        """Test database.py client functions operating through get_server_url()."""
        ts = int(time.time() * 1000)
        uname = f"cloud_user_{ts}"
        email = f"cloud_{ts}@example.com"

        # Register on server directly first
        import requests
        requests.post(f"{self.server_url}/api/auth/register", json={
            "username": uname,
            "email": email,
            "full_name": "Cloud User",
            "password": "mypassword123",
            "role": "user"
        })

        # Set temporary server URL
        os.environ["COMMITMASTER_SERVER_URL"] = self.server_url

        try:
            self.assertEqual(db.get_server_url(), self.server_url)

            # Test check_user_exists routes to server
            conflict = db.check_user_exists(uname, "unused@test.com")
            self.assertEqual(conflict, "username")

            # Test authenticate routes to server
            user = db.authenticate(uname, "mypassword123")
            self.assertIsNotNone(user)
            self.assertEqual(user["username"], uname)

            # Test bad auth
            bad = db.authenticate(uname, "badpass")
            self.assertIsNone(bad)
        finally:
            del os.environ["COMMITMASTER_SERVER_URL"]

if __name__ == "__main__":
    unittest.main()
