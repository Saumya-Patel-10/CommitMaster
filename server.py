"""
CommitMaster — Central Cloud Backend Server.
============================================
Provides centralized authentication, user administration, activity logging,
and multi-device data synchronization for CommitMaster desktop clients.

Deployment targets:
  - Render (Free 1-click web service via render.yaml or Dockerfile)
  - Railway (1-click via railway.json)
  - Fly.io / Heroku / AWS / VPS / Docker
  - Local PC / Private Network (python server.py)

Supported Database backends:
  - PostgreSQL / Supabase / Neon / Render Postgres (via DATABASE_URL environment variable)
  - SQLite (default: server_commitmaster.db)
"""

import os
import sys
import json
import sqlite3
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from flask import Flask, request, jsonify, render_template_string

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s in %(name)s: %(message)s"
)
logger = logging.getLogger("commitmaster-server")

app = Flask(__name__)

# Basic CORS headers helper
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    # Security checklist headers (Item 18)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Configuration
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.getenv("SERVER_DB_PATH", os.path.join(SERVER_DIR, "server_commitmaster.db"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Default admin credentials
DEFAULT_ADMIN_USER = os.getenv("ADMIN_USERNAME", "saumya.patel@Admin_#")
DEFAULT_ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")
DEFAULT_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "saumya.a.patel@gmail.com")

# Password hashing utilities
def hash_password(password: str) -> str:
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except Exception:
        salt = secrets.token_hex(16)
        hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return f"sha256${salt}${hashed}"

def verify_password(password: str, password_hash: str) -> bool:
    try:
        import bcrypt
        if password_hash.startswith("sha256$"):
            parts = password_hash.split("$")
            salt, stored = parts[1], parts[2]
            return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == stored
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        if password_hash.startswith("sha256$"):
            parts = password_hash.split("$")
            salt, stored = parts[1], parts[2]
            return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == stored
        return False

# Database connection
def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            email         TEXT NOT NULL UNIQUE,
            full_name     TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user',
            avatar_color  TEXT NOT NULL DEFAULT '#3fb950',
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            last_login    TEXT,
            bio           TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id             INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            watched_apps        TEXT DEFAULT '["Code.exe","Cursor.exe","Antigravity.exe"]',
            projects_dirs       TEXT DEFAULT '[]',
            auto_commit         INTEGER DEFAULT 0,
            skip_sensitive      INTEGER DEFAULT 1,
            session_end_grace   INTEGER DEFAULT 120,
            ai_base_url         TEXT DEFAULT 'http://localhost:1234/v1',
            ai_model            TEXT DEFAULT '',
            theme               TEXT DEFAULT 'dark',
            notifications       INTEGER DEFAULT 1,
            accent_color        TEXT DEFAULT '#3fb950',
            font_family         TEXT DEFAULT 'Segoe UI',
            font_scale          TEXT DEFAULT 'standard',
            ui_density          TEXT DEFAULT 'comfortable',
            auto_push           INTEGER DEFAULT 0,
            ask_before_push     INTEGER DEFAULT 1,
            ai_provider         TEXT DEFAULT 'bionic',
            openai_api_key      TEXT DEFAULT '',
            claude_api_key      TEXT DEFAULT '',
            gemini_api_key      TEXT DEFAULT '',
            openai_model        TEXT DEFAULT 'gpt-4o-mini',
            claude_model        TEXT DEFAULT 'claude-3-5-haiku-20241022',
            gemini_model        TEXT DEFAULT 'gemini-1.5-flash',
            reminder_interval_enabled    INTEGER DEFAULT 1,
            reminder_interval_hours      INTEGER DEFAULT 1,
            reminder_interval_minutes    INTEGER DEFAULT 0,
            reminder_app_monitor_enabled INTEGER DEFAULT 1,
            reminder_only_if_dirty       INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS commit_activity (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            repo_path   TEXT NOT NULL,
            repo_name   TEXT NOT NULL,
            commit_hash TEXT DEFAULT '',
            commit_msg  TEXT NOT NULL,
            files_count INTEGER DEFAULT 0,
            status      TEXT NOT NULL DEFAULT 'committed',
            committed_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_usage (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date        TEXT NOT NULL,
            sessions    INTEGER NOT NULL DEFAULT 1,
            commits_made INTEGER NOT NULL DEFAULT 0,
            repos_scanned INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, date)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at  TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_by  INTEGER REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS github_accounts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            account_name    TEXT NOT NULL,
            github_username TEXT NOT NULL,
            github_token    TEXT NOT NULL,
            author_name     TEXT DEFAULT '',
            author_email    TEXT DEFAULT '',
            avatar_url      TEXT DEFAULT '',
            is_default      INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS repo_github_accounts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            repo_path   TEXT NOT NULL,
            account_id  INTEGER NOT NULL REFERENCES github_accounts(id) ON DELETE CASCADE,
            UNIQUE(user_id, repo_path)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS watched_repositories (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            github_account_id INTEGER REFERENCES github_accounts(id) ON DELETE SET NULL,
            repo_name         TEXT NOT NULL,
            repo_full_name    TEXT NOT NULL,
            clone_url         TEXT DEFAULT '',
            ssh_url           TEXT DEFAULT '',
            default_branch    TEXT DEFAULT 'main',
            local_path        TEXT DEFAULT '',
            is_private        INTEGER NOT NULL DEFAULT 0,
            description       TEXT DEFAULT '',
            is_active_watch   INTEGER NOT NULL DEFAULT 1,
            last_scanned      TEXT,
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, repo_full_name)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            kind        TEXT NOT NULL,
            repo_name   TEXT NOT NULL DEFAULT '',
            files       INTEGER NOT NULL DEFAULT 0,
            errors      INTEGER NOT NULL DEFAULT 0,
            security    INTEGER NOT NULL DEFAULT 0,
            warnings    INTEGER NOT NULL DEFAULT 0,
            detail      TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_server_events_kind ON app_events(kind, created_at)")

    conn.commit()

    # Ensure default admin account exists
    cur.execute("DELETE FROM users WHERE username = 'admin'")
    cur.execute("UPDATE users SET role = 'user' WHERE role = 'admin' AND username != ?", (DEFAULT_ADMIN_USER,))

    cur.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_ADMIN_USER,))
    saumya_row = cur.fetchone()
    if not saumya_row:
        pw_hash = hash_password(DEFAULT_ADMIN_PASS)
        cur.execute("""
            INSERT INTO users (username, email, full_name, password_hash, role, avatar_color)
            VALUES (?, ?, ?, ?, 'admin', '#3fb950')
        """, (DEFAULT_ADMIN_USER, DEFAULT_ADMIN_EMAIL, "Saumya Patel", pw_hash))
        admin_id = cur.lastrowid
        cur.execute("INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (admin_id,))
        logger.info(f"Initialized default admin account: '{DEFAULT_ADMIN_USER}'")
    else:
        cur.execute("UPDATE users SET role = 'admin' WHERE username = ?", (DEFAULT_ADMIN_USER,))

    conn.commit()
    conn.close()

# Initialize DB on server load
init_db()

# ── Home Web Dashboard ────────────────────────────────────────────────────────
LANDING_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CommitMaster — Cloud Backend Server</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d1117;
            --card: #161b22;
            --border: #30363d;
            --accent: #2ea043;
            --accent-glow: rgba(46, 160, 67, 0.25);
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --admin-color: #f0883e;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }
        .container {
            max-width: 760px;
            width: 100%;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 36px;
            box-shadow: 0 16px 48px rgba(0,0,0,0.45);
        }
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 24px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
        }
        .title {
            display: flex;
            align-items: center;
            gap: 14px;
        }
        .logo {
            width: 44px;
            height: 44px;
            background: var(--accent);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 22px;
            color: #ffffff;
            box-shadow: 0 0 16px var(--accent-glow);
        }
        h1 { font-size: 24px; font-weight: 700; }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(46, 160, 67, 0.15);
            color: #3fb950;
            border: 1px solid rgba(46, 160, 67, 0.3);
            border-radius: 20px;
            padding: 5px 12px;
            font-size: 13px;
            font-weight: 600;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            margin-bottom: 28px;
        }
        .stat-card {
            background: #0d1117;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 18px;
            text-align: center;
        }
        .stat-val {
            font-size: 28px;
            font-weight: 700;
            color: var(--text-primary);
        }
        .stat-lbl {
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .info-box {
            background: #0d1117;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 24px;
        }
        .info-box h2 {
            font-size: 16px;
            margin-bottom: 10px;
            color: var(--text-primary);
        }
        .info-box p {
            font-size: 14px;
            color: var(--text-secondary);
            line-height: 1.6;
            margin-bottom: 12px;
        }
        .code-block {
            background: #161b22;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: #58a6ff;
            word-break: break-all;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .footer {
            font-size: 13px;
            color: var(--text-secondary);
            text-align: center;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">
                <div class="logo">⬡</div>
                <div>
                    <h1>CommitMaster Server</h1>
                    <div style="font-size: 13px; color: var(--text-secondary);">Enterprise Central Backend API v3.0</div>
                </div>
            </div>
            <div class="badge">● Online & Ready</div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-val">{{ stats.total_users }}</div>
                <div class="stat-lbl">Registered Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{{ stats.total_commits }}</div>
                <div class="stat-lbl">Commits Synced</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{{ stats.total_admins }}</div>
                <div class="stat-lbl">Administrators</div>
            </div>
        </div>

        <div class="info-box">
            <h2>🔗 Connect Windows Desktop Apps to this Server</h2>
            <p>To use this server across all your Windows devices, copy this Server URL and set it in your CommitMaster desktop app:</p>
            <div class="code-block">
                <span>{{ server_url }}</span>
            </div>
            <p style="margin-top: 14px; font-size: 13px;">
                In the desktop app, click <strong>"⚙ Server Settings"</strong> on the Sign In screen, or paste into <code>config.json</code> under <code>"server_url"</code>.
            </p>
        </div>

        <div class="footer">
            CommitMaster Central API • Running on Python & Flask
        </div>
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def home():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    total_admins = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM commit_activity")
    total_commits = cur.fetchone()[0]
    conn.close()

    server_url = request.url_root.rstrip("/")
    return render_template_string(LANDING_HTML, stats={
        "total_users": total_users,
        "total_admins": total_admins,
        "total_commits": total_commits,
    }, server_url=server_url)

# ── Health & Diagnostics ──────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        conn.close()
        return jsonify({
            "status": "ok",
            "version": "3.0",
            "service": "CommitMaster Cloud Backend",
            "users_count": user_count,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

# ── Authentication Endpoints ──────────────────────────────────────────────────
@app.route("/api/auth/check", methods=["POST"])
def auth_check():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT username, email FROM users
        WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)
    """, (username, email))
    row = cur.fetchone()
    conn.close()

    if row:
        if row["username"].lower() == username.lower():
            return jsonify({"conflict": "username"})
        return jsonify({"conflict": "email"})
    return jsonify({"conflict": None})

@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    full_name = (data.get("full_name") or "").strip()
    password = data.get("password") or ""
    avatar_color = data.get("avatar_color") or "#3fb950"

    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password are required."}), 400

    if username.strip().lower() == DEFAULT_ADMIN_USER.lower():
        return jsonify({"error": f"The username '{DEFAULT_ADMIN_USER}' is reserved for the primary administrator."}), 403

    # All client registrations are strictly standard users
    role = "user"

    conn = get_db()
    cur = conn.cursor()
    # Check duplicate
    cur.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": f"Username '{username}' is already taken."}), 409

    cur.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": f"Email '{email}' is already registered."}), 409

    pw_hash = hash_password(password)
    try:
        cur.execute("""
            INSERT INTO users (username, email, full_name, password_hash, role, avatar_color)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, email, full_name, pw_hash, role, avatar_color))
        user_id = cur.lastrowid
        cur.execute("INSERT INTO user_preferences (user_id) VALUES (?)", (user_id,))

        # Create session token
        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                    (token, user_id, expires))
        conn.commit()

        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user_dict = dict(cur.fetchone())
        user_dict.pop("password_hash", None)
        conn.close()

        return jsonify({"user": user_dict, "token": token}), 201
    except Exception as exc:
        conn.close()
        logger.error(f"Error in register: {exc}")
        return jsonify({"error": "Failed to create account: " + str(exc)}), 500

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(force=True, silent=True) or {}
    username_or_email = (data.get("username_or_email") or "").strip()
    password = data.get("password") or ""

    if not username_or_email or not password:
        return jsonify({"error": "Username/email and password required"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM users
        WHERE (LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)) AND is_active = 1
    """, (username_or_email, username_or_email))
    row = cur.fetchone()

    if not row or not verify_password(password, row["password_hash"]):
        conn.close()
        return jsonify({"error": "Invalid credentials. Please try again."}), 401

    user_id = row["id"]
    cur.execute("UPDATE users SET last_login = datetime('now') WHERE id = ?", (user_id,))

    # Record daily usage session
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        INSERT INTO app_usage (user_id, date, sessions)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, date) DO UPDATE SET sessions = sessions + 1
    """, (user_id, today))

    # Create session token
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    cur.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires))
    conn.commit()

    user_dict = dict(row)
    user_dict.pop("password_hash", None)
    conn.close()

    return jsonify({"user": user_dict, "token": token})

