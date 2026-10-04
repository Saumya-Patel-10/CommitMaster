"""
CommitMaster — ADMIN APP (Your Personal Instance)
====================================================
This is YOUR app, Saumya. It is separate from the user download.

It combines everything in one unified window:
  MY WORKSPACE  →  Overview, My Commits, Settings, My Profile
  ADMIN CONTROL →  Dashboard, Users, Activity Log, Charts, Global Settings, My Settings

Run:  python admin_app.py
"""
import os
import sys
import json
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, Callable

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import database as db
from commitmaster.app_styles import COLORS, FONTS, SIZES, AVATAR_COLORS
from commitmaster.login_window import LoginWindow

_TOKEN_FILE = os.path.join(APP_DIR, ".admin_session")


# ── Token helpers ──────────────────────────────────────────────────────────────

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


# ── Entry point ────────────────────────────────────────────────────────────────

def launch_admin_app():
    db.init_db()

    token = _load_token()
    user = None
    if token:
        user = db.validate_session_token(token)

    if user and user.get("role") == "admin":
        _open_admin_window(dict(user))
    else:
        _clear_token()
        _open_admin_login()


def _open_admin_login():
    """Show the login screen; only admits admin-role accounts."""
    def on_success(user: dict):
        if user.get("role") != "admin":
            messagebox.showerror(
                "Access Denied",
                "This app is for administrators only.\n"
                "Please use the CommitMaster user app instead.",
            )
            _open_admin_login()
            return
        token = db.create_session_token(user["id"])
        _save_token(token)
        _open_admin_window(user)

    win = LoginWindow(on_success=on_success)
    win.run()


def _open_admin_window(user: dict):
    app = AdminApp(user)
    app.run()


# ── Unified Admin App Window ───────────────────────────────────────────────────

