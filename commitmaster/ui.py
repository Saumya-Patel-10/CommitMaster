"""UI layer: Windows notifications + a modern commit preview dialog (tkinter).

Design goals:
  • Dark-mode inspired palette with accent greens — feels premium, not 1998.
  • AI messages stream in asynchronously; the dialog shows a spinner while
    Bionic is thinking, then replaces placeholders once AI responds.
  • All tkinter code runs on a single dedicated UI thread (not the main thread
    and not the monitor thread) to avoid cross-thread corruption.
  • Every dialog is a true Toplevel so it doesn't block other windows.
"""
import concurrent.futures
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

from commitmaster.commit_engine import GROUP_LABELS
from commitmaster.logger import get

log = get("ui")

# ── Palette ───────────────────────────────────────────────────────────────────
# Dark slate background, GitHub-green accent, clean whites.
C = {
    "bg":          "#1e2330",   # main background
    "bg2":         "#252b3b",   # card / frame background
    "bg3":         "#2d3548",   # slightly lighter
    "border":      "#3a4460",   # card border
    "accent":      "#3fb950",   # GitHub green
    "accent_dark": "#2ea44f",   # button hover
    "text":        "#e6edf3",   # primary text
    "text2":       "#8b949e",   # secondary / muted text
    "warn_bg":     "#3d2f00",   # warning card bg
    "warn_fg":     "#f0a62e",   # warning text
    "err_fg":      "#f85149",   # error text
    "entry_bg":    "#161b27",   # text-entry background
    "entry_fg":    "#e6edf3",
    "entry_sel":   "#3fb950",
    "btn_bg":      "#3fb950",
    "btn_fg":      "#0d1117",
    "btn2_bg":     "#3a4460",
    "btn2_fg":     "#e6edf3",
}

GROUP_ICONS = {
    "feat":  "✨",
    "code":  "🔧",
    "test":  "🧪",
    "docs":  "📝",
    "chore": "⚙️",
}


# ── Notification ──────────────────────────────────────────────────────────────

def notify(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="CommitMaster", timeout=10)
    except Exception as exc:
        log.debug("plyer notification failed: %s", exc)
        print(f"[CommitMaster] {title}: {message}")


# ── Thread management ─────────────────────────────────────────────────────────
# All tkinter work is funnelled through a single dedicated UI thread.

_ui_queue: queue.Queue = queue.Queue()
_ui_thread: Optional[threading.Thread] = None
_ui_started = threading.Event()


def _ui_worker() -> None:
    """Runs forever on its own thread, executing callables from _ui_queue."""
    _ui_started.set()
    while True:
        try:
            fn = _ui_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        if fn is None:
            break
        try:
            fn()
        except Exception as exc:
            log.error("UI callback raised: %s", exc, exc_info=True)


def _ensure_ui_thread() -> None:
    global _ui_thread
    if _ui_thread is None or not _ui_thread.is_alive():
        _ui_thread = threading.Thread(target=_ui_worker, daemon=True, name="ui-thread")
        _ui_thread.start()
        _ui_started.wait(timeout=2)


def run_in_ui_thread(fn) -> None:
    """Schedule fn() to run on the dedicated UI thread."""
    _ensure_ui_thread()
    _ui_queue.put(fn)


# ── Helper: build a root window (hidden) ──────────────────────────────────────

def _make_root() -> tk.Tk:
    root = tk.Tk()
    root.withdraw()
    root.configure(bg=C["bg"])
    try:
        root.iconbitmap(default="")   # suppress default Tk feather icon
    except Exception:
        pass
    return root


def _style_window(win: tk.Toplevel) -> None:
    win.configure(bg=C["bg"])
    try:
        win.attributes("-alpha", 0.0)
        win.after(10, lambda: win.attributes("-alpha", 1.0))
    except Exception:
        pass


def _center(win: tk.Toplevel) -> None:
    win.update_idletasks()
    w = win.winfo_reqwidth()
    h = win.winfo_reqheight()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")


def _label(parent, text, fg=None, bg=None, font_size=10, bold=False, **kw):
    f = ("Segoe UI", font_size, "bold" if bold else "normal")
    return tk.Label(parent, text=text, fg=fg or C["text"], bg=bg or C["bg"],
                    font=f, **kw)


