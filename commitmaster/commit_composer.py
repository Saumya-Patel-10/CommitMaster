"""Commit composer - a GitHub-Desktop-style Summary + Description editor shared by the
User Dashboard, Admin Portal and Admin App.

Key guarantees
  • Only files that are currently *selected* (and still modified) are ever used - for AI
    generation, validation, inspection and committing.  Stale selections from earlier
    scans are pruned by `sync_selection`.
  • Default strategy is one commit per file, each with its own Summary + Description.
"""
import os
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Dict, List, Optional, Tuple

from commitmaster import ai_messages, commit_engine, file_inspector, ui
from commitmaster import database as db
from commitmaster.app_styles import COLORS, FONTS

COMMIT_BTN = "#3a56b0"
COMMIT_BTN_HOVER = "#4a69cc"
SUMMARY_LIMIT = 72
STATUS_COLORS = {"M": "#f0883e", "MM": "#f0883e", "A": "#3fb950", "AM": "#3fb950", "D": "#f85149",
                 "??": "#58a6ff", "R": "#bc8cff", "U": "#f85149"}


# ══════════════════════════════════════════════════════════════════════════════
# Shared selection state (lives on the host window: UserDashboard / AdminApp)
# ══════════════════════════════════════════════════════════════════════════════

def ensure_state(host) -> None:
    """Create the composer attributes on the host window if they do not exist yet."""
    if not hasattr(host, "_gd_drafts"):
        host._gd_drafts = {}                       # {path: {"summary": str, "description": str}}
    if not hasattr(host, "_gd_unified"):
        host._gd_unified = {"summary": "", "description": ""}
    if not hasattr(host, "_gd_composer"):
        host._gd_composer = None
    # Individual commits are the default workflow
    if not getattr(host, "_gd_mode_initialised", False):
        host._gd_commit_mode_var.set("individual")
        host._gd_mode_initialised = True


def sync_selection(host, changes: List[Tuple[str, str]], sensitive_patterns: List[str]) -> None:
    """
    Reconcile checkbox / draft state with the files that are modified *right now*.
    Files that were committed or reverted since the last scan are dropped so they can
    never leak into a new selection, AI request or commit.
    """
    ensure_state(host)
    current = [p for _, p in changes]
    live = set(current)

    for stale in [p for p in host._gd_staged_vars if p not in live]:
        del host._gd_staged_vars[stale]
    for stale in [p for p in host._gd_drafts if p not in live]:
        del host._gd_drafts[stale]
    for legacy in ("_gd_file_comments", "_gd_file_comment_vars"):
        d = getattr(host, legacy, None)
        if isinstance(d, dict):
            for stale in [p for p in d if p not in live]:
                del d[stale]

    for _, path in changes:
        if path not in host._gd_staged_vars:
            sensitive = any(s in path.lower() for s in sensitive_patterns)
            var = tk.BooleanVar(value=not sensitive)
            var.trace_add("write", lambda *_a, h=host: _selection_changed(h))
            host._gd_staged_vars[path] = var
    host._gd_changes = changes


def reset_state(host) -> None:
    """Forget every selection / draft (used when the user switches repository)."""
    ensure_state(host)
    host._gd_staged_vars.clear()
    host._gd_drafts.clear()
    host._gd_unified = {"summary": "", "description": ""}
    host._gd_changes = []


def selected_paths(host) -> List[str]:
    """Selected files, in display order, restricted to files that are still modified."""
    return [p for _, p in host._gd_changes
            if p in host._gd_staged_vars and host._gd_staged_vars[p].get()]


def _selection_changed(host) -> None:
    comp = getattr(host, "_gd_composer", None)
    try:
        if comp is not None and comp.winfo_exists():
            comp.schedule_refresh()
    except tk.TclError:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Small widgets
# ══════════════════════════════════════════════════════════════════════════════

