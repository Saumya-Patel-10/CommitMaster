"""
CommitMaster — GUI Application Entrypoint.
Initialises the database, shows login, then routes to user dashboard or admin portal.
Run: python app.py
"""
import os
import sys
import json

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import database as db
from commitmaster.login_window import LoginWindow
from commitmaster.user_dashboard import UserDashboard
from commitmaster.admin_portal import AdminPortal

# Path for persisting the last-used session token
_TOKEN_FILE = os.path.join(APP_DIR, ".session_token")


def _save_token(token: str) -> None:
    try:
        with open(_TOKEN_FILE, "w") as f:
            json.dump({"token": token}, f)
    except Exception:
        pass


def _load_token() -> str:
    try:
        if os.path.exists(_TOKEN_FILE):
            with open(_TOKEN_FILE) as f:
                return json.load(f).get("token", "")
    except Exception:
        pass
    return ""


def _clear_token() -> None:
    try:
        if os.path.exists(_TOKEN_FILE):
            os.remove(_TOKEN_FILE)
    except Exception:
        pass


def launch_app():
    """Main entry point — initialise DB and start the GUI."""
    try:
        db.init_db()

        # ── Try auto-login from saved token ───────────────────────────────────────
        token = _load_token()
        user = None
        if token:
            user = db.validate_session_token(token)

        if user:
            _open_dashboard(dict(user))
        else:
            _open_login()
    except Exception as exc:
        import traceback
        import tkinter as tk
        from tkinter import messagebox
        err_msg = traceback.format_exc()
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "CommitMaster — Error",
                f"An unexpected error occurred while starting CommitMaster:\n\n{err_msg}",
                parent=root
            )
            root.destroy()
        except Exception:
            pass
        raise



def _open_login():
    def on_success(user: dict):
        # Save session token for next launch
        token = db.create_session_token(user["id"])
        _save_token(token)
        _open_dashboard(user)

    win = LoginWindow(on_success=on_success)
    win.run()


def _open_dashboard(user: dict):
    def on_logout():
        _clear_token()
        _open_login()

    def on_admin():
        dashboard.root.withdraw()   # hide dashboard while admin portal is open

        def on_admin_close():
            dashboard.root.deiconify()  # restore dashboard

        portal = AdminPortal(admin_user=user, on_close=on_admin_close)
        portal.run()

    admin_cb = on_admin if user.get("role") == "admin" else None
    dashboard = UserDashboard(user=user, on_logout=on_logout, on_admin=admin_cb)
    dashboard.run()


if __name__ == "__main__":
    launch_app()
