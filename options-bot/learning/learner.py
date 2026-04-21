"""Learning and adaptation layer — adjusts thresholds based on performance.

Runs after market close each day AND after every 20 closed trades.
Does NOT retrain ML models. Adjusts weights and thresholds only.

Adjustments (from architecture doc):
  - min_confidence per profile: raise 0.05 if expectancy negative, lower 0.02 if strongly positive
  - Regime fit weights: reduce if setup type has been losing in that regime
  - Auto-pause: win rate < 35% over 20 trades -> pause, require manual restart
  - All changes logged with old value, new value, reason, timestamp
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from learning.storage import (
    get_recent_trades, load_learning_state, save_learning_state,
    learning_state_transaction,
    LearningState, TradeRecord,
)


# In-process serialization for run_learning. Cross-process serialization
# is handled by the BEGIN IMMEDIATE transaction inside
# learning_state_transaction(); this lock just prevents two threads in
# the same interpreter from both contending on the SQLite lock (which
# would work but produce noisy "database is locked" retries).
_run_learning_lock = threading.Lock()

logger = logging.getLogger("options-bot.learning")

# Threshold bounds — never adjust outside these
MIN_CONFIDENCE_FLOOR = 0.50
MIN_CONFIDENCE_CEILING = 0.85
CONFIDENCE_RAISE_STEP = 0.05
CONFIDENCE_LOWER_STEP = 0.02
STRONG_EXPECTANCY = 0.15      # Expectancy above this = strongly positive
AUTO_PAUSE_WIN_RATE = 0.35    # Below this over 20 trades = auto-pause
REGIME_FIT_REDUCTION = 0.10   # Reduce regime fit score by this amount per losing regime


def run_learning(setup_type: str, default_confidence: float) -> Optional[LearningState]:
    """Run the full learning cycle for one setup_type.

    Args:
        setup_type: the trades.setup_type grouping key — e.g. "momentum",
            "mean_reversion", "catalyst", "compression_breakout",
            "macro_trend". Aggregator profiles (scalp_0dte, swing,
            tsla_swing) accept multiple setup_types and each gets its
            own learning_state row under its setup_type key.
        default_confidence: the profile's constructor default (used if no state exists)

    Returns:
        Updated LearningState, or None if insufficient data.

    Concurrency: the load-compute-save sequence is wrapped in
    learning_state_transaction() so two processes running run_learning
    for the same setup_type serialize at the SQLite level (BEGIN IMMEDIATE
    reserved lock). An in-process threading.Lock additionally prevents
    two threads in one interpreter from contending on the DB lock.
    """
    # Acquire the in-process lock first so threads queue cleanly.
    with _run_learning_lock:
        return _run_learning_locked(setup_type, default_confidence)


def _run_learning_locked(setup_type: str, default_confidence: float) -> Optional[LearningState]:
    # get_recent_trades reads closed trades — idempotent SELECT, no mutation.
    # Safe to run outside the transaction.
    trades = get_recent_trades(setup_type, limit=20)
    if len(trades) < 5:
        logger.info(f"Learning: {setup_type} has {len(trades)} trades (need 5+), skipping")
        return None

    # Atomic load → compute → save against learning_state.
    with learning_state_transaction() as _tx:
        state = load_learning_state(setup_type, conn=_tx)
        if state is None:
            state = LearningState(
                profile_name=setup_type,  # learning_state.profile_name column stores the setup_type value
                min_confidence=default_confidence,
                regime_fit_overrides={},
                tod_fit_overrides={},
                paused_by_learning=False,
                adjustment_log=[],
            )

        now = datetime.now(timezone.utc).isoformat()
        changes = []

        # ── Compute performance metrics ──
        wins = [t for t in trades if t.pnl_pct > 0]
        losses = [t for t in trades if t.pnl_pct <= 0]
        win_rate = len(wins) / len(trades)
        avg_win = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl_pct for t in losses) / len(losses) if losses else 0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        logger.info(
            f"Learning: {setup_type} | {len(trades)} trades | "
            f"WR={win_rate:.0%} avg_win={avg_win:+.1f}% avg_loss={avg_loss:+.1f}% "
            f"expectancy={expectancy:+.2f}"
        )

        # ── Auto-pause check ──
        if len(trades) >= 20 and win_rate < AUTO_PAUSE_WIN_RATE:
            if not state.paused_by_learning:
                state.paused_by_learning = True
                change = {
                    "type": "auto_pause", "timestamp": now,
                    "reason": f"win_rate={win_rate:.0%} < {AUTO_PAUSE_WIN_RATE:.0%} over {len(trades)} trades",
                }
                changes.append(change)
                logger.warning(f"Learning: AUTO-PAUSE {setup_type} — {change['reason']}")

        # ── Confidence threshold adjustment ──
        old_conf = state.min_confidence

        if expectancy < 0:
            # Negative expectancy: raise threshold (be more selective)
            new_conf = min(old_conf + CONFIDENCE_RAISE_STEP, MIN_CONFIDENCE_CEILING)
            if new_conf != old_conf:
                state.min_confidence = round(new_conf, 3)
                changes.append({
                    "type": "confidence_raise", "timestamp": now,
                    "old": old_conf, "new": state.min_confidence,
                    "reason": f"negative expectancy={expectancy:+.2f} over {len(trades)} trades",
                })
                logger.info(f"Learning: {setup_type} confidence {old_conf:.3f} -> {state.min_confidence:.3f} (raised)")

        elif expectancy > STRONG_EXPECTANCY:
            # Strongly positive: lower threshold slightly (take more trades)
            new_conf = max(old_conf - CONFIDENCE_LOWER_STEP, MIN_CONFIDENCE_FLOOR)
            if new_conf != old_conf:
                state.min_confidence = round(new_conf, 3)
                changes.append({
                    "type": "confidence_lower", "timestamp": now,
                    "old": old_conf, "new": state.min_confidence,
                    "reason": f"strong expectancy={expectancy:+.2f} over {len(trades)} trades",
                })
                logger.info(f"Learning: {setup_type} confidence {old_conf:.3f} -> {state.min_confidence:.3f} (lowered)")

        # ── Regime fit adjustment ──
        _adjust_regime_fits(state, trades, now, changes)

        # ── Time-of-day fit adjustment ──
        _adjust_tod_fits(state, trades, now, changes)

        # ── Persist (within the same transaction) ──
        if changes:
            state.adjustment_log.extend(changes)
            save_learning_state(state, conn=_tx)
            logger.info(f"Learning: {setup_type} — {len(changes)} adjustment(s) saved")
        else:
            logger.info(f"Learning: {setup_type} — no adjustments needed")

        return state


def _adjust_regime_fits(state: LearningState, trades: list[TradeRecord],
                         now: str, changes: list):
    """Reduce regime fit score for setup/regime combos that have been losing."""
    from collections import defaultdict

    # Group trades by regime
    regime_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for t in trades:
        if t.market_regime and t.market_regime != "unknown":
            key = t.market_regime
            regime_stats[key]["total"] += 1
            if t.pnl_pct > 0:
                regime_stats[key]["wins"] += 1

    for regime, stats in regime_stats.items():
        if stats["total"] < 5:
            continue  # Not enough data for this regime
        wr = stats["wins"] / stats["total"]
        if wr < 0.40:  # Losing in this regime
            override_key = f"{state.profile_name}_{regime}"
            old_val = state.regime_fit_overrides.get(override_key, 0.0)
            new_val = round(old_val - REGIME_FIT_REDUCTION, 2)
            new_val = max(new_val, -0.50)  # Floor: don't reduce more than 0.50
            if new_val != old_val:
                state.regime_fit_overrides[override_key] = new_val
                changes.append({
                    "type": "regime_fit_reduce", "timestamp": now,
                    "regime": regime, "old": old_val, "new": new_val,
                    "reason": f"win_rate={wr:.0%} in {regime} over {stats['total']} trades",
                })
                logger.info(
                    f"Learning: {state.profile_name} regime_fit "
                    f"{regime} adjustment {old_val} -> {new_val}"
                )


TOD_FIT_REDUCTION = 0.10


def _adjust_tod_fits(state: LearningState, trades: list[TradeRecord],
                      now: str, changes: list):
    """Reduce TOD fit score for setup/TOD combos that have been losing."""
    from collections import defaultdict

    tod_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for t in trades:
        if t.time_of_day:
            key = t.time_of_day
            tod_stats[key]["total"] += 1
            if t.pnl_pct > 0:
                tod_stats[key]["wins"] += 1

    for tod, stats in tod_stats.items():
        if stats["total"] < 5:
            continue
        wr = stats["wins"] / stats["total"]
        if wr < 0.40:
            override_key = f"{state.profile_name}_{tod}"
            old_val = state.tod_fit_overrides.get(override_key, 0.0)
            new_val = round(old_val - TOD_FIT_REDUCTION, 2)
            new_val = max(new_val, -0.50)
            if new_val != old_val:
                state.tod_fit_overrides[override_key] = new_val
                changes.append({
                    "type": "tod_fit_reduce", "timestamp": now,
                    "tod": tod, "old": old_val, "new": new_val,
                    "reason": f"win_rate={wr:.0%} at {tod} over {stats['total']} trades",
                })
                logger.info(
                    f"Learning: {state.profile_name} tod_fit "
                    f"{tod} adjustment {old_val} -> {new_val}"
                )
