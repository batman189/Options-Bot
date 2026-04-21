"""Database storage for learning layer state and trade history queries.
Reads closed trades for performance analysis. Writes threshold adjustments
and regime-fit overrides to learning_state table."""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger("options-bot.learning.storage")

DB_PATH = Path(__file__).parent.parent / "db" / "options_bot.db"


@dataclass
class TradeRecord:
    """A closed trade with all fields needed by the learning layer."""
    trade_id: str
    symbol: str
    setup_type: str
    confidence_score: float
    market_regime: str
    entry_date: str
    exit_reason: str
    pnl_pct: float
    hold_minutes: int
    profile_name: str
    time_of_day: str = ""  # From v2_signal_logs join


@dataclass
class LearningState:
    """Persisted learning state for one profile."""
    profile_name: str
    min_confidence: float
    regime_fit_overrides: dict
    tod_fit_overrides: dict
    paused_by_learning: bool
    adjustment_log: list[dict]


def get_recent_trades(setup_type: str, limit: int = 20) -> list[TradeRecord]:
    """Get last N closed V2 trades matching a setup_type, with time_of_day from signal logs.

    Keyed on trades.setup_type. The param was named profile_name before
    Bug B but the column queried was always setup_type; for single-setup
    profiles (momentum/mean_reversion/catalyst/compression_breakout/
    macro_trend) the names coincide, but aggregator profiles (scalp_0dte,
    swing, tsla_swing) have profile.name != setup_type and the old name
    silently hid that mismatch.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT t.id, t.symbol, t.setup_type, t.confidence_score,
               t.market_regime, t.entry_date, t.exit_reason,
               t.pnl_pct, t.hold_minutes,
               vsl.time_of_day
        FROM trades t
        LEFT JOIN v2_signal_logs vsl ON vsl.trade_id = t.id AND vsl.entered = 1
        WHERE t.status = 'closed'
          AND t.setup_type = ?
          AND t.setup_type IS NOT NULL
        ORDER BY t.exit_date DESC LIMIT ?
    """, (setup_type, limit)).fetchall()
    conn.close()
    return [TradeRecord(
        trade_id=r["id"], symbol=r["symbol"], setup_type=r["setup_type"],
        confidence_score=r["confidence_score"] or 0,
        market_regime=r["market_regime"] or "unknown",
        entry_date=r["entry_date"] or "", exit_reason=r["exit_reason"] or "",
        pnl_pct=r["pnl_pct"] or 0, hold_minutes=r["hold_minutes"] or 0,
        profile_name=setup_type,
        time_of_day=r["time_of_day"] or "",
    ) for r in rows]


def load_learning_state(
    setup_type: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[LearningState]:
    """Load persisted learning state. Returns None if no record exists.

    The learning_state table's primary key column is literally named
    profile_name (legacy, pre-dates aggregator profiles) but the value
    stored is the setup_type — consistent with run_learning() writes
    and the trades.setup_type grouping that drives the 20-trade trigger.

    conn: optional connection — caller is responsible for lifetime. When None,
    opens its own short-lived connection (backwards compatible).
    """
    _owned = conn is None
    if _owned:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM learning_state WHERE profile_name = ?", (setup_type,)
    ).fetchone()
    if _owned:
        conn.close()
    if row is None:
        return None
    tod_raw = row["tod_fit_overrides"] if "tod_fit_overrides" in row.keys() else "{}"
    return LearningState(
        profile_name=row["profile_name"],
        min_confidence=row["min_confidence"],
        regime_fit_overrides=json.loads(row["regime_fit_overrides"] or "{}"),
        tod_fit_overrides=json.loads(tod_raw or "{}"),
        paused_by_learning=bool(row["paused_by_learning"]),
        adjustment_log=json.loads(row["adjustment_log"] or "[]"),
    )


def save_learning_state(
    state: LearningState,
    conn: Optional[sqlite3.Connection] = None,
):
    """Persist learning state to DB. Upsert (insert or update).

    conn: optional connection. When supplied, the caller is responsible
    for commit/rollback and close (used by run_learning's atomic
    load-modify-save transaction). When None, opens and commits its own
    connection (backwards compatible for one-shot callers).
    """
    now = datetime.now(timezone.utc).isoformat()
    _owned = conn is None
    if _owned:
        conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        INSERT INTO learning_state
            (profile_name, min_confidence, regime_fit_overrides, tod_fit_overrides,
             paused_by_learning, adjustment_log, last_adjustment, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(profile_name) DO UPDATE SET
            min_confidence = excluded.min_confidence,
            regime_fit_overrides = excluded.regime_fit_overrides,
            tod_fit_overrides = excluded.tod_fit_overrides,
            paused_by_learning = excluded.paused_by_learning,
            adjustment_log = excluded.adjustment_log,
            last_adjustment = excluded.last_adjustment,
            updated_at = excluded.updated_at
    """, (
        state.profile_name, state.min_confidence,
        json.dumps(state.regime_fit_overrides),
        json.dumps(state.tod_fit_overrides),
        int(state.paused_by_learning),
        json.dumps(state.adjustment_log[-50:]),
        now, now, now,
    ))
    if _owned:
        conn.commit()
        conn.close()
    logger.info(f"Learning state saved for {state.profile_name}: conf={state.min_confidence:.3f}")


@contextmanager
def learning_state_transaction():
    """Open a SQLite connection with BEGIN IMMEDIATE for the full
    load-modify-save sequence on learning_state. Serializes concurrent
    writers across processes — the reserved lock blocks any other
    writer's BEGIN IMMEDIATE until commit or rollback. Use via:

        with learning_state_transaction() as conn:
            state = load_learning_state(name, conn=conn)
            # ... mutate state ...
            save_learning_state(state, conn=conn)

    Exit handles commit/rollback/close. A 30s busy_timeout lets
    contending writers wait rather than error out immediately.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    # isolation_level=None disables Python's implicit transactions so our
    # explicit BEGIN IMMEDIATE takes effect.
    conn.isolation_level = None
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def get_closed_trade_count(setup_type: str) -> int:
    """Count V2 closed trades matching a setup_type (for 20-trade trigger).

    Param renamed from profile_name in Bug B — the query was always
    WHERE setup_type = ? but the old name made callers think they
    could pass profile.name. For scalp_0dte/swing/tsla_swing that
    silently returned 0 and the 20-trade trigger never fired.
    """
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("""
        SELECT COUNT(*) FROM trades
        WHERE status = 'closed' AND setup_type = ? AND setup_type IS NOT NULL
    """, (setup_type,)).fetchone()
    conn.close()
    return row[0] if row else 0
