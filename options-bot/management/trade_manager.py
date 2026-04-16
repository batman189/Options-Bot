"""Trade management — monitors positions, calls profile exit logic, executes closes.
Per-position check interval: Momentum/Catalyst 60s, Mean Reversion 300s.
Every cycle logged. Exits marked on fill confirmation, not order submission."""

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from management.eod import should_force_close_eod, get_et_now
from profiles.base_profile import BaseProfile

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
    strike: float = 0.0                # Option strike price
    right: str = ""                    # CALL or PUT
    last_checked: float = 0.0          # timestamp of last evaluation
    pending_exit: bool = False          # order submitted, awaiting fill
    pending_exit_reason: str = ""
    pending_exit_order_id: int = 0     # id(order) of pending exit, 0 if none
    exit_retry_count: int = 0          # consecutive failed exit attempts


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
                      setup_type: str = "", strike: float = 0.0, right: str = ""):
        """Register a new position for monitoring. Called after fill confirmation."""
        self._positions[trade_id] = ManagedPosition(
            trade_id=trade_id, symbol=symbol, direction=direction,
            profile=profile, expiration=expiration,
            entry_time=entry_time, entry_price=entry_price,
            quantity=quantity, confidence=confidence, setup_type=setup_type,
            strike=strike, right=right,
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
            get_current_price: callable(ManagedPosition) -> float or None
            get_setup_score: callable(symbol, setup_type) -> float or None

        Returns:
            List of CycleLog entries (one per position evaluated this cycle).
        """
        now = time.time()
        now_et = get_et_now()
        cycle_logs = []

        # Clean up expired trades in DB before evaluating
        self._cleanup_stale_trades()

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

            # Get current option price (not stock price)
            current_price = get_current_price(pos)
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

            # SPY mean_reversion: force close at 3:45 PM ET regardless of expiration
            # Weekly options survive EOD but SPY overnight gap risk is unacceptable
            if pos.symbol == "SPY" and pos.profile.name == "mean_reversion":
                eod_minutes = now_et.hour * 60 + now_et.minute
                if eod_minutes >= (15 * 60 + 45):  # 3:45 PM ET
                    logger.info(
                        f"TradeManager: SPY mean_reversion EOD close "
                        f"{pos.symbol} at {now_et.strftime('%H:%M')} ET"
                    )
                    log = CycleLog(
                        trade_id=trade_id, symbol=pos.symbol, pnl_pct=round(pnl_pct, 2),
                        elapsed_minutes=elapsed, thesis_score=setup_score,
                        decision="eod_close_spy", profile_name=pos.profile.name,
                    )
                    cycle_logs.append(log)
                    self._log_cycle(log)
                    pos.pending_exit = True
                    pos.pending_exit_reason = "eod_close_spy"
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

        # Close trade in DB with full exit data
        pnl_dollars = (fill_price - pos.entry_price) * pos.quantity * 100
        is_day_trade = pos.entry_time.date() == now_et.date()
        try:
            import sqlite3
            from pathlib import Path
            db_path = Path(__file__).parent.parent / "db" / "options_bot.db"
            conn = sqlite3.connect(str(db_path))
            now_utc = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """UPDATE trades SET setup_type = ?, confidence_score = ?, hold_minutes = ?,
                   exit_price = ?, pnl_dollars = ?, pnl_pct = ?, exit_reason = ?,
                   was_day_trade = ?, status = 'closed', exit_date = ?,
                   unrealized_pnl = NULL, unrealized_pnl_pct = NULL, updated_at = ?
                   WHERE id = ?""",
                (pos.setup_type, pos.confidence, hold_minutes,
                 fill_price, round(pnl_dollars, 2), round(pnl_pct, 2),
                 pos.pending_exit_reason or "unknown",
                 1 if is_day_trade else 0,
                 now_utc, now_utc, trade_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"TradeManager: failed to write exit for {trade_id[:8]}: {e}")

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
                new_state = run_learning(pos.profile.name, pos.profile.min_confidence)
                if new_state and new_state.regime_fit_overrides:
                    logger.info(f"TradeManager: learning updated regime_fit_overrides for "
                                f"{pos.profile.name}: {new_state.regime_fit_overrides} "
                                f"(applies on next restart)")
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

    def _cleanup_stale_trades(self):
        """Close expired trades in DB using real Alpaca data. Runs every cycle.

        For each trade WHERE status='open' AND expiration < today:
        1. Check Alpaca order history for sell fills on that contract
        2. If Alpaca sold it: use real fill price for P&L
        3. If Alpaca has no record: check if position still exists
        4. If position gone with no sell: mark expired_worthless
        """
        import sqlite3
        import re
        from pathlib import Path
        try:
            db_path = Path(__file__).parent.parent / "db" / "options_bot.db"
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, symbol, direction, strike, expiration, entry_price, quantity "
                "FROM trades WHERE status = 'open' AND expiration < date('now')"
            ).fetchall()

            if not rows:
                conn.close()
                return

            # Fetch recent Alpaca orders to find real sell fills
            alpaca_sells = {}
            try:
                from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER
                from alpaca.trading.client import TradingClient
                from alpaca.trading.requests import GetOrdersRequest
                from alpaca.trading.enums import QueryOrderStatus

                client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)
                # Search last 7 days of orders to catch sells from prior sessions
                from datetime import timedelta
                after_date = datetime.now(timezone.utc) - timedelta(days=7)
                req = GetOrdersRequest(status=QueryOrderStatus.ALL, after=after_date, limit=500)
                orders = client.get_orders(filter=req)

                for o in orders:
                    if "SELL" not in str(o.side).upper():
                        continue
                    if str(o.status) != "OrderStatus.FILLED":
                        continue
                    # Parse OCC symbol: SPY260407P00659000
                    m = re.match(r'^([A-Z]+)(\d{6})([CP])(\d{8})$', o.symbol or "")
                    if not m:
                        continue
                    underlying = m.group(1)
                    strike = int(m.group(4)) / 1000.0
                    exp = f"20{m.group(2)[:2]}-{m.group(2)[2:4]}-{m.group(2)[4:6]}"
                    key = (underlying, strike, exp)
                    if key not in alpaca_sells:
                        alpaca_sells[key] = []
                    alpaca_sells[key].append({
                        "price": float(o.filled_avg_price) if o.filled_avg_price else None,
                        "qty": int(o.qty) if o.qty else 0,
                        "filled_at": o.filled_at.isoformat() if o.filled_at else None,
                    })
            except Exception as e:
                logger.warning(f"TradeManager: could not fetch Alpaca orders for cleanup: {e}")

            now_utc = datetime.now(timezone.utc).isoformat()
            for row in rows:
                key = (row["symbol"], row["strike"], row["expiration"])
                sells = alpaca_sells.get(key, [])

                if sells:
                    # Alpaca sold this contract — use real fill price
                    fill = sells.pop(0)  # Use first matching sell
                    exit_price = fill["price"] or 0.0
                    exit_date = fill["filled_at"] or now_utc
                    pnl_dollars = (exit_price - row["entry_price"]) * row["quantity"] * 100
                    pnl_pct = ((exit_price - row["entry_price"]) / row["entry_price"]) * 100 if row["entry_price"] else 0
                    exit_reason = "eod_close"
                    logger.info(
                        f"TradeManager: closed {row['id'][:8]} {row['symbol']} "
                        f"strike={row['strike']} via Alpaca sell @ ${exit_price:.2f} "
                        f"pnl=${pnl_dollars:.2f} ({pnl_pct:+.1f}%)"
                    )
                else:
                    # No Alpaca sell found — check if Alpaca even has a position
                    # If no position exists either, this was likely never filled
                    try:
                        positions = client.get_all_positions()
                        pos_symbols = [p.symbol for p in positions]
                    except Exception:
                        pos_symbols = []

                    # Build OCC symbol to check against Alpaca positions
                    exp_compact = row["expiration"].replace("-", "")[2:]  # 20260408 -> 260408
                    right_char = "P" if row["direction"] in ("PUT", "bearish") else "C"
                    occ = f"{row['symbol']}{exp_compact}{right_char}{int(row['strike'] * 1000):08d}"

                    if occ in pos_symbols:
                        # Position still exists in Alpaca — don't close it
                        logger.info(
                            f"TradeManager: {row['id'][:8]} {row['symbol']} "
                            f"strike={row['strike']} still held in Alpaca — skipping"
                        )
                        continue

                    # Alpaca has no position and no sell — order was never filled
                    exit_price = 0.0
                    exit_date = now_utc
                    pnl_dollars = 0.0
                    pnl_pct = 0.0
                    exit_reason = "order_never_filled"
                    logger.info(
                        f"TradeManager: {row['id'][:8]} {row['symbol']} "
                        f"strike={row['strike']} not in Alpaca (no sell, no position) "
                        f"-> order_never_filled"
                    )

                conn.execute(
                    """UPDATE trades SET status = 'closed', exit_reason = ?,
                       exit_price = ?, pnl_dollars = ?, pnl_pct = ?,
                       exit_date = ?, updated_at = ?
                       WHERE id = ?""",
                    (exit_reason, exit_price, round(pnl_dollars, 2),
                     round(pnl_pct, 2), exit_date, now_utc, row["id"]),
                )
                self._positions.pop(row["id"], None)

            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"TradeManager: stale trade cleanup failed (non-fatal): {e}")
