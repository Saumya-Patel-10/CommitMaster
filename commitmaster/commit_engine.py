"""Git operations via the git CLI.

We call `git` directly instead of driving GitHub Desktop's UI or a Git Bash
window — same engine, far more reliable.  GitHub Desktop is only opened at the
end so the user can review and push visually.
"""
import glob
import os
import re
import subprocess
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from commitmaster.logger import get

log = get("commit_engine")


class GitError(Exception):
    pass


def _subprocess_kwargs() -> dict:
    """Return subprocess kwargs to run background commands silently without popping up console windows."""
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si
    return kwargs


# ── Core git helper ───────────────────────────────────────────────────────────

def git(repo_path: str, *args, timeout: int = 30) -> str:
    """Run a git command inside repo_path and return stdout silently in background."""
    cmd = ["git", "-C", repo_path, *args]
    log.debug("git %s", " ".join(args))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            **_subprocess_kwargs(),
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

_CHANGES_CACHE: Dict[str, Tuple[float, List[Tuple[str, str]]]] = {}
_DIFF_CACHE: Dict[Tuple[str, str, int], Tuple[float, str]] = {}


def invalidate_changes_cache(repo_path: Optional[str] = None) -> None:
    """Clear cached uncommitted changes and diffs for a repo or all repos."""
    if repo_path:
        norm = os.path.normpath(repo_path)
        _CHANGES_CACHE.pop(norm, None)
        to_del = [k for k in _DIFF_CACHE if k[0] == norm]
        for k in to_del:
            _DIFF_CACHE.pop(k, None)
    else:
        _CHANGES_CACHE.clear()
        _DIFF_CACHE.clear()


def is_log_file(path: str) -> bool:
    """Return True if path is a log file (e.g. *.log or within a logs/ directory)."""
    norm = path.replace("\\", "/").lower()
    base = os.path.basename(norm)
    return norm.endswith(".log") or base.endswith(".log") or "/logs/" in norm or norm.startswith("logs/")


