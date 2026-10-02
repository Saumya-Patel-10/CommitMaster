"""Watches running coding apps and emits session lifecycle events.

Runs a tiny polling loop (psutil.enumerate is ~1ms of CPU every few seconds --
effectively free). While a coding app is open the monitor stays quiet, only
scanning repos for pending changes on the configured interval. When all coding
apps have been closed for `session_end_grace_seconds`, it emits `session_end`.
"""
import os
import threading
import time

import psutil

from commitmaster import commit_engine

IDLE, ACTIVE, ENDING = "idle", "active", "ending"


class SessionMonitor(threading.Thread):
    def __init__(self, cfg, events):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.events = events          # queue.Queue for UI-thread delivery
        self.state = IDLE
        self.paused = False
        self._stop = threading.Event()
        self._last_scan = 0.0
        self._dirty_repos = set()

    def run(self):
        poll = self.cfg["poll_interval_seconds"]
        grace = self.cfg["session_end_grace_seconds"]
        ended_at = None
        while not self._stop.is_set():
            if not self.paused:
                active = self._coding_app_running()
                now = time.time()

                if self.state == IDLE and active:
                    self.state = ACTIVE
                    self._dirty_repos = set()
                    self._last_scan = 0.0

                elif self.state == ACTIVE:
                    if not active:
                        self.state = ENDING
                        ended_at = now
                    elif now - self._last_scan >= self.cfg["repo_scan_interval_seconds"]:
                        self._last_scan = now
                        self._dirty_repos.update(self._scan_dirty_repos())

                elif self.state == ENDING:
                    if active:  # user reopened an app -- back to coding
                        self.state = ACTIVE
                        ended_at = None
                    elif now - ended_at >= grace:
                        repos = sorted(self._dirty_repos | set(self._scan_dirty_repos()))
                        self.events.put(("session_end", repos))
                        self.state = IDLE
                        ended_at = None

            self._stop.wait(poll)

    def stop(self):
        self._stop.set()

    def _coding_app_running(self):
        watched = {a.lower() for a in self.cfg["watched_apps"]}
        for proc in psutil.process_iter(["name"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() in watched:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def _scan_dirty_repos(self):
        dirty = set()
        for repo in commit_engine.list_repos(self.cfg["projects_dirs"]):
            try:
                if commit_engine.uncommitted_changes(repo):
                    dirty.add(repo)
            except commit_engine.GitError:
                continue
        return dirty

    def record_dirty_repo(self, path):
        if os.path.isdir(path):
            self._dirty_repos.add(os.path.normpath(path))