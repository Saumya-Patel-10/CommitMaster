"""Git operation manager tests. Disposable repositories and local test remotes only.

Nothing here touches a real GitHub remote or the user's repositories. The HTTP
remote is a local server that runs the real ``git http-backend`` and enforces
Basic auth, so the token/askpass path is exercised end to end.
"""
import base64
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from commitmaster import git_ops, git_safety
from commitmaster.git_runner import RepoBusyError, RepoLock, run_process

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "ghp_TESTTOKEN_0123456789abcdef"
USER = "tester"


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if check and r.returncode != 0:
        raise AssertionError(f"git {args} failed: {r.stderr}")
    return r.stdout.strip()


def write(repo, name, text="x\n"):
    path = os.path.join(repo, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def init_repo(path, with_commit=True):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", path], check=True, capture_output=True)
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "Tester")
    git(path, "config", "commit.gpgsign", "false")
    if with_commit:
        write(path, "README.md", "hello\n")
        git(path, "add", "README.md")
        git(path, "commit", "-m", "init")
    return path


def bare_remote(path):
    subprocess.run(["git", "init", "--bare", "-b", "main", path], check=True, capture_output=True)
    return path


def push_fn_for(repo, remote, **extra):
    def push_fn(cancel=None, on_stage=None, on_line=None):
        return git_safety.push_authorized(
            repo, remote, "main", confirmed=True, remote_url=remote, remote_name="origin",
            cancel=cancel, on_stage=on_stage, on_line=on_line, **extra)
    return push_fn


def run_op(repo, **kwargs):
    op = git_ops.start_operation(
        "commit_push", repo, lambda o: git_ops.run_commit_and_push(o, repo, **kwargs),
        secrets=[TOKEN])
    assert op.wait(120), "operation did not finish within 120s"
    return op


# ── local HTTP git remote (real git http-backend, Basic auth, fault injection) ─

class GitHttpServer:
    def __init__(self, root, reject=False, stall_receive=0.0):
        self.root, self.reject, self.stall_receive = root, reject, stall_receive
        self.stopping = threading.Event()
        self.auth_headers = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *a):
                pass

            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                auth = self.headers.get("Authorization", "")
                outer.auth_headers.append(auth)
                expected = "Basic " + base64.b64encode(f"{USER}:{TOKEN}".encode()).decode()
                if outer.reject or auth != expected:
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="test"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                path, _, query = self.path.partition("?")
                if outer.stall_receive and self.command == "POST" and "receive-pack" in path:
                    end = time.time() + outer.stall_receive
                    while time.time() < end and not outer.stopping.is_set():
                        time.sleep(0.1)
                    return                                   # drop the connection, never run the backend
                env = dict(os.environ, GIT_PROJECT_ROOT=outer.root, GIT_HTTP_EXPORT_ALL="1",
                           REQUEST_METHOD=self.command, PATH_INFO=path, QUERY_STRING=query,
                           CONTENT_TYPE=self.headers.get("Content-Type", ""), CONTENT_LENGTH=str(len(body)),
                           REMOTE_USER=USER, REMOTE_ADDR="127.0.0.1",
                           HTTP_CONTENT_ENCODING=self.headers.get("Content-Encoding", ""),
                           GIT_PROTOCOL=self.headers.get("Git-Protocol", ""))
                proc = subprocess.run(["git", "http-backend"], input=body, env=env, capture_output=True)
                head, _, payload = proc.stdout.partition(b"\r\n\r\n")
                status, headers = "200 OK", []
                for line in head.decode("latin-1").split("\r\n"):
                    if line.lower().startswith("status:"):
                        status = line.split(":", 1)[1].strip()
                    elif ":" in line:
                        headers.append(tuple(x.strip() for x in line.split(":", 1)))
                self.send_response(int(status.split()[0]))
                for k, v in headers:
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = _serve

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, name="origin.git"):
        return f"http://127.0.0.1:{self.port}/{name}"

    def close(self):
        self.stopping.set()
        self.httpd.shutdown()
        self.httpd.server_close()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cm-test-")
        self._env = {k: os.environ.get(k) for k in ("COMMITMASTER_PUSH_LEDGER", "COMMITMASTER_OPS_JOURNAL")}
        os.environ["COMMITMASTER_PUSH_LEDGER"] = os.path.join(self.tmp, "ledger.json")
        os.environ["COMMITMASTER_OPS_JOURNAL"] = os.path.join(self.tmp, "journal.json")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def repo_with_remote(self, remote_name="origin.git"):
        remote = bare_remote(os.path.join(self.tmp, remote_name))
        repo = init_repo(os.path.join(self.tmp, "repo"))
        git(repo, "remote", "add", "origin", remote)
        git(repo, "push", "origin", "main")
        return repo, remote


