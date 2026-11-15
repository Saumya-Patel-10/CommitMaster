"""Commit and push operations that refuse silent extras, hook bypass, and force push.

Outcomes for push are success, no_remote_update, failed, and uncertain.
An uncertain result is recorded and is not retried until the caller passes
acknowledge_uncertain=True. This module never puts a token on the git
command line.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

OUTCOMES = ("success", "no_remote_update", "failed", "uncertain")


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


class PushResult(tuple):
    """Unpacks as (ok, message). ok is True only for a confirmed remote update."""

    def __new__(cls, outcome: str, message: str):
        if outcome not in OUTCOMES:
            outcome = "failed"
        ok = outcome == "success"
        return tuple.__new__(cls, (ok, message))

    def __init__(self, outcome: str, message: str):
        self.outcome = outcome if outcome in OUTCOMES else "failed"
        self.message = message


def _subprocess_kwargs() -> dict:
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return kwargs


def _run(args: Sequence[str], cwd: Optional[str] = None, env: Optional[dict] = None, timeout: int = 60) -> subprocess.CompletedProcess:
    if any(arg == "--no-verify" or arg in ("--force", "--force-with-lease") for arg in args):
        raise GitError("refusing hook bypass or force push")
    if args and args[0] == "git":
        try:
            push_at = args.index("push")
        except ValueError:
            push_at = -1
        if push_at >= 0 and any(arg == "-f" or str(arg).startswith("+") for arg in args[push_at + 1:]):
            raise GitError("refusing force push")
    return subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        **_subprocess_kwargs(),
    )


def _repo_root(repo_path: str) -> str:
    result = _run(["git", "-C", repo_path, "rev-parse", "--show-toplevel"])
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


def commit_authorized(repo_path: str, files: Sequence[str], message: str, *, confirmed: bool = False) -> str:
    """Commit exactly the named files. Does not reset or rewrite the real index."""
    if not confirmed:
        raise GitError("Commit refused until the exact file list is previewed and confirmed.")
    if _session_is_read_only():
        raise GitError("This session is read-only. Commit refused.")
    text = (message or "").strip()
    if not text:
        raise GitError("Commit refused: empty message.")
    if "--no-verify" in text:
        raise GitError("Commit refused.")
    wanted = normalize_files(repo_path, files)
    if not wanted:
        raise GitError("Nothing to commit.")

    env = os.environ.copy()
    index_path = tempfile.mktemp(prefix="cm-index-")
    env["GIT_INDEX_FILE"] = index_path
    try:
        read = _run(["git", "-C", repo_path, "read-tree", "HEAD"], env=env)
        if read.returncode != 0:
            _run(["git", "-C", repo_path, "read-tree", "--empty"], env=env)
        add = _run(["git", "-C", repo_path, "add", "--"] + wanted, env=env)
        if add.returncode != 0:
            detail = (add.stderr or add.stdout or "git add failed").strip()
            raise GitError(detail)
        listed = _run(["git", "-C", repo_path, "diff", "--cached", "--name-only"], env=env)
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
        commit = _run(["git", "-C", repo_path, "commit", "-m", text], env=env)
        if commit.returncode != 0:
            detail = (commit.stderr or commit.stdout or "git commit failed").strip()
            raise GitError(detail)
        summary_run = _run(["git", "-C", repo_path, "log", "-1", "--oneline"])
        _run(["git", "-C", repo_path, "add", "--"] + wanted)
        return (summary_run.stdout or text).strip()
    finally:
        try:
            os.remove(index_path)
        except OSError:
            pass


def classify_push_result(returncode: int, stdout: str, stderr: str, before: Optional[str], after: Optional[str], timed_out: bool = False) -> PushResult:
    blob = f"{stdout}\n{stderr}".lower()
    if timed_out or any(mark in blob for mark in _UNCERTAIN):
        return PushResult("uncertain", "Push outcome is uncertain. It was not retried. Confirm the remote before trying again.")
    if returncode == 0 and before and after and before == after:
        return PushResult("no_remote_update", "Remote already had this commit. Nothing was updated.")
    if returncode == 0 and "everything up-to-date" in blob:
        return PushResult("no_remote_update", "Remote already had this commit. Nothing was updated.")
    if returncode == 0 and (not before or not after or before != after):
        return PushResult("success", (stdout or stderr or "Push completed.").strip())
    if any(mark in blob for mark in _CONFIRMED_FAILURE) or returncode != 0:
        detail = (stderr or stdout or "git push failed").strip()
        return PushResult("failed", detail)
    return PushResult("uncertain", "Push outcome is uncertain. It was not retried.")


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
    path = _ledger_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)


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


def _remote_sha(remote_url: str, branch: str) -> Optional[str]:
    try:
        result = _run(["git", "ls-remote", remote_url, f"refs/heads/{branch}"], timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    line = result.stdout.strip().splitlines()
    if not line or not line[0].strip():
        return None
    return line[0].split()[0]


def _askpass_script() -> str:
    fd, path = tempfile.mkstemp(prefix="cm-askpass-", suffix=".py")
    os.fchmod(fd, stat.S_IRUSR | stat.S_IXUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(
            "import os, sys\n"
            "prompt = ' '.join(sys.argv[1:]).lower()\n"
            "sys.stdout.write(os.environ.get('CM_GIT_USERNAME','') if 'user' in prompt else os.environ.get('CM_GIT_TOKEN',''))\n"
        )
    return path


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
) -> PushResult:
    if not confirmed:
        return PushResult("failed", "Push refused until the remote and branch are previewed and confirmed.")
    if _session_is_read_only():
        return PushResult("failed", "This session is read-only. Push refused.")
    blocked = _demo_blocks_remote(remote_url or remote)
    if blocked:
        return PushResult("failed", blocked)
    if has_uncertain(repo_path, branch) and not acknowledge_uncertain:
        return PushResult(
            "uncertain",
            "A previous push to this branch had an uncertain outcome. Not retrying automatically.",
        )
    if acknowledge_uncertain:
        clear_uncertain(repo_path, branch)

    before = _remote_sha(remote_url or remote, branch) if (remote_url or remote) else None
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    askpass = ""
    command = ["git", "-C", repo_path, "-c", "credential.helper=", "push", remote, branch]
    if token:
        askpass = _askpass_script()
        env["GIT_ASKPASS"] = askpass
        env["CM_GIT_USERNAME"] = username or "x-access-token"
        env["CM_GIT_TOKEN"] = token
        if remote_url and token not in remote_url:
            command = ["git", "-C", repo_path, "-c", "credential.helper=", "push", remote_url, branch]
    timed_out = False
    try:
        try:
            result = _run(command, env=env, timeout=timeout)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            stdout, stderr, code = "", "timed out", 1
        except GitError as exc:
            return PushResult("failed", str(exc))
    finally:
        if askpass:
            try:
                os.remove(askpass)
            except OSError:
                pass
        env.pop("CM_GIT_TOKEN", None)

    if token:
        stdout = stdout.replace(token, "[REDACTED]")
        stderr = stderr.replace(token, "[REDACTED]")
    after = _remote_sha(remote_url or remote, branch) if not timed_out else None
    outcome = classify_push_result(code, stdout, stderr, before, after, timed_out=timed_out)
    if outcome.outcome == "uncertain":
        mark_uncertain(repo_path, branch, outcome.message)
    elif outcome.outcome in ("success", "no_remote_update"):
        clear_uncertain(repo_path, branch)
    return outcome
