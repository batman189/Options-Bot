"""Outcome tracker — records signal predictions and resolves them at
fixed time windows (1h, 4h, EOD, next-day) per ARCHITECTURE.md §2.

Public API:
- record_signal(...) — sync writer called from the orchestrator after
  each EntryDecision(should_enter=True). Inserts 4 rows (one per
  window) into signal_outcomes.
- resolve_pending_outcomes(client) — async resolver scanning for ripe
  pending outcomes, fetching current premium via UnifiedDataClient,
  writing the result.
- get_setup_type_accuracy(setup_type, profile_name=None) — sync
  aggregator returning win-rate stats over evaluated outcomes.

Storage: backend/database.py's signal_outcomes table.

Direction correctness convention: for both bullish (call) and bearish
(put) signals, "correct" means evaluated_premium > entry_premium. The
contract type already encodes the direction — a put gains premium when
the underlying drops, which is exactly what bearish predicted. Premium-
movement-in-favor is therefore the universal correctness check; we do
not branch on direction at evaluation time.

This module replaces the legacy learning/learner.py + learning/storage.py
(per ARCHITECTURE.md §7's reuse-decisions table). Those files remain
in place pending the wire-in prompt that retires them.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

import config
from data.unified_client import UnifiedDataClient
from utils.market_calendar import (
    current_or_next_trading_close,
    next_trading_open,
    round_to_next_trading_minute,
)

logger = logging.getLogger("options-bot.learning.outcome_tracker")

WINDOW_LABELS = ("1h", "4h", "EOD", "next_day")
STATUS_PENDING = "pending"
STATUS_EVALUATED = "evaluated"
STATUS_EXPIRED = "expired"
EXPIRY_GRACE_HOURS = 24  # mark pending outcomes 'expired' if more than
                         # this many hours past their evaluate_at without
                         # successful resolution.


def _compute_evaluate_at(predicted_at: datetime, label: str) -> datetime:
    """Return the evaluate_at timestamp for one window label.

    1h/4h: round forward to next trading minute if the naive +1h/+4h
    falls outside RTH. EOD: closest trading session's close strictly
    after predicted_at. next_day: open of the next trading session
    after predicted_at + 1 calendar day (so a Friday signal lands on
    Monday's open).
    """
    if label == "1h":
        return round_to_next_trading_minute(predicted_at + timedelta(hours=1))
    if label == "4h":
        return round_to_next_trading_minute(predicted_at + timedelta(hours=4))
    if label == "EOD":
        return current_or_next_trading_close(predicted_at)
    if label == "next_day":
        return next_trading_open(predicted_at + timedelta(days=1))
    raise ValueError(f"unknown window label: {label!r}")


def record_signal(
    signal_id: str,
    profile_id: str,
    symbol: str,
    setup_type: str,
    direction: str,
    contract_symbol: str,
    contract_strike: float,
    contract_right: str,
    contract_expiration: str,
    entry_premium: float,
    predicted_at: datetime,
) -> None:
    """Insert 4 outcome rows (one per WINDOW_LABEL) for a freshly
    emitted signal.

    Args:
        signal_id: stable identifier linking the 4 outcome rows back to
            the source decision. The orchestrator generates this.
        profile_id: ProfileConfig name or DB id; used to filter the
            accuracy aggregation by profile.
        symbol: underlying ticker.
        setup_type: scanner setup type (momentum, compression_breakout,
            macro_trend, ...).
        direction: "bullish" / "bearish" / "neutral" — scanner vocab,
            stored verbatim.
        contract_symbol: OCC-style or whatever identifier the chain
            adapter uses; the resolver only uses contract_strike +
            contract_right + contract_expiration to look up the
            contract on re-fetch, but contract_symbol is recorded for
            traceability.
        contract_strike, contract_right, contract_expiration: the
            specific contract the signal predicted.
        entry_premium: per-share premium at signal time, in dollars.
        predicted_at: tz-aware datetime; raises ValueError if naive.

    Sync sqlite3 writer — safe to call from a strategy thread. On any
    DB error other than IntegrityError, logs warning and returns
    silently (matches write_v2_signal_log's fail-safe pattern).
    The (signal_id, window_label) UNIQUE constraint handles
    idempotent re-calls — duplicate inserts are absorbed without
    raising.
    """
    if predicted_at.tzinfo is None:
        raise ValueError("predicted_at must be timezone-aware")

    rows = []
    for label in WINDOW_LABELS:
        evaluate_at = _compute_evaluate_at(predicted_at, label)
        rows.append((
            signal_id,
            profile_id,
            symbol,
            setup_type,
            direction,
            contract_symbol,
            contract_strike,
            contract_right,
            contract_expiration,
            entry_premium,
            predicted_at.isoformat(),
            label,
            evaluate_at.isoformat(),
            STATUS_PENDING,
        ))

    try:
        conn = sqlite3.connect(str(config.DB_PATH), timeout=5)
        try:
            conn.executemany(
                """INSERT INTO signal_outcomes
                   (signal_id, profile_id, symbol, setup_type, direction,
                    contract_symbol, contract_strike, contract_right,
                    contract_expiration, entry_premium, predicted_at,
                    window_label, evaluate_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.IntegrityError as e:
        logger.info(
            "record_signal: idempotent re-insert for signal_id=%s (%s)",
            signal_id, e,
        )
    except Exception as e:
        logger.warning(
            "record_signal failed (non-fatal) for signal_id=%s: %s",
            signal_id, e,
        )


def _find_chain_contract(
    chain: list[dict],
    strike: float,
    right_lower: str,
) -> Optional[dict]:
    """Match a contract in the raw chain by strike + lowercased right."""
    for c in chain:
        if c.get("right", "").lower() != right_lower:
            continue
        c_strike = c.get("strike")
        if c_strike is None:
            continue
        if float(c_strike) == float(strike):
            return c
    return None


async def resolve_pending_outcomes(
    client: UnifiedDataClient,
    now: Optional[datetime] = None,
) -> dict:
    """Resolve all pending outcomes whose evaluate_at <= now.

    For each ripe row:
      - Fetch the chain for (contract_symbol's underlying, expiration).
        Note: we use the row's symbol (underlying) for the chain lookup,
        not contract_symbol (which is the OCC option identifier).
      - Locate the contract by (strike, right). chain dicts use
        UPPERCASE right; row's contract_right is lowercase
        (the canonical preset/chain_adapter convention).
      - If found and mid > 0:
          UPDATE row → status='evaluated', evaluated_premium=mid,
          pnl_pct_at_window=(mid - entry_premium) / entry_premium,
          evaluated_at=now.
      - If chain fetch raised, or contract not found, or mid <= 0:
          if now > evaluate_at + EXPIRY_GRACE_HOURS → status='expired'.
          otherwise leave pending and retry next cycle.

    Returns: {'evaluated': N, 'expired': M, 'still_pending': P}.

    Idempotent — only rows with status='pending' are touched.

    Async signature so wire-in can call it from a FastAPI startup
    task. Body uses sync sqlite3; the chain fetch via UnifiedDataClient
    is the dominant blocker (network), so async DB access offers no
    practical gain here.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    summary = {"evaluated": 0, "expired": 0, "still_pending": 0}

    conn = sqlite3.connect(str(config.DB_PATH), timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """SELECT id, symbol, contract_strike, contract_right,
                      contract_expiration, entry_premium, evaluate_at
               FROM signal_outcomes
               WHERE status = ? AND evaluate_at <= ?""",
            (STATUS_PENDING, now.isoformat()),
        )
        ripe = cursor.fetchall()

        for row in ripe:
            try:
                chain = client.get_options_chain(
                    row["symbol"], row["contract_expiration"],
                )
            except Exception as e:
                logger.warning(
                    "resolve: get_options_chain(%s, %s) failed: %s",
                    row["symbol"], row["contract_expiration"], e,
                )
                chain = None

            contract = (
                _find_chain_contract(
                    chain or [],
                    row["contract_strike"],
                    row["contract_right"],
                )
                if chain
                else None
            )

            mid = contract.get("mid") if contract else None
            if contract is not None and mid is not None and mid > 0:
                pnl_pct = (
                    (mid - row["entry_premium"]) / row["entry_premium"]
                )
                conn.execute(
                    """UPDATE signal_outcomes
                       SET status=?, evaluated_premium=?,
                           pnl_pct_at_window=?, evaluated_at=?
                       WHERE id=?""",
                    (
                        STATUS_EVALUATED,
                        float(mid),
                        float(pnl_pct),
                        now.isoformat(),
                        row["id"],
                    ),
                )
                summary["evaluated"] += 1
                continue

            # Could not resolve. Decide expire vs leave-pending.
            evaluate_at = datetime.fromisoformat(row["evaluate_at"])
            grace_deadline = evaluate_at + timedelta(
                hours=EXPIRY_GRACE_HOURS,
            )
            if now > grace_deadline:
                conn.execute(
                    """UPDATE signal_outcomes
                       SET status=?, evaluated_at=?
                       WHERE id=?""",
                    (STATUS_EXPIRED, now.isoformat(), row["id"]),
                )
                summary["expired"] += 1
            else:
                summary["still_pending"] += 1

        conn.commit()
    finally:
        conn.close()

    return summary


def get_setup_type_accuracy(
    setup_type: str,
    profile_name: Optional[str] = None,
) -> dict:
    """Aggregate evaluated outcomes for setup_type, optionally
    filtered by profile_name.

    Returns:
      {
        'setup_type': setup_type,
        'profile_name': profile_name or None,
        'total': N,                       # evaluated outcomes count
        'correct': K,                     # pnl_pct_at_window > 0
        'win_rate': K/N or None if N=0,
        'average_pnl_pct': avg or None,
        'by_window': {
          '1h': {'total': ..., 'correct': ..., 'win_rate': ...,
                 'average_pnl_pct': ...},
          '4h': {...}, 'EOD': {...}, 'next_day': {...},
        }
      }

    Pending and expired rows are excluded from aggregation. On DB
    error, logs warning and returns the same shape with zero counts
    and None aggregates.
    """
    empty_window = {
        "total": 0,
        "correct": 0,
        "win_rate": None,
        "average_pnl_pct": None,
    }
    base = {
        "setup_type": setup_type,
        "profile_name": profile_name,
        "total": 0,
        "correct": 0,
        "win_rate": None,
        "average_pnl_pct": None,
        "by_window": {label: dict(empty_window) for label in WINDOW_LABELS},
    }

    try:
        conn = sqlite3.connect(str(config.DB_PATH), timeout=5)
    except Exception as e:
        logger.warning("get_setup_type_accuracy connect failed: %s", e)
        return base

    try:
        conn.row_factory = sqlite3.Row
        params: list = [STATUS_EVALUATED, setup_type]
        where = "WHERE status = ? AND setup_type = ?"
        if profile_name is not None:
            where += " AND profile_id = ?"
            params.append(profile_name)

        rows = conn.execute(
            f"""SELECT window_label, pnl_pct_at_window
                FROM signal_outcomes {where}""",
            params,
        ).fetchall()
    except Exception as e:
        logger.warning("get_setup_type_accuracy query failed: %s", e)
        return base
    finally:
        conn.close()

    if not rows:
        return base

    total_pnl = 0.0
    total_correct = 0
    by_window_pnls: dict[str, list[float]] = {
        label: [] for label in WINDOW_LABELS
    }
    by_window_correct: dict[str, int] = {
        label: 0 for label in WINDOW_LABELS
    }

    for r in rows:
        pnl = r["pnl_pct_at_window"] or 0.0
        label = r["window_label"]
        total_pnl += pnl
        if pnl > 0:
            total_correct += 1
        if label in by_window_pnls:
            by_window_pnls[label].append(pnl)
            if pnl > 0:
                by_window_correct[label] += 1

    n = len(rows)
    base["total"] = n
    base["correct"] = total_correct
    base["win_rate"] = total_correct / n
    base["average_pnl_pct"] = total_pnl / n

    for label in WINDOW_LABELS:
        pnls = by_window_pnls[label]
        if not pnls:
            continue
        base["by_window"][label] = {
            "total": len(pnls),
            "correct": by_window_correct[label],
            "win_rate": by_window_correct[label] / len(pnls),
            "average_pnl_pct": sum(pnls) / len(pnls),
        }

    return base
