"""CommitMaster — tray app that reminds you to commit when a coding session ends."""
import os
import queue
import sys
import threading

import pystray
from PIL import Image, ImageDraw

from commitmaster import flow, ui
from commitmaster.config import CONFIG_FILE, get_manager
from commitmaster.logger import get
from commitmaster.session_monitor import SessionMonitor
from commitmaster.settings_ui import open_settings

log = get("main")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


# ── Tray icon ─────────────────────────────────────────────────────────────────

def _tray_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Outer circle — GitHub green
    d.ellipse([2, 2, 62, 62], fill=(63, 185, 80))
    # Dark inner circle for depth
    d.ellipse([8, 8, 56, 56], fill=(30, 35, 48))
    # Commit node (centre)
    d.ellipse([26, 26, 38, 38], fill=(63, 185, 80))
    # Branch lines
    d.line([32, 10, 32, 26], fill=(63, 185, 80), width=3)   # top stem
    d.line([32, 38, 32, 54], fill=(63, 185, 80), width=3)   # bottom stem
    d.line([14, 32, 26, 32], fill=(63, 185, 80), width=3)   # left arm
    d.line([38, 32, 50, 32], fill=(63, 185, 80), width=3)   # right arm
    # Branch dots
    d.ellipse([10, 28, 18, 36], fill=(63, 185, 80))
    d.ellipse([46, 28, 54, 36], fill=(63, 185, 80))
    return img


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("=" * 60)
    log.info("CommitMaster starting up.")

    cm = get_manager()        # singleton ConfigManager (hot-reload enabled)
    cfg = cm.get()

    if not cfg["projects_dirs"]:
        # Ensure config.json exists on disk before trying to open it.
        if not os.path.exists(CONFIG_FILE):
            from commitmaster.config import save_config
            save_config(cfg)
            log.info("Created default config.json at %s", CONFIG_FILE)
        ui.show_info(
            "Welcome to CommitMaster!\n\n"
            "First step: open Settings (tray icon → Settings) and add the\n"
            "folder(s) holding your cloned repos.\n\n"
            "Or edit config.json directly and set:\n"
            '  "projects_dirs": ["C:\\\\Data\\\\Saumya\\\\Projects"]'
        )
        if os.path.exists(CONFIG_FILE):
            os.startfile(CONFIG_FILE)

    events: queue.Queue = queue.Queue()
    monitor = SessionMonitor(cm, events)
    monitor.start()

    if "--check-now" in sys.argv:
        log.info("--check-now flag detected — triggering session end immediately.")
        events.put(("session_end", []))

    # ── Tray callbacks ────────────────────────────────────────────────────────

    def on_check_now(_icon, _item):
        log.info("Tray: manual check triggered.")
        flow.handle_session_end(cm, [])

    def on_settings(_icon, _item):
        log.info("Tray: opening settings.")
        threading.Thread(target=open_settings, args=(cm,), daemon=True).start()

    def on_open_config(_icon, _item):
        os.startfile(CONFIG_FILE)

    def on_pause(_icon, item):
        monitor.paused = not monitor.paused
        state = "paused" if monitor.paused else "resumed"
        log.info("Monitoring %s.", state)
        ui.notify("CommitMaster", f"Monitoring {state}.")

    def on_open_log(_icon, _item):
        from commitmaster.logger import LOG_FILE
        if os.path.exists(LOG_FILE):
            os.startfile(LOG_FILE)

    def on_exit(_icon, _item):
        log.info("CommitMaster exiting.")
        monitor.stop()
        cm.stop()
        _icon.stop()

    # ── Build tray icon ───────────────────────────────────────────────────────

    ui.notify(
        "CommitMaster is running",
        "Watching your coding apps. Look for the green icon in the system tray.",
    )

    icon = pystray.Icon(
        "CommitMaster",
        _tray_image(),
        "CommitMaster",
        menu=pystray.Menu(
            pystray.MenuItem("Check for uncommitted work now", on_check_now),
            pystray.MenuItem("⚙  Settings…", on_settings, default=True),
            pystray.MenuItem("Open config.json", on_open_config),
            pystray.MenuItem("Open commitmaster.log", on_open_log),
            pystray.MenuItem("Pause monitoring", on_pause),
            pystray.MenuItem("Exit", on_exit),
        ),
    )
    icon.run_detached()

    # ── Main event loop ───────────────────────────────────────────────────────
    log.info("Main event loop started.")
    while True:
        try:
            event, payload = events.get(timeout=1)
        except queue.Empty:
            continue
        if event == "session_end":
            flow.handle_session_end(cm, payload)


if __name__ == "__main__":
    main()