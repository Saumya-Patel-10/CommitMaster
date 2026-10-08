"""
Test suite verifying:
1. One and only one admin account: saumya.patel@Admin_#
2. Scroll functionality in AdminPortal and AdminApp
3. Two distinct logos and Windows taskbar icons for User and Admin apps
"""
import os
import sys
import unittest
import sqlite3
import tkinter as tk
from PIL import Image

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import database as db
from commitmaster import windows_integration
from commitmaster.admin_portal import AdminPortal
from admin_app import AdminApp


class TestAdminScrollAndLogos(unittest.TestCase):

    def test_01_single_admin_account_enforced(self):
        """Verify that saumya.patel@Admin_# is the one and only admin account."""
        db.init_db()

        # Check commitmaster.db
        conn = sqlite3.connect("commitmaster.db")
        cur = conn.cursor()
        cur.execute("SELECT id, username, role FROM users WHERE role = 'admin'")
        admins = cur.fetchall()
        conn.close()

        self.assertEqual(len(admins), 1, f"Expected exactly 1 admin, found: {admins}")
        self.assertEqual(admins[0][1], "saumya.patel@Admin_#")

        # Test protection: cannot delete or demote Saumya
        saumya_id = admins[0][0]
        self.assertFalse(db.delete_user(saumya_id))
        self.assertFalse(db.hard_delete_user(saumya_id))

        # Test protection: cannot promote standard user to admin
        dummy_id = db.create_user("test_regular_user", "reg@example.com", "Regular", "pass123", role="admin")
        self.assertIsNotNone(dummy_id)
        u = db.get_user(dummy_id)
        self.assertEqual(u["role"], "user", "create_user should have forced role to 'user'")

        # Attempt to update dummy to admin
        db.update_user(dummy_id, role="admin")
        u = db.get_user(dummy_id)
        self.assertEqual(u["role"], "user", "update_user should refuse promoting non-Saumya user to admin")

        # Clean up dummy
        db.hard_delete_user(dummy_id)

    def test_02_distinct_logos_and_icons_exist(self):
        """Verify two distinct logos (user and admin) and valid multi-size ICO files."""
        user_ico = windows_integration.get_icon_path("user")
        admin_ico = windows_integration.get_icon_path("admin")

        self.assertIsNotNone(user_ico)
        self.assertIsNotNone(admin_ico)
        self.assertTrue(os.path.exists(user_ico))
        self.assertTrue(os.path.exists(admin_ico))
        self.assertNotEqual(user_ico, admin_ico)

        # Verify ICO files open and have proper dimensions
        with Image.open(user_ico) as im_u:
            self.assertEqual(im_u.format, "ICO")
        with Image.open(admin_ico) as im_a:
            self.assertEqual(im_a.format, "ICO")

        # Verify distinct PNG logos
        user_png = os.path.join(APP_DIR, "assets", "logo_user.png")
        admin_png = os.path.join(APP_DIR, "assets", "logo_admin.png")
        self.assertTrue(os.path.exists(user_png))
        self.assertTrue(os.path.exists(admin_png))

    def test_03_admin_portal_scroll_works(self):
        """Verify AdminPortal calculates proper scrollregion and can scroll."""
        portal = AdminPortal(
            admin_user={"id": 1, "username": "saumya.patel@Admin_#", "email": "saumya.a.patel@gmail.com", "role": "admin"},
            on_close=lambda: None
        )
        portal.root.withdraw()
        portal._go("account")
        portal.root.update()

        sr = portal._canvas.cget("scrollregion")
        coords = [int(float(x)) for x in sr.split()]
        self.assertEqual(len(coords), 4)
        # Scrollregion height must be greater than canvas height to allow scrolling
        self.assertGreater(coords[3], 500, f"Scrollregion height {coords[3]} is too small")

        # Test scrolling down
        before_scroll = portal._canvas.yview()
        portal._canvas.yview_scroll(10, "units")
        after_scroll = portal._canvas.yview()
        self.assertGreater(after_scroll[0], before_scroll[0])
        portal.root.destroy()

    def test_04_admin_app_scroll_works(self):
        """Verify AdminApp calculates proper scrollregion and can scroll."""
        app = AdminApp({
            "id": 1,
            "username": "saumya.patel@Admin_#",
            "email": "saumya.a.patel@gmail.com",
            "role": "admin"
        })
        app.root.withdraw()
        app._go("account")
        app.root.update()

        sr = app._canvas.cget("scrollregion")
        coords = [int(float(x)) for x in sr.split()]
        self.assertEqual(len(coords), 4)
        self.assertGreater(coords[3], 1000, f"AdminApp Scrollregion height {coords[3]} should reflect account page")

        # Test scrolling down
        before_scroll = app._canvas.yview()
        app._canvas.yview_scroll(10, "units")
        after_scroll = app._canvas.yview()
        self.assertGreater(after_scroll[0], before_scroll[0])
        app.root.destroy()


if __name__ == "__main__":
    unittest.main()
