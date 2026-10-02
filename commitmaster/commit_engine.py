"""Git operations via the git CLI.

We call `git` directly instead of driving GitHub Desktop's UI or a Git Bash
window — same engine, far more reliable.  GitHub Desktop is only opened at the
end so the user can review and push visually.
"""
import glob
import os
import subprocess
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from commitmaster.logger import get

log = get("commit_engine")


class GitError(Exception):
    pass


# ── Core git helper ───────────────────────────────────────────────────────────

def git(repo_path: str, *args, timeout: int = 30) -> str:
    """Run a git command inside repo_path and return stdout."""
    cmd = ["git", "-C", repo_path, *args]
    log.debug("git %s", " ".join(args))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        raise GitError("git was not found on PATH.  Install Git for Windows first.")
    except subprocess.TimeoutExpired:
        raise GitError(f"git command timed out: {' '.join(args)}")
    if result.returncode != 0:
        msg = result.stderr.strip() or f"git {' '.join(args)} failed"
        log.warning("git error in %s: %s", repo_path, msg)
        raise GitError(msg)
    return result.stdout


# ── Repo discovery ────────────────────────────────────────────────────────────

def is_git_repo(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".git"))


def list_repos(roots: List[str], max_depth: int = 3) -> List[str]:
    """Find git repos under the configured project folders (shallow walk)."""
    repos: List[str] = []
    for root in roots:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            log.debug("projects_dir not found, skipping: %s", root)
            continue
        if is_git_repo(root):
            repos.append(root)
            continue
        _walk(root, 1, max_depth, repos)
    found = sorted(set(repos))
    log.debug("list_repos found %d repos under %s", len(found), roots)
    return found


def _walk(folder: str, depth: int, max_depth: int, repos: List[str]) -> None:
    if depth > max_depth:
        return
    try:
        entries = os.scandir(folder)
    except OSError as exc:
        log.debug("Cannot scan %s: %s", folder, exc)
        return
    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            if entry.name == ".git":
                repos.append(folder)
            elif not entry.name.startswith(".") and entry.name not in ("node_modules", "__pycache__", ".venv", "venv"):
                _walk(entry.path, depth + 1, max_depth, repos)


# ── Repo introspection ────────────────────────────────────────────────────────

def uncommitted_changes(repo_path: str) -> List[Tuple[str, str]]:
    """Return list of (status, path) for pending changes, [] if clean."""
    out = git(repo_path, "status", "--porcelain", "-uall")
    changes: List[Tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        status, path = line[:2], line[3:].strip()
        if " -> " in path:       # renames: keep the new path
            path = path.split(" -> ")[1]
        changes.append((status.strip(), path.strip('"')))
    return changes


def repo_name(repo_path: str) -> str:
    return os.path.basename(os.path.normpath(repo_path))


def current_branch(repo_path: str) -> str:
    try:
        return git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip()
    except GitError:
        return "unknown"


def diff_summary(repo_path: str, max_chars: int = 8_000) -> str:
    """Full diff context for the AI — includes staged + unstaged changes."""
    try:
        # Staged changes (index vs HEAD)
        staged = git(repo_path, "diff", "--cached", "--unified=2")
        # Unstaged changes (working tree vs index)
        unstaged = git(repo_path, "diff", "--unified=2")
        stat = git(repo_path, "diff", "HEAD", "--stat")
        text = f"=== Stat ===\n{stat}\n\n=== Staged ===\n{staged}\n\n=== Unstaged ===\n{unstaged}"
    except GitError:
        # Fallback for repos with no commits yet
        try:
            text = git(repo_path, "diff", "HEAD", "--unified=2")
        except GitError:
            text = "(diff unavailable)"
    return text[:max_chars]


# ── Commit operations ─────────────────────────────────────────────────────────

def stage_and_commit(repo_path: str, files: List[str], message: str) -> str:
    """Stage specific files and create one commit.  Returns commit summary."""
    if not files:
        raise GitError("Nothing to stage")
    # Chunk the adds — very long arg lists can hit OS command-line limits.
    for i in range(0, len(files), 40):
        git(repo_path, "add", "--", *files[i:i + 40])
    git(repo_path, "commit", "-m", message)
    summary = git(repo_path, "log", "-1", "--oneline").strip()
    log.info("Committed in %s: %s", repo_name(repo_path), summary)
    return summary


# ── GitHub Desktop ────────────────────────────────────────────────────────────

def find_github_desktop() -> Optional[str]:
    """Locate GitHub Desktop's executable from common install paths (uses glob for versioned dirs)."""
    home = os.path.expanduser("~")
    patterns = [
        os.path.join(home, r"AppData\Local\GitHubDesktop\GitHubDesktop.exe"),
        os.path.join(home, r"AppData\Local\GitHubDesktop\app-*\GitHubDesktop.exe"),
        r"C:\Program Files\GitHub Desktop\GitHubDesktop.exe",
        r"C:\Program Files (x86)\GitHub Desktop\GitHubDesktop.exe",
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            path = sorted(matches)[-1]  # pick highest version if multiple
            log.debug("Found GitHub Desktop at: %s", path)
            return path
    log.debug("GitHub Desktop not found.")
    return None


def open_in_github_desktop(repo_path: str, gd_path: Optional[str] = None) -> bool:
    exe = gd_path or find_github_desktop()
    if not exe or not os.path.exists(exe):
        log.warning("GitHub Desktop not available.")
        return False
    try:
        subprocess.Popen([exe, repo_path])
        return True
    except OSError as exc:
        log.error("Could not open GitHub Desktop: %s", exc)
        return False


# ── File classification ───────────────────────────────────────────────────────

# Passed in at call-time so we don't read config.json per file.
def classify_file(status: str, path: str, sensitive_patterns: List[str]) -> str:
    """Deterministic first-pass grouping; the AI only writes the messages."""
    lowered = path.lower().replace("\\", "/")
    if any(p in lowered for p in sensitive_patterns):
        return "sensitive"
    if "test" in lowered:
        return "test"
    if lowered.endswith((".md", ".rst", ".txt")) or lowered.startswith("docs/") or "/docs/" in lowered:
        return "docs"
    if lowered.endswith((".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".lock", ".env.example")) \
            or lowered.startswith(".") or "/." in lowered:
        return "chore"
    if "A" in status or status == "??":   # new / untracked
        return "feat"
    return "code"


GROUP_LABELS = OrderedDict([
    ("feat",      "New features / files"),
    ("code",      "Modified code"),
    ("test",      "Tests"),
    ("docs",      "Documentation"),
    ("chore",     "Config / metadata"),
    ("sensitive", "⚠ Sensitive files (handle manually)"),
])


def build_groups(
    changes: List[Tuple[str, str]],
    sensitive_patterns: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    """changes: [(status, path)] → {group: [paths]} preserving order."""
    if sensitive_patterns is None:
        # Lazy fallback — callers should pass this in from config.
        from commitmaster.config import load_config
        sensitive_patterns = load_config()["sensitive_patterns"]
    groups: Dict[str, List[str]] = OrderedDict((g, []) for g in GROUP_LABELS)
    for status, path in changes:
        grp = classify_file(status, path, sensitive_patterns)
        groups[grp].append(path)
    return {g: files for g, files in groups.items() if files}