class AdminApp:
    """
    A single unified window combining:
      • MY WORKSPACE  — all personal user features (overview, commits, settings, profile)
      • ADMIN CONTROL — full admin features (users, logs, charts, global settings, my settings)
    """

    def __init__(self, user: Dict):
        self.user = user
        self.root = tk.Tk()
        self._setup_window()
        self._build_layout()
        self._nav_to("overview")

    # ── Window ────────────────────────────────────────────────────────────────

    def _setup_window(self):
        name = self.user.get("full_name") or self.user["username"]
        self.root.title(f"CommitMaster — Admin Workspace  ({name})")
        self.root.geometry("1200x760")
        self.root.minsize(1000, 640)
        self.root.configure(bg=COLORS["bg_darkest"])
        self.root.update_idletasks()
        w, h = 1200, 760
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")

    # ── Layout skeleton ───────────────────────────────────────────────────────

    def _build_layout(self):
        # Sidebar (wider to fit two sections)
        self._sidebar = tk.Frame(self.root, bg=COLORS["bg_sidebar"], width=240)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        self._main = tk.Frame(self.root, bg=COLORS["bg_dark"])
        self._main.pack(side="left", fill="both", expand=True)

        self._build_sidebar()
        self._build_header()

        # Scrollable content area
        outer = tk.Frame(self._main, bg=COLORS["bg_dark"])
        outer.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(outer, bg=COLORS["bg_dark"], highlightthickness=0)
        sb = tk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._cf = tk.Frame(self._canvas, bg=COLORS["bg_dark"])
        self._cw = self._canvas.create_window((0, 0), window=self._cf, anchor="nw")
        self._cf.bind("<Configure>",
                      lambda e: self._canvas.configure(
                          scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(self._cw, width=e.width))
        self._canvas.bind_all("<MouseWheel>",
                              lambda e: self._canvas.yview_scroll(
                                  -1 * (e.delta // 120), "units"))

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = self._sidebar

        # Logo
        logo_f = tk.Frame(sb, bg=COLORS["bg_sidebar"], height=64)
        logo_f.pack(fill="x")
        logo_f.pack_propagate(False)
        tk.Label(logo_f, text="⬡ CommitMaster",
                 font=FONTS["heading_sm"], fg=COLORS["accent"],
                 bg=COLORS["bg_sidebar"]).pack(side="left", padx=14, pady=18)
        # Admin badge
        tk.Label(logo_f, text=" ADMIN ", font=("Segoe UI", 8, "bold"),
                 fg=COLORS["bg_darkest"], bg=COLORS["admin"]).pack(
            side="right", padx=10, pady=20)

        tk.Frame(sb, height=1, bg=COLORS["border"]).pack(fill="x")

        # Avatar
        av_f = tk.Frame(sb, bg=COLORS["bg_sidebar"], pady=12)
        av_f.pack(fill="x", padx=14)
        color = self.user.get("avatar_color", AVATAR_COLORS[0])
        av = tk.Label(av_f, text=self._initials(), font=FONTS["heading_sm"],
                      bg=color, fg="white", width=4, height=2)
        av.pack(anchor="w")
        tk.Label(av_f, text=self.user.get("full_name") or self.user["username"],
                 font=FONTS["label_bold"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_sidebar"], wraplength=180).pack(anchor="w", pady=(4, 0))
        tk.Label(av_f, text="● Administrator", font=FONTS["caption"],
                 fg=COLORS["admin"], bg=COLORS["bg_sidebar"]).pack(anchor="w")

        tk.Frame(sb, height=1, bg=COLORS["border"]).pack(fill="x", pady=(8, 4))

        # ── MY WORKSPACE section ───────────────────────────────────────────────
        self._section_label(sb, "MY WORKSPACE")
        workspace_nav = [
            ("📊", "Overview",    "overview"),
            ("📝", "My Commits",  "commits"),
            ("⚙️",  "Settings",   "settings"),
            ("👤", "My Profile", "profile"),
        ]

        # ── ADMIN CONTROL section ──────────────────────────────────────────────
        admin_nav = [
            ("🛡", "Admin Dashboard", "admin_dashboard"),
            ("👥", "Users",           "users"),
            ("📋", "Activity Log",    "activity"),
            ("📈", "Usage Charts",    "charts"),
            ("🌐", "Global Settings", "global_settings"),
            ("🔑", "My Account",      "my_settings"),
        ]

        all_nav = [("workspace", workspace_nav), ("admin", admin_nav)]
        self._nav_buttons: Dict[str, tk.Button] = {}

        for section, items in all_nav:
            if section == "admin":
                tk.Frame(sb, height=1, bg=COLORS["border"]).pack(
                    fill="x", pady=(6, 4))
                self._section_label(sb, "ADMIN CONTROL")

            for icon, label, key in items:
                btn = tk.Button(
                    sb, text=f"  {icon}  {label}",
                    font=FONTS["label"], fg=COLORS["text_secondary"],
                    bg=COLORS["bg_sidebar"], relief="flat", bd=0,
                    cursor="hand2", anchor="w", padx=14, pady=9,
                    command=lambda k=key: self._nav_to(k))
                btn.pack(fill="x")
                self._nav_buttons[key] = btn

        # Spacer + logout
        tk.Frame(sb, bg=COLORS["bg_sidebar"]).pack(fill="both", expand=True)
        tk.Frame(sb, height=1, bg=COLORS["border"]).pack(fill="x")
        logout_btn = tk.Button(
            sb, text="  ⏻  Sign Out",
            font=FONTS["label"], fg=COLORS["text_secondary"],
            bg=COLORS["bg_sidebar"], relief="flat", bd=0,
            cursor="hand2", anchor="w", padx=14, pady=11,
            command=self._logout)
        logout_btn.pack(fill="x")
        logout_btn.bind("<Enter>",
                        lambda e: logout_btn.config(bg=COLORS["bg_medium"]))
        logout_btn.bind("<Leave>",
                        lambda e: logout_btn.config(bg=COLORS["bg_sidebar"]))

    def _section_label(self, parent, text: str):
        tk.Label(parent, text=f"  {text}",
                 font=("Segoe UI", 9, "bold"),
                 fg=COLORS["text_muted"], bg=COLORS["bg_sidebar"],
                 anchor="w").pack(fill="x", padx=4, pady=(4, 2))

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        self._header_bar = tk.Frame(self._main, bg=COLORS["bg_dark"], height=56)
        self._header_bar.pack(fill="x")
        self._header_bar.pack_propagate(False)
        # Dual accent: green left, orange right
        accent_bar = tk.Frame(self._main, height=2, bg=COLORS["bg_medium"])
        accent_bar.pack(fill="x")
        tk.Frame(accent_bar, height=2, bg=COLORS["accent"],
                 width=600).pack(side="left")
        tk.Frame(accent_bar, height=2, bg=COLORS["admin"]).pack(
            side="left", fill="x", expand=True)

        self._header_title = tk.Label(
            self._header_bar, text="Overview",
            font=FONTS["heading_md"], fg=COLORS["text_primary"],
            bg=COLORS["bg_dark"])
        self._header_title.pack(side="left", padx=24, pady=12)

        # Right side: section badge
        self._section_badge = tk.Label(
            self._header_bar, text="  MY WORKSPACE  ",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS["bg_darkest"], bg=COLORS["accent"])
        self._section_badge.pack(side="right", padx=16, pady=18)

    # ── Navigation ────────────────────────────────────────────────────────────

    _WORKSPACE_KEYS = {"overview", "commits", "settings", "profile"}
    _ADMIN_KEYS = {"admin_dashboard", "users", "activity",
                   "charts", "global_settings", "my_settings"}

    _TITLES = {
        "overview":        "Overview",
        "commits":         "My Commits",
        "settings":        "CommitMaster Settings",
        "profile":         "My Profile",
        "admin_dashboard": "Admin Dashboard",
        "users":           "User Management",
        "activity":        "Activity Log",
        "charts":          "Usage Charts",
        "global_settings": "Global Settings",
        "my_settings":     "My Account",
    }

    def _nav_to(self, key: str):
        is_admin = key in self._ADMIN_KEYS
        accent = COLORS["admin"] if is_admin else COLORS["accent"]

        # Update nav button colours
        for k, btn in self._nav_buttons.items():
            if k == key:
                btn.config(bg=COLORS["bg_medium"], fg=accent)
            else:
                btn.config(bg=COLORS["bg_sidebar"], fg=COLORS["text_secondary"])

        self._header_title.config(text=self._TITLES.get(key, key))
        self._section_badge.config(
            text="  ADMIN CONTROL  " if is_admin else "  MY WORKSPACE  ",
            bg=accent)

        # Clear and render
        for w in self._cf.winfo_children():
            w.destroy()

        pages = {
            "overview":        self._page_overview,
            "commits":         self._page_commits,
            "settings":        self._page_settings,
            "profile":         self._page_profile,
            "admin_dashboard": self._page_admin_dashboard,
            "users":           self._page_users,
            "activity":        self._page_activity,
            "charts":          self._page_charts,
            "global_settings": self._page_global_settings,
            "my_settings":     self._page_my_settings,
        }
        if key in pages:
            pages[key]()

    # ── Shared widget helpers ─────────────────────────────────────────────────

    def _pad(self) -> tk.Frame:
        f = tk.Frame(self._cf, bg=COLORS["bg_dark"], padx=24, pady=20)
        f.pack(fill="both", expand=True)
        return f

    def _card(self, parent, **kw) -> tk.Frame:
        return tk.Frame(parent, bg=COLORS["bg_card"],
                        highlightbackground=COLORS["border"],
                        highlightthickness=1, **kw)

    def _stat_card(self, parent, title: str, value: str,
                   color: str, icon: str, subtitle: str = ""):
        card = self._card(parent)
        card.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        inner = tk.Frame(card, bg=COLORS["bg_card"], padx=18, pady=16)
        inner.pack(fill="both", expand=True)
        tk.Frame(card, height=3, bg=color).place(relx=0, rely=0, relwidth=1)
        tk.Label(inner, text=icon, font=("Segoe UI Emoji", 20),
                 fg=color, bg=COLORS["bg_card"]).pack(anchor="w")
        tk.Label(inner, text=value, font=FONTS["heading_lg"],
                 fg=color, bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 0))
        tk.Label(inner, text=title, font=FONTS["label_bold"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
        if subtitle:
            tk.Label(inner, text=subtitle, font=FONTS["caption"],
                     fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w")

    def _section_hdr(self, parent, text: str, pady=(16, 8)):
        tk.Label(parent, text=text, font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(
            anchor="w", pady=pady)

    def _entry_row(self, parent, label: str, var: tk.StringVar,
                   width: int = 14, show: str = "") -> tk.Entry:
        f = tk.Frame(parent, bg=COLORS["bg_card"])
        f.pack(fill="x", pady=(0, 10))
        tk.Label(f, text=label, font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                 width=width, anchor="w").pack(side="left")
        e = tk.Entry(f, textvariable=var, font=FONTS["body_md"],
                     bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                     relief="flat", highlightthickness=1,
                     highlightbackground=COLORS["border"],
                     insertbackground=COLORS["text_primary"],
                     show=show)
        e.pack(side="left", fill="x", expand=True, ipady=7)
        return e

    def _primary_btn(self, parent, text: str, cmd, color=None) -> tk.Button:
        c = color or COLORS["accent"]
        btn = tk.Button(parent, text=text, font=FONTS["heading_sm"],
                        fg="white", bg=c, activeforeground="white",
                        activebackground=c, relief="flat", bd=0,
                        cursor="hand2", padx=18, pady=10, command=cmd)
        btn.bind("<Enter>", lambda e: btn.config(bg=self._darken(c)))
        btn.bind("<Leave>", lambda e: btn.config(bg=c))
        return btn

    @staticmethod
    def _darken(hex_color: str) -> str:
        """Produce a slightly darker version of a hex color."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r, g, b = max(0, r - 25), max(0, g - 25), max(0, b - 25)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _bar_chart(self, parent, data: list, width=800, height=160,
                   value_key="commits_made", color=None):
        color = color or COLORS["accent"]
        canvas = tk.Canvas(parent, width=width, height=height,
                           bg=COLORS["bg_card"], highlightthickness=0)
        canvas.pack(anchor="w", pady=(0, 8))
        if not data:
            canvas.create_text(width // 2, height // 2, text="No data yet",
                                fill=COLORS["text_muted"], font=FONTS["body_sm"])
            return
        max_v = max((r.get(value_key, 0) for r in data), default=1) or 1
        n = len(data)
        bar_w = max(4, (width - 40) // max(n, 1) - 2)
        pad_l, pad_b = 20, 30
        for i, row in enumerate(data):
            val = row.get(value_key, 0)
            x0 = pad_l + i * ((width - 40) // max(n, 1))
            bh = int((val / max_v) * (height - pad_b - 10))
            y1 = height - pad_b
            c = color if val > 0 else COLORS["border"]
            canvas.create_rectangle(x0, y1 - bh, x0 + bar_w, y1,
                                    fill=c, outline="")
            if n <= 16 or i % 2 == 0:
                canvas.create_text(x0 + bar_w // 2, height - 12,
                                   text=row.get("date", "")[5:],
                                   fill=COLORS["text_muted"], font=FONTS["caption"])

    # ═══════════════════════════════════════════════════════════════════════════
    # MY WORKSPACE PAGES
    # ═══════════════════════════════════════════════════════════════════════════

    def _page_overview(self):
        p = self._pad()
        name = self.user.get("full_name") or self.user["username"]
        tk.Label(p, text=f"Welcome back, {name}! 👋",
                 font=FONTS["heading_lg"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(p, text="Your personal coding activity and admin overview.",
                 font=FONTS["body_md"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 20))

        # My personal stats
        self._section_hdr(p, "MY ACTIVITY", (0, 8))
        activity = db.get_activity_log(self.user["id"], limit=1000)
        usage = db.get_usage_stats(self.user["id"], days=30)
        row1 = tk.Frame(p, bg=COLORS["bg_dark"])
        row1.pack(fill="x", pady=(0, 16))
        self._stat_card(row1, "My Commits",   str(len(activity)),         COLORS["success"], "📝")
        self._stat_card(row1, "Active Days",  str(len(usage)),            COLORS["info"],    "📅")
        self._stat_card(row1, "Repositories", str(len(set(
            r["repo_name"] for r in activity))),                          COLORS["warning"], "📁")

        # System-wide admin stats
        self._section_hdr(p, "SYSTEM OVERVIEW", (8, 8))
        stats = db.get_dashboard_stats()
        row2 = tk.Frame(p, bg=COLORS["bg_dark"])
        row2.pack(fill="x", pady=(0, 20))
        self._stat_card(row2, "Total Users",   str(stats["total_users"]),       COLORS["info"],  "👥")
        self._stat_card(row2, "Active Today",  str(stats["active_today"]),      COLORS["success"],"🟢")
        self._stat_card(row2, "System Commits",str(stats["total_commits"]),     COLORS["accent"],"📊")
        self._stat_card(row2, "This Week",     str(stats["commits_this_week"]), COLORS["admin"], "📈")

        # My 30-day chart
        self._section_hdr(p, "MY COMMIT ACTIVITY — LAST 30 DAYS", (0, 8))
        self._bar_chart(p, usage, width=760, height=150)

        # Recent commits
        self._section_hdr(p, "MY RECENT COMMITS", (8, 8))
        if not activity:
            tk.Label(p, text="No commits recorded yet. Start coding!",
                     font=FONTS["body_md"], fg=COLORS["text_muted"],
                     bg=COLORS["bg_dark"]).pack(anchor="w")
        else:
            for entry in activity[:6]:
                self._commit_row(p, entry)

    def _commit_row(self, parent, entry: dict):
        row = tk.Frame(parent, bg=COLORS["bg_card"],
                       highlightbackground=COLORS["border"], highlightthickness=1)
        row.pack(fill="x", pady=3)
        inner = tk.Frame(row, bg=COLORS["bg_card"], padx=14, pady=10)
        inner.pack(fill="x")
        tk.Label(inner, text=entry["repo_name"][:20],
                 font=FONTS["mono_sm"], fg=COLORS["accent"],
                 bg=COLORS["bg_medium"], padx=6, pady=2).pack(side="left")
        msg = entry["commit_msg"][:80] + ("…" if len(entry["commit_msg"]) > 80 else "")
        tk.Label(inner, text=msg, font=FONTS["body_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"],
                 anchor="w").pack(side="left", padx=10, fill="x", expand=True)
        tk.Label(inner, text=entry["committed_at"][:16],
                 font=FONTS["caption"], fg=COLORS["text_muted"],
                 bg=COLORS["bg_card"]).pack(side="right")

    def _page_commits(self):
        p = self._pad()
        tk.Label(p, text="My Commit History", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(p, text="All commits you've made through CommitMaster.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))

        activity = db.get_activity_log(self.user["id"], limit=500)
        if not activity:
            tk.Label(p, text="No commits yet.",
                     font=FONTS["body_md"], fg=COLORS["text_muted"],
                     bg=COLORS["bg_dark"]).pack(anchor="w", pady=20)
            return
        hdr = tk.Frame(p, bg=COLORS["bg_medium"])
        hdr.pack(fill="x")
        for col, w in [("Repository", 18), ("Commit Message", 48),
                       ("Files", 8), ("Status", 12), ("Date", 16)]:
            tk.Label(hdr, text=col, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                     width=w, anchor="w", padx=8, pady=6).pack(side="left")
        for entry in activity:
            row = tk.Frame(p, bg=COLORS["bg_card"])
            row.pack(fill="x")
            tk.Frame(p, height=1, bg=COLORS["border"]).pack(fill="x")
            status_color = {
                "committed": COLORS["success"],
                "skipped":   COLORS["warning"],
                "failed":    COLORS["error"],
            }.get(entry.get("status", "committed"), COLORS["text_secondary"])
            for text, w, fc in [
                (entry["repo_name"][:18], 18, COLORS["accent"]),
                (entry["commit_msg"][:48], 48, COLORS["text_primary"]),
                (str(entry.get("files_count", 0)), 8, COLORS["text_secondary"]),
                (entry.get("status", "committed"), 12, status_color),
                (entry["committed_at"][:16], 16, COLORS["text_muted"]),
            ]:
                tk.Label(row, text=text, font=FONTS["body_sm"],
                         fg=fc, bg=COLORS["bg_card"],
                         width=w, anchor="w", padx=8, pady=8).pack(side="left")

    def _page_settings(self):
        """Personal CommitMaster settings (watched apps, folders, AI config)."""
        p = self._pad()
        prefs = db.get_preferences(self.user["id"]) or {}
        try:
            watched = json.loads(prefs.get("watched_apps",
                                           '["Code.exe","Cursor.exe"]'))
        except Exception:
            watched = []
        try:
            proj_dirs = json.loads(prefs.get("projects_dirs", "[]"))
        except Exception:
            proj_dirs = []

        tk.Label(p, text="CommitMaster Settings", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(p, text="Your personal monitoring preferences.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))

        # Session card
        sess_card = self._card(p, padx=20, pady=16)
        sess_card.pack(fill="x", pady=(0, 12))
        tk.Label(sess_card, text="Session Monitoring",
                 font=FONTS["heading_sm"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")

        self._auto_var  = tk.BooleanVar(value=bool(prefs.get("auto_commit", 0)))
        self._skip_var  = tk.BooleanVar(value=bool(prefs.get("skip_sensitive", 1)))
        self._notif_var = tk.BooleanVar(value=bool(prefs.get("notifications", 1)))
        for text, var in [
            ("Auto-commit without preview", self._auto_var),
            ("Skip sensitive files (.env, .pem, etc.)", self._skip_var),
            ("Show desktop notifications", self._notif_var),
        ]:
            tk.Checkbutton(sess_card, text=text, variable=var,
                           font=FONTS["body_md"], fg=COLORS["text_primary"],
                           bg=COLORS["bg_card"], selectcolor=COLORS["bg_input"],
                           activebackground=COLORS["bg_card"],
                           activeforeground=COLORS["text_primary"]).pack(
                anchor="w", pady=4)

        gf = tk.Frame(sess_card, bg=COLORS["bg_card"])
        gf.pack(anchor="w", pady=(8, 0))
        tk.Label(gf, text="Grace period (seconds): ",
                 font=FONTS["body_md"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(side="left")
        self._grace_var = tk.StringVar(value=str(prefs.get("session_end_grace", 120)))
        tk.Entry(gf, textvariable=self._grace_var, width=6, font=FONTS["body_md"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                 relief="flat", highlightthickness=1,
                 highlightbackground=COLORS["border"]).pack(side="left", ipady=4)

        # AI card
        ai_card = self._card(p, padx=20, pady=16)
        ai_card.pack(fill="x", pady=(0, 12))
        tk.Label(ai_card, text="AI / LM Studio",
                 font=FONTS["heading_sm"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._ai_url_var   = tk.StringVar(value=prefs.get("ai_base_url", "http://localhost:1234/v1"))
        self._ai_model_var = tk.StringVar(value=prefs.get("ai_model", ""))
        self._entry_row(ai_card, "Server URL:", self._ai_url_var, width=16)
        self._entry_row(ai_card, "Model name:", self._ai_model_var, width=16)

        # Folders card
        dirs_card = self._card(p, padx=20, pady=16)
        dirs_card.pack(fill="x", pady=(0, 12))
        tk.Label(dirs_card, text="Project Folders",
                 font=FONTS["heading_sm"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._dirs_lb = tk.Listbox(dirs_card, font=FONTS["mono"],
                                    bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                                    selectbackground=COLORS["accent"],
                                    relief="flat", height=4, bd=0)
        for d in proj_dirs:
            self._dirs_lb.insert("end", d)
        self._dirs_lb.pack(fill="x", pady=(8, 0))
        btn_f = tk.Frame(dirs_card, bg=COLORS["bg_card"])
        btn_f.pack(anchor="w", pady=(6, 0))
        for text, cmd in [("＋ Add", self._add_dir), ("✕ Remove", self._rm_dir)]:
            tk.Button(btn_f, text=text, font=FONTS["label"],
                      fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                      relief="flat", bd=0, cursor="hand2",
                      padx=10, pady=4, command=cmd).pack(side="left", padx=(0, 6))

        self._primary_btn(p, "  💾  Save Settings",
                          self._save_settings).pack(anchor="w", pady=(8, 0))

    def _add_dir(self):
        d = filedialog.askdirectory(title="Select Project Folder",
                                    parent=self.root)
        if d:
            self._dirs_lb.insert("end", d)

    def _rm_dir(self):
        sel = self._dirs_lb.curselection()
        if sel:
            self._dirs_lb.delete(sel[0])

    def _save_settings(self):
        dirs = list(self._dirs_lb.get(0, "end"))
        db.update_preferences(
            self.user["id"],
            auto_commit=int(self._auto_var.get()),
            skip_sensitive=int(self._skip_var.get()),
            notifications=int(self._notif_var.get()),
            session_end_grace=int(self._grace_var.get() or 120),
            ai_base_url=self._ai_url_var.get(),
            ai_model=self._ai_model_var.get(),
            projects_dirs=json.dumps(dirs),
        )
        messagebox.showinfo("Saved", "Settings saved!", parent=self.root)

    def _page_profile(self):
        p = self._pad()
        tk.Label(p, text="My Profile", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(p, text="Your public profile information.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))

        # Avatar colour picker
        av_card = self._card(p, padx=20, pady=16)
        av_card.pack(fill="x", pady=(0, 12))
        self._prof_color_var = tk.StringVar(
            value=self.user.get("avatar_color", AVATAR_COLORS[0]))
        av_row = tk.Frame(av_card, bg=COLORS["bg_card"])
        av_row.pack(fill="x")
        self._prof_av = tk.Label(av_row, text=self._initials(),
                                 font=FONTS["heading_lg"],
                                 bg=self._prof_color_var.get(),
                                 fg="white", width=4, height=2)
        self._prof_av.pack(side="left", padx=(0, 16))
        swatch_col = tk.Frame(av_row, bg=COLORS["bg_card"])
        swatch_col.pack(side="left")
        tk.Label(swatch_col, text="Avatar Color", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w")
        sw_row = tk.Frame(swatch_col, bg=COLORS["bg_card"])
        sw_row.pack(anchor="w", pady=(6, 0))
        for color in AVATAR_COLORS:
            sw = tk.Label(sw_row, text="  ", bg=color, width=3,
                          cursor="hand2", highlightthickness=2,
                          highlightbackground=COLORS["border"])
            sw.pack(side="left", padx=3)
            sw.bind("<Button-1>",
                    lambda e, c=color: (
                        self._prof_color_var.set(c),
                        self._prof_av.config(bg=c)))

        # Info card
        info_card = self._card(p, padx=20, pady=16)
        info_card.pack(fill="x", pady=(0, 12))
        self._prof_vars = {}
        for label, key, default in [
            ("Full Name", "full_name", self.user.get("full_name", "")),
            ("Email",     "email",     self.user.get("email", "")),
        ]:
            var = tk.StringVar(value=default)
            self._prof_vars[key] = var
            self._entry_row(info_card, label, var)

        bio_f = tk.Frame(info_card, bg=COLORS["bg_card"])
        bio_f.pack(fill="x", pady=(0, 10))
        tk.Label(bio_f, text="Bio", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                 width=14, anchor="w").pack(side="left", anchor="n")
        self._prof_bio = tk.Text(bio_f, font=FONTS["body_md"],
                                 bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                                 relief="flat", height=3, bd=0, highlightthickness=1,
                                 highlightbackground=COLORS["border"],
                                 insertbackground=COLORS["text_primary"])
        self._prof_bio.insert("1.0", self.user.get("bio") or "")
        self._prof_bio.pack(side="left", fill="x", expand=True)

        self._primary_btn(p, "  💾  Save Profile",
                          self._save_profile).pack(anchor="w", pady=(0, 20))

    def _save_profile(self):
        db.update_user(
            self.user["id"],
            full_name=self._prof_vars["full_name"].get().strip(),
            email=self._prof_vars["email"].get().strip(),
            bio=self._prof_bio.get("1.0", "end-1c"),
            avatar_color=self._prof_color_var.get(),
        )
        updated = db.get_user(self.user["id"])
        if updated:
            self.user.update(updated)
        messagebox.showinfo("Saved", "Profile updated!", parent=self.root)

    # ═══════════════════════════════════════════════════════════════════════════
    # ADMIN CONTROL PAGES  (imported logic from AdminPortal)
    # ═══════════════════════════════════════════════════════════════════════════

    def _page_admin_dashboard(self):
        p = self._pad()
        tk.Label(p, text="Admin Dashboard", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        from datetime import datetime as dt
        tk.Label(p, text=dt.now().strftime("%A, %B %d %Y"),
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 20))

        stats = db.get_dashboard_stats()
        row = tk.Frame(p, bg=COLORS["bg_dark"])
        row.pack(fill="x")
        self._stat_card(row, "Total Users",   str(stats["total_users"]),
                        COLORS["info"],    "👥", f"{stats['total_admins']} admins")
        self._stat_card(row, "Active Today",  str(stats["active_today"]),
                        COLORS["success"], "🟢", "unique logins")
        self._stat_card(row, "Total Commits", str(stats["total_commits"]),
                        COLORS["accent"],  "📝", "all time")
        self._stat_card(row, "This Week",     str(stats["commits_this_week"]),
                        COLORS["admin"],   "📈", "7-day window")

        self._section_hdr(p, "TOP COMMITTERS")
        top_card = self._card(p, padx=20, pady=16)
        top_card.pack(fill="x", pady=(0, 20))
        if not stats["top_committers"]:
            tk.Label(top_card, text="No commit data yet.",
                     font=FONTS["body_sm"], fg=COLORS["text_muted"],
                     bg=COLORS["bg_card"]).pack(anchor="w")
        for i, tc in enumerate(stats["top_committers"], 1):
            rf = tk.Frame(top_card, bg=COLORS["bg_card"])
            rf.pack(fill="x", pady=4)
            medals = [COLORS["admin"], COLORS["warning"], COLORS["info"],
                      COLORS["text_secondary"], COLORS["text_muted"]]
            tk.Label(rf, text=f"#{i}", font=FONTS["label_bold"],
                     fg=medals[i - 1], bg=COLORS["bg_card"], width=3).pack(side="left")
            tk.Label(rf, text=tc["username"], font=FONTS["body_md"],
                     fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(
                side="left", padx=8)
            tk.Label(rf, text=f"{tc['commits']} commits",
                     font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                     bg=COLORS["bg_card"]).pack(side="right")

        self._section_hdr(p, "SYSTEM ACTIVITY — LAST 14 DAYS")
        usage = db.get_usage_stats(days=14)
        self._multi_bar_chart(p, usage, width=820, height=180)

    def _multi_bar_chart(self, parent, data: list, width=820, height=180):
        canvas = tk.Canvas(parent, width=width, height=height,
                           bg=COLORS["bg_card"], highlightthickness=0)
        canvas.pack(anchor="w", pady=(0, 8))
        if not data:
            canvas.create_text(width // 2, height // 2, text="No data",
                                fill=COLORS["text_muted"], font=FONTS["body_sm"])
            return
        n = len(data)
        pad_l, pad_b = 20, 30
        avail_w = width - pad_l - 20
        grp = avail_w // max(n, 1)
        bw = max(3, grp // 3 - 2)
        max_val = max(
            max((r.get("commits_made", 0) for r in data), default=1),
            max((r.get("sessions", 0) for r in data), default=1)
        ) or 1
        ch = height - pad_b - 10
        for i, row in enumerate(data):
            x0 = pad_l + i * grp
            y1 = height - pad_b
            for j, (key, color) in enumerate([
                ("commits_made", COLORS["chart_commits"]),
                ("sessions",     COLORS["chart_sessions"]),
            ]):
                v = row.get(key, 0)
                bh = int((v / max_val) * ch)
                xj = x0 + j * (bw + 2)
                canvas.create_rectangle(xj, y1 - bh, xj + bw, y1,
                                        fill=color, outline="")
            if n <= 14 or i % 2 == 0:
                canvas.create_text(x0 + grp // 2, height - 12,
                                   text=row["date"][5:],
                                   fill=COLORS["text_muted"], font=FONTS["caption"])
        # Legend
        lx = width - 180
        for color, label in [(COLORS["chart_commits"], "Commits"),
                              (COLORS["chart_sessions"], "Sessions")]:
            canvas.create_rectangle(lx, 8, lx + 12, 18, fill=color, outline="")
            canvas.create_text(lx + 16, 13, text=label,
                                fill=COLORS["text_secondary"],
                                font=FONTS["caption"], anchor="w")
            lx += 80

    def _page_users(self):
        from commitmaster.admin_portal import AdminPortal, _UserDialog
        p = self._pad()
        top = tk.Frame(p, bg=COLORS["bg_dark"])
        top.pack(fill="x", pady=(0, 14))
        tk.Label(top, text="User Management", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(side="left")
        tk.Button(top, text="  ＋ Add User",
                  font=FONTS["label_bold"], fg="white",
                  bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                  activeforeground="white", relief="flat", bd=0,
                  cursor="hand2", padx=14, pady=6,
                  command=lambda: self._add_user(p)).pack(side="right")

        sf = tk.Frame(p, bg=COLORS["bg_dark"])
        sf.pack(fill="x", pady=(0, 10))
        tk.Label(sf, text="🔍", font=FONTS["body_md"],
                 fg=COLORS["text_muted"], bg=COLORS["bg_dark"]).pack(side="left")
        self._user_search = tk.StringVar()
        self._user_search.trace("w", lambda *a: self._refresh_users_list(p))
        tk.Entry(sf, textvariable=self._user_search, font=FONTS["body_md"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                 relief="flat", highlightthickness=1,
                 highlightbackground=COLORS["border"],
                 width=30).pack(side="left", padx=8, ipady=6)

        hdr = tk.Frame(p, bg=COLORS["bg_medium"])
        hdr.pack(fill="x")
        for col, w in [("User", 30), ("Email", 28), ("Role", 10),
                       ("Status", 10), ("Commits", 10), ("Actions", 22)]:
            tk.Label(hdr, text=col, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                     width=w, anchor="w", padx=8, pady=6).pack(side="left")

        self._users_list_frame = tk.Frame(p, bg=COLORS["bg_dark"])
        self._users_list_frame.pack(fill="x")
        self._users_page_ref = p
        self._refresh_users_list(p)

    def _refresh_users_list(self, p=None):
        container = self._users_list_frame
        for w in container.winfo_children():
            w.destroy()
        query = self._user_search.get().lower() if hasattr(self, "_user_search") else ""
        for user in db.get_all_users():
            if query and not any(query in str(user.get(f, "")).lower()
                                 for f in ["username", "email", "full_name"]):
                continue
            self._user_row(container, user)

    def _user_row(self, parent, user: Dict):
        row = tk.Frame(parent, bg=COLORS["bg_card"])
        row.pack(fill="x")
        tk.Frame(parent, height=1, bg=COLORS["border"]).pack(fill="x")
        row.bind("<Enter>", lambda e: row.config(bg=COLORS["bg_card_hover"]))
        row.bind("<Leave>", lambda e: row.config(bg=COLORS["bg_card"]))

        color = user.get("avatar_color", AVATAR_COLORS[0])
        name = user.get("full_name") or user["username"]
        initials = (name.split()[0][0] + name.split()[-1][0]
                    if len(name.split()) >= 2 else name[:2]).upper()
        tk.Label(row, text=initials, bg=color, fg="white",
                 font=("Segoe UI", 9, "bold"), width=3,
                 padx=4, pady=4).pack(side="left", padx=(8, 0), pady=6)

        nf = tk.Frame(row, bg=COLORS["bg_card"], width=180)
        nf.pack(side="left", padx=8, pady=6)
        nf.pack_propagate(False)
        tk.Label(nf, text=name, font=FONTS["label_bold"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"],
                 anchor="w").pack(anchor="w")
        tk.Label(nf, text=f"@{user['username']}", font=FONTS["caption"],
                 fg=COLORS["text_muted"], bg=COLORS["bg_card"],
                 anchor="w").pack(anchor="w")

        tk.Label(row, text=user.get("email", ""), font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                 width=26, anchor="w").pack(side="left", padx=4)
        rc = COLORS["admin"] if user["role"] == "admin" else COLORS["info"]
        tk.Label(row, text=user["role"].capitalize(), font=FONTS["label"],
                 fg=rc, bg=COLORS["bg_card"], width=10).pack(side="left")
        sc = COLORS["success"] if user["is_active"] else COLORS["error"]
        tk.Label(row, text="● Active" if user["is_active"] else "● Disabled",
                 font=FONTS["label"], fg=sc, bg=COLORS["bg_card"],
                 width=10).pack(side="left")
        tk.Label(row, text=str(user.get("total_commits", 0)),
                 font=FONTS["body_sm"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"], width=10).pack(side="left")

        af = tk.Frame(row, bg=COLORS["bg_card"])
        af.pack(side="left", padx=8)
        for text, cmd in [
            ("✏ Edit",   lambda u=user: self._edit_user(u)),
        ]:
            tk.Button(af, text=text, font=FONTS["label"],
                      fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                      relief="flat", bd=0, cursor="hand2",
                      padx=8, pady=3, command=cmd).pack(side="left", padx=2)
        if user["id"] != self.user["id"]:
            ttxt = "🔒 Disable" if user["is_active"] else "🔓 Enable"
            tk.Button(af, text=ttxt, font=FONTS["label"],
                      fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                      relief="flat", bd=0, cursor="hand2",
                      padx=8, pady=3,
                      command=lambda u=user: self._toggle_user(u)).pack(
                side="left", padx=2)
            tk.Button(af, text="🗑 Delete", font=FONTS["label"],
                      fg=COLORS["error"], bg="#3a1010",
                      relief="flat", bd=0, cursor="hand2",
                      padx=8, pady=3,
                      command=lambda u=user: self._delete_user(u)).pack(
                side="left", padx=2)

    def _add_user(self, p):
        from commitmaster.admin_portal import _UserDialog
        dlg = _UserDialog(self.root, "Add User")
        if dlg.result:
            d = dlg.result
            uid = db.create_user(d["username"], d["email"],
                                  d["full_name"], d["password"], d["role"])
            if uid:
                messagebox.showinfo("Success",
                                    f"User '{d['username']}' created.",
                                    parent=self.root)
                self._refresh_users_list()
            else:
                messagebox.showerror("Error",
                                     "Username or email already exists.",
                                     parent=self.root)

    def _edit_user(self, user: Dict):
        from commitmaster.admin_portal import _UserDialog
        dlg = _UserDialog(self.root, "Edit User", user)
        if dlg.result:
            d = dlg.result
            db.update_user(user["id"], full_name=d["full_name"],
                           email=d["email"], role=d["role"])
            if d.get("password"):
                db.change_password(user["id"], d["password"])
            messagebox.showinfo("Saved", "User updated.", parent=self.root)
            self._refresh_users_list()

    def _toggle_user(self, user: Dict):
        new_state = 0 if user["is_active"] else 1
        label = "Disable" if new_state == 0 else "Enable"
        if messagebox.askyesno("Confirm",
                               f"{label} user '{user['username']}'?",
                               parent=self.root):
            db.update_user(user["id"], is_active=new_state)
            self._refresh_users_list()

    def _delete_user(self, user: Dict):
        if messagebox.askyesno(
            "Confirm Delete",
            f"Permanently delete '{user['username']}' and all their data?\n"
            "This cannot be undone.",
            parent=self.root
        ):
            db.hard_delete_user(user["id"])
            self._refresh_users_list()

    def _page_activity(self):
        p = self._pad()
        tk.Label(p, text="System Activity Log", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(p, text="All commits across all users.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))
        activity = db.get_activity_log(limit=200)
        hdr = tk.Frame(p, bg=COLORS["bg_medium"])
        hdr.pack(fill="x")
        for col, w in [("User", 16), ("Repository", 18),
                       ("Commit Message", 38), ("Files", 7), ("Date", 16)]:
            tk.Label(hdr, text=col, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                     width=w, anchor="w", padx=6, pady=6).pack(side="left")
        if not activity:
            tk.Label(p, text="No activity yet.",
                     font=FONTS["body_md"], fg=COLORS["text_muted"],
                     bg=COLORS["bg_dark"]).pack(anchor="w", pady=20)
            return
        for entry in activity:
            row = tk.Frame(p, bg=COLORS["bg_card"])
            row.pack(fill="x")
            tk.Frame(p, height=1, bg=COLORS["border"]).pack(fill="x")
            row.bind("<Enter>", lambda e, r=row: r.config(bg=COLORS["bg_card_hover"]))
            row.bind("<Leave>", lambda e, r=row: r.config(bg=COLORS["bg_card"]))
            color = entry.get("avatar_color", AVATAR_COLORS[0])
            tk.Label(row, text=(entry.get("username") or "?")[:2].upper(),
                     bg=color, fg="white", font=FONTS["caption"],
                     width=2, padx=3, pady=3).pack(side="left", padx=(6, 0), pady=5)
            for text, w, fc in [
                (entry.get("username", ""), 14, COLORS["text_primary"]),
                (entry["repo_name"][:18], 18, COLORS["accent"]),
                (entry["commit_msg"][:38], 38, COLORS["text_primary"]),
                (str(entry.get("files_count", 0)), 7, COLORS["text_secondary"]),
                (entry["committed_at"][:16], 16, COLORS["text_muted"]),
            ]:
                tk.Label(row, text=text, font=FONTS["body_sm"],
                         fg=fc, bg=COLORS["bg_card"],
                         width=w, anchor="w", padx=4, pady=7).pack(side="left")

    def _page_charts(self):
        p = self._pad()
        tk.Label(p, text="Usage Analytics", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(p, text="System-wide usage across all users.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 20))

        self._section_hdr(p, "ACTIVITY — LAST 30 DAYS", (0, 8))
        self._multi_bar_chart(p, db.get_usage_stats(days=30), width=900, height=200)

        self._section_hdr(p, "COMMITS PER USER", (16, 8))
        users = db.get_all_users()
        if users:
            self._user_bar_chart(p, users)

        self._section_hdr(p, "DAILY BREAKDOWN — LAST 7 DAYS", (16, 8))
        hdr = tk.Frame(p, bg=COLORS["bg_medium"])
        hdr.pack(fill="x")
        for col, w in [("Date", 20), ("Sessions", 15),
                       ("Commits", 15), ("Active Users", 15)]:
            tk.Label(hdr, text=col, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                     width=w, anchor="w", padx=8, pady=6).pack(side="left")
        for row_data in reversed(db.get_usage_stats(days=7)):
            row = tk.Frame(p, bg=COLORS["bg_card"])
            row.pack(fill="x")
            tk.Frame(p, height=1, bg=COLORS["border"]).pack(fill="x")
            for val, w in [
                (row_data["date"], 20),
                (str(row_data.get("sessions", 0)), 15),
                (str(row_data.get("commits_made", 0)), 15),
                (str(row_data.get("active_users", 0)), 15),
            ]:
                tk.Label(row, text=val, font=FONTS["body_sm"],
                         fg=COLORS["text_primary"], bg=COLORS["bg_card"],
                         width=w, anchor="w", padx=8, pady=7).pack(side="left")

    def _user_bar_chart(self, parent, users: list):
        canvas = tk.Canvas(parent, width=900, height=160,
                           bg=COLORS["bg_card"], highlightthickness=0)
        canvas.pack(anchor="w", pady=(0, 8))
        data = sorted(
            [(u["username"][:12], u.get("total_commits", 0)) for u in users],
            key=lambda x: x[1], reverse=True)[:12]
        if not data:
            return
        max_v = max(c for _, c in data) or 1
        n = len(data)
        bw = min(50, (880 // n) - 4)
        for i, (name, val) in enumerate(data):
            x0 = 20 + i * (880 // n)
            bh = int((val / max_v) * 110)
            y1 = 120
            c = AVATAR_COLORS[i % len(AVATAR_COLORS)]
            canvas.create_rectangle(x0, y1 - bh, x0 + bw, y1,
                                    fill=c, outline="")
            if val > 0:
                canvas.create_text(x0 + bw // 2, y1 - bh - 10,
                                    text=str(val), fill=c, font=FONTS["caption"])
            canvas.create_text(x0 + bw // 2, y1 + 14,
                                text=name, fill=COLORS["text_muted"],
                                font=FONTS["caption"])

    def _page_global_settings(self):
        p = self._pad()
        tk.Label(p, text="Global Settings", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(p, text="Defaults applied to all new users.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))
        card = self._card(p, padx=24, pady=20)
        card.pack(fill="x")
        self._global_vars = {}
        conn = db.get_conn()
        for key, label, default in [
            ("default_grace_seconds", "Default Grace Period (seconds)", "120"),
            ("default_ai_url",        "Default AI Server URL", "http://localhost:1234/v1"),
            ("max_users",             "Max Users (0 = unlimited)", "0"),
            ("app_name",              "Application Name", "CommitMaster"),
        ]:
            cur = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            val = row[0] if row else default
            var = tk.StringVar(value=val)
            self._global_vars[key] = var
            self._entry_row(card, label, var, width=32)

        self._primary_btn(p, "  💾  Save Global Settings",
                          self._save_global,
                          color=COLORS["admin"]).pack(anchor="w", pady=(16, 0))

    def _save_global(self):
        from datetime import datetime as dt
        conn = db.get_conn()
        now = dt.now().strftime("%Y-%m-%d %H:%M:%S")
        for key, var in self._global_vars.items():
            conn.execute("""
                INSERT INTO system_settings (key, value, updated_at, updated_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                    updated_at=excluded.updated_at, updated_by=excluded.updated_by
            """, (key, var.get(), now, self.user["id"]))
        conn.commit()
        messagebox.showinfo("Saved", "Global settings saved!", parent=self.root)

    def _page_my_settings(self):
        """Admin edits their own username, password, profile."""
        p = self._pad()
        tk.Label(p, text="My Account", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(p,
                 text="Change your admin credentials. Changes take effect immediately.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 20))

        # ── Change Username ────────────────────────────────────────────────────
        uc = self._card(p, padx=20, pady=16)
        uc.pack(fill="x", pady=(0, 12))
        tk.Label(uc, text="Change Username", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
        tk.Label(uc, text="Used for login. Choose carefully.",
                 font=FONTS["caption"], fg=COLORS["text_muted"],
                 bg=COLORS["bg_card"]).pack(anchor="w", pady=(2, 10))
        cf = tk.Frame(uc, bg=COLORS["bg_card"])
        cf.pack(fill="x", pady=(0, 6))
        tk.Label(cf, text="Current:", font=FONTS["label"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(side="left")
        tk.Label(cf, text=f"  @{self.user['username']}",
                 font=FONTS["label_bold"], fg=COLORS["accent"],
                 bg=COLORS["bg_card"]).pack(side="left")
        self._new_uname_var = tk.StringVar()
        self._entry_row(uc, "New username:", self._new_uname_var, width=18)
        self._primary_btn(uc, "  ✏  Update Username",
                          self._change_username,
                          color=COLORS["info"]).pack(anchor="w", pady=(4, 0))

        # ── Change Password ────────────────────────────────────────────────────
        pc = self._card(p, padx=20, pady=16)
        pc.pack(fill="x", pady=(0, 12))
        tk.Label(pc, text="Change Password", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(
            anchor="w", pady=(0, 10))
        self._pw1_var = tk.StringVar()
        self._pw2_var = tk.StringVar()
        self._entry_row(pc, "New Password:",     self._pw1_var, width=18, show="•")
        self._entry_row(pc, "Confirm Password:", self._pw2_var, width=18, show="•")
        self._primary_btn(pc, "  🔒  Change Password",
                          self._change_password,
                          color=COLORS["warning"]).pack(anchor="w", pady=(4, 0))

        # ── Profile info ───────────────────────────────────────────────────────
        prc = self._card(p, padx=20, pady=16)
        prc.pack(fill="x", pady=(0, 12))
        tk.Label(prc, text="Profile Information", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(
            anchor="w", pady=(0, 10))
        self._acct_vars = {}
        for label, key, default in [
            ("Full Name", "full_name", self.user.get("full_name", "")),
            ("Email",     "email",     self.user.get("email", "")),
        ]:
            var = tk.StringVar(value=default)
            self._acct_vars[key] = var
            self._entry_row(prc, label, var, width=14)

        bio_f = tk.Frame(prc, bg=COLORS["bg_card"])
        bio_f.pack(fill="x", pady=(0, 10))
        tk.Label(bio_f, text="Bio", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                 width=14, anchor="w").pack(side="left", anchor="n")
        self._acct_bio = tk.Text(bio_f, font=FONTS["body_md"],
                                  bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                                  relief="flat", height=3, bd=0,
                                  highlightthickness=1,
                                  highlightbackground=COLORS["border"],
                                  insertbackground=COLORS["text_primary"])
        self._acct_bio.insert("1.0", self.user.get("bio") or "")
        self._acct_bio.pack(side="left", fill="x", expand=True)
        self._primary_btn(p, "  💾  Save Profile Info",
                          self._save_acct_profile,
                          color=COLORS["admin"]).pack(anchor="w", pady=(0, 20))

    def _change_username(self):
        new_uname = self._new_uname_var.get().strip()
        if not new_uname:
            messagebox.showwarning("Error", "Enter a new username.", parent=self.root)
            return
        if new_uname == self.user["username"]:
            messagebox.showwarning("Error",
                                   "That's already your username.", parent=self.root)
            return
        conn = db.get_conn()
        try:
            conn.execute("UPDATE users SET username = ? WHERE id = ?",
                         (new_uname, self.user["id"]))
            conn.commit()
            self.user["username"] = new_uname
            self._new_uname_var.set("")
            messagebox.showinfo(
                "Username Changed",
                f"Your username is now @{new_uname}.\n"
                "Use this to log in next time.",
                parent=self.root)
            self._nav_to("my_settings")
        except Exception as exc:
            messagebox.showerror("Error",
                                 f"Username already taken:\n{exc}",
                                 parent=self.root)

    def _change_password(self):
        pw1 = self._pw1_var.get()
        pw2 = self._pw2_var.get()
        if not pw1:
            messagebox.showwarning("Error", "Enter a new password.", parent=self.root)
            return
        if pw1 != pw2:
            messagebox.showwarning("Error", "Passwords do not match.", parent=self.root)
            return
        if len(pw1) < 6:
            messagebox.showwarning("Error",
                                   "Password must be at least 6 characters.",
                                   parent=self.root)
            return
        db.change_password(self.user["id"], pw1)
        self._pw1_var.set("")
        self._pw2_var.set("")
        messagebox.showinfo("Done", "Password changed successfully!", parent=self.root)

    def _save_acct_profile(self):
        db.update_user(
            self.user["id"],
            full_name=self._acct_vars["full_name"].get().strip(),
            email=self._acct_vars["email"].get().strip(),
            bio=self._acct_bio.get("1.0", "end-1c"),
        )
        updated = db.get_user(self.user["id"])
        if updated:
            self.user.update(updated)
        messagebox.showinfo("Saved", "Profile saved!", parent=self.root)

    # ── Misc ──────────────────────────────────────────────────────────────────

    def _initials(self) -> str:
        name = self.user.get("full_name") or self.user["username"]
        parts = name.strip().split()
        return ((parts[0][0] + parts[-1][0]) if len(parts) >= 2 else name[:2]).upper()

    def _logout(self):
        db.revoke_session_token(self.user["id"])
        _clear_token()
        self.root.destroy()
        _open_admin_login()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    launch_admin_app()
