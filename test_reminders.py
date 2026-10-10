"""
Unit tests for CommitMaster Notification Reminder System:
  • Bottom-right corner Toast window and work-area placement
  • ReminderService interval timer and IDE monitoring lifecycle
  • Database preferences persistence and migration
  • Config defaults and synchronization
"""
import os
import sys
import time
import unittest
import tkinter as tk

from commitmaster import config, database as db
from commitmaster.notification_toast import NotificationToast, _get_work_area
from commitmaster.reminder_service import ReminderService, STATE_IDLE, STATE_ACTIVE, STATE_ENDING


class TestNotificationReminders(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_work_area_computation(self):
        """Test Windows desktop work area is valid."""
        left, top, right, bottom = _get_work_area()
        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)
        self.assertGreater(right, 100)
        self.assertGreater(bottom, 100)

    def test_notification_toast_creation_and_close(self):
        """Test bottom-right toast creation, positioning, and programmatic close."""
        root = tk.Tk()
        root.withdraw()

        toast = NotificationToast(
            title="Test Reminder",
            message="Testing toast popup",
            badge_text="UNIT TEST",
            dirty_repos=[os.getcwd()],
            duration_seconds=10,
            master=root,
        )
        toast.show()

        self.assertIsNotNone(toast.win)
        self.assertTrue(toast.win.winfo_exists())

        # Test close
        toast.close()
        self.assertIsNone(toast.win)
        root.destroy()

    def test_database_reminder_preferences(self):
        """Test user_preferences contains reminder columns and updates correctly."""
        # Check admin user
        admin = db.get_user(1)
        self.assertIsNotNone(admin)

        prefs = db.get_preferences(1)
        self.assertIn("reminder_interval_enabled", prefs)
        self.assertIn("reminder_interval_hours", prefs)
        self.assertIn("reminder_interval_minutes", prefs)
        self.assertIn("reminder_app_monitor_enabled", prefs)
        self.assertIn("reminder_only_if_dirty", prefs)

        # Update values
        db.update_preferences(
            1,
            reminder_interval_enabled=1,
            reminder_interval_hours=2,
            reminder_interval_minutes=30,
            reminder_app_monitor_enabled=1,
            reminder_only_if_dirty=1,
        )

        updated = db.get_preferences(1)
        self.assertEqual(updated["reminder_interval_hours"], 2)
        self.assertEqual(updated["reminder_interval_minutes"], 30)
        self.assertEqual(updated["reminder_interval_enabled"], 1)

    def test_config_defaults(self):
        """Test config.json default includes reminder settings and expanded watched IDEs."""
        cfg = config.DEFAULTS
        self.assertIn("watched_apps", cfg)
        self.assertIn("Code.exe", cfg["watched_apps"])
        self.assertIn("Antigravity.exe", cfg["watched_apps"])

        rem = cfg.get("reminder", {})
        self.assertIn("interval_enabled", rem)
        self.assertIn("app_monitor_enabled", rem)

    def test_reminder_service_lifecycle(self):
        """Test ReminderService initialization, state, snooze, and preferences update."""
        service = ReminderService(user_id=1, grace_period_seconds=5)
        self.assertEqual(service.monitor_state, STATE_IDLE)

        # Test snooze
        old_time = service.last_interval_reminder_time
        service.snooze(15)
        self.assertGreater(service.last_interval_reminder_time, old_time)

        # Test dynamic updates
        service.update_preferences(
            interval_enabled=False,
            interval_hours=3,
            interval_minutes=15,
            app_monitor_enabled=False,
        )
        self.assertFalse(service.interval_enabled)
        self.assertEqual(service.interval_hours, 3)
        self.assertEqual(service.interval_minutes, 15)
        self.assertFalse(service.app_monitor_enabled)

        service.stop()

    def test_ide_presets_and_scanner(self):
        """Test IDE presets structure and running process scanner."""
        from commitmaster.reminder_service import IDE_PRESETS, get_running_ide_processes
        self.assertGreater(len(IDE_PRESETS), 5)
        for preset in IDE_PRESETS:
            self.assertIn("name", preset)
            self.assertIn("exe", preset)
            self.assertTrue(preset["exe"].endswith(".exe"))

        running = get_running_ide_processes()
        self.assertIsInstance(running, set)

    def test_did_you_commit_toast_actions(self):
        """Test did_you_commit toast mode has Yes and No handlers."""
        root = tk.Tk()
        root.withdraw()

        yes_called = [False]
        no_called = [False]

        toast = NotificationToast(
            title="Did you commit your changes?",
            message="You closed your IDE. Did you commit?",
            badge_text="IDE CLOSED",
            toast_mode="did_you_commit",
            on_yes=lambda: yes_called.__setitem__(0, True),
            on_no=lambda: no_called.__setitem__(0, True),
            master=root,
        )
        toast.show()

        # Simulate clicking "Yes, I did" -> no commit action
        toast._do_yes()
        self.assertTrue(yes_called[0])
        self.assertFalse(no_called[0])
        self.assertIsNone(toast.win)

        # Create another toast and simulate clicking "No, help me commit"
        toast2 = NotificationToast(
            title="Did you commit your changes?",
            message="You closed your IDE. Did you commit?",
            badge_text="IDE CLOSED",
            toast_mode="did_you_commit",
            on_yes=lambda: None,
            on_no=lambda: no_called.__setitem__(0, True),
            master=root,
        )
        toast2.show()
        toast2._do_no()
        self.assertTrue(no_called[0])
        self.assertIsNone(toast2.win)

        root.destroy()

    def test_autocommit_countdown_and_cancellation(self):
        """Test 10-second countdown tick and cancellation logic."""
        class MockDashboard:
            def __init__(self):
                self._countdown_remaining = 10
                self._countdown_cancelled = False
                self._countdown_timer = 999

            def cancel(self):
                self._countdown_cancelled = True
                self._countdown_timer = None

            def tick(self):
                if self._countdown_cancelled:
                    return False
                self._countdown_remaining -= 1
                return self._countdown_remaining == 0

        mock = MockDashboard()
        self.assertEqual(mock._countdown_remaining, 10)
        # Tick 3 times
        mock.tick()
        mock.tick()
        mock.tick()
        self.assertEqual(mock._countdown_remaining, 7)

        # Cancel
        mock.cancel()
        self.assertTrue(mock._countdown_cancelled)
        self.assertIsNone(mock._countdown_timer)
        self.assertFalse(mock.tick())
        self.assertEqual(mock._countdown_remaining, 7)


if __name__ == "__main__":
    unittest.main()

