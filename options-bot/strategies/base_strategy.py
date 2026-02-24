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
        self.sleeptime = self.config.get("sleeptime", "5M")

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

        # Pre-fetch 5-min bars from Alpaca for backtesting.
        # ThetaData Standard only provides EOD stock data, so we use Alpaca
        # for intraday bars needed by the ML feature pipeline.
        self._cached_5min_bars = None
        backtest_start = self.parameters.get("backtest_start")
        backtest_end = self.parameters.get("backtest_end")
        if backtest_start and backtest_end:
            try:
                from data.alpaca_provider import AlpacaStockProvider
                provider = AlpacaStockProvider()
                # Add 45-day buffer before start for lookback warmup
                bt_start = datetime.datetime.strptime(backtest_start, "%Y-%m-%d")
                bt_end = datetime.datetime.strptime(backtest_end, "%Y-%m-%d")
                fetch_start = bt_start - datetime.timedelta(days=45)
                fetch_end = bt_end + datetime.timedelta(days=1)
                logger.info(f"  Pre-fetching 5-min bars from Alpaca: {fetch_start.date()} to {fetch_end.date()}...")
                self._cached_5min_bars = provider.get_historical_bars(
                    self.symbol, fetch_start, fetch_end, timeframe="5min"
                )
                logger.info(f"  Pre-fetched {len(self._cached_5min_bars)} 5-min bars from Alpaca")
            except Exception as e:
                logger.error(f"  Failed to pre-fetch 5-min bars from Alpaca: {e}", exc_info=True)

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
    # Order: profit target -> stop loss -> max hold -> DTE floor -> model override
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
            logger.warning(f"ENTRY STEP 1 FAIL: Cannot get price for {self.symbol}")
            return

        logger.info(f"  ENTRY STEP 1 OK: {self.symbol} price=${underlying_price:.2f}")

        # Step 2: Get historical 5-min bars for feature computation.
        # In backtesting, we use pre-cached Alpaca bars (ThetaData Standard
        # only has EOD stock data). In live trading, use Lumibot data store.
        if self._cached_5min_bars is not None and not self._cached_5min_bars.empty:
            # BACKTEST PATH: slice cached Alpaca bars up to current sim time
            current_dt = self.get_datetime()
            # Make timezone-aware comparison work
            cached_idx = self._cached_5min_bars.index
            if cached_idx.tz is not None and current_dt.tzinfo is not None:
                current_dt = current_dt.astimezone(cached_idx.tz)
            elif cached_idx.tz is not None:
                import pytz
                current_dt = pytz.UTC.localize(current_dt)
            elif current_dt.tzinfo is not None:
                current_dt = current_dt.replace(tzinfo=None)

            bars_df = self._cached_5min_bars[self._cached_5min_bars.index <= current_dt].tail(200)
            if len(bars_df) < 50:
                logger.warning(f"ENTRY STEP 2: Only {len(bars_df)} cached bars available (need 50+)")
                return
            logger.info(f"  ENTRY STEP 2 OK: Got {len(bars_df)} 5-min bars from Alpaca cache")
        else:
            # LIVE PATH: use Lumibot's data store
            try:
                bars_result = self.get_historical_prices(
                    self._stock_asset, length=200, timestep="5min"
                )
            except Exception as e:
                logger.error(
                    f"CRITICAL: get_historical_prices() raised: {e}",
                    exc_info=True,
                )
                return

            if bars_result is None or bars_result.df is None or bars_result.df.empty:
                logger.error(
                    "CRITICAL: get_historical_prices() returned no data. "
                    "No 5-min bars available for feature computation."
                )
                return

            bars_df = bars_result.df
            logger.info(f"  ENTRY STEP 2 OK: Got {len(bars_df)} bars from data store")

            # If MultiIndex, flatten to just the datetime level
            if hasattr(bars_df.index, 'levels'):
                bars_df = bars_df.droplevel(0) if len(bars_df.index.levels) > 1 else bars_df

        # Ensure lowercase column names
        bars_df.columns = [c.lower() for c in bars_df.columns]

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

            logger.info(
                f"  ENTRY STEP 4 OK: Features computed, "
                f"{len(featured_df)} rows, {len(featured_df.columns)} columns"
            )
        except Exception as e:
            logger.error(f"ENTRY STEP 4 FAIL: Feature computation failed: {e}", exc_info=True)
            return

        # Get the latest bar's features as a dict
        if featured_df.empty:
            logger.warning("ENTRY STEP 4 FAIL: featured_df is empty after computation")
            return
        latest_features = featured_df.iloc[-1].to_dict()

        # Count NaN features
        nan_count = sum(1 for v in latest_features.values()
                        if isinstance(v, float) and v != v)
        total_features = len(latest_features)
        logger.info(f"  Features: {total_features} total, {nan_count} NaN")

        # Step 5: ML prediction
        try:
            predicted_return = self.predictor.predict(latest_features)
        except Exception as e:
            logger.error(f"ENTRY STEP 5 FAIL: Model prediction failed: {e}", exc_info=True)
            return

        logger.info(f"  ENTRY STEP 5 OK: Predicted return={predicted_return:.3f}%")

        # Step 6: Check minimum threshold
        min_move = self.config.get("min_predicted_move_pct", 1.0)
        if abs(predicted_return) < min_move:
            logger.info(f"  ENTRY STEP 6 SKIP: |{predicted_return:.3f}%| < {min_move}% threshold")
            return

        logger.info(f"  ENTRY STEP 6 OK: |{predicted_return:.3f}%| >= {min_move}% threshold")

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
