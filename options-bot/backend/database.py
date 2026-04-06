"""
SQLite database connection and schema management.
Schema matches PROJECT_ARCHITECTURE.md Section 5a exactly.
"""

import sqlite3
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
    exit_greeks TEXT,
    pnl_dollars REAL,
    pnl_pct REAL,
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

-- Signal logs (Phase 4.5)
-- One row per trading iteration. Shows why the bot did or didn't trade.
CREATE TABLE IF NOT EXISTS signal_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    underlying_price REAL,
    predicted_return REAL,
    predictor_type TEXT,
    step_stopped_at REAL,
    stop_reason TEXT,
    entered INTEGER DEFAULT 0,
    trade_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_signal_logs_profile_time
    ON signal_logs (profile_id, timestamp DESC);

-- Training queue (Phase B — feedback loop)
-- Completed trades queued for model retraining. Consumed by walk-forward or incremental trainer.
CREATE TABLE IF NOT EXISTS training_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    entry_features TEXT,
    predicted_return REAL,
    actual_return_pct REAL,
    queued_at TEXT NOT NULL,
    consumed INTEGER DEFAULT 0,
    consumed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_training_queue_pending
    ON training_queue (profile_id, consumed);

-- V2 Signal logs — one row per scorer evaluation, every trading iteration
-- Records scanner output, scorer factor breakdown, and entry decision
CREATE TABLE IF NOT EXISTS v2_signal_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    setup_type TEXT,
    setup_score REAL,
    confidence_score REAL,
    raw_score REAL,
    regime TEXT,
    regime_reason TEXT,
    time_of_day TEXT,
    signal_clarity REAL,
    regime_fit REAL,
    ivr REAL,
    institutional_flow REAL,
    historical_perf REAL,
    sentiment REAL,
    time_of_day_score REAL,
    threshold_label TEXT,
    entered INTEGER DEFAULT 0,
    trade_id TEXT,
    block_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_v2_signal_logs_profile_time
    ON v2_signal_logs (profile_name, timestamp DESC);
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
        # Enable WAL mode for concurrent read/write access (prevents "database is locked")
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(SCHEMA_SQL)
        await db.commit()

    # Migrations for existing databases
    async with aiosqlite.connect(str(DB_PATH)) as db:
        try:
            await db.execute("ALTER TABLE training_logs ADD COLUMN profile_id TEXT")
            await db.commit()
            logger.info("Migration: added profile_id column to training_logs")
        except sqlite3.OperationalError:
            pass  # Column already exists
        except Exception as e:
            logger.error(f"Migration failed (training_logs.profile_id): {e}")

    # Add error_reason column to profiles table
    async with aiosqlite.connect(str(DB_PATH)) as db:
        try:
            await db.execute("ALTER TABLE profiles ADD COLUMN error_reason TEXT")
            await db.commit()
            logger.info("Migration: added error_reason column to profiles")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Add unrealized P&L columns to trades table
    async with aiosqlite.connect(str(DB_PATH)) as db:
        for col, col_type in [
            ("unrealized_pnl", "REAL"),
            ("unrealized_pnl_pct", "REAL"),
        ]:
            try:
                await db.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
                await db.commit()
                logger.info(f"Migration: added {col} column to trades")
            except sqlite3.OperationalError:
                pass  # Column already exists
            except Exception as e:
                logger.error(f"Migration failed (trades.{col}): {e}")

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

        expected_tables = {"models", "profiles", "signal_logs", "system_state", "trades", "training_logs", "training_queue"}
        missing = expected_tables - set(tables)
        if missing:
            logger.error(f"MISSING TABLES: {missing}")
            raise RuntimeError(f"Database initialization failed. Missing tables: {missing}")

    logger.info("Database schema verified — all tables present.")


def write_v2_signal_log(data: dict):
    """Write one V2 signal log entry. Synchronous (called from strategy threads).

    Args:
        data: dict with keys matching v2_signal_logs columns.
              Missing keys default to None. 'entered' defaults to 0.
    """
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute(
            """INSERT INTO v2_signal_logs
               (timestamp, profile_name, symbol, setup_type, setup_score,
                confidence_score, raw_score, regime, regime_reason, time_of_day,
                signal_clarity, regime_fit, ivr, institutional_flow,
                historical_perf, sentiment, time_of_day_score,
                threshold_label, entered, trade_id, block_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("timestamp"),
                data.get("profile_name"),
                data.get("symbol"),
                data.get("setup_type"),
                data.get("setup_score"),
                data.get("confidence_score"),
                data.get("raw_score"),
                data.get("regime"),
                data.get("regime_reason"),
                data.get("time_of_day"),
                data.get("signal_clarity"),
                data.get("regime_fit"),
                data.get("ivr"),
                data.get("institutional_flow"),
                data.get("historical_perf"),
                data.get("sentiment"),
                data.get("time_of_day_score"),
                data.get("threshold_label"),
                1 if data.get("entered") else 0,
                data.get("trade_id"),
                data.get("block_reason"),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"write_v2_signal_log failed (non-fatal): {e}")
