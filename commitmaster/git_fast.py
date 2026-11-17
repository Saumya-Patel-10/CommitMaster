"""Answer a few hot, read-only git questions by reading files instead of spawning `git`.

On Windows every `git` process costs roughly 40 ms, and the UI asks "which branch is this?"
from many places. These helpers return ``None`` whenever they cannot be certain (reftable
storage, bare repositories, unreadable files, unusual layouts) so callers fall back to the real
git command and the observable behaviour is unchanged.
"""
import os
import re
from typing import Optional, Tuple

_HEX = re.compile(r"^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$")


def _read(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _locate(repo_path: str) -> Optional[Tuple[str, str]]:
    """Return (git_dir, common_dir) for the repository containing repo_path, like git's own discovery."""
    current = os.path.abspath(repo_path)
    for _ in range(64):
        dotgit = os.path.join(current, ".git")
        if os.path.isdir(dotgit):
            return dotgit, dotgit
        if os.path.isfile(dotgit):                       # linked worktree or submodule
            text = _read(dotgit)
            if not text or not text.startswith("gitdir:"):
                return None
            gitdir = text[len("gitdir:"):].strip()
            if not os.path.isabs(gitdir):
                gitdir = os.path.join(current, gitdir)
            gitdir = os.path.normpath(gitdir)
            common = gitdir
            pointer = _read(os.path.join(gitdir, "commondir"))
            if pointer and pointer.strip():
                target = pointer.strip()
                common = os.path.normpath(target if os.path.isabs(target) else os.path.join(gitdir, target))
            return gitdir, common
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return None


def _is_reftable(common_dir: str) -> bool:
    return os.path.exists(os.path.join(common_dir, "reftable"))


def ref_exists(repo_path: str, ref: str) -> Optional[bool]:
    """True/False for a full ref name such as ``refs/remotes/origin/main``; None if unknown."""
    if os.environ.get("GIT_DIR") or not ref.startswith("refs/"):
        return None
    located = _locate(repo_path)
    if not located:
        return None
    _gitdir, common = located
    if _is_reftable(common):
        return None
    if os.path.isfile(os.path.join(common, *ref.split("/"))):
        return True
    packed = _read(os.path.join(common, "packed-refs"))
    if packed is None:
        return False if os.path.isdir(common) else None
    suffix = " " + ref
    return any(line.rstrip("\r\n").endswith(suffix) for line in packed.splitlines() if line and line[0] not in "#^")


def head_branch(repo_path: str) -> Optional[str]:
    """Same answer as ``git rev-parse --abbrev-ref HEAD`` with this app's conventions.

    The branch name; ``"HEAD"`` when detached; ``"unknown"`` when the branch has no commits yet
    (git itself errors there). None means "ask git".
    """
    if os.environ.get("GIT_DIR"):
        return None
    located = _locate(repo_path)
    if not located:
        return None
    gitdir, common = located
    if _is_reftable(common):
        return None
    head = _read(os.path.join(gitdir, "HEAD"))
    if head is None:
        return None
    head = head.strip()
    if head.startswith("ref:"):
        target = head[4:].strip()
        if not target.startswith("refs/heads/"):
            return None
        exists = ref_exists(repo_path, target)
        if exists is None:
            return None
        return target[len("refs/heads/"):] if exists else "unknown"
    if _HEX.match(head):
        return "HEAD"
    return None
