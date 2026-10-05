"""
CommitMaster — Pre-Commit File Inspector.
Performs sanity checks, syntax validation, secret leak detection,
and conflict marker scanning on files before they are committed to git.
"""
import ast
import json
import os
import re
from typing import Any, Dict, List, Optional

from commitmaster.logger import get

log = get("file_inspector")

# Common secret detection regexes
SECRET_PATTERNS = [
    ("github_pat", r"\b(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})\b", "GitHub Personal Access Token"),
    ("private_key", r"-----BEGIN (?:RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----", "Private cryptographic key"),
    ("aws_access_key", r"\b(AKIA[0-9A-Z]{16})\b", "AWS Access Key ID"),
    ("openai_key", r"\b(sk-[a-zA-Z0-9]{20,})\b", "OpenAI API Key"),
    ("generic_secret", r"""(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[:=]\s*['"]([a-zA-Z0-9_\-\.]{20,})['"]""", "Hardcoded API Key / Secret"),
]

# Merge conflict markers
CONFLICT_PATTERNS = [
    ("conflict_head", r"^<{7}\s+", "Git merge conflict marker (HEAD)"),
    ("conflict_middle", r"^={7}$", "Git merge conflict marker (separator)"),
    ("conflict_tail", r"^>{7}\s+", "Git merge conflict marker (branch/remote)"),
]

# Extensions safe to inspect as text
TEXT_EXTENSIONS = {
    ".py", ".pyw", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".scss",
    ".md", ".txt", ".rst", ".sh", ".bat", ".ps1", ".sql", ".xml",
    ".csv", ".env", ".env.local", ".env.development", ".env.production",
}

# Large file limit (10MB)
LARGE_FILE_BYTES = 10 * 1024 * 1024

# Dangerous binary file extensions that are usually accidentally committed
ACCIDENTAL_BINARY_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".zip", ".tar", ".gz", ".7z", ".iso", ".bin"}


