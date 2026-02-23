# CLAUDE CODE PROMPT 06 — EV Filter, Risk Manager, and Swing Strategy

## TASK
Create the EV filter, risk manager, base strategy, and swing strategy. These are Phase 1 Steps 6-9 from the architecture. After this prompt, the bot will be able to paper trade.

**This is the integration prompt** — it connects everything built so far (data providers, features, ML model) into a working Lumibot strategy that scans chains, filters by EV, checks risk limits, executes trades, manages exits, and logs everything to SQLite.

**CRITICAL**: Read this ENTIRE prompt before writing code. The strategy uses LUMIBOT'S built-in methods for live data (not our data providers — those are for training). Every Lumibot API call is documented in LUMIBOT_BUILD_SPEC.md and must match those exact signatures.

---

## FILES TO CREATE

1. `options-bot/ml/ev_filter.py` — Expected Value calculation
2. `options-bot/risk/__init__.py` — empty
3. `options-bot/risk/risk_manager.py` — PDT tracking + position sizing + portfolio limits
4. `options-bot/strategies/__init__.py` — empty
5. `options-bot/strategies/base_strategy.py` — Base strategy class with shared logic
6. `options-bot/strategies/swing_strategy.py` — Swing trading strategy

---

## FILE 1: `options-bot/ml/ev_filter.py`

