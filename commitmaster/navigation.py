"""Shared navigation behaviour for the user dashboard, admin portal and admin app:

  • sidebar buttons with an active-page indicator and hover feedback
  • flicker-free page switching (the page is built off-screen, then revealed)
  • back / forward history with header buttons and Alt+← / Alt+→ shortcuts
  • Ctrl+1 … Ctrl+9 shortcuts to jump between sidebar sections
  • eased mouse-wheel scrolling that never fights nested scroll areas or dialogs
"""
import tkinter as tk
from typing import Callable, Dict, List, Optional

from commitmaster.app_styles import COLORS, FONTS


# ── Sidebar buttons ───────────────────────────────────────────────────────────

def make_nav_button(parent: tk.Widget, icon: str, label: str, command: Callable,
                    padx: int = 14, pady: int = 9) -> tk.Button:
    """A sidebar entry: [3px accent indicator][ icon  label ]. Returns the Button (with ._indicator)."""
    row = tk.Frame(parent, bg=COLORS["bg_sidebar"])
    row.pack(fill="x")
    indicator = tk.Frame(row, width=3, bg=COLORS["bg_sidebar"])
    indicator.pack(side="left", fill="y")
    btn = tk.Button(row, text=f"  {icon}   {label}", font=FONTS["label"],
                    fg=COLORS["text_secondary"], bg=COLORS["bg_sidebar"],
                    activebackground=COLORS["bg_medium"], activeforeground=COLORS["text_primary"],
                    relief="flat", bd=0, cursor="hand2", anchor="w", padx=padx, pady=pady,
                    command=command)
    btn.pack(side="left", fill="x", expand=True)
    btn._indicator = indicator          # type: ignore[attr-defined]
    btn._active = False                 # type: ignore[attr-defined]

    def on_enter(_e):
        if not btn._active:             # type: ignore[attr-defined]
            btn.config(bg=COLORS["bg_card_hover"], fg=COLORS["text_primary"])
            indicator.config(bg=COLORS["bg_card_hover"])

    def on_leave(_e):
        if not btn._active:             # type: ignore[attr-defined]
            btn.config(bg=COLORS["bg_sidebar"], fg=COLORS["text_secondary"])
            indicator.config(bg=COLORS["bg_sidebar"])

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


def set_active_nav(buttons: Dict[str, tk.Button], active_key: str, accent: Optional[str] = None) -> None:
    accent = accent or COLORS["accent"]
    for key, btn in buttons.items():
        try:
            is_active = key == active_key
            btn._active = is_active     # type: ignore[attr-defined]
            if is_active:
                btn.config(bg=COLORS["bg_medium"], fg=accent)
                btn._indicator.config(bg=accent)    # type: ignore[attr-defined]
            else:
                btn.config(bg=COLORS["bg_sidebar"], fg=COLORS["text_secondary"])
                btn._indicator.config(bg=COLORS["bg_sidebar"])  # type: ignore[attr-defined]
        except tk.TclError:
            pass


# ── Page switching + history ──────────────────────────────────────────────────

class PageNavigator:
    """Builds pages off-screen and tracks back/forward history."""

    def __init__(self, root: tk.Tk, canvas: tk.Canvas, content: tk.Frame, window_id: int):
        self.root, self.canvas, self.content, self.window_id = root, canvas, content, window_id
        self.history: List[str] = []
        self.pos = -1
        self.back_btn: Optional[tk.Button] = None
        self.fwd_btn: Optional[tk.Button] = None

    def show(self, key: str, render: Callable[[], None], record: bool = True) -> None:
        if record and (self.pos < 0 or self.history[self.pos] != key):
            del self.history[self.pos + 1:]
            self.history.append(key)
            self.pos = len(self.history) - 1
        # Hide while rebuilding so the user never sees half-drawn pages.
        self.canvas.itemconfigure(self.window_id, state="hidden")
        self.canvas.yview_moveto(0)
        try:
            for w in self.content.winfo_children():
                w.destroy()
            render()
            self.root.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.canvas.yview_moveto(0)
        finally:
            self.canvas.itemconfigure(self.window_id, state="normal")
            self.refresh_buttons()

    def step(self, delta: int) -> Optional[str]:
        """Move through history; returns the key to display (or None if at an end)."""
        target = self.pos + delta
        if 0 <= target < len(self.history):
            self.pos = target
            return self.history[target]
        return None

    def refresh_buttons(self) -> None:
        for btn, ok in ((self.back_btn, self.pos > 0), (self.fwd_btn, self.pos < len(self.history) - 1)):
            if btn is not None:
                try:
                    btn.config(state="normal" if ok else "disabled",
                               fg=COLORS["text_primary"] if ok else COLORS["text_muted"],
                               cursor="hand2" if ok else "arrow")
                except tk.TclError:
                    pass


