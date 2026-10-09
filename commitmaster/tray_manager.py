"""
CommitMaster — Windows System Tray / Taskbar Notification Area Manager.
========================================================================
Runs CommitMaster as a background tray icon in the Windows taskbar panel.
Supports:
  • Minimizing window directly into the system tray
  • Right-click context menu (Open, Git Desktop, My Commits, Profile, Switch Account, Quit)
  • Single/double click to restore window
  • Full quit action that cleanly terminates the entire process
"""
import os
import sys
import threading
from typing import Any, Callable, Optional
from PIL import Image, ImageDraw
import pystray

from commitmaster.logger import get

log = get("tray_manager")

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_tray_image() -> Image.Image:
    """Load or generate a crisp CommitMaster tray icon image."""
    logo_path = os.path.join(APP_DIR, "assets", "logo_64.png")
    if os.path.exists(logo_path):
        try:
            return Image.open(logo_path).convert("RGBA")
        except Exception:
            pass

    # High-quality fallback vector drawing
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Background circle - deep obsidian
    d.ellipse([2, 2, 62, 62], fill=(9, 13, 22), outline=(30, 41, 59), width=2)
    # Center emerald node
    d.ellipse([24, 24, 40, 40], fill=(16, 185, 129))
    # Top & bottom stems
    d.line([32, 12, 32, 24], fill=(16, 185, 129), width=3)
    d.line([32, 40, 32, 52], fill=(16, 185, 129), width=3)
    # Branch line to right
    d.line([36, 28, 48, 20], fill=(255, 108, 76), width=3)
    d.ellipse([46, 16, 54, 24], fill=(255, 108, 76))
    return img


class TrayManager:
    """
    Manages the Windows taskbar notification area / system tray icon.
    """

    def __init__(
        self,
        on_open: Callable[[], None],
        on_git_desktop: Optional[Callable[[], None]] = None,
        on_commits: Optional[Callable[[], None]] = None,
        on_profile: Optional[Callable[[], None]] = None,
        on_switch_account: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ):
        self.on_open = on_open
        self.on_git_desktop = on_git_desktop or on_open
        self.on_commits = on_commits or on_open
        self.on_profile = on_profile or on_open
        self.on_switch_account = on_switch_account or on_open
        self.on_quit = on_quit or (lambda: sys.exit(0))

        self._icon: Optional[pystray.Icon] = None
        self._running: bool = False

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("🖥️ Open CommitMaster", lambda icon, item: self.on_open(), default=True),
            pystray.MenuItem("💻 Git Desktop", lambda icon, item: self.on_git_desktop()),
            pystray.MenuItem("📝 My Commits", lambda icon, item: self.on_commits()),
            pystray.MenuItem("👤 Profile", lambda icon, item: self.on_profile()),
            pystray.MenuItem("👥 Switch Account", lambda icon, item: self.on_switch_account()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Quit", lambda icon, item: self._handle_quit()),
        )

    def start(self) -> None:
        """Start the system tray icon detached in the background."""
        if self._running and self._icon:
            return

        try:
            image = _load_tray_image()
            menu = self._build_menu()
            self._icon = pystray.Icon(
                "CommitMaster",
                image,
                "CommitMaster — Intelligent Git Companion",
                menu=menu
            )
            self._running = True
            self._icon.run_detached()
            log.info("System tray icon started successfully.")
        except Exception as exc:
            log.warning("Could not start system tray icon: %s", exc)

    def stop(self) -> None:
        """Stop and remove the system tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
        self._running = False
        log.info("System tray icon stopped.")

    def notify(self, title: str, message: str) -> None:
        """Display a Windows notification balloon via the system tray icon."""
        if self._icon and self._running:
            try:
                self._icon.notify(message, title)
            except Exception as e:
                log.debug("Tray notification failed: %s", e)

    def _handle_quit(self) -> None:
        """User clicked Quit from the tray menu — shut down everything."""
        log.info("User requested Quit from tray icon.")
        self.stop()
        if self.on_quit:
            try:
                self.on_quit()
            except Exception:
                pass
        # Exit process cleanly
        os._exit(0)
