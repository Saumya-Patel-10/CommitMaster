"""
CommitMaster — Login & Registration window.
A premium dark-mode login screen with animated branding.
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
    Calls on_success(user_dict) when the user successfully authenticates.
    """

    def __init__(self, on_success: Callable[[dict], None]):
        self.on_success = on_success
        self.root = tk.Tk()
        self._setup_window()
        self._build_ui()
        self._animate_logo()

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        self.root.title("CommitMaster — Sign In")
        self.root.geometry("460x680")
        self.root.resizable(False, False)
        self.root.configure(bg=COLORS["bg_darkest"])
        # Center on screen
        self.root.update_idletasks()
        w, h = 460, 680
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._mode = "login"  # or "register"

        outer = tk.Frame(self.root, bg=COLORS["bg_darkest"])
        outer.pack(fill="both", expand=True, padx=40, pady=30)

        # ── Logo ──────────────────────────────────────────────────────────────
        self._logo_canvas = tk.Canvas(outer, width=80, height=80,
                                      bg=COLORS["bg_darkest"], highlightthickness=0)
        self._logo_canvas.pack(pady=(20, 0))
        self._draw_logo(0)

        # ── App name ──────────────────────────────────────────────────────────
        tk.Label(outer, text="CommitMaster", font=FONTS["heading_xl"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_darkest"]).pack(pady=(8, 0))
        self._tagline = tk.Label(outer, text="Your coding session companion",
                                 font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                                 bg=COLORS["bg_darkest"])
        self._tagline.pack()

        # ── Card ──────────────────────────────────────────────────────────────
        card = tk.Frame(outer, bg=COLORS["bg_card"],
                        relief="flat", bd=0)
        card.pack(fill="x", pady=24)
        self._border_top = tk.Frame(card, height=2, bg=COLORS["accent"])
        self._border_top.pack(fill="x")

        inner = tk.Frame(card, bg=COLORS["bg_card"], padx=28, pady=24)
        inner.pack(fill="both")

        # Mode toggle label
        self._mode_title = tk.Label(inner, text="Sign In",
                                    font=FONTS["heading_md"],
                                    fg=COLORS["text_primary"], bg=COLORS["bg_card"])
        self._mode_title.pack(anchor="w", pady=(0, 16))

        # Full name (register only)
        self._name_frame = tk.Frame(inner, bg=COLORS["bg_card"])
        self._name_frame.pack(fill="x", pady=(0, 10))
        tk.Label(self._name_frame, text="Full Name",
                 font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._name_entry = self._make_entry(self._name_frame)

        # Username
        uframe = tk.Frame(inner, bg=COLORS["bg_card"])
        uframe.pack(fill="x", pady=(0, 10))
        tk.Label(uframe, text="Username or Email",
                 font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._user_entry = self._make_entry(uframe)
        self._user_entry.focus()

        # Email (register only)
        self._email_frame = tk.Frame(inner, bg=COLORS["bg_card"])
        self._email_frame.pack(fill="x", pady=(0, 10))
        tk.Label(self._email_frame, text="Email",
                 font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._email_entry = self._make_entry(self._email_frame)

        # Password
        pframe = tk.Frame(inner, bg=COLORS["bg_card"])
        pframe.pack(fill="x", pady=(0, 6))
        tk.Label(pframe, text="Password",
                 font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._pass_entry = self._make_entry(pframe, show="•")
        self._pass_entry.bind("<Return>", lambda e: self._submit())

        # Confirm password (register only)
        self._confirm_frame = tk.Frame(inner, bg=COLORS["bg_card"])
        self._confirm_frame.pack(fill="x", pady=(0, 10))
        tk.Label(self._confirm_frame, text="Confirm Password",
                 font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(anchor="w")
        self._confirm_entry = self._make_entry(self._confirm_frame, show="•")
        self._confirm_entry.bind("<Return>", lambda e: self._submit())

        # Error label
        self._err_label = tk.Label(inner, text="", font=FONTS["body_sm"],
                                   fg=COLORS["error"], bg=COLORS["bg_card"],
                                   wraplength=340)
        self._err_label.pack(pady=(0, 4))

        # Submit button
        self._submit_btn = tk.Button(
            inner, text="Sign In", font=FONTS["heading_sm"],
            bg=COLORS["accent"], fg="#ffffff",
            activebackground=COLORS["accent_hover"], activeforeground="#ffffff",
            relief="flat", cursor="hand2", bd=0,
            command=self._submit, padx=16, pady=10
        )
        self._submit_btn.pack(fill="x", pady=(6, 0))
        self._add_hover(self._submit_btn, COLORS["accent_hover"], COLORS["accent"])

        # ── Toggle login/register ─────────────────────────────────────────────
        toggle_f = tk.Frame(outer, bg=COLORS["bg_darkest"])
        toggle_f.pack()
        self._toggle_lbl = tk.Label(toggle_f, text="Don't have an account? ",
                                    font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                                    bg=COLORS["bg_darkest"])
        self._toggle_lbl.pack(side="left")
        self._toggle_btn = tk.Label(toggle_f, text="Create one",
                                    font=("Segoe UI", 11, "underline"),
                                    fg=COLORS["accent"], bg=COLORS["bg_darkest"],
                                    cursor="hand2")
        self._toggle_btn.pack(side="left")
        self._toggle_btn.bind("<Button-1>", lambda e: self._toggle_mode())

        # Default: hide register-only fields
        self._set_mode("login")

    def _make_entry(self, parent, show="") -> tk.Entry:
        e = tk.Entry(parent, font=FONTS["body_md"],
                     bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                     insertbackground=COLORS["text_primary"],
                     relief="flat", bd=0, show=show,
                     highlightthickness=1,
                     highlightbackground=COLORS["border"],
                     highlightcolor=COLORS["border_focus"])
        e.pack(fill="x", ipady=8, ipadx=10, pady=(4, 0))
        return e

    def _add_hover(self, widget, hover_bg, normal_bg):
        widget.bind("<Enter>", lambda e: widget.config(bg=hover_bg))
        widget.bind("<Leave>", lambda e: widget.config(bg=normal_bg))

    # ── Mode switching ────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self._mode = mode
        if mode == "login":
            self._name_frame.pack_forget()
            self._email_frame.pack_forget()
            self._confirm_frame.pack_forget()
            self._mode_title.config(text="Sign In")
            self._submit_btn.config(text="Sign In")
            self._toggle_lbl.config(text="Don't have an account? ")
            self._toggle_btn.config(text="Create one")
        else:
            # Re-insert register fields in correct order
            self._name_frame.pack(fill="x", pady=(0, 10), before=self._user_entry.master)
            self._email_frame.pack(fill="x", pady=(0, 10), after=self._pass_entry.master)
            self._confirm_frame.pack(fill="x", pady=(0, 10), after=self._email_frame)
            self._mode_title.config(text="Create Account")
            self._submit_btn.config(text="Create Account")
            self._toggle_lbl.config(text="Already have an account? ")
            self._toggle_btn.config(text="Sign in")

    def _toggle_mode(self):
        self._err_label.config(text="")
        new_mode = "register" if self._mode == "login" else "login"
        self._set_mode(new_mode)

    # ── Submit ─────────────────────────────────────────────────────────────────

    def _submit(self):
        self._err_label.config(text="")
        username = self._user_entry.get().strip()
        password = self._pass_entry.get()

        if self._mode == "login":
            if not username or not password:
                self._err_label.config(text="Please fill in all fields.")
                return
            user = db.authenticate(username, password)
            if user:
                self.root.destroy()
                self.on_success(user)
            else:
                self._err_label.config(text="Invalid credentials. Please try again.")
                self._pass_entry.delete(0, "end")

        else:  # register
            full_name = self._name_entry.get().strip()
            email = self._email_entry.get().strip()
            confirm = self._confirm_entry.get()
            if not all([full_name, username, email, password, confirm]):
                self._err_label.config(text="Please fill in all fields.")
                return
            if password != confirm:
                self._err_label.config(text="Passwords do not match.")
                return
            if len(password) < 6:
                self._err_label.config(text="Password must be at least 6 characters.")
                return
            uid = db.create_user(username, email, full_name, password)
            if uid:
                user = db.get_user(uid)
                self.root.destroy()
                self.on_success(user)
            else:
                self._err_label.config(text="Username or email already exists.")

    # ── Logo animation ────────────────────────────────────────────────────────

    def _draw_logo(self, angle: float):
        c = self._logo_canvas
        c.delete("all")
        cx, cy, r = 40, 40, 36
        import math
        # Glow
        c.create_oval(cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3,
                      fill="#1a2f1a", outline="")
        # Outer ring
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      outline=COLORS["accent"], width=2)
        # Commit dot
        c.create_oval(cx - 6, cy - 6, cx + 6, cy + 6,
                      fill=COLORS["accent"], outline="")
        # Rotating branch arms
        for i, da in enumerate([0, 90, 180, 270]):
            a = math.radians(angle + da)
            x1, y1 = cx + 9 * math.cos(a), cy + 9 * math.sin(a)
            x2, y2 = cx + 26 * math.cos(a), cy + 26 * math.sin(a)
            c.create_line(x1, y1, x2, y2, fill=COLORS["accent"], width=2)
            c.create_oval(x2 - 4, y2 - 4, x2 + 4, y2 + 4,
                          fill=COLORS["accent_dark"], outline="")

    def _animate_logo(self, angle: float = 0):
        self._draw_logo(angle)
        self.root.after(50, lambda: self._animate_logo((angle + 3) % 360))

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()
