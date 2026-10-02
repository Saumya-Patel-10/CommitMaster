"""End-of-session flow: ask → inspect repos → AI messages → preview → commit.

All heavy work (git + AI HTTP) runs on a background thread so the UI stays
responsive.  The UI callbacks are dispatched to the tkinter thread via
ui.run_in_ui_thread.
"""
import concurrent.futures
import threading
from typing import Dict, List, Optional

from commitmaster import ai_messages, commit_engine, ui
from commitmaster.config import ConfigManager
from commitmaster.logger import get

log = get("flow")


def handle_session_end(config_manager: ConfigManager, known_dirty_repos: List[str]) -> None:
    """Entry point called from the main event loop or tray menu.
    Dispatches the flow to a worker thread."""
    threading.Thread(
        target=_flow_worker,
        args=(config_manager, known_dirty_repos),
        daemon=True,
        name="flow-worker",
    ).start()


def _flow_worker(config_manager: ConfigManager, known_dirty_repos: List[str]) -> None:
    """Runs entirely on a background thread; ui.* calls are safe because
    ui.run_in_ui_thread posts them to the tkinter main thread."""
    cfg = config_manager.get()

    # --- Step 1: ask "Done coding for today?" ---
    done = ui.ask_done_coding()
    if not done:
        ui.notify("CommitMaster", "No problem — I'll check again after your next session.")
        log.info("User declined end-of-session flow.")
        return

    # --- Step 2: fresh repo scan merged with cached dirty set ---
    repos = sorted(set(known_dirty_repos) | set(_scan_dirty(cfg)))
    if not repos:
        ui.show_info("All repositories are clean — nothing to commit! 🎉")
        log.info("No dirty repos found.")
        return

    # --- Step 3: repo picker ---
    chosen = ui.pick_repos(repos)
    if not chosen:
        log.info("User chose no repos to commit.")
        return

    log.info("User chose to commit %d repo(s): %s", len(chosen), chosen)
    for repo in chosen:
        _commit_one(cfg, repo)


# ── Per-repo commit flow ──────────────────────────────────────────────────────

def _commit_one(cfg: dict, repo: str) -> None:
    name = commit_engine.repo_name(repo)
    log.info("Starting commit flow for: %s", name)
    try:
        changes = commit_engine.uncommitted_changes(repo)
        if not changes:
            ui.show_info(f"{name}: nothing to commit.")
            return

        sensitive = cfg.get("sensitive_patterns", [])
        groups = commit_engine.build_groups(changes, sensitive_patterns=sensitive)
        if not groups:
            ui.show_info(f"{name}: nothing to commit.")
            return

        branch = commit_engine.current_branch(repo)

        if cfg.get("auto_commit"):
            _auto_commit(cfg, repo, name, branch, groups)
        else:
            _interactive_commit(cfg, repo, name, branch, groups)

    except commit_engine.GitError as exc:
        log.error("Git error in %s: %s", name, exc)
        ui.show_error(
            f"Git error in {name}:\n{exc}\n\n"
            "If this mentions user.name/user.email, run:\n"
            '  git config --global user.name "Your Name"\n'
            '  git config --global user.email "you@example.com"'
        )


def _auto_commit(cfg: dict, repo: str, name: str, branch: str, groups: dict) -> None:
    """Generate messages and commit silently, then open GitHub Desktop."""
    log.info("Auto-commit mode for %s.", name)
    messages = ai_messages.generate_messages(cfg, repo, groups)
    _do_commits(repo, groups, messages)
    _after_commit(cfg, repo, name, auto=True)


def _interactive_commit(cfg: dict, repo: str, name: str, branch: str, groups: dict) -> None:
    """Show the preview dialog — AI messages are fetched in parallel and
    injected into the dialog once ready."""
    log.info("Interactive commit mode for %s.", name)

    # Kick off AI generation in the background BEFORE showing the dialog
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai") as pool:
        ai_future = pool.submit(ai_messages.generate_messages, cfg, repo, groups)

        # Show dialog with loading placeholders immediately
        action = ui.preview_and_commit(name, branch, groups, ai_future=ai_future)

    if not action or action[0] != "commit":
        log.info("User cancelled commit for %s.", name)
        return

    _do_commits(repo, groups, action[1])
    _after_commit(cfg, repo, name, auto=False)


def _do_commits(repo: str, groups: dict, messages: Dict[str, str]) -> None:
    for group, files in groups.items():
        if group == "sensitive":
            continue
        message = messages.get(group, "").strip()
        if not message or not files:
            continue
        try:
            commit_engine.stage_and_commit(repo, files, message)
        except commit_engine.GitError as exc:
            log.error("Commit failed for group '%s': %s", group, exc)
            ui.show_error(f"Commit failed ({group}):\n{exc}")


def _after_commit(cfg: dict, repo: str, name: str, auto: bool) -> None:
    gd_path = cfg.get("github_desktop_path") or None
    opened = commit_engine.open_in_github_desktop(repo, gd_path=gd_path)
    where = "GitHub Desktop is open — review and push when ready." if opened \
        else "Open GitHub Desktop to review and push."
    prefix = "Auto-committed. " if auto else ""
    ui.notify(f"Committed: {name}", prefix + where)
    log.info("Post-commit: %s. GitHub Desktop opened: %s", name, opened)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scan_dirty(cfg: dict) -> List[str]:
    dirty = []
    for repo in commit_engine.list_repos(cfg["projects_dirs"]):
        try:
            if commit_engine.uncommitted_changes(repo):
                dirty.append(repo)
        except commit_engine.GitError:
            pass
    return dirty