def install_header_controls(header: tk.Widget, title_label: tk.Widget, nav: PageNavigator,
                            on_back: Callable, on_forward: Callable) -> None:
    """Add ‹ › history buttons in front of the page title."""
    box = tk.Frame(header, bg=header.cget("bg"))
    box.pack(side="left", padx=(16, 0), before=title_label)

    def mk(text, cmd):
        b = tk.Button(box, text=text, font=("Segoe UI", 14), relief="flat", bd=0, width=2,
                      bg=COLORS["bg_medium"], fg=COLORS["text_muted"], activebackground=COLORS["bg_card_hover"],
                      activeforeground=COLORS["text_primary"], disabledforeground=COLORS["text_muted"],
                      command=cmd, state="disabled")
        b.pack(side="left", padx=(0, 4))
        return b

    nav.back_btn = mk("‹", on_back)
    nav.fwd_btn = mk("›", on_forward)
    nav.refresh_buttons()
    title_label.pack_configure(padx=(10, 24))


def install_shortcuts(root: tk.Tk, ordered_keys: List[str], go: Callable[[str], None],
                      on_back: Callable, on_forward: Callable) -> None:
    for i, key in enumerate(ordered_keys[:9], start=1):
        root.bind(f"<Control-Key-{i}>", lambda _e, k=key: go(k))
    root.bind("<Alt-Left>", lambda _e: on_back())
    root.bind("<Alt-Right>", lambda _e: on_forward())
    root.bind("<Control-r>", lambda _e: go(None))     # None = reload current page


# ── Middle Mouse Autoscroll (Chrome-Style) ───────────────────────────────────
import time


