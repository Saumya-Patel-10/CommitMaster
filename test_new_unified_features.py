"""
Test suite for CommitMaster unified features:
  1. Monitored Apps & IDE selection
  2. Multi-account saving and switching (including Admin second user account)
  3. Single unified application routing and exclusive admin username management
  4. Account deletion with 30-day recovery grace period
  5. Custom avatar logo and profile picture (PFP) upload
"""
import os
import sys
import unittest
import tempfile
import json
import shutil
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import database as db
from commitmaster import account_manager
from commitmaster import avatar_utils
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
        user_id = db.create_user("coder1", "coder1@example.com", "Coder One", "secret123")
        self.assertIsNotNone(user_id)

        # Update watched apps preferences
        test_apps = ["Code.exe", "Cursor.exe", "pycharm64.exe", "custom_tool.exe"]
        db.update_preferences(user_id, watched_apps=json.dumps(test_apps))

        prefs = db.get_preferences(user_id)
        saved_watched = json.loads(prefs.get("watched_apps", "[]"))
        self.assertEqual(saved_watched, test_apps)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Admin Second Account (Strict User Role) & Shared Email Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_admin_second_account_is_strictly_user(self):
        """
        Verify that an Admin can create another account (even with the same email),
        but that other account is strictly a 'user' role with NO admin access.
        """
        admin = db.get_user_by_username_or_email("saumya.patel@Admin_#")
        self.assertIsNotNone(admin)
        self.assertEqual(admin["role"], "admin")
        admin_email = admin.get("email") or "saumya.patel@admin.com"

        # Admin creates a second account with their email
        second_username = "saumya_personal"
        second_uid = db.create_user(second_username, admin_email, "Saumya Patel", "Pass123!")
        self.assertIsNotNone(second_uid)

        second_user = db.get_user(second_uid)
        self.assertEqual(second_user["role"], "user")
        self.assertFalse(db.is_admin_username(second_username))

        # Trying to pass role="admin" during creation must still force role="user"
        third_uid = db.create_user("fake_admin", "fake@example.com", "Fake Admin", "Pass123!", role="admin")
        third_user = db.get_user(third_uid)
        self.assertEqual(third_user["role"], "user")
        self.assertFalse(db.is_admin_username("fake_admin"))

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Account Deletion with 30-Day Recovery Period Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_account_soft_deletion_and_recovery(self):
        """
        Test soft-deleting an account, ensuring 30-day recovery grace period,
        auto-recovery on login within 30 days, and rejection of admin deletion.
        """
        # Primary admin account cannot be soft-deleted
        admin = db.get_user_by_username_or_email("saumya.patel@Admin_#")
        ok_admin_del, msg = db.soft_delete_user(admin["id"])
        self.assertFalse(ok_admin_del)
        self.assertIn("cannot be deleted", msg)

        # Regular user account can be soft-deleted
        uid = db.create_user("delete_me_user", "del@example.com", "Delete Me", "ValidPass1!")
        self.assertIsNotNone(uid)

        del_ok, del_msg = db.soft_delete_user(uid)
        self.assertTrue(del_ok)

        # Check soft-deleted fields
        user_info = db.get_user(uid)
        self.assertIsNotNone(user_info["deleted_at"])
        self.assertIsNotNone(user_info["deletion_scheduled_until"])

        # Authenticate within 30 days -> account recovered automatically
        recovered_user = db.authenticate("delete_me_user", "ValidPass1!")
        self.assertIsNotNone(recovered_user)
        self.assertTrue(recovered_user.get("account_recovered"))

        # Re-check user info: deleted_at and deletion_scheduled_until must now be cleared
        refreshed = db.get_user(uid)
        self.assertIsNone(refreshed["deleted_at"])
        self.assertIsNone(refreshed["deletion_scheduled_until"])

    def test_account_permanent_deletion_after_30_days(self):
        """Test that attempting to authenticate > 30 days after deletion permanently drops user."""
        uid = db.create_user("expired_user", "exp@example.com", "Expired User", "ValidPass1!")
        db.soft_delete_user(uid)

        # Manually backdate deletion date past 30 days
        expired_date = (datetime.now() - timedelta(days=31)).strftime("%Y-%m-%d %H:%M:%S")
        conn = db.get_conn()
        conn.execute(
            "UPDATE users SET deletion_scheduled_until = ? WHERE id = ?",
            (expired_date, uid)
        )
        conn.commit()

        # Login attempt should fail because 30-day grace period has passed
        user = db.authenticate("expired_user", "ValidPass1!")
        self.assertIsNone(user)

        # User is permanently deleted
        self.assertIsNone(db.get_user(uid))

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Custom Avatar Logo & Profile Picture (PFP) Upload Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_custom_avatar_logo_and_pfp(self):
        """Test custom color logo creation and image profile picture upload."""
        uid = db.create_user("avatar_artist", "art@example.com", "Avatar Artist", "Pass123!", avatar_color="#e06c75")
        user = db.get_user(uid)
        self.assertEqual(user["avatar_color"], "#e06c75")
        self.assertFalse(user["avatar_image"])

        # Create a mock image file to upload
        from PIL import Image
        test_img_path = os.path.join(self.test_dir, "test_pic.png")
        img = Image.new("RGB", (300, 200), color=(70, 130, 180))
        img.save(test_img_path)

        # Save as avatar image
        ok, res_path = avatar_utils.save_avatar_image(uid, test_img_path)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(res_path))

        # Check DB updated
        updated_user = db.get_user(uid)
        self.assertEqual(updated_user["avatar_image"], res_path)

        # Remove avatar image -> reverts to custom avatar logo
        rem_ok = avatar_utils.remove_avatar_image(uid)
        self.assertTrue(rem_ok)
        reverted_user = db.get_user(uid)
        self.assertEqual(reverted_user["avatar_image"], "")

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Multi-Account Management & Switching Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_multi_account_saving_and_switching(self):
        """Test saving multiple accounts, switching active account, and removing."""
        uid1 = db.create_user("user_alpha", "alpha@test.com", "Alpha User", "pass1")
        uid2 = db.create_user("user_beta", "beta@test.com", "Beta User", "pass2")

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

    def test_account_switcher_dialog_arguments_compatibility(self):
        """
        Verify that AccountSwitcherDialog accepts on_account_switched as kwarg,
        resolving the exact bug seen in the user error dialog.
        """
        import inspect
        sig = inspect.signature(account_manager.AccountSwitcherDialog.__init__)
        params = sig.parameters
        self.assertTrue(any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()))

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Exclusive Admin Username Routing Tests
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


if __name__ == "__main__":
    unittest.main()
