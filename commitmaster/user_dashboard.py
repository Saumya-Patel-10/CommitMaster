"""
CommitMaster — Main application dashboard (User view).
Shown after successful login. Includes sidebar nav, per-user settings,
commit history, and profile management.
"""
import json
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, Optional

from commitmaster.app_styles import (
    COLORS, FONTS, SIZES, AVATAR_COLORS, THEMES, ACCENTS, FONT_FAMILIES, FONT_SCALES,
    apply_customization, get_active_customization
)
from commitmaster import database as db
from commitmaster import commit_engine, ai_messages, ui, github_service
from commitmaster.config import load_config
from commitmaster.github_service import mask_token, verify_github_token
from commitmaster.github_account_dialog import GitHubAccountDialog, SelectGitHubReposDialog


class UserDashboard:
    """
    Full-featured user dashboard window with theme customization and
    multiple linked GitHub accounts support.
    on_logout() is called when the user chooses to log out.
    on_admin() is called when an admin wants to open the admin portal.
    """

    def __init__(self, user: Dict, on_logout: Callable, on_admin: Optional[Callable] = None):
        self.user = user
        self.on_logout = on_logout
        self.on_admin = on_admin
        self._active_nav = None

        # Load user saved customization
        prefs = db.get_preferences(self.user["id"]) or {}
        apply_customization(
            theme=prefs.get("theme"),
            accent=prefs.get("accent_color"),
            font_family=prefs.get("font_family"),
            font_scale=prefs.get("font_scale"),
            ui_density=prefs.get("ui_density"),
        )

        self.root = tk.Tk()

        # Git Desktop state
        self._gd_selected_repo: Optional[str] = None
        self._gd_changes: list = []
        self._gd_staged_vars: dict = {}
        self._gd_file_comments: dict = {}
        self._gd_active_file: Optional[str] = None
        self._gd_headline_var: tk.StringVar = tk.StringVar()
        self._gd_ask_push_var: tk.BooleanVar = tk.BooleanVar(value=bool(prefs.get("ask_before_push", 1)))
        self._gd_comment_var: tk.StringVar = tk.StringVar()
        self._gd_diff_text = None
        self._gd_desc_text = None
        self._gd_comment_entry = None
        self._gd_ai_status_lbl = None

        # Watched Repos state
        self._wr_search_var: tk.StringVar = tk.StringVar()
        self._wr_filter_mode: str = "all"

        self._setup_window()
        self._build_layout()
        self._nav_to("overview")

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        name = self.user.get("full_name") or self.user["username"]
        self.root.title(f"CommitMaster — {name}")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)
        self.root.configure(bg=COLORS["bg_darkest"])
        self.root.update_idletasks()
        w, h = 1100, 700
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")

    # ── Layout skeleton ───────────────────────────────────────────────────────

    def _build_layout(self):
        # Sidebar
        self._sidebar = tk.Frame(self.root, bg=COLORS["bg_sidebar"],
                                 width=SIZES["sidebar_width"])
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        # Main area
        self._main = tk.Frame(self.root, bg=COLORS["bg_dark"])
        self._main.pack(side="left", fill="both", expand=True)

        self._build_sidebar()
        self._build_header()

        # Content area (scrollable)
        self._content_outer = tk.Frame(self._main, bg=COLORS["bg_dark"])
        self._content_outer.pack(fill="both", expand=True)
        self._content_canvas = tk.Canvas(self._content_outer, bg=COLORS["bg_dark"],
                                         highlightthickness=0)
        self._content_scrollbar = tk.Scrollbar(self._content_outer, orient="vertical",
                                               command=self._content_canvas.yview)
        self._content_canvas.configure(yscrollcommand=self._content_scrollbar.set)
        self._content_scrollbar.pack(side="right", fill="y")
        self._content_canvas.pack(side="left", fill="both", expand=True)
        self._content_frame = tk.Frame(self._content_canvas, bg=COLORS["bg_dark"])
        self._content_window = self._content_canvas.create_window(
            (0, 0), window=self._content_frame, anchor="nw")
        self._content_frame.bind("<Configure>", self._on_frame_configure)
        self._content_canvas.bind("<Configure>", self._on_canvas_configure)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        try:
            if event.delta:
                raw = -1.0 * (event.delta / 120.0) * 4.0
                if 0 < raw < 1:
                    steps = 1
                elif -1 < raw < 0:
                    steps = -1
                else:
                    steps = int(raw)
                self._content_canvas.yview_scroll(steps, "units")
        except Exception:
            pass

    def _on_frame_configure(self, event):
        self._content_canvas.configure(
            scrollregion=self._content_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._content_canvas.itemconfig(self._content_window, width=event.width)

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = self._sidebar

        # Logo area
        logo_f = tk.Frame(sb, bg=COLORS["bg_sidebar"], height=70)
        logo_f.pack(fill="x")
        logo_f.pack_propagate(False)
        tk.Label(logo_f, text="⬡ CommitMaster", font=FONTS["heading_sm"],
                 fg=COLORS["accent"], bg=COLORS["bg_sidebar"]).pack(
            side="left", padx=16, pady=20)

        # Separator
        tk.Frame(sb, height=1, bg=COLORS["border"]).pack(fill="x")

        # Avatar + name
        av_f = tk.Frame(sb, bg=COLORS["bg_sidebar"], pady=16)
        av_f.pack(fill="x", padx=16)
        color = self.user.get("avatar_color", AVATAR_COLORS[0])
        initials = self._get_initials()
        av = tk.Label(av_f, text=initials, font=FONTS["heading_sm"],
                      bg=color, fg="white", width=4, height=2)
        av.pack(anchor="w")
        tk.Label(av_f, text=self.user.get("full_name") or self.user["username"],
                 font=FONTS["label_bold"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_sidebar"], wraplength=160).pack(anchor="w", pady=(4, 0))
        role_tag = "● Admin" if self.user["role"] == "admin" else "● User"
        role_color = COLORS["admin"] if self.user["role"] == "admin" else COLORS["success"]
        tk.Label(av_f, text=role_tag, font=FONTS["caption"],
                 fg=role_color, bg=COLORS["bg_sidebar"]).pack(anchor="w")

        tk.Frame(sb, height=1, bg=COLORS["border"]).pack(fill="x", pady=(8, 4))

        # Nav items
        nav_items = [
            ("📊", "Overview",        "overview"),
            ("🖥️", "Git Desktop",     "git_desktop"),
            ("📁", "Watched Repos",   "watched_repos"),
            ("📝", "My Commits",      "commits"),
            ("🐙", "GitHub Accounts", "github_accounts"),
            ("🎨", "Customize",       "customize"),
            ("⚙️",  "Settings",       "settings"),
            ("👤", "My Profile",      "profile"),
        ]
        if self.user["role"] == "admin":
            nav_items.append(("🛡", "Admin Portal", "admin"))

        self._nav_buttons = {}
        for icon, label, key in nav_items:
            btn = self._make_nav_btn(sb, icon, label, key)
            self._nav_buttons[key] = btn

        # Spacer + logout
        tk.Frame(sb, bg=COLORS["bg_sidebar"]).pack(fill="both", expand=True)
        tk.Frame(sb, height=1, bg=COLORS["border"]).pack(fill="x")
        logout_btn = tk.Button(sb, text="  ⏻  Sign Out",
                               font=FONTS["label"], fg=COLORS["text_secondary"],
                               bg=COLORS["bg_sidebar"], relief="flat", bd=0,
                               cursor="hand2", anchor="w",
                               command=self._do_logout, padx=16, pady=12)
        logout_btn.pack(fill="x")
        self._add_hover(logout_btn, COLORS["bg_medium"], COLORS["bg_sidebar"])

    def _make_nav_btn(self, parent, icon: str, label: str, key: str) -> tk.Button:
        btn = tk.Button(parent, text=f"  {icon}  {label}",
                        font=FONTS["label"], fg=COLORS["text_secondary"],
                        bg=COLORS["bg_sidebar"], relief="flat", bd=0,
                        cursor="hand2", anchor="w", padx=16, pady=10,
                        command=lambda k=key: self._nav_to(k))
        btn.pack(fill="x")
        return btn

    def _rebuild_ui(self, nav_to: str = "customize"):
        """Tear down and recreate UI with new theme/tokens."""
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=COLORS["bg_darkest"])
        self._build_layout()
        self._nav_to(nav_to)

    def _nav_to(self, key: str):
        if key == "admin" and self.on_admin:
            self.on_admin()
            return
        # Update active state
        for k, btn in self._nav_buttons.items():
            if k == key:
                btn.config(bg=COLORS["bg_medium"], fg=COLORS["accent"])
            else:
                btn.config(bg=COLORS["bg_sidebar"], fg=COLORS["text_secondary"])
        self._active_nav = key
        # Clear content
        for w in self._content_frame.winfo_children():
            w.destroy()
        # Render page
        pages = {
            "overview":        self._page_overview,
            "git_desktop":     self._page_git_desktop,
            "watched_repos":   self._page_watched_repos,
            "commits":         self._page_commits,
            "github_accounts": self._page_github_accounts,
            "customize":       self._page_customize,
            "settings":        self._page_settings,
            "profile":         self._page_profile,
        }
        if key in pages:
            pages[key]()
        self._content_canvas.yview_moveto(0)
        self.root.update_idletasks()
        self._content_canvas.configure(scrollregion=self._content_canvas.bbox("all"))

    def _add_hover(self, widget, hover_bg, normal_bg):
        widget.bind("<Enter>", lambda e: widget.config(bg=hover_bg))
        widget.bind("<Leave>", lambda e: widget.config(bg=normal_bg))

    # ── Header ─────────────────────────────────────────────────────────────────

    def _build_header(self):
        header = tk.Frame(self._main, bg=COLORS["bg_dark"], height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Frame(self._main, height=1, bg=COLORS["border"]).pack(fill="x")
        self._header_title = tk.Label(header, text="Overview",
                                      font=FONTS["heading_md"],
                                      fg=COLORS["text_primary"], bg=COLORS["bg_dark"])
        self._header_title.pack(side="left", padx=24, pady=12)
        # Right side: version badge
        tk.Label(header, text="v2.0", font=FONTS["caption"],
                 fg=COLORS["text_muted"], bg=COLORS["bg_dark"]).pack(
            side="right", padx=16)

    def _set_header(self, title: str):
        self._header_title.config(text=title)

    # ── Helper widgets ─────────────────────────────────────────────────────────

    def _card(self, parent, **kw) -> tk.Frame:
        f = tk.Frame(parent, bg=COLORS["bg_card"],
                     highlightbackground=COLORS["border"],
                     highlightthickness=1, **kw)
        return f

    def _section_title(self, parent, text: str, pady=(0, 12)) -> tk.Label:
        lbl = tk.Label(parent, text=text, font=FONTS["heading_sm"],
                       fg=COLORS["text_secondary"], bg=COLORS["bg_dark"])
        lbl.pack(anchor="w", pady=pady)
        return lbl

    def _stat_card(self, parent, title: str, value: str, color: str, icon: str):
        card = self._card(parent)
        card.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        inner = tk.Frame(card, bg=COLORS["bg_card"], padx=18, pady=16)
        inner.pack(fill="both", expand=True)
        tk.Label(inner, text=icon, font=("Segoe UI Emoji", 20),
                 fg=color, bg=COLORS["bg_card"]).pack(anchor="w")
        tk.Label(inner, text=value, font=FONTS["heading_lg"],
                 fg=color, bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 0))
        tk.Label(inner, text=title, font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w")

    # ── Pages ──────────────────────────────────────────────────────────────────

    def _page_overview(self):
        self._set_header("Overview")
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        # Greeting
        name = self.user.get("full_name") or self.user["username"]
        tk.Label(pad, text=f"Welcome back, {name}! 👋",
                 font=FONTS["heading_lg"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad, text="Here's your coding activity at a glance.",
                 font=FONTS["body_md"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 20))

        # Stats row
        activity = db.get_activity_log(self.user["id"], limit=1000)
        usage = db.get_usage_stats(self.user["id"], days=30)
        total_commits = len(activity)
        total_sessions = sum(r["sessions"] for r in usage)
        active_days = len(usage)
        repos = len(set(r["repo_name"] for r in activity))

        stats_row = tk.Frame(pad, bg=COLORS["bg_dark"])
        stats_row.pack(fill="x", pady=(0, 20))
        self._stat_card(stats_row, "Total Commits", str(total_commits),
                        COLORS["success"], "📝")
        self._stat_card(stats_row, "Sessions (30d)", str(total_sessions),
                        COLORS["info"], "🖥")
        self._stat_card(stats_row, "Active Days", str(active_days),
                        COLORS["warning"], "📅")
        self._stat_card(stats_row, "Repositories", str(repos),
                        COLORS["admin"], "📁")

        # ── Local Repository Scanner & AI Push Preview ─────────────────────────
        self._build_repo_scanner_card(pad)

        # Usage chart
        self._section_title(pad, "COMMIT ACTIVITY — LAST 30 DAYS", (16, 8))
        self._draw_chart(pad, usage, width=700, height=160)

        # Recent commits
        self._section_title(pad, "RECENT COMMITS", (20, 8))
        if not activity:
            tk.Label(pad, text="No commits recorded yet. Start coding!",
                     font=FONTS["body_md"], fg=COLORS["text_muted"],
                     bg=COLORS["bg_dark"]).pack(anchor="w")
        else:
            for entry in activity[:8]:
                self._commit_row(pad, entry)

    def _build_repo_scanner_card(self, parent):
        card = self._card(parent, padx=18, pady=16)
        card.pack(fill="x", pady=(0, 20))

        cfg = load_config()

        # ── Card Header ──────────────────────────────────────────────────────────
        hdr_row = tk.Frame(card, bg=COLORS["bg_card"])
        hdr_row.pack(fill="x", pady=(0, 4))

        tk.Label(
            hdr_row, text="⚡ Local Repository Scanner & AI Push Preview",
            font=FONTS["heading_sm"], fg=COLORS["accent"], bg=COLORS["bg_card"]
        ).pack(side="left")

        ai_url = cfg.get("ai", {}).get("base_url", "http://localhost:1234/v1")
        ai_model = cfg.get("ai", {}).get("model") or ai_messages.detect_model(cfg)
        status_text = f"⚡ Local AI: {ai_model or 'Online'} ({ai_url})" if ai_model else f"⚡ Local AI Server: {ai_url}"
        tk.Label(
            hdr_row, text=status_text, font=FONTS["caption"],
            fg=COLORS["accent"] if ai_model else COLORS["text_muted"], bg=COLORS["bg_card"]
        ).pack(side="right")

        tk.Label(
            card,
            text="Scan your local repository for uncommitted files, inspect AI-generated commit comments, edit them as you see fit, and approve to push to GitHub.",
            font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 12))

        # ── Repository Selection Row ─────────────────────────────────────────────
        watched_repos = db.get_watched_repos(self.user["id"])
        available_repos = []
        for wr in watched_repos:
            lp = wr.get("local_path", "").strip()
            if lp and os.path.isdir(lp) and commit_engine.is_git_repo(lp):
                if lp not in available_repos:
                    available_repos.append(lp)

        if not self._gd_selected_repo or self._gd_selected_repo not in available_repos:
            self._gd_selected_repo = available_repos[0] if available_repos else None

        sel_bar = tk.Frame(card, bg=COLORS["bg_card"])
        sel_bar.pack(fill="x", pady=(0, 10))

        tk.Label(sel_bar, text="Repository:", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(side="left", padx=(0, 8))

        repo_options = [f"📁 {commit_engine.repo_name(r)} ({r})" for r in available_repos] or ["(No local git repos added)"]
        repo_map = {f"📁 {commit_engine.repo_name(r)} ({r})": r for r in available_repos}

        curr_label = repo_options[0]
        for opt, path in repo_map.items():
            if path == self._gd_selected_repo:
                curr_label = opt
                break

        repo_var = tk.StringVar(value=curr_label)

        content_container = tk.Frame(card, bg=COLORS["bg_card"])
        content_container.pack(fill="x")

        def on_repo_changed(val):
            target = repo_map.get(val)
            if target:
                self._gd_selected_repo = target
                render_scanner_content()

        repo_menu = tk.OptionMenu(sel_bar, repo_var, *repo_options, command=on_repo_changed)
        repo_menu.config(font=FONTS["body_sm"], bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
                         activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
                         relief="flat", bd=0, highlightthickness=0)
        repo_menu["menu"].config(bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body_sm"])
        repo_menu.pack(side="left", padx=(0, 10))

        def add_local_folder():
            d = filedialog.askdirectory(title="Select Local Git Repository Folder", parent=self.root)
            if d:
                norm = os.path.normpath(d)
                if commit_engine.is_git_repo(norm):
                    db.add_watched_repo(
                        user_id=self.user["id"],
                        repo_name=commit_engine.repo_name(norm),
                        local_path=norm,
                        is_active_watch=1,
                    )
                    self._gd_selected_repo = norm
                    self._nav_to("overview")
                else:
                    messagebox.showerror("Not a Git Repository", f"'{norm}' does not contain a .git directory.", parent=self.root)

        add_btn = tk.Button(
            sel_bar, text="＋ Add Local Repo", font=FONTS["caption"],
            fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
            command=add_local_folder
        )
        add_btn.pack(side="left", padx=(0, 8))
        self._add_hover(add_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        scan_btn = tk.Button(
            sel_bar, text="⚡ Scan for Changes Now", font=FONTS["label_bold"],
            fg="white", bg=COLORS["accent"],
            activebackground=COLORS["accent_hover"], activeforeground="white",
            relief="flat", bd=0, cursor="hand2", padx=12, pady=4,
            command=lambda: render_scanner_content()
        )
        scan_btn.pack(side="left", padx=(0, 12))
        self._add_hover(scan_btn, COLORS["accent_hover"], COLORS["accent"])

        branch_lbl = tk.Label(sel_bar, text="", font=FONTS["label_bold"], bg=COLORS["bg_card"])
        branch_lbl.pack(side="left", padx=(0, 8))

        account_lbl = tk.Label(sel_bar, text="", font=FONTS["caption"], bg=COLORS["bg_card"])
        account_lbl.pack(side="left")

        # ── Renderer for Changes & AI Preview ─────────────────────────────────
        def render_scanner_content():
            for w in content_container.winfo_children():
                w.destroy()

            if not self._gd_selected_repo or not os.path.isdir(self._gd_selected_repo):
                empty_box = tk.Frame(content_container, bg=COLORS["bg_medium"], padx=16, pady=20)
                empty_box.pack(fill="x")
                tk.Label(empty_box, text="📂 No Local Repository Selected",
                         font=FONTS["label_bold"], fg=COLORS["text_primary"], bg=COLORS["bg_medium"]).pack(anchor="w")
                tk.Label(empty_box,
                         text="Click '＋ Add Local Repo' above to choose a Git repository folder on your PC.",
                         font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_medium"]).pack(anchor="w", pady=(4, 10))
                tk.Button(empty_box, text="📁 Choose Local Repository Folder", font=FONTS["label_bold"],
                          fg="white", bg=COLORS["accent"], relief="flat", bd=0, padx=14, pady=6,
                          command=add_local_folder).pack(anchor="w")
                branch_lbl.config(text="")
                account_lbl.config(text="")
                return

            branch = commit_engine.current_branch(self._gd_selected_repo)
            branch_lbl.config(text=f"🌿 {branch}", fg=COLORS["accent"])
            acc = db.get_repo_account(self.user["id"], self._gd_selected_repo)
            if acc:
                account_lbl.config(text=f"🐙 @{acc['github_username']}", fg=COLORS["info"])
            else:
                account_lbl.config(text="🐙 Default Git Push", fg=COLORS["text_muted"])

            # Scan for uncommitted changes
            changes = commit_engine.uncommitted_changes(self._gd_selected_repo)
            self._gd_changes = changes

            sensitive_patterns = cfg.get("sensitive_patterns", [])
            for status, path in changes:
                if path not in self._gd_staged_vars:
                    is_sens = any(s in path.lower() for s in sensitive_patterns)
                    self._gd_staged_vars[path] = tk.BooleanVar(value=not is_sens)

            if not changes:
                clean_f = tk.Frame(content_container, bg=COLORS["bg_card"], padx=14, pady=16,
                                   highlightthickness=1, highlightbackground=COLORS["border"])
                clean_f.pack(fill="x")
                tk.Label(clean_f, text=f"✔ Working Tree Clean ({commit_engine.repo_name(self._gd_selected_repo)})",
                         font=FONTS["label_bold"], fg=COLORS["success"], bg=COLORS["bg_card"]).pack(anchor="w")
                tk.Label(clean_f,
                         text="No uncommitted changes detected. All files are up to date and clean.\n"
                              "Make edits to any file in your project, then click '⚡ Scan for Changes Now' to generate comments and push.",
                         font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 8))
                btn_row = tk.Frame(clean_f, bg=COLORS["bg_card"])
                btn_row.pack(anchor="w")
                tk.Button(btn_row, text="🔄 Check Again", font=FONTS["caption"],
                          fg=COLORS["text_primary"], bg=COLORS["bg_medium"], relief="flat", bd=0, padx=10, pady=4,
                          command=render_scanner_content).pack(side="left", padx=(0, 8))
                tk.Button(btn_row, text="🖥️ Open in Git Desktop", font=FONTS["caption"],
                          fg=COLORS["accent"], bg=COLORS["bg_medium"], relief="flat", bd=0, padx=10, pady=4,
                          command=lambda: self._nav_to("git_desktop")).pack(side="left")
                return

            # ── Uncommitted Changes Display ───────────────────────────────────
            chg_hdr = tk.Frame(content_container, bg=COLORS["bg_card"])
            chg_hdr.pack(fill="x", pady=(4, 6))

            tk.Label(
                chg_hdr, text=f"Detected Changes ({len(changes)} files in {commit_engine.repo_name(self._gd_selected_repo)}):",
                font=FONTS["label_bold"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]
            ).pack(side="left")

            def toggle_all():
                all_staged = all(self._gd_staged_vars[p].get() for _, p in changes if p in self._gd_staged_vars)
                for _, p in changes:
                    if p in self._gd_staged_vars:
                        self._gd_staged_vars[p].set(not all_staged)

            tgl_btn = tk.Button(chg_hdr, text="Toggle All", font=FONTS["caption"],
                                fg=COLORS["accent"], bg=COLORS["bg_card"], relief="flat", bd=0,
                                cursor="hand2", command=toggle_all)
            tgl_btn.pack(side="right")

            # File list frame
            files_box = tk.Frame(content_container, bg=COLORS["bg_input"], padx=8, pady=6,
                                 highlightthickness=1, highlightbackground=COLORS["border"])
            files_box.pack(fill="x", pady=(0, 10))

            status_colors = {"M": ("Modified", "#f0883e"), "A": ("Added", "#3fb950"), "D": ("Deleted", "#f85149"), "??": ("Untracked", "#58a6ff")}
            for st, path in changes[:12]:
                row = tk.Frame(files_box, bg=COLORS["bg_input"])
                row.pack(fill="x", pady=1)

                var = self._gd_staged_vars.get(path)
                if not var:
                    var = tk.BooleanVar(value=True)
                    self._gd_staged_vars[path] = var
                cb = tk.Checkbutton(row, variable=var, bg=COLORS["bg_input"], selectcolor=COLORS["bg_card"],
                                    activebackground=COLORS["bg_input"])
                cb.pack(side="left")

                label_txt, color_hex = status_colors.get(st, (st, "#8b949e"))
                tk.Label(row, text=f"[{st}]", font=FONTS["mono_sm"], fg=color_hex, bg=COLORS["bg_input"]).pack(side="left", padx=(0, 6))
                tk.Label(row, text=path, font=FONTS["body_sm"], fg=COLORS["text_primary"], bg=COLORS["bg_input"]).pack(side="left")

            if len(changes) > 12:
                tk.Label(files_box, text=f"... and {len(changes) - 12} more files (see Git Desktop for complete list)",
                         font=FONTS["caption"], fg=COLORS["text_muted"], bg=COLORS["bg_input"]).pack(anchor="w", pady=(4, 0))

            # ── AI Commentary & Edit Section ──────────────────────────────────
            ai_box = tk.Frame(content_container, bg=COLORS["bg_card"], padx=14, pady=12,
                              highlightthickness=1, highlightbackground=COLORS["accent"])
            ai_box.pack(fill="x", pady=(0, 10))

            ai_top = tk.Frame(ai_box, bg=COLORS["bg_card"])
            ai_top.pack(fill="x", pady=(0, 6))

            status_lbl = tk.Label(ai_top, text="💡 AI comments ready to generate or edit manually",
                                  font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"])

            def trigger_ai_gen():
                selected_files = [p for p, v in self._gd_staged_vars.items() if v.get()]
                if not selected_files:
                    selected_files = [p for _, p in changes]
                status_lbl.config(text="⏳ Native Local PC AI is reading diffs and crafting comments...", fg=COLORS["info"])
                self.root.update_idletasks()

                def do_call():
                    res = ai_messages.generate_file_comments(cfg, self._gd_selected_repo, selected_files)
                    def update_ui():
                        self._gd_headline_var.set(res.get("headline", ""))
                        desc_text.delete("1.0", "end")
                        desc_text.insert("end", res.get("description", ""))
                        status_lbl.config(text="✔ AI comments generated! You can edit them below before approving.", fg=COLORS["success"])
                    self.root.after(0, update_ui)

                threading.Thread(target=do_call, daemon=True).start()

            ai_gen_btn = tk.Button(
                ai_top, text="✨ Write AI Comments for Each File (Native Local AI)",
                font=FONTS["label_bold"], fg="white", bg=COLORS["accent"],
                activebackground=COLORS["accent_hover"], activeforeground="white",
                relief="flat", bd=0, cursor="hand2", padx=12, pady=5,
                command=trigger_ai_gen
            )
            ai_gen_btn.pack(side="left", padx=(0, 10))
            self._add_hover(ai_gen_btn, COLORS["accent_hover"], COLORS["accent"])

            status_lbl.pack(side="left")

            # Commit headline
            tk.Label(ai_box, text="Commit Headline (Editable):", font=FONTS["label_bold"],
                     fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 2))

            if not self._gd_headline_var.get():
                self._gd_headline_var.set(f"refactor: update {len(changes)} files in {commit_engine.repo_name(self._gd_selected_repo)}")

            headline_ent = tk.Entry(
                ai_box, textvariable=self._gd_headline_var, font=FONTS["body_md"],
                bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                highlightthickness=1, highlightbackground=COLORS["border"],
            )
            headline_ent.pack(fill="x", pady=(0, 8), ipady=4)

            # Detailed comments
            tk.Label(ai_box, text="Commit Description & Per-File Commentary (100% Editable):", font=FONTS["caption"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 2))

            desc_text = tk.Text(
                ai_box, font=FONTS["body_sm"], height=4, bg=COLORS["bg_input"],
                fg=COLORS["text_primary"], relief="flat", padx=8, pady=6,
                highlightthickness=1, highlightbackground=COLORS["border"],
            )
            desc_text.pack(fill="x", pady=(0, 10))

            # Initial description if empty
            initial_desc = "\n".join(f"- {p}: Update file logic" for _, p in changes[:8])
            desc_text.insert("end", initial_desc)

            # ── Action Buttons Row ────────────────────────────────────────────
            act_row = tk.Frame(ai_box, bg=COLORS["bg_card"])
            act_row.pack(fill="x")

            ask_cb = tk.Checkbutton(
                act_row, text="Ask me before git pushing", variable=self._gd_ask_push_var,
                font=FONTS["body_sm"], fg=COLORS["text_primary"], bg=COLORS["bg_card"],
                selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"],
                activeforeground=COLORS["text_primary"],
            )
            ask_cb.pack(side="left", padx=(0, 12))

            push_res_lbl = tk.Label(ai_box, text="", font=FONTS["label_bold"], bg=COLORS["bg_card"])
            push_res_lbl.pack(anchor="w", pady=(6, 0))

            def execute_approve_and_push(push_remote: bool):
                staged = [p for p, v in self._gd_staged_vars.items() if v.get()]
                if not staged:
                    messagebox.showwarning("No Files Selected", "Please check at least one file to include in the commit.", parent=self.root)
                    return

                headline = self._gd_headline_var.get().strip() or "chore: update repository files"
                desc = desc_text.get("1.0", "end").strip()
                full_msg = f"{headline}\n\n{desc}" if desc else headline

                acc = db.get_repo_account(self.user["id"], self._gd_selected_repo)
                repo_name = commit_engine.repo_name(self._gd_selected_repo)
                cur_branch = commit_engine.current_branch(self._gd_selected_repo)

                if push_remote and self._gd_ask_push_var.get():
                    unpushed = commit_engine.get_unpushed_commits(self._gd_selected_repo)
                    confirmed = ui.ask_push_confirmation(repo_name, cur_branch, acc, unpushed)
                    if not confirmed:
                        push_res_lbl.config(text="ℹ Push cancelled by user. Changes remain uncommitted.", fg=COLORS["warning"])
                        return

                push_res_lbl.config(text="⏳ Committing and pushing to GitHub...", fg=COLORS["info"])
                self.root.update_idletasks()

                def do_commit_and_push_worker():
                    try:
                        summary = commit_engine.stage_and_commit(self._gd_selected_repo, staged, full_msg)
                        commit_hash = summary.split()[0] if summary else ""
                        db.log_commit(
                            user_id=self.user["id"],
                            repo_path=self._gd_selected_repo,
                            commit_msg=headline,
                            files_count=len(staged),
                            commit_hash=commit_hash,
                        )

                        if push_remote:
                            if acc:
                                ok, pmsg = commit_engine.push_repo_with_account(self._gd_selected_repo, acc)
                            else:
                                accounts = db.get_github_accounts(self.user["id"])
                                if accounts:
                                    ok, pmsg = commit_engine.push_repo_with_account(self._gd_selected_repo, accounts[0])
                                else:
                                    ok, pmsg = commit_engine.push(self._gd_selected_repo)

                            def on_push_done():
                                if ok:
                                    push_res_lbl.config(text=f"🎉 Successfully committed and pushed to GitHub! ({commit_hash})", fg=COLORS["success"])
                                    messagebox.showinfo("Push Succeeded", f"✔ Successfully committed and pushed to GitHub!\n\nHeadline: {headline}\nFiles: {len(staged)} files\nSummary: {summary}", parent=self.root)
                                    render_scanner_content()
                                else:
                                    push_res_lbl.config(text=f"❌ Push error: {pmsg}", fg=COLORS["danger"])
                                    messagebox.showerror("Push Error", f"Commit succeeded locally, but git push failed:\n\n{pmsg}", parent=self.root)
                            self.root.after(0, on_push_done)
                        else:
                            def on_commit_done():
                                push_res_lbl.config(text=f"✔ Committed locally: {summary}", fg=COLORS["success"])
                                messagebox.showinfo("Committed Locally", f"Commit saved locally:\n{summary}", parent=self.root)
                                render_scanner_content()
                            self.root.after(0, on_commit_done)

                    except Exception as err:
                        def on_err():
                            push_res_lbl.config(text=f"❌ Commit failed: {err}", fg=COLORS["danger"])
                            messagebox.showerror("Commit Failed", f"Could not create commit:\n\n{err}", parent=self.root)
                        self.root.after(0, on_err)

                threading.Thread(target=do_commit_and_push_worker, daemon=True).start()

            # Push button
            push_btn = tk.Button(
                act_row, text="🚀 Approve & Git Push to GitHub", font=FONTS["label_bold"],
                fg="white", bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                activeforeground="white", relief="flat", bd=0, cursor="hand2", padx=16, pady=7,
                command=lambda: execute_approve_and_push(push_remote=True)
            )
            push_btn.pack(side="left", padx=(0, 8))
            self._add_hover(push_btn, COLORS["accent_hover"], COLORS["accent"])

            # Commit locally button
            commit_btn = tk.Button(
                act_row, text="💾 Commit Locally Only", font=FONTS["label_bold"],
                fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
                relief="flat", bd=0, cursor="hand2", padx=12, pady=7,
                command=lambda: execute_approve_and_push(push_remote=False)
            )
            commit_btn.pack(side="left", padx=(0, 8))
            self._add_hover(commit_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

            # Open in Git Desktop button
            open_gd_btn = tk.Button(
                act_row, text="🖥️ Open Full Diff in Git Desktop", font=FONTS["label"],
                fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                activebackground=COLORS["bg_medium"], activeforeground=COLORS["text_primary"],
                relief="flat", bd=0, cursor="hand2", padx=10, pady=7,
                command=lambda: self._nav_to("git_desktop")
            )
            open_gd_btn.pack(side="left")
            self._add_hover(open_gd_btn, COLORS["bg_medium"], COLORS["bg_card"])

        render_scanner_content()

    def _draw_chart(self, parent, usage_data: list, width=700, height=160):
        """Draw a simple bar chart for commit activity."""
        canvas = tk.Canvas(parent, width=width, height=height,
                           bg=COLORS["bg_card"], highlightthickness=0)
        canvas.pack(anchor="w", pady=(0, 8))

        if not usage_data:
            canvas.create_text(width // 2, height // 2,
                                text="No data yet", fill=COLORS["text_muted"],
                                font=FONTS["body_sm"])
            return

        max_commits = max((r.get("commits_made", 0) for r in usage_data), default=1) or 1
        n = len(usage_data)
        bar_w = max(4, (width - 40) // max(n, 1) - 2)
        pad_l, pad_b = 20, 30

        for i, row in enumerate(usage_data):
            val = row.get("commits_made", 0)
            x0 = pad_l + i * ((width - 40) // max(n, 1))
            bar_h = int((val / max_commits) * (height - pad_b - 10))
            y1 = height - pad_b
            y0 = y1 - bar_h
            color = COLORS["accent"] if val > 0 else COLORS["border"]
            canvas.create_rectangle(x0, y0, x0 + bar_w, y1, fill=color, outline="")
            # Day label (abbreviated)
            if n <= 14 or i % 3 == 0:
                date_str = row["date"][5:]  # MM-DD
                canvas.create_text(x0 + bar_w // 2, height - 12,
                                   text=date_str, fill=COLORS["text_muted"],
                                   font=FONTS["caption"], angle=0)

    def _commit_row(self, parent, entry: dict):
        row = tk.Frame(parent, bg=COLORS["bg_card"],
                       highlightbackground=COLORS["border"],
                       highlightthickness=1)
        row.pack(fill="x", pady=3)
        inner = tk.Frame(row, bg=COLORS["bg_card"], padx=14, pady=10)
        inner.pack(fill="x")
        # Left: repo badge
        badge = tk.Label(inner, text=entry["repo_name"][:20],
                         font=FONTS["mono_sm"], fg=COLORS["accent"],
                         bg=COLORS["bg_medium"], padx=6, pady=2)
        badge.pack(side="left")
        # Middle: message
        msg = entry["commit_msg"][:80] + ("…" if len(entry["commit_msg"]) > 80 else "")
        tk.Label(inner, text=msg, font=FONTS["body_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"],
                 anchor="w").pack(side="left", padx=10, fill="x", expand=True)
        # Right: date
        date_str = entry["committed_at"][:16]
        tk.Label(inner, text=date_str, font=FONTS["caption"],
                 fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(side="right")

    def _page_commits(self):
        self._set_header("My Commits")
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Commit History", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad, text="All commits made through CommitMaster.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))

        activity = db.get_activity_log(self.user["id"], limit=500)
        if not activity:
            tk.Label(pad, text="No commits recorded yet.",
                     font=FONTS["body_md"], fg=COLORS["text_muted"],
                     bg=COLORS["bg_dark"]).pack(anchor="w", pady=20)
            return

        # Table header
        hdr = tk.Frame(pad, bg=COLORS["bg_medium"])
        hdr.pack(fill="x")
        for col, width in [("Repository", 18), ("Commit Message", 50), ("Files", 8), ("Date", 16)]:
            tk.Label(hdr, text=col, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                     width=width, anchor="w", padx=8, pady=6).pack(side="left")

        for entry in activity:
            self._commit_table_row(pad, entry)

    def _commit_table_row(self, parent, entry: dict):
        row = tk.Frame(parent, bg=COLORS["bg_card"],
                       highlightbackground=COLORS["border"],
                       highlightthickness=0)
        row.pack(fill="x")
        tk.Frame(parent, height=1, bg=COLORS["border"]).pack(fill="x")

        def on_enter(e): row.config(bg=COLORS["bg_card_hover"])
        def on_leave(e): row.config(bg=COLORS["bg_card"])
        row.bind("<Enter>", on_enter)
        row.bind("<Leave>", on_leave)

        fields = [
            (entry["repo_name"][:20], 18, COLORS["accent"]),
            (entry["commit_msg"][:50], 50, COLORS["text_primary"]),
            (str(entry.get("files_count", 0)), 8, COLORS["text_secondary"]),
            (entry["committed_at"][:16], 16, COLORS["text_muted"]),
        ]
        for text, width, color in fields:
            tk.Label(row, text=text, font=FONTS["body_sm"],
                     fg=color, bg=COLORS["bg_card"],
                     width=width, anchor="w", padx=8, pady=8).pack(side="left")

    def _page_settings(self):
        self._set_header("Settings")
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        prefs = db.get_preferences(self.user["id"]) or {}
        watched_raw = prefs.get("watched_apps", '["Code.exe","Cursor.exe"]')
        try:
            watched = json.loads(watched_raw)
        except Exception:
            watched = []
        dirs_raw = prefs.get("projects_dirs", "[]")
        try:
            proj_dirs = json.loads(dirs_raw)
        except Exception:
            proj_dirs = []

        tk.Label(pad, text="CommitMaster Settings", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad, text="Your personal preferences are saved per-account.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))

        # ── Session settings card ─────────────────────────────────────────────
        card = self._card(pad, padx=20, pady=16)
        card.pack(fill="x", pady=(0, 12))
        tk.Label(card, text="Session Monitoring", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")

        self._auto_commit_var = tk.BooleanVar(value=bool(prefs.get("auto_commit", 0)))
        self._skip_sensitive_var = tk.BooleanVar(value=bool(prefs.get("skip_sensitive", 1)))
        self._notif_var = tk.BooleanVar(value=bool(prefs.get("notifications", 1)))
        self._ask_push_var = tk.BooleanVar(value=bool(prefs.get("ask_before_push", 1)))

        for text, var in [
            ("Auto-commit without preview", self._auto_commit_var),
            ("Skip sensitive files (.env, .pem, etc.)", self._skip_sensitive_var),
            ("Show desktop notifications", self._notif_var),
            ("Ask for confirmation before pushing to GitHub", self._ask_push_var),
        ]:
            cb = tk.Checkbutton(card, text=text, variable=var,
                                font=FONTS["body_md"], fg=COLORS["text_primary"],
                                bg=COLORS["bg_card"], selectcolor=COLORS["bg_input"],
                                activebackground=COLORS["bg_card"],
                                activeforeground=COLORS["text_primary"])
            cb.pack(anchor="w", pady=4)

        # Grace period
        gf = tk.Frame(card, bg=COLORS["bg_card"])
        gf.pack(anchor="w", pady=(8, 0))
        tk.Label(gf, text="Session end grace period (seconds): ",
                 font=FONTS["body_md"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(side="left")
        self._grace_var = tk.StringVar(value=str(prefs.get("session_end_grace", 120)))
        grace_e = tk.Entry(gf, textvariable=self._grace_var, width=6,
                           font=FONTS["body_md"], bg=COLORS["bg_input"],
                           fg=COLORS["text_primary"], relief="flat",
                           highlightthickness=1, highlightbackground=COLORS["border"])
        grace_e.pack(side="left", ipady=4)

        # ── AI settings card ──────────────────────────────────────────────────
        card2 = self._card(pad, padx=20, pady=16)
        card2.pack(fill="x", pady=(0, 12))
        tk.Label(card2, text="AI / LM Studio", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")

        url_f = tk.Frame(card2, bg=COLORS["bg_card"])
        url_f.pack(fill="x", pady=(8, 0))
        tk.Label(url_f, text="Server URL:", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=14,
                 anchor="w").pack(side="left")
        self._ai_url_var = tk.StringVar(
            value=prefs.get("ai_base_url", "http://localhost:1234/v1"))
        tk.Entry(url_f, textvariable=self._ai_url_var, font=FONTS["mono"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                 highlightthickness=1, highlightbackground=COLORS["border"]).pack(
            side="left", fill="x", expand=True, ipady=4)

        model_f = tk.Frame(card2, bg=COLORS["bg_card"])
        model_f.pack(fill="x", pady=(8, 0))
        tk.Label(model_f, text="Model name:", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=14,
                 anchor="w").pack(side="left")
        self._ai_model_var = tk.StringVar(value=prefs.get("ai_model", ""))
        tk.Entry(model_f, textvariable=self._ai_model_var, font=FONTS["mono"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                 highlightthickness=1, highlightbackground=COLORS["border"]).pack(
            side="left", fill="x", expand=True, ipady=4)

        # ── Project folders card ──────────────────────────────────────────────
        card3 = self._card(pad, padx=20, pady=16)
        card3.pack(fill="x", pady=(0, 12))
        tk.Label(card3, text="Project Folders", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")

        self._dirs_listbox = tk.Listbox(card3, font=FONTS["mono"],
                                        bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                                        selectbackground=COLORS["accent"],
                                        relief="flat", height=4, bd=0)
        for d in proj_dirs:
            self._dirs_listbox.insert("end", d)
        self._dirs_listbox.pack(fill="x", pady=(8, 0))

        dirs_btns = tk.Frame(card3, bg=COLORS["bg_card"])
        dirs_btns.pack(anchor="w", pady=(6, 0))
        self._make_small_btn(dirs_btns, "＋ Add Folder",
                             self._add_dir).pack(side="left", padx=(0, 6))
        self._make_small_btn(dirs_btns, "✕ Remove",
                             self._remove_dir).pack(side="left")

        # ── Save button ───────────────────────────────────────────────────────
        save_btn = tk.Button(pad, text="  💾  Save Settings",
                             font=FONTS["heading_sm"], fg="white",
                             bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                             activeforeground="white", relief="flat", bd=0,
                             cursor="hand2", padx=20, pady=10,
                             command=self._save_settings)
        save_btn.pack(anchor="w", pady=(8, 0))
        self._add_hover(save_btn, COLORS["accent_hover"], COLORS["accent"])

    def _make_small_btn(self, parent, text: str, cmd) -> tk.Button:
        btn = tk.Button(parent, text=text, font=FONTS["label"],
                        fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                        activebackground=COLORS["bg_card_hover"],
                        activeforeground=COLORS["text_primary"],
                        relief="flat", bd=0, cursor="hand2",
                        padx=10, pady=4, command=cmd)
        self._add_hover(btn, COLORS["bg_card_hover"], COLORS["bg_medium"])
        return btn

    def _add_dir(self):
        d = filedialog.askdirectory(title="Select Project Folder")
        if d:
            self._dirs_listbox.insert("end", d)

    def _remove_dir(self):
        sel = self._dirs_listbox.curselection()
        if sel:
            self._dirs_listbox.delete(sel[0])

    def _save_settings(self):
        dirs = list(self._dirs_listbox.get(0, "end"))
        db.update_preferences(
            self.user["id"],
            auto_commit=int(self._auto_commit_var.get()),
            skip_sensitive=int(self._skip_sensitive_var.get()),
            notifications=int(self._notif_var.get()),
            session_end_grace=int(self._grace_var.get() or 120),
            ai_base_url=self._ai_url_var.get(),
            ai_model=self._ai_model_var.get(),
            ask_before_push=int(self._ask_push_var.get()),
            projects_dirs=json.dumps(dirs),
        )
        messagebox.showinfo("Saved", "Settings saved successfully!", parent=self.root)

    def _page_profile(self):
        self._set_header("My Profile")
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Profile", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad, text="Manage your personal information.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))

        # Avatar selector row
        av_row = tk.Frame(pad, bg=COLORS["bg_dark"])
        av_row.pack(anchor="w", pady=(0, 16))
        self._selected_color = tk.StringVar(value=self.user.get("avatar_color", AVATAR_COLORS[0]))

        tk.Label(av_row, text="Avatar Color:", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(side="left")
        for color in AVATAR_COLORS:
            dot = tk.Label(av_row, text="  ", bg=color, width=3,
                           cursor="hand2",
                           highlightthickness=2,
                           highlightbackground=COLORS["border"])
            dot.pack(side="left", padx=4)
            dot.bind("<Button-1>", lambda e, c=color: self._selected_color.set(c))

        card = self._card(pad, padx=20, pady=16)
        card.pack(fill="x", pady=(0, 12))

        fields = [
            ("Full Name", self.user.get("full_name", ""), "full_name"),
            ("Email", self.user.get("email", ""), "email"),
        ]
        self._profile_vars = {}
        for label, default, key in fields:
            rf = tk.Frame(card, bg=COLORS["bg_card"])
            rf.pack(fill="x", pady=(0, 10))
            tk.Label(rf, text=label, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                     width=12, anchor="w").pack(side="left")
            var = tk.StringVar(value=default)
            self._profile_vars[key] = var
            e = tk.Entry(rf, textvariable=var, font=FONTS["body_md"],
                         bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                         relief="flat", highlightthickness=1,
                         highlightbackground=COLORS["border"])
            e.pack(side="left", fill="x", expand=True, ipady=6)

        # Bio
        bio_f = tk.Frame(card, bg=COLORS["bg_card"])
        bio_f.pack(fill="x", pady=(0, 10))
        tk.Label(bio_f, text="Bio", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                 width=12, anchor="w").pack(side="left", anchor="n")
        self._bio_text = tk.Text(bio_f, font=FONTS["body_md"],
                                 bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                                 relief="flat", height=3, bd=0,
                                 highlightthickness=1,
                                 highlightbackground=COLORS["border"])
        self._bio_text.insert("1.0", self.user.get("bio") or "")
        self._bio_text.pack(side="left", fill="x", expand=True)

        save_btn = tk.Button(pad, text="  💾  Save Profile",
                             font=FONTS["heading_sm"], fg="white",
                             bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                             activeforeground="white", relief="flat", bd=0,
                             cursor="hand2", padx=20, pady=10,
                             command=self._save_profile)
        save_btn.pack(anchor="w", pady=(0, 16))
        self._add_hover(save_btn, COLORS["accent_hover"], COLORS["accent"])

        # ── Change password ────────────────────────────────────────────────────
        card2 = self._card(pad, padx=20, pady=16)
        card2.pack(fill="x")
        tk.Label(card2, text="Change Password", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 10))

        self._pw_vars = {}
        for label, key, show in [
            ("New Password", "new_pw", "•"),
            ("Confirm New", "confirm_pw", "•"),
        ]:
            rf = tk.Frame(card2, bg=COLORS["bg_card"])
            rf.pack(fill="x", pady=(0, 8))
            tk.Label(rf, text=label, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                     width=14, anchor="w").pack(side="left")
            var = tk.StringVar()
            self._pw_vars[key] = var
            e = tk.Entry(rf, textvariable=var, font=FONTS["body_md"],
                         bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                         relief="flat", highlightthickness=1,
                         highlightbackground=COLORS["border"], show=show)
            e.pack(side="left", fill="x", expand=True, ipady=6)

        pw_btn = tk.Button(card2, text="  🔒  Change Password",
                           font=FONTS["label"], fg="white",
                           bg=COLORS["warning"], activebackground="#c4840e",
                           activeforeground="white", relief="flat", bd=0,
                           cursor="hand2", padx=14, pady=6,
                           command=self._change_password)
        pw_btn.pack(anchor="w", pady=(4, 0))

    def _save_profile(self):
        db.update_user(
            self.user["id"],
            full_name=self._profile_vars["full_name"].get(),
            email=self._profile_vars["email"].get(),
            bio=self._bio_text.get("1.0", "end-1c"),
            avatar_color=self._selected_color.get(),
        )
        messagebox.showinfo("Saved", "Profile updated successfully!", parent=self.root)

    def _change_password(self):
        new_pw = self._pw_vars["new_pw"].get()
        confirm = self._pw_vars["confirm_pw"].get()
        if not new_pw or not confirm:
            messagebox.showwarning("Error", "Please fill in both password fields.",
                                   parent=self.root)
            return
        if new_pw != confirm:
            messagebox.showwarning("Error", "Passwords do not match.", parent=self.root)
            return
        if len(new_pw) < 6:
            messagebox.showwarning("Error",
                                   "Password must be at least 6 characters.",
                                   parent=self.root)
            return
        db.change_password(self.user["id"], new_pw)
        messagebox.showinfo("Success", "Password changed successfully!", parent=self.root)
    # ── GitHub Accounts Page ──────────────────────────────────────────────────

    def _page_github_accounts(self):
        self._set_header("GitHub Accounts & Repositories")
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        # Header with Add Button
        top_f = tk.Frame(pad, bg=COLORS["bg_dark"])
        top_f.pack(fill="x", pady=(0, 16))

        titles_f = tk.Frame(top_f, bg=COLORS["bg_dark"])
        titles_f.pack(side="left", fill="x", expand=True)
        tk.Label(titles_f, text="Linked GitHub Accounts", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(titles_f,
                 text="Connect multiple GitHub accounts and choose which identity pushes to each repository.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 0))

        add_btn = tk.Button(top_f, text="  + Link GitHub Account  ", font=FONTS["heading_sm"],
                            fg="white", bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                            activeforeground="white", relief="flat", bd=0, cursor="hand2",
                            padx=14, pady=8, command=self._open_add_github_dialog)
        add_btn.pack(side="right", padx=(10, 0))
        self._add_hover(add_btn, COLORS["accent_hover"], COLORS["accent"])

        # Fetch accounts and repos
        accounts = db.get_github_accounts(self.user["id"])
        watched_repos = db.get_watched_repos(self.user["id"])
        repos = [r["local_path"] for r in watched_repos if r.get("local_path") and os.path.isdir(r["local_path"])]

        default_acc = db.get_default_github_account(self.user["id"])
        default_name = default_acc["account_name"] if default_acc else "None set"

        # Summary Row
        stats_row = tk.Frame(pad, bg=COLORS["bg_dark"])
        stats_row.pack(fill="x", pady=(0, 16))
        self._stat_card(stats_row, "Linked Accounts", str(len(accounts)), COLORS["accent"], "🐙")
        self._stat_card(stats_row, "Default Push Account", default_name, COLORS["info"], "★")
        self._stat_card(stats_row, "Authorized Repos", str(len(repos)), COLORS["warning"], "📁")

        # ── Section 1: Linked Accounts ───────────────────────────────────────
        self._section_title(pad, "Connected Accounts", pady=(8, 10))

        if not accounts:
            empty_card = self._card(pad, padx=24, pady=24)
            empty_card.pack(fill="x", pady=(0, 16))
            tk.Label(empty_card, text="🐙  No GitHub accounts linked yet", font=FONTS["heading_sm"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w")
            tk.Label(empty_card,
                     text="Click the '+ Link GitHub Account' button above to connect your first account using a GitHub Personal Access Token (PAT).",
                     font=FONTS["body_sm"], fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 0))
        else:
            for acc in accounts:
                self._build_account_card(pad, acc)

        # ── Section 2: Repository Account Assignment & Direct Push ───────────
        self._section_title(pad, "Repository Account Assignment & Direct Push", pady=(18, 10))
        tk.Label(pad,
                 text="Select which GitHub account pushes to each repository. Click 'Push to GitHub' to push the current branch immediately.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(0, 12))

        if not repos:
            no_repo_card = self._card(pad, padx=20, pady=20)
            no_repo_card.pack(fill="x", pady=(0, 16))
            tk.Label(no_repo_card, text="No git repositories found in your configured project folders.",
                     font=FONTS["body_md"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w")
            tk.Label(no_repo_card, text="Add project folders in Settings to scan for repositories.",
                     font=FONTS["caption"], fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 0))
        else:
            bindings = db.get_all_repo_bindings(self.user["id"])
            for repo in repos:
                self._build_repo_row(pad, repo, accounts, bindings)

    def _build_account_card(self, parent, acc: Dict):
        card = self._card(parent, padx=16, pady=14)
        card.pack(fill="x", pady=(0, 8))

        row = tk.Frame(card, bg=COLORS["bg_card"])
        row.pack(fill="x")

        # Icon badge
        av = tk.Label(row, text="🐙", font=("Segoe UI", 16),
                      bg=COLORS["bg_medium"], fg=COLORS["accent"], width=3, height=2)
        av.pack(side="left", padx=(0, 12))

        # Details
        info_f = tk.Frame(row, bg=COLORS["bg_card"])
        info_f.pack(side="left", fill="x", expand=True)

        name_row = tk.Frame(info_f, bg=COLORS["bg_card"])
        name_row.pack(fill="x")

        tk.Label(name_row, text=acc["account_name"], font=FONTS["label_bold"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(side="left")

        if acc.get("is_default"):
            badge = tk.Label(name_row, text="  ★ DEFAULT PUSH ACCOUNT  ", font=("Segoe UI", 8, "bold"),
                             fg=COLORS["bg_darkest"], bg=COLORS["accent"])
            badge.pack(side="left", padx=(8, 0))

        details_str = f"@{acc['github_username']}  •  Token: {mask_token(acc.get('github_token', ''))}"
        if acc.get("author_name") or acc.get("author_email"):
            author_info = f"{acc.get('author_name', '')} <{acc.get('author_email', '')}>".strip()
            details_str += f"  •  Author: {author_info}"

        tk.Label(info_f, text=details_str, font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(2, 0))

        status_lbl = tk.Label(info_f, text="", font=FONTS["caption"],
                              fg=COLORS["text_muted"], bg=COLORS["bg_card"])
        status_lbl.pack(anchor="w")

        # Buttons
        actions_f = tk.Frame(row, bg=COLORS["bg_card"])
        actions_f.pack(side="right")

        test_btn = tk.Button(actions_f, text="⚡ Test", font=FONTS["caption"],
                             fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                             relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
                             command=lambda a=acc, s=status_lbl: self._test_account_connection(a, s))
        test_btn.pack(side="left", padx=4)
        self._add_hover(test_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        if not acc.get("is_default"):
            def_btn = tk.Button(actions_f, text="★ Set Default", font=FONTS["caption"],
                                fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                                relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
                                command=lambda a=acc: self._set_account_default(a["id"]))
            def_btn.pack(side="left", padx=4)
            self._add_hover(def_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        edit_btn = tk.Button(actions_f, text="✏ Edit", font=FONTS["caption"],
                             fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                             relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
                             command=lambda a=acc: self._open_edit_github_dialog(a))
        edit_btn.pack(side="left", padx=4)
        self._add_hover(edit_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        del_btn = tk.Button(actions_f, text="🗑 Delete", font=FONTS["caption"],
                            fg=COLORS["error"], bg=COLORS["bg_medium"],
                            relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
                            command=lambda a=acc: self._delete_github_account(a["id"], a["account_name"]))
        del_btn.pack(side="left", padx=4)
        self._add_hover(del_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

    def _build_repo_row(self, parent, repo_path: str, accounts: list, bindings: dict):
        card = self._card(parent, padx=16, pady=12)
        card.pack(fill="x", pady=(0, 8))

        row = tk.Frame(card, bg=COLORS["bg_card"])
        row.pack(fill="x")

        info_f = tk.Frame(row, bg=COLORS["bg_card"])
        info_f.pack(side="left", fill="x", expand=True)

        name = commit_engine.repo_name(repo_path)
        branch = commit_engine.current_branch(repo_path)
        remote_url = commit_engine.get_remote_url(repo_path) or "(no remote configured)"

        title_line = tk.Frame(info_f, bg=COLORS["bg_card"])
        title_line.pack(fill="x")
        tk.Label(title_line, text=f"📁 {name}", font=FONTS["label_bold"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(side="left")
        tk.Label(title_line, text=f"  [{branch}]", font=FONTS["mono_sm"],
                 fg=COLORS["accent"], bg=COLORS["bg_card"]).pack(side="left")

        tk.Label(info_f, text=f"{repo_path}  •  Remote: {remote_url}", font=FONTS["caption"],
                 fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(2, 0))

        ctrl_f = tk.Frame(row, bg=COLORS["bg_card"])
        ctrl_f.pack(side="right")

        norm_repo = os.path.normpath(repo_path)
        current_aid = bindings.get(norm_repo)

        options = ["(Use Default Account)"]
        id_map = {"(Use Default Account)": None}
        selected_text = "(Use Default Account)"

        for a in accounts:
            label = f"{a['account_name']} (@{a['github_username']})"
            options.append(label)
            id_map[label] = a["id"]
            if current_aid == a["id"]:
                selected_text = label

        var = tk.StringVar(value=selected_text)

        def on_account_change(val):
            aid = id_map.get(val)
            if aid is None:
                db.unbind_repo_account(self.user["id"], repo_path)
            else:
                db.bind_repo_to_account(self.user["id"], repo_path, aid)

        om = tk.OptionMenu(ctrl_f, var, *options, command=on_account_change)
        om.config(font=FONTS["caption"], bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
                  activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
                  relief="flat", bd=0, highlightthickness=0)
        om["menu"].config(bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["caption"], bd=0)
        om.pack(side="left", padx=(0, 10))

        push_btn = tk.Button(ctrl_f, text="🚀 Push Now", font=FONTS["label_bold"],
                             fg="white", bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                             activeforeground="white", relief="flat", bd=0, cursor="hand2",
                             padx=12, pady=5, command=lambda r=repo_path: self._push_repo(r))
        push_btn.pack(side="left")
        self._add_hover(push_btn, COLORS["accent_hover"], COLORS["accent"])

    def _open_add_github_dialog(self):
        GitHubAccountDialog(self.root, self.user["id"], on_saved=lambda: self._nav_to("github_accounts"))

    def _open_edit_github_dialog(self, account: Dict):
        GitHubAccountDialog(self.root, self.user["id"], account=account, on_saved=lambda: self._nav_to("github_accounts"))

    def _set_account_default(self, account_id: int):
        db.set_default_github_account(account_id, self.user["id"])
        self._nav_to("github_accounts")

    def _delete_github_account(self, account_id: int, name: str):
        if messagebox.askyesno("Confirm Delete", f"Delete linked GitHub account '{name}'?", parent=self.root):
            db.delete_github_account(account_id, self.user["id"])
            self._nav_to("github_accounts")

    def _test_account_connection(self, account: Dict, status_label: tk.Label):
        status_label.config(text="⏳ Testing connection...", fg=COLORS["info"])
        self.root.update_idletasks()

        def do_test():
            ok, info, msg = verify_github_token(account.get("github_token", ""))
            if ok:
                status_label.config(text=f"✔ Connected: {msg}", fg=COLORS["success"])
            else:
                status_label.config(text=f"✖ {msg}", fg=COLORS["error"])

        threading.Thread(target=do_test, daemon=True).start()

    def _push_repo(self, repo_path: str):
        account = db.get_repo_account(self.user["id"], repo_path)
        if not account:
            messagebox.showwarning(
                "No GitHub Account",
                "Please link a GitHub account first so CommitMaster can push this repository.",
                parent=self.root
            )
            return

        name = commit_engine.repo_name(repo_path)
        branch = commit_engine.current_branch(repo_path)
        uname = account.get("github_username")

        confirm = messagebox.askyesno(
            "Confirm Push",
            f"Push branch '{branch}' of '{name}' to GitHub\nusing account '{account['account_name']}' (@{uname})?",
            parent=self.root
        )
        if not confirm:
            return

        def run_push():
            success, msg = commit_engine.push_repo_with_account(repo_path, account)
            if success:
                messagebox.showinfo("Push Succeeded", msg, parent=self.root)
            else:
                messagebox.showerror("Push Failed", f"Could not push {name}:\n\n{msg}", parent=self.root)

        threading.Thread(target=run_push, daemon=True).start()

    # ── Git Desktop (GitHub Desktop-like with Native Local AI) ─────────

    def _page_git_desktop(self):
        self._set_header("Git Desktop")
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=18, pady=14)
        pad.pack(fill="both", expand=True)

        cfg = load_config()
        watched_repos = db.get_watched_repos(self.user["id"])

        # Discover all available local git repository paths ONLY from authorized repos
        available_repos = []
        for wr in watched_repos:
            lp = wr.get("local_path", "").strip()
            if lp and os.path.isdir(lp) and commit_engine.is_git_repo(lp):
                if lp not in available_repos:
                    available_repos.append(lp)

        if not self._gd_selected_repo or self._gd_selected_repo not in available_repos:
            if available_repos:
                self._gd_selected_repo = available_repos[0]
            else:
                self._gd_selected_repo = None

        if not available_repos:
            empty_card = self._card(pad, padx=24, pady=32)
            empty_card.pack(fill="both", expand=True)
            tk.Label(empty_card, text="🖥️ No Repositories Authorized in Git Desktop",
                     font=FONTS["heading_md"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 6))
            tk.Label(empty_card,
                     text="CommitMaster respects your privacy and only accesses repositories you explicitly authorize.\n"
                          "Add a local git folder or select from your linked GitHub accounts below to start using Git Desktop.",
                     font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"], justify="left").pack(anchor="w", pady=(0, 16))

            btn_f = tk.Frame(empty_card, bg=COLORS["bg_card"])
            btn_f.pack(anchor="w")

            add_loc_btn = tk.Button(btn_f, text="📁 Add Local Repository", font=FONTS["label_bold"],
                                    fg="white", bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                                    activeforeground="white", relief="flat", bd=0, cursor="hand2",
                                    padx=16, pady=8, command=self._gd_add_local_repo)
            add_loc_btn.pack(side="left", padx=(0, 10))

            sel_gh_btn = tk.Button(btn_f, text="🐙 Select from GitHub Account", font=FONTS["label_bold"],
                                   fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                                   activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
                                   relief="flat", bd=0, cursor="hand2",
                                   padx=16, pady=8, command=self._wr_select_github_repos)
            sel_gh_btn.pack(side="left")
            return

        # ── Top Toolbar ───────────────────────────────────────────────────────
        tb = self._card(pad, padx=14, pady=10)
        tb.pack(fill="x", pady=(0, 10))

        tb_left = tk.Frame(tb, bg=COLORS["bg_card"])
        tb_left.pack(side="left", fill="x", expand=True)

        tk.Label(tb_left, text="Repository:", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(side="left", padx=(0, 6))

        repo_options = [f"📁 {commit_engine.repo_name(r)} ({r})" for r in available_repos] or ["(No repos detected)"]
        repo_map = {f"📁 {commit_engine.repo_name(r)} ({r})": r for r in available_repos}

        current_repo_label = repo_options[0]
        for opt, path in repo_map.items():
            if path == self._gd_selected_repo:
                current_repo_label = opt
                break

        repo_var = tk.StringVar(value=current_repo_label)

        def on_repo_select(val):
            target = repo_map.get(val)
            if target and target != self._gd_selected_repo:
                self._gd_selected_repo = target
                self._gd_active_file = None
                self._gd_file_comments = {}
                self._nav_to("git_desktop")

        repo_menu = tk.OptionMenu(tb_left, repo_var, *repo_options, command=on_repo_select)
        repo_menu.config(font=FONTS["body_sm"], bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
                         activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
                         relief="flat", bd=0, highlightthickness=0)
        repo_menu["menu"].config(bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body_sm"])
        repo_menu.pack(side="left", padx=(0, 10))

        add_repo_btn = tk.Button(tb_left, text="＋ Add Local Repo", font=FONTS["caption"],
                                 fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                                 relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
                                 command=self._gd_add_local_repo)
        add_repo_btn.pack(side="left", padx=(0, 12))
        self._add_hover(add_repo_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        if self._gd_selected_repo and os.path.isdir(self._gd_selected_repo):
            branch = commit_engine.current_branch(self._gd_selected_repo)
            tk.Label(tb_left, text=f"🌿 {branch}", font=FONTS["label_bold"],
                     fg=COLORS["accent"], bg=COLORS["bg_card"]).pack(side="left", padx=(0, 10))

            acc = db.get_repo_account(self.user["id"], self._gd_selected_repo)
            if acc:
                tk.Label(tb_left, text=f"🐙 @{acc['github_username']}", font=FONTS["caption"],
                         fg=COLORS["info"], bg=COLORS["bg_card"]).pack(side="left", padx=(0, 10))

        tb_right = tk.Frame(tb, bg=COLORS["bg_card"])
        tb_right.pack(side="right")

        ai_model = cfg.get("ai", {}).get("model") or ai_messages.detect_model(cfg)
        ai_text = f"⚡ Local AI: {ai_model or 'Ready'}"
        tk.Label(tb_right, text=ai_text, font=FONTS["caption"],
                 fg=COLORS["accent"] if ai_model else COLORS["warning"],
                 bg=COLORS["bg_card"]).pack(side="left", padx=(0, 10))

        refresh_btn = tk.Button(tb_right, text="🔄 Refresh", font=FONTS["caption"],
                                fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                                relief="flat", bd=0, cursor="hand2", padx=10, pady=4,
                                command=lambda: self._nav_to("git_desktop"))
        refresh_btn.pack(side="left")
        self._add_hover(refresh_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        if not self._gd_selected_repo:
            no_repo_box = self._card(pad, padx=30, pady=40)
            no_repo_box.pack(fill="both", expand=True)
            tk.Label(no_repo_box, text="🖥️ No Git Repositories Found", font=FONTS["heading_md"],
                     fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
            tk.Label(no_repo_box,
                     text="Link a GitHub repository under 'Watched Repos' or add a local folder to start using Git Desktop.",
                     font=FONTS["body_md"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(6, 16))
            tk.Button(no_repo_box, text="📁 Choose Local Repository Folder", font=FONTS["label_bold"],
                      fg="white", bg=COLORS["accent"], relief="flat", bd=0, padx=16, pady=8,
                      command=self._gd_add_local_repo).pack(anchor="w")
            return

        # Fetch changes
        changes = commit_engine.uncommitted_changes(self._gd_selected_repo)
        self._gd_changes = changes
        sensitive_patterns = cfg.get("sensitive_patterns", [])

        # Maintain or initialize staging checkboxes
        for status, path in changes:
            if path not in self._gd_staged_vars:
                is_sens = any(s in path.lower() for s in sensitive_patterns)
                self._gd_staged_vars[path] = tk.BooleanVar(value=not is_sens)

        if (not self._gd_active_file or not any(p == self._gd_active_file for _, p in changes)) and changes:
            self._gd_active_file = changes[0][1]

        # ── Main Workspace: Left (Files) & Right (Diff + File AI Commentary) ──
        ws = tk.Frame(pad, bg=COLORS["bg_dark"])
        ws.pack(fill="both", expand=True)

        # Left Panel (Changed Files - 280px)
        left_p = tk.Frame(ws, bg=COLORS["bg_card"], width=290,
                          highlightthickness=1, highlightbackground=COLORS["border"])
        left_p.pack(side="left", fill="y", padx=(0, 10))
        left_p.pack_propagate(False)

        left_hdr = tk.Frame(left_p, bg=COLORS["bg_medium"], padx=10, pady=8)
        left_hdr.pack(fill="x")
        tk.Label(left_hdr, text=f"Changes ({len(changes)})", font=FONTS["label_bold"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_medium"]).pack(side="left")

        toggle_all_btn = tk.Button(left_hdr, text="Toggle All", font=FONTS["caption"],
                                   fg=COLORS["accent"], bg=COLORS["bg_medium"], relief="flat", bd=0,
                                   cursor="hand2", command=self._gd_toggle_all_files)
        toggle_all_btn.pack(side="right")

        # Scrollable file list
        files_canvas = tk.Canvas(left_p, bg=COLORS["bg_card"], highlightthickness=0)
        files_sb = tk.Scrollbar(left_p, orient="vertical", command=files_canvas.yview)
        files_frame = tk.Frame(files_canvas, bg=COLORS["bg_card"])

        files_canvas.create_window((0, 0), window=files_frame, anchor="nw")
        files_frame.bind("<Configure>", lambda e: files_canvas.configure(scrollregion=files_canvas.bbox("all")))
        files_canvas.configure(yscrollcommand=files_sb.set)

        files_sb.pack(side="right", fill="y")
        files_canvas.pack(side="left", fill="both", expand=True)

        if not changes:
            tk.Label(files_frame, text="✔ Working tree clean\nNo uncommitted changes",
                     font=FONTS["body_sm"], fg=COLORS["success"], bg=COLORS["bg_card"],
                     justify="center", padx=16, pady=24).pack(fill="x")
        else:
            for status, path in changes:
                self._gd_build_file_row(files_frame, status, path)

        # Right Panel (Diff Viewer & AI File Commentary)
        right_p = tk.Frame(ws, bg=COLORS["bg_dark"])
        right_p.pack(side="left", fill="both", expand=True)

        # AI commentary card for currently selected file
        self._gd_build_ai_file_comment_card(right_p)

        # Diff View Frame
        diff_card = tk.Frame(right_p, bg=COLORS["bg_card"],
                             highlightthickness=1, highlightbackground=COLORS["border"])
        diff_card.pack(fill="both", expand=True)

        diff_hdr = tk.Frame(diff_card, bg=COLORS["bg_medium"], padx=12, pady=6)
        diff_hdr.pack(fill="x")
        active_name = self._gd_active_file or "No file selected"
        tk.Label(diff_hdr, text=f"Diff: {active_name}", font=FONTS["mono_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_medium"]).pack(side="left")

        diff_f = tk.Frame(diff_card, bg=COLORS["bg_card"])
        diff_f.pack(fill="both", expand=True)

        self._gd_diff_text = tk.Text(
            diff_f, bg=COLORS["bg_input"], fg=COLORS["text_primary"],
            font=("Consolas", 10), wrap="none", relief="flat", bd=0,
            padx=10, pady=10,
        )
        diff_sb_y = tk.Scrollbar(diff_f, orient="vertical", command=self._gd_diff_text.yview)
        diff_sb_x = tk.Scrollbar(diff_card, orient="horizontal", command=self._gd_diff_text.xview)
        self._gd_diff_text.configure(yscrollcommand=diff_sb_y.set, xscrollcommand=diff_sb_x.set)

        diff_sb_y.pack(side="right", fill="y")
        self._gd_diff_text.pack(side="left", fill="both", expand=True)
        diff_sb_x.pack(fill="x")

        # Tags for diff syntax highlighting
        self._gd_diff_text.tag_config("diff_add", foreground="#7ee787", background="#132a19")
        self._gd_diff_text.tag_config("diff_del", foreground="#ffa198", background="#331414")
        self._gd_diff_text.tag_config("diff_hunk", foreground="#79c0ff", font=("Consolas", 10, "bold"))
        self._gd_diff_text.tag_config("diff_meta", foreground="#8b949e")

        if self._gd_active_file:
            self._gd_load_file_diff(self._gd_active_file)

        # ── Bottom Dock: Native Local AI Generator + Commit & Push ───────────
        self._gd_build_commit_dock(pad, cfg)

    def _gd_add_local_repo(self):
        d = filedialog.askdirectory(title="Select Local Git Repository")
        if d:
            if commit_engine.is_git_repo(d):
                self._gd_selected_repo = os.path.normpath(d)
                self._gd_active_file = None
                self._nav_to("git_desktop")
            else:
                messagebox.showerror("Not a Git Repository", f"'{d}' is not a valid git repository (.git folder not found).", parent=self.root)

    def _gd_toggle_all_files(self):
        if not self._gd_staged_vars:
            return
        all_checked = all(var.get() for var in self._gd_staged_vars.values())
        for var in self._gd_staged_vars.values():
            var.set(not all_checked)

    def _gd_build_file_row(self, parent, status: str, path: str):
        row = tk.Frame(parent, bg=COLORS["bg_card"], padx=6, pady=4)
        row.pack(fill="x")

        var = self._gd_staged_vars.get(path)
        if not var:
            var = tk.BooleanVar(value=True)
            self._gd_staged_vars[path] = var

        cb = tk.Checkbutton(row, variable=var, bg=COLORS["bg_card"],
                            selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"])
        cb.pack(side="left")

        # Status badge color
        status_colors = {
            "M": ("M", "#f0883e"),
            "A": ("A", "#3fb950"),
            "D": ("D", "#f85149"),
            "??": ("?", "#58a6ff"),
        }
        st_text, st_color = status_colors.get(status, (status[:1], "#8b949e"))
        tk.Label(row, text=f"[{st_text}]", font=FONTS["mono_sm"], fg=st_color, bg=COLORS["bg_card"]).pack(side="left", padx=(2, 4))

        filename = os.path.basename(path)
        dir_part = os.path.dirname(path)
        display_text = f"{filename}  ({dir_part})" if dir_part else filename

        lbl = tk.Label(row, text=display_text, font=FONTS["body_sm"], fg=COLORS["text_primary"],
                       bg=COLORS["bg_card"], anchor="w", cursor="hand2")
        lbl.pack(side="left", fill="x", expand=True)

        def on_click(e):
            self._gd_select_file(path)
        lbl.bind("<Button-1>", on_click)
        row.bind("<Button-1>", on_click)

    def _gd_select_file(self, path: str):
        self._gd_active_file = path
        self._gd_load_file_diff(path)
        comment = self._gd_file_comments.get(path, "")
        if self._gd_comment_var:
            self._gd_comment_var.set(comment or "(Click '✨ Write AI Comments for Each File' below to generate with local AI)")

    def _gd_load_file_diff(self, file_path: str):
        if not self._gd_diff_text or not self._gd_selected_repo:
            return
        self._gd_diff_text.delete("1.0", "end")
        raw_diff = commit_engine.file_diff(self._gd_selected_repo, file_path, max_chars=8000)

        for line in raw_diff.splitlines():
            line_str = line + "\n"
            if line.startswith("+++") or line.startswith("---"):
                self._gd_diff_text.insert("end", line_str, "diff_meta")
            elif line.startswith("+"):
                self._gd_diff_text.insert("end", line_str, "diff_add")
            elif line.startswith("-"):
                self._gd_diff_text.insert("end", line_str, "diff_del")
            elif line.startswith("@@"):
                self._gd_diff_text.insert("end", line_str, "diff_hunk")
            else:
                self._gd_diff_text.insert("end", line_str)

    def _gd_build_ai_file_comment_card(self, parent):
        card = tk.Frame(parent, bg=COLORS["bg_card"], padx=12, pady=8,
                        highlightthickness=1, highlightbackground=COLORS["border"])
        card.pack(fill="x", pady=(0, 8))

        f_hdr = tk.Frame(card, bg=COLORS["bg_card"])
        f_hdr.pack(fill="x")
        tk.Label(f_hdr, text="🤖 Native Local AI — File Comment:",
                 font=FONTS["label_bold"], fg=COLORS["accent"], bg=COLORS["bg_card"]).pack(side="left")

        current_file = self._gd_active_file or ""
        comment = self._gd_file_comments.get(current_file, "")
        if not comment:
            comment = "(Click '✨ Write AI Comments for Each File' below to generate with local AI)"

        self._gd_comment_var.set(comment)
        self._gd_comment_entry = tk.Entry(
            card, textvariable=self._gd_comment_var, font=FONTS["body_sm"],
            bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
            highlightthickness=1, highlightbackground=COLORS["border"],
        )
        self._gd_comment_entry.pack(fill="x", pady=(4, 0), ipady=4)

        def on_comment_edit(e=None):
            if self._gd_active_file:
                self._gd_file_comments[self._gd_active_file] = self._gd_comment_var.get()
        self._gd_comment_entry.bind("<KeyRelease>", on_comment_edit)

    def _gd_build_commit_dock(self, parent, cfg):
        dock = self._card(parent, padx=14, pady=10)
        dock.pack(fill="x", pady=(10, 0))

        # Action: Write AI comments button
        ai_row = tk.Frame(dock, bg=COLORS["bg_card"])
        ai_row.pack(fill="x", pady=(0, 6))

        gen_btn = tk.Button(
            ai_row, text="✨ Write AI Comments for Each File (Native Local PC AI)",
            font=FONTS["label_bold"], fg="white", bg=COLORS["accent"],
            activebackground=COLORS["accent_hover"], activeforeground="white",
            relief="flat", bd=0, cursor="hand2", padx=14, pady=5,
            command=lambda: self._gd_generate_ai_comments(cfg)
        )
        gen_btn.pack(side="left", padx=(0, 10))
        self._add_hover(gen_btn, COLORS["accent_hover"], COLORS["accent"])

        self._gd_ai_status_lbl = tk.Label(ai_row, text="", font=FONTS["caption"],
                                          fg=COLORS["text_secondary"], bg=COLORS["bg_card"])
        self._gd_ai_status_lbl.pack(side="left")

        # Headline Input
        tk.Label(dock, text="Commit Headline:", font=FONTS["label_bold"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")

        headline_e = tk.Entry(
            dock, textvariable=self._gd_headline_var, font=FONTS["body_md"],
            bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
            highlightthickness=1, highlightbackground=COLORS["border"],
        )
        headline_e.pack(fill="x", pady=(2, 6), ipady=4)

        # Full Description Text
        tk.Label(dock, text="Description & Per-File Commentary:", font=FONTS["caption"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w")

        self._gd_desc_text = tk.Text(
            dock, font=FONTS["body_sm"], height=3, bg=COLORS["bg_input"],
            fg=COLORS["text_primary"], relief="flat", padx=8, pady=6,
            highlightthickness=1, highlightbackground=COLORS["border"],
        )
        self._gd_desc_text.pack(fill="x", pady=(2, 8))

        # Push Confirmation & Action Buttons Row
        action_row = tk.Frame(dock, bg=COLORS["bg_card"])
        action_row.pack(fill="x")

        # Ask before git pushing checkbox
        cb = tk.Checkbutton(
            action_row, text="Ask me before git pushing", variable=self._gd_ask_push_var,
            font=FONTS["body_sm"], fg=COLORS["text_primary"], bg=COLORS["bg_card"],
            selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"],
            activeforeground=COLORS["text_primary"],
        )
        cb.pack(side="left", padx=(0, 14))

        # Commit button
        commit_btn = tk.Button(
            action_row, text="💾 Commit Changes", font=FONTS["label_bold"],
            fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=14, pady=6,
            command=lambda: self._gd_do_commit(push=False)
        )
        commit_btn.pack(side="left", padx=(0, 8))
        self._add_hover(commit_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        # Commit & Push button
        commit_push_btn = tk.Button(
            action_row, text="🚀 Commit & Push to GitHub", font=FONTS["label_bold"],
            fg="white", bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
            activeforeground="white", relief="flat", bd=0, cursor="hand2", padx=16, pady=6,
            command=lambda: self._gd_do_commit(push=True)
        )
        commit_push_btn.pack(side="left", padx=(0, 8))
        self._add_hover(commit_push_btn, COLORS["accent_hover"], COLORS["accent"])

        # Push Remote button
        unpushed = commit_engine.get_unpushed_commits(self._gd_selected_repo) if self._gd_selected_repo else []
        push_label = f"⬆️ Push Commits ({len(unpushed)})" if unpushed else "⬆️ Push Commits"
        push_remote_btn = tk.Button(
            action_row, text=push_label, font=FONTS["label"],
            fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=12, pady=6,
            command=self._gd_push_commits
        )
        push_remote_btn.pack(side="left")
        self._add_hover(push_remote_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

    def _gd_generate_ai_comments(self, cfg):
        if not self._gd_selected_repo:
            return

        selected_files = [p for p, var in self._gd_staged_vars.items() if var.get()]
        if not selected_files:
            selected_files = [p for _, p in self._gd_changes]

        if not selected_files:
            messagebox.showinfo("No Changes", "No files selected or modified in this repository.", parent=self.root)
            return

        if self._gd_ai_status_lbl:
            self._gd_ai_status_lbl.config(text="⏳ Native Local AI is analyzing diffs...", fg=COLORS["info"])
        self.root.update_idletasks()

        def do_gen():
            res = ai_messages.generate_file_comments(cfg, self._gd_selected_repo, selected_files)

            def apply():
                self._gd_headline_var.set(res.get("headline", ""))
                self._gd_file_comments = res.get("file_comments", {})
                if self._gd_desc_text:
                    self._gd_desc_text.delete("1.0", "end")
                    self._gd_desc_text.insert("end", res.get("description", ""))
                if self._gd_active_file and self._gd_comment_var:
                    comm = self._gd_file_comments.get(self._gd_active_file, "")
                    self._gd_comment_var.set(comm)
                if self._gd_ai_status_lbl:
                    self._gd_ai_status_lbl.config(text="✔ AI comments ready for files!", fg=COLORS["success"])

            self.root.after(0, apply)

        threading.Thread(target=do_gen, daemon=True).start()

    def _gd_do_commit(self, push: bool = False):
        if not self._gd_selected_repo:
            return

        staged_files = [p for p, var in self._gd_staged_vars.items() if var.get()]
        if not staged_files:
            messagebox.showwarning("Nothing Staged", "Please select at least one changed file to commit.", parent=self.root)
            return

        headline = self._gd_headline_var.get().strip() or "chore: update repository files"
        desc = self._gd_desc_text.get("1.0", "end").strip() if self._gd_desc_text else ""
        full_msg = f"{headline}\n\n{desc}" if desc else headline

        try:
            summary = commit_engine.stage_and_commit(self._gd_selected_repo, staged_files, full_msg)
            # Log commit
            db.log_commit(
                user_id=self.user["id"],
                repo_path=self._gd_selected_repo,
                commit_msg=headline,
                files_count=len(staged_files),
                commit_hash=summary.split()[0] if summary else "",
            )

            if push:
                self._gd_push_commits()
            else:
                messagebox.showinfo("Committed", f"Committed successfully:\n{summary}", parent=self.root)
                self._nav_to("git_desktop")

        except Exception as exc:
            messagebox.showerror("Commit Failed", f"Could not create commit:\n{exc}", parent=self.root)

    def _gd_push_commits(self):
        if not self._gd_selected_repo:
            return

        account = db.get_repo_account(self.user["id"], self._gd_selected_repo)
        if not account:
            messagebox.showwarning("No Account Linked", "Please link a GitHub account under 'GitHub Accounts' before pushing.", parent=self.root)
            return

        name = commit_engine.repo_name(self._gd_selected_repo)
        branch = commit_engine.current_branch(self._gd_selected_repo)
        unpushed = commit_engine.get_unpushed_commits(self._gd_selected_repo)

        # Ask user before pushing if checkbox is checked
        if self._gd_ask_push_var.get():
            confirmed = ui.ask_push_confirmation(name, branch, account, unpushed)
            if not confirmed:
                messagebox.showinfo("Push Cancelled", "Push cancelled. Commits remain saved locally.", parent=self.root)
                return

        def do_push():
            ok, msg = commit_engine.push_repo_with_account(self._gd_selected_repo, account)
            def done():
                if ok:
                    messagebox.showinfo("Push Succeeded", msg, parent=self.root)
                    self._nav_to("git_desktop")
                else:
                    messagebox.showerror("Push Failed", f"Could not push to GitHub:\n\n{msg}", parent=self.root)
            self.root.after(0, done)

        threading.Thread(target=do_push, daemon=True).start()

    # ── Watched Repositories (Active Project Tracker) ──────────────────

    def _page_watched_repos(self):
        self._set_header("Watched Repositories")
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Watched GitHub Repositories", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad,
                 text="Select which repositories to actively keep an eye on. CommitMaster monitors watched repositories for changes and assists with local AI comments before asking to push.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_dark"], wraplength=700).pack(anchor="w", pady=(2, 14))

        watched_all = db.get_watched_repos(self.user["id"])
        active_count = sum(1 for r in watched_all if r.get("is_active_watch"))
        local_count = sum(1 for r in watched_all if r.get("local_path"))

        stats_row = tk.Frame(pad, bg=COLORS["bg_dark"])
        stats_row.pack(fill="x", pady=(0, 16))
        self._stat_card(stats_row, "Total Repositories", str(len(watched_all)), COLORS["accent"], "🐙")
        self._stat_card(stats_row, "Actively Watched", str(active_count), COLORS["success"], "👀")
        self._stat_card(stats_row, "Linked Local Folders", str(local_count), COLORS["info"], "📁")

        # Action Bar: Sync from GitHub + Search Filter
        ctrl_card = self._card(pad, padx=14, pady=10)
        ctrl_card.pack(fill="x", pady=(0, 14))

        ctrl_f = tk.Frame(ctrl_card, bg=COLORS["bg_card"])
        ctrl_f.pack(fill="x")

        add_local_btn = tk.Button(ctrl_f, text="📁 Add Local Repository", font=FONTS["label_bold"],
                                  fg="white", bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                                  activeforeground="white", relief="flat", bd=0, cursor="hand2",
                                  padx=12, pady=6, command=self._wr_add_local_repo)
        add_local_btn.pack(side="left", padx=(0, 8))
        self._add_hover(add_local_btn, COLORS["accent_hover"], COLORS["accent"])

        sel_gh_btn = tk.Button(ctrl_f, text="🐙 Select GitHub Repos", font=FONTS["label_bold"],
                               fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                               activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
                               relief="flat", bd=0, cursor="hand2",
                               padx=12, pady=6, command=self._wr_select_github_repos)
        sel_gh_btn.pack(side="left", padx=(0, 14))
        self._add_hover(sel_gh_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        tk.Label(ctrl_f, text="Search:", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(side="left", padx=(0, 4))
        search_e = tk.Entry(ctrl_f, textvariable=self._wr_search_var, font=FONTS["body_sm"],
                            bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                            highlightthickness=1, highlightbackground=COLORS["border"], width=22)
        search_e.pack(side="left", ipady=4, padx=(0, 12))
        search_e.bind("<KeyRelease>", lambda e: self._nav_to("watched_repos"))

        for mode, label in [("all", "All"), ("watched", "👀 Watched Only"), ("local", "📁 Linked Local")]:
            is_cur = (self._wr_filter_mode == mode)
            f_btn = tk.Button(
                ctrl_f, text=label, font=FONTS["caption"],
                fg=COLORS["accent"] if is_cur else COLORS["text_secondary"],
                bg=COLORS["bg_card_hover"] if is_cur else COLORS["bg_medium"],
                relief="flat", bd=0, cursor="hand2", padx=10, pady=4,
                command=lambda m=mode: self._wr_set_filter_mode(m)
            )
            f_btn.pack(side="left", padx=2)

        # Repositories List
        query = self._wr_search_var.get().strip().lower()
        filtered = []
        for r in watched_all:
            if query and query not in r["repo_full_name"].lower() and query not in (r.get("description") or "").lower():
                continue
            if self._wr_filter_mode == "watched" and not r.get("is_active_watch"):
                continue
            if self._wr_filter_mode == "local" and not r.get("local_path"):
                continue
            filtered.append(r)

        if not filtered:
            empty_box = self._card(pad, padx=24, pady=30)
            empty_box.pack(fill="x", pady=(0, 10))
            tk.Label(empty_box, text="No repositories authorized yet.", font=FONTS["heading_sm"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w")
            tk.Label(empty_box, text="CommitMaster only accesses repositories you explicitly add. Click '📁 Add Local Repository' or '🐙 Select GitHub Repos' above to choose which projects to work on.",
                     font=FONTS["caption"], fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 0))
        else:
            for repo_item in filtered:
                self._wr_build_repo_card(pad, repo_item)

    def _wr_set_filter_mode(self, mode: str):
        self._wr_filter_mode = mode
        self._nav_to("watched_repos")

    def _wr_select_github_repos(self):
        accounts = db.get_github_accounts(self.user["id"])
        if not accounts:
            if messagebox.askyesno(
                "No GitHub Accounts",
                "No GitHub accounts linked yet. Would you like to link a GitHub account now?",
                parent=self.root,
            ):
                self._open_add_github_dialog()
            return
        SelectGitHubReposDialog(self.root, self.user["id"], on_selected=lambda: self._nav_to("watched_repos"))

    def _wr_add_local_repo(self):
        folder = filedialog.askdirectory(title="Select Local Git Repository Folder", parent=self.root)
        if not folder:
            return
        if not commit_engine.is_git_repo(folder):
            messagebox.showerror("Not a Git Repository", f"The folder '{folder}' does not contain a .git repository.", parent=self.root)
            return

        rname = commit_engine.repo_name(folder)
        db.add_or_update_watched_repo(
            user_id=self.user["id"],
            repo_name=rname,
            repo_full_name=rname,
            local_path=folder,
            is_active_watch=1,
        )
        self._gd_selected_repo = folder
        messagebox.showinfo("Repository Added", f"Repository '{rname}' added and authorized in CommitMaster!", parent=self.root)
        self._nav_to("watched_repos")

    def _wr_remove_repo(self, repo: Dict):
        if messagebox.askyesno("Remove Access", f"Remove '{repo['repo_full_name']}' from CommitMaster?\n\nCommitMaster will no longer access, track, or auto-commit to this repository.", parent=self.root):
            db.delete_watched_repo(repo["id"], self.user["id"])
            if self._gd_selected_repo == repo.get("local_path"):
                self._gd_selected_repo = None
            self._nav_to("watched_repos")

    def _wr_sync_github(self):
        self._wr_select_github_repos()

    def _wr_build_repo_card(self, parent, repo: Dict):
        card = self._card(parent, padx=16, pady=12)
        card.pack(fill="x", pady=(0, 8))

        top_row = tk.Frame(card, bg=COLORS["bg_card"])
        top_row.pack(fill="x")

        # Left side: Title, Badges
        left_info = tk.Frame(top_row, bg=COLORS["bg_card"])
        left_info.pack(side="left", fill="x", expand=True)

        title_line = tk.Frame(left_info, bg=COLORS["bg_card"])
        title_line.pack(fill="x")

        priv_text = "🔒 Private" if repo.get("is_private") else "🌐 Public"
        priv_fg = COLORS["warning"] if repo.get("is_private") else COLORS["text_secondary"]
        tk.Label(title_line, text=priv_text, font=FONTS["caption"],
                 fg=priv_fg, bg=COLORS["bg_card"]).pack(side="left", padx=(0, 6))

        tk.Label(title_line, text=repo["repo_full_name"], font=FONTS["label_bold"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(side="left", padx=(0, 6))

        tk.Label(title_line, text=f"[{repo.get('default_branch', 'main')}]", font=FONTS["mono_sm"],
                 fg=COLORS["accent"], bg=COLORS["bg_card"]).pack(side="left", padx=(0, 6))

        if repo.get("github_username"):
            tk.Label(title_line, text=f"@{repo['github_username']}", font=FONTS["caption"],
                     fg=COLORS["info"], bg=COLORS["bg_card"]).pack(side="left")

        if repo.get("description"):
            tk.Label(left_info, text=repo["description"], font=FONTS["caption"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"], wraplength=540, justify="left").pack(anchor="w", pady=(2, 0))

        # Local Path details
        lp = repo.get("local_path", "").strip()
        path_text = f"📁 Local Path: {lp}" if lp else "📁 Local Path: Not Linked (Locate or Clone below)"
        path_fg = COLORS["text_primary"] if lp else COLORS["text_muted"]
        tk.Label(left_info, text=path_text, font=FONTS["caption"],
                 fg=path_fg, bg=COLORS["bg_card"]).pack(anchor="w", pady=(3, 0))

        # Right side: Action controls
        right_ctrl = tk.Frame(top_row, bg=COLORS["bg_card"])
        right_ctrl.pack(side="right")

        # 1. Watch Toggle button
        is_watched = bool(repo.get("is_active_watch"))
        watch_btn_text = "🟢 Actively Watched (Auto-Commit)" if is_watched else "⚪ Manual Only (No Auto-Commit)"
        watch_btn_bg = COLORS["success"] if is_watched else COLORS["bg_medium"]
        watch_btn_fg = "white" if is_watched else COLORS["text_secondary"]

        def toggle_watch():
            db.toggle_watched_repo(repo["id"], self.user["id"])
            self._nav_to("watched_repos")

        watch_btn = tk.Button(
            right_ctrl, text=watch_btn_text, font=FONTS["caption"],
            fg=watch_btn_fg, bg=watch_btn_bg, relief="flat", bd=0, cursor="hand2",
            padx=10, pady=5, command=toggle_watch
        )
        watch_btn.pack(side="left", padx=(0, 6))

        # 2. Local Folder Link / Change
        link_text = "📁 Change Folder" if lp else "📁 Link Folder"
        link_btn = tk.Button(
            right_ctrl, text=link_text, font=FONTS["caption"],
            fg=COLORS["text_primary"], bg=COLORS["bg_medium"], relief="flat", bd=0,
            cursor="hand2", padx=8, pady=5,
            command=lambda r=repo: self._wr_link_local_folder(r)
        )
        link_btn.pack(side="left", padx=(0, 6))

        # 3. Clone if not local
        if not lp and repo.get("clone_url"):
            clone_btn = tk.Button(
                right_ctrl, text="📥 Clone", font=FONTS["caption"],
                fg=COLORS["text_primary"], bg=COLORS["bg_medium"], relief="flat", bd=0,
                cursor="hand2", padx=8, pady=5,
                command=lambda r=repo: self._wr_clone_repo(r)
            )
            clone_btn.pack(side="left", padx=(0, 6))

        # 4. Open in Git Desktop
        if lp and os.path.isdir(lp):
            open_gd_btn = tk.Button(
                right_ctrl, text="🖥️ Open Desktop", font=FONTS["label_bold"],
                fg="white", bg=COLORS["info"], relief="flat", bd=0, cursor="hand2",
                padx=10, pady=5,
                command=lambda p=lp: self._wr_open_in_desktop(p)
            )
            open_gd_btn.pack(side="left", padx=(0, 6))

        # 5. Revoke Access / Remove Repo
        del_btn = tk.Button(
            right_ctrl, text="🗑️ Remove Access", font=FONTS["caption"],
            fg=COLORS["error"], bg=COLORS["bg_medium"], relief="flat", bd=0,
            cursor="hand2", padx=8, pady=5,
            command=lambda r=repo: self._wr_remove_repo(r)
        )
        del_btn.pack(side="left")

    def _wr_link_local_folder(self, repo: Dict):
        d = filedialog.askdirectory(title=f"Select local clone folder for {repo['repo_name']}")
        if d:
            if commit_engine.is_git_repo(d):
                db.set_watched_repo_local_path(repo["id"], self.user["id"], d)
                messagebox.showinfo("Linked", f"Linked '{repo['repo_name']}' to {d}", parent=self.root)
                self._nav_to("watched_repos")
            else:
                messagebox.showwarning("Not a Git Repo", f"Folder '{d}' does not contain a .git directory.", parent=self.root)

    def _wr_clone_repo(self, repo: Dict):
        parent_dir = filedialog.askdirectory(title=f"Select parent directory to clone {repo['repo_name']}")
        if not parent_dir:
            return

        target_path = os.path.join(parent_dir, repo["repo_name"])
        account = db.get_github_account(repo.get("github_account_id") or 0)

        def do_clone():
            ok, msg = commit_engine.clone_repo(repo["clone_url"], target_path, account)
            def done():
                if ok:
                    db.set_watched_repo_local_path(repo["id"], self.user["id"], target_path)
                    db.toggle_watched_repo(repo["id"], self.user["id"], is_active=True)
                    messagebox.showinfo("Cloned", f"Repository cloned to:\n{target_path}", parent=self.root)
                    self._nav_to("watched_repos")
                else:
                    messagebox.showerror("Clone Failed", f"Could not clone repository:\n\n{msg}", parent=self.root)
            self.root.after(0, done)

        threading.Thread(target=do_clone, daemon=True).start()

    def _wr_open_in_desktop(self, local_path: str):
        self._gd_selected_repo = local_path
        self._gd_active_file = None
        self._nav_to("git_desktop")


    # ── Customize Interface Page ──────────────────────────────────────────────

    def _page_customize(self):
        self._set_header("Interface Customization")
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Customize Interface", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad, text="Personalize themes, accent colors, typography, and density. Changes can be applied live.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))

        prefs = db.get_preferences(self.user["id"]) or {}
        curr = get_active_customization()

        self._custom_theme = curr.get("theme", "github_dark")
        self._custom_accent = curr.get("accent", "green")
        self._custom_accent_hex = tk.StringVar(value=curr.get("accent_hex", "#3fb950"))
        self._custom_font_family = tk.StringVar(value=curr.get("font_family", "Segoe UI"))
        self._custom_font_scale = tk.StringVar(value=curr.get("font_scale", "standard"))
        self._custom_density = tk.StringVar(value=curr.get("ui_density", "comfortable"))
        self._custom_auto_push = tk.BooleanVar(value=bool(prefs.get("auto_push", 0)))

        # ── Theme Presets Section ─────────────────────────────────────────────
        self._section_title(pad, "Theme Presets", pady=(4, 10))
        themes_grid = tk.Frame(pad, bg=COLORS["bg_dark"])
        themes_grid.pack(fill="x", pady=(0, 16))

        self._theme_cards = {}
        for col_idx, (t_key, t_info) in enumerate(THEMES.items()):
            col = col_idx % 4
            row = col_idx // 4
            t_card = tk.Frame(themes_grid, bg=t_info["bg_card"],
                              highlightthickness=2,
                              highlightbackground=COLORS["accent"] if t_key == self._custom_theme else t_info["border"],
                              padx=12, pady=10, cursor="hand2")
            t_card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            themes_grid.grid_columnconfigure(col, weight=1)

            t_name = tk.Label(t_card, text=t_info["name"].split("(")[0].strip(),
                              font=FONTS["label_bold"], fg=t_info["text_primary"],
                              bg=t_info["bg_card"], cursor="hand2")
            t_name.pack(anchor="w")

            swatch_f = tk.Frame(t_card, bg=t_info["bg_card"], cursor="hand2")
            swatch_f.pack(anchor="w", pady=(6, 0))
            for color_val in [t_info["bg_darkest"], t_info["bg_card"], t_info["border"], t_info["text_primary"]]:
                s = tk.Label(swatch_f, text="  ", bg=color_val, width=2, height=1, relief="flat")
                s.pack(side="left", padx=2)

            def make_handler(k=t_key):
                return lambda e: self._select_theme_card(k)

            t_card.bind("<Button-1>", make_handler())
            t_name.bind("<Button-1>", make_handler())
            swatch_f.bind("<Button-1>", make_handler())
            self._theme_cards[t_key] = t_card

        # ── Accent Colors Section ─────────────────────────────────────────────
        self._section_title(pad, "Primary Accent Color", pady=(8, 10))
        accent_card = self._card(pad, padx=20, pady=16)
        accent_card.pack(fill="x", pady=(0, 16))

        acc_chips_f = tk.Frame(accent_card, bg=COLORS["bg_card"])
        acc_chips_f.pack(fill="x", pady=(0, 10))

        self._accent_chips = {}
        for a_key, a_info in ACCENTS.items():
            chip_f = tk.Frame(acc_chips_f, bg=COLORS["bg_card"], cursor="hand2")
            chip_f.pack(side="left", padx=(0, 12))

            dot = tk.Label(chip_f, text="  ", bg=a_info["accent"], width=3, height=1,
                           highlightthickness=2,
                           highlightbackground="white" if a_key == self._custom_accent else COLORS["border"],
                           cursor="hand2")
            dot.pack(anchor="center")
            lbl = tk.Label(chip_f, text=a_info["name"].split("/")[0].strip(),
                           font=FONTS["caption"], fg=COLORS["text_secondary"],
                           bg=COLORS["bg_card"], cursor="hand2")
            lbl.pack(anchor="center", pady=(2, 0))

            def make_acc_handler(k=a_key, hexv=a_info["accent"]):
                return lambda e: self._select_accent_chip(k, hexv)

            dot.bind("<Button-1>", make_acc_handler())
            lbl.bind("<Button-1>", make_acc_handler())
            self._accent_chips[a_key] = dot

        # Custom Hex row
        hex_row = tk.Frame(accent_card, bg=COLORS["bg_card"])
        hex_row.pack(fill="x", pady=(6, 0))
        tk.Label(hex_row, text="Or Custom Hex: ", font=FONTS["label"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(side="left")
        hex_entry = tk.Entry(hex_row, textvariable=self._custom_accent_hex, font=FONTS["mono_sm"],
                             bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                             relief="flat", highlightthickness=1,
                             highlightbackground=COLORS["border"], width=10)
        hex_entry.pack(side="left", ipady=4, padx=6)
        apply_hex_btn = self._make_small_btn(hex_row, "Set Hex", self._apply_custom_hex)
        apply_hex_btn.pack(side="left")

        # ── Typography & UI Density Section ──────────────────────────────────
        self._section_title(pad, "Typography & Scaling", pady=(8, 10))
        type_card = self._card(pad, padx=20, pady=16)
        type_card.pack(fill="x", pady=(0, 16))

        # Font Family
        ff_row = tk.Frame(type_card, bg=COLORS["bg_card"])
        ff_row.pack(fill="x", pady=(0, 10))
        tk.Label(ff_row, text="Font Family:", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=16, anchor="w").pack(side="left")

        ff_menu = tk.OptionMenu(ff_row, self._custom_font_family, *FONT_FAMILIES)
        ff_menu.config(font=FONTS["body_md"], bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                       relief="flat", bd=0, highlightthickness=0)
        ff_menu["menu"].config(bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body_md"])
        ff_menu.pack(side="left", ipady=2)

        # Font Scale
        fs_row = tk.Frame(type_card, bg=COLORS["bg_card"])
        fs_row.pack(fill="x", pady=(0, 10))
        tk.Label(fs_row, text="Font Scale:", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=16, anchor="w").pack(side="left")
        for scale_k, scale_lbl in [("compact", "Compact (90%)"), ("standard", "Standard (100%)"), ("large", "Comfortable (115%)")]:
            rb = tk.Radiobutton(fs_row, text=scale_lbl, variable=self._custom_font_scale,
                                value=scale_k, font=FONTS["body_md"], fg=COLORS["text_primary"],
                                bg=COLORS["bg_card"], selectcolor=COLORS["bg_input"],
                                activebackground=COLORS["bg_card"], activeforeground=COLORS["text_primary"])
            rb.pack(side="left", padx=(0, 16))

        # UI Density
        den_row = tk.Frame(type_card, bg=COLORS["bg_card"])
        den_row.pack(fill="x", pady=(0, 10))
        tk.Label(den_row, text="UI Density:", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=16, anchor="w").pack(side="left")
        for den_k, den_lbl in [("comfortable", "Comfortable"), ("compact", "Compact")]:
            rb = tk.Radiobutton(den_row, text=den_lbl, variable=self._custom_density,
                                value=den_k, font=FONTS["body_md"], fg=COLORS["text_primary"],
                                bg=COLORS["bg_card"], selectcolor=COLORS["bg_input"],
                                activebackground=COLORS["bg_card"], activeforeground=COLORS["text_primary"])
            rb.pack(side="left", padx=(0, 16))

        # Auto-Push Toggle
        ap_cb = tk.Checkbutton(type_card, text="Automatically push commits to linked GitHub account when committing",
                               variable=self._custom_auto_push, font=FONTS["body_md"],
                               fg=COLORS["text_primary"], bg=COLORS["bg_card"], selectcolor=COLORS["bg_input"],
                               activebackground=COLORS["bg_card"], activeforeground=COLORS["text_primary"])
        ap_cb.pack(anchor="w", pady=(4, 0))

        # ── Action Buttons ───────────────────────────────────────────────────
        action_f = tk.Frame(pad, bg=COLORS["bg_dark"])
        action_f.pack(fill="x", pady=(12, 10))

        apply_btn = tk.Button(action_f, text="  ✨  Apply & Save Customization  ",
                              font=FONTS["heading_sm"], fg="white",
                              bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                              activeforeground="white", relief="flat", bd=0, cursor="hand2",
                              padx=18, pady=10, command=self._save_and_apply_customization)
        apply_btn.pack(side="left", padx=(0, 12))
        self._add_hover(apply_btn, COLORS["accent_hover"], COLORS["accent"])

        reset_btn = tk.Button(action_f, text="  ↺  Reset Defaults  ", font=FONTS["label"],
                              fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                              activebackground=COLORS["bg_card_hover"],
                              activeforeground=COLORS["text_primary"],
                              relief="flat", bd=0, cursor="hand2",
                              padx=14, pady=10, command=self._reset_customization)
        reset_btn.pack(side="left")
        self._add_hover(reset_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

    def _select_theme_card(self, theme_key: str):
        self._custom_theme = theme_key
        for k, card in self._theme_cards.items():
            border_c = COLORS["accent"] if k == theme_key else THEMES[k]["border"]
            card.config(highlightbackground=border_c)

    def _select_accent_chip(self, accent_key: str, hex_val: str):
        self._custom_accent = accent_key
        self._custom_accent_hex.set(hex_val)
        for k, dot in self._accent_chips.items():
            dot.config(highlightbackground="white" if k == accent_key else COLORS["border"])

    def _apply_custom_hex(self):
        val = self._custom_accent_hex.get().strip()
        if not val.startswith("#") or len(val) not in (4, 7):
            messagebox.showwarning("Invalid Hex", "Please enter a valid hex color like #3fb950", parent=self.root)
            return
        self._custom_accent = val
        for dot in self._accent_chips.values():
            dot.config(highlightbackground=COLORS["border"])

    def _save_and_apply_customization(self):
        theme = self._custom_theme
        accent = self._custom_accent_hex.get().strip() or self._custom_accent
        family = self._custom_font_family.get()
        scale = self._custom_font_scale.get()
        density = self._custom_density.get()
        auto_push = 1 if self._custom_auto_push.get() else 0

        db.update_preferences(
            self.user["id"],
            theme=theme,
            accent_color=accent,
            font_family=family,
            font_scale=scale,
            ui_density=density,
            auto_push=auto_push,
        )

        apply_customization(
            theme=theme,
            accent=accent,
            font_family=family,
            font_scale=scale,
            ui_density=density,
        )

        messagebox.showinfo("Applied", "Interface customization applied successfully!", parent=self.root)
        self._rebuild_ui("customize")

    def _reset_customization(self):
        db.update_preferences(
            self.user["id"],
            theme="github_dark",
            accent_color="#3fb950",
            font_family="Segoe UI",
            font_scale="standard",
            ui_density="comfortable",
        )
        apply_customization("github_dark", "green", "Segoe UI", "standard", "comfortable")
        self._rebuild_ui("customize")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_initials(self) -> str:
        name = self.user.get("full_name") or self.user["username"]
        parts = name.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return name[:2].upper()

    def _do_logout(self):
        db.revoke_session_token(self.user["id"])
        self.root.destroy()
        self.on_logout()

    def run(self):
        self.root.mainloop()
