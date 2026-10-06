"""
CommitMaster — Pre-Commit File Inspector.

Performs sanity checks, syntax validation, secret-leak detection, insecure-code
pattern detection and conflict-marker scanning on files before they are committed.

Every issue is returned as a dict with enough information for the UI to show the
user *what* is wrong, *where* it is (with the offending code), *why* it matters
and *how* to fix it:

    {
        "file":        "path/in/repo.py",
        "severity":    "error" | "security" | "warning",
        "type":        "secret_leak" | "insecure_code" | ...,
        "title":       "Hardcoded API key",
        "line":        12,
        "col":         8,
        "message":     one line description (kept for backwards compatibility),
        "snippet":     the offending line (secrets masked),
        "context":     [{"line": 10, "text": "...", "hit": False}, ...],
        "explanation": why this is a problem,
        "fix":         how to resolve it,
        "reference":   e.g. "CWE-798",
    }
"""
import ast
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from commitmaster.logger import get

log = get("file_inspector")

CONTEXT_RADIUS = 2          # lines of code shown above / below an issue
MAX_ISSUES_PER_FILE = 25

# ── Secret detection ──────────────────────────────────────────────────────────
# (type, regex, label, fix hint).  A named group "secret" (or group 1) marks the
# part of the line that will be masked in the snippet.
SECRET_PATTERNS = [
    ("github_pat", r"\b(?P<secret>ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})\b",
     "GitHub Personal Access Token"),
    ("private_key", r"(?P<secret>-----BEGIN (?:RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----)",
     "Private cryptographic key"),
    ("aws_access_key", r"\b(?P<secret>AKIA[0-9A-Z]{16})\b", "AWS Access Key ID"),
    ("openai_key", r"\b(?P<secret>sk-[a-zA-Z0-9]{20,})\b", "OpenAI API Key"),
    ("stripe_key", r"\b(?P<secret>sk_live_[0-9a-zA-Z]{16,})\b", "Stripe live secret key"),
    ("google_api_key", r"\b(?P<secret>AIza[0-9A-Za-z_\-]{35})\b", "Google API key"),
    ("slack_token", r"\b(?P<secret>xox[baprs]-[0-9A-Za-z\-]{10,})\b", "Slack token"),
    ("url_credentials", r"[a-zA-Z][a-zA-Z0-9+.\-]*://[^/\s:@'\"]+:(?P<secret>[^/\s:@'\"]{4,})@",
     "Password embedded in a URL"),
    ("generic_secret",
     r"""(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[:=]\s*['"](?P<secret>[a-zA-Z0-9_\-\.]{20,})['"]""",
     "Hardcoded API key / secret"),
]

_SECRET_EXPLANATION = (
    "A credential written into source code is stored forever in Git history and is visible to "
    "everyone with access to the repository (and to the public if the repo is or becomes public). "
    "Bots scan GitHub continuously and abuse leaked keys within minutes."
)
_SECRET_FIX = (
    "1. Revoke / rotate this credential now - treat it as compromised.\n"
    "2. Load it from an environment variable or a git-ignored config file instead, e.g.\n"
    "       value = os.environ[\"MY_API_KEY\"]\n"
    "3. Commit a placeholder in an example file (e.g. config.example.json) and add the real file to .gitignore."
)

# ── Insecure code patterns ────────────────────────────────────────────────────
# Each rule: id, regex, exts (None = any text file), title, explanation, fix,
# reference, severity
_PY = (".py", ".pyw")
_JS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".html", ".htm")