class PlaceholderEntry(tk.Entry):
    def __init__(self, parent, placeholder: str, **kw):
        super().__init__(parent, **kw)
        self._placeholder = placeholder
        self._normal_fg = kw.get("fg", COLORS["text_primary"])
        self._showing = False
        self.bind("<FocusIn>", lambda e: self._hide())
        self.bind("<FocusOut>", lambda e: self._show_if_empty())
        self._show_if_empty()

    def _show_if_empty(self):
        if not tk.Entry.get(self):
            self._showing = True
            self.insert(0, self._placeholder)
            self.config(fg=COLORS["text_muted"])

    def _hide(self):
        if self._showing:
            self.delete(0, "end")
            self.config(fg=self._normal_fg)
            self._showing = False

    def value(self) -> str:
        return "" if self._showing else tk.Entry.get(self).strip()

    def set_value(self, text: str):
        self._hide()
        self.delete(0, "end")
        self.insert(0, text or "")
        self.config(fg=self._normal_fg)
        self._showing = False
        if not text:
            self._show_if_empty()


class PlaceholderText(tk.Text):
    def __init__(self, parent, placeholder: str, **kw):
        super().__init__(parent, **kw)
        self._placeholder = placeholder
        self._normal_fg = kw.get("fg", COLORS["text_primary"])
        self._showing = False
        self.bind("<FocusIn>", lambda e: self._hide())
        self.bind("<FocusOut>", lambda e: self._show_if_empty())
        self._show_if_empty()

    def _show_if_empty(self):
        if not self.get("1.0", "end").strip():
            self._showing = True
            self.delete("1.0", "end")
            self.insert("1.0", self._placeholder)
            self.config(fg=COLORS["text_muted"])

    def _hide(self):
        if self._showing:
            self.delete("1.0", "end")
            self.config(fg=self._normal_fg)
            self._showing = False

    def value(self) -> str:
        return "" if self._showing else self.get("1.0", "end").strip()

    def set_value(self, text: str):
        self._hide()
        self.delete("1.0", "end")
        self.insert("1.0", text or "")
        self.config(fg=self._normal_fg)
        self._showing = False
        if not text:
            self._show_if_empty()


def _icon_button(parent, text, command, tip: str = "") -> tk.Button:
    b = tk.Button(parent, text=text, command=command, font=("Segoe UI", 11), fg=COLORS["text_secondary"],
                  bg=COLORS["bg_input"], activebackground=COLORS["bg_card_hover"],
                  activeforeground=COLORS["text_primary"], relief="flat", bd=0, cursor="hand2", padx=6, pady=1)
    b.bind("<Enter>", lambda e: b.config(fg=COLORS["text_primary"]))
    b.bind("<Leave>", lambda e: b.config(fg=COLORS["text_secondary"]))
    return b


# ══════════════════════════════════════════════════════════════════════════════
# The composer
# ══════════════════════════════════════════════════════════════════════════════

