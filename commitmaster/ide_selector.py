"""
CommitMaster — Reusable Monitored Apps & IDE Selector Widget.
=============================================================
Provides an interactive, checkbox-driven checklist of popular coding IDEs,
automatic detection of running processes, custom executable file browsing,
and an active process picker.
"""
import os
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, Dict, List, Optional, Set
import psutil

from commitmaster.app_styles import COLORS, FONTS
from commitmaster.reminder_service import IDE_PRESETS, get_running_ide_processes


class IdeSelectorWidget:
    """
    Reusable UI component to choose which coding IDEs and apps CommitMaster monitors.
    """

    def __init__(
        self,
        parent: tk.Widget,
        initial_watched: List[str],
        on_change: Optional[Callable[[], None]] = None,
        bg_card: str = COLORS["bg_card"],
        bg_inner: str = COLORS["bg_medium"]
    ):
        self.parent = parent
        self.on_change = on_change
        self.bg_card = bg_card
        self.bg_inner = bg_inner

        self.initial_watched = initial_watched or []
        self._preset_vars: Dict[str, tk.BooleanVar] = {}
        self._preset_badge_labels: Dict[str, tk.Label] = {}
        self._custom_apps: List[str] = []
        self._custom_app_vars: Dict[str, tk.BooleanVar] = {}

        self.container = tk.Frame(parent, bg=self.bg_inner, padx=12, pady=10,
                                  highlightthickness=1, highlightbackground=COLORS["border"])
        self.container.pack(fill="x", pady=4)

        self._build_ui()

    def _build_ui(self):
        # ── Header row
        hdr = tk.Frame(self.container, bg=self.bg_inner)
        hdr.pack(fill="x", pady=(0, 8))

        tk.Label(
            hdr, text="💻 Monitored Coding IDEs & Applications",
            font=FONTS["label_bold"], fg=COLORS["text_primary"], bg=self.bg_inner
        ).pack(side="left")

        btn_tools = tk.Frame(hdr, bg=self.bg_inner)
        btn_tools.pack(side="right")

        sel_all_btn = tk.Button(
            btn_tools, text="Select All", font=("Segoe UI", 8),
            bg=self.bg_card, fg=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=6, pady=2,
            command=self._select_all
        )
        sel_all_btn.pack(side="left", padx=2)

        desel_btn = tk.Button(
            btn_tools, text="Clear All", font=("Segoe UI", 8),
            bg=self.bg_card, fg=COLORS["text_secondary"],
            relief="flat", bd=0, cursor="hand2", padx=6, pady=2,
            command=self._deselect_all
        )
        desel_btn.pack(side="left", padx=2)

        ref_btn = tk.Button(
            btn_tools, text="🔄 Refresh Running", font=("Segoe UI", 8),
            bg=self.bg_card, fg=COLORS["accent"],
            relief="flat", bd=0, cursor="hand2", padx=6, pady=2,
            command=self._refresh_running_badges
        )
        ref_btn.pack(side="left", padx=2)

        # ── Preset IDEs Grid (3 columns)
        grid_frame = tk.Frame(self.container, bg=self.bg_inner)
        grid_frame.pack(fill="x", pady=(2, 10))
        for col_i in range(3):
            grid_frame.columnconfigure(col_i, weight=1)

        running_now = get_running_ide_processes()
        watched_lower = {w.lower() for w in self.initial_watched}
        default_all = len(self.initial_watched) == 0

        for idx, preset in enumerate(IDE_PRESETS):
            p_exe = preset["exe"]
            p_name = preset["name"]
            p_icon = preset.get("icon", "💻")
            row_idx = idx // 3
            col_idx = idx % 3

            is_checked = default_all or (p_exe.lower() in watched_lower) or any(
                a.lower() in watched_lower for a in preset.get("aliases", [])
            )
            var = tk.BooleanVar(value=is_checked)
            self._preset_vars[p_exe] = var

            is_run = (p_exe.lower() in running_now) or any(
                a.lower() in running_now for a in preset.get("aliases", [])
            )

            cell = tk.Frame(
                grid_frame, bg=self.bg_card, padx=8, pady=5,
                highlightthickness=1, highlightbackground=COLORS["border"]
            )
            cell.grid(row=row_idx, column=col_idx, padx=4, pady=3, sticky="nsew")

            left_box = tk.Frame(cell, bg=self.bg_card)
            left_box.pack(side="left", fill="x", expand=True)

            cb = tk.Checkbutton(
                left_box, text=f"{p_icon} {p_name}", variable=var,
                font=FONTS["body_sm"], fg=COLORS["text_primary"],
                bg=self.bg_card, selectcolor=COLORS["bg_darkest"],
                activebackground=self.bg_card, activeforeground=COLORS["text_primary"],
                command=self._on_check_toggle
            )
            cb.pack(side="left")

            tk.Label(
                left_box, text=f"({p_exe})", font=FONTS["caption"],
                fg=COLORS["text_muted"], bg=self.bg_card
            ).pack(side="left", padx=(2, 0))

            badge_text = "● Running now" if is_run else ""
            badge_lbl = tk.Label(
                cell, text=badge_text, font=("Segoe UI", 8, "bold"),
                fg="#3fb950" if is_run else self.bg_card, bg=self.bg_card
            )
            badge_lbl.pack(side="right", padx=(4, 2))
            self._preset_badge_labels[p_exe] = badge_lbl

        # ── Custom Apps Section
        preset_exes_lower = {p["exe"].lower() for p in IDE_PRESETS}
        for p in IDE_PRESETS:
            for a in p.get("aliases", []):
                preset_exes_lower.add(a.lower())

        custom_watched = [w for w in self.initial_watched if w.lower() not in preset_exes_lower]
        self._custom_apps = list(dict.fromkeys(custom_watched))

        custom_sec = tk.Frame(self.container, bg=self.bg_inner)
        custom_sec.pack(fill="x", pady=(4, 0))

        tk.Label(
            custom_sec, text="＋ Additional Apps & IDEs (.exe):",
            font=FONTS["label"], fg=COLORS["text_secondary"], bg=self.bg_inner
        ).pack(anchor="w", pady=(0, 4))

        self._custom_container = tk.Frame(custom_sec, bg=self.bg_inner)
        self._custom_container.pack(fill="x")
        self._rebuild_custom_ui()

        # Add tools row
        add_row = tk.Frame(custom_sec, bg=self.bg_inner)
        add_row.pack(fill="x", pady=(6, 0))

        self._custom_entry_var = tk.StringVar()
        custom_entry = tk.Entry(
            add_row, textvariable=self._custom_entry_var, font=FONTS["mono_sm"],
            bg=COLORS["bg_input"], fg=COLORS["text_primary"], relief="flat",
            highlightthickness=1, highlightbackground=COLORS["border"], width=22
        )
        custom_entry.pack(side="left", ipady=3, padx=(0, 6))
        custom_entry.bind("<Return>", lambda e: self._add_from_entry())

        add_btn = tk.Button(
            add_row, text="＋ Add", font=FONTS["caption"],
            bg=COLORS["accent"], fg="white",
            relief="flat", bd=0, cursor="hand2", padx=8, pady=3,
            command=self._add_from_entry
        )
        add_btn.pack(side="left", padx=(0, 6))

        browse_btn = tk.Button(
            add_row, text="📁 Browse .exe", font=FONTS["caption"],
            bg=self.bg_card, fg=COLORS["text_primary"],
            relief="flat", bd=0, cursor="hand2", padx=8, pady=3,
            command=self._browse_exe
        )
        browse_btn.pack(side="left", padx=(0, 6))

        # Active processes picker
        pick_btn = tk.Button(
            add_row, text="⚡ Pick Running Process", font=FONTS["caption"],
            bg=self.bg_card, fg=COLORS["accent"],
            relief="flat", bd=0, cursor="hand2", padx=8, pady=3,
            command=self._pick_running_process
        )
        pick_btn.pack(side="left")

    def _rebuild_custom_ui(self):
        for w in self._custom_container.winfo_children():
            w.destroy()

        running_now = get_running_ide_processes()
        for c_exe in self._custom_apps:
            if c_exe not in self._custom_app_vars:
                self._custom_app_vars[c_exe] = tk.BooleanVar(value=True)
            c_var = self._custom_app_vars[c_exe]

            c_row = tk.Frame(
                self._custom_container, bg=self.bg_card, padx=8, pady=3,
                highlightthickness=1, highlightbackground=COLORS["border"]
            )
            c_row.pack(fill="x", pady=2)

            tk.Checkbutton(
                c_row, text=f"⚙️ {c_exe}", variable=c_var,
                font=FONTS["body_sm"], fg=COLORS["text_primary"],
                bg=self.bg_card, selectcolor=COLORS["bg_darkest"],
                activebackground=self.bg_card, activeforeground=COLORS["text_primary"],
                command=self._on_check_toggle
            ).pack(side="left")

            if c_exe.lower() in running_now:
                tk.Label(
                    c_row, text="● Running now", font=("Segoe UI", 8, "bold"),
                    fg="#3fb950", bg=self.bg_card
                ).pack(side="left", padx=8)

            rm_btn = tk.Button(
                c_row, text="✕", font=("Segoe UI", 8),
                bg=self.bg_card, fg=COLORS["danger"],
                relief="flat", bd=0, cursor="hand2", padx=6, pady=1,
                command=lambda target=c_exe: self._remove_custom(target)
            )
            rm_btn.pack(side="right")

    def _select_all(self):
        for v in self._preset_vars.values():
            v.set(True)
        for v in self._custom_app_vars.values():
            v.set(True)
        self._on_check_toggle()

    def _deselect_all(self):
        for v in self._preset_vars.values():
            v.set(False)
        for v in self._custom_app_vars.values():
            v.set(False)
        self._on_check_toggle()

    def _refresh_running_badges(self):
        running_now = get_running_ide_processes()
        for p in IDE_PRESETS:
            p_exe = p["exe"]
            is_run = (p_exe.lower() in running_now) or any(
                a.lower() in running_now for a in p.get("aliases", [])
            )
            lbl = self._preset_badge_labels.get(p_exe)
            if lbl and lbl.winfo_exists():
                lbl.config(
                    text="● Running now" if is_run else "",
                    fg="#3fb950" if is_run else self.bg_card
                )
        self._rebuild_custom_ui()

    def _add_from_entry(self):
        val = self._custom_entry_var.get().strip()
        if not val:
            return
        clean = os.path.basename(val)
        if not clean.lower().endswith(".exe"):
            clean += ".exe"
        if clean not in self._custom_apps:
            self._custom_apps.append(clean)
            self._custom_app_vars[clean] = tk.BooleanVar(value=True)
            self._rebuild_custom_ui()
            self._on_check_toggle()
        self._custom_entry_var.set("")

    def _browse_exe(self):
        f = filedialog.askopenfilename(
            title="Select Executable to Monitor",
            filetypes=[("Executable Files (*.exe)", "*.exe"), ("All Files (*.*)", "*.*")],
            parent=self.parent
        )
        if f:
            base = os.path.basename(f)
            self._custom_entry_var.set(base)
            self._add_from_entry()

    def _pick_running_process(self):
        """Show dialog to pick from any running process on the PC."""
        dlg = tk.Toplevel(self.parent)
        dlg.title("Select Running Process to Monitor")
        dlg.geometry("380x420")
        dlg.minsize(360, 360)
        dlg.configure(bg=COLORS["bg_darkest"])
        dlg.transient(self.parent)
        dlg.grab_set()

        tk.Label(
            dlg, text="Active Desktop Processes", font=FONTS["heading_sm"],
            fg=COLORS["text_primary"], bg=COLORS["bg_darkest"]
        ).pack(anchor="w", padx=16, pady=(16, 4))

        tk.Label(
            dlg, text="Choose any process currently running on your PC:",
            font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"]
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # Collect running processes
        procs = set()
        try:
            for p in psutil.process_iter(["name"]):
                name = p.info.get("name")
                if name and name.lower().endswith(".exe"):
                    procs.add(name)
        except Exception:
            pass

        sorted_procs = sorted(procs, key=lambda s: s.lower())

        lb_frame = tk.Frame(dlg, bg=COLORS["bg_card"], padx=2, pady=2)
        lb_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        lb = tk.Listbox(
            lb_frame, bg=COLORS["bg_input"], fg=COLORS["text_primary"],
            font=FONTS["mono_sm"], selectbackground=COLORS["accent"],
            selectforeground="white", relief="flat", bd=0
        )
        sb = tk.Scrollbar(lb_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        for p_name in sorted_procs:
            lb.insert("end", p_name)

        def _choose():
            sel = lb.curselection()
            if sel:
                chosen = lb.get(sel[0])
                if chosen not in self._custom_apps:
                    self._custom_apps.append(chosen)
                    self._custom_app_vars[chosen] = tk.BooleanVar(value=True)
                    self._rebuild_custom_ui()
                    self._on_check_toggle()
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg=COLORS["bg_darkest"])
        btn_row.pack(fill="x", padx=16, pady=(0, 16))

        tk.Button(
            btn_row, text="Cancel", font=FONTS["body_sm"],
            bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
            relief="flat", bd=0, cursor="hand2", padx=12, pady=6,
            command=dlg.destroy
        ).pack(side="left")

        tk.Button(
            btn_row, text="✔ Add Selected Process", font=FONTS["label_bold"],
            bg=COLORS["accent"], fg="white",
            relief="flat", bd=0, cursor="hand2", padx=14, pady=6,
            command=_choose
        ).pack(side="right")

    def _remove_custom(self, target: str):
        if target in self._custom_apps:
            self._custom_apps.remove(target)
        if target in self._custom_app_vars:
            del self._custom_app_vars[target]
        self._rebuild_custom_ui()
        self._on_check_toggle()

    def _on_check_toggle(self):
        if self.on_change:
            self.on_change()

    def get_selected_apps(self) -> List[str]:
        """Return the complete list of all selected .exe process names."""
        selected: List[str] = []
        for preset in IDE_PRESETS:
            p_exe = preset["exe"]
            var = self._preset_vars.get(p_exe)
            if var and var.get():
                selected.append(p_exe)

        for c_exe in self._custom_apps:
            var = self._custom_app_vars.get(c_exe)
            if var and var.get() and c_exe not in selected:
                selected.append(c_exe)

        return selected