class TestCommitAndPush(Base):
    def test_normal_commit_only(self):
        repo = init_repo(os.path.join(self.tmp, "repo"))
        write(repo, "a.txt")
        op = run_op(repo, files=["a.txt"], message="feat: add a", push=False)
        self.assertEqual(op.state, git_ops.SUCCEEDED, op.log_text())
        self.assertEqual(op.commit_state, "done")
        self.assertEqual(op.push_state, "not_requested")
        self.assertEqual(git(repo, "log", "-1", "--format=%s"), "feat: add a")
        self.assertEqual(git(repo, "status", "--porcelain"), "")

    def test_normal_commit_and_push_updates_tracking_and_verifies(self):
        repo, remote = self.repo_with_remote()
        write(repo, "a.txt")
        op = run_op(repo, files=["a.txt"], message="feat: add a", push=True, push_fn=push_fn_for(repo, remote))
        self.assertEqual(op.state, git_ops.SUCCEEDED, op.log_text())
        self.assertEqual(op.push_state, "success")
        self.assertEqual(git(repo, "rev-parse", "HEAD"), git(remote, "rev-parse", "refs/heads/main"))
        self.assertEqual(op.final_state.get("ahead"), 0)
        self.assertEqual(op.final_state.get("behind"), 0)

    def test_stage_sequence_is_reported(self):
        repo, remote = self.repo_with_remote()
        write(repo, "a.txt")
        op = run_op(repo, files=["a.txt"], message="m", push=True, push_fn=push_fn_for(repo, remote))
        text = op.log_text()
        order = [text.index(label) for label in (
            "Preparing repository", "Checking changes", "Staging selected files", "Creating commit",
            "Authenticating", "Connecting to GitHub", "Uploading changes", "Verifying remote state")]
        self.assertEqual(order, sorted(order), text)

    def test_existing_commit_push_only(self):
        repo, remote = self.repo_with_remote()
        write(repo, "b.txt")
        git(repo, "add", "b.txt")
        git(repo, "commit", "-m", "local only")
        before = git(repo, "rev-parse", "HEAD")
        op = git_ops.start_operation("push", repo, lambda o: git_ops.run_push_only(o, repo, push_fn=push_fn_for(repo, remote)))
        self.assertTrue(op.wait(60))
        self.assertEqual(op.state, git_ops.SUCCEEDED, op.log_text())
        self.assertEqual(op.push_state, "success", op.log_text())
        self.assertEqual(git(remote, "rev-parse", "refs/heads/main"), before)
        self.assertEqual(op.final_state.get("ahead"), 0)

    def test_push_only_on_detached_head_is_refused_without_touching_anything(self):
        repo, remote = self.repo_with_remote()
        git(repo, "checkout", "--detach")
        op = git_ops.start_operation("push", repo, lambda o: git_ops.run_push_only(o, repo, push_fn=push_fn_for(repo, remote)))
        self.assertTrue(op.wait(60))
        self.assertEqual(op.push_state, "failed")
        self.assertIn("detached", op.error.lower())

    def test_multiple_files_only_selected_are_committed(self):
        repo, remote = self.repo_with_remote()
        for name in ("one.txt", "two.txt", "three.txt", "sub/four.txt"):
            write(repo, name)
        op = run_op(repo, files=["one.txt", "two.txt", "sub/four.txt"], message="feat: several",
                    push=True, push_fn=push_fn_for(repo, remote))
        self.assertEqual(op.state, git_ops.SUCCEEDED, op.log_text())
        committed = git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertEqual(sorted(committed), ["one.txt", "sub/four.txt", "two.txt"])
        self.assertIn("three.txt", git(repo, "status", "--porcelain"))

    def test_individual_commits_one_per_file(self):
        repo = init_repo(os.path.join(self.tmp, "repo"))
        write(repo, "a.txt"); write(repo, "b.txt")
        op = run_op(repo, files=["a.txt", "b.txt"], pairs=[("a.txt", "feat: a"), ("b.txt", "feat: b")], push=False)
        self.assertEqual(op.state, git_ops.SUCCEEDED, op.log_text())
        self.assertEqual(git(repo, "rev-list", "--count", "HEAD"), "3")

    def test_second_attempt_reports_already_committed(self):
        repo = init_repo(os.path.join(self.tmp, "repo"))
        write(repo, "a.txt")
        self.assertEqual(run_op(repo, files=["a.txt"], message="m", push=False).state, git_ops.SUCCEEDED)
        again = run_op(repo, files=["a.txt"], message="m", push=False)
        self.assertEqual(again.state, git_ops.FAILED)
        self.assertIn("already be committed", again.error)
        self.assertEqual(git(repo, "rev-list", "--count", "HEAD"), "2")

    def test_large_repository(self):
        repo, remote = self.repo_with_remote()
        for i in range(4000):
            write(repo, f"src/pkg{i // 100}/mod{i}.py", f"VALUE = {i}\n")
        for attempt in range(6):           # fixture only: Windows real-time scanners can lock fresh files
            try:
                git(repo, "add", "-A")
                break
            except AssertionError:
                if attempt == 5:
                    raise
                time.sleep(2 + attempt * 2)
        git(repo, "commit", "-m", "bulk")
        git(repo, "push", "origin", "main")
        write(repo, "src/pkg0/mod0.py", "VALUE = 'changed'\n")
        write(repo, "src/pkg1/mod150.py", "VALUE = 'changed'\n")
        started = time.monotonic()
        op = run_op(repo, files=["src/pkg0/mod0.py", "src/pkg1/mod150.py"], message="chore: tweak",
                    push=True, push_fn=push_fn_for(repo, remote))
        took = time.monotonic() - started
        print(f"\n[bench] 4001-file repo, 2-file commit+push: {took:.2f}s")
        self.assertEqual(op.state, git_ops.SUCCEEDED, op.log_text())
        self.assertLess(took, 30)


