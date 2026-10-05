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
    """
    Return list of (status, path) for pending changes, [] if clean.
    Uses GitHub Desktop's proven inspection architecture:
    1. Runs update-index --refresh to ensure index stats are in sync with filesystem.
    2. Passes -c core.quotepath=false and --untracked-files=all with porcelain=v2.
    3. Seamlessly expands any untracked folder into individual file entries.
    Guarantees 100% parity with official GitHub Desktop.
    """
    repo_path = os.path.normpath(repo_path)
    # 1. Update index stat cache (identical to GitHub Desktop internal worker)
    try:
        git(repo_path, "update-index", "-q", "--refresh")
    except GitError:
        pass

    # 2. First try porcelain=v2 with raw unquoted paths (matching GitHub Desktop)
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
    for file_path, msg in file_comments:
        clean_msg = (msg or "").strip() or f"chore: update {os.path.basename(file_path)}"
        # Stage only this specific file (handles additions, modifications, and deletions)
        git(repo_path, "add", "-A", "--", file_path)
        git(repo_path, "commit", "-m", clean_msg)
        summary = git(repo_path, "log", "-1", "--oneline").strip()
        commit_hash = summary.split()[0] if summary else ""
        results.append({
            "file": file_path,
            "hash": commit_hash,
            "summary": summary,
            "message": clean_msg,
        })
        log.info("Committed individually in %s [%s]: %s", repo_name(repo_path), file_path, summary)

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


def file_diff(repo_path: str, file_path: str, max_chars: int = 5000) -> str:
    """Get the diff for a single file (staged, unstaged, or untracked)."""
    norm_file = file_path.replace("\\", "/")
    try:
        # First try staged diff
        staged = git(repo_path, "diff", "--cached", "--", norm_file)
        if staged.strip():
            return staged[:max_chars]
        
        # Next try unstaged diff
        unstaged = git(repo_path, "diff", "--", norm_file)
        if unstaged.strip():
            return unstaged[:max_chars]
            
        # Try diff HEAD
        head_diff = git(repo_path, "diff", "HEAD", "--", norm_file)
        if head_diff.strip():
            return head_diff[:max_chars]

        # If untracked file, display preview of file content
        full_path = os.path.join(repo_path, file_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(max_chars)
                    lines = content.splitlines()
                    preview = "\n".join(f"+ {line}" for line in lines[:60])
                    return f"--- /dev/null\n+++ b/{norm_file}\n@@ -0,0 +1,{len(lines[:60])} @@\n{preview}"
            except Exception:
                pass
        return "(no changes or binary file)"
    except GitError as exc:
        return f"(diff unavailable: {exc})"


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
    """Clone a git repository to target directory."""
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
            cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace"
        )
        if result.returncode == 0:
            return True, f"Successfully cloned into {target_dir}."
        err = result.stderr.replace(token, "[REDACTED]") if token else result.stderr
        return False, err.strip() or "git clone failed"
    except Exception as exc:
        return False, str(exc)