class CommitComposer(tk.Frame):
    """
    host     - window object holding the _gd_* state (UserDashboard / AdminApp)
    on_done  - called (on the UI thread) after a successful commit so the page can rescan
    """

    def __init__(self, parent, host, cfg: dict, on_done):
        super().__init__(parent, bg=COLORS["bg_card"])
        ensure_state(host)
        self.host, self.cfg, self.on_done = host, cfg, on_done
        self._fields: Dict[str, Tuple[PlaceholderEntry, PlaceholderText]] = {}
        self._refresh_job = None
        self._busy = False

        # toolbar -----------------------------------------------------------
        bar = tk.Frame(self, bg=COLORS["bg_card"])
        bar.pack(fill="x", pady=(0, 10))
        tk.Label(bar, text="Commit as", font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"]).pack(side="left", padx=(0, 8))
        seg = tk.Frame(bar, bg=COLORS["border"], padx=1, pady=1)
        seg.pack(side="left")
        for text, value in (("📝  One commit per file", "individual"), ("📦  Single commit", "all")):
            tk.Radiobutton(seg, text=text, value=value, variable=host._gd_commit_mode_var, indicatoron=False,
                           font=FONTS["body_sm"], fg=COLORS["text_primary"], bg=COLORS["bg_input"],
                           selectcolor=COLORS["accent"], activebackground=COLORS["bg_card_hover"],
                           activeforeground=COLORS["text_primary"], relief="flat", bd=0, padx=12, pady=5,
                           cursor="hand2", command=self.render_body).pack(side="left")

        self.gen_btn = tk.Button(bar, text="✨ Generate with AI", font=FONTS["label_bold"], fg="white",
                                 bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                                 activeforeground="white", relief="flat", bd=0, cursor="hand2", padx=14, pady=5,
                                 command=self.generate)
        self.gen_btn.pack(side="right")
        self.ai_status = tk.Label(bar, text="", font=FONTS["caption"], fg=COLORS["text_secondary"],
                                  bg=COLORS["bg_card"])
        self.ai_status.pack(side="right", padx=(0, 12))

        # body --------------------------------------------------------------
        self.body = tk.Frame(self, bg=COLORS["bg_card"])
        self.body.pack(fill="x")

        # footer ------------------------------------------------------------
        self.footer = tk.Frame(self, bg=COLORS["bg_card"])
        self.footer.pack(fill="x", pady=(10, 0))
        self._build_footer()

        host._gd_composer = self
        self.render_body(harvest=False)

    # ── helpers ───────────────────────────────────────────────────────────────
    @property
    def repo(self) -> str:
        return self.host._gd_selected_repo

    def _mode(self) -> str:
        return self.host._gd_commit_mode_var.get()

    def schedule_refresh(self) -> None:
        """Debounced re-render after the file selection changes."""
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
        self._refresh_job = self.after(40, self.render_body)

    def _status_of(self, path: str) -> str:
        for st, p in self.host._gd_changes:
            if p == path:
                return st
        return "M"

    # ── body rendering ────────────────────────────────────────────────────────
    def _harvest(self) -> None:
        """Copy what the user typed into the drafts before widgets are rebuilt."""
        for key, (entry, text) in list(self._fields.items()):
            try:
                data = {"summary": entry.value(), "description": text.value()}
            except tk.TclError:
                continue
            if key == "__all__":
                self.host._gd_unified = data
            else:
                self.host._gd_drafts[key] = data

    def render_body(self, harvest: bool = True) -> None:
        self._refresh_job = None
        if harvest:
            self._harvest()
        self._fields = {}
        for w in self.body.winfo_children():
            w.destroy()

        sel = selected_paths(self.host)
        if not sel:
            tk.Label(self.body, text="Select at least one file in the list above to write its commit message.",
                     font=FONTS["body_sm"], fg=COLORS["text_muted"], bg=COLORS["bg_card"],
                     pady=18).pack(anchor="w")
        elif self._mode() == "individual":
            tk.Label(self.body, text=f"{len(sel)} file{'s' if len(sel) != 1 else ''} selected - each gets its own "
                                     "commit with its own Summary and Description.",
                     font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w",
                                                                                                    pady=(0, 6))
            for path in sel:
                self._file_block(path)
        else:
            tk.Label(self.body, text=f"All {len(sel)} selected file{'s' if len(sel) != 1 else ''} go into one commit.",
                     font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w",
                                                                                                    pady=(0, 6))
            self._composer_box(self.body, "__all__", self.host._gd_unified, header=None, height=7)
        self._update_commit_button()

    def _file_block(self, path: str) -> None:
        block = tk.Frame(self.body, bg=COLORS["bg_card"], highlightthickness=1,
                         highlightbackground=COLORS["border"])
        block.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(block, bg=COLORS["bg_card"], padx=12, pady=10)
        inner.pack(fill="x")

        hdr = tk.Frame(inner, bg=COLORS["bg_card"])
        hdr.pack(fill="x", pady=(0, 8))
        st = self._status_of(path)
        tk.Label(hdr, text=f" {st if st != '??' else 'U'} ", font=FONTS["mono_sm"], fg="#0d1117",
                 bg=STATUS_COLORS.get(st, "#8b949e")).pack(side="left")
        tk.Label(hdr, text=path, font=FONTS["label_bold"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(side="left", padx=(8, 0))
        try:
            n_iss = len(file_inspector.inspect_file(self.repo, path))
        except Exception:
            n_iss = 0
        if n_iss:
            tk.Label(hdr, text=f" 🛡 {n_iss} issue{'s' if n_iss != 1 else ''} ", font=FONTS["caption"],
                     fg="white", bg="#9e6a03").pack(side="right")

        self._composer_box(inner, path, self.host._gd_drafts.get(path, {}), header=path, height=4)

    def _composer_box(self, parent, key: str, draft: Dict[str, str], header: Optional[str], height: int) -> None:
        """The GitHub-Desktop-like pair of fields: [avatar][Summary (required)] + Description."""
        row = tk.Frame(parent, bg=COLORS["bg_card"])
        row.pack(fill="x")
        self._avatar(row).pack(side="left", padx=(0, 10), anchor="n")

        right = tk.Frame(row, bg=COLORS["bg_card"])
        right.pack(side="left", fill="x", expand=True)

        sum_wrap = tk.Frame(right, bg=COLORS["bg_input"], highlightthickness=1,
                            highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"])
        sum_wrap.pack(fill="x")
        entry = PlaceholderEntry(sum_wrap, "Summary (required)", font=FONTS["body_md"], bg=COLORS["bg_input"],
                                 fg=COLORS["text_primary"], relief="flat", insertbackground=COLORS["text_primary"])
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(8, 0))
        counter = tk.Label(sum_wrap, text="0", font=FONTS["caption"], fg=COLORS["text_muted"], bg=COLORS["bg_input"],
                           padx=8)
        counter.pack(side="right")

        def update_counter(_e=None):
            n = len(entry.value())
            counter.config(text=str(n), fg=COLORS["error"] if n > SUMMARY_LIMIT else COLORS["text_muted"])
        entry.bind("<KeyRelease>", update_counter)

        desc_wrap = tk.Frame(right, bg=COLORS["bg_input"], highlightthickness=1,
                             highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"])
        desc_wrap.pack(fill="x", pady=(8, 0))
        text = PlaceholderText(desc_wrap, "Description", font=FONTS["body_sm"], height=height, wrap="word",
                               bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat", padx=8, pady=6,
                               insertbackground=COLORS["text_primary"], undo=True)
        text.pack(fill="x")

        tools = tk.Frame(desc_wrap, bg=COLORS["bg_input"])
        tools.pack(fill="x", padx=4, pady=(0, 3))
        _icon_button(tools, "👤+", lambda k=key: self._add_coauthor(k)).pack(side="left")
        tk.Frame(tools, width=1, bg=COLORS["border"]).pack(side="left", fill="y", pady=3, padx=2)
        _icon_button(tools, "✨", lambda k=key: self.generate(only=None if k == "__all__" else [k])
                     ).pack(side="left")
        tk.Frame(tools, width=1, bg=COLORS["border"]).pack(side="left", fill="y", pady=3, padx=2)
        _icon_button(tools, "⚙", self._open_settings).pack(side="left")

        entry.set_value(draft.get("summary", ""))
        text.set_value(draft.get("description", ""))
        update_counter()
        self._fields[key] = (entry, text)

    def _avatar(self, parent) -> tk.Canvas:
        user = getattr(self.host, "user", {}) or {}
        color = user.get("avatar_color") or COLORS["accent"]
        name = user.get("full_name") or user.get("username") or "?"
        parts = name.split()
        initials = (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()
        c = tk.Canvas(parent, width=34, height=34, bg=COLORS["bg_card"], highlightthickness=0)
        c.create_oval(2, 2, 32, 32, fill=color, outline="")
        c.create_text(17, 17, text=initials, fill="white", font=("Segoe UI", 10, "bold"))
        return c

    def _add_coauthor(self, key: str) -> None:
        raw = simpledialog.askstring("Add co-author", "Co-author as  Name <email@example.com>:",
                                     parent=self.winfo_toplevel())
        if not raw or "<" not in raw:
            return
        entry, text = self._fields[key]
        current = text.value()
        text.set_value((current + "\n\n" if current else "") + f"Co-authored-by: {raw.strip()}")

    def _open_settings(self) -> None:
        try:
            self.host._nav_to("settings")
        except Exception:
            pass

    # ── footer ────────────────────────────────────────────────────────────────
    def _build_footer(self) -> None:
        host = self.host
        top = tk.Frame(self.footer, bg=COLORS["bg_card"])
        top.pack(fill="x", pady=(0, 8))
        tk.Checkbutton(top, text="Ask me before pushing", variable=host._gd_ask_push_var, font=FONTS["body_sm"],
                       fg=COLORS["text_primary"], bg=COLORS["bg_card"], selectcolor=COLORS["bg_input"],
                       activebackground=COLORS["bg_card"], activeforeground=COLORS["text_primary"]
                       ).pack(side="left")

        self.commit_btn = tk.Button(self.footer, font=FONTS["label_bold"], fg="white", bg=COMMIT_BTN,
                                    activebackground=COMMIT_BTN_HOVER, activeforeground="white", relief="flat",
                                    bd=0, cursor="hand2", pady=9, command=lambda: self.commit(push=False))
        self.commit_btn.pack(fill="x")
        self.commit_btn.bind("<Enter>", lambda e: self.commit_btn.config(bg=COMMIT_BTN_HOVER))
        self.commit_btn.bind("<Leave>", lambda e: self.commit_btn.config(bg=COMMIT_BTN))

        row = tk.Frame(self.footer, bg=COLORS["bg_card"])
        row.pack(fill="x", pady=(6, 0))
        self.push_commit_btn = tk.Button(row, text="🚀 Commit & push to GitHub", font=FONTS["label_bold"],
                                         fg=COLORS["text_primary"], bg=COLORS["bg_medium"],
                                         activebackground=COLORS["bg_card_hover"],
                                         activeforeground=COLORS["text_primary"], relief="flat", bd=0,
                                         cursor="hand2", padx=14, pady=6, command=lambda: self.commit(push=True))
        self.push_commit_btn.pack(side="left", padx=(0, 8))
        self.push_btn = tk.Button(row, text="⬆ Push existing commits", font=FONTS["label"],
                                  fg=COLORS["text_secondary"], bg=COLORS["bg_card"],
                                  activebackground=COLORS["bg_medium"], activeforeground=COLORS["text_primary"],
                                  relief="flat", bd=0, cursor="hand2", padx=10, pady=6, command=self.push_only)
        self.push_btn.pack(side="left")
        self.result_lbl = tk.Label(self.footer, text="", font=FONTS["label_bold"], bg=COLORS["bg_card"],
                                   anchor="w", justify="left", wraplength=760)
        self.result_lbl.pack(fill="x", pady=(8, 0))

    def _update_commit_button(self) -> None:
        sel = selected_paths(self.host)
        branch = commit_engine.current_branch(self.repo) if self.repo else "main"
        if self._mode() == "individual" and len(sel) > 1:
            label = f"Commit {len(sel)} files separately to "
        elif len(sel) > 1:
            label = f"Commit {len(sel)} files to "
        else:
            label = "Commit to "
        self.commit_btn.config(text=f"{label}{branch}")
        state = "normal" if sel and not self._busy else "disabled"
        for b in (self.commit_btn, self.push_commit_btn):
            b.config(state=state)

    def _say(self, text: str, color: Optional[str] = None) -> None:
        if self.winfo_exists():
            self.result_lbl.config(text=text, fg=color or COLORS["text_secondary"])

    # ── AI generation ─────────────────────────────────────────────────────────
    def generate(self, only: Optional[List[str]] = None) -> None:
        sel = selected_paths(self.host)
        files = [f for f in (only or sel) if f in sel] or sel
        if not files:
            messagebox.showinfo("No files selected", "Select at least one modified file first.",
                                parent=self.winfo_toplevel())
            return
        if self._busy:
            return
        self._harvest()
        self._busy = True
        self.gen_btn.config(state="disabled")
        self.ai_status.config(text=f"⏳ Reading {len(files)} file diff{'s' if len(files) != 1 else ''}...",
                              fg=COLORS["info"])
        root = self.winfo_toplevel()
        repo = self.repo
        is_full_selection = set(files) == set(sel)

        def progress(i, n, f):
            root.after(0, lambda: self.winfo_exists() and self.ai_status.config(
                text=f"⏳ Analysing {os.path.basename(f)} ({i + 1}/{n})...", fg=COLORS["info"]))

        def worker():
            try:
                res = ai_messages.generate_file_comments(self.cfg, repo, files, progress=progress)
                err = None
            except Exception as exc:                      # pragma: no cover - defensive
                res, err = None, exc
            root.after(0, lambda: self._apply_generated(res, err, files, is_full_selection))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_generated(self, res, err, files: List[str], is_full_selection: bool) -> None:
        self._busy = False
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self.gen_btn.config(state="normal")
        if err or not res:
            self.ai_status.config(text=f"❌ Could not generate: {err}", fg=COLORS["error"])
            self._update_commit_button()
            return
        still_selected = set(selected_paths(self.host))
        for f in files:
            if f in still_selected:
                self.host._gd_drafts[f] = {
                    "summary": res["file_comments"].get(f, ""),
                    "description": res["file_descriptions"].get(f, ""),
                }
        if is_full_selection:
            self.host._gd_unified = {"summary": res.get("headline", ""), "description": res.get("description", "")}
        db.log_event(self.host.user["id"], "ai_generate", repo_name=commit_engine.repo_name(self.repo),
                     files=len(files))
        self.ai_status.config(text=f"✔ Written for {len(files)} file{'s' if len(files) != 1 else ''} - "
                                   "review and edit before committing", fg=COLORS["success"])
        self.render_body(harvest=False)

    # ── commit / push ─────────────────────────────────────────────────────────
    def commit(self, push: bool) -> None:
        if self._busy:
            return
        host, root = self.host, self.winfo_toplevel()
        sel = selected_paths(host)
        if not sel:
            messagebox.showwarning("No files selected", "Check at least one file to commit.", parent=root)
            return
        self._harvest()
        mode = self._mode()

        # Summary is required ------------------------------------------------
        if mode == "individual":
            missing = [p for p in sel if not host._gd_drafts.get(p, {}).get("summary", "").strip()]
        else:
            missing = [] if host._gd_unified.get("summary", "").strip() else ["__all__"]
        if missing:
            names = "the commit" if missing == ["__all__"] else "\n  • " + "\n  • ".join(missing[:8])
            messagebox.showwarning("Summary required",
                                   f"Please write a Summary for {names}\n\nTip: press “✨ Generate with AI”.",
                                   parent=root)
            entry = self._fields.get(missing[0], (None, None))[0]
            if entry is not None:
                entry.focus_set()
            return

        repo = self.repo
        repo_name = commit_engine.repo_name(repo)

        # Pre-commit inspection (only the selected files) --------------------
        issues = file_inspector.inspect_files(repo, sel)
        db.log_scan(host.user["id"], repo, len(sel), file_inspector.summarize_issues(issues))
        if issues and not ui.ask_pre_commit_issues_warning(issues, repo_name=repo_name, parent=root, repo_path=repo):
            self._say("ℹ Commit cancelled so you can fix the reported issues.", COLORS["warning"])
            return

        acc = db.get_repo_account(host.user["id"], repo)
        if push and host._gd_ask_push_var.get():
            unpushed = commit_engine.get_unpushed_commits(repo)
            if not ui.ask_push_confirmation(repo_name, commit_engine.current_branch(repo), acc, unpushed):
                self._say("ℹ Push cancelled - nothing was committed.", COLORS["warning"])
                return

        # Build the messages on the UI thread, then commit in the background ---
        if mode == "individual":
            pairs = [(p, ai_messages.compose_commit_message(host._gd_drafts[p]["summary"],
                                                            host._gd_drafts[p].get("description", "")))
                     for p in sel]
            single_msg = None
        else:
            pairs = None
            u = host._gd_unified
            single_msg = ai_messages.compose_commit_message(u["summary"], u.get("description", ""))

        self._busy = True
        self._update_commit_button()
        self._say("⏳ Committing...", COLORS["info"])
        user_id = host.user["id"]

        def worker():
            committed: List[str] = []
            try:
                if pairs is not None:
                    results = commit_engine.stage_and_commit_individual(repo, pairs)
                    for item in results:
                        db.log_commit(user_id, repo, item["message"].splitlines()[0], 1, item["hash"])
                    summary = f"{len(results)} commit{'s' if len(results) != 1 else ''} created"
                else:
                    line = commit_engine.stage_and_commit(repo, sel, single_msg)
                    db.log_commit(user_id, repo, single_msg.splitlines()[0], len(sel), line.split()[0] if line else "")
                    summary = line
                committed = list(sel)
            except Exception as exc:
                partial = getattr(exc, "results", [])
                for item in partial:                      # commits that did go through
                    db.log_commit(user_id, repo, item["message"].splitlines()[0], 1, item["hash"])
                db.log_commit(user_id, repo, f"FAILED: {exc}", len(sel) - len(partial), status="failed")
                done_files = [item["file"] for item in partial]
                root.after(0, lambda e=exc, d=done_files: self._finish_error("Commit failed", e, d))
                return

            push_ok, push_msg = None, ""
            if push:
                push_ok, push_msg = self._do_push(repo, acc, user_id)
            root.after(0, lambda: self._finish_ok(summary, committed, push, push_ok, push_msg))

        threading.Thread(target=worker, daemon=True).start()

    def _do_push(self, repo: str, acc: Optional[dict], user_id: int) -> Tuple[bool, str]:
        if acc:
            ok, msg = commit_engine.push_repo_with_account(repo, acc)
        else:
            accounts = db.get_github_accounts(user_id)
            if accounts:
                ok, msg = commit_engine.push_repo_with_account(repo, accounts[0])
            else:
                ok, msg = commit_engine.push(repo)
        db.log_event(user_id, "push_ok" if ok else "push_failed", repo_name=commit_engine.repo_name(repo),
                     detail="" if ok else msg[:200])
        return ok, msg

    def _finish_error(self, title: str, err, done_files: Optional[List[str]] = None) -> None:
        self._busy = False
        for p in done_files or []:
            self.host._gd_drafts.pop(p, None)
        if not self.winfo_exists():
            return
        self._say(f"❌ {title}: {err}", COLORS["error"])
        messagebox.showerror(title, f"{err}", parent=self.winfo_toplevel())
        if done_files:
            self.on_done()          # some files were committed - rescan so the list is accurate
        else:
            self._update_commit_button()

    def _finish_ok(self, summary: str, committed: List[str], pushed: bool, push_ok, push_msg: str) -> None:
        self._busy = False
        host = self.host
        for p in committed:
            host._gd_drafts.pop(p, None)
            if p in host._gd_staged_vars:
                host._gd_staged_vars[p].set(False)
        host._gd_unified = {"summary": "", "description": ""}
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        root = self.winfo_toplevel()
        if pushed and push_ok is False:
            self._say(f"⚠ Committed locally ({summary}) but push failed: {push_msg}", COLORS["warning"])
            messagebox.showerror("Push failed", f"Commit succeeded locally, but git push failed:\n\n{push_msg}",
                                 parent=root)
        elif pushed:
            messagebox.showinfo("Committed & pushed", f"✔ {summary}\n\n{push_msg}", parent=root)
        else:
            self._say(f"✔ Committed locally: {summary}", COLORS["success"])
        self.on_done()

    def push_only(self) -> None:
        if self._busy:
            return
        host, root = self.host, self.winfo_toplevel()
        repo = self.repo
        repo_name = commit_engine.repo_name(repo)
        acc = db.get_repo_account(host.user["id"], repo)
        unpushed = commit_engine.get_unpushed_commits(repo)
        if host._gd_ask_push_var.get():
            if not ui.ask_push_confirmation(repo_name, commit_engine.current_branch(repo), acc, unpushed):
                self._say("ℹ Push cancelled. Commits remain saved locally.", COLORS["warning"])
                return
        self._busy = True
        self._say("⏳ Pushing...", COLORS["info"])
        user_id = host.user["id"]

        def worker():
            ok, msg = self._do_push(repo, acc, user_id)

            def done():
                self._busy = False
                if not self.winfo_exists():
                    return
                self._update_commit_button()
                if ok:
                    self._say(f"✔ {msg}", COLORS["success"])
                else:
                    self._say(f"❌ Push failed: {msg}", COLORS["error"])
                    messagebox.showerror("Push failed", msg, parent=root)
            root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()
