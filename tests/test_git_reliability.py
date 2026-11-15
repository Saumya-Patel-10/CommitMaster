"""Local git reliability. Uses disposable repositories only."""
import os
import subprocess
import sys
import tempfile
import unittest

from commitmaster import git_safety
from commitmaster.commit_engine import GitError


def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)


def _init(path):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", path], check=True, capture_output=True)
    _git(path, "config", "user.email", "git-test@example.com")
    _git(path, "config", "user.name", "Git Test")


class TestGitReliability(unittest.TestCase):
    def test_commit_refuses_without_confirmation_and_does_not_add_extra_files(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = os.path.join(directory, "repo")
            _init(repo)
            open(os.path.join(repo, "keep.txt"), "w", encoding="utf-8").write("one\n")
            _git(repo, "add", "keep.txt")
            _git(repo, "commit", "-m", "init")
            open(os.path.join(repo, "wanted.txt"), "w", encoding="utf-8").write("wanted\n")
            open(os.path.join(repo, "extra.txt"), "w", encoding="utf-8").write("extra\n")
            with self.assertRaises(GitError):
                git_safety.commit_authorized(repo, ["wanted.txt"], "add wanted", confirmed=False)
            summary = git_safety.commit_authorized(repo, ["wanted.txt"], "add wanted", confirmed=True)
            self.assertIn("add wanted", summary)
            status = subprocess.run(["git", "-C", repo, "status", "--porcelain"], check=True, capture_output=True, text=True)
            self.assertIn("extra.txt", status.stdout)
            self.assertNotIn("wanted.txt", status.stdout)

    def test_commit_refuses_a_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = os.path.join(directory, "repo")
            _init(repo)
            os.makedirs(os.path.join(repo, "nested"))
            open(os.path.join(repo, "nested", "a.txt"), "w", encoding="utf-8").write("a\n")
            with self.assertRaises(GitError):
                git_safety.commit_authorized(repo, ["nested"], "add nested", confirmed=True)

    def test_push_success_then_no_remote_update_and_no_force(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = os.path.join(directory, "ledger.json")
            os.environ["COMMITMASTER_PUSH_LEDGER"] = ledger
            origin = os.path.join(directory, "origin.git")
            subprocess.run(["git", "init", "--bare", origin], check=True, capture_output=True)
            repo = os.path.join(directory, "repo")
            _init(repo)
            open(os.path.join(repo, "file.txt"), "w", encoding="utf-8").write("v1\n")
            git_safety.commit_authorized(repo, ["file.txt"], "first", confirmed=True)
            _git(repo, "remote", "add", "origin", origin)
            _git(repo, "branch", "-M", "main")
            first = git_safety.push_authorized(repo, "origin", "main", confirmed=True, remote_url=origin)
            self.assertEqual(first.outcome, "success", first.message)
            second = git_safety.push_authorized(repo, "origin", "main", confirmed=True, remote_url=origin)
            self.assertEqual(second.outcome, "no_remote_update", second.message)
            with self.assertRaises(GitError):
                git_safety._run(["git", "-C", repo, "push", "--force", "origin", "main"])
            refused = git_safety.push_authorized(repo, "origin", "main", confirmed=False, remote_url=origin)
            self.assertEqual(refused.outcome, "failed")

    def test_uncertain_push_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = os.path.join(directory, "ledger.json")
            os.environ["COMMITMASTER_PUSH_LEDGER"] = ledger
            repo = os.path.join(directory, "repo")
            _init(repo)
            open(os.path.join(repo, "file.txt"), "w", encoding="utf-8").write("v1\n")
            git_safety.commit_authorized(repo, ["file.txt"], "first", confirmed=True)
            classified = git_safety.classify_push_result(1, "", "RPC failed; the remote end hung up unexpectedly", "abc", None)
            self.assertEqual(classified.outcome, "uncertain")
            git_safety.mark_uncertain(repo, "main", classified.message)
            blocked = git_safety.push_authorized(repo, "origin", "main", confirmed=True, remote_url="/tmp/does-not-matter")
            self.assertEqual(blocked.outcome, "uncertain")
            self.assertIn("Not retrying", blocked.message)

    def test_demo_cannot_push_to_github(self):
        script = (
            "from commitmaster import product, git_safety\n"
            "product.activate('demo')\n"
            "blocked = git_safety._demo_blocks_remote('https://github.com/example/repo.git')\n"
            "local = git_safety._demo_blocks_remote('/tmp/local.git')\n"
            "assert blocked and local is None\n"
            "print('blocked')\n"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.dirname(os.path.dirname(__file__))
        result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("blocked", result.stdout)

    def test_token_is_not_placed_on_the_command_builder(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "commitmaster", "commit_engine.py"), encoding="utf-8").read()
        self.assertNotIn("{token}@", source)
        with tempfile.TemporaryDirectory() as directory:
            repo = os.path.join(directory, "repo")
            _init(repo)
            from commitmaster import commit_engine
            with self.assertRaises(GitError):
                commit_engine.git(repo, "commit", "--no-verify", "-m", "bypass")


if __name__ == "__main__":
    unittest.main()
