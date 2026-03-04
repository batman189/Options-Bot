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
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiosqlite

import sys
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

    def __init__(self, db_path: Path = None):
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

    def get_day_trade_count(self, equity: float) -> int:
        """
        Count round-trip day trades in the last 5 business days.
        Returns 0 if equity >= $25K (PDT rule does not apply).
        """
        logger.info(f"get_day_trade_count called, equity={equity:.2f}")

        async def _count():
            try:
                cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
                async with aiosqlite.connect(self._db_path) as db:
                    cursor = await db.execute(
                        """SELECT COUNT(*) FROM trades
                           WHERE was_day_trade = 1
                           AND exit_date >= ?
                           AND status = 'closed'""",
                        (cutoff,),
                    )
                    row = await cursor.fetchone()
                    count = row[0] if row else 0
                    logger.info(f"Day trade count in last 7 days: {count}")
                    return count
            except Exception as e:
                logger.error(f"get_day_trade_count DB error: {e}", exc_info=True)
                return 0

        if equity >= 25_000:
            logger.info("Equity >= $25K — PDT rule does not apply")
            return 0

        return self._run_async(_count()) or 0

    def check_pdt_limit(self, equity: float) -> tuple[bool, str]:
        """
        Returns (can_trade: bool, reason: str).
        Blocks entry if 3+ day trades used and equity < $25K.
        """
        logger.info(f"check_pdt_limit called, equity={equity:.2f}")

        if equity >= 25_000:
            return True, "PDT rule not applicable (equity >= $25K)"

        count = self.get_day_trade_count(equity)
        if count >= 3:
            reason = f"PDT limit reached: {count}/3 day trades used in last 5 days"
            logger.warning(reason)
            return False, reason

        return True, f"PDT OK: {count}/3 day trades used"

    def check_pdt(self, equity: float) -> dict:
        """
        PDT check wrapper returning dict format expected by base_strategy.py.

        Calls check_pdt_limit() and converts the (bool, str) tuple to:
            {"allowed": bool, "message": str}

        Args:
            equity: Current portfolio value in dollars

        Returns:
            {"allowed": True/False, "message": str explaining result}
        """
        allowed, message = self.check_pdt_limit(equity)
        return {"allowed": allowed, "message": message}

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

    def check_position_limits(
        self, profile_config: dict, portfolio_value: float, profile_id: str = "unknown"
    ) -> tuple[bool, str]:
        """
        Check both per-profile and portfolio-level position limits.
        Phase 2: Also enforces MAX_TOTAL_EXPOSURE_PCT.

        Args:
            profile_config: The profile's config dict (from profiles.config in DB).
            portfolio_value: Current portfolio value in dollars.
            profile_id: The profile's unique ID for per-profile position counting.

        Returns:
            (can_trade: bool, reason: str)
        """
        logger.info(f"check_position_limits called, portfolio_value={portfolio_value:.2f}")

        total_open = self.get_open_position_count()
        if total_open >= MAX_TOTAL_POSITIONS:
            reason = f"Portfolio position limit reached: {total_open}/{MAX_TOTAL_POSITIONS}"
            logger.warning(reason)
            return False, reason

        max_concurrent = profile_config.get("max_concurrent_positions", 3)
        profile_open = self._get_profile_open_count(profile_id)
        if profile_open >= max_concurrent:
            reason = f"Profile position limit reached: {profile_open}/{max_concurrent}"
            logger.warning(reason)
            return False, reason

        # Phase 2: Portfolio exposure check
        if portfolio_value > 0:
            exposure = self.check_portfolio_exposure(portfolio_value)
            if not exposure["allowed"]:
                return False, exposure["message"]

        logger.info("Position limits OK")
        return True, "Position limits OK"

    def _get_profile_open_count(self, profile_id: str) -> int:
        """Count open positions for a specific profile."""
        logger.info(f"_get_profile_open_count called, profile_id={profile_id}")

        async def _count():
            try:
                async with aiosqlite.connect(self._db_path) as db:
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM trades WHERE status = 'open' AND profile_id = ?",
                        (profile_id,),
                    )
                    row = await cursor.fetchone()
                    count = row[0] if row else 0
                    logger.info(f"Profile {profile_id} open count: {count}")
                    return count
            except Exception as e:
                logger.error(f"_get_profile_open_count DB error: {e}", exc_info=True)
                return 0

        return self._run_async(_count()) or 0

    # =========================================================================
    # Portfolio Exposure Enforcement (Phase 2)
    # Architecture Section 11 — MAX_TOTAL_EXPOSURE_PCT = 60%
    # =========================================================================

    def check_portfolio_exposure(
        self,
        portfolio_value: float,
    ) -> dict:
        """
        Check whether total portfolio exposure across all open positions
        exceeds MAX_TOTAL_EXPOSURE_PCT (60%).

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

    def calculate_position_size(
        self,
        portfolio_value: float,
        option_price: float,
        profile_config: dict,
    ) -> int:
        """
        Calculate number of contracts to buy.

        Rules:
        - Max dollars per position = portfolio_value * max_position_pct
        - Max contracts = profile config max_contracts
        - Final quantity = min(dollars_allow, max_contracts)

        Args:
            portfolio_value: Current portfolio value.
            option_price: Option premium per share (multiply by 100 for contract value).
            profile_config: Profile config dict.

        Returns:
            Number of contracts (minimum 1 if any are affordable).
        """
        logger.info(
            f"calculate_position_size: portfolio={portfolio_value:.2f}, "
            f"option_price={option_price:.4f}"
        )

        if option_price <= 0:
            logger.warning("Option price is 0 or negative — returning 0 contracts")
            return 0

        max_position_pct = profile_config.get("max_position_pct", 20) / 100
        max_contracts_config = profile_config.get("max_contracts", 5)

        max_dollars = portfolio_value * max_position_pct
        contract_cost = option_price * 100  # Each contract = 100 shares
        contracts_by_dollars = int(max_dollars / contract_cost)

        quantity = min(contracts_by_dollars, max_contracts_config)
        if quantity <= 0:
            logger.warning(
                f"Position size: 0 contracts affordable "
                f"(contract_cost=${contract_cost:.2f} > max_dollars=${max_dollars:.2f})"
            )
            return 0
        logger.info(
            f"Position size: max_dollars=${max_dollars:.2f}, "
            f"contract_cost=${contract_cost:.2f}, "
            f"contracts_by_dollars={contracts_by_dollars}, "
            f"max_contracts_config={max_contracts_config}, "
            f"final_quantity={quantity}"
        )
        return quantity

    # =========================================================================
    # Combined Pre-Trade Check (used by base_strategy.py)
    # =========================================================================

    def check_can_open_position(
        self,
        profile_id: str,
        profile_config: dict,
        portfolio_value: float,
        option_price: float,
    ) -> dict:
        """
        Composite pre-trade check: PDT + position limits + exposure + sizing.

        Returns:
            {
                "allowed": bool,
                "quantity": int,       # contracts to buy (0 if blocked)
                "reasons": list[str],  # human-readable reasons if blocked
            }
        """
        reasons = []

        # PDT check
        pdt_ok, pdt_msg = self.check_pdt_limit(portfolio_value)
        if not pdt_ok:
            reasons.append(pdt_msg)

        # Position limits + exposure
        pos_ok, pos_msg = self.check_position_limits(profile_config, portfolio_value, profile_id)
        if not pos_ok:
            reasons.append(pos_msg)

        # Daily trade count check
        max_daily = profile_config.get("max_daily_trades", 5)
        daily_count = self._get_profile_daily_trade_count(profile_id)
        if daily_count >= max_daily:
            reasons.append(
                f"Daily trade limit reached: {daily_count}/{max_daily}"
            )

        if reasons:
            return {"allowed": False, "quantity": 0, "reasons": reasons}

        # Position sizing
        quantity = self.calculate_position_size(
            portfolio_value, option_price, profile_config
        )
        if quantity <= 0:
            return {
                "allowed": False,
                "quantity": 0,
                "reasons": ["Position size is 0 (option too expensive or portfolio too small)"],
            }

        return {"allowed": True, "quantity": quantity, "reasons": []}

    def _get_profile_daily_trade_count(self, profile_id: str) -> int:
        """Count trades opened today for a specific profile."""
        async def _count():
            try:
                today = datetime.utcnow().strftime("%Y-%m-%d")
                async with aiosqlite.connect(self._db_path) as db:
                    cursor = await db.execute(
                        """SELECT COUNT(*) FROM trades
                           WHERE profile_id = ?
                           AND entry_date >= ?""",
                        (profile_id, today),
                    )
                    row = await cursor.fetchone()
                    return row[0] if row else 0
            except Exception as e:
                logger.error(f"_get_profile_daily_trade_count DB error: {e}")
                return 0

        return self._run_async(_count()) or 0

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
                now = datetime.utcnow().isoformat()
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

    def log_trade_close(
        self,
        trade_id: str,
        exit_price: float,
        exit_underlying_price: float,
        exit_reason: str,
        exit_greeks: dict = None,
        pnl_dollars: float = 0,
        pnl_pct: float = 0,
        hold_days: int = 0,
        was_day_trade: bool = False,
    ):
        """Log a closed trade to the database."""
        logger.info(
            f"log_trade_close: {trade_id} reason={exit_reason} "
            f"pnl=${pnl_dollars:.2f} ({pnl_pct:.1f}%)"
        )

        async def _log():
            try:
                now = datetime.utcnow().isoformat()
                async with aiosqlite.connect(self._db_path) as db:
                    await db.execute(
                        """UPDATE trades SET
                               exit_price = ?, exit_date = ?, exit_underlying_price = ?,
                               exit_reason = ?, exit_greeks = ?,
                               pnl_dollars = ?, pnl_pct = ?,
                               hold_days = ?, was_day_trade = ?,
                               status = 'closed', updated_at = ?
                           WHERE id = ?""",
                        (
                            exit_price, now, exit_underlying_price,
                            exit_reason, json.dumps(exit_greeks or {}),
                            pnl_dollars, pnl_pct,
                            hold_days, 1 if was_day_trade else 0,
                            now, trade_id,
                        ),
                    )
                    await db.commit()
                logger.info(f"Trade closed and logged: {trade_id}")
            except Exception as e:
                logger.error(f"log_trade_close DB error: {e}", exc_info=True)

        self._run_async(_log())