"""
Commit Reminder Service for CommitMaster.

Provides dual-engine reminder tracking:
  1. Interval-based reminders:
     Periodic notifications at user-defined hours & minutes intervals
     to remind them to review and commit changes.
  2. App / IDE monitoring & Project Detection:
     Monitors running desktop processes for IDEs (VS Code, Cursor, Antigravity,
     PyCharm, IntelliJ, etc.). When an IDE starts, the system tracks the coding
     session and scans running processes to detect what project the user is working on.
     When the IDE closes, it checks uncommitted changes and triggers a "Did you commit?"
     notification.
     • If user says "Yes, I did" -> do nothing.
     • If user says "No, help me commit" -> opens app, takes user to Git Desktop,
       prompts/selects the detected repository, generates AI commit messages,
       and handles preview opt-in or 10-second auto-commit review countdown.
"""
import os
import threading
import time
from typing import Callable, Dict, List, Optional, Set, Tuple

import psutil

from commitmaster import commit_engine
from commitmaster import database as db
from commitmaster.config import load_config
from commitmaster.logger import get
from commitmaster.notification_toast import show_toast

log = get("reminder_service")

# Curated list of popular coding IDEs & editors
IDE_PRESETS = [
    {"name": "Visual Studio Code", "exe": "Code.exe", "aliases": ["code.exe"], "icon": "🟦"},
    {"name": "Cursor", "exe": "Cursor.exe", "aliases": ["cursor.exe"], "icon": "🟣"},
    {"name": "Antigravity IDE", "exe": "Antigravity IDE.exe", "aliases": ["Antigravity.exe", "antigravity ide.exe"], "icon": "🔵"},
    {"name": "PyCharm", "exe": "pycharm64.exe", "aliases": ["pycharm.exe"], "icon": "🟢"},
    {"name": "IntelliJ IDEA", "exe": "idea64.exe", "aliases": ["idea.exe"], "icon": "🔴"},
    {"name": "Sublime Text", "exe": "sublime_text.exe", "aliases": ["sublime_text.exe"], "icon": "🟠"},
    {"name": "Visual Studio", "exe": "devenv.exe", "aliases": ["devenv.exe"], "icon": "🟣"},
    {"name": "WebStorm", "exe": "webstorm64.exe", "aliases": ["webstorm.exe"], "icon": "🔷"},
    {"name": "CLion", "exe": "clion64.exe", "aliases": ["clion.exe"], "icon": "🟩"},
    {"name": "Zed", "exe": "zed.exe", "aliases": ["zed.exe"], "icon": "⚡"},
    {"name": "Bionic", "exe": "Bionic.exe", "aliases": ["bionic.exe"], "icon": "🤖"},
    {"name": "LM Studio", "exe": "LM Studio.exe", "aliases": ["lm studio.exe"], "icon": "🦙"},
]

DEFAULT_WATCHED_IDES = [item["exe"] for item in IDE_PRESETS]

STATE_IDLE = "idle"
STATE_ACTIVE = "active"
STATE_ENDING = "ending"


def get_running_ide_processes() -> Set[str]:
    """Return set of lower-case process names currently active on the desktop."""
    running = set()
    try:
        for p in psutil.process_iter(["name"]):
            name = p.info.get("name")
            if name:
                running.add(name.lower())
    except Exception:
        pass
    return running


