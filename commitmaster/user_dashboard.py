"""
CommitMaster — Main application dashboard (User view).
Shown after successful login. Includes sidebar nav, per-user settings,
commit history, and profile management.
"""
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Dict, Optional

from commitmaster.app_styles import COLORS, FONTS, SIZES, AVATAR_COLORS
from commitmaster import database as db


class UserDashboard:
    """
    Full-featured user dashboard window.
    on_logout() is called when the user chooses to log out.
    on_admin() is called when an admin wants to open the admin portal.
    """

    def __init__(self, user: Dict, on_logout: Callable, on_admin: Optional[Callable] = None):
        self.user = user
        self.on_logout = on_logout
        self.on_admin = on_admin
        self._active_nav = None
        self.root = tk.Tk()
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
        self._content_canvas.bind_all("<MouseWheel>",
                                      lambda e: self._content_canvas.yview_scroll(
                                          -1 * (e.delta // 120), "units"))

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
            ("📊", "Overview",     "overview"),
            ("📝", "My Commits",   "commits"),
            ("⚙️",  "Settings",    "settings"),
            ("👤", "My Profile",  "profile"),
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
            "overview": self._page_overview,
            "commits":  self._page_commits,
            "settings": self._page_settings,
            "profile":  self._page_profile,
        }
        if key in pages:
            pages[key]()

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

        for text, var in [
            ("Auto-commit without preview", self._auto_commit_var),
            ("Skip sensitive files (.env, .pem, etc.)", self._skip_sensitive_var),
            ("Show desktop notifications", self._notif_var),
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
        for var in self._pw_vars.values():
            var.set("")

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
