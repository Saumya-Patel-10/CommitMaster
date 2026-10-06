"""Reusable Tk widgets that render file_inspector issues with code snippets and fix advice."""
import os
import tkinter as tk
from typing import Any, Dict, List, Optional

SEVERITY_STYLE = {
    "error":    ("ERROR",    "#f85149"),
    "security": ("SECURITY", "#f0883e"),
    "warning":  ("WARNING",  "#d29922"),
}


def default_palette() -> Dict[str, str]:
    """Palette built from the live app theme (falls back to a dark theme)."""
    try:
        from commitmaster.app_styles import COLORS
        return {
            "bg": COLORS["bg_card"], "bg2": COLORS["bg_medium"], "code_bg": COLORS["bg_input"],
            "text": COLORS["text_primary"], "text2": COLORS["text_secondary"], "muted": COLORS["text_muted"],
            "border": COLORS["border"],
        }
    except Exception:
        return {"bg": "#161b22", "bg2": "#21262d", "code_bg": "#0d1117", "text": "#e6edf3",
                "text2": "#8b949e", "muted": "#6e7681", "border": "#30363d"}


def _copy_to_clipboard(widget: tk.Widget, text: str, button: Optional[tk.Button] = None) -> None:
    try:
        widget.clipboard_clear()
        widget.clipboard_append(text)
        widget.update()
        if button is not None:
            old = button.cget("text")
            button.config(text="✔ Copied")
            button.after(1400, lambda: button.winfo_exists() and button.config(text=old))
    except tk.TclError:
        pass


def issue_to_text(issue: Dict[str, Any]) -> str:
    lines = [f"[{issue.get('severity', '').upper()}] {issue.get('title') or issue.get('message')} "
             f"- {issue.get('file', '')}:{issue.get('line', 1)}"]
    for c in issue.get("context") or []:
        lines.append(f"  {'>' if c['hit'] else ' '} {c['line']:>4} | {c['text']}")
    if issue.get("explanation"):
        lines.append(f"Why it matters: {issue['explanation']}")
    if issue.get("fix"):
        lines.append(f"How to fix: {issue['fix']}")
    return "\n".join(lines)


