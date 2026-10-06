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
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import database as db
from commitmaster import commit_engine, ai_messages, ui, github_service, file_inspector
from commitmaster import commit_composer, charts, navigation, issue_view
from commitmaster.config import load_config
from commitmaster.app_styles import (
    COLORS, FONTS, SIZES, AVATAR_COLORS, THEMES, ACCENTS, FONT_FAMILIES, FONT_SCALES,
    apply_customization, get_active_customization
)
from commitmaster.github_service import mask_token, verify_github_token
from commitmaster.github_account_dialog import GitHubAccountDialog, SelectGitHubReposDialog
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
    try:
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
    except Exception as exc:
        import traceback
        err_msg = traceback.format_exc()
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "CommitMaster Admin — Error",
                f"An unexpected error occurred while starting CommitMaster Admin:\n\n{err_msg}",
                parent=root
            )
            root.destroy()
        except Exception:
            pass
        raise



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
      • MY WORKSPACE  — all personal user features (overview, commits, github accounts, customize, settings, profile)
      • ADMIN CONTROL — full admin features (users, logs, charts, global settings, my settings)
    """

    def __init__(self, user: Dict):
        self.user = user

        # Apply saved customization
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
        self._gd_file_comment_vars: dict = {}
        self._gd_commit_mode_var: tk.StringVar = tk.StringVar(value="individual")
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

    # ── Window ────────────────────────────────────────────────────────────────

    def _setup_window(self):
        name = self.user.get("full_name") or self.user["username"]
        self.root.title(f"CommitMaster — Admin Workspace  ({name})")
        self.root.minsize(1000, 640)
        self.root.configure(bg=COLORS["bg_darkest"])
        self.root.update_idletasks()
        w, h = 1200, 760
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")
        from commitmaster import windows_integration
        windows_integration.apply_windows_theme(self.root, f"CommitMaster — Admin Workspace  ({name})")

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
        self._cf.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._navigator = navigation.PageNavigator(self.root, self._canvas, self._cf, self._cw)
        navigation.install_smooth_scroll(self.root, self._canvas, self._cf)
        navigation.install_header_controls(
            self._header_bar, self._header_title, self._navigator, self._nav_back, self._nav_forward)
        navigation.install_shortcuts(
            self.root, self._nav_order, self._go, self._nav_back, self._nav_forward)

    def _on_frame_configure(self, event):
        bbox = self._canvas.bbox("all")
        if getattr(self, "_last_scrollregion", None) != bbox:
            self._last_scrollregion = bbox
            self._canvas.configure(scrollregion=bbox)

    def _on_canvas_configure(self, event):
        if getattr(self, "_last_canvas_width", None) != event.width:
            self._last_canvas_width = event.width
            self._canvas.itemconfig(self._cw, width=event.width)

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
                self._canvas.yview_scroll(steps, "units")
        except Exception:
            pass

    def _add_hover(self, widget, hover_bg, normal_bg):
        widget.bind("<Enter>", lambda e: widget.config(bg=hover_bg))
        widget.bind("<Leave>", lambda e: widget.config(bg=normal_bg))

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = self._sidebar

        # 1. Pinned Top Header (Logo)
        logo_f = tk.Frame(sb, bg=COLORS["bg_sidebar"], height=64)
        logo_f.pack(side="top", fill="x")
        logo_f.pack_propagate(False)
        from commitmaster import windows_integration
        logo_img = windows_integration.get_logo_photo(26)
        if logo_img:
            self._sidebar_logo_img = logo_img
            tk.Label(logo_f, image=logo_img, bg=COLORS["bg_sidebar"]).pack(side="left", padx=(14, 6), pady=18)
            tk.Label(logo_f, text="CommitMaster", font=FONTS["heading_sm"],
                     fg=COLORS["text_primary"], bg=COLORS["bg_sidebar"]).pack(side="left", pady=18)
        else:
            tk.Label(logo_f, text="⬡ CommitMaster",
                     font=FONTS["heading_sm"], fg=COLORS["accent"],
                     bg=COLORS["bg_sidebar"]).pack(side="left", padx=14, pady=18)
        # Admin badge
        tk.Label(logo_f, text=" ADMIN ", font=("Segoe UI", 8, "bold"),
                 fg=COLORS["bg_darkest"], bg=COLORS["admin"]).pack(
            side="right", padx=10, pady=20)

        tk.Frame(sb, height=1, bg=COLORS["border"]).pack(side="top", fill="x")

        # 2. Pinned Bottom Footer (Sign Out)
        footer_f = tk.Frame(sb, bg=COLORS["bg_sidebar"])
        footer_f.pack(side="bottom", fill="x")
        tk.Frame(footer_f, height=1, bg=COLORS["border"]).pack(side="top", fill="x")
        logout_btn = tk.Button(
            footer_f, text="  ⏻  Sign Out",
            font=FONTS["label"], fg=COLORS["text_secondary"],
            bg=COLORS["bg_sidebar"], relief="flat", bd=0,
            cursor="hand2", anchor="w", padx=14, pady=11,
            command=self._logout)
        logout_btn.pack(side="bottom", fill="x")
        logout_btn.bind("<Enter>",
                        lambda e: logout_btn.config(bg=COLORS["bg_medium"]))
        logout_btn.bind("<Leave>",
                        lambda e: logout_btn.config(bg=COLORS["bg_sidebar"]))

        # 3. Scrollable Middle Area for Navigation
        middle_f = tk.Frame(sb, bg=COLORS["bg_sidebar"])
        middle_f.pack(side="top", fill="both", expand=True)

        self._sb_canvas = tk.Canvas(middle_f, bg=COLORS["bg_sidebar"], highlightthickness=0)
        self._sb_scrollbar = tk.Scrollbar(middle_f, orient="vertical", command=self._sb_canvas.yview)
        self._sb_canvas.configure(yscrollcommand=self._sb_scrollbar.set)

        self._sb_frame = tk.Frame(self._sb_canvas, bg=COLORS["bg_sidebar"])
        self._sb_window = self._sb_canvas.create_window((0, 0), window=self._sb_frame, anchor="nw")

        def _on_sb_frame_configure(e):
            bbox = self._sb_canvas.bbox("all")
            self._sb_canvas.configure(scrollregion=bbox)
            if bbox and (bbox[3] - bbox[1]) > self._sb_canvas.winfo_height() and self._sb_canvas.winfo_height() > 50:
                self._sb_scrollbar.pack(side="right", fill="y")
            else:
                self._sb_scrollbar.pack_forget()

        def _on_sb_canvas_configure(e):
            self._sb_canvas.itemconfig(self._sb_window, width=e.width)

        self._sb_frame.bind("<Configure>", _on_sb_frame_configure)
        self._sb_canvas.bind("<Configure>", _on_sb_canvas_configure)
        self._sb_canvas.pack(side="left", fill="both", expand=True)

        target = self._sb_frame

        # Avatar
        av_f = tk.Frame(target, bg=COLORS["bg_sidebar"], pady=12)
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

        tk.Frame(target, height=1, bg=COLORS["border"]).pack(fill="x", pady=(8, 4))

        # ── MY WORKSPACE section ───────────────────────────────────────────────
        self._section_label(target, "MY WORKSPACE")
        workspace_nav = [
            ("📊", "Overview",            "overview"),
            ("💻", "Git Desktop",         "git_desktop"),
            ("📁", "Watched Repos",       "watched_repos"),
            ("📝", "My Commits",          "commits"),
            ("🐙", "GitHub Accounts",     "github_accounts"),
            ("🎨", "Customize Interface", "customize"),
            ("⚙️",  "Settings",           "settings"),
            ("👤", "My Profile",          "profile"),
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
        self._nav_order = []

        for section, items in all_nav:
            if section == "admin":
                tk.Frame(target, height=1, bg=COLORS["border"]).pack(
                    fill="x", pady=(6, 4))
                self._section_label(target, "ADMIN CONTROL")

            for icon, label, key in items:
                btn = navigation.make_nav_button(target, icon, label, lambda k=key: self._go(k), padx=14, pady=9)
                self._nav_buttons[key] = btn
                self._nav_order.append(key)

        # Bottom padding inside scroll area
        tk.Frame(target, bg=COLORS["bg_sidebar"], height=16).pack(fill="x")

        # Smooth mousewheel binding across all sidebar elements
        def _on_sb_wheel(event):
            delta = getattr(event, "delta", 0)
            if not delta:
                return "break"
            pixels = int(-(delta / 120.0) * 45) if abs(delta) >= 120 else (-1 if delta > 0 else 1) * 35
            self._sb_canvas.yview_scroll(pixels, "units")
            return "break"

        def _bind_sb_mousewheel(widget):
            try:
                widget.bind("<MouseWheel>", _on_sb_wheel, add="+")
                widget.bind("<Button-4>", lambda e: self._sb_canvas.yview_scroll(-35, "units"), add="+")
                widget.bind("<Button-5>", lambda e: self._sb_canvas.yview_scroll(35, "units"), add="+")
                for child in widget.winfo_children():
                    _bind_sb_mousewheel(child)
            except Exception:
                pass

        _bind_sb_mousewheel(sb)


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

    _WORKSPACE_KEYS = {"overview", "git_desktop", "watched_repos", "commits", "github_accounts", "customize", "settings", "profile"}
    _ADMIN_KEYS = {"admin_dashboard", "users", "activity",
                   "charts", "global_settings", "my_settings"}

    _TITLES = {
        "overview":        "Overview",
        "git_desktop":     "Git Desktop",
        "watched_repos":   "Watched Repositories",
        "commits":         "My Commits",
        "github_accounts": "GitHub Accounts & Repositories",
        "customize":       "Customize Interface",
        "settings":        "CommitMaster Settings",
        "profile":         "My Profile",
        "admin_dashboard": "Admin Dashboard",
        "users":           "User Management",
        "activity":        "Activity Log",
        "charts":          "Usage Charts",
        "global_settings": "Global Settings",
        "my_settings":     "My Account",
    }

    def _rebuild_ui(self, nav_to: str = "customize"):
        """Tear down and recreate UI with new theme/tokens."""
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=COLORS["bg_darkest"])
        self._build_layout()
        self._nav_to(nav_to)

    def _go(self, key=None):
        """Navigate to `key`; None reloads the current page."""
        self._nav_to(key or getattr(self, "_active_key", None) or "overview")

    def _nav_back(self):
        key = self._navigator.step(-1)
        if key:
            self._nav_to(key, record=False)

    def _nav_forward(self):
        key = self._navigator.step(1)
        if key:
            self._nav_to(key, record=False)

    def _nav_to(self, key: str, record: bool = True):
        is_admin = key in self._ADMIN_KEYS
        accent = COLORS["admin"] if is_admin else COLORS["accent"]
        navigation.set_active_nav(self._nav_buttons, key, accent)
        self._active_key = key
        self._gd_composer = None

        self._header_title.config(text=self._TITLES.get(key, key))
        self._section_badge.config(
            text="  ADMIN CONTROL  " if is_admin else "  MY WORKSPACE  ",
            bg=accent)

        pages = {
            "overview":        self._page_overview,
            "git_desktop":     self._page_git_desktop,
            "watched_repos":   self._page_watched_repos,
            "commits":         self._page_commits,
            "github_accounts": self._page_github_accounts,
            "customize":       self._page_customize,
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
            self._navigator.show(key, pages[key], record=record)

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

        # ── Local Repository Scanner & AI Push Preview ─────────────────────────
        self._build_repo_scanner_card(p)

        # My 30-day chart
        self._section_hdr(p, "MY ACTIVITY — LAST 30 DAYS", (0, 8))
        charts.user_activity_chart(p, self.user["id"], days=30, height=210).pack(fill="x", pady=(0, 8))

        # Recent commits
        self._section_hdr(p, "MY RECENT COMMITS", (8, 8))
        if not activity:
            tk.Label(p, text="No commits recorded yet. Start coding!",
                     font=FONTS["body_md"], fg=COLORS["text_muted"],
                     bg=COLORS["bg_dark"]).pack(anchor="w")
        else:
            for entry in activity[:6]:
                self._commit_row(p, entry)

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
        cfg_model = cfg.get("ai", {}).get("model")
        cached_model = cfg_model or (ai_messages._MODEL_CACHE["models"][0] if ai_messages._MODEL_CACHE["models"] else None)
        status_text = f"⚡ Local AI: {cached_model or 'Online'} ({ai_url})" if cached_model else f"⚡ Local AI Server: {ai_url}"
        ai_status_lbl = tk.Label(
            hdr_row, text=status_text, font=FONTS["caption"],
            fg=COLORS["accent"] if cached_model else COLORS["text_muted"], bg=COLORS["bg_card"]
        )
        ai_status_lbl.pack(side="right")

        if not cached_model and not cfg_model:
            def _async_detect():
                m = ai_messages.detect_model(cfg, force=False)
                if m:
                    def _update():
                        try:
                            if ai_status_lbl.winfo_exists():
                                ai_status_lbl.config(
                                    text=f"⚡ Local AI: {m} ({ai_url})",
                                    fg=COLORS["accent"]
                                )
                        except tk.TclError:
                            pass
                    try:
                        self.root.after(0, _update)
                    except (tk.TclError, RuntimeError):
                        pass
            threading.Thread(target=_async_detect, daemon=True).start()

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
                if target != self._gd_selected_repo:
                    commit_composer.reset_state(self)
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
                    db.add_or_update_watched_repo(
                        user_id=self.user["id"],
                        repo_name=commit_engine.repo_name(norm),
                        repo_full_name=commit_engine.repo_name(norm),
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
            commit_composer.sync_selection(self, changes, cfg.get("sensitive_patterns", []))

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
                vars_ = [self._gd_staged_vars[p] for _, p in changes if p in self._gd_staged_vars]
                target = not all(v.get() for v in vars_)
                for v in vars_:
                    v.set(target)

            tgl_btn = tk.Button(chg_hdr, text="Toggle All", font=FONTS["caption"],
                                fg=COLORS["accent"], bg=COLORS["bg_card"], relief="flat", bd=0,
                                cursor="hand2", command=toggle_all)
            tgl_btn.pack(side="right")

            # Pre-commit inspection on all pending changes (code snippets + fix advice on demand)
            detected_issues = file_inspector.inspect_files(self._gd_selected_repo, [p for _, p in changes])
            issues_panel = issue_view.build_issues_panel(content_container, detected_issues, self._gd_selected_repo)
            if issues_panel is not None:
                issues_panel.pack(fill="x", pady=(0, 8))

            # File list (scrolls when long)
            list_h = min(len(changes), 8) * 28 + 12
            files_box = tk.Frame(content_container, bg=COLORS["bg_input"],
                                 highlightthickness=1, highlightbackground=COLORS["border"])
            files_box.pack(fill="x", pady=(0, 10))
            files_cv = tk.Canvas(files_box, bg=COLORS["bg_input"], highlightthickness=0, height=list_h)
            files_sb = tk.Scrollbar(files_box, orient="vertical", command=files_cv.yview)
            files_in = tk.Frame(files_cv, bg=COLORS["bg_input"], padx=8, pady=6)
            files_win = files_cv.create_window((0, 0), window=files_in, anchor="nw")
            files_in.bind("<Configure>", lambda e: files_cv.configure(scrollregion=files_cv.bbox("all")))
            files_cv.bind("<Configure>", lambda e: files_cv.itemconfig(files_win, width=e.width))
            files_cv.configure(yscrollcommand=files_sb.set)
            if len(changes) > 8:
                files_sb.pack(side="right", fill="y")
            files_cv.pack(side="left", fill="both", expand=True)

            status_colors = {"M": ("Modified", "#f0883e"), "A": ("Added", "#3fb950"), "D": ("Deleted", "#f85149"), "??": ("Untracked", "#58a6ff")}
            for st, path in changes:
                row = tk.Frame(files_in, bg=COLORS["bg_input"])
                row.pack(fill="x", pady=1)
                var = self._gd_staged_vars[path]
                cb = tk.Checkbutton(row, variable=var, bg=COLORS["bg_input"], selectcolor=COLORS["bg_card"],
                                    activebackground=COLORS["bg_input"])
                cb.pack(side="left")

                label_txt, color_hex = status_colors.get(st, (st, "#8b949e"))
                tk.Label(row, text=f"[{st}]", font=FONTS["mono_sm"], fg=color_hex, bg=COLORS["bg_input"]).pack(side="left", padx=(0, 6))
                tk.Label(row, text=path, font=FONTS["body_sm"], fg=COLORS["text_primary"], bg=COLORS["bg_input"]).pack(side="left")

                if path in detected_issues:
                    top_iss = detected_issues[path][0]
                    sev = top_iss.get("severity")
                    l_no = top_iss.get("line", 1)
                    n_more = len(detected_issues[path])
                    if sev == "error":
                        b_text, b_bg = f"❌ Error (L{l_no})", "#da3633"
                    elif sev == "security":
                        b_text, b_bg = f"🛡️ Security (L{l_no})", "#d29922"
                    else:
                        b_text, b_bg = f"⚠️ Warning (L{l_no})", "#9e6a03"
                    if n_more > 1:
                        b_text += f" +{n_more - 1}"
                    tk.Label(row, text=f" {b_text} ", font=FONTS["caption"], fg="#ffffff", bg=b_bg).pack(side="left", padx=(8, 0))

            # ── Commit composer: Summary + Description, one commit per file by default ──
            composer_box = tk.Frame(content_container, bg=COLORS["bg_card"], padx=14, pady=12,
                                    highlightthickness=1, highlightbackground=COLORS["accent"])
            composer_box.pack(fill="x", pady=(0, 10))
            commit_composer.CommitComposer(
                composer_box, self, cfg, on_done=render_scanner_content
            ).pack(fill="x")
            tk.Button(
                composer_box, text="🖥️ Open full diff in Git Desktop", font=FONTS["label"],
                fg=COLORS["text_secondary"], bg=COLORS["bg_card"], activebackground=COLORS["bg_medium"],
                activeforeground=COLORS["text_primary"], relief="flat", bd=0, cursor="hand2", padx=10, pady=6,
                command=lambda: self._nav_to("git_desktop")
            ).pack(anchor="w", pady=(6, 0))

        render_scanner_content()

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

    # ── GitHub Accounts Page ──────────────────────────────────────────────────

    def _page_github_accounts(self):
        p = self._pad()

        # Header with Add Button
        top_f = tk.Frame(p, bg=COLORS["bg_dark"])
        top_f.pack(fill="x", pady=(0, 16))

        titles_f = tk.Frame(top_f, bg=COLORS["bg_dark"])
        titles_f.pack(side="left", fill="x", expand=True)
        tk.Label(titles_f, text="Linked GitHub Accounts", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(titles_f,
                 text="Manage multiple accounts and configure repository-to-account push assignments.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 0))

        add_btn = tk.Button(top_f, text="  + Link GitHub Account  ", font=FONTS["heading_sm"],
                            fg="white", bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                            activeforeground="white", relief="flat", bd=0, cursor="hand2",
                            padx=14, pady=8, command=self._open_add_github_dialog)
        add_btn.pack(side="right", padx=(10, 0))

        accounts = db.get_github_accounts(self.user["id"])
        watched_repos = db.get_watched_repos(self.user["id"])
        repos = [r["local_path"] for r in watched_repos if r.get("local_path") and os.path.isdir(r["local_path"])]

        default_acc = db.get_default_github_account(self.user["id"])
        default_name = default_acc["account_name"] if default_acc else "None set"

        # Summary Row
        stats_row = tk.Frame(p, bg=COLORS["bg_dark"])
        stats_row.pack(fill="x", pady=(0, 16))
        self._stat_card(stats_row, "Linked Accounts", str(len(accounts)), COLORS["accent"], "🐙")
        self._stat_card(stats_row, "Default Push Account", default_name, COLORS["info"], "★")
        self._stat_card(stats_row, "Authorized Repos", str(len(repos)), COLORS["warning"], "📁")

        # ── Section 1: Linked Accounts ───────────────────────────────────────
        self._section_hdr(p, "Connected Accounts", pady=(8, 10))

        if not accounts:
            empty_card = self._card(p, padx=24, pady=24)
            empty_card.pack(fill="x", pady=(0, 16))
            tk.Label(empty_card, text="🐙  No GitHub accounts linked yet", font=FONTS["heading_sm"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w")
            tk.Label(empty_card,
                     text="Click the '+ Link GitHub Account' button above to connect your first account using a GitHub Personal Access Token (PAT).",
                     font=FONTS["body_sm"], fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 0))
        else:
            for acc in accounts:
                self._build_account_card(p, acc)

        # ── Section 2: Repository Account Assignment & Direct Push ───────────
        self._section_hdr(p, "Repository Account Assignment & Direct Push", pady=(18, 10))
        tk.Label(p,
                 text="Select which GitHub account should be used when pushing commits from each repository. Click 'Push to GitHub' to push the current branch immediately.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(0, 12))

        if not repos:
            no_repo_card = self._card(p, padx=20, pady=20)
            no_repo_card.pack(fill="x", pady=(0, 16))
            tk.Label(no_repo_card, text="No git repositories found in your configured project folders.",
                     font=FONTS["body_md"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w")
            tk.Label(no_repo_card, text="Add project folders in Settings to scan for repositories.",
                     font=FONTS["caption"], fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 0))
        else:
            bindings = db.get_all_repo_bindings(self.user["id"])
            for repo in repos:
                self._build_repo_row(p, repo, accounts, bindings)

    def _build_account_card(self, parent, acc: Dict):
        card = self._card(parent, padx=16, pady=14)
        card.pack(fill="x", pady=(0, 8))

        row = tk.Frame(card, bg=COLORS["bg_card"])
        row.pack(fill="x")

        # Avatar / Icon badge
        av = tk.Label(row, text="🐙", font=("Segoe UI", 16),
                      bg=COLORS["bg_medium"], fg=COLORS["accent"], width=3, height=2)
        av.pack(side="left", padx=(0, 12))

        # Account Details
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

        # Action Buttons
        actions_f = tk.Frame(row, bg=COLORS["bg_card"])
        actions_f.pack(side="right")

        test_btn = tk.Button(actions_f, text="⚡ Test", font=FONTS["caption"],
                             fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                             relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
                             command=lambda a=acc, s=status_lbl: self._test_account_connection(a, s))
        test_btn.pack(side="left", padx=4)

        if not acc.get("is_default"):
            def_btn = tk.Button(actions_f, text="★ Set Default", font=FONTS["caption"],
                                fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                                relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
                                command=lambda a=acc: self._set_account_default(a["id"]))
            def_btn.pack(side="left", padx=4)

        edit_btn = tk.Button(actions_f, text="✏ Edit", font=FONTS["caption"],
                             fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                             relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
                             command=lambda a=acc: self._open_edit_github_dialog(a))
        edit_btn.pack(side="left", padx=4)

        del_btn = tk.Button(actions_f, text="🗑 Delete", font=FONTS["caption"],
                            fg=COLORS["error"], bg=COLORS["bg_medium"],
                            relief="flat", bd=0, cursor="hand2", padx=8, pady=4,
                            command=lambda a=acc: self._delete_github_account(a["id"], a["account_name"]))
        del_btn.pack(side="left", padx=4)

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
        pad = tk.Frame(self._cf, bg=COLORS["bg_dark"], padx=18, pady=14)
        pad.pack(fill="both", expand=True)

        cfg = load_config()
        watched_repos = db.get_watched_repos(self.user["id"])

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
                commit_composer.reset_state(self)
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

        cfg_model = cfg.get("ai", {}).get("model")
        cached_model = cfg_model or (ai_messages._MODEL_CACHE["models"][0] if ai_messages._MODEL_CACHE["models"] else None)
        ai_text = f"⚡ Local AI: {cached_model or 'Ready'}"
        ai_lbl = tk.Label(tb_right, text=ai_text, font=FONTS["caption"],
                          fg=COLORS["accent"] if cached_model else COLORS["warning"],
                          bg=COLORS["bg_card"])
        ai_lbl.pack(side="left", padx=(0, 10))

        if not cached_model and not cfg_model:
            def _async_detect_gd():
                m = ai_messages.detect_model(cfg, force=False)
                if m:
                    def _update():
                        try:
                            if ai_lbl.winfo_exists():
                                ai_lbl.config(text=f"⚡ Local AI: {m}", fg=COLORS["accent"])
                        except tk.TclError:
                            pass
                    try:
                        self.root.after(0, _update)
                    except (tk.TclError, RuntimeError):
                        pass
            threading.Thread(target=_async_detect_gd, daemon=True).start()

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

        changes = commit_engine.uncommitted_changes(self._gd_selected_repo)
        self._gd_changes = changes
        sensitive_patterns = cfg.get("sensitive_patterns", [])

        commit_composer.sync_selection(self, changes, sensitive_patterns)

        if (not self._gd_active_file or not any(p == self._gd_active_file for _, p in changes)) and changes:
            self._gd_active_file = changes[0][1]

        # ── Workspace: Left (Files) & Right (Diff + File Commentary) ─────────
        ws = tk.Frame(pad, bg=COLORS["bg_dark"])
        ws.pack(fill="both", expand=True)

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
            cached_issues = file_inspector.inspect_files(self._gd_selected_repo, [p for _, p in changes]) if self._gd_selected_repo else {}
            for status, path in changes:
                self._gd_build_file_row(files_frame, status, path, issues=cached_issues.get(path, []))

        right_p = tk.Frame(ws, bg=COLORS["bg_dark"])
        right_p.pack(side="left", fill="both", expand=True)

        # Issues for the file currently shown in the diff (code snippet + how to fix)
        self._gd_issue_frame = tk.Frame(right_p, bg=COLORS["bg_dark"])
        self._gd_issue_frame.pack(side="bottom", fill="x", pady=(8, 0))

        diff_card = tk.Frame(right_p, bg=COLORS["bg_card"],
                             highlightthickness=1, highlightbackground=COLORS["border"])
        diff_card.pack(fill="both", expand=True)

        diff_hdr = tk.Frame(diff_card, bg=COLORS["bg_medium"], padx=12, pady=6)
        diff_hdr.pack(fill="x")
        active_name = self._gd_active_file or "No file selected"
        self._gd_diff_title = tk.Label(diff_hdr, text=f"Diff: {active_name}", font=FONTS["mono_sm"],
                                       fg=COLORS["text_primary"], bg=COLORS["bg_medium"])
        self._gd_diff_title.pack(side="left")

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

        self._gd_diff_text.tag_config("diff_add", foreground="#7ee787", background="#132a19")
        self._gd_diff_text.tag_config("diff_del", foreground="#ffa198", background="#331414")
        self._gd_diff_text.tag_config("diff_hunk", foreground="#79c0ff", font=("Consolas", 10, "bold"))
        self._gd_diff_text.tag_config("diff_meta", foreground="#8b949e")

        if self._gd_active_file:
            self._gd_load_file_diff(self._gd_active_file)
            self._gd_refresh_issue_panel(self._gd_active_file)

        # ── Bottom dock: commit composer (Summary + Description) ──────────────
        dock = self._card(pad, padx=14, pady=12)
        dock.pack(fill="x", pady=(10, 0))
        commit_composer.CommitComposer(
            dock, self, cfg, on_done=lambda: self._nav_to("git_desktop")
        ).pack(fill="x")

    def _gd_add_local_repo(self):
        d = filedialog.askdirectory(title="Select Local Git Repository Folder", parent=self.root)
        if d:
            if commit_engine.is_git_repo(d):
                norm = os.path.normpath(d)
                rname = commit_engine.repo_name(norm)
                db.add_or_update_watched_repo(
                    user_id=self.user["id"],
                    repo_name=rname,
                    repo_full_name=rname,
                    local_path=norm,
                    is_active_watch=1,
                )
                self._gd_selected_repo = norm
                self._gd_active_file = None
                self._nav_to("git_desktop")
            else:
                messagebox.showerror("Not a Git Repository", f"'{d}' is not a valid git repository (.git folder not found).", parent=self.root)

    def _gd_toggle_all_files(self):
        vars_ = [self._gd_staged_vars[p] for _, p in self._gd_changes if p in self._gd_staged_vars]
        if not vars_:
            return
        target = not all(v.get() for v in vars_)
        for v in vars_:
            v.set(target)

    def _gd_build_file_row(self, parent, status: str, path: str, issues: Optional[List[Dict[str, Any]]] = None):
        row = tk.Frame(parent, bg=COLORS["bg_card"], padx=6, pady=4)
        row.pack(fill="x")

        var = self._gd_staged_vars.get(path)
        if not var:
            var = tk.BooleanVar(value=True)
            self._gd_staged_vars[path] = var

        cb = tk.Checkbutton(row, variable=var, bg=COLORS["bg_card"],
                            selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"])
        cb.pack(side="left")

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

        # Inline issue badge if problems detected in this file
        if issues is None and self._gd_selected_repo:
            issues = file_inspector.inspect_file(self._gd_selected_repo, path)

        if issues:
            top_iss = issues[0]
            sev = top_iss.get("severity")
            l_no = top_iss.get("line", 1)
            b_text = f"❌ Error (L{l_no})" if sev == "error" else (f"🛡️ Secret (L{l_no})" if sev == "security" else f"⚠️ Warning (L{l_no})")
            b_bg = "#da3633" if sev == "error" else ("#d29922" if sev == "security" else "#9e6a03")
            tk.Label(row, text=f" {b_text} ", font=FONTS["caption"], fg="#ffffff", bg=b_bg).pack(side="right", padx=(4, 2))

        def on_click(e):
            self._gd_select_file(path)
        lbl.bind("<Button-1>", on_click)
        row.bind("<Button-1>", on_click)

    def _gd_select_file(self, path: str):
        self._gd_active_file = path
        self._gd_load_file_diff(path)
        title = getattr(self, "_gd_diff_title", None)
        if title is not None:
            title.config(text=f"Diff: {path}")
        self._gd_refresh_issue_panel(path)

    def _gd_refresh_issue_panel(self, path: str):
        frame = getattr(self, "_gd_issue_frame", None)
        if frame is None or not frame.winfo_exists():
            return
        for w in frame.winfo_children():
            w.destroy()
        issues = file_inspector.inspect_file(self._gd_selected_repo, path) if self._gd_selected_repo else []
        panel = issue_view.build_issues_panel(frame, {path: issues} if issues else {}, self._gd_selected_repo)
        if panel is not None:
            panel.pack(fill="x")

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
        pad = tk.Frame(self._cf, bg=COLORS["bg_dark"], padx=24, pady=20)
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

        lp = repo.get("local_path", "").strip()
        path_text = f"📁 Local Path: {lp}" if lp else "📁 Local Path: Not Linked (Locate or Clone below)"
        path_fg = COLORS["text_primary"] if lp else COLORS["text_muted"]
        tk.Label(left_info, text=path_text, font=FONTS["caption"],
                 fg=path_fg, bg=COLORS["bg_card"]).pack(anchor="w", pady=(3, 0))

        right_ctrl = tk.Frame(top_row, bg=COLORS["bg_card"])
        right_ctrl.pack(side="right")

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

        link_text = "📁 Change Folder" if lp else "📁 Link Folder"
        link_btn = tk.Button(
            right_ctrl, text=link_text, font=FONTS["caption"],
            fg=COLORS["text_primary"], bg=COLORS["bg_medium"], relief="flat", bd=0,
            cursor="hand2", padx=8, pady=5,
            command=lambda r=repo: self._wr_link_local_folder(r)
        )
        link_btn.pack(side="left", padx=(0, 6))

        if not lp and repo.get("clone_url"):
            clone_btn = tk.Button(
                right_ctrl, text="📥 Clone", font=FONTS["caption"],
                fg=COLORS["text_primary"], bg=COLORS["bg_medium"], relief="flat", bd=0,
                cursor="hand2", padx=8, pady=5,
                command=lambda r=repo: self._wr_clone_repo(r)
            )
            clone_btn.pack(side="left", padx=(0, 6))

        if lp and os.path.isdir(lp):
            open_gd_btn = tk.Button(
                right_ctrl, text="🖥️ Open Desktop", font=FONTS["label_bold"],
                fg="white", bg=COLORS["info"], relief="flat", bd=0, cursor="hand2",
                padx=10, pady=5,
                command=lambda p=lp: self._wr_open_in_desktop(p)
            )
            open_gd_btn.pack(side="left", padx=(0, 6))

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
        p = self._pad()

        tk.Label(p, text="Customize Interface", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(p, text="Personalize themes, accent colors, typography, and density for your workspace.",
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
        self._section_hdr(p, "Theme Presets", pady=(4, 10))
        themes_grid = tk.Frame(p, bg=COLORS["bg_dark"])
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
        self._section_hdr(p, "Primary Accent Color", pady=(8, 10))
        accent_card = self._card(p, padx=20, pady=16)
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
        apply_hex_btn = tk.Button(hex_row, text="Set Hex", font=FONTS["caption"],
                                  fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                                  relief="flat", bd=0, padx=8, pady=3, command=self._apply_custom_hex)
        apply_hex_btn.pack(side="left")

        # ── Typography & UI Density Section ──────────────────────────────────
        self._section_hdr(p, "Typography & Scaling", pady=(8, 10))
        type_card = self._card(p, padx=20, pady=16)
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
        action_f = tk.Frame(p, bg=COLORS["bg_dark"])
        action_f.pack(fill="x", pady=(12, 10))

        apply_btn = tk.Button(action_f, text="  ✨  Apply & Save Customization  ",
                              font=FONTS["heading_sm"], fg="white",
                              bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                              activeforeground="white", relief="flat", bd=0, cursor="hand2",
                              padx=18, pady=10, command=self._save_and_apply_customization)
        apply_btn.pack(side="left", padx=(0, 12))

        reset_btn = tk.Button(action_f, text="  ↺  Reset Defaults  ", font=FONTS["label"],
                              fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                              activebackground=COLORS["bg_card_hover"],
                              activeforeground=COLORS["text_primary"],
                              relief="flat", bd=0, cursor="hand2",
                              padx=14, pady=10, command=self._reset_customization)
        reset_btn.pack(side="left")

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

        # Desktop Integration card
        desk_card = self._card(p, padx=20, pady=16)
        desk_card.pack(fill="x", pady=(0, 12))
        tk.Label(desk_card, text="Windows Desktop Integration",
                 font=FONTS["heading_sm"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        tk.Label(desk_card,
                 text="Create 1-click desktop shortcuts with official branding for instant access without terminal commands.",
                 font=FONTS["caption"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w", pady=(2, 10))

        desk_btn_f = tk.Frame(desk_card, bg=COLORS["bg_card"])
        desk_btn_f.pack(anchor="w")
        tk.Button(desk_btn_f, text="📌 Create Desktop Shortcuts", font=FONTS["label_bold"],
                  fg="white", bg=COLORS["info"], relief="flat", bd=0, cursor="hand2",
                  padx=14, pady=6, command=self._create_desktop_shortcuts).pack(side="left", padx=(0, 8))

        self._primary_btn(p, "  💾  Save Settings",
                          self._save_settings).pack(anchor="w", pady=(8, 0))

    def _create_desktop_shortcuts(self):
        from commitmaster import windows_integration
        ok, msg = windows_integration.create_desktop_shortcut("both")
        if ok:
            messagebox.showinfo(
                "Shortcuts Created",
                "Desktop shortcuts created successfully!\n\n"
                "• CommitMaster Admin\n"
                "• CommitMaster (User App)\n\n"
                "Both have been placed on your Windows Desktop with the official icon.",
                parent=self.root
            )
        else:
            messagebox.showerror("Shortcut Error", f"Could not create shortcuts:\n{msg}", parent=self.root)


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

        charts.build_admin_overview(p, days=14)

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
        self._user_search.trace_add("write", lambda *a: self._refresh_users_list(p))
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

        charts.build_admin_analytics(p, days=30)

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
            ("default_theme",         "Default System Theme", "github_dark"),
            ("default_accent",        "Default Accent Color", "#3fb950"),
            ("default_font_family",   "Default Font Family", "Segoe UI"),
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
