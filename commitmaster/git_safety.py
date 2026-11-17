"""Commit and push operations that refuse silent extras, hook bypass, and force push.

Outcomes for push are success, no_remote_update, failed, and uncertain.
An uncertain result is recorded and is not retried until the caller passes
acknowledge_uncertain=True. This module never puts a token on the git
command line.

Reliability notes (see docs/audit/git-hang-root-cause.md):

* every git child runs with stdin closed, prompts disabled, a wall-clock
  timeout, an optional idle timeout and cooperative cancellation, and the whole
  process tree is killed on abort (``git_runner.run_process``);
* mutating operations take a per-repository thread+process lock
  (``git_runner.RepoLock``), which fixes FINDING-GIT-01;
* the askpass helper is a portable ``#!/bin/sh`` script (``os.fchmod`` does not
  exist on Windows, which used to crash every token push);
* the remote is verified with the same credentials as the push, and after a
  timeout or cancellation the real remote state is checked before deciding
  between failed and uncertain;
* the remote-tracking ref is updated after a verified push so ahead/behind is
  correct in the UI.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import threading

from commitmaster.git_runner import (
    OperationCancelled,
    RepoBusyError,
    RepoLock,
    hardened_env,
    redact,
    run_process,
)

OUTCOMES = ("success", "no_remote_update", "failed", "uncertain")

# Default time a caller waits for another operation on the same repo to finish.
LOCK_WAIT_SECONDS = 30.0


class GitError(Exception):
    pass


_CONFIRMED_FAILURE = (
    "connection refused",
    "could not resolve",
    "authentication failed",
    "permission denied",
    "repository not found",
    "rejected",
    "non-fast-forward",
    "failed to push",
    "src refspec",
)
_UNCERTAIN = (
    "timed out",
    "rpc failed",
    "hung up unexpectedly",
    "connection reset",
    "early eof",
    "empty reply from server",
    "ssl_error_syscall",
    "operation timed out",
)

# (reason code, substrings, advice shown to the user)
_FAILURE_REASONS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("auth", (
        "authentication failed", "terminal prompts disabled", "invalid username or token",
        "could not read username", "could not read password", "bad credentials",
        "requested url returned error: 401", "requested url returned error: 403",
        "permission to", "denied to", "support for password authentication was removed",
    ), "GitHub rejected the credentials. Reconnect the account in GitHub Accounts (the token may be expired, "
       "revoked, or missing the 'repo' permission). Your commit is saved locally."),
    ("not_found", ("repository not found", "requested url returned error: 404"),
     "The repository was not found or this account cannot see it. Check the remote URL and the selected account."),
    ("non_fast_forward", ("non-fast-forward", "fetch first", "tip of your current branch is behind",
                          "updates were rejected because the remote contains work"),
     "The remote branch has commits you do not have. Pull or fetch and merge, then push again. "
     "Nothing was overwritten and your local commit is safe."),
    ("protected_branch", ("protected branch", "gh006", "gh013", "repository rule violations"),
     "The branch is protected or a repository rule blocked the push. Push to another branch and open a pull request."),
    ("hook_rejected", ("pre-receive hook declined", "hook declined", "remote rejected"),
     "A server-side hook rejected the push. Read the remote message in the log."),
    ("no_upstream", ("has no upstream branch", "no configured push destination", "src refspec"),
     "The branch does not exist on the remote yet or no destination is configured."),
    ("network", ("could not resolve", "connection refused", "network is unreachable", "failed to connect",
                 "unable to access", "connection timed out", "no route to host"),
     "Could not reach the remote. Check the network or VPN and try again. Your commit is saved locally."),
)


class PushResult(tuple):
    """Unpacks as (ok, message). ok is True only for a confirmed remote update."""

    def __new__(cls, outcome: str, message: str, reason: str = ""):
        if outcome not in OUTCOMES:
            outcome = "failed"
        ok = outcome == "success"
        return tuple.__new__(cls, (ok, message))

    def __init__(self, outcome: str, message: str, reason: str = ""):
        self.outcome = outcome if outcome in OUTCOMES else "failed"
        self.message = message
        self.reason = reason


def classify_failure(text: str) -> Tuple[str, str]:
    """Return (reason, advice) for a failed git network operation."""
    blob = (text or "").lower()
    for reason, marks, advice in _FAILURE_REASONS:
        if any(mark in blob for mark in marks):
            return reason, advice
    return "unknown", ""


_PROGRESS_LINE = re.compile(
    r"^\s*(Enumerating objects|Counting objects|Compressing objects|Writing objects|Delta compression|"
    r"Total \d+|remote: (Compressing|Counting|Enumerating|Resolving deltas))", re.I)


def clean_output(text: str) -> str:
    """Drop progress chatter so only meaningful git messages reach the user."""
    kept = [ln for ln in (text or "").splitlines() if ln.strip() and not _PROGRESS_LINE.match(ln)]
    return "\n".join(kept).strip()


_RUN_FORBIDDEN = ("--no-verify", "--force", "--force-with-lease")


def _run(
    args: Sequence[str],
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    timeout: int = 60,
    *,
    cancel: Optional[threading.Event] = None,
    on_line: Optional[Callable[[str, str], None]] = None,
    idle_timeout: Optional[float] = None,
):
    """Run git (or another command). Raises GitError for forbidden flags,
    subprocess.TimeoutExpired on timeout/idle hang, OperationCancelled on cancel."""
    if any(arg in _RUN_FORBIDDEN for arg in args):
        raise GitError("refusing hook bypass or force push")
    if args and args[0] == "git":
        try:
            push_at = args.index("push")
        except ValueError:
            push_at = -1
        if push_at >= 0 and any(arg == "-f" or str(arg).startswith("+") for arg in args[push_at + 1:]):
            raise GitError("refusing force push")
    try:
        result = run_process(
            args, cwd=cwd, env=hardened_env(env), timeout=timeout,
            idle_timeout=idle_timeout, cancel=cancel, on_line=on_line,
        )
    except FileNotFoundError:
        raise GitError("git was not found on PATH. Install Git for Windows first.")
    if result.cancelled:
        raise OperationCancelled("Operation cancelled.")
    if result.timed_out or result.hung:
        exc = subprocess.TimeoutExpired(list(args), timeout, output=result.stdout, stderr=result.stderr)
        exc.hung = result.hung  # type: ignore[attr-defined]
        raise exc
    return result


def _repo_root(repo_path: str) -> str:
    result = _run(["git", "-C", repo_path, "rev-parse", "--show-toplevel"], timeout=20)
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "not a git repository")
    return os.path.realpath(result.stdout.strip())


def normalize_files(repo_path: str, files: Iterable[str]) -> List[str]:
    root = _repo_root(repo_path)
    cleaned: List[str] = []
    for raw in files:
        if raw is None or not str(raw).strip():
            raise GitError("refusing an empty path")
        rel = str(raw).replace("\\", "/").lstrip("/")
        if rel.startswith("../") or rel == ".." or "/../" in f"/{rel}/":
            raise GitError(f"refusing path outside the repository: {raw}")
        full = os.path.realpath(os.path.join(root, rel))
        if os.path.commonpath([root, full]) != root:
            raise GitError(f"refusing path outside the repository: {raw}")
        if os.path.isdir(full):
            raise GitError(f"refusing to add a directory ({rel}); name each file")
        cleaned.append(rel)
    if len(set(cleaned)) != len(cleaned):
        raise GitError("duplicate paths in the commit request")
    return cleaned


def _session_is_read_only() -> bool:
    return os.getenv("COMMITMASTER_SESSION_READ_ONLY", "").strip() in ("1", "true", "True")


def _demo_blocks_remote(remote_url: str) -> Optional[str]:
    try:
        from commitmaster import product
        if not product.is_demo():
            return None
    except Exception:
        return None
    url = (remote_url or "").strip()
    if not url:
        return None
    lowered = url.lower()
    if lowered.startswith("file://") or lowered.startswith("/") or (len(lowered) > 2 and lowered[1] == ":"):
        return None
    if "github.com" in lowered or lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("git@"):
        return "Demo app refuses to push to a real remote."
    return None


# ── repository state helpers (read-only) ──────────────────────────────────────

def git_dir(repo_path: str) -> str:
    result = _run(["git", "-C", repo_path, "rev-parse", "--absolute-git-dir"], timeout=20)
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "not a git repository")
    return os.path.normpath(result.stdout.strip())


def in_progress_operation(repo_path: str) -> Optional[str]:
    """Name of a merge/rebase/cherry-pick/revert that is half-done, if any."""
    gd = git_dir(repo_path)
    markers = (
        ("MERGE_HEAD", "merge"),
        ("rebase-merge", "rebase"),
        ("rebase-apply", "rebase"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
        ("REVERT_HEAD", "revert"),
        ("BISECT_LOG", "bisect"),
    )
    for name, label in markers:
        if os.path.exists(os.path.join(gd, name)):
            return label
    return None


def unmerged_files(repo_path: str) -> List[str]:
    result = _run(["git", "-C", repo_path, "diff", "--name-only", "--diff-filter=U"], timeout=30)
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


def head_branch(repo_path: str) -> Optional[str]:
    """Current branch name, or None when HEAD is detached."""
    result = _run(["git", "-C", repo_path, "symbolic-ref", "--quiet", "--short", "HEAD"], timeout=20)
    name = result.stdout.strip()
    return name if result.returncode == 0 and name else None


def local_sha(repo_path: str, ref: str = "HEAD") -> Optional[str]:
    result = _run(["git", "-C", repo_path, "rev-parse", "--verify", "--quiet", ref], timeout=20)
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


# ── commit ────────────────────────────────────────────────────────────────────

def commit_authorized(
    repo_path: str,
    files: Sequence[str],
    message: str,
    *,
    confirmed: bool = False,
    cancel: Optional[threading.Event] = None,
    on_stage: Optional[Callable[[str, str], None]] = None,
    on_line: Optional[Callable[[str, str], None]] = None,
    lock_timeout: float = LOCK_WAIT_SECONDS,
    command_timeout: int = 60,
) -> str:
    """Commit exactly the named files. Does not reset or rewrite the real index.

    Concurrent callers on one repository are queued (up to ``lock_timeout``
    seconds) instead of racing on ``.git/refs`` (FINDING-GIT-01).
    """
    if not confirmed:
        raise GitError("Commit refused until the exact file list is previewed and confirmed.")
    if _session_is_read_only():
        raise GitError("This session is read-only. Commit refused.")
    text = (message or "").strip()
    if not text:
        raise GitError("Commit refused: empty message.")
    if "--no-verify" in text:
        raise GitError("Commit refused.")
    stage = on_stage or (lambda name, detail="": None)

    try:
        lock = RepoLock(repo_path, owner="commit", timeout=lock_timeout)
        lock.acquire()
    except RepoBusyError as exc:
        raise GitError(str(exc))
    try:
        stage("preparing", "Validating the file list")
        wanted = normalize_files(repo_path, files)
        if not wanted:
            raise GitError("Nothing to commit.")
        if in_progress_operation(repo_path) in ("merge", "rebase", "cherry-pick", "revert"):
            raise GitError(
                f"A {in_progress_operation(repo_path)} is in progress in this repository. Finish or abort it "
                "before committing from CommitMaster."
            )

        tmp_dir = tempfile.mkdtemp(prefix="cm-index-")
        env = hardened_env()
        env["GIT_INDEX_FILE"] = os.path.join(tmp_dir, "index")
        kw = dict(env=env, cancel=cancel, on_line=on_line, timeout=command_timeout)
        try:
            stage("staging", f"Staging {len(wanted)} selected file(s) in an isolated index")
            read = _run(["git", "-C", repo_path, "read-tree", "HEAD"], **kw)
            if read.returncode != 0:
                _run(["git", "-C", repo_path, "read-tree", "--empty"], **kw)
            add = _run(["git", "-C", repo_path, "add", "--"] + wanted, **kw)
            if add.returncode != 0:
                raise GitError((add.stderr or add.stdout or "git add failed").strip())
            listed = _run(["git", "-C", repo_path, "diff", "--cached", "--name-only"], **kw)
            if listed.returncode != 0:
                raise GitError(listed.stderr.strip() or "could not list staged files")
            staged = [line.replace("\\", "/") for line in listed.stdout.splitlines() if line.strip()]
            if sorted(staged) != sorted(wanted):
                extra = sorted(set(staged) - set(wanted))
                missing = sorted(set(wanted) - set(staged))
                raise GitError(
                    "Commit refused because the staged set did not match the preview. "
                    f"extra={extra} missing={missing}"
                )
            stage("committing", "Creating the commit (repository hooks run now)")
            # Hooks can legitimately take a while, so the idle timeout is generous.
            commit = _run(
                ["git", "-C", repo_path, "commit", "-m", text],
                env=env, cancel=cancel, on_line=on_line,
                timeout=max(command_timeout, 300), idle_timeout=120,
            )
            if commit.returncode != 0:
                detail = clean_output(commit.stderr or commit.stdout) or "git commit failed"
                raise GitError(detail)
            summary_run = _run(["git", "-C", repo_path, "log", "-1", "--oneline"], timeout=30)
            # Bring the real index in line with the new HEAD for the committed paths only.
            _run(["git", "-C", repo_path, "add", "--"] + wanted, timeout=command_timeout, cancel=None)
            return (summary_run.stdout or text).strip()
        except subprocess.TimeoutExpired as exc:
            kind = "stopped producing output" if getattr(exc, "hung", False) else "timed out"
            sub = next((a for a in exc.cmd[1:] if a in ("read-tree", "add", "diff", "commit", "log")), "command")
            raise GitError(
                f"git {sub} {kind} while committing. A repository hook may be waiting for input. "
                "Nothing was pushed and no work was discarded."
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    finally:
        lock.release()


# ── push ──────────────────────────────────────────────────────────────────────

def classify_push_result(returncode: int, stdout: str, stderr: str, before: Optional[str], after: Optional[str], timed_out: bool = False) -> PushResult:
    blob = f"{stdout}\n{stderr}".lower()
    if timed_out or any(mark in blob for mark in _UNCERTAIN):
        return PushResult("uncertain", "Push outcome is uncertain. It was not retried. Confirm the remote before trying again.", "uncertain")
    if returncode == 0 and before and after and before == after:
        return PushResult("no_remote_update", "Remote already had this commit. Nothing was updated.")
    if returncode == 0 and "everything up-to-date" in blob:
        return PushResult("no_remote_update", "Remote already had this commit. Nothing was updated.")
    if returncode == 0 and (not before or not after or before != after):
        return PushResult("success", (clean_output(stdout) or clean_output(stderr) or "Push completed.").strip())
    if any(mark in blob for mark in _CONFIRMED_FAILURE) or returncode != 0:
        detail = clean_output(stderr) or clean_output(stdout) or "git push failed"
        reason, advice = classify_failure(f"{stdout}\n{stderr}")
        if advice:
            detail = f"{detail}\n\n{advice}"
        return PushResult("failed", detail, reason)
    return PushResult("uncertain", "Push outcome is uncertain. It was not retried.", "uncertain")


def _ledger_path() -> str:
    override = os.getenv("COMMITMASTER_PUSH_LEDGER", "").strip()
    if override:
        return override
    from commitmaster import paths
    return os.path.join(paths.get_data_dir(), ".push_uncertain.json")


def _ledger_key(repo_path: str, branch: str) -> str:
    return f"{os.path.realpath(repo_path)}|{branch}"


def _read_ledger() -> Dict[str, str]:
    path = _ledger_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_ledger(data: Dict[str, str]) -> None:
    """Atomic write so a crash mid-write cannot corrupt the ledger."""
    path = _ledger_path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ledger-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def mark_uncertain(repo_path: str, branch: str, detail: str) -> None:
    data = _read_ledger()
    data[_ledger_key(repo_path, branch)] = detail
    _write_ledger(data)


def clear_uncertain(repo_path: str, branch: str) -> None:
    data = _read_ledger()
    data.pop(_ledger_key(repo_path, branch), None)
    _write_ledger(data)


def has_uncertain(repo_path: str, branch: str) -> bool:
    return _ledger_key(repo_path, branch) in _read_ledger()


def _auth_env(token: str = "", username: str = "") -> Tuple[dict, str]:
    """Environment for a network git command. Returns (env, askpass_path)."""
    env = hardened_env()
    askpass = ""
    if token:
        askpass = _askpass_script()
        env["GIT_ASKPASS"] = askpass
        env["SSH_ASKPASS"] = askpass
        env["CM_GIT_USERNAME"] = username or "x-access-token"
        env["CM_GIT_TOKEN"] = token
    return env, askpass


def _remote_sha(remote_url: str, branch: str, env: Optional[dict] = None, timeout: int = 20,
                cancel: Optional[threading.Event] = None, credential_helper_off: bool = False) -> Optional[str]:
    """SHA of refs/heads/<branch> on the remote.

    Tri-state: a SHA string; ``""`` when the remote was reached and the branch does not exist
    yet; ``None`` when the remote could not be queried (offline, auth, timeout). The difference
    matters after an aborted push: "" proves nothing was received, None proves nothing.
    """
    cmd = ["git"]
    if credential_helper_off:
        cmd += ["-c", "credential.helper="]
    cmd += ["ls-remote", remote_url, f"refs/heads/{branch}"]
    try:
        result = _run(cmd, env=env, timeout=timeout, cancel=cancel)
    except (OSError, subprocess.TimeoutExpired, GitError, OperationCancelled):
        return None
    if result.returncode != 0:
        return None
    line = result.stdout.strip().splitlines()
    if not line or not line[0].strip():
        return ""
    return line[0].split()[0]


_ASKPASS_SH = (
    "#!/bin/sh\n"
    "# CommitMaster one-shot askpass helper. Secrets arrive through the environment only.\n"
    "case \"$1\" in\n"
    "  *sername*) printf '%s' \"$CM_GIT_USERNAME\" ;;\n"
    "  *) printf '%s' \"$CM_GIT_TOKEN\" ;;\n"
    "esac\n"
)


def _askpass_script() -> str:
    """Create a private, executable askpass helper (works on Windows and POSIX).

    Git for Windows runs ``#!/bin/sh`` scripts through its bundled sh, so the same
    helper works everywhere. ``os.fchmod`` is POSIX-only and must not be used.
    """
    fd, path = tempfile.mkstemp(prefix="cm-askpass-", suffix=".sh")
    with os.fdopen(fd, "wb") as handle:
        handle.write(_ASKPASS_SH.encode("ascii"))          # LF endings, no BOM
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path.replace("\\", "/") if os.name == "nt" else path


def _sync_tracking_ref(repo_path: str, remote_name: str, branch: str, sha: str) -> None:
    """Mirror what ``git push`` does: update refs/remotes/<remote>/<branch>.

    Pushing to a URL (used for token auth) leaves the tracking ref stale, which made
    pushed commits look "unpushed" forever. Only runs for a configured remote name and
    only for a commit that exists locally.
    """
    if not remote_name or not sha:
        return
    try:
        have = _run(["git", "-C", repo_path, "remote", "get-url", remote_name], timeout=15)
        if have.returncode != 0:
            return
        if _run(["git", "-C", repo_path, "cat-file", "-e", f"{sha}^{{commit}}"], timeout=15).returncode != 0:
            return
        _run(["git", "-C", repo_path, "update-ref", f"refs/remotes/{remote_name}/{branch}", sha], timeout=15)
        up = _run(["git", "-C", repo_path, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"], timeout=15)
        if up.returncode != 0:
            _run(["git", "-C", repo_path, "branch", f"--set-upstream-to={remote_name}/{branch}", branch], timeout=15)
    except (OSError, subprocess.TimeoutExpired, GitError, OperationCancelled):
        pass


def push_authorized(
    repo_path: str,
    remote: str,
    branch: str,
    *,
    confirmed: bool = False,
    username: str = "",
    token: str = "",
    remote_url: str = "",
    acknowledge_uncertain: bool = False,
    timeout: int = 60,
    remote_name: str = "",
    cancel: Optional[threading.Event] = None,
    on_stage: Optional[Callable[[str, str], None]] = None,
    on_line: Optional[Callable[[str, str], None]] = None,
    idle_timeout: Optional[float] = 90,
    lock_timeout: float = LOCK_WAIT_SECONDS,
) -> PushResult:
    if not confirmed:
        return PushResult("failed", "Push refused until the remote and branch are previewed and confirmed.", "not_confirmed")
    if _session_is_read_only():
        return PushResult("failed", "This session is read-only. Push refused.", "read_only")
    blocked = _demo_blocks_remote(remote_url or remote)
    if blocked:
        return PushResult("failed", blocked, "demo")
    if not branch or branch == "HEAD":
        return PushResult(
            "failed",
            "HEAD is detached, so there is no branch to push. Create or switch to a branch first "
            "(for example: git switch -c my-branch). Your commits are not lost.",
            "detached_head",
        )
    if has_uncertain(repo_path, branch) and not acknowledge_uncertain:
        return PushResult(
            "uncertain",
            "A previous push to this branch had an uncertain outcome. Not retrying automatically.",
            "uncertain",
        )

    stage = on_stage or (lambda name, detail="": None)
    secrets = [token] if token else []
    safe_line = None
    if on_line:
        def safe_line(stream: str, line: str, _cb=on_line, _s=secrets) -> None:   # noqa: E306
            _cb(stream, redact(line, _s))

    try:
        lock = RepoLock(repo_path, owner="push", timeout=lock_timeout)
        lock.acquire()
    except RepoBusyError as exc:
        return PushResult("failed", str(exc), "busy")

    askpass = ""
    try:
        if acknowledge_uncertain:
            clear_uncertain(repo_path, branch)

        target = remote_url or remote
        env, askpass = _auth_env(token, username)
        helper_off = bool(token)
        stage("authenticating", "Using the selected GitHub account" if token else "Using the system credential helper")
        stage("connecting", "Reading the remote branch state")
        before = _remote_sha(target, branch, env=env, cancel=cancel, credential_helper_off=helper_off) if target else None
        pushed_sha = local_sha(repo_path, f"refs/heads/{branch}")
        if pushed_sha is None:
            return PushResult("failed", f"Local branch '{branch}' does not exist, nothing to push.", "no_branch")

        command = ["git", "-C", repo_path]
        if helper_off:
            command += ["-c", "credential.helper="]
        command += ["push", "--progress", remote, branch]

        stage("uploading", f"Pushing {branch}")
        timed_out = hung = False
        try:
            result = _run(command, env=env, timeout=timeout, cancel=cancel, on_line=safe_line, idle_timeout=idle_timeout)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            hung = bool(getattr(exc, "hung", False))
            stdout, stderr, code = "", "timed out", 1
        except OperationCancelled:
            stage("verifying", "Cancelled; checking what the remote actually received")
            after = _remote_sha(target, branch, env=env, credential_helper_off=helper_off) if target else None
            return _after_abort(repo_path, branch, before, after, pushed_sha, "cancelled", remote_name)
        except GitError as exc:
            return PushResult("failed", str(exc), "refused")

        stdout, stderr = redact(stdout, secrets), redact(stderr, secrets)

        stage("verifying", "Confirming the remote branch")
        after = _remote_sha(target, branch, env=env, credential_helper_off=helper_off) if target else None
        if timed_out:
            return _after_abort(repo_path, branch, before, after, pushed_sha, "stalled" if hung else "timeout", remote_name)

        outcome = classify_push_result(code, stdout, stderr, before or None, after or None)
        if outcome.outcome == "success" and after is not None and after != pushed_sha:
            # git said OK but the remote head is not our commit: do not claim success.
            outcome = PushResult(
                "uncertain",
                "Git reported success but the remote branch does not point at your commit. "
                "Check GitHub before pushing again.", "verify_mismatch")
        if outcome.outcome == "uncertain":
            mark_uncertain(repo_path, branch, outcome.message)
        elif outcome.outcome in ("success", "no_remote_update"):
            clear_uncertain(repo_path, branch)
            _sync_tracking_ref(repo_path, remote_name, branch, after or pushed_sha)
        return outcome
    finally:
        if askpass:
            try:
                os.remove(askpass)
            except OSError:
                pass
        lock.release()


def _after_abort(repo_path: str, branch: str, before: Optional[str], after: Optional[str],
                 pushed_sha: Optional[str], why: str, remote_name: str) -> PushResult:
    """Decide the true outcome after a timeout/stall/cancel by looking at the remote."""
    label = {"cancelled": "cancelled", "timeout": "timed out", "stalled": "stopped responding"}[why]
    if after and pushed_sha and after == pushed_sha:
        clear_uncertain(repo_path, branch)
        _sync_tracking_ref(repo_path, remote_name, branch, after)
        if before == after:
            return PushResult("no_remote_update", "Remote already had this commit. Nothing was updated.")
        return PushResult("success", f"The push was {label}, but the remote already has your commit.", "verified_after_abort")
    if after is not None and before is not None and after == before:
        return PushResult(
            "failed",
            f"The push {label}. The remote was checked and did not receive your commit. "
            "Your local commit is safe; you can push again.", why)
    message = (
        f"The push {label} and the remote state could not be verified. It was not retried. "
        "Check the repository on GitHub before pushing again."
    )
    mark_uncertain(repo_path, branch, message)
    return PushResult("uncertain", message, why)
