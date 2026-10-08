"""Configuration loading/saving for CommitMaster.

Settings live in config.json next to the app.  A singleton ConfigManager
keeps an in-memory copy and re-reads it from disk whenever the file changes,
so Settings-UI saves are instantly visible to the monitor — no restart needed.
"""
import json
import os
import sys
import threading
import time
from typing import Any, Dict

from commitmaster.logger import get

log = get("config")

CONFIG_FILE = os.path.join(
    getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config.json",
)

DEFAULTS: Dict[str, Any] = {
    # Process names of coding apps to watch (Task Manager → Details to find these).
    "watched_apps": [
        "Code.exe",         # VS Code
        "Cursor.exe",       # Cursor
        "Antigravity.exe",  # Antigravity IDE
        "pycharm64.exe",    # PyCharm
        "idea64.exe",       # IntelliJ IDEA
        "sublime_text.exe", # Sublime Text
        "devenv.exe",       # Visual Studio
        "webstorm64.exe",   # WebStorm
        "clion64.exe",      # CLion
        "zed.exe",          # Zed
        "Bionic.exe",       # Bionic
        "LM Studio.exe",    # LM Studio
    ],
    # Root folders that contain your cloned GitHub repos.
    "projects_dirs": [],
    "poll_interval_seconds": 2,        # how often we check which apps are open
    "repo_scan_interval_seconds": 60,  # how often we scan repos while coding
    "session_end_grace_seconds": 120,  # apps must be closed this long before prompt fires
    # Commit reminder notification configuration
    "reminder": {
        "interval_enabled": True,
        "interval_hours": 1,
        "interval_minutes": 0,
        "app_monitor_enabled": True,
        "only_if_dirty": True,
    },
    # Commit behaviour
    "auto_commit": False,              # True = skip preview, commit automatically
    "skip_sensitive_files": True,      # never auto-stage .env / keys / pem
    "sensitive_patterns": [".env", ".pem", ".key", "secret", "credential", ".p12", "id_rsa"],
    "github_desktop_path": "",         # auto-detected if empty
    "server_url": "",                  # Central Cloud Server URL (e.g. https://your-server.onrender.com or empty for local)
    # AI Provider configuration: Bionic/LM Studio, OpenAI, Claude, Gemini, Ollama
    "ai": {
        "provider": "bionic",         # "bionic" | "openai" | "claude" | "gemini" | "ollama"
        "base_url": "http://localhost:1234/v1",
        "model": "",                  # blank = auto-detect or provider default
        "timeout_seconds": 90,
        "openai_api_key": "",
        "claude_api_key": "",
        "gemini_api_key": "",
        "openai_model": "gpt-4o-mini",
        "claude_model": "claude-3-5-haiku-20241022",
        "gemini_model": "gemini-1.5-flash",
        "openai_base_url": "https://api.openai.com/v1",
        "api_key": "",
    },
    # Legacy key — kept so old config.json files still work.
    "lm_studio": {
        "base_url": "http://localhost:1234/v1",
        "model": "",
        "timeout_seconds": 60,
    },
}

# Supported AI provider labels and default models
AI_PROVIDER_NAMES = {
    "bionic": "Local (Bionic / LM Studio)",
    "openai": "OpenAI",
    "claude": "Anthropic Claude",
    "gemini": "Google Gemini",
    "ollama": "Local (Ollama)",
}

AI_DEFAULT_MODELS = {
    "bionic": "",
    "openai": "gpt-4o-mini",
    "claude": "claude-3-5-haiku-20241022",
    "gemini": "gemini-1.5-flash",
    "ollama": "llama3.2",
}

AI_MODEL_PRESETS = {
    "openai": ["gpt-4o-mini", "gpt-4o", "o3-mini", "gpt-4-turbo"],
    "claude": ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
    "gemini": ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
    "bionic": ["(auto-detect loaded model)"],
    "ollama": ["llama3.2", "codellama", "mistral", "deepseek-coder"],
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> Dict[str, Any]:
    """Read config.json and merge with defaults.  Does NOT auto-save."""
    cfg: dict = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read config.json (%s) — using defaults.", exc)
    merged = _deep_merge(DEFAULTS, cfg)
    # Back-compat: if old lm_studio key present and new ai key is default, migrate.
    if "lm_studio" in cfg and cfg["lm_studio"].get("base_url"):
        ls = cfg["lm_studio"]
        if merged["ai"]["base_url"] == DEFAULTS["ai"]["base_url"]:
            merged["ai"]["base_url"] = ls["base_url"]
        if not merged["ai"]["model"] and ls.get("model"):
            merged["ai"]["model"] = ls["model"]
    return merged


def save_config(cfg: Dict[str, Any]) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        log.debug("Config saved to %s", CONFIG_FILE)
    except OSError as exc:
        log.error("Failed to save config: %s", exc)


# ---------------------------------------------------------------------------
# Singleton hot-reload manager
# ---------------------------------------------------------------------------

class ConfigManager:
    """Thread-safe config wrapper that auto-reloads when config.json changes."""

    def __init__(self):
        self._lock = threading.RLock()
        self._cfg: Dict[str, Any] = load_config()
        self._mtime: float = self._file_mtime()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True, name="cfg-watcher")
        self._thread.start()
        log.debug("ConfigManager started (watching %s)", CONFIG_FILE)

    # Public API -------------------------------------------------------

    def get(self) -> Dict[str, Any]:
        """Return the current (possibly freshly-reloaded) config dict."""
        with self._lock:
            return dict(self._cfg)

    def save(self, cfg: Dict[str, Any]) -> None:
        """Persist cfg to disk and update in-memory copy immediately."""
        with self._lock:
            save_config(cfg)
            self._cfg = _deep_merge(DEFAULTS, cfg)
            self._mtime = self._file_mtime()

    def stop(self) -> None:
        self._stop.set()

    # Internal ----------------------------------------------------------

    def _file_mtime(self) -> float:
        try:
            return os.path.getmtime(CONFIG_FILE)
        except OSError:
            return 0.0

    def _watch(self) -> None:
        while not self._stop.wait(3.0):
            mtime = self._file_mtime()
            if mtime != self._mtime:
                log.info("config.json changed on disk — reloading.")
                with self._lock:
                    self._cfg = load_config()
                    self._mtime = mtime


# Module-level singleton — created once when first imported.
_manager: "ConfigManager | None" = None
_manager_lock = threading.Lock()


def get_manager() -> ConfigManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = ConfigManager()
    return _manager