def build_issue_card(parent: tk.Widget, issue: Dict[str, Any], pal: Optional[Dict[str, str]] = None,
                     repo_path: Optional[str] = None, show_file: bool = True, wrap: int = 640) -> tk.Frame:
    """One issue = header (severity, title, location) + code snippet + why + how to fix."""
    pal = pal or default_palette()
    sev_label, sev_color = SEVERITY_STYLE.get(issue.get("severity", "warning"), SEVERITY_STYLE["warning"])
    line_no = issue.get("line", 1)

    card = tk.Frame(parent, bg=pal["bg2"], highlightthickness=1, highlightbackground=pal["border"])
    inner = tk.Frame(card, bg=pal["bg2"], padx=12, pady=10)
    inner.pack(fill="x")

    # Header ----------------------------------------------------------------
    hdr = tk.Frame(inner, bg=pal["bg2"])
    hdr.pack(fill="x")
    tk.Label(hdr, text=f" {sev_label} ", fg="#ffffff", bg=sev_color,
             font=("Segoe UI", 8, "bold")).pack(side="left")
    tk.Label(hdr, text=issue.get("title") or issue.get("message", ""), fg=pal["text"], bg=pal["bg2"],
             font=("Segoe UI", 10, "bold")).pack(side="left", padx=(8, 0))
    if issue.get("reference"):
        tk.Label(hdr, text=issue["reference"], fg=pal["muted"], bg=pal["bg2"],
                 font=("Segoe UI", 8)).pack(side="right")

    loc = f"{issue.get('file', '')}:{line_no}" if show_file else f"Line {line_no}"
    tk.Label(inner, text=f"📍 {loc}", fg=pal["text2"], bg=pal["bg2"], font=("Consolas", 9),
             anchor="w").pack(fill="x", pady=(4, 6))

    # Code snippet ----------------------------------------------------------
    ctx = issue.get("context") or []
    if ctx:
        code = tk.Frame(inner, bg=pal["code_bg"], highlightthickness=1, highlightbackground=pal["border"])
        code.pack(fill="x", pady=(0, 8))
        num_w = max(len(str(c["line"])) for c in ctx)
        for c in ctx:
            hit = c["hit"]
            bg = "#4a1d1d" if hit else pal["code_bg"]
            fg = "#ffb4ac" if hit else pal["text2"]
            row = tk.Frame(code, bg=bg)
            row.pack(fill="x")
            tk.Label(row, text=("▶" if hit else " "), fg=sev_color, bg=bg,
                     font=("Consolas", 9, "bold"), width=2).pack(side="left")
            tk.Label(row, text=str(c["line"]).rjust(num_w), fg=pal["muted"] if not hit else "#ff7b72",
                     bg=bg, font=("Consolas", 9)).pack(side="left", padx=(0, 8))
            tk.Label(row, text=c["text"] if c["text"].strip() else " ", fg=fg, bg=bg,
                     font=("Consolas", 9), anchor="w", justify="left").pack(side="left", fill="x", expand=True)
    elif issue.get("snippet"):
        code = tk.Frame(inner, bg=pal["code_bg"], padx=8, pady=4,
                        highlightthickness=1, highlightbackground=pal["border"])
        code.pack(fill="x", pady=(0, 8))
        tk.Label(code, text=issue["snippet"], fg="#ffb4ac", bg=pal["code_bg"], font=("Consolas", 9),
                 anchor="w", justify="left").pack(fill="x")

    # Explanation -----------------------------------------------------------
    if issue.get("explanation"):
        tk.Label(inner, text="Why this matters", fg=pal["text"], bg=pal["bg2"],
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        tk.Label(inner, text=issue["explanation"], fg=pal["text2"], bg=pal["bg2"], font=("Segoe UI", 9),
                 wraplength=wrap, justify="left", anchor="w").pack(fill="x", pady=(1, 8))

    # Fix -------------------------------------------------------------------
    if issue.get("fix"):
        fix_box = tk.Frame(inner, bg="#12261a", highlightthickness=1, highlightbackground="#238636")
        fix_box.pack(fill="x")
        fb = tk.Frame(fix_box, bg="#12261a", padx=10, pady=8)
        fb.pack(fill="x")
        tk.Label(fb, text="💡 How to fix", fg="#56d364", bg="#12261a",
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        tk.Label(fb, text=issue["fix"], fg="#c9d1d9", bg="#12261a", font=("Consolas", 9) if "\n" in issue["fix"] and "    " in issue["fix"] else ("Segoe UI", 9),
                 wraplength=wrap - 20, justify="left", anchor="w").pack(fill="x", pady=(2, 0))

    # Actions ---------------------------------------------------------------
    actions = tk.Frame(inner, bg=pal["bg2"])
    actions.pack(fill="x", pady=(8, 0))
    copy_btn = tk.Button(actions, text="📋 Copy details", font=("Segoe UI", 8), fg=pal["text"], bg=pal["border"],
                         relief="flat", bd=0, padx=8, pady=2, cursor="hand2")
    copy_btn.config(command=lambda: _copy_to_clipboard(copy_btn, issue_to_text(issue), copy_btn))
    copy_btn.pack(side="left")
    if repo_path and issue.get("file"):
        full = os.path.join(repo_path, issue["file"])
        if os.path.exists(full):
            def _open():
                try:
                    os.startfile(full)  # type: ignore[attr-defined]
                except Exception:
                    pass
            tk.Button(actions, text="📂 Open file", font=("Segoe UI", 8), fg=pal["text"], bg=pal["border"],
                      relief="flat", bd=0, padx=8, pady=2, cursor="hand2", command=_open).pack(side="left", padx=(6, 0))
    tk.Label(actions, text="Intentional? add  # nosec  to the line to silence it.", fg=pal["muted"],
             bg=pal["bg2"], font=("Segoe UI", 8)).pack(side="right")
    return card


def build_issue_list(parent: tk.Widget, issues: List[Dict[str, Any]], pal: Optional[Dict[str, str]] = None,
                     repo_path: Optional[str] = None, show_file: bool = True, wrap: int = 640) -> None:
    for issue in issues:
        build_issue_card(parent, issue, pal, repo_path, show_file, wrap).pack(fill="x", pady=(0, 8))


def build_issues_panel(parent: tk.Widget, issues_by_file: Dict[str, List[Dict[str, Any]]],
                       repo_path: Optional[str] = None, bg: Optional[str] = None) -> Optional[tk.Frame]:
    """
    Compact banner ("N issues in M files") with a 'Show details' toggle that expands into full
    issue cards (code snippet, why, how to fix).  Returns None when there is nothing to show.
    """
    if not issues_by_file:
        return None
    from commitmaster.file_inspector import summarize_issues
    pal = default_palette()
    s = summarize_issues(issues_by_file)
    wrap = tk.Frame(parent, bg=pal["bg"])

    bar = tk.Frame(wrap, bg="#3d2f00", padx=12, pady=8, highlightthickness=1, highlightbackground="#d29922")
    bar.pack(fill="x")
    parts = []
    if s["security"]:
        parts.append(f"🛡 {s['security']} security")
    if s["errors"]:
        parts.append(f"❌ {s['errors']} error{'s' if s['errors'] != 1 else ''}")
    if s["warnings"]:
        parts.append(f"⚠ {s['warnings']} warning{'s' if s['warnings'] != 1 else ''}")
    tk.Label(bar, text=f"Pre-commit scan: {'  ·  '.join(parts)}  in {len(issues_by_file)} file"
                       f"{'s' if len(issues_by_file) != 1 else ''}",
             font=("Segoe UI", 10, "bold"), fg="#f0a62e", bg="#3d2f00").pack(side="left")

    details = tk.Frame(wrap, bg=pal["bg"])
    state = {"open": False}

    def _copy_vulnerability_log(btn_widget):
        from commitmaster.file_inspector import format_issue_report
        repo_name = os.path.basename(repo_path) if repo_path else ""
        report_text = format_issue_report(issues_by_file, repo_name=repo_name)
        _copy_to_clipboard(btn_widget, report_text, btn_widget)

    toggle = tk.Button(bar, text="Show details ▾", font=("Segoe UI", 9, "bold"), fg="#ffffff", bg="#9e6a03",
                       relief="flat", bd=0, cursor="hand2", padx=10, pady=2)

    copy_btn = tk.Button(bar, text="📋 Copy Vulnerability Log", font=("Segoe UI", 9, "bold"), fg="#ffffff",
                         bg="#8a3b14", activebackground="#a84718", activeforeground="#ffffff",
                         relief="flat", bd=0, cursor="hand2", padx=10, pady=2,
                         command=lambda: _copy_vulnerability_log(copy_btn))
    copy_btn.pack(side="right", padx=(0, 8))

    def _toggle():
        if state["open"]:
            details.pack_forget()
            toggle.config(text="Show details ▾")
        else:
            if not details.winfo_children():
                det_top = tk.Frame(details, bg=pal["bg"])
                det_top.pack(fill="x", pady=(6, 2))
                tk.Label(det_top, text="Flagged Pre-Commit Issues & Security Findings",
                         font=("Segoe UI", 10, "bold"), fg=pal["text"], bg=pal["bg"]).pack(side="left")
                det_copy = tk.Button(det_top, text="📋 Copy Entire Vulnerability Log", font=("Segoe UI", 8, "bold"),
                                     fg="#ffffff", bg="#8a3b14", relief="flat", bd=0, cursor="hand2", padx=8, pady=2,
                                     command=lambda: _copy_vulnerability_log(det_copy))
                det_copy.pack(side="right")

                for path, issues in issues_by_file.items():
                    tk.Label(details, text=f"📄 {path}", fg=pal["text"], bg=pal["bg"],
                             font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 4))
                    build_issue_list(details, issues, pal, repo_path, show_file=False, wrap=760)
            details.pack(fill="x", pady=(6, 0))
            toggle.config(text="Hide details ▴")
        state["open"] = not state["open"]

    toggle.config(command=_toggle)
    toggle.pack(side="right")
    return wrap
