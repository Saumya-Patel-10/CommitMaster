"""Live panel for a running git operation (replaces the indefinite "Committing...").

It only *reads* ``GitOperation.snapshot()`` (thread-safe) on the Tk thread via
``after()``; it never touches git. Every number shown comes from real git output:
the percentage appears only when git printed one, otherwise the bar is
indeterminate. Elapsed time and "no output for N s" come from monotonic clocks.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from commitmaster import git_ops
from commitmaster.app_styles import COLORS, FONTS

_COMMIT_ONLY = ("preparing", "checking", "staging", "committing", "verifying")
_PUSH_ONLY = ("preparing", "checking", "authenticating", "connecting", "uploading", "verifying")
_ALL = tuple(key for key, _ in git_ops.STAGES)
_STALL_WARN_SECONDS = 20


def _steps_for(op: git_ops.GitOperation):
    keys = {"commit": _COMMIT_ONLY, "push": _PUSH_ONLY}.get(op.kind, _ALL)
    out = []
    for key in keys:
        label = git_ops.STAGE_LABELS[key]
        if key == "verifying" and op.kind == "commit":
            label = "Verifying repository state"
        out.append((key, label))
    return out


def format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


class OperationPanel(tk.Frame):
    def __init__(self, parent, op: git_ops.GitOperation,
                 on_finished: Optional[Callable[[git_ops.GitOperation], None]] = None,
                 on_dismiss: Optional[Callable[[], None]] = None):
        super().__init__(parent, bg=COLORS["bg_input"], highlightthickness=1, highlightbackground=COLORS["border"])
        self.op = op
        self.on_finished = on_finished
        self.on_dismiss = on_dismiss
        self._steps = _steps_for(op)
        self._step_labels = {}
        self._job = None
        self._finished_called = False
        self._log_visible = False
        self._last_log_len = -1

        head = tk.Frame(self, bg=COLORS["bg_input"])
        head.pack(fill="x", padx=12, pady=(10, 4))
        self.title = tk.Label(head, text="Working...", font=FONTS["label_bold"], fg=COLORS["text_primary"],
                              bg=COLORS["bg_input"], anchor="w")
        self.title.pack(side="left")
        self.elapsed = tk.Label(head, text="0:00", font=FONTS["caption"], fg=COLORS["text_secondary"],
                                bg=COLORS["bg_input"])
        self.elapsed.pack(side="right")

        self.detail = tk.Label(self, text="", font=FONTS["caption"], fg=COLORS["text_secondary"],
                               bg=COLORS["bg_input"], anchor="w", justify="left", wraplength=720)
        self.detail.pack(fill="x", padx=12)

        steps = tk.Frame(self, bg=COLORS["bg_input"])
        steps.pack(fill="x", padx=12, pady=(6, 2))
        for key, label in self._steps:
            lbl = tk.Label(steps, text=f"○  {label}", font=FONTS["body_sm"], fg=COLORS["text_muted"],
                           bg=COLORS["bg_input"], anchor="w")
            lbl.pack(fill="x")
            self._step_labels[key] = (lbl, label)

        self.bar = ttk.Progressbar(self, mode="indeterminate", length=300)
        self.bar.pack(fill="x", padx=12, pady=(6, 2))
        self.bar.start(60)
        self._determinate = False
        self.progress_lbl = tk.Label(self, text="", font=FONTS["caption"], fg=COLORS["text_secondary"],
                                     bg=COLORS["bg_input"], anchor="w")
        self.progress_lbl.pack(fill="x", padx=12)

        self.warn = tk.Label(self, text="", font=FONTS["caption"], fg=COLORS["warning"], bg=COLORS["bg_input"],
                             anchor="w", justify="left", wraplength=720)
        self.warn.pack(fill="x", padx=12)

        self.result = tk.Label(self, text="", font=FONTS["body_sm"], bg=COLORS["bg_input"], anchor="w",
                               justify="left", wraplength=720)
        self.result.pack(fill="x", padx=12, pady=(4, 0))

        buttons = tk.Frame(self, bg=COLORS["bg_input"])
        buttons.pack(fill="x", padx=12, pady=(8, 10))
        self.cancel_btn = tk.Button(buttons, text="Cancel", font=FONTS["label"], fg=COLORS["text_primary"],
                                    bg=COLORS["bg_medium"], relief="flat", bd=0, padx=12, pady=4,
                                    cursor="hand2", command=self._cancel)
        self.cancel_btn.pack(side="left")
        self.log_btn = tk.Button(buttons, text="Show details", font=FONTS["label"], fg=COLORS["text_secondary"],
                                 bg=COLORS["bg_input"], relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                                 command=self._toggle_log)
        self.log_btn.pack(side="left", padx=(8, 0))
        self.copy_btn = tk.Button(buttons, text="Copy log", font=FONTS["label"], fg=COLORS["text_secondary"],
                                  bg=COLORS["bg_input"], relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                                  command=self._copy_log)
        self.copy_btn.pack(side="left")
        self.close_btn = tk.Button(buttons, text="Dismiss", font=FONTS["label"], fg=COLORS["text_primary"],
                                   bg=COLORS["bg_medium"], relief="flat", bd=0, padx=12, pady=4, cursor="hand2",
                                   command=self.dismiss)

        self.log_frame = tk.Frame(self, bg=COLORS["bg_input"])
        self.log_text = tk.Text(self.log_frame, height=10, wrap="word", font=("Consolas", 9), bg=COLORS["bg_card"],
                                fg=COLORS["text_secondary"], relief="flat", state="disabled")
        scroll = tk.Scrollbar(self.log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)

        self._tick()

    # -- user actions ---------------------------------------------------------
    def _cancel(self) -> None:
        self.op.cancel()
        self.cancel_btn.config(state="disabled", text="Cancelling...")

    def _toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.log_frame.pack(fill="both", padx=12, pady=(0, 10))
            self.log_btn.config(text="Hide details")
            self._last_log_len = -1
            self._refresh_log()
        else:
            self.log_frame.pack_forget()
            self.log_btn.config(text="Show details")

    def _copy_log(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self.op.log_text())
            self.copy_btn.config(text="Copied")
            self.after(1500, lambda: self.winfo_exists() and self.copy_btn.config(text="Copy log"))
        except tk.TclError:
            pass

    def dismiss(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
        if self.on_dismiss and self.op.finished:
            try:
                self.on_dismiss()
            except Exception:
                pass
        self.destroy()

    # -- rendering ------------------------------------------------------------
    def _refresh_log(self) -> None:
        text = self.op.log_text()
        if len(text) == self._last_log_len:
            return
        self._last_log_len = len(text)
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _tick(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        snap = self.op.snapshot()
        self.elapsed.config(text=format_elapsed(snap["elapsed"]))
        finished = self.op.finished
        keys = [k for k, _ in self._steps]
        current = snap["stage"] if snap["stage"] in keys else None
        cur_index = keys.index(current) if current else -1

        for i, key in enumerate(keys):
            lbl, label = self._step_labels[key]
            if finished:
                reached = i <= cur_index
                failed_here = snap["state"] in (git_ops.FAILED, git_ops.CANCELLED) and i == cur_index
                if failed_here:
                    lbl.config(text=f"✖  {label}", fg=COLORS["error"])
                elif reached or snap["state"] in (git_ops.SUCCEEDED,):
                    lbl.config(text=f"✔  {label}", fg=COLORS["success"])
                elif snap["state"] == git_ops.COMMITTED_NOT_PUSHED and i < cur_index:
                    lbl.config(text=f"✔  {label}", fg=COLORS["success"])
                else:
                    lbl.config(text=f"○  {label}", fg=COLORS["text_muted"])
            elif i < cur_index:
                lbl.config(text=f"✔  {label}", fg=COLORS["success"])
            elif i == cur_index:
                lbl.config(text=f"▶  {label}", fg=COLORS["text_primary"])
            else:
                lbl.config(text=f"○  {label}", fg=COLORS["text_muted"])

        if not finished:
            self.title.config(text=snap["stage_label"] + ("..." if not snap["cancel_requested"] else " (cancelling)"))
            self.detail.config(text=snap["detail"])
            prog = snap["progress"]
            if prog:
                if not self._determinate:
                    self.bar.stop()
                    self.bar.config(mode="determinate", maximum=100)
                    self._determinate = True
                self.bar["value"] = prog["percent"]
                self.progress_lbl.config(text=f"{prog['label']}: {prog['percent']}% ({prog['current']}/{prog['total']})")
            else:
                if self._determinate:
                    self.bar.config(mode="indeterminate")
                    self.bar.start(60)
                    self._determinate = False
                self.progress_lbl.config(text="")
            if snap["idle"] > _STALL_WARN_SECONDS:
                self.warn.config(text=(f"No output from git for {int(snap['idle'])} s. A repository hook or the "
                                       "network may be waiting. You can cancel safely; local work is kept."))
            else:
                self.warn.config(text="")
        else:
            self._render_final(snap)

        if self._log_visible:
            self._refresh_log()

        if finished:
            if not self._finished_called:
                self._finished_called = True
                if self.on_finished:
                    try:
                        self.on_finished(self.op)
                    except Exception:
                        pass
            return
        self._job = self.after(200, self._tick)

    def _render_final(self, snap) -> None:
        self.bar.stop()
        self.bar.pack_forget()
        self.progress_lbl.pack_forget()
        self.warn.config(text="")
        self.cancel_btn.pack_forget()
        self.close_btn.pack(side="right")
        state = snap["state"]
        lines = []
        commit = snap["commit_state"]
        if commit == "done":
            lines.append(("✔ Local commit created: " + (snap["commit_summary"] or ""), COLORS["success"]))
        elif commit == "failed":
            lines.append(("✖ No commit was created. Your files are unchanged.", COLORS["error"]))
        push = snap["push_state"]
        if push == "success":
            lines.append(("✔ Pushed and verified on the remote.", COLORS["success"]))
        elif push == "no_remote_update":
            lines.append(("✔ The remote already had these commits (nothing to upload).", COLORS["success"]))
        elif push == "failed":
            lines.append(("⚠ Not pushed. Your commit is saved locally.", COLORS["warning"]))
        elif push == "uncertain":
            lines.append(("⚠ Push result is uncertain. Check the remote before pushing again.", COLORS["warning"]))
        elif push == "cancelled":
            lines.append(("ℹ Push cancelled. Your commit is saved locally.", COLORS["warning"]))
        if state == git_ops.CANCELLED:
            lines.append(("ℹ Cancelled. No work was discarded.", COLORS["warning"]))
        fs = snap["final_state"]
        if fs and fs.get("upstream") is not None and fs.get("ahead") is not None:
            lines.append((f"{fs.get('branch') or 'HEAD'} → {fs['upstream']}: ahead {fs['ahead']}, behind {fs.get('behind', 0)}",
                          COLORS["text_secondary"]))
        if snap["error"] and state != git_ops.SUCCEEDED:
            lines.append((snap["error"], COLORS["error"] if state == git_ops.FAILED else COLORS["text_secondary"]))
        titles = {
            git_ops.SUCCEEDED: ("Done", COLORS["success"]),
            git_ops.COMMITTED_NOT_PUSHED: ("Committed locally, not pushed", COLORS["warning"]),
            git_ops.FAILED: ("Failed", COLORS["error"]),
            git_ops.CANCELLED: ("Cancelled", COLORS["warning"]),
        }
        title, color = titles.get(state, (state, COLORS["text_primary"]))
        self.title.config(text=title, fg=color)
        self.detail.config(text="")
        self.result.config(text="\n".join(t for t, _ in lines), fg=lines[0][1] if lines else COLORS["text_primary"])
