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
    hold_minutes INTEGER,
    setup_type TEXT,
    confidence_score REAL,
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

-- Scanner snapshots — written by trading subprocess, read by API
CREATE TABLE IF NOT EXISTS scanner_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    regime TEXT,
    best_setup TEXT,
    best_score REAL,
    momentum_score REAL,
    mean_reversion_score REAL,
    compression_score REAL,
    catalyst_score REAL,
    macro_trend_score REAL,
    momentum_reason TEXT,
    mean_reversion_reason TEXT,
    compression_reason TEXT,
    catalyst_reason TEXT,
    macro_trend_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_scanner_snapshots_time
    ON scanner_snapshots (timestamp DESC);

-- Context snapshots — regime data written by trading subprocess, read by API
CREATE TABLE IF NOT EXISTS context_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    regime TEXT NOT NULL,
    time_of_day TEXT,
    spy_30min_move_pct REAL,
    spy_60min_range_pct REAL,
    spy_30min_reversals INTEGER,
    spy_volume_ratio REAL,
    vix_level REAL,
    vix_intraday_change_pct REAL,
    regime_reason TEXT
);

-- Learning state — threshold adjustments per profile
CREATE TABLE IF NOT EXISTS learning_state (
    profile_name TEXT PRIMARY KEY,
    min_confidence REAL NOT NULL,
    regime_fit_overrides TEXT DEFAULT '{}',
    tod_fit_overrides TEXT DEFAULT '{}',
    paused_by_learning INTEGER DEFAULT 0,
    adjustment_log TEXT DEFAULT '[]',
    last_adjustment TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ── Macro awareness layer ──
-- Scheduled and detected macro events (FOMC, CPI, earnings, etc.)
CREATE TABLE IF NOT EXISTS macro_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_time_et TEXT NOT NULL,            -- Display / LLM input (keeps the ET offset)
    event_time_utc TEXT,                    -- Comparison / filtering (always +00:00)
    impact_level TEXT NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    UNIQUE (symbol, event_type, event_time_et)
);
CREATE INDEX IF NOT EXISTS idx_macro_events_symbol_time
    ON macro_events (symbol, event_time_et);
CREATE INDEX IF NOT EXISTS idx_macro_events_time
    ON macro_events (event_time_et);
-- idx_macro_events_utc is created in the migration block below so existing
-- DBs that predate event_time_utc don't crash on executescript.

CREATE TABLE IF NOT EXISTS macro_catalysts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    catalyst_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    severity REAL NOT NULL,
    expires_at TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    content_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_macro_catalysts_symbol_expiry
    ON macro_catalysts (symbol, expires_at);
-- idx_macro_catalysts_hash is created in the migration block below so it
-- can be added idempotently to existing DBs that predate content_hash.

