"""Commit message generation via Bionic / LM Studio's local OpenAI-compatible server.

Primary provider: Bionic (backed by LM Studio runtime) with Gemma-3-12b-it.
The model is auto-detected if config leaves it blank, so swapping models in
Bionic needs no code or config change.

The AI receives:
  - Repo name + branch
  - Full `git diff HEAD` (capped to avoid token overflows)
  - Untracked file names
  - A breakdown of which group each file belongs to

It returns a JSON array; we parse it tolerantly because local models sometimes
wrap JSON in markdown fences or extra prose.
"""
import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

import requests

from commitmaster.logger import get

log = get("ai_messages")

FALLBACK_MESSAGES = {
    "feat":  "feat: add new files",
    "code":  "refactor: update existing code",
    "test":  "test: update tests",
    "docs":  "docs: update documentation",
    "chore": "chore: update config / dependencies",
}

# ── Prompt ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a senior software engineer writing git commit messages. "
    "Follow the Conventional Commits specification exactly. "
    "Reply ONLY with a valid JSON array — no markdown fences, no prose."
)

USER_PROMPT = """\
Repository: {repo}
Branch: {branch}

=== Diff (truncated to {diff_chars} chars) ===
{diff}

=== Untracked / new files ===
{untracked}

=== Groups needing one commit message each ===
{groups}

Write ONE commit message per group.
Format: {{"group": "<group_name>", "message": "<type>: <imperative summary, ≤72 chars>"}}
Use types: feat, fix, refactor, docs, test, chore.
Reply with a JSON array of those objects, nothing else.
"""

_MAX_DIFF_CHARS = 8_000
_MAX_RETRIES = 2


# ── Public API ────────────────────────────────────────────────────────────────

_MODEL_CACHE: Dict[str, Any] = {
    "last_check": 0.0,
    "base_url": "",
    "models": [],
}


def list_models(cfg: dict, force: bool = False) -> List[str]:
    """Return model IDs available in Bionic / LM Studio ([] if unreachable)."""
    base = cfg.get("ai", {}).get("base_url", "http://localhost:1234/v1").rstrip("/")
    now = time.time()
    if not force and _MODEL_CACHE["base_url"] == base and (now - _MODEL_CACHE["last_check"] < 20.0):
        return list(_MODEL_CACHE["models"])

    try:
        r = requests.get(f"{base}/models", timeout=(0.4, 1.0))
        r.raise_for_status()
        models = [m["id"] for m in r.json().get("data", [])]
        _MODEL_CACHE["last_check"] = now
        _MODEL_CACHE["base_url"] = base
        _MODEL_CACHE["models"] = models
        return models
    except Exception as exc:
        log.debug("list_models failed: %s", exc)
        _MODEL_CACHE["last_check"] = now
        _MODEL_CACHE["base_url"] = base
        _MODEL_CACHE["models"] = []
        return []


def detect_model(cfg: dict, force: bool = False) -> Optional[str]:
    """Return the first model loaded in Bionic / LM Studio, or None."""
    cfg_model = cfg.get("ai", {}).get("model")
    if cfg_model:
        return cfg_model
    models = list_models(cfg, force=force)
    if models:
        log.debug("Auto-detected model: %s", models[0])
        return models[0]
    return None


def test_connection(cfg: dict) -> tuple[bool, str]:
    """Returns (ok, message) for the Settings 'Test connection' button."""
    model = cfg.get("ai", {}).get("model") or detect_model(cfg, force=True)
    if model:
        return True, f"Connected ✔\nModel in use: {model}"
    base = cfg.get("ai", {}).get("base_url", "http://localhost:1234/v1")
    return False, (
        f"Could not reach the AI server at {base}.\n\n"
        "Make sure Bionic / LM Studio is running and the local server is started."
    )


