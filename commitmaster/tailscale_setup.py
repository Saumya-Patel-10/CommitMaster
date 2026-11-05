"""
CommitMaster — Tailscale Onboarding & Auto-Installer Service
============================================================
Handles guided consent, automatic download & installation of Tailscale,
directs users to create/sign in to their Tailscale account, and registers
client nodes to Saumya's central private cloud hub.
"""

import os
import sys
import json
import time
import shutil
import logging
import threading
import subprocess
import webbrowser
import tempfile
from typing import Optional, Tuple, Dict, Any, Callable

import tkinter as tk
from tkinter import ttk, messagebox

import requests

from commitmaster import tailscale_service
from commitmaster import database as db
from commitmaster.app_styles import COLORS, FONTS

log = logging.getLogger("commitmaster.tailscale_setup")

TAILSCALE_INSTALLER_URL = "https://pkgs.tailscale.com/stable/tailscale-setup-latest.exe"
TAILSCALE_START_URL = "https://login.tailscale.com/start"
DEFAULT_HUB_HOST = "100.64.108.92:8000"
DEFAULT_MAGIC_DNS_HUB = "saumya-pc.tail9690b8.ts.net:8000"


def get_default_hub_address() -> str:
    """Return best known hub address (MagicDNS if resolvable, otherwise Tailscale IP)."""
    return DEFAULT_HUB_HOST


def open_tailscale_signup_page() -> bool:
    """Open Tailscale's official start / sign-up page in the default web browser."""
    try:
        webbrowser.open(TAILSCALE_START_URL)
        return True
    except Exception as exc:
        log.error("Failed to open Tailscale signup page: %s", exc)
        return False


