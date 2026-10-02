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
import re
import time
from typing import Dict, List, Optional

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

def list_models(cfg: dict) -> List[str]:
    """Return model IDs available in Bionic / LM Studio ([] if unreachable)."""
    base = cfg["ai"]["base_url"].rstrip("/")
    try:
        r = requests.get(f"{base}/models", timeout=5)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]
    except Exception as exc:
        log.debug("list_models failed: %s", exc)
        return []


def detect_model(cfg: dict) -> Optional[str]:
    """Return the first model loaded in Bionic / LM Studio, or None."""
    models = list_models(cfg)
    if models:
        log.debug("Auto-detected model: %s", models[0])
        return models[0]
    return None


def test_connection(cfg: dict) -> tuple[bool, str]:
    """Returns (ok, message) for the Settings 'Test connection' button."""
    model = cfg["ai"].get("model") or detect_model(cfg)
    if model:
        return True, f"Connected ✔\nModel in use: {model}"
    base = cfg["ai"]["base_url"]
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
            raw = resp.json()["choices"][0]["message"]["content"]
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