"""Git operations via the git CLI.

We call `git` directly instead of driving GitHub Desktop's UI or a Git Bash
window -- same engine, far more reliable. GitHub Desktop is only opened at the
end so the user can review and push visually.
"""
import os
import subprocess
from collections import OrderedDict

from commitmaster.config import load_config  # noqa: F401  (used by callers)


class GitError(Exception):
    pass


def git(repo_path, *args, timeout=30):
    """Run a git command inside repo_path and return stdout."""
    cmd = ["git", "-C", repo_path, *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        raise GitError("git was not found on PATH. Install Git for Windows first.")
    except subprocess.TimeoutExpired:
        raise GitError(f"git command timed out: {' '.join(args)}")
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def is_git_repo(path):
    return os.path.isdir(os.path.join(path, ".git"))


def list_repos(roots, max_depth=3):
    """Find git repos under the configured project folders (shallow walk)."""
    repos = []
    for root in roots:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        if is_git_repo(root):
            repos.append(root)
            continue
        _walk(root, 1, max_depth, repos)
    return sorted(set(repos))


def _walk(folder, depth, max_depth, repos):
    if depth > max_depth:
        return
    try:
        entries = os.scandir(folder)
    except OSError:
        return
    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            if entry.name == ".git":
                repos.append(folder)
            elif not entry.name.startswith("."):
                _walk(entry.path, depth + 1, max_depth, repos)


def uncommitted_changes(repo_path):
    """Return list of (status, path) for pending changes, [] if clean."""
    out = git(repo_path, "status", "--porcelain", "-uall")
    changes = []
    for line in out.splitlines():
        if not line.strip():
            continue
        status, path = line[:2], line[3:].strip()
        if " -> " in path:  # renames: keep the new path
            path = path.split(" -> ")[1]
        changes.append((status.strip(), path.strip('"')))
    return changes


def repo_name(repo_path):
    return os.path.basename(os.path.normpath(repo_path))


def current_branch(repo_path):
    return git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip()


def diff_summary(repo_path, max_chars=7000):
    """Tracked changes diff + names of untracked files, for AI context."""
    tracked = git(repo_path, "diff", "HEAD", "--unified=1")
    stat = git(repo_path, "diff", "HEAD", "--stat")
    untracked = git(repo_path, "ls-files", "--others", "--exclude-standard")
    text = f"Changed files:\n{stat}\n\nUntracked files:\n{untracked}\n\nDiff:\n{tracked}"
    return text[:max_chars]


def stage_and_commit(repo_path, files, message):
    """Stage specific files and create one commit. Returns commit summary."""
    if not files:
        raise GitError("Nothing to stage")
    # Chunk the adds -- very long arg lists can hit OS command-line limits.
    for i in range(0, len(files), 40):
        git(repo_path, "add", "--", *files[i:i + 40])
    git(repo_path, "commit", "-m", message)
    return git(repo_path, "log", "-1", "--oneline").strip()


def find_github_desktop():
    """Locate GitHub Desktop's executable from common install paths."""
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, r"AppData\Local\GitHubDesktop\GitHubDesktop.exe"),
        os.path.join(home, r"AppData\Local\GitHubDesktop\app-\GitHubDesktop.exe"),
        r"C:\Program Files\GitHub Desktop\GitHubDesktop.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def open_in_github_desktop(repo_path):
    exe = find_github_desktop()
    if not exe:
        return False
    subprocess.Popen([exe, repo_path])
    return True


def classify_file(status, path):
    """Deterministic first-pass grouping; the AI only writes the messages."""
    lowered = path.lower().replace("\\", "/")
    if any(p in lowered for p in load_config()["sensitive_patterns"]):
        return "sensitive"
    if "test" in lowered:
        return "test"
    if lowered.endswith((".md", ".rst", ".txt")) or lowered.startswith("docs/"):
        return "docs"
    if lowered.endswith((".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".lock")) \
            or lowered.startswith(".") or "/." in lowered:
        return "chore"
    if "A" in status or status == "??":  # new / untracked files
        return "feat"
    return "code"


GROUP_LABELS = OrderedDict([
    ("feat", "New features / files"),
    ("code", "Modified code"),
    ("test", "Tests"),
    ("docs", "Documentation"),
    ("chore", "Config / metadata"),
    ("sensitive", "Sensitive files (review manually!)"),
])


def build_groups(changes):
    """changes: [(status, path)] -> {group: [paths]} preserving order."""
    groups = OrderedDict((g, []) for g in GROUP_LABELS)
    for status, path in changes:
        groups[classify_file(status, path)].append(path)
    return {g: files for g, files in groups.items() if files}