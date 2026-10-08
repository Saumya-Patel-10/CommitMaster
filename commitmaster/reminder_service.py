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
    Background worker thread managing interval-based and IDE-monitoring commit reminders.
    """

    def __init__(
        self,
        user_id: int,
        on_commit_action: Optional[Callable] = None,
        on_need_commit_action: Optional[Callable[[str, List[str]], None]] = None,
        master: Optional[object] = None,
        grace_period_seconds: int = 10,
    ):
        super().__init__(daemon=True, name=f"reminder-service-{user_id}")
        self.user_id = user_id
        self.on_commit_action = on_commit_action
        self.on_need_commit_action = on_need_commit_action
        self.master = master
        self.grace_period_seconds = grace_period_seconds

        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Preferences state
        self.interval_enabled: bool = True
        self.interval_hours: int = 1
        self.interval_minutes: int = 0
        self.app_monitor_enabled: bool = True
        self.only_if_dirty: bool = True
        self.watched_apps: List[str] = list(DEFAULT_WATCHED_IDES)

        # Runtime tracking
        self.last_interval_reminder_time: float = time.time()
        self.monitor_state: str = STATE_IDLE
        self.active_ide_name: str = ""
        self.detected_project_path: str = ""
        self.detected_project_name: str = ""
        self.ide_closed_at: float = 0.0

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
                self.app_monitor_enabled = bool(prefs.get("reminder_app_monitor_enabled", 1))
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
            # Reset interval timer when user updates settings
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

    # ── Main Polling Loop ─────────────────────────────────────────────────────

    def run(self) -> None:
        log.info("ReminderService background thread started for user %d.", self.user_id)

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

                # 2. Process App / IDE Monitoring & Active Project Tracking
                if app_enabled:
                    running_ide, proj_path, proj_name = self._detect_running_ide_and_project(watched)

                    if running_ide:
                        # Keep active project updated while IDE is running
                        if proj_path:
                            self.detected_project_path = proj_path
                            self.detected_project_name = proj_name or commit_engine.repo_name(proj_path)

                    if self.monitor_state == STATE_IDLE and running_ide:
                        self.monitor_state = STATE_ACTIVE
                        self.active_ide_name = running_ide
                        log.info(
                            "IDE detected: %s. Coding session active (detected project: %s).",
                            running_ide, self.detected_project_name or "scanning..."
                        )

                    elif self.monitor_state == STATE_ACTIVE:
                        if not running_ide:
                            self.monitor_state = STATE_ENDING
                            self.ide_closed_at = now
                            log.info(
                                "IDE %s closed. Starting %ds grace period.",
                                self.active_ide_name, self.grace_period_seconds
                            )

                    elif self.monitor_state == STATE_ENDING:
                        if running_ide:
                            # Reopened IDE within grace period
                            self.monitor_state = STATE_ACTIVE
                            self.active_ide_name = running_ide
                            self.ide_closed_at = 0.0
                            log.info("IDE %s reopened. Session resumed.", running_ide)
                        elif now - self.ide_closed_at >= self.grace_period_seconds:
                            # Grace period elapsed: IDE truly closed!
                            self._handle_ide_closed_trigger(only_dirty, self.active_ide_name)
                            self.monitor_state = STATE_IDLE
                            self.active_ide_name = ""
                            self.ide_closed_at = 0.0

            except Exception as exc:
                log.error("Exception in ReminderService loop: %s", exc, exc_info=True)

            # Sleep short duration between poll iterations
            self._stop_event.wait(3.0)

        log.info("ReminderService background thread stopped.")

    # ── Notification Triggers ─────────────────────────────────────────────────

    def _handle_interval_trigger(self, only_dirty: bool, hours: int, mins: int) -> None:
        """Trigger interval reminder toast."""
        dirty_repos = self._scan_user_dirty_repos()
        if only_dirty and not dirty_repos:
            log.debug("Interval reminder due, but all repositories are clean. Skipping toast.")
            return

        time_str_parts = []
        if hours > 0:
            time_str_parts.append(f"{hours}h")
        if mins > 0 or not time_str_parts:
            time_str_parts.append(f"{mins}m")
        time_str = " ".join(time_str_parts)

        repo_cnt = len(dirty_repos)
        if repo_cnt > 0:
            msg = f"It's been {time_str} since your last check. You have uncommitted changes in {repo_cnt} repository{'ies' if repo_cnt > 1 else 'y'}."
        else:
            msg = f"Regular {time_str} interval reminder. Make sure your progress is saved and committed to git!"

        log.info("Dispatching interval reminder toast (dirty repos: %d).", repo_cnt)
        show_toast(
            title="⏰ Time to Commit Your Work!",
            message=msg,
            badge_text="INTERVAL REMINDER",
            dirty_repos=dirty_repos,
            on_commit=self.on_commit_action,
            on_snooze=self.snooze,
            master=self.master,
        )

    def _handle_ide_closed_trigger(self, only_dirty: bool, ide_name: str) -> None:
        """
        Trigger 'Did you commit?' notification when monitored IDE closes.
        • If user selects 'Yes, I did' -> do nothing.
        • If user selects 'No, help me commit' -> open app, navigate to Git Desktop,
          prompt/select repo, and generate AI commit comments.
        """
        dirty_repos = self._scan_user_dirty_repos()
        if only_dirty and not dirty_repos:
            log.info("IDE %s closed, but all repositories are clean. Skipping toast.", ide_name)
            return

        display_name = ide_name.replace(".exe", "").title()
        proj_name = self.detected_project_name
        if not proj_name and dirty_repos:
            proj_name = commit_engine.repo_name(dirty_repos[0])

        proj_desc = f" while working on '{proj_name}'" if proj_name else ""
        repo_cnt = len(dirty_repos)
        if repo_cnt > 0:
            msg = f"You just closed {display_name}{proj_desc}. You have uncommitted changes in {repo_cnt} repository{'ies' if repo_cnt > 1 else 'y'}. Did you commit your work?"
        else:
            msg = f"You just closed {display_name}{proj_desc}. Did you commit your latest work and changes?"

        log.info(
            "Dispatching 'Did you commit?' notification for %s (project: %s, dirty repos: %d).",
            ide_name, proj_name, repo_cnt
        )

        def _on_no_action():
            log.info("User selected 'No, not yet'. Launching Git Desktop commit flow...")
            target_proj = self.detected_project_path or (dirty_repos[0] if dirty_repos else "")
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

        show_toast(
            title="Did you commit your changes?",
            message=msg,
            badge_text="IDE CLOSED",
            dirty_repos=dirty_repos,
            toast_mode="did_you_commit",
            on_yes=lambda: log.info("User confirmed work already committed. Dismissed."),
            on_no=_on_no_action,
            on_snooze=self.snooze,
            master=self.master,
        )

    def trigger_test_notification(self) -> None:
        """Instantly show a test notification so the user can verify its appearance."""
        dirty_repos = self._scan_user_dirty_repos()
        if not dirty_repos:
            dirty_repos = [r"c:\Data\Saumya\Projects\CommitMaster"]

        def _on_test_no():
            if self.on_need_commit_action:
                self.on_need_commit_action(dirty_repos[0], dirty_repos)
            elif self.on_commit_action:
                self.on_commit_action()

        show_toast(
            title="Did you commit your changes?",
            message="You just closed your coding IDE. Did you commit your latest work and changes?",
            badge_text="TEST PREVIEW",
            dirty_repos=dirty_repos,
            toast_mode="did_you_commit",
            on_yes=lambda: log.info("Test preview: user clicked 'Yes'."),
            on_no=_on_test_no,
            on_snooze=self.snooze,
            master=self.master,
        )

    # ── Helpers & Project Discovery ───────────────────────────────────────────

    def _detect_running_ide_and_project(self, watched_lower: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Check if any watched IDE is running and discover what project is being worked on.
        Returns (ide_name, project_path, project_name).
        """
        running_ide = None
        detected_path = None
        detected_name = None

        # Build alias set for watched IDEs
        all_watched = set(watched_lower)
        for preset in IDE_PRESETS:
            preset_exe = preset["exe"].lower()
            if preset_exe in all_watched:
                for alias in preset.get("aliases", []):
                    all_watched.add(alias.lower())

        try:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    name = p.info.get("name")
                    if not name:
                        continue
                    name_lower = name.lower()
                    if name_lower in all_watched:
                        if not running_ide:
                            running_ide = name

                        # Inspect process to detect active project
                        if not detected_path:
                            proc = psutil.Process(p.info["pid"])

                            # Strategy 1: Check process CWD
                            try:
                                cwd = proc.cwd()
                                if cwd and os.path.isdir(cwd) and commit_engine.is_git_repo(cwd):
                                    detected_path = os.path.normpath(cwd)
                                    detected_name = commit_engine.repo_name(cwd)
                            except Exception:
                                pass

                            # Strategy 2: Check command line arguments for folder paths
                            if not detected_path:
                                try:
                                    cmd = proc.cmdline()
                                    for arg in cmd:
                                        clean_arg = arg.strip(' "\'')
                                        if clean_arg and os.path.isdir(clean_arg) and commit_engine.is_git_repo(clean_arg):
                                            detected_path = os.path.normpath(clean_arg)
                                            detected_name = commit_engine.repo_name(clean_arg)
                                            break
                                except Exception:
                                    pass

                            # Strategy 3: Check against user's watched repos in database
                            if not detected_path:
                                try:
                                    watched_repos = db.get_watched_repos(user_id=self.user_id, active_only=True)
                                    cmd_str = " ".join(proc.cmdline() if hasattr(proc, "cmdline") else []).lower()
                                    for wr in watched_repos:
                                        lp = (wr.get("local_path") or "").strip()
                                        if lp and os.path.isdir(lp):
                                            lp_norm = os.path.normpath(lp)
                                            if lp_norm.lower() in cmd_str:
                                                detected_path = lp_norm
                                                detected_name = wr.get("repo_name") or commit_engine.repo_name(lp_norm)
                                                break
                                except Exception:
                                    pass

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as exc:
            log.debug("Process inspection exception: %s", exc)

        return running_ide, detected_path, detected_name

    def _scan_user_dirty_repos(self) -> List[str]:
        """Scan all watched repos for this user and return list of paths with uncommitted changes."""
        dirty: List[str] = []
        candidate_paths: Set[str] = set()

        # 1. Detected project if already known
        if self.detected_project_path and os.path.isdir(self.detected_project_path):
            candidate_paths.add(self.detected_project_path)

        # 2. Repos from watched_repositories table
        try:
            watched = db.get_watched_repos(user_id=self.user_id, active_only=True)
            for w in watched:
                lp = (w.get("local_path") or "").strip()
                if lp and os.path.isdir(lp) and commit_engine.is_git_repo(lp):
                    candidate_paths.add(os.path.normpath(lp))
        except Exception as exc:
            log.debug("Error querying watched repos: %s", exc)

        # 3. Check projects_dirs from preferences
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

        # 4. Current workspace if it's a git repo
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