CODE_RULES: List[Dict[str, Any]] = [
    {
        "id": "dynamic_code_exec", "exts": _PY,
        "regex": r"(?<![\w.])(?:eval|exec)\s*\(",
        "title": "Dynamic code execution (eval / exec)",
        "explanation": "eval/exec run arbitrary Python from a string. If any part of that string can be "
                       "influenced by a user, file or network response, an attacker can run their own code on this machine.",
        "fix": "Avoid executing strings. Use ast.literal_eval() for data, json.loads() for JSON, or a dispatch "
               "table (dict of allowed functions) instead of eval.",
        "reference": "CWE-95",
    },
    {
        "id": "shell_injection", "exts": _PY,
        "regex": r"\bsubprocess\.\w+\(.*shell\s*=\s*True",
        "title": "Command injection risk (shell=True)",
        "explanation": "With shell=True the command line is parsed by the shell. Unsanitised input such as "
                       "`; rm -rf /` or `& del` gets executed as an extra command.",
        "fix": "Pass the command as a list and drop shell=True:\n"
               "       subprocess.run([\"git\", \"status\", path], check=True)",
        "reference": "CWE-78",
    },
    {
        "id": "os_system", "exts": _PY,
        "regex": r"\bos\.(?:system|popen)\s*\(",
        "title": "Command injection risk (os.system / os.popen)",
        "explanation": "os.system hands a string to the shell, so any untrusted text inside it can inject extra commands.",
        "fix": "Use subprocess.run([...list of args...], check=True) without a shell.",
        "reference": "CWE-78",
    },
    {
        "id": "unsafe_deserialization", "exts": _PY,
        "regex": r"\b(?:pickle|cPickle|marshal|shelve)\.loads?\s*\(",
        "title": "Unsafe deserialization (pickle / marshal)",
        "explanation": "Loading a pickle can execute arbitrary code embedded in the data. Never unpickle data that "
                       "did not come from a fully trusted source.",
        "fix": "Use a data-only format such as JSON, or sign and verify the payload (hmac) before loading it.",
        "reference": "CWE-502",
    },
    {
        "id": "unsafe_yaml", "exts": _PY,
        "regex": r"\byaml\.load\s*\((?!.*(?:Safe|safe))",
        "title": "Unsafe YAML loading",
        "explanation": "yaml.load with the default loader can construct arbitrary Python objects, which allows code execution.",
        "fix": "Use yaml.safe_load(...) or pass Loader=yaml.SafeLoader.",
        "reference": "CWE-502",
    },
    {
        "id": "sql_injection", "exts": _PY,
        "skip_if": r"\?",
        "regex": r"""(?i)\.execute(?:many|script)?\s*\(\s*(?:f["']|["'][^"']*(?:select|insert|update|delete|drop|alter)[^"']*["']\s*(?:%|\+|\.format))""",
        "title": "SQL injection risk (query built from strings)",
        "explanation": "Building SQL with f-strings, % or + lets an attacker change the meaning of the query "
                       "(e.g. a name of `x'; DROP TABLE users;--`).",
        "fix": "Use parameter placeholders and pass values separately:\n"
               "       cur.execute(\"SELECT * FROM users WHERE name = ?\", (name,))\n"
               "   Table / column names cannot be parameters - validate them against a fixed allow-list.",
        "reference": "CWE-89",
    },
    {
        "id": "weak_hash", "exts": _PY,
        "regex": r"\bhashlib\.(?:md5|sha1)\s*\(",
        "title": "Weak hash algorithm (MD5 / SHA-1)",
        "explanation": "MD5 and SHA-1 are broken for security use - collisions can be forged and they are far too fast "
                       "for password hashing.",
        "fix": "Use hashlib.sha256 (or better) for integrity checks, and bcrypt / argon2 / scrypt for passwords. "
               "If this is only a non-security checksum, pass usedforsecurity=False to document it.",
        "reference": "CWE-327",
    },
    {
        "id": "tls_verify_off", "exts": _PY,
        "regex": r"\bverify\s*=\s*False|_create_unverified_context",  # nosec
        "title": "TLS certificate verification disabled",
        "explanation": "Without certificate verification anyone on the network path can impersonate the server "
                       "(man-in-the-middle) and read or alter the traffic.",
        "fix": "Remove the verify override. If you use a private CA, point to it: requests.get(url, verify=\"/path/ca.pem\").",
        "reference": "CWE-295",
    },
    {
        "id": "debug_enabled", "exts": _PY,
        "regex": r"\.run\s*\(.*debug\s*=\s*True|^\s*DEBUG\s*=\s*True\b",
        "title": "Debug mode enabled",
        "explanation": "Debug mode can expose an interactive console and stack traces with secrets to anyone who reaches the app.",
        "fix": "Read the flag from the environment (DEBUG = os.environ.get(\"DEBUG\") == \"1\") and keep it off in production.",
        "reference": "CWE-489",
    },
    {
        "id": "insecure_tempfile", "exts": _PY,
        "regex": r"\btempfile\.mktemp\s*\(",
        "title": "Insecure temporary file (mktemp)",
        "explanation": "mktemp only returns a name; another process can create that file first (race condition / symlink attack).",
        "fix": "Use tempfile.NamedTemporaryFile() or tempfile.mkstemp(), which create the file atomically.",
        "reference": "CWE-377",
    },
    {
        "id": "hardcoded_password", "exts": None,
        "regex": r"""(?i)\b(?:password|passwd|pwd)\b\s*[:=]\s*['"](?P<secret>[^'"\s]{4,})['"]""",
        "title": "Hardcoded password",
        "explanation": "A password in the source is shared with everyone who can read the code and is kept in Git history.",
        "fix": "Read it from an environment variable / secret store, or prompt for it at runtime.",
        "reference": "CWE-798",
        "mask": True,
    },
    {
        "id": "js_eval", "exts": _JS,
        "regex": r"(?<![\w.])eval\s*\(|new\s+Function\s*\(",
        "title": "Dynamic code execution in JavaScript",
        "explanation": "eval / new Function execute strings as code - a classic route for cross-site scripting.",
        "fix": "Parse data with JSON.parse and call functions directly instead of evaluating strings.",
        "reference": "CWE-95",
    },
    {
        "id": "js_xss", "exts": _JS,
        "regex": r"\.innerHTML\s*=|document\.write\s*\(|dangerouslySetInnerHTML",
        "title": "Cross-site scripting (XSS) risk",
        "explanation": "Writing untrusted text as HTML lets an attacker inject <script> tags or event handlers into the page.",
        "fix": "Use textContent (or your framework's escaping) instead of innerHTML. If HTML is required, "
               "sanitise it first with a library such as DOMPurify.",
        "reference": "CWE-79",
    },
]

