"""Trade management — monitors positions, calls profile exit logic, executes closes.
Per-position check interval: Momentum/Catalyst 60s, Mean Reversion 300s.
Every cycle logged. Exits marked on fill confirmation, not order submission."""

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from management.eod import should_force_close_eod, get_et_now
from profiles.base_profile import BaseProfile, ExitDecision, PositionState

logger = logging.getLogger("options-bot.management")

LOOP_INTERVAL = 60  # Base loop runs every 60 seconds

@dataclass
class ManagedPosition:
    """A position tracked by the trade manager."""
    trade_id: str
    symbol: str
    direction: str
    profile: BaseProfile
    expiration: date
    entry_time: datetime
    entry_price: float
    quantity: int
    confidence: float = 0.0            # Scorer confidence at entry
    setup_type: str = ""               # Scanner setup type (momentum, mean_reversion, catalyst)
    last_checked: float = 0.0          # timestamp of last evaluation
    pending_exit: bool = False          # order submitted, awaiting fill
    pending_exit_reason: str = ""


@dataclass
class CycleLog:
    """Log entry for one position in one monitoring cycle."""
    trade_id: str
    symbol: str
    pnl_pct: float
    elapsed_minutes: int
    thesis_score: Optional[float]
    decision: str       # "holding", "exit_<reason>", "eod_close", "pending_fill"
    profile_name: str