@app.route("/api/auth/session", methods=["POST"])
def auth_session():
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action")
    conn = get_db()
    cur = conn.cursor()

    if action == "validate":
        token = data.get("token") or ""
        cur.execute("""
            SELECT u.* FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token = ? AND s.expires_at > datetime('now') AND u.is_active = 1
        """, (token,))
        row = cur.fetchone()
        conn.close()
        if row:
            u_dict = dict(row)
            u_dict.pop("password_hash", None)
            return jsonify({"valid": True, "user": u_dict})
        return jsonify({"valid": False, "user": None})

    elif action == "create":
        user_id = int(data.get("user_id", 0))
        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        cur.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                    (token, user_id, expires))
        conn.commit()
        conn.close()
        return jsonify({"token": token})

    elif action == "revoke":
        user_id = int(data.get("user_id", 0))
        cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

    conn.close()
    return jsonify({"error": "Unknown session action"}), 400

# ── User Profile & Preferences ────────────────────────────────────────────────
@app.route("/api/users/<int:user_id>", methods=["GET", "PUT"])
def user_detail(user_id):
    conn = get_db()
    cur = conn.cursor()

    if request.method == "GET":
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "User not found"}), 404
        u_dict = dict(row)
        u_dict.pop("password_hash", None)
        return jsonify({"user": u_dict})

    elif request.method == "PUT":
        data = request.get_json(force=True, silent=True) or {}
        allowed = {"full_name", "email", "bio", "avatar_color", "is_active", "role"}
        updates = {k: v for k, v in data.items() if k in allowed}
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            cur.execute(f"UPDATE users SET {set_clause} WHERE id = ?",
                        (*updates.values(), user_id))
            conn.commit()
        conn.close()
        return jsonify({"ok": True})