CREATE TABLE IF NOT EXISTS macro_regime (
    id TEXT PRIMARY KEY,
    risk_tone TEXT NOT NULL,
    vix_context TEXT,
    major_themes_json TEXT DEFAULT '[]',
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS macro_api_usage (
    date_et TEXT PRIMARY KEY,
    call_count INTEGER NOT NULL DEFAULT 0,
    last_call_at TEXT NOT NULL
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

    # Add unrealized P&L and V2 columns to trades table
    async with aiosqlite.connect(str(DB_PATH)) as db:
        for col, col_type in [
            ("unrealized_pnl", "REAL"),
            ("unrealized_pnl_pct", "REAL"),
            ("hold_minutes", "INTEGER"),
            ("setup_type", "TEXT"),
            ("confidence_score", "REAL"),
        ]:
            try:
                await db.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
                await db.commit()
                logger.info(f"Migration: added {col} column to trades")
            except sqlite3.OperationalError:
                pass  # Column already exists
            except Exception as e:
                logger.error(f"Migration failed (trades.{col}): {e}")

    # Add tod_fit_overrides column to learning_state table
    async with aiosqlite.connect(str(DB_PATH)) as db:
        try:
            await db.execute("ALTER TABLE learning_state ADD COLUMN tod_fit_overrides TEXT DEFAULT '{}'")
            await db.commit()
            logger.info("Migration: added tod_fit_overrides column to learning_state")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Add macro_trend columns to scanner_snapshots
    async with aiosqlite.connect(str(DB_PATH)) as db:
        for col, col_type in [("macro_trend_score", "REAL"), ("macro_trend_reason", "TEXT")]:
            try:
                await db.execute(f"ALTER TABLE scanner_snapshots ADD COLUMN {col} {col_type}")
                await db.commit()
            except sqlite3.OperationalError:
                pass

    # Add content_hash column + UNIQUE index to macro_catalysts for dedup.
    # Existing rows have NULL hashes — we backfill them in Python below,
    # dedup duplicates (keeping the newest fetched_at per hash), then
    # create the UNIQUE index. Order matters: backfill BEFORE index so
    # pre-existing dupes don't block the index creation.
    async with aiosqlite.connect(str(DB_PATH)) as db:
        try:
            await db.execute("ALTER TABLE macro_catalysts ADD COLUMN content_hash TEXT")
            await db.commit()
            logger.info("Migration: added content_hash column to macro_catalysts")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Backfill content_hash for any rows that still have NULL, then dedup.
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        try:
            # Import lazily — this module is imported by many callers and we
            # don't want to pull the macro package in at top-level.
            from macro.allowlists import _catalyst_hash
        except Exception as e:
            logger.warning(f"Migration: could not import _catalyst_hash, skipping backfill: {e}")
            _catalyst_hash = None

        if _catalyst_hash is not None:
            cursor = await db.execute(
                "SELECT id, symbol, catalyst_type, summary, fetched_at "
                "FROM macro_catalysts WHERE content_hash IS NULL"
            )
            null_rows = await cursor.fetchall()
            if null_rows:
                # Group by computed hash; keep the row with max fetched_at per group.
                by_hash: dict[str, list[dict]] = {}
                for r in null_rows:
                    h = _catalyst_hash(r["symbol"], r["catalyst_type"], r["summary"])
                    by_hash.setdefault(h, []).append({
                        "id": r["id"], "fetched_at": r["fetched_at"],
                    })
                deleted = 0
                updated = 0
                for h, rows in by_hash.items():
                    rows.sort(key=lambda x: x["fetched_at"] or "", reverse=True)
                    keep = rows[0]
                    drop = rows[1:]
                    for d in drop:
                        await db.execute(
                            "DELETE FROM macro_catalysts WHERE id = ?", (d["id"],)
                        )
                        deleted += 1
                    await db.execute(
                        "UPDATE macro_catalysts SET content_hash = ? WHERE id = ?",
                        (h, keep["id"]),
                    )
                    updated += 1
                await db.commit()
                logger.info(
                    f"Migration: macro_catalysts backfill — hashed {updated} row(s), "
                    f"removed {deleted} duplicate(s)"
                )

    # Now safe to create the UNIQUE index — all rows have unique hashes.
    async with aiosqlite.connect(str(DB_PATH)) as db:
        try:
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_macro_catalysts_hash "
                "ON macro_catalysts (content_hash)"
            )
            await db.commit()
        except sqlite3.OperationalError as e:
            logger.warning(f"Migration: could not create idx_macro_catalysts_hash: {e}")

    # One-time cleanup: purge catalysts that are already past their TTL.
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "DELETE FROM macro_catalysts WHERE expires_at < datetime('now')"
        )
        await db.commit()
        purged = cursor.rowcount if cursor.rowcount is not None else 0
        if purged > 0:
            logger.info(f"Migration: purged {purged} expired macro_catalysts row(s)")

    # Add event_time_utc column to macro_events so filtering is offset-agnostic.
    # Lexicographic comparison of ISO8601 strings with different offsets breaks
    # around DST transitions — a row stored as -04:00 can compare incorrectly to
    # a query bound with -05:00 even when both represent UTC instants that
    # would order correctly. event_time_utc is always +00:00 so lex = instant.
    async with aiosqlite.connect(str(DB_PATH)) as db:
        try:
            await db.execute("ALTER TABLE macro_events ADD COLUMN event_time_utc TEXT")
            await db.commit()
            logger.info("Migration: added event_time_utc column to macro_events")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Backfill event_time_utc for existing rows that have NULL.
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, event_time_et FROM macro_events WHERE event_time_utc IS NULL"
        )
        rows = await cursor.fetchall()
        if rows:
            from datetime import datetime, timezone as _tz
            from zoneinfo import ZoneInfo as _ZoneInfo
            _ET = _ZoneInfo("America/New_York")
            updated = 0
            for r in rows:
                try:
                    dt = datetime.fromisoformat(r["event_time_et"])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=_ET)
                    utc_iso = dt.astimezone(_tz.utc).isoformat()
                except Exception:
                    continue
                await db.execute(
                    "UPDATE macro_events SET event_time_utc = ? WHERE id = ?",
                    (utc_iso, r["id"]),
                )
                updated += 1
            await db.commit()
            logger.info(
                f"Migration: backfilled event_time_utc for {updated} macro_events row(s)"
            )

    # Create the UTC-timestamp index for fast instant-correct filtering.
    async with aiosqlite.connect(str(DB_PATH)) as db:
        try:
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_macro_events_utc "
                "ON macro_events (event_time_utc)"
            )
            await db.commit()
        except sqlite3.OperationalError as e:
            logger.warning(f"Migration: could not create idx_macro_events_utc: {e}")

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

    # Backfill no_entry_after_et_hour + force_close_et_hhmm for existing
    # mean_reversion profiles. Before Cleanup 1/5 these were hardcoded in
    # profiles/mean_reversion.py for SPY only. Now every mean_reversion
    # profile needs the fields set in its config JSON — otherwise
    # apply_config() leaves them at the base-class default of None and
    # the generic time rules silently no-op.
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, config FROM profiles WHERE preset = 'mean_reversion'"
        )
        mr_profiles = await cursor.fetchall()
        patched = 0
        for row in mr_profiles:
            try:
                import json as _json
                cfg = _json.loads(row["config"]) if row["config"] else {}
            except Exception as e:
                logger.warning(
                    f"Migration: could not parse config for profile {row['id']}: {e}"
                )
                continue
            changed = False
            if "no_entry_after_et_hour" not in cfg:
                cfg["no_entry_after_et_hour"] = 14
                changed = True
            if "force_close_et_hhmm" not in cfg:
                cfg["force_close_et_hhmm"] = "15:45"
                changed = True
            if changed:
                await db.execute(
                    "UPDATE profiles SET config = ? WHERE id = ?",
                    (_json.dumps(cfg), row["id"]),
                )
                patched += 1
        if patched:
            await db.commit()
            logger.info(
                f"Migration: backfilled no_entry_after_et_hour/force_close_et_hhmm "
                f"into {patched} mean_reversion profile(s)"
            )

    # Verify tables were created
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        logger.info(f"Database initialized. Tables: {tables}")

        expected_tables = {
            "models", "profiles", "signal_logs", "v2_signal_logs",
            "context_snapshots", "scanner_snapshots", "learning_state",
            "system_state", "trades", "training_logs", "training_queue",
            "macro_events", "macro_catalysts", "macro_regime", "macro_api_usage",
        }
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
