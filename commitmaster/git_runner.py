"""Low-level git process runner and per-repository lock.

Why this exists
---------------
``subprocess.run(..., timeout=N)`` is not enough for git on Windows:

* it only kills ``git.exe``; hooks and ``git-remote-https`` children keep the
  stdout/stderr pipes open, so ``communicate()`` can block long after the
  timeout (this is one way the UI ended up stuck on "Committing...");
* it cannot be cancelled from another thread;
* it gives no live output, so progress could not reflect real git activity;
* a child that reads stdin or prompts for credentials waits forever.

``run_process`` fixes those: stdin is /dev/null, prompts are disabled, output
is streamed line by line (``\\r`` progress updates included), a wall-clock
timeout and an optional idle ("no output") timeout are enforced, a cancel
event is honoured, and on any abort the whole process tree is killed.

``RepoLock`` serialises mutating operations on one repository, both between
threads and between processes (the lock is an OS file lock inside ``.git`` so
it is released by the OS if the process dies; there is no stale-lock state).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Sequence

__all__ = [
    "OperationCancelled",
    "RepoBusyError",
    "ProcResult",
    "run_process",
    "hardened_env",
    "redact",
    "RepoLock",
]


class OperationCancelled(Exception):
    """Raised when the caller cancelled a running git process."""


class RepoBusyError(Exception):
    """Raised when another operation already holds the repository lock."""


class ProcResult:
    __slots__ = ("args", "returncode", "stdout", "stderr", "timed_out", "hung", "cancelled", "duration")

    def __init__(self, args, returncode, stdout, stderr, timed_out=False, hung=False, cancelled=False, duration=0.0):
        self.args = list(args)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.hung = hung
        self.cancelled = cancelled
        self.duration = duration


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    """Remove secrets (tokens) from text before it is logged or displayed."""
    if not text:
        return text
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "[REDACTED]")
    return text


def hardened_env(base: Optional[dict] = None) -> dict:
    """Environment that makes git fail fast instead of waiting for a human."""
    env = dict(os.environ if base is None else base)
    env["GIT_TERMINAL_PROMPT"] = "0"           # never prompt on the (hidden) terminal
    env["GCM_INTERACTIVE"] = "never"           # Git Credential Manager: no UI
    env["GIT_EDITOR"] = "true"                 # never open an editor
    env["GIT_MERGE_AUTOEDIT"] = "no"
    env["GIT_OPTIONAL_LOCKS"] = "0"            # read-only commands must not take index.lock
    env["LC_MESSAGES"] = "C"                   # stable English text for error classification
    env["LANGUAGE"] = "C"
    return env


def _popen_kwargs() -> dict:
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        )
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _make_job(proc: subprocess.Popen):
    """Windows: put ``proc`` in a Job Object so every descendant can be terminated together.

    ``taskkill /T`` follows parent PIDs, which MSYS fork emulation (Git for Windows' sh running a
    hook) breaks, leaving orphans that keep our pipes open. A job tracks descendants by membership.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.AssignProcessToJobObject.restype = wintypes.BOOL
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        if not k32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle))):
            k32.CloseHandle(job)
            return None
        return job
    except Exception:
        return None


def _terminate_job(job) -> None:
    if not job or os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.TerminateJobObject(job, 1)
    except Exception:
        pass


def _close_job(job) -> None:
    if not job or os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle(job)
    except Exception:
        pass


def kill_process_tree(proc: subprocess.Popen, job=None) -> None:
    """Kill ``proc`` and every descendant (hooks, credential helpers, ssh)."""
    _terminate_job(job)
    if proc.poll() is not None and job is None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _emit(on_line, name: str, raw: bytes) -> None:
    if not on_line:
        return
    line = raw.decode("utf-8", errors="replace")
    if line.strip():
        try:
            on_line(name, line)
        except Exception:
            pass


def _pump(stream, name: str, sink: List[bytes], on_line, state: dict) -> None:
    """Capture raw bytes faithfully; separately split on \\n and \\r so git's
    in-place progress updates reach ``on_line`` while they happen."""
    pending = b""
    try:
        while True:
            chunk = stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096)
            if not chunk:
                break
            state["last_output"] = time.monotonic()
            sink.append(chunk)
            if on_line is None:
                continue
            pending += chunk
            while True:
                cuts = [i for i in (pending.find(b"\n"), pending.find(b"\r")) if i != -1]
                if not cuts:
                    break
                cut = min(cuts)
                raw, pending = pending[:cut], pending[cut + 1:]
                _emit(on_line, name, raw)
        if pending:
            _emit(on_line, name, pending)
    except Exception:
        pass


