"""
Iron Condor strategy — 0DTE SPY premium selling with ML regime filter.

This strategy sells iron condors (credit spreads on both sides) when the
GEX regime calculator determines conditions are safe for premium selling.
It overrides the directional buying logic in BaseOptionsStrategy with
multi-leg premium selling logic.

Entry:
  1. GEX regime filter: only enter when regime = 'sell_premium'
  2. Time window: 10:00 AM - 2:30 PM ET (no opening whipsaw, no late theta)
  3. Cooldown: configurable minutes between entries
  4. Select ~16 delta short strikes, $3 wide spreads
  5. Submit 4-leg order via Lumibot multi-leg API

Exit:
  1. Close at 75% of max profit (simulation shows +EV at 72% win rate)
  2. Close at 1x credit received (tight stop — keeps win/loss ratio viable)
  3. Close at 3:30 PM ET regardless (avoid last-30-min gamma risk)

Position tracking:
  - _open_ic_trades: dict of {trade_id: IronCondorPosition}
  - Multi-leg P&L computed from current prices of all 4 legs
"""

import json
import sqlite3
import time
import uuid
import logging
import datetime
from typing import Optional
from dataclasses import dataclass, field

import numpy as np

from strategies.base_strategy import BaseOptionsStrategy
from strategies.iron_condor import (
    select_iron_condor_strikes,
    build_iron_condor_orders,
    build_iron_condor_close_orders,
    IronCondorLegs,
)
from ml.gex_calculator import compute_gex_features, GEXResult

from lumibot.entities import Asset

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH

logger = logging.getLogger("options-bot.strategy.iron_condor")


@dataclass
class IronCondorPosition:
    """Tracks an open iron condor position."""
    trade_id: str
    legs: IronCondorLegs
    quantity: int
    credit_received: float       # per contract
    max_loss: float              # per contract
    entry_time: str
    entry_underlying_price: float
    gex_regime: str
    gex_confidence: float