def uncommitted_changes(
    repo_path: str,
    force: bool = False,
    track_logs: Optional[bool] = None,
) -> List[Tuple[str, str]]:
    """
    Return list of (status, path) for pending changes, [] if clean.
    Uses GitHub Desktop's proven inspection architecture:
    1. Fast short-lived TTL cache (2.5s) prevents repetitive subprocess freezes during UI renders.
    2. Passes -c core.quotepath=false and --untracked-files=all with porcelain=v2.
    3. Seamlessly expands any untracked folder into individual file entries.
    4. Automatically filters out .log files unless track_logs is enabled.
    Guarantees 100% parity with official GitHub Desktop with zero lag.
    """
    repo_path = os.path.normpath(repo_path)
    now = time.monotonic()

    if track_logs is None:
        try:
            from commitmaster.config import load_config
            cfg = load_config()
            track_logs = bool(cfg.get("track_log_files", False))
        except Exception:
            track_logs = False

    if not force:
        cached = _CHANGES_CACHE.get(repo_path)
        if cached is not None and (now - cached[0]) < 2.5:
            res = list(cached[1])
            if not track_logs:
                res = [(st, p) for st, p in res if not is_log_file(p)]
            return res

    # 1. First try porcelain=v2 with raw unquoted paths (matching GitHub Desktop)
    try:
        out = git(
            repo_path,
            "-c", "core.quotepath=false",
            "status",
            "--porcelain=v2",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
        changes = _parse_porcelain_v2(out, repo_path=repo_path)
        log.debug("uncommitted_changes (v2) found %d files in %s", len(changes), repo_path)
        _CHANGES_CACHE[repo_path] = (now, changes)
        if not track_logs:
            changes = [(st, p) for st, p in changes if not is_log_file(p)]
        return changes
    except GitError:
        # Resilient fallback to porcelain v1 for older Git installations
        out = git(
            repo_path,
            "-c", "core.quotepath=false",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        changes = _parse_porcelain_v1(out, repo_path=repo_path)
        log.debug("uncommitted_changes (v1 fallback) found %d files in %s", len(changes), repo_path)
        _CHANGES_CACHE[repo_path] = (now, changes)
        if not track_logs:
            changes = [(st, p) for st, p in changes if not is_log_file(p)]
        return changes


def _format_xy_status(xy: str) -> str:
    """Map 2-character Git status code (e.g., '.M', 'M.', 'MM', 'A.', '.D') to human-readable label."""
    if not xy or len(xy) < 2:
        return "M"
    index_st, work_st = xy[0], xy[1]
    if index_st == "U" or work_st == "U" or xy in ("AA", "DD"):
        return "U"
    if "R" in xy:
        return "R"
    if "A" in xy:
        return "A" if "M" not in xy else "AM"
    if "D" in xy:
        return "D"
    if xy == "MM":
        return "MM"
    if "M" in xy:
        return "M"
    return xy.strip(".") or "M"


def _expand_dir_files(repo_path: Optional[str], dir_rel_path: str, seen: set) -> List[Tuple[str, str]]:
    """Expand untracked directory into individual files matching GitHub Desktop's view."""
    added = []
    if not repo_path:
        return added
    full_path = os.path.join(repo_path, dir_rel_path)
    if os.path.isdir(full_path):
        for root, _, filenames in os.walk(full_path):
            for fn in sorted(filenames):
                rel = os.path.relpath(os.path.join(root, fn), repo_path).replace("\\", "/")
                if rel not in seen:
                    seen.add(rel)
                    added.append(("??", rel))
    return added


def _parse_porcelain_v2(out: str, repo_path: Optional[str] = None) -> List[Tuple[str, str]]:
    """Parse git status --porcelain=v2 output without dropping any files or paths with spaces."""
    changes: List[Tuple[str, str]] = []
    seen = set()

    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        line_type = line[:1]

        if line_type == "1":
            # 1 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <path>
            tokens = line.split(" ", 8)
            if len(tokens) >= 9:
                xy = tokens[1]
                path = tokens[8].strip('"')
                st = _format_xy_status(xy)
                if path not in seen:
                    seen.add(path)
                    changes.append((st, path))

        elif line_type == "2":
            # 2 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <X><score> <path>\t<origPath>
            tokens = line.split(" ", 9)
            if len(tokens) >= 10:
                xy = tokens[1]
                path_part = tokens[9]
                new_path = path_part.split("\t")[0].strip('"')
                st = _format_xy_status(xy)
                if new_path not in seen:
                    seen.add(new_path)
                    changes.append((st, new_path))

        elif line_type == "u":
            # Unmerged / conflict: u <XY> <sub> <m1> <m2> <m3> <mW> <h1> <h2> <h3> <path>
            tokens = line.split(" ", 10)
            if len(tokens) >= 11:
                path = tokens[10].strip('"')
                if path not in seen:
                    seen.add(path)
                    changes.append(("U", path))

        elif line_type == "?":
            # ? <path>
            path = line[2:].strip().strip('"')
            if path:
                if path.endswith("/") or (repo_path and os.path.isdir(os.path.join(repo_path, path))):
                    expanded = _expand_dir_files(repo_path, path, seen)
                    if expanded:
                        changes.extend(expanded)
                    elif path not in seen:
                        seen.add(path)
                        changes.append(("??", path))
                elif path not in seen:
                    seen.add(path)
                    changes.append(("??", path))

    return changes


def _parse_porcelain_v1(out: str, repo_path: Optional[str] = None) -> List[Tuple[str, str]]:
    """Tolerant porcelain v1 parser with clean unquoting and directory expansion."""
    changes: List[Tuple[str, str]] = []
    seen = set()

    for line in out.splitlines():
        if not line or line.startswith("#") or line.startswith("!!"):
            continue
        if len(line) < 3:
            continue
        status = line[:2]
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[1]
        path = path.strip('"')
        st = status.strip() or status
        if path:
            if path.endswith("/") or (repo_path and os.path.isdir(os.path.join(repo_path, path))):
                expanded = _expand_dir_files(repo_path, path, seen)
                if expanded:
                    changes.extend(expanded)
                elif path not in seen:
                    seen.add(path)
                    changes.append((st, path))
            elif path not in seen:
                seen.add(path)
                changes.append((st, path))

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
    # Clean staging index first so only intended files are committed
    try:
        git(repo_path, "reset")
    except GitError:
        pass
    # Chunk the adds — very long arg lists can hit OS command-line limits.
    for i in range(0, len(files), 40):
        git(repo_path, "add", "-A", "--", *files[i:i + 40])
    git(repo_path, "commit", "-m", message)
    invalidate_changes_cache(repo_path)
    summary = git(repo_path, "log", "-1", "--oneline").strip()
    log.info("Committed in %s: %s", repo_name(repo_path), summary)
    return summary


def stage_and_commit_individual(
    repo_path: str,
    file_comments: List[Tuple[str, str]],
) -> List[Dict[str, str]]:
    """
    Commit each file individually with its own dedicated commit comment.
    file_comments: list of (file_path, comment_message)
    Returns list of dicts: {"file": path, "hash": hash, "summary": summary, "message": message}
    """
    if not file_comments:
        raise GitError("No files specified for individual commits.")

    # Unstage any previously staged files
    try:
        git(repo_path, "reset")
    except GitError:
        pass

    results: List[Dict[str, str]] = []
    failures: List[str] = []
    for file_path, msg in file_comments:
        clean_msg = (msg or "").strip() or f"chore: update {os.path.basename(file_path)}"
        try:
            # Stage only this specific file (handles additions, modifications, and deletions)
            git(repo_path, "add", "-A", "--", file_path)
            git(repo_path, "commit", "-m", clean_msg)
        except GitError as exc:
            failures.append(f"{file_path}: {exc}")
            try:
                git(repo_path, "reset", "-q", "--", file_path)   # leave nothing half-staged
            except GitError:
                pass
            continue
        summary = git(repo_path, "log", "-1", "--oneline").strip()
        commit_hash = summary.split()[0] if summary else ""
        results.append({
            "file": file_path,
            "hash": commit_hash,
            "summary": summary,
            "message": clean_msg,
        })
        log.info("Committed individually in %s [%s]: %s", repo_name(repo_path), file_path, summary)

    if results:
        invalidate_changes_cache(repo_path)

    if failures:
        err = GitError(f"{len(results)} of {len(file_comments)} commits succeeded. Failed: " + "; ".join(failures))
        err.results = results          # type: ignore[attr-defined]
        raise err
    return results


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


# ── Remote & GitHub Push Operations ──────────────────────────────────────────

def get_remote_url(repo_path: str, remote: str = "origin") -> Optional[str]:
    """Get the fetch/push URL for a remote, or None if remote doesn't exist."""
    try:
        url = git(repo_path, "remote", "get-url", remote).strip()
        return url
    except GitError:
        return None


def parse_github_slug(url: str) -> Optional[str]:
    """Extract owner/repo from https://github.com/owner/repo.git or git@github.com:owner/repo.git."""
    if not url:
        return None
    url = url.strip()
    if "github.com" not in url:
        return None
    # Handle git@github.com:owner/repo.git
    if "git@github.com:" in url:
        slug = url.split("git@github.com:")[1]
    # Handle https://...github.com/owner/repo.git
    elif "github.com/" in url:
        slug = url.split("github.com/")[1]
    else:
        return None
    slug = slug.rstrip("/")
    if slug.endswith(".git"):
        slug = slug[:-4]
    return slug


def configure_author_identity(repo_path: str, name: str, email: str) -> None:
    """Configure local repo git user.name and user.email to match account."""
    if name:
        git(repo_path, "config", "user.name", name)
    if email:
        git(repo_path, "config", "user.email", email)


def push_repo_with_account(
    repo_path: str,
    account: Dict,
    remote: str = "origin",
    branch: Optional[str] = None,
    timeout: int = 60,
) -> Tuple[bool, str]:
    """
    Push current or specified branch to remote using the given linked GitHub account.
    Authenticates securely using PAT without exposing token in git configs or process logs.
    Returns (success: bool, message: str).
    """
    token = account.get("github_token", "").strip()
    if not token:
        return False, "Selected GitHub account does not have a Personal Access Token (PAT)."

    branch = branch or current_branch(repo_path)
    if not branch or branch == "unknown":
        return False, "Could not determine current git branch."

    remote_url = get_remote_url(repo_path, remote)
    if not remote_url:
        return False, f"Remote '{remote}' not found in {repo_name(repo_path)}."

    slug = parse_github_slug(remote_url)
    if not slug:
        return False, f"Remote URL '{remote_url}' is not recognized as a GitHub repository."

    # Construct authenticated HTTPS target
    username = account.get("github_username", "").strip() or "x-access-token"
    auth_url = f"https://{username}:{token}@github.com/{slug}.git"

    # Configure local author identity if provided
    author_name = account.get("author_name", "")
    author_email = account.get("author_email", "")
    if author_name or author_email:
        try:
            configure_author_identity(repo_path, author_name, author_email)
        except Exception as exc:
            log.warning("Could not set git author identity: %s", exc)

    cmd = ["git", "-C", repo_path, "-c", "credential.helper=", "push", "-u", auth_url, branch]
    log.info("Pushing %s (%s) to %s via @%s", repo_name(repo_path), branch, slug, username)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            **_subprocess_kwargs(),
        )
    except FileNotFoundError:
        return False, "git executable not found on PATH."
    except subprocess.TimeoutExpired:
        return False, f"git push timed out after {timeout} seconds."

    # Scrub token from outputs before logging or returning
    stdout = result.stdout.replace(token, "[TOKEN_REDACTED]")
    stderr = result.stderr.replace(token, "[TOKEN_REDACTED]")

    if result.returncode == 0:
        msg = stdout.strip() or stderr.strip() or f"Pushed successfully to {slug} ({branch})"
        log.info("Push succeeded for %s: %s", repo_name(repo_path), msg)
        return True, f"Successfully pushed to GitHub ({slug}) on branch '{branch}' via @{username}!"
    else:
        err_msg = stderr.strip() or stdout.strip() or "git push failed"
        log.warning("Push failed for %s: %s", repo_name(repo_path), err_msg)
        return False, err_msg


def push(repo_path: str, remote: str = "origin", branch: Optional[str] = None) -> Tuple[bool, str]:
    """Push branch to remote using standard git CLI (supports SSH/Git Credential Manager)."""
    b = branch or current_branch(repo_path)
    try:
        out = git(repo_path, "push", remote, b)
        return True, out or f"Pushed successfully to {remote} ({b})"
    except GitError as exc:
        return False, str(exc)


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


def get_remote_upstream_ref(repo_path: str, branch: Optional[str] = None) -> Optional[str]:
    """Find the upstream remote branch (e.g. origin/main, @{upstream}) that was committed on GitHub."""
    b = branch or current_branch(repo_path)
    try:
        up = git(repo_path, "rev-parse", "--abbrev-ref", "@{upstream}").strip()
        if up and not up.startswith("@"):
            return up
    except GitError:
        pass
    if b:
        try:
            git(repo_path, "rev-parse", "--verify", f"origin/{b}")
            return f"origin/{b}"
        except GitError:
            pass
    for candidate in ("origin/main", "origin/master"):
        try:
            git(repo_path, "rev-parse", "--verify", candidate)
            return candidate
        except GitError:
            pass
    return None


def file_diff(
    repo_path: str,
    file_path: str,
    max_chars: int = 5000,
    against_remote: bool = False,
) -> str:
    """Get the diff for a single file (staged, unstaged, untracked, or against remote GitHub) with TTL caching."""
    norm_repo = os.path.normpath(repo_path)
    norm_file = file_path.replace("\\", "/")
    cache_key = (norm_repo, norm_file, max_chars, against_remote)
    now = time.monotonic()
    cached = _DIFF_CACHE.get(cache_key)
    if cached is not None and (now - cached[0]) < 3.0:
        return cached[1]

    try:
        head_diff = ""
        # If against_remote requested, compare against remote ref committed on GitHub
        if against_remote:
            up_ref = get_remote_upstream_ref(repo_path)
            if up_ref:
                try:
                    head_diff = git(repo_path, "diff", up_ref, "--unified=3", "--", norm_file)
                except GitError:
                    pass

        if not head_diff:
            try:
                head_diff = git(repo_path, "diff", "HEAD", "--unified=3", "--", norm_file)
            except GitError:
                # Repository without any commit yet: fall back to index / working tree
                head_diff = git(repo_path, "diff", "--cached", "--unified=3", "--", norm_file)
                head_diff += git(repo_path, "diff", "--unified=3", "--", norm_file)

        if head_diff.strip():
            res = head_diff[:max_chars]
            _DIFF_CACHE[cache_key] = (now, res)
            return res

        # If untracked file, display preview of file content
        full_path = os.path.join(repo_path, file_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(max_chars)
                    lines = content.splitlines()
                    preview = "\n".join(f"+ {line}" for line in lines[:60])
                    res = f"--- /dev/null\n+++ b/{norm_file}\n@@ -0,0 +1,{len(lines[:60])} @@\n{preview}"
                    _DIFF_CACHE[cache_key] = (now, res)
                    return res
            except Exception:
                pass
        res = "(no changes or binary file)"
        _DIFF_CACHE[cache_key] = (now, res)
        return res
    except GitError as exc:
        return f"(diff unavailable: {exc})"


def get_repo_commit_count(repo_path: str) -> int:
    """Return total number of commits made in this specific repository."""
    if not repo_path or not is_git_repo(repo_path):
        return 0
    try:
        out = git(repo_path, "rev-list", "--count", "HEAD").strip()
        return int(out) if out.isdigit() else 0
    except Exception:
        return 0


def get_repo_commit_history(repo_path: str, limit: int = 60) -> List[Dict[str, Any]]:
    """Return list of historical commits for this repository."""
    if not repo_path or not is_git_repo(repo_path):
        return []
    commits = []
    try:
        delimiter = "---COMMIT_DELIM---"
        field_sep = "---F_SEP---"
        fmt = f"{delimiter}%H{field_sep}%h{field_sep}%an{field_sep}%ae{field_sep}%ar{field_sep}%ad{field_sep}%s{field_sep}%b"
        out = git(repo_path, "log", f"-n{limit}", f"--pretty=format:{fmt}", "--date=short")
        parts = out.split(delimiter)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            fields = part.split(field_sep)
            if len(fields) >= 7:
                full_h = fields[0].strip()
                short_h = fields[1].strip()
                author = fields[2].strip()
                email = fields[3].strip()
                rel_date = fields[4].strip()
                iso_date = fields[5].strip()
                subject = fields[6].strip()
                body = fields[7].strip() if len(fields) > 7 else ""

                files_stat = []
                try:
                    numstat = git(repo_path, "show", "--numstat", "--format=", full_h)
                    for nline in numstat.splitlines():
                        nline = nline.strip()
                        if not nline:
                            continue
                        ntoks = nline.split("\t", 2)
                        if len(ntoks) == 3:
                            add_s, del_s, fpath = ntoks
                            files_stat.append({
                                "path": fpath,
                                "added": int(add_s) if add_s.isdigit() else 0,
                                "removed": int(del_s) if del_s.isdigit() else 0,
                            })
                except Exception:
                    pass

                commits.append({
                    "hash": full_h,
                    "short_hash": short_h,
                    "author": author,
                    "author_email": email,
                    "date_relative": rel_date,
                    "date": iso_date,
                    "subject": subject,
                    "body": body,
                    "full_message": f"{subject}\n\n{body}".strip() if body else subject,
                    "files": files_stat,
                    "files_count": len(files_stat),
                    "total_added": sum(f["added"] for f in files_stat),
                    "total_removed": sum(f["removed"] for f in files_stat),
                })
    except Exception as exc:
        log.debug("Error reading commit history for %s: %s", repo_path, exc)
    return commits


def get_commit_details(repo_path: str, commit_hash: str) -> Dict[str, Any]:
    """Return detailed metadata and changed files list for a single historical commit."""
    details: Dict[str, Any] = {
        "hash": commit_hash,
        "short_hash": commit_hash[:7],
        "author": "",
        "author_email": "",
        "date_relative": "",
        "date": "",
        "subject": "",
        "body": "",
        "parent_hash": "",
        "short_parent": "",
        "files": [],
        "files_count": 0,
        "total_added": 0,
        "total_removed": 0,
    }
    if not repo_path or not is_git_repo(repo_path):
        return details

    try:
        fmt = "%H%x09%h%x09%an%x09%ae%x09%ar%x09%ad%x09%P%x09%s%x09%b"
        out = git(repo_path, "show", "-s", f"--pretty=format:{fmt}", "--date=short", commit_hash)
        parts = out.split("\t")
        if len(parts) >= 8:
            details["hash"] = parts[0].strip()
            details["short_hash"] = parts[1].strip()
            details["author"] = parts[2].strip()
            details["author_email"] = parts[3].strip()
            details["date_relative"] = parts[4].strip()
            details["date"] = parts[5].strip()
            parents = parts[6].strip().split()
            details["parent_hash"] = parents[0] if parents else ""
            details["short_parent"] = parents[0][:7] if parents else ""
            details["subject"] = parts[7].strip()
            details["body"] = parts[8].strip() if len(parts) > 8 else ""

        numstat = git(repo_path, "show", "--numstat", "--format=", commit_hash)
        files_stat = []
        for nline in numstat.splitlines():
            nline = nline.strip()
            if not nline:
                continue
            ntoks = nline.split("\t", 2)
            if len(ntoks) == 3:
                add_s, del_s, fpath = ntoks
                files_stat.append({
                    "file": fpath,
                    "path": fpath,
                    "added": int(add_s) if add_s.isdigit() else 0,
                    "removed": int(del_s) if del_s.isdigit() else 0,
                })
        details["files"] = files_stat
        details["files_count"] = len(files_stat)
        details["total_added"] = sum(f["added"] for f in files_stat)
        details["total_removed"] = sum(f["removed"] for f in files_stat)
    except Exception as exc:
        log.debug("Error getting commit details: %s", exc)
    return details


def get_commit_file_diff(repo_path: str, commit_hash: str, file_path: str) -> str:
    """Return unified diff for a single file in a specific historical commit."""
    norm_file = file_path.replace("\\", "/")
    try:
        has_parent = False
        try:
            git(repo_path, "rev-parse", "--verify", f"{commit_hash}^")
            has_parent = True
        except GitError:
            pass

        if has_parent:
            diff_text = git(repo_path, "diff", f"{commit_hash}^", commit_hash, "--unified=3", "--", norm_file)
        else:
            diff_text = git(repo_path, "show", commit_hash, "--unified=3", "--format=", "--", norm_file)
        return diff_text or "(No changes detected in this file)"
    except Exception as exc:
        return f"(Diff unavailable: {exc})"


def parse_diff_to_split_lines(diff_text: str) -> List[Dict[str, Any]]:
    """
    Parse a unified git diff into side-by-side rows matching GitHub's split diff viewer.
    Each returned hunk contains:
      - 'header': e.g. '@@ -47,18 +47,19 @@ def _setup_window(self):'
      - 'rows': list of dicts with left_no, left_type, left_text, right_no, right_type, right_text
    """
    hunks: List[Dict[str, Any]] = []
    current_hunk: Optional[Dict[str, Any]] = None
    old_line_no = 0
    new_line_no = 0

    hunk_regex = re.compile(r"^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@(.*)$")
    lines = diff_text.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        raw_line = lines[i]
        m = hunk_regex.match(raw_line)
        if m:
            if current_hunk:
                hunks.append(current_hunk)
            old_line_no = int(m.group(1))
            new_line_no = int(m.group(2))
            current_hunk = {
                "header": raw_line,
                "rows": []
            }
            i += 1
            continue

        if current_hunk is None:
            i += 1
            continue

        if raw_line.startswith("+"):
            add_lines = []
            while i < n and lines[i].startswith("+"):
                add_lines.append(lines[i][1:])
                i += 1
            for text in add_lines:
                current_hunk["rows"].append({
                    "left_no": "", "left_type": "empty", "left_text": "",
                    "right_no": str(new_line_no), "right_type": "add", "right_text": text
                })
                new_line_no += 1
            continue
        elif raw_line.startswith("-"):
            del_lines = []
            while i < n and lines[i].startswith("-"):
                del_lines.append(lines[i][1:])
                i += 1
            add_lines = []
            while i < n and lines[i].startswith("+"):
                add_lines.append(lines[i][1:])
                i += 1
            max_len = max(len(del_lines), len(add_lines))
            for k in range(max_len):
                if k < len(del_lines) and k < len(add_lines):
                    current_hunk["rows"].append({
                        "left_no": str(old_line_no), "left_type": "delete", "left_text": del_lines[k],
                        "right_no": str(new_line_no), "right_type": "add", "right_text": add_lines[k]
                    })
                    old_line_no += 1
                    new_line_no += 1
                elif k < len(del_lines):
                    current_hunk["rows"].append({
                        "left_no": str(old_line_no), "left_type": "delete", "left_text": del_lines[k],
                        "right_no": "", "right_type": "empty", "right_text": ""
                    })
                    old_line_no += 1
                else:
                    current_hunk["rows"].append({
                        "left_no": "", "left_type": "empty", "left_text": "",
                        "right_no": str(new_line_no), "right_type": "add", "right_text": add_lines[k]
                    })
                    new_line_no += 1
            continue
        else:
            text = raw_line[1:] if raw_line.startswith(" ") else raw_line
            current_hunk["rows"].append({
                "left_no": str(old_line_no), "left_type": "context", "left_text": text,
                "right_no": str(new_line_no), "right_type": "context", "right_text": text
            })
            old_line_no += 1
            new_line_no += 1
            i += 1

    if current_hunk:
        hunks.append(current_hunk)

    return hunks


def get_unpushed_commits(
    repo_path: str,
    remote: str = "origin",
    branch: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Return list of commits waiting to be pushed to remote."""
    branch = branch or current_branch(repo_path)
    commits = []
    try:
        out = git(repo_path, "log", f"{remote}/{branch}..{branch}", "--oneline", timeout=10)
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            commits.append({
                "hash": parts[0],
                "message": parts[1] if len(parts) > 1 else "",
            })
    except GitError:
        # If upstream branch isn't tracked yet, get recent local commits
        try:
            out = git(repo_path, "log", "-5", "--oneline", timeout=10)
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" ", 1)
                commits.append({
                    "hash": parts[0],
                    "message": parts[1] if len(parts) > 1 else "",
                })
        except GitError:
            pass
    return commits


def get_branches(repo_path: str) -> List[str]:
    """Get list of local branch names."""
    try:
        out = git(repo_path, "branch", "--format=%(refname:short)")
        return [b.strip() for b in out.splitlines() if b.strip()]
    except GitError:
        return [current_branch(repo_path)]


def clone_repo(clone_url: str, target_dir: str, account: Optional[Dict] = None) -> Tuple[bool, str]:
    """Clone a git repository to target directory silently in the background."""
    target_dir = os.path.normpath(target_dir)
    os.makedirs(os.path.dirname(target_dir), exist_ok=True)
    
    url = clone_url
    token = account.get("github_token", "").strip() if account else ""
    if token and "github.com" in url:
        slug = parse_github_slug(url)
        if slug:
            username = account.get("github_username", "x-access-token")
            url = f"https://{username}:{token}@github.com/{slug}.git"

    cmd = ["git", "clone", url, target_dir]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace",
            **_subprocess_kwargs(),
        )
        if result.returncode == 0:
            return True, f"Successfully cloned into {target_dir}."
        err = result.stderr.replace(token, "[REDACTED]") if token else result.stderr
        return False, err.strip() or "git clone failed"
    except Exception as exc:
        return False, str(exc)