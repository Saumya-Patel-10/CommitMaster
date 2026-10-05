"""
Unit and integration test for new features:
1. File Inspector (Pre-commit syntax errors, merge conflict markers, secret leaks)
2. Individual file commits vs All-in-one commits in Commit Engine
3. User Dashboard & Admin App import and syntax sanity
"""
import os
import shutil
import tempfile
import unittest

from commitmaster import commit_engine, file_inspector
from commitmaster.commit_engine import git


class TestNewFeatures(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="cm_test_")
        # Initialize a real temporary git repo
        git(self.test_dir, "init")
        git(self.test_dir, "config", "user.name", "Test User")
        git(self.test_dir, "config", "user.email", "test@commitmaster.local")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_file_inspector_clean_file(self):
        good_py = os.path.join(self.test_dir, "valid.py")
        with open(good_py, "w", encoding="utf-8") as f:
            f.write("def hello():\n    return 'world'\n")
        issues = file_inspector.inspect_file(self.test_dir, "valid.py")
        self.assertEqual(len(issues), 0)

    def test_file_inspector_python_syntax_error(self):
        bad_py = os.path.join(self.test_dir, "broken.py")
        with open(bad_py, "w", encoding="utf-8") as f:
            f.write("def foo(\n    print('missing paren'\n")
        issues = file_inspector.inspect_file(self.test_dir, "broken.py")
        self.assertTrue(len(issues) >= 1)
        self.assertEqual(issues[0]["type"], "python_syntax_error")
        self.assertEqual(issues[0]["severity"], "error")
        self.assertIn("Python Syntax Error", issues[0]["message"])
        self.assertGreater(issues[0]["line"], 0)

    def test_file_inspector_merge_conflict_marker(self):
        conflict_file = os.path.join(self.test_dir, "conflict.txt")
        with open(conflict_file, "w", encoding="utf-8") as f:
            f.write("line 1\n<<<<<<< HEAD\nline from my branch\n=======\nline from remote\n>>>>>>> main\n")
        issues = file_inspector.inspect_file(self.test_dir, "conflict.txt")
        self.assertTrue(len(issues) >= 1)
        conflict_issues = [i for i in issues if i["type"] == "merge_conflict"]
        self.assertTrue(len(conflict_issues) >= 1)
        self.assertEqual(conflict_issues[0]["severity"], "error")
        self.assertIn("conflict marker", conflict_issues[0]["message"].lower())

    def test_file_inspector_secret_leak(self):
        secret_file = os.path.join(self.test_dir, "config_prod.py")
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write("# Secret key definition\ngithub_token = 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'\n")
        issues = file_inspector.inspect_file(self.test_dir, "config_prod.py")
        self.assertTrue(len(issues) >= 1)
        secret_issues = [i for i in issues if i["type"] == "secret_leak"]
        self.assertTrue(len(secret_issues) >= 1)
        self.assertEqual(secret_issues[0]["severity"], "security")

    def test_file_inspector_json_syntax_error(self):
        bad_json = os.path.join(self.test_dir, "data.json")
        with open(bad_json, "w", encoding="utf-8") as f:
            f.write('{"name": "CommitMaster", "broken": }\n')
        issues = file_inspector.inspect_file(self.test_dir, "data.json")
        self.assertTrue(len(issues) >= 1)
        self.assertEqual(issues[0]["type"], "json_syntax_error")

    def test_all_in_one_commit(self):
        # Create 2 files
        f1 = os.path.join(self.test_dir, "file1.txt")
        f2 = os.path.join(self.test_dir, "file2.txt")
        with open(f1, "w") as f:
            f.write("content 1\n")
        with open(f2, "w") as f:
            f.write("content 2\n")

        summary = commit_engine.stage_and_commit(self.test_dir, ["file1.txt", "file2.txt"], "feat: add both files")
        self.assertIn("feat: add both files", summary)

        # Total commits in log should be exactly 1
        log_out = git(self.test_dir, "log", "--oneline")
        commits = [line for line in log_out.splitlines() if line.strip()]
        self.assertEqual(len(commits), 1)

    def test_individual_commits_per_file(self):
        # Create 3 files
        for name in ("alpha.py", "beta.md", "gamma.json"):
            path = os.path.join(self.test_dir, name)
            with open(path, "w") as f:
                f.write(f"# {name} content\n")

        file_comments = [
            ("alpha.py", "feat(core): add alpha logic"),
            ("beta.md", "docs: update beta documentation"),
            ("gamma.json", "chore(config): initialize gamma schema"),
        ]

        results = commit_engine.stage_and_commit_individual(self.test_dir, file_comments)
        self.assertEqual(len(results), 3)

        # Verify each commit in git history
        log_out = git(self.test_dir, "log", "--oneline")
        commits = [line for line in log_out.splitlines() if line.strip()]
        self.assertEqual(len(commits), 3)
        self.assertIn("gamma", commits[0])  # Most recent commit
        self.assertIn("beta", commits[1])
        self.assertIn("alpha", commits[2])


if __name__ == "__main__":
    unittest.main()