```python
"""
Expected Value filter for option contract selection.
Matches PROJECT_ARCHITECTURE.md Section 9 — Entry Logic step 9.

Scans the option chain, filters by DTE and moneyness,
calculates EV for each candidate, returns the best contract.

EV formula:
    expected_gain = |predicted_return_pct / 100| * underlying_price * |delta|
    theta_cost = |theta| * max_hold_days
    EV = (expected_gain - premium - theta_cost) / premium * 100

The contract with the highest EV above the minimum threshold wins.
"""

import logging
import datetime
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger("options-bot.ml.ev_filter")


@dataclass
class EVCandidate:
    """A scored option contract candidate."""
    expiration: datetime.date
    strike: float
    right: str  # "CALL" or "PUT"
    premium: float  # Mid price (bid+ask)/2 or last price
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_volatility: float
    ev_pct: float  # Calculated EV percentage
    expected_gain: float
    theta_cost: float


def scan_chain_for_best_ev(
    strategy,
    symbol: str,
    predicted_return_pct: float,
    underlying_price: float,
    min_dte: int,
    max_dte: int,
    max_hold_days: int,
    min_ev_pct: float,
    moneyness_range_pct: float = 5.0,
) -> Optional[EVCandidate]:
    """
    Scan the option chain and find the contract with the highest EV.

    Args:
        strategy: The Lumibot Strategy instance (for get_chains, get_greeks, get_last_price)
        symbol: Underlying ticker (e.g., "TSLA")
        predicted_return_pct: Model's predicted forward return (e.g., 2.5 means +2.5%)
        underlying_price: Current price of the underlying
        min_dte: Minimum days to expiration (from profile config)
        max_dte: Maximum days to expiration
        max_hold_days: Maximum holding period (for theta cost calculation)
        min_ev_pct: Minimum EV percentage to accept
        moneyness_range_pct: How far from ATM to scan (default ±5%)

    Returns:
        EVCandidate with the highest EV, or None if nothing qualifies.

    Uses Lumibot's get_chains() and get_greeks() — NOT our data providers.
    """
    from lumibot.entities import Asset

    logger.info(
        f"Scanning chain for {symbol}: predicted_return={predicted_return_pct:.2f}%, "
        f"price=${underlying_price:.2f}, DTE={min_dte}-{max_dte}, "
        f"min_ev={min_ev_pct}%"
    )

    # Determine direction from prediction
    direction = "CALL" if predicted_return_pct > 0 else "PUT"
    abs_predicted_return = abs(predicted_return_pct)

    # Get option chains from Lumibot
    stock_asset = Asset(symbol, asset_type="stock")
    try:
        chains = strategy.get_chains(stock_asset)
    except Exception as e:
        logger.error(f"Failed to get chains for {symbol}: {e}")
        return None

    if not chains or "Chains" not in chains:
        logger.warning(f"No chains data for {symbol}")
        return None

    chain_data = chains["Chains"]
    if direction not in chain_data:
        logger.warning(f"No {direction} chains for {symbol}")
        return None

    today = strategy.get_datetime().date()
    moneyness_lo = underlying_price * (1 - moneyness_range_pct / 100)
    moneyness_hi = underlying_price * (1 + moneyness_range_pct / 100)

    candidates = []
    contracts_scanned = 0
    contracts_skipped_dte = 0
    contracts_skipped_moneyness = 0
    contracts_skipped_greeks = 0
    contracts_skipped_price = 0

    for exp_date, strikes in chain_data[direction].items():
        # Normalize expiration to datetime.date
        if isinstance(exp_date, str):
            exp_date = datetime.datetime.strptime(exp_date, "%Y-%m-%d").date()
        elif isinstance(exp_date, datetime.datetime):
            exp_date = exp_date.date()

        dte = (exp_date - today).days
        if dte < min_dte or dte > max_dte:
            contracts_skipped_dte += len(strikes)
            continue

        for strike in strikes:
            contracts_scanned += 1
            strike = float(strike)

            # Filter by moneyness
            if strike < moneyness_lo or strike > moneyness_hi:
                contracts_skipped_moneyness += 1
                continue

            # Build the option asset
            option_asset = Asset(
                symbol=symbol,
                asset_type="option",
                expiration=exp_date,
                strike=strike,
                right=direction,
            )

            # Get Greeks (Lumibot Black-Scholes)
            greeks = strategy.get_greeks(
                option_asset,
                underlying_price=underlying_price,
            )
            if greeks is None:
                contracts_skipped_greeks += 1
                continue

            delta = greeks.get("delta", 0)
            gamma = greeks.get("gamma", 0)
            theta = greeks.get("theta", 0)
            vega = greeks.get("vega", 0)
            iv = greeks.get("implied_volatility", 0)

            if abs(delta) < 0.05:
                # Skip deep OTM with negligible delta
                contracts_skipped_greeks += 1
                continue

            # Get option price
            option_price = strategy.get_last_price(option_asset)
            if option_price is None or option_price <= 0:
                contracts_skipped_price += 1
                continue

            # Premium is per-share price (multiply by 100 for per-contract cost,
            # but EV calc uses per-share to keep units consistent)
            premium = option_price

            # Calculate EV
            # Expected gain: how much the option price should move
            # predicted move in $ = underlying_price * abs_predicted_return / 100
            # option gain ≈ predicted_move * |delta|
            predicted_move_dollars = underlying_price * abs_predicted_return / 100
            expected_gain = predicted_move_dollars * abs(delta)

            # Theta cost over holding period
            theta_cost = abs(theta) * min(max_hold_days, dte)

            # EV percentage
            ev_pct = (expected_gain - premium - theta_cost) / premium * 100

            candidates.append(EVCandidate(
                expiration=exp_date,
                strike=strike,
                right=direction,
                premium=premium,
                delta=delta,
                gamma=gamma,
                theta=theta,
                vega=vega,
                implied_volatility=iv,
                ev_pct=ev_pct,
                expected_gain=expected_gain,
                theta_cost=theta_cost,
            ))

    logger.info(
        f"Chain scan complete: {contracts_scanned} scanned, "
        f"{len(candidates)} candidates scored, "
        f"{contracts_skipped_dte} skipped (DTE), "
        f"{contracts_skipped_moneyness} skipped (moneyness), "
        f"{contracts_skipped_greeks} skipped (Greeks), "
        f"{contracts_skipped_price} skipped (price)"
    )

    if not candidates:
        logger.info("No EV candidates found")
        return None

    # Filter by minimum EV
    qualified = [c for c in candidates if c.ev_pct >= min_ev_pct]
    if not qualified:
        best_below = max(candidates, key=lambda c: c.ev_pct)
        logger.info(
            f"No candidates meet min EV {min_ev_pct}%. "
            f"Best was {best_below.strike} {best_below.right} "
            f"exp={best_below.expiration} EV={best_below.ev_pct:.1f}%"
        )
        return None

    # Select highest EV
    best = max(qualified, key=lambda c: c.ev_pct)
    logger.info(
        f"Best contract: {best.strike} {best.right} exp={best.expiration} "
        f"EV={best.ev_pct:.1f}% premium=${best.premium:.2f} "
        f"delta={best.delta:.3f} theta={best.theta:.4f}"
    )
    return best
```

