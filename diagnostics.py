"""Privacy-preserving rotating diagnostics for the windowed application."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import re
import sys
import threading

import config as cfg

_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"(?i)(x-goog-api-key[=: ]+)[^\s,;]+"),
    re.compile(r"(?i)([?&]key=)[^&\s]+"),
)


def redact(value):
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: (match.group(1) if match.lastindex else "")
                           + "[REDACTED]", text)
    return text


class _RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def redirect_null_streams():
    """Point missing std streams at the log file.

    Windowed PyInstaller builds run with sys.stdout/sys.stderr set to
    None; any third-party write to them (tqdm bars, warnings) then dies
    with a cryptic "'NoneType' object has no attribute 'write'". Logs
    keep the evidence instead of crashing.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        cfg.LOG_DIR.mkdir(parents=True, exist_ok=True)
        stream = open(cfg.LOG_DIR / "stderr.log", "a", encoding="utf-8")
    except OSError:
        stream = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def setup():
    root = logging.getLogger("wordarc")
    if root.handlers:
        return root
    try:
        cfg.LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            cfg.LOG_DIR / "wordarc.log", maxBytes=1_000_000, backupCount=3,
            encoding="utf-8")
    except OSError:
        # Logging must never prevent the desktop application from starting.
        handler = logging.NullHandler()
    handler.setFormatter(_RedactingFormatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    previous = sys.excepthook

    def report(exc_type, exc, tb):
        root.exception("unhandled error", exc_info=(exc_type, exc, tb))
        previous(exc_type, exc, tb)

    sys.excepthook = report

    def report_thread(args):
        # A worker thread that dies takes its traceback with it: whatever it
        # was feeding sits on its last message and the log stays empty.
        root.exception("unhandled error in %s",
                       getattr(args.thread, "name", "a worker thread"),
                       exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = report_thread
    redirect_null_streams()
    return root
