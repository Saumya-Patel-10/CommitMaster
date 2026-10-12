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
        """Admin requires authentication and can see registered users, stats, and activity."""
        import requests

        # Unauthenticated request to admin endpoint must be rejected
        unauth_resp = requests.get(f"{self.server_url}/api/admin/users")
        self.assertEqual(unauth_resp.status_code, 401)

        # Authenticate as the designated administrator
        login_resp = requests.post(f"{self.server_url}/api/auth/login", json={
            "username_or_email": server.DEFAULT_ADMIN_USER,
            "password": server.DEFAULT_ADMIN_PASS
        })
        self.assertEqual(login_resp.status_code, 200)
        admin_token = login_resp.json().get("token")
        self.assertTrue(admin_token)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Fetch admin users list with authenticated admin token
        resp = requests.get(f"{self.server_url}/api/admin/users", headers=admin_headers)
        self.assertEqual(resp.status_code, 200)
        users = resp.json().get("users", [])
        self.assertTrue(len(users) >= 1)

        # Check stats with authenticated admin token
        stats_resp = requests.get(f"{self.server_url}/api/admin/stats", headers=admin_headers)
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

    def test_06_security_audit_enforcement(self):
        """Verify the 3 vibe-coding vulnerability vectors are strictly closed."""
        import requests
        ts = int(time.time() * 1000)

        # 1. Unauthenticated session minting backdoor is closed
        backdoor_resp = requests.post(f"{self.server_url}/api/auth/session", json={
            "action": "create",
            "user_id": 1
        })
        self.assertEqual(backdoor_resp.status_code, 401)

        # 2. Unauthenticated password tampering is closed
        tamper_resp = requests.post(f"{self.server_url}/api/auth/update-password", json={
            "user_id": 1,
            "new_password": "tampered_password_123"
        })
        self.assertEqual(tamper_resp.status_code, 401)

        # Create two separate standard users
        user1_resp = requests.post(f"{self.server_url}/api/auth/register", json={
            "username": f"user_sec_a_{ts}",
            "email": f"sec_a_{ts}@example.com",
            "full_name": "Security User A",
            "password": "passwordA123!"
        })
        self.assertEqual(user1_resp.status_code, 201)
        u1_data = user1_resp.json()
        u1_id = u1_data["user"]["id"]
        u1_token = u1_data["token"]
        u1_headers = {"Authorization": f"Bearer {u1_token}"}

        user2_resp = requests.post(f"{self.server_url}/api/auth/register", json={
            "username": f"user_sec_b_{ts}",
            "email": f"sec_b_{ts}@example.com",
            "full_name": "Security User B",
            "password": "passwordB123!"
        })
        self.assertEqual(user2_resp.status_code, 201)
        u2_id = user2_resp.json()["user"]["id"]

        # 3. Standard user cannot access admin routes (Privilege escalation blocked)
        admin_probe = requests.get(f"{self.server_url}/api/admin/users", headers=u1_headers)
        self.assertEqual(admin_probe.status_code, 403)

        # 4. Row Level Security / IDOR: User 1 cannot inspect User 2's profile
        idor_probe = requests.get(f"{self.server_url}/api/users/{u2_id}", headers=u1_headers)
        self.assertEqual(idor_probe.status_code, 403)

        # 5. Row Level Security / IDOR: User 1 cannot update User 2's profile
        idor_update = requests.put(f"{self.server_url}/api/users/{u2_id}", json={
            "full_name": "Hacked User B"
        }, headers=u1_headers)
        self.assertEqual(idor_update.status_code, 403)

        # 6. Client secrets leakage blocked: AI API keys are masked in GET /preferences
        # Update user 1's preferences with an AI key
        set_pref = requests.put(f"{self.server_url}/api/users/{u1_id}/preferences", json={
            "openai_api_key": "sk-proj-supersecretkey1234567890abcdef"
        }, headers=u1_headers)
        self.assertEqual(set_pref.status_code, 200)

        # Fetch preferences and verify the key is masked
        get_pref = requests.get(f"{self.server_url}/api/users/{u1_id}/preferences", headers=u1_headers)
        self.assertEqual(get_pref.status_code, 200)
        returned_key = get_pref.json().get("preferences", {}).get("openai_api_key", "")
        self.assertIn("...", returned_key)
        self.assertNotIn("supersecretkey", returned_key)

        # 7. Server-side Rate Limiting on /api/auth/login
        ratelimit_target = f"ratelimit_user_{ts}"
        for _ in range(5):
            fail_resp = requests.post(f"{self.server_url}/api/auth/login", json={
                "username_or_email": ratelimit_target,
                "password": "wrongpassword"
            })
            self.assertEqual(fail_resp.status_code, 401)
        # 6th attempt must trigger rate limit 429
        blocked_resp = requests.post(f"{self.server_url}/api/auth/login", json={
            "username_or_email": ratelimit_target,
            "password": "wrongpassword"
        })
        self.assertEqual(blocked_resp.status_code, 429)

        # 8. Server-side Rate Limiting on /api/auth/reset-password
        for _ in range(5):
            fail_reset = requests.post(f"{self.server_url}/api/auth/reset-password", json={
                "user_id": u1_id,
                "answer_1": "wrong_ans_1",
                "answer_2": "wrong_ans_2",
                "new_password": "new_secret_pass_123"
            })
            self.assertIn(fail_reset.status_code, (401, 404))
        # 6th attempt must be throttled with 429
        blocked_reset = requests.post(f"{self.server_url}/api/auth/reset-password", json={
            "user_id": u1_id,
            "answer_1": "wrong_ans_1",
            "answer_2": "wrong_ans_2",
            "new_password": "new_secret_pass_123"
        })
        self.assertEqual(blocked_reset.status_code, 429)

if __name__ == "__main__":
    unittest.main()
