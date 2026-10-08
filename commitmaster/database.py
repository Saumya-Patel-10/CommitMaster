"""
CommitMaster — Database layer.
Manages database operations with dual-mode support:
  1. Central Cloud Backend Server (REST API via server_url for multi-device sync)
  2. Local SQLite fallback (commitmaster.db)
"""
import sqlite3
import hashlib
import os
import secrets
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple, Iterator
import requests

# Database file path (same directory as config.json or %LOCALAPPDATA%)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(APP_DIR, "commitmaster.db")

_local = threading.local()


def get_server_url() -> str:
    """Return configured CommitMaster Cloud Backend Server URL or empty string."""
    env_url = os.getenv("COMMITMASTER_SERVER_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    try:
        from commitmaster.config import load_config
        cfg = load_config()
        url = (cfg.get("server_url") or "").strip()
        if url:
            return url.rstrip("/")
    except Exception:
        pass
    return ""


def set_server_url(url: str) -> None:
    """Save the server URL into config.json and reload."""
    clean_url = (url or "").strip().rstrip("/")
    try:
        from commitmaster.config import load_config, save_config, get_manager
        cfg = load_config()
        cfg["server_url"] = clean_url
        save_config(cfg)
        try:
            get_manager().reload()
        except Exception:
            pass
    except Exception:
        pass


def test_server_connection(url: Optional[str] = None) -> Tuple[bool, str]:
    """Test connectivity to the backend server."""
    target_url = (url if url is not None else get_server_url()).strip().rstrip("/")
    if not target_url:
        return False, "No server URL provided (Local Mode)"
    try:
        resp = requests.get(f"{target_url}/api/health", timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            ver = data.get("version", "3.0")
            count = data.get("users_count", 0)
            return True, f"Connected to {data.get('service', 'CommitMaster Server')} (v{ver}, {count} users)"
        return False, f"Server responded with status {resp.status_code}"
    except requests.exceptions.Timeout:
        return False, "Connection timed out (server took too long to respond)"
    except requests.exceptions.ConnectionError:
        return False, f"Cannot connect to {target_url}. Check if the server is running."
    except Exception as exc:
        return False, f"Connection error: {exc}"


def _cache_user_locally(user: Dict, password: Optional[str] = None) -> None:
    """Cache user in local SQLite database for offline resiliency."""
    try:
        conn = get_conn()
        pw_hash = _hash_password(password) if password else user.get("password_hash", "")
        conn.execute("""
            INSERT INTO users (id, username, email, full_name, password_hash, role, avatar_color, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                email = excluded.email,
                full_name = excluded.full_name,
                role = excluded.role,
                avatar_color = excluded.avatar_color,
                is_active = excluded.is_active
        """, (
            user["id"], user["username"], user["email"],
            user.get("full_name", ""), pw_hash or "remote_auth",
            user.get("role", "user"), user.get("avatar_color", "#3fb950"),
            user.get("is_active", 1)
        ))
        conn.execute("INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (user["id"],))
        conn.commit()
    except Exception:
        pass


def get_conn() -> sqlite3.Connection:
    """Get a thread-local database connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def close_conn() -> None:
    """Close and clear the thread-local database connection."""
    if hasattr(_local, "conn") and _local.conn is not None:
        try:
            _local.conn.close()
        except Exception:
            pass
        _local.conn = None


def fetch_rows_iter(query: str, params: tuple = ()) -> Iterator[sqlite3.Row]:
    """
    Execute a parameterized SQL query and yield rows row-by-row.
    Avoids loading full query result sets into memory (Requirement 6).
    """
    conn = get_conn()
    cur = conn.execute(query, params)
    for row in cur:
        yield row


def init_db() -> None:
    """Initialize all database tables."""
    conn = get_conn()
    cur = conn.cursor()

    # ── Users table ────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL UNIQUE,
            email       TEXT    NOT NULL,
            full_name   TEXT    NOT NULL DEFAULT '',
            password_hash TEXT  NOT NULL,
            role        TEXT    NOT NULL DEFAULT 'user',
            avatar_color TEXT   NOT NULL DEFAULT '#3fb950',
            avatar_image TEXT   DEFAULT '',
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            last_login  TEXT,
            bio         TEXT    DEFAULT '',
            is_verified INTEGER NOT NULL DEFAULT 0,
            google_id   TEXT    DEFAULT '',
            deleted_at  TEXT    DEFAULT NULL,
            deletion_scheduled_until TEXT DEFAULT NULL
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
            notifications       INTEGER DEFAULT 1,
            reminder_interval_enabled    INTEGER DEFAULT 1,
            reminder_interval_hours      INTEGER DEFAULT 1,
            reminder_interval_minutes    INTEGER DEFAULT 0,
            reminder_app_monitor_enabled INTEGER DEFAULT 1,
            reminder_only_if_dirty       INTEGER DEFAULT 1
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

    # ── Application events (scans, failures, pushes, AI usage) for analytics ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            kind        TEXT    NOT NULL,
            repo_name   TEXT    NOT NULL DEFAULT '',
            files       INTEGER NOT NULL DEFAULT 0,
            errors      INTEGER NOT NULL DEFAULT 0,
            security    INTEGER NOT NULL DEFAULT 0,
            warnings    INTEGER NOT NULL DEFAULT 0,
            detail      TEXT    NOT NULL DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_app_events_kind_time ON app_events(kind, created_at)")

    # ── Verification OTPs (for Google and account verification) ────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS verification_otps (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    NOT NULL,
            otp_code    TEXT    NOT NULL,
            purpose     TEXT    NOT NULL DEFAULT 'verify_account',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            expires_at  TEXT    NOT NULL,
            is_used     INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_verification_otps_email ON verification_otps(email, purpose, is_used)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_verification_otps_email_only ON verification_otps(email)")

    # ── Foreign Key & Email Indexes (Requirement 5) ──────────────────────────
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_commit_activity_user_id ON commit_activity(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_commit_activity_repo ON commit_activity(user_id, repo_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_app_usage_user_id ON app_usage(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_system_settings_updated_by ON system_settings(updated_by)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_github_accounts_user_id ON github_accounts(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_repo_github_accounts_user_id ON repo_github_accounts(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_repo_github_accounts_account_id ON repo_github_accounts(account_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_watched_repositories_user_id ON watched_repositories(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_watched_repositories_github_account_id ON watched_repositories(github_account_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_app_events_user_id ON app_events(user_id)")

    # ── Login Rate Limiting Table (Security Checklist Item 11) ───────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS login_rate_limit (
            identifier  TEXT PRIMARY KEY,
            fail_count  INTEGER NOT NULL DEFAULT 1,
            last_failed TEXT NOT NULL,
            locked_until TEXT DEFAULT NULL
        )
    """)

    # ── Migrations for existing user_preferences ──────────────────────────────
    try:
        existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(user_preferences)")}
        migration_ddls = {
            "accent_color": "ALTER TABLE user_preferences ADD COLUMN accent_color TEXT DEFAULT '#3fb950'",
            "font_family": "ALTER TABLE user_preferences ADD COLUMN font_family TEXT DEFAULT 'Segoe UI'",
            "font_scale": "ALTER TABLE user_preferences ADD COLUMN font_scale TEXT DEFAULT 'standard'",
            "ui_density": "ALTER TABLE user_preferences ADD COLUMN ui_density TEXT DEFAULT 'comfortable'",
            "auto_push": "ALTER TABLE user_preferences ADD COLUMN auto_push INTEGER DEFAULT 0",
            "ask_before_push": "ALTER TABLE user_preferences ADD COLUMN ask_before_push INTEGER DEFAULT 1",
            "ai_provider": "ALTER TABLE user_preferences ADD COLUMN ai_provider TEXT DEFAULT 'bionic'",
            "openai_api_key": "ALTER TABLE user_preferences ADD COLUMN openai_api_key TEXT DEFAULT ''",
            "claude_api_key": "ALTER TABLE user_preferences ADD COLUMN claude_api_key TEXT DEFAULT ''",
            "gemini_api_key": "ALTER TABLE user_preferences ADD COLUMN gemini_api_key TEXT DEFAULT ''",
            "openai_model": "ALTER TABLE user_preferences ADD COLUMN openai_model TEXT DEFAULT 'gpt-4o-mini'",
            "claude_model": "ALTER TABLE user_preferences ADD COLUMN claude_model TEXT DEFAULT 'claude-3-5-haiku-20241022'",
            "gemini_model": "ALTER TABLE user_preferences ADD COLUMN gemini_model TEXT DEFAULT 'gemini-1.5-flash'",
            "reminder_interval_enabled": "ALTER TABLE user_preferences ADD COLUMN reminder_interval_enabled INTEGER DEFAULT 1",
            "reminder_interval_hours": "ALTER TABLE user_preferences ADD COLUMN reminder_interval_hours INTEGER DEFAULT 1",
            "reminder_interval_minutes": "ALTER TABLE user_preferences ADD COLUMN reminder_interval_minutes INTEGER DEFAULT 0",
            "reminder_app_monitor_enabled": "ALTER TABLE user_preferences ADD COLUMN reminder_app_monitor_enabled INTEGER DEFAULT 1",
            "reminder_only_if_dirty": "ALTER TABLE user_preferences ADD COLUMN reminder_only_if_dirty INTEGER DEFAULT 1",
            "bg_pattern": "ALTER TABLE user_preferences ADD COLUMN bg_pattern TEXT DEFAULT 'dot_matrix'",
        }
        for col_name, ddl in migration_ddls.items():
            if col_name not in existing_cols:
                cur.execute(ddl)
    except Exception:
        pass

    # ── Migrations for existing users table ────────────────────────────────────
    try:
        user_cols = {row[1] for row in cur.execute("PRAGMA table_info(users)")}
        if "is_verified" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER NOT NULL DEFAULT 0")
        if "google_id" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN google_id TEXT DEFAULT ''")
        if "avatar_image" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN avatar_image TEXT DEFAULT ''")
        if "deleted_at" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN deleted_at TEXT DEFAULT NULL")
        if "deletion_scheduled_until" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN deletion_scheduled_until TEXT DEFAULT NULL")

        # Migrate users table if unique constraint exists on email
        sql_row = cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if sql_row and "email TEXT NOT NULL UNIQUE" in (sql_row[0] or ""):
            cur.execute("PRAGMA foreign_keys=OFF")
            cur.execute("""
                CREATE TABLE users_migrated (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    username    TEXT    NOT NULL UNIQUE,
                    email       TEXT    NOT NULL,
                    full_name   TEXT    NOT NULL DEFAULT '',
                    password_hash TEXT  NOT NULL,
                    role        TEXT    NOT NULL DEFAULT 'user',
                    avatar_color TEXT   NOT NULL DEFAULT '#3fb950',
                    avatar_image TEXT   DEFAULT '',
                    is_active   INTEGER NOT NULL DEFAULT 1,
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                    last_login  TEXT,
                    bio         TEXT    DEFAULT '',
                    is_verified INTEGER NOT NULL DEFAULT 0,
                    google_id   TEXT    DEFAULT '',
                    deleted_at  TEXT    DEFAULT NULL,
                    deletion_scheduled_until TEXT DEFAULT NULL
                )
            """)
            cur.execute("""
                INSERT INTO users_migrated (id, username, email, full_name, password_hash, role, avatar_color, avatar_image, is_active, created_at, last_login, bio, is_verified, google_id)
                SELECT id, username, email, full_name, password_hash, role, avatar_color,
                       COALESCE(avatar_image, ''), is_active, created_at, last_login, bio,
                       COALESCE(is_verified, 0), COALESCE(google_id, '')
                FROM users
            """)
            cur.execute("DROP TABLE users")
            cur.execute("ALTER TABLE users_migrated RENAME TO users")
            cur.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass

    conn.commit()

    # Automatically purge any accounts whose 30-day recovery grace period has expired
    try:
        clean_expired_deleted_accounts()
    except Exception:
        pass

    # Create default admin if no users exist
    _ensure_default_admin(conn)


import re
from typing import Iterator

# ── Row-by-Row Fetching Generator (Requirement 6) ─────────────────────────────

def fetch_rows_iter(query: str, params: tuple = ()) -> Iterator[Dict[str, Any]]:
    """
    Fetch database records row by row using a generator cursor to minimize memory footprint.
    Eliminates allocating large list buffers when querying datasets.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    while True:
        row = cur.fetchone()
        if row is None:
            break
        yield dict(row)


# ── Input Validation (Security Checklist Item 14) ─────────────────────────────

def validate_username(username: str) -> Tuple[bool, str]:
    """Validate username length and characters against injection attacks."""
    if not username or len(username.strip()) < 3:
        return False, "Username must be at least 3 characters."
    if len(username.strip()) > 64:
        return False, "Username cannot exceed 64 characters."
    if not re.match(r"^[a-zA-Z0-9_@#\.\-]+$", username.strip()):
        return False, "Username contains forbidden characters (use alphanumeric, _, @, #, ., -)."
    return True, ""


def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email address format strictly."""
    if not email or len(email.strip()) < 5:
        return False, "Email address cannot be empty."
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
        return False, "Invalid email address format."
    return True, ""


# ── Password Hashing & Verification (Security Checklist Item 10) ─────────────

def _hash_password(password: str) -> str:
    """Hash a password using bcrypt if installed, or PBKDF2-HMAC-SHA256 (600,000 iterations)."""
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        salt = secrets.token_hex(16)
        iterations = 600000
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return f"pbkdf2:sha256:{iterations}${salt}${key.hex()}"


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against bcrypt, PBKDF2, or legacy salted SHA-256."""
    if not password_hash:
        return False
    # Bcrypt
    if password_hash.startswith("$2b$") or password_hash.startswith("$2a$"):
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False
    # PBKDF2-HMAC-SHA256
    if password_hash.startswith("pbkdf2:sha256:"):
        try:
            parts = password_hash.split("$")
            iter_part = parts[0].split(":")[2]
            salt = parts[1]
            stored_hex = parts[2]
            iterations = int(iter_part)
            computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
            return secrets.compare_digest(computed.hex(), stored_hex)
        except Exception:
            return False
    # Legacy salted SHA-256 fallback
    if password_hash.startswith("sha256$"):
        try:
            parts = password_hash.split("$")
            salt, stored = parts[1], parts[2]
            computed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
            return secrets.compare_digest(computed, stored)
        except Exception:
            return False
    return False


# ── Login Rate Limiting (Security Checklist Item 11) ──────────────────────────

def check_login_rate_limit(identifier: str) -> Tuple[bool, str]:
    """Check if identifier (username/email) has exceeded failed login attempts."""
    try:
        conn = get_conn()
        now = datetime.now()
        cur = conn.execute("SELECT fail_count, locked_until FROM login_rate_limit WHERE identifier = ?", (identifier.strip().lower(),))
        row = cur.fetchone()
        if not row:
            return True, ""
        if row["locked_until"]:
            locked_dt = datetime.strptime(row["locked_until"], "%Y-%m-%d %H:%M:%S")
            if now < locked_dt:
                wait_min = max(1, int((locked_dt - now).total_seconds() // 60) + 1)
                return False, f"Too many failed login attempts. Temporarily locked for {wait_min} more minute(s)."
            else:
                conn.execute("DELETE FROM login_rate_limit WHERE identifier = ?", (identifier.strip().lower(),))
                conn.commit()
                return True, ""
        return True, ""
    except Exception:
        return True, ""


def record_failed_login(identifier: str) -> None:
    """Increment failed login attempts and lock after 5 failures for 15 minutes."""
    try:
        conn = get_conn()
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute("SELECT fail_count FROM login_rate_limit WHERE identifier = ?", (identifier.strip().lower(),))
        row = cur.fetchone()
        if row:
            fails = row["fail_count"] + 1
            locked_until = (now + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S") if fails >= 5 else None
            conn.execute("UPDATE login_rate_limit SET fail_count = ?, last_failed = ?, locked_until = ? WHERE identifier = ?",
                         (fails, now_str, locked_until, identifier.strip().lower()))
        else:
            conn.execute("INSERT INTO login_rate_limit (identifier, fail_count, last_failed) VALUES (?, 1, ?)",
                         (identifier.strip().lower(), now_str))
        conn.commit()
    except Exception:
        pass


def clear_failed_login(identifier: str) -> None:
    """Reset failed login count upon successful authentication."""
    try:
        conn = get_conn()
        conn.execute("DELETE FROM login_rate_limit WHERE identifier = ?", (identifier.strip().lower(),))
        conn.commit()
    except Exception:
        pass


# ── Response Trimming Helper (Security Checklist Item 17) ─────────────────────

def _clean_user_dict(user: Optional[Dict]) -> Optional[Dict]:
    """Strip password_hash and internal secrets before returning user objects to callers."""
    if not user:
        return None
    d = dict(user)
    d.pop("password_hash", None)
    return d



DEFAULT_ADMIN_USERNAME = "saumya.patel@Admin_#"


def get_admin_username() -> str:
    """Return the designated admin username, defaults to 'saumya.patel@Admin_#'."""
    return get_system_setting("admin_username", DEFAULT_ADMIN_USERNAME) or DEFAULT_ADMIN_USERNAME


def is_admin_username(username: Optional[str]) -> bool:
    """Check if the provided username is the designated admin username."""
    if not username:
        return False
    return username.strip().lower() == get_admin_username().strip().lower()


def set_admin_username(new_username: str, admin_user_id: Optional[int] = None) -> Tuple[bool, str]:
    """
    Update the designated admin username in system settings and users table.
    From then on, ONLY this username can access the Admin Portal.
    """
    new_username = new_username.strip()
    if not new_username:
        return False, "Username cannot be empty."
    if " " in new_username:
        return False, "Username cannot contain spaces."

    current_admin = get_admin_username()
    if new_username == current_admin:
        return True, "Admin username is already set to this value."

    conn = get_conn()
    cur = conn.cursor()

    # Check if another user already has this username
    cur.execute("SELECT id, username FROM users WHERE LOWER(username) = LOWER(?)", (new_username,))
    existing = cur.fetchone()
    if existing and (not admin_user_id or existing["id"] != admin_user_id):
        return False, f"Username '{new_username}' is already in use by another user."

    if admin_user_id:
        cur.execute("SELECT id, username FROM users WHERE id = ?", (admin_user_id,))
    else:
        cur.execute("SELECT id, username FROM users WHERE LOWER(username) = LOWER(?)", (current_admin,))
    admin_row = cur.fetchone()

    if admin_row:
        cur.execute("UPDATE users SET username = ?, role = 'admin' WHERE id = ?", (new_username, admin_row["id"]))
    elif existing:
        cur.execute("UPDATE users SET role = 'admin' WHERE id = ?", (existing["id"],))

    # Demote any other accounts claiming admin
    cur.execute("UPDATE users SET role = 'user' WHERE role = 'admin' AND LOWER(username) != LOWER(?)", (new_username,))

    set_system_setting("admin_username", new_username, user_id=admin_user_id)
    conn.commit()
    return True, f"Admin username successfully changed to '{new_username}'."


def mark_user_verified(user_id_or_email: Any, google_id: str = "") -> bool:
    """Mark a user account as email/Google verified."""
    conn = get_conn()
    if google_id:
        if isinstance(user_id_or_email, int):
            conn.execute("UPDATE users SET is_verified = 1, google_id = ? WHERE id = ?", (google_id, user_id_or_email))
        else:
            conn.execute("UPDATE users SET is_verified = 1, google_id = ? WHERE LOWER(email) = LOWER(?)", (google_id, str(user_id_or_email).strip()))
    else:
        if isinstance(user_id_or_email, int):
            conn.execute("UPDATE users SET is_verified = 1 WHERE id = ?", (user_id_or_email,))
        else:
            conn.execute("UPDATE users SET is_verified = 1 WHERE LOWER(email) = LOWER(?)", (str(user_id_or_email).strip(),))
    conn.commit()
    return True


def save_verification_otp(email: str, code: str, purpose: str = "verify_account", expiry_minutes: int = 10) -> bool:
    """Save a 6-digit verification OTP with expiration."""
    conn = get_conn()
    conn.execute("UPDATE verification_otps SET is_used = 1 WHERE LOWER(email) = LOWER(?) AND purpose = ?", (email.strip(), purpose))
    expires_at = (datetime.now() + timedelta(minutes=expiry_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO verification_otps (email, otp_code, purpose, expires_at, is_used)
        VALUES (?, ?, ?, ?, 0)
    """, (email.strip().lower(), code.strip(), purpose, expires_at))
    conn.commit()
    return True


def verify_stored_otp(email: str, code: str, purpose: str = "verify_account") -> Tuple[bool, str]:
    """Verify stored OTP code for email."""
    conn = get_conn()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute("""
        SELECT id, otp_code, expires_at, is_used FROM verification_otps
        WHERE LOWER(email) = LOWER(?) AND purpose = ? AND is_used = 0
        ORDER BY id DESC LIMIT 1
    """, (email.strip(), purpose))
    row = cur.fetchone()
    if not row:
        return False, "No active verification code found for this email. Please request a new code."
    if row["expires_at"] < now_str:
        return False, "Verification code has expired. Please request a new code."
    if row["otp_code"] != code.strip():
        return False, "Invalid verification code. Please check and try again."
    conn.execute("UPDATE verification_otps SET is_used = 1 WHERE id = ?", (row["id"],))
    conn.commit()
    mark_user_verified(email)
    return True, "Verification successful!"


def is_user_verified(user_id_or_email: Any) -> bool:
    """Check if a user is verified."""
    conn = get_conn()
    try:
        if isinstance(user_id_or_email, int):
            cur = conn.execute("SELECT is_verified FROM users WHERE id = ?", (user_id_or_email,))
        else:
            cur = conn.execute("SELECT is_verified FROM users WHERE LOWER(email) = LOWER(?)", (str(user_id_or_email).strip(),))
        row = cur.fetchone()
        return bool(row["is_verified"]) if row and "is_verified" in row.keys() else False
    except Exception:
        return False


def _ensure_default_admin(conn: sqlite3.Connection) -> None:
    """Ensure there is one and only one admin account matching get_admin_username()."""
    admin_uname = get_admin_username()
    cur = conn.cursor()
    # Remove any generic admin user
    cur.execute("DELETE FROM users WHERE username = 'admin'")
    # Demote any other accounts claiming the admin role
    cur.execute("UPDATE users SET role = 'user' WHERE role = 'admin' AND username != ?", (admin_uname,))

    cur.execute("SELECT id FROM users WHERE username = ?", (admin_uname,))
    row = cur.fetchone()
    if not row:
        pw_hash = _hash_password("admin123")
        cur.execute("""
            INSERT INTO users (username, email, full_name, password_hash, role, avatar_color, is_verified)
            VALUES (?, ?, ?, ?, 'admin', '#3fb950', 1)
        """, (admin_uname, "saumya.a.patel@gmail.com", "Saumya Patel", pw_hash))
        admin_id = cur.lastrowid
        cur.execute("INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (admin_id,))
    else:
        cur.execute("UPDATE users SET role = 'admin', is_verified = 1 WHERE username = ?", (admin_uname,))
    conn.commit()


# ── User CRUD ──────────────────────────────────────────────────────────────────

def check_user_exists(username: str, email: str = "") -> Optional[str]:
    """
    Check if a username or email is already taken.
    Returns 'username' if username exists, 'email' if email exists, or None.
    """
    url = get_server_url()
    if url:
        try:
            resp = requests.post(f"{url}/api/auth/check", json={
                "username": username.strip(),
                "email": email.strip().lower()
            }, timeout=6)
            if resp.status_code == 200:
                conflict = resp.json().get("conflict")
                if conflict:
                    return conflict
        except Exception:
            pass

    conn = get_conn()
    cur = conn.execute("""
        SELECT username, email FROM users
        WHERE LOWER(username) = LOWER(?) OR (LOWER(email) = LOWER(?) AND ? != '')
    """, (username.strip(), email.strip().lower(), email.strip()))
    rows = cur.fetchall()
    for row in rows:
        if row["username"].lower() == username.strip().lower():
            return "username"
        if email.strip() and row["email"] and row["email"].lower() == email.strip().lower():
            return "email"
    return None


def create_user(username: str, email: str, full_name: str, password: str,
                role: str = "user", avatar_color: str = "#3fb950", avatar_image: str = "") -> Optional[int]:
    """Create a new user. Returns user ID or None on failure."""
    # Enforce strictly: only designated admin username is admin. All other accounts are strictly standard users.
    if not is_admin_username(username.strip()):
        role = "user"
    url = get_server_url()
    if url:
        try:
            resp = requests.post(f"{url}/api/auth/register", json={
                "username": username.strip(),
                "email": email.strip().lower(),
                "full_name": full_name.strip(),
                "password": password,
                "role": role,
                "avatar_color": avatar_color,
                "avatar_image": avatar_image,
            }, timeout=8)
            if resp.status_code in (200, 201):
                data = resp.json()
                u = data.get("user")
                if u:
                    _cache_user_locally(u, password=password)
                    return u["id"]
            elif resp.status_code == 409:
                return None
        except Exception:
            pass

    conn = get_conn()
    try:
        pw_hash = _hash_password(password)
        cur = conn.execute("""
            INSERT INTO users (username, email, full_name, password_hash, role, avatar_color, avatar_image, is_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (username.strip(), email.strip().lower(), full_name.strip(), pw_hash, role, avatar_color, avatar_image))
        uid = cur.lastrowid
        conn.execute("INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (uid,))
        conn.commit()
        return uid
    except sqlite3.IntegrityError:
        return None


def authenticate(username_or_email: str, password: str) -> Optional[Dict]:
    """
    Authenticate user by username or email.
    Supports accounts sharing an email by checking candidates against the password.
    If an account was scheduled for deletion within the last 30 days, it is automatically recovered.
    If the 30-day recovery period has elapsed, the account is permanently deleted.
    """
    clean_id = (username_or_email or "").strip().lower()
    allowed, lock_msg = check_login_rate_limit(clean_id)
    if not allowed:
        raise ValueError(lock_msg)

    url = get_server_url()
    if url:
        try:
            resp = requests.post(f"{url}/api/auth/login", json={
                "username_or_email": username_or_email.strip(),
                "password": password,
            }, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                user = data.get("user")
                if user:
                    clear_failed_login(clean_id)
                    _cache_user_locally(user, password=password)
                    _record_daily_session(user["id"])
                    return _clean_user_dict(user)
            elif resp.status_code == 401:
                record_failed_login(clean_id)
                return None
        except Exception:
            pass

    conn = get_conn()
    cur = conn.execute("""
        SELECT * FROM users
        WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)
    """, (username_or_email.strip(), username_or_email.strip()))
    candidates = cur.fetchall()
    now_dt = datetime.now()

    for row in candidates:
        if _verify_password(password, row["password_hash"]):
            clear_failed_login(clean_id)
            # Check 30-day deletion recovery
            if row["deleted_at"] is not None:
                until_str = row["deletion_scheduled_until"]
                is_expired = False
                if until_str:
                    try:
                        until_dt = datetime.strptime(until_str, "%Y-%m-%d %H:%M:%S")
                        if now_dt > until_dt:
                            is_expired = True
                    except Exception:
                        pass

                if is_expired:
                    # Grace period expired: permanently delete
                    if not is_admin_username(row["username"]):
                        hard_delete_user(row["id"])
                        return None
                else:
                    # Inside 30 days: restore account!
                    recover_deleted_user(row["id"])
                    user_dict = dict(get_user(row["id"]))
                    user_dict["account_recovered"] = True
                    conn.execute("UPDATE users SET last_login = datetime('now') WHERE id = ?", (row["id"],))
                    conn.commit()
                    _record_daily_session(row["id"])
                    return _clean_user_dict(user_dict)

            if row["is_active"] != 1:
                continue

            conn.execute("UPDATE users SET last_login = datetime('now') WHERE id = ?", (row["id"],))
            conn.commit()
            _record_daily_session(row["id"])
            return _clean_user_dict(dict(row))

    record_failed_login(clean_id)
    return None


def get_user(user_id: int) -> Optional[Dict]:
    """Get user by ID."""
    url = get_server_url()
    if url:
        try:
            resp = requests.get(f"{url}/api/users/{user_id}", timeout=6)
            if resp.status_code == 200:
                u = resp.json().get("user")
                if u:
                    return _clean_user_dict(u)
        except Exception:
            pass

    conn = get_conn()
    cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    return _clean_user_dict(dict(row)) if row else None


def get_user_by_username_or_email(identifier: str) -> Optional[Dict]:
    """Get user by username or email."""
    if not identifier:
        return None
    conn = get_conn()
    cur = conn.execute("""
        SELECT * FROM users
        WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)
    """, (identifier.strip(), identifier.strip()))
    row = cur.fetchone()
    return _clean_user_dict(dict(row)) if row else None


def get_all_users() -> List[Dict]:
    """Get all users (admin view). Fetches row-by-row and trims sensitive fields."""
    url = get_server_url()
    if url:
        try:
            resp = requests.get(f"{url}/api/admin/users", timeout=8)
            if resp.status_code == 200:
                users = resp.json().get("users")
                if users is not None:
                    return [_clean_user_dict(u) for u in users]
        except Exception:
            pass

    conn = get_conn()
    cur = conn.execute("""
        SELECT u.*, 
               (SELECT COUNT(*) FROM commit_activity WHERE user_id = u.id) as total_commits
        FROM users u
        ORDER BY u.created_at DESC
    """)
    out = []
    for r in cur:
        out.append(_clean_user_dict(dict(r)))
    return out


def update_user(user_id: int, **kwargs) -> bool:
    """Update user fields. Supports: full_name, email, bio, avatar_color, is_active, role."""
    allowed = {"full_name", "email", "bio", "avatar_color", "is_active", "role"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    conn = get_conn()
    cur = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    target_row = cur.fetchone()
    if target_row:
        uname = target_row["username"]
        # Enforce single admin rules
        if is_admin_username(uname):
            if "role" in updates and updates["role"] != "admin":
                updates["role"] = "admin"  # cannot demote
        else:
            if updates.get("role") == "admin":
                updates["role"] = "user"  # cannot promote others to admin

    url = get_server_url()
    if url:
        try:
            requests.put(f"{url}/api/users/{user_id}", json=updates, timeout=6)
        except Exception:
            pass

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?",
                 (*updates.values(), user_id))
    conn.commit()
    return True


def change_password(user_id: int, new_password: str) -> bool:
    """Change a user's password."""
    url = get_server_url()
    if url:
        try:
            requests.post(f"{url}/api/users/{user_id}/password",
                          json={"new_password": new_password}, timeout=6)
        except Exception:
            pass

    conn = get_conn()
    pw_hash = _hash_password(new_password)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
    conn.commit()
    return True


def soft_delete_user(user_id: int) -> Tuple[bool, str]:
    """
    Schedule a user account for deletion with a 30-day recovery grace period.
    The user can log back in within 30 days to automatically restore and recover their account.
    """
    conn = get_conn()
    cur = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
    target = cur.fetchone()
    if not target:
        return False, "User not found."
    if is_admin_username(target["username"]):
        return False, "The exclusive Admin account cannot be deleted. You can reassign the admin username in Settings first."

    url = get_server_url()
    if url:
        try:
            requests.delete(f"{url}/api/admin/users/{user_id}?hard=false", timeout=6)
        except Exception:
            pass

    now = datetime.now()
    scheduled_until = now + timedelta(days=30)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    until_str = scheduled_until.strftime("%Y-%m-%d %H:%M:%S")

    conn.execute("""
        UPDATE users
        SET is_active = 0,
            deleted_at = ?,
            deletion_scheduled_until = ?
        WHERE id = ?
    """, (now_str, until_str, user_id))
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()

    try:
        from commitmaster import account_manager
        account_manager.remove_saved_account(user_id)
    except Exception:
        pass

    return True, "Your account has been scheduled for deletion. You have 30 days to log back in to recover it."


def delete_user(user_id: int) -> bool:
    """Soft-delete a user with a 30-day recovery grace period."""
    ok, _ = soft_delete_user(user_id)
    return ok


def recover_deleted_user(user_id: int) -> bool:
    """Restore a soft-deleted user account upon login within the 30-day grace period."""
    conn = get_conn()
    conn.execute("""
        UPDATE users
        SET is_active = 1,
            deleted_at = NULL,
            deletion_scheduled_until = NULL
        WHERE id = ?
    """, (user_id,))
    conn.commit()
    return True


def clean_expired_deleted_accounts() -> int:
    """Permanently delete accounts whose 30-day recovery grace period has expired."""
    conn = get_conn()
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        SELECT id, username FROM users
        WHERE deleted_at IS NOT NULL
          AND deletion_scheduled_until IS NOT NULL
          AND deletion_scheduled_until < ?
    """, (now_str,))
    expired = cur.fetchall()
    count = 0
    for u in expired:
        if not is_admin_username(u["username"]):
            hard_delete_user(u["id"])
            count += 1
    return count


def hard_delete_user(user_id: int) -> bool:
    """Permanently delete a user and all their data."""
    conn = get_conn()
    cur = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    target = cur.fetchone()
    if target and is_admin_username(target["username"]):
        return False  # Protected admin account cannot be deleted

    url = get_server_url()
    if url:
        try:
            requests.delete(f"{url}/api/admin/users/{user_id}?hard=true", timeout=6)
        except Exception:
            pass

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return True


# ── Preferences ────────────────────────────────────────────────────────────────

def get_preferences(user_id: int) -> Optional[Dict]:
    """Get user preferences."""
    url = get_server_url()
    if url:
        try:
            resp = requests.get(f"{url}/api/users/{user_id}/preferences", timeout=6)
            if resp.status_code == 200:
                p = resp.json().get("preferences")
                if p:
                    return p
        except Exception:
            pass

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
        "ask_before_push", "ai_provider", "openai_api_key", "claude_api_key",
        "gemini_api_key", "openai_model", "claude_model", "gemini_model",
        "reminder_interval_enabled", "reminder_interval_hours", "reminder_interval_minutes",
        "reminder_app_monitor_enabled", "reminder_only_if_dirty", "bg_pattern"
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    url = get_server_url()
    if url:
        try:
            requests.put(f"{url}/api/users/{user_id}/preferences", json=updates, timeout=6)
        except Exception:
            pass

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
    url = get_server_url()
    if url:
        try:
            requests.post(f"{url}/api/activity/commits", json={
                "user_id": user_id,
                "repo_path": repo_path,
                "repo_name": repo_name,
                "commit_hash": commit_hash,
                "commit_msg": commit_msg,
                "files_count": files_count,
                "status": status,
            }, timeout=6)
        except Exception:
            pass

    conn = get_conn()
    conn.execute("""
        INSERT INTO commit_activity (user_id, repo_path, repo_name, commit_hash, commit_msg, files_count, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, repo_path, repo_name, commit_hash, commit_msg, files_count, status))
    conn.commit()
    if status == "committed":
        _increment_daily_commits(user_id)
    else:
        log_event(user_id, "commit_failed", repo_name=repo_name, detail=commit_msg[:200])


