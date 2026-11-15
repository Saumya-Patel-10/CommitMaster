"""Handoff from the admin app into a separate user-product process.

The user process reads the handoff and then deletes it. The handoff cannot
carry an admin scope, a password, a GitHub token, or an AI credential.
Impersonation is a different process from the admin console, so the admin
lock does not exist in that process.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from typing import Any, Dict, Optional

_SECRET_KEYS = {
    "password", "password_hash", "github_token", "token_secret",
    "openai_api_key", "claude_api_key", "gemini_api_key", "api_key",
    "totp_secret", "session_scope",
}


class HandoffError(RuntimeError):
    pass


def scrub_user(user: Dict[str, Any]) -> Dict[str, Any]:
    clean = {}
    for key, value in dict(user or {}).items():
        if key.lower() in _SECRET_KEYS or key.lower().endswith("_token") or key.lower().endswith("_secret"):
            continue
        if key == "token":
            continue
        clean[key] = value
    clean["role"] = "user"
    return clean


def write_handoff(payload: Dict[str, Any], directory: str) -> str:
    mode = payload.get("mode")
    if mode not in ("workspace", "impersonation"):
        raise HandoffError("handoff mode must be workspace or impersonation")
    if payload.get("scope") == "admin" or payload.get("session_scope") == "admin":
        raise HandoffError("refusing to hand an admin session to the user app")
    body = {
        "mode": mode,
        "token": payload.get("token") or "",
        "read_only": bool(payload.get("read_only", mode == "impersonation")),
        "expires_at": payload.get("expires_at") or "",
        "justification": payload.get("justification") or "",
        "banner": payload.get("banner") or "",
        "user": scrub_user(payload.get("user") or {}),
    }
    if not body["token"]:
        raise HandoffError("handoff is missing a session token")
    os.makedirs(directory, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix="handoff-", suffix=".json", dir=directory)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
    except (AttributeError, NotImplementedError):
        pass
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(body, handle)
    return path


def consume_handoff(argv: Optional[list] = None) -> Optional[Dict[str, Any]]:
    """Read --handoff PATH. Admin flags are ignored and never elevate."""
    args = list(sys.argv[1:] if argv is None else argv)
    if "--admin" in args or "--admin-edition" in args:
        args = [a for a in args if a not in ("--admin", "--admin-edition")]
    if "--handoff" not in args:
        return None
    index = args.index("--handoff")
    if index + 1 >= len(args):
        raise HandoffError("missing handoff path")
    path = args[index + 1]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if not isinstance(payload, dict):
        raise HandoffError("handoff was not a JSON object")
    if payload.get("mode") not in ("workspace", "impersonation"):
        raise HandoffError("refusing handoff")
    if payload.get("scope") == "admin":
        raise HandoffError("user app refuses an admin handoff")
    payload["user"] = scrub_user(payload.get("user") or {})
    payload["read_only"] = bool(payload.get("read_only", payload["mode"] == "impersonation"))
    return payload


def user_entry_command(handoff_path: str) -> list:
    """Command for a new process. Never re-executes the admin executable."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        for name in ("CommitMaster-User.exe", "CommitMaster.exe"):
            candidate = os.path.join(exe_dir, name)
            if os.path.isfile(candidate) and os.path.abspath(candidate) != os.path.abspath(sys.executable):
                return [candidate, "--handoff", handoff_path]
        raise HandoffError("CommitMaster-User.exe was not found next to the admin app")
    app_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
    return [sys.executable, app_py, "--handoff", handoff_path]


def spawn_user_process(payload: Dict[str, Any], directory: str) -> subprocess.Popen:
    path = write_handoff(payload, directory)
    command = user_entry_command(path)
    env = os.environ.copy()
    for key in ("ADMIN_PASSWORD", "ADMIN_TOTP_SECRET", "ADMIN_MIGRATION_SECRET", "SERVER_ENCRYPTION_KEY"):
        env.pop(key, None)
    return subprocess.Popen(command, env=env, cwd=os.path.dirname(command[-1]) if not getattr(sys, "frozen", False) else None)