---

## FILE 2: `options-bot/risk/__init__.py`

```python
```

---

## FILE 3: `options-bot/risk/risk_manager.py`

```python
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
```

---

## FILE 4: `options-bot/strategies/__init__.py`

```python
```

---

## FILE 5: `options-bot/strategies/base_strategy.py`

```python
"""
Base strategy class with shared logic for all profile types.
Matches PROJECT_ARCHITECTURE.md Section 4 — One Strategy instance per profile.

Handles:
    - Exit logic (profit target, stop loss, max hold, DTE floor)
    - Trade logging to SQLite
    - Feature computation for live predictions
    - Model loading and prediction
    - Position tracking

Subclasses (SwingStrategy, GeneralStrategy) only need to implement:
    - get_prediction_horizon_bars()
    - get_feature_set_name()
"""

import json
import uuid
import logging
import datetime
from typing import Optional

from lumibot.strategies import Strategy
from lumibot.entities import Asset

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH, MODELS_DIR
from ml.xgboost_predictor import XGBoostPredictor
from ml.ev_filter import scan_chain_for_best_ev
from risk.risk_manager import RiskManager

logger = logging.getLogger("options-bot.strategy.base")


class BaseOptionsStrategy(Strategy):
    """
    Base strategy for all options trading profiles.
    Do not instantiate directly — use SwingStrategy or GeneralStrategy.
    """

    # Subclasses set these
    parameters = {
        "profile_id": None,
        "profile_name": "Unnamed",
        "symbol": "TSLA",
        "preset": "swing",
        "config": {},
        "model_path": None,
    }

    def initialize(self):
        """Called once at startup."""
        self.profile_id = self.parameters.get("profile_id", "unknown")
        self.profile_name = self.parameters.get("profile_name", "Unnamed")
        self.symbol = self.parameters.get("symbol", "TSLA")
        self.preset = self.parameters.get("preset", "swing")
        self.config = self.parameters.get("config", {})
        self.model_path = self.parameters.get("model_path")

        # Set sleep time from config
        self.sleeptime = self.config.get("sleeptime", "5min")

        logger.info(f"Initializing {self.profile_name} ({self.preset}) on {self.symbol}")
        logger.info(f"  Profile ID: {self.profile_id}")
        logger.info(f"  Sleep time: {self.sleeptime}")
        logger.info(f"  Config: {json.dumps(self.config, indent=2)}")

        # Load ML model
        self.predictor = None
        if self.model_path:
            try:
                self.predictor = XGBoostPredictor(self.model_path)
                logger.info(f"  Model loaded: {self.model_path}")
            except Exception as e:
                logger.error(f"  Failed to load model: {e}", exc_info=True)

        # Initialize risk manager
        self.risk_mgr = RiskManager()

        # Track our open positions: {trade_id: {asset, entry_price, entry_date, ...}}
        self._open_trades = {}

        # Stock asset for price lookups
        self._stock_asset = Asset(self.symbol, asset_type="stock")

        logger.info(f"Strategy initialized: {self.profile_name}")

    def on_trading_iteration(self):
        """Main trading loop — called every sleeptime."""
        logger.info(f"--- {self.profile_name} iteration at {self.get_datetime()} ---")

        try:
            # STEP 1: Check exits FIRST (Architecture Section 9)
            self._check_exits()

            # STEP 2: Check for new entries
            if self.predictor is not None:
                self._check_entries()
            else:
                logger.warning("No model loaded — skipping entries")

        except Exception as e:
            logger.error(f"Error in trading iteration: {e}", exc_info=True)

    # =========================================================================
    # EXIT LOGIC
    # Architecture Section 9 — Exit rules checked BEFORE entries, every iteration
    # Order: profit target → stop loss → max hold → DTE floor → model override
    # First match wins.
    # =========================================================================

    def _check_exits(self):
        """Check all open positions for exit conditions."""
        positions = self.get_positions()
        if not positions:
            return

        now = self.get_datetime()
        today = now.date()

        for position in positions:
            asset = position.asset
            if asset.asset_type != "option":
                continue

            # Find our trade record for this position
            trade_id = None
            trade_info = None
            for tid, tinfo in self._open_trades.items():
                if (tinfo["symbol"] == asset.symbol and
                    tinfo["strike"] == asset.strike and
                    tinfo["expiration"] == asset.expiration and
                    tinfo["right"] == asset.right):
                    trade_id = tid
                    trade_info = tinfo
                    break

            if not trade_info:
                logger.warning(f"Open position not tracked: {asset}")
                continue

            # Get current option price
            current_price = self.get_last_price(asset)
            if current_price is None:
                logger.warning(f"Cannot get price for {asset} — skipping exit check")
                continue

            entry_price = trade_info["entry_price"]
            pnl_pct = ((current_price - entry_price) / entry_price) * 100

            # Get current underlying price
            underlying_price = self.get_last_price(self._stock_asset) or 0

            # Exit rule checks
            exit_reason = None

            # 1. Profit Target
            profit_target = self.config.get("profit_target_pct", 50)
            if pnl_pct >= profit_target:
                exit_reason = "profit_target"

            # 2. Stop Loss
            if exit_reason is None:
                stop_loss = self.config.get("stop_loss_pct", 30)
                if pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"

            # 3. Max Holding Days
            if exit_reason is None:
                max_hold = self.config.get("max_hold_days", 7)
                entry_date = datetime.datetime.fromisoformat(trade_info["entry_date"]).date()
                hold_days = (today - entry_date).days
                if hold_days >= max_hold:
                    exit_reason = "max_hold"

            # 4. DTE Floor
            if exit_reason is None:
                dte = (asset.expiration - today).days
                if dte < 3:
                    exit_reason = "dte_exit"

            # Execute exit if triggered
            if exit_reason:
                self._execute_exit(
                    trade_id=trade_id,
                    trade_info=trade_info,
                    position=position,
                    asset=asset,
                    current_price=current_price,
                    underlying_price=underlying_price,
                    exit_reason=exit_reason,
                )

    def _execute_exit(
        self, trade_id, trade_info, position, asset,
        current_price, underlying_price, exit_reason,
    ):
        """Execute a sell_to_close order and log it."""
        logger.info(
            f"EXIT: {trade_info['symbol']} {trade_info['strike']} {trade_info['right']} "
            f"reason={exit_reason} price=${current_price:.2f}"
        )

        try:
            quantity = abs(position.quantity)
            order = self.create_order(
                asset, quantity, side="sell_to_close"
            )
            self.submit_order(order)

            # Calculate P&L
            entry_price = trade_info["entry_price"]
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            pnl_dollars = (current_price - entry_price) * quantity * 100

            entry_date = datetime.datetime.fromisoformat(trade_info["entry_date"]).date()
            hold_days = (self.get_datetime().date() - entry_date).days
            was_day_trade = hold_days == 0

            # Get exit Greeks
            exit_greeks = self.get_greeks(asset, underlying_price=underlying_price)
            exit_greeks_dict = {}
            if exit_greeks:
                exit_greeks_dict = {
                    "delta": exit_greeks.get("delta"),
                    "gamma": exit_greeks.get("gamma"),
                    "theta": exit_greeks.get("theta"),
                    "vega": exit_greeks.get("vega"),
                    "iv": exit_greeks.get("implied_volatility"),
                }

            # Log to database
            self.risk_mgr.log_trade_close(
                trade_id=trade_id,
                exit_price=current_price,
                exit_underlying_price=underlying_price,
                exit_reason=exit_reason,
                exit_greeks=exit_greeks_dict,
                pnl_dollars=pnl_dollars,
                pnl_pct=pnl_pct,
                hold_days=hold_days,
                was_day_trade=was_day_trade,
            )

            # Remove from tracking
            del self._open_trades[trade_id]

            logger.info(
                f"EXIT complete: P&L=${pnl_dollars:.2f} ({pnl_pct:.1f}%) "
                f"hold={hold_days}d reason={exit_reason}"
            )

        except Exception as e:
            logger.error(f"Exit order failed: {e}", exc_info=True)

    # =========================================================================
    # ENTRY LOGIC
    # Architecture Section 9 — Entry steps 1-12
    # =========================================================================

    def _check_entries(self):
        """Evaluate whether to open a new position."""
        # Step 1: Get current underlying price
        underlying_price = self.get_last_price(self._stock_asset)
        if underlying_price is None:
            logger.warning(f"Cannot get price for {self.symbol}")
            return

        logger.info(f"  {self.symbol} price: ${underlying_price:.2f}")

        # Step 2: Get historical bars for feature computation
        try:
            bars_result = self.get_historical_prices(
                self._stock_asset, length=200, timestep="5min"
            )
            if bars_result is None or bars_result.df.empty:
                logger.warning("No historical bars available")
                return
            bars_df = bars_result.df
        except Exception as e:
            logger.error(f"Failed to get historical bars: {e}")
            return

        # Step 4: Compute features
        from ml.feature_engineering.base_features import compute_base_features
        try:
            featured_df = compute_base_features(bars_df.copy())

            # Add style-specific features
            if self.preset == "swing":
                from ml.feature_engineering.swing_features import compute_swing_features
                featured_df = compute_swing_features(featured_df)
            elif self.preset == "general":
                from ml.feature_engineering.general_features import compute_general_features
                featured_df = compute_general_features(featured_df)
        except Exception as e:
            logger.error(f"Feature computation failed: {e}")
            return

        # Get the latest bar's features as a dict
        if featured_df.empty:
            return
        latest_features = featured_df.iloc[-1].to_dict()

        # Step 5: ML prediction
        try:
            predicted_return = self.predictor.predict(latest_features)
        except Exception as e:
            logger.error(f"Model prediction failed: {e}")
            return

        logger.info(f"  Predicted return: {predicted_return:.3f}%")

        # Step 6: Check minimum threshold
        min_move = self.config.get("min_predicted_move_pct", 1.0)
        if abs(predicted_return) < min_move:
            logger.info(f"  Prediction {predicted_return:.3f}% below threshold {min_move}% — skipping")
            return

        # Step 7: Direction determined by prediction sign (CALL if +, PUT if -)

        # Step 8: Risk manager check
        portfolio_value = self.get_portfolio_value()

        # PDT check — we don't know yet if this will be a day trade,
        # but if we're near the limit, be cautious
        pdt = self.risk_mgr.check_pdt(portfolio_value)
        if not pdt["allowed"]:
            logger.warning(f"  {pdt['message']} — skipping entry")
            return

        # Step 9: Scan chain through EV filter
        min_dte = self.config.get("min_dte", 7)
        max_dte = self.config.get("max_dte", 45)
        max_hold = self.config.get("max_hold_days", 7)
        min_ev = self.config.get("min_ev_pct", 10)

        best_contract = scan_chain_for_best_ev(
            strategy=self,
            symbol=self.symbol,
            predicted_return_pct=predicted_return,
            underlying_price=underlying_price,
            min_dte=min_dte,
            max_dte=max_dte,
            max_hold_days=max_hold,
            min_ev_pct=min_ev,
        )

        if best_contract is None:
            logger.info("  No contract meets EV threshold — no trade")
            return

        # Step 10: Position sizing + risk checks
        risk_check = self.risk_mgr.check_can_open_position(
            profile_id=self.profile_id,
            profile_config=self.config,
            portfolio_value=portfolio_value,
            option_price=best_contract.premium,
        )

        if not risk_check["allowed"]:
            logger.warning(f"  Risk check failed: {risk_check['reasons']}")
            return

        quantity = risk_check["quantity"]

        # Step 11: Submit order
        option_asset = Asset(
            symbol=self.symbol,
            asset_type="option",
            expiration=best_contract.expiration,
            strike=best_contract.strike,
            right=best_contract.right,
        )

        trade_id = str(uuid.uuid4())

        try:
            order = self.create_order(
                option_asset, quantity, side="buy_to_open"
            )
            self.submit_order(order)

            logger.info(
                f"  ORDER SUBMITTED: {quantity}x {best_contract.right} "
                f"${best_contract.strike} exp={best_contract.expiration} "
                f"@ ${best_contract.premium:.2f}"
            )

            # Track the trade locally
            entry_greeks = {
                "delta": best_contract.delta,
                "gamma": best_contract.gamma,
                "theta": best_contract.theta,
                "vega": best_contract.vega,
                "iv": best_contract.implied_volatility,
            }

            self._open_trades[trade_id] = {
                "symbol": self.symbol,
                "strike": best_contract.strike,
                "expiration": best_contract.expiration,
                "right": best_contract.right,
                "entry_price": best_contract.premium,
                "entry_date": self.get_datetime().isoformat(),
                "entry_underlying_price": underlying_price,
                "quantity": quantity,
            }

            # Step 12: Log EVERYTHING
            # Filter features to only include numeric/serializable values
            loggable_features = {}
            for k, v in latest_features.items():
                if k in ["open", "high", "low", "close", "volume"]:
                    continue
                try:
                    if v is not None and not (isinstance(v, float) and (v != v)):  # NaN check
                        loggable_features[k] = float(v) if isinstance(v, (int, float)) else str(v)
                except (TypeError, ValueError):
                    pass

            self.risk_mgr.log_trade_open(
                trade_id=trade_id,
                profile_id=self.profile_id,
                symbol=self.symbol,
                direction=best_contract.right,
                strike=best_contract.strike,
                expiration=str(best_contract.expiration),
                quantity=quantity,
                entry_price=best_contract.premium,
                entry_underlying_price=underlying_price,
                predicted_return=predicted_return,
                ev_pct=best_contract.ev_pct,
                features=loggable_features,
                greeks=entry_greeks,
                model_type="xgboost",
            )

        except Exception as e:
            logger.error(f"  Order submission failed: {e}", exc_info=True)

    # =========================================================================
    # LIFECYCLE HOOKS
    # =========================================================================

    def on_filled_order(self, position, order, price, quantity, multiplier):
        """Called when an order fills."""
        logger.info(
            f"ORDER FILLED: {order.side} {quantity}x {position.asset} @ ${price:.2f}"
        )

    def on_canceled_order(self, order):
        """Called when an order is canceled."""
        logger.warning(f"ORDER CANCELED: {order}")

    def on_bot_crash(self, error):
        """Called on unhandled crash."""
        logger.error(f"BOT CRASH: {error}", exc_info=True)

    def before_market_opens(self):
        """Called before market open."""
        logger.info(f"{self.profile_name}: Market opening soon")

    def after_market_closes(self):
        """Called after market close."""
        logger.info(
            f"{self.profile_name}: Market closed. "
            f"Open trades: {len(self._open_trades)}"
        )

    def trace_stats(self, context, snapshot_before):
        """Return custom stats for logging."""
        return {
            "profile": self.profile_name,
            "symbol": self.symbol,
            "open_trades": len(self._open_trades),
            "portfolio_value": self.get_portfolio_value(),
        }
```

