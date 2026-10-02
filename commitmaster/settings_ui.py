"""Settings window: full GUI for every option in config.json.

Opened from the tray menu. Saves back to config.json on "Save"; changes to
watched apps / folders take effect on the next monitor poll, so no restart
is needed except for intervals, which are re-read each loop iteration anyway.
"""
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from commitmaster import ai_messages, commit_engine
from commitmaster.config import load_config, save_config


class SettingsWindow:
    def __init__(self):
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.title("CommitMaster — Settings")
        self.root.geometry("640x560")
        self.root.minsize(560, 480)

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_general = ttk.Frame(notebook); notebook.add(self.tab_general, text="  General  ")
        self.tab_folders = ttk.Frame(notebook); notebook.add(self.tab_folders, text="  Apps & Folders  ")
        self.tab_ai = ttk.Frame(notebook); notebook.add(self.tab_ai, text="  AI / LM Studio  ")
        self.tab_advanced = ttk.Frame(notebook); notebook.add(self.tab_advanced, text="  Advanced  ")

        self._build_general()
        self._build_folders()
        self._build_ai()
        self._build_advanced()
        self._build_buttons()

    # ---------- tabs ----------
    def _build_general(self):
        f = self.tab_general
        self.var_auto_commit = tk.BooleanVar(value=self.cfg["auto_commit"])
        self.var_skip_sensitive = tk.BooleanVar(value=self.cfg["skip_sensitive_files"])
        ttk.Label(f, text="Commit behaviour", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        ttk.Checkbutton(f, text="Commit automatically without preview (not recommended)",
                        variable=self.var_auto_commit).pack(anchor="w", padx=20, pady=2)
        ttk.Checkbutton(f, text="Skip sensitive files (.env, keys, certificates)",
                        variable=self.var_skip_sensitive).pack(anchor="w", padx=20, pady=2)

        ttk.Label(f, text="Timing (seconds)", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(16, 4))
        grid = ttk.Frame(f); grid.pack(anchor="w", padx=20)
        self._spin(grid, "Check coding apps every", "poll_interval_seconds", 1, 60, 0)
        self._spin(grid, "Scan repos every", "repo_scan_interval_seconds", 10, 3600, 1)
        self._spin(grid, "Wait after last app closes", "session_end_grace_seconds", 10, 3600, 2)

        ttk.Label(f, text="Tip: 'wait after last app closes' is how long CommitMaster\n"
                          "waits after you close all coding apps before asking\n"
                          "\"Hey, you done coding for that day?\"",
                  foreground="gray35", justify="left").pack(anchor="w", padx=20, pady=(14, 0))

    def _spin(self, parent, label, key, minimum, maximum, row):
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=3)
        spin = ttk.Spinbox(parent, from_=minimum, to=maximum, width=8,
                           textvariable=tk.StringVar(value=str(self.cfg[key])))
        spin.grid(row=row, column=1, padx=8, pady=3)
        setattr(self, f"spin_{key}", spin)

    def _build_folders(self):
        f = self.tab_folders
        ttk.Label(f, text="Project folders (containing your cloned GitHub repos)",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        self.lst_dirs = self._list_editor(
            f, self.cfg["projects_dirs"],
            browse=True, height=4)

        ttk.Label(f, text="Watched coding apps (process names — Task Manager → Details)",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        self.lst_apps = self._list_editor(f, self.cfg["watched_apps"], browse=False, height=6)

    def _list_editor(self, parent, values, browse, height):
        frame = ttk.Frame(parent); frame.pack(fill="x", padx=20)
        listbox = tk.Listbox(frame, height=height)
        listbox.pack(side="left", fill="x", expand=True)
        for v in values:
            listbox.insert(tk.END, v)
        buttons = ttk.Frame(frame); buttons.pack(side="left", fill="y", padx=(6, 0))

        def add():
            value = entry.get().strip()
            if not value:
                return
            listbox.insert(tk.END, value); entry.delete(0, tk.END)
        def remove():
            for i in reversed(listbox.curselection()):
                listbox.delete(i)
        def browse_dir():
            chosen = filedialog.askdirectory(parent=self.root, title="Choose a projects folder")
            if chosen:
                listbox.insert(tk.END, chosen.replace("/", "\\"))
        btns = [("＋ Add", add), ("－ Remove", remove)]
        if browse:
            btns.append(("📁 Browse…", browse_dir))
        for text, cmd in btns:
            ttk.Button(buttons, text=text, width=10, command=cmd).pack(pady=2)
        entry_row = ttk.Frame(parent); entry_row.pack(fill="x", padx=20, pady=(4, 0))
        entry = ttk.Entry(entry_row)
        entry.pack(side="left", fill="x", expand=True)
        ttk.Button(entry_row, text="Add ↑", width=8, command=add).pack(side="left", padx=6)
        listbox.entry = entry
        return listbox

    def _build_ai(self):
        f = self.tab_ai
        lm = self.cfg["lm_studio"]
        ttk.Label(f, text="LM Studio local server", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        row = ttk.Frame(f); row.pack(fill="x", padx=20, pady=2)
        ttk.Label(row, text="Server URL:").pack(side="left")
        self.ent_base_url = ttk.Entry(row); self.ent_base_url.insert(0, lm["base_url"])
        self.ent_base_url.pack(side="left", fill="x", expand=True, padx=8)

        row2 = ttk.Frame(f); row2.pack(fill="x", padx=20, pady=2)
        ttk.Label(row2, text="Model:").pack(side="left")
        self.cmb_model = ttk.Combobox(row2, width=40)
        if lm["model"]:
            self.cmb_model["values"] = [lm["model"]]
            self.cmb_model.set(lm["model"])
        else:
            self.cmb_model.set("(auto-detect loaded model)")
        self.cmb_model.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row2, text="⟳ Refresh", command=self._refresh_models).pack(side="left")

        row3 = ttk.Frame(f); row3.pack(fill="x", padx=20, pady=2)
        ttk.Label(row3, text="Timeout (s):").pack(side="left")
        self.spin_timeout = ttk.Spinbox(row3, from_=5, to=600, width=6)
        self.spin_timeout.set(str(lm["timeout_seconds"]))
        self.spin_timeout.pack(side="left", padx=8)

        ttk.Label(f, text="Leave the model as '(auto-detect loaded model)' to always use\n"
                          "whatever model is loaded in LM Studio — swap models freely.",
                  foreground="gray35", justify="left").pack(anchor="w", padx=20, pady=(10, 0))
        ttk.Button(f, text="Test connection", command=self._test_lm).pack(anchor="w", padx=20, pady=(10, 0))

    def _refresh_models(self):
        cfg = {"lm_studio": {"base_url": self.ent_base_url.get().strip(), "model": ""}}
        models = ai_messages.list_models(cfg)
        if models:
            self.cmb_model["values"] = ["(auto-detect loaded model)"] + models
            self.cmb_model.current(0)
            messagebox.showinfo("CommitMaster", f"Found {len(models)} model(s):\n" + "\n".join(models[:10]), parent=self.root)
        else:
            messagebox.showwarning("CommitMaster",
                "Could not reach LM Studio.\n\n1. Open LM Studio\n2. Developer tab → Start Server\n"
                "3. Confirm the URL matches above.", parent=self.root)

    def _test_lm(self):
        cfg = {"lm_studio": {"base_url": self.ent_base_url.get().strip(),
                             "model": self._model_value(), "timeout_seconds": 30}}
        model = ai_messages.detect_model(cfg) or (self._model_value() or None)
        if model:
            messagebox.showinfo("CommitMaster", f"✔ Connected!\nModel in use: {model}", parent=self.root)
        else:
            self._refresh_models()

    def _build_advanced(self):
        f = self.tab_advanced
        ttk.Label(f, text="GitHub Desktop", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        row = ttk.Frame(f); row.pack(fill="x", padx=20)
        ttk.Label(row, text="Path:").pack(side="left")
        self.ent_gd = ttk.Entry(row); self.ent_gd.insert(0, self.cfg["github_desktop_path"])
        self.ent_gd.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Auto-detect", command=self._detect_gd).pack(side="left")
        ttk.Label(f, text="Leave empty for auto-detection. This is opened after a commit\nso you can review and push.",
                  foreground="gray35", justify="left").pack(anchor="w", padx=20, pady=(4, 0))

        ttk.Label(f, text="Sensitive file patterns (comma separated — never auto-staged)",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(16, 4))
        self.ent_sensitive = ttk.Entry(f)
        self.ent_sensitive.insert(0, ", ".join(self.cfg["sensitive_patterns"]))
        self.ent_sensitive.pack(fill="x", padx=20)

        ttk.Label(f, text="Defaults are restored by deleting config.json and restarting.",
                  foreground="gray35").pack(anchor="w", padx=20, pady=(20, 0))

    def _detect_gd(self):
        path = commit_engine.find_github_desktop()
        if path:
            self.ent_gd.delete(0, tk.END); self.ent_gd.insert(0, path)
        else:
            messagebox.showwarning("CommitMaster", "GitHub Desktop not found in default locations.\n"
                "Install it, or browse for GitHubDesktop.exe and paste the path.", parent=self.root)

    # ---------- save ----------
    def _model_value(self):
        value = self.cmb_model.get().strip()
        return "" if value.startswith("(") else value

    def _collect_lists(self, listbox):
        return [listbox.get(i) for i in range(listbox.size())]

    def save(self):
        try:
            cfg = {
                "watched_apps": self._collect_lists(self.lst_apps),
                "projects_dirs": self._collect_lists(self.lst_dirs),
                "poll_interval_seconds": int(self.spin_poll_interval_seconds.get()),
                "repo_scan_interval_seconds": int(self.spin_repo_scan_interval_seconds.get()),
                "session_end_grace_seconds": int(self.spin_session_end_grace_seconds.get()),
                "auto_commit": self.var_auto_commit.get(),
                "skip_sensitive_files": self.var_skip_sensitive.get(),
                "sensitive_patterns": [p.strip() for p in self.ent_sensitive.get().split(",") if p.strip()],
                "github_desktop_path": self.ent_gd.get().strip(),
                "lm_studio": {
                    "base_url": self.ent_base_url.get().strip(),
                    "model": self._model_value(),
                    "timeout_seconds": int(self.spin_timeout.get()),
                },
            }
        except ValueError:
            messagebox.showerror("CommitMaster", "Timing values must be whole numbers.", parent=self.root)
            return
        if not cfg["watched_apps"]:
            messagebox.showerror("CommitMaster", "Add at least one coding app to watch.", parent=self.root)
            return
        if not cfg["projects_dirs"]:
            messagebox.showerror("CommitMaster", "Add at least one project folder.", parent=self.root)
            return
        save_config({**load_config(), **cfg})
        messagebox.showinfo("CommitMaster", "Settings saved ✔", parent=self.root)
        self.root.destroy()

    # ---------- chrome ----------
    def _build_buttons(self):
        bar = ttk.Frame(self.root); bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bar, text="Save", command=self.save).pack(side="right", padx=4)
        ttk.Button(bar, text="Cancel", command=self.root.destroy).pack(side="right", padx=4)

    def run(self):
        self.root.mainloop()


def open_settings():
    """Entry point used by the tray menu; runs the window on its own thread."""
    try:
        SettingsWindow().run()
    except tk.TclError:
        pass  # window closed or display issue — never crash the tray app