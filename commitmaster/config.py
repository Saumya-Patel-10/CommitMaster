"""Configuration loading/saving for CommitMaster.

Settings live in config.json next to the app. Every value is user-editable,
so nothing about your setup (watched apps, model name, folders) is hard-coded.
"""
import json
import os
import sys

CONFIG_FILE = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config.json")

DEFAULTS = {
    # Process names of coding apps to watch (Task Manager > Details to find these).
    "watched_apps": [
        "Code.exe",        # VS Code
        "Cursor.exe",      # Cursor
        "Antigravity.exe", # Antigravity IDE
        "Bionic.exe",      # Bionic (adjust if your build uses another name)
        "LM Studio.exe",
    ],
    # Root folders that contain your cloned GitHub repos.
    "projects_dirs": [],
    "poll_interval_seconds": 2,        # how often we check which apps are open
    "repo_scan_interval_seconds": 60,  # how often we scan repos while coding
    "session_end_grace_seconds": 120,  # apps must be closed this long before "done coding?" fires
    # Commit behaviour
    "auto_commit": False,              # True = skip preview, commit automatically
    "skip_sensitive_files": True,      # never auto-stage .env / keys / pem
    "sensitive_patterns": [".env", ".pem", ".key", "secret", "credential", ".p12", "id_rsa"],
    "github_desktop_path": "",         # auto-detected if empty
    # LM Studio local server (OpenAI-compatible). Model is auto-detected when
    # empty, so you can swap models in LM Studio without touching this file.
    "lm_studio": {
        "base_url": "http://localhost:1234/v1",
        "model": "",
        "timeout_seconds": 60,
    },
}


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            cfg = {}
    merged = _deep_merge(DEFAULTS, cfg)
    save_config(merged)  # keep the file in sync with defaults
    return merged


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _deep_merge(base, override):
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out