def generate_messages(cfg: dict, repo_path: str, groups: Dict[str, List[str]]) -> Dict[str, str]:
    """
    groups: {group_name: [file_paths]} — 'sensitive' group is skipped.
    Returns {group_name: commit_message_string}.
    Falls back to FALLBACK_MESSAGES if the AI is unavailable or returns bad JSON.
    """
    from commitmaster import commit_engine  # local import to avoid circular

    result = {g: FALLBACK_MESSAGES.get(g, "chore: update files")
              for g in groups if g != "sensitive"}

    model = cfg["ai"].get("model") or detect_model(cfg)
    if not model:
        log.warning("No AI model available — using fallback messages.")
        return result

    # Build diff context
    try:
        diff_text = commit_engine.diff_summary(repo_path, max_chars=_MAX_DIFF_CHARS)
        untracked = commit_engine.git(repo_path, "ls-files", "--others", "--exclude-standard")
    except Exception as exc:
        log.warning("Could not build diff context: %s", exc)
        diff_text, untracked = "(diff unavailable)", ""

    groups_block = "\n".join(
        f"- {g}: {', '.join(files[:30])}"  # cap file list per group
        for g, files in groups.items()
        if g != "sensitive" and files
    )

    prompt = USER_PROMPT.format(
        repo=commit_engine.repo_name(repo_path),
        branch=commit_engine.current_branch(repo_path),
        diff=diff_text,
        diff_chars=_MAX_DIFF_CHARS,
        untracked=untracked.strip() or "(none)",
        groups=groups_block,
    )

    base = cfg["ai"]["base_url"].rstrip("/")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 600,
        "stream": False,
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            log.info("Calling AI model '%s' (attempt %d)…", model, attempt)
            resp = requests.post(
                f"{base}/chat/completions",
                json=payload,
                timeout=cfg["ai"]["timeout_seconds"],
            )
            resp.raise_for_status()
            msg_obj = resp.json()["choices"][0]["message"]
            raw = (msg_obj.get("content") or "").strip()
            if not raw and "reasoning_content" in msg_obj:
                raw = (msg_obj.get("reasoning_content") or "").strip()
            log.debug("Raw AI response: %s", raw[:500])
            parsed = _parse_json(raw)
            _apply_parsed(parsed, groups, result)
            log.info("AI messages generated successfully.")
            return result
        except requests.Timeout:
            log.warning("AI request timed out (attempt %d/%d).", attempt, _MAX_RETRIES)
            if attempt < _MAX_RETRIES:
                time.sleep(2)
        except requests.RequestException as exc:
            log.error("AI request failed: %s", exc)
            break
        except (KeyError, IndexError, ValueError) as exc:
            log.error("Could not parse AI response: %s", exc)
            break

    log.warning("Returning fallback commit messages.")
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_json(text: str) -> list:
    """Tolerant JSON extraction — strips markdown fences if present."""
    # Strip ```json ... ``` fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # Find first [...] array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in model output: {text[:200]!r}")
    return json.loads(match.group(0))


def _apply_parsed(parsed: list, groups: Dict[str, List[str]], result: Dict[str, str]) -> None:
    """Map AI response items back to group names (tolerant matching)."""
    for item in parsed:
        group = item.get("group", "").strip()
        message = item.get("message", "").strip()
        if not message:
            continue
        if group in result:
            result[group] = message
        else:
            # Fuzzy match: if group name contains a known group key, use it
            for known in result:
                if known in group.lower() or group.lower() in known:
                    result[known] = message
                    break



# ══════════════════════════════════════════════════════════════════════════════
# Per-file commit messages  →  Summary (highlight) + Description (exact changes)
# ══════════════════════════════════════════════════════════════════════════════
#
# Every selected file is analysed in isolation: the model only ever sees the diff
# of ONE file, so a message can never be mixed up with another file's changes.

FILE_SYSTEM_PROMPT = (
    "You are a senior software engineer who writes precise, professional git commit messages. "
    "You describe ONLY what is visible in the diff you are given. "
    "Reply ONLY with a valid JSON object - no markdown fences, no extra prose."
)

FILE_USER_PROMPT = """\
Repository: {repo}   Branch: {branch}

You are writing the commit message for exactly ONE file.
File: {path}
Change type: {status}

=== Diff of this file only ===
{diff}

{others}Write:
  "summary":     a Conventional Commit headline, <= 72 chars, format "<type>(<scope>): <imperative highlight>".
                 State the PURPOSE / OUTCOME of the change clearly (imperative mood), not just naming the file.
                 Good: "feat(auth): add token refresh with retry on 401"
                 Bad:  "refactor(login): update login_window"
                 Types: feat, fix, refactor, perf, docs, test, chore, style.
  "description": Professional markdown description formatted with clear subsections:
                 - If new features/classes/functions/capabilities were added, MUST include a dedicated subsection:
                   "### New Features"
                   followed by concise bullet points ("- ...") describing each new capability.
                 - For modifications or refactoring to existing logic, include:
                   "### Changes & Improvements"
                   followed by concise bullet points ("- ...") explaining the updates.
                 - For bug or security fixes, include:
                   "### Bug Fixes & Security"
                 - For deletions, include:
                   "### Removals"
                 Never mention other files. Keep bullets concise, informative, and professional.

Reply with JSON only:
{{"summary": "...", "description": "### New Features\\n- ...\\n\\n### Changes & Improvements\\n- ..."}}
"""