@app.route("/api/users/<int:user_id>/password", methods=["POST"])
def user_change_password(user_id):
    data = request.get_json(force=True, silent=True) or {}
    new_pw = data.get("new_password") or ""
    if not new_pw:
        return jsonify({"error": "New password required"}), 400

    pw_hash = hash_password(new_pw)
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/users/<int:user_id>/preferences", methods=["GET", "PUT"])
def user_preferences(user_id):
    conn = get_db()
    cur = conn.cursor()

    if request.method == "GET":
        cur.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"preferences": {}})
        return jsonify({"preferences": dict(row)})

    elif request.method == "PUT":
        data = request.get_json(force=True, silent=True) or {}
        allowed = {
            "watched_apps", "projects_dirs", "auto_commit", "skip_sensitive",
            "session_end_grace", "ai_base_url", "ai_model", "theme", "notifications",
            "accent_color", "font_family", "font_scale", "ui_density", "auto_push",
            "ask_before_push", "ai_provider", "openai_api_key", "claude_api_key",
            "gemini_api_key", "openai_model", "claude_model", "gemini_model",
            "reminder_interval_enabled", "reminder_interval_hours", "reminder_interval_minutes",
            "reminder_app_monitor_enabled", "reminder_only_if_dirty"
        }
        updates = {k: v for k, v in data.items() if k in allowed}
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            cur.execute(f"UPDATE user_preferences SET {set_clause} WHERE user_id = ?",
                        (*updates.values(), user_id))
            conn.commit()
        conn.close()
        return jsonify({"ok": True})

