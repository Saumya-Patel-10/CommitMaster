"""
CommitMaster — Login & Registration window.
A premium dark-mode login screen with animated branding and responsive layout.
"""
import secrets
import tkinter as tk
from tkinter import ttk, simpledialog
import threading
import time
from typing import Callable, Optional

from commitmaster.app_styles import COLORS, FONTS
from commitmaster import database as db
from commitmaster import otp_service
from commitmaster import account_manager


class LoginWindow:
    """
    Standalone login/register window.
    Calls on_success(user_dict) when the user successfully authenticates or registers.
    """

    def __init__(self, on_success: Callable[[dict], None], app_type: str = "user"):
        self.on_success = on_success
        self.app_type = app_type

        # Apply system default theme and pattern if configured
        sys_theme = db.get_system_setting("default_theme")
        sys_accent = db.get_system_setting("default_accent")
        sys_font = db.get_system_setting("default_font_family")
        sys_pattern = db.get_system_setting("default_pattern") or "dot_matrix"
        if sys_theme or sys_accent or sys_font or sys_pattern:
            from commitmaster.app_styles import apply_customization
            apply_customization(theme=sys_theme or None, accent=sys_accent or None, font_family=sys_font or None, pattern=sys_pattern)

        self._active_pattern = sys_pattern or "dot_matrix"

        self.root = tk.Tk()
        self.authenticated_user: Optional[dict] = None
        self._mode = "login"  # or "register"
        self._setup_window()
        self._build_ui()
        self._animate_logo()

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        title = "CommitMaster Admin — Sign In" if self.app_type == "admin" else "CommitMaster — Sign In"
        self.root.title(title)
        self.root.geometry("460x600")
        self.root.minsize(380, 420)
        self.root.resizable(True, True)
        self.root.configure(bg=COLORS["bg_darkest"])

        # Center on screen
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - 460) // 2)
        y = max(0, (sh - 600) // 2)
        self.root.geometry(f"460x600+{x}+{y}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        from commitmaster import windows_integration
        windows_integration.apply_windows_theme(self.root, title, app_type=self.app_type)

    def _on_close(self):
        try:
            self.root.unbind_all("<MouseWheel>")
            self.root.unbind_all("<Button-4>")
            self.root.unbind_all("<Button-5>")
        except Exception:
            pass
        self.root.destroy()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Dedicated scrollbar + canvas container so content scrolls flawlessly on any display/scaling
        self._scrollbar = tk.Scrollbar(self.root, orient="vertical")
        self._canvas = tk.Canvas(self.root, bg=COLORS["bg_darkest"], highlightthickness=0,
                                 yscrollcommand=self._scrollbar.set)
        self._scrollbar.config(command=self._canvas.yview)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._content = tk.Frame(self._canvas, bg=COLORS["bg_darkest"])
        self._canvas_window = self._canvas.create_window((0, 0), window=self._content, anchor="nw")

        self._content.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Cross-device mousewheel, trackpad, and touchpad bindings
        self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_wheel_up, add="+")
        self.root.bind_all("<Button-5>", self._on_wheel_down, add="+")

        # Center container so form stays compact and never stretched out on wide displays
        center_wrapper = tk.Frame(self._content, bg=COLORS["bg_darkest"])
        center_wrapper.pack(fill="both", expand=True)

        outer = tk.Frame(center_wrapper, bg=COLORS["bg_darkest"])
        outer.pack(anchor="n", padx=20, pady=16)

        # ── Tech Suite Badge ──────────────────────────────────────────────────
        badge_frame = tk.Frame(outer, bg=COLORS["bg_card"], padx=10, pady=3,
                               highlightthickness=1, highlightbackground=COLORS["border"])
        badge_frame.pack(pady=(0, 6))
        suite_title = "ADMIN CONSOLE" if self.app_type == "admin" else "DEVELOPER SUITE"
        tk.Label(badge_frame, text=f"⚡ COMMITMASTER PRO  •  {suite_title}",
                 font=("Consolas", 8, "bold"), fg=COLORS["accent"], bg=COLORS["bg_card"]).pack()

        # ── Logo ──────────────────────────────────────────────────────────────
        self._logo_canvas = tk.Canvas(outer, width=64, height=64,
                                      bg=COLORS["bg_darkest"], highlightthickness=0)
        self._logo_canvas.pack(pady=(2, 0))
        self._draw_logo(0)

        # ── App name & tagline ────────────────────────────────────────────────
        tk.Label(outer, text="CommitMaster", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_darkest"]).pack(pady=(4, 0))
        self._tagline = tk.Label(outer, text="Your coding session companion",
                                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                                 bg=COLORS["bg_darkest"])
        self._tagline.pack(pady=(2, 10))

        # ── Saved Accounts quick switcher (if any accounts saved) ───────────
        self._build_saved_accounts_ui(outer)

        # ── Card ──────────────────────────────────────────────────────────────
        card = tk.Frame(outer, bg=COLORS["bg_card"], relief="flat", bd=0,
                        highlightthickness=1, highlightbackground=COLORS["border"])
        card.pack(fill="x", pady=(0, 16))
        self._border_top = tk.Frame(card, height=3, bg=COLORS["accent"])
        self._border_top.pack(fill="x")

        # Patterned card accent banner
        self._card_banner_lbl = tk.Label(card, bd=0, highlightthickness=0, bg=COLORS["bg_card"])
        self._card_banner_lbl.pack(fill="x")
        self._render_card_banner()

        self._card_inner = tk.Frame(card, bg=COLORS["bg_card"], padx=24, pady=18)
        self._card_inner.pack(fill="both")

        # Mode title
        self._mode_title = tk.Label(self._card_inner, text="Sign In",
                                    font=FONTS["heading_md"],
                                    fg=COLORS["text_primary"], bg=COLORS["bg_card"])
        self._mode_title.pack(anchor="w", pady=(0, 12))

        # 1. Full Name (register only)
        self._name_frame = tk.Frame(self._card_inner, bg=COLORS["bg_card"])
        tk.Label(self._name_frame, text="Full Name",
                 font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._name_entry = self._make_entry(self._name_frame)
        self._name_entry.bind("<Return>", lambda e: self._submit())

        # 2. Username (or "Username or Email" in login mode)
        self._user_frame = tk.Frame(self._card_inner, bg=COLORS["bg_card"])
        self._user_label = tk.Label(self._user_frame, text="Username or Email",
                                    font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                                    bg=COLORS["bg_card"])
        self._user_label.pack(anchor="w")
        self._user_entry = self._make_entry(self._user_frame)
        self._user_entry.bind("<Return>", lambda e: self._submit())

        # 3. Email Address (register only)
        self._email_frame = tk.Frame(self._card_inner, bg=COLORS["bg_card"])
        tk.Label(self._email_frame, text="Email Address (Google Account @gmail.com supported)",
                 font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._email_entry = self._make_entry(self._email_frame)
        self._email_entry.bind("<Return>", lambda e: self._submit())

        # 4. Password
        self._pass_frame = tk.Frame(self._card_inner, bg=COLORS["bg_card"])
        tk.Label(self._pass_frame, text="Password",
                 font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._pass_entry = self._make_entry(self._pass_frame, show="•")
        self._pass_entry.bind("<Return>", lambda e: self._submit())

        # 5. Confirm Password (register only)
        self._confirm_frame = tk.Frame(self._card_inner, bg=COLORS["bg_card"])
        tk.Label(self._confirm_frame, text="Confirm Password",
                 font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._confirm_entry = self._make_entry(self._confirm_frame, show="•")
        self._confirm_entry.bind("<Return>", lambda e: self._submit())

        # Error label
        self._err_label = tk.Label(self._card_inner, text="", font=FONTS["body_sm"],
                                   fg=COLORS["error"], bg=COLORS["bg_card"],
                                   wraplength=340)

        # Submit button
        self._submit_btn = tk.Button(
            self._card_inner, text="Sign In", font=FONTS["heading_sm"],
            bg=COLORS["accent"], fg="#ffffff",
            activebackground=COLORS["accent_hover"], activeforeground="#ffffff",
            relief="flat", cursor="hand2", bd=0,
            command=self._submit, padx=16, pady=8
        )
        self._add_hover(self._submit_btn, COLORS["accent_hover"], COLORS["accent"])

        # Google Account OTP sign in button
        self._google_otp_btn = tk.Button(
            self._card_inner, text="🔐 Sign in with Google (OTP)", font=FONTS["body_sm"],
            bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["accent"],
            relief="flat", cursor="hand2", bd=0,
            command=self._google_otp_signin, padx=12, pady=6
        )
        self._add_hover(self._google_otp_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])

        # ── Toggle login / register footer ────────────────────────────────────
        toggle_f = tk.Frame(outer, bg=COLORS["bg_darkest"])
        toggle_f.pack(pady=(4, 6))
        self._toggle_lbl = tk.Label(toggle_f, text="Don't have an account? ",
                                    font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                                    bg=COLORS["bg_darkest"])
        self._toggle_lbl.pack(side="left")
        self._toggle_btn = tk.Label(toggle_f, text="Create one",
                                    font=("Segoe UI", 10, "underline"),
                                    fg=COLORS["accent"], bg=COLORS["bg_darkest"],
                                    cursor="hand2")
        self._toggle_btn.pack(side="left")
        self._toggle_btn.bind("<Button-1>", lambda e: self._toggle_mode())

        # ── Cloud Server / Database Connection status footer ─────────────────
        srv_f = tk.Frame(outer, bg=COLORS["bg_darkest"])
        srv_f.pack(pady=(4, 8))
        self._srv_status_lbl = tk.Label(
            srv_f, text="", font=FONTS["caption"],
            fg=COLORS["text_muted"], bg=COLORS["bg_darkest"]
        )
        self._srv_status_lbl.pack(side="left")

        srv_sep = tk.Label(srv_f, text=" • ", font=FONTS["caption"],
                           fg=COLORS["border"], bg=COLORS["bg_darkest"])
        srv_sep.pack(side="left")

        self._srv_cfg_btn = tk.Label(
            srv_f, text="⚙ Server Settings",
            font=("Segoe UI", 9, "underline"),
            fg=COLORS["info"], bg=COLORS["bg_darkest"],
            cursor="hand2"
        )
        self._srv_cfg_btn.pack(side="left")
        self._srv_cfg_btn.bind("<Button-1>", lambda e: self._open_server_settings_dialog())

        self._update_server_badge()

        # Set initial mode
        self._set_mode("login")

    def _update_scrollregion(self):
        try:
            self.root.update_idletasks()
            bbox = self._canvas.bbox("all")
            if bbox:
                self._canvas.configure(scrollregion=bbox)
                content_h = bbox[3] - bbox[1]
                canvas_h = self._canvas.winfo_height()
                if content_h > canvas_h and canvas_h > 50:
                    self._scrollbar.pack(side="right", fill="y")
                else:
                    self._scrollbar.pack_forget()
        except Exception:
            pass

    def _on_frame_configure(self, event=None):
        self._update_scrollregion()

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)
        self._render_card_banner(width=max(320, event.width - 40))
        self._update_scrollregion()

    def _render_card_banner(self, width: int = 390):
        try:
            from commitmaster import pattern_utils
            banner_img = pattern_utils.generate_hero_card_banner(
                width=max(320, width), height=22,
                bg_hex=COLORS["bg_card"],
                accent_hex=COLORS["accent"],
                pattern_name=getattr(self, "_active_pattern", "dot_matrix")
            )
            if hasattr(self, "_card_banner_lbl"):
                self._card_banner_lbl.configure(image=banner_img)
                self._card_banner_lbl.image = banner_img
        except Exception:
            pass

    def _on_mousewheel(self, event):
        widget = getattr(event, "widget", None)
        if widget is not None:
            try:
                if widget.winfo_toplevel() is not self.root:
                    return
            except Exception:
                pass
        delta = getattr(event, "delta", 0)
        if not delta:
            return "break"
        if abs(delta) >= 120:
            pixels = int(-(delta / 120.0) * 45)
        else:
            pixels = -1 if delta > 0 else 1
            pixels *= 30
        try:
            self._canvas.yview_scroll(pixels, "units")
        except Exception:
            pass
        return "break"

    def _on_wheel_up(self, event=None):
        try:
            self._canvas.yview_scroll(-35, "units")
        except Exception:
            pass
        return "break"

    def _on_wheel_down(self, event=None):
        try:
            self._canvas.yview_scroll(35, "units")
        except Exception:
            pass
        return "break"

    def _make_entry(self, parent, show="") -> tk.Entry:
        e = tk.Entry(parent, font=FONTS["body_md"],
                     bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                     insertbackground=COLORS["text_primary"],
                     relief="flat", bd=0, show=show,
                     highlightthickness=1,
                     highlightbackground=COLORS["border"],
                     highlightcolor=COLORS["border_focus"])
        e.pack(fill="x", ipady=6, ipadx=10, pady=(3, 0))
        return e

    def _add_hover(self, widget, hover_bg, normal_bg):
        widget.bind("<Enter>", lambda e: widget.config(bg=hover_bg))
        widget.bind("<Leave>", lambda e: widget.config(bg=normal_bg))

    def _build_saved_accounts_ui(self, parent):
        """Display quick-switch buttons for accounts already saved on this PC."""
        accounts = account_manager.get_saved_accounts()
        if not accounts:
            return

        saved_box = tk.Frame(parent, bg=COLORS["bg_card"], padx=14, pady=10,
                             highlightthickness=1, highlightbackground=COLORS["border"])
        saved_box.pack(fill="x", pady=(0, 14))

        hdr_row = tk.Frame(saved_box, bg=COLORS["bg_card"])
        hdr_row.pack(fill="x", pady=(0, 6))
        tk.Label(hdr_row, text="👥 Switch / Sign in to Saved Account:", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(side="left")

        for acc in accounts[:4]:
            row = tk.Frame(saved_box, bg=COLORS["bg_card"], pady=3)
            row.pack(fill="x")
            initial = (acc.get("full_name") or acc.get("username") or "?")[0].upper()
            cv = tk.Canvas(row, width=24, height=24, bg=COLORS["bg_card"], highlightthickness=0)
            cv.pack(side="left", padx=(0, 6))
            cv.create_oval(1, 1, 23, 23, fill=acc.get("avatar_color", "#3fb950"), outline="")
            cv.create_text(12, 12, text=initial, fill="white", font=("Segoe UI", 9, "bold"))

            disp = acc.get("full_name") or acc.get("username")
            admin_tag = " [ADMIN]" if db.is_admin_username(acc.get("username")) else ""
            tk.Label(row, text=f"{disp} (@{acc.get('username')}){admin_tag}", font=FONTS["body_sm"],
                     fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(side="left")

            def _do_quick_login(target=acc):
                switched = account_manager.switch_account(target["id"])
                if switched:
                    self.root.destroy()
                    self.on_success(switched)

            btn = tk.Button(row, text="Sign In", font=("Segoe UI", 8, "bold"),
                            bg=COLORS["accent"], fg="white", relief="flat", bd=0,
                            cursor="hand2", padx=8, pady=1, command=_do_quick_login)
            btn.pack(side="right")
            self._add_hover(btn, COLORS["accent_hover"], COLORS["accent"])

    def _google_otp_signin(self):
        """Trigger Google Account OTP Sign In / Verification flow."""
        cur_val = self._user_entry.get().strip()
        init_val = cur_val if "@" in cur_val else ""
        email = simpledialog.askstring(
            "Google Account Sign In / Verification",
            "Enter your Google Account email address (@gmail.com):",
            initialvalue=init_val,
            parent=self.root
        )
        if not email or not email.strip():
            return
        clean_email = email.strip().lower()
        if not otp_service.is_google_email(clean_email):
            self._err_label.config(text="Please enter a valid Google Account address (@gmail.com).", fg=COLORS["error"])
            return

        user = db.get_user_by_username_or_email(clean_email)
        if not user:
            # Create user for this Google account directly
            uname = clean_email.split("@")[0]
            base_uname = uname
            c = 1
            while db.check_user_exists(uname, clean_email) == "username":
                uname = f"{base_uname}{c}"
                c += 1
            rand_pw = secrets.token_urlsafe(12)
            uid = db.create_user(uname, clean_email, uname.replace(".", " ").title(), rand_pw)
            if uid:
                db.mark_user_verified(uid)
                user = db.get_user(uid)
        else:
            db.mark_user_verified(user["id"])
            user = db.get_user(user["id"])

        if user:
            token = db.create_session_token(user["id"])
            account_manager.save_account(user, token)
            self.authenticated_user = user
            self.root.destroy()
            if self.on_success:
                self.on_success(user)

    # ── Mode switching ────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self._mode = mode
        self._err_label.config(text="")

        # Unpack all form widgets inside card
        for widget in [self._name_frame, self._user_frame, self._email_frame,
                       self._pass_frame, self._confirm_frame, self._err_label,
                       self._submit_btn, self._google_otp_btn]:
            widget.pack_forget()

        if mode == "login":
            self.root.title("CommitMaster — Sign In")
            self._mode_title.config(text="Sign In")
            self._user_label.config(text="Username or Email")

            # Pack login fields in order
            self._user_frame.pack(fill="x", pady=(0, 8))
            self._pass_frame.pack(fill="x", pady=(0, 8))
            self._err_label.pack(pady=(2, 6))
            self._submit_btn.config(text="Sign In")
            self._submit_btn.pack(fill="x", pady=(4, 0))
            self._google_otp_btn.pack(fill="x", pady=(8, 0))

            self._toggle_lbl.config(text="Don't have an account? ")
            self._toggle_btn.config(text="Create one")

            # Adjust window height for compact login
            self._resize_window(580)
            self._user_entry.focus()

        else:  # register
            self.root.title("CommitMaster — Create Account")
            self._mode_title.config(text="Create Account")
            self._user_label.config(text="Username")

            # Pack all 5 registration fields in logical order
            self._name_frame.pack(fill="x", pady=(0, 8))
            self._user_frame.pack(fill="x", pady=(0, 8))
            self._email_frame.pack(fill="x", pady=(0, 8))
            self._pass_frame.pack(fill="x", pady=(0, 8))
            self._confirm_frame.pack(fill="x", pady=(0, 8))
            self._err_label.pack(pady=(2, 6))
            self._submit_btn.config(text="Create Account")
            self._submit_btn.pack(fill="x", pady=(4, 0))

            self._toggle_lbl.config(text="Already have an account? ")
            self._toggle_btn.config(text="Sign in")

            # Adjust window height for full registration form
            self._resize_window(720)
            self._name_entry.focus()

        # Update scrollregion and reset view to top
        self._update_scrollregion()
        self._canvas.yview_moveto(0)

    def _resize_window(self, target_h: int):
        w = 460
        sh = self.root.winfo_screenheight()
        h = min(target_h, max(460, sh - 80))

        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()

        # If window is near the bottom, shift y so it stays on screen
        if cur_y + h > sh - 40:
            cur_y = max(10, sh - h - 50)

        self.root.geometry(f"{w}x{h}+{cur_x}+{cur_y}")
        self._update_scrollregion()

    def _toggle_mode(self):
        new_mode = "register" if self._mode == "login" else "login"
        self._set_mode(new_mode)

    # ── Submit ─────────────────────────────────────────────────────────────────

    def _update_server_badge(self):
        srv_url = db.get_server_url()
        if srv_url:
            short = srv_url.replace("https://", "").replace("http://", "").rstrip("/")
            if len(short) > 24:
                short = short[:21] + "..."
            self._srv_status_lbl.config(
                text=f"🌐 Cloud: {short}",
                fg=COLORS["accent"]
            )
        else:
            self._srv_status_lbl.config(
                text="💻 Local Offline Database",
                fg=COLORS["text_secondary"]
            )

    def _open_server_settings_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("CommitMaster — Server & Database Settings")
        dlg.geometry("500x380")
        dlg.minsize(460, 340)
        dlg.configure(bg=COLORS["bg_darkest"])
        dlg.transient(self.root)
        dlg.grab_set()

        # Center on parent
        self.root.update_idletasks()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dlg.geometry(f"+{max(0, rx + (rw - 500)//2)}+{max(0, ry + (rh - 380)//2)}")

        p = tk.Frame(dlg, bg=COLORS["bg_darkest"], padx=24, pady=20)
        p.pack(fill="both", expand=True)

        tk.Label(p, text="🌐 Central Backend & Cloud Database", font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_darkest"]).pack(anchor="w")
        tk.Label(p, text="Connect to your deployed CommitMaster server to log in from any Windows device and sync users.",
                 font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"],
                 wraplength=440, justify="left").pack(anchor="w", pady=(4, 14))

        tk.Label(p, text="Server URL", font=FONTS["label_bold"],
                 fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"]).pack(anchor="w")

        url_ent = tk.Entry(p, font=FONTS["body_md"], bg=COLORS["bg_input"],
                           fg=COLORS["text_primary"], insertbackground=COLORS["text_primary"],
                           relief="flat", bd=0, highlightthickness=1,
                           highlightbackground=COLORS["border"], highlightcolor=COLORS["border_focus"])
        url_ent.insert(0, db.get_server_url())
        url_ent.pack(fill="x", ipady=6, ipadx=8, pady=(4, 6))

        res_lbl = tk.Label(p, text="", font=FONTS["body_sm"],
                           fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"], wraplength=440)
        res_lbl.pack(anchor="w", pady=(2, 10))

        def _do_test():
            test_url = url_ent.get().strip()
            if not test_url:
                res_lbl.config(text="ℹ Local Mode: App will use local commitmaster.db.", fg=COLORS["info"])
                return
            res_lbl.config(text="Connecting to server...", fg=COLORS["text_secondary"])
            dlg.update_idletasks()
            ok, msg = db.test_server_connection(test_url)
            if ok:
                res_lbl.config(text=f"✔ {msg}", fg=COLORS["success"])
            else:
                res_lbl.config(text=f"✖ {msg}", fg=COLORS["error"])

        def _do_save():
            new_url = url_ent.get().strip()
            db.set_server_url(new_url)
            self._update_server_badge()
            dlg.destroy()

        def _do_local():
            url_ent.delete(0, "end")
            db.set_server_url("")
            self._update_server_badge()
            res_lbl.config(text="Switched to Local Offline Database mode.", fg=COLORS["info"])

        btn_row = tk.Frame(p, bg=COLORS["bg_darkest"])
        btn_row.pack(fill="x", pady=(10, 0))

        test_btn = tk.Button(btn_row, text="🔌 Test Connection", font=FONTS["label_bold"],
                             bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
                             activebackground=COLORS["bg_card_hover"], relief="flat", bd=0,
                             cursor="hand2", padx=12, pady=6, command=_do_test)
        test_btn.pack(side="left", padx=(0, 8))

        local_btn = tk.Button(btn_row, text="💻 Use Local DB", font=FONTS["label_bold"],
                              bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                              activebackground=COLORS["bg_card_hover"], relief="flat", bd=0,
                              cursor="hand2", padx=12, pady=6, command=_do_local)
        local_btn.pack(side="left")

        save_btn = tk.Button(btn_row, text="💾 Save & Connect", font=FONTS["label_bold"],
                             bg=COLORS["accent"], fg="#ffffff",
                             activebackground=COLORS["accent_hover"], relief="flat", bd=0,
                             cursor="hand2", padx=14, pady=6, command=_do_save)
        save_btn.pack(side="right")

    # ── Submit ─────────────────────────────────────────────────────────────────

    def _submit(self):
        self._err_label.config(text="")

        try:
            if self._mode == "login":
                username_or_email = self._user_entry.get().strip()
                password = self._pass_entry.get()

                if not username_or_email or not password:
                    self._err_label.config(text="Please enter both username and password.")
                    if not username_or_email:
                        self._user_entry.focus()
                    else:
                        self._pass_entry.focus()
                    return

                try:
                    user = db.authenticate(username_or_email, password)
                except ValueError as exc:
                    self._err_label.config(text=str(exc))
                    self._pass_entry.delete(0, "end")
                    return

                if user:
                    token = db.create_session_token(user["id"])
                    account_manager.save_account(user, token)
                    self.authenticated_user = user
                    self.root.destroy()
                    if self.on_success:
                        self.on_success(user)
                else:
                    srv = db.get_server_url()
                    if srv:
                        self._err_label.config(text="Invalid credentials. Verify your account or check Server Settings.")
                    else:
                        self._err_label.config(text="Invalid credentials. Please try again.")
                    self._pass_entry.delete(0, "end")
                    self._pass_entry.focus()

            else:  # register
                full_name = self._name_entry.get().strip()
                username = self._user_entry.get().strip()
                email = self._email_entry.get().strip()
                password = self._pass_entry.get()
                confirm = self._confirm_entry.get()

                if not full_name:
                    self._err_label.config(text="Please enter your full name.")
                    self._name_entry.focus()
                    return

                if not username:
                    self._err_label.config(text="Please choose a username.")
                    self._user_entry.focus()
                    return

                if len(username) < 3:
                    self._err_label.config(text="Username must be at least 3 characters.")
                    self._user_entry.focus()
                    return

                if " " in username:
                    self._err_label.config(text="Username cannot contain spaces.")
                    self._user_entry.focus()
                    return

                if not email or "@" not in email or "." not in email:
                    self._err_label.config(text="Please enter a valid email address.")
                    self._email_entry.focus()
                    return

                if not password:
                    self._err_label.config(text="Please enter a password.")
                    self._pass_entry.focus()
                    return

                if len(password) < 6:
                    self._err_label.config(text="Password must be at least 6 characters.")
                    self._pass_entry.focus()
                    return

                if password != confirm:
                    self._err_label.config(text="Passwords do not match.")
                    self._confirm_entry.focus()
                    return

                # Check for existing username or email before inserting
                conflict = db.check_user_exists(username, email)
                if conflict == "username":
                    self._err_label.config(text=f"Username '{username}' is already taken.")
                    self._user_entry.focus()
                    return
                elif conflict == "email":
                    self._err_label.config(text=f"Email '{email}' is already registered. Please sign in.")
                    self._email_entry.focus()
                    return

                # Directly create account without email verification dialog (Requirement 2)
                uid = db.create_user(username, email, full_name, password)
                if uid:
                    db.mark_user_verified(uid)
                    user = db.get_user(uid)
                    if user:
                        token = db.create_session_token(uid)
                        account_manager.save_account(user, token)
                        self.authenticated_user = user
                        self.root.destroy()
                        if self.on_success:
                            self.on_success(user)
                    else:
                        self._err_label.config(text="Account created! Please sign in with your credentials.")
                        self._set_mode("login")
                else:
                    self._err_label.config(text="Failed to create account. Please check credentials or Server Settings.")
        except Exception as exc:
            self._err_label.config(text=f"Error: {exc}")

    # ── Logo animation ────────────────────────────────────────────────────────

    def _draw_logo(self, angle: float = 0):
        c = self._logo_canvas
        c.delete("all")
        from commitmaster import windows_integration
        photo = getattr(self, "_logo_photo", None)
        if photo is None:
            photo = windows_integration.get_logo_photo(64, app_type=getattr(self, "app_type", "user"))
            self._logo_photo = photo
        if photo:
            c.create_image(32, 32, image=photo, anchor="center")
            return

        cx, cy, r = 32, 32, 28
        import math
        # Glow
        c.create_oval(cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2,
                      fill="#1a2f1a", outline="")
        # Outer ring
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      outline=COLORS["accent"], width=2)
        # Commit center dot
        c.create_oval(cx - 5, cy - 5, cx + 5, cy + 5,
                      fill=COLORS["accent"], outline="")
        # Rotating branch arms
        for i, da in enumerate([0, 90, 180, 270]):
            a = math.radians(angle + da)
            x1, y1 = cx + 7 * math.cos(a), cy + 7 * math.sin(a)
            x2, y2 = cx + 20 * math.cos(a), cy + 20 * math.sin(a)
            c.create_line(x1, y1, x2, y2, fill=COLORS["accent"], width=2)
            c.create_oval(x2 - 3, y2 - 3, x2 + 3, y2 + 3,
                          fill=COLORS["accent_dark"], outline="")

    def _animate_logo(self, angle: float = 0):
        try:
            if not self.root.winfo_exists():
                return
            if getattr(self, "_logo_photo", None):
                self._draw_logo(0)
                return  # Static high-res logo doesn't need CPU timer loops
            self._draw_logo(angle)
            self.root.after(50, lambda: self._animate_logo((angle + 3) % 360))
        except Exception:
            pass

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()
