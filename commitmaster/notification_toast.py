"""
Bottom-Right Corner Toast Notification Window for CommitMaster.

Displays a sleek, modern, dark-themed floating card in the bottom-right corner
of the screen (above the Windows taskbar). Includes:
  • CommitMaster branding and trigger badge (Interval / IDE Closed)
  • Repo changes preview
  • Action buttons: "🚀 Review & Commit", "⏱ Snooze (15m)", and "Dismiss"
  • Auto-dismiss timer that pauses on mouse hover
  • Fallback / companion Windows notification via plyer
"""
import ctypes
import os
import sys
import threading
import time
import tkinter as tk
from typing import Callable, List, Optional, Tuple

from commitmaster.app_styles import COLORS, FONTS
from commitmaster.logger import get
from commitmaster import windows_integration

log = get("notification_toast")

_ACTIVE_TOAST = None
_TOAST_LOCK = threading.Lock()


def _get_work_area() -> Tuple[int, int, int, int]:
    """Return (left, top, right, bottom) of the Windows desktop work area, excluding taskbar."""
    if sys.platform == "win32":
        try:
            import ctypes.wintypes
            rect = ctypes.wintypes.RECT()
            # SPI_GETWORKAREA = 48
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception as exc:
            log.debug("SystemParametersInfoW failed: %s", exc)

    # Fallback to entire screen dimensions
    try:
        root = tk._default_root
        if root:
            return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
    except Exception:
        pass
    return 0, 0, 1920, 1080