# ── Commit Activity & Logs ────────────────────────────────────────────────────
@app.route("/api/activity/commits", methods=["GET", "POST"])
def activity_commits():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        user_id = int(data.get("user_id", 0))
        repo_path = data.get("repo_path") or ""
        repo_name = data.get("repo_name") or os.path.basename(repo_path.rstrip("/\\"))
        commit_msg = data.get("commit_msg") or ""
        commit_hash = data.get("commit_hash") or ""
        files_count = int(data.get("files_count", 0))
        status = data.get("status") or "committed"

        cur.execute("""
            INSERT INTO commit_activity (user_id, repo_path, repo_name, commit_hash, commit_msg, files_count, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, repo_path, repo_name, commit_hash, commit_msg, files_count, status))

        if status == "committed":
            today = datetime.now().strftime("%Y-%m-%d")
            cur.execute("""
                INSERT INTO app_usage (user_id, date, sessions, commits_made)
                VALUES (?, ?, 0, 1)
                ON CONFLICT(user_id, date) DO UPDATE SET commits_made = commits_made + 1
            """, (user_id, today))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

    elif request.method == "GET":
        user_id = request.args.get("user_id", type=int)
        limit = request.args.get("limit", default=100, type=int)

        if user_id:
            cur.execute("""
                SELECT ca.*, u.username, u.full_name, u.avatar_color
                FROM commit_activity ca
                JOIN users u ON ca.user_id = u.id
                WHERE ca.user_id = ?
                ORDER BY ca.committed_at DESC LIMIT ?
            """, (user_id, limit))
        else:
            cur.execute("""
                SELECT ca.*, u.username, u.full_name, u.avatar_color
                FROM commit_activity ca
                JOIN users u ON ca.user_id = u.id
                ORDER BY ca.committed_at DESC LIMIT ?
            """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify({"activity": rows})

@app.route("/api/events", methods=["POST"])
def log_event():
    data = request.get_json(force=True, silent=True) or {}
    conn = get_db()
    conn.execute("""
        INSERT INTO app_events (user_id, kind, repo_name, files, errors, security, warnings, detail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("user_id"),
        data.get("kind", "scan"),
        data.get("repo_name", ""),
        data.get("files", 0),
        data.get("errors", 0),
        data.get("security", 0),
        data.get("warnings", 0),
        (data.get("detail") or "")[:300]
    ))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# ── Metrics & Analytics ───────────────────────────────────────────────────────
