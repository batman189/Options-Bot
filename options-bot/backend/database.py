"""
SQLite database connection and schema management.
Schema matches PROJECT_ARCHITECTURE.md Section 5a exactly.
"""

import aiosqlite
import logging
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH

logger = logging.getLogger("options-bot.database")

# SQL schema — matches PROJECT_ARCHITECTURE.md Section 5a EXACTLY
SCHEMA_SQL = """
-- Profiles table
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    preset TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    symbols TEXT NOT NULL,
    config TEXT NOT NULL,
    model_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Models table
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    model_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    status TEXT NOT NULL,
    training_started_at TEXT,
    training_completed_at TEXT,
    data_start_date TEXT,
    data_end_date TEXT,
    metrics TEXT,
    feature_names TEXT,
    hyperparameters TEXT,
    created_at TEXT NOT NULL
);

-- Trades table
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    strike REAL NOT NULL,
    expiration TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price REAL,
    entry_date TEXT,
    entry_underlying_price REAL,
    entry_predicted_return REAL,
    entry_ev_pct REAL,
    entry_features TEXT,
    entry_greeks TEXT,
    entry_model_type TEXT,
    exit_price REAL,
    exit_date TEXT,
    exit_underlying_price REAL,
    exit_reason TEXT,
    exit_features TEXT,
    exit_greeks TEXT,
    pnl_dollars REAL,
    pnl_pct REAL,
    actual_return_pct REAL,
    hold_days INTEGER,
    was_day_trade INTEGER DEFAULT 0,
    market_vix REAL,
    market_regime TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- System state table
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Training logs
CREATE TABLE IF NOT EXISTS training_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    profile_id TEXT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


async def get_db() -> aiosqlite.Connection:
    """Get a database connection. Used as a FastAPI dependency."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """Initialize the database schema. Called once at startup."""
    logger.info(f"Initializing database at {DB_PATH}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()

    # Migrations for existing databases
    async with aiosqlite.connect(str(DB_PATH)) as db:
        try:
            await db.execute("ALTER TABLE training_logs ADD COLUMN profile_id TEXT")
            await db.commit()
            logger.info("Migration: added profile_id column to training_logs")
        except Exception:
            pass  # Column already exists

    # Reset stale "training" profiles — if the process was killed mid-training,
    # profiles stay stuck at status='training' forever. Reset them to 'ready'
    # (if they have a model) or 'created' (if they don't).
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, model_id FROM profiles WHERE status = 'training'"
        )
        stuck_profiles = await cursor.fetchall()
        for row in stuck_profiles:
            new_status = "ready" if row["model_id"] else "created"
            await db.execute(
                "UPDATE profiles SET status = ? WHERE id = ?",
                (new_status, row["id"]),
            )
            logger.warning(
                f"Reset stale training status: profile {row['id']} → {new_status}"
            )
        if stuck_profiles:
            await db.commit()
            logger.info(f"Reset {len(stuck_profiles)} profile(s) stuck in 'training' status")

    # Verify tables were created
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        logger.info(f"Database initialized. Tables: {tables}")

        expected_tables = {"models", "profiles", "system_state", "trades", "training_logs"}
        missing = expected_tables - set(tables)
        if missing:
            logger.error(f"MISSING TABLES: {missing}")
            raise RuntimeError(f"Database initialization failed. Missing tables: {missing}")

    logger.info("Database schema verified — all tables present.")
