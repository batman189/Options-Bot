"""
Custom logging handler that writes WARNING/ERROR records to the
training_logs SQLite table so the System UI error panel can display them.

Uses synchronous sqlite3 (not aiosqlite) because Python's logging
handlers run in the emitting thread and must not block on async I/O.
Writes are fire-and-forget — a failed DB insert never crashes the bot.
"""

import logging
import sqlite3
from datetime import datetime, timezone


class DatabaseLogHandler(logging.Handler):
    """
    Logging handler that inserts records into the training_logs table.

    Schema (from database.py):
        id       INTEGER PRIMARY KEY AUTOINCREMENT
        model_id TEXT NOT NULL          -- set to 'live' for runtime logs
        timestamp TEXT NOT NULL
        level     TEXT NOT NULL
        message   TEXT NOT NULL
    """

    def __init__(self, db_path: str):
        super().__init__()
        self._db_path = db_path

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            level = record.levelname.lower()  # 'warning' or 'error'

            conn = sqlite3.connect(self._db_path, timeout=2)
            try:
                conn.execute(
                    "INSERT INTO training_logs (model_id, timestamp, level, message) "
                    "VALUES (?, ?, ?, ?)",
                    ("live", ts, level, msg[:2000]),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            # Never let a logging failure crash the bot
            self.handleError(record)
