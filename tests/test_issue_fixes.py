"""
Targeted tests for:
1. Capitalio Performance Chart multi-series stats (Commits, Vulnerabilities, Errors, Failures, Sessions)
2. Notification toast single-notification verification
3. Admin user management multi-select & bulk operations
"""
import unittest
import tkinter as tk
from commitmaster import database as db
from commitmaster import charts
from commitmaster import notification_toast


class TestIssueFixes(unittest.TestCase):

    def setUp(self):
        db.init_db()

    def test_01_capitalio_performance_chart_multi_series_and_toggles(self):
        root = tk.Tk()
        root.withdraw()
        dates = ["2026-10-10", "2026-10-11", "2026-10-12", "2026-10-13", "2026-10-14"]
        series_dict = {
            "commits": {"label": "Commits", "values": [5, 10, 15, 8, 12], "color": "#10b981", "fill": True, "visible": True},
            "vulns": {"label": "Vulnerabilities", "values": [0, 1, 0, 2, 0], "color": "#f59e0b", "fill": False, "visible": True},
            "errors": {"label": "Code Errors", "values": [1, 0, 2, 0, 1], "color": "#a855f7", "fill": False, "visible": True},
            "failures": {"label": "Failures", "values": [0, 0, 1, 0, 0], "color": "#f43f5e", "fill": False, "visible": True},
            "sessions": {"label": "Sessions", "values": [2, 3, 4, 3, 4], "color": "#38bdf8", "fill": False, "visible": False},
        }

        toggled = []
        def _on_toggle(key, is_vis):
            toggled.append((key, is_vis))

        chart = charts.CapitalioPerformanceChart(
            root, dates=dates, series_dict=series_dict, height=220, on_toggle_callback=_on_toggle
        )
        self.assertTrue(chart.is_series_visible("commits"))
        self.assertTrue(chart.is_series_visible("vulns"))
        self.assertTrue(chart.is_series_visible("errors"))
        self.assertTrue(chart.is_series_visible("failures"))
        self.assertFalse(chart.is_series_visible("sessions"))

        # Toggle vulnerabilities off
        chart.toggle_series("vulns")
        self.assertFalse(chart.is_series_visible("vulns"))
        self.assertEqual(toggled[-1], ("vulns", False))

        # Toggle sessions on
        chart.toggle_series("sessions")
        self.assertTrue(chart.is_series_visible("sessions"))
        self.assertEqual(toggled[-1], ("sessions", True))

        # Redraw does not raise
        chart.redraw()
        root.destroy()

    def test_02_toast_does_not_call_plyer(self):
        # Verify plyer notification is NOT in notification_toast.py globals or show_toast
        import inspect
        src = inspect.getsource(notification_toast.show_toast)
        self.assertNotIn("notification.notify", src)
        self.assertNotIn("from plyer import notification", src)

    def test_03_bulk_user_operations_in_database(self):
        import time
        ts = time.time_ns()
        # Create test users with unique usernames
        u1 = db.create_user(f"bulk_u1_{ts}", f"u1_{ts}@example.com", "User One", "P@ss12345", "user")
        u2 = db.create_user(f"bulk_u2_{ts}", f"u2_{ts}@example.com", "User Two", "P@ss12345", "user")
        self.assertIsNotNone(u1)
        self.assertIsNotNone(u2)

        # Bulk disable
        updated = db.bulk_update_users_active([u1, u2], 0, exclude_user_id=1)
        self.assertEqual(updated, 2)
        self.assertFalse(db.get_user(u1)["is_active"])
        self.assertFalse(db.get_user(u2)["is_active"])

        # Bulk enable
        updated = db.bulk_update_users_active([u1, u2], 1, exclude_user_id=1)
        self.assertEqual(updated, 2)
        self.assertTrue(db.get_user(u1)["is_active"])
        self.assertTrue(db.get_user(u2)["is_active"])

        # Bulk delete
        deleted = db.bulk_delete_users([u1, u2], hard=True, exclude_user_id=1)
        self.assertEqual(deleted, 2)
        self.assertIsNone(db.get_user(u1))
        self.assertIsNone(db.get_user(u2))


if __name__ == "__main__":
    unittest.main()
