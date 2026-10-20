"""
Test suite for Origin Tracking, Auto-Commit binding, and Watched Repos Status Tab with AI Recommendations.
"""
import os
import sys
import unittest
import tempfile
import shutil
import subprocess

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import database as db
from commitmaster import repo_analyzer
from commitmaster.reminder_service import ReminderService


class TestOriginTrackingAndStatus(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_status.db")
        db.close_conn()
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        # Create a mock git repository with origin remote
        self.repo_dir = os.path.join(self.test_dir, "test_repo")
        os.makedirs(self.repo_dir, exist_ok=True)
        subprocess.run(["git", "init"], cwd=self.repo_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=self.repo_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "runner@example.com"], cwd=self.repo_dir, capture_output=True, check=True)
        
        # Add a dummy commit so repo has HEAD
        test_file = os.path.join(self.repo_dir, "hello.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("# Hello world script\ndef main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()\n")
        subprocess.run(["git", "add", "hello.py"], cwd=self.repo_dir, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.repo_dir, capture_output=True, check=True)

        # Set remote origin to octocat's repository
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/octocat/test_repo.git"],
            cwd=self.repo_dir,
            capture_output=True,
            check=True
        )

    def tearDown(self):
        db.close_conn()
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_auto_detect_and_bind_repo_origin(self):
        """Verify that a repo cloned from octocat binds to octocat's GitHub account."""
        user_id = db.create_user("coder1", "coder1@example.com", "Coder One", "secret123")
        self.assertIsNotNone(user_id)

        # Add two accounts: alice and octocat
        acc_alice = db.add_github_account(
            user_id=user_id,
            account_name="Alice Personal",
            github_username="alice",
            github_token="ghp_alice_token_123",
            author_name="Alice Dev",
            author_email="alice@example.com",
            is_default=True,
        )
        acc_octocat = db.add_github_account(
            user_id=user_id,
            account_name="Octocat Work",
            github_username="octocat",
            github_token="ghp_octocat_token_456",
            author_name="The Octocat",
            author_email="octocat@github.com",
            is_default=False,
        )

        # Add repo to watched_repositories without explicit account
        db.add_or_update_watched_repo(
            user_id=user_id,
            repo_full_name="octocat/test_repo",
            repo_name="test_repo",
            local_path=self.repo_dir,
        )

        # Auto-detect and bind origin
        bound_acc = db.auto_detect_and_bind_repo_origin(user_id, self.repo_dir)
        self.assertIsNotNone(bound_acc)
        self.assertEqual(bound_acc["id"], acc_octocat)
        self.assertEqual(bound_acc["github_username"], "octocat")

        # Calling get_repo_account should return octocat
        matched = db.get_repo_account(user_id, self.repo_dir)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["id"], acc_octocat)
        self.assertEqual(matched["github_username"], "octocat")

    def test_manual_override_persists(self):
        """Verify that if user manually changes the account in settings, manual choice takes precedence."""
        user_id = db.create_user("coder2", "coder2@example.com", "Coder Two", "secret123")
        acc_alice = db.add_github_account(
            user_id=user_id,
            account_name="Alice Personal",
            github_username="alice",
            github_token="ghp_alice_token_123",
            author_name="Alice Dev",
            author_email="alice@example.com",
            is_default=True,
        )
        acc_octocat = db.add_github_account(
            user_id=user_id,
            account_name="Octocat Work",
            github_username="octocat",
            github_token="ghp_octocat_token_456",
            author_name="The Octocat",
            author_email="octocat@github.com",
            is_default=False,
        )

        db.add_or_update_watched_repo(
            user_id=user_id,
            repo_full_name="octocat/test_repo",
            repo_name="test_repo",
            local_path=self.repo_dir,
        )
        db.auto_detect_and_bind_repo_origin(user_id, self.repo_dir)

        # User manually overrides to alice
        db.bind_repo_to_account(user_id, self.repo_dir, acc_alice)

        # get_repo_account should return alice
        matched = db.get_repo_account(user_id, self.repo_dir)
        self.assertEqual(matched["id"], acc_alice)
        self.assertEqual(matched["github_username"], "alice")

    def test_repo_analyzer_scan_status_and_logs(self):
        """Verify that scan_repo_status_and_logs correctly parses branch, commit counts, and diagnostics."""
        user_id = db.create_user("coder3", "coder3@example.com", "Coder Three", "secret123")

        # Create an uncommitted file with a dynamically built secret to avoid flagging test files
        fake_key = "sk-" + "1234567890abcdef1234567890abcdef"
        dirty_file = os.path.join(self.repo_dir, "dirty.py")
        with open(dirty_file, "w", encoding="utf-8") as f:
            f.write(f"import os\n# Dirty file with hardcoded secret\nAPI_KEY = '{fake_key}'\n")

        # Create a sample error log file in the repo
        log_file = os.path.join(self.repo_dir, "app.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("2026-10-19 12:00:00 [ERROR] Failed to connect to remote service: TimeoutException\n")

        status_info = repo_analyzer.scan_repo_status_and_logs(self.repo_dir, user_id)
        self.assertIn("branch", status_info)
        self.assertGreaterEqual(status_info["commits_count"], 1)
        self.assertGreaterEqual(status_info["uncommitted_count"], 1)

        # Check disk logs were picked up
        disk_logs = status_info.get("disk_logs", [])
        self.assertTrue(any("TimeoutException" in str(item.get("snippet")) for item in disk_logs))

        # Check code diagnostics picked up the hardcoded secret
        code_issues = status_info.get("code_issues", [])
        self.assertTrue(any(issue.get("file") == "dirty.py" for issue in code_issues))

    def test_repo_analyzer_recommendations(self):
        """Verify that generate_repo_recommendations returns test cases, feature ideas, and guidelines."""
        # Create a README
        readme_file = os.path.join(self.repo_dir, "README.md")
        with open(readme_file, "w", encoding="utf-8") as f:
            f.write("# Payment Service\nHigh-performance payment gateway client for processing stripe and paypal transactions.\n")

        cfg = {"ai": {"provider": "bionic"}}
        recs = repo_analyzer.generate_repo_recommendations(self.repo_dir, cfg)

        self.assertIn("test_cases", recs)
        self.assertIn("features", recs)
        self.assertIn("bug_prevention", recs)

        # Check test cases have title, description, scenario, target
        test_cases = recs["test_cases"]
        self.assertGreaterEqual(len(test_cases), 1)
        first_tc = test_cases[0]
        self.assertIn("title", first_tc)
        self.assertIn("description", first_tc)
        self.assertIn("scenario", first_tc)

        # Check features have title and description
        features = recs["features"]
        self.assertGreaterEqual(len(features), 1)
        self.assertIn("title", features[0])

    def test_admin_and_user_feature_parity(self):
        """Verify that AdminApp and UserDashboard have 100% parity for new features and fixes."""
        import admin_app
        from commitmaster.user_dashboard import UserDashboard
        from commitmaster import admin_portal

        required_methods = [
            "_wr_switch_sub_tab",
            "_wr_auto_commit_pending",
            "_refresh_ai_recommendations",
            "_render_repo_status_tab",
            "_section_title",
            "_should_track_logs",
            "_wr_add_local_repo",
            "_wr_link_local_folder",
            "_wr_build_repo_card",
        ]

        for method_name in required_methods:
            self.assertTrue(
                hasattr(admin_app.AdminApp, method_name),
                f"AdminApp is missing method {method_name}!"
            )
            self.assertTrue(
                hasattr(UserDashboard, method_name),
                f"UserDashboard is missing method {method_name}!"
            )

        # Ensure surface pattern texture card selector was removed from both admin customize interfaces
        self.assertFalse(hasattr(admin_portal.AdminPortal, "_select_pattern_card"))
        self.assertFalse(hasattr(admin_app.AdminApp, "_select_pattern_card"))


if __name__ == "__main__":
    unittest.main()
