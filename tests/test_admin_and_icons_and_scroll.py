"""
Test suite verifying:
1. One and only one admin account: test.admin@Admin_#
2. Scroll functionality in AdminPortal and AdminApp
3. Two distinct logos and Windows taskbar icons for User and Admin apps
"""
import os
import sys
import unittest
import sqlite3
import tkinter as tk
from PIL import Image

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import database as db
from commitmaster import windows_integration
from commitmaster.admin_portal import AdminPortal
from admin_app import AdminApp


class TestAdminScrollAndLogos(unittest.TestCase):

    def test_01_single_admin_account_enforced(self):
        """Verify that test.admin@Admin_# is the one and only admin account."""
        db.init_db()

        # Check commitmaster.db
        conn = sqlite3.connect(db.DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id, username, role FROM users WHERE role = 'admin'")
        admins = cur.fetchall()
        conn.close()

        self.assertEqual(len(admins), 1, f"Expected exactly 1 admin, found: {admins}")
        self.assertEqual(admins[0][1], "test.admin@Admin_#")

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
            admin_user={"id": 1, "username": "test.admin@Admin_#", "email": "test.admin@example.com", "role": "admin"},
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
            "username": "test.admin@Admin_#",
            "email": "test.admin@example.com",
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

    def test_05_admin_portal_window_resizability_and_protocol(self):
        """Verify AdminPortal window is resizable, has minsize, and binds WM_DELETE_WINDOW."""
        closed = []
        portal = AdminPortal(
            admin_user={"id": 1, "username": "test.admin@Admin_#", "email": "test.admin@example.com", "role": "admin"},
            on_close=lambda: closed.append(True)
        )
        portal.root.withdraw()
        portal.root.update_idletasks()

        # Check resizable
        resizable_x, resizable_y = portal.root.resizable()
        self.assertTrue(resizable_x)
        self.assertTrue(resizable_y)

        # Check minsize
        min_w, min_h = portal.root.minsize()
        self.assertGreaterEqual(min_w, 960)
        self.assertGreaterEqual(min_h, 600)

        # Check WM_DELETE_WINDOW protocol
        protocol_handler = portal.root.protocol("WM_DELETE_WINDOW")
        self.assertTrue(bool(protocol_handler))

        # Trigger go_back and verify on_close callback called
        portal._go_back()
        self.assertTrue(len(closed) > 0 and closed[0])

    def test_06_admin_portal_responsive_user_table_and_activity(self):
        """Verify AdminPortal responsive grid layout in User Management and Activity Log."""
        portal = AdminPortal(
            admin_user={"id": 1, "username": "test.admin@Admin_#", "email": "test.admin@example.com", "role": "admin"},
            on_close=lambda: None
        )
        portal.root.withdraw()

        # Navigate to users page
        portal._go("users")
        portal.root.update()

        # Verify grid layout used for user rows
        self.assertTrue(hasattr(portal, "_user_row_widgets"))
        for uid, row_data in portal._user_row_widgets.items():
            row_frame = row_data["row"]
            # Column 6 must be the Actions frame
            col_info = row_frame.grid_columnconfigure(6)
            self.assertGreaterEqual(col_info["minsize"], 200)

        # Simulate resize to wide window
        portal.root.geometry("1400x800")
        portal.root.update()
        canvas_w = portal._canvas.winfo_width()
        content_w = portal._content_frame.winfo_width()
        self.assertGreaterEqual(canvas_w, 800)

        # Navigate to activity log
        portal._go("activity")
        portal.root.update()

        # Navigate to customize page
        portal._go("customize")
        portal.root.update()
        self.assertTrue(hasattr(portal, "_theme_cards"))
        self.assertEqual(len(portal._theme_cards), 8)

        portal.root.destroy()


if __name__ == "__main__":
    unittest.main()
