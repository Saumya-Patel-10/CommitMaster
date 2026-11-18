"""
CommitMaster — WebView2 Host & Python↔JavaScript Message Bridge.

Embeds a Chromium-based WebView2 viewport into Tkinter frames using pywebview
or Edge WebView2 controls. Provides an asynchronous, non-blocking JSON messaging
bridge for controlling 3D Three.js scenes, themes, and interactive node drilldowns.

Design principles:
  • WebView2 is optional — the entire app degrades gracefully to 2D if missing.
  • All 3D assets load from local files (web/dist or web/), requiring zero network.
  • Bidirectional communication is thread-safe and never blocks the Tkinter UI loop.
  • Resilient to process restarts, window resizing, and theme switches.
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional

from commitmaster import paths
from commitmaster.accessibility import get_accessibility_state
from commitmaster.logger import get

log = get("webview_host")


def get_web_dist_path() -> str:
    """
    Locate the index.html for 3D views.
    Checks:
      1. web/dist/index.html (production build)
      2. web/index.html (source dev mode)
      3. bundled PyInstaller path (sys._MEIPASS / web/dist)
    """
    # 1. Check frozen PyInstaller bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass_dist = os.path.join(sys._MEIPASS, "web", "dist", "index.html")
        if os.path.exists(meipass_dist):
            return meipass_dist
        meipass_src = os.path.join(sys._MEIPASS, "web", "index.html")
        if os.path.exists(meipass_src):
            return meipass_src

    # 2. Check workspace relative paths
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_path = os.path.join(repo_root, "web", "dist", "index.html")
    if os.path.exists(dist_path):
        return dist_path

    src_path = os.path.join(repo_root, "web", "index.html")
    if os.path.exists(src_path):
        return src_path

    return dist_path


def is_webview2_available() -> bool:
    """
    Check if WebView2 runtime / pywebview is installed and available.
    """
    try:
        import webview
        return True
    except ImportError:
        pass

    # Windows registry check for Evergreen WebView2 Runtime
    if sys.platform == "win32":
        try:
            import winreg
            keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-9915-4726-9221-7A37798369BA}"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-9915-4726-9221-7A37798369BA}"),
            ]
            for hkey, subkey in keys:
                try:
                    with winreg.OpenKey(hkey, subkey) as k:
                        val, _ = winreg.QueryValueEx(k, "pv")
                        if val:
                            return True
                except OSError:
                    continue
        except Exception:
            pass

    return False


class WebViewBridgeAPI:
    """
    Exposed JS-facing API for receiving messages from JavaScript in pywebview.
    """

    def __init__(self, panel: "WebViewPanel"):
        self.panel = panel

    def send_message(self, json_str: str) -> None:
        """Called from JavaScript: window.pywebview.api.send_message(payload_str)"""
        try:
            data = json.loads(json_str) if isinstance(json_str, str) else json_str
            self.panel._dispatch_incoming(data)
        except Exception as exc:
            log.error("Failed to parse message from JS: %s", exc)


class WebViewPanel:
    """
    Manages an embedded WebView2 control within a Tkinter container.
    Provides message sending, event listening, and automatic synchronization
    of theme tokens and accessibility preferences.
    """

    def __init__(
        self,
        parent_frame: tk.Frame,
        web_url_or_path: Optional[str] = None,
        on_ready: Optional[Callable[[], None]] = None,
    ):
        self.parent_frame = parent_frame
        self.target_url = web_url_or_path or get_web_dist_path()
        self.on_ready = on_ready

        self._is_ready = False
        self._window: Optional[Any] = None
        self._listeners: Dict[str, List[Callable[[Any], None]]] = {}
        self._pending_outgoing: queue.Queue = queue.Queue()
        self._lock = threading.Lock()

        # Wire built-in ready listener
        self.on_message("ready", self._on_js_ready)

    def is_available(self) -> bool:
        return is_webview2_available() and os.path.exists(self.target_url)

    def is_ready(self) -> bool:
        return self._is_ready

    def on_message(self, msg_type: str, callback: Callable[[Any], None]) -> None:
        """Register a handler for incoming messages from JS."""
        with self._lock:
            if msg_type not in self._listeners:
                self._listeners[msg_type] = []
            self._listeners[msg_type].append(callback)

    def off_message(self, msg_type: str, callback: Callable[[Any], None]) -> None:
        """Unregister a handler."""
        with self._lock:
            if msg_type in self._listeners:
                self._listeners[msg_type] = [cb for cb in self._listeners[msg_type] if cb != callback]

    def _dispatch_incoming(self, message: Dict[str, Any]) -> None:
        if not isinstance(message, dict):
            return

        msg_type = message.get("type", "")
        payload = message.get("payload")

        with self._lock:
            cbs = list(self._listeners.get(msg_type, []))

        for cb in cbs:
            try:
                cb(payload)
            except Exception as exc:
                log.error("Error executing JS message callback for '%s': %s", msg_type, exc)

    def _on_js_ready(self, payload: Any) -> None:
        log.info("WebView2 3D scene engine reported READY: %s", payload)
        self._is_ready = True

        # Flush pending messages
        while not self._pending_outgoing.empty():
            msg = self._pending_outgoing.get_nowait()
            self._send_raw(msg)

        if self.on_ready:
            try:
                self.parent_frame.after(0, self.on_ready)
            except Exception as exc:
                log.debug("on_ready callback error: %s", exc)

    def send_message(self, msg_type: str, payload: Any = None, action: str = "load") -> None:
        """
        Send a JSON payload to the 3D scene in JavaScript.
        Thread-safe: enqueues if the webview is not yet ready.
        """
        message = {
            "type": msg_type,
            "action": action,
            "payload": payload,
        }

        if not self._is_ready or not self._window:
            self._pending_outgoing.put(message)
            return

        self._send_raw(message)

    def _send_raw(self, message: Dict[str, Any]) -> None:
        if not self._window:
            return

        try:
            msg_json = json.dumps(message)
            script = f"if (window.__bridge_receive__) {{ window.__bridge_receive__({msg_json}); }}"
            self._window.evaluate_js(script)
        except Exception as exc:
            log.debug("Error delivering message to WebView2: %s", exc)

    def navigate(self, scene_name: str, scene_data: Optional[Dict[str, Any]] = None) -> None:
        """Switch active 3D visualization scene."""
        self.send_message("scene_switch", {"scene": scene_name, "data": scene_data})

    def set_theme(self, theme_colors: Dict[str, str]) -> None:
        """Sync active theme colors to the 3D CSS variables and Three.js background."""
        self.send_message("theme_update", theme_colors)

    def set_accessibility(self, user_prefs: Optional[Dict[str, Any]] = None) -> None:
        """Sync reduced motion and performance tier to JavaScript."""
        state = get_accessibility_state(user_prefs)
        self.send_message("accessibility_update", {
            "reducedMotion": state["reduced_motion"],
            "performanceTier": state["performance_tier"],
        })
        self.send_message("3d_toggle", {"enabled": state["3d_enabled"]})

    def start(self) -> None:
        """
        Initialize and mount the WebView2 control.
        """
        if not self.is_available():
            log.warning("WebView2 not available on system. Using fallback mode.")
            return

        try:
            import webview
            api = WebViewBridgeAPI(self)

            # Resolve local file URL
            url = f"file:///{os.path.abspath(self.target_url).replace(os.sep, '/')}"

            # Create pywebview window
            self._window = webview.create_window(
                title="CommitMaster 3D Viewport",
                url=url,
                js_api=api,
                frameless=True,
                easy_drag=False,
                background_color="#0a0e17",
            )
        except Exception as exc:
            log.error("Failed to initialize WebView2 control: %s", exc)

    def destroy(self) -> None:
        """Clean up WebView2 window and message queues."""
        self._is_ready = False
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
        with self._lock:
            self._listeners.clear()