class Autoscroller:
    """
    Chrome-style autoscroll (pan-scroll) using the mouse scroll wheel (middle button).

    Supports:
      • Hold-and-drag: Press and hold scroll wheel (Button-2), swipe down or up to scroll.
        Speed scales dynamically with distance from anchor. Releasing the wheel stops scrolling.
      • Click-and-move: Click scroll wheel once to enter autoscroll mode, move mouse to steer
        speed, click any mouse button or press any key to stop.
      • Floating circular anchor marker positioned at the middle-click coordinate with arrows.
      • Distance-proportional velocity curve with a gentle reading deadband and fast swipe acceleration.
      • 60 FPS sub-pixel smooth animation loop with zero jitter.
    """

    DEADZONE = 8
    MAX_SPEED = 320.0

    def __init__(self, root: tk.Tk, canvas: tk.Canvas, content: tk.Frame):
        self.root = root
        self.canvas = canvas
        self.content = content
        self.active = False
        self.toggle_mode = False
        self.origin_x = 0
        self.origin_y = 0
        self.current_y = 0
        self.press_time = 0.0
        self.dragged = False
        self.speed = 0.0
        self.subpixel = 0.0
        self.tick_job: Optional[str] = None
        self.target_widget: Optional[tk.Widget] = None
        self.marker: Optional[tk.Toplevel] = None
        self._cur_cursor = ""

        # Bind scroll wheel (middle button / Button-2)
        root.bind_all("<ButtonPress-2>", self.on_press, add="+")
        root.bind_all("<B2-Motion>", self.on_drag, add="+")
        root.bind_all("<ButtonRelease-2>", self.on_release, add="+")
        root.bind_all("<Motion>", self.on_motion, add="+")
        root.bind_all("<ButtonPress-1>", self.on_interrupt_click, add="+")
        root.bind_all("<ButtonPress-3>", self.on_interrupt_click, add="+")
        root.bind_all("<KeyPress>", self.on_key, add="+")
        root.bind_all("<FocusOut>", self.on_focus_out, add="+")

    def _find_scroll_target(self, widget: Optional[tk.Misc]) -> tk.Widget:
        w = widget
        while w is not None and w is not self.root:
            if isinstance(w, (tk.Text, tk.Listbox)):
                return w
            if isinstance(w, tk.Canvas) and w is not self.canvas:
                try:
                    first, last = w.yview()
                    if (first, last) != (0.0, 1.0):
                        return w
                except tk.TclError:
                    pass
            w = getattr(w, "master", None)
        return self.canvas

    def on_press(self, event):
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Misc):
            return
        try:
            if widget.winfo_toplevel() is not self.root:
                return  # Don't hijack dialogs
        except tk.TclError:
            return

        # If already active in toggle mode, clicking Button-2 stops it
        if self.active and self.toggle_mode:
            self.stop()
            return "break"

        self.active = True
        self.toggle_mode = False
        self.origin_x = event.x_root
        self.origin_y = event.y_root
        self.current_y = event.y_root
        self.press_time = time.monotonic()
        self.dragged = False
        self.speed = 0.0
        self.subpixel = 0.0
        self.target_widget = self._find_scroll_target(widget)

        self._show_marker(self.origin_x, self.origin_y)
        self._update_cursor("sb_v_double_arrow")
        self._start_tick()
        return "break"

    def on_drag(self, event):
        if not self.active:
            return
        self.current_y = event.y_root
        dy = self.current_y - self.origin_y
        if abs(dy) > 5:
            self.dragged = True
        self._update_speed(dy)
        return "break"

    def on_release(self, event):
        if not self.active:
            return
        elapsed = time.monotonic() - self.press_time
        dy = event.y_root - self.origin_y

        # If user held down and dragged/swiped, releasing Button-2 immediately stops
        if self.dragged or elapsed > 0.35 or abs(dy) > self.DEADZONE:
            self.stop()
        else:
            # Clicked quickly without moving -> enter Chrome-style toggle mode
            self.toggle_mode = True
        return "break"

    def on_motion(self, event):
        if not self.active or not self.toggle_mode:
            return
        self.current_y = event.y_root
        dy = self.current_y - self.origin_y
        self._update_speed(dy)
        return "break"

    def on_interrupt_click(self, _event=None):
        if self.active and self.toggle_mode:
            self.stop()
            return "break"

    def on_key(self, _event=None):
        if self.active:
            self.stop()
            return "break"

    def on_focus_out(self, _event=None):
        if self.active:
            self.stop()

    def _update_speed(self, dy: float):
        abs_dy = abs(dy)
        if abs_dy <= self.DEADZONE:
            self.speed = 0.0
            self._update_cursor("sb_v_double_arrow")
        else:
            dist = abs_dy - self.DEADZONE
            # Distance-proportional fast acceleration curve:
            # 20px drag: ~5 px/frame
            # 80px drag: ~32 px/frame
            # 160px drag: ~84 px/frame (blazing fast swipe)
            # 300px+ drag: ~235 px/frame
            spd = (dist * 0.28) + ((dist / 22.0) ** 1.95)
            if spd > self.MAX_SPEED:
                spd = self.MAX_SPEED
            self.speed = spd if dy > 0 else -spd
            self._update_cursor("sb_down_arrow" if dy > 0 else "sb_up_arrow")

    def _start_tick(self):
        if self.tick_job is None:
            self._tick()

    def _tick(self):
        self.tick_job = None
        if not self.active:
            return

        try:
            if not self.canvas.winfo_exists():
                self.stop()
                return
        except tk.TclError:
            self.stop()
            return

        if abs(self.speed) > 0.001:
            target = self.target_widget if (self.target_widget and self.target_widget.winfo_exists()) else self.canvas
            if isinstance(target, (tk.Text, tk.Listbox)):
                self.subpixel += (self.speed / 18.0)
            else:
                self.subpixel += self.speed

            step = int(self.subpixel)
            if step != 0:
                self.subpixel -= step
                try:
                    target.yview_scroll(step, "units")
                except tk.TclError:
                    pass

        try:
            self.tick_job = self.root.after(16, self._tick)
        except tk.TclError:
            pass

    def _show_marker(self, x: int, y: int):
        self._hide_marker()
        try:
            top = tk.Toplevel(self.root)
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            top.geometry(f"34x34+{x - 17}+{y - 17}")
            mc = tk.Canvas(top, width=34, height=34, bg=COLORS.get("bg_dark", "#161b22"), highlightthickness=0)
            mc.pack(fill="both", expand=True)

            accent = COLORS.get("accent", "#58a6ff")
            text_col = COLORS.get("text_primary", "#ffffff")
            bg_med = COLORS.get("bg_medium", "#21262d")

            mc.create_oval(2, 2, 32, 32, fill=bg_med, outline=accent, width=2)
            mc.create_polygon(17, 6, 12, 12, 22, 12, fill=text_col)
            mc.create_oval(15, 15, 19, 19, fill=accent, outline="")
            mc.create_polygon(17, 28, 12, 22, 22, 22, fill=text_col)

            # Delegate mouse clicks/drags directly over the marker window
            mc.bind("<ButtonPress-1>", self.on_interrupt_click)
            mc.bind("<ButtonPress-2>", self.on_press)
            mc.bind("<ButtonPress-3>", self.on_interrupt_click)
            mc.bind("<B2-Motion>", self.on_drag)
            mc.bind("<ButtonRelease-2>", self.on_release)
            mc.bind("<Motion>", self.on_motion)

            self.marker = top
        except Exception:
            self.marker = None

    def _hide_marker(self):
        if self.marker is not None:
            try:
                self.marker.destroy()
            except Exception:
                pass
            self.marker = None

    def _update_cursor(self, cursor: str):
        if self._cur_cursor == cursor:
            return
        self._cur_cursor = cursor
        try:
            self.root.config(cursor=cursor)
            if self.canvas and self.canvas.winfo_exists():
                self.canvas.config(cursor=cursor)
        except tk.TclError:
            pass

    def _restore_cursor(self):
        self._cur_cursor = ""
        try:
            self.root.config(cursor="")
            if self.canvas and self.canvas.winfo_exists():
                self.canvas.config(cursor="")
        except tk.TclError:
            pass

    def stop(self):
        self.active = False
        self.toggle_mode = False
        self.speed = 0.0
        if self.tick_job is not None:
            try:
                self.root.after_cancel(self.tick_job)
            except tk.TclError:
                pass
            self.tick_job = None
        self._hide_marker()
        self._restore_cursor()


