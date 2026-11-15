"""Admin desktop client. Production user data is reached only through the server."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

from commitmaster import paths, user_mode


class AdminClientError(RuntimeError):
    pass


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-CommitMaster-Product": "admin",
        "Content-Type": "application/json",
    }


def require_server(url: str) -> str:
    clean = (url or "").strip().rstrip("/")
    if not clean:
        raise AdminClientError("The admin app has no server URL. It does not open the production database directly.")
    return clean


def login(url: str, username: str, password: str, totp_code: str) -> Dict[str, Any]:
    endpoint = require_server(url) + "/api/admin/login"
    response = requests.post(endpoint, json={
        "username_or_email": username,
        "password": password,
        "totp_code": totp_code,
    }, headers={"X-CommitMaster-Product": "admin"}, timeout=15)
    if response.status_code != 200:
        detail = response.text
        try:
            detail = response.json().get("error", detail)
        except Exception:
            pass
        raise AdminClientError(detail or "Admin login failed")
    body = response.json()
    if body.get("scope") != "admin" or not body.get("token"):
        raise AdminClientError("Server did not issue an admin-scoped session")
    return body


def open_own_workspace(url: str, admin_token: str):
    endpoint = require_server(url) + "/api/admin/workspace-token"
    response = requests.post(endpoint, headers=_headers(admin_token), timeout=15)
    if response.status_code != 200:
        raise AdminClientError(f"Could not open the user workspace ({response.status_code})")
    body = response.json()
    if body.get("scope") == "admin" or (body.get("user") or {}).get("role") == "admin":
        raise AdminClientError("Refusing a workspace session that still has admin power")
    return user_mode.spawn_user_process({
        "mode": "workspace",
        "token": body.get("token"),
        "user": body.get("user") or {},
        "read_only": False,
        "expires_at": body.get("expires_at") or "",
        "banner": "Your standard user workspace. This window cannot return to the admin console.",
    }, paths.get_data_dir())


def open_impersonation(url: str, admin_token: str, user_id: int, justification: str, confirm: bool, read_only: bool = True):
    endpoint = require_server(url) + "/api/admin/impersonate"
    response = requests.post(endpoint, headers=_headers(admin_token), json={
        "user_id": user_id,
        "justification": justification,
        "confirm": bool(confirm),
        "read_only": bool(read_only),
    }, timeout=15)
    if response.status_code != 200:
        detail = response.text
        try:
            detail = response.json().get("error", detail)
        except Exception:
            pass
        raise AdminClientError(detail or "Impersonation was refused")
    body = response.json()
    user = body.get("user") or {}
    if user.get("role") == "admin" or body.get("scope") == "admin":
        raise AdminClientError("Impersonation session included administrative power and was discarded")
    for key in ("password", "password_hash", "github_token", "openai_api_key", "claude_api_key", "gemini_api_key"):
        if user.get(key):
            raise AdminClientError("Impersonation response included a credential and was discarded")
    return user_mode.spawn_user_process({
        "mode": "impersonation",
        "token": body.get("token"),
        "user": user,
        "read_only": bool(body.get("read_only", True)),
        "expires_at": body.get("expires_at") or "",
        "justification": justification,
        "banner": "IMPERSONATION. You are not an administrator. This session expires and cannot open the admin console.",
    }, paths.get_data_dir())


def prompt_server_login() -> Optional[Dict[str, Any]]:
    """Ask for the admin password and authenticator code. The TOTP secret is not on this machine."""
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    root = tk.Tk()
    root.withdraw()
    from commitmaster import database as db
    url = db.get_server_url()
    try:
        require_server(url)
    except AdminClientError as exc:
        messagebox.showerror("CommitMaster Admin", str(exc))
        root.destroy()
        return None
    username = simpledialog.askstring("CommitMaster Admin", "Admin username", parent=root)
    password = simpledialog.askstring("CommitMaster Admin", "Password", show="*", parent=root)
    code = simpledialog.askstring("CommitMaster Admin", "Authenticator code", parent=root)
    if not username or not password or not code:
        root.destroy()
        return None
    try:
        session = login(url, username, password, code)
    except AdminClientError as exc:
        messagebox.showerror("CommitMaster Admin", str(exc))
        root.destroy()
        return None
    root.destroy()
    return session
