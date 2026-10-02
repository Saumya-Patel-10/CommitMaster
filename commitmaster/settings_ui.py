"""Settings window: full GUI for every option in config.json.

Modern dark-mode tabbed dialog that matches the rest of the CommitMaster UI.
Saves back to config via ConfigManager.save() — changes take effect immediately,
no restart needed.
"""
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog

from commitmaster import ai_messages, commit_engine
from commitmaster.config import ConfigManager, get_manager, load_config, save_config, _deep_merge, DEFAULTS
from commitmaster.logger import get
from commitmaster.ui import C, _button, _label, _center, _make_root, _style_window, run_in_ui_thread, show_info, show_error

log = get("settings_ui")

# ── ttk Dark Theme ────────────────────────────────────────────────────────────

def _apply_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".",
                    background=C["bg"],
                    foreground=C["text"],
                    fieldbackground=C["entry_bg"],
                    selectbackground=C["accent"],
                    selectforeground=C["bg"],
                    troughcolor=C["bg2"],
                    font=("Segoe UI", 10))
    style.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=0)
    style.configure("TNotebook.Tab",
                    background=C["bg3"], foreground=C["text2"],
                    padding=[14, 7], borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", C["bg2"])],
              foreground=[("selected", C["accent"])])
    style.configure("TFrame", background=C["bg"])
    style.configure("TLabel", background=C["bg"], foreground=C["text"])
    style.configure("TEntry", fieldbackground=C["entry_bg"],
                    foreground=C["entry_fg"], insertcolor=C["accent"])
    style.configure("TCheckbutton",
                    background=C["bg"], foreground=C["text"],
                    indicatorcolor=C["bg3"], selectcolor=C["accent"])
    style.map("TCheckbutton",
              indicatorcolor=[("selected", C["accent"])],
              foreground=[("active", C["accent"])])
    style.configure("TSpinbox",
                    fieldbackground=C["entry_bg"], foreground=C["entry_fg"],
                    arrowcolor=C["text2"])
    style.configure("TCombobox",
                    fieldbackground=C["entry_bg"], foreground=C["entry_fg"],
                    selectbackground=C["accent"], selectforeground=C["bg"])
    style.configure("TScrollbar",
                    background=C["bg3"], troughcolor=C["bg2"],
                    arrowcolor=C["text2"])
    style.configure("Accent.TButton",
                    background=C["accent"], foreground=C["bg"],
                    font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton", background=[("active", C["accent_dark"])])
    style.configure("Secondary.TButton",
                    background=C["bg3"], foreground=C["text"],
                    font=("Segoe UI", 10))
    style.map("Secondary.TButton", background=[("active", C["border"])])
    style.configure("TLabelframe",
                    background=C["bg"], foreground=C["text2"],
                    bordercolor=C["border"])
    style.configure("TLabelframe.Label",
                    background=C["bg"], foreground=C["accent"],
                    font=("Segoe UI", 10, "bold"))


# ── Settings Window ───────────────────────────────────────────────────────────

class SettingsWindow:
    def __init__(self, config_manager: ConfigManager):
        self._cm = config_manager
        self.cfg = config_manager.get()
        self.root = _make_root()
        self.root.deiconify()          # settings uses a real Tk root (not hidden)
        self.root.title("CommitMaster — Settings")
        self.root.geometry("680x600")
        self.root.minsize(580, 500)
        self.root.configure(bg=C["bg"])
        _apply_theme(self.root)

        self._build()

    def _build(self) -> None:
        # ── Title bar ─────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=C["bg2"], padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  CommitMaster Settings",
                 fg=C["accent"], bg=C["bg2"],
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x")

        # ── Notebook ──────────────────────────────────────────────────────────
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=10)

        self.tab_general  = ttk.Frame(nb)
        self.tab_folders  = ttk.Frame(nb)
        self.tab_ai       = ttk.Frame(nb)
        self.tab_advanced = ttk.Frame(nb)

        nb.add(self.tab_general,  text="  General  ")
        nb.add(self.tab_folders,  text="  Apps & Folders  ")
        nb.add(self.tab_ai,       text="  AI / Bionic  ")
        nb.add(self.tab_advanced, text="  Advanced  ")

        self._build_general()
        self._build_folders()
        self._build_ai()
        self._build_advanced()
        self._build_footer()

    # ── Tab: General ──────────────────────────────────────────────────────────

    def _build_general(self) -> None:
        f = self.tab_general
        self.var_auto_commit    = tk.BooleanVar(value=self.cfg["auto_commit"])
        self.var_skip_sensitive = tk.BooleanVar(value=self.cfg["skip_sensitive_files"])

        sec = self._section(f, "Commit Behaviour")
        ttk.Checkbutton(sec,
                        text="Commit automatically without preview  (not recommended)",
                        variable=self.var_auto_commit).pack(anchor="w", padx=4, pady=3)
        ttk.Checkbutton(sec,
                        text="Skip sensitive files  (.env, keys, certificates)",
                        variable=self.var_skip_sensitive).pack(anchor="w", padx=4, pady=3)

        sec2 = self._section(f, "Timing  (seconds)")
        grid = ttk.Frame(sec2)
        grid.pack(anchor="w")
        self._spin(grid, "Check coding apps every",     "poll_interval_seconds",       1,    60, 0)
        self._spin(grid, "Scan repos every",            "repo_scan_interval_seconds",  10, 3600, 1)
        self._spin(grid, "Wait after last app closes",  "session_end_grace_seconds",   10, 3600, 2)

        ttk.Label(f,
                  text="  'Wait after last app closes' controls how long CommitMaster\n"
                       "  waits before asking Hey, done coding for today?",
                  foreground=C["text2"]).pack(anchor="w", padx=16, pady=(8, 0))

    # ── Tab: Apps & Folders ───────────────────────────────────────────────────

    def _build_folders(self) -> None:
        f = self.tab_folders
        sec = self._section(f, "Project Folders  (contain your cloned repos)")
        self.lst_dirs = self._list_editor(sec, self.cfg["projects_dirs"], browse=True, height=4)

        sec2 = self._section(f, "Watched Coding Apps  (process names — Task Manager → Details)")
        self.lst_apps = self._list_editor(sec2, self.cfg["watched_apps"], browse=False, height=5)

    def _list_editor(self, parent, values, browse: bool, height: int) -> tk.Listbox:
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=4, pady=4)

        lb = tk.Listbox(
            frame, height=height,
            bg=C["entry_bg"], fg=C["text"],
            selectbackground=C["accent"], selectforeground=C["bg"],
            font=("Consolas", 10), relief="flat", bd=0,
            highlightthickness=1, highlightbackground=C["border"],
        )
        lb.pack(side="left", fill="both", expand=True)
        for v in values:
            lb.insert(tk.END, v)

        btn_col = ttk.Frame(frame)
        btn_col.pack(side="left", fill="y", padx=(6, 0))

        entry_row = ttk.Frame(parent)
        entry_row.pack(fill="x", padx=4, pady=(0, 4))
        entry = ttk.Entry(entry_row)
        entry.pack(side="left", fill="x", expand=True)

        def _add(_evt=None):
            val = entry.get().strip()
            if val:
                lb.insert(tk.END, val)
                entry.delete(0, tk.END)

        def _remove():
            for i in reversed(lb.curselection()):
                lb.delete(i)

        def _browse():
            chosen = filedialog.askdirectory(parent=self.root, title="Choose a projects folder")
            if chosen:
                lb.insert(tk.END, chosen.replace("/", "\\"))

        ttk.Button(btn_col, text="＋  Add",    command=_add,    style="Secondary.TButton", width=10).pack(pady=2)
        ttk.Button(btn_col, text="－  Remove", command=_remove, style="Secondary.TButton", width=10).pack(pady=2)
        if browse:
            ttk.Button(btn_col, text="📁  Browse…", command=_browse, style="Secondary.TButton", width=10).pack(pady=2)

        ttk.Button(entry_row, text="Add ↑", command=_add, style="Secondary.TButton", width=7).pack(side="left", padx=4)
        entry.bind("<Return>", _add)
        lb.entry = entry
        return lb

    # ── Tab: AI / Bionic ──────────────────────────────────────────────────────

    def _build_ai(self) -> None:
        f = self.tab_ai
        ai = self.cfg["ai"]

        sec = self._section(f, "Bionic / LM Studio  (OpenAI-compatible local server)")

        row = ttk.Frame(sec); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Server URL:", width=14).pack(side="left")
        self.ent_base_url = ttk.Entry(row)
        self.ent_base_url.insert(0, ai["base_url"])
        self.ent_base_url.pack(side="left", fill="x", expand=True, padx=6)

        row2 = ttk.Frame(sec); row2.pack(fill="x", pady=3)
        ttk.Label(row2, text="Model:", width=14).pack(side="left")
        self.cmb_model = ttk.Combobox(row2, width=38)
        model_val = ai.get("model", "")
        if model_val:
            self.cmb_model["values"] = [model_val]
            self.cmb_model.set(model_val)
        else:
            self.cmb_model.set("(auto-detect loaded model)")
        self.cmb_model.pack(side="left", padx=6)
        ttk.Button(row2, text="⟳ Refresh",
                   command=self._refresh_models,
                   style="Secondary.TButton").pack(side="left")

        row3 = ttk.Frame(sec); row3.pack(fill="x", pady=3)
        ttk.Label(row3, text="Timeout (s):", width=14).pack(side="left")
        self.spin_timeout = ttk.Spinbox(row3, from_=5, to=600, width=7)
        self.spin_timeout.set(str(ai["timeout_seconds"]))
        self.spin_timeout.pack(side="left", padx=6)

        ttk.Label(f,
                  text="  Leave model as '(auto-detect)' to always use whatever is loaded in\n"
                       "  Bionic / LM Studio — swap models freely without config changes.",
                  foreground=C["text2"]).pack(anchor="w", padx=16, pady=(8, 4))

        test_row = ttk.Frame(f); test_row.pack(anchor="w", padx=16)
        ttk.Button(test_row, text="🔌  Test connection",
                   command=self._test_connection,
                   style="Accent.TButton").pack(side="left")
        self.lbl_test_result = ttk.Label(test_row, text="", foreground=C["text2"])
        self.lbl_test_result.pack(side="left", padx=10)

    def _refresh_models(self) -> None:
        self.lbl_test_result.config(text="Fetching models…", foreground=C["warn_fg"])
        self.root.update_idletasks()
        tmp_cfg = {"ai": {"base_url": self.ent_base_url.get().strip(), "model": "", "timeout_seconds": 10}}
        models = ai_messages.list_models(tmp_cfg)
        if models:
            self.cmb_model["values"] = ["(auto-detect loaded model)"] + models
            self.cmb_model.current(0)
            self.lbl_test_result.config(text=f"✅  {len(models)} model(s) found", foreground=C["accent"])
        else:
            self.lbl_test_result.config(text="⚠  Could not reach server", foreground=C["warn_fg"])

    def _test_connection(self) -> None:
        self.lbl_test_result.config(text="Testing…", foreground=C["warn_fg"])
        self.root.update_idletasks()
        tmp_cfg = {
            "ai": {
                "base_url": self.ent_base_url.get().strip(),
                "model": self._model_value(),
                "timeout_seconds": 10,
            }
        }
        ok, msg = ai_messages.test_connection(tmp_cfg)
        color = C["accent"] if ok else C["err_fg"]
        self.lbl_test_result.config(text=("✅  " if ok else "⚠  ") + msg.split("\n")[0], foreground=color)

    # ── Tab: Advanced ─────────────────────────────────────────────────────────

    def _build_advanced(self) -> None:
        f = self.tab_advanced
        sec = self._section(f, "GitHub Desktop")

        row = ttk.Frame(sec); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Path:", width=8).pack(side="left")
        self.ent_gd = ttk.Entry(row)
        self.ent_gd.insert(0, self.cfg.get("github_desktop_path", ""))
        self.ent_gd.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Auto-detect", command=self._detect_gd,
                   style="Secondary.TButton").pack(side="left")

        ttk.Label(f, text="  Leave empty for auto-detection.  Opened after commit so you can push.",
                  foreground=C["text2"]).pack(anchor="w", padx=16, pady=(4, 0))

        sec2 = self._section(f, "Sensitive File Patterns  (never auto-staged — comma separated)")
        self.ent_sensitive = ttk.Entry(sec2)
        self.ent_sensitive.insert(0, ", ".join(self.cfg.get("sensitive_patterns", [])))
        self.ent_sensitive.pack(fill="x", padx=4, pady=4)

        ttk.Label(f,
                  text="  To restore all defaults: delete config.json and restart CommitMaster.",
                  foreground=C["text2"]).pack(anchor="w", padx=16, pady=(12, 0))

    def _detect_gd(self) -> None:
        path = commit_engine.find_github_desktop()
        if path:
            self.ent_gd.delete(0, tk.END)
            self.ent_gd.insert(0, path)
        else:
            show_error("GitHub Desktop not found in default locations.\n"
                       "Install it, or paste the path to GitHubDesktop.exe manually.")

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self) -> None:
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x")
        bar = tk.Frame(self.root, bg=C["bg2"], padx=12, pady=10)
        bar.pack(fill="x")
        _button(bar, "💾  Save",   self._save).pack(side="right", padx=(8, 0))
        _button(bar, "Cancel", self.root.destroy, accent=False).pack(side="right")
        _label(bar, "Changes apply immediately — no restart needed.",
               fg=C["text2"], bg=C["bg2"], font_size=9).pack(side="left")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            new_cfg = {
                "watched_apps":             self._listbox_values(self.lst_apps),
                "projects_dirs":            self._listbox_values(self.lst_dirs),
                "poll_interval_seconds":    int(self.spin_poll_interval_seconds.get()),
                "repo_scan_interval_seconds": int(self.spin_repo_scan_interval_seconds.get()),
                "session_end_grace_seconds": int(self.spin_session_end_grace_seconds.get()),
                "auto_commit":              self.var_auto_commit.get(),
                "skip_sensitive_files":     self.var_skip_sensitive.get(),
                "sensitive_patterns":       [p.strip() for p in self.ent_sensitive.get().split(",") if p.strip()],
                "github_desktop_path":      self.ent_gd.get().strip(),
                "ai": {
                    "base_url":         self.ent_base_url.get().strip(),
                    "model":            self._model_value(),
                    "timeout_seconds":  int(self.spin_timeout.get()),
                    "provider":         self.cfg["ai"].get("provider", "bionic"),
                },
            }
        except ValueError:
            show_error("Timing values must be whole numbers.")
            return

        if not new_cfg["watched_apps"]:
            show_error("Add at least one coding app to watch.")
            return
        if not new_cfg["projects_dirs"]:
            show_error("Add at least one project folder.")
            return

        merged = _deep_merge(self._cm.get(), new_cfg)
        self._cm.save(merged)
        log.info("Settings saved by user.")

        # Show brief inline confirmation
        try:
            self.root.title("CommitMaster — Settings  ✔ Saved!")
            self.root.after(2000, lambda: self.root.title("CommitMaster — Settings"))
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _listbox_values(lb: tk.Listbox):
        return [lb.get(i) for i in range(lb.size())]

    def _model_value(self) -> str:
        val = self.cmb_model.get().strip()
        return "" if val.startswith("(") else val

    def _section(self, parent, title: str) -> ttk.Frame:
        lf = ttk.LabelFrame(parent, text=f"  {title}  ", padding=(10, 6))
        lf.pack(fill="x", padx=12, pady=(10, 0))
        return lf

    def _spin(self, parent, label: str, key: str, lo: int, hi: int, row: int) -> None:
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=4, padx=(0, 8))
        spin = ttk.Spinbox(parent, from_=lo, to=hi, width=8,
                           textvariable=tk.StringVar(value=str(self.cfg[key])))
        spin.grid(row=row, column=1, pady=4)
        setattr(self, f"spin_{key}", spin)

    def run(self) -> None:
        _center(self.root)
        self.root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────

def open_settings(config_manager: Optional[ConfigManager] = None) -> None:
    """Called from the tray menu on a daemon thread."""
    if config_manager is None:
        config_manager = get_manager()
    try:
        SettingsWindow(config_manager).run()
    except tk.TclError as exc:
        log.warning("Settings window closed unexpectedly: %s", exc)


from typing import Optional