# Files that should basically never be committed
SENSITIVE_FILE_NAMES = (".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc")
SENSITIVE_FILE_EXTS = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks")
SENSITIVE_FILE_SAFE = (".example", ".sample", ".template", ".dist")

# Merge conflict markers
CONFLICT_PATTERNS = [
    ("conflict_head", r"^<{7}\s+", "Git merge conflict marker (HEAD)"),
    ("conflict_middle", r"^={7}$", "Git merge conflict marker (separator)"),
    ("conflict_tail", r"^>{7}\s+", "Git merge conflict marker (branch/remote)"),
]

# Precompiled regexes for maximum performance
_COMPILED_CONFLICTS = [(cid, re.compile(pat), desc) for cid, pat, desc in CONFLICT_PATTERNS]
_COMPILED_SECRETS = [(stype, re.compile(pat), desc) for stype, pat, desc in SECRET_PATTERNS]
_COMPILED_RULES = [
    {
        **rule,
        "_rx": re.compile(rule["regex"]),
        "_skip_rx": re.compile(rule["skip_if"]) if rule.get("skip_if") else None,
    }
    for rule in CODE_RULES
]

_FILE_INSPECT_CACHE: Dict[str, Tuple[float, int, List[Dict[str, Any]]]] = {}

# Extensions safe to inspect as text
TEXT_EXTENSIONS = {
    ".py", ".pyw", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".html", ".htm", ".css", ".scss",
    ".md", ".txt", ".rst", ".sh", ".bat", ".ps1", ".sql", ".xml",
    ".csv", ".env", ".env.local", ".env.development", ".env.production",
}

# Large file limit (10MB)
LARGE_FILE_BYTES = 10 * 1024 * 1024