def _button(parent, text, command, accent=True, **kw):
    bg = C["btn_bg"] if accent else C["btn2_bg"]
    fg = C["btn_fg"] if accent else C["btn2_fg"]
    btn = tk.Button(parent, text=text, command=command,
                    bg=bg, fg=fg, activebackground=C["accent_dark"],
                    activeforeground=C["btn_fg"],
                    relief="flat", padx=16, pady=6,
                    font=("Segoe UI", 10, "bold"),
                    cursor="hand2", bd=0, **kw)
    btn.bind("<Enter>", lambda e: btn.config(bg=C["accent_dark"] if accent else "#4a5470"))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg))
    return btn


# ── Public dialog functions (each blocks until the dialog closes) ─────────────

def ask_done_coding() -> bool:
    """'Hey, done coding for today?' — returns True/False."""
    result = {"value": False}
    done_evt = threading.Event()

    def _show():
        root = _make_root()
        win = tk.Toplevel(root)
        win.title("CommitMaster")
        _style_window(win)
        win.resizable(False, False)
        win.lift()
        win.attributes("-topmost", True)

        outer = tk.Frame(win, bg=C["bg"], padx=28, pady=22)
        outer.pack(fill="both", expand=True)

        # Header
        tk.Label(outer, text="💾  CommitMaster", fg=C["accent"],
                 bg=C["bg"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Frame(outer, bg=C["border"], height=1).pack(fill="x", pady=(8, 16))

        _label(outer, "Hey, are you done coding for today?",
               font_size=12, bold=True).pack(anchor="w")
        _label(outer, "I'll check your repos for uncommitted changes.",
               fg=C["text2"], font_size=10).pack(anchor="w", pady=(4, 20))

        btn_row = tk.Frame(outer, bg=C["bg"])
        btn_row.pack(fill="x")

        def _yes():
            result["value"] = True
            win.destroy()
            root.destroy()
            done_evt.set()

        def _no():
            win.destroy()
            root.destroy()
            done_evt.set()

        _button(btn_row, "✔  Yes, commit my work", _yes).pack(side="left", padx=(0, 8))
        _button(btn_row, "Not yet", _no, accent=False).pack(side="left")

        win.protocol("WM_DELETE_WINDOW", _no)
        _center(win)
        root.mainloop()

    run_in_ui_thread(_show)
    done_evt.wait()
    return result["value"]


def pick_repos(repos: List[str]) -> List[str]:
    """Show a multi-select list of dirty repos.  Returns the chosen ones."""
    if not repos:
        return []

    chosen: List[str] = []
    done_evt = threading.Event()

    def _show():
        root = _make_root()
        win = tk.Toplevel(root)
        win.title("CommitMaster — Select Repositories")
        _style_window(win)
        win.minsize(480, 320)

        outer = tk.Frame(win, bg=C["bg"], padx=20, pady=16)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="💾  CommitMaster", fg=C["accent"],
                 bg=C["bg"], font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Frame(outer, bg=C["border"], height=1).pack(fill="x", pady=(6, 12))

        _label(outer, "Repositories with uncommitted changes:", bold=True).pack(anchor="w")
        _label(outer, "Select all you want to commit (hold Ctrl for multiple):",
               fg=C["text2"]).pack(anchor="w", pady=(2, 8))

        # Listbox
        frame = tk.Frame(outer, bg=C["bg2"], bd=0, highlightthickness=1,
                         highlightbackground=C["border"])
        frame.pack(fill="both", expand=True, pady=(0, 12))

        lb = tk.Listbox(
            frame,
            selectmode=tk.EXTENDED,
            bg=C["bg2"], fg=C["text"],
            selectbackground=C["accent"], selectforeground=C["bg"],
            activestyle="none",
            font=("Consolas", 10),
            relief="flat", bd=0,
            highlightthickness=0,
        )
        sb = tk.Scrollbar(frame, orient="vertical", command=lb.yview,
                          bg=C["bg3"], troughcolor=C["bg2"])
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)

        from commitmaster.commit_engine import repo_name as _rn
        for repo in repos:
            lb.insert(tk.END, f"  📁  {_rn(repo)}   ({repo})")
        lb.selection_set(0, tk.END)   # select all by default

        def _commit():
            sel = lb.curselection()
            chosen.extend(repos[i] for i in sel)
            win.destroy()
            root.destroy()
            done_evt.set()

        def _cancel():
            win.destroy()
            root.destroy()
            done_evt.set()

        btn_row = tk.Frame(outer, bg=C["bg"])
        btn_row.pack(fill="x")
        _button(btn_row, "✔  Commit selected", _commit).pack(side="left", padx=(0, 8))
        _button(btn_row, "Skip", _cancel, accent=False).pack(side="left")

        win.protocol("WM_DELETE_WINDOW", _cancel)
        _center(win)
        root.mainloop()

    run_in_ui_thread(_show)
    done_evt.wait()
    return chosen


def preview_and_commit(
    repo_name: str,
    branch: str,
    groups: Dict[str, List[str]],
    ai_future: Optional[concurrent.futures.Future] = None,
) -> Optional[tuple]:
    """
    Show the commit preview dialog.
    - groups:    {group_name: [file_paths]}  (sensitive excluded from edit)
    - ai_future: a Future[dict] that resolves to {group: message}.
                 While pending, the entry boxes show "⏳ AI is thinking…" and
                 update automatically when the future completes.
    Returns ("commit", {group: message}) or None if cancelled.
    """
    result = {"action": None}
    done_evt = threading.Event()

    def _show():
        root = _make_root()
        win = tk.Toplevel(root)
        win.title(f"CommitMaster — {repo_name}  ({branch})")
        _style_window(win)
        win.geometry("820x600")
        win.minsize(700, 480)

        sensitive_files = groups.get("sensitive", [])
        commit_groups = [(g, f) for g, f in groups.items() if g != "sensitive"]

        # ── Header ───────────────────────────────────────────────────────────
        header = tk.Frame(win, bg=C["bg2"], padx=16, pady=12)
        header.pack(fill="x")

        tk.Label(header, text="💾  CommitMaster", fg=C["accent"],
                 bg=C["bg2"], font=("Segoe UI", 13, "bold")).pack(side="left")
        info_text = f"  ·  {repo_name}   •   {branch}"
        tk.Label(header, text=info_text, fg=C["text2"],
                 bg=C["bg2"], font=("Segoe UI", 11)).pack(side="left")

        # AI status badge (top-right)
        ai_badge = tk.Label(
            header, text="⏳ AI generating…", fg=C["warn_fg"],
            bg=C["bg2"], font=("Segoe UI", 9),
        )
        if ai_future is not None:
            ai_badge.pack(side="right")

        tk.Frame(win, bg=C["border"], height=1).pack(fill="x")

        # ── Scrollable body ───────────────────────────────────────────────────
        body_outer = tk.Frame(win, bg=C["bg"])
        body_outer.pack(fill="both", expand=True, padx=16, pady=12)

        canvas = tk.Canvas(body_outer, bg=C["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(body_outer, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=C["bg"])

        canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ── Group cards ───────────────────────────────────────────────────────
        entries: Dict[str, tk.Entry] = {}

        for group, files in commit_groups:
            icon = GROUP_ICONS.get(group, "•")
            label_text = GROUP_LABELS.get(group, group.title())

            card = tk.Frame(body, bg=C["bg2"], bd=0,
                            highlightthickness=1, highlightbackground=C["border"])
            card.pack(fill="x", pady=6)

            # Card header
            card_hdr = tk.Frame(card, bg=C["bg3"], padx=10, pady=8)
            card_hdr.pack(fill="x")
            tk.Label(card_hdr,
                     text=f"  {icon}  {label_text}",
                     fg=C["accent"], bg=C["bg3"],
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            tk.Label(card_hdr,
                     text=f"{len(files)} file{'s' if len(files) != 1 else ''}",
                     fg=C["text2"], bg=C["bg3"],
                     font=("Segoe UI", 9)).pack(side="right")

            # File list (capped at 10)
            file_frame = tk.Frame(card, bg=C["bg2"], padx=14, pady=4)
            file_frame.pack(fill="x")
            for f in files[:10]:
                tk.Label(file_frame, text=f"  {f}",
                         fg=C["text2"], bg=C["bg2"],
                         font=("Consolas", 9), anchor="w").pack(fill="x")
            if len(files) > 10:
                tk.Label(file_frame, text=f"  … and {len(files) - 10} more",
                         fg=C["text2"], bg=C["bg2"],
                         font=("Segoe UI", 9, "italic"), anchor="w").pack(fill="x")

            # Commit message entry
            entry_frame = tk.Frame(card, bg=C["bg2"], padx=10, pady=8)
            entry_frame.pack(fill="x")
            tk.Label(entry_frame, text="Commit message:",
                     fg=C["text2"], bg=C["bg2"],
                     font=("Segoe UI", 9)).pack(anchor="w")

            entry_var = tk.StringVar(value="⏳  AI is generating commit message…")
            entry = tk.Entry(
                entry_frame,
                textvariable=entry_var,
                bg=C["entry_bg"], fg=C["text"],
                insertbackground=C["accent"],
                font=("Consolas", 10),
                relief="flat", bd=6,
                highlightthickness=1,
                highlightbackground=C["border"],
                highlightcolor=C["accent"],
            )
            entry.pack(fill="x", pady=(4, 0))
            entries[group] = entry

        # Sensitive files warning
        if sensitive_files:
            warn_card = tk.Frame(body, bg=C["warn_bg"], bd=0,
                                 highlightthickness=1, highlightbackground=C["warn_fg"],
                                 padx=12, pady=10)
            warn_card.pack(fill="x", pady=6)
            tk.Label(warn_card,
                     text="⚠   Sensitive files — NOT staged (handle manually if intended):",
                     fg=C["warn_fg"], bg=C["warn_bg"],
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
            for sf in sensitive_files:
                tk.Label(warn_card, text=f"  {sf}",
                         fg=C["warn_fg"], bg=C["warn_bg"],
                         font=("Consolas", 9)).pack(anchor="w")

        # ── Footer buttons ────────────────────────────────────────────────────
        tk.Frame(win, bg=C["border"], height=1).pack(fill="x")
        footer = tk.Frame(win, bg=C["bg2"], padx=16, pady=10)
        footer.pack(fill="x")

        def _commit():
            messages = {g: e.get().strip() for g, e in entries.items()
                        if e.get().strip() and not e.get().startswith("⏳")}
            result["action"] = ("commit", messages)
            canvas.unbind_all("<MouseWheel>")
            win.destroy()
            root.destroy()
            done_evt.set()

        def _cancel():
            canvas.unbind_all("<MouseWheel>")
            win.destroy()
            root.destroy()
            done_evt.set()

        _button(footer, "✔  Commit All", _commit).pack(side="left", padx=(0, 8))
        _button(footer, "✎  Edit & Commit", _commit, accent=False).pack(side="left", padx=(0, 8))
        _button(footer, "✖  Cancel", _cancel, accent=False).pack(side="right")

        win.protocol("WM_DELETE_WINDOW", _cancel)
        _center(win)

        # ── AI future watcher ─────────────────────────────────────────────────
        if ai_future is not None:
            def _poll_ai():
                if ai_future.done():
                    try:
                        ai_msgs = ai_future.result()
                        for group, entry in entries.items():
                            msg = ai_msgs.get(group, "")
                            if msg:
                                entry.delete(0, tk.END)
                                entry.insert(0, msg)
                        ai_badge.config(text="✅ AI messages ready", fg=C["accent"])
                        log.debug("AI messages injected into preview dialog.")
                    except Exception as exc:
                        log.error("AI future raised: %s", exc)
                        ai_badge.config(text="⚠ AI unavailable (fallback used)", fg=C["warn_fg"])
                        for group, entry in entries.items():
                            if entry.get().startswith("⏳"):
                                from commitmaster.ai_messages import FALLBACK_MESSAGES
                                entry.delete(0, tk.END)
                                entry.insert(0, FALLBACK_MESSAGES.get(group, "chore: update files"))
                else:
                    win.after(400, _poll_ai)   # check again in 400 ms

            win.after(200, _poll_ai)
        else:
            # No AI future — fill with fallbacks immediately
            from commitmaster.ai_messages import FALLBACK_MESSAGES
            for group, entry in entries.items():
                entry.delete(0, tk.END)
                entry.insert(0, FALLBACK_MESSAGES.get(group, "chore: update files"))

        root.mainloop()

    run_in_ui_thread(_show)
    done_evt.wait()
    return result["action"]


def show_info(message: str) -> None:
    done = threading.Event()

    def _show():
        root = _make_root()
        _modern_dialog(root, "ℹ  CommitMaster", message, C["accent"])
        root.mainloop()
        done.set()

    run_in_ui_thread(_show)
    done.wait()


def show_error(message: str) -> None:
    done = threading.Event()

    def _show():
        root = _make_root()
        _modern_dialog(root, "⚠  CommitMaster — Error", message, C["err_fg"])
        root.mainloop()
        done.set()

    run_in_ui_thread(_show)
    done.wait()


def _modern_dialog(root: tk.Tk, title: str, message: str, accent_color: str) -> None:
    win = tk.Toplevel(root)
    win.title("CommitMaster")
    _style_window(win)
    win.resizable(False, False)
    win.lift()
    win.attributes("-topmost", True)

    outer = tk.Frame(win, bg=C["bg"], padx=24, pady=20)
    outer.pack(fill="both", expand=True)

    tk.Label(outer, text=title, fg=accent_color, bg=C["bg"],
             font=("Segoe UI", 11, "bold")).pack(anchor="w")
    tk.Frame(outer, bg=C["border"], height=1).pack(fill="x", pady=(6, 12))
    tk.Label(outer, text=message, fg=C["text"], bg=C["bg"],
             font=("Segoe UI", 10), justify="left", wraplength=420).pack(anchor="w")

    def _close():
        win.destroy()
        root.destroy()

    tk.Frame(outer, bg=C["bg"], height=12).pack()
    _button(outer, "OK", _close).pack(anchor="e")
    win.protocol("WM_DELETE_WINDOW", _close)
    _center(win)


def ask_push_confirmation(
    repo_name: str,
    branch: str,
    account_info: Optional[Dict] = None,
    commits: Optional[List[Dict]] = None,
) -> bool:
    """Prompt user with explicit confirmation before pushing commits to GitHub."""
    result = {"confirmed": False}
    done_evt = threading.Event()

    def _show():
        root = _make_root()
        win = tk.Toplevel(root)
        win.title("CommitMaster — Confirm GitHub Push")
        _style_window(win)
        win.geometry("540x440")
        win.minsize(480, 360)
        win.attributes("-topmost", True)

        outer = tk.Frame(win, bg=C["bg"], padx=20, pady=16)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="🚀  Push to GitHub?", fg=C["accent"],
                 bg=C["bg"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Frame(outer, bg=C["border"], height=1).pack(fill="x", pady=(6, 12))

        # Details Card
        card = tk.Frame(outer, bg=C["bg2"], bd=0, highlightthickness=1,
                        highlightbackground=C["border"], padx=14, pady=10)
        card.pack(fill="x", pady=(0, 10))

        tk.Label(card, text=f"Repository:  {repo_name}", fg=C["text"],
                 bg=C["bg2"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(card, text=f"Branch:        {branch}", fg=C["text2"],
                 bg=C["bg2"], font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

        if account_info:
            uname = account_info.get("github_username", "")
            aname = account_info.get("account_name", "")
            tk.Label(card, text=f"GitHub Account: @{uname} ({aname})", fg=C["accent"],
                     bg=C["bg2"], font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 0))

        # Commits preview
        tk.Label(outer, text="Commits ready to push:", fg=C["text2"],
                 bg=C["bg"], font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 4))

        commits_frame = tk.Frame(outer, bg=C["bg2"], highlightthickness=1,
                                 highlightbackground=C["border"], padx=8, pady=8)
        commits_frame.pack(fill="both", expand=True, pady=(0, 12))

        if commits:
            for c in commits[:5]:
                h = c.get("hash", "")
                m = c.get("message", "")
                row = tk.Frame(commits_frame, bg=C["bg2"])
                row.pack(fill="x", pady=1)
                tk.Label(row, text=f"● {h}", fg=C["accent"], bg=C["bg2"],
                         font=("Consolas", 9, "bold")).pack(side="left")
                tk.Label(row, text=f"  {m}", fg=C["text"], bg=C["bg2"],
                         font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)
            if len(commits) > 5:
                tk.Label(commits_frame, text=f"  ... and {len(commits) - 5} more commit(s)",
                         fg=C["text2"], bg=C["bg2"], font=("Segoe UI", 8, "italic")).pack(anchor="w")
        else:
            tk.Label(commits_frame, text="Recent commits will be published to remote repository.",
                     fg=C["text2"], bg=C["bg2"], font=("Segoe UI", 9)).pack(anchor="w")

        # Buttons
        btn_row = tk.Frame(outer, bg=C["bg"])
        btn_row.pack(fill="x")

        def _yes():
            result["confirmed"] = True
            win.destroy()
            root.destroy()
            done_evt.set()

        def _no():
            result["confirmed"] = False
            win.destroy()
            root.destroy()
            done_evt.set()

        _button(btn_row, "🚀  Yes, Push to GitHub", _yes).pack(side="left", padx=(0, 8))
        _button(btn_row, "❌  Keep Local (Don't Push)", _no, accent=False).pack(side="left")

        win.protocol("WM_DELETE_WINDOW", _no)
        _center(win)
        root.mainloop()

    run_in_ui_thread(_show)
    done_evt.wait()
    return result["confirmed"]