@app.route("/api/metrics/timeseries", methods=["GET"])
def metrics_timeseries():
    days = request.args.get("days", default=30, type=int)
    user_id = request.args.get("user_id", type=int)

    today = datetime.now().date()
    dates = [(today - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(days - 1, -1, -1)]
    idx = {d: i for i, d in enumerate(dates)}
    names = ["sessions", "active_users", "commits", "files_committed", "pushes", "scans",
             "vulnerabilities", "errors", "warnings", "commit_failures", "push_failures", "ai_generations"]
    series = {n: [0] * len(dates) for n in names}
    since = dates[0]

    conn = get_db()
    if user_id:
        usage_query = "SELECT date, SUM(sessions) s, COUNT(DISTINCT user_id) u FROM app_usage WHERE date >= ? AND user_id = ? GROUP BY date"
        commit_query = "SELECT date(committed_at, 'localtime') d, COUNT(*) c, SUM(files_count) f FROM commit_activity WHERE status = 'committed' AND date(committed_at, 'localtime') >= ? AND user_id = ? GROUP BY d"
        event_query = "SELECT date(created_at, 'localtime') d, kind, COUNT(*) c, SUM(errors) e, SUM(security) s, SUM(warnings) w FROM app_events WHERE date(created_at, 'localtime') >= ? AND user_id = ? GROUP BY d, kind"
        args: tuple = (since, user_id)
    else:
        usage_query = "SELECT date, SUM(sessions) s, COUNT(DISTINCT user_id) u FROM app_usage WHERE date >= ? GROUP BY date"
        commit_query = "SELECT date(committed_at, 'localtime') d, COUNT(*) c, SUM(files_count) f FROM commit_activity WHERE status = 'committed' AND date(committed_at, 'localtime') >= ? GROUP BY d"
        event_query = "SELECT date(created_at, 'localtime') d, kind, COUNT(*) c, SUM(errors) e, SUM(security) s, SUM(warnings) w FROM app_events WHERE date(created_at, 'localtime') >= ? GROUP BY d, kind"
        args = (since,)

    for r in conn.execute(usage_query, args):
        if r["date"] in idx:
            series["sessions"][idx[r["date"]]] = r["s"] or 0
            series["active_users"][idx[r["date"]]] = r["u"] or 0

    for r in conn.execute(commit_query, args):
        if r["d"] in idx:
            series["commits"][idx[r["d"]]] = r["c"] or 0
            series["files_committed"][idx[r["d"]]] = r["f"] or 0

    kind_map = {"push_ok": "pushes", "scan": "scans", "commit_failed": "commit_failures",
                "push_failed": "push_failures", "ai_generate": "ai_generations"}
    for r in conn.execute(event_query, args):
        i = idx.get(r["d"])
        if i is None:
            continue
        key = kind_map.get(r["kind"])
        if key:
            series[key][i] += r["c"] or 0
        if r["kind"] == "scan":
            series["vulnerabilities"][i] += r["s"] or 0
            series["errors"][i] += r["e"] or 0
            series["warnings"][i] += r["w"] or 0

    conn.close()
    return jsonify({"dates": dates, "series": series})

@app.route("/api/metrics/user-commits", methods=["GET"])
def metrics_user_commits():
    days = request.args.get("days", default=30, type=int)
    limit = request.args.get("limit", default=5, type=int)

    today = datetime.now().date()
    dates = [(today - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(days - 1, -1, -1)]
    idx = {d: i for i, d in enumerate(dates)}

    conn = get_db()
    rows = conn.execute("""
        SELECT u.username, date(ca.committed_at, 'localtime') d, COUNT(*) c
        FROM commit_activity ca JOIN users u ON u.id = ca.user_id
        WHERE ca.status = 'committed' AND date(ca.committed_at, 'localtime') >= ?
        GROUP BY u.id, d
    """, (dates[0],)).fetchall()
    conn.close()

    totals: Dict[str, int] = {}
    per_user: Dict[str, List[int]] = {}
    for r in rows:
        if r["d"] not in idx:
            continue
        per_user.setdefault(r["username"], [0] * len(dates))[idx[r["d"]]] = r["c"]
        totals[r["username"]] = totals.get(r["username"], 0) + r["c"]
    top = sorted(totals, key=totals.get, reverse=True)[:limit]
    return jsonify({"dates": dates, "series": {u: per_user[u] for u in top}})

@app.route("/api/events/security", methods=["GET"])
def events_security():
    limit = request.args.get("limit", default=8, type=int)
    conn = get_db()
    rows = conn.execute("""
        SELECT e.*, u.username FROM app_events e LEFT JOIN users u ON u.id = e.user_id
        WHERE e.kind = 'scan' AND (e.security > 0 OR e.errors > 0)
        ORDER BY e.created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return jsonify({"events": [dict(r) for r in rows]})

@app.route("/api/usage/stats", methods=["GET"])
def usage_stats():
    days = request.args.get("days", default=30, type=int)
    user_id = request.args.get("user_id", type=int)
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    conn = get_db()
    if user_id:
        rows = conn.execute("""
            SELECT date, SUM(sessions) as sessions, SUM(commits_made) as commits_made
            FROM app_usage WHERE user_id = ? AND date >= ?
            GROUP BY date ORDER BY date
        """, (user_id, since)).fetchall()
    else:
        rows = conn.execute("""
            SELECT date, SUM(sessions) as sessions, SUM(commits_made) as commits_made,
                   COUNT(DISTINCT user_id) as active_users
            FROM app_usage WHERE date >= ?
            GROUP BY date ORDER BY date
        """, (since,)).fetchall()
    conn.close()
    return jsonify({"stats": [dict(r) for r in rows]})

# ── Admin Endpoints ───────────────────────────────────────────────────────────
@app.route("/api/admin/users", methods=["GET"])
def admin_get_users():
    conn = get_db()
    rows = conn.execute("""
        SELECT u.*, 
               (SELECT COUNT(*) FROM commit_activity WHERE user_id = u.id) as total_commits
        FROM users u
        ORDER BY u.created_at DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d.pop("password_hash", None)
        result.append(d)
    return jsonify({"users": result})

@app.route("/api/admin/users/<int:user_id>", methods=["PUT", "DELETE"])
def admin_user_ops(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,))
    target = cur.fetchone()
    if not target:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    target_uname = target["username"]

    if request.method == "PUT":
        data = request.get_json(force=True, silent=True) or {}
        # Enforce single admin policy
        if data.get("role") == "admin" and target_uname != DEFAULT_ADMIN_USER:
            conn.close()
            return jsonify({"error": f"Only '{DEFAULT_ADMIN_USER}' can hold administrator privileges."}), 400
        if target_uname == DEFAULT_ADMIN_USER and data.get("role") and data.get("role") != "admin":
            conn.close()
            return jsonify({"error": f"The primary administrator '{DEFAULT_ADMIN_USER}' cannot be demoted."}), 400

        allowed = {"role", "is_active", "full_name", "email", "bio", "avatar_color"}
        updates = {k: v for k, v in data.items() if k in allowed}
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            cur.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*updates.values(), user_id))
            conn.commit()
        conn.close()
        return jsonify({"ok": True})

    elif request.method == "DELETE":
        if target_uname == DEFAULT_ADMIN_USER:
            conn.close()
            return jsonify({"error": f"The primary administrator account '{DEFAULT_ADMIN_USER}' cannot be deleted."}), 400

        hard = request.args.get("hard", "false").lower() == "true"
        if hard:
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        else:
            cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

