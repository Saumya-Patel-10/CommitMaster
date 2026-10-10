"""
CommitMaster — Forgot Password & Account Recovery Dialog.
=========================================================
Allows users to recover access to their account and reset their password
by answering the two security questions they configured during account registration.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional, Dict, Any

from commitmaster.app_styles import COLORS, FONTS
from commitmaster import database as db


class ForgotPasswordDialog:
    """Modal dialog for resetting a user's password via registered security questions."""

    def __init__(self, parent: tk.Tk, on_success: Optional[Callable[[str], None]] = None):
        self.parent = parent
        self.on_success = on_success

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("CommitMaster — Reset Password")
        self.dialog.geometry("480x580")
        self.dialog.minsize(440, 520)
        self.dialog.configure(bg=COLORS["bg_darkest"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center on parent
        self._center_window()

        self._user_data: Optional[Dict[str, Any]] = None

        self._build_ui()

    def _center_window(self):
        try:
            self.parent.update_idletasks()
            px, py = self.parent.winfo_x(), self.parent.winfo_y()
            pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
            x = max(20, px + (pw - 480) // 2)
            y = max(20, py + (ph - 580) // 2)
            self.dialog.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _add_hover(self, widget, hover_bg, normal_bg):
        widget.bind("<Enter>", lambda e: widget.config(bg=hover_bg))
        widget.bind("<Leave>", lambda e: widget.config(bg=normal_bg))

    def _make_entry(self, parent, show="", placeholder="") -> tk.Entry:
        e = tk.Entry(
            parent, font=FONTS["body_md"],
            bg=COLORS["bg_input"], fg=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"],
            relief="flat", bd=0, show=show,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["border_focus"]
        )
        e.pack(fill="x", ipady=6, ipadx=10, pady=(3, 0))
        return e

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.dialog, bg=COLORS["bg_dark"], padx=20, pady=16)
        hdr.pack(fill="x")

        hdr_top = tk.Frame(hdr, bg=COLORS["bg_dark"])
        hdr_top.pack(fill="x")

        tk.Label(
            hdr_top, text="🔐 Account Recovery",
            font=FONTS["heading_md"], fg=COLORS["text_primary"], bg=COLORS["bg_dark"]
        ).pack(side="left")

        close_btn = tk.Label(
            hdr_top, text="✕", font=("Segoe UI", 12, "bold"),
            fg=COLORS["text_muted"], bg=COLORS["bg_dark"], cursor="hand2"
        )
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self.dialog.destroy())

        tk.Label(
            hdr, text="Reset your password securely by verifying your security questions.",
            font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_dark"]
        ).pack(anchor="w", pady=(4, 0))

        # ── Scrollable Body Container ─────────────────────────────────────────
        container = tk.Frame(self.dialog, bg=COLORS["bg_darkest"], padx=20, pady=16)
        container.pack(fill="both", expand=True)

        self._card = tk.Frame(
            container, bg=COLORS["bg_card"], padx=18, pady=16,
            highlightthickness=1, highlightbackground=COLORS["border"]
        )
        self._card.pack(fill="both", expand=True)

        # ── Error / Info Label ────────────────────────────────────────────────
        self._msg_lbl = tk.Label(
            self._card, text="", font=FONTS["body_sm"],
            fg=COLORS["error"], bg=COLORS["bg_card"], wraplength=380, justify="left"
        )
        self._msg_lbl.pack(fill="x", pady=(0, 10))

        # ── Step 1: Account Lookup Frame ──────────────────────────────────────
        self._step1_frame = tk.Frame(self._card, bg=COLORS["bg_card"])
        self._step1_frame.pack(fill="both", expand=True)

        tk.Label(
            self._step1_frame, text="Step 1 of 2: Identify Your Account",
            font=FONTS["label_bold"], fg=COLORS["accent"], bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            self._step1_frame, text="Enter the username or email address associated with your account:",
            font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"], wraplength=380
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            self._step1_frame, text="Username or Email",
            font=FONTS["label_bold"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]
        ).pack(anchor="w")

        self._lookup_entry = self._make_entry(self._step1_frame)
        self._lookup_entry.focus()
        self._lookup_entry.bind("<Return>", lambda e: self._find_account())

        self._find_btn = tk.Button(
            self._step1_frame, text="Next: Answer Security Questions →",
            font=FONTS["heading_sm"], bg=COLORS["accent"], fg="#ffffff",
            activebackground=COLORS["accent_hover"], activeforeground="#ffffff",
            relief="flat", cursor="hand2", bd=0, padx=14, pady=8,
            command=self._find_account
        )
        self._add_hover(self._find_btn, COLORS["accent_hover"], COLORS["accent"])
        self._find_btn.pack(fill="x", pady=(18, 0))

        # ── Step 2: Answer Questions & Reset Frame ───────────────────────────
        self._step2_frame = tk.Frame(self._card, bg=COLORS["bg_card"])

        tk.Label(
            self._step2_frame, text="Step 2 of 2: Verify & Choose New Password",
            font=FONTS["label_bold"], fg=COLORS["accent"], bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 4))

        self._account_badge_lbl = tk.Label(
            self._step2_frame, text="",
            font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]
        )
        self._account_badge_lbl.pack(anchor="w", pady=(0, 8))

        # Question 1
        self._q1_label = tk.Label(
            self._step2_frame, text="", font=FONTS["label_bold"],
            fg=COLORS["text_primary"], bg=COLORS["bg_card"], wraplength=380, justify="left"
        )
        self._q1_label.pack(anchor="w", pady=(4, 0))
        self._a1_entry = self._make_entry(self._step2_frame)

        # Question 2
        self._q2_label = tk.Label(
            self._step2_frame, text="", font=FONTS["label_bold"],
            fg=COLORS["text_primary"], bg=COLORS["bg_card"], wraplength=380, justify="left"
        )
        self._q2_label.pack(anchor="w", pady=(8, 0))
        self._a2_entry = self._make_entry(self._step2_frame)

        # Separator
        sep = tk.Frame(self._step2_frame, height=1, bg=COLORS["border"])
        sep.pack(fill="x", pady=(12, 10))

        # New Password
        tk.Label(
            self._step2_frame, text="New Password (min 6 characters)",
            font=FONTS["label_bold"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]
        ).pack(anchor="w")
        self._new_pass_entry = self._make_entry(self._step2_frame, show="•")

        # Confirm New Password
        tk.Label(
            self._step2_frame, text="Confirm New Password",
            font=FONTS["label_bold"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(6, 0))
        self._confirm_pass_entry = self._make_entry(self._step2_frame, show="•")

        # Show passwords toggle
        self._show_pass_var = tk.BooleanVar(value=False)
        show_cb = tk.Checkbutton(
            self._step2_frame, text="Show passwords", variable=self._show_pass_var,
            font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
            activebackground=COLORS["bg_card"], activeforeground=COLORS["text_primary"],
            selectcolor=COLORS["bg_input"], bd=0, highlightthickness=0,
            command=self._toggle_show_pass
        )
        show_cb.pack(anchor="w", pady=(4, 8))

        # Buttons row
        btn_box = tk.Frame(self._step2_frame, bg=COLORS["bg_card"])
        btn_box.pack(fill="x", pady=(8, 0))

        back_btn = tk.Button(
            btn_box, text="← Back", font=FONTS["body_sm"],
            bg=COLORS["bg_medium"], fg=COLORS["text_secondary"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
            relief="flat", cursor="hand2", bd=0, padx=12, pady=7,
            command=self._back_to_step1
        )
        self._add_hover(back_btn, COLORS["bg_card_hover"], COLORS["bg_medium"])
        back_btn.pack(side="left")

        self._reset_btn = tk.Button(
            btn_box, text="Reset Password", font=FONTS["heading_sm"],
            bg=COLORS["accent"], fg="#ffffff",
            activebackground=COLORS["accent_hover"], activeforeground="#ffffff",
            relief="flat", cursor="hand2", bd=0, padx=16, pady=7,
            command=self._do_reset_password
        )
        self._add_hover(self._reset_btn, COLORS["accent_hover"], COLORS["accent"])
        self._reset_btn.pack(side="right")

    def _toggle_show_pass(self):
        show_char = "" if self._show_pass_var.get() else "•"
        self._new_pass_entry.config(show=show_char)
        self._confirm_pass_entry.config(show=show_char)

    def _find_account(self):
        self._msg_lbl.config(text="", fg=COLORS["error"])
        ident = self._lookup_entry.get().strip()
        if not ident:
            self._msg_lbl.config(text="Please enter your username or email address.")
            self._lookup_entry.focus()
            return

        data = db.get_user_security_questions(ident)
        if not data:
            # Check if user exists but has no questions configured
            existing_user = db.get_user_by_username_or_email(ident)
            if existing_user:
                self._msg_lbl.config(
                    text="This account does not have security questions configured. Please sign in or contact an administrator to recover access."
                )
            else:
                self._msg_lbl.config(text=f"No account found matching '{ident}'. Please check the spelling.")
            return

        self._user_data = data
        self._step1_frame.pack_forget()

        # Populate Step 2
        uname = data.get("username", ident)
        self._account_badge_lbl.config(text=f"Recovering account: @{uname}")
        self._q1_label.config(text=f"1. {data.get('question_1', '')}")
        self._q2_label.config(text=f"2. {data.get('question_2', '')}")

        self._a1_entry.delete(0, "end")
        self._a2_entry.delete(0, "end")
        self._new_pass_entry.delete(0, "end")
        self._confirm_pass_entry.delete(0, "end")

        self._step2_frame.pack(fill="both", expand=True)
        self._a1_entry.focus()

    def _back_to_step1(self):
        self._msg_lbl.config(text="")
        self._step2_frame.pack_forget()
        self._step1_frame.pack(fill="both", expand=True)
        self._lookup_entry.focus()

    def _do_reset_password(self):
        self._msg_lbl.config(text="", fg=COLORS["error"])
        if not self._user_data:
            return

        a1 = self._a1_entry.get().strip()
        a2 = self._a2_entry.get().strip()
        new_pass = self._new_pass_entry.get()
        confirm_pass = self._confirm_pass_entry.get()

        if not a1:
            self._msg_lbl.config(text="Please answer security question 1.")
            self._a1_entry.focus()
            return

        if not a2:
            self._msg_lbl.config(text="Please answer security question 2.")
            self._a2_entry.focus()
            return

        if not new_pass:
            self._msg_lbl.config(text="Please enter a new password.")
            self._new_pass_entry.focus()
            return

        if len(new_pass) < 6:
            self._msg_lbl.config(text="New password must be at least 6 characters long.")
            self._new_pass_entry.focus()
            return

        if new_pass != confirm_pass:
            self._msg_lbl.config(text="New passwords do not match. Please verify.")
            self._confirm_pass_entry.focus()
            return

        user_id = self._user_data["user_id"]
        ok, msg = db.reset_password_with_security_questions(user_id, a1, a2, new_pass)

        if ok:
            messagebox.showinfo(
                "Password Reset Successful",
                "Your password has been successfully reset! You can now sign in with your new password.",
                parent=self.dialog
            )
            username = self._user_data.get("username", "")
            self.dialog.destroy()
            if self.on_success:
                self.on_success(username)
        else:
            self._msg_lbl.config(text=msg, fg=COLORS["error"])
            self._a1_entry.focus()
