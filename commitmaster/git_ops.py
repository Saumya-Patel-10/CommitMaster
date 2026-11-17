"""Git operation manager: commit + push as an observable, cancellable background job.

The UI never calls git directly for a commit/push. It starts an operation here,
then polls ``GitOperation.snapshot()`` (cheap, thread-safe) to render the stage,
elapsed time, real git progress and the diagnostic log.

Guarantees
----------
* the worker thread ALWAYS reaches a terminal state (success, failure, cancelled,
  uncertain) even if the runner raises, so the UI cannot stay on "Committing...";
* one active operation per repository; duplicate clicks are refused, not queued;
* commit and push have separate states: a local commit is never reported as
  pushed, and a failed push never hides the fact the commit exists;
* nothing destructive is ever run (no force-push, reset, branch delete, checkout);
* after the run the real git state (HEAD, ahead/behind, working tree) is read back;
* a small journal survives crashes so an interrupted push is reported as
  "uncertain" at next start instead of being silently forgotten.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Sequence, Tuple

from commitmaster import git_safety
from commitmaster.git_runner import OperationCancelled, RepoBusyError, RepoLock, redact
from commitmaster.git_safety import GitError, PushResult

# Ordered stages shown by the UI. "label" is what the user reads.
STAGES: Tuple[Tuple[str, str], ...] = (
    ("preparing", "Preparing repository"),
    ("checking", "Checking changes"),
    ("staging", "Staging selected files"),
    ("committing", "Creating commit"),
    ("authenticating", "Authenticating"),
    ("connecting", "Connecting to GitHub"),
    ("uploading", "Uploading changes"),
    ("verifying", "Verifying remote state"),
)
STAGE_LABELS = dict(STAGES)

# Terminal states
SUCCEEDED = "succeeded"                  # everything requested finished and was verified
COMMITTED_NOT_PUSHED = "committed_not_pushed"   # local commit exists; push failed / refused / uncertain
FAILED = "failed"                        # nothing was committed
CANCELLED = "cancelled"
RUNNING = "running"

_PROGRESS = re.compile(
    r"(Enumerating objects|Counting objects|Compressing objects|Writing objects|Receiving objects|Resolving deltas)"
    r":\s+(\d+)%\s+\((\d+)/(\d+)\)")


class OperationInProgress(Exception):
    """A commit/push is already running for this repository."""


class GitOperation:
    """Live, thread-safe record of one commit/push run."""

    def __init__(self, kind: str, repo: str, secrets: Sequence[str] = ()) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind                      # "commit", "push", "commit_push"
        self.repo = repo
        self.cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._secrets = [s for s in secrets if s]
        self._log: Deque[Tuple[float, str, str]] = deque(maxlen=800)
        self.started = time.monotonic()
        self.started_wall = time.time()
        self.ended: Optional[float] = None
        self.state = RUNNING
        self.stage = "preparing"
        self.detail = ""
        self.last_activity = self.started
        self.progress: Optional[Dict[str, Any]] = None   # {"label","percent","current","total"}
        self.commit_state = "pending"         # pending|running|done|failed|skipped
        self.push_state = "not_requested"     # not_requested|pending|running|success|no_remote_update|failed|uncertain|cancelled
        self.commit_summary = ""
        self.commit_shas: List[str] = []
        self.push_result: Optional[PushResult] = None
        self.error = ""
        self.advice = ""
        self.final_state: Dict[str, Any] = {}
        self.result_files: List[str] = []     # files that were committed
        self.partial = False                  # batch commit: some commits made, some failed
        self._branch = ""
        self._head_before = ""
        self._done = threading.Event()

    # -- recording -----------------------------------------------------------
    def log(self, level: str, message: str) -> None:
        message = redact(message, self._secrets)
        with self._lock:
            self._log.append((time.time(), level, message))
            self.last_activity = time.monotonic()

    def set_stage(self, stage: str, detail: str = "") -> None:
        with self._lock:
            self.stage = stage
            self.detail = redact(detail, self._secrets)
            self.progress = None
            self.last_activity = time.monotonic()
        self.log("info", f"{STAGE_LABELS.get(stage, stage)}" + (f": {detail}" if detail else ""))
        _journal_update(self)

    def on_line(self, stream: str, line: str) -> None:
        """Receives live git output (already redacted by the caller where it matters)."""
        match = _PROGRESS.search(line)
        if match:
            with self._lock:
                self.progress = {
                    "label": match.group(1), "percent": int(match.group(2)),
                    "current": int(match.group(3)), "total": int(match.group(4)),
                }
                self.last_activity = time.monotonic()
            return
        self.log("git" if stream == "stdout" else "git-err", line.strip())

    # -- control -------------------------------------------------------------
    def cancel(self) -> None:
        if self.state == RUNNING and not self.cancel_event.is_set():
            self.cancel_event.set()
            self.log("warn", "Cancel requested. Stopping git safely...")

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self._done.wait(timeout)

    def elapsed(self) -> float:
        end = self.ended if self.ended is not None else time.monotonic()
        return end - self.started

    def idle_seconds(self) -> float:
        return 0.0 if self.finished else time.monotonic() - self.last_activity

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "id": self.id, "kind": self.kind, "repo": self.repo, "state": self.state,
                "stage": self.stage, "stage_label": STAGE_LABELS.get(self.stage, self.stage),
                "detail": self.detail, "elapsed": self.elapsed(),
                "idle": 0.0 if self.finished else time.monotonic() - self.last_activity,
                "progress": dict(self.progress) if self.progress else None,
                "commit_state": self.commit_state, "push_state": self.push_state,
                "commit_summary": self.commit_summary, "error": self.error, "advice": self.advice,
                "final_state": dict(self.final_state),
                "cancel_requested": self.cancel_event.is_set(),
                "log": list(self._log),
            }

    def log_text(self) -> str:
        with self._lock:
            return "\n".join(
                f"{time.strftime('%H:%M:%S', time.localtime(ts))} [{lvl}] {msg}" for ts, lvl, msg in self._log
            )

    def _finish(self, state: str) -> None:
        with self._lock:
            self.state = state
            self.ended = time.monotonic()
        self.log("info", f"Finished: {state}")
        _journal_remove(self)
        self._done.set()


# ── journal (crash recovery) ──────────────────────────────────────────────────

_journal_guard = threading.Lock()


def _journal_path() -> str:
    override = os.getenv("COMMITMASTER_OPS_JOURNAL", "").strip()
    if override:
        return override
    from commitmaster import paths
    return os.path.join(paths.get_data_dir(), ".git_ops_journal.json")


def _journal_read() -> Dict[str, Any]:
    try:
        with open(_journal_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _journal_write(data: Dict[str, Any]) -> None:
    path = _journal_path()
    directory = os.path.dirname(path) or "."
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".journal-", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(tmp, path)
    except OSError:
        pass            # journaling must never break a commit


def _journal_update(op: GitOperation) -> None:
    with _journal_guard:
        data = _journal_read()
        data[op.id] = {
            "repo": op.repo, "kind": op.kind, "stage": op.stage, "pid": os.getpid(),
            "started": op.started_wall, "branch": getattr(op, "_branch", ""),
            "head_before": getattr(op, "_head_before", ""),
        }
        _journal_write(data)


def _journal_remove(op: GitOperation) -> None:
    with _journal_guard:
        data = _journal_read()
        if data.pop(op.id, None) is not None:
            _journal_write(data)


def _pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            try:
                code = wintypes.DWORD()
                # A terminated process stays openable while anyone holds a handle: check its exit code.
                return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
            finally:
                k32.CloseHandle(handle)
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def recover_interrupted_operations() -> List[Dict[str, Any]]:
    """Call once at startup. Returns operations that were running when a process died.

    Anything that had reached the network stages is recorded as an uncertain push, so the
    user is told to check the remote and a blind retry is blocked until acknowledged.
    """
    recovered: List[Dict[str, Any]] = []
    with _journal_guard:
        data = _journal_read()
        keep: Dict[str, Any] = {}
        for op_id, entry in data.items():
            if _pid_alive(int(entry.get("pid", 0) or 0)):
                keep[op_id] = entry
                continue
            item = dict(entry, id=op_id)
            repo, branch = entry.get("repo", ""), entry.get("branch", "")
            network = entry.get("stage") in ("authenticating", "connecting", "uploading", "verifying")
            if network and repo and branch:
                try:
                    git_safety.mark_uncertain(
                        repo, branch, "CommitMaster closed while a push was in progress. Check the remote before pushing again.")
                    item["push_marked_uncertain"] = True
                except OSError:
                    pass
            try:
                now = git_safety.local_sha(repo, "HEAD") if repo and os.path.isdir(repo) else None
            except Exception:
                now = None
            item["head_now"] = now
            item["commit_created"] = bool(now and entry.get("head_before") and now != entry.get("head_before"))
            recovered.append(item)
        if keep != data:
            _journal_write(keep)
    return recovered


# ── manager ───────────────────────────────────────────────────────────────────

_active_guard = threading.Lock()
_active: Dict[str, GitOperation] = {}


def _key(repo: str) -> str:
    return os.path.normcase(os.path.realpath(repo))


def active_operation(repo: str) -> Optional[GitOperation]:
    with _active_guard:
        op = _active.get(_key(repo))
    return op if op and not op.finished else None


def start_operation(
    kind: str,
    repo: str,
    runner: Callable[[GitOperation], None],
    *,
    secrets: Sequence[str] = (),
    on_finish: Optional[Callable[[GitOperation], None]] = None,
) -> GitOperation:
    """Run ``runner(op)`` on a worker thread. Raises OperationInProgress on a duplicate."""
    op = GitOperation(kind, repo, secrets)
    with _active_guard:
        current = _active.get(_key(repo))
        if current is not None and not current.finished:
            raise OperationInProgress(
                f"A {current.kind.replace('_', ' ')} is already running in this repository "
                f"({STAGE_LABELS.get(current.stage, current.stage)})."
            )
        _active[_key(repo)] = op

    def worker() -> None:
        try:
            # Zero wait: the registry already serialised in-process callers, so a held lock here
            # means another CommitMaster process (or a git GUI) is working on the repository.
            with RepoLock(repo, owner=kind, timeout=0):
                runner(op)
        except RepoBusyError as exc:
            op.error, op.state = str(exc), FAILED
            op.log("error", op.error)
        except OperationCancelled:
            op.error = "Cancelled."
        except BaseException as exc:                       # noqa: BLE001 - last line of defence
            op.error = op.error or f"{type(exc).__name__}: {exc}"
            op.log("error", f"Unexpected error: {op.error}")
        finally:
            _finalise(op)
            if op.state == RUNNING:
                op.state = FAILED
            op._finish(op.state)
            if on_finish:
                try:
                    on_finish(op)
                except Exception:
                    pass

    threading.Thread(target=worker, name=f"git-op-{op.id}", daemon=True).start()
    return op


def _finalise(op: GitOperation) -> None:
    """Pick the terminal state from the recorded commit/push states."""
    if op.state != RUNNING:
        return
    if op.cancel_event.is_set() and op.commit_state not in ("done", "skipped"):
        op.state = CANCELLED
    elif op.commit_state == "skipped" and op.push_state == "cancelled":
        op.state = CANCELLED                      # push-only run that was cancelled; commits untouched
    elif op.commit_state in ("failed", "pending", "running"):
        op.state = CANCELLED if op.cancel_event.is_set() else FAILED
    elif op.partial:
        op.state = COMMITTED_NOT_PUSHED
    elif op.push_state in ("success", "no_remote_update", "not_requested"):
        op.state = SUCCEEDED
    else:
        op.state = COMMITTED_NOT_PUSHED


# ── high-level commit/push runner ─────────────────────────────────────────────

def repository_state(repo: str) -> Dict[str, Any]:
    """Read-only snapshot used before and after an operation. Never mutates the repo."""
    state: Dict[str, Any] = {"repo": repo}
    try:
        branch = git_safety.head_branch(repo)
        state["branch"] = branch
        state["detached"] = branch is None
        state["head"] = git_safety.local_sha(repo, "HEAD")
        state["in_progress"] = git_safety.in_progress_operation(repo)
        state["unmerged"] = git_safety.unmerged_files(repo)
        up = git_safety._run(["git", "-C", repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], timeout=15)
        state["upstream"] = up.stdout.strip() if up.returncode == 0 else None
        if state["upstream"]:
            counts = git_safety._run(["git", "-C", repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}"], timeout=20)
            if counts.returncode == 0 and counts.stdout.split():
                ahead, behind = counts.stdout.split()[:2]
                state["ahead"], state["behind"] = int(ahead), int(behind)
        status = git_safety._run(["git", "-C", repo, "status", "--porcelain", "-uno"], timeout=30)
        state["dirty_tracked"] = len([ln for ln in status.stdout.splitlines() if ln.strip()])
    except Exception as exc:                     # reading state must never fail the operation
        state["error"] = str(exc)
    return state


def _changed_paths(repo: str, files: Sequence[str]) -> List[str]:
    out = git_safety._run(["git", "-C", repo, "status", "--porcelain", "--"] + list(files), timeout=30)
    changed = []
    for line in out.stdout.splitlines():
        if len(line) > 3:
            changed.append(line[3:].strip().strip('"').split(" -> ")[-1])
    return changed


def run_commit_and_push(
    op: GitOperation,
    repo: str,
    *,
    files: Sequence[str],
    message: Optional[str] = None,
    pairs: Optional[Sequence[Tuple[str, str]]] = None,
    push: bool = False,
    push_fn: Optional[Callable[..., PushResult]] = None,
    acknowledge_uncertain: bool = False,
) -> None:
    """Runner for ``start_operation``. ``push_fn(cancel=, on_stage=, on_line=)`` performs the push."""
    from commitmaster import commit_engine

    op.set_stage("preparing", "Opening repository")
    if not os.path.isdir(repo) or not commit_engine.is_git_repo(repo):
        op.error = "This folder is not a git repository."
        op.commit_state = "failed"
        return
    pre = repository_state(repo)
    op._branch = pre.get("branch") or ""
    op._head_before = pre.get("head") or ""
    _journal_update(op)

    op.set_stage("checking", "Reading working tree and branch state")
    if pre.get("in_progress") in ("merge", "rebase", "cherry-pick", "revert"):
        op.error = (f"A {pre['in_progress']} is in progress. Finish or abort it first, "
                    "then commit. CommitMaster will not touch it.")
        op.commit_state = "failed"
        return
    if pre.get("unmerged"):
        op.error = "These files have unresolved merge conflicts: " + ", ".join(pre["unmerged"][:8])
        op.advice = "Resolve the conflicts and save the files, then try again."
        op.commit_state = "failed"
        return
    if files:
        changed = _changed_paths(repo, files)
        if not changed:
            op.error = ("None of the selected files have changes any more. They may already be committed.")
            op.commit_state = "failed"
            return
    if push and pre.get("detached"):
        op.log("warn", "HEAD is detached: the commit will be created locally, but there is no branch to push.")

    # ---- commit (local) ----
    op.commit_state = "running"
    try:
        if pairs is not None:
            results = commit_engine.stage_and_commit_individual(
                repo, list(pairs), confirmed=True, cancel=op.cancel_event, on_stage=op.set_stage, on_line=op.on_line)
            for item in results:
                op.commit_shas.append(item["hash"])
            op.commit_summary = f"{len(results)} commit{'s' if len(results) != 1 else ''} created"
            op.result_files = [item["file"] for item in results]
        else:
            line = commit_engine.stage_and_commit(
                repo, list(files), message or "", confirmed=True,
                cancel=op.cancel_event, on_stage=op.set_stage, on_line=op.on_line)
            op.commit_summary = line
            op.commit_shas.append(line.split()[0] if line else "")
            op.result_files = list(files)
        op.commit_state = "done"
    except OperationCancelled:
        op.error = "Cancelled before the commit finished."
        op.commit_state = _commit_state_after_abort(repo, op)
    except GitError as exc:
        partial = getattr(exc, "results", [])
        if partial:
            op.commit_state = "done"
            op.result_files = [item["file"] for item in partial]
            op.commit_shas = [item["hash"] for item in partial]
            op.commit_summary = f"{len(partial)} of {len(pairs or [])} commits created"
        else:
            op.commit_state = _commit_state_after_abort(repo, op)
        op.error = str(exc)
        op.log("error", op.error)
        if op.commit_state == "done":
            # Some commits exist locally; never push a half-finished batch automatically.
            op.partial = True
    except Exception as exc:                                  # noqa: BLE001
        op.commit_state = _commit_state_after_abort(repo, op)
        op.error = f"{type(exc).__name__}: {exc}"
        op.log("error", op.error)

    if op.commit_state != "done":
        return
    op.log("info", f"Local commit created: {op.commit_summary}")

    # ---- push (remote) ----
    if push and op.partial:
        op.push_state = "cancelled"
        op.log("warn", "Push skipped because not every commit in the batch was created. Review, then push.")
    elif push:
        if op.cancel_event.is_set():
            op.push_state = "cancelled"
            op.log("warn", "Cancelled before the push started. The local commit is kept.")
        elif push_fn is None:
            op.push_state = "failed"
            op.error = "No push method was provided."
        else:
            op.push_state = "running"
            try:
                result = push_fn(cancel=op.cancel_event, on_stage=op.set_stage, on_line=op.on_line)
            except OperationCancelled:
                op.push_state = "cancelled"
                op.error = "Push cancelled. The local commit is kept."
            except Exception as exc:                          # noqa: BLE001
                op.push_state = "failed"
                op.error = f"{type(exc).__name__}: {exc}"
                op.log("error", op.error)
            else:
                op.push_result = result
                op.push_state = result.outcome
                if result.outcome in ("failed", "uncertain"):
                    op.error = result.message
                    op.advice = ""
                op.log("info" if result.outcome in ("success", "no_remote_update") else "error",
                       f"Push {result.outcome}: {result.message}")
                if result.outcome == "failed" and getattr(result, "reason", "") == "cancelled":
                    op.push_state = "cancelled"

    # ---- verify final state ----
    op.set_stage("verifying", "Reading back the repository state")
    post = repository_state(repo)
    op.final_state = post
    if op.commit_state == "done" and post.get("head") and op._head_before and post["head"] == op._head_before:
        op.log("error", "Commit reported success but HEAD did not move. Check the repository.")


def push_in_background(
    tk_root,
    repo: str,
    push_fn: Callable[..., PushResult],
    on_result: Callable[[GitOperation], None],
    *,
    secrets: Sequence[str] = (),
) -> Optional[GitOperation]:
    """Push without blocking Tk, for screens that show a dialog instead of the operation panel.

    ``on_result(op)`` always runs once, on the Tk thread, with a finished operation, so a
    crash in the worker can no longer leave the screen waiting forever. Returns None (after
    calling ``on_result``) if a run is already active for the repository.
    """
    try:
        op = start_operation("push", repo, lambda o: run_push_only(o, repo, push_fn=push_fn), secrets=secrets)
    except OperationInProgress as exc:
        stub = GitOperation("push", repo)
        stub.error = str(exc)
        stub.state, stub.push_state = FAILED, "failed"
        stub._finish(FAILED)
        on_result(stub)
        return None

    def poll() -> None:
        if not op.finished:
            tk_root.after(150, poll)
            return
        on_result(op)

    tk_root.after(150, poll)
    return op


def push_result_text(op: GitOperation) -> Tuple[bool, str]:
    """(ok, message) for dialogs. ok is True only when the remote is verified to have the commits."""
    ok = op.push_state in ("success", "no_remote_update")
    if op.push_result is not None:
        return ok, op.push_result.message
    return ok, op.error or ("Pushed." if ok else "The push did not complete.")


def run_push_only(
    op: GitOperation,
    repo: str,
    *,
    push_fn: Callable[..., PushResult],
) -> None:
    """Runner for pushing commits that already exist locally (no commit is created)."""
    from commitmaster import commit_engine

    op.set_stage("preparing", "Opening repository")
    if not os.path.isdir(repo) or not commit_engine.is_git_repo(repo):
        op.error = "This folder is not a git repository."
        op.commit_state = "skipped"
        return
    pre = repository_state(repo)
    op._branch = pre.get("branch") or ""
    op._head_before = pre.get("head") or ""
    _journal_update(op)
    op.commit_state = "skipped"          # nothing to commit: the commits already exist
    op.push_state = "pending"
    op.set_stage("checking", "Reading branch and upstream state")
    if pre.get("in_progress") in ("merge", "rebase", "cherry-pick", "revert"):
        op.error = f"A {pre['in_progress']} is in progress. Finish or abort it before pushing."
        op.push_state = "failed"
        return
    if pre.get("detached"):
        op.error = ("HEAD is detached, so there is no branch to push. Create or switch to a branch first. "
                    "Your commits are not lost.")
        op.push_state = "failed"
        return
    if pre.get("ahead") == 0 and pre.get("upstream"):
        op.log("info", "The branch is level with its upstream; git will confirm against the remote.")

    op.push_state = "running"
    try:
        result = push_fn(cancel=op.cancel_event, on_stage=op.set_stage, on_line=op.on_line)
    except OperationCancelled:
        op.push_state = "cancelled"
        op.error = "Push cancelled. Your commits are kept locally."
    except Exception as exc:                                  # noqa: BLE001
        op.push_state = "failed"
        op.error = f"{type(exc).__name__}: {exc}"
        op.log("error", op.error)
    else:
        op.push_result = result
        op.push_state = result.outcome
        if getattr(result, "reason", "") == "cancelled":
            op.push_state = "cancelled"
        if result.outcome in ("failed", "uncertain"):
            op.error = result.message
        op.log("info" if result.outcome in ("success", "no_remote_update") else "error",
               f"Push {result.outcome}: {result.message}")
    op.set_stage("verifying", "Reading back the repository state")
    op.final_state = repository_state(repo)


def _commit_state_after_abort(repo: str, op: GitOperation) -> str:
    """After a failure/cancel, decide from the real HEAD whether a commit was actually made."""
    try:
        now = git_safety.local_sha(repo, "HEAD")
    except Exception:
        return "failed"
    before = getattr(op, "_head_before", "")
    if now and now != before:
        op.commit_shas.append(now[:7])
        op.commit_summary = op.commit_summary or f"commit {now[:7]}"
        op.result_files = op.result_files or []
        op.log("warn", "A commit was created before the operation stopped; it is kept.")
        return "done"
    return "failed"
