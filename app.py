"""
CommitMaster — Desktop Application Entrypoint (public USER edition).
====================================================================
This is the app published to the Microsoft Store / GitHub releases.

  • It contains NO administrator account and NO admin console. Every person who
    installs it gets the personal User Dashboard for their own account only.
  • On first launch (or whenever there is no valid saved session) the sign-in
    screen is shown: sign in if you already have an account, or create one.
  • A previous session is resumed only when its stored token is still valid.
  • Quick sign-in entries can be removed from the login screen.

The private administrator console lives in admin_app.py (CommitMaster-Admin.exe),
which reuses `run_session_loop(admin_edition=True)` from this module.

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

from commitmaster import paths
from commitmaster import database as db
from commitmaster import account_manager
from commitmaster import edition
from commitmaster.login_window import LoginWindow
from commitmaster.user_dashboard import UserDashboard

_TOKEN_FILE = paths.get_token_path()


def _save_token(token: str) -> None:
    try:
        with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump({"token": token}, f)
    except Exception:
        pass


def _load_token() -> str:
    try:
        if os.path.exists(_TOKEN_FILE):
            with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("token", "") or ""
    except Exception:
        pass
    return ""


def _clear_token() -> None:
    try:
        if os.path.exists(_TOKEN_FILE):
            os.remove(_TOKEN_FILE)
    except Exception:
        pass


def _resume_saved_session():
    """
    Return the user for a previously signed-in session ONLY if its token is still valid.
    Never falls back to any particular account; returns None to show the sign-in screen.
    """
    # An explicit logout clears the active account pointer and token file,
    # so nothing is resumed after the user signed out.
    active_id = account_manager.get_active_account_id()
    if active_id is None:
        return None
    token = _load_token()
    if not token:
        return None
    try:
        user = db.validate_session_token(token)
    except Exception:
        user = None
    if not user:
        return None
    user = dict(user)
    # The token must belong to the account that is marked active on this device.
    if user.get("id") != active_id:
        return None
    return user


def _run_first_run_setup() -> None:
    """Show the AI setup wizard once on a fresh install. Never blocks app start on errors."""
    try:
        from commitmaster import ai_setup
        if not ai_setup.needs_first_run_setup():
            return
        from commitmaster.setup_wizard import SetupWizard
        SetupWizard().run()
    except Exception:
        import traceback
        traceback.print_exc()


def _auto_configure_ai_async() -> None:
    """After sign-in, detect/start the local AI server and fill in port, URL and model."""
    import threading

    def work():
        try:
            from commitmaster import ai_setup
            ai_setup.auto_configure()
        except Exception:
            pass

    threading.Thread(target=work, daemon=True, name="ai-autoconfig").start()


def run_session_loop(admin_edition: bool = False) -> None:
    """Sign-in / dashboard lifecycle shared by the user and admin editions."""
    try:
        from commitmaster import windows_integration
        windows_integration.set_dpi_awareness()
        windows_integration.init_app_user_model_id("admin" if admin_edition else "unified")
        windows_integration.register_windows_app("admin" if admin_edition else "user")

        db.init_db()

        # First launch: ask how AI will be used (Local / API key / Both), install the
        # local runtime + model if needed, then continue to sign in / create account.
        if not admin_edition:
            _run_first_run_setup()

        current_user = _resume_saved_session()
        if admin_edition and current_user and not db.is_admin_username(current_user.get("username")):
            current_user = None

        while True:
            if not current_user:
                auth_result = {"user": None}

                def on_login_success(u: dict):
                    auth_result["user"] = u

                win = LoginWindow(on_success=on_login_success,
                                  app_type="admin" if admin_edition else "user")
                win.run()

                current_user = auth_result["user"] or getattr(win, "authenticated_user", None)
                if not current_user:
                    break  # window closed without signing in

                if admin_edition and not db.is_admin_username(current_user.get("username")):
                    try:
                        account_manager.clear_active_account()
                    except Exception:
                        pass
                    root = tk.Tk()
                    root.withdraw()
                    messagebox.showerror(
                        "Access Denied",
                        "This is the administrator app.\nPlease use the regular CommitMaster app.",
                        parent=root,
                    )
                    root.destroy()
                    current_user = None
                    continue

            user_dict = dict(current_user)
            token = db.create_session_token(user_dict["id"])
            _save_token(token)
            db.set_active_session_token(token)
            try:
                account_manager.save_account(user_dict, token)
            except Exception:
                pass

            # Signed in: fill in local AI host / port / model automatically (background).
            _auto_configure_ai_async()

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

            if admin_edition and db.is_admin_username(user_dict.get("username", "")):
                import admin_app
                admin_app._open_admin_window(
                    user=user_dict,
                    on_logout=on_logout,
                    on_switch_account=on_switch_account,
                )
            else:
                dashboard = UserDashboard(
                    user=user_dict,
                    on_logout=on_logout,
                    on_switch_account=on_switch_account,
                )
                dashboard.run()
                if getattr(dashboard, "next_action", None):
                    session_state["action"] = dashboard.next_action
                    session_state["next_user"] = getattr(dashboard, "next_user", None)

            if session_state["action"] == "switch" and session_state["next_user"]:
                current_user = session_state["next_user"]
                continue
            elif session_state["action"] == "logout":
                current_user = None
                continue
            else:
                break

    except Exception:
        import traceback
        err_msg = traceback.format_exc()
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "CommitMaster — Error",
                f"An unexpected error occurred while starting CommitMaster:\n\n{err_msg}",
                parent=root,
            )
            root.destroy()
        except Exception:
            pass
        raise


def launch_app():
    """Public user edition entry point (no admin account, no admin console)."""
    run_session_loop(admin_edition=False)


if __name__ == "__main__":
    launch_app()
