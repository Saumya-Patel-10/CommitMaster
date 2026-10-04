"""
CommitMaster — Database layer.
Manages SQLite database for users, sessions, and activity logs.
"""
import sqlite3
import hashlib
import os
import secrets
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

# Database file path (same directory as config.json)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(APP_DIR, "commitmaster.db")

_local = threading.local()


def get_conn() -> sqlite3.Connection:
    """Get a thread-local database connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db() -> None:
    """Initialize all database tables."""
    conn = get_conn()
    cur = conn.cursor()

    # ── Users table ────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL UNIQUE,
            email       TEXT    NOT NULL UNIQUE,
            full_name   TEXT    NOT NULL DEFAULT '',
            password_hash TEXT  NOT NULL,
            role        TEXT    NOT NULL DEFAULT 'user',
            avatar_color TEXT   NOT NULL DEFAULT '#3fb950',
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            last_login  TEXT,
            bio         TEXT    DEFAULT ''
        )
    """)

    # ── User preferences table ─────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id             INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            watched_apps        TEXT    DEFAULT '["Code.exe","Cursor.exe","Antigravity.exe"]',
            projects_dirs       TEXT    DEFAULT '[]',
            auto_commit         INTEGER DEFAULT 0,
            skip_sensitive      INTEGER DEFAULT 1,
            session_end_grace   INTEGER DEFAULT 120,
            ai_base_url         TEXT    DEFAULT 'http://localhost:1234/v1',
            ai_model            TEXT    DEFAULT '',
            theme               TEXT    DEFAULT 'dark',
            notifications       INTEGER DEFAULT 1
        )
    """)

    # ── Commit activity log ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS commit_activity (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            repo_path   TEXT    NOT NULL,
            repo_name   TEXT    NOT NULL,
            commit_hash TEXT    DEFAULT '',
            commit_msg  TEXT    NOT NULL,
            files_count INTEGER DEFAULT 0,
            status      TEXT    NOT NULL DEFAULT 'committed',
            committed_at TEXT   NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ── App usage log (daily) ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_usage (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date        TEXT    NOT NULL,
            sessions    INTEGER NOT NULL DEFAULT 1,
            commits_made INTEGER NOT NULL DEFAULT 0,
            repos_scanned INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, date)
        )
    """)

    # ── Session tokens ─────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT    PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            expires_at  TEXT    NOT NULL
        )
    """)

    # ── System settings (admin-controlled global defaults) ─────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key         TEXT    PRIMARY KEY,
            value       TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_by  INTEGER REFERENCES users(id)
        )
    """)

    conn.commit()

    # Create default admin if no users exist
    _ensure_default_admin(conn)


def _hash_password(password: str) -> str:
    """Hash a password using SHA-256 with a salt (bcrypt-style fallback)."""
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        salt = secrets.token_hex(16)
        hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return f"sha256${salt}${hashed}"


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        import bcrypt
        if password_hash.startswith("sha256$"):
            # Fallback sha256 path
            parts = password_hash.split("$")
            salt, stored = parts[1], parts[2]
            return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == stored
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ImportError:
        if password_hash.startswith("sha256$"):
            parts = password_hash.split("$")
            salt, stored = parts[1], parts[2]
            return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == stored
        return False


def _ensure_default_admin(conn: sqlite3.Connection) -> None:
    """Create default admin account if the users table is empty."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    if count == 0:
        pw_hash = _hash_password("admin123")
        cur.execute("""
            INSERT INTO users (username, email, full_name, password_hash, role, avatar_color)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("admin", "admin@commitmaster.local", "Administrator", pw_hash, "admin", "#f0883e"))
        admin_id = cur.lastrowid
        cur.execute("""
            INSERT INTO user_preferences (user_id) VALUES (?)
        """, (admin_id,))
        conn.commit()


