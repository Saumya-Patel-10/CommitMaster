"""
CommitMaster — Path Resolution & Persistent Storage Management.
=================================================================
Each product keeps its own database, config, and logs:

  user   %LOCALAPPDATA%\\CommitMaster
  admin  %LOCALAPPDATA%\\CommitMaster-Admin
  demo   %LOCALAPPDATA%\\CommitMaster-Demo

A workspace checkout that still contains commitmaster.db is not the runtime
data directory. The user product may copy that database once into its own
empty folder. Admin and demo never receive it.

COMMITMASTER_DATA_DIR is a root. Each product uses a child folder named for
that product, unless the path already ends in its own folder. A path that
ends in another product's folder is refused.

Persistent state is never read or written under PyInstaller's _MEIPASS.
"""
import os
import shutil
import sys

# Base workspace directory (the repository that contains this package).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE_DIR = os.path.dirname(_THIS_DIR)

# Copied once, and only into an empty user folder. Session tokens and admin
# secrets stay where they are.
_USER_COPY_FILES = (
    "commitmaster.db",
    "config.json",
    ".commitmaster_accounts.json",
    "commitmaster.log",
)


class DataDirectoryError(RuntimeError):
    """Raised when a product is pointed at another product's data directory."""


def get_app_dir() -> str:
    """
    Return the root application directory for read-only static assets (icons, images).
    In frozen PyInstaller mode, bundled assets may live in sys._MEIPASS.
    """
    return getattr(sys, "_MEIPASS", _WORKSPACE_DIR)


def _own_folder_name() -> str:
    try:
        from commitmaster import product as _product
        return _product.data_dir_name()
    except Exception:
        return "CommitMaster"


def _product_folder_names() -> dict:
    try:
        from commitmaster.product import DATA_DIR_NAMES
        return dict(DATA_DIR_NAMES)
    except Exception:
        return {"user": "CommitMaster", "admin": "CommitMaster-Admin", "demo": "CommitMaster-Demo"}


def _foreign_folder(path: str, own_name: str) -> str:
    """Return another product's folder name when `path` points at that folder."""
    base = os.path.basename(os.path.normpath(path))
    for name in _product_folder_names().values():
        if base == name and name != own_name:
            return name
    return ""


def resolve_data_dir(env_dir: str, own_name: str) -> str:
    """Map an override root onto this product's folder, or refuse a foreign one."""
    foreign = _foreign_folder(env_dir, own_name)
    if foreign:
        raise DataDirectoryError(
            f"This product stores data in {own_name} and refuses {foreign}."
        )
    base = os.path.basename(os.path.normpath(env_dir))
    if base == own_name:
        return os.path.normpath(env_dir)
    return os.path.normpath(os.path.join(env_dir, own_name))


def _copy_user_workspace_once(dest: str) -> None:
    """Copy the workspace database into an empty user folder. Never copies secrets."""
    if os.path.exists(os.path.join(dest, "commitmaster.db")):
        return
    workspace_db = os.path.join(_WORKSPACE_DIR, "commitmaster.db")
    if not os.path.isfile(workspace_db):
        return
    for fname in _USER_COPY_FILES:
        src = os.path.join(_WORKSPACE_DIR, fname)
        dst = os.path.join(dest, fname)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)


def get_data_dir() -> str:
    """
    Return this product's persistent data directory.
    Never returns _MEIPASS and never returns another product's folder.
    """
    own_name = _own_folder_name()
    env_dir = os.getenv("COMMITMASTER_DATA_DIR", "").strip()
    if env_dir:
        dest = resolve_data_dir(env_dir, own_name)
        os.makedirs(dest, exist_ok=True)
        return dest

    local_app_data = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
    dest = os.path.join(local_app_data, own_name)
    os.makedirs(dest, exist_ok=True)
    # Frozen and packaged builds start empty. Source runs may seed the user
    # folder once from a workspace database that predates the split.
    if own_name == "CommitMaster" and not getattr(sys, "frozen", False):
        _copy_user_workspace_once(dest)
    return dest


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
