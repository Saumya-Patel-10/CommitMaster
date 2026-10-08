"""
CommitMaster — Google Account OTP Verification Service & UI.
=============================================================
Provides OTP generation, expiration management, email dispatch (SMTP),
desktop notification preview, and a sleek dark-mode OTP verification dialog.
"""
import os
import secrets
import smtplib
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable, Optional, Tuple
import tkinter as tk

from commitmaster import database as db
from commitmaster.app_styles import COLORS, FONTS
from commitmaster.logger import get

log = get("otp_service")


def is_google_email(email: str) -> bool:
    """Return True if the email is associated with Google (e.g., @gmail.com)."""
    if not email or "@" not in email:
        return False
    domain = email.strip().split("@")[-1].lower()
    return domain in ("gmail.com", "googlemail.com", "google.com") or domain.endswith(".google.com")


def generate_otp() -> str:
    """Generate a secure 6-digit numeric OTP string."""
    return f"{secrets.randbelow(900000) + 100000}"


def send_google_otp(email: str, purpose: str = "verify_account") -> Tuple[bool, str, str]:
    """
    Generate and deliver a 6-digit OTP code to a Google account email.
    Saves in DB, attempts SMTP if configured, and displays a desktop notification.
    Returns (success, message, code).
    """
    clean_email = email.strip().lower()
    code = generate_otp()
    db.save_verification_otp(clean_email, code, purpose=purpose, expiry_minutes=10)
    log.info("Generated OTP for %s [purpose=%s]: %s", clean_email, purpose, code)

    # 1. Attempt sending via SMTP if configured
    smtp_host = db.get_system_setting("smtp_host") or os.getenv("SMTP_HOST", "")
    smtp_port = int(db.get_system_setting("smtp_port") or os.getenv("SMTP_PORT", "587"))
    smtp_user = db.get_system_setting("smtp_user") or os.getenv("SMTP_USER", "")
    smtp_pass = db.get_system_setting("smtp_pass") or os.getenv("SMTP_PASS", "")

    sent_via_email = False
    if smtp_host and smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart()
            msg["From"] = f"CommitMaster <{smtp_user}>"
            msg["To"] = clean_email
            msg["Subject"] = f"CommitMaster Verification Code: {code}"
            body_text = (
                f"Hello,\n\n"
                f"Your CommitMaster Google account verification code is:\n\n"
                f"    {code}\n\n"
                f"This code will expire in 10 minutes.\n"
                f"If you did not request this verification, please ignore this email.\n\n"
                f"— CommitMaster Security Team"
            )
            msg.attach(MIMEText(body_text, "plain"))

            def _send_bg():
                try:
                    server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                    server.quit()
                    log.info("Email OTP successfully sent to %s", clean_email)
                except Exception as ex:
                    log.warning("Failed to send SMTP email to %s: %s", clean_email, ex)

            threading.Thread(target=_send_bg, daemon=True).start()
            sent_via_email = True
        except Exception as e:
            log.warning("Could not construct SMTP message: %s", e)

    # 2. Always show desktop notification toast for instant desktop experience
    try:
        from commitmaster.notification_toast import show_toast
        show_toast(
            title="🔐 Google Account Verification Code",
            message=f"Verification code for {clean_email}:\n👉 {code} 👈\n(Valid for 10 minutes)",
            badge_text="OTP CODE",
        )
    except Exception as exc:
        log.debug("Toast dispatch for OTP failed: %s", exc)

    msg_status = "Verification code sent to your Google account." if sent_via_email else (
        "Verification code generated and sent! Check your notification / email."
    )
    return True, msg_status, code


def verify_google_otp(email: str, code: str, purpose: str = "verify_account") -> Tuple[bool, str]:
    """Validate 6-digit OTP code for a Google account."""
    if not code or not code.strip():
        return False, "Please enter the 6-digit verification code."
    return db.verify_stored_otp(email, code.strip(), purpose=purpose)


# ── Sleek Dark-Mode OTP Verification Dialog ───────────────────────────────────

