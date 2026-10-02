"""Centralised logging for CommitMaster.

All modules should import and use the `log` object from here.
Logs go to:
  1. A rotating file:  <app_dir>/commitmaster.log  (max 1 MB × 3 backups)
  2. stdout / stderr (for --check-now debugging sessions)
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

APP_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_FILE = os.path.join(APP_DIR, "commitmaster.log")

_fmt = logging.Formatter(
    "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(_fmt)
_file_handler.setLevel(logging.DEBUG)

_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_fmt)
_stream_handler.setLevel(logging.INFO)

_root = logging.getLogger("commitmaster")
_root.setLevel(logging.DEBUG)
if not _root.handlers:
    _root.addHandler(_file_handler)
    _root.addHandler(_stream_handler)


def get(name: str) -> logging.Logger:
    """Return a child logger, e.g. get('commit_engine')."""
    return _root.getChild(name)