---

## FILE 6: `options-bot/strategies/swing_strategy.py`

```python
"""
Swing trading strategy.
Matches PROJECT_ARCHITECTURE.md Section 6 — Swing preset.

Configuration (from preset defaults):
    - min_dte: 7
    - max_dte: 45
    - max_hold_days: 7
    - prediction_horizon: 5d
    - profit_target_pct: 50
    - stop_loss_pct: 30
    - sleeptime: 5min

All trading logic inherited from BaseOptionsStrategy.
This class exists to:
    1. Be explicitly named for clarity
    2. Allow swing-specific overrides in the future
"""

import logging

from strategies.base_strategy import BaseOptionsStrategy

logger = logging.getLogger("options-bot.strategy.swing")


class SwingStrategy(BaseOptionsStrategy):
    """Swing trading strategy — 7+ DTE options, hold up to 7 days."""
    pass
```

---

## STEP 7: Update main.py to launch a strategy

**File**: `options-bot/main.py` (REPLACE existing content)

```python
"""
Options Bot entry point.
Starts the FastAPI backend and optionally launches a trading strategy.

Usage:
    # Start backend only:
    python main.py

    # Start backend + paper trading:
    python main.py --trade --profile-id <uuid>

    # Quick test with TSLA swing (no profile required):
    python main.py --trade --symbol TSLA --preset swing --model-path models/<file>.joblib
"""

import argparse
import json
import logging
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import LOG_FORMAT, LOG_LEVEL, DB_PATH, PRESET_DEFAULTS

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("options-bot.main")


def start_backend():
    """Start the FastAPI backend in a background thread."""
    import uvicorn
    from backend.app import app

    def _run():
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info("FastAPI backend started at http://localhost:8000")
    return thread


def load_profile_from_db(profile_id: str) -> dict:
    """Load profile config from database."""
    import aiosqlite
    import asyncio

    async def _load():
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM profiles WHERE id = ?", (profile_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None

            # Also load model path
            model_path = None
            if row["model_id"]:
                cursor2 = await db.execute(
                    "SELECT file_path FROM models WHERE id = ?",
                    (row["model_id"],),
                )
                mrow = await cursor2.fetchone()
                if mrow:
                    model_path = mrow["file_path"]

            return {
                "profile_id": row["id"],
                "profile_name": row["name"],
                "symbol": json.loads(row["symbols"])[0],
                "preset": row["preset"],
                "config": json.loads(row["config"]),
                "model_path": model_path,
            }

    return asyncio.run(_load())


def start_trading(params: dict):
    """Launch a Lumibot strategy for paper trading."""
    from lumibot.brokers import Alpaca
    from lumibot.traders import Trader
    from config import ALPACA_API_KEY, ALPACA_API_SECRET

    logger.info(f"Starting paper trading: {params.get('profile_name', 'Manual')}")

    broker = Alpaca({
        "API_KEY": ALPACA_API_KEY,
        "API_SECRET": ALPACA_API_SECRET,
        "PAPER": True,
    })

    preset = params.get("preset", "swing")
    if preset == "swing":
        from strategies.swing_strategy import SwingStrategy
        strategy_class = SwingStrategy
    elif preset == "general":
        # GeneralStrategy not yet created — use base for now
        from strategies.base_strategy import BaseOptionsStrategy
        strategy_class = BaseOptionsStrategy
    else:
        from strategies.base_strategy import BaseOptionsStrategy
        strategy_class = BaseOptionsStrategy

    strategy = strategy_class(
        broker=broker,
        name=params.get("profile_name", f"{preset}_{params.get('symbol', 'TSLA')}"),
        parameters=params,
    )

    trader = Trader()
    trader.add_strategy(strategy)

    logger.info("Launching Lumibot trader...")
    trader.run_all()


def main():
    parser = argparse.ArgumentParser(description="Options Bot")
    parser.add_argument("--trade", action="store_true", help="Start paper trading")
    parser.add_argument("--profile-id", type=str, help="Profile UUID to trade")
    parser.add_argument("--symbol", type=str, default="TSLA", help="Ticker symbol")
    parser.add_argument("--preset", type=str, default="swing", help="Trading preset")
    parser.add_argument("--model-path", type=str, help="Path to model .joblib file")
    parser.add_argument("--no-backend", action="store_true", help="Skip starting FastAPI")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OPTIONS BOT STARTING")
    logger.info("=" * 60)

    # Start backend unless disabled
    if not args.no_backend:
        start_backend()

    if args.trade:
        if args.profile_id:
            # Load from database
            params = load_profile_from_db(args.profile_id)
            if not params:
                logger.error(f"Profile {args.profile_id} not found")
                sys.exit(1)
            if not params.get("model_path"):
                logger.error("Profile has no trained model. Run training first.")
                sys.exit(1)
        else:
            # Manual params
            if not args.model_path:
                logger.error("--model-path required when not using --profile-id")
                sys.exit(1)
            preset = args.preset
            if preset not in PRESET_DEFAULTS:
                logger.error(f"Invalid preset: {preset}")
                sys.exit(1)
            params = {
                "profile_id": "manual",
                "profile_name": f"{args.symbol} {preset.title()}",
                "symbol": args.symbol,
                "preset": preset,
                "config": PRESET_DEFAULTS[preset],
                "model_path": args.model_path,
            }

        start_trading(params)
    else:
        logger.info("Backend-only mode. Use --trade to start paper trading.")
        logger.info("Swagger docs: http://localhost:8000/docs")
        # Keep main thread alive
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down...")


if __name__ == "__main__":
    main()
```

