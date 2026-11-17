"""git_fast must agree with real git, and must say "don't know" instead of guessing."""
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from commitmaster import commit_engine as ce
from commitmaster import git_fast


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if check and result.returncode != 0:
        raise AssertionError(f"git {args}: {result.stderr}")
    return result.stdout.strip()


def make_repo(path, branch="main", commit=True):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-b", branch, path], check=True, capture_output=True)
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "T")
    git(path, "config", "commit.gpgsign", "false")
    if commit:
        from pathlib import Path
        (Path(path) / "a.txt").write_text("a\n", encoding="utf-8")
        git(path, "add", "a.txt")
        git(path, "commit", "-m", "one")
    return path


def real_branch(repo):
    result = subprocess.run(["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


class TestHeadBranch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def check(self, repo):
        self.assertEqual(git_fast.head_branch(repo), real_branch(repo), repo)
        self.assertEqual(ce.current_branch(repo), real_branch(repo), repo)

    def test_plain_and_slashed_branch_names(self):
        repo = make_repo(os.path.join(self.tmp, "r"))
        self.check(repo)
        git(repo, "checkout", "-b", "feature/deep/name")
        self.check(repo)
        self.assertEqual(git_fast.head_branch(repo), "feature/deep/name")

    def test_detached_head(self):
        repo = make_repo(os.path.join(self.tmp, "r"))
        git(repo, "checkout", "--detach")
        self.assertEqual(git_fast.head_branch(repo), "HEAD")
        self.check(repo)

    def test_unborn_branch_matches_the_app_convention(self):
        repo = make_repo(os.path.join(self.tmp, "r"), commit=False)
        self.assertEqual(git_fast.head_branch(repo), "unknown")
        self.check(repo)

    def test_packed_refs(self):
        repo = make_repo(os.path.join(self.tmp, "r"))
        git(repo, "checkout", "-b", "packed-branch")
        git(repo, "pack-refs", "--all")
        self.assertFalse(os.path.exists(os.path.join(repo, ".git", "refs", "heads", "packed-branch")))
        self.assertEqual(git_fast.head_branch(repo), "packed-branch")
        self.check(repo)

    def test_subdirectory_and_linked_worktree(self):
        repo = make_repo(os.path.join(self.tmp, "r"))
        sub = os.path.join(repo, "sub", "dir")
        os.makedirs(sub)
        self.check(sub)
        wt = os.path.join(self.tmp, "wt")
        git(repo, "worktree", "add", "-b", "wt-branch", wt)
        self.assertEqual(git_fast.head_branch(wt), "wt-branch")
        self.check(wt)
        self.check(repo)   # main worktree unaffected

    def test_not_a_repository_asks_git(self):
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain)
        self.assertIsNone(git_fast.head_branch(plain))
        self.assertEqual(ce.current_branch(plain), "unknown")

    def test_reftable_and_garbage_are_not_guessed(self):
        repo = make_repo(os.path.join(self.tmp, "r"))
        os.makedirs(os.path.join(repo, ".git", "reftable"))
        self.assertIsNone(git_fast.head_branch(repo))
        self.assertIsNone(git_fast.ref_exists(repo, "refs/heads/main"))
        os.rmdir(os.path.join(repo, ".git", "reftable"))
        with open(os.path.join(repo, ".git", "HEAD"), "w") as handle:
            handle.write("something odd\n")
        self.assertIsNone(git_fast.head_branch(repo))

    def test_git_dir_environment_defers_to_git(self):
        repo = make_repo(os.path.join(self.tmp, "r"))
        with mock.patch.dict(os.environ, {"GIT_DIR": os.path.join(repo, ".git")}):
            self.assertIsNone(git_fast.head_branch(repo))

    def test_current_branch_spawns_no_process(self):
        repo = make_repo(os.path.join(self.tmp, "r"))
        with mock.patch.object(ce, "git", side_effect=AssertionError("spawned git")):
            self.assertEqual(ce.current_branch(repo), "main")


class TestRefExists(unittest.TestCase):
    def test_loose_packed_and_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote = make_repo(os.path.join(tmp, "remote"))
            clone = os.path.join(tmp, "clone")
            subprocess.run(["git", "clone", remote, clone], check=True, capture_output=True)
            ref = "refs/remotes/origin/main"
            self.assertTrue(git_fast.ref_exists(clone, ref))
            git(clone, "pack-refs", "--all")
            self.assertTrue(git_fast.ref_exists(clone, ref))
            self.assertFalse(git_fast.ref_exists(clone, "refs/remotes/origin/nope"))
            # Prefix of a real ref is not a match.
            self.assertFalse(git_fast.ref_exists(clone, "refs/remotes/origin/ma"))
            self.assertIsNone(git_fast.ref_exists(clone, "origin/main"))


class TestUnpushedCommits(unittest.TestCase):
    def test_same_answers_and_no_doomed_git_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote = make_repo(os.path.join(tmp, "remote"))
            clone = os.path.join(tmp, "clone")
            subprocess.run(["git", "clone", remote, clone], check=True, capture_output=True)
            git(clone, "config", "user.email", "t@example.com")
            git(clone, "config", "user.name", "T")
            git(clone, "config", "commit.gpgsign", "false")
            self.assertEqual(ce.get_unpushed_commits(clone), [])
            with open(os.path.join(clone, "b.txt"), "w") as handle:
                handle.write("b\n")
            git(clone, "add", "b.txt")
            git(clone, "commit", "-m", "two")
            self.assertEqual([c["message"] for c in ce.get_unpushed_commits(clone)], ["two"])

            # No such remote branch: previous behaviour was a failing `git log` plus a fallback to the last 5.
            git(clone, "checkout", "-b", "local-only")
            calls = []
            real_git = ce.git

            def spy(repo, *args, **kw):
                calls.append(args)
                return real_git(repo, *args, **kw)

            with mock.patch.object(ce, "git", side_effect=spy):
                recent = ce.get_unpushed_commits(clone)
            self.assertEqual([c["message"] for c in recent], ["two", "one"])
            self.assertEqual(len(calls), 1, calls)             # only the fallback `log -5`
            self.assertNotIn("origin/local-only..local-only", " ".join(" ".join(a) for a in calls))


if __name__ == "__main__":
    unittest.main()
