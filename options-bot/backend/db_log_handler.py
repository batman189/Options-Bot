"""
Custom logging handlers that write records to the training_logs SQLite table.

DatabaseLogHandler  — WARNING/ERROR runtime logs (model_id='live')
TrainingLogHandler  — INFO+ training logs, thread-filtered (per training job)

Uses synchronous sqlite3 (not aiosqlite) because Python's logging
handlers run in the emitting thread and must not block on async I/O.
Writes are fire-and-forget — a failed DB insert never crashes the bot.
"""

import logging
import sqlite3
import threading
from datetime import datetime, timezone


class DatabaseLogHandler(logging.Handler):
    """
    Logging handler that inserts WARNING/ERROR records into training_logs.
    Used for runtime error tracking on the System UI error panel.
    """

    def __init__(self, db_path: str):
        super().__init__()
        self._db_path = db_path

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            level = record.levelname.lower()

            conn = sqlite3.connect(self._db_path, timeout=2)
            try:
                conn.execute(
                    "INSERT INTO training_logs (model_id, profile_id, timestamp, level, message) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("live", None, ts, level, msg[:2000]),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            self.handleError(record)


class TrainingLogHandler(logging.Handler):
    """
    Per-training-job handler that captures INFO+ logs from the current thread.

    Thread filtering ensures concurrent training jobs for different profiles
    don't cross-contaminate log entries.
    """

    def __init__(self, db_path: str, profile_id: str):
        super().__init__()
        self._db_path = db_path
        self.profile_id = profile_id
        self._thread_id = threading.current_thread().ident
        self.setLevel(logging.INFO)

    def emit(self, record: logging.LogRecord):
        if threading.current_thread().ident != self._thread_id:
            return
        try:
            msg = self.format(record)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            level = record.levelname.lower()

            conn = sqlite3.connect(self._db_path, timeout=2)
            try:
                conn.execute(
                    "INSERT INTO training_logs (model_id, profile_id, timestamp, level, message) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("training", self.profile_id, ts, level, msg[:2000]),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            self.handleError(record)