---

## VERIFICATION

After creating all files, run these commands:

```bash
cd options-bot

# 1. Verify files exist
echo "=== Checking files ==="
for f in \
    ml/ev_filter.py \
    risk/__init__.py \
    risk/risk_manager.py \
    strategies/__init__.py \
    strategies/base_strategy.py \
    strategies/swing_strategy.py \
    main.py; do
    if [ -f "$f" ]; then echo "  ✅ $f"; else echo "  ❌ MISSING: $f"; fi
done

# 2. Verify imports
echo ""
echo "=== Testing imports ==="
python -c "from ml.ev_filter import scan_chain_for_best_ev, EVCandidate; print('  ✅ ev_filter.py')"
python -c "from risk.risk_manager import RiskManager; print('  ✅ risk_manager.py')"
python -c "from strategies.base_strategy import BaseOptionsStrategy; print('  ✅ base_strategy.py')"
python -c "from strategies.swing_strategy import SwingStrategy; print('  ✅ swing_strategy.py')"

# 3. Test risk manager DB operations
echo ""
echo "=== Testing risk manager ==="
python -c "
from risk.risk_manager import RiskManager
rm = RiskManager()
print('  PDT count:', rm.get_day_trade_count())
print('  PDT check:', rm.check_pdt(25000))
print('  Position size:', rm.calculate_position_size(25000, 5.50, 20, 5))
print('  ✅ RiskManager working')
"

# 4. Test main.py starts backend (quick check)
echo ""
echo "=== Testing main.py backend start ==="
timeout 5 python main.py 2>&1 | head -10 || true
echo "  ✅ main.py starts without crash"

# 5. Show model files available for trading
echo ""
echo "=== Available models ==="
ls -la models/*.joblib 2>/dev/null || echo "  No models found — run train_model.py first"
```

