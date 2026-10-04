"""
Unit tests for Interface Customization & Multiple GitHub Accounts.
"""
import os
import sys
import unittest

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import app_styles
from commitmaster import database as db
from commitmaster import commit_engine
from commitmaster import github_service


class TestCustomizationAndGitHub(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_theme_customization(self):
        # Apply dracula theme and cyan accent
        app_styles.apply_customization(theme="dracula", accent="cyan", font_family="Segoe UI", font_scale="large")
        self.assertEqual(app_styles.COLORS["bg_dark"], "#21222c")
        self.assertEqual(app_styles.COLORS["accent"], "#58a6ff")
        self.assertEqual(app_styles.FONTS["heading_xl"][0], "Segoe UI")

        # Apply midnight and amber
        app_styles.apply_customization(theme="midnight", accent="orange", font_family="Consolas", font_scale="compact")
        self.assertEqual(app_styles.COLORS["bg_dark"], "#0b0c10")
        self.assertEqual(app_styles.COLORS["accent"], "#f0883e")
        self.assertEqual(app_styles.FONTS["heading_xl"][0], "Consolas")

        # Reset to github_dark
        app_styles.apply_customization(theme="github_dark", accent="green", font_family="Segoe UI", font_scale="standard")
        self.assertEqual(app_styles.COLORS["bg_dark"], "#161b22")
        self.assertEqual(app_styles.COLORS["accent"], "#3fb950")

    def test_token_masking(self):
        self.assertEqual(github_service.mask_token(""), "")
        self.assertEqual(github_service.mask_token("ghp_1234567890abcdef"), "ghp_••••••••cdef")
        self.assertEqual(github_service.mask_token("github_pat_11AAAA1234"), "gith••••••••1234")

    def test_github_slug_parsing(self):
        https_url = "https://github.com/Saumya-Patel-10/CommitMaster.git"
        ssh_url = "git@github.com:Saumya-Patel-10/CommitMaster.git"
        no_git_url = "https://github.com/Saumya-Patel-10/CommitMaster"

        self.assertEqual(commit_engine.parse_github_slug(https_url), "Saumya-Patel-10/CommitMaster")
        self.assertEqual(commit_engine.parse_github_slug(ssh_url), "Saumya-Patel-10/CommitMaster")
        self.assertEqual(commit_engine.parse_github_slug(no_git_url), "Saumya-Patel-10/CommitMaster")

    def test_database_github_accounts_and_bindings(self):
        # Create test user
        test_uname = "tester_github_multi"
        test_email = "tester_gh@example.com"
        user = db.authenticate(test_uname, "pass123")
        if not user:
            uid = db.create_user(test_uname, test_email, "Test User", "pass123")
        else:
            uid = user["id"]
        self.assertIsNotNone(uid)

        # Update preferences with new customization fields
        ok = db.update_preferences(
            uid,
            theme="cyberpunk",
            accent_color="#38bdf8",
            font_family="Roboto",
            font_scale="compact",
            ui_density="compact",
            auto_push=1,
        )
        self.assertTrue(ok)
        prefs = db.get_preferences(uid)
        self.assertEqual(prefs["theme"], "cyberpunk")
        self.assertEqual(prefs["accent_color"], "#38bdf8")
        self.assertEqual(prefs["font_family"], "Roboto")
        self.assertEqual(prefs["auto_push"], 1)

        # Add 2 GitHub accounts
        acc1_id = db.add_github_account(
            user_id=uid,
            account_name="Personal Account",
            github_username="personal-dev",
            github_token="ghp_personal_test_token_1234",
            author_name="Personal Dev",
            author_email="personal@example.com",
            is_default=True,
        )
        self.assertIsNotNone(acc1_id)

        acc2_id = db.add_github_account(
            user_id=uid,
            account_name="Work Org Account",
            github_username="work-corp-dev",
            github_token="ghp_work_corp_token_5678",
            author_name="Work Dev",
            author_email="work@example.com",
            is_default=False,
        )
        self.assertIsNotNone(acc2_id)

        # Verify default account
        def_acc = db.get_default_github_account(uid)
        self.assertIsNotNone(def_acc)
        self.assertEqual(def_acc["id"], acc1_id)

        # Switch default account
        db.set_default_github_account(acc2_id, uid)
        def_acc2 = db.get_default_github_account(uid)
        self.assertEqual(def_acc2["id"], acc2_id)

        # Bind repos
        dummy_repo_a = r"C:\Data\Saumya\Projects\RepoA"
        dummy_repo_b = r"C:\Data\Saumya\Projects\RepoB"

        db.bind_repo_to_account(uid, dummy_repo_a, acc1_id)
        db.bind_repo_to_account(uid, dummy_repo_b, acc2_id)

        bound_a = db.get_repo_account(uid, dummy_repo_a)
        bound_b = db.get_repo_account(uid, dummy_repo_b)

        self.assertEqual(bound_a["id"], acc1_id)
        self.assertEqual(bound_b["id"], acc2_id)

        # Clean up test user
        db.delete_github_account(acc1_id, uid)
        db.delete_github_account(acc2_id, uid)
        db.hard_delete_user(uid)

    def test_watched_repositories_and_web_auth(self):
        # 1. Test Web Auth URL generation
        auth_url = github_service.get_github_web_auth_url("CommitMaster Test")
        self.assertIn("https://github.com/settings/tokens/new", auth_url)
        self.assertIn("scopes=", auth_url)
        self.assertIn("repo", auth_url)
        self.assertTrue("user:email" in auth_url or "user%3Aemail" in auth_url)

        # 2. Test Watched Repos database operations
        uid = db.create_user("test_watched_user", "watched@example.com", "Watcher", "pass123")
        self.assertIsNotNone(uid)

        # Add watched repos
        repo_id = db.add_or_update_watched_repo(
            user_id=uid,
            repo_full_name="octocat/Hello-World",
            repo_name="Hello-World",
            clone_url="https://github.com/octocat/Hello-World.git",
            ssh_url="git@github.com:octocat/Hello-World.git",
            default_branch="main",
            local_path=r"C:\Projects\Hello-World",
            is_private=0,
            description="My first repo",
            is_active_watch=1,
        )
        self.assertIsNotNone(repo_id)

        # Retrieve watched repos
        watched = db.get_watched_repos(uid, active_only=True)
        self.assertEqual(len(watched), 1)
        self.assertEqual(watched[0]["repo_full_name"], "octocat/Hello-World")
        self.assertEqual(watched[0]["is_active_watch"], 1)

        # Toggle watch
        db.toggle_watched_repo(watched[0]["id"], uid, is_active=False)
        active_watched = db.get_watched_repos(uid, active_only=True)
        self.assertEqual(len(active_watched), 0)

        # Update local path
        db.set_watched_repo_local_path(watched[0]["id"], uid, r"C:\Data\NewPath")
        found_by_path = db.get_watched_repo_by_path(r"C:\Data\NewPath", uid)
        self.assertIsNotNone(found_by_path)
        self.assertEqual(found_by_path["repo_name"], "Hello-World")

        # Sync GitHub repos in bulk
        fake_api_repos = [
            {"name": "Repo1", "full_name": "octocat/Repo1", "private": False, "description": "Repo 1", "clone_url": "https://..."},
            {"name": "Repo2", "full_name": "octocat/Repo2", "private": True, "description": "Repo 2", "clone_url": "https://..."},
        ]
        count = db.sync_github_repos(uid, None, fake_api_repos)
        self.assertEqual(count, 2)
        all_user_repos = db.get_watched_repos(uid)
        self.assertEqual(len(all_user_repos), 3)

        # Clean up
        db.hard_delete_user(uid)

    def test_per_file_ai_comments_and_push_preferences(self):
        from commitmaster import ai_messages
        cfg = {"ai": {"base_url": "http://localhost:1234/v1", "model": "", "timeout_seconds": 1}}
        
        # Test per-file comment generation on current repo
        test_files = ["commitmaster/database.py", "commitmaster/github_service.py", "README.md"]
        result = ai_messages.generate_file_comments(cfg, APP_DIR, test_files)
        
        self.assertIn("headline", result)
        self.assertIn("file_comments", result)
        self.assertIn("description", result)
        self.assertIsInstance(result["file_comments"], dict)
        self.assertIn("commitmaster/database.py", result["file_comments"])
        self.assertTrue(len(result["headline"]) > 0)
        self.assertTrue(len(result["description"]) > 0)

        # Test ask_before_push preference
        uid = db.create_user("test_push_pref", "push@example.com", "Pusher", "pass123")
        self.assertIsNotNone(uid)

        # Default ask_before_push
        prefs = db.get_preferences(uid)
        self.assertEqual(prefs.get("ask_before_push"), 1)

        # Update ask_before_push to 0
        db.update_preferences(uid, ask_before_push=0)
        prefs_updated = db.get_preferences(uid)
        self.assertEqual(prefs_updated.get("ask_before_push"), 0)

        db.hard_delete_user(uid)


if __name__ == "__main__":
    unittest.main()