# ── Analytics events ──────────────────────────────────────────────────────────

def log_event(user_id: Optional[int], kind: str, repo_name: str = "", files: int = 0,
              errors: int = 0, security: int = 0, warnings: int = 0, detail: str = "") -> None:
    """
    Record an analytics event.  kind is one of:
    'scan' (pre-commit inspection), 'commit_failed', 'push_ok', 'push_failed', 'ai_generate'.
    Never raises - analytics must not break the app.
    """
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO app_events (user_id, kind, repo_name, files, errors, security, warnings, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, kind, repo_name, files, errors, security, warnings, detail[:300]))
        conn.commit()
    except Exception:
        pass


def log_scan(user_id: Optional[int], repo_path: str, files: int, issues_summary: Dict[str, int]) -> None:
    """Record a pre-commit inspection result (vulnerability / error / warning counts)."""
    log_event(user_id, "scan", repo_name=os.path.basename(repo_path.rstrip("/\\")), files=files,
              errors=issues_summary.get("errors", 0), security=issues_summary.get("security", 0),
              warnings=issues_summary.get("warnings", 0))


def _day_range(days: int) -> List[str]:
    today = datetime.now().date()
    return [(today - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(days - 1, -1, -1)]


def get_metrics_timeseries(days: int = 30, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Daily time series (zero-filled) for charts.  Returns:
    {"dates": [...], "series": {name: [int, ...]}} with series:
    sessions, active_users, commits, files_committed, pushes, scans,
    vulnerabilities, errors, warnings, commit_failures, push_failures, ai_generations
    """
    url = get_server_url()
    if url:
        try:
            params = {"days": days}
            if user_id:
                params["user_id"] = user_id
            resp = requests.get(f"{url}/api/metrics/timeseries", params=params, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if "dates" in data and "series" in data:
                    return data
        except Exception:
            pass

    dates = _day_range(days)
    idx = {d: i for i, d in enumerate(dates)}
    names = ["sessions", "active_users", "commits", "files_committed", "pushes", "scans",
             "vulnerabilities", "errors", "warnings", "commit_failures", "push_failures", "ai_generations"]
    series = {n: [0] * len(dates) for n in names}
    since = dates[0]
    conn = get_conn()

    if user_id:
        usage_query = """
            SELECT date, SUM(sessions) s, COUNT(DISTINCT user_id) u FROM app_usage
            WHERE date >= ? AND user_id = ? GROUP BY date"""
        commit_query = """
            SELECT date(committed_at, 'localtime') d, COUNT(*) c, SUM(files_count) f FROM commit_activity
            WHERE status = 'committed' AND date(committed_at, 'localtime') >= ? AND user_id = ? GROUP BY d"""
        event_query = """
            SELECT date(created_at, 'localtime') d, kind, COUNT(*) c,
                   SUM(errors) e, SUM(security) s, SUM(warnings) w
            FROM app_events WHERE date(created_at, 'localtime') >= ? AND user_id = ? GROUP BY d, kind"""
        query_args: tuple = (since, user_id)
    else:
        usage_query = """
            SELECT date, SUM(sessions) s, COUNT(DISTINCT user_id) u FROM app_usage
            WHERE date >= ? GROUP BY date"""
        commit_query = """
            SELECT date(committed_at, 'localtime') d, COUNT(*) c, SUM(files_count) f FROM commit_activity
            WHERE status = 'committed' AND date(committed_at, 'localtime') >= ? GROUP BY d"""
        event_query = """
            SELECT date(created_at, 'localtime') d, kind, COUNT(*) c,
                   SUM(errors) e, SUM(security) s, SUM(warnings) w
            FROM app_events WHERE date(created_at, 'localtime') >= ? GROUP BY d, kind"""
        query_args = (since,)

    for r in conn.execute(usage_query, query_args):
        if r["date"] in idx:
            series["sessions"][idx[r["date"]]] = r["s"] or 0
            series["active_users"][idx[r["date"]]] = r["u"] or 0

    for r in conn.execute(commit_query, query_args):
        if r["d"] in idx:
            series["commits"][idx[r["d"]]] = r["c"] or 0
            series["files_committed"][idx[r["d"]]] = r["f"] or 0

    kind_map = {"push_ok": "pushes", "scan": "scans", "commit_failed": "commit_failures",
                "push_failed": "push_failures", "ai_generate": "ai_generations"}
    for r in conn.execute(event_query, query_args):
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
    return {"dates": dates, "series": series}


def get_user_commit_series(days: int = 30, limit: int = 5) -> Dict[str, Any]:
    """Daily commit counts for the `limit` most active users (for multi-line charts)."""
    url = get_server_url()
    if url:
        try:
            resp = requests.get(f"{url}/api/metrics/user-commits", params={"days": days, "limit": limit}, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if "dates" in data and "series" in data:
                    return data
        except Exception:
            pass

    dates = _day_range(days)
    idx = {d: i for i, d in enumerate(dates)}
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.username, date(ca.committed_at, 'localtime') d, COUNT(*) c
        FROM commit_activity ca JOIN users u ON u.id = ca.user_id
        WHERE ca.status = 'committed' AND date(ca.committed_at, 'localtime') >= ?
        GROUP BY u.id, d""", (dates[0],)).fetchall()
    totals: Dict[str, int] = {}
    per_user: Dict[str, List[int]] = {}
    for r in rows:
        if r["d"] not in idx:
            continue
        per_user.setdefault(r["username"], [0] * len(dates))[idx[r["d"]]] = r["c"]
        totals[r["username"]] = totals.get(r["username"], 0) + r["c"]
    top = sorted(totals, key=totals.get, reverse=True)[:limit]
    return {"dates": dates, "series": {u: per_user[u] for u in top}}


def get_recent_security_events(limit: int = 8) -> List[Dict]:
    """Latest scans that found security problems or errors (for the admin dashboard)."""
    url = get_server_url()
    if url:
        try:
            resp = requests.get(f"{url}/api/events/security", params={"limit": limit}, timeout=6)
            if resp.status_code == 200:
                evs = resp.json().get("events")
                if evs is not None:
                    return evs
        except Exception:
            pass

    conn = get_conn()
    cur = conn.execute("""
        SELECT e.*, u.username FROM app_events e LEFT JOIN users u ON u.id = e.user_id
        WHERE e.kind = 'scan' AND (e.security > 0 OR e.errors > 0)
        ORDER BY e.created_at DESC LIMIT ?""", (limit,))
    return [dict(r) for r in cur.fetchall()]


def get_activity_log(user_id: Optional[int] = None, limit: int = 100) -> List[Dict]:
    """Get commit activity log, optionally filtered by user."""
    url = get_server_url()
    if url:
        try:
            params = {"limit": limit}
            if user_id:
                params["user_id"] = user_id
            resp = requests.get(f"{url}/api/activity/commits", params=params, timeout=6)
            if resp.status_code == 200:
                act = resp.json().get("activity")
                if act is not None:
                    return act
        except Exception:
            pass

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
    url = get_server_url()
    if url:
        try:
            params = {"days": days}
            if user_id:
                params["user_id"] = user_id
            resp = requests.get(f"{url}/api/usage/stats", params=params, timeout=6)
            if resp.status_code == 200:
                stats = resp.json().get("stats")
                if stats is not None:
                    return stats
        except Exception:
            pass

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
    url = get_server_url()
    if url:
        try:
            resp = requests.get(f"{url}/api/admin/stats", timeout=6)
            if resp.status_code == 200:
                stats = resp.json().get("stats")
                if stats:
                    return stats
        except Exception:
            pass

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

def _save_local_session(token: str, user_id: int):
    expires = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires)
    )
    conn.commit()


