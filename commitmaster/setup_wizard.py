"""
CommitMaster — First-run AI Setup Wizard.
=========================================
Shown once, before sign-in, on a fresh install:

  1. How will you use AI?        Local AI  |  API key  |  Both
  2. (Local/Both) Runtime        Ollama or LM Studio (installed ones are detected)
  3. (Local/Both) Model          pick a model (recommended one is pre-selected)
  4. (API/Both)   API provider   OpenAI / Claude / Gemini + key
  5. Install & download          installs the runtime if missing, downloads the model
  6. Done                        → continue to sign in / create account

After sign-in, `ai_setup.auto_configure()` fills in host / port / model automatically.
"""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from commitmaster import ai_setup
from commitmaster.app_styles import COLORS, FONTS


def _fmt_bytes(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    return f"{n / 1024 ** 2:.0f} MB"


class SetupWizard:
    """Modal-ish wizard. `run()` blocks until finished/skipped; `completed` tells which."""

    API_PROVIDERS = [("OpenAI", "openai"), ("Anthropic Claude", "claude"), ("Google Gemini", "gemini")]

    def __init__(self, parent: Optional[tk.Misc] = None, on_done: Optional[Callable[[], None]] = None):
        self.completed = False
        self._on_done = on_done
        self._parent = parent
        self.root = tk.Toplevel(parent) if parent is not None else tk.Tk()
        self.root.title("CommitMaster — AI Setup")
        self.root.configure(bg=COLORS["bg_darkest"])
        self.root.resizable(False, False)
        w, h = 600, 640
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        h = min(h, sh - 80)
        self.root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if parent is not None:
            self.root.transient(parent)
            self.root.grab_set()

        # Wizard state
        self.mode = tk.StringVar(value="local")
        self.runtime = tk.StringVar(value=ai_setup.OLLAMA)
        self.model_choice = tk.StringVar(value=ai_setup.recommended_model_id())
        self.api_provider = tk.StringVar(value="openai")
        self.api_key = tk.StringVar()
        self.installed = ai_setup.detect_installed()
        self.existing_models: List[str] = []
        self._cancel = threading.Event()
        self._events: "queue.Queue" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._busy = False
        self._result: Dict = {}
        self._page = ""

        self._container = tk.Frame(self.root, bg=COLORS["bg_darkest"], padx=28, pady=22)
        self._container.pack(fill="both", expand=True)
        self._show("mode")

    # ── Navigation ────────────────────────────────────────────────────────────

    def _sequence(self) -> List[str]:
        seq = ["mode"]
        if self.mode.get() in ("local", "both"):
            seq += ["runtime", "model"]
        if self.mode.get() in ("api", "both"):
            seq += ["api"]
        seq += ["install", "done"]
        return seq

    def _next(self):
        if not self._validate():
            return
        seq = self._sequence()
        self._show(seq[seq.index(self._page) + 1])

    def _back(self):
        seq = self._sequence()
        i = seq.index(self._page)
        if i > 0 and not self._busy:
            self._show(seq[i - 1])

    def _clear(self):
        for c in self._container.winfo_children():
            c.destroy()

    def _show(self, page: str):
        self._page = page
        self._clear()
        getattr(self, f"_page_{page}")()

    # ── Shared widgets ────────────────────────────────────────────────────────

    def _header(self, title: str, subtitle: str, step: str = ""):
        if step:
            tk.Label(self._container, text=step, font=("Consolas", 8, "bold"),
                     fg=COLORS["accent"], bg=COLORS["bg_darkest"]).pack(anchor="w")
        tk.Label(self._container, text=title, font=FONTS["heading_md"],
                 fg=COLORS["text_primary"], bg=COLORS["bg_darkest"]).pack(anchor="w", pady=(2, 2))
        tk.Label(self._container, text=subtitle, font=FONTS["body_sm"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_darkest"], wraplength=540, justify="left").pack(anchor="w", pady=(0, 14))

    def _footer(self, next_text="Next  ›", back=True, skip=False, next_cmd=None):
        bar = tk.Frame(self._container, bg=COLORS["bg_darkest"])
        bar.pack(side="bottom", fill="x", pady=(14, 0))
        self._next_btn = tk.Button(bar, text=next_text, font=FONTS["heading_sm"], bg=COLORS["accent"],
                                   fg="#ffffff", activebackground=COLORS["accent_hover"],
                                   activeforeground="#ffffff", relief="flat", bd=0, cursor="hand2",
                                   padx=18, pady=7, command=next_cmd or self._next)
        self._next_btn.pack(side="right")
        if back:
            tk.Button(bar, text="‹  Back", font=FONTS["body_sm"], bg=COLORS["bg_card"],
                      fg=COLORS["text_primary"], relief="flat", bd=0, cursor="hand2",
                      padx=14, pady=7, command=self._back).pack(side="right", padx=(0, 8))
        if skip:
            lbl = tk.Label(bar, text="Skip for now", font=("Segoe UI", 9, "underline"),
                           fg=COLORS["text_muted"], bg=COLORS["bg_darkest"], cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e: self._skip())
        self._err = tk.Label(self._container, text="", font=FONTS["body_sm"], fg=COLORS["error"],
                             bg=COLORS["bg_darkest"], wraplength=540, justify="left")
        self._err.pack(side="bottom", anchor="w")

    def _option_card(self, parent, variable, value, title, desc, badge: str = "", state="normal"):
        card = tk.Frame(parent, bg=COLORS["bg_card"], highlightthickness=1,
                        highlightbackground=COLORS["border"], padx=12, pady=9)
        card.pack(fill="x", pady=4)
        rb = tk.Radiobutton(card, variable=variable, value=value, bg=COLORS["bg_card"],
                            activebackground=COLORS["bg_card"], selectcolor=COLORS["bg_input"],
                            fg=COLORS["accent"], bd=0, highlightthickness=0, state=state,
                            cursor="hand2")
        rb.pack(side="left", padx=(0, 8))
        body = tk.Frame(card, bg=COLORS["bg_card"])
        body.pack(side="left", fill="x", expand=True)
        row = tk.Frame(body, bg=COLORS["bg_card"])
        row.pack(fill="x")
        tk.Label(row, text=title, font=FONTS["label_bold"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_card"]).pack(side="left")
        if badge:
            tk.Label(row, text=f"  {badge}", font=("Segoe UI", 8, "bold"), fg=COLORS["accent"],
                     bg=COLORS["bg_card"]).pack(side="left")
        tk.Label(body, text=desc, font=FONTS["caption"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_card"], wraplength=440, justify="left").pack(anchor="w")
        for w in (card, body, row):
            w.bind("<Button-1>", lambda e, v=value: variable.set(v))
        return card

    # ── Pages ─────────────────────────────────────────────────────────────────

    def _page_mode(self):
        self._header("How will you use AI?",
                     "CommitMaster writes your commit messages with AI. Choose where that AI runs — "
                     "you can change this later in Settings.", "STEP 1 — AI SOURCE")
        self._option_card(self._container, self.mode, "local", "Local AI",
                          "Runs on your PC with Ollama or LM Studio. Private, free, works offline.")
        self._option_card(self._container, self.mode, "api", "API Key",
                          "Use OpenAI, Claude or Gemini with your own key. Nothing to install.")
        self._option_card(self._container, self.mode, "both", "Both",
                          "Local AI first, automatically falls back to your API key if it's unavailable.",
                          badge="BEST RELIABILITY")
        self._footer(back=False, skip=True)

    def _page_runtime(self):
        self._header("Choose your local AI app",
                     "We checked this PC for Ollama and LM Studio.", "STEP 2 — LOCAL AI APP")
        inst = self.installed
        found = [rt for rt in (ai_setup.OLLAMA, ai_setup.LMSTUDIO) if inst.get(rt)]
        if found:
            msg = "Found on this PC: " + ", ".join(ai_setup.RUNTIME_LABELS[r] for r in found)
            colour = COLORS["success"]
            if self.runtime.get() not in found:
                self.runtime.set(found[0])
        else:
            msg = "Neither Ollama nor LM Studio was found. Pick one — we'll download and install it for you."
            colour = COLORS["info"]
        tk.Label(self._container, text=msg, font=FONTS["body_sm"], fg=colour, bg=COLORS["bg_darkest"],
                 wraplength=540, justify="left").pack(anchor="w", pady=(0, 6))
        self._option_card(self._container, self.runtime, ai_setup.OLLAMA, "Ollama",
                          "Lightweight and simple; runs quietly in the background. Recommended for most people.",
                          badge="INSTALLED ✔" if inst.get(ai_setup.OLLAMA) else "WILL BE INSTALLED")
        self._option_card(self._container, self.runtime, ai_setup.LMSTUDIO, "LM Studio",
                          "Full desktop app with a model browser and chat window.",
                          badge="INSTALLED ✔" if inst.get(ai_setup.LMSTUDIO) else "WILL BE INSTALLED")
        self._footer()

    def _page_model(self):
        rt = self.runtime.get()
        self._header("Choose a model",
                     f"This model will be downloaded into {ai_setup.RUNTIME_LABELS[rt]}. "
                     f"Your PC has about {ai_setup.system_ram_gb():.0f} GB of RAM.", "STEP 3 — MODEL")

        # Models that are already on this PC (if the runtime is installed and running)
        self.existing_models = []
        if self.installed.get(rt) and ai_setup.server_up(rt):
            self.existing_models = ai_setup.list_local_models(rt)

        outer = tk.Frame(self._container, bg=COLORS["bg_darkest"])
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=COLORS["bg_darkest"], highlightthickness=0)
        sb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=COLORS["bg_darkest"])
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120) * 2, "units"))

        ram = ai_setup.system_ram_gb()
        rec = ai_setup.recommended_model_id(ram)
        if self.existing_models:
            tk.Label(inner, text="Already on this PC", font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                     bg=COLORS["bg_darkest"]).pack(anchor="w", pady=(0, 2))
            for name in self.existing_models[:6]:
                self._option_card(inner, self.model_choice, f"existing::{name}", name,
                                  "Already downloaded — no download needed.", badge="INSTALLED ✔")
            tk.Label(inner, text="Download a new model", font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                     bg=COLORS["bg_darkest"]).pack(anchor="w", pady=(8, 2))
        for m in ai_setup.MODEL_CATALOG:
            fits = ram >= m["min_ram_gb"]
            badge = "RECOMMENDED" if m["id"] == rec else ("" if fits else "NEEDS MORE RAM")
            self._option_card(inner, self.model_choice, m["id"], f"{m['label']}  ·  {m['size_gb']} GB download",
                              m["desc"], badge=badge)
        if self.model_choice.get() not in [m["id"] for m in ai_setup.MODEL_CATALOG] \
                and not self.model_choice.get().startswith("existing::"):
            self.model_choice.set(rec)
        self._footer()

    def _page_api(self):
        self._header("Add your API key",
                     "Your key is stored only on this PC and used to talk to the provider you choose.",
                     "STEP 4 — API KEY")
        for label, val in self.API_PROVIDERS:
            self._option_card(self._container, self.api_provider, val, label,
                              {"openai": "Fast and inexpensive (gpt-4o-mini by default).",
                               "claude": "Anthropic Claude (claude-3.5-haiku by default).",
                               "gemini": "Google Gemini (gemini-1.5-flash by default)."}[val])
        tk.Label(self._container, text="API key", font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_darkest"]).pack(anchor="w", pady=(10, 0))
        e = tk.Entry(self._container, textvariable=self.api_key, show="•", font=FONTS["body_md"],
                     bg=COLORS["bg_input"], fg=COLORS["text_primary"], insertbackground=COLORS["text_primary"],
                     relief="flat", bd=0, highlightthickness=1, highlightbackground=COLORS["border"],
                     highlightcolor=COLORS["border_focus"])
        e.pack(fill="x", ipady=6, ipadx=8, pady=(3, 6))
        e.focus()
        self._test_lbl = tk.Label(self._container, text="", font=FONTS["body_sm"],
                                  fg=COLORS["text_secondary"], bg=COLORS["bg_darkest"],
                                  wraplength=540, justify="left")
        tk.Button(self._container, text="Test key", font=FONTS["body_sm"], bg=COLORS["bg_card"],
                  fg=COLORS["text_primary"], relief="flat", bd=0, cursor="hand2", padx=12, pady=5,
                  command=self._test_key).pack(anchor="w")
        self._test_lbl.pack(anchor="w", pady=(4, 0))
        self._footer()

    def _test_key(self):
        from commitmaster import ai_messages
        from commitmaster.config import load_config
        key = self.api_key.get().strip()
        if not key:
            self._test_lbl.config(text="Enter a key first.", fg=COLORS["error"])
            return
        prov = self.api_provider.get()
        cfg = load_config()
        cfg["ai"]["provider"] = prov
        cfg["ai"]["model"] = ""
        cfg["ai"][f"{prov}_api_key"] = key
        self._test_lbl.config(text="Testing…", fg=COLORS["text_secondary"])
        self.root.update_idletasks()

        def work():
            ok, msg = ai_messages.test_connection(cfg)
            self._events.put(("test", ok, msg.split("\n")[0]))
        threading.Thread(target=work, daemon=True).start()
        self.root.after(150, self._poll_test)

    def _poll_test(self):
        try:
            while True:
                kind, ok, msg = self._events.get_nowait()
                if kind == "test" and self._page == "api":
                    self._test_lbl.config(text=("✔ " if ok else "✖ ") + msg,
                                          fg=COLORS["success"] if ok else COLORS["error"])
                    return
        except queue.Empty:
            if self._page == "api":
                self.root.after(150, self._poll_test)

    def _page_install(self):
        local = self.mode.get() in ("local", "both")
        self._header("Setting things up" if local else "Saving your settings",
                     "Please keep this window open. Large model downloads can take several minutes."
                     if local else "Applying your AI settings…", "FINAL STEP")
        self._status = tk.Label(self._container, text="Starting…", font=FONTS["body_md"],
                                fg=COLORS["text_primary"], bg=COLORS["bg_darkest"], wraplength=540, justify="left")
        self._status.pack(anchor="w", pady=(10, 6))
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("CM.Horizontal.TProgressbar", troughcolor=COLORS["bg_input"],
                        background=COLORS["accent"], bordercolor=COLORS["border"], lightcolor=COLORS["accent"],
                        darkcolor=COLORS["accent"])
        self._bar = ttk.Progressbar(self._container, style="CM.Horizontal.TProgressbar",
                                    orient="horizontal", mode="indeterminate", length=540)
        self._bar.pack(fill="x")
        self._bar.start(12)
        self._detail = tk.Label(self._container, text="", font=FONTS["caption"], fg=COLORS["text_secondary"],
                                bg=COLORS["bg_darkest"])
        self._detail.pack(anchor="w", pady=(4, 0))
        self._footer(next_text="Working…", back=False, next_cmd=lambda: None)
        self._next_btn.config(state="disabled")
        self._start_worker()

    def _page_done(self):
        mode = self.mode.get()
        summary = {"local": "Local AI", "api": "API key", "both": "Local AI + API key fallback"}[mode]
        self._header("You're all set 🎉", f"AI source: {summary}. Next, sign in or create your account — "
                     "all AI settings (server address, port and model) are already configured for you.",
                     "DONE")
        lines = []
        if mode in ("local", "both"):
            rt = self._result.get("runtime", self.runtime.get())
            lines.append(f"• {ai_setup.RUNTIME_LABELS[rt]} at {ai_setup.api_root(rt, self._result.get('host', ''), self._result.get('port', 0))}")
            if self._result.get("model"):
                lines.append(f"• Model: {self._result['model']}")
        if mode in ("api", "both"):
            lines.append(f"• API provider: {dict((v, l) for l, v in self.API_PROVIDERS)[self.api_provider.get()]}")
        if self._result.get("warning"):
            lines.append(f"\n⚠ {self._result['warning']}")
        tk.Label(self._container, text="\n".join(lines), font=FONTS["body_md"], fg=COLORS["text_primary"],
                 bg=COLORS["bg_darkest"], justify="left", wraplength=540).pack(anchor="w", pady=10)
        self._footer(next_text="Continue to Sign In  ›", back=False, next_cmd=self._finish)

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate(self) -> bool:
        if self._page == "api":
            if not self.api_key.get().strip():
                self._err.config(text="Please enter your API key (or go back and choose Local AI).")
                return False
        return True

    # ── Worker ────────────────────────────────────────────────────────────────

    def _choices(self) -> Dict:
        mode = self.mode.get()
        ch: Dict = {"mode": mode}
        if mode in ("local", "both"):
            ch["runtime"] = self.runtime.get()
            sel = self.model_choice.get()
            if sel.startswith("existing::"):
                ch["existing_model"] = sel.split("::", 1)[1]
            else:
                ch["model_id"] = sel
        if mode in ("api", "both"):
            ch["api_provider"] = self.api_provider.get()
            ch["api_key"] = self.api_key.get().strip()
        return ch

    def _start_worker(self):
        self._cancel.clear()
        self._busy = True
        choices = self._choices()

        def progress(done, total, text):
            self._events.put(("progress", done, total, text))

        def status(text):
            self._events.put(("status", text))

        def work():
            try:
                result = dict(choices)
                if choices["mode"] in ("local", "both"):
                    result = ai_setup.run_local_setup(choices, progress, status, self._cancel)
                    if choices.get("existing_model"):
                        result["model"] = choices["existing_model"]
                    import commitmaster.ai_setup as s
                    if not s.server_up(result["runtime"]):
                        result["warning"] = (
                            f"{s.RUNTIME_LABELS[result['runtime']]} isn't running yet. "
                            "CommitMaster will try to start it after you sign in."
                            if result["runtime"] == s.OLLAMA else
                            "In LM Studio open the Developer tab and start the server. "
                            "CommitMaster will detect it automatically after you sign in.")
                status("Saving settings…")
                ai_setup.apply_setup(result)
                self._events.put(("ok", result))
            except ai_setup.SetupCancelled:
                self._events.put(("cancelled",))
            except Exception as exc:  # noqa: BLE001
                self._events.put(("error", str(exc)))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()
        self.root.after(100, self._poll)

    def _poll(self):
        if self._page != "install":
            return
        try:
            while True:
                ev = self._events.get_nowait()
                kind = ev[0]
                if kind == "status":
                    self._status.config(text=ev[1])
                elif kind == "progress":
                    _, done, total, text = ev
                    if total > 0:
                        if str(self._bar["mode"]) != "determinate":
                            self._bar.stop()
                            self._bar.config(mode="determinate", maximum=100)
                        self._bar["value"] = min(100, done * 100 / total)
                        self._detail.config(text=f"{text}   {_fmt_bytes(done)} / {_fmt_bytes(total)}  "
                                                 f"({done * 100 // total}%)")
                    elif text:
                        self._detail.config(text=text)
                elif kind == "ok":
                    self._busy = False
                    self._result = ev[1]
                    self._bar.stop()
                    self._show("done")
                    return
                elif kind == "error":
                    self._busy = False
                    self._show_failure(ev[1])
                    return
                elif kind == "cancelled":
                    self._busy = False
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _show_failure(self, message: str):
        self._bar.stop()
        self._bar.config(mode="determinate", value=0)
        self._status.config(text="Something went wrong", fg=COLORS["error"])
        self._detail.config(text=message, fg=COLORS["text_secondary"], wraplength=540, justify="left")
        bar = tk.Frame(self._container, bg=COLORS["bg_darkest"])
        bar.pack(anchor="w", pady=14)

        def retry():
            self._show("install")

        def anyway():
            from commitmaster import ai_setup as s
            res = self._choices()
            res["warning"] = "Setup did not fully finish. You can re-run AI Setup from the sign-in screen."
            s.apply_setup({**res, "model": res.get("existing_model", "")})
            self._result = res
            self._show("done")

        for text, cmd, bg in (("Retry", retry, COLORS["accent"]),
                              ("Continue anyway", anyway, COLORS["bg_card"]),
                              ("Back", lambda: self._show("mode"), COLORS["bg_card"])):
            tk.Button(bar, text=text, command=cmd, font=FONTS["body_sm"], bg=bg, fg="#ffffff" if bg == COLORS["accent"] else COLORS["text_primary"],
                      relief="flat", bd=0, cursor="hand2", padx=14, pady=6).pack(side="left", padx=(0, 8))

    # ── Finish / close ────────────────────────────────────────────────────────

    def _skip(self):
        ai_setup.mark_setup_skipped()
        self.completed = True
        self._close()

    def _finish(self):
        self.completed = True
        self._close()

    def _on_close(self):
        if self._busy:
            self._cancel.set()
        self._close()

    def _close(self):
        try:
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        if self.completed and self._on_done:
            self._on_done()

    def run(self):
        if self._parent is None:
            self.root.mainloop()
        else:
            self.root.wait_window()
