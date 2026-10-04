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

    # ── Linked GitHub accounts ────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS github_accounts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            account_name    TEXT    NOT NULL,
            github_username TEXT    NOT NULL,
            github_token    TEXT    NOT NULL,
            author_name     TEXT    DEFAULT '',
            author_email    TEXT    DEFAULT '',
            avatar_url      TEXT    DEFAULT '',
            is_default      INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ── Repository to GitHub account bindings ──────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS repo_github_accounts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            repo_path   TEXT    NOT NULL,
            account_id  INTEGER NOT NULL REFERENCES github_accounts(id) ON DELETE CASCADE,
            UNIQUE(user_id, repo_path)
        )
    """)

    # ── Watched repositories (GitHub repositories selected to keep an eye on) ─
    cur.execute("""
        CREATE TABLE IF NOT EXISTS watched_repositories (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            github_account_id INTEGER REFERENCES github_accounts(id) ON DELETE SET NULL,
            repo_name         TEXT    NOT NULL,
            repo_full_name    TEXT    NOT NULL,
            clone_url         TEXT    DEFAULT '',
            ssh_url           TEXT    DEFAULT '',
            default_branch    TEXT    DEFAULT 'main',
            local_path        TEXT    DEFAULT '',
            is_private        INTEGER NOT NULL DEFAULT 0,
            description       TEXT    DEFAULT '',
            is_active_watch   INTEGER NOT NULL DEFAULT 1,
            last_scanned      TEXT,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, repo_full_name)
        )
    """)

    # ── Migrations for existing user_preferences ──────────────────────────────
    for col_name, col_type in [
        ("accent_color", "TEXT DEFAULT '#3fb950'"),
        ("font_family", "TEXT DEFAULT 'Segoe UI'"),
        ("font_scale", "TEXT DEFAULT 'standard'"),
        ("ui_density", "TEXT DEFAULT 'comfortable'"),
        ("auto_push", "INTEGER DEFAULT 0"),
        ("ask_before_push", "INTEGER DEFAULT 1"),
    ]:
        try:
            cur.execute(f"ALTER TABLE user_preferences ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

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


# ── User CRUD ──────────────────────────────────────────────────────────────────

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
        "session_end_grace", "ai_base_url", "ai_model", "theme", "notifications",
        "accent_color", "font_family", "font_scale", "ui_density", "auto_push",
        "ask_before_push"
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


# ── Linked GitHub Accounts ───────────────────────────────────────────────────

def add_github_account(user_id: int, account_name: str, github_username: str,
                       github_token: str, author_name: str = "", author_email: str = "",
                       avatar_url: str = "", is_default: bool = False) -> Optional[int]:
    """Add a new GitHub account for a user. Returns account ID or None on failure."""
    conn = get_conn()
    cur = conn.cursor()

    # If first account or is_default, make it default
    cur.execute("SELECT COUNT(*) FROM github_accounts WHERE user_id = ?", (user_id,))
    count = cur.fetchone()[0]
    default_val = 1 if (is_default or count == 0) else 0

    if default_val == 1:
        # Clear other defaults for this user
        conn.execute("UPDATE github_accounts SET is_default = 0 WHERE user_id = ?", (user_id,))

    cur.execute("""
        INSERT INTO github_accounts (
            user_id, account_name, github_username, github_token,
            author_name, author_email, avatar_url, is_default
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, account_name.strip(), github_username.strip(), github_token.strip(),
        author_name.strip(), author_email.strip(), avatar_url.strip(), default_val
    ))
    conn.commit()
    return cur.lastrowid


def update_github_account(account_id: int, user_id: int, **kwargs) -> bool:
    """Update a linked GitHub account's details."""
    allowed = {"account_name", "github_username", "github_token", "author_name", "author_email", "avatar_url", "is_default"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    conn = get_conn()
    if updates.get("is_default"):
        conn.execute("UPDATE github_accounts SET is_default = 0 WHERE user_id = ?", (user_id,))

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE github_accounts SET {set_clause} WHERE id = ? AND user_id = ?",
                 (*updates.values(), account_id, user_id))
    conn.commit()
    return True