def _decode(chunks: List[bytes]) -> str:
    """Same text semantics as subprocess(text=True): UTF-8 and universal newlines."""
    text = b"".join(chunks).decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def run_process(
    args: Sequence[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    timeout: float = 60,
    idle_timeout: Optional[float] = None,
    cancel: Optional[threading.Event] = None,
    on_line: Optional[Callable[[str, str], None]] = None,
) -> ProcResult:
    """Run a command to completion with timeout, idle timeout and cancellation.

    Never raises for a non-zero exit; inspect ``returncode`` / flags instead.
    Raises ``FileNotFoundError`` if the executable is missing.
    """
    started = time.monotonic()
    proc = subprocess.Popen(
        list(args), cwd=cwd, env=env if env is not None else hardened_env(),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        **_popen_kwargs(),
    )
    job = _make_job(proc)
    state = {"last_output": started}
    out_chunks: List[bytes] = []
    err_chunks: List[bytes] = []
    readers = [
        threading.Thread(target=_pump, args=(proc.stdout, "stdout", out_chunks, on_line, state), daemon=True),
        threading.Thread(target=_pump, args=(proc.stderr, "stderr", err_chunks, on_line, state), daemon=True),
    ]
    for r in readers:
        r.start()

    timed_out = hung = cancelled = False
    while True:
        try:
            proc.wait(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            pass
        now = time.monotonic()
        if cancel is not None and cancel.is_set():
            cancelled = True
        elif timeout and now - started > timeout:
            timed_out = True
        elif idle_timeout and now - state["last_output"] > idle_timeout:
            hung = True
        if cancelled or timed_out or hung:
            kill_process_tree(proc, job)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            break

    for r in readers:
        r.join(timeout=3)
    # Closing a pipe while a reader thread is still inside read() blocks forever, so only
    # close streams whose reader has finished (daemon readers are reaped with the pipe).
    for stream, reader in zip((proc.stdout, proc.stderr), readers):
        if not reader.is_alive():
            try:
                stream.close()
            except Exception:
                pass
    _close_job(job)
    rc = proc.returncode if proc.returncode is not None else -1
    return ProcResult(
        args, rc, _decode(out_chunks), _decode(err_chunks),
        timed_out=timed_out, hung=hung, cancelled=cancelled,
        duration=time.monotonic() - started,
    )


# ── repository lock ───────────────────────────────────────────────────────────

_registry_guard = threading.Lock()
_registry: Dict[str, "_Slot"] = {}


class _Slot:
    def __init__(self) -> None:
        self.rlock = threading.RLock()
        self.depth = 0
        self.fd: Optional[int] = None
        self.owner = ""


def _lock_file_for(repo_path: str) -> Optional[str]:
    git_dir = os.path.join(repo_path, ".git")
    if os.path.isdir(git_dir):
        return os.path.join(git_dir, "commitmaster.lock")
    if os.path.isfile(git_dir):                      # worktree / submodule: ".git" is a pointer file
        try:
            with open(git_dir, "r", encoding="utf-8") as handle:
                text = handle.read().strip()
            if text.startswith("gitdir:"):
                target = text.split(":", 1)[1].strip()
                if not os.path.isabs(target):
                    target = os.path.join(repo_path, target)
                return os.path.join(os.path.normpath(target), "commitmaster.lock")
        except OSError:
            pass
    return None


def _os_lock(fd: int) -> bool:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _os_unlock(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


class RepoLock:
    """Re-entrant (per thread) thread+process lock for one repository.

    ``timeout=0`` fails immediately with ``RepoBusyError``; ``timeout=N`` waits
    up to N seconds, which turns concurrent callers into an orderly queue.
    """

    def __init__(self, repo_path: str, owner: str = "", timeout: float = 0.0) -> None:
        self.key = os.path.normcase(os.path.realpath(repo_path))
        self.repo_path = repo_path
        self.owner = owner
        self.timeout = timeout
        self._slot: Optional[_Slot] = None

    def holder(self) -> str:
        with _registry_guard:
            slot = _registry.get(self.key)
        return slot.owner if slot else ""

    def acquire(self) -> None:
        with _registry_guard:
            slot = _registry.setdefault(self.key, _Slot())
        deadline = time.monotonic() + max(0.0, self.timeout)
        while not slot.rlock.acquire(blocking=False):
            if time.monotonic() >= deadline:
                raise RepoBusyError(
                    f"Another CommitMaster operation is already running on this repository"
                    f"{' (' + slot.owner + ')' if slot.owner else ''}."
                )
            time.sleep(0.05)
        try:
            if slot.depth == 0:
                lock_path = _lock_file_for(self.repo_path)
                if lock_path:
                    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
                    while not _os_lock(fd):
                        if time.monotonic() >= deadline:
                            os.close(fd)
                            raise RepoBusyError(
                                "Another CommitMaster process is already running an operation on this repository."
                            )
                        time.sleep(0.05)
                    slot.fd = fd
                slot.owner = self.owner
            slot.depth += 1
            self._slot = slot
        except BaseException:
            slot.rlock.release()
            raise

    def release(self) -> None:
        slot = self._slot
        if slot is None:
            return
        self._slot = None
        slot.depth -= 1
        if slot.depth == 0:
            slot.owner = ""
            if slot.fd is not None:
                _os_unlock(slot.fd)
                try:
                    os.close(slot.fd)
                except OSError:
                    pass
                slot.fd = None
        slot.rlock.release()

    def __enter__(self) -> "RepoLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()