class TestFailureModes(Base):
    def test_non_fast_forward_rejection_keeps_local_commit_and_never_forces(self):
        repo, remote = self.repo_with_remote()
        other = os.path.join(self.tmp, "other")
        subprocess.run(["git", "clone", remote, other], check=True, capture_output=True)
        git(other, "config", "user.email", "o@example.com"); git(other, "config", "user.name", "O")
        write(other, "remote_change.txt")
        git(other, "add", "-A"); git(other, "commit", "-m", "remote work"); git(other, "push", "origin", "main")
        remote_head = git(remote, "rev-parse", "refs/heads/main")
        write(repo, "mine.txt")
        op = run_op(repo, files=["mine.txt"], message="mine", push=True, push_fn=push_fn_for(repo, remote))
        self.assertEqual(op.state, git_ops.COMMITTED_NOT_PUSHED)
        self.assertEqual(op.commit_state, "done")
        self.assertEqual(op.push_state, "failed")
        self.assertEqual(op.push_result.reason, "non_fast_forward")
        self.assertEqual(git(remote, "rev-parse", "refs/heads/main"), remote_head)      # remote untouched
        self.assertEqual(git(repo, "log", "-1", "--format=%s"), "mine")                # local work kept

    def test_unresolved_merge_conflict_blocks_commit(self):
        repo = init_repo(os.path.join(self.tmp, "repo"))
        git(repo, "checkout", "-b", "feature")
        write(repo, "c.txt", "feature\n"); git(repo, "add", "c.txt"); git(repo, "commit", "-m", "f")
        git(repo, "checkout", "main")
        write(repo, "c.txt", "main\n"); git(repo, "add", "c.txt"); git(repo, "commit", "-m", "m")
        subprocess.run(["git", "-C", repo, "merge", "feature"], capture_output=True)       # conflicts
        head = git(repo, "rev-parse", "HEAD")
        write(repo, "other.txt")
        op = run_op(repo, files=["other.txt"], message="x", push=False)
        self.assertEqual(op.state, git_ops.FAILED)
        self.assertRegex(op.error, "merge")
        self.assertEqual(git(repo, "rev-parse", "HEAD"), head)
        self.assertTrue(os.path.exists(os.path.join(repo, ".git", "MERGE_HEAD")))         # untouched

    def test_detached_head_commit_ok_push_refused(self):
        repo, remote = self.repo_with_remote()
        git(repo, "checkout", "--detach")
        write(repo, "d.txt")
        op = git_ops.start_operation("commit_push", repo, lambda o: git_ops.run_commit_and_push(
            o, repo, files=["d.txt"], message="detached work", push=True,
            push_fn=lambda cancel=None, on_stage=None, on_line=None: git_safety.push_authorized(
                repo, remote, git_safety.head_branch(repo) or "HEAD", confirmed=True, remote_url=remote)))
        self.assertTrue(op.wait(60))
        self.assertEqual(op.state, git_ops.COMMITTED_NOT_PUSHED, op.log_text())
        self.assertEqual(op.push_result.reason, "detached_head")
        self.assertEqual(git(repo, "log", "-1", "--format=%s"), "detached work")

    def test_missing_upstream_is_set_after_verified_push(self):
        repo, remote = self.repo_with_remote()
        git(repo, "checkout", "-b", "main2")            # no upstream for main2
        git(repo, "branch", "-D", "main", check=False)
        write(repo, "n.txt")
        res_holder = {}

        def push_fn(cancel=None, on_stage=None, on_line=None):
            res = git_safety.push_authorized(repo, remote, "main2", confirmed=True, remote_url=remote,
                                             remote_name="origin", cancel=cancel, on_stage=on_stage, on_line=on_line)
            res_holder["r"] = res
            return res
        op = run_op(repo, files=["n.txt"], message="new branch work", push=True, push_fn=push_fn)
        self.assertEqual(op.push_state, "success", op.log_text())
        self.assertEqual(git(repo, "rev-parse", "--abbrev-ref", "main2@{upstream}"), "origin/main2")
        self.assertEqual(op.final_state.get("ahead"), 0)

    def test_network_unreachable_fails_fast_with_actionable_reason(self):
        repo, _ = self.repo_with_remote()
        write(repo, "a.txt")
        dead = "http://127.0.0.1:9/origin.git"                       # discard port, nothing listens
        started = time.monotonic()
        op = run_op(repo, files=["a.txt"], message="m", push=True, push_fn=push_fn_for(repo, dead))
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(op.state, git_ops.COMMITTED_NOT_PUSHED)
        self.assertEqual(op.push_result.outcome, "failed")
        self.assertEqual(op.push_result.reason, "network")
        self.assertIn("saved locally", op.push_result.message)

    def test_authentication_failure_is_detected_and_work_preserved(self):
        repo, _ = self.repo_with_remote()
        remote = bare_remote(os.path.join(self.tmp, "http-origin.git"))
        server = GitHttpServer(self.tmp, reject=True)
        self.addCleanup(server.close)
        write(repo, "a.txt")
        op = run_op(repo, files=["a.txt"], message="m", push=True,
                    push_fn=push_fn_for(repo, server.url("http-origin.git"), token=TOKEN, username=USER))
        self.assertEqual(op.state, git_ops.COMMITTED_NOT_PUSHED, op.log_text())
        self.assertEqual(op.push_result.reason, "auth")
        self.assertNotIn(TOKEN, op.log_text())
        self.assertNotIn(TOKEN, op.push_result.message)
        self.assertEqual(git(repo, "log", "-1", "--format=%s"), "m")

    def test_token_push_over_http_works_on_this_platform_and_never_leaks(self):
        """Regression: os.fchmod crashed every token push on Windows."""
        askpass_before = set(f for f in os.listdir(tempfile.gettempdir()) if f.startswith("cm-askpass-"))
        repo, _ = self.repo_with_remote()
        remote = bare_remote(os.path.join(self.tmp, "http-origin.git"))
        git(remote, "config", "http.receivepack", "true")
        server = GitHttpServer(self.tmp)
        self.addCleanup(server.close)
        url = server.url("http-origin.git")
        git(repo, "remote", "add", "web", url)
        write(repo, "a.txt")
        op = run_op(repo, files=["a.txt"], message="over http", push=True,
                    push_fn=lambda cancel=None, on_stage=None, on_line=None: git_safety.push_authorized(
                        repo, url, "main", confirmed=True, remote_url=url, token=TOKEN, username=USER,
                        remote_name="web", cancel=cancel, on_stage=on_stage, on_line=on_line))
        self.assertEqual(op.state, git_ops.SUCCEEDED, op.log_text())
        self.assertEqual(git(repo, "rev-parse", "HEAD"), git(remote, "rev-parse", "refs/heads/main"))
        self.assertNotIn(TOKEN, op.log_text())
        self.assertEqual(git(repo, "rev-parse", "refs/remotes/web/main"), git(repo, "rev-parse", "HEAD"))
        self.assertTrue(any(h.startswith("Basic ") for h in server.auth_headers))
        leaked = set(f for f in os.listdir(tempfile.gettempdir()) if f.startswith("cm-askpass-")) - askpass_before
        self.assertEqual(leaked, set(), "askpass helper must be deleted")
        self.assertNotIn(TOKEN, git(repo, "config", "--list", check=False))

    def test_cancel_during_upload_kills_git_and_keeps_local_commit(self):
        import psutil
        repo, _ = self.repo_with_remote()
        remote = bare_remote(os.path.join(self.tmp, "http-origin.git"))
        git(remote, "config", "http.receivepack", "true")
        server = GitHttpServer(self.tmp, stall_receive=60)
        self.addCleanup(server.close)
        url = server.url("http-origin.git")
        write(repo, "a.txt")
        op = git_ops.start_operation("commit_push", repo, lambda o: git_ops.run_commit_and_push(
            o, repo, files=["a.txt"], message="to be cancelled", push=True,
            push_fn=lambda cancel=None, on_stage=None, on_line=None: git_safety.push_authorized(
                repo, url, "main", confirmed=True, remote_url=url, token=TOKEN, username=USER,
                remote_name="origin", cancel=cancel, on_stage=on_stage, on_line=on_line)))
        deadline = time.time() + 30
        while op.snapshot()["stage"] != "uploading" and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(op.snapshot()["stage"], "uploading", op.log_text())
        time.sleep(1.0)
        t0 = time.monotonic()
        op.cancel()
        self.assertTrue(op.wait(30), "cancel did not stop the operation")
        self.assertLess(time.monotonic() - t0, 15)
        self.assertEqual(op.state, git_ops.COMMITTED_NOT_PUSHED, op.log_text())
        self.assertEqual(op.push_state, "cancelled")
        self.assertEqual(git(repo, "log", "-1", "--format=%s"), "to be cancelled")
        time.sleep(0.5)
        leftovers = [p.name() for p in psutil.Process().children(recursive=True) if "git" in p.name().lower()]
        self.assertEqual(leftovers, [])

    def test_stalled_push_hits_idle_timeout_and_is_verified_against_remote(self):
        repo, _ = self.repo_with_remote()
        remote = bare_remote(os.path.join(self.tmp, "http-origin.git"))
        git(remote, "config", "http.receivepack", "true")
        server = GitHttpServer(self.tmp, stall_receive=60)
        self.addCleanup(server.close)
        url = server.url("http-origin.git")
        write(repo, "a.txt"); git(repo, "add", "a.txt"); git(repo, "commit", "-m", "x")
        started = time.monotonic()
        res = git_safety.push_authorized(repo, url, "main", confirmed=True, remote_url=url, token=TOKEN,
                                         username=USER, idle_timeout=3, timeout=30)
        self.assertLess(time.monotonic() - started, 25)
        self.assertEqual(res.outcome, "failed", res.message)       # remote verified: it did NOT get the commit
        self.assertEqual(res.reason, "stalled")
        self.assertFalse(git_safety.has_uncertain(repo, "main"))

    def test_cancel_during_commit_hook_kills_process_tree(self):
        import psutil
        repo = init_repo(os.path.join(self.tmp, "repo"))
        hook = os.path.join(repo, ".git", "hooks", "pre-commit")
        with open(hook, "w", newline="\n") as handle:
            handle.write("#!/bin/sh\nsleep 120\n")
        os.chmod(hook, 0o755)
        write(repo, "a.txt")
        head = git(repo, "rev-parse", "HEAD")
        op = git_ops.start_operation("commit", repo, lambda o: git_ops.run_commit_and_push(
            o, repo, files=["a.txt"], message="blocked by hook", push=False))
        deadline = time.time() + 30
        while op.snapshot()["stage"] != "committing" and time.time() < deadline:
            time.sleep(0.05)
        time.sleep(1.0)
        t0 = time.monotonic()
        op.cancel()
        self.assertTrue(op.wait(30))
        self.assertLess(time.monotonic() - t0, 15)
        self.assertEqual(op.state, git_ops.CANCELLED, op.log_text())
        self.assertEqual(git(repo, "rev-parse", "HEAD"), head)
        self.assertIn("a.txt", git(repo, "status", "--porcelain"))       # work not lost
        time.sleep(0.5)
        self.assertEqual([p.name() for p in psutil.Process().children(recursive=True)], [])

    def test_hook_waiting_for_stdin_cannot_hang_the_commit(self):
        repo = init_repo(os.path.join(self.tmp, "repo"))
        hook = os.path.join(repo, ".git", "hooks", "pre-commit")
        with open(hook, "w", newline="\n") as handle:
            handle.write("#!/bin/sh\nread answer\nexit 0\n")
        os.chmod(hook, 0o755)
        write(repo, "a.txt")
        started = time.monotonic()
        op = run_op(repo, files=["a.txt"], message="hook reads stdin", push=False)
        self.assertEqual(op.state, git_ops.SUCCEEDED, op.log_text())
        self.assertLess(time.monotonic() - started, 20)

    def test_failing_hook_reports_failure_and_keeps_changes(self):
        repo = init_repo(os.path.join(self.tmp, "repo"))
        hook = os.path.join(repo, ".git", "hooks", "pre-commit")
        with open(hook, "w", newline="\n") as handle:
            handle.write("#!/bin/sh\necho 'lint failed' >&2\nexit 1\n")
        os.chmod(hook, 0o755)
        write(repo, "a.txt")
        op = run_op(repo, files=["a.txt"], message="m", push=False)
        self.assertEqual(op.state, git_ops.FAILED)
        self.assertIn("lint failed", op.error)
        self.assertIn("a.txt", git(repo, "status", "--porcelain"))