UNIFIED_USER_PROMPT = """\
Repository: {repo}   Branch: {branch}

These files are being committed together. Per-file summaries:
{items}

Write ONE Conventional Commit headline (<= 72 chars, "<type>(<scope>): <imperative highlight>") that captures the
overall purpose of the whole change. Do not list file names.
Reply with JSON only: {{"summary": "..."}}
"""

_PER_FILE_DIFF_CHARS = 6_000
_CONVENTIONAL = re.compile(r"^(feat|fix|refactor|perf|docs|test|tests|chore|style|build|ci|revert)(\([^)]+\))?!?:\s+\S", re.I)
_GENERIC_SUMMARY = re.compile(
    r"^\w+(\([^)]*\))?!?:\s*(update|updated|modify|modified|change|changed|edit|edited|fix|tweak)\s+[\w./\\ -]+\.\w{1,5}\s*$",
    re.I,
)
_CONFIG_EXTS = (".json", ".toml", ".yml", ".yaml", ".ini", ".cfg", ".lock", ".env", ".gitignore", ".txt")
_DOC_EXTS = (".md", ".rst", ".txt")


class _AIUnavailable(Exception):
    """Raised when the AI server cannot be reached - stops further per-file attempts."""


def compose_commit_message(summary: str, description: str = "") -> str:
    """Join summary + description into the final git commit message."""
    summary = (summary or "").strip()
    description = (description or "").strip()
    return f"{summary}\n\n{description}" if description else summary


