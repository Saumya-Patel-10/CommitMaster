"""
CommitMaster — Desktop Application Entrypoint (public USER edition).
====================================================================
This is the public user entry. The Store package name stays SaumyaPatel.CommitMaster.
This revision has not been packed as an MSIX or submitted to the Store.

  • It contains NO administrator account and NO admin console. Every person who
    installs it gets the personal User Dashboard for their own account only.
  • On first launch (or whenever there is no valid saved session) the sign-in
    screen is shown: sign in if you already have an account, or create one.
  • A previous session is resumed only when its stored token is still valid.
  • Quick sign-in entries can be removed from the login screen.

This entry point is the public user product. It never imports or opens the
administrator console. A handoff from the admin app can open this user's own
workspace, or a read-only impersonation session, in a separate process.

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
from commitmaster import product
from commitmaster import user_mode
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


def _apply_handoff(handoff: dict) -> dict:
    """A handoff may open a normal workspace or a read-only impersonation. Never admin."""
    user = dict(handoff.get("user") or {})
    user["role"] = "user"
    user.pop("password", None)
    user.pop("password_hash", None)
    token = handoff.get("token") or ""
    if token:
        _save_token(token)
        db.set_active_session_token(token)
    if handoff.get("read_only"):
        os.environ["COMMITMASTER_SESSION_READ_ONLY"] = "1"
    else:
        os.environ.pop("COMMITMASTER_SESSION_READ_ONLY", None)
    user["_session_mode"] = handoff.get("mode") or "workspace"
    user["_session_banner"] = handoff.get("banner") or ""
    user["_session_expires"] = handoff.get("expires_at") or ""
    user["_session_justification"] = handoff.get("justification") or ""
    return user


def run_session_loop(handoff: dict | None = None) -> None:
    """Sign-in / dashboard lifecycle for the public user product and the demo product."""
    if product.is_admin():
        raise RuntimeError("the user session cannot run inside the admin product")
    try:
        from commitmaster import windows_integration
        windows_integration.set_dpi_awareness()
        windows_integration.init_app_user_model_id("demo" if product.is_demo() else "unified")
        windows_integration.register_windows_app("user")

        db.init_db()

        if handoff is None and not product.is_demo():
            _run_first_run_setup()

        current_user = _apply_handoff(handoff) if handoff else _resume_saved_session()

        while True:
            if not current_user:
                auth_result = {"user": None}

                def on_login_success(u: dict):
                    auth_result["user"] = u

                win = LoginWindow(on_success=on_login_success, app_type="user")
                win.run()

                current_user = auth_result["user"] or getattr(win, "authenticated_user", None)
                if not current_user:
                    break  # window closed without signing in

            user_dict = dict(current_user)
            # This process is the user or demo product. Account role cannot open an admin surface.
            user_dict["role"] = "user"
            if not handoff:
                token = db.create_session_token(user_dict["id"])
                _save_token(token)
                db.set_active_session_token(token)
                try:
                    account_manager.save_account(user_dict, token)
                except Exception:
                    pass

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

            dashboard = UserDashboard(
                user=user_dict,
                on_logout=on_logout,
                on_switch_account=on_switch_account,
            )
            dashboard.run()
            if getattr(dashboard, "next_action", None):
                session_state["action"] = dashboard.next_action
                session_state["next_user"] = getattr(dashboard, "next_user", None)
            handoff = None

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
    """Public user entry point. Demo may already have locked the process."""
    if not product.is_locked():
        product.activate("user")
    if product.is_admin():
        raise RuntimeError("the user entry point cannot start the admin product")
    ignored = {"--admin", "--admin-edition"}
    if any(arg in ignored for arg in sys.argv[1:]):
        sys.argv = [sys.argv[0]] + [arg for arg in sys.argv[1:] if arg not in ignored]
    handoff = user_mode.consume_handoff(sys.argv[1:])
    run_session_loop(handoff=handoff)


if __name__ == "__main__":
    launch_app()