def delete_github_account(account_id: int, user_id: int) -> bool:
    """Delete a linked GitHub account."""
    conn = get_conn()
    # Check if was default
    cur = conn.execute("SELECT is_default FROM github_accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
    row = cur.fetchone()
    was_default = row and row["is_default"]

    conn.execute("DELETE FROM github_accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
    conn.commit()

    if was_default:
        # Set next available account as default if any exist
        cur = conn.execute("SELECT id FROM github_accounts WHERE user_id = ? ORDER BY id ASC LIMIT 1", (user_id,))
        next_row = cur.fetchone()
        if next_row:
            conn.execute("UPDATE github_accounts SET is_default = 1 WHERE id = ?", (next_row["id"],))
            conn.commit()

    return True


def get_github_accounts(user_id: int) -> List[Dict]:
    """Get all linked GitHub accounts for a user."""
    conn = get_conn()
    cur = conn.execute("""
        SELECT ga.*, 
               (SELECT COUNT(*) FROM repo_github_accounts WHERE account_id = ga.id) as bound_repos_count
        FROM github_accounts ga
        WHERE ga.user_id = ?
        ORDER BY ga.is_default DESC, ga.created_at ASC
    """, (user_id,))
    return [dict(r) for r in cur.fetchall()]


def get_github_account(account_id: int, user_id: Optional[int] = None) -> Optional[Dict]:
    """Get a specific GitHub account by ID."""
    conn = get_conn()
    if user_id:
        cur = conn.execute("SELECT * FROM github_accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
    else:
        cur = conn.execute("SELECT * FROM github_accounts WHERE id = ?", (account_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def set_default_github_account(account_id: int, user_id: int) -> bool:
    """Set an account as the default GitHub account for a user."""
    conn = get_conn()
    conn.execute("UPDATE github_accounts SET is_default = 0 WHERE user_id = ?", (user_id,))
    conn.execute("UPDATE github_accounts SET is_default = 1 WHERE id = ? AND user_id = ?", (account_id, user_id))
    conn.commit()
    return True


def get_default_github_account(user_id: int) -> Optional[Dict]:
    """Get the user's default GitHub account."""
    conn = get_conn()
    cur = conn.execute("""
        SELECT * FROM github_accounts
        WHERE user_id = ? AND is_default = 1
        LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    if not row:
        # Fallback to any account if default flag wasn't set
        cur = conn.execute("SELECT * FROM github_accounts WHERE user_id = ? ORDER BY id ASC LIMIT 1", (user_id,))
        row = cur.fetchone()
    return dict(row) if row else None


# ── Repository to GitHub Account Bindings ─────────────────────────────────────

def bind_repo_to_account(user_id: int, repo_path: str, account_id: int) -> bool:
    """Bind a local repository path to a specific GitHub account."""
    norm_path = os.path.normpath(repo_path)
    conn = get_conn()
    conn.execute("""
        INSERT INTO repo_github_accounts (user_id, repo_path, account_id)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, repo_path) DO UPDATE SET account_id = excluded.account_id
    """, (user_id, norm_path, account_id))
    conn.commit()
    return True


def unbind_repo_account(user_id: int, repo_path: str) -> bool:
    """Remove repository to account binding (will use default account instead)."""
    norm_path = os.path.normpath(repo_path)
    conn = get_conn()
    conn.execute("DELETE FROM repo_github_accounts WHERE user_id = ? AND repo_path = ?", (user_id, norm_path))
    conn.commit()
    return True


def get_repo_account(user_id: int, repo_path: str) -> Optional[Dict]:
    """Get the GitHub account assigned to a specific repo (or fallback to default account)."""
    norm_path = os.path.normpath(repo_path)
    conn = get_conn()
    cur = conn.execute("""
        SELECT ga.* FROM repo_github_accounts rga
        JOIN github_accounts ga ON rga.account_id = ga.id
        WHERE rga.user_id = ? AND rga.repo_path = ?
    """, (user_id, norm_path))
    row = cur.fetchone()
    if row:
        return dict(row)
    # Fallback to user's default account
    return get_default_github_account(user_id)


def get_all_repo_bindings(user_id: int) -> Dict[str, int]:
    """Get all repo_path -> account_id bindings for a user."""
    conn = get_conn()
    cur = conn.execute("SELECT repo_path, account_id FROM repo_github_accounts WHERE user_id = ?", (user_id,))
    return {row["repo_path"]: row["account_id"] for row in cur.fetchall()}


# ── System Settings Helpers ──────────────────────────────────────────────────

def get_system_setting(key: str, default: str = "") -> str:
    """Get a system setting value."""
    conn = get_conn()
    cur = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
    row = cur.fetchone()
    return row["value"] if row else default


def set_system_setting(key: str, value: str, user_id: Optional[int] = None) -> bool:
    """Set a system setting value."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    conn.execute("""
        INSERT INTO system_settings (key, value, updated_at, updated_by)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value,
            updated_at = excluded.updated_at, updated_by = excluded.updated_by
    """, (key, str(value), now, user_id))
    conn.commit()
    return True


def get_all_system_settings() -> Dict[str, str]:
    """Get all system settings as a dictionary."""
    conn = get_conn()
    cur = conn.execute("SELECT key, value FROM system_settings")
    return {row["key"]: row["value"] for row in cur.fetchall()}


# ── Watched Repositories Operations ──────────────────────────────────────────

def add_or_update_watched_repo(
    user_id: int,
    repo_full_name: str,
    repo_name: str,
    clone_url: str = "",
    ssh_url: str = "",
    default_branch: str = "main",
    local_path: str = "",
    is_private: int = 0,
    description: str = "",
    github_account_id: Optional[int] = None,
    is_active_watch: int = 1,
) -> int:
    """Insert or update a watched GitHub repository."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO watched_repositories (
            user_id, github_account_id, repo_name, repo_full_name,
            clone_url, ssh_url, default_branch, local_path,
            is_private, description, is_active_watch
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, repo_full_name) DO UPDATE SET
            github_account_id = COALESCE(excluded.github_account_id, watched_repositories.github_account_id),
            repo_name = excluded.repo_name,
            clone_url = excluded.clone_url,
            ssh_url = excluded.ssh_url,
            default_branch = excluded.default_branch,
            is_private = excluded.is_private,
            description = excluded.description,
            local_path = CASE WHEN excluded.local_path != '' THEN excluded.local_path ELSE watched_repositories.local_path END
    """, (
        user_id, github_account_id, repo_name, repo_full_name,
        clone_url, ssh_url, default_branch, local_path,
        1 if is_private else 0, description or "", is_active_watch,
    ))
    conn.commit()
    return cur.lastrowid


def toggle_watched_repo(repo_id: int, user_id: int, is_active: Optional[bool] = None) -> bool:
    """Toggle or set the active watch status of a repository."""
    conn = get_conn()
    if is_active is None:
        conn.execute("""
            UPDATE watched_repositories
            SET is_active_watch = CASE WHEN is_active_watch = 1 THEN 0 ELSE 1 END
            WHERE id = ? AND user_id = ?
        """, (repo_id, user_id))
    else:
        conn.execute("""
            UPDATE watched_repositories
            SET is_active_watch = ?
            WHERE id = ? AND user_id = ?
        """, (1 if is_active else 0, repo_id, user_id))
    conn.commit()
    return True


def set_watched_repo_local_path(repo_id: int, user_id: int, local_path: str) -> bool:
    """Assign or update the local folder path for a watched repository."""
    norm_path = os.path.normpath(local_path) if local_path else ""
    conn = get_conn()
    conn.execute("""
        UPDATE watched_repositories
        SET local_path = ?
        WHERE id = ? AND user_id = ?
    """, (norm_path, repo_id, user_id))
    conn.commit()
    return True


def delete_watched_repo(repo_id: int, user_id: int) -> bool:
    """Remove a repository from the user's watched list."""
    conn = get_conn()
    conn.execute("DELETE FROM watched_repositories WHERE id = ? AND user_id = ?", (repo_id, user_id))
    conn.commit()
    return True


def get_watched_repos(user_id: Optional[int] = None, active_only: bool = False) -> List[Dict]:
    """Retrieve watched repositories (optionally filtered by user and active watch status)."""
    conn = get_conn()
    query = """
        SELECT wr.*, ga.account_name, ga.github_username
        FROM watched_repositories wr
        LEFT JOIN github_accounts ga ON wr.github_account_id = ga.id
    """
    conditions = []
    params = []
    if user_id is not None:
        conditions.append("wr.user_id = ?")
        params.append(user_id)
    if active_only:
        conditions.append("wr.is_active_watch = 1")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY wr.is_active_watch DESC, wr.repo_name ASC"
    cur = conn.execute(query, tuple(params))
    return [dict(r) for r in cur.fetchall()]


def get_watched_repo_by_path(local_path: str, user_id: Optional[int] = None) -> Optional[Dict]:
    """Find a watched repository by its local folder path."""
    if not local_path:
        return None
    norm_path = os.path.normpath(local_path)
    conn = get_conn()
    query = "SELECT * FROM watched_repositories WHERE local_path = ?"
    params = [norm_path]
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    cur = conn.execute(query, tuple(params))
    row = cur.fetchone()
    return dict(row) if row else None


def sync_github_repos(user_id: int, github_account_id: int, repos_list: List[Dict]) -> int:
    """Bulk upsert repositories discovered from GitHub for a user."""
    conn = get_conn()
    count = 0
    for repo in repos_list:
        full_name = repo.get("full_name") or repo.get("name")
        if not full_name:
            continue
        name = repo.get("name") or full_name.split("/")[-1]
        clone_url = repo.get("clone_url", "")
        ssh_url = repo.get("ssh_url", "")
        default_branch = repo.get("default_branch", "main")
        is_private = 1 if repo.get("private") else 0
        desc = repo.get("description") or ""

        conn.execute("""
            INSERT INTO watched_repositories (
                user_id, github_account_id, repo_name, repo_full_name,
                clone_url, ssh_url, default_branch, is_private, description, is_active_watch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(user_id, repo_full_name) DO UPDATE SET
                github_account_id = excluded.github_account_id,
                repo_name = excluded.repo_name,
                clone_url = excluded.clone_url,
                ssh_url = excluded.ssh_url,
                default_branch = excluded.default_branch,
                is_private = excluded.is_private,
                description = excluded.description
        """, (user_id, github_account_id, name, full_name, clone_url, ssh_url, default_branch, is_private, desc))
        count += 1
    conn.commit()
    return count