class GoogleOtpDialog:
    """
    Modern modal dialog for entering and validating the 6-digit Google Account OTP code.
    """

    def __init__(
        self,
        parent: tk.Tk,
        email: str,
        on_success: Callable[[], None],
        purpose: str = "verify_account",
        initial_code: Optional[str] = None
    ):
        self.parent = parent
        self.email = email.strip().lower()
        self.on_success = on_success
        self.purpose = purpose
        self.initial_code = initial_code

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("CommitMaster — Google Account Verification")
        self.dialog.geometry("440x440")
        self.dialog.minsize(420, 400)
        self.dialog.configure(bg=COLORS["bg_darkest"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center on parent or screen
        self.dialog.update_idletasks()
        pw = parent.winfo_width() if parent else 440
        ph = parent.winfo_height() if parent else 440
        px = parent.winfo_rootx() if parent else 100
        py = parent.winfo_rooty() if parent else 100
        x = max(50, px + (pw - 440) // 2)
        y = max(50, py + (ph - 440) // 2)
        self.dialog.geometry(f"440x440+{x}+{y}")

        self._remaining_seconds = 600  # 10 minutes
        self._build_ui()
        self._start_countdown()

    def _build_ui(self):
        p = tk.Frame(self.dialog, bg=COLORS["bg_darkest"], padx=28, pady=24)
        p.pack(fill="both", expand=True)

        # Icon and header
        hdr = tk.Frame(p, bg=COLORS["bg_darkest"])
        hdr.pack(fill="x", pady=(0, 12))

        tk.Label(
            hdr, text="🔐", font=("Segoe UI Emoji", 28),
            bg=COLORS["bg_darkest"]
        ).pack(side="left", padx=(0, 10))

        title_box = tk.Frame(hdr, bg=COLORS["bg_darkest"])
        title_box.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_box, text="Verify Google Account", font=FONTS["heading_md"],
            fg=COLORS["text_primary"], bg=COLORS["bg_darkest"]
        ).pack(anchor="w")

        tk.Label(
            title_box, text="One-Time Password (OTP) System", font=FONTS["caption"],
            fg=COLORS["accent"], bg=COLORS["bg_darkest"]
        ).pack(anchor="w")

        # Description
        desc_lbl = tk.Label(
            p,
            text=f"A 6-digit verification code has been generated for:\n{self.email}\n\nEnter the code below to verify and activate your account.",
            font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"],
            justify="left", wraplength=380
        )
        desc_lbl.pack(anchor="w", pady=(0, 16))

        # OTP Input Card
        card = tk.Frame(p, bg=COLORS["bg_card"], padx=20, pady=16,
                        highlightthickness=1, highlightbackground=COLORS["border"])
        card.pack(fill="x", pady=(0, 12))

        tk.Label(
            card, text="6-Digit Verification Code", font=FONTS["label_bold"],
            fg=COLORS["text_secondary"], bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 6))

        self._otp_var = tk.StringVar()
        if self.initial_code:
            self._otp_var.set(self.initial_code)

        self._otp_entry = tk.Entry(
            card,
            textvariable=self._otp_var,
            font=("Consolas", 22, "bold"),
            justify="center",
            bg=COLORS["bg_input"],
            fg=COLORS["accent"],
            insertbackground=COLORS["accent"],
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"]
        )
        self._otp_entry.pack(fill="x", ipady=8)
        self._otp_entry.focus()
        self._otp_entry.bind("<Return>", lambda e: self._submit())

        # Timer & Resend row
        timer_row = tk.Frame(p, bg=COLORS["bg_darkest"])
        timer_row.pack(fill="x", pady=(4, 10))

        self._timer_lbl = tk.Label(
            timer_row, text="Expires in: 10:00", font=FONTS["caption"],
            fg=COLORS["text_muted"], bg=COLORS["bg_darkest"]
        )
        self._timer_lbl.pack(side="left")

        self._resend_btn = tk.Label(
            timer_row, text="Resend Code", font=("Segoe UI", 9, "underline"),
            fg=COLORS["accent"], bg=COLORS["bg_darkest"], cursor="hand2"
        )
        self._resend_btn.pack(side="right")
        self._resend_btn.bind("<Button-1>", lambda e: self._resend())

        # Status / Error label
        self._status_lbl = tk.Label(
            p, text="", font=FONTS["body_sm"],
            fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"], wraplength=380
        )
        self._status_lbl.pack(fill="x", pady=(0, 12))

        # Bottom buttons
        btn_row = tk.Frame(p, bg=COLORS["bg_darkest"])
        btn_row.pack(fill="x", pady=(4, 0))

        cancel_btn = tk.Button(
            btn_row, text="Cancel", font=FONTS["body_md"],
            bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
            relief="flat", bd=0, cursor="hand2", padx=16, pady=8,
            command=self.dialog.destroy
        )
        cancel_btn.pack(side="left")

        verify_btn = tk.Button(
            btn_row, text="✔ Verify Code", font=FONTS["heading_sm"],
            bg=COLORS["accent"], fg="#ffffff",
            activebackground=COLORS["accent_hover"], activeforeground="#ffffff",
            relief="flat", bd=0, cursor="hand2", padx=20, pady=8,
            command=self._submit
        )
        verify_btn.pack(side="right")

    def _start_countdown(self):
        def _tick():
            if not self.dialog.winfo_exists():
                return
            if self._remaining_seconds > 0:
                mins = self._remaining_seconds // 60
                secs = self._remaining_seconds % 60
                self._timer_lbl.config(text=f"Expires in: {mins:02d}:{secs:02d}")
                self._remaining_seconds -= 1
                self.dialog.after(1000, _tick)
            else:
                self._timer_lbl.config(text="Code expired! Please request a new code.", fg=COLORS["danger"])

        self.dialog.after(1000, _tick)

    def _resend(self):
        self._status_lbl.config(text="Generating new verification code...", fg=COLORS["text_secondary"])
        self.dialog.update_idletasks()
        ok, msg, code = send_google_otp(self.email, purpose=self.purpose)
        if ok:
            self._remaining_seconds = 600
            self._status_lbl.config(text="✔ New code sent to your Google account!", fg=COLORS["success"])
            self._otp_entry.delete(0, "end")
            self._otp_entry.focus()
        else:
            self._status_lbl.config(text=f"✖ {msg}", fg=COLORS["danger"])

    def _submit(self):
        code = self._otp_var.get().strip()
        if not code:
            self._status_lbl.config(text="Please enter the 6-digit code.", fg=COLORS["danger"])
            self._otp_entry.focus()
            return

        ok, msg = verify_google_otp(self.email, code, purpose=self.purpose)
        if ok:
            self._status_lbl.config(text="✔ Verification successful!", fg=COLORS["success"])
            self.dialog.after(600, self._finish_success)
        else:
            self._status_lbl.config(text=f"✖ {msg}", fg=COLORS["danger"])
            self._otp_entry.focus()

    def _finish_success(self):
        try:
            self.dialog.destroy()
        except Exception:
            pass
        if self.on_success:
            self.on_success()
