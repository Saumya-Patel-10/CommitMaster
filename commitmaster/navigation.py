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


# ── Smooth scrolling ──────────────────────────────────────────────────────────

def install_smooth_scroll(root: tk.Tk, canvas: tk.Canvas, content: tk.Frame) -> None:
    """Instant, buttery-smooth mousewheel and touchpad scrolling.
    Zero-lag, responsive, and handles nested scroll areas cleanly."""
    try:
        canvas.configure(yscrollincrement=1)
    except tk.TclError:
        pass

    def nested_scroll_widget(widget) -> Optional[tk.Widget]:
        w = widget
        while w is not None and w is not root:
            if isinstance(w, (tk.Text, tk.Listbox)):
                return w
            if isinstance(w, tk.Canvas) and w is not canvas:
                try:
                    first, last = w.yview()
                    if (first, last) != (0.0, 1.0):
                        return w
                except tk.TclError:
                    pass
            w = getattr(w, "master", None)
        return None

    def on_wheel(event):
        widget = event.widget
        if not isinstance(widget, tk.Misc):
            return
        try:
            if widget.winfo_toplevel() is not root:
                return  # Dialogs handle their own scrolling
        except tk.TclError:
            return

        inner = nested_scroll_widget(widget)
        if inner is not None:
            # Let inner widget scroll cleanly
            steps = int(-event.delta / 120) * 3 if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
            try:
                inner.yview_scroll(steps, "units")
            except tk.TclError:
                pass
            return "break"

        delta = event.delta
        if not delta:
            return

        # 45 pixels per standard wheel notch feels perfectly responsive and buttery smooth
        if abs(delta) >= 120:
            pixels = int(-(delta / 120.0) * 45)
        else:
            pixels = int(-delta * 0.45)
            if pixels == 0:
                pixels = -1 if delta > 0 else 1

        try:
            canvas.yview_scroll(pixels, "units")
        except tk.TclError:
            pass
        return "break"

    def on_wheel_up(_event):
        try:
            canvas.yview_scroll(-45, "units")
        except tk.TclError:
            pass
        return "break"

    def on_wheel_down(_event):
        try:
            canvas.yview_scroll(45, "units")
        except tk.TclError:
            pass
        return "break"

    root.bind_all("<MouseWheel>", on_wheel)
    root.bind_all("<Button-4>", on_wheel_up)
    root.bind_all("<Button-5>", on_wheel_down)
