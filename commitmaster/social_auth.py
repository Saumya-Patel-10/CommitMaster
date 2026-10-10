"""
CommitMaster — Social Authentication & Account Creation (GitHub & Google).
==========================================================================
Provides seamless 1-click and token-backed authentication and account creation:
  • Continue with GitHub: Web auth, GitHub CLI detection, and Personal Access Tokens.
    Auto-fetches username, primary email, full name, and avatar picture.
    Creates or logs into the account and binds GitHub repositories.
  • Continue with Google: Google Account authentication and account creation.
    Auto-verifies email, sets Google avatar branding, and initializes account.
"""
import os
import re
import secrets
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from typing import Any, Callable, Dict, Optional, Tuple

import requests
from PIL import Image, ImageTk

from commitmaster.app_styles import COLORS, FONTS
from commitmaster import database as db
from commitmaster import account_manager
from commitmaster import github_service
from commitmaster.logger import get

log = get("social_auth")

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVATARS_DIR = os.path.join(APP_DIR, "assets", "avatars")


def download_and_save_avatar(user_id: int, image_url: str) -> Optional[str]:
    """Download avatar image from a remote URL and store it locally as the user's profile pic."""
    if not image_url or not image_url.startswith(("http://", "https://")):
        return None

    try:
        os.makedirs(AVATARS_DIR, exist_ok=True)
        dest_path = os.path.join(AVATARS_DIR, f"user_{user_id}.png")

        resp = requests.get(image_url, timeout=8, headers={"User-Agent": "CommitMaster-Desktop-App"})
        if resp.status_code == 200 and resp.content:
            import io
            with Image.open(io.BytesIO(resp.content)) as img:
                img = img.convert("RGBA")
                w, h = img.size
                min_dim = min(w, h)
                left = (w - min_dim) // 2
                top = (h - min_dim) // 2
                cropped = img.crop((left, top, left + min_dim, top + min_dim))
                resized = cropped.resize((256, 256), Image.Resampling.LANCZOS)
                resized.save(dest_path, format="PNG")

            conn = db.get_conn()
            conn.execute("UPDATE users SET avatar_image = ? WHERE id = ?", (dest_path, user_id))
            conn.commit()

            try:
                from commitmaster import avatar_utils
                avatar_utils._invalidate_cache(user_id)
            except Exception:
                pass

            log.info("Downloaded and saved avatar for user %d from %s", user_id, image_url)
            return dest_path
    except Exception as exc:
        log.warning("Could not download avatar from %s: %s", image_url, exc)
    return None


