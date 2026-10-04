"""
CommitMaster — GitHub Account Modal Dialog.
Allows adding or editing linked GitHub accounts with token verification,
auto-detection of username/email, and default account management.
"""
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Optional, Callable

from commitmaster import database as db
from commitmaster.app_styles import COLORS, FONTS
from commitmaster.github_service import verify_github_token, mask_token


class GitHubAccountDialog:
    """Dialog for creating or editing a linked GitHub account."""

    def __init__(self, parent, user_id: int, account: Optional[Dict] = None, on_saved: Optional[Callable] = None):
        self.parent = parent
        self.user_id = user_id
        self.account = account
        self.on_saved = on_saved
        self.is_edit = account is not None

        self._build_dialog()

    def _build_dialog(self):
        title = "Edit GitHub Account" if self.is_edit else "Link New GitHub Account"
        self.top = tk.Toplevel(self.parent)
        self.top.title(title)
        self.top.configure(bg=COLORS["bg_dark"])
        self.top.geometry("520x620")
        self.top.minsize(480, 560)
        self.top.grab_set()
        self.top.focus_set()
        self.top.transient(self.parent)

        # Center on parent
        self.top.update_idletasks()
        try:
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            w, h = 520, 620
            self.top.geometry(f"{w}x{h}+{px + (pw - w)//2}+{py + (ph - h)//2}")
        except Exception:
            pass

        pad = tk.Frame(self.top, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        # Header
        tk.Label(pad, text=title, font=FONTS["heading_md"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad,
                 text="Connect a GitHub account to push repositories directly and monitor your projects.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"], wraplength=460).pack(anchor="w", pady=(2, 10))

        # Web Sign-In Card (Guides user to GitHub web token creation with pre-filled scopes)
        web_card = tk.Frame(pad, bg=COLORS["bg_card"], padx=12, pady=10,
                            highlightthickness=1, highlightbackground=COLORS["border"])
        web_card.pack(fill="x", pady=(0, 14))

        web_hdr = tk.Frame(web_card, bg=COLORS["bg_card"])
        web_hdr.pack(fill="x")
        tk.Label(web_hdr, text="🌐 Sign in via GitHub Web",
                 font=FONTS["label_bold"], fg=COLORS["accent"], bg=COLORS["bg_card"]).pack(side="left")

        tk.Label(web_card,
                 text="Opens GitHub in your browser with all required scopes selected. Click 'Generate token' on the page, copy it, and paste it below.",
                 font=FONTS["caption"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"], wraplength=460, justify="left").pack(anchor="w", pady=(4, 8))

        web_btns = tk.Frame(web_card, bg=COLORS["bg_card"])
        web_btns.pack(fill="x")

        open_web_btn = tk.Button(web_btns, text="🌐 Open GitHub Web Sign-In",
                                 font=FONTS["label_bold"], fg="white",
                                 bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                                 activeforeground="white", relief="flat", bd=0,
                                 cursor="hand2", padx=12, pady=6,
                                 command=self._open_web_sign_in)
        open_web_btn.pack(side="left", padx=(0, 8))

        paste_btn = tk.Button(web_btns, text="📋 Paste from Clipboard",
                              font=FONTS["label"], fg=COLORS["text_primary"],
                              bg=COLORS["bg_medium"], activebackground=COLORS["bg_card_hover"],
                              activeforeground=COLORS["text_primary"], relief="flat", bd=0,
                              cursor="hand2", padx=10, pady=6,
                              command=self._paste_from_clipboard)
        paste_btn.pack(side="left")

        # Fields frame
        form = tk.Frame(pad, bg=COLORS["bg_dark"])
        form.pack(fill="both", expand=True)

        # 1. Account Nickname / Label
        self._name_var = tk.StringVar(value=self.account.get("account_name", "") if self.is_edit else "")
        self._add_row(form, "Account Label / Nickname *", self._name_var,
                      placeholder="e.g. Personal GitHub, Work Org, Freelance")

        # 2. Token Row with Show/Hide toggle and Verify button
        tk.Label(form, text="Personal Access Token (PAT) *", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(8, 2))

        token_frame = tk.Frame(form, bg=COLORS["bg_dark"])
        token_frame.pack(fill="x", pady=(0, 4))

        self._token_var = tk.StringVar(value=self.account.get("github_token", "") if self.is_edit else "")
        self._show_token = False
        self._token_entry = tk.Entry(token_frame, textvariable=self._token_var, font=FONTS["body_md"],
                                     bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                                     relief="flat", highlightthickness=1,
                                     highlightbackground=COLORS["border"], show="•")
        self._token_entry.pack(side="left", fill="x", expand=True, ipady=6)

        self._toggle_btn = tk.Button(token_frame, text="👁 Show", font=FONTS["label"],
                                     fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                                     relief="flat", bd=0, padx=8, pady=4, cursor="hand2",
                                     command=self._toggle_token_visibility)
        self._toggle_btn.pack(side="left", padx=(6, 0))

        verify_btn = tk.Button(form, text="⚡ Verify & Auto-Fill from GitHub",
                               font=FONTS["label_bold"], fg="white",
                               bg=COLORS["info"], activebackground="#388bfd",
                               activeforeground="white", relief="flat", bd=0,
                               cursor="hand2", padx=12, pady=6,
                               command=self._verify_and_autofill)
        verify_btn.pack(anchor="w", pady=(2, 8))

        self._verify_status_label = tk.Label(form, text="", font=FONTS["caption"],
                                             fg=COLORS["text_secondary"], bg=COLORS["bg_dark"])
        self._verify_status_label.pack(anchor="w", pady=(0, 6))

        # 3. GitHub Username
        self._uname_var = tk.StringVar(value=self.account.get("github_username", "") if self.is_edit else "")
        self._add_row(form, "GitHub Username *", self._uname_var, placeholder="e.g. Saumya-Patel-10")

        # 4. Git Author Name & Email (optional)
        self._author_var = tk.StringVar(value=self.account.get("author_name", "") if self.is_edit else "")
        self._add_row(form, "Git Author Name (optional)", self._author_var, placeholder="e.g. Saumya Patel")

        self._email_var = tk.StringVar(value=self.account.get("author_email", "") if self.is_edit else "")
        self._add_row(form, "Git Author Email (optional)", self._email_var, placeholder="e.g. saumya@example.com")

        # 5. Default account checkbox
        is_def = bool(self.account.get("is_default", 0)) if self.is_edit else False
        self._default_var = tk.BooleanVar(value=is_def)
        def_cb = tk.Checkbutton(form, text="Set as default push account",
                                variable=self._default_var,
                                font=FONTS["body_md"], fg=COLORS["text_primary"],
                                bg=COLORS["bg_dark"], selectcolor=COLORS["bg_input"],
                                activebackground=COLORS["bg_dark"],
                                activeforeground=COLORS["text_primary"])
        def_cb.pack(anchor="w", pady=(10, 14))

        # Action Buttons
        btn_row = tk.Frame(pad, bg=COLORS["bg_dark"])
        btn_row.pack(fill="x", pady=(10, 0))

        save_btn = tk.Button(btn_row, text="💾 Save Account", font=FONTS["heading_sm"],
                             fg="white", bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                             activeforeground="white", relief="flat", bd=0, cursor="hand2",
                             padx=18, pady=8, command=self._save_account)
        save_btn.pack(side="left", padx=(0, 10))

        cancel_btn = tk.Button(btn_row, text="Cancel", font=FONTS["label"],
                               fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                               activebackground=COLORS["bg_card_hover"],
                               activeforeground=COLORS["text_primary"],
                               relief="flat", bd=0, cursor="hand2",
                               padx=14, pady=8, command=self.top.destroy)
        cancel_btn.pack(side="left")

    def _add_row(self, parent, label: str, var: tk.StringVar, placeholder: str = ""):
        f = tk.Frame(parent, bg=COLORS["bg_dark"])
        f.pack(fill="x", pady=(0, 8))
        tk.Label(f, text=label, font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        e = tk.Entry(f, textvariable=var, font=FONTS["body_md"],
                     bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                     relief="flat", highlightthickness=1,
                     highlightbackground=COLORS["border"])
        e.pack(fill="x", ipady=6, pady=(2, 0))

    def _toggle_token_visibility(self):
        self._show_token = not self._show_token
        self._token_entry.config(show="" if self._show_token else "•")
        self._toggle_btn.config(text="🙈 Hide" if self._show_token else "👁 Show")

    def _verify_and_autofill(self):
        token = self._token_var.get().strip()
        if not token:
            self._verify_status_label.config(text="⚠ Please enter a Personal Access Token first.", fg=COLORS["error"])
            return

        self._verify_status_label.config(text="⏳ Verifying token with GitHub API...", fg=COLORS["info"])
        self.top.update_idletasks()

        ok, info, msg = verify_github_token(token)
        if ok:
            self._verify_status_label.config(text=f"✔ {msg}", fg=COLORS["success"])
            if not self._name_var.get().strip():
                self._name_var.set(f"GitHub (@{info['username']})")
            self._uname_var.set(info["username"])
            if info.get("name") and not self._author_var.get().strip():
                self._author_var.set(info["name"])
            if info.get("email") and not self._email_var.get().strip():
                self._email_var.set(info["email"])
        else:
            self._verify_status_label.config(text=f"✖ {msg}", fg=COLORS["error"])

    def _open_web_sign_in(self):
        """Open browser to GitHub's token creation page with pre-filled scopes."""
        from commitmaster import github_service
        ok = github_service.open_github_web_auth()
        if ok:
            self._verify_status_label.config(
                text="🌐 Browser opened! Log into GitHub, scroll down, click 'Generate token', then copy and paste it here.",
                fg=COLORS["info"],
            )
        else:
            self._verify_status_label.config(
                text="⚠ Could not launch browser automatically. Visit: https://github.com/settings/tokens/new",
                fg=COLORS["warning"],
            )

    def _paste_from_clipboard(self):
        """Read clipboard, populate token, and automatically verify."""
        try:
            content = self.top.clipboard_get().strip()
            if content:
                self._token_var.set(content)
                self._verify_and_autofill()
            else:
                self._verify_status_label.config(text="⚠ Clipboard is empty.", fg=COLORS["warning"])
        except Exception as exc:
            self._verify_status_label.config(text=f"⚠ Could not read clipboard: {exc}", fg=COLORS["warning"])

    def _save_account(self):
        name = self._name_var.get().strip()
        token = self._token_var.get().strip()
        uname = self._uname_var.get().strip()
        author = self._author_var.get().strip()
        email = self._email_var.get().strip()
        is_default = self._default_var.get()

        if not name or not token or not uname:
            messagebox.showwarning("Validation Error",
                                   "Please fill in Account Label, Token, and Username.",
                                   parent=self.top)
            return

        account_id = None
        if self.is_edit:
            ok = db.update_github_account(
                self.account["id"],
                self.user_id,
                account_name=name,
                github_username=uname,
                github_token=token,
                author_name=author,
                author_email=email,
                is_default=1 if is_default else 0,
            )
            account_id = self.account["id"]
        else:
            aid = db.add_github_account(
                user_id=self.user_id,
                account_name=name,
                github_username=uname,
                github_token=token,
                author_name=author,
                author_email=email,
                is_default=is_default,
            )
            ok = aid is not None
            account_id = aid

        if ok:
            # Sync user's repositories in background thread
            try:
                import threading
                from commitmaster import github_service

                def _bg_sync(uid, aid, tok):
                    succ, repos, _ = github_service.fetch_user_repositories(tok)
                    if succ and repos:
                        db.sync_github_repos(uid, aid, repos)

                threading.Thread(target=_bg_sync, args=(self.user_id, account_id, token), daemon=True).start()
            except Exception:
                pass

            messagebox.showinfo("Success",
                                f"GitHub account '{name}' saved successfully!\nRepositories are being synced.",
                                parent=self.top)
            self.top.destroy()
            if self.on_saved:
                self.on_saved()
        else:
            messagebox.showerror("Error", "Could not save GitHub account to database.", parent=self.top)