# Dangerous binary file extensions that are usually accidentally committed
ACCIDENTAL_BINARY_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".zip", ".tar", ".gz", ".7z", ".iso", ".bin"}

_PLACEHOLDER_HINTS = ("example", "dummy", "placeholder", "your_", "your-", "xxxx", "test", "changeme",
                      "<", "{", "$", "%s", "password", "secret", "****", "....", "none", "null",
                      "redact", "redacted", "token_redacted", "[token")


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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mask(value: str) -> str:
    """Keep the first 4 characters so the user can recognise the secret, hide the rest."""
    if len(value) <= 6:
        return "*" * len(value)
    return value[:4] + "*" * min(len(value) - 4, 12)


def _masked_line(line: str, match: Optional["re.Match"]) -> str:
    """Return the line with the secret portion masked."""
    if not match:
        return line
    try:
        start, end = match.span("secret")
    except IndexError:
        return line
    if start < 0:
        return line
    return line[:start] + _mask(line[start:end]) + line[end:]


def _context(lines: List[str], lineno: int, replace_line: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return the surrounding code of `lineno` (1-based) as [{line, text, hit}, ...]."""
    start = max(1, lineno - CONTEXT_RADIUS)
    end = min(len(lines), lineno + CONTEXT_RADIUS)
    ctx = []
    for n in range(start, end + 1):
        text = lines[n - 1].rstrip("\r\n")
        if n == lineno and replace_line is not None:
            text = replace_line
        elif n != lineno:
            # never leak a secret through the neighbouring lines
            text = _mask_known_secrets(text)
        ctx.append({"line": n, "text": text[:160], "hit": n == lineno})
    return ctx


def _mask_known_secrets(text: str) -> str:
    for _, pattern, _ in SECRET_PATTERNS:
        m = re.search(pattern, text)
        if m:
            text = _masked_line(text, m)
    return text


def _issue(rel_path: str, severity: str, itype: str, title: str, lineno: int, col: int,
           message: str, lines: List[str], snippet: Optional[str] = None,
           explanation: str = "", fix: str = "", reference: str = "",
           shown_line: Optional[str] = None, with_context: bool = True) -> Dict[str, Any]:
    if snippet is None:
        raw = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
        snippet = (shown_line if shown_line is not None else raw).strip()[:120]
    return {
        "file": rel_path,
        "severity": severity,
        "type": itype,
        "title": title,
        "line": lineno,
        "col": col,
        "message": message,
        "snippet": snippet,
        "context": _context(lines, lineno, shown_line) if (with_context and lines) else [],
        "explanation": explanation,
        "fix": fix,
        "reference": reference,
    }


def _is_placeholder(value: str) -> bool:
    low = value.lower()
    return any(h in low for h in _PLACEHOLDER_HINTS)


def _is_sensitive_filename(rel_path: str) -> bool:
    base = os.path.basename(rel_path).lower()
    if any(base.endswith(s) for s in SENSITIVE_FILE_SAFE):
        return False
    if base in SENSITIVE_FILE_NAMES or base.startswith(".env."):
        return True
    return os.path.splitext(base)[1] in SENSITIVE_FILE_EXTS


def _is_suppressed(line: str) -> bool:
    """Lines carrying `# nosec` or `commitmaster:ignore` are deliberately accepted by the developer."""
    low = line.lower()
    return "nosec" in low or "commitmaster:ignore" in low


def _is_comment(line: str, ext: str) -> bool:
    s = line.lstrip()
    if ext in _PY or ext in (".sh", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".ps1"):
        return s.startswith("#")
    if ext in _JS:
        return s.startswith("//") or s.startswith("*") or s.startswith("/*")
    return False


# ── Main inspection ───────────────────────────────────────────────────────────

def inspect_file(repo_path: str, rel_path: str) -> List[Dict[str, Any]]:
    """Inspect a single file for pre-commit issues (see module docstring for the issue format)."""
    full_path = os.path.normpath(os.path.join(repo_path, rel_path))

    # Deleted files need no syntax / leak check
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        return []

    try:
        st = os.stat(full_path)
        mtime, file_size = st.st_mtime, st.st_size
    except OSError as e:
        log.warning("Could not stat %s: %s", rel_path, e)
        return []

    if full_path in _FILE_INSPECT_CACHE:
        c_mtime, c_size, c_issues = _FILE_INSPECT_CACHE[full_path]
        if c_mtime == mtime and c_size == file_size:
            return list(c_issues)

    issues: List[Dict[str, Any]] = []

    _, ext = os.path.splitext(rel_path.lower())
    base_name = os.path.basename(rel_path)

    # 1. Oversized files
    if file_size > LARGE_FILE_BYTES:
        issues.append(_issue(
            rel_path, "warning", "large_file", "Very large file", 1, 0,
            f"Large file detected ({file_size / (1024 * 1024):.1f} MB). "
            "Storing large files in Git can bloat repository history.",
            [], snippet=f"File size: {file_size:,} bytes",
            explanation="Git keeps every version of every file forever, so large files make clones slow and cannot be "
                        "removed from history easily. GitHub rejects files above 100 MB.",
            fix="Add the file to .gitignore, or track it with Git LFS (git lfs track \"*." + (ext.lstrip('.') or 'bin') + "\").",
            reference="",
        ))

    # 2. Accidental binary executables / archives
    if ext in ACCIDENTAL_BINARY_EXTENSIONS and file_size > 1024 * 1024:
        issues.append(_issue(
            rel_path, "warning", "accidental_binary", "Binary file in source control", 1, 0,
            f"Binary archive/executable file ({ext}) detected. Verify this file belongs in source control.",
            [], snippet=f"Extension: {ext}",
            explanation="Build outputs and archives are usually generated artefacts; committing them bloats the "
                        "repository and they cannot be diffed or reviewed.",
            fix="Add it to .gitignore, or publish it as a GitHub Release asset instead.",
        ))

    # 3. Secret-bearing files (.env, private keys, ...)
    if _is_sensitive_filename(rel_path):
        issues.append(_issue(
            rel_path, "security", "sensitive_file", "Credential file about to be committed", 1, 0,
            f"'{base_name}' normally contains credentials and should not be committed.",
            [], snippet=f"{base_name}  (contents hidden)",
            explanation="Files such as .env, private keys and certificates hold secrets. Once pushed they are in the "
                        "repository history permanently, even if you delete the file later.",
            fix="1. Run: git rm --cached \"" + rel_path + "\"\n"
                "2. Add \"" + base_name + "\" to .gitignore.\n"
                "3. If it was already pushed, rotate every secret inside it.\n"
                "4. Keep a " + base_name + ".example with dummy values for teammates.",
            reference="CWE-538",
        ))

    # 4. Empty files
    if file_size == 0:
        ignored_empty_exts = (".db", ".db-wal", ".db-shm", ".db-journal", ".sqlite", ".sqlite3", ".lock", ".log")
        if base_name not in ("__init__.py", ".gitkeep", ".keep", ".gitignore") and ext not in ignored_empty_exts:
            issues.append(_issue(
                rel_path, "warning", "empty_file", "Empty file", 1, 0,
                "File is empty (0 bytes). Check if content was accidentally cleared.",
                [], snippet="(empty file)",
                explanation="An empty file is often the result of a failed save or an accidental select-all + delete.",
                fix="Open the file and confirm it should be empty; restore it with `git checkout -- <file>` if not.",
            ))
        res = issues[:MAX_ISSUES_PER_FILE + 5]
        _FILE_INSPECT_CACHE[full_path] = (mtime, file_size, res)
        return list(res)

    # Binary → skip text based checks
    if ext not in TEXT_EXTENSIONS and is_binary_file(full_path):
        res = issues[:MAX_ISSUES_PER_FILE + 5]
        _FILE_INSPECT_CACHE[full_path] = (mtime, file_size, res)
        return list(res)

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as exc:
        issues.append(_issue(
            rel_path, "error", "read_error", "File cannot be read", 1, 0,
            f"Could not read file: {exc}", [], snippet="",
            explanation="The file could not be opened - it may be locked by another program or have wrong permissions.",
            fix="Close programs that may be using the file and check its permissions.",
        ))
        res = issues[:MAX_ISSUES_PER_FILE + 5]
        _FILE_INSPECT_CACHE[full_path] = (mtime, file_size, res)
        return list(res)

    lines = content.splitlines()

    # 5. Merge conflict markers
    for lineno, line in enumerate(lines, start=1):
        for _, rx, cdesc in _COMPILED_CONFLICTS:
            if rx.search(line):
                issues.append(_issue(
                    rel_path, "error", "merge_conflict", "Unresolved merge conflict", lineno, 1,
                    f"Unresolved merge conflict marker found: {cdesc}", lines,
                    explanation="Git inserted these markers because two changes touched the same lines. Committing them "
                                "puts invalid text into the file and usually breaks the code.",
                    fix="Open the file, keep the correct version of the lines between <<<<<<< and >>>>>>>, "
                        "delete the three marker lines, then save.",
                ))
                break

    # 6. Secret / credential leaks
    is_test_or_example = any(k in rel_path.lower() for k in ("test", "example", "mock", "fixture"))
    for lineno, line in enumerate(lines, start=1):
        if len(issues) >= MAX_ISSUES_PER_FILE:
            break
        for stype, rx, sdesc in _COMPILED_SECRETS:
            match = rx.search(line)
            if not match:
                continue
            val = match.group("secret") if "secret" in match.groupdict() else match.group(0)
            if _is_placeholder(val):
                continue
            if is_test_or_example and len(val) < 25:
                continue
            issues.append(_issue(
                rel_path, "security", "secret_leak", sdesc, lineno, match.start("secret") + 1,
                f"Potential credential leak: {sdesc}", lines,
                shown_line=_masked_line(line, match),
                explanation=_SECRET_EXPLANATION, fix=_SECRET_FIX,
                reference="CWE-798",
            ))
            break

    # 7. Insecure code patterns
    for rule in _COMPILED_RULES:
        if rule["exts"] is not None and ext not in rule["exts"]:
            continue
        if ext in (".md", ".txt", ".rst", ".json", ".csv"):
            continue
        rx = rule["_rx"]
        skip_rx = rule["_skip_rx"]
        for lineno, line in enumerate(lines, start=1):
            if len(issues) >= MAX_ISSUES_PER_FILE:
                break
            if _is_comment(line, ext) or _is_suppressed(line):
                continue
            if skip_rx and skip_rx.search(line):
                continue
            m = rx.search(line)
            if not m:
                continue
            shown = None
            if rule.get("mask"):
                val = m.groupdict().get("secret") or ""
                if _is_placeholder(val) or (is_test_or_example and len(val) < 12):
                    continue
                shown = _masked_line(line, m)
            issues.append(_issue(
                rel_path, "security", "insecure_code", rule["title"], lineno, m.start() + 1,
                f"Security risk: {rule['title']}", lines, shown_line=shown,
                explanation=rule["explanation"], fix=rule["fix"], reference=rule["reference"],
            ))

    # 8. Syntax validation by file type
    if ext in (".py", ".pyw"):
        try:
            ast.parse(content, filename=rel_path)
        except SyntaxError as e:
            lineno = e.lineno or 1
            issues.insert(0, _issue(
                rel_path, "error", "python_syntax_error", "Python syntax error", lineno, e.offset or 0,
                f"Python Syntax Error: {e.msg} (line {lineno})", lines,
                snippet=(e.text or "").strip()[:120],
                explanation=f"Python cannot parse this file: {e.msg}. Importing or running it will crash immediately.",
                fix="Check the highlighted line and the lines just above it for a missing bracket, quote or colon, "
                    "then run `python -m py_compile " + rel_path + "` to confirm.",
            ))
        except Exception as exc:
            issues.insert(0, _issue(
                rel_path, "error", "python_parse_error", "Python parse failure", 1, 0,
                f"Python AST parse error: {exc}", lines, snippet="",
                explanation="The Python parser failed unexpectedly on this file.",
                fix="Try running `python -m py_compile " + rel_path + "` to see the exact error.",
            ))

    elif ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            issues.insert(0, _issue(
                rel_path, "error", "json_syntax_error", "Invalid JSON", e.lineno, e.colno,
                f"JSON Syntax Error: {e.msg} (line {e.lineno}, col {e.colno})", lines,
                explanation=f"The file is not valid JSON ({e.msg}). Programs reading it will fail.",
                fix="Look for a trailing comma, a missing quote or bracket near the highlighted line. "
                    "Pasting the file into a JSON validator will pinpoint the problem.",
            ))

    elif ext in (".yaml", ".yml"):
        for lineno, line in enumerate(lines, start=1):
            if line.startswith("\t") or (line.lstrip() != line and "\t" in line[:len(line) - len(line.lstrip())]):
                issues.insert(0, _issue(
                    rel_path, "error", "yaml_tab_error", "Tab used for YAML indentation", lineno, 1,
                    "YAML indentation error: tabs cannot be used for indentation in YAML files (use spaces)", lines,
                    explanation="The YAML specification forbids tab characters for indentation; parsers will reject the file.",
                    fix="Replace the leading tab(s) with spaces (2 spaces per level is the common convention).",
                ))
                break

    res = issues[:MAX_ISSUES_PER_FILE + 5]
    _FILE_INSPECT_CACHE[full_path] = (mtime, file_size, res)
    return list(res)


def inspect_files(repo_path: str, files: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Inspect multiple files and return mapping of { file_path: [issues] }.
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


def format_issue_report(issues_by_file: Dict[str, List[Dict[str, Any]]], repo_name: str = "") -> str:
    """Format a clean, comprehensive, and professional vulnerability and security audit log."""
    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    summary = summarize_issues(issues_by_file)
    total_files = len(issues_by_file)

    lines = [
        "=" * 80,
        "COMMITMASTER PRE-COMMIT HEALTH & VULNERABILITY AUDIT REPORT",
        f"Generated:   {now_str}",
        f"Repository:  {repo_name or 'Local Working Tree'}",
        f"Flagged:     {summary['total']} total issue(s) across {total_files} file(s)",
        f"Breakdown:   {summary['security']} Security / Secret Leaks | {summary['errors']} Critical / Syntax Errors | {summary['warnings']} Warnings",
        "=" * 80,
        "",
    ]

    for path, issues in issues_by_file.items():
        lines.append(f"[FILE: {path}] ({len(issues)} issue{'s' if len(issues) != 1 else ''})")
        lines.append("-" * 80)
        for idx, i in enumerate(issues, start=1):
            sev = i.get('severity', 'warning').upper()
            title = i.get('title') or i.get('message', 'Issue')
            line_no = i.get('line', 1)
            ref = f" [{i['reference']}]" if i.get("reference") else ""
            lines.append(f"  {idx}. [{sev}] {title} (Line {line_no}){ref}")

            ctx = i.get("context") or []
            if ctx:
                lines.append("     Code Context:")
                for c in ctx:
                    marker = ">" if c.get("hit") else " "
                    lines.append(f"       {marker} {c.get('line', ''):>4} | {c.get('text', '')}")
            elif i.get("snippet"):
                lines.append(f"     Snippet: {i['snippet']}")

            if i.get("explanation"):
                lines.append(f"     Why it matters: {i['explanation']}")
            if i.get("fix"):
                fix_lines = i["fix"].splitlines()
                lines.append(f"     Recommended Fix: {fix_lines[0]}")
                for fl in fix_lines[1:]:
                    lines.append(f"                      {fl}")
            lines.append("")
        lines.append("")

    lines.append("=" * 80)
    lines.append("End of CommitMaster Pre-Commit Vulnerability Log.")
    lines.append("=" * 80)
    return "\n".join(lines).strip()
