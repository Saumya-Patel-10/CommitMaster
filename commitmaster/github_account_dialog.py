"""
CommitMaster — GitHub Account Modal Dialog & Repository Selector.
Allows adding or editing linked GitHub accounts with token verification,
and selecting which specific repositories CommitMaster has permission to access.
"""
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, Optional, Callable, List

from commitmaster import database as db
from commitmaster.app_styles import COLORS, FONTS
from commitmaster.github_service import verify_github_token, mask_token, fetch_user_repositories


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
        self.top.geometry("560x680")
        self.top.minsize(480, 520)
        self.top.resizable(True, True)
        self.top.grab_set()
        self.top.focus_set()
        self.top.transient(self.parent)

        # Center on parent or screen
        self.top.update_idletasks()
        try:
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            w, h = 560, 680
            self.top.geometry(f"{w}x{h}+{max(0, px + (pw - w)//2)}+{max(0, py + (ph - h)//2)}")
        except Exception:
            pass

        # ── Pinned Bottom Action Bar ──────────────────────────────────────────
        # Packing side="bottom" FIRST ensures the save and cancel buttons are ALWAYS visible
        btn_bar = tk.Frame(self.top, bg=COLORS["bg_dark"], padx=20, pady=14)
        btn_bar.pack(side="bottom", fill="x")

        save_btn = tk.Button(btn_bar, text="  💾 Save GitHub Account  ", font=FONTS["heading_sm"],
                             fg="white", bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                             activeforeground="white", relief="flat", bd=0, cursor="hand2",
                             padx=20, pady=9, command=self._save_account)
        save_btn.pack(side="left", padx=(0, 10))

        cancel_btn = tk.Button(btn_bar, text="Cancel", font=FONTS["label"],
                               fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                               activebackground=COLORS["bg_card_hover"],
                               activeforeground=COLORS["text_primary"],
                               relief="flat", bd=0, cursor="hand2",
                               padx=16, pady=9, command=self.top.destroy)
        cancel_btn.pack(side="left")

        # Subtle separator above button bar
        sep = tk.Frame(self.top, height=1, bg=COLORS["border"])
        sep.pack(side="bottom", fill="x")

        # ── Scrollable Center Canvas ─────────────────────────────────────────
        canvas_outer = tk.Frame(self.top, bg=COLORS["bg_dark"])
        canvas_outer.pack(side="top", fill="both", expand=True)

        self._canvas = tk.Canvas(canvas_outer, bg=COLORS["bg_dark"], highlightthickness=0)
        self._scrollbar = tk.Scrollbar(canvas_outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._form = tk.Frame(self._canvas, bg=COLORS["bg_dark"], padx=24, pady=16)
        self._canvas_win = self._canvas.create_window((0, 0), window=self._form, anchor="nw")

        self._form.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(self._canvas_win, width=e.width))

        # Mouse wheel support
        def _on_mousewheel(event):
            try:
                if event.delta:
                    self._canvas.yview_scroll(int(-1 * (event.delta / 120) * 3), "units")
            except Exception:
                pass
        self.top.bind("<MouseWheel>", _on_mousewheel)

        pad = self._form

        # Header
        tk.Label(pad, text=title, font=FONTS["heading_md"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad,
                 text="Link a GitHub account to push repositories and selectively monitor your projects.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"], wraplength=480, justify="left").pack(anchor="w", pady=(2, 12))

        # Web Sign-In Card (Guides user to GitHub web token creation with pre-filled scopes)
        web_card = tk.Frame(pad, bg=COLORS["bg_card"], padx=14, pady=12,
                            highlightthickness=1, highlightbackground=COLORS["border"])
        web_card.pack(fill="x", pady=(0, 14))

        web_hdr = tk.Frame(web_card, bg=COLORS["bg_card"])
        web_hdr.pack(fill="x")
        tk.Label(web_hdr, text="🌐 Sign in via GitHub Web",
                 font=FONTS["label_bold"], fg=COLORS["accent"], bg=COLORS["bg_card"]).pack(side="left")

        tk.Label(web_card,
                 text="Opens GitHub in your browser with all required scopes pre-selected. Click 'Generate token' on GitHub, copy it, and paste it below.",
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

        # ── Input Fields ──────────────────────────────────────────────────────
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
        verify_btn.pack(anchor="w", pady=(2, 6))

        self._verify_status_label = tk.Label(form, text="", font=FONTS["caption"],
                                             fg=COLORS["text_secondary"], bg=COLORS["bg_dark"], wraplength=480, justify="left")
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
        def_cb.pack(anchor="w", pady=(8, 16))

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

        if ok:
            messagebox.showinfo(
                "Account Saved",
                f"GitHub account '{name}' (@{uname}) saved successfully!\n\n"
                "You can now select which specific repositories you want CommitMaster to access.",
                parent=self.top
            )
            self.top.destroy()
            if self.on_saved:
                self.on_saved()
        else:
            messagebox.showerror("Error", "Could not save GitHub account to database.", parent=self.top)


class SelectGitHubReposDialog:
    """Dialog for explicitly selecting which GitHub repositories CommitMaster has access to."""

    def __init__(self, parent, user_id: int, on_selected: Optional[Callable] = None):
        self.parent = parent
        self.user_id = user_id
        self.on_selected = on_selected
        self._all_repos = []
        self._check_vars = {}

        self.top = tk.Toplevel(self.parent)
        self.top.title("Select Repositories to Authorize")
        self.top.configure(bg=COLORS["bg_dark"])
        self.top.geometry("640x700")
        self.top.minsize(540, 520)
        self.top.resizable(True, True)
        self.top.grab_set()
        self.top.focus_set()
        self.top.transient(self.parent)

        # Center dialog
        self.top.update_idletasks()
        try:
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            w, h = 640, 700
            self.top.geometry(f"{w}x{h}+{max(0, px + (pw - w)//2)}+{max(0, py + (ph - h)//2)}")
        except Exception:
            pass

        self._build_ui()
        self._load_accounts_and_fetch()

    def _build_ui(self):
        # ── Pinned Bottom Bar ─────────────────────────────────────────────────
        btn_bar = tk.Frame(self.top, bg=COLORS["bg_dark"], padx=20, pady=14)
        btn_bar.pack(side="bottom", fill="x")

        self._submit_btn = tk.Button(
            btn_bar, text="  ✓ Authorize Selected Repositories  ",
            font=FONTS["heading_sm"], fg="white", bg=COLORS["accent"],
            activebackground=COLORS["accent_hover"], activeforeground="white",
            relief="flat", bd=0, cursor="hand2", padx=18, pady=9,
            command=self._save_selected
        )
        self._submit_btn.pack(side="left", padx=(0, 10))

        cancel_btn = tk.Button(
            btn_bar, text="Cancel", font=FONTS["label"],
            fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=16, pady=9,
            command=self.top.destroy
        )
        cancel_btn.pack(side="left")

        # Auto-watch checkbox on bottom bar
        self._active_watch_var = tk.BooleanVar(value=True)
        cb_watch = tk.Checkbutton(
            btn_bar, text="Actively watch selected (auto-commit & AI comments)",
            variable=self._active_watch_var, font=FONTS["caption"],
            fg=COLORS["text_secondary"], bg=COLORS["bg_dark"],
            selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_dark"],
            activeforeground=COLORS["text_primary"]
        )
        cb_watch.pack(side="right")

        tk.Frame(self.top, height=1, bg=COLORS["border"]).pack(side="bottom", fill="x")

        # ── Top Controls ──────────────────────────────────────────────────────
        top_frame = tk.Frame(self.top, bg=COLORS["bg_dark"], padx=20, pady=16)
        top_frame.pack(side="top", fill="x")

        tk.Label(top_frame, text="Select Repositories to Authorize", font=FONTS["heading_md"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(top_frame,
                 text="Check only the repositories you want CommitMaster to access. Unchecked repositories will never be touched.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 10))

        # Account selector & Search row
        filter_row = tk.Frame(top_frame, bg=COLORS["bg_dark"])
        filter_row.pack(fill="x")

        tk.Label(filter_row, text="GitHub Account:", font=FONTS["caption"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(side="left", padx=(0, 6))

        self._acc_var = tk.StringVar()
        self._acc_dropdown = tk.OptionMenu(filter_row, self._acc_var, "", command=self._on_account_change)
        self._acc_dropdown.config(font=FONTS["caption"], bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
                                  relief="flat", bd=0, highlightthickness=0)
        self._acc_dropdown["menu"].config(bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["caption"], bd=0)
        self._acc_dropdown.pack(side="left", padx=(0, 14))

        tk.Label(filter_row, text="Search:", font=FONTS["caption"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(side="left", padx=(0, 6))

        self._search_var = tk.StringVar()
        search_e = tk.Entry(filter_row, textvariable=self._search_var, font=FONTS["body_sm"],
                            bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                            relief="flat", highlightthickness=1, highlightbackground=COLORS["border"], width=18)
        search_e.pack(side="left", ipady=3, padx=(0, 10))
        search_e.bind("<KeyRelease>", lambda e: self._render_list())

        select_all_btn = tk.Button(filter_row, text="Select All", font=FONTS["caption"],
                                   fg=COLORS["accent"], bg=COLORS["bg_medium"], relief="flat", bd=0,
                                   cursor="hand2", padx=8, pady=3, command=self._select_all)
        select_all_btn.pack(side="left", padx=2)

        deselect_btn = tk.Button(filter_row, text="Deselect All", font=FONTS["caption"],
                                 fg=COLORS["text_secondary"], bg=COLORS["bg_medium"], relief="flat", bd=0,
                                 cursor="hand2", padx=8, pady=3, command=self._deselect_all)
        deselect_btn.pack(side="left", padx=2)

        self._status_lbl = tk.Label(top_frame, text="Loading repositories...", font=FONTS["caption"],
                                    fg=COLORS["text_muted"], bg=COLORS["bg_dark"])
        self._status_lbl.pack(anchor="w", pady=(8, 0))

        tk.Frame(self.top, height=1, bg=COLORS["border"]).pack(side="top", fill="x")

        # ── Scrollable Repositories List ──────────────────────────────────────
        list_outer = tk.Frame(self.top, bg=COLORS["bg_dark"])
        list_outer.pack(side="top", fill="both", expand=True)

        self._canvas = tk.Canvas(list_outer, bg=COLORS["bg_dark"], highlightthickness=0)
        self._scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._list_frame = tk.Frame(self._canvas, bg=COLORS["bg_dark"], padx=20, pady=10)
        self._canvas_win = self._canvas.create_window((0, 0), window=self._list_frame, anchor="nw")

        self._list_frame.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(self._canvas_win, width=e.width))

        def _on_wheel(e):
            try:
                if e.delta:
                    self._canvas.yview_scroll(int(-1 * (e.delta / 120) * 3), "units")
            except Exception:
                pass
        self.top.bind("<MouseWheel>", _on_wheel)

    def _load_accounts_and_fetch(self):
        accounts = db.get_github_accounts(self.user_id)
        if not accounts:
            self._status_lbl.config(text="⚠ No GitHub accounts linked. Please link an account first.", fg=COLORS["warning"])
            return

        self._accounts_map = {f"{a['account_name']} (@{a['github_username']})": a for a in accounts}
        menu = self._acc_dropdown["menu"]
        menu.delete(0, "end")
        first_lbl = list(self._accounts_map.keys())[0]
        self._acc_var.set(first_lbl)
        for lbl in self._accounts_map.keys():
            menu.add_command(label=lbl, command=lambda l=lbl: (self._acc_var.set(l), self._on_account_change(l)))

        self._fetch_repos_for_account(self._accounts_map[first_lbl])

    def _on_account_change(self, selected_lbl):
        acc = self._accounts_map.get(selected_lbl)
        if acc:
            self._fetch_repos_for_account(acc)

    def _fetch_repos_for_account(self, account):
        self._status_lbl.config(text=f"Fetching repositories for @{account['github_username']}...", fg=COLORS["info"])
        self.top.update_idletasks()

        def _worker():
            succ, repos, msg = fetch_user_repositories(account["github_token"])
            def _apply():
                if succ:
                    self._all_repos = repos
                    self._status_lbl.config(text=f"✔ Found {len(repos)} repositories under @{account['github_username']}. Select the ones you want:", fg=COLORS["success"])
                    self._render_list()
                else:
                    self._status_lbl.config(text=f"✖ Failed to fetch: {msg}", fg=COLORS["error"])
            self.top.after(0, _apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _render_list(self):
        for widget in self._list_frame.winfo_children():
            widget.destroy()

        # Existing authorized repos for this user
        existing_watched = {r["repo_full_name"].lower(): r for r in db.get_watched_repos(self.user_id)}

        q = self._search_var.get().strip().lower()
        matched = [r for r in self._all_repos if not q or q in r.get("full_name", "").lower() or q in (r.get("description") or "").lower()]

        if not matched:
            lbl = tk.Label(self._list_frame, text="No repositories match your search.", font=FONTS["body_sm"],
                           fg=COLORS["text_muted"], bg=COLORS["bg_dark"])
            lbl.pack(anchor="w", pady=20)
            return

        for repo in matched:
            full_name = repo.get("full_name") or repo.get("name")
            is_already = full_name.lower() in existing_watched

            if full_name not in self._check_vars:
                # If already authorized, check it by default
                self._check_vars[full_name] = tk.BooleanVar(value=is_already)

            card = tk.Frame(self._list_frame, bg=COLORS["bg_card"], padx=12, pady=10,
                            highlightthickness=1, highlightbackground=COLORS["border"])
            card.pack(fill="x", pady=(0, 6))

            hdr_row = tk.Frame(card, bg=COLORS["bg_card"])
            hdr_row.pack(fill="x")

            cb = tk.Checkbutton(
                hdr_row, text=f" {full_name}", variable=self._check_vars[full_name],
                font=FONTS["label_bold"], fg=COLORS["text_primary"], bg=COLORS["bg_card"],
                selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"],
                activeforeground=COLORS["accent"], cursor="hand2"
            )
            cb.pack(side="left")

            priv_badge = "🔒 Private" if repo.get("private") else "🌐 Public"
            badge_color = COLORS["warning"] if repo.get("private") else COLORS["info"]
            tk.Label(hdr_row, text=f"  {priv_badge}  ", font=("Segoe UI", 8, "bold"),
                     fg="white", bg=badge_color).pack(side="left", padx=8)

            if is_already:
                tk.Label(hdr_row, text="✔ Already Authorized", font=FONTS["caption"],
                         fg=COLORS["success"], bg=COLORS["bg_card"]).pack(side="right")

            desc = repo.get("description") or "(No description)"
            tk.Label(card, text=desc[:120], font=FONTS["caption"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", padx=(28, 0), pady=(2, 0))

    def _select_all(self):
        for var in self._check_vars.values():
            var.set(True)

    def _deselect_all(self):
        for var in self._check_vars.values():
            var.set(False)

    def _save_selected(self):
        selected_full_names = {name for name, var in self._check_vars.items() if var.get()}
        if not selected_full_names:
            messagebox.showwarning("None Selected", "Please select at least one repository to authorize.", parent=self.top)
            return

        acc_lbl = self._acc_var.get()
        acc = self._accounts_map.get(acc_lbl)
        account_id = acc["id"] if acc else None

        active_watch_val = 1 if self._active_watch_var.get() else 0
        count = 0
        for repo in self._all_repos:
            fname = repo.get("full_name") or repo.get("name")
            if fname in selected_full_names:
                db.add_or_update_watched_repo(
                    user_id=self.user_id,
                    github_account_id=account_id,
                    repo_name=repo.get("name") or fname.split("/")[-1],
                    repo_full_name=fname,
                    clone_url=repo.get("clone_url", ""),
                    ssh_url=repo.get("ssh_url", ""),
                    default_branch=repo.get("default_branch", "main"),
                    is_private=1 if repo.get("private") else 0,
                    description=repo.get("description") or "",
                    is_active_watch=active_watch_val,
                )
                count += 1

        messagebox.showinfo("Repositories Authorized",
                            f"Successfully authorized {count} repository{'ies' if count != 1 else 'y'}!\n\n"
                            "CommitMaster will only access these authorized repositories.", parent=self.top)
        self.top.destroy()
        if self.on_selected:
            self.on_selected()
