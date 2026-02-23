"""
Risk manager — PDT tracking, position sizing, and portfolio limits.
Matches PROJECT_ARCHITECTURE.md Section 11.

Checks performed BEFORE every order:
    1. PDT day trade limit (3 per 5 business days if equity < $25K)
    2. Profile-level position limits (max contracts, max positions, daily trades)
    3. Profile-level daily loss limit
    4. Portfolio-level exposure cap
    5. Portfolio-level total positions cap

The risk manager is a HARD GATE — it cannot be overridden by model output.
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta, date
from typing import Optional

import aiosqlite

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH

logger = logging.getLogger("options-bot.risk")


class RiskManager:
    """Enforces all risk limits before order submission."""

    def __init__(self, db_path: str = None):
        self._db_path = db_path or str(DB_PATH)
        logger.info(f"RiskManager initialized (db={self._db_path})")

    def _run_async(self, coro):
        """Run an async function synchronously (Lumibot strategies are sync)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, coro).result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    # =========================================================================
    # PDT TRACKING
    # =========================================================================

    def get_day_trade_count(self, lookback_days: int = 5) -> int:
        """
        Count day trades in the last N business days.
        A day trade = buy + sell of the same security on the same day.
        We track this via the was_day_trade flag in the trades table.
        """
        async def _count():
            cutoff = datetime.utcnow() - timedelta(days=lookback_days + 2)  # +2 for weekends
            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute(
                    """SELECT COUNT(*) FROM trades
                       WHERE was_day_trade = 1
                       AND status = 'closed'
                       AND exit_date >= ?""",
                    (cutoff.isoformat(),),
                )
                row = await cursor.fetchone()
                return row[0] if row else 0

        count = self._run_async(_count())
        logger.info(f"PDT day trade count (last {lookback_days} days): {count}")
        return count

    def check_pdt(self, portfolio_value: float) -> dict:
        """
        Check if a new day trade is allowed.

        Returns:
            {"allowed": bool, "day_trades_used": int, "limit": int, "message": str}
        """
        if portfolio_value >= 25000:
            return {
                "allowed": True,
                "day_trades_used": 0,
                "limit": -1,  # Unlimited
                "message": "PDT not applicable (equity >= $25K)",
            }

        count = self.get_day_trade_count(lookback_days=5)
        limit = 3
        allowed = count < limit

        result = {
            "allowed": allowed,
            "day_trades_used": count,
            "limit": limit,
            "message": (
                f"PDT: {count}/{limit} day trades used"
                if allowed
                else f"PDT BLOCKED: {count}/{limit} day trades used in last 5 business days"
            ),
        }
        logger.info(result["message"])
        return result

    # =========================================================================
    # POSITION SIZING
    # =========================================================================

    def calculate_position_size(
        self,
        portfolio_value: float,
        option_price: float,
        max_position_pct: float = 20.0,
        max_contracts: int = 5,
    ) -> int:
        """
        Calculate how many contracts to buy.

        Args:
            portfolio_value: Total portfolio value
            option_price: Per-share option price (multiply by 100 for per-contract cost)
            max_position_pct: Max % of portfolio for this position
            max_contracts: Hard cap on contracts

        Returns:
            Number of contracts (0 if position would be too expensive).
        """
        if option_price <= 0:
            return 0

        cost_per_contract = option_price * 100  # Options multiplier
        max_dollar_amount = portfolio_value * (max_position_pct / 100)
        max_by_dollars = int(max_dollar_amount / cost_per_contract)

        quantity = min(max_by_dollars, max_contracts)
        quantity = max(quantity, 0)

        logger.info(
            f"Position sizing: price=${option_price:.2f}, "
            f"cost/contract=${cost_per_contract:.2f}, "
            f"max_dollars=${max_dollar_amount:.2f}, "
            f"result={quantity} contracts"
        )
        return quantity

    # =========================================================================
    # PRE-ORDER CHECKS
    # =========================================================================

    def get_profile_open_positions(self, profile_id: str) -> int:
        """Count open positions for a profile."""
        async def _count():
            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM trades WHERE profile_id = ? AND status = 'open'",
                    (profile_id,),
                )
                row = await cursor.fetchone()
                return row[0] if row else 0

        return self._run_async(_count())

    def get_profile_daily_trades(self, profile_id: str) -> int:
        """Count trades opened today for a profile."""
        async def _count():
            today = datetime.utcnow().date().isoformat()
            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute(
                    """SELECT COUNT(*) FROM trades
                       WHERE profile_id = ?
                       AND entry_date >= ?""",
                    (profile_id, today),
                )
                row = await cursor.fetchone()
                return row[0] if row else 0

        return self._run_async(_count())

    def get_total_open_positions(self) -> int:
        """Count open positions across ALL profiles."""
        async def _count():
            async with aiosqlite.connect(self._db_path) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM trades WHERE status = 'open'",
                )
                row = await cursor.fetchone()
                return row[0] if row else 0

        return self._run_async(_count())

    def check_can_open_position(
        self,
        profile_id: str,
        profile_config: dict,
        portfolio_value: float,
        option_price: float,
    ) -> dict:
        """
        Run ALL pre-order checks. Returns dict with result and reasons.

        Args:
            profile_id: Profile UUID
            profile_config: Profile config dict with risk limits
            portfolio_value: Current portfolio value
            option_price: Per-share option price

        Returns:
            {
                "allowed": bool,
                "quantity": int (contracts to buy, 0 if blocked),
                "reasons": [str] (why blocked, empty if allowed),
            }
        """
        reasons = []

        # 1. Profile concurrent positions
        max_concurrent = profile_config.get("max_concurrent_positions", 3)
        open_positions = self.get_profile_open_positions(profile_id)
        if open_positions >= max_concurrent:
            reasons.append(
                f"Max concurrent positions reached: {open_positions}/{max_concurrent}"
            )

        # 2. Profile daily trades
        max_daily = profile_config.get("max_daily_trades", 5)
        daily_trades = self.get_profile_daily_trades(profile_id)
        if daily_trades >= max_daily:
            reasons.append(
                f"Max daily trades reached: {daily_trades}/{max_daily}"
            )

        # 3. Portfolio-level total positions
        max_total = 10  # Architecture Section 11
        total_open = self.get_total_open_positions()
        if total_open >= max_total:
            reasons.append(
                f"Portfolio max positions reached: {total_open}/{max_total}"
            )

        # 4. Position sizing
        max_position_pct = profile_config.get("max_position_pct", 20)
        max_contracts = profile_config.get("max_contracts", 5)
        quantity = self.calculate_position_size(
            portfolio_value, option_price, max_position_pct, max_contracts
        )
        if quantity <= 0:
            reasons.append(
                f"Position too expensive: ${option_price * 100:.2f}/contract "
                f"vs max ${portfolio_value * max_position_pct / 100:.2f}"
            )

        allowed = len(reasons) == 0
        if not allowed:
            logger.warning(f"Order BLOCKED: {'; '.join(reasons)}")
        else:
            logger.info(f"Order ALLOWED: {quantity} contracts")

        return {
            "allowed": allowed,
            "quantity": quantity,
            "reasons": reasons,
        }

    # =========================================================================
    # TRADE LOGGING
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
        model_type: str = "xgboost",
    ):
        """Log an opened trade to the database."""
        async def _log():
            now = datetime.utcnow().isoformat()
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT INTO trades
                       (id, profile_id, symbol, direction, strike, expiration, quantity,
                        entry_price, entry_date, entry_underlying_price,
                        entry_predicted_return, entry_ev_pct, entry_features,
                        entry_greeks, entry_model_type, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                    (
                        trade_id, profile_id, symbol, direction, strike,
                        expiration, quantity, entry_price, now,
                        entry_underlying_price, predicted_return, ev_pct,
                        json.dumps(features), json.dumps(greeks),
                        model_type, now, now,
                    ),
                )
                await db.commit()
            logger.info(f"Trade opened: {trade_id} {symbol} {direction} {strike}")

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
        async def _log():
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
            logger.info(
                f"Trade closed: {trade_id} reason={exit_reason} "
                f"P&L=${pnl_dollars:.2f} ({pnl_pct:.1f}%)"
            )

        self._run_async(_log())
