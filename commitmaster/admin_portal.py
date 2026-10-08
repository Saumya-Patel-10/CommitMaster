"""
CommitMaster — Admin Management Portal.
Full admin dashboard with user management, activity logs, and usage charts.
"""
import os
import json
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from datetime import datetime
from typing import Dict, Callable

from commitmaster import commit_engine, charts, navigation
from commitmaster.app_styles import (
    COLORS, FONTS, SIZES, AVATAR_COLORS, THEMES, ACCENTS, FONT_FAMILIES, FONT_SCALES,
    apply_customization, get_active_customization
)
from commitmaster import database as db
from commitmaster.github_service import mask_token, verify_github_token
from commitmaster.github_account_dialog import GitHubAccountDialog


class AdminPortal:
    """
    Admin portal — opened from the user dashboard if the logged-in user is an admin.
    """

    def __init__(self, admin_user: Dict, on_close: Callable):
        self.admin_user = admin_user
        self.on_close = on_close

        # Apply saved customization
        prefs = db.get_preferences(self.admin_user["id"]) or {}
        apply_customization(
            theme=prefs.get("theme"),
            accent=prefs.get("accent_color"),
            font_family=prefs.get("font_family"),
            font_scale=prefs.get("font_scale"),
            ui_density=prefs.get("ui_density"),
        )

        self.root = tk.Tk()
        self._setup_window()
        self._build_layout()
        self._nav_to("dashboard")

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        self.root.title("CommitMaster — Admin Portal")
        self.root.minsize(1000, 640)
        self.root.configure(bg=COLORS["bg_darkest"])
        self.root.update_idletasks()
        w, h = 1200, 750
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")
        from commitmaster import windows_integration
        windows_integration.apply_windows_theme(self.root, "CommitMaster Admin — Admin Portal", app_type="admin")

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self):
        # Sidebar
        self._sidebar = tk.Frame(self.root, bg=COLORS["bg_sidebar"],
                                 width=SIZES["sidebar_width"])
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        # Main
        self._main = tk.Frame(self.root, bg=COLORS["bg_dark"])
        self._main.pack(side="left", fill="both", expand=True)

        self._build_sidebar()
        self._build_header()

        # Scrollable content
        self._content_outer = tk.Frame(self._main, bg=COLORS["bg_dark"])
        self._content_outer.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(self._content_outer, bg=COLORS["bg_dark"],
                                 highlightthickness=0)
        self._scrollbar = tk.Scrollbar(self._content_outer, orient="vertical",
                                       command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._content_frame = tk.Frame(self._canvas, bg=COLORS["bg_dark"])
        self._cw = self._canvas.create_window((0, 0), window=self._content_frame, anchor="nw")
        self._content_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._navigator = navigation.PageNavigator(self.root, self._canvas, self._content_frame, self._cw)
        navigation.install_smooth_scroll(self.root, self._canvas, self._content_frame)
        navigation.install_header_controls(
            self._header_frame, self._header_title, self._navigator, self._nav_back, self._nav_forward)
        navigation.install_shortcuts(
            self.root, self._nav_order, self._go, self._nav_back, self._nav_forward)

    def _on_frame_configure(self, event=None):
        bbox = self._canvas.bbox("all")
        if bbox and (bbox[2] > 1 or bbox[3] > 1):
            if getattr(self, "_last_scrollregion", None) != bbox:
                self._last_scrollregion = bbox
                self._canvas.configure(scrollregion=bbox)
        elif event and getattr(event, "height", 0) > 1:
            self._canvas.configure(scrollregion=(0, 0, max(event.width, self._canvas.winfo_width()), event.height))

    def _on_canvas_configure(self, event):
        if getattr(self, "_last_canvas_width", None) != event.width:
            self._last_canvas_width = event.width
            self._canvas.itemconfig(self._cw, width=event.width)
        bbox = self._canvas.bbox("all")
        if bbox and (bbox[2] > 1 or bbox[3] > 1):
            self._canvas.configure(scrollregion=bbox)

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = self._sidebar

        # 1. Pinned Top Header (Logo)
        logo_f = tk.Frame(sb, bg=COLORS["bg_sidebar"], height=70)
        logo_f.pack(side="top", fill="x")
        logo_f.pack_propagate(False)
        from commitmaster import windows_integration
        logo_img = windows_integration.get_logo_photo(26, app_type="admin")
        if logo_img:
            self._sidebar_logo_img = logo_img
            tk.Label(logo_f, image=logo_img, bg=COLORS["bg_sidebar"]).pack(side="left", padx=(16, 8), pady=20)
            tk.Label(logo_f, text="CommitMaster Admin", font=FONTS["heading_sm"],
                     fg=COLORS["text_primary"], bg=COLORS["bg_sidebar"]).pack(side="left", pady=20)
        else:
            tk.Label(logo_f, text="🛡 CommitMaster Admin", font=FONTS["heading_sm"],
                     fg=COLORS["admin"], bg=COLORS["bg_sidebar"]).pack(
                side="left", padx=16, pady=20)

        tk.Frame(sb, height=1, bg=COLORS["border"]).pack(side="top", fill="x")

        # 2. Pinned Bottom Footer (Back button)
        footer_f = tk.Frame(sb, bg=COLORS["bg_sidebar"])
        footer_f.pack(side="bottom", fill="x")
        tk.Frame(footer_f, height=1, bg=COLORS["border"]).pack(side="top", fill="x")
        back_btn = tk.Button(footer_f, text="  ← Back to App",
                             font=FONTS["label"], fg=COLORS["text_secondary"],
                             bg=COLORS["bg_sidebar"], relief="flat", bd=0,
                             cursor="hand2", anchor="w", padx=16, pady=12,
                             command=self._go_back)
        back_btn.pack(side="bottom", fill="x")
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg=COLORS["bg_medium"]))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg=COLORS["bg_sidebar"]))

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

        # Admin avatar
        av_f = tk.Frame(target, bg=COLORS["bg_sidebar"], pady=12)
        av_f.pack(fill="x", padx=16)
        color = self.admin_user.get("avatar_color", AVATAR_COLORS[0])
        initials = self._get_initials()
        tk.Label(av_f, text=initials, font=FONTS["heading_sm"],
                 bg=color, fg="white", width=4, height=2).pack(anchor="w")
        tk.Label(av_f, text=self.admin_user.get("full_name") or self.admin_user["username"],
                 font=FONTS["label_bold"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_sidebar"]).pack(anchor="w", pady=(4, 0))
        tk.Label(av_f, text="● Administrator", font=FONTS["caption"],
                 fg=COLORS["admin"], bg=COLORS["bg_sidebar"]).pack(anchor="w")

        tk.Frame(target, height=1, bg=COLORS["border"]).pack(fill="x", pady=(8, 4))

        # ── Admin Control section ─────────────────────────────────────────────
        tk.Label(target, text="  ADMIN CONTROL", font=("Segoe UI", 9, "bold"),
                 fg=COLORS["text_muted"], bg=COLORS["bg_sidebar"]).pack(
            anchor="w", pady=(4, 2))
        admin_nav = [
            ("📊", "Dashboard",      "dashboard"),
            ("👥", "Users",          "users"),
            ("📝", "Activity Log",   "activity"),
            ("📈", "Usage Charts",   "charts"),
            ("⚙️",  "Global Settings","global_settings"),
        ]
        tk.Frame(target, height=1, bg=COLORS["border"]).pack(fill="x", pady=(4, 4))
        # ── My Account section ────────────────────────────────────────────────
        tk.Label(target, text="  MY ACCOUNT", font=("Segoe UI", 9, "bold"),
                 fg=COLORS["text_muted"], bg=COLORS["bg_sidebar"]).pack(
            anchor="w", pady=(4, 2))
        my_nav = [
            ("🐙", "GitHub Accounts",     "github_accounts"),
            ("🎨", "Customize Interface", "customize"),
            ("👤", "My Settings",          "my_settings"),
        ]
        all_nav = admin_nav + my_nav
        self._nav_buttons = {}
        self._nav_order = [k for _, _, k in all_nav]
        for icon, label, key in all_nav:
            btn = navigation.make_nav_button(target, icon, label, lambda k=key: self._go(k), padx=16, pady=10)
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


    def _build_header(self):
        header = tk.Frame(self._main, bg=COLORS["bg_dark"], height=56)
        self._header_frame = header
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Frame(self._main, height=2, bg=COLORS["admin"]).pack(fill="x")
        self._header_title = tk.Label(header, text="Dashboard",
                                      font=FONTS["heading_md"],
                                      fg=COLORS["text_primary"], bg=COLORS["bg_dark"])
        self._header_title.pack(side="left", padx=24, pady=12)
        # Admin badge
        badge = tk.Label(header, text="  ADMIN  ",
                         font=("Segoe UI", 9, "bold"),
                         fg=COLORS["bg_darkest"], bg=COLORS["admin"])
        badge.pack(side="right", padx=16, pady=18)

    def _rebuild_ui(self, nav_to: str = "customize"):
        """Tear down and recreate UI with new theme/tokens."""
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=COLORS["bg_darkest"])
        self._build_layout()
        self._nav_to(nav_to)

    def _go(self, key=None):
        """Navigate to `key`; None reloads the current page."""
        self._nav_to(key or getattr(self, "_active_key", None) or "dashboard")

    def _nav_back(self):
        key = self._navigator.step(-1)
        if key:
            self._nav_to(key, record=False)

    def _nav_forward(self):
        key = self._navigator.step(1)
        if key:
            self._nav_to(key, record=False)

    def _nav_to(self, key: str, record: bool = True):
        navigation.set_active_nav(self._nav_buttons, key, COLORS["admin"])
        self._active_key = key
        self._header_title.config(text={
            "dashboard":       "Dashboard",
            "users":           "User Management",
            "activity":        "Activity Log",
            "charts":          "Usage Charts",
            "global_settings": "Global Settings",
            "github_accounts": "GitHub Accounts & Repositories",
            "customize":       "Customize Interface",
            "my_settings":     "My Settings",
        }.get(key, key))

        pages = {
            "dashboard":       self._page_dashboard,
            "users":           self._page_users,
            "activity":        self._page_activity,
            "charts":          self._page_charts,
            "global_settings": self._page_global_settings,
            "github_accounts": self._page_github_accounts,
            "customize":       self._page_customize,
            "my_settings":     self._page_my_settings,
        }
        if key in pages:
            self._navigator.show(key, pages[key], record=record)

    # ── My Settings page (admin edits their own account) ──────────────────────

    def _page_my_settings(self):
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        # Header
        tk.Label(pad, text="My Settings", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad,
                 text="Manage your admin account. Changes apply immediately.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 20))

        # ── Avatar colour picker ────────────────────────────────────────────────
        av_card = self._card(pad, padx=20, pady=16)
        av_card.pack(fill="x", pady=(0, 12))

        av_top = tk.Frame(av_card, bg=COLORS["bg_card"])
        av_top.pack(fill="x")
        self._my_color_var = tk.StringVar(
            value=self.admin_user.get("avatar_color", AVATAR_COLORS[0]))

        # Live preview avatar
        self._av_preview = tk.Label(av_top,
                                    text=self._get_initials(),
                                    font=FONTS["heading_lg"],
                                    bg=self._my_color_var.get(),
                                    fg="white", width=4, height=2)
        self._av_preview.pack(side="left", padx=(0, 16))

        color_col = tk.Frame(av_top, bg=COLORS["bg_card"])
        color_col.pack(side="left")
        tk.Label(color_col, text="Avatar Color",
                 font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        swatch_row = tk.Frame(color_col, bg=COLORS["bg_card"])
        swatch_row.pack(anchor="w", pady=(6, 0))
        for color in AVATAR_COLORS:
            swatch = tk.Label(swatch_row, text="  ", bg=color, width=3,
                              cursor="hand2", highlightthickness=2,
                              highlightbackground=COLORS["border"])
            swatch.pack(side="left", padx=3)
            swatch.bind("<Button-1>", lambda e, c=color: self._pick_my_color(c))

        # ── Profile fields ──────────────────────────────────────────────────────
        prof_card = self._card(pad, padx=20, pady=16)
        prof_card.pack(fill="x", pady=(0, 12))
        tk.Label(prof_card, text="Profile Information",
                 font=FONTS["heading_sm"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 12))

        self._my_vars = {}
        fields = [
            ("Full Name",  "full_name", self.admin_user.get("full_name", ""), False),
            ("Email",      "email",     self.admin_user.get("email", ""),     False),
        ]
        for label, key, default, _ in fields:
            rf = tk.Frame(prof_card, bg=COLORS["bg_card"])
            rf.pack(fill="x", pady=(0, 10))
            tk.Label(rf, text=label, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                     width=14, anchor="w").pack(side="left")
            var = tk.StringVar(value=default)
            self._my_vars[key] = var
            e = tk.Entry(rf, textvariable=var, font=FONTS["body_md"],
                         bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                         relief="flat", highlightthickness=1,
                         highlightbackground=COLORS["border"],
                         insertbackground=COLORS["text_primary"])
            e.pack(side="left", fill="x", expand=True, ipady=7)

        # Bio
        bio_f = tk.Frame(prof_card, bg=COLORS["bg_card"])
        bio_f.pack(fill="x", pady=(0, 10))
        tk.Label(bio_f, text="Bio", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                 width=14, anchor="w").pack(side="left", anchor="n")
        self._my_bio = tk.Text(bio_f, font=FONTS["body_md"],
                               bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                               relief="flat", height=3, bd=0,
                               highlightthickness=1,
                               highlightbackground=COLORS["border"],
                               insertbackground=COLORS["text_primary"])
        self._my_bio.insert("1.0", self.admin_user.get("bio") or "")
        self._my_bio.pack(side="left", fill="x", expand=True)

        save_profile_btn = tk.Button(
            pad, text="  💾  Save Profile",
            font=FONTS["heading_sm"], fg="white",
            bg=COLORS["admin"], activebackground=COLORS["admin_dark"],
            activeforeground="white", relief="flat", bd=0, cursor="hand2",
            padx=20, pady=10, command=self._save_my_profile)
        save_profile_btn.pack(anchor="w", pady=(0, 20))
        save_profile_btn.bind("<Enter>",
                              lambda e: save_profile_btn.config(bg=COLORS["admin_dark"]))
        save_profile_btn.bind("<Leave>",
                              lambda e: save_profile_btn.config(bg=COLORS["admin"]))

        # ── Change Username ─────────────────────────────────────────────────────
        user_card = self._card(pad, padx=20, pady=16)
        user_card.pack(fill="x", pady=(0, 12))
        tk.Label(user_card, text="Change Username",
                 font=FONTS["heading_sm"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 4))
        tk.Label(user_card,
                 text="Username is used to log in. Choose carefully.",
                 font=FONTS["caption"], fg=COLORS["text_muted"],
                 bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 10))

        uf = tk.Frame(user_card, bg=COLORS["bg_card"])
        uf.pack(fill="x", pady=(0, 8))
        tk.Label(uf, text="Current username:", font=FONTS["label"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(side="left")
        tk.Label(uf, text=f"  @{self.admin_user['username']}",
                 font=FONTS["label_bold"], fg=COLORS["accent"],
                 bg=COLORS["bg_card"]).pack(side="left")

        nuf = tk.Frame(user_card, bg=COLORS["bg_card"])
        nuf.pack(fill="x", pady=(0, 8))
        tk.Label(nuf, text="New username:", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                 width=18, anchor="w").pack(side="left")
        self._new_username_var = tk.StringVar()
        nue = tk.Entry(nuf, textvariable=self._new_username_var,
                       font=FONTS["body_md"], bg=COLORS["bg_input"],
                       fg=COLORS["text_primary"], relief="flat",
                       highlightthickness=1, highlightbackground=COLORS["border"],
                       insertbackground=COLORS["text_primary"])
        nue.pack(side="left", fill="x", expand=True, ipady=7)

        chg_user_btn = tk.Button(
            user_card, text="  ✏  Change Username",
            font=FONTS["label"], fg="white",
            bg=COLORS["info"], activebackground="#3a7bd5",
            activeforeground="white", relief="flat", bd=0, cursor="hand2",
            padx=14, pady=6, command=self._change_my_username)
        chg_user_btn.pack(anchor="w", pady=(4, 0))

        # ── Change Password ─────────────────────────────────────────────────────
        pw_card = self._card(pad, padx=20, pady=16)
        pw_card.pack(fill="x", pady=(0, 12))
        tk.Label(pw_card, text="Change Password",
                 font=FONTS["heading_sm"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 10))

        self._my_pw_vars = {}
        pw_fields = [
            ("New Password",     "new_pw",  "•"),
            ("Confirm Password", "confirm", "•"),
        ]
        for label, key, show in pw_fields:
            pf = tk.Frame(pw_card, bg=COLORS["bg_card"])
            pf.pack(fill="x", pady=(0, 8))
            tk.Label(pf, text=label, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                     width=18, anchor="w").pack(side="left")
            var = tk.StringVar()
            self._my_pw_vars[key] = var
            e = tk.Entry(pf, textvariable=var, font=FONTS["body_md"],
                         bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                         relief="flat", highlightthickness=1,
                         highlightbackground=COLORS["border"],
                         show=show,
                         insertbackground=COLORS["text_primary"])
            e.pack(side="left", fill="x", expand=True, ipady=7)

        pw_btn = tk.Button(
            pw_card, text="  🔒  Change Password",
            font=FONTS["label"], fg="white",
            bg=COLORS["warning"], activebackground="#c4840e",
            activeforeground="white", relief="flat", bd=0, cursor="hand2",
            padx=14, pady=6, command=self._change_my_password)
        pw_btn.pack(anchor="w", pady=(4, 0))

        # ── Git Push Protection ───────────────────────────────────────────────
        push_card = self._card(pad, padx=20, pady=16)
        push_card.pack(fill="x", pady=(0, 12))
        tk.Label(push_card, text="🛡️ Git Push Protection",
                 font=FONTS["heading_sm"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 4))
        tk.Label(push_card,
                 text="Require interactive user review and confirmation modal before pushing commits to GitHub remotes.",
                 font=FONTS["caption"], fg=COLORS["text_muted"],
                 bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 10))

        prefs = db.get_preferences(self.admin_user["id"]) or {}
        self._my_ask_push_var = tk.IntVar(value=prefs.get("ask_before_push", 1))

        def _toggle_push_pref():
            db.update_preferences(self.admin_user["id"], ask_before_push=self._my_ask_push_var.get())

        cb = tk.Checkbutton(
            push_card,
            text=" Always ask for confirmation before git pushing (protect remotes)",
            variable=self._my_ask_push_var,
            command=_toggle_push_pref,
            font=FONTS["label"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_card"],
            activebackground=COLORS["bg_card"],
            activeforeground=COLORS["accent"],
            selectcolor=COLORS["bg_input"],
            cursor="hand2",
        )
        cb.pack(anchor="w", pady=4)

    def _pick_my_color(self, color: str):
        self._my_color_var.set(color)
        self._av_preview.config(bg=color)

    def _save_my_profile(self):
        db.update_user(
            self.admin_user["id"],
            full_name=self._my_vars["full_name"].get().strip(),
            email=self._my_vars["email"].get().strip(),
            bio=self._my_bio.get("1.0", "end-1c"),
            avatar_color=self._my_color_var.get(),
        )
        # Refresh in-memory user dict
        updated = db.get_user(self.admin_user["id"])
        if updated:
            self.admin_user.update(updated)
        from tkinter import messagebox
        messagebox.showinfo("Saved", "Profile updated successfully!", parent=self.root)

    def _change_my_username(self):
        new_uname = self._new_username_var.get().strip()
        if not new_uname:
            from tkinter import messagebox
            messagebox.showwarning("Error", "Please enter a new username.", parent=self.root)
            return
        if new_uname == self.admin_user["username"]:
            from tkinter import messagebox
            messagebox.showwarning("Error", "That is already your current username.", parent=self.root)
            return
        conn = db.get_conn()
        try:
            conn.execute("UPDATE users SET username = ? WHERE id = ?",
                         (new_uname, self.admin_user["id"]))
            conn.commit()
            self.admin_user["username"] = new_uname
            self._new_username_var.set("")
            from tkinter import messagebox
            messagebox.showinfo(
                "Username Changed",
                f"Username updated to @{new_uname}.\n"
                "Use this to log in next time.",
                parent=self.root)
            self._nav_to("my_settings")   # refresh page to show new username
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("Error", f"Username already taken: {exc}", parent=self.root)

    def _change_my_password(self):
        new_pw  = self._my_pw_vars["new_pw"].get()
        confirm = self._my_pw_vars["confirm"].get()
        from tkinter import messagebox
        if not new_pw:
            messagebox.showwarning("Error", "Please enter a new password.", parent=self.root)
            return
        if new_pw != confirm:
            messagebox.showwarning("Error", "Passwords do not match.", parent=self.root)
            return
        if len(new_pw) < 6:
            messagebox.showwarning("Error",
                                   "Password must be at least 6 characters.",
                                   parent=self.root)
            return
        db.change_password(self.admin_user["id"], new_pw)
        for v in self._my_pw_vars.values():
            v.set("")
        messagebox.showinfo("Password Changed",
                            "Password updated successfully!",
                            parent=self.root)

    # ── Helper widgets ─────────────────────────────────────────────────────────

    def _card(self, parent, **kw) -> tk.Frame:
        return tk.Frame(parent, bg=COLORS["bg_card"],
                        highlightbackground=COLORS["border"],
                        highlightthickness=1, **kw)

    def _stat_card(self, parent, title: str, value: str,
                   color: str, icon: str, subtitle: str = ""):
        card = self._card(parent)
        card.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        inner = tk.Frame(card, bg=COLORS["bg_card"], padx=20, pady=18)
        inner.pack(fill="both", expand=True)
        # Top accent bar
        tk.Frame(card, height=3, bg=color).place(relx=0, rely=0, relwidth=1)
        tk.Label(inner, text=icon, font=("Segoe UI Emoji", 22),
                 fg=color, bg=COLORS["bg_card"]).pack(anchor="w")
        tk.Label(inner, text=value, font=FONTS["heading_lg"],
                 fg=color, bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 0))
        tk.Label(inner, text=title, font=FONTS["label_bold"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
        if subtitle:
            tk.Label(inner, text=subtitle, font=FONTS["caption"],
                     fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(anchor="w")

    def _action_btn(self, parent, text: str, cmd, color=None) -> tk.Button:
        c = color or COLORS["bg_medium"]
        btn = tk.Button(parent, text=text, font=FONTS["label"],
                        fg=COLORS["text_primary"], bg=c,
                        activebackground=COLORS["bg_card_hover"],
                        activeforeground=COLORS["text_primary"],
                        relief="flat", bd=0, cursor="hand2",
                        padx=10, pady=4, command=cmd)
        btn.bind("<Enter>", lambda e: btn.config(bg=COLORS["bg_card_hover"]))
        btn.bind("<Leave>", lambda e: btn.config(bg=c))
        return btn

    # ── Pages ──────────────────────────────────────────────────────────────────

    def _page_dashboard(self):
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="System Dashboard", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad, text=f"CommitMaster Admin — {datetime.now().strftime('%A, %B %d %Y')}",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 20))

        stats = db.get_dashboard_stats()

        # Stats row 1
        row1 = tk.Frame(pad, bg=COLORS["bg_dark"])
        row1.pack(fill="x")
        self._stat_card(row1, "Total Users", str(stats["total_users"]),
                        COLORS["info"], "👥", f"{stats['total_admins']} admins")
        self._stat_card(row1, "Active Today", str(stats["active_today"]),
                        COLORS["success"], "🟢", "unique logins")
        self._stat_card(row1, "Total Commits", str(stats["total_commits"]),
                        COLORS["accent"], "📝", "all time")
        self._stat_card(row1, "This Week", str(stats["commits_this_week"]),
                        COLORS["admin"], "📈", "commits (7d)")

        # Top committers
        tk.Label(pad, text="TOP COMMITTERS", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(
            anchor="w", pady=(24, 8))

        top_card = self._card(pad, padx=20, pady=16)
        top_card.pack(fill="x", pady=(0, 20))

        if not stats["top_committers"]:
            tk.Label(top_card, text="No commit data yet.",
                     font=FONTS["body_sm"], fg=COLORS["text_muted"],
                     bg=COLORS["bg_card"]).pack(anchor="w")
        for i, tc in enumerate(stats["top_committers"], 1):
            row = tk.Frame(top_card, bg=COLORS["bg_card"])
            row.pack(fill="x", pady=4)
            color = [COLORS["admin"], COLORS["warning"], COLORS["info"],
                     COLORS["text_secondary"], COLORS["text_muted"]][i - 1]
            tk.Label(row, text=f"#{i}", font=FONTS["label_bold"],
                     fg=color, bg=COLORS["bg_card"], width=3).pack(side="left")
            tk.Label(row, text=tc["username"], font=FONTS["body_md"],
                     fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(side="left", padx=8)
            tk.Label(row, text=f"{tc['commits']} commits", font=FONTS["body_sm"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(side="right")

        charts.build_admin_overview(pad, days=14)

    def _page_users(self):
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        # Header
        top = tk.Frame(pad, bg=COLORS["bg_dark"])
        top.pack(fill="x", pady=(0, 16))
        tk.Label(top, text="User Management", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(side="left")
        add_btn = tk.Button(top, text="  ＋ Add User",
                            font=FONTS["label_bold"], fg="white",
                            bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                            activeforeground="white", relief="flat", bd=0,
                            cursor="hand2", padx=14, pady=6,
                            command=self._add_user_dialog)
        add_btn.pack(side="right")

        # Search bar
        sf = tk.Frame(pad, bg=COLORS["bg_dark"])
        sf.pack(fill="x", pady=(0, 12))
        tk.Label(sf, text="🔍", font=FONTS["body_md"],
                 fg=COLORS["text_muted"], bg=COLORS["bg_dark"]).pack(side="left")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._refresh_users(pad))
        se = tk.Entry(sf, textvariable=self._search_var, font=FONTS["body_md"],
                      bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                      relief="flat", highlightthickness=1,
                      highlightbackground=COLORS["border"], width=30)
        se.pack(side="left", padx=8, ipady=6)
        tk.Label(sf, text="Search by name, username or email",
                 font=FONTS["caption"], fg=COLORS["text_muted"],
                 bg=COLORS["bg_dark"]).pack(side="left")

        # Table header
        hdr = tk.Frame(pad, bg=COLORS["bg_medium"])
        hdr.pack(fill="x")
        for col, width in [("User", 30), ("Email", 30), ("Role", 10),
                           ("Status", 10), ("Commits", 10), ("Actions", 20)]:
            tk.Label(hdr, text=col, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                     width=width, anchor="w", padx=8, pady=6).pack(side="left")

        # User list container
        self._users_container = tk.Frame(pad, bg=COLORS["bg_dark"])
        self._users_container.pack(fill="x")
        self._users_pad = pad
        self._refresh_users(pad)

    def _refresh_users(self, pad=None):
        container = self._users_container
        for w in container.winfo_children():
            w.destroy()

        query = self._search_var.get().lower() if hasattr(self, "_search_var") else ""
        users = db.get_all_users()

        for user in users:
            if query and not any(
                query in str(user.get(f, "")).lower()
                for f in ["username", "email", "full_name"]
            ):
                continue
            self._user_table_row(container, user)

    def _user_table_row(self, parent, user: Dict):
        row = tk.Frame(parent, bg=COLORS["bg_card"],
                       highlightbackground=COLORS["border"], highlightthickness=0)
        row.pack(fill="x")
        tk.Frame(parent, height=1, bg=COLORS["border"]).pack(fill="x")

        def on_enter(e): row.config(bg=COLORS["bg_card_hover"])
        def on_leave(e): row.config(bg=COLORS["bg_card"])
        row.bind("<Enter>", on_enter)
        row.bind("<Leave>", on_leave)

        color = user.get("avatar_color", AVATAR_COLORS[0])
        initials = self._user_initials(user)
        av = tk.Label(row, text=initials, font=("Segoe UI", 9, "bold"),
                      bg=color, fg="white", width=3, padx=4, pady=4)
        av.pack(side="left", padx=(8, 0), pady=6)

        name_f = tk.Frame(row, bg=COLORS["bg_card"], width=180)
        name_f.pack(side="left", padx=8, pady=6)
        name_f.pack_propagate(False)
        tk.Label(name_f, text=user.get("full_name") or user["username"],
                 font=FONTS["label_bold"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"], anchor="w").pack(anchor="w")
        tk.Label(name_f, text=f"@{user['username']}", font=FONTS["caption"],
                 fg=COLORS["text_muted"], bg=COLORS["bg_card"], anchor="w").pack(anchor="w")

        email_lbl = tk.Label(row, text=user.get("email", ""),
                             font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                             bg=COLORS["bg_card"], width=28, anchor="w")
        email_lbl.pack(side="left", padx=4)

        role_color = COLORS["admin"] if user["role"] == "admin" else COLORS["info"]
        tk.Label(row, text=user["role"].capitalize(), font=FONTS["label"],
                 fg=role_color, bg=COLORS["bg_card"], width=10).pack(side="left")

        status = "Active" if user["is_active"] else "Disabled"
        sc = COLORS["success"] if user["is_active"] else COLORS["error"]
        tk.Label(row, text=f"● {status}", font=FONTS["label"],
                 fg=sc, bg=COLORS["bg_card"], width=10).pack(side="left")

        commits = user.get("total_commits", 0)
        tk.Label(row, text=str(commits), font=FONTS["body_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"], width=10).pack(side="left")

        # Action buttons
        actions = tk.Frame(row, bg=COLORS["bg_card"])
        actions.pack(side="left", padx=8)

        # Protect admin from deleting themselves
        can_edit = user["id"] != self.admin_user["id"]

        self._action_btn(actions, "✏ Edit",
                         lambda u=user: self._edit_user_dialog(u)).pack(side="left", padx=2)
        if can_edit:
            toggle_text = "🔒 Disable" if user["is_active"] else "🔓 Enable"
            self._action_btn(actions, toggle_text,
                             lambda u=user: self._toggle_user(u)).pack(side="left", padx=2)
            self._action_btn(actions, "🗑 Delete",
                             lambda u=user: self._delete_user(u),
                             color="#3a1010").pack(side="left", padx=2)

    def _add_user_dialog(self):
        dialog = _UserDialog(self.root, "Add User")
        if dialog.result:
            d = dialog.result
            uid = db.create_user(d["username"], d["email"], d["full_name"],
                                 d["password"], d["role"])
            if uid:
                messagebox.showinfo("Success", f"User '{d['username']}' created.",
                                    parent=self.root)
                self._refresh_users()
            else:
                messagebox.showerror("Error",
                                     "Username or email already exists.",
                                     parent=self.root)

    def _edit_user_dialog(self, user: Dict):
        dialog = _UserDialog(self.root, "Edit User", user)
        if dialog.result:
            d = dialog.result
            db.update_user(user["id"],
                           full_name=d["full_name"],
                           email=d["email"],
                           role=d["role"])
            if d.get("password"):
                db.change_password(user["id"], d["password"])
            messagebox.showinfo("Saved", "User updated.", parent=self.root)
            self._refresh_users()

    def _toggle_user(self, user: Dict):
        new_state = 0 if user["is_active"] else 1
        action = "disabled" if new_state == 0 else "enabled"
        if messagebox.askyesno("Confirm",
                               f"{'Disable' if new_state == 0 else 'Enable'} "
                               f"user '{user['username']}'?", parent=self.root):
            db.update_user(user["id"], is_active=new_state)
            self._refresh_users()

    def _delete_user(self, user: Dict):
        if messagebox.askyesno(
            "Confirm Delete",
            f"Permanently delete user '{user['username']}' and all their data?\n"
            "This cannot be undone.",
            parent=self.root
        ):
            db.hard_delete_user(user["id"])
            self._refresh_users()

    def _page_activity(self):
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="System Activity Log", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad, text="All commits made through CommitMaster across all users.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))

        activity = db.get_activity_log(limit=200)

        # Table header
        hdr = tk.Frame(pad, bg=COLORS["bg_medium"])
        hdr.pack(fill="x")
        for col, width in [("User", 16), ("Repository", 18),
                           ("Commit Message", 40), ("Files", 7), ("Date", 16)]:
            tk.Label(hdr, text=col, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                     width=width, anchor="w", padx=6, pady=6).pack(side="left")

        if not activity:
            tk.Label(pad, text="No activity yet.",
                     font=FONTS["body_md"], fg=COLORS["text_muted"],
                     bg=COLORS["bg_dark"]).pack(anchor="w", pady=20)
            return

        for entry in activity:
            row = tk.Frame(pad, bg=COLORS["bg_card"],
                           highlightbackground=COLORS["border"],
                           highlightthickness=0)
            row.pack(fill="x")
            tk.Frame(pad, height=1, bg=COLORS["border"]).pack(fill="x")

            def on_enter(e, r=row): r.config(bg=COLORS["bg_card_hover"])
            def on_leave(e, r=row): r.config(bg=COLORS["bg_card"])
            row.bind("<Enter>", on_enter)
            row.bind("<Leave>", on_leave)

            color = entry.get("avatar_color", AVATAR_COLORS[0])
            av = tk.Label(row, text=(entry.get("username") or "?")[:2].upper(),
                          bg=color, fg="white", font=FONTS["caption"],
                          width=2, padx=3, pady=3)
            av.pack(side="left", padx=(6, 0), pady=5)

            fields = [
                (entry.get("username", ""), 14, COLORS["text_primary"]),
                (entry["repo_name"][:18], 18, COLORS["accent"]),
                (entry["commit_msg"][:40], 40, COLORS["text_primary"]),
                (str(entry.get("files_count", 0)), 7, COLORS["text_secondary"]),
                (entry["committed_at"][:16], 16, COLORS["text_muted"]),
            ]
            for text, width, fcolor in fields:
                tk.Label(row, text=text, font=FONTS["body_sm"],
                         fg=fcolor, bg=COLORS["bg_card"],
                         width=width, anchor="w", padx=4, pady=7).pack(side="left")

    def _page_charts(self):
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Usage Analytics", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad,
                 text="System-wide usage across all users. Charts update on page visit.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 20))

        charts.build_admin_analytics(pad, days=30)

    def _page_global_settings(self):
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Global Settings", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad, text="These defaults apply to all new users.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))

        card = tk.Frame(pad, bg=COLORS["bg_card"],
                        highlightbackground=COLORS["border"],
                        highlightthickness=1, padx=24, pady=20)
        card.pack(fill="x")

        self._global_vars = {}
        settings_fields = [
            ("default_grace_seconds", "Default Grace Period (seconds)", "120"),
            ("default_ai_url", "Default AI Server URL", "http://localhost:1234/v1"),
            ("max_users", "Max Users (0 = unlimited)", "0"),
            ("app_name", "Application Name", "CommitMaster"),
            ("default_theme", "Default System Theme", "github_dark"),
            ("default_accent", "Default Accent Color", "#3fb950"),
            ("default_font_family", "Default Font Family", "Segoe UI"),
        ]

        conn = db.get_conn()
        for key, label, default in settings_fields:
            cur = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            val = row[0] if row else default

            f = tk.Frame(card, bg=COLORS["bg_card"])
            f.pack(fill="x", pady=(0, 12))
            tk.Label(f, text=label, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                     width=30, anchor="w").pack(side="left")
            var = tk.StringVar(value=val)
            self._global_vars[key] = var
            e = tk.Entry(f, textvariable=var, font=FONTS["body_md"],
                         bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                         relief="flat", highlightthickness=1,
                         highlightbackground=COLORS["border"])
            e.pack(side="left", fill="x", expand=True, ipady=6)

        save_btn = tk.Button(pad, text="  💾  Save Global Settings",
                             font=FONTS["heading_sm"], fg="white",
                             bg=COLORS["admin"], activebackground=COLORS["admin_dark"],
                             activeforeground="white", relief="flat", bd=0,
                             cursor="hand2", padx=20, pady=10,
                             command=self._save_global_settings)
        save_btn.pack(anchor="w", pady=(16, 0))

    def _save_global_settings(self):
        conn = db.get_conn()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for key, var in self._global_vars.items():
            conn.execute("""
                INSERT INTO system_settings (key, value, updated_at, updated_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                    updated_at = excluded.updated_at, updated_by = excluded.updated_by
            """, (key, var.get(), now, self.admin_user["id"]))
        conn.commit()
        messagebox.showinfo("Saved", "Global settings saved!", parent=self.root)

    # ── GitHub Accounts Page ──────────────────────────────────────────────────

    def _page_github_accounts(self):
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        top_f = tk.Frame(pad, bg=COLORS["bg_dark"])
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

        accounts = db.get_github_accounts(self.admin_user["id"])
        prefs = db.get_preferences(self.admin_user["id"]) or {}
        dirs_raw = prefs.get("projects_dirs", "[]")
        try:
            proj_dirs = json.loads(dirs_raw)
        except Exception:
            proj_dirs = []
        if not proj_dirs:
            proj_dirs = [db.APP_DIR]
        repos = commit_engine.list_repos(proj_dirs)

        default_acc = db.get_default_github_account(self.admin_user["id"])
        default_name = default_acc["account_name"] if default_acc else "None set"

        # Summary Row
        stats_row = tk.Frame(pad, bg=COLORS["bg_dark"])
        stats_row.pack(fill="x", pady=(0, 16))
        self._stat_card(stats_row, "Linked Accounts", str(len(accounts)), COLORS["accent"], "🐙")
        self._stat_card(stats_row, "Default Push Account", default_name, COLORS["info"], "★")
        self._stat_card(stats_row, "Detected Repos", str(len(repos)), COLORS["warning"], "📁")

        # Section 1: Connected Accounts
        tk.Label(pad, text="Connected Accounts", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(8, 10))

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

        # Section 2: Repository Account Assignment
        tk.Label(pad, text="Repository Account Assignment & Direct Push", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(18, 6))
        tk.Label(pad,
                 text="Select which GitHub account pushes to each repository. Click 'Push Now' to immediately push the current branch.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(0, 12))

        if not repos:
            no_repo_card = self._card(pad, padx=20, pady=20)
            no_repo_card.pack(fill="x", pady=(0, 16))
            tk.Label(no_repo_card, text="No git repositories found in your configured project folders.",
                     font=FONTS["body_md"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w")
        else:
            bindings = db.get_all_repo_bindings(self.admin_user["id"])
            for repo in repos:
                self._build_repo_row(pad, repo, accounts, bindings)

    def _build_account_card(self, parent, acc: Dict):
        card = self._card(parent, padx=16, pady=14)
        card.pack(fill="x", pady=(0, 8))

        row = tk.Frame(card, bg=COLORS["bg_card"])
        row.pack(fill="x")

        av = tk.Label(row, text="🐙", font=("Segoe UI", 16),
                      bg=COLORS["bg_medium"], fg=COLORS["accent"], width=3, height=2)
        av.pack(side="left", padx=(0, 12))

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
                db.unbind_repo_account(self.admin_user["id"], repo_path)
            else:
                db.bind_repo_to_account(self.admin_user["id"], repo_path, aid)

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
        GitHubAccountDialog(self.root, self.admin_user["id"], on_saved=lambda: self._nav_to("github_accounts"))

    def _open_edit_github_dialog(self, account: Dict):
        GitHubAccountDialog(self.root, self.admin_user["id"], account=account, on_saved=lambda: self._nav_to("github_accounts"))

    def _set_account_default(self, account_id: int):
        db.set_default_github_account(account_id, self.admin_user["id"])
        self._nav_to("github_accounts")

    def _delete_github_account(self, account_id: int, name: str):
        if messagebox.askyesno("Confirm Delete", f"Delete linked GitHub account '{name}'?", parent=self.root):
            db.delete_github_account(account_id, self.admin_user["id"])
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
        account = db.get_repo_account(self.admin_user["id"], repo_path)
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

    # ── Customize Interface Page ──────────────────────────────────────────────

    def _page_customize(self):
        p = self._content_frame
        pad = tk.Frame(p, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Customize Interface", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w")
        tk.Label(pad, text="Personalize themes, accent colors, typography, and density for your workspace.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 16))

        prefs = db.get_preferences(self.admin_user["id"]) or {}
        curr = get_active_customization()

        self._custom_theme = curr.get("theme", "github_dark")
        self._custom_accent = curr.get("accent", "green")
        self._custom_accent_hex = tk.StringVar(value=curr.get("accent_hex", "#3fb950"))
        self._custom_font_family = tk.StringVar(value=curr.get("font_family", "Segoe UI"))
        self._custom_font_scale = tk.StringVar(value=curr.get("font_scale", "standard"))
        self._custom_density = tk.StringVar(value=curr.get("ui_density", "comfortable"))
        self._custom_auto_push = tk.BooleanVar(value=bool(prefs.get("auto_push", 0)))

        # Theme Presets Section
        tk.Label(pad, text="Theme Presets", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(4, 10))
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

        # Accent Colors Section
        tk.Label(pad, text="Primary Accent Color", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(8, 10))
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
        apply_hex_btn = tk.Button(hex_row, text="Set Hex", font=FONTS["caption"],
                                  fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                                  relief="flat", bd=0, padx=8, pady=3, command=self._apply_custom_hex)
        apply_hex_btn.pack(side="left")

        # Typography & Scaling
        tk.Label(pad, text="Typography & Scaling", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(8, 10))
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

        # Action Buttons
        action_f = tk.Frame(pad, bg=COLORS["bg_dark"])
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
            self.admin_user["id"],
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
            self.admin_user["id"],
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
        name = self.admin_user.get("full_name") or self.admin_user["username"]
        parts = name.strip().split()
        return ((parts[0][0] + parts[-1][0]) if len(parts) >= 2 else name[:2]).upper()

    def _user_initials(self, user: Dict) -> str:
        name = user.get("full_name") or user["username"]
        parts = name.strip().split()
        return ((parts[0][0] + parts[-1][0]) if len(parts) >= 2 else name[:2]).upper()

    def _go_back(self):
        self.root.destroy()
        self.on_close()

    def run(self):
        self.root.mainloop()


# ── User Create/Edit Dialog ───────────────────────────────────────────────────

class _UserDialog(tk.simpledialog.Dialog if hasattr(tk, "simpledialog") else object):
    pass


class _UserDialog:
    """A modal dialog for creating or editing a user."""

    def __init__(self, parent, title: str, user: Dict = None):
        self.result = None
        self.user = user
        self._build(parent, title)

    def _build(self, parent, title: str):
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.configure(bg=COLORS["bg_dark"])
        self.top.geometry("420x520")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.focus_set()
        self.top.transient(parent)

        pad = tk.Frame(self.top, bg=COLORS["bg_dark"], padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text=title, font=FONTS["heading_md"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(anchor="w", pady=(0, 16))

        self._vars = {}
        is_edit = self.user is not None

        fields = [
            ("Full Name",  "full_name", self.user.get("full_name", "") if is_edit else "", False),
            ("Username",   "username",  self.user.get("username", "") if is_edit else "", False),
            ("Email",      "email",     self.user.get("email", "") if is_edit else "", False),
            ("Password",   "password",  "", True),
        ]
        if is_edit:
            fields[-1] = ("New Password (leave blank to keep)", "password", "", True)

        for label, key, default, is_pw in fields:
            f = tk.Frame(pad, bg=COLORS["bg_dark"])
            f.pack(fill="x", pady=(0, 10))
            tk.Label(f, text=label, font=FONTS["label_bold"],
                     fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]).pack(anchor="w")
            var = tk.StringVar(value=default)
            self._vars[key] = var
            e = tk.Entry(f, textvariable=var, font=FONTS["body_md"],
                         bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                         relief="flat", highlightthickness=1,
                         highlightbackground=COLORS["border"],
                         show="•" if is_pw else "")
            e.pack(fill="x", ipady=7)
            if key == "username" and is_edit:
                e.config(state="disabled")

        # Role (strictly locked: only saumya.patel@Admin_# is admin)
        rf = tk.Frame(pad, bg=COLORS["bg_dark"])
        rf.pack(fill="x", pady=(0, 10))
        is_saumya = is_edit and self.user.get("username") == "saumya.patel@Admin_#"
        if is_saumya:
            self._role_var = tk.StringVar(value="admin")
            tk.Label(rf, text="Role: Administrator", font=FONTS["label_bold"],
                     fg=COLORS["admin"], bg=COLORS["bg_dark"]).pack(anchor="w")
            tk.Label(rf, text="Primary Administrator — role cannot be changed",
                     font=FONTS["caption"], fg=COLORS["text_muted"], bg=COLORS["bg_dark"]).pack(anchor="w")
        else:
            self._role_var = tk.StringVar(value="user")
            tk.Label(rf, text="Role: Standard User", font=FONTS["label_bold"],
                     fg=COLORS["accent"], bg=COLORS["bg_dark"]).pack(anchor="w")
            tk.Label(rf, text="Account role locked to User (only saumya.patel@Admin_# holds Admin rights)",
                     font=FONTS["caption"], fg=COLORS["text_muted"], bg=COLORS["bg_dark"]).pack(anchor="w")

        # Buttons
        btn_f = tk.Frame(pad, bg=COLORS["bg_dark"])
        btn_f.pack(fill="x", pady=(12, 0))
        tk.Button(btn_f, text="Cancel", font=FONTS["label"],
                  fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                  relief="flat", bd=0, cursor="hand2", padx=16, pady=7,
                  command=self.top.destroy).pack(side="right", padx=(6, 0))
        tk.Button(btn_f, text="Save" if is_edit else "Create",
                  font=FONTS["label_bold"], fg="white",
                  bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                  activeforeground="white", relief="flat", bd=0,
                  cursor="hand2", padx=16, pady=7,
                  command=self._submit).pack(side="right")

        parent.wait_window(self.top)

    def _submit(self):
        data = {k: v.get().strip() for k, v in self._vars.items()}
        data["role"] = self._role_var.get()
        self.result = data
        self.top.destroy()