## WHAT SUCCESS LOOKS LIKE

1. All 7 files created (6 new + main.py replaced)
2. All imports clean
3. RiskManager connects to SQLite, returns PDT count, calculates position sizes
4. main.py starts backend without crash
5. At least one .joblib model exists from Prompt 05

**To actually paper trade** (do this manually after verifying):
```bash
# Find your model file
ls models/*.joblib

# Start paper trading
python main.py --trade --symbol TSLA --preset swing --model-path models/<your_model_file>.joblib
```

The bot will:
- Start FastAPI backend on port 8000
- Connect to Alpaca paper trading
- Run the swing strategy every 5 minutes
- Compute features from live 5-min bars
- Make predictions using the trained model
- Scan chains for best EV contract
- Submit orders if all risk checks pass
- Log everything to SQLite

**You may not see trades immediately** — the model needs to predict a move > 1% AND find a contract with EV > 10%. This is expected behavior. Check logs for "Prediction below threshold" or "No contract meets EV threshold" messages.

## WHAT FAILURE LOOKS LIKE

- Import errors (check all previous prompts were completed)
- Alpaca connection failure (check .env keys)
- Model not found (check models/ directory)
- Database errors (ensure Prompt 02 was completed and DB exists)
- Strategy crashes on first iteration (check logs for exact error)

## DO NOT

- Do NOT modify any files from previous prompts (except main.py which is replaced)
- Do NOT create general_strategy.py yet (Phase 2)
- Do NOT add backtesting code yet (Prompt 07)
- Do NOT add incremental retraining (Phase 2)
- Do NOT add any files not listed here
