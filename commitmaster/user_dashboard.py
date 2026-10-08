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
from typing import Any, Callable, Dict, List, Optional, Tuple

from commitmaster.app_styles import (
    COLORS, FONTS, SIZES, AVATAR_COLORS, THEMES, ACCENTS, FONT_FAMILIES, FONT_SCALES,
    apply_customization, get_active_customization
)
from commitmaster import database as db
from commitmaster import commit_engine, ai_messages, ui, github_service, file_inspector
from commitmaster import commit_composer, charts, navigation, issue_view
from commitmaster.config import load_config
from commitmaster.github_service import mask_token, verify_github_token
from commitmaster.github_account_dialog import GitHubAccountDialog, SelectGitHubReposDialog
from commitmaster.reminder_service import ReminderService, IDE_PRESETS, get_running_ide_processes


class UserDashboard:
    """
    Full-featured user dashboard window with theme customization and
    multiple linked GitHub accounts support.
    on_logout() is called when the user chooses to log out.
    on_admin() is called when an admin wants to open the admin portal.
    """

    def __init__(self, user: Dict, on_logout: Callable, on_admin: Optional[Callable] = None, on_switch_account: Optional[Callable[[Dict], None]] = None):
        self.user = user
        self.on_logout = on_logout
        self.on_admin = on_admin
        self.on_switch_account = on_switch_account
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

        # Auto-commit and countdown state
        self._countdown_timer = None
        self._countdown_remaining = 0
        self._countdown_cancelled = False
        self._pending_autocommit = False
        self._autocommit_banner_frame = None
        self._autocommit_banner_lbl = None
        self._autocommit_stop_btn = None
        self._custom_apps: list = []
        self._rem_ide_check_vars: dict = {}
        self._custom_app_vars: dict = {}

        # Commit Reminder Service (Intervals & IDE Monitoring)
        self._reminder_service = ReminderService(
            user_id=self.user["id"],
            on_commit_action=self._on_reminder_commit,
            on_need_commit_action=self._handle_ide_close_uncommitted,
            master=self.root,
            grace_period_seconds=int(prefs.get("session_end_grace", 15)),
        )
        self._reminder_service.start()

        self._nav_to("overview")

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        name = self.user.get("full_name") or self.user["username"]
        self.root.title(f"CommitMaster — {name}")
        self.root.minsize(900, 600)
        self.root.configure(bg=COLORS["bg_darkest"])
        self.root.update_idletasks()
        w, h = 1100, 700
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")
        from commitmaster import windows_integration
        windows_integration.apply_windows_theme(self.root, f"CommitMaster — {name}", app_type="user")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

    def _on_reminder_commit(self):
        """Action handler when user clicks 'Review & Commit' in the bottom-right toast."""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self._go("git_desktop")
        except Exception:
            pass

    def _handle_ide_close_uncommitted(self, project_path: str, dirty_repos: List[str]):
        """
        Triggered when user closes their coding IDE and clicks 'No, help me commit'.
        Brings CommitMaster to front, navigates to Git Desktop, selects the detected repository,
        and starts AI commit message generation and confirmation/autocommit.
        """
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

        target_repo = project_path or (dirty_repos[0] if dirty_repos else "")
        if target_repo and commit_engine.is_git_repo(target_repo):
            try:
                db.add_or_update_watched_repo(
                    user_id=self.user["id"],
                    repo_full_name=commit_engine.repo_name(target_repo),
                    local_path=os.path.normpath(target_repo),
                    is_active_watch=1,
                )
            except Exception:
                pass
            self._gd_selected_repo = os.path.normpath(target_repo)
            self._gd_active_file = None
            commit_composer.reset_state(self)

        self._go("git_desktop")
        self.root.after(400, lambda: self._start_ide_close_commit_flow(target_repo, dirty_repos))

    def _start_ide_close_commit_flow(self, target_repo: Optional[str], dirty_repos: List[str]):
        """
        Ensures repository is chosen, checks uncommitted files, and triggers AI commit generation.
        """
        if not self._gd_selected_repo and dirty_repos:
            self._gd_selected_repo = os.path.normpath(dirty_repos[0])
            self._go("git_desktop")
            self.root.after(350, lambda: self._start_ide_close_commit_flow(self._gd_selected_repo, dirty_repos))
            return

        if not self._gd_selected_repo:
            messagebox.showinfo(
                "Select Repository",
                "Please choose your repository from the dropdown above to review and commit your changes.",
                parent=self.root,
            )
            return

        changes = commit_engine.uncommitted_changes(self._gd_selected_repo)
        if not changes:
            messagebox.showinfo(
                "Working Tree Clean",
                f"No uncommitted changes found in '{commit_engine.repo_name(self._gd_selected_repo)}'. All work is committed!",
                parent=self.root,
            )
            return

        # Ensure all changed files are staged/checked
        for _, path in changes:
            if path in self._gd_staged_vars:
                self._gd_staged_vars[path].set(True)

        prefs = db.get_preferences(self.user["id"]) or {}
        auto_commit_opt = bool(prefs.get("auto_commit", 0))
        self._pending_autocommit = auto_commit_opt

        comp = getattr(self, "_gd_composer", None)
        if comp and hasattr(comp, "generate"):
            comp.generate()

    def _on_composer_generated(self, comp, res, err, files):
        """Called when AI commit generation finishes in CommitComposer."""
        if err or not res:
            self._pending_autocommit = False
            return

        if getattr(self, "_pending_autocommit", False):
            self._pending_autocommit = False
            self._start_autocommit_countdown(comp)
        else:
            # Preview opt-in mode: user confirmation required
            if comp and hasattr(comp, "ai_status") and comp.ai_status.winfo_exists():
                comp.ai_status.config(
                    text="✔ AI commit messages generated! Review changes and click 'Commit & Push' when ready.",
                    fg=COLORS["success"],
                )

    def _start_autocommit_countdown(self, comp):
        """10-second countdown for automatic commit giving user time to review and cancel."""
        self._cancel_autocommit()
        self._countdown_cancelled = False
        self._countdown_remaining = 10

        try:
            banner = tk.Frame(comp, bg=COLORS["warning"], padx=14, pady=10)
            banner.pack(fill="x", pady=(0, 10), before=comp.footer)
            self._autocommit_banner_frame = banner

            b_left = tk.Frame(banner, bg=COLORS["warning"])
            b_left.pack(side="left", fill="x", expand=True)

            lbl = tk.Label(
                b_left,
                text=f"⏱ Auto-committing and pushing in {self._countdown_remaining}s... Review comments below.",
                font=FONTS["label_bold"],
                fg="#0d1117",
                bg=COLORS["warning"],
            )
            lbl.pack(side="left")
            self._autocommit_banner_lbl = lbl

            stop_btn = tk.Button(
                banner,
                text="⛔ Stop Auto-Commit",
                font=FONTS["label_bold"],
                fg="#ffffff",
                bg="#cf222e",
                activebackground="#a40e26",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                cursor="hand2",
                padx=14,
                pady=5,
                command=self._cancel_autocommit,
            )
            stop_btn.pack(side="right")
            self._autocommit_stop_btn = stop_btn

            self._countdown_timer = self.root.after(1000, lambda: self._autocommit_tick(comp))
        except Exception:
            pass

    def _autocommit_tick(self, comp):
        """Handle 1-second ticks of the 10-second auto-commit countdown."""
        if getattr(self, "_countdown_cancelled", False):
            return

        self._countdown_remaining -= 1
        if self._countdown_remaining > 0:
            if hasattr(self, "_autocommit_banner_lbl") and self._autocommit_banner_lbl and self._autocommit_banner_lbl.winfo_exists():
                self._autocommit_banner_lbl.config(
                    text=f"⏱ Auto-committing and pushing in {self._countdown_remaining}s... Review comments below."
                )
            self._countdown_timer = self.root.after(1000, lambda: self._autocommit_tick(comp))
        else:
            # Countdown reached 0: proceed to commit and push
            if hasattr(self, "_autocommit_banner_lbl") and self._autocommit_banner_lbl and self._autocommit_banner_lbl.winfo_exists():
                self._autocommit_banner_lbl.config(
                    text="🚀 10s elapsed. Committing and pushing to GitHub now..."
                )
            if hasattr(self, "_autocommit_stop_btn") and self._autocommit_stop_btn and self._autocommit_stop_btn.winfo_exists():
                self._autocommit_stop_btn.destroy()

            try:
                comp.commit(push=True)
            except Exception as exc:
                if hasattr(self, "_autocommit_banner_lbl") and self._autocommit_banner_lbl and self._autocommit_banner_lbl.winfo_exists():
                    self._autocommit_banner_lbl.config(
                        text=f"❌ Auto-commit failed: {exc}",
                        fg="#ffffff",
                        bg="#cf222e",
                    )
            self.root.after(4000, self._cleanup_autocommit_banner)

    def _cancel_autocommit(self):
        """Cancel the 10-second auto-commit countdown."""
        self._countdown_cancelled = True
        if getattr(self, "_countdown_timer", None):
            try:
                self.root.after_cancel(self._countdown_timer)
            except Exception:
                pass
            self._countdown_timer = None

        if hasattr(self, "_autocommit_banner_lbl") and self._autocommit_banner_lbl and self._autocommit_banner_lbl.winfo_exists():
            self._autocommit_banner_lbl.config(
                text="⏹ Auto-commit stopped. You can review, edit, or commit manually.",
                fg="#ffffff",
                bg="#21262d",
            )
        if hasattr(self, "_autocommit_banner_frame") and self._autocommit_banner_frame and self._autocommit_banner_frame.winfo_exists():
            self._autocommit_banner_frame.config(bg="#21262d")
        if hasattr(self, "_autocommit_stop_btn") and self._autocommit_stop_btn and self._autocommit_stop_btn.winfo_exists():
            self._autocommit_stop_btn.destroy()

        self.root.after(4000, self._cleanup_autocommit_banner)

    def _cleanup_autocommit_banner(self):
        """Remove the countdown banner from the view."""
        if hasattr(self, "_autocommit_banner_frame") and self._autocommit_banner_frame:
            try:
                self._autocommit_banner_frame.destroy()
            except Exception:
                pass
            self._autocommit_banner_frame = None

    def _on_close_window(self):
        """Clean shutdown when user closes the main dashboard window."""
        if hasattr(self, "_reminder_service") and self._reminder_service:
            try:
                self._reminder_service.stop()
            except Exception:
                pass
        self.root.destroy()

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
        self._navigator = navigation.PageNavigator(
            self.root, self._content_canvas, self._content_frame, self._content_window)
        navigation.install_smooth_scroll(self.root, self._content_canvas, self._content_frame)
        navigation.install_header_controls(
            self._header_frame, self._header_title, self._navigator, self._nav_back, self._nav_forward)
        navigation.install_shortcuts(
            self.root, self._nav_order, self._go, self._nav_back, self._nav_forward)

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

    def _on_frame_configure(self, event=None):
        bbox = self._content_canvas.bbox("all")
        if bbox and (bbox[2] > 1 or bbox[3] > 1):
            if getattr(self, "_last_scrollregion", None) != bbox:
                self._last_scrollregion = bbox
                self._content_canvas.configure(scrollregion=bbox)
        elif event and getattr(event, "height", 0) > 1:
            self._content_canvas.configure(scrollregion=(0, 0, max(event.width, self._content_canvas.winfo_width()), event.height))

    def _on_canvas_configure(self, event):
        if getattr(self, "_last_canvas_width", None) != event.width:
            self._last_canvas_width = event.width
            self._content_canvas.itemconfig(self._content_window, width=event.width)
        bbox = self._content_canvas.bbox("all")
        if bbox and (bbox[2] > 1 or bbox[3] > 1):
            self._content_canvas.configure(scrollregion=bbox)

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = self._sidebar

        # 1. Pinned Top Header (Logo)
        logo_f = tk.Frame(sb, bg=COLORS["bg_sidebar"], height=70)
        logo_f.pack(side="top", fill="x")
        logo_f.pack_propagate(False)
        from commitmaster import windows_integration
        logo_img = windows_integration.get_logo_photo(26)
        if logo_img:
            self._sidebar_logo_img = logo_img
            tk.Label(logo_f, image=logo_img, bg=COLORS["bg_sidebar"]).pack(side="left", padx=(16, 8), pady=20)
            tk.Label(logo_f, text="CommitMaster", font=FONTS["heading_sm"],
                     fg=COLORS["text_primary"], bg=COLORS["bg_sidebar"]).pack(side="left", pady=20)
        else:
            tk.Label(logo_f, text="⬡ CommitMaster", font=FONTS["heading_sm"],
                     fg=COLORS["accent"], bg=COLORS["bg_sidebar"]).pack(
                side="left", padx=16, pady=20)

        tk.Frame(sb, height=1, bg=COLORS["border"]).pack(side="top", fill="x")

        # 2. Pinned Bottom Footer (Switch Account & Sign Out)
        footer_f = tk.Frame(sb, bg=COLORS["bg_sidebar"])
        footer_f.pack(side="bottom", fill="x")
        tk.Frame(footer_f, height=1, bg=COLORS["border"]).pack(side="top", fill="x")

        switch_btn = tk.Button(footer_f, text="  👥  Switch Account",
                               font=FONTS["label"], fg=COLORS["text_secondary"],
                               bg=COLORS["bg_sidebar"], relief="flat", bd=0,
                               cursor="hand2", anchor="w",
                               command=self._open_account_switcher, padx=16, pady=10)
        switch_btn.pack(side="top", fill="x")
        self._add_hover(switch_btn, COLORS["bg_medium"], COLORS["bg_sidebar"])

        logout_btn = tk.Button(footer_f, text="  ⏻  Sign Out",
                               font=FONTS["label"], fg=COLORS["text_secondary"],
                               bg=COLORS["bg_sidebar"], relief="flat", bd=0,
                               cursor="hand2", anchor="w",
                               command=self._do_logout, padx=16, pady=10)
        logout_btn.pack(side="bottom", fill="x")
        self._add_hover(logout_btn, COLORS["bg_medium"], COLORS["bg_sidebar"])

        # 3. Scrollable Middle Area
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

        # Avatar + name
        av_f = tk.Frame(target, bg=COLORS["bg_sidebar"], pady=16)
        av_f.pack(fill="x", padx=16)
        color = self.user.get("avatar_color", AVATAR_COLORS[0])
        initials = self._get_initials()
        av = tk.Label(av_f, text=initials, font=FONTS["heading_sm"],
                      bg=color, fg="white", width=4, height=2)
        av.pack(anchor="w")
        tk.Label(av_f, text=self.user.get("full_name") or self.user["username"],
                 font=FONTS["label_bold"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_sidebar"], wraplength=160).pack(anchor="w", pady=(4, 0))
        is_admin = db.is_admin_username(self.user.get("username", "")) and self.user.get("role") == "admin"
        role_tag = "● Admin" if is_admin else "● User"
        role_color = COLORS["admin"] if is_admin else COLORS["success"]
        tk.Label(av_f, text=role_tag, font=FONTS["caption"],
                 fg=role_color, bg=COLORS["bg_sidebar"]).pack(anchor="w")

        tk.Frame(target, height=1, bg=COLORS["border"]).pack(fill="x", pady=(8, 4))

        # Nav items
        nav_items = [
            ("📊", "Overview",        "overview"),
            ("💻", "Git Desktop",     "git_desktop"),
            ("📁", "Watched Repos",   "watched_repos"),
            ("📝", "My Commits",      "commits"),
            ("🐙", "GitHub Accounts", "github_accounts"),
            ("🎨", "Customize",       "customize"),
            ("⚙️",  "Settings",       "settings"),
            ("👤", "My Profile",      "profile"),
        ]
        if is_admin:
            nav_items.append(("🛡", "Admin Portal", "admin"))

        self._nav_buttons = {}
        self._nav_order = [k for _, _, k in nav_items if k != "admin"]
        for icon, label, key in nav_items:
            btn = self._make_nav_btn(target, icon, label, key)
            self._nav_buttons[key] = btn

        # Bottom padding inside scroll area
        tk.Frame(target, bg=COLORS["bg_sidebar"], height=16).pack(fill="x")

        # Smooth mousewheel binding
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


    def _make_nav_btn(self, parent, icon: str, label: str, key: str) -> tk.Button:
        return navigation.make_nav_button(parent, icon, label, lambda k=key: self._go(k))

    def _rebuild_ui(self, nav_to: str = "customize"):
        """Tear down and recreate UI with new theme/tokens."""
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=COLORS["bg_darkest"])
        self._build_layout()
        self._nav_to(nav_to)

    def _go(self, key=None):
        """Navigate to `key`; None reloads the current page."""
        self._nav_to(key or self._active_nav or "overview")

    def _nav_back(self):
        key = self._navigator.step(-1)
        if key:
            self._nav_to(key, record=False)

    def _nav_forward(self):
        key = self._navigator.step(1)
        if key:
            self._nav_to(key, record=False)

    def _nav_to(self, key: str, record: bool = True):
        if key == "admin" and self.on_admin:
            self.on_admin()
            return
        navigation.set_active_nav(self._nav_buttons, key)
        self._active_nav = key
        self._gd_composer = None
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
            self._navigator.show(key, pages[key], record=record)

    def _add_hover(self, widget, hover_bg, normal_bg):
        widget.bind("<Enter>", lambda e: widget.config(bg=hover_bg))
        widget.bind("<Leave>", lambda e: widget.config(bg=normal_bg))

    # ── Header ─────────────────────────────────────────────────────────────────

    def _build_header(self):
        header = tk.Frame(self._main, bg=COLORS["bg_dark"], height=56)
        self._header_frame = header
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Frame(self._main, height=1, bg=COLORS["border"]).pack(fill="x")
        self._header_title = tk.Label(header, text="Overview",
                                      font=FONTS["heading_md"],
                                      fg=COLORS["text_primary"], bg=COLORS["bg_dark"])
        self._header_title.pack(side="left", padx=24, pady=12)
        # Right side: switch account & version badge
        tk.Label(header, text="v3.0", font=FONTS["caption"],
                 fg=COLORS["text_muted"], bg=COLORS["bg_dark"]).pack(
            side="right", padx=(4, 16))

        hdr_switch_btn = tk.Button(
            header, text="👥 Switch Account", font=FONTS["caption"],
            bg=COLORS["bg_card"], fg=COLORS["text_primary"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["accent"],
            relief="flat", bd=0, cursor="hand2", padx=10, pady=4,
            command=self._open_account_switcher
        )
        hdr_switch_btn.pack(side="right", padx=6)
        self._add_hover(hdr_switch_btn, COLORS["bg_card_hover"], COLORS["bg_card"])

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
        self._section_title(pad, "YOUR ACTIVITY — LAST 30 DAYS", (16, 8))
        charts.user_activity_chart(pad, self.user["id"], days=30, height=210).pack(fill="x", pady=(0, 8))

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
        prov = ai_messages.get_active_provider(cfg)
        prov_label = ai_messages.get_provider_label(cfg)
        prov_model = ai_messages.resolve_active_model(cfg)
        if prov in ("openai", "claude", "gemini"):
            status_text = f"⚡ {prov_label}: {prov_model}" if prov_model else f"⚡ {prov_label}: (Needs API Key)"
            status_color = COLORS["accent"] if prov_model else COLORS["text_secondary"]
        else:
            cached_model = prov_model or (ai_messages._MODEL_CACHE["models"][0] if ai_messages._MODEL_CACHE["models"] else None)
            status_text = f"⚡ {prov_label}: {cached_model or 'Online'} ({ai_url})" if cached_model else f"⚡ {prov_label}: {ai_url}"
            status_color = COLORS["accent"] if cached_model else COLORS["text_muted"]

        ai_status_lbl = tk.Label(
            hdr_row, text=status_text, font=FONTS["caption"],
            fg=status_color, bg=COLORS["bg_card"]
        )
        ai_status_lbl.pack(side="right")

        if prov not in ("openai", "claude", "gemini") and not cached_model and not prov_model:
            def _async_detect():
                m = ai_messages.detect_model(cfg, force=False)
                if m:
                    def _update():
                        try:
                            if ai_status_lbl.winfo_exists():
                                ai_status_lbl.config(
                                    text=f"⚡ {prov_label}: {m} ({ai_url})",
                                    fg=COLORS["accent"]
                                )
                        except tk.TclError:
                            pass
                    self.root.after(0, _update)
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

        # ── Commit Reminder Notifications Card ────────────────────────────────
        rem_card = self._card(pad, padx=20, pady=16)
        rem_card.pack(fill="x", pady=(0, 12))

        rem_hdr = tk.Frame(rem_card, bg=COLORS["bg_card"])
        rem_hdr.pack(fill="x", pady=(0, 4))
        tk.Label(rem_hdr, text="🔔  Commit Reminder Notifications", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(side="left")

        test_btn = tk.Button(
            rem_hdr, text="🔔 Test Bottom-Right Alert",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["bg_medium"], fg=COLORS["accent"],
            activebackground=COLORS["bg_card_hover"],
            activeforeground=COLORS["accent_hover"],
            relief="flat", bd=0, cursor="hand2", padx=10, pady=3,
            command=self._test_reminder_toast
        )
        test_btn.pack(side="right")
        self._add_hover(test_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        tk.Label(rem_card,
                 text="Configure how CommitMaster alerts you on the bottom right corner of your screen.",
                 font=FONTS["caption"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 10))

        # ── Option 1: Interval-Based Reminders
        int_frame = tk.Frame(rem_card, bg=COLORS["bg_medium"], padx=14, pady=10)
        int_frame.pack(fill="x", pady=(0, 10))

        self._rem_interval_var = tk.BooleanVar(value=bool(prefs.get("reminder_interval_enabled", 1)))
        int_cb = tk.Checkbutton(
            int_frame, text="1. Interval-Based Reminders (Timer)",
            variable=self._rem_interval_var,
            font=FONTS["label_bold"], fg=COLORS["text_primary"],
            bg=COLORS["bg_medium"], selectcolor=COLORS["bg_dark"],
            activebackground=COLORS["bg_medium"], activeforeground=COLORS["text_primary"]
        )
        int_cb.pack(anchor="w")

        tk.Label(
            int_frame,
            text="Set regular intervals in hours and minutes to receive a bottom-right corner reminder.",
            font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_medium"]
        ).pack(anchor="w", pady=(2, 8))

        time_row = tk.Frame(int_frame, bg=COLORS["bg_medium"])
        time_row.pack(anchor="w", fill="x")

        tk.Label(time_row, text="Remind every: ", font=FONTS["body_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_medium"]).pack(side="left")

        self._rem_hours_var = tk.StringVar(value=str(prefs.get("reminder_interval_hours", 1)))
        self._rem_mins_var = tk.StringVar(value=str(prefs.get("reminder_interval_minutes", 0)))

        tk.Entry(time_row, textvariable=self._rem_hours_var, width=3, font=FONTS["mono"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                 highlightthickness=1, highlightbackground=COLORS["border"], justify="center").pack(side="left", padx=(0, 4))
        tk.Label(time_row, text="hrs", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_medium"]).pack(side="left", padx=(0, 10))

        tk.Entry(time_row, textvariable=self._rem_mins_var, width=3, font=FONTS["mono"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                 highlightthickness=1, highlightbackground=COLORS["border"], justify="center").pack(side="left", padx=(0, 4))
        tk.Label(time_row, text="mins", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_medium"]).pack(side="left", padx=(0, 16))

        # Quick preset buttons (30m, 1h, 2h, 4h)
        tk.Label(time_row, text="Quick Presets: ", font=FONTS["caption"],
                 fg=COLORS["text_muted"], bg=COLORS["bg_medium"]).pack(side="left", padx=(4, 4))

        def _set_preset(h, m):
            self._rem_hours_var.set(str(h))
            self._rem_mins_var.set(str(m))

        for lbl, h, m in [("30m", 0, 30), ("1h", 1, 0), ("2h", 2, 0), ("4h", 4, 0)]:
            p_btn = tk.Button(
                time_row, text=lbl, font=("Segoe UI", 8),
                bg=COLORS["bg_card"], fg=COLORS["text_primary"],
                activebackground=COLORS["accent"], activeforeground="#0d1117",
                relief="flat", bd=0, cursor="hand2", padx=6, pady=1,
                command=lambda h=h, m=m: _set_preset(h, m)
            )
            p_btn.pack(side="left", padx=2)
            self._add_hover(p_btn, COLORS["bg_card_hover"], COLORS["bg_card"])

        # ── Option 2: App / IDE Monitoring
        app_frame = tk.Frame(rem_card, bg=COLORS["bg_medium"], padx=14, pady=10)
        app_frame.pack(fill="x", pady=(0, 10))

        self._rem_app_monitor_var = tk.BooleanVar(value=bool(prefs.get("reminder_app_monitor_enabled", 1)))
        app_cb = tk.Checkbutton(
            app_frame, text="2. App & IDE Monitoring (Session Lifecycle)",
            variable=self._rem_app_monitor_var,
            font=FONTS["label_bold"], fg=COLORS["text_primary"],
            bg=COLORS["bg_medium"], selectcolor=COLORS["bg_dark"],
            activebackground=COLORS["bg_medium"], activeforeground=COLORS["text_primary"]
        )
        app_cb.pack(anchor="w")

        tk.Label(
            app_frame,
            text="Monitors your desktop for IDEs. When you start coding, the system wakes up and keeps an eye\n"
                 "on your work. When you close the IDE, a bottom-right notification reminds you to commit your changes.",
            font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_medium"], justify="left"
        ).pack(anchor="w", pady=(2, 8))

        # IDE selection & live scanner toolbar
        ide_sel_hdr = tk.Frame(app_frame, bg=COLORS["bg_medium"])
        ide_sel_hdr.pack(fill="x", pady=(4, 6))

        tk.Label(
            ide_sel_hdr,
            text="Select Coding Apps & IDEs to Monitor:",
            font=FONTS["label_bold"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_medium"]
        ).pack(side="left")

        # Preset watched detection
        preset_exes_lower = {p["exe"].lower(): p["exe"] for p in IDE_PRESETS}
        for p in IDE_PRESETS:
            for alias in p.get("aliases", []):
                preset_exes_lower[alias.lower()] = p["exe"]

        watched_lower = [w.lower() for w in watched] if watched else []
        default_check_all = len(watched) == 0

        self._rem_ide_check_vars = {}
        self._rem_ide_badge_labels = {}

        def _select_all_ides():
            for v in self._rem_ide_check_vars.values():
                v.set(True)
            for v in self._custom_app_vars.values():
                v.set(True)

        def _deselect_all_ides():
            for v in self._rem_ide_check_vars.values():
                v.set(False)
            for v in self._custom_app_vars.values():
                v.set(False)

        def _refresh_active_badges():
            running = get_running_ide_processes()
            for p in IDE_PRESETS:
                p_exe = p["exe"]
                is_run = (p_exe.lower() in running) or any(a.lower() in running for a in p.get("aliases", []))
                lbl = self._rem_ide_badge_labels.get(p_exe)
                if lbl and lbl.winfo_exists():
                    if is_run:
                        lbl.config(text="● Running now", fg="#3fb950")
                    else:
                        lbl.config(text="", fg=COLORS["bg_card"])

        btn_tools = tk.Frame(ide_sel_hdr, bg=COLORS["bg_medium"])
        btn_tools.pack(side="right")

        sel_all_btn = tk.Button(
            btn_tools, text="Select All", font=("Segoe UI", 8),
            bg=COLORS["bg_card"], fg=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=6, pady=1,
            command=_select_all_ides
        )
        sel_all_btn.pack(side="left", padx=2)
        self._add_hover(sel_all_btn, COLORS["bg_card_hover"], COLORS["bg_card"])

        desel_btn = tk.Button(
            btn_tools, text="Clear All", font=("Segoe UI", 8),
            bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
            relief="flat", bd=0, cursor="hand2", padx=6, pady=1,
            command=_deselect_all_ides
        )
        desel_btn.pack(side="left", padx=2)
        self._add_hover(desel_btn, COLORS["bg_card_hover"], COLORS["bg_card"])

        ref_btn = tk.Button(
            btn_tools, text="🔄 Refresh Active", font=("Segoe UI", 8),
            bg=COLORS["bg_card"], fg=COLORS["accent"],
            relief="flat", bd=0, cursor="hand2", padx=6, pady=1,
            command=_refresh_active_badges
        )
        ref_btn.pack(side="left", padx=(4, 0))
        self._add_hover(ref_btn, COLORS["bg_card_hover"], COLORS["bg_card"])

        # Grid of IDE Presets (3 columns)
        grid_frame = tk.Frame(app_frame, bg=COLORS["bg_medium"])
        grid_frame.pack(fill="x", pady=(2, 8))
        for col_i in range(3):
            grid_frame.columnconfigure(col_i, weight=1)

        running_now = get_running_ide_processes()

        for idx, preset in enumerate(IDE_PRESETS):
            p_exe = preset["exe"]
            p_name = preset["name"]
            p_icon = preset.get("icon", "💻")
            row_idx = idx // 3
            col_idx = idx % 3

            is_checked = default_check_all or (p_exe.lower() in watched_lower) or any(a.lower() in watched_lower for a in preset.get("aliases", []))
            var = tk.BooleanVar(value=is_checked)
            self._rem_ide_check_vars[p_exe] = var

            is_run = (p_exe.lower() in running_now) or any(a.lower() in running_now for a in preset.get("aliases", []))

            cell = tk.Frame(grid_frame, bg=COLORS["bg_card"], padx=8, pady=6,
                            highlightthickness=1, highlightbackground=COLORS["border"])
            cell.grid(row=row_idx, column=col_idx, padx=4, pady=3, sticky="nsew")

            left_box = tk.Frame(cell, bg=COLORS["bg_card"])
            left_box.pack(side="left", fill="x", expand=True)

            cb = tk.Checkbutton(
                left_box, text=f"{p_icon} {p_name}", variable=var,
                font=FONTS["body_sm"], fg=COLORS["text_primary"],
                bg=COLORS["bg_card"], selectcolor=COLORS["bg_dark"],
                activebackground=COLORS["bg_card"], activeforeground=COLORS["text_primary"]
            )
            cb.pack(side="left")

            tk.Label(
                left_box, text=f"({p_exe})", font=FONTS["caption"],
                fg=COLORS["text_muted"], bg=COLORS["bg_card"]
            ).pack(side="left", padx=(2, 0))

            badge_text = "● Running now" if is_run else ""
            badge_lbl = tk.Label(
                cell, text=badge_text, font=("Segoe UI", 8, "bold"),
                fg="#3fb950" if is_run else COLORS["bg_card"], bg=COLORS["bg_card"]
            )
            badge_lbl.pack(side="right", padx=(4, 2))
            self._rem_ide_badge_labels[p_exe] = badge_lbl

        # Custom IDEs / Coding Apps Section
        preset_names_lower = set(preset_exes_lower.keys())
        custom_from_watched = [w for w in watched if w.lower() not in preset_names_lower]
        self._custom_apps = list(dict.fromkeys(custom_from_watched))
        self._custom_app_vars = {}

        custom_section = tk.Frame(app_frame, bg=COLORS["bg_medium"])
        custom_section.pack(fill="x", pady=(4, 0))

        tk.Label(
            custom_section, text="＋ Custom Apps or IDEs (.exe):",
            font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_medium"]
        ).pack(anchor="w", pady=(0, 4))

        self._custom_apps_container = tk.Frame(custom_section, bg=COLORS["bg_medium"])
        self._custom_apps_container.pack(fill="x")

        def _rebuild_custom_apps_ui():
            for w in self._custom_apps_container.winfo_children():
                w.destroy()
            for c_exe in self._custom_apps:
                if c_exe not in self._custom_app_vars:
                    self._custom_app_vars[c_exe] = tk.BooleanVar(value=True)
                c_var = self._custom_app_vars[c_exe]

                c_row = tk.Frame(self._custom_apps_container, bg=COLORS["bg_card"], padx=8, pady=4,
                                 highlightthickness=1, highlightbackground=COLORS["border"])
                c_row.pack(fill="x", pady=2)

                tk.Checkbutton(
                    c_row, text=f"⚙️ {c_exe}", variable=c_var,
                    font=FONTS["body_sm"], fg=COLORS["text_primary"],
                    bg=COLORS["bg_card"], selectcolor=COLORS["bg_dark"],
                    activebackground=COLORS["bg_card"], activeforeground=COLORS["text_primary"]
                ).pack(side="left")

                is_c_run = c_exe.lower() in running_now
                if is_c_run:
                    tk.Label(
                        c_row, text="● Running now", font=("Segoe UI", 8, "bold"),
                        fg="#3fb950", bg=COLORS["bg_card"]
                    ).pack(side="left", padx=8)

                def _remove_c_app(target=c_exe):
                    if target in self._custom_apps:
                        self._custom_apps.remove(target)
                    if target in self._custom_app_vars:
                        del self._custom_app_vars[target]
                    _rebuild_custom_apps_ui()

                rm_btn = tk.Button(
                    c_row, text="✕ Remove", font=("Segoe UI", 8),
                    bg=COLORS["bg_medium"], fg=COLORS["danger"],
                    relief="flat", bd=0, cursor="hand2", padx=6, pady=1,
                    command=_remove_c_app
                )
                rm_btn.pack(side="right")
                self._add_hover(rm_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        _rebuild_custom_apps_ui()

        add_row = tk.Frame(custom_section, bg=COLORS["bg_medium"])
        add_row.pack(fill="x", pady=(6, 0))

        custom_entry_var = tk.StringVar()
        custom_entry = tk.Entry(
            add_row, textvariable=custom_entry_var, font=FONTS["mono"],
            bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
            highlightthickness=1, highlightbackground=COLORS["border"], width=30
        )
        custom_entry.pack(side="left", ipady=3, padx=(0, 6))

        def _add_custom_app_from_entry():
            val = custom_entry_var.get().strip()
            if not val:
                return
            clean_name = os.path.basename(val)
            if not clean_name.lower().endswith(".exe"):
                clean_name += ".exe"
            if clean_name not in self._custom_apps:
                self._custom_apps.append(clean_name)
                self._custom_app_vars[clean_name] = tk.BooleanVar(value=True)
                _rebuild_custom_apps_ui()
            custom_entry_var.set("")

        def _browse_exe_dialog():
            f = filedialog.askopenfilename(
                title="Select IDE / Coding App Executable",
                filetypes=[("Executable Files (*.exe)", "*.exe"), ("All Files (*.*)", "*.*")],
                parent=self.root
            )
            if f:
                base = os.path.basename(f)
                custom_entry_var.set(base)
                _add_custom_app_from_entry()

        browse_btn = tk.Button(
            add_row, text="📁 Browse .exe", font=FONTS["caption"],
            bg=COLORS["bg_card"], fg=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=10, pady=3,
            command=_browse_exe_dialog
        )
        browse_btn.pack(side="left", padx=(0, 6))
        self._add_hover(browse_btn, COLORS["bg_card_hover"], COLORS["bg_card"])

        add_btn = tk.Button(
            add_row, text="＋ Add App", font=FONTS["caption"],
            bg=COLORS["accent"], fg="white",
            relief="flat", bd=0, cursor="hand2", padx=10, pady=3,
            command=_add_custom_app_from_entry
        )
        add_btn.pack(side="left")
        self._add_hover(add_btn, COLORS["accent_hover"], COLORS["accent"])

        self._rem_watched_apps_var = tk.StringVar(value=", ".join(watched) if watched else "")

        # ── Option 3: Smart Filter
        filter_row = tk.Frame(rem_card, bg=COLORS["bg_card"])
        filter_row.pack(fill="x", pady=(2, 0))

        self._rem_only_dirty_var = tk.BooleanVar(value=bool(prefs.get("reminder_only_if_dirty", 1)))
        dirty_cb = tk.Checkbutton(
            filter_row, text="Only alert when uncommitted changes exist in watched repositories",
            variable=self._rem_only_dirty_var,
            font=FONTS["body_sm"], fg=COLORS["text_primary"],
            bg=COLORS["bg_card"], selectcolor=COLORS["bg_dark"],
            activebackground=COLORS["bg_card"], activeforeground=COLORS["text_primary"]
        )
        dirty_cb.pack(anchor="w")

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
            ("Skip sensitive files (.env, keys, certs)", self._skip_sensitive_var),
            ("Desktop notifications on commit", self._notif_var),
            ("Ask before git push", self._ask_push_var),
        ]:
            cb = tk.Checkbutton(card, text=text, variable=var,
                                font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                                bg=COLORS["bg_card"], selectcolor=COLORS["bg_dark"],
                                activebackground=COLORS["bg_card"],
                                activeforeground=COLORS["text_primary"])
            cb.pack(anchor="w", pady=2)

        # Grace period
        grace_f = tk.Frame(card, bg=COLORS["bg_card"])
        grace_f.pack(fill="x", pady=(6, 0))
        tk.Label(grace_f, text="Session End Grace Period (s):", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(side="left")
        self._grace_var = tk.StringVar(value=str(prefs.get("session_end_grace", 120)))
        tk.Entry(grace_f, textvariable=self._grace_var, width=6, font=FONTS["mono"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                 highlightthickness=1, highlightbackground=COLORS["border"]).pack(side="left", padx=8)

        # ── AI settings card ──────────────────────────────────────────────────
        card2 = self._card(pad, padx=20, pady=16)
        card2.pack(fill="x", pady=(0, 12))
        tk.Label(card2, text="AI Providers & API Keys", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
        tk.Label(card2, text="Connect OpenAI, Claude, Google Gemini, or local models for commit generation.",
                 font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(2, 8))

        self._provider_map = {
            "OpenAI": "openai",
            "Anthropic Claude": "claude",
            "Google Gemini": "gemini",
            "Local (Bionic / LM Studio)": "bionic",
            "Local (Ollama)": "ollama",
        }
        self._reverse_provider_map = {v: k for k, v in self._provider_map.items()}

        prov_row = tk.Frame(card2, bg=COLORS["bg_card"])
        prov_row.pack(fill="x", pady=(4, 0))
        tk.Label(prov_row, text="Active Provider:", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=16, anchor="w").pack(side="left")

        cfg = load_config()
        current_prov = prefs.get("ai_provider") or cfg.get("ai", {}).get("provider", "bionic")
        self._ai_provider_var = tk.StringVar(value=self._reverse_provider_map.get(current_prov, "Local (Bionic / LM Studio)"))

        prov_menu = tk.OptionMenu(prov_row, self._ai_provider_var, *self._provider_map.keys())
        prov_menu.config(font=FONTS["body_sm"], bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                         activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
                         relief="flat", bd=0, highlightthickness=1, highlightbackground=COLORS["border"])
        prov_menu["menu"].config(bg=COLORS["bg_card"], fg=COLORS["text_primary"], font=FONTS["body_sm"])
        prov_menu.pack(side="left", padx=4)

        # Cloud API Keys
        # OpenAI Key
        oa_row = tk.Frame(card2, bg=COLORS["bg_card"])
        oa_row.pack(fill="x", pady=(6, 0))
        tk.Label(oa_row, text="OpenAI Key:", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=16, anchor="w").pack(side="left")
        self._openai_key_var = tk.StringVar(value=prefs.get("openai_api_key") or cfg.get("ai", {}).get("openai_api_key", ""))
        tk.Entry(oa_row, textvariable=self._openai_key_var, show="•", font=FONTS["mono"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                 highlightthickness=1, highlightbackground=COLORS["border"]).pack(side="left", fill="x", expand=True, ipady=4)

        # Claude Key
        cl_row = tk.Frame(card2, bg=COLORS["bg_card"])
        cl_row.pack(fill="x", pady=(6, 0))
        tk.Label(cl_row, text="Claude Key:", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=16, anchor="w").pack(side="left")
        self._claude_key_var = tk.StringVar(value=prefs.get("claude_api_key") or cfg.get("ai", {}).get("claude_api_key", ""))
        tk.Entry(cl_row, textvariable=self._claude_key_var, show="•", font=FONTS["mono"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                 highlightthickness=1, highlightbackground=COLORS["border"]).pack(side="left", fill="x", expand=True, ipady=4)

        # Gemini Key
        gm_row = tk.Frame(card2, bg=COLORS["bg_card"])
        gm_row.pack(fill="x", pady=(6, 0))
        tk.Label(gm_row, text="Gemini Key:", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=16, anchor="w").pack(side="left")
        self._gemini_key_var = tk.StringVar(value=prefs.get("gemini_api_key") or cfg.get("ai", {}).get("gemini_api_key", ""))
        tk.Entry(gm_row, textvariable=self._gemini_key_var, show="•", font=FONTS["mono"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                 highlightthickness=1, highlightbackground=COLORS["border"]).pack(side="left", fill="x", expand=True, ipady=4)

        # Model name
        model_f = tk.Frame(card2, bg=COLORS["bg_card"])
        model_f.pack(fill="x", pady=(6, 0))
        tk.Label(model_f, text="Model Name:", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=16, anchor="w").pack(side="left")
        self._ai_model_var = tk.StringVar(value=prefs.get("ai_model") or cfg.get("ai", {}).get("model", ""))
        tk.Entry(model_f, textvariable=self._ai_model_var, font=FONTS["mono"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                 highlightthickness=1, highlightbackground=COLORS["border"]).pack(side="left", fill="x", expand=True, ipady=4)

        # Server URL
        url_f = tk.Frame(card2, bg=COLORS["bg_card"])
        url_f.pack(fill="x", pady=(6, 0))
        tk.Label(url_f, text="Server URL:", font=FONTS["body_sm"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"], width=16, anchor="w").pack(side="left")
        self._ai_url_var = tk.StringVar(value=prefs.get("ai_base_url") or cfg.get("ai", {}).get("base_url", "http://localhost:1234/v1"))
        tk.Entry(url_f, textvariable=self._ai_url_var, font=FONTS["mono"],
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
                 highlightthickness=1, highlightbackground=COLORS["border"]).pack(side="left", fill="x", expand=True, ipady=4)

        # Test Connection button & status
        test_f = tk.Frame(card2, bg=COLORS["bg_card"])
        test_f.pack(fill="x", pady=(10, 0))
        self._ai_test_lbl = tk.Label(test_f, text="", font=FONTS["caption"], bg=COLORS["bg_card"], fg=COLORS["text_secondary"])

        def _test_ai():
            self._ai_test_lbl.config(text="Testing connection...", fg=COLORS["info"])
            self.root.update_idletasks()
            prov = self._provider_map.get(self._ai_provider_var.get(), "bionic")
            m_val = self._ai_model_var.get().strip()
            tmp_cfg = {
                "ai": {
                    "provider": prov,
                    "base_url": self._ai_url_var.get().strip(),
                    "model": m_val,
                    "openai_api_key": self._openai_key_var.get().strip(),
                    "claude_api_key": self._claude_key_var.get().strip(),
                    "gemini_api_key": self._gemini_key_var.get().strip(),
                    "openai_model": m_val or "gpt-4o-mini",
                    "claude_model": m_val or "claude-3-5-haiku-20241022",
                    "gemini_model": m_val or "gemini-1.5-flash",
                    "timeout_seconds": 10,
                }
            }
            ok, msg = ai_messages.test_connection(tmp_cfg)
            color = COLORS["success"] if ok else COLORS["error"]
            self._ai_test_lbl.config(text=("✔ " if ok else "✖ ") + msg.split("\n")[0], fg=color)

        tk.Button(test_f, text="🔌 Test AI Connection", font=FONTS["label"],
                  fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                  activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
                  relief="flat", bd=0, cursor="hand2", padx=10, pady=4, command=_test_ai).pack(side="left")
        self._ai_test_lbl.pack(side="left", padx=(10, 0))

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

        # ── Desktop Shortcut card ─────────────────────────────────────────────
        card_desk = self._card(pad, padx=20, pady=16)
        card_desk.pack(fill="x", pady=(0, 12))
        tk.Label(card_desk, text="Windows Desktop Integration", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
        tk.Label(card_desk,
                 text="Create 1-click desktop shortcuts with official branding for instant access without terminal commands.",
                 font=FONTS["caption"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w", pady=(2, 10))

        desk_btns = tk.Frame(card_desk, bg=COLORS["bg_card"])
        desk_btns.pack(anchor="w")
        desk_btn = tk.Button(desk_btns, text="📌 Create Desktop Shortcuts", font=FONTS["label_bold"],
                             fg="white", bg=COLORS["info"], relief="flat", bd=0, cursor="hand2",
                             padx=14, pady=6, command=self._create_desktop_shortcuts)
        desk_btn.pack(side="left")

        # ── Save button ───────────────────────────────────────────────────────
        save_btn = tk.Button(pad, text="  💾  Save Settings",
                             font=FONTS["heading_sm"], fg="white",
                             bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                             activeforeground="white", relief="flat", bd=0,
                             cursor="hand2", padx=20, pady=10,
                             command=self._save_settings)
        save_btn.pack(anchor="w", pady=(8, 0))
        self._add_hover(save_btn, COLORS["accent_hover"], COLORS["accent"])

    def _create_desktop_shortcuts(self):
        from commitmaster import windows_integration
        target = "both" if self.user.get("role") == "admin" else "user"
        ok, msg = windows_integration.create_desktop_shortcut(target)
        if ok:
            messagebox.showinfo(
                "Shortcuts Created",
                "Desktop shortcut created successfully!\n\n"
                "Placed on your Windows Desktop with the official icon.",
                parent=self.root
            )
        else:
            messagebox.showerror("Shortcut Error", f"Could not create shortcut:\n{msg}", parent=self.root)


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

    def _test_reminder_toast(self):
        if hasattr(self, "_reminder_service") and self._reminder_service:
            self._reminder_service.trigger_test_notification()
        else:
            from commitmaster.notification_toast import show_toast
            show_toast(
                title="🔔 Notification Reminder Preview",
                message="This is a preview of the bottom-right corner reminder! Both interval timers and IDE app monitoring use this card.",
                badge_text="TEST PREVIEW",
                master=self.root,
            )

    def _save_settings(self):
        dirs = list(self._dirs_listbox.get(0, "end"))
        prov = self._provider_map.get(self._ai_provider_var.get(), "bionic")
        m_val = self._ai_model_var.get().strip()

        # Parse watched apps from checkboxes and custom apps
        new_watched = []
        for exe, var in getattr(self, "_rem_ide_check_vars", {}).items():
            if var.get():
                new_watched.append(exe)
        for c_exe, var in getattr(self, "_custom_app_vars", {}).items():
            if var.get() and c_exe not in new_watched:
                new_watched.append(c_exe)
        if not new_watched and hasattr(self, "_rem_watched_apps_var"):
            raw_watched = self._rem_watched_apps_var.get()
            new_watched = [a.strip() for a in raw_watched.split(",") if a.strip()]

        # Parse reminder interval
        try:
            rem_hrs = max(0, int(self._rem_hours_var.get().strip()))
        except Exception:
            rem_hrs = 1
        try:
            rem_mins = max(0, int(self._rem_mins_var.get().strip()))
        except Exception:
            rem_mins = 0
        if rem_hrs == 0 and rem_mins == 0:
            rem_mins = 30

        db.update_preferences(
            self.user["id"],
            auto_commit=int(self._auto_commit_var.get()),
            skip_sensitive=int(self._skip_sensitive_var.get()),
            notifications=int(self._notif_var.get()),
            session_end_grace=int(self._grace_var.get() or 120),
            reminder_interval_enabled=int(self._rem_interval_var.get()),
            reminder_interval_hours=rem_hrs,
            reminder_interval_minutes=rem_mins,
            reminder_app_monitor_enabled=int(self._rem_app_monitor_var.get()),
            reminder_only_if_dirty=int(self._rem_only_dirty_var.get()),
            watched_apps=json.dumps(new_watched),
            ai_provider=prov,
            openai_api_key=self._openai_key_var.get().strip(),
            claude_api_key=self._claude_key_var.get().strip(),
            gemini_api_key=self._gemini_key_var.get().strip(),
            openai_model=m_val if prov == "openai" else "gpt-4o-mini",
            claude_model=m_val if prov == "claude" else "claude-3-5-haiku-20241022",
            gemini_model=m_val if prov == "gemini" else "gemini-1.5-flash",
            ai_base_url=self._ai_url_var.get().strip(),
            ai_model=m_val,
            ask_before_push=int(self._ask_push_var.get()),
            projects_dirs=json.dumps(dirs),
        )

        # Sync to config.json
        cfg = load_config()
        cfg["watched_apps"] = new_watched
        cfg["reminder"] = {
            "interval_enabled": bool(self._rem_interval_var.get()),
            "interval_hours": rem_hrs,
            "interval_minutes": rem_mins,
            "app_monitor_enabled": bool(self._rem_app_monitor_var.get()),
            "only_if_dirty": bool(self._rem_only_dirty_var.get()),
        }
        cfg["ai"]["provider"] = prov
        cfg["ai"]["openai_api_key"] = self._openai_key_var.get().strip()
        cfg["ai"]["claude_api_key"] = self._claude_key_var.get().strip()
        cfg["ai"]["gemini_api_key"] = self._gemini_key_var.get().strip()
        cfg["ai"]["base_url"] = self._ai_url_var.get().strip()
        cfg["ai"]["model"] = m_val if prov in ("bionic", "ollama") else ""
        if prov == "openai" and m_val:
            cfg["ai"]["openai_model"] = m_val
        elif prov == "claude" and m_val:
            cfg["ai"]["claude_model"] = m_val
        elif prov == "gemini" and m_val:
            cfg["ai"]["gemini_model"] = m_val
        save_config(cfg)

        # Dynamically update running reminder service
        if hasattr(self, "_reminder_service") and self._reminder_service:
            self._reminder_service.update_preferences(
                interval_enabled=bool(self._rem_interval_var.get()),
                interval_hours=rem_hrs,
                interval_minutes=rem_mins,
                app_monitor_enabled=bool(self._rem_app_monitor_var.get()),
                only_if_dirty=bool(self._rem_only_dirty_var.get()),
                watched_apps=new_watched,
            )

        messagebox.showinfo("Saved", "Settings saved successfully! Reminder service updated.", parent=self.root)

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

        # ── Verification Status & Google Account OTP
        ver_row = tk.Frame(card, bg=COLORS["bg_card"])
        ver_row.pack(fill="x", pady=(0, 10))
        tk.Label(ver_row, text="Verification:", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                 width=12, anchor="w").pack(side="left")

        is_ver = db.is_user_verified(self.user["id"])
        if is_ver:
            tk.Label(ver_row, text="✔ Verified Google Account", font=FONTS["label_bold"],
                     fg=COLORS["success"], bg=COLORS["bg_card"]).pack(side="left")
        else:
            tk.Label(ver_row, text="⚠️ Unverified", font=FONTS["label"],
                     fg=COLORS["warning"], bg=COLORS["bg_card"]).pack(side="left")

            def _trigger_google_otp():
                u_email = self._profile_vars["email"].get().strip() or self.user.get("email", "")
                if not u_email:
                    messagebox.showwarning("No Email", "Please enter an email address first.", parent=self.root)
                    return
                from commitmaster import otp_service
                ok, msg, code = otp_service.send_google_otp(u_email, purpose="verify_account")
                if not ok:
                    messagebox.showerror("Error", msg, parent=self.root)
                    return

                def _on_v():
                    db.mark_user_verified(self.user["id"])
                    self.user["is_verified"] = 1
                    messagebox.showinfo("Verified", "Your Google account has been verified successfully!", parent=self.root)
                    self._nav_to("profile")

                otp_service.GoogleOtpDialog(self.root, u_email, on_success=_on_v, purpose="verify_account", initial_code=code)

            otp_v_btn = tk.Button(ver_row, text="🔐 Verify with Google OTP", font=FONTS["caption"],
                                  fg="white", bg=COLORS["accent"], relief="flat", bd=0, cursor="hand2",
                                  padx=10, pady=2, command=_trigger_google_otp)
            otp_v_btn.pack(side="left", padx=12)
            self._add_hover(otp_v_btn, COLORS["accent_hover"], COLORS["accent"])

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
                    self.root.after(0, _update)
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

        # Fetch changes
        changes = commit_engine.uncommitted_changes(self._gd_selected_repo)
        self._gd_changes = changes
        sensitive_patterns = cfg.get("sensitive_patterns", [])

        # Reconcile checkboxes / drafts with what is modified right now
        commit_composer.sync_selection(self, changes, sensitive_patterns)

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
            cached_issues = file_inspector.inspect_files(self._gd_selected_repo, [p for _, p in changes]) if self._gd_selected_repo else {}
            for status, path in changes:
                self._gd_build_file_row(files_frame, status, path, issues=cached_issues.get(path, []))

        # Right Panel (Diff Viewer & AI File Commentary)
        right_p = tk.Frame(ws, bg=COLORS["bg_dark"])
        right_p.pack(side="left", fill="both", expand=True)

        # Issues for the file currently shown in the diff (code snippet + how to fix)
        self._gd_issue_frame = tk.Frame(right_p, bg=COLORS["bg_dark"])
        self._gd_issue_frame.pack(side="bottom", fill="x", pady=(8, 0))

        # Diff View Frame
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

        # Tags for diff syntax highlighting
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
        d = filedialog.askdirectory(title="Select Local Git Repository")
        if d:
            if commit_engine.is_git_repo(d):
                self._gd_selected_repo = os.path.normpath(d)
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
        if hasattr(self, "_reminder_service") and self._reminder_service:
            try:
                self._reminder_service.stop()
            except Exception:
                pass
        db.revoke_session_token(self.user["id"])
        self.root.destroy()
        self.on_logout()

    def _open_account_switcher(self):
        """Open interactive Account Switcher dialog to switch or add accounts."""
        from commitmaster.account_manager import AccountSwitcherDialog

        def _on_switch_done(new_user):
            if hasattr(self, "_reminder_service") and self._reminder_service:
                try:
                    self._reminder_service.stop()
                except Exception:
                    pass
            self.root.destroy()
            if self.on_switch_account:
                self.on_switch_account(new_user)
            else:
                from app import launch_app
                launch_app()

        def _on_add():
            if hasattr(self, "_reminder_service") and self._reminder_service:
                try:
                    self._reminder_service.stop()
                except Exception:
                    pass
            self.root.destroy()
            self.on_logout()

        AccountSwitcherDialog(
            self.root, self.user,
            on_switch=_on_switch_done,
            on_add_account=_on_add,
            on_logout=self._do_logout
        )

    def run(self):
        self.root.mainloop()
