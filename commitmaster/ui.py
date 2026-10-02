"""UI layer: Windows notifications and the commit preview dialog (tkinter)."""
import threading
import tkinter as tk
from tkinter import messagebox

from commitmaster.commit_engine import GROUP_LABELS


def notify(title, message):
    """Fire a native Windows toast; never crash the app if it fails."""
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="CommitMaster", timeout=10)
    except Exception:
        print(f"[CommitMaster] {title}: {message}")


def ask_done_coding():
    """'Hey, you done coding for that day?' -> Yes/No."""
    root = _root()
    answer = messagebox.askyesno("CommitMaster", "Hey, you done coding for that day?")
    root.destroy()
    return answer


def pick_repo(repos):
    """One or more dirty repos -> let the user choose which to commit."""
    root = _root()
    chosen = []
    if len(repos) == 1:
        if messagebox.askyesno("CommitMaster", f"Commit changes in:\n{repos[0]}?"):
            chosen = repos
    else:
        win = tk.Toplevel(root)
        win.title("CommitMaster - pick a repository")
        tk.Label(win, text="Several projects have uncommitted changes.\nWhich one first?").pack(padx=12, pady=8)
        listbox = tk.Listbox(win, width=80, height=min(8, len(repos)))
        for repo in repos:
            listbox.insert(tk.END, repo)
        listbox.pack(padx=12, pady=4)
        def _choose(_event=None):
            selection = listbox.curselection()
            if selection:
                chosen.append(repos[selection[0]])
            win.destroy()
            if chosen and messagebox.askyesno("CommitMaster", "Commit more repositories after this one?"):
                rest = [r for r in repos if r not in chosen]
                chosen.extend(pick_repo(rest) if rest else [])
        listbox.bind("<Double-Button-1>", _choose)
        tk.Button(win, text="Commit selected", command=_choose).pack(pady=6)
        _center(win)
        root.wait_window(win)
    root.destroy()
    return chosen


def preview_and_commit(repo_name, branch, groups):
    """groups: {group: [files]} -> returns (action, messages) or None to cancel."""
    root = _root()
    win = tk.Toplevel(root)
    win.title(f"CommitMaster - {repo_name} ({branch})")
    win.geometry("760x520")

    entries = {}
    sensitive_files = groups.get("sensitive", [])
    rows = [(g, files) for g, files in groups.items() if g != "sensitive"]

    header = tk.Frame(win); header.pack(fill="x", padx=10, pady=6)
    tk.Label(header, text=f"{repo_name}  •  branch: {branch}",
             font=("Segoe UI", 11, "bold")).pack(side="left")

    canvas = tk.Canvas(win); scrollbar = tk.Scrollbar(win, command=canvas.yview)
    body = tk.Frame(canvas)
    canvas.create_window((0, 0), window=body, anchor="nw")
    body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="top", fill="both", expand=True, padx=10)
    scrollbar.pack(side="right", fill="y")

    for group, files in rows:
        frame = tk.Frame(body, bd=1, relief="groove"); frame.pack(fill="x", pady=6, padx=4)
        tk.Label(frame, text=f"{GROUP_LABELS[group]} ({len(files)} file{'s' if len(files) != 1 else ''})",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=6, pady=(4, 0))
        for f in files[:8]:
            tk.Label(frame, text=f"   {f}", fg="gray40").pack(anchor="w", padx=6)
        if len(files) > 8:
            tk.Label(frame, text=f"   ... and {len(files) - 8} more", fg="gray40").pack(anchor="w", padx=6)
        entry = tk.Entry(frame, font=("Consolas", 10))
        entry.pack(fill="x", padx=6, pady=6)
        entries[group] = entry

    if sensitive_files:
        warn = tk.Frame(body, bd=1, relief="solid", bg="#fff3cd"); warn.pack(fill="x", pady=6, padx=4)
        tk.Label(warn, text="⚠ Sensitive files NOT staged (add manually if intended):",
                 bg="#fff3cd", fg="#856404").pack(anchor="w", padx=6, pady=2)
        for f in sensitive_files:
            tk.Label(warn, text=f"   {f}", bg="#fff3cd", fg="#856404").pack(anchor="w", padx=6)

    buttons = tk.Frame(win); buttons.pack(fill="x", padx=10, pady=8)
    result = {"action": None}

    def _commit():
        messages = {g: e.get().strip() for g, e in entries.items() if e.get().strip()}
        result["action"] = ("commit", messages)
        win.destroy()

    tk.Button(buttons, text="✔ Commit", command=_commit, bg="#2ea44f", fg="white",
              width=14).pack(side="left", padx=4)
    tk.Button(buttons, text="Cancel", command=win.destroy, width=12).pack(side="right", padx=4)
    for group, entry in entries.items():
        entry.insert(0, entry.get() or _preset(win, group))

    _center(win)
    root.wait_window(win)
    root.destroy()
    return result["action"]


def _preset(_win, group):
    from commitmaster.ai_messages import FALLBACK_MESSAGES
    return FALLBACK_MESSAGES.get(group, "")


def show_info(message):
    root = _root()
    messagebox.showinfo("CommitMaster", message)
    root.destroy()


def _root():
    root = tk.Tk()
    root.withdraw()
    return root


def _center(win):
    win.update_idletasks()
    w, h = win.winfo_width(), win.winfo_height()
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"+{x}+{y}")


def run_in_ui_thread(fn):
    """tkinter dialogs must run on a clean thread of their own."""
    threading.Thread(target=fn, daemon=True).start()