class TradeManager:
    """Monitors open positions and coordinates exits."""

    def __init__(self, data_client=None):
        self._client = data_client
        self._positions: dict[str, ManagedPosition] = {}
        self._cycle_logs: list[CycleLog] = []

    def add_position(self, trade_id: str, symbol: str, direction: str,
                      profile: BaseProfile, expiration: date,
                      entry_time: datetime, entry_price: float,
                      quantity: int, confidence: float, setup_score: float,
                      setup_type: str = ""):
        """Register a new position for monitoring. Called after fill confirmation."""
        self._positions[trade_id] = ManagedPosition(
            trade_id=trade_id, symbol=symbol, direction=direction,
            profile=profile, expiration=expiration,
            entry_time=entry_time, entry_price=entry_price,
            quantity=quantity, confidence=confidence, setup_type=setup_type,
        )
        profile.record_entry(
            trade_id=trade_id, symbol=symbol, direction=direction,
            confidence=confidence, setup_score=setup_score,
            entry_time=entry_time.isoformat(), entry_price=entry_price,
        )
        logger.info(f"TradeManager: added {trade_id[:8]} {symbol} {direction} x{quantity}")

    def run_cycle(self, get_current_price, get_setup_score) -> list[CycleLog]:
        """Run one monitoring cycle across all positions.

        Args:
            get_current_price: callable(symbol, strike, expiration, right) -> float or None
            get_setup_score: callable(symbol, setup_type) -> float or None

        Returns:
            List of CycleLog entries (one per position evaluated this cycle).
        """
        now = time.time()
        now_et = get_et_now()
        cycle_logs = []

        for trade_id, pos in list(self._positions.items()):
            # Skip if pending fill confirmation
            if pos.pending_exit:
                log = CycleLog(
                    trade_id=trade_id, symbol=pos.symbol, pnl_pct=0,
                    elapsed_minutes=0, thesis_score=None,
                    decision="pending_fill", profile_name=pos.profile.name,
                )
                cycle_logs.append(log)
                self._log_cycle(log)
                continue

            # Check interval: skip if not enough time since last check
            interval = getattr(pos.profile, "check_interval_seconds", 60)
            if (now - pos.last_checked) < interval:
                continue
            pos.last_checked = now

            # Get current data
            current_price = get_current_price(pos.symbol)
            if current_price is None:
                log = CycleLog(
                    trade_id=trade_id, symbol=pos.symbol, pnl_pct=0,
                    elapsed_minutes=0, thesis_score=None,
                    decision="price_unavailable", profile_name=pos.profile.name,
                )
                cycle_logs.append(log)
                self._log_cycle(log)
                continue

            pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
            pnl_dollars = (current_price - pos.entry_price) * pos.quantity * 100

            # Persist unrealized P&L to trades table
            try:
                import sqlite3
                from pathlib import Path
                db_path = Path(__file__).parent.parent / "db" / "options_bot.db"
                conn = sqlite3.connect(str(db_path))
                conn.execute(
                    """UPDATE trades SET unrealized_pnl = ?, unrealized_pnl_pct = ?,
                       updated_at = ? WHERE id = ? AND status = 'open'""",
                    (round(pnl_dollars, 2), round(pnl_pct, 2),
                     datetime.now(timezone.utc).isoformat(), trade_id),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass  # Non-fatal — never interrupt position monitoring

            # Normalize timezones for subtraction
            entry = pos.entry_time
            if entry.tzinfo is None and now_et.tzinfo is not None:
                entry = entry.replace(tzinfo=now_et.tzinfo)
            elif entry.tzinfo is not None and now_et.tzinfo is None:
                entry = entry.replace(tzinfo=None)
            elapsed = int((now_et - entry).total_seconds() / 60)
            setup_score = get_setup_score(pos.symbol, pos.profile.name)

            # --- EOD force-close (checked BEFORE profile exit, overrides all) ---
            # Only applies to positions expiring TODAY
            if should_force_close_eod(pos.expiration, now_et):
                log = CycleLog(
                    trade_id=trade_id, symbol=pos.symbol, pnl_pct=round(pnl_pct, 2),
                    elapsed_minutes=elapsed, thesis_score=setup_score,
                    decision="eod_close", profile_name=pos.profile.name,
                )
                cycle_logs.append(log)
                self._log_cycle(log)
                pos.pending_exit = True
                pos.pending_exit_reason = "eod_close"
                continue

            # --- Profile exit evaluation (thesis + time decay + profit lock + hard stop + stale + max hold) ---
            exit_decision = pos.profile.check_exit(
                trade_id=trade_id,
                current_pnl_pct=pnl_pct,
                current_setup_score=setup_score,
                elapsed_minutes=elapsed,
            )

            if exit_decision.exit:
                decision_str = f"exit_{exit_decision.reason}"
                if exit_decision.scale_out:
                    decision_str += "_scale_out"
            else:
                decision_str = "holding"

            log = CycleLog(
                trade_id=trade_id, symbol=pos.symbol, pnl_pct=round(pnl_pct, 2),
                elapsed_minutes=elapsed, thesis_score=setup_score,
                decision=decision_str, profile_name=pos.profile.name,
            )
            cycle_logs.append(log)
            self._log_cycle(log)

            if exit_decision.exit:
                pos.pending_exit = True
                pos.pending_exit_reason = exit_decision.reason

        self._cycle_logs.extend(cycle_logs)
        return cycle_logs

    def confirm_fill(self, trade_id: str, fill_price: float):
        """Called by integration layer when exit order fills.
        Only now is the position marked closed in DB.
        Triggers learning layer check every 20 closed trades."""
        pos = self._positions.pop(trade_id, None)
        if pos is None:
            logger.warning(f"TradeManager: fill confirmation for unknown {trade_id[:8]}")
            return

        pnl_pct = ((fill_price - pos.entry_price) / pos.entry_price) * 100
        now_et = get_et_now()
        entry = pos.entry_time
        if entry.tzinfo is None and now_et.tzinfo is not None:
            entry = entry.replace(tzinfo=now_et.tzinfo)
        hold_minutes = int((now_et - entry).total_seconds() / 60)

        pos.profile.record_exit(trade_id)

        # Write setup_type, confidence_score, hold_minutes to trades table
        try:
            import sqlite3
            from pathlib import Path
            db_path = Path(__file__).parent.parent / "db" / "options_bot.db"
            conn = sqlite3.connect(str(db_path))
            now_utc = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """UPDATE trades SET setup_type = ?, confidence_score = ?, hold_minutes = ?,
                   exit_price = ?, pnl_pct = ?, status = 'closed', exit_date = ?, updated_at = ?
                   WHERE id = ?""",
                (pos.setup_type, pos.confidence, hold_minutes,
                 fill_price, round(pnl_pct, 2), now_utc, now_utc, trade_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"TradeManager: failed to write V2 fields for {trade_id[:8]}: {e}")

        logger.info(
            f"TradeManager: CLOSED {trade_id[:8]} {pos.symbol} "
            f"reason={pos.pending_exit_reason} "
            f"entry=${pos.entry_price:.2f} exit=${fill_price:.2f} "
            f"pnl={pnl_pct:+.1f}% hold={hold_minutes}min "
            f"setup={pos.setup_type} conf={pos.confidence:.3f}"
        )

        # 20-trade trigger: check if learning layer should run
        try:
            from learning.storage import get_closed_trade_count
            from learning.learner import run_learning
            count = get_closed_trade_count(pos.profile.name)
            if count > 0 and count % 20 == 0:
                logger.info(f"TradeManager: 20-trade trigger ({count} closed) for {pos.profile.name}")
                run_learning(pos.profile.name, pos.profile.min_confidence)
        except Exception as e:
            logger.warning(f"TradeManager: learning trigger failed (non-fatal): {e}")

    def get_pending_exits(self) -> list[tuple[str, ManagedPosition]]:
        """Return positions with pending exit orders for the integration layer."""
        return [(tid, pos) for tid, pos in self._positions.items() if pos.pending_exit]

    def get_open_count(self) -> int:
        """Number of positions currently being managed."""
        return len(self._positions)

    def get_recent_logs(self, n: int = 50) -> list[CycleLog]:
        """Last N cycle log entries for debugging."""
        return self._cycle_logs[-n:]

    def _log_cycle(self, log: CycleLog):
        """Log every cycle for every position — primary diagnostic tool."""
        score_str = f"{log.thesis_score:.3f}" if log.thesis_score is not None else "N/A"
        logger.info(
            f"  [{log.profile_name}] {log.trade_id[:8]} {log.symbol} "
            f"pnl={log.pnl_pct:+.1f}% elapsed={log.elapsed_minutes}min "
            f"thesis={score_str} -> {log.decision}"
        )
