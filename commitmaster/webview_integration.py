"""
CommitMaster — Dashboard integration helpers for 3D visualization scenes.

Provides high-level helpers to instantiate and embed 3D views into Tkinter
pages, manage data-loading threads, and render high-fidelity 2D Tkinter
fallbacks when WebView2 is unavailable or 3D effects are disabled.
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, Optional, Union

from commitmaster import scene_data
from commitmaster.app_styles import COLORS, FONTS
from commitmaster.logger import get
from commitmaster.webview_host import WebViewPanel, is_webview2_available

log = get("webview_integration")


class ScenePageManager:
    """
    Manages active 3D visualization scenes across the application lifecycle.
    Caches WebView panels and ensures clean theme updates and resource disposal.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self._active_panel: Optional[WebViewPanel] = None
        self._current_scene: Optional[str] = None

    def mount_scene(
        self,
        parent_frame: tk.Frame,
        scene_name: str,
        data_provider: Callable[[], Dict[str, Any]],
        fallback_builder: Optional[Callable[[tk.Frame, Dict[str, Any]], tk.Widget]] = None,
    ) -> Union[WebViewPanel, tk.Widget]:
        """
        Mount a 3D scene into parent_frame.
        If WebView2 is unavailable, falls back to a 2D Tkinter view immediately.
        """
        # 1. Fallback if WebView2 is not installed or available
        if not is_webview2_available():
            log.info("WebView2 not available; mounting 2D fallback for scene '%s'", scene_name)
            return self._mount_fallback(parent_frame, scene_name, data_provider, fallback_builder)

        # 2. Build or reuse WebViewPanel
        try:
            panel = WebViewPanel(parent_frame)
            panel.start()

            # Data loader in background thread
            def load_and_dispatch():
                try:
                    payload = data_provider()
                    # Deliver scene switch and data
                    panel.navigate(scene_name, payload)
                except Exception as exc:
                    log.error("Failed to load data for 3D scene '%s': %s", scene_name, exc)

            threading.Thread(target=load_and_dispatch, daemon=True, name=f"3d-data-{scene_name}").start()

            self._active_panel = panel
            self._current_scene = scene_name
            return panel
        except Exception as exc:
            log.error("Failed to initialize 3D scene panel for '%s': %s", scene_name, exc)
            return self._mount_fallback(parent_frame, scene_name, data_provider, fallback_builder)

    def _mount_fallback(
        self,
        parent_frame: tk.Frame,
        scene_name: str,
        data_provider: Callable[[], Dict[str, Any]],
        fallback_builder: Optional[Callable[[tk.Frame, Dict[str, Any]], tk.Widget]] = None,
    ) -> tk.Widget:
        container = tk.Frame(parent_frame, bg=COLORS["bg_card"], padx=20, pady=20)
        container.pack(fill="both", expand=True)

        header = tk.Label(
            container,
            text=f"2D Fallback View — {scene_name.replace('_', ' ').title()}",
            font=FONTS["title"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_card"],
        )
        header.pack(anchor="w", pady=(0, 10))

        sub = tk.Label(
            container,
            text="Interactive 3D acceleration is currently inactive. Showing data summary.",
            font=FONTS["caption"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_card"],
        )
        sub.pack(anchor="w", pady=(0, 15))

        try:
            data = data_provider()
            if fallback_builder:
                return fallback_builder(container, data)

            # Default generic summary representation
            info_box = tk.Text(
                container,
                bg=COLORS["bg_input"],
                fg=COLORS["text_primary"],
                font=FONTS["code"],
                relief="flat",
                height=15,
            )
            info_box.pack(fill="both", expand=True)

            summary = data.get("summary", data.get("metrics", {}))
            text_lines = [f"{k}: {v}" for k, v in summary.items()]
            if not text_lines:
                text_lines = [f"Records loaded: {len(data.get('nodes', data.get('findings', [])))} items"]

            info_box.insert("1.0", "\n".join(text_lines))
            info_box.config(state="disabled")
        except Exception as exc:
            log.debug("Fallback data preview failed: %s", exc)

        return container

    def sync_theme(self, theme_tokens: Dict[str, str]) -> None:
        """Push current theme tokens to the active 3D viewport."""
        if self._active_panel and self._active_panel.is_ready():
            self._active_panel.set_theme(theme_tokens)

    def dispose(self) -> None:
        if self._active_panel:
            self._active_panel.destroy()
            self._active_panel = None
