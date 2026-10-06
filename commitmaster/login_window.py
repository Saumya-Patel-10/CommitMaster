"""
CommitMaster — Login & Registration window.
A premium dark-mode login screen with animated branding and responsive layout.
"""
import tkinter as tk
from tkinter import ttk
import threading
import time
from typing import Callable, Optional

from commitmaster.app_styles import COLORS, FONTS
from commitmaster import database as db


class LoginWindow:
    """
    Standalone login/register window.
    Calls on_success(user_dict) when the user successfully authenticates or registers.
    """

    def __init__(self, on_success: Callable[[dict], None]):
        self.on_success = on_success

        # Apply system default theme if configured
        sys_theme = db.get_system_setting("default_theme")
        sys_accent = db.get_system_setting("default_accent")
        sys_font = db.get_system_setting("default_font_family")
        if sys_theme or sys_accent or sys_font:
            from commitmaster.app_styles import apply_customization
            apply_customization(theme=sys_theme or None, accent=sys_accent or None, font_family=sys_font or None)

        self.root = tk.Tk()
        self._mode = "login"  # or "register"
        self._setup_window()
        self._build_ui()
        self._animate_logo()

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        self.root.title("CommitMaster — Sign In")
        self.root.geometry("460x540")
        self.root.minsize(440, 500)
        self.root.resizable(True, True)
        self.root.configure(bg=COLORS["bg_darkest"])

        # Center on screen
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - 460) // 2)
        y = max(0, (sh - 540) // 2)
        self.root.geometry(f"460x540+{x}+{y}")
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        from commitmaster import windows_integration
        windows_integration.apply_windows_theme(self.root, "CommitMaster — Sign In")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Scrollable container so content is NEVER cut off on any display/scaling
        self._canvas = tk.Canvas(self.root, bg=COLORS["bg_darkest"], highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)

        self._content = tk.Frame(self._canvas, bg=COLORS["bg_darkest"])
        self._canvas_window = self._canvas.create_window((0, 0), window=self._content, anchor="nw")

        self._content.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel scroll support
        self.root.bind("<MouseWheel>", self._on_mousewheel)

        outer = tk.Frame(self._content, bg=COLORS["bg_darkest"])
        outer.pack(fill="both", expand=True, padx=36, pady=20)

        # ── Logo ──────────────────────────────────────────────────────────────
        self._logo_canvas = tk.Canvas(outer, width=64, height=64,
                                      bg=COLORS["bg_darkest"], highlightthickness=0)
        self._logo_canvas.pack(pady=(4, 0))
        self._draw_logo(0)

        # ── App name & tagline ────────────────────────────────────────────────
        tk.Label(outer, text="CommitMaster", font=FONTS["heading_lg"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_darkest"]).pack(pady=(4, 0))
        self._tagline = tk.Label(outer, text="Your coding session companion",
                                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                                 bg=COLORS["bg_darkest"])
        self._tagline.pack(pady=(2, 14))

        # ── Card ──────────────────────────────────────────────────────────────
        card = tk.Frame(outer, bg=COLORS["bg_card"], relief="flat", bd=0)
        card.pack(fill="x", pady=(0, 16))
        self._border_top = tk.Frame(card, height=2, bg=COLORS["accent"])
        self._border_top.pack(fill="x")

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
        tk.Label(self._email_frame, text="Email Address",
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

        # ── Toggle login / register footer ────────────────────────────────────
        toggle_f = tk.Frame(outer, bg=COLORS["bg_darkest"])
        toggle_f.pack(pady=(4, 10))
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

        # Set initial mode
        self._set_mode("login")

    def _on_frame_configure(self, event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        if self._canvas.winfo_height() < self._content.winfo_reqheight():
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

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

    # ── Mode switching ────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self._mode = mode
        self._err_label.config(text="")

        # Unpack all form widgets inside card
        for widget in [self._name_frame, self._user_frame, self._email_frame,
                       self._pass_frame, self._confirm_frame, self._err_label,
                       self._submit_btn]:
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

            self._toggle_lbl.config(text="Don't have an account? ")
            self._toggle_btn.config(text="Create one")

            # Adjust window height for compact login
            self._resize_window(540)
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
            self._resize_window(690)
            self._name_entry.focus()

        # Update scrollregion
        self.root.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _resize_window(self, target_h: int):
        cur_w = self.root.winfo_width()
        cur_h = self.root.winfo_height()
        w = max(460, cur_w if cur_w > 100 else 460)

        # Check screen height
        sh = self.root.winfo_screenheight()
        h = min(target_h, sh - 80)

        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()

        # If window is near the bottom, shift y so it stays on screen
        if cur_y + h > sh - 40:
            cur_y = max(20, sh - h - 60)

        self.root.geometry(f"{w}x{h}+{cur_x}+{cur_y}")

    def _toggle_mode(self):
        new_mode = "register" if self._mode == "login" else "login"
        self._set_mode(new_mode)

    # ── Submit ─────────────────────────────────────────────────────────────────

    def _submit(self):
        self._err_label.config(text="")

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

            user = db.authenticate(username_or_email, password)
            if user:
                self.root.destroy()
                self.on_success(user)
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

            uid = db.create_user(username, email, full_name, password)
            if uid:
                user = db.get_user(uid)
                self.root.destroy()
                self.on_success(user)
            else:
                self._err_label.config(text="Failed to create account. Please try again.")

    # ── Logo animation ────────────────────────────────────────────────────────

    def _draw_logo(self, angle: float = 0):
        c = self._logo_canvas
        c.delete("all")
        from commitmaster import windows_integration
        photo = getattr(self, "_logo_photo", None)
        if photo is None:
            photo = windows_integration.get_logo_photo(64)
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