def create_session_token(user_id: int) -> str:
    """Create a session token for a user (for auto-login)."""
    url = get_server_url()
    if url:
        try:
            resp = requests.post(f"{url}/api/auth/session", json={"action": "create", "user_id": user_id}, timeout=6)
            if resp.status_code == 200:
                tok = resp.json().get("token")
                if tok:
                    _save_local_session(tok, user_id)
                    return tok
        except Exception:
            pass

    token = secrets.token_urlsafe(32)
    _save_local_session(token, user_id)
    return token


def validate_session_token(token: str) -> Optional[Dict]:
    """Validate a session token and return the user dict if valid."""
    url = get_server_url()
    if url:
        try:
            resp = requests.post(f"{url}/api/auth/session", json={"action": "validate", "token": token}, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("valid") and data.get("user"):
                    return data["user"]
        except Exception:
            pass

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
    url = get_server_url()
    if url:
        try:
            requests.post(f"{url}/api/auth/session", json={"action": "revoke", "user_id": user_id}, timeout=6)
        except Exception:
            pass
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
    url = get_server_url()
    if url:
        try:
            resp = requests.get(f"{url}/api/settings", timeout=5)
            if resp.status_code == 200:
                settings = resp.json().get("settings", {})
                if key in settings:
                    return settings[key]
        except Exception:
            pass

    conn = get_conn()
    cur = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
    row = cur.fetchone()
    return row["value"] if row else default


def set_system_setting(key: str, value: str, user_id: Optional[int] = None) -> bool:
    """Set a system setting value."""
    url = get_server_url()
    if url:
        try:
            requests.post(f"{url}/api/settings", json={"key": key, "value": str(value), "user_id": user_id}, timeout=5)
        except Exception:
            pass

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
    url = get_server_url()
    if url:
        try:
            resp = requests.get(f"{url}/api/settings", timeout=5)
            if resp.status_code == 200:
                s = resp.json().get("settings")
                if s is not None:
                    return s
        except Exception:
            pass

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
    out = []
    for r in cur:
        out.append(dict(r))
    return out


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

