"""
CommitMaster — Multi-Account Manager & Account Switcher.
========================================================
Supports persisting multiple user accounts, switching between them seamlessly
with a single click, and launching an interactive Account Switcher dialog.
"""
import json
import os
import sys
import tkinter as tk
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from commitmaster import database as db
from commitmaster import paths
from commitmaster.app_styles import COLORS, FONTS
from commitmaster.logger import get

log = get("account_manager")

APP_DIR = paths.get_data_dir()
_ACCOUNTS_FILE = paths.get_accounts_path()
_TOKEN_FILE = paths.get_token_path()


def _read_data() -> Dict[str, Any]:
    try:
        if os.path.exists(_ACCOUNTS_FILE):
            with open(_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.debug("Error reading accounts file: %s", e)
    return {"active_user_id": None, "accounts": []}


def _write_data(data: Dict[str, Any]) -> None:
    try:
        with open(_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.warning("Error writing accounts file: %s", e)


def get_saved_accounts() -> List[Dict[str, Any]]:
    """Return list of all locally saved user accounts."""
    data = _read_data()
    accounts = data.get("accounts", [])
    active_id = data.get("active_user_id")
    # Sync verification and roles from DB if available
    updated = False
    for acc in accounts:
        acc["is_active"] = (acc.get("id") == active_id)
        try:
            db_u = db.get_user(acc["id"])
            if db_u:
                acc["role"] = db_u.get("role", acc.get("role", "user"))
                acc["is_verified"] = db_u.get("is_verified", acc.get("is_verified", 0))
                acc["full_name"] = db_u.get("full_name", acc.get("full_name", ""))
                acc["username"] = db_u.get("username", acc.get("username", ""))
                acc["avatar_color"] = db_u.get("avatar_color", acc.get("avatar_color", "#3fb950"))
                acc["avatar_image"] = db_u.get("avatar_image", acc.get("avatar_image", ""))
                updated = True
        except Exception:
            pass
    if updated:
        _write_data(data)
    return accounts


def get_active_account_id() -> Optional[int]:
    """Return the user ID of the currently active account."""
    data = _read_data()
    return data.get("active_user_id")


def get_active_account() -> Optional[Dict[str, Any]]:
    """Return the currently active account dict, falling back to default saved account."""
    data = _read_data()
    active_id = data.get("active_user_id")
    accounts = data.get("accounts", [])
    if active_id is not None:
        for a in accounts:
            if a.get("id") == active_id:
                return a
    # Fallback to default or first saved account if not explicitly logged out
    for a in accounts:
        if a.get("is_default") or a.get("is_active"):
            return a
    if accounts:
        return accounts[0]
    return None


def get_default_account() -> Optional[Dict[str, Any]]:
    """
    Return the default or primary account for automatic login.
    Checks:
      1. Explicitly active account (active_user_id).
      2. Account marked as is_default: True.
      3. First saved account in local accounts list.
      4. Database designated admin account (DEFAULT_ADMIN_USERNAME).
    """
    active = get_active_account()
    if active:
        return active

    data = _read_data()
    accounts = data.get("accounts", [])
    for a in accounts:
        if a.get("is_default"):
            return a

    if accounts:
        return accounts[0]

    try:
        admin_uname = db.get_admin_username()
        db_user = db.get_user_by_username_or_email(admin_uname)
        if db_user:
            return dict(db_user)
    except Exception:
        pass

    return None


def set_default_account(user_id: int) -> bool:
    """Set the specified account as the default auto-login account."""
    data = _read_data()
    accounts = data.get("accounts", [])
    found = False
    for a in accounts:
        if a.get("id") == user_id:
            a["is_default"] = True
            found = True
        else:
            a["is_default"] = False
    if found:
        data["active_user_id"] = user_id
        _write_data(data)
    return found


def save_account(*args, **kwargs) -> None:
    """
    Save or update an account in the local accounts list and set as active.
    Supports flexible arguments:
      - save_account(user_dict, token)
      - save_account(username, user_id, role, full_name, email, avatar_color)
      - save_account(user_dict)
      - save_account(username=..., user_id=..., ...)
    """
    data = _read_data()
    accounts = data.get("accounts", [])

    user_dict: Dict[str, Any] = {}
    tok = kwargs.get("token", "")

    if len(args) == 1 and isinstance(args[0], dict):
        user_dict = dict(args[0])
    elif len(args) == 2 and isinstance(args[0], dict):
        user_dict = dict(args[0])
        tok = str(args[1])
    elif len(args) >= 2 and isinstance(args[0], str):
        user_dict["username"] = args[0]
        user_dict["id"] = args[1]
        if len(args) > 2:
            user_dict["role"] = args[2]
        if len(args) > 3:
            user_dict["full_name"] = args[3]
        if len(args) > 4:
            user_dict["email"] = args[4]
        if len(args) > 5:
            user_dict["avatar_color"] = args[5]
    elif kwargs:
        user_dict = dict(kwargs)

    uid = user_dict.get("id") or user_dict.get("user_id") or kwargs.get("user_id", 0)
    tok = tok or user_dict.get("token") or kwargs.get("token", "")

    avatar_img = user_dict.get("avatar_image", kwargs.get("avatar_image", ""))
    if not avatar_img and uid:
        try:
            db_u = db.get_user(uid)
            if db_u and db_u.get("avatar_image"):
                avatar_img = db_u["avatar_image"]
        except Exception:
            pass
    if not avatar_img and uid:
        candidate = os.path.join(APP_DIR, "assets", "avatars", f"user_{uid}.png")
        if os.path.exists(candidate):
            avatar_img = candidate

    acc_entry = {
        "id": uid,
        "username": user_dict.get("username", kwargs.get("username", "")),
        "email": user_dict.get("email", kwargs.get("email", "")),
        "full_name": user_dict.get("full_name", kwargs.get("full_name", "")),
        "role": user_dict.get("role", kwargs.get("role", "user")),
        "avatar_color": user_dict.get("avatar_color", kwargs.get("avatar_color", "#3fb950")),
        "avatar_image": avatar_img,
        "is_verified": user_dict.get("is_verified", kwargs.get("is_verified", 0)),
        "token": tok,
        "is_default": user_dict.get("is_default", kwargs.get("is_default", True)),
        "is_active": True,
        "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Replace existing or append
    idx = next((i for i, a in enumerate(accounts) if (uid and a["id"] == uid) or (not uid and a.get("username") == acc_entry["username"])), None)
    if idx is not None:
        accounts[idx] = acc_entry
    else:
        accounts.append(acc_entry)

    data["accounts"] = accounts
    data["active_user_id"] = uid
    _write_data(data)

    if tok:
        try:
            with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump({"token": tok}, f)
        except Exception:
            pass
        try:
            admin_tok = paths.get_admin_token_path()
            with open(admin_tok, "w", encoding="utf-8") as f:
                json.dump({"token": tok}, f)
        except Exception:
            pass
        db.set_active_session_token(tok)
    log.info("Saved account %s (id=%s) as active.", acc_entry.get("username"), str(uid))


def remove_saved_account(user_id_or_username: Any) -> None:
    """Remove a saved account from the device by ID or username."""
    data = _read_data()
    if isinstance(user_id_or_username, int):
        accounts = [a for a in data.get("accounts", []) if a["id"] != user_id_or_username]
        removed_id = user_id_or_username
    else:
        accounts = [a for a in data.get("accounts", []) if a.get("username", "").lower() != str(user_id_or_username).lower()]
        removed_id = None
    data["accounts"] = accounts
    if data.get("active_user_id") == removed_id or (removed_id is None and not any(a["id"] == data.get("active_user_id") for a in accounts)):
        data["active_user_id"] = accounts[0]["id"] if accounts else None
    _write_data(data)
    log.info("Removed account %s from saved accounts.", str(user_id_or_username))


def switch_account(user_id_or_username: Any) -> Optional[Dict[str, Any]]:
    """
    Switch active session to another saved user account by ID or username.
    Returns the refreshed user dictionary, or None if not found.
    """
    data = _read_data()
    accounts = data.get("accounts", [])
    if isinstance(user_id_or_username, int):
        target = next((a for a in accounts if a["id"] == user_id_or_username), None)
    else:
        target = next((a for a in accounts if a.get("username", "").lower() == str(user_id_or_username).lower()), None)

    if not target:
        return None

    uid = target["id"]
    data["active_user_id"] = uid
    target["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_data(data)

    # Sync token file
    token = target.get("token", "")
    if token:
        try:
            with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump({"token": token}, f)
        except Exception:
            pass

    # Fetch live user from database if possible
    live_user = db.get_user(uid)
    if live_user:
        return live_user
    return target


def clear_active_account() -> None:
    """Clear active session token and active account pointer."""
    data = _read_data()
    data["active_user_id"] = None
    _write_data(data)
    try:
        if os.path.exists(_TOKEN_FILE):
            os.remove(_TOKEN_FILE)
    except Exception:
        pass


# ── Interactive Account Switcher Dialog ───────────────────────────────────────

class AccountSwitcherDialog:
    """
    Modal dialog allowing users to switch between multiple logged-in accounts,
    add another account, or remove accounts.
    """

    def __init__(
        self,
        parent: tk.Tk,
        current_user: Dict[str, Any],
        on_switch: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_add_account: Optional[Callable[[], None]] = None,
        on_logout: Optional[Callable[[], None]] = None,
        **kwargs
    ):
        self.parent = parent
        self.current_user = current_user
        self.on_switch = on_switch or kwargs.get("on_account_switched") or (lambda u: None)
        self.on_add_account = on_add_account or kwargs.get("on_add") or (lambda: None)
        self.on_logout = on_logout or (lambda: None)

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("CommitMaster — Switch Accounts")
        self.dialog.geometry("480x520")
        self.dialog.minsize(440, 460)
        self.dialog.configure(bg=COLORS["bg_darkest"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center on parent
        self.dialog.update_idletasks()
        pw = parent.winfo_width() if parent else 480
        ph = parent.winfo_height() if parent else 520
        px = parent.winfo_rootx() if parent else 100
        py = parent.winfo_rooty() if parent else 100
        x = max(50, px + (pw - 480) // 2)
        y = max(50, py + (ph - 520) // 2)
        self.dialog.geometry(f"480x520+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        p = tk.Frame(self.dialog, bg=COLORS["bg_darkest"], padx=24, pady=20)
        p.pack(fill="both", expand=True)

        # Header
        hdr = tk.Frame(p, bg=COLORS["bg_darkest"])
        hdr.pack(fill="x", pady=(0, 14))

        tk.Label(
            hdr, text="👥 Switch Accounts", font=FONTS["heading_md"],
            fg=COLORS["text_primary"], bg=COLORS["bg_darkest"]
        ).pack(side="left")

        tk.Label(
            p, text="Select an account to switch instantly, or sign in to another account.",
            font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"]
        ).pack(anchor="w", pady=(0, 14))

        # Accounts scrollable list container
        container = tk.Frame(p, bg=COLORS["bg_darkest"])
        container.pack(fill="both", expand=True, pady=(0, 14))

        canvas = tk.Canvas(container, bg=COLORS["bg_darkest"], highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLORS["bg_darkest"])

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=430)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_sw_wheel(event):
            delta = getattr(event, "delta", 0)
            if not delta:
                return "break"
            pixels = int(-(delta / 120.0) * 35) if abs(delta) >= 120 else (-1 if delta > 0 else 1) * 25
            try:
                canvas.yview_scroll(pixels, "units")
            except Exception:
                pass
            return "break"

        self.dialog.bind("<MouseWheel>", _on_sw_wheel)
        self.dialog.bind("<Button-4>", lambda e: canvas.yview_scroll(-25, "units"))
        self.dialog.bind("<Button-5>", lambda e: canvas.yview_scroll(25, "units"))
        canvas.bind("<MouseWheel>", _on_sw_wheel)
        scrollable_frame.bind("<MouseWheel>", _on_sw_wheel)

        accounts = get_saved_accounts()
        curr_id = self.current_user.get("id")

        if not accounts:
            tk.Label(
                scrollable_frame, text="No accounts saved on this device.",
                font=FONTS["body_md"], fg=COLORS["text_muted"], bg=COLORS["bg_darkest"]
            ).pack(pady=20)
        else:
            for acc in accounts:
                is_active = (acc["id"] == curr_id)
                self._render_account_card(scrollable_frame, acc, is_active)

        # Action buttons
        btn_box = tk.Frame(p, bg=COLORS["bg_darkest"])
        btn_box.pack(fill="x", pady=(4, 0))

        add_btn = tk.Button(
            btn_box, text="＋ Add Another Account", font=FONTS["body_md"],
            bg=COLORS["bg_card"], fg=COLORS["text_primary"],
            activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=14, pady=8,
            command=self._do_add_account
        )
        add_btn.pack(side="left")

        logout_btn = tk.Button(
            btn_box, text="Log Out Current", font=FONTS["body_sm"],
            bg=COLORS["bg_darkest"], fg=COLORS["danger"],
            activebackground=COLORS["bg_card"], activeforeground=COLORS["danger"],
            relief="flat", bd=0, cursor="hand2", padx=10, pady=8,
            command=self._do_logout
        )
        logout_btn.pack(side="right")

    def _render_account_card(self, parent: tk.Frame, acc: Dict[str, Any], is_active: bool):
        card = tk.Frame(
            parent,
            bg=COLORS["bg_card"] if not is_active else COLORS["bg_medium"],
            padx=14, pady=10,
            highlightthickness=1,
            highlightbackground=COLORS["accent"] if is_active else COLORS["border"]
        )
        card.pack(fill="x", pady=4)

        # Avatar photo or badge
        from commitmaster import avatar_utils
        if not acc.get("avatar_image") and acc.get("id"):
            try:
                db_u = db.get_user(acc["id"])
                if db_u and db_u.get("avatar_image"):
                    acc["avatar_image"] = db_u["avatar_image"]
            except Exception:
                pass
        if not acc.get("avatar_image") and acc.get("id"):
            candidate = os.path.join(avatar_utils.AVATARS_DIR, f"user_{acc['id']}.png")
            if os.path.exists(candidate):
                acc["avatar_image"] = candidate

        if not hasattr(self, "_photos"):
            self._photos = []

        av_photo = avatar_utils.get_avatar_photo(acc, size=40, rounded=True, master=self.dialog)
        if av_photo:
            self._photos.append(av_photo)
            av_lbl = tk.Label(card, image=av_photo, bg=card["bg"], width=40, height=40)
            av_lbl.image = av_photo
            av_lbl.pack(side="left", padx=(0, 12))
        else:
            av_color = acc.get("avatar_color", "#3fb950")
            initial = (acc.get("full_name") or acc.get("username") or "?")[0].upper()
            av_canvas = tk.Canvas(card, width=40, height=40, bg=card["bg"], highlightthickness=0)
            av_canvas.pack(side="left", padx=(0, 12))
            av_canvas.create_oval(2, 2, 38, 38, fill=av_color, outline="")
            av_canvas.create_text(20, 20, text=initial, fill="white", font=("Segoe UI", 12, "bold"))

        # Details
        info_box = tk.Frame(card, bg=card["bg"])
        info_box.pack(side="left", fill="x", expand=True)

        name_row = tk.Frame(info_box, bg=card["bg"])
        name_row.pack(fill="x")

        display_name = acc.get("full_name") or acc.get("username")
        tk.Label(
            name_row, text=display_name, font=FONTS["label_bold"],
            fg=COLORS["text_primary"], bg=card["bg"]
        ).pack(side="left")

        if is_active:
            tk.Label(
                name_row, text="● ACTIVE", font=("Segoe UI", 8, "bold"),
                fg=COLORS["accent"], bg=card["bg"]
            ).pack(side="left", padx=(8, 0))

        if db.is_admin_username(acc.get("username")):
            tk.Label(
                name_row, text="ADMIN", font=("Segoe UI", 8, "bold"),
                fg="#f0883e", bg=card["bg"]
            ).pack(side="left", padx=(6, 0))

        if acc.get("is_verified"):
            tk.Label(
                name_row, text="✔ Verified", font=("Segoe UI", 8),
                fg=COLORS["success"], bg=card["bg"]
            ).pack(side="left", padx=(6, 0))

        # Email & username
        sub_text = f"@{acc.get('username')} • {acc.get('email')}"
        tk.Label(
            info_box, text=sub_text, font=FONTS["caption"],
            fg=COLORS["text_secondary"], bg=card["bg"]
        ).pack(anchor="w", pady=(1, 0))

        # Action on card
        action_box = tk.Frame(card, bg=card["bg"])
        action_box.pack(side="right")

        if not is_active:
            switch_btn = tk.Button(
                action_box, text="Switch", font=FONTS["body_sm"],
                bg=COLORS["accent"], fg="#ffffff",
                activebackground=COLORS["accent_hover"], activeforeground="#ffffff",
                relief="flat", bd=0, cursor="hand2", padx=10, pady=4,
                command=lambda a=acc: self._do_switch(a)
            )
            switch_btn.pack(side="right", padx=(4, 0))

            rm_btn = tk.Button(
                action_box, text="✕", font=("Segoe UI", 9),
                bg=card["bg"], fg=COLORS["text_muted"],
                activebackground=COLORS["bg_card_hover"], activeforeground=COLORS["danger"],
                relief="flat", bd=0, cursor="hand2", padx=4, pady=2,
                command=lambda uid=acc["id"]: self._do_remove(uid)
            )
            rm_btn.pack(side="right")
        else:
            tk.Label(
                action_box, text="Current Account", font=FONTS["caption"],
                fg=COLORS["text_muted"], bg=card["bg"]
            ).pack(side="right", padx=6)

    def _do_switch(self, account: Dict[str, Any]):
        try:
            self.dialog.destroy()
        except Exception:
            pass
        switched_user = switch_account(account["id"])
        if switched_user and self.on_switch:
            self.on_switch(switched_user)

    def _do_remove(self, user_id: int):
        remove_saved_account(user_id)
        # Rebuild dialog
        try:
            self.dialog.destroy()
        except Exception:
            pass
        AccountSwitcherDialog(
            self.parent, self.current_user, self.on_switch, self.on_add_account, self.on_logout
        )

    def _do_add_account(self):
        try:
            self.dialog.destroy()
        except Exception:
            pass
        if self.on_add_account:
            self.on_add_account()

    def _do_logout(self):
        try:
            self.dialog.destroy()
        except Exception:
            pass
        clear_active_account()
        if self.on_logout:
            self.on_logout()