def is_binary_file(filepath: str) -> bool:
    """Detect if a file is likely binary by checking for null bytes in initial chunk."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        return False
    return False


def inspect_file(repo_path: str, rel_path: str) -> List[Dict[str, Any]]:
    """
    Inspect a single file for pre-commit issues.
    Returns list of dicts:
    {
        "file": rel_path,
        "severity": "error" | "security" | "warning",
        "type": str,
        "line": int,
        "col": int,
        "message": str,
        "snippet": str,
    }
    """
    issues: List[Dict[str, Any]] = []
    full_path = os.path.join(repo_path, rel_path)

    # Check existence (if deleted in git, no syntax/leak check needed)
    if not os.path.exists(full_path):
        return issues

    if os.path.isdir(full_path):
        return issues

    try:
        file_size = os.path.getsize(full_path)
    except OSError as e:
        log.warning("Could not stat %s: %s", rel_path, e)
        return issues

    # 1. Check for oversized files
    if file_size > LARGE_FILE_BYTES:
        issues.append({
            "file": rel_path,
            "severity": "warning",
            "type": "large_file",
            "line": 1,
            "col": 0,
            "message": f"Large file detected ({file_size / (1024 * 1024):.1f} MB). Storing large files in Git can bloat repository history.",
            "snippet": f"File size: {file_size:,} bytes",
        })

    # 2. Check for accidental binary executable files
    _, ext = os.path.splitext(rel_path.lower())
    if ext in ACCIDENTAL_BINARY_EXTENSIONS and file_size > 1024 * 1024:  # > 1MB binary
        issues.append({
            "file": rel_path,
            "severity": "warning",
            "type": "accidental_binary",
            "line": 1,
            "col": 0,
            "message": f"Binary archive/executable file ({ext}) detected. Verify this file belongs in source control.",
            "snippet": f"Extension: {ext}",
        })

    # 3. Check for empty files (except standard files like __init__.py or .gitkeep)
    base_name = os.path.basename(rel_path)
    if file_size == 0:
        if base_name not in ("__init__.py", ".gitkeep", ".keep", ".gitignore"):
            issues.append({
                "file": rel_path,
                "severity": "warning",
                "type": "empty_file",
                "line": 1,
                "col": 0,
                "message": "File is empty (0 bytes). Check if content was accidentally cleared.",
                "snippet": "(empty file)",
            })
        return issues

    # If file is clearly binary, skip text-based syntax/regex parsing
    if ext not in TEXT_EXTENSIONS and is_binary_file(full_path):
        return issues

    # Read content
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as exc:
        issues.append({
            "file": rel_path,
            "severity": "error",
            "type": "read_error",
            "line": 1,
            "col": 0,
            "message": f"Could not read file: {exc}",
            "snippet": "",
        })
        return issues

    lines = content.splitlines()

    # 4. Check for Git merge conflict markers
    for lineno, line in enumerate(lines, start=1):
        for ctype, pattern, cdesc in CONFLICT_PATTERNS:
            if re.search(pattern, line):
                issues.append({
                    "file": rel_path,
                    "severity": "error",
                    "type": "merge_conflict",
                    "line": lineno,
                    "col": 1,
                    "message": f"Unresolved merge conflict marker found: {cdesc}",
                    "snippet": line.strip()[:80],
                })
                break  # one conflict marker warning per line

    # 5. Check for Secret / Credential Leaks
    # Skip checking secrets in tests or examples if dummy
    is_test_or_example = any(k in rel_path.lower() for k in ("test", "example", "mock", "fixture"))
    for lineno, line in enumerate(lines, start=1):
        for stype, spattern, sdesc in SECRET_PATTERNS:
            match = re.search(spattern, line)
            if match:
                val = match.group(0)
                # Check for false positives (placeholders like "your_token_here", "dummy", "test", etc.)
                if any(fp in val.lower() for fp in ("example", "dummy", "placeholder", "your_", "xxxx", "test")):
                    continue
                if is_test_or_example and len(val) < 25:
                    continue
                issues.append({
                    "file": rel_path,
                    "severity": "security",
                    "type": "secret_leak",
                    "line": lineno,
                    "col": match.start() + 1,
                    "message": f"Potential credential leak: {sdesc}",
                    "snippet": f"{line.strip()[:35]}...[REDACTED]",
                })
                break

    # 6. Syntax validation by file type
    # A. Python syntax check
    if ext in (".py", ".pyw"):
        try:
            ast.parse(content, filename=rel_path)
        except SyntaxError as e:
            issues.append({
                "file": rel_path,
                "severity": "error",
                "type": "python_syntax_error",
                "line": e.lineno or 1,
                "col": e.offset or 0,
                "message": f"Python Syntax Error: {e.msg} (line {e.lineno or 1})",
                "snippet": (e.text or "").strip()[:80],
            })
        except Exception as exc:
            issues.append({
                "file": rel_path,
                "severity": "error",
                "type": "python_parse_error",
                "line": 1,
                "col": 0,
                "message": f"Python AST parse error: {exc}",
                "snippet": "",
            })

    # B. JSON syntax check
    elif ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            snippet = lines[e.lineno - 1].strip() if 0 <= e.lineno - 1 < len(lines) else ""
            issues.append({
                "file": rel_path,
                "severity": "error",
                "type": "json_syntax_error",
                "line": e.lineno,
                "col": e.colno,
                "message": f"JSON Syntax Error: {e.msg} (line {e.lineno}, col {e.colno})",
                "snippet": snippet[:80],
            })

    # C. YAML check (verify no tabs used for indentation)
    elif ext in (".yaml", ".yml"):
        # Check standard yaml indentation rule: tabs are illegal for indentation
        for lineno, line in enumerate(lines, start=1):
            if line.startswith("\t") or (line.lstrip() != line and "\t" in line[:len(line) - len(line.lstrip())]):
                issues.append({
                    "file": rel_path,
                    "severity": "error",
                    "type": "yaml_tab_error",
                    "line": lineno,
                    "col": 1,
                    "message": "YAML indentation error: tabs cannot be used for indentation in YAML files (use spaces)",
                    "snippet": line.strip()[:80],
                })
                break  # report first tab indentation issue

    return issues


def inspect_files(repo_path: str, files: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Inspect multiple files and return mapping of { file_path: [issues] }
    Only files with detected issues are present in the output dictionary.
    """
    results: Dict[str, List[Dict[str, Any]]] = {}
    for f in files:
        file_issues = inspect_file(repo_path, f)
        if file_issues:
            results[f] = file_issues
    return results


def summarize_issues(issues_by_file: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    """Return count breakdown of errors, security risks, and warnings."""
    summary = {"errors": 0, "security": 0, "warnings": 0, "total": 0}
    for file_issues in issues_by_file.values():
        for issue in file_issues:
            summary["total"] += 1
            sev = issue.get("severity")
            if sev == "error":
                summary["errors"] += 1
            elif sev == "security":
                summary["security"] += 1
            else:
                summary["warnings"] += 1
    return summary