# ── Smooth scrolling ──────────────────────────────────────────────────────────

def install_smooth_scroll(root: tk.Tk, canvas: tk.Canvas, content: tk.Frame) -> Autoscroller:
    """Instant, buttery-smooth mousewheel, touchpad scrolling and Chrome-style
    middle mouse hold-and-drag autoscroll with distance-based speed scaling.
    Zero-lag, responsive, and handles nested scroll areas cleanly."""
    try:
        canvas.configure(yscrollincrement=1)
    except tk.TclError:
        pass

    def nested_scroll_widget(widget) -> Optional[tk.Widget]:
        w = widget
        while w is not None and w is not root:
            if isinstance(w, (tk.Text, tk.Listbox)):
                try:
                    first, last = w.yview()
                    if (first, last) != (0.0, 1.0):
                        return w
                except tk.TclError:
                    pass
            elif isinstance(w, tk.Canvas) and w is not canvas:
                try:
                    first, last = w.yview()
                    if (first, last) != (0.0, 1.0):
                        return w
                except tk.TclError:
                    pass
            w = getattr(w, "master", None)
        return None

    def on_wheel(event):
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Misc):
            return
        try:
            if widget.winfo_toplevel() is not root:
                return  # Dialogs handle their own scrolling
        except tk.TclError:
            return

        inner = nested_scroll_widget(widget)
        if inner is not None:
            try:
                first, last = inner.yview()
                can_scroll_down = (event.delta < 0) and (last < 0.999)
                can_scroll_up = (event.delta > 0) and (first > 0.001)
                if can_scroll_down or can_scroll_up:
                    if isinstance(inner, tk.Canvas):
                        delta = event.delta
                        pixels = int(-(delta / 120.0) * 55) if abs(delta) >= 120 else (-1 if delta > 0 else 1) * 40
                        inner.yview_scroll(pixels, "units")
                    else:
                        steps = int(-event.delta / 120) * 3 if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
                        inner.yview_scroll(steps, "units")
                    return "break"
            except tk.TclError:
                pass

        delta = event.delta
        if not delta:
            return

        # 75 pixels per standard wheel notch feels snappy and buttery smooth
        if abs(delta) >= 120:
            pixels = int(-(delta / 120.0) * 75)
        else:
            pixels = int(-delta * 0.75)
            if pixels == 0:
                pixels = -1 if delta > 0 else 1

        try:
            canvas.yview_scroll(pixels, "units")
        except tk.TclError:
            pass
        return "break"

    def on_wheel_up(event):
        widget = getattr(event, "widget", None)
        inner = nested_scroll_widget(widget) if isinstance(widget, tk.Misc) else None
        if inner is not None:
            try:
                first, _ = inner.yview()
                if first > 0.001:
                    inner.yview_scroll(-3, "units")
                    return "break"
            except tk.TclError:
                pass
        try:
            canvas.yview_scroll(-75, "units")
        except tk.TclError:
            pass
        return "break"

    def on_wheel_down(event):
        widget = getattr(event, "widget", None)
        inner = nested_scroll_widget(widget) if isinstance(widget, tk.Misc) else None
        if inner is not None:
            try:
                _, last = inner.yview()
                if last < 0.999:
                    inner.yview_scroll(3, "units")
                    return "break"
            except tk.TclError:
                pass
        try:
            canvas.yview_scroll(75, "units")
        except tk.TclError:
            pass
        return "break"


    root.bind_all("<MouseWheel>", on_wheel, add="+")
    root.bind_all("<Button-4>", on_wheel_up, add="+")
    root.bind_all("<Button-5>", on_wheel_down, add="+")

    # Install Chrome-style autoscroll handler
    scroller = Autoscroller(root, canvas, content)
    canvas._autoscroller = scroller  # type: ignore[attr-defined]
    return scroller
