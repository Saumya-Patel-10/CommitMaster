"""Watches running coding apps and emits session lifecycle events.

Runs a tiny polling loop (psutil.process_iter is ~1 ms of CPU every few
seconds — effectively free).  State machine:

  IDLE  →  ACTIVE  (a watched app opens)
  ACTIVE → ENDING  (all watched apps closed)
  ENDING → ACTIVE  (user re-opens an app)
  ENDING → IDLE    (grace period expires → emits 'session_end' event)
"""
import os
import threading
import time
from typing import Set

import psutil

from commitmaster import commit_engine
from commitmaster.config import ConfigManager
from commitmaster.logger import get

log = get("session_monitor")

IDLE, ACTIVE, ENDING = "idle", "active", "ending"


class SessionMonitor(threading.Thread):
    def __init__(self, config_manager: ConfigManager, events):
        super().__init__(daemon=True, name="session-monitor")
        self._cm = config_manager
        self.events = events          # queue.Queue for main-thread delivery
        self.state = IDLE
        self.paused = False
        self._stop_evt = threading.Event()
        self._last_scan = 0.0
        self._dirty_repos: Set[str] = set()

    # ── Public ────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        self._stop_evt.set()

    def record_dirty_repo(self, path: str) -> None:
        if os.path.isdir(path):
            self._dirty_repos.add(os.path.normpath(path))

    # ── Thread body ───────────────────────────────────────────────────────────

    def run(self) -> None:
        log.info("SessionMonitor started.")
        ended_at: float = 0.0

        while not self._stop_evt.is_set():
            cfg = self._cm.get()          # always use fresh config
            poll = cfg["poll_interval_seconds"]
            grace = cfg["session_end_grace_seconds"]
            scan_interval = cfg["repo_scan_interval_seconds"]

            if not self.paused:
                active = self._coding_app_running(cfg)
                now = time.time()

                if self.state == IDLE and active:
                    log.info("Coding session started.")
                    self.state = ACTIVE
                    self._dirty_repos = set()
                    self._last_scan = 0.0

                elif self.state == ACTIVE:
                    if not active:
                        log.info("All coding apps closed — starting grace period (%ds).", grace)
                        self.state = ENDING
                        ended_at = now
                    elif now - self._last_scan >= scan_interval:
                        self._last_scan = now
                        self._dirty_repos.update(self._scan_dirty_repos(cfg))

                elif self.state == ENDING:
                    if active:
                        log.info("App re-opened — resuming session.")
                        self.state = ACTIVE
                        ended_at = 0.0
                    elif now - ended_at >= grace:
                        repos = sorted(self._dirty_repos | set(self._scan_dirty_repos(cfg)))
                        log.info("Session ended — %d dirty repo(s) detected.", len(repos))
                        self.events.put(("session_end", repos))
                        self.state = IDLE
                        ended_at = 0.0
                        self._dirty_repos = set()

            self._stop_evt.wait(poll)

        log.info("SessionMonitor stopped.")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _coding_app_running(cfg: dict) -> bool:
        watched = {a.lower() for a in cfg["watched_apps"]}
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info["name"]
                if name and name.lower() in watched:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    @staticmethod
    def _scan_dirty_repos(cfg: dict) -> Set[str]:
        dirty: Set[str] = set()
        sensitive = cfg.get("sensitive_patterns", [])
        for repo in commit_engine.list_repos(cfg["projects_dirs"]):
            try:
                if commit_engine.uncommitted_changes(repo):
                    dirty.add(repo)
            except commit_engine.GitError as exc:
                log.debug("Skipping %s: %s", repo, exc)
        return dirty