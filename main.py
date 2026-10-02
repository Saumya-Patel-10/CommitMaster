"""CommitMaster — tray app that reminds you to commit when a coding session ends."""
import os
import queue
import sys
import threading

import pystray
from PIL import Image, ImageDraw

from commitmaster import flow, ui
from commitmaster.config import CONFIG_FILE, load_config
from commitmaster.session_monitor import SessionMonitor
from commitmaster.settings_ui import open_settings

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def _tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, 60, 60], fill=(46, 164, 79))          # GitHub green
    d.rounded_rectangle([18, 22, 46, 44], 4, fill="white") # commit "bubble"
    d.ellipse([28, 29, 36, 37], fill=(46, 164, 79))        # commit "dot"
    d.line([12, 52, 52, 52], fill="white", width=4)        # branch line
    return img


def main():
    cfg = load_config()
    events = queue.Queue()

    if not cfg["projects_dirs"]:
        ui.show_info("Welcome to CommitMaster!\n\n"
                     "First step: open config.json and set \"projects_dirs\" to the "
                     "folder(s) holding your cloned GitHub repos, e.g.\n"
                     "  \"projects_dirs\": [\"C:\\\\Data\\\\Saumya\\\\Projects\"]")
        os.startfile(CONFIG_FILE)

    monitor = SessionMonitor(cfg, events)
    monitor.start()

    if "--check-now" in sys.argv:  # test mode: trigger the flow immediately
        events.put(("session_end", []))

    def on_pause(_icon, item):
        monitor.paused = not monitor.paused

    def on_settings(_icon, item):
        threading.Thread(target=open_settings, daemon=True).start()

    def on_open_config(_icon, item):
        os.startfile(CONFIG_FILE)

    def on_check_now(_icon, item):
        ui.run_in_ui_thread(lambda: flow.handle_session_end(cfg, []))

    def on_exit(_icon, item):
        monitor.stop()
        icon.stop()

    ui.notify("CommitMaster is running",
              "Watching your coding apps. Look for the green icon in the system "
              "tray (you may need to click the ^ arrow to see hidden icons).")

    icon = pystray.Icon(
        "CommitMaster", _tray_image(), "CommitMaster",
        menu=pystray.Menu(
            pystray.MenuItem("Check for uncommitted work now", on_check_now),
            pystray.MenuItem("⚙ Settings…", on_settings, default=True),
            pystray.MenuItem("Open config.json", on_open_config),
            pystray.MenuItem("Pause monitoring", on_pause),
            pystray.MenuItem("Exit", on_exit),
        ),
    )
    icon.run_detached()

    # Main thread: consume monitor events and drive the UI flow.
    while True:
        try:
            event, payload = events.get(timeout=1)
        except queue.Empty:
            continue
        if event == "session_end":
            flow.handle_session_end(cfg, payload)


if __name__ == "__main__":
    main()