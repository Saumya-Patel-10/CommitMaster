"""Commit message generation via LM Studio's local OpenAI-compatible server.

The model name is read from config; if empty (or unknown) we auto-detect the
model currently loaded in LM Studio, so you can swap Gemma -> anything else
without touching code or config.
"""
import json
import re

import requests

from commitmaster import commit_engine

FALLBACK_MESSAGES = {
    "feat": "feat: add new files",
    "code": "chore: update existing code",
    "test": "test: update tests",
    "docs": "docs: update documentation",
    "chore": "chore: update config files",
}

PROMPT = """You are a senior engineer writing git commit messages.
For each group of changed files below, write ONE concise conventional-commit
message (format: "type: short imperative summary", max 72 chars).
Use types: feat, fix, refactor, docs, test, chore.
Reply ONLY with a JSON array like:
[{"files": ["a.py"], "message": "feat: add login validation"}]

Repository: {repo}
Branch: {branch}

{context}

Groups of files needing messages:
{groups}
"""


def list_models(cfg):
    """All model ids currently available in LM Studio ([] if unreachable)."""
    base = cfg["lm_studio"]["base_url"].rstrip("/")
    try:
        r = requests.get(f"{base}/models", timeout=5)
        return [m["id"] for m in r.json().get("data", [])]
    except (requests.RequestException, ValueError):
        return []


def detect_model(cfg):
    models = list_models(cfg)
    return models[0] if models else None


def generate_messages(cfg, repo_path, groups):
    """groups: {group_name: [files]} -> {group_name: message}"""
    files_block = "\n".join(
        f"- {g}: {', '.join(files)}" for g, files in groups.items() if g != "sensitive"
    )
    model = cfg["lm_studio"]["model"] or detect_model(cfg)
    if not model:
        return {g: FALLBACK_MESSAGES.get(g, "chore: update files") for g in groups}

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You output only valid JSON. No prose."},
            {"role": "user", "content": PROMPT.format(
                repo=commit_engine.repo_name(repo_path),
                branch=commit_engine.current_branch(repo_path),
                context=commit_engine.diff_summary(repo_path),
                groups=files_block,
            )},
        ],
        "temperature": 0.3,
        "max_tokens": 500,
        "stream": False,
    }
    base = cfg["lm_studio"]["base_url"].rstrip("/")
    try:
        r = requests.post(f"{base}/chat/completions", json=payload,
                          timeout=cfg["lm_studio"]["timeout_seconds"])
        content = r.json()["choices"][0]["message"]["content"]
        messages = _parse_json(content)
        result = {g: FALLBACK_MESSAGES.get(g, "chore: update files")
                  for g in groups if g != "sensitive"}
        for item in messages:
            for f in item.get("files", []):
                for g, group_files in groups.items():
                    if f in group_files and g in result:
                        result[g] = item["message"].strip()
        return result
    except (requests.RequestException, KeyError, ValueError, IndexError):
        # LM Studio offline or bad output -> deterministic fallbacks
        return {g: FALLBACK_MESSAGES.get(g, "chore: update files") for g in groups}


def _parse_json(text):
    """Tolerant JSON extraction -- local models sometimes wrap JSON in prose."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON array in model output")
    return json.loads(match.group(0))