def launch_tailscale_app() -> bool:
    """Launch Tailscale GUI application or trigger tailscale up."""
    binary = tailscale_service.get_tailscale_binary()
    if binary:
        try:
            # Try launching the GUI client if present in the same directory
            gui_exe = os.path.join(os.path.dirname(binary), "tailscale-ipn.exe")
            if os.path.exists(gui_exe):
                subprocess.Popen([gui_exe])
                return True
            # Otherwise run tailscale up
            subprocess.Popen([binary, "up"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True
        except Exception as exc:
            log.warning("Could not launch tailscale app directly: %s", exc)
    return False


def download_tailscale_installer(
    dest_path: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_flag: Optional[threading.Event] = None
) -> Tuple[bool, str]:
    """
    Download the official Tailscale Windows installer with real-time progress callbacks.
    Returns (success, installer_path_or_error_msg).
    """
    if not dest_path:
        dest_path = os.path.join(tempfile.gettempdir(), "tailscale-setup-latest.exe")

    try:
        log.info("Downloading Tailscale installer from %s to %s", TAILSCALE_INSTALLER_URL, dest_path)
        resp = requests.get(TAILSCALE_INSTALLER_URL, stream=True, timeout=15)
        resp.raise_for_status()

        total_bytes = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 65536

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if cancel_flag and cancel_flag.is_set():
                    log.info("Download cancelled by user.")
                    return False, "Download cancelled by user."
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_bytes)

        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000000:
            log.info("Tailscale installer downloaded successfully: %s (%d bytes)", dest_path, downloaded)
            return True, dest_path
        return False, "Downloaded file appears incomplete."

    except Exception as exc:
        log.error("Failed to download Tailscale installer: %s", exc)
        return False, str(exc)


def run_tailscale_installer(installer_path: str, wait_timeout: int = 180) -> Tuple[bool, str]:
    """
    Execute the downloaded Tailscale setup executable.
    Runs interactively or with passive UI so user sees setup progress.
    """
    if not os.path.exists(installer_path):
        return False, f"Installer file not found at: {installer_path}"

    try:
        log.info("Running Tailscale installer: %s", installer_path)
        # Run installer
        proc = subprocess.Popen([installer_path])
        return True, "Installer launched successfully."
    except Exception as exc:
        log.error("Failed to run installer %s: %s", installer_path, exc)
        return False, str(exc)


def register_with_network_hub(
    hub_address: str,
    tailscale_login: str,
    display_name: str = "",
    username: str = "",
    timeout: float = 6.0
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Register node into Saumya's central network hub over Tailscale.
    Sends node metadata, registers with network_members, and returns hub info.
    """
    clean_hub = hub_address.strip()
    if not clean_hub.startswith("http://") and not clean_hub.startswith("https://"):
        clean_hub = f"http://{clean_hub}"

    endpoint = f"{clean_hub.rstrip('/')}/api/network/join"
    
    payload = {
        "tailscale_login": tailscale_login.strip(),
        "display_name": display_name.strip() or tailscale_login.split("@")[0],
        "node_hostname": tailscale_service.get_device_hostname(),
        "node_ip": tailscale_service.get_tailscale_ip() or "",
        "username": username.strip() or tailscale_login.split("@")[0]
    }

    try:
        log.info("Registering with network hub at %s: %s", endpoint, payload)
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            # Successfully joined: save server URL to client configuration
            db.set_server_url(clean_hub)
            return True, data.get("message", "Connected successfully to CommitMaster network!"), data
        else:
            err = resp.json().get("error", f"Server returned HTTP {resp.status_code}")
            return False, err, {}
    except requests.exceptions.ConnectionError:
        return False, f"Could not connect to Hub at {clean_hub}. Ensure Tailscale is connected and the hub is running.", {}
    except Exception as exc:
        return False, f"Network registration error: {exc}", {}


# ── Interactive Onboarding Dialog ─────────────────────────────────────────────

class TailscaleSetupDialog(tk.Toplevel):
    """
    Full guided wizard for onboarding users to Saumya's private Tailscale network.
    Handles disclosure, download, installation, sign-up guidance, and node registration.
    """

    def __init__(self, parent=None, on_complete: Optional[Callable[[bool], None]] = None):
        super().__init__(parent)
        self.title("CommitMaster — Private Cloud Network Setup")
        self.geometry("640x580")
        self.minsize(580, 520)
        self.configure(bg=COLORS["bg_darkest"])
        self.transient(parent)
        self.grab_set()

        self.on_complete = on_complete
        self.installer_path: Optional[str] = None
        self.cancel_download_event = threading.Event()
        self.current_step = 1

        self._build_ui()
        self._show_step(1)

    def _build_ui(self):
        # Header banner
        header = tk.Frame(self, bg=COLORS["bg_dark"], height=70)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title_box = tk.Frame(header, bg=COLORS["bg_dark"])
        title_box.pack(side="left", padx=24, pady=12)

        tk.Label(
            title_box,
            text="🛡️ Private Cloud Network Setup",
            font=FONTS["title"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_dark"]
        ).pack(anchor="w")

        self.step_label = tk.Label(
            title_box,
            text="Step 1 of 4: Disclosure & Consent",
            font=FONTS["small"],
            fg=COLORS["accent"],
            bg=COLORS["bg_dark"]
        )
        self.step_label.pack(anchor="w")

        # Container for wizard pages
        self.content_container = tk.Frame(self, bg=COLORS["bg_darkest"])
        self.content_container.pack(fill="both", expand=True, padx=28, pady=20)

    def _clear_content(self):
        for widget in self.content_container.winfo_children():
            widget.destroy()

    def _show_step(self, step_num: int):
        self.current_step = step_num
        self._clear_content()

        if step_num == 1:
            self.step_label.config(text="Step 1 of 4: Network Disclosure & Consent")
            self._render_step_disclosure()
        elif step_num == 2:
            self.step_label.config(text="Step 2 of 4: Tailscale Setup")
            self._render_step_download()
        elif step_num == 3:
            self.step_label.config(text="Step 3 of 4: Tailscale Account & Sign-In")
            self._render_step_account()
        elif step_num == 4:
            self.step_label.config(text="Step 4 of 4: Connect to Team Network")
            self._render_step_connect()
        elif step_num == 5:
            self.step_label.config(text="Connected to Private Cloud!")
            self._render_step_success()

    # ── Step 1: Disclosure & Consent ──────────────────────────────────────────
    def _render_step_disclosure(self):
        card = tk.Frame(self.content_container, bg=COLORS["bg_card"], bd=1, relief="solid", highlightthickness=0)
        card.pack(fill="both", expand=True, pady=10)

        inner = tk.Frame(card, bg=COLORS["bg_card"])
        inner.pack(fill="both", expand=True, padx=24, pady=20)

        tk.Label(
            inner,
            text="Private Cloud Storage & Team Sync",
            font=FONTS["heading"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 8))

        disclosure_text = (
            "CommitMaster uses Tailscale to connect securely to your team's private cloud network "
            "without opening public ports or exposing your data to the public internet.\n\n"
            "Key features of the private network:\n"
            "  • Centralized Cloud Database: Commit history, statistics, and graphs sync across devices.\n"
            "  • End-to-End Encryption: Powered by WireGuard® mesh networking.\n"
            "  • Privacy First: Direct device-to-device peer mesh; admin details are securely protected.\n\n"
            "Notice: Joining the team network requires Tailscale to be installed on your computer. "
            "With your permission, CommitMaster can automatically download the official installer "
            "and guide you through connecting."
        )

        tk.Label(
            inner,
            text=disclosure_text,
            font=FONTS["body"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_card"],
            justify="left",
            wraplength=520
        ).pack(anchor="w", pady=(0, 16))

        # Check existing installation
        is_installed = tailscale_service.is_tailscale_installed()
        status_text = "🟢 Tailscale is already installed on this PC." if is_installed else "ℹ️ Tailscale is not yet installed on this PC."
        status_color = COLORS["success"] if is_installed else COLORS["info"]

        tk.Label(
            inner,
            text=status_text,
            font=FONTS["body_bold"],
            fg=status_color,
            bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 20))

        # Bottom buttons
        btn_box = tk.Frame(self.content_container, bg=COLORS["bg_darkest"])
        btn_box.pack(fill="x", side="bottom", pady=10)

        skip_btn = tk.Button(
            btn_box,
            text="Skip (Local Offline Mode)",
            command=self._on_skip,
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
            activebackground=COLORS["bg_dark"],
            font=FONTS["body"],
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2"
        )
        skip_btn.pack(side="left")

        confirm_text = "Continue to Connect ->" if is_installed else "Install Tailscale & Connect ->"
        confirm_btn = tk.Button(
            btn_box,
            text=confirm_text,
            command=lambda: self._show_step(2),
            bg=COLORS["accent"],
            fg="#ffffff",
            activebackground=COLORS["accent_hover"],
            font=FONTS["body_bold"],
            bd=0,
            padx=18,
            pady=8,
            cursor="hand2"
        )
        confirm_btn.pack(side="right")

    # ── Step 2: Download & Install ────────────────────────────────────────────
    def _render_step_download(self):
        # If already installed, skip right to account sign in
        if tailscale_service.is_tailscale_installed():
            self._show_step(3)
            return

        card = tk.Frame(self.content_container, bg=COLORS["bg_card"], bd=1, relief="solid")
        card.pack(fill="both", expand=True, pady=10)

        inner = tk.Frame(card, bg=COLORS["bg_card"])
        inner.pack(fill="both", expand=True, padx=24, pady=24)

        tk.Label(
            inner,
            text="Downloading Tailscale Installer",
            font=FONTS["heading"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 8))

        self.dl_status_label = tk.Label(
            inner,
            text="Starting download from pkgs.tailscale.com...",
            font=FONTS["body"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_card"]
        )
        self.dl_status_label.pack(anchor="w", pady=(0, 16))

        self.progress_bar = ttk.Progressbar(inner, orient="horizontal", mode="determinate", length=480)
        self.progress_bar.pack(fill="x", pady=(0, 12))

        self.bytes_label = tk.Label(
            inner,
            text="0 MB / 0 MB",
            font=FONTS["small"],
            fg=COLORS["text_muted"],
            bg=COLORS["bg_card"]
        )
        self.bytes_label.pack(anchor="w", pady=(0, 20))

        # Run setup action button (hidden until download finishes)
        self.run_install_btn = tk.Button(
            inner,
            text="Launch Tailscale Setup",
            command=self._launch_downloaded_installer,
            bg=COLORS["accent"],
            fg="#ffffff",
            font=FONTS["body_bold"],
            bd=0,
            padx=18,
            pady=8,
            cursor="hand2"
        )

        # Start download in background thread
        threading.Thread(target=self._start_download_worker, daemon=True).start()

    def _start_download_worker(self):
        def on_progress(downloaded, total):
            if total > 0:
                pct = int((downloaded / total) * 100)
                dl_mb = downloaded / (1024 * 1024)
                tot_mb = total / (1024 * 1024)
                self.after(0, lambda: self._update_download_ui(pct, f"{dl_mb:.1f} MB / {tot_mb:.1f} MB"))

        success, result = download_tailscale_installer(
            progress_callback=on_progress,
            cancel_flag=self.cancel_download_event
        )

        if success:
            self.installer_path = result
            self.after(0, self._on_download_success)
        else:
            self.after(0, lambda: self._on_download_failure(result))

    def _update_download_ui(self, pct: int, text: str):
        if hasattr(self, "progress_bar"):
            self.progress_bar["value"] = pct
        if hasattr(self, "bytes_label"):
            self.bytes_label.config(text=text)

    def _on_download_success(self):
        self.dl_status_label.config(
            text="✅ Download complete! Click below to run the Tailscale installer.",
            fg=COLORS["success"]
        )
        self.progress_bar["value"] = 100
        self.run_install_btn.pack(anchor="w", pady=10)

    def _on_download_failure(self, err_msg: str):
        self.dl_status_label.config(
            text=f"❌ Download failed: {err_msg}",
            fg=COLORS["error"]
        )

    def _launch_downloaded_installer(self):
        if self.installer_path and os.path.exists(self.installer_path):
            run_tailscale_installer(self.installer_path)
            messagebox.showinfo(
                "Tailscale Setup Started",
                "The Tailscale setup wizard has been launched.\n\n"
                "Please complete the installation, then click 'Next' to continue."
            )
            self._show_step(3)

    # ── Step 3: Account & Sign In Guidance ────────────────────────────────────
    def _render_step_account(self):
        card = tk.Frame(self.content_container, bg=COLORS["bg_card"], bd=1, relief="solid")
        card.pack(fill="both", expand=True, pady=10)

        inner = tk.Frame(card, bg=COLORS["bg_card"])
        inner.pack(fill="both", expand=True, padx=24, pady=24)

        tk.Label(
            inner,
            text="Sign In or Create Tailscale Account",
            font=FONTS["heading"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 8))

        guide_text = (
            "To join your team's private network, you need a free Tailscale account.\n"
            "You can sign in with your Google, GitHub, Microsoft, or Apple account.\n\n"
            "1. Click 'Open Tailscale Sign-Up' below to create or log in in your browser.\n"
            "2. Once signed in, make sure Tailscale is active on this computer.\n"
            "3. Click 'Next: Join Team Network' to register your node."
        )

        tk.Label(
            inner,
            text=guide_text,
            font=FONTS["body"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_card"],
            justify="left"
        ).pack(anchor="w", pady=(0, 20))

        action_box = tk.Frame(inner, bg=COLORS["bg_card"])
        action_box.pack(anchor="w", pady=(0, 24))

        signup_btn = tk.Button(
            action_box,
            text="🌐 Open Tailscale Sign-Up (Browser)",
            command=open_tailscale_signup_page,
            bg=COLORS["accent"],
            fg="#ffffff",
            activebackground=COLORS["accent_hover"],
            font=FONTS["body_bold"],
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2"
        )
        signup_btn.pack(side="left", padx=(0, 12))

        launch_btn = tk.Button(
            action_box,
            text="🚀 Launch Tailscale App",
            command=launch_tailscale_app,
            bg=COLORS["bg_dark"],
            fg=COLORS["text_primary"],
            activebackground=COLORS["bg_medium"],
            font=FONTS["body"],
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2"
        )
        launch_btn.pack(side="left")

        # Bottom navigation
        btn_box = tk.Frame(self.content_container, bg=COLORS["bg_darkest"])
        btn_box.pack(fill="x", side="bottom", pady=10)

        back_btn = tk.Button(
            btn_box,
            text="<- Back",
            command=lambda: self._show_step(1),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
            font=FONTS["body"],
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2"
        )
        back_btn.pack(side="left")

        next_btn = tk.Button(
            btn_box,
            text="Next: Join Team Network ->",
            command=lambda: self._show_step(4),
            bg=COLORS["accent"],
            fg="#ffffff",
            activebackground=COLORS["accent_hover"],
            font=FONTS["body_bold"],
            bd=0,
            padx=18,
            pady=8,
            cursor="hand2"
        )
        next_btn.pack(side="right")

    # ── Step 4: Network Details & Join ────────────────────────────────────────
    def _render_step_connect(self):
        card = tk.Frame(self.content_container, bg=COLORS["bg_card"], bd=1, relief="solid")
        card.pack(fill="both", expand=True, pady=10)

        inner = tk.Frame(card, bg=COLORS["bg_card"])
        inner.pack(fill="both", expand=True, padx=24, pady=20)

        tk.Label(
            inner,
            text="Register Node with Team Hub",
            font=FONTS["heading"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            inner,
            text="Enter your Tailscale account details below to add your machine to the central database.",
            font=FONTS["body"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 16))

        # Auto-detect existing logged in Tailscale user if connected
        detected_user = tailscale_service.get_tailnet_user() or {}
        default_email = detected_user.get("LoginName", "")
        default_name = detected_user.get("DisplayName", "")
        my_node_ip = tailscale_service.get_tailscale_ip() or ""

        # Email field
        tk.Label(inner, text="Your Tailscale Account / Email *", font=FONTS["body_bold"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
        self.email_entry = tk.Entry(inner, font=FONTS["body"], bg=COLORS["bg_input"], fg=COLORS["text_primary"], insertbackground=COLORS["text_primary"], bd=1, relief="solid")
        self.email_entry.pack(fill="x", pady=(4, 12))
        if default_email:
            self.email_entry.insert(0, default_email)

        # Display Name field
        tk.Label(inner, text="Your Name / Display Name", font=FONTS["body_bold"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
        self.name_entry = tk.Entry(inner, font=FONTS["body"], bg=COLORS["bg_input"], fg=COLORS["text_primary"], insertbackground=COLORS["text_primary"], bd=1, relief="solid")
        self.name_entry.pack(fill="x", pady=(4, 12))
        if default_name:
            self.name_entry.insert(0, default_name)

        # Hub address
        tk.Label(inner, text="Team Hub Address (Private Tailnet)", font=FONTS["body_bold"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
        self.hub_entry = tk.Entry(inner, font=FONTS["body"], bg=COLORS["bg_input"], fg=COLORS["text_primary"], insertbackground=COLORS["text_primary"], bd=1, relief="solid")
        self.hub_entry.pack(fill="x", pady=(4, 12))
        self.hub_entry.insert(0, get_default_hub_address())

        self.join_status_label = tk.Label(
            inner,
            text=f"Detected Node IP: {my_node_ip or 'Connecting...'}",
            font=FONTS["small"],
            fg=COLORS["text_muted"],
            bg=COLORS["bg_card"]
        )
        self.join_status_label.pack(anchor="w", pady=(4, 16))

        # Bottom buttons
        btn_box = tk.Frame(self.content_container, bg=COLORS["bg_darkest"])
        btn_box.pack(fill="x", side="bottom", pady=10)

        back_btn = tk.Button(
            btn_box,
            text="<- Back",
            command=lambda: self._show_step(3),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
            font=FONTS["body"],
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2"
        )
        back_btn.pack(side="left")

        self.connect_btn = tk.Button(
            btn_box,
            text="🛡️ Connect & Register Node",
            command=self._on_register_node,
            bg=COLORS["accent"],
            fg="#ffffff",
            activebackground=COLORS["accent_hover"],
            font=FONTS["body_bold"],
            bd=0,
            padx=18,
            pady=8,
            cursor="hand2"
        )
        self.connect_btn.pack(side="right")

    def _on_register_node(self):
        email = self.email_entry.get().strip()
        display_name = self.name_entry.get().strip()
        hub_addr = self.hub_entry.get().strip()

        if not email:
            messagebox.showwarning("Email Required", "Please enter your Tailscale account email to register.")
            return

        self.connect_btn.config(state="disabled", text="Connecting to Hub...")
        self.join_status_label.config(text="Sending registration request to central hub...", fg=COLORS["info"])

        def worker():
            ok, msg, data = register_with_network_hub(
                hub_address=hub_addr,
                tailscale_login=email,
                display_name=display_name
            )
            self.after(0, lambda: self._handle_register_result(ok, msg, data))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_register_result(self, ok: bool, msg: str, data: Dict):
        self.connect_btn.config(state="normal", text="🛡️ Connect & Register Node")
        if ok:
            self.registration_data = data
            self._show_step(5)
        else:
            self.join_status_label.config(text=f"❌ Connection failed: {msg}", fg=COLORS["error"])
            messagebox.showerror("Connection Failed", msg)

    # ── Step 5: Success & Completion ──────────────────────────────────────────
    def _render_step_success(self):
        card = tk.Frame(self.content_container, bg=COLORS["bg_card"], bd=1, relief="solid")
        card.pack(fill="both", expand=True, pady=10)

        inner = tk.Frame(card, bg=COLORS["bg_card"])
        inner.pack(fill="both", expand=True, padx=24, pady=30)

        tk.Label(
            inner,
            text="🎉 Connected to Team Network!",
            font=FONTS["title"],
            fg=COLORS["success"],
            bg=COLORS["bg_card"]
        ).pack(anchor="w", pady=(0, 12))

        hub_info = getattr(self, "registration_data", {}).get("hub", {})
        hub_ip = hub_info.get("tailscale_ip", DEFAULT_HUB_HOST)

        info_text = (
            "Your machine is now registered on CommitMaster's private cloud network.\n\n"
            f"  • Central Hub: {hub_ip}\n"
            "  • Status: Active & Approved\n"
            "  • Cloud Database: Synchronized\n\n"
            "All your commit messages, productivity analytics, repository statistics, "
            "and graphs are automatically synchronized to the team server over encrypted WireGuard."
        )

        tk.Label(
            inner,
            text=info_text,
            font=FONTS["body"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_card"],
            justify="left"
        ).pack(anchor="w", pady=(0, 24))

        finish_btn = tk.Button(
            inner,
            text="Open CommitMaster",
            command=self._on_finish,
            bg=COLORS["accent"],
            fg="#ffffff",
            activebackground=COLORS["accent_hover"],
            font=FONTS["body_bold"],
            bd=0,
            padx=20,
            pady=10,
            cursor="hand2"
        )
        finish_btn.pack(anchor="w")

    def _on_skip(self):
        if messagebox.askyesno(
            "Continue in Local Mode?",
            "Without joining the private network, your commits and statistics will only be stored "
            "locally on this PC and won't sync to the team's central server.\n\n"
            "Do you wish to continue in local offline mode?"
        ):
            if self.on_complete:
                self.on_complete(False)
            self.destroy()

    def _on_finish(self):
        if self.on_complete:
            self.on_complete(True)
        self.destroy()


def show_tailscale_setup(parent=None, on_complete: Optional[Callable[[bool], None]] = None) -> TailscaleSetupDialog:
    """Convenience entry point to display the onboarding dialog."""
    return TailscaleSetupDialog(parent=parent, on_complete=on_complete)