def check_user_exists(username: str, email: str) -> Optional[str]:
    """Returns 'username' if username is taken, 'email' if email is taken, else None."""
    conn = get_conn()
    cur = conn.execute(
        "SELECT username, email FROM users WHERE LOWER(username) = ? OR LOWER(email) = ?",
        (username.strip().lower(), email.strip().lower())
    )
    row = cur.fetchone()
    if row:
        if row["username"].lower() == username.strip().lower():
            return "username"
        if row["email"].lower() == email.strip().lower():
            return "email"
    return None


def create_user(username: str, email: str, full_name: str, password: str,
                role: str = "user", avatar_color: str = "#3fb950") -> Optional[int]:
    """Create a new user. Returns user ID or None on failure."""
    conn = get_conn()
    try:
        pw_hash = _hash_password(password)
        cur = conn.execute("""
            INSERT INTO users (username, email, full_name, password_hash, role, avatar_color)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username.strip(), email.strip().lower(), full_name.strip(), pw_hash, role, avatar_color))
        uid = cur.lastrowid
        conn.execute("INSERT INTO user_preferences (user_id) VALUES (?)", (uid,))
        conn.commit()
        return uid
    except sqlite3.IntegrityError:
        return None


def authenticate(username_or_email: str, password: str) -> Optional[Dict]:
    """Authenticate user by username or email. Returns user dict or None."""
    conn = get_conn()
    cur = conn.execute("""
        SELECT * FROM users
        WHERE (username = ? OR email = ?) AND is_active = 1
    """, (username_or_email, username_or_email))
    row = cur.fetchone()
    if row and _verify_password(password, row["password_hash"]):
        conn.execute("UPDATE users SET last_login = datetime('now') WHERE id = ?", (row["id"],))
        conn.commit()
        _record_daily_session(row["id"])
        return dict(row)
    return None


def get_user(user_id: int) -> Optional[Dict]:
    """Get user by ID."""
    conn = get_conn()
    cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def get_all_users() -> List[Dict]:
    """Get all users (admin view)."""
    conn = get_conn()
    cur = conn.execute("""
        SELECT u.*, 
               (SELECT COUNT(*) FROM commit_activity WHERE user_id = u.id) as total_commits
        FROM users u
        ORDER BY u.created_at DESC
    """)
    return [dict(r) for r in cur.fetchall()]


def update_user(user_id: int, **kwargs) -> bool:
    """Update user fields. Supports: full_name, email, bio, avatar_color, is_active, role."""
    allowed = {"full_name", "email", "bio", "avatar_color", "is_active", "role"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    conn = get_conn()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?",
                 (*updates.values(), user_id))
    conn.commit()
    return True


def change_password(user_id: int, new_password: str) -> bool:
    """Change a user's password."""
    conn = get_conn()
    pw_hash = _hash_password(new_password)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
    conn.commit()
    return True


def delete_user(user_id: int) -> bool:
    """Soft-delete a user (deactivate)."""
    conn = get_conn()
    conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    conn.commit()
    return True


def hard_delete_user(user_id: int) -> bool:
    """Permanently delete a user and all their data."""
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return True


# ── Preferences ────────────────────────────────────────────────────────────────

def get_preferences(user_id: int) -> Optional[Dict]:
    """Get user preferences."""
    conn = get_conn()
    cur = conn.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def update_preferences(user_id: int, **kwargs) -> bool:
    """Update user preferences."""
    allowed = {
        "watched_apps", "projects_dirs", "auto_commit", "skip_sensitive",
        "session_end_grace", "ai_base_url", "ai_model", "theme", "notifications"
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    conn = get_conn()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE user_preferences SET {set_clause} WHERE user_id = ?",
                 (*updates.values(), user_id))
    conn.commit()
    return True


# ── Activity Logging ───────────────────────────────────────────────────────────

def log_commit(user_id: int, repo_path: str, commit_msg: str,
               files_count: int = 0, commit_hash: str = "",
               status: str = "committed") -> None:
    """Log a commit action."""
    repo_name = os.path.basename(repo_path.rstrip("/\\"))
    conn = get_conn()
    conn.execute("""
        INSERT INTO commit_activity (user_id, repo_path, repo_name, commit_hash, commit_msg, files_count, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, repo_path, repo_name, commit_hash, commit_msg, files_count, status))
    conn.commit()
    _increment_daily_commits(user_id)


def get_activity_log(user_id: Optional[int] = None, limit: int = 100) -> List[Dict]:
    """Get commit activity log, optionally filtered by user."""
    conn = get_conn()
    if user_id:
        cur = conn.execute("""
            SELECT ca.*, u.username, u.full_name, u.avatar_color
            FROM commit_activity ca
            JOIN users u ON ca.user_id = u.id
            WHERE ca.user_id = ?
            ORDER BY ca.committed_at DESC LIMIT ?
        """, (user_id, limit))
    else:
        cur = conn.execute("""
            SELECT ca.*, u.username, u.full_name, u.avatar_color
            FROM commit_activity ca
            JOIN users u ON ca.user_id = u.id
            ORDER BY ca.committed_at DESC LIMIT ?
        """, (limit,))
    return [dict(r) for r in cur.fetchall()]


def _record_daily_session(user_id: int) -> None:
    """Record a login session for daily usage tracking."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    conn.execute("""
        INSERT INTO app_usage (user_id, date, sessions)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, date) DO UPDATE SET sessions = sessions + 1
    """, (user_id, today))
    conn.commit()


def _increment_daily_commits(user_id: int) -> None:
    """Increment daily commit count for a user."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    conn.execute("""
        INSERT INTO app_usage (user_id, date, sessions, commits_made)
        VALUES (?, ?, 0, 1)
        ON CONFLICT(user_id, date) DO UPDATE SET commits_made = commits_made + 1
    """, (user_id, today))
    conn.commit()


def get_usage_stats(user_id: Optional[int] = None, days: int = 30) -> List[Dict]:
    """Get daily usage stats for charts."""
    conn = get_conn()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    if user_id:
        cur = conn.execute("""
            SELECT date, SUM(sessions) as sessions, SUM(commits_made) as commits_made
            FROM app_usage WHERE user_id = ? AND date >= ?
            GROUP BY date ORDER BY date
        """, (user_id, since))
    else:
        cur = conn.execute("""
            SELECT date, SUM(sessions) as sessions, SUM(commits_made) as commits_made,
                   COUNT(DISTINCT user_id) as active_users
            FROM app_usage WHERE date >= ?
            GROUP BY date ORDER BY date
        """, (since,))
    return [dict(r) for r in cur.fetchall()]


def get_dashboard_stats() -> Dict[str, Any]:
    """Get aggregate stats for the admin dashboard."""
    conn = get_conn()
    stats = {}

    cur = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
    stats["total_users"] = cur.fetchone()[0]

    cur = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    stats["total_admins"] = cur.fetchone()[0]

    cur = conn.execute("SELECT COUNT(*) FROM commit_activity")
    stats["total_commits"] = cur.fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")
    cur = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM app_usage WHERE date = ?", (today,))
    stats["active_today"] = cur.fetchone()[0]

    cur = conn.execute("""
        SELECT COUNT(*) FROM commit_activity
        WHERE committed_at >= datetime('now', '-7 days')
    """)
    stats["commits_this_week"] = cur.fetchone()[0]

    cur = conn.execute("""
        SELECT u.username, COUNT(ca.id) as commits
        FROM users u LEFT JOIN commit_activity ca ON u.id = ca.user_id
        GROUP BY u.id ORDER BY commits DESC LIMIT 5
    """)
    stats["top_committers"] = [dict(r) for r in cur.fetchall()]

    return stats


# ── Session tokens ─────────────────────────────────────────────────────────────

def create_session_token(user_id: int) -> str:
    """Create a session token for a user (for auto-login)."""
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires)
    )
    conn.commit()
    return token


def validate_session_token(token: str) -> Optional[Dict]:
    """Validate a session token and return the user dict if valid."""
    conn = get_conn()
    cur = conn.execute("""
        SELECT u.* FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > datetime('now') AND u.is_active = 1
    """, (token,))
    row = cur.fetchone()
    return dict(row) if row else None


def revoke_session_token(user_id: int) -> None:
    """Revoke all session tokens for a user (logout)."""
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
