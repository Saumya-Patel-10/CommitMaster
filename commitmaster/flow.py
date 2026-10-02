"""End-of-session flow: ask -> inspect repos -> AI messages -> preview -> commit."""
import concurrent.futures

from commitmaster import ai_messages, commit_engine, ui


def handle_session_end(cfg, known_dirty_repos):
    """Runs in a worker thread; all UI calls are pushed to their own UI thread."""
    ui.run_in_ui_thread(lambda: _flow(cfg, known_dirty_repos))


def _flow(cfg, known_dirty_repos):
    if not ui.ask_done_coding():
        ui.notify("CommitMaster", "No problem — I'll check in after your next session.")
        return

    repos = sorted(set(known_dirty_repos) | set(_fresh_dirty(cfg)))
    if not repos:
        ui.show_info("All your repositories are clean. Nothing to commit — great job! 🎉")
        return

    chosen = ui.pick_repo(repos)
    for repo in chosen:
        _commit_repo(cfg, repo)


def _fresh_dirty(cfg):
    dirty = []
    for repo in commit_engine.list_repos(cfg["projects_dirs"]):
        try:
            if commit_engine.uncommitted_changes(repo):
                dirty.append(repo)
        except commit_engine.GitError:
            continue
    return dirty


def _commit_repo(cfg, repo):
    name = commit_engine.repo_name(repo)
    try:
        changes = commit_engine.uncommitted_changes(repo)
        groups = commit_engine.build_groups(changes)
        if not groups:
            ui.show_info(f"{name}: nothing to commit.")
            return
        branch = commit_engine.current_branch(repo)

        if cfg["auto_commit"]:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(ai_messages.generate_messages, cfg, repo, groups)
                messages = future.result()
            _do_commit(cfg, repo, groups, messages)
            _after_commit(cfg, repo, name, auto=True)
            return

        # Generate messages while the preview window is already usable:
        # show deterministic placeholders, then update them when AI replies.
        action = ui.preview_and_commit(name, branch, _with_fallbacks(groups))
        if not action or action[0] != "commit":
            return
        _do_commit(cfg, repo, groups, action[1])
        _after_commit(cfg, repo, name, auto=False)
    except commit_engine.GitError as exc:
        ui.show_info(f"{name}: git error —\n{exc}\n\n"
                     "If this mentions user.name/user.email, run:\n"
                     '  git config --global user.name "Your Name"\n'
                     '  git config --global user.email "you@example.com"')


def _with_fallbacks(groups):
    from commitmaster.ai_messages import FALLBACK_MESSAGES
    return {g: FALLBACK_MESSAGES.get(g, "chore: update files") for g in groups}


def _do_commit(cfg, repo, groups, messages):
    for group, files in groups.items():
        if group == "sensitive":
            continue  # never auto-stage secrets
        message = messages.get(group)
        if not message:
            continue
        if files:
            commit_engine.stage_and_commit(repo, files, message)


def _after_commit(cfg, repo, name, auto):
    opened = commit_engine.open_in_github_desktop(repo)
    where = "GitHub Desktop is open for you to review and push." if opened \
        else "Open GitHub Desktop to review and push."
    ui.notify(f"Committed: {name}",
              ("Auto-committed. " if auto else "") + where)