class IronCondorStrategy(BaseOptionsStrategy):
    """
    Iron condor premium selling strategy.
    Overrides the directional entry/exit logic with spread-based logic.
    """

    def initialize(self):
        """Initialize — call parent, then set up IC-specific state."""
        super().initialize()
        self._open_ic_trades: dict[str, IronCondorPosition] = {}
        self._last_gex_result: Optional[GEXResult] = None
        self._last_gex_time: Optional[datetime.datetime] = None
        self._gex_cache_minutes = self.config.get("gex_cache_minutes", 5)
        logger.info("IronCondorStrategy initialized")

    def on_trading_iteration(self):
        """
        Main loop — check exits first, then check for new entries.
        Overrides BaseOptionsStrategy to use IC-specific logic.
        """
        # Emergency stop loss from parent
        if self._check_emergency_stop():
            return

        # Check exits on open IC positions
        self._check_ic_exits()

        # Check for new IC entries
        self._check_ic_entries()

    def _get_gex_regime(self) -> Optional[GEXResult]:
        """
        Get GEX regime, with caching to avoid hitting API every iteration.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        if (self._last_gex_result is not None
                and self._last_gex_time is not None
                and (now - self._last_gex_time).total_seconds() < self._gex_cache_minutes * 60):
            return self._last_gex_result

        result = compute_gex_features(self, self.symbol)
        if result:
            self._last_gex_result = result
            self._last_gex_time = now
        return result

    def _check_ic_entries(self):
        """Evaluate whether to open a new iron condor."""
        logger.info("IC _check_entries: starting")

        # Gate 1: Cooldown
        if self._last_entry_time is not None and self._cooldown_minutes > 0:
            now = self.get_datetime()
            elapsed = (now - self._last_entry_time).total_seconds() / 60
            if elapsed < self._cooldown_minutes:
                logger.info(f"  IC SKIP: Cooldown ({elapsed:.0f}min < {self._cooldown_minutes}min)")
                return

        # Gate 2: Time window (10:00 AM - 2:30 PM ET)
        try:
            from zoneinfo import ZoneInfo
            now = self.get_datetime()
            eastern = ZoneInfo("America/New_York")
            now_et = now.astimezone(eastern) if now.tzinfo else now.replace(tzinfo=ZoneInfo("UTC")).astimezone(eastern)
            hour, minute = now_et.hour, now_et.minute
            time_decimal = hour + minute / 60

            if time_decimal < 10.0:
                logger.info(f"  IC SKIP: Too early ({now_et.strftime('%H:%M')} ET < 10:00)")
                return
            if time_decimal > 14.5:
                logger.info(f"  IC SKIP: Too late ({now_et.strftime('%H:%M')} ET > 14:30)")
                return
        except Exception as e:
            logger.warning(f"  IC: Time check failed: {e}")

        # Gate 3: Max concurrent IC positions
        max_concurrent = self.config.get("max_concurrent_positions", 2)
        if len(self._open_ic_trades) >= max_concurrent:
            logger.info(f"  IC SKIP: Max concurrent ({len(self._open_ic_trades)}/{max_concurrent})")
            return

        # Gate 4: GEX regime filter
        gex = self._get_gex_regime()
        if gex is None:
            logger.warning("  IC SKIP: GEX data unavailable")
            return

        if gex.regime != "sell_premium":
            logger.info(
                f"  IC SKIP: GEX regime={gex.regime} (conf={gex.confidence:.2f}). "
                f"Need 'sell_premium' for iron condor entry."
            )
            self._write_signal_log(
                underlying_price=gex.underlying_price,
                step_stopped_at=1.5,
                stop_reason=f"GEX regime={gex.regime} (need sell_premium)",
            )
            return

        # Gate 5: ML model confidence (if predictor available)
        # The ML model acts as a secondary filter — if it has strong directional
        # conviction, don't sell premium (the market may be about to move)
        if self.predictor is not None:
            try:
                underlying_price = self.get_last_price(self._stock_asset)
                bars_df = self._fetch_bars()
                if bars_df is not None and len(bars_df) >= 50:
                    from features.base_features import compute_all_features
                    featured_df = compute_all_features(bars_df, self.config.get("feature_set", "scalp"))
                    latest_features = featured_df.iloc[-1].to_dict()
                    prediction = self.predictor.predict(latest_features)
                    confidence = abs(prediction) if prediction is not None else 0

                    # If model has high directional conviction, skip the IC
                    max_confidence_for_ic = self.config.get("max_confidence_for_ic", 0.35)
                    if confidence > max_confidence_for_ic:
                        logger.info(
                            f"  IC SKIP: Model confidence {confidence:.3f} > {max_confidence_for_ic} "
                            f"— strong directional signal, not safe for premium selling"
                        )
                        return
            except Exception as e:
                logger.debug(f"  IC: ML filter check failed (non-blocking): {e}")

        # All gates passed — construct the iron condor
        underlying_price = gex.underlying_price

        # Get available strikes for today
        chains = self.get_chains(self._stock_asset)
        if not chains or "Chains" not in chains:
            logger.warning("  IC SKIP: Cannot get option chains")
            return

        # Collect all available strikes for today's expiration
        from datetime import date
        today = date.today()
        today_str = today.strftime("%Y-%m-%d")
        available_strikes = set()
        for right in ("CALL", "PUT"):
            if right in chains.get("Chains", {}):
                for exp_str, strikes in chains["Chains"][right].items():
                    if exp_str == today_str:
                        available_strikes.update(strikes)

        if len(available_strikes) < 10:
            logger.warning(f"  IC SKIP: Only {len(available_strikes)} strikes available for today")
            return

        # Select strikes
        target_delta = self.config.get("ic_target_delta", 0.16)
        spread_width = self.config.get("ic_spread_width", 3.0)

        legs = select_iron_condor_strikes(
            underlying_price=underlying_price,
            available_strikes=sorted(available_strikes),
            iv=gex.mean_iv if gex.mean_iv > 0 else 0.20,
            hours_remaining=gex.details.get("hours_remaining", 4.0),
            target_delta=target_delta,
            spread_width_dollars=spread_width,
        )

        if legs is None:
            logger.warning("  IC SKIP: Could not select suitable strikes")
            return

        # Position sizing: risk per trade as % of portfolio
        max_risk_pct = self.config.get("max_position_pct", 5)
        portfolio_value = self.get_portfolio_value() or 50000
        max_risk_dollars = portfolio_value * max_risk_pct / 100
        max_loss_per_contract = legs.max_loss * 100  # * 100 for options multiplier
        quantity = max(1, int(max_risk_dollars / max_loss_per_contract)) if max_loss_per_contract > 0 else 1
        max_contracts = self.config.get("max_contracts", 10)
        quantity = min(quantity, max_contracts)

        logger.info(
            f"  IC ENTRY: {quantity}x iron condor on {self.symbol} "
            f"PUT {legs.long_put_strike}/{legs.short_put_strike} "
            f"CALL {legs.short_call_strike}/{legs.long_call_strike} "
            f"credit=${legs.estimated_credit:.2f} max_loss=${legs.max_loss:.2f}"
        )

        # Build and submit multi-leg order
        # Alpaca requires limit price for multi-leg orders. Use estimated credit
        # as the limit (we want to receive at least this much premium).
        try:
            orders = build_iron_condor_orders(self, legs, quantity)
            # Submit as credit order with limit price = estimated net credit
            self.submit_order(
                orders,
                order_type="credit",
                price=round(legs.estimated_credit, 2),
            )

            trade_id = str(uuid.uuid4())
            self._open_ic_trades[trade_id] = IronCondorPosition(
                trade_id=trade_id,
                legs=legs,
                quantity=quantity,
                credit_received=legs.estimated_credit,
                max_loss=legs.max_loss,
                entry_time=self.get_datetime().isoformat(),
                entry_underlying_price=underlying_price,
                gex_regime=gex.regime,
                gex_confidence=gex.confidence,
            )
            self._last_entry_time = self.get_datetime()

            # Log to DB
            try:
                conn = sqlite3.connect(str(DB_PATH), timeout=2)
                now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
                conn.execute(
                    """INSERT INTO trades (id, profile_id, symbol, direction, strike,
                       expiration, quantity, entry_price, entry_date,
                       entry_underlying_price, entry_predicted_return, entry_ev_pct,
                       entry_model_type, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                    (trade_id, self.profile_id, self.symbol,
                     f"IC {legs.short_put_strike}/{legs.short_call_strike}",
                     legs.short_put_strike,  # use short put as primary strike for DB
                     str(legs.expiration), quantity,
                     legs.estimated_credit,  # credit as "entry_price"
                     now_utc, underlying_price,
                     gex.confidence, legs.estimated_credit * 100 / legs.max_loss if legs.max_loss > 0 else 0,
                     "iron_condor", now_utc, now_utc),
                )
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"  IC: Failed to log trade to DB: {e}")

            self._write_signal_log(
                underlying_price=underlying_price,
                predicted_return=gex.confidence,
                step_stopped_at=None,
                entered=True,
                trade_id=trade_id,
            )

            logger.info(f"  IC ENTRY OK: trade_id={trade_id}")

        except Exception as e:
            logger.error(f"  IC ENTRY FAILED: {e}", exc_info=True)

    def _check_ic_exits(self):
        """Check exit conditions for open iron condor positions."""
        if not self._open_ic_trades:
            return

        underlying_price = self.get_last_price(self._stock_asset)
        if not underlying_price:
            return

        # Time check for hard close
        hard_close = False
        try:
            from zoneinfo import ZoneInfo
            now = self.get_datetime()
            eastern = ZoneInfo("America/New_York")
            now_et = now.astimezone(eastern) if now.tzinfo else now.replace(tzinfo=ZoneInfo("UTC")).astimezone(eastern)
            if now_et.hour > 15 or (now_et.hour == 15 and now_et.minute >= 30):
                hard_close = True
        except Exception:
            pass

        for trade_id, ic_pos in list(self._open_ic_trades.items()):
            legs = ic_pos.legs
            exit_reason = None

            # Get current prices of the 4 legs to compute current spread value
            try:
                sp_asset = Asset(self.symbol, asset_type="option", expiration=legs.expiration,
                                 strike=legs.short_put_strike, right="PUT")
                lp_asset = Asset(self.symbol, asset_type="option", expiration=legs.expiration,
                                 strike=legs.long_put_strike, right="PUT")
                sc_asset = Asset(self.symbol, asset_type="option", expiration=legs.expiration,
                                 strike=legs.short_call_strike, right="CALL")
                lc_asset = Asset(self.symbol, asset_type="option", expiration=legs.expiration,
                                 strike=legs.long_call_strike, right="CALL")

                sp_price = self.get_last_price(sp_asset) or 0
                lp_price = self.get_last_price(lp_asset) or 0
                sc_price = self.get_last_price(sc_asset) or 0
                lc_price = self.get_last_price(lc_asset) or 0

                # Current cost to close = buy back short legs, sell long legs
                current_debit = (sp_price - lp_price) + (sc_price - lc_price)
                # P&L = credit received - current cost to close
                pnl_per_contract = ic_pos.credit_received - current_debit
                pnl_pct_of_max = (pnl_per_contract / ic_pos.credit_received * 100
                                  if ic_pos.credit_received > 0 else 0)

                # Update unrealized P&L in DB
                total_pnl = pnl_per_contract * ic_pos.quantity * 100
                try:
                    conn = sqlite3.connect(str(DB_PATH), timeout=2)
                    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    conn.execute(
                        "UPDATE trades SET unrealized_pnl = ?, unrealized_pnl_pct = ?, updated_at = ? WHERE id = ?",
                        (round(total_pnl, 2), round(pnl_pct_of_max, 2), now_utc, trade_id),
                    )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

                # Exit Rule 1: Take profit at 50% of max profit
                profit_target_pct = self.config.get("ic_profit_target_pct", 75)
                if pnl_pct_of_max >= profit_target_pct:
                    exit_reason = "ic_profit_target"
                    logger.info(
                        f"IC EXIT: Profit target hit — "
                        f"P&L={pnl_pct_of_max:.1f}% of max credit >= {profit_target_pct}%"
                    )

                # Exit Rule 2: Stop loss at 2x credit received
                if exit_reason is None:
                    ic_stop_multiplier = self.config.get("ic_stop_multiplier", 1.0)
                    loss_threshold = ic_pos.credit_received * ic_stop_multiplier
                    if current_debit >= loss_threshold:
                        exit_reason = "ic_stop_loss"
                        logger.info(
                            f"IC EXIT: Stop loss — current_debit=${current_debit:.2f} "
                            f">= {ic_stop_multiplier}x credit=${loss_threshold:.2f}"
                        )

                # Exit Rule 3: Hard close at 3:30 PM ET
                if exit_reason is None and hard_close:
                    exit_reason = "ic_eod_close"
                    logger.info("IC EXIT: 3:30 PM hard close")

            except Exception as e:
                logger.error(f"IC exit check failed for {trade_id[:8]}: {e}", exc_info=True)
                continue

            # Execute exit if triggered
            if exit_reason:
                try:
                    close_orders = build_iron_condor_close_orders(self, legs, ic_pos.quantity)
                    # Close as debit order — pay up to current_debit to close
                    self.submit_order(
                        close_orders,
                        order_type="debit",
                        price=round(current_debit, 2),
                    )

                    # Update DB
                    total_pnl = pnl_per_contract * ic_pos.quantity * 100
                    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    try:
                        conn = sqlite3.connect(str(DB_PATH), timeout=2)
                        conn.execute(
                            """UPDATE trades SET exit_price = ?, exit_date = ?,
                               exit_underlying_price = ?, exit_reason = ?,
                               pnl_dollars = ?, pnl_pct = ?,
                               status = 'closed', updated_at = ?
                               WHERE id = ?""",
                            (current_debit, now_utc, underlying_price, exit_reason,
                             round(total_pnl, 2), round(pnl_pct_of_max, 2),
                             now_utc, trade_id),
                        )
                        conn.commit()
                        conn.close()
                    except Exception as e:
                        logger.error(f"IC: Failed to update trade in DB: {e}")

                    del self._open_ic_trades[trade_id]
                    logger.info(
                        f"IC CLOSED: {trade_id[:8]} reason={exit_reason} "
                        f"P&L=${total_pnl:.2f} ({pnl_pct_of_max:.1f}%)"
                    )

                except Exception as e:
                    logger.error(f"IC close order failed: {e}", exc_info=True)

    def _check_emergency_stop(self) -> bool:
        """Check emergency portfolio stop loss. Returns True if trading should halt."""
        try:
            current_value = self.get_portfolio_value()
            if self._initial_portfolio_value == 0.0 and current_value:
                self._initial_portfolio_value = current_value
                return False
            if self._initial_portfolio_value > 0 and current_value:
                drawdown_pct = ((self._initial_portfolio_value - current_value)
                                / self._initial_portfolio_value * 100)
                if drawdown_pct >= self.config.get("max_daily_loss_pct", 20):
                    logger.error(
                        f"EMERGENCY STOP: Portfolio drawdown {drawdown_pct:.1f}% "
                        f"exceeds limit. Halting trading."
                    )
                    return True
        except Exception:
            pass
        return False