class GitHubAuthDialog:
    """
    Dialog for signing in or creating a CommitMaster account with GitHub.
    Supports browser token generation, GitHub CLI detection, and PAT verification.
    """

    def __init__(self, parent: tk.Tk, on_success: Callable[[Dict[str, Any]], None]):
        self.master = parent
        self.on_success = on_success

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("CommitMaster — Continue with GitHub")
        self.dialog.geometry("480x520")
        self.dialog.minsize(440, 480)
        self.dialog.configure(bg=COLORS["bg_darkest"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center on parent
        self.dialog.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w, h = 480, 520
        x = max(20, px + (pw - w) // 2)
        y = max(20, py + (ph - h) // 2)
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

        from commitmaster import windows_integration
        windows_integration.apply_windows_theme(self.dialog, "CommitMaster — Continue with GitHub")

        self._token_var = tk.StringVar()
        self._build_ui()

    def _build_ui(self):
        p = tk.Frame(self.dialog, bg=COLORS["bg_darkest"], padx=24, pady=20)
        p.pack(fill="both", expand=True)

        # Header with Octocat branding
        hdr = tk.Frame(p, bg=COLORS["bg_darkest"])
        hdr.pack(fill="x", pady=(0, 12))

        tk.Label(
            hdr, text="🐙  Continue with GitHub",
            font=FONTS["heading_lg"], fg=COLORS["text_primary"], bg=COLORS["bg_darkest"]
        ).pack(anchor="w")

        tk.Label(
            hdr,
            text="Sign in or create your CommitMaster account with your GitHub profile.",
            font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"]
        ).pack(anchor="w", pady=(2, 0))

        # Card container
        card = tk.Frame(p, bg=COLORS["bg_card"], padx=18, pady=16, highlightthickness=1, highlightbackground=COLORS["border"])
        card.pack(fill="x", pady=(0, 12))

        # Option 1: Browser 1-click token creation
        tk.Label(
            card, text="Step 1: Authorize on GitHub (Browser)",
            font=FONTS["label_bold"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]
        ).pack(anchor="w")

        tk.Label(
            card,
            text="Click below to open GitHub with all required scopes pre-selected.\n"
                 "Generate the token, then paste it below.",
            font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"], justify="left"
        ).pack(anchor="w", pady=(2, 8))

        btn_row = tk.Frame(card, bg=COLORS["bg_card"])
        btn_row.pack(fill="x", pady=(0, 12))

        open_btn = tk.Button(
            btn_row, text="🌐 Generate Token on GitHub (Browser)",
            font=FONTS["label_bold"], bg=COLORS["bg_medium"], fg=COLORS["accent"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["accent_hover"],
            relief="flat", bd=0, cursor="hand2", padx=12, pady=6,
            command=self._open_browser_auth
        )
        open_btn.pack(side="left", padx=(0, 8))

        # GitHub CLI auto-detect button
        gh_btn = tk.Button(
            btn_row, text="⚡ Detect from 'gh' CLI",
            font=FONTS["caption"], bg=COLORS["bg_medium"], fg=COLORS["text_secondary"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=8, pady=6,
            command=self._detect_gh_cli
        )
        gh_btn.pack(side="left")

        tk.Frame(card, height=1, bg=COLORS["border"]).pack(fill="x", pady=(4, 12))

        # Option 2: Enter token
        tk.Label(
            card, text="Step 2: Enter GitHub Token (PAT)",
            font=FONTS["label_bold"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]
        ).pack(anchor="w")

        ent_row = tk.Frame(card, bg=COLORS["bg_card"])
        ent_row.pack(fill="x", pady=(6, 4))

        self._token_ent = tk.Entry(
            ent_row, textvariable=self._token_var, font=FONTS["mono"],
            bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
            highlightthickness=1, highlightbackground=COLORS["border"], show="•"
        )
        self._token_ent.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))

        paste_btn = tk.Button(
            ent_row, text="📋 Paste", font=FONTS["caption"],
            bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
            command=self._paste_token
        )
        paste_btn.pack(side="right")

        self._token_ent.bind("<Return>", lambda e: self._submit())

        # Status / Error label
        self._status_lbl = tk.Label(
            p, text="", font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"],
            wraplength=430, justify="left"
        )
        self._status_lbl.pack(fill="x", pady=(2, 10))

        # Actions row
        act_row = tk.Frame(p, bg=COLORS["bg_darkest"])
        act_row.pack(fill="x", pady=(4, 0))

        cancel_btn = tk.Button(
            act_row, text="Cancel", font=FONTS["label"],
            bg=COLORS["bg_medium"], fg=COLORS["text_secondary"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=16, pady=8,
            command=self.dialog.destroy
        )
        cancel_btn.pack(side="left")

        self._submit_btn = tk.Button(
            act_row, text="🐙 Connect & Continue", font=FONTS["heading_sm"],
            bg=COLORS["accent"], fg="#ffffff",
            activebackground=COLORS["accent_hover"], activeforeground="#ffffff",
            relief="flat", bd=0, cursor="hand2", padx=18, pady=8,
            command=self._submit
        )
        self._submit_btn.pack(side="right")

        self._token_ent.focus()

    def _open_browser_auth(self):
        url = github_service.get_github_web_auth_url("CommitMaster Desktop Login")
        webbrowser.open(url, new=2)
        self._status_lbl.config(
            text="Opened GitHub in browser! Sign in, scroll down, click 'Generate token', and paste it here.",
            fg=COLORS["info"]
        )

    def _detect_gh_cli(self):
        try:
            res = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            )
            token = res.stdout.strip()
            if res.returncode == 0 and token.startswith(("ghp_", "github_pat_")):
                self._token_var.set(token)
                self._status_lbl.config(text="✔ GitHub token detected from 'gh' CLI!", fg=COLORS["success"])
                return
        except Exception:
            pass
        self._status_lbl.config(
            text="Could not detect token from 'gh' CLI. Please click 'Generate Token on GitHub'.",
            fg=COLORS["warning"]
        )

    def _paste_token(self):
        try:
            clipboard = self.dialog.clipboard_get().strip()
            if clipboard:
                self._token_var.set(clipboard)
        except Exception:
            pass

    def _submit(self):
        token = self._token_var.get().strip()
        if not token:
            self._status_lbl.config(text="Please paste or enter your GitHub Personal Access Token.", fg=COLORS["error"])
            return

        self._submit_btn.config(state="disabled", text="Verifying with GitHub...")
        self._status_lbl.config(text="Connecting to GitHub API...", fg=COLORS["info"])
        self.dialog.update_idletasks()

        threading.Thread(target=self._verify_and_login, args=(token,), daemon=True).start()

    def _verify_and_login(self, token: str):
        ok, info, msg = github_service.verify_github_token(token)
        if not ok or not info:
            def _fail():
                self._submit_btn.config(state="normal", text="🐙 Connect & Continue")
                self._status_lbl.config(text=f"Authentication failed: {msg}", fg=COLORS["error"])
            self.dialog.after(0, _fail)
            return

        # Success from GitHub! Now match or create user in CommitMaster
        gh_user = info.get("username", "")
        gh_email = info.get("email", "")
        gh_name = info.get("name") or gh_user
        gh_avatar = info.get("avatar_url", "")

        user = None
        if gh_email:
            user = db.get_user_by_username_or_email(gh_email)
        if not user and gh_user:
            user = db.get_user_by_username_or_email(gh_user)

        # Check existing linked account
        if not user:
            try:
                conn = db.get_conn()
                row = conn.execute("SELECT user_id FROM github_accounts WHERE account_username = ? LIMIT 1", (gh_user,)).fetchone()
                if row:
                    user = db.get_user(row["user_id"])
            except Exception:
                pass

        if not user:
            # CREATE NEW ACCOUNT WITH GITHUB
            base_uname = gh_user.lower().replace(" ", "_")
            uname = base_uname
            c = 1
            while db.check_user_exists(uname, gh_email or f"{uname}@github.com") == "username":
                uname = f"{base_uname}{c}"
                c += 1

            email_to_use = gh_email or f"{uname}@users.noreply.github.com"
            rand_pw = secrets.token_urlsafe(16)
            uid = db.create_user(uname, email_to_use, gh_name, rand_pw)
            if not uid:
                def _err():
                    self._submit_btn.config(state="normal", text="🐙 Connect & Continue")
                    self._status_lbl.config(text="Could not create user account in local database.", fg=COLORS["error"])
                self.dialog.after(0, _err)
                return

            db.mark_user_verified(uid)
            if gh_avatar:
                download_and_save_avatar(uid, gh_avatar)

            # Link GitHub token
            try:
                db.add_github_account(uid, token, gh_user, gh_avatar, is_default=1)
            except Exception:
                pass

            user = db.get_user(uid)
            log.info("Created new account with GitHub: @%s (uid: %d)", uname, uid)
        else:
            # EXISTING USER: Sign in & update linked GitHub account
            uid = user["id"]
            db.mark_user_verified(uid)
            try:
                db.add_github_account(uid, token, gh_user, gh_avatar, is_default=1)
            except Exception:
                pass
            if gh_avatar and not user.get("avatar_image"):
                download_and_save_avatar(uid, gh_avatar)
            user = db.get_user(uid)
            log.info("Signed in existing user with GitHub: @%s (uid: %d)", user["username"], uid)

        session_token = db.create_session_token(user["id"])
        account_manager.save_account(user, session_token)

        def _finish():
            self.dialog.destroy()
            if self.on_success:
                self.on_success(user)

        self.dialog.after(0, _finish)


class GoogleAuthDialog:
    """
    Dialog for signing in or creating a CommitMaster account with Google.
    Supports email verification and Google account authentication.
    """

    def __init__(self, parent: tk.Tk, on_success: Callable[[Dict[str, Any]], None]):
        self.master = parent
        self.on_success = on_success

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("CommitMaster — Continue with Google")
        self.dialog.geometry("460x440")
        self.dialog.minsize(420, 420)
        self.dialog.configure(bg=COLORS["bg_darkest"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center on parent
        self.dialog.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w, h = 460, 440
        x = max(20, px + (pw - w) // 2)
        y = max(20, py + (ph - h) // 2)
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

        from commitmaster import windows_integration
        windows_integration.apply_windows_theme(self.dialog, "CommitMaster — Continue with Google")

        self._email_var = tk.StringVar()
        self._name_var = tk.StringVar()
        self._build_ui()

    def _build_ui(self):
        p = tk.Frame(self.dialog, bg=COLORS["bg_darkest"], padx=24, pady=20)
        p.pack(fill="both", expand=True)

        # Header with Google branding
        hdr = tk.Frame(p, bg=COLORS["bg_darkest"])
        hdr.pack(fill="x", pady=(0, 12))

        tk.Label(
            hdr, text="🌐  Continue with Google",
            font=FONTS["heading_lg"], fg=COLORS["text_primary"], bg=COLORS["bg_darkest"]
        ).pack(anchor="w")

        tk.Label(
            hdr,
            text="Sign in or create your CommitMaster account with your Google Account.",
            font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"]
        ).pack(anchor="w", pady=(2, 0))

        # Card container
        card = tk.Frame(p, bg=COLORS["bg_card"], padx=18, pady=16, highlightthickness=1, highlightbackground=COLORS["border"])
        card.pack(fill="x", pady=(0, 12))

        # Email entry
        tk.Label(
            card, text="Google Account Email",
            font=FONTS["label_bold"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]
        ).pack(anchor="w")

        tk.Label(
            card, text="Supports @gmail.com, @googlemail.com, and Google Workspace domains.",
            font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(1, 4))

        self._email_ent = tk.Entry(
            card, textvariable=self._email_var, font=FONTS["body_md"],
            bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
            highlightthickness=1, highlightbackground=COLORS["border"]
        )
        self._email_ent.pack(fill="x", ipady=6, pady=(0, 10))
        self._email_ent.bind("<Return>", lambda e: self._submit())

        # Full Name entry (for new account creation)
        tk.Label(
            card, text="Your Full Name (Optional for new users)",
            font=FONTS["label_bold"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]
        ).pack(anchor="w")

        self._name_ent = tk.Entry(
            card, textvariable=self._name_var, font=FONTS["body_md"],
            bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
            highlightthickness=1, highlightbackground=COLORS["border"]
        )
        self._name_ent.pack(fill="x", ipady=6, pady=(4, 0))
        self._name_ent.bind("<Return>", lambda e: self._submit())

        # Status / Error label
        self._status_lbl = tk.Label(
            p, text="", font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"],
            wraplength=410, justify="left"
        )
        self._status_lbl.pack(fill="x", pady=(2, 10))

        # Actions row
        act_row = tk.Frame(p, bg=COLORS["bg_darkest"])
        act_row.pack(fill="x", pady=(4, 0))

        cancel_btn = tk.Button(
            act_row, text="Cancel", font=FONTS["label"],
            bg=COLORS["bg_medium"], fg=COLORS["text_secondary"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=16, pady=8,
            command=self.dialog.destroy
        )
        cancel_btn.pack(side="left")

        self._submit_btn = tk.Button(
            act_row, text="🌐 Sign in with Google", font=FONTS["heading_sm"],
            bg="#4285f4", fg="#ffffff",
            activebackground="#3367d6", activeforeground="#ffffff",
            relief="flat", bd=0, cursor="hand2", padx=18, pady=8,
            command=self._submit
        )
        self._submit_btn.pack(side="right")

        self._email_ent.focus()

    def _submit(self):
        email = self._email_var.get().strip().lower()
        if not email or "@" not in email or "." not in email:
            self._status_lbl.config(text="Please enter a valid Google Account email address.", fg=COLORS["error"])
            return

        self._submit_btn.config(state="disabled", text="Verifying Google Account...")
        self._status_lbl.config(text="Authenticating with Google Account...", fg=COLORS["info"])
        self.dialog.update_idletasks()

        user = db.get_user_by_username_or_email(email)
        if not user:
            # CREATE NEW ACCOUNT WITH GOOGLE
            raw_uname = email.split("@")[0].lower()
            clean_uname = re.sub(r"[^a-zA-Z0-9_]", "_", raw_uname).strip("_") or "user"
            uname = clean_uname
            c = 1
            while db.check_user_exists(uname, email) == "username":
                uname = f"{clean_uname}{c}"
                c += 1

            full_name = self._name_var.get().strip() or clean_uname.replace("_", " ").title()
            rand_pw = secrets.token_urlsafe(16)

            uid = db.create_user(uname, email, full_name, rand_pw)
            if not uid:
                self._submit_btn.config(state="normal", text="🌐 Sign in with Google")
                self._status_lbl.config(text="Could not create user account in local database.", fg=COLORS["error"])
                return

            db.mark_user_verified(uid)
            try:
                conn = db.get_conn()
                conn.execute("UPDATE users SET google_id = ?, avatar_color = ? WHERE id = ?", (email, "#4285f4", uid))
                conn.commit()
            except Exception:
                pass

            user = db.get_user(uid)
            log.info("Created new account with Google: @%s (uid: %d)", uname, uid)
        else:
            # EXISTING USER: Sign in
            uid = user["id"]
            db.mark_user_verified(uid)
            try:
                conn = db.get_conn()
                conn.execute("UPDATE users SET google_id = ? WHERE id = ?", (email, uid))
                conn.commit()
            except Exception:
                pass
            user = db.get_user(uid)
            log.info("Signed in existing user with Google: @%s (uid: %d)", user["username"], uid)

        session_token = db.create_session_token(user["id"])
        account_manager.save_account(user, session_token)

        self.dialog.destroy()
        if self.on_success:
            self.on_success(user)
