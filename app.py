"""
CommitMaster — Unified Desktop Application Entrypoint.
======================================================
Instead of separate user and admin applications, CommitMaster runs as a single unified app.
Authentication and role routing are handled dynamically:
  • If the user logs in as the designated administrator (default: "saumya.patel@Admin_#",
    or the updated username configured in Admin Settings), the full Admin Portal is launched.
    This Admin Portal can ONLY and ONLY be accessed by this specific username.
  • All other users are automatically routed to the personal User Dashboard.
  • Supports seamless switching between multiple saved accounts.
  • Google account verification via OTP is natively integrated.

Run: python app.py
"""
import os
import sys
import json
import tkinter as tk
from tkinter import messagebox

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import database as db
from commitmaster import account_manager
from commitmaster.login_window import LoginWindow
from commitmaster.user_dashboard import UserDashboard

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
    """Main entry point — initialise DB and run the non-blocking unified application loop."""
    try:
        from commitmaster import windows_integration
        windows_integration.set_dpi_awareness()
        windows_integration.init_app_user_model_id("unified")

        db.init_db()

        # ── 1. Check active account from multi-account manager ───────────────
        current_user = None
        active_acc = account_manager.get_active_account()
        if active_acc and active_acc.get("username"):
            current_user = db.get_user_by_username_or_email(active_acc["username"])

        # ── 2. Fallback to persisted session token ───────────────────────────
        if not current_user:
            token = _load_token()
            if token:
                current_user = db.validate_session_token(token)

        # ── 3. Clean, Non-blocking Session Lifecycle Loop ────────────────────
        while True:
            if not current_user:
                auth_result = {"user": None}
                def on_login_success(u: dict):
                    auth_result["user"] = u

                win = LoginWindow(on_success=on_login_success)
                win.run()

                current_user = auth_result["user"] or getattr(win, "authenticated_user", None)
                if not current_user:
                    # User closed the login window without authenticating
                    break

            # Persist session token and active account
            user_dict = dict(current_user)
            token = db.create_session_token(user_dict["id"])
            _save_token(token)
            try:
                account_manager.save_account(
                    username=user_dict["username"],
                    user_id=user_dict["id"],
                    role=user_dict.get("role", "user"),
                    full_name=user_dict.get("full_name", ""),
                    email=user_dict.get("email", ""),
                    avatar_color=user_dict.get("avatar_color", "")
                )
            except Exception:
                pass

            session_state = {"action": "exit", "next_user": None}

            def on_logout():
                _clear_token()
                try:
                    account_manager.clear_active_account()
                except Exception:
                    pass
                session_state["action"] = "logout"
                session_state["next_user"] = None

            def on_switch_account(switched_user: dict):
                session_state["action"] = "switch"
                session_state["next_user"] = switched_user

            username = user_dict.get("username", "")

            # Strict exclusivity check: ONLY designated admin username opens admin portal
            if db.is_admin_username(username):
                import admin_app
                admin_app._open_admin_window(
                    user=user_dict,
                    on_logout=on_logout,
                    on_switch_account=on_switch_account
                )
            else:
                dashboard = UserDashboard(
                    user=user_dict,
                    on_logout=on_logout,
                    on_switch_account=on_switch_account
                )
                dashboard.run()
                if getattr(dashboard, "next_action", None):
                    session_state["action"] = dashboard.next_action
                    session_state["next_user"] = getattr(dashboard, "next_user", None)

            # Process state after the window has completely destroyed its mainloop
            if session_state["action"] == "switch" and session_state["next_user"]:
                current_user = session_state["next_user"]
                continue
            elif session_state["action"] == "logout":
                current_user = None
                continue
            else:
                break

    except Exception as exc:
        import traceback
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


if __name__ == "__main__":
    launch_app()