def generate_file_comments(
    cfg: dict,
    repo_path: str,
    files: Optional[List[str]] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Generate a Summary + Description for every file in `files` (and only those files).

    Returns:
    {
        "headline":          unified summary (for a single combined commit),
        "description":       unified description (per-file sections),
        "file_comments":     {path: summary},
        "file_descriptions": {path: description},
    }
    """
    from commitmaster import commit_engine

    try:
        changes = {p: st for st, p in commit_engine.uncommitted_changes(repo_path)}
    except Exception as exc:
        log.debug("Could not read status: %s", exc)
        changes = {}

    if not files:
        files = list(changes)
    seen = set()
    files = [f for f in files if not (f in seen or seen.add(f))]

    if not files:
        return {"headline": "chore: update repository", "description": "No modified files found.",
                "file_comments": {}, "file_descriptions": {}}

    model = cfg.get("ai", {}).get("model") or detect_model(cfg)
    if not model:
        log.info("Local AI offline or not detected - using diff-based heuristic messages.")

    repo = commit_engine.repo_name(repo_path)
    branch = commit_engine.current_branch(repo_path)
    sensitive = cfg.get("sensitive_patterns", [])

    per_file: Dict[str, Dict[str, str]] = {}
    for idx, f in enumerate(files):
        if progress:
            try:
                progress(idx, len(files), f)
            except Exception:
                pass
        status = changes.get(f, "M")

        if any(s in f.lower().replace("\\", "/") for s in sensitive):
            per_file[f] = {
                "summary": "chore(config): update protected configuration",
                "description": "- Sensitive file - content intentionally not analysed or shared with the AI",
            }
            continue

        full_diff = commit_engine.file_diff(repo_path, f, max_chars=400_000)
        diff = full_diff[:_PER_FILE_DIFF_CHARS]          # what the model gets to read
        facts = _analyze_diff(full_diff, f, status)      # statistics use the whole diff

        result = None
        if model:
            try:
                result = _ai_message_for_file(cfg, model, repo, branch, f, status, diff, files, facts)
            except _AIUnavailable:
                model = None            # don't wait for a timeout on every remaining file
            except Exception as exc:
                log.warning("AI message for %s failed: %s", f, exc)
        per_file[f] = result or _heuristic_message(f, status, facts)

    headline = _unified_summary(cfg, model, repo, branch, per_file)
    return {
        "headline": headline,
        "description": _unified_description(per_file),
        "file_comments": {f: m["summary"] for f, m in per_file.items()},
        "file_descriptions": {f: m["description"] for f, m in per_file.items()},
    }


# ── AI calls ──────────────────────────────────────────────────────────────────

def _chat_json(cfg: dict, model: str, system: str, user: str, max_tokens: int) -> dict:
    base = cfg.get("ai", {}).get("base_url", "http://localhost:1234/v1").rstrip("/")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    timeout = cfg.get("ai", {}).get("timeout_seconds", 120)
    try:
        resp = requests.post(f"{base}/chat/completions", json=payload, timeout=timeout)
        resp.raise_for_status()
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise _AIUnavailable(str(exc))
    msg_obj = resp.json()["choices"][0]["message"]
    raw = (msg_obj.get("content") or "").strip()
    if not raw and msg_obj.get("reasoning_content"):
        raw = msg_obj["reasoning_content"].strip()
    log.debug("Raw AI response: %s", raw[:300])
    return _extract_json_object(raw)


def _extract_json_object(text: str) -> dict:
    clean = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in model output: {text[:120]!r}")
    return json.loads(match.group(0))


def _ai_message_for_file(cfg, model, repo, branch, path, status, diff, all_files, facts) -> Optional[Dict[str, str]]:
    base = os.path.basename(path)
    other_names = [os.path.basename(o) for o in all_files if o != path]
    others = ""
    if other_names:
        others = ("Other files exist in this working tree but are committed separately - never mention them: "
                  + ", ".join(other_names[:15]) + "\n\n")
    prompt = FILE_USER_PROMPT.format(
        repo=repo, branch=branch, path=path, base=base,
        status=_STATUS_WORDS.get(status, "modified"), diff=diff or "(no textual diff)", others=others,
    )
    data = _chat_json(cfg, model, FILE_SYSTEM_PROMPT, prompt, max_tokens=500)

    summary = _clean_summary(str(data.get("summary", "")), path, facts)
    desc = data.get("description", "")
    if isinstance(desc, list):
        desc = "\n".join(str(d) for d in desc)
    desc = _clean_description(str(desc), path, other_names)
    fallback = _heuristic_message(path, status, facts)
    if not summary or _GENERIC_SUMMARY.match(summary):
        summary = fallback["summary"]
    if not desc:
        desc = fallback["description"]
    return {"summary": summary, "description": desc}


def _unified_summary(cfg, model, repo, branch, per_file) -> str:
    if len(per_file) == 1:
        return next(iter(per_file.values()))["summary"]
    if model:
        items = "\n".join(f"- {os.path.basename(f)}: {m['summary']}" for f, m in per_file.items())
        try:
            data = _chat_json(cfg, model, FILE_SYSTEM_PROMPT,
                              UNIFIED_USER_PROMPT.format(repo=repo, branch=branch, items=items), max_tokens=150)
            s = _clean_summary(str(data.get("summary", "")), "", {})
            if s and _CONVENTIONAL.match(s):
                return s
        except Exception as exc:
            log.debug("Unified summary AI failed: %s", exc)
    return _heuristic_unified_summary(per_file)


def _heuristic_unified_summary(per_file: Dict[str, Dict[str, str]]) -> str:
    types: Dict[str, int] = {}
    for m in per_file.values():
        t = (m["summary"].split(":", 1)[0].split("(")[0] or "chore").lower()
        types[t] = types.get(t, 0) + 1
    priority = ["feat", "fix", "perf", "refactor", "docs", "test", "chore"]
    main = max(types, key=lambda t: (types[t], -priority.index(t) if t in priority else -99))
    bodies = [m["summary"].split(":", 1)[-1].strip() for m in per_file.values()]
    first = bodies[0]
    n = len(bodies)
    text = f"{main}: {first}" + (f" and {n - 1} related change{'s' if n > 2 else ''}" if n > 1 else "")
    if len(text) > 72:
        stems = ", ".join(os.path.splitext(os.path.basename(f))[0] for f in list(per_file)[:3])
        text = f"{main}: update {n} files ({stems}{'…' if n > 3 else ''})"
    return _truncate(text, 72)


def _unified_description(per_file: Dict[str, Dict[str, str]]) -> str:
    blocks = []
    for f, m in per_file.items():
        desc = m.get("description", "").strip()
        blocks.append(f"## 📄 {f}\n{desc}".strip())
    return "\n\n".join(blocks)


# ── Cleaning / validation ─────────────────────────────────────────────────────

_STATUS_WORDS = {"M": "modified", "MM": "modified", "A": "new file", "AM": "new file", "??": "new file",
                 "D": "deleted", "R": "renamed", "U": "conflicted"}


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    if " " in cut[limit // 2:]:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-") + "…"


def _clean_summary(text: str, path: str, facts: dict) -> str:
    s = text.strip().splitlines()[0].strip() if text.strip() else ""
    s = s.strip("`\"' ").rstrip(".")
    if not s:
        return ""
    if path and not _CONVENTIONAL.match(s):
        ftype, scope = _guess_type(path, facts.get("status", "M"), facts), _scope_for(path)
        s = f"{ftype}({scope}): {s[0].lower() + s[1:]}"
    return _truncate(s, 72)


def _clean_description(text: str, path: str, other_basenames: List[str]) -> str:
    lines = []
    for raw in text.replace("\\n", "\n").splitlines():
        line = raw.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if any(len(b) > 3 and b.lower() in line.lower() for b in other_basenames):
            continue                      # never let another file leak in
        if line.startswith("#"):
            lines.append(line)
        else:
            cleaned = re.sub(r"^[\-\*\u2022\d.\)\s]+", "", line).strip()
            if cleaned:
                lines.append("- " + cleaned[0].upper() + cleaned[1:])
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines[:25])


# ── Diff analysis + heuristic fallback ───────────────────────────────────────

_SYM_RX = re.compile(
    r"^[+-]\s*(?:export\s+)?(?:async\s+)?(?:(def|class|function)\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\(|function))"
)
_HUNK_RX = re.compile(r"^@@[^@]*@@\s*(?:async\s+)?(?:export\s+)?(?:(def|class|function)\s+(\w+))")
_HEADING_RX = re.compile(r"^([+-])\s{0,3}#{1,4}\s+(.+)$")


def _analyze_diff(diff: str, path: str, status: str) -> dict:
    added = removed = 0
    add_syms: List[tuple] = []
    rem_syms: List[tuple] = []
    ctx_syms: List[str] = []
    headings_added: List[str] = []
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
        m = _SYM_RX.match(line)
        if m:
            kind = m.group(1) or "function"
            name = m.group(2) or m.group(3)
            (add_syms if line[0] == "+" else rem_syms).append((kind, name))
            continue
        h = _HUNK_RX.match(line)
        if h:
            ctx_syms.append(h.group(2))
            continue
        hd = _HEADING_RX.match(line)
        if hd and hd.group(1) == "+" and path.lower().endswith(_DOC_EXTS):
            headings_added.append(hd.group(2).strip())
    added_names = {n for _, n in add_syms}
    removed_names = {n for _, n in rem_syms}
    return {
        "status": status,
        "added": added,
        "removed": removed,
        "new_syms": [(k, n) for k, n in add_syms if n not in removed_names],
        "gone_syms": [(k, n) for k, n in rem_syms if n not in added_names],
        "touched": list(dict.fromkeys(
            [n for _, n in add_syms if n in removed_names] +
            [n for n in ctx_syms if n not in added_names and n not in removed_names])),
        "headings": headings_added,
    }


def _scope_for(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem in ("__init__", "index", "main") or not stem:
        parent = os.path.basename(os.path.dirname(path.replace("\\", "/")))
        stem = parent or stem or "repo"
    return stem.lstrip(".") or "repo"


def _guess_type(path: str, status: str, facts: dict) -> str:
    low = path.lower().replace("\\", "/")
    base = os.path.basename(low)
    if "test" in low:
        return "test"
    if low.endswith(_DOC_EXTS) and base not in ("requirements.txt",) or low.startswith("docs/"):
        return "docs"
    if low.endswith(_CONFIG_EXTS) or base.startswith(".") or base in ("requirements.txt", "dockerfile"):
        return "chore"
    if low.endswith((".css", ".scss")):
        return "style"
    if status in ("??", "A", "AM") or facts.get("new_syms"):
        return "feat"
    return "refactor"


def _humanize(path: str) -> str:
    return _scope_for(path).replace("_", " ").replace("-", " ")


def _names(items, limit=2) -> str:
    names = [n for _, n in items] if items and isinstance(items[0], tuple) else list(items)
    shown = [f"`{n}`" for n in names[:limit]]
    if len(names) > limit:
        shown.append(f"{len(names) - limit} more")
    if len(shown) > 1:
        return ", ".join(shown[:-1]) + " and " + shown[-1]
    return shown[0] if shown else ""


def _heuristic_message(path: str, status: str, facts: dict) -> Dict[str, str]:
    facts = dict(facts or {})
    facts.setdefault("status", status)
    ftype = _guess_type(path, status, facts)
    scope = _scope_for(path)
    human = _humanize(path)
    new_syms, touched, gone = facts.get("new_syms", []), facts.get("touched", []), facts.get("gone_syms", [])
    added, removed = facts.get("added", 0), facts.get("removed", 0)
    is_new = status in ("??", "A", "AM")

    def _is_dunder(name: str) -> bool:
        return name.startswith("__") and name.endswith("__")

    major_new = [s for s in new_syms if not _is_dunder(s[1]) and not s[1].startswith("_")]
    minor_new = [s for s in new_syms if not _is_dunder(s[1]) and s[1].startswith("_")]
    dunder_new = [s for s in new_syms if _is_dunder(s[1])]
    headline_syms = major_new if major_new else (minor_new if minor_new else dunder_new)
    meaningful_touched = [n for n in touched if not _is_dunder(n)]
    if not meaningful_touched:
        meaningful_touched = touched

    def build(limit: int) -> str:
        if status == "D":
            return f"remove {human}"
        if is_new:
            if ftype == "docs":
                return f"add {human} documentation"
            if major_new:
                classes = [n for k, n in major_new if k == "class"]
                if classes:
                    return f"implement `{classes[0]}` component"
                return f"add {_names(major_new, limit)}"
            return f"introduce {human}"
        if ftype == "docs":
            heads = facts.get("headings") or []
            return f"update {human} documentation" + (f" - {heads[0][:26]}" if heads else "")
        if major_new:
            classes = [n for k, n in major_new if k == "class"]
            if classes:
                return f"implement `{classes[0]}` component"
            return f"add {_names(major_new, limit)}"
        if meaningful_touched:
            names_str = _names(meaningful_touched, limit)
            return f"refine {names_str} logic"
        if ftype == "chore":
            return f"update {human} configuration"
        if ftype == "test":
            return f"update {human} tests"
        return f"enhance {human} logic (+{added}/-{removed} lines)"

    if status == "D":
        ftype = "chore"
    summary = ""
    for limit in (2, 1):
        summary = f"{ftype}({scope}): {build(limit)}"
        if len(summary) <= 72:
            break
    summary = _truncate(summary, 72)

    sections: List[str] = []
    base = os.path.basename(path)
    kind_word = {"def": "function", "function": "function", "class": "class"}

    # Subsection 1: New Features (Prominently highlighted if present)
    new_feature_bullets = []
    if is_new:
        new_feature_bullets.append(f"Introduces `{base}` module ({added} line{'s' if added != 1 else ''})")
    for kind, name in major_new[:6]:
        k = kind_word.get(kind, kind)
        new_feature_bullets.append(f"Adds {k} `{name}`")
    for kind, name in minor_new[:3]:
        k = kind_word.get(kind, kind)
        new_feature_bullets.append(f"Adds helper {k} `{name}`")
    for kind, name in dunder_new[:2]:
        new_feature_bullets.append(f"Implements `{name}` method")

    if new_feature_bullets:
        sections.append("### New Features\n" + "\n".join(f"- {b}" for b in new_feature_bullets))

    # Subsection 2: Changes & Improvements
    change_bullets = []
    for name in meaningful_touched[:5]:
        change_bullets.append(f"Updates logic in `{name}`")
    for h in (facts.get("headings") or [])[:3]:
        change_bullets.append(f"Documents \"{h[:60]}\"")
    if not new_feature_bullets and not change_bullets and status != "D":
        change_bullets.append(f"Refines implementation details in `{base}`")

    if change_bullets:
        sections.append("### Changes & Improvements\n" + "\n".join(f"- {b}" for b in change_bullets))

    # Subsection 3: Removals & Deprecations (if any)
    removal_bullets = []
    if status == "D":
        removal_bullets.append(f"Removes `{base}` from the project repository")
    for kind, name in gone[:4]:
        k = kind_word.get(kind, kind)
        removal_bullets.append(f"Removes {k} `{name}`")

    if removal_bullets:
        sections.append("### Removals & Deprecations\n" + "\n".join(f"- {b}" for b in removal_bullets))

    # Subsection 4: Metrics / Summary
    if status != "D":
        stats_line = f"{added} line{'s' if added != 1 else ''} added, {removed} removed across {path}"
        sections.append(f"### Changes Summary\n- {stats_line}")

    description = "\n\n".join(sections)
    return {"summary": summary, "description": description}