class ReminderService(threading.Thread):
    """
    Background worker thread managing interval-based and IDE monitoring commit reminders.
    """

    def __init__(
        self,
        user_id: int,
        on_commit_action: Optional[Callable] = None,
        on_need_commit_action: Optional[Callable[[str, List[str]], None]] = None,
        master: Optional[object] = None,
        grace_period_seconds: int = 2,
    ):
        super().__init__(daemon=True, name=f"reminder-service-{user_id}")
        self.user_id = user_id
        self.on_commit_action = on_commit_action
        self.on_need_commit_action = on_need_commit_action
        self.master = master
        self.grace_period_seconds = max(1, min(grace_period_seconds, 3))

        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Preferences state
        self.interval_enabled: bool = True
        self.interval_hours: int = 1
        self.interval_minutes: int = 0
        self.app_monitor_enabled: bool = True
        self.only_if_dirty: bool = True
        self.watched_apps: List[str] = list(DEFAULT_WATCHED_IDES)

        # Multi-IDE session tracking: maps lower-case exe name -> info dict
        self._tracked_ide_sessions: Dict[str, Dict[str, Any]] = {}
        self.last_interval_reminder_time: float = time.time()
        self.detected_project_path: str = ""
        self.detected_project_name: str = ""
        self.monitor_state: str = STATE_IDLE
        self._initial_check_done: bool = False

        # Load initial preferences
        self.reload_preferences()

    # ── Configuration & Control ───────────────────────────────────────────────

    def reload_preferences(self) -> None:
        """Fetch latest reminder preferences from DB and config."""
        try:
            prefs = db.get_preferences(self.user_id) or {}
            cfg = load_config()

            with self._lock:
                self.interval_enabled = bool(prefs.get("reminder_interval_enabled", 1))
                self.interval_hours = int(prefs.get("reminder_interval_hours", 1))
                self.interval_minutes = int(prefs.get("reminder_interval_minutes", 0))
                # IDE & Coding App monitoring is ALWAYS ON
                self.app_monitor_enabled = True
                self.only_if_dirty = bool(prefs.get("reminder_only_if_dirty", 1))

                # Watched apps from DB preference or config
                import json
                db_apps = []
                raw_db_apps = prefs.get("watched_apps")
                if raw_db_apps:
                    try:
                        db_apps = json.loads(raw_db_apps)
                    except Exception:
                        pass
                apps_from_cfg = cfg.get("watched_apps") or []
                combined = list(dict.fromkeys(db_apps + apps_from_cfg + DEFAULT_WATCHED_IDES))
                self.watched_apps = combined

            log.debug(
                "ReminderService config reloaded: interval=%s (%dh %dm), app_monitor=%s, only_dirty=%s, watched=%d apps",
                self.interval_enabled, self.interval_hours, self.interval_minutes,
                self.app_monitor_enabled, self.only_if_dirty, len(self.watched_apps)
            )
        except Exception as exc:
            log.warning("Could not reload reminder preferences: %s", exc)

    def update_preferences(
        self,
        interval_enabled: Optional[bool] = None,
        interval_hours: Optional[int] = None,
        interval_minutes: Optional[int] = None,
        app_monitor_enabled: Optional[bool] = None,
        only_if_dirty: Optional[bool] = None,
        watched_apps: Optional[List[str]] = None,
    ) -> None:
        """Update settings dynamically while service is running."""
        with self._lock:
            if interval_enabled is not None:
                self.interval_enabled = interval_enabled
            if interval_hours is not None:
                self.interval_hours = interval_hours
            if interval_minutes is not None:
                self.interval_minutes = interval_minutes
            if app_monitor_enabled is not None:
                self.app_monitor_enabled = app_monitor_enabled
            if only_if_dirty is not None:
                self.only_if_dirty = only_if_dirty
            if watched_apps is not None:
                self.watched_apps = watched_apps
            self.last_interval_reminder_time = time.time()

        log.info("ReminderService preferences updated dynamically.")

    def snooze(self, minutes: int = 15) -> None:
        """Delay next interval reminder by X minutes."""
        with self._lock:
            self.last_interval_reminder_time = time.time() + (minutes * 60)
        log.info("Reminder snoozed for %d minutes.", minutes)

    def stop(self) -> None:
        """Signal background thread to exit."""
        self._stop_event.set()

    # ── Notification Message Formatter ────────────────────────────────────────

    def _format_dirty_repo_msg(self, dirty_repos: List[str]) -> str:
        """
        Produce user-specified exact format:
        "There are some files which haven't been commit in _____ repo"
        """
        repo_names = [commit_engine.repo_name(p) for p in dirty_repos]
        unique_names = list(dict.fromkeys(repo_names))
        if not unique_names:
            repo_str = "your"
        elif len(unique_names) == 1:
            repo_str = unique_names[0]
        else:
            repo_str = ", ".join(unique_names)
        return f"There are some files which haven't been commit in {repo_str} repo"

    # ── Main Polling Loop ─────────────────────────────────────────────────────

    def run(self) -> None:
        log.info("ReminderService background thread started for user %d.", self.user_id)

        # Baseline running IDEs on startup
        with self._lock:
            watched = [a.lower() for a in self.watched_apps]
        self._tracked_ide_sessions = self._get_running_ide_map(watched)

        # Step 1: Initial startup check — alert user immediately if uncommitted changes exist
        time.sleep(1.5)
        if not self._stop_event.is_set():
            self._check_and_notify_initial_uncommitted()

        while not self._stop_event.is_set():
            try:
                now = time.time()

                with self._lock:
                    int_enabled = self.interval_enabled
                    int_hours = self.interval_hours
                    int_mins = self.interval_minutes
                    app_enabled = self.app_monitor_enabled
                    only_dirty = self.only_if_dirty
                    watched = [a.lower() for a in self.watched_apps]

                # 1. Process Interval-based reminders
                if int_enabled:
                    total_interval_seconds = max((int_hours * 3600) + (int_mins * 60), 60)
                    if now - self.last_interval_reminder_time >= total_interval_seconds:
                        self._handle_interval_trigger(only_dirty, int_hours, int_mins)
                        with self._lock:
                            self.last_interval_reminder_time = time.time()

                # 2. Process App / IDE Monitoring (Independent per-IDE tracking)
                if app_enabled:
                    current_running = self._get_running_ide_map(watched)

                    # Detect newly launched IDEs
                    for ide_k, info in current_running.items():
                        if ide_k not in self._tracked_ide_sessions:
                            self._tracked_ide_sessions[ide_k] = info
                            log.info("IDE started: %s (%s). Session active.", info["name"], ide_k)
                        else:
                            # Keep detected project updated
                            if info.get("project_path"):
                                self._tracked_ide_sessions[ide_k]["project_path"] = info["project_path"]
                                self._tracked_ide_sessions[ide_k]["project_name"] = info["project_name"]
                                self.detected_project_path = info["project_path"]
                                self.detected_project_name = info["project_name"]

                    # Detect closed IDEs (e.g. VS Code closed even if Antigravity is running)
                    closed_ides = []
                    for ide_k, info in list(self._tracked_ide_sessions.items()):
                        if ide_k not in current_running:
                            closed_ides.append((ide_k, info))

                    for ide_k, info in closed_ides:
                        self._tracked_ide_sessions.pop(ide_k, None)
                        log.info("IDE closed: %s (%s). Triggering uncommitted check.", info["name"], ide_k)
                        self._handle_ide_closed_trigger(
                            only_dirty=only_dirty,
                            ide_name=info["name"],
                            project_path=info.get("project_path"),
                            project_name=info.get("project_name")
                        )

            except Exception as exc:
                log.error("Exception in ReminderService loop: %s", exc, exc_info=True)

            self._stop_event.wait(2.0)

        log.info("ReminderService background thread stopped.")

    # ── Notification Triggers ─────────────────────────────────────────────────

    def _check_and_notify_initial_uncommitted(self) -> None:
        """On app start, alert user if any linked repository has uncommitted changes."""
        try:
            dirty_repos = self._scan_user_dirty_repos()
            if dirty_repos:
                msg = self._format_dirty_repo_msg(dirty_repos)
                log.info("Initial startup check: uncommitted changes in %s", dirty_repos)
                show_toast(
                    title="CommitMaster Reminder",
                    message=msg,
                    badge_text="REMINDER",
                    dirty_repos=dirty_repos,
                    toast_mode="did_you_commit",
                    on_yes=lambda: log.info("User acknowledged initial reminder."),
                    on_no=lambda: self._launch_commit_flow(dirty_repos[0], dirty_repos),
                    on_snooze=self.snooze,
                    master=self.master,
                )
        except Exception as exc:
            log.debug("Initial uncommitted check failed: %s", exc)

    def _handle_interval_trigger(self, only_dirty: bool, hours: int, mins: int) -> None:
        """Trigger interval reminder toast."""
        dirty_repos = self._scan_user_dirty_repos()
        if only_dirty and not dirty_repos:
            log.debug("Interval reminder due, but all repositories are clean. Skipping toast.")
            return

        if dirty_repos:
            msg = self._format_dirty_repo_msg(dirty_repos)
        else:
            time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
            msg = f"Regular {time_str} interval reminder. Make sure your progress is saved and committed to git!"

        log.info("Dispatching interval reminder toast (dirty repos: %d).", len(dirty_repos))
        show_toast(
            title="⏰ Time to Commit Your Work!",
            message=msg,
            badge_text="INTERVAL REMINDER",
            dirty_repos=dirty_repos,
            toast_mode="did_you_commit",
            on_yes=lambda: log.info("Interval reminder: user confirmed work committed."),
            on_no=lambda: self._launch_commit_flow(dirty_repos[0] if dirty_repos else "", dirty_repos),
            on_snooze=self.snooze,
            master=self.master,
        )

    def _handle_ide_closed_trigger(
        self,
        only_dirty: bool,
        ide_name: str,
        project_path: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> None:
        """
        Trigger 'Did you commit?' notification when monitored IDE closes.
        """
        dirty_repos = self._scan_user_dirty_repos(project_path)
        if only_dirty and not dirty_repos:
            log.info("IDE %s closed, but all repositories are clean. Skipping toast.", ide_name)
            return

        display_name = ide_name.replace(".exe", "").title()
        if dirty_repos:
            msg = self._format_dirty_repo_msg(dirty_repos)
        else:
            msg = f"You just closed {display_name}. Did you commit your latest work and changes?"

        log.info(
            "Dispatching 'Did you commit?' notification for %s (dirty repos: %s).",
            ide_name, dirty_repos
        )

        show_toast(
            title="Did you commit your changes?",
            message=msg,
            badge_text="IDE CLOSED",
            dirty_repos=dirty_repos,
            toast_mode="did_you_commit",
            on_yes=lambda: log.info("User confirmed work already committed. Dismissed."),
            on_no=lambda: self._launch_commit_flow(project_path or (dirty_repos[0] if dirty_repos else ""), dirty_repos),
            on_snooze=self.snooze,
            master=self.master,
        )

    def _launch_commit_flow(self, target_proj: str, dirty_repos: List[str]) -> None:
        """Launch Git Desktop commit flow for target repo."""
        log.info("Launching Git Desktop commit flow for repo: %s", target_proj)
        if self.on_need_commit_action:
            try:
                self.on_need_commit_action(target_proj, dirty_repos)
            except Exception as exc:
                log.error("on_need_commit_action failed: %s", exc)
        elif self.on_commit_action:
            try:
                self.on_commit_action()
            except Exception as exc:
                log.error("on_commit_action failed: %s", exc)

    def trigger_test_notification(self) -> None:
        """Instantly show a test notification so the user can verify its appearance."""
        dirty_repos = self._scan_user_dirty_repos()
        if not dirty_repos:
            dirty_repos = [r"c:\Data\Saumya\Projects\CommitMaster"]

        msg = self._format_dirty_repo_msg(dirty_repos)
        show_toast(
            title="Did you commit your changes?",
            message=msg,
            badge_text="TEST PREVIEW",
            dirty_repos=dirty_repos,
            toast_mode="did_you_commit",
            on_yes=lambda: log.info("Test preview: user clicked 'Yes'."),
            on_no=lambda: self._launch_commit_flow(dirty_repos[0], dirty_repos),
            on_snooze=self.snooze,
            master=self.master,
        )

    # ── Helpers & Project Discovery ───────────────────────────────────────────

    def _get_running_ide_map(self, watched_lower: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Scan all running desktop processes and build map of currently active IDEs.
        Returns dict keyed by canonical lower-case executable (e.g. 'code.exe').
        """
        running: Dict[str, Dict[str, Any]] = {}
        all_watched = set(watched_lower)
        preset_map = {}
        for preset in IDE_PRESETS:
            p_exe = preset["exe"].lower()
            preset_map[p_exe] = preset["name"]
            if p_exe in all_watched:
                for alias in preset.get("aliases", []):
                    all_watched.add(alias.lower())
                    preset_map[alias.lower()] = preset["name"]

        try:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    name = p.info.get("name")
                    if not name:
                        continue
                    name_lower = name.lower()
                    if name_lower in all_watched:
                        disp_name = preset_map.get(name_lower, name)
                        if name_lower not in running:
                            proj_path, proj_name = None, None
                            try:
                                proc = psutil.Process(p.info["pid"])
                                # Strategy 1: Check process CWD
                                try:
                                    cwd = proc.cwd()
                                    if cwd and os.path.isdir(cwd) and commit_engine.is_git_repo(cwd):
                                        proj_path = os.path.normpath(cwd)
                                        proj_name = commit_engine.repo_name(cwd)
                                except Exception:
                                    pass

                                # Strategy 2: Check command line arguments for folder paths
                                if not proj_path:
                                    try:
                                        cmd = proc.cmdline()
                                        for arg in cmd:
                                            clean_arg = arg.strip(' "\'')
                                            if clean_arg and os.path.isdir(clean_arg) and commit_engine.is_git_repo(clean_arg):
                                                proj_path = os.path.normpath(clean_arg)
                                                proj_name = commit_engine.repo_name(clean_arg)
                                                break
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                            running[name_lower] = {
                                "exe": name,
                                "name": disp_name,
                                "project_path": proj_path,
                                "project_name": proj_name,
                            }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as exc:
            log.debug("Process iteration exception: %s", exc)

        return running

    def _scan_user_dirty_repos(self, specific_project: Optional[str] = None) -> List[str]:
        """
        Scan all repositories linked to this user and return paths with uncommitted changes.
        """
        dirty: List[str] = []
        candidate_paths: Set[str] = set()

        # 1. Specific project or recently detected project
        if specific_project and os.path.isdir(specific_project) and commit_engine.is_git_repo(specific_project):
            candidate_paths.add(os.path.normpath(specific_project))
        if self.detected_project_path and os.path.isdir(self.detected_project_path) and commit_engine.is_git_repo(self.detected_project_path):
            candidate_paths.add(os.path.normpath(self.detected_project_path))

        # 2. ALL repos from watched_repositories table (active_only=False to include all linked repos)
        try:
            watched = db.get_watched_repos(user_id=self.user_id, active_only=False)
            for w in watched:
                lp = (w.get("local_path") or "").strip()
                if lp and os.path.isdir(lp) and commit_engine.is_git_repo(lp):
                    candidate_paths.add(os.path.normpath(lp))
        except Exception as exc:
            log.debug("Error querying watched repos: %s", exc)

        # 3. Check repo_github_accounts table
        try:
            conn = db.get_conn()
            cur = conn.cursor()
            rows = cur.execute("SELECT repo_path FROM repo_github_accounts WHERE user_id = ?", (self.user_id,)).fetchall()
            for r in rows:
                rp = (r["repo_path"] if hasattr(r, "__getitem__") else r[0]) or ""
                if rp and os.path.isdir(rp) and commit_engine.is_git_repo(rp):
                    candidate_paths.add(os.path.normpath(rp))
        except Exception as exc:
            log.debug("Error querying repo_github_accounts: %s", exc)

        # 4. Check user preferences projects_dirs
        try:
            import json
            prefs = db.get_preferences(self.user_id) or {}
            raw_dirs = prefs.get("projects_dirs", "[]")
            dirs_list = json.loads(raw_dirs) if isinstance(raw_dirs, str) else []
            for d in dirs_list:
                if os.path.isdir(d):
                    for entry in os.scandir(d):
                        if entry.is_dir() and commit_engine.is_git_repo(entry.path):
                            candidate_paths.add(os.path.normpath(entry.path))
        except Exception as exc:
            log.debug("Error checking projects_dirs: %s", exc)

        # 5. Current workspace
        try:
            cwd = os.getcwd()
            if commit_engine.is_git_repo(cwd):
                candidate_paths.add(os.path.normpath(cwd))
        except Exception:
            pass

        # Check for uncommitted changes in candidate paths
        for p in candidate_paths:
            try:
                if commit_engine.uncommitted_changes(p):
                    dirty.append(p)
            except Exception as exc:
                log.debug("Error checking repo %s: %s", p, exc)

        return sorted(dirty)