@app.route("/api/admin/stats", methods=["GET"])
def admin_stats():
    conn = get_db()
    cur = conn.cursor()
    stats = {}

    cur.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
    stats["total_users"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    stats["total_admins"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM commit_activity")
    stats["total_commits"] = cur.fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(DISTINCT user_id) FROM app_usage WHERE date = ?", (today,))
    stats["active_today"] = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM commit_activity
        WHERE committed_at >= datetime('now', '-7 days')
    """)
    stats["commits_this_week"] = cur.fetchone()[0]

    cur.execute("""
        SELECT u.username, COUNT(ca.id) as commits
        FROM users u LEFT JOIN commit_activity ca ON u.id = ca.user_id
        GROUP BY u.id ORDER BY commits DESC LIMIT 5
    """)
    stats["top_committers"] = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"stats": stats})

# ── System Settings ───────────────────────────────────────────────────────────
@app.route("/api/settings", methods=["GET", "POST"])
def system_settings_route():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "GET":
        cur.execute("SELECT key, value FROM system_settings")
        settings_dict = {row["key"]: row["value"] for row in cur.fetchall()}
        conn.close()
        return jsonify({"settings": settings_dict})

    elif request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        key = data.get("key")
        value = data.get("value")
        user_id = data.get("user_id")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if key:
            cur.execute("""
                INSERT INTO system_settings (key, value, updated_at, updated_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                    updated_at = excluded.updated_at, updated_by = excluded.updated_by
            """, (key, str(value), now, user_id))
            conn.commit()
        conn.close()
        return jsonify({"ok": True})

# ── Database Migration / Seed Helper Endpoint ─────────────────────────────────
@app.route("/api/admin/migrate-seed", methods=["POST"])
def migrate_seed():
    """Seed data directly from a local CommitMaster database."""
    data = request.get_json(force=True, silent=True) or {}
    secret_key = data.get("secret_key")
    # Require matching admin credentials or secret
    if secret_key != os.getenv("ADMIN_MIGRATION_SECRET", "commitmaster-secret-seed-2026"):
        return jsonify({"error": "Unauthorized"}), 403

    users = data.get("users", [])
    conn = get_db()
    cur = conn.cursor()
    seeded_count = 0

    for u in users:
        try:
            cur.execute("""
                INSERT INTO users (username, email, full_name, password_hash, role, avatar_color, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    email = excluded.email,
                    full_name = excluded.full_name,
                    password_hash = excluded.password_hash,
                    role = excluded.role,
                    avatar_color = excluded.avatar_color
            """, (
                u["username"], u["email"], u.get("full_name", ""),
                u["password_hash"], u.get("role", "user"),
                u.get("avatar_color", "#3fb950"), u.get("is_active", 1)
            ))
            cur.execute("SELECT id FROM users WHERE username = ?", (u["username"],))
            row = cur.fetchone()
            if row:
                uid = row[0]
                cur.execute("INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (uid,))
            seeded_count += 1
        except Exception as e:
            logger.warning(f"Failed to seed user {u.get('username')}: {e}")

    conn.commit()
    conn.close()
    return jsonify({"ok": True, "seeded_users": seeded_count})

# ── Main Entrypoint ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print("=" * 60)
    print("CommitMaster Cloud Backend Server v3.0")
    print(f"Listening on http://{host}:{port}")
    print(f"Database: {DB_FILE}")
    print("=" * 60)
    app.run(host=host, port=port, debug=False)
