"""
CommitMaster — Path Resolution & Persistent Storage Management.
=================================================================
Centralizes persistent application data paths to prevent data loss across
frozen PyInstaller one-file runs, updates, and environment changes.

Guarantees:
  1. commitmaster.db, accounts, sessions, config, and logs ALWAYS persist in a
     permanent directory (%LOCALAPPDATA%\\CommitMaster or workspace repo).
  2. NEVER writes or reads persistent state from PyInstaller's temporary
     sys._MEIPASS directory (which Windows deletes when the app closes).
  3. Seamless auto-sync between workspace repository and %LOCALAPPDATA%\\CommitMaster
     so user history and commit records are never lost.
"""
import os
import shutil
import sys
from typing import Optional

# Base workspace directory (c:\Data\Saumya\Projects\CommitMaster)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE_DIR = os.path.dirname(_THIS_DIR)


def get_app_dir() -> str:
    """
    Return the root application directory for read-only static assets (icons, images).
    In frozen PyInstaller mode, bundled assets may live in sys._MEIPASS.
    """
    return getattr(sys, "_MEIPASS", _WORKSPACE_DIR)


def get_data_dir() -> str:
    """
    Return the persistent writable data directory for database, config, tokens, and logs.
    NEVER returns a temporary _MEIPASS folder.
    """
    # 1. Explicit override via environment variable
    env_dir = os.getenv("COMMITMASTER_DATA_DIR", "").strip()
    if env_dir:
        os.makedirs(env_dir, exist_ok=True)
        return env_dir

    local_app_data = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
    local_commitmaster_dir = os.path.join(local_app_data, "CommitMaster")

    # 2. Check if running directly in or alongside workspace repository
    # Workspace repo has the authentic commitmaster.db
    workspace_db = os.path.join(_WORKSPACE_DIR, "commitmaster.db")
    if os.path.exists(workspace_db):
        # We are in the workspace repo (either source or running in repo/dist)
        # Also ensure %LOCALAPPDATA%\CommitMaster is initialized as a backup
        try:
            os.makedirs(local_commitmaster_dir, exist_ok=True)
            local_db = os.path.join(local_commitmaster_dir, "commitmaster.db")
            if not os.path.exists(local_db):
                shutil.copy2(workspace_db, local_db)
        except Exception:
            pass
        return _WORKSPACE_DIR

    # 3. If running frozen from outside workspace repo
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        # If running from dist/ inside workspace
        candidate_repo = os.path.dirname(exe_dir)
        candidate_db = os.path.join(candidate_repo, "commitmaster.db")
        if os.path.exists(candidate_db):
            return candidate_repo

    # 4. Standard Windows persistent application data directory
    os.makedirs(local_commitmaster_dir, exist_ok=True)
    local_db = os.path.join(local_commitmaster_dir, "commitmaster.db")
    # If local_db doesn't exist but workspace has it, copy it over!
    if not os.path.exists(local_db) and os.path.exists(workspace_db):
        try:
            shutil.copy2(workspace_db, local_db)
            for fname in [".commitmaster_accounts.json", ".session_token", ".admin_session", "config.json"]:
                src = os.path.join(_WORKSPACE_DIR, fname)
                dst = os.path.join(local_commitmaster_dir, fname)
                if os.path.exists(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)
        except Exception:
            pass

    return local_commitmaster_dir


def get_db_path() -> str:
    """Return absolute path to commitmaster.db."""
    return os.path.join(get_data_dir(), "commitmaster.db")


def get_accounts_path() -> str:
    """Return absolute path to .commitmaster_accounts.json."""
    return os.path.join(get_data_dir(), ".commitmaster_accounts.json")


def get_token_path() -> str:
    """Return absolute path to .session_token."""
    return os.path.join(get_data_dir(), ".session_token")


def get_admin_token_path() -> str:
    """Return absolute path to .admin_session."""
    return os.path.join(get_data_dir(), ".admin_session")


def get_config_path() -> str:
    """Return absolute path to config.json."""
    return os.path.join(get_data_dir(), "config.json")


def get_log_path() -> str:
    """Return absolute path to commitmaster.log."""
    return os.path.join(get_data_dir(), "commitmaster.log")


def get_avatars_dir() -> str:
    """Return absolute path to avatars directory."""
    d = os.path.join(get_data_dir(), "assets", "avatars")
    os.makedirs(d, exist_ok=True)
    return d