class TestConcurrencyAndRecovery(Base):
    def test_repeated_clicks_start_one_operation(self):
        repo = init_repo(os.path.join(self.tmp, "repo"))
        hook = os.path.join(repo, ".git", "hooks", "pre-commit")
        with open(hook, "w", newline="\n") as handle:
            handle.write("#!/bin/sh\nsleep 2\n")
        os.chmod(hook, 0o755)
        write(repo, "a.txt")
        first = git_ops.start_operation("commit", repo, lambda o: git_ops.run_commit_and_push(
            o, repo, files=["a.txt"], message="once", push=False))
        rejected = 0
        for _ in range(5):
            try:
                git_ops.start_operation("commit", repo, lambda o: None)
            except git_ops.OperationInProgress:
                rejected += 1
        self.assertEqual(rejected, 5)
        self.assertTrue(first.wait(60))
        self.assertEqual(first.state, git_ops.SUCCEEDED, first.log_text())
        self.assertEqual(git(repo, "rev-list", "--count", "HEAD"), "2")     # exactly one new commit

    def test_concurrent_commits_are_serialised_not_corrupted(self):
        """FINDING-GIT-01 from the audit: 5 simultaneous commits used to crash on refs/heads lock."""
        repo = init_repo(os.path.join(self.tmp, "repo"))
        for i in range(5):
            write(repo, f"f{i}.txt", f"{i}\n")
        errors = []

        def work(i):
            try:
                git_safety.commit_authorized(repo, [f"f{i}.txt"], f"commit {i}", confirmed=True)
            except Exception as exc:                  # noqa: BLE001
                errors.append(repr(exc))
        threads = [threading.Thread(target=work, args=(i,)) for i in range(5)]
        [t.start() for t in threads]
        [t.join(120) for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(git(repo, "rev-list", "--count", "HEAD"), "6")
        self.assertEqual(git(repo, "fsck", "--no-progress", check=False) is not None, True)

    def test_lock_held_by_another_process_gives_clear_busy_error(self):
        repo = init_repo(os.path.join(self.tmp, "repo"))
        script = (
            "import sys, time\n"
            "from commitmaster.git_runner import RepoLock\n"
            "l = RepoLock(sys.argv[1], owner='other-process'); l.acquire(); print('held', flush=True); time.sleep(30)\n"
        )
        child = subprocess.Popen([sys.executable, "-c", script, repo], cwd=ROOT, stdout=subprocess.PIPE, text=True,
                                 env=dict(os.environ, PYTHONPATH=ROOT))
        try:
            self.assertEqual(child.stdout.readline().strip(), "held")
            write(repo, "a.txt")
            op = run_op(repo, files=["a.txt"], message="m", push=False)
            self.assertEqual(op.state, git_ops.FAILED)
            self.assertIn("another commitmaster process", op.error.lower())
            with self.assertRaises(RepoBusyError):
                RepoLock(repo, timeout=0.2).acquire()
        finally:
            child.kill(); child.wait()
        with RepoLock(repo, timeout=5):                    # released by the OS when the process died
            pass

    def test_runner_crash_still_reaches_terminal_state(self):
        """The original bug: an exception on the worker thread left the UI on 'Committing...' forever."""
        repo = init_repo(os.path.join(self.tmp, "repo"))

        def boom(op):
            raise AttributeError("module 'os' has no attribute 'fchmod'")
        op = git_ops.start_operation("commit_push", repo, boom)
        self.assertTrue(op.wait(10))
        self.assertEqual(op.state, git_ops.FAILED)
        self.assertIn("fchmod", op.error)
        self.assertIsNone(git_ops.active_operation(repo))

    def test_push_function_crash_keeps_commit_and_terminates(self):
        repo, _ = self.repo_with_remote()
        write(repo, "a.txt")

        def bad_push(cancel=None, on_stage=None, on_line=None):
            raise AttributeError("module 'os' has no attribute 'fchmod'")
        op = run_op(repo, files=["a.txt"], message="m", push=True, push_fn=bad_push)
        self.assertEqual(op.state, git_ops.COMMITTED_NOT_PUSHED)
        self.assertEqual(op.commit_state, "done")
        self.assertEqual(op.push_state, "failed")

    def test_restart_during_operation_is_recovered_and_lock_released(self):
        repo = init_repo(os.path.join(self.tmp, "repo"))
        hook = os.path.join(repo, ".git", "hooks", "pre-commit")
        with open(hook, "w", newline="\n") as handle:
            handle.write("#!/bin/sh\nsleep 120\n")
        os.chmod(hook, 0o755)
        write(repo, "a.txt")
        head = git(repo, "rev-parse", "HEAD")
        script = (
            "import sys, time\n"
            "from commitmaster import git_ops\n"
            "repo = sys.argv[1]\n"
            "op = git_ops.start_operation('commit', repo, lambda o: git_ops.run_commit_and_push(o, repo, files=['a.txt'], message='m', push=False))\n"
            "time.sleep(120)\n"
        )
        child = subprocess.Popen([sys.executable, "-c", script, repo], cwd=ROOT, env=dict(os.environ, PYTHONPATH=ROOT),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 40
            while time.time() < deadline:
                data = git_ops._journal_read()
                if any(e.get("stage") == "committing" for e in data.values()):
                    break
                time.sleep(0.2)
            else:
                self.fail("child never reached the committing stage")
        finally:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
            else:
                child.kill()
            child.wait()
        time.sleep(0.5)
        recovered = git_ops.recover_interrupted_operations()
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["stage"], "committing")
        self.assertFalse(recovered[0]["commit_created"])
        self.assertEqual(git(repo, "rev-parse", "HEAD"), head)
        self.assertEqual(git_ops.recover_interrupted_operations(), [])             # reported once
        with RepoLock(repo, timeout=5):
            pass

    def test_restart_during_push_marks_push_uncertain(self):
        repo, _ = self.repo_with_remote()
        entry = {"abc": {"repo": repo, "kind": "commit_push", "stage": "uploading", "pid": 99999999,
                         "started": time.time(), "branch": "main", "head_before": git(repo, "rev-parse", "HEAD")}}
        git_ops._journal_write(entry)
        recovered = git_ops.recover_interrupted_operations()
        self.assertTrue(recovered[0]["push_marked_uncertain"])
        self.assertTrue(git_safety.has_uncertain(repo, "main"))
        blocked = git_safety.push_authorized(repo, "origin", "main", confirmed=True, remote_url="x")
        self.assertEqual(blocked.outcome, "uncertain")


class TestRunnerPrimitives(Base):
    def test_output_is_faithful_including_crlf_and_trailing_newline(self):
        res = run_process([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'a\\r\\nb\\n')"], timeout=20)
        self.assertEqual(res.stdout, "a\nb\n")

    def test_timeout_kills_grandchildren_that_hold_the_pipe(self):
        code = ("import subprocess, sys, time\n"
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                "time.sleep(60)\n")
        t0 = time.monotonic()
        res = run_process([sys.executable, "-c", code], timeout=2)
        self.assertTrue(res.timed_out)
        self.assertLess(time.monotonic() - t0, 12)         # subprocess.run would block until the grandchild exits

    def test_askpass_helper_does_not_need_fchmod_and_is_private(self):
        path = git_safety._askpass_script()
        try:
            with open(path, "rb") as handle:
                data = handle.read()
            self.assertTrue(data.startswith(b"#!/bin/sh\n"))
            self.assertNotIn(b"\r", data)
            self.assertNotIn(TOKEN.encode(), data)
        finally:
            os.remove(path)

    def test_progress_lines_are_parsed_from_real_push_output(self):
        repo, remote = self.repo_with_remote()
        for i in range(30):
            write(repo, f"d/{i}.txt", os.urandom(2000).hex())
        git(repo, "add", "-A"); git(repo, "commit", "-m", "many")
        seen = []
        op = git_ops.GitOperation("push", repo)
        res = git_safety.push_authorized(repo, remote, "main", confirmed=True, remote_url=remote,
                                         on_line=lambda s, l: (op.on_line(s, l), seen.append(op.snapshot()["progress"])))
        self.assertEqual(res.outcome, "success", res.message)
        self.assertTrue(any(p for p in seen), "expected real 'Writing objects: N%' progress")


if __name__ == "__main__":
    unittest.main()