class NotificationToast:
    """
    A modern dark-mode floating toast window anchored to the bottom-right corner.
    """

    def __init__(
        self,
        title: str,
        message: str,
        badge_text: str = "REMINDER",
        dirty_repos: Optional[List[str]] = None,
        on_commit: Optional[Callable] = None,
        on_snooze: Optional[Callable[[int], None]] = None,
        on_dismiss: Optional[Callable] = None,
        on_yes: Optional[Callable] = None,
        on_no: Optional[Callable] = None,
        toast_mode: str = "default",
        duration_seconds: int = 25,
        master: Optional[tk.Misc] = None,
    ):
        self.title = title
        self.message = message
        self.badge_text = badge_text
        self.dirty_repos = dirty_repos or []
        self.on_commit = on_commit
        self.on_snooze = on_snooze
        self.on_dismiss = on_dismiss
        self.on_yes = on_yes
        self.on_no = on_no
        self.toast_mode = toast_mode
        self.duration_seconds = duration_seconds
        self.master = master

        self.win: Optional[tk.Toplevel] = None
        self._hovered = False
        self._seconds_left = duration_seconds
        self._timer_id = None
        self._destroyed = False

    def show(self) -> None:
        """Create and position the toast window."""
        global _ACTIVE_TOAST

        # Dismiss any previously active toast cleanly
        with _TOAST_LOCK:
            if _ACTIVE_TOAST and not _ACTIVE_TOAST._destroyed:
                try:
                    _ACTIVE_TOAST.close()
                except Exception:
                    pass
            _ACTIVE_TOAST = self

        parent = self.master or tk._default_root
        if not parent:
            # Standalone root
            self._own_root = tk.Tk()
            self._own_root.withdraw()
            self.win = tk.Toplevel(self._own_root)
        else:
            self._own_root = None
            self.win = tk.Toplevel(parent)

        win = self.win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=COLORS["border"])  # Outer border color

        # Inner container with dark background
        card = tk.Frame(win, bg=COLORS["bg_card"], padx=14, pady=12)
        card.pack(fill="both", expand=True, padx=1, pady=1)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(card, bg=COLORS["bg_card"])
        hdr.pack(fill="x", pady=(0, 6))

        # Brand / Icon
        logo_drawn = False
        try:
            logo = windows_integration.get_logo_photo(20, master=win)
            if logo:
                self._logo_ref = logo
                tk.Label(hdr, image=logo, bg=COLORS["bg_card"]).pack(side="left", padx=(0, 6))
                logo_drawn = True
        except Exception:
            logo_drawn = False

        if not logo_drawn:
            tk.Label(hdr, text="⬡", font=("Segoe UI", 12, "bold"),
                     fg=COLORS["accent"], bg=COLORS["bg_card"]).pack(side="left", padx=(0, 6))

        tk.Label(hdr, text="CommitMaster", font=FONTS["label_bold"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(side="left")

        # Badge (e.g. INTERVAL or IDE CLOSED)
        badge_bg = COLORS["bg_card_hover"]
        badge_fg = COLORS["accent"]
        if "CLOSED" in self.badge_text.upper():
            badge_fg = COLORS["warning"]
        elif "TEST" in self.badge_text.upper():
            badge_fg = COLORS["info"]

        badge_lbl = tk.Label(
            hdr, text=f" {self.badge_text} ",
            font=("Segoe UI", 8, "bold"),
            bg=badge_bg, fg=badge_fg, padx=4, pady=1
        )
        badge_lbl.pack(side="left", padx=8)

        # Close button '✕'
        close_btn = tk.Label(hdr, text="✕", font=("Segoe UI", 10, "bold"),
                             fg=COLORS["text_muted"], bg=COLORS["bg_card"],
                             cursor="hand2", padx=4)
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self.close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=COLORS["danger"]))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=COLORS["text_muted"]))

        # ── Title ─────────────────────────────────────────────────────────────
        tk.Label(card, text=self.title, font=FONTS["heading_sm"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"],
                 anchor="w", justify="left").pack(fill="x", pady=(0, 4))

        # ── Message ───────────────────────────────────────────────────────────
        msg_lbl = tk.Label(card, text=self.message, font=FONTS["body_sm"],
                           fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                           anchor="w", justify="left", wraplength=340)
        msg_lbl.pack(fill="x", pady=(0, 6))

        # ── Dirty Repositories Chip List (if present) ─────────────────────────
        if self.dirty_repos:
            repo_f = tk.Frame(card, bg=COLORS["bg_card"])
            repo_f.pack(fill="x", pady=(0, 8))
            tk.Label(repo_f, text="Uncommitted changes in:", font=("Segoe UI", 8, "bold"),
                     fg=COLORS["warning"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 2))
            
            chips_row = tk.Frame(repo_f, bg=COLORS["bg_card"])
            chips_row.pack(fill="x")
            
            # Display up to 3 repository names as chips
            for r in self.dirty_repos[:3]:
                r_name = os.path.basename(r.rstrip("/\\"))
                chip = tk.Label(chips_row, text=f"📁 {r_name}", font=("Segoe UI", 8),
                                bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
                                padx=6, pady=2)
                chip.pack(side="left", padx=(0, 4))
            
            if len(self.dirty_repos) > 3:
                more_lbl = tk.Label(chips_row, text=f"+{len(self.dirty_repos) - 3} more",
                                    font=("Segoe UI", 8), fg=COLORS["text_muted"], bg=COLORS["bg_card"])
                more_lbl.pack(side="left", padx=2)

        # ── Actions ───────────────────────────────────────────────────────────
        btn_row = tk.Frame(card, bg=COLORS["bg_card"])
        btn_row.pack(fill="x", pady=(4, 0))

        if self.toast_mode == "did_you_commit" or self.on_no is not None:
            # "No, help me commit" (Accent Button)
            no_btn = tk.Button(
                btn_row, text="✖ No, help me commit",
                font=("Segoe UI", 9, "bold"),
                bg=COLORS["accent"], fg="#0d1117",
                activebackground=COLORS["accent_hover"],
                activeforeground="#0d1117",
                relief="flat", bd=0, cursor="hand2",
                padx=10, pady=5, command=self._do_no
            )
            no_btn.pack(side="left", padx=(0, 6))

            # "Yes, I did" (Secondary Button: closes toast without action)
            yes_btn = tk.Button(
                btn_row, text="✔ Yes, I already did",
                font=("Segoe UI", 9),
                bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
                activebackground=COLORS["bg_card_hover"],
                activeforeground=COLORS["text_primary"],
                relief="flat", bd=0, cursor="hand2",
                padx=8, pady=5, command=self._do_yes
            )
            yes_btn.pack(side="left", padx=(0, 6))

            # Snooze (15m) Button
            snooze_btn = tk.Button(
                btn_row, text="⏱ Snooze",
                font=("Segoe UI", 9),
                bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                activebackground=COLORS["bg_medium"],
                activeforeground=COLORS["text_secondary"],
                relief="flat", bd=0, cursor="hand2",
                padx=6, pady=5, command=self._do_snooze
            )
            snooze_btn.pack(side="left")
        else:
            # Review & Commit Now Button
            commit_btn = tk.Button(
                btn_row, text="🚀 Review & Commit",
                font=("Segoe UI", 9, "bold"),
                bg=COLORS["accent"], fg="#0d1117",
                activebackground=COLORS["accent_hover"],
                activeforeground="#0d1117",
                relief="flat", bd=0, cursor="hand2",
                padx=10, pady=5, command=self._do_commit
            )
            commit_btn.pack(side="left", padx=(0, 6))

            # Snooze (15m) Button
            snooze_btn = tk.Button(
                btn_row, text="⏱ Snooze 15m",
                font=("Segoe UI", 9),
                bg=COLORS["bg_medium"], fg=COLORS["text_primary"],
                activebackground=COLORS["bg_card_hover"],
                activeforeground=COLORS["text_primary"],
                relief="flat", bd=0, cursor="hand2",
                padx=8, pady=5, command=self._do_snooze
            )
            snooze_btn.pack(side="left", padx=(0, 6))

            # Dismiss Button
            dismiss_btn = tk.Button(
                btn_row, text="Dismiss",
                font=("Segoe UI", 9),
                bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                activebackground=COLORS["bg_medium"],
                activeforeground=COLORS["text_secondary"],
                relief="flat", bd=0, cursor="hand2",
                padx=6, pady=5, command=self.close
            )
            dismiss_btn.pack(side="left")

        # ── Hover pausing & auto-dismiss ──────────────────────────────────────
        def _on_enter(e):
            self._hovered = True

        def _on_leave(e):
            self._hovered = False

        card.bind("<Enter>", _on_enter)
        card.bind("<Leave>", _on_leave)
        for w in (card, hdr, msg_lbl, btn_row):
            w.bind("<Enter>", _on_enter, add="+")
            w.bind("<Leave>", _on_leave, add="+")

        # ── Positioning on Bottom-Right Corner ────────────────────────────────
        win.update_idletasks()
        w = max(win.winfo_reqwidth(), 370)
        h = win.winfo_reqheight()

        left, top, right, bottom = _get_work_area()
        margin = 18
        x = right - w - margin
        y = bottom - h - margin

        win.geometry(f"{w}x{h}+{x}+{y}")

        # Start countdown
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        if self._destroyed or not self.win or not self.win.winfo_exists():
            return
        if not self._hovered:
            self._seconds_left -= 1
            if self._seconds_left <= 0:
                self.close()
                return
        self._timer_id = self.win.after(1000, self._schedule_tick)

    def _do_commit(self) -> None:
        self.close()
        if self.on_commit:
            try:
                self.on_commit()
            except Exception as exc:
                log.error("on_commit callback failed: %s", exc)

    def _do_yes(self) -> None:
        """User said yes they committed: do nothing."""
        self.close()
        if self.on_yes:
            try:
                self.on_yes()
            except Exception as exc:
                log.error("on_yes callback failed: %s", exc)

    def _do_no(self) -> None:
        """User said no they have not committed: trigger commit workflow."""
        self.close()
        if self.on_no:
            try:
                self.on_no()
            except Exception as exc:
                log.error("on_no callback failed: %s", exc)
        elif self.on_commit:
            try:
                self.on_commit()
            except Exception as exc:
                log.error("on_commit callback failed: %s", exc)

    def _do_snooze(self) -> None:
        self.close()
        if self.on_snooze:
            try:
                self.on_snooze(15)
            except Exception as exc:
                log.error("on_snooze callback failed: %s", exc)

    def close(self) -> None:
        """Close and destroy the toast window."""
        global _ACTIVE_TOAST
        if self._destroyed:
            return
        self._destroyed = True
        with _TOAST_LOCK:
            if _ACTIVE_TOAST is self:
                _ACTIVE_TOAST = None

        if self.win:
            try:
                if self._timer_id:
                    self.win.after_cancel(self._timer_id)
                self.win.destroy()
            except Exception:
                pass
            self.win = None

        if getattr(self, "_own_root", None):
            try:
                self._own_root.destroy()
            except Exception:
                pass
            self._own_root = None

        if self.on_dismiss:
            try:
                self.on_dismiss()
            except Exception:
                pass


def show_toast(
    title: str,
    message: str,
    badge_text: str = "REMINDER",
    dirty_repos: Optional[List[str]] = None,
    on_commit: Optional[Callable] = None,
    on_snooze: Optional[Callable[[int], None]] = None,
    on_dismiss: Optional[Callable] = None,
    on_yes: Optional[Callable] = None,
    on_no: Optional[Callable] = None,
    toast_mode: str = "default",
    duration_seconds: int = 25,
    master: Optional[tk.Misc] = None,
) -> None:
    """
    Thread-safe function to display the bottom-right toast notification.
    Dispatches to Tkinter thread if necessary. Also triggers desktop notification fallback.
    """
    # Companion notification in Windows Action Center (safely fallback if unavail)
    try:
        from plyer import notification
        # On Windows 11 balloontip can fail without a registered icon handle, so guard against errors
        notification.notify(
            title=f"CommitMaster: {title}",
            message=message,
            app_name="CommitMaster",
            timeout=8,
        )
    except Exception as exc:
        log.debug("Companion notification skipped: %s", exc)

    def _do_show():
        try:
            toast = NotificationToast(
                title=title,
                message=message,
                badge_text=badge_text,
                dirty_repos=dirty_repos,
                on_commit=on_commit,
                on_snooze=on_snooze,
                on_dismiss=on_dismiss,
                on_yes=on_yes,
                on_no=on_no,
                toast_mode=toast_mode,
                duration_seconds=duration_seconds,
                master=master,
            )
            toast.show()
        except Exception as exc:
            log.error("Failed to display NotificationToast: %s", exc)

    target_root = master or getattr(tk, "_default_root", None)
    if target_root and hasattr(target_root, "after") and target_root.winfo_exists():
        target_root.after(0, _do_show)
    else:
        from commitmaster import ui
        ui.run_in_ui_thread(_do_show)
