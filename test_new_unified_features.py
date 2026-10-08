"""
Test suite for CommitMaster unified features:
  1. Monitored Apps & IDE selection
  2. Google Account OTP verification
  3. Multi-account saving and switching
  4. Single unified application routing and exclusive admin username management
"""
import os
import sys
import unittest
import tempfile
import json
import shutil
from unittest.mock import MagicMock, patch

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import database as db
from commitmaster import otp_service
from commitmaster import account_manager
import app


class TestUnifiedFeatures(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory for an isolated test database and accounts file
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_commitmaster.db")
        self.accounts_file = os.path.join(self.test_dir, ".test_accounts.json")

        db.close_conn()
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        self.orig_accounts_file = account_manager._ACCOUNTS_FILE
        account_manager._ACCOUNTS_FILE = self.accounts_file

        db.init_db()

    def tearDown(self):
        db.close_conn()
        db.DB_PATH = self.orig_db_path
        account_manager._ACCOUNTS_FILE = self.orig_accounts_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Monitored Apps & IDE Selector Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_ide_selector_preferences(self):
        """Test storing and retrieving watched apps for a user."""
        user_id = db.create_user("coder1", "secret123", "Coder One", "coder1@example.com")
        self.assertIsNotNone(user_id)

        # Update watched apps preferences
        test_apps = ["Code.exe", "Cursor.exe", "pycharm64.exe", "custom_tool.exe"]
        db.update_preferences(user_id, watched_apps=json.dumps(test_apps))

        prefs = db.get_preferences(user_id)
        saved_watched = json.loads(prefs.get("watched_apps", "[]"))
        self.assertEqual(saved_watched, test_apps)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Google Account OTP Verification Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_is_google_email(self):
        """Test Google email domain detection."""
        self.assertTrue(otp_service.is_google_email("alice@gmail.com"))
        self.assertTrue(otp_service.is_google_email("bob@googlemail.com"))
        self.assertTrue(otp_service.is_google_email("CHARLIE@GMAIL.COM"))
        self.assertFalse(otp_service.is_google_email("dan@company.com"))
        self.assertFalse(otp_service.is_google_email("eve@yahoo.com"))
        self.assertFalse(otp_service.is_google_email(""))

    def test_generate_and_verify_otp(self):
        """Test generating, storing, and validating 6-digit OTP codes."""
        email = "testuser@gmail.com"
        otp = otp_service.generate_otp()
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

        # Save to database
        db.save_verification_otp(email, otp, purpose="account_verification", expiry_minutes=5)

        # Test verification with wrong OTP
        wrong_ok, wrong_msg = db.verify_stored_otp(email, "000000", purpose="account_verification")
        self.assertFalse(wrong_ok)
        self.assertIn("Invalid", wrong_msg)

        # Test verification with correct OTP
        ok, msg = db.verify_stored_otp(email, otp, purpose="account_verification")
        self.assertTrue(ok)

        # OTP cannot be reused
        reused_ok, reused_msg = db.verify_stored_otp(email, otp, purpose="account_verification")
        self.assertTrue("used" in reused_msg.lower() or "no active" in reused_msg.lower())

    def test_user_google_verification_status(self):
        """Test marking user as verified upon successful Google OTP verification."""
        user_id = db.create_user("google_user", "pass123", "Google User", "google_user@gmail.com")
        self.assertFalse(db.is_user_verified(user_id))

        db.mark_user_verified(user_id, google_id="google_user@gmail.com")
        self.assertTrue(db.is_user_verified(user_id))

        user = db.get_user(user_id)
        self.assertEqual(user.get("is_verified"), 1)
        self.assertEqual(user.get("google_id"), "google_user@gmail.com")

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Multi-Account Management & Switching Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_multi_account_saving_and_switching(self):
        """Test saving multiple accounts, switching active account, and removing."""
        uid1 = db.create_user("user_alpha", "pass1", "Alpha User", "alpha@test.com")
        uid2 = db.create_user("user_beta", "pass2", "Beta User", "beta@test.com")

        # Save first account
        account_manager.save_account("user_alpha", uid1, "user", "Alpha User", "alpha@test.com", "#4f46e5")
        saved = account_manager.get_saved_accounts()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["username"], "user_alpha")
        self.assertTrue(saved[0]["is_active"])

        # Save second account
        account_manager.save_account("user_beta", uid2, "user", "Beta User", "beta@test.com", "#10b981")
        saved = account_manager.get_saved_accounts()
        self.assertEqual(len(saved), 2)

        # Active account is now user_beta
        active = account_manager.get_active_account()
        self.assertEqual(active["username"], "user_beta")

        # Switch back to user_alpha
        switched = account_manager.switch_account("user_alpha")
        self.assertTrue(switched)
        active = account_manager.get_active_account()
        self.assertEqual(active["username"], "user_alpha")

        # Remove an account
        account_manager.remove_saved_account("user_beta")
        saved = account_manager.get_saved_accounts()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["username"], "user_alpha")

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Exclusive Admin Username Routing Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_default_admin_username_exclusivity(self):
        """Test that only 'saumya.patel@Admin_#' is recognized as admin by default."""
        self.assertTrue(db.is_admin_username("saumya.patel@Admin_#"))
        self.assertFalse(db.is_admin_username("other_user"))
        self.assertFalse(db.is_admin_username("admin"))

        # Check default admin user exists in database
        default_admin = db.get_user_by_username_or_email("saumya.patel@Admin_#")
        self.assertIsNotNone(default_admin)
        self.assertEqual(default_admin["role"], "admin")

    def test_change_admin_username_settings(self):
        """
        Test that changing admin username in settings transfers admin exclusivity
        and locks the old username out of the Admin Portal.
        """
        default_admin = db.get_user_by_username_or_email("saumya.patel@Admin_#")
        admin_id = default_admin["id"]

        new_admin = "saumya.lead@custom_admin"
        ok, msg = db.set_admin_username(new_admin, admin_id)
        self.assertTrue(ok)

        # The new username must now be the ONLY admin username
        self.assertTrue(db.is_admin_username(new_admin))
        self.assertFalse(db.is_admin_username("saumya.patel@Admin_#"))

        # Verify DB records
        updated_admin = db.get_user(admin_id)
        self.assertEqual(updated_admin["username"], new_admin)
        self.assertEqual(updated_admin["role"], "admin")

    def test_app_routing_admin_vs_user(self):
        """Test that app._route_user delegates to AdminApp for admin and UserDashboard for users."""
        admin_user = db.get_user_by_username_or_email("saumya.patel@Admin_#")
        regular_id = db.create_user("regular_joe", "pass123", "Joe", "joe@example.com")
        regular_user = db.get_user(regular_id)

        # Test routing for admin
        with patch("admin_app._open_admin_window") as mock_admin_win:
            app._route_user(admin_user)
            mock_admin_win.assert_called_once()
            args, kwargs = mock_admin_win.call_args
            self.assertEqual(kwargs["user"]["username"], "saumya.patel@Admin_#")

        # Test routing for regular user
        with patch("app.UserDashboard") as mock_user_dash:
            mock_instance = MagicMock()
            mock_user_dash.return_value = mock_instance
            app._route_user(regular_user)
            mock_user_dash.assert_called_once()
            mock_instance.run.assert_called_once()
            args, kwargs = mock_user_dash.call_args
            self.assertEqual(kwargs["user"]["username"], "regular_joe")


if __name__ == "__main__":
    unittest.main()
