"""
Risk manager — PDT tracking, position sizing, portfolio-level limits, trade logging.
Phase 2 additions:
  - Portfolio exposure enforcement (MAX_TOTAL_EXPOSURE_PCT)
  - Emergency stop loss (EMERGENCY_STOP_LOSS_PCT)

Matches PROJECT_ARCHITECTURE.md Section 11.
"""

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

import sys
# Add project root to sys.path — no setup.py/pyproject.toml in this project
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    DB_PATH,
    MAX_TOTAL_POSITIONS,
    MAX_TOTAL_EXPOSURE_PCT,
    EMERGENCY_STOP_LOSS_PCT,
)

logger = logging.getLogger("options-bot.risk_manager")


class RiskManager:
    """
    Enforces all risk rules before order submission.
    Called by BaseOptionsStrategy before every entry.

    Phase 1: PDT tracking, position count, per-profile limits
    Phase 2: Portfolio exposure %, emergency stop loss
    """

    def __init__(self, db_path: Optional[Path] = None):
        logger.info("RiskManager.__init__ starting")
        self._db_path = str(db_path or DB_PATH)
        self._loop = None
        self._thread = None
        self._start_async_loop()
        logger.info("RiskManager.__init__ complete")

    # =========================================================================
    # Async loop management (bridge between sync Lumibot and async SQLite)
    # =========================================================================

    def _start_async_loop(self):
        """Start a dedicated event loop thread for async DB operations."""
        logger.info("Starting async event loop thread")
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        logger.info("Async event loop thread started")

    def _run_async(self, coro):
        """Run a coroutine on the background event loop and return result."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=30)
        except Exception as e:
            logger.error(f"Async operation failed: {e}", exc_info=True)
            return None

    # =========================================================================
    # PDT Rule Enforcement
    # Architecture Section 11 — PDT tracking
    # =========================================================================

    # get_day_trade_count — DELETED in the V1 cleanup pass. Orphaned by
    # the earlier check_pdt_limit/check_pdt removal. V2 reads Alpaca's
    # daytrade_count directly (v2_strategy.py self._pdt_day_trades),
    # which is the canonical source. No DB-based PDT count is needed.

    # =========================================================================
    # Position Limits
    # Architecture Section 11
    # =========================================================================

    def get_open_position_count(self) -> int:
        """Count all open positions across all profiles."""
        logger.info("get_open_position_count called")

        async def _count():
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM trades WHERE status = 'open'"
                    )
                    row = await cursor.fetchone()
                    count = row[0] if row else 0
                    logger.info(f"Open position count: {count}")
                    return count
            except Exception as e:
                logger.error(f"get_open_position_count DB error: {e}", exc_info=True)
                return 0

        return self._run_async(_count()) or 0

    # check_position_limits — DELETED in the V1 cleanup pass. No V2 caller
    # ever invoked it; the only call site was check_all (also deleted), a
    # V1 composite gate. V2 does per-profile position accounting in the
    # sizer + portfolio exposure check inline in v2_strategy's Step 8.

    # _get_profile_open_count — DELETED in the V1 cleanup pass. Only ever
    # called by check_position_limits (also deleted). V2 does per-profile
    # position accounting inside sizing.sizer.calculate.

    # =========================================================================
    # Portfolio Exposure Enforcement (Phase 2)
    # Architecture Section 11 — MAX_TOTAL_EXPOSURE_PCT = 20%
    # NOTE: V2 only reads `exposure_dollars` from this call's return dict;
    # the live hard block is in sizing.sizer.MAX_EXPOSURE_PCT. Both are
    # held equal by an assert at sizer import time.
    # =========================================================================

    def check_portfolio_exposure(
        self,
        portfolio_value: float,
    ) -> dict:
        """
        Check whether total portfolio exposure across all open positions
        exceeds MAX_TOTAL_EXPOSURE_PCT (20%).

        Exposure = sum of (entry_price * quantity * 100) for all open option positions.
        Options multiplier is 100 shares per contract.

        Returns:
            {
                "allowed": bool,
                "exposure_pct": float,
                "exposure_dollars": float,
                "limit_pct": float,
                "message": str,
            }
        """
        async def _get_exposure():
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    cursor = await db.execute(
                        """SELECT SUM(
                               entry_price * quantity *
                               CASE WHEN direction IN ('CALL', 'PUT') THEN 100 ELSE 1 END
                           )
                           FROM trades
                           WHERE status = 'open'"""
                    )
                    row = await cursor.fetchone()
                    return float(row[0]) if row and row[0] else 0.0
            except Exception as e:
                logger.error(f"_get_exposure DB error: {e}", exc_info=True)
                return 0.0

        exposure_dollars = self._run_async(_get_exposure()) or 0.0

        if portfolio_value <= 0:
            logger.warning("check_portfolio_exposure: portfolio_value is 0 — allowing")
            return {
                "allowed": True,
                "exposure_pct": 0.0,
                "exposure_dollars": exposure_dollars,
                "limit_pct": MAX_TOTAL_EXPOSURE_PCT,
                "message": "Portfolio value unknown — exposure check skipped",
            }

        exposure_pct = (exposure_dollars / portfolio_value) * 100
        allowed = exposure_pct < MAX_TOTAL_EXPOSURE_PCT

        message = (
            f"Portfolio exposure: {exposure_pct:.1f}% "
            f"(${exposure_dollars:,.0f} / ${portfolio_value:,.0f}) "
            f"limit={MAX_TOTAL_EXPOSURE_PCT}%"
        )
        if not allowed:
            message = f"EXPOSURE LIMIT REACHED: {message}"
            logger.warning(message)
        else:
            logger.info(message)

        return {
            "allowed": allowed,
            "exposure_pct": exposure_pct,
            "exposure_dollars": exposure_dollars,
            "limit_pct": float(MAX_TOTAL_EXPOSURE_PCT),
            "message": message,
        }

    # =========================================================================
    # Emergency Stop Loss (Phase 2)
    # Architecture Section 11 — EMERGENCY_STOP_LOSS_PCT = 20%
    # =========================================================================

    def check_emergency_stop_loss(
        self,
        current_portfolio_value: float,
        initial_portfolio_value: float,
    ) -> dict:
        """
        Check whether the portfolio has lost more than EMERGENCY_STOP_LOSS_PCT (20%)
        since the strategy started. If triggered, all positions should be liquidated
        and all profiles paused.

        Args:
            current_portfolio_value: Current total equity from broker.
            initial_portfolio_value: Portfolio value recorded at strategy start.

        Returns:
            {
                "triggered": bool,
                "drawdown_pct": float,
                "limit_pct": float,
                "message": str,
            }
        """
        if initial_portfolio_value <= 0:
            return {
                "triggered": False,
                "drawdown_pct": 0.0,
                "limit_pct": float(EMERGENCY_STOP_LOSS_PCT),
                "message": "Initial portfolio value unknown — emergency stop skipped",
            }

        drawdown_pct = (
            (initial_portfolio_value - current_portfolio_value) / initial_portfolio_value
        ) * 100

        triggered = drawdown_pct >= EMERGENCY_STOP_LOSS_PCT

        message = (
            f"Portfolio drawdown: {drawdown_pct:.1f}% "
            f"(${current_portfolio_value:,.0f} from ${initial_portfolio_value:,.0f}) "
            f"limit={EMERGENCY_STOP_LOSS_PCT}%"
        )
        if triggered:
            message = f"EMERGENCY STOP TRIGGERED: {message}"
            logger.critical(message)
            try:
                from utils.alerter import send_alert
                send_alert(
                    level="CRITICAL",
                    message="Emergency stop loss triggered — trading halted",
                    details={
                        "portfolio_value": f"${current_portfolio_value:,.0f}",
                        "drawdown_pct": round(drawdown_pct, 2),
                        "threshold_pct": EMERGENCY_STOP_LOSS_PCT,
                    },
                )
            except Exception:
                pass  # Alert failure must never crash risk checks
        else:
            logger.info(message)

        return {
            "triggered": triggered,
            "drawdown_pct": drawdown_pct,
            "limit_pct": float(EMERGENCY_STOP_LOSS_PCT),
            "message": message,
        }

    # =========================================================================
    # Position Sizing
    # Architecture Section 11
    # =========================================================================

    # calculate_position_size — DELETED in the V1 cleanup pass. V2 sizes
    # via sizing.sizer.calculate — single source of truth that honors the
    # Growth Mode 15%-risk branch, drawdown halvings, and portfolio
    # exposure cap. Only pre-cleanup V1 composite gate called this helper.

    # check_can_open_position — DELETED in the V1 cleanup pass. This was
    # the V1 composite pre-trade check that wired check_pdt_limit,
    # check_position_limits, and calculate_position_size together. V2
    # does its own gating in v2_strategy.on_trading_iteration Steps 4-8
    # and sizes via sizing.sizer.calculate. No V2 path invoked this.

    # _get_profile_daily_trade_count — DELETED in the V1 cleanup pass.
    # Orphaned after the pre-cleanup V1 check_can_open_position path went
    # away. V2 has no per-profile daily trade cap; sizing handles per-
    # profile limits via portfolio exposure.

    # =========================================================================
    # Trade Logging
    # Architecture Section 5a — trades table
    # =========================================================================

    def log_trade_open(
        self,
        trade_id: str,
        profile_id: str,
        symbol: str,
        direction: str,
        strike: float,
        expiration: str,
        quantity: int,
        entry_price: float,
        entry_underlying_price: float,
        predicted_return: float,
        ev_pct: float,
        features: dict,
        greeks: dict,
        model_type: str,
        market_vix: float = None,
        market_regime: str = None,
    ):
        """Log a new trade opening to the database."""
        logger.info(f"log_trade_open: {trade_id} {symbol} {direction} strike={strike}")

        async def _log():
            try:
                now = datetime.now(timezone.utc).isoformat()
                async with aiosqlite.connect(self._db_path) as db:
                    await db.execute(
                        """INSERT INTO trades (
                               id, profile_id, symbol, direction, strike,
                               expiration, quantity, entry_price, entry_date,
                               entry_underlying_price, entry_predicted_return, entry_ev_pct,
                               entry_features, entry_greeks, entry_model_type,
                               market_vix, market_regime,
                               status, created_at, updated_at
                           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            trade_id, profile_id, symbol, direction, strike,
                            expiration, quantity, entry_price, now,
                            entry_underlying_price, predicted_return, ev_pct,
                            json.dumps(features), json.dumps(greeks), model_type,
                            market_vix, market_regime,
                            "open", now, now,
                        ),
                    )
                    await db.commit()
                logger.info(f"Trade opened and logged: {trade_id}")
            except Exception as e:
                logger.error(f"log_trade_open DB error: {e}", exc_info=True)

        self._run_async(_log())

    # log_trade_close — DELETED in the V1 cleanup pass. V2 closes trades
    # via management.trade_manager.confirm_fill (and scripts/reconcile_positions
    # for reconciliation), both of which do their own UPDATEs with the
    # full V2 column set (exit_reason + exit_greeks + hold_minutes, etc.).
    # No V2 path invoked this method.

    # =========================================================================
    # Portfolio-level Greeks aggregation
    # =========================================================================

    def get_portfolio_greeks(self, open_positions: list[dict]) -> dict:
        """
        Sum delta/gamma/theta/vega across all open positions.

        Args:
            open_positions: list of dicts, each with an "entry_greeks" sub-dict
                            containing delta, gamma, theta, vega. Missing Greeks
                            are treated as 0.

        Returns:
            {"total_delta": float, "total_gamma": float,
             "total_theta": float, "total_vega": float,
             "position_count": int}
        """
        total = {"total_delta": 0.0, "total_gamma": 0.0,
                 "total_theta": 0.0, "total_vega": 0.0,
                 "position_count": len(open_positions)}

        for pos in open_positions:
            greeks = pos.get("entry_greeks", {})
            if not greeks or not isinstance(greeks, dict):
                continue
            quantity = pos.get("quantity", 1)
            # Options: 1 contract = 100 shares, so Greeks are per-contract already
            total["total_delta"] += (greeks.get("delta") or 0) * quantity
            total["total_gamma"] += (greeks.get("gamma") or 0) * quantity
            total["total_theta"] += (greeks.get("theta") or 0) * quantity
            total["total_vega"] += (greeks.get("vega") or 0) * quantity

        return total

