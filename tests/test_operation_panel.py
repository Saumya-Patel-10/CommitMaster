"""UI-level tests: the commit composer drives a real disposable repo through the operation panel.

Skipped automatically when no display is available.
"""
import os
import shutil
import subprocess
import tempfile
import time
import tkinter as tk
import unittest
from unittest import mock

from commitmaster import commit_composer, git_ops


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def make_repo(path):
    os.makedirs(path)
    subprocess.run(["git", "init", "-b", "main", path], check=True, capture_output=True)
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "T")
    with open(os.path.join(path, "README.md"), "w") as f:
        f.write("hi\n")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "init")


class FakeHost:
    def __init__(self, root, repo, files):
        self.user = {"id": 1}
        self._gd_selected_repo = repo
        self._gd_commit_mode_var = tk.StringVar(master=root, value="individual")
        self._gd_ask_push_var = tk.BooleanVar(master=root, value=False)
        self._gd_staged_vars = {}
        self._gd_changes = []
        commit_composer.ensure_state(self)
        commit_composer.sync_selection(self, [("M", f) for f in files], [])
        for f in files:
            self._gd_drafts[f] = {"summary": f"feat: update {f}", "description": ""}


class TestComposerThroughPanel(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        self.root.withdraw()
        self.tmp = tempfile.mkdtemp(prefix="cm-ui-")
        self.env = {k: os.environ.get(k) for k in ("COMMITMASTER_OPS_JOURNAL", "COMMITMASTER_PUSH_LEDGER")}
        os.environ["COMMITMASTER_OPS_JOURNAL"] = os.path.join(self.tmp, "j.json")
        os.environ["COMMITMASTER_PUSH_LEDGER"] = os.path.join(self.tmp, "l.json")
        patches = [
            mock.patch.object(commit_composer.db, "get_repo_account", return_value=None),
            mock.patch.object(commit_composer.db, "get_github_accounts", return_value=[]),
            mock.patch.object(commit_composer.db, "log_scan"),
            mock.patch.object(commit_composer.db, "log_commit"),
            mock.patch.object(commit_composer.db, "log_event"),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pump(self, until, timeout=60):
        """Run the Tk event loop; return the largest gap between loop iterations (seconds)."""
        worst, last, end = 0.0, time.monotonic(), time.monotonic() + timeout
        while time.monotonic() < end and not until():
            self.root.update()
            now = time.monotonic()
            worst = max(worst, now - last)
            last = now
            time.sleep(0.005)
        return worst

    def test_commit_shows_stages_stays_responsive_and_reports_result(self):
        repo = os.path.join(self.tmp, "repo")
        make_repo(repo)
        hook = os.path.join(repo, ".git", "hooks", "pre-commit")
        with open(hook, "w", newline="\n") as handle:
            handle.write("#!/bin/sh\nsleep 3\n")           # a slow hook: the old UI froze or stuck here
        os.chmod(hook, 0o755)
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("a\n")
        host = FakeHost(self.root, repo, ["a.txt"])
        done = []
        composer = commit_composer.CommitComposer(self.root, host, {}, on_done=lambda: done.append(1))
        composer.pack()
        composer.commit(push=False)
        self.assertTrue(composer._busy)                             # buttons lock immediately
        self.pump(lambda: composer.panel is not None, timeout=30)
        seen_stages = set()

        def watch():
            seen_stages.add(composer.panel.op.snapshot()["stage"]) if composer.panel else None
            return composer.panel is not None and composer.panel.op.finished and composer._busy is False
        worst_gap = self.pump(watch, timeout=60)
        print(f"\n[bench] max UI event-loop gap during a 3 s hook commit: {worst_gap * 1000:.0f} ms")
        self.assertLess(worst_gap, 0.25, "the Tk event loop must not block during a commit")
        self.assertIn("committing", seen_stages)
        self.assertEqual(composer.panel.op.state, git_ops.SUCCEEDED, composer.panel.op.log_text())
        self.assertEqual(git(repo, "log", "-1", "--format=%s"), "feat: update a.txt")
        self.assertIn("Local commit created", composer.panel.result.cget("text"))
        self.assertEqual(done, [1])
        self.assertEqual(composer.panel.title.cget("text"), "Done")

    def test_failed_push_is_shown_separately_from_the_local_commit(self):
        repo = os.path.join(self.tmp, "repo")
        make_repo(repo)
        git(repo, "remote", "add", "origin", "http://127.0.0.1:9/nope.git")     # nothing listens here
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("a\n")
        host = FakeHost(self.root, repo, ["a.txt"])
        composer = commit_composer.CommitComposer(self.root, host, {}, on_done=lambda: None)
        composer.pack()
        composer.commit(push=True)
        self.pump(lambda: composer.panel is not None and composer.panel.op.finished and not composer._busy, timeout=90)
        op = composer.panel.op
        self.assertEqual(op.state, git_ops.COMMITTED_NOT_PUSHED, op.log_text())
        text = composer.panel.result.cget("text")
        self.assertIn("Local commit created", text)
        self.assertIn("Not pushed", text)
        self.assertEqual(composer.panel.title.cget("text"), "Committed locally, not pushed")
        self.assertEqual(git(repo, "log", "-1", "--format=%s"), "feat: update a.txt")
        self.assertFalse(composer._busy)                       # buttons usable again, nothing stuck

    def test_rebuilt_page_reattaches_to_the_running_operation(self):
        repo = os.path.join(self.tmp, "repo")
        make_repo(repo)
        hook = os.path.join(repo, ".git", "hooks", "pre-commit")
        with open(hook, "w", newline="\n") as handle:
            handle.write("#!/bin/sh\nsleep 3\n")
        os.chmod(hook, 0o755)
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("a\n")
        host = FakeHost(self.root, repo, ["a.txt"])
        first = commit_composer.CommitComposer(self.root, host, {}, on_done=lambda: None)
        first.pack()
        first.commit(push=False)
        self.pump(lambda: first.panel is not None, timeout=30)
        first.destroy()                                         # page re-render while the commit runs
        second = commit_composer.CommitComposer(self.root, host, {}, on_done=lambda: None)
        second.pack()
        self.assertIsNotNone(second.panel)
        self.assertTrue(second._busy)                           # cannot start a duplicate
        self.pump(lambda: second.panel.op.finished and not second._busy, timeout=60)
        self.assertEqual(git(repo, "rev-list", "--count", "HEAD"), "2")


if __name__ == "__main__":
    unittest.main()
