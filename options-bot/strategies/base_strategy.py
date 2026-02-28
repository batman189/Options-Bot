"""
Base strategy class with shared logic for all profile types.
Matches PROJECT_ARCHITECTURE.md Section 4 — One Strategy instance per profile.

Phase 2 additions:
    - Emergency stop loss check at top of on_trading_iteration()
    - _initial_portfolio_value recorded at startup for drawdown tracking
    - _emergency_liquidate_all() — market-sells all open positions
    - Model override exit (rule 5) in _check_exits()

Handles:
    - Exit logic (profit target, stop loss, max hold, DTE floor, model override)
    - Emergency stop loss (portfolio drawdown >= EMERGENCY_STOP_LOSS_PCT)
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
        logger.info("BaseOptionsStrategy.initialize() starting")

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

        # Load ML model — detect type from DB to load correct predictor class
        self.predictor = None
        if self.model_path:
            try:
                model_type = self._detect_model_type()
                logger.info(
                    f"  Loading {model_type} model from: {self.model_path}"
                )
                if model_type == "tft":
                    from ml.tft_predictor import TFTPredictor
                    self.predictor = TFTPredictor(self.model_path)
                elif model_type == "ensemble":
                    from ml.ensemble_predictor import EnsemblePredictor
                    self.predictor = EnsemblePredictor(self.model_path)
                else:
                    # Default: xgboost (covers 'xgboost' and any unknown type)
                    self.predictor = XGBoostPredictor(self.model_path)
                logger.info(
                    f"  Predictor loaded: {type(self.predictor).__name__}"
                )
            except Exception as e:
                logger.error(f"  Failed to load model: {e}", exc_info=True)
                # Fall back to XGBoost as last resort
                try:
                    self.predictor = XGBoostPredictor(self.model_path)
                    logger.warning("  Fell back to XGBoostPredictor after load error")
                except Exception as e2:
                    logger.error(f"  XGBoost fallback also failed: {e2}")

        # Initialize risk manager
        logger.info("  Initializing RiskManager")
        self.risk_mgr = RiskManager()

        # Track our open positions: {trade_id: {asset, entry_price, entry_date, ...}}
        self._open_trades = {}

        # Stock asset for price lookups
        self._stock_asset = Asset(self.symbol, asset_type="stock")

        # Record initial portfolio value for emergency stop loss calculation
        self._initial_portfolio_value = 0.0  # Set on first iteration

        # Pre-fetch 5-min bars from Alpaca for backtesting.
        # ThetaData Standard only provides EOD stock data, so we use Alpaca
        # for intraday bars needed by the ML feature pipeline.
        self._cached_5min_bars = None
        backtest_start = self.parameters.get("backtest_start")
        backtest_end = self.parameters.get("backtest_end")
        self._backtest_mode = bool(backtest_start and backtest_end)

        if backtest_start and backtest_end:
            try:
                from data.alpaca_provider import AlpacaStockProvider
                provider = AlpacaStockProvider()
                # Add 45-day buffer before start for lookback warmup
                bt_start = datetime.datetime.strptime(backtest_start, "%Y-%m-%d")
                bt_end = datetime.datetime.strptime(backtest_end, "%Y-%m-%d")
                fetch_start = bt_start - datetime.timedelta(days=45)
                fetch_end = bt_end + datetime.timedelta(days=1)
                logger.info(
                    f"  Pre-fetching 5-min bars from Alpaca: "
                    f"{fetch_start.date()} to {fetch_end.date()}..."
                )
                self._cached_5min_bars = provider.get_historical_bars(
                    self.symbol, fetch_start, fetch_end, timeframe="5min"
                )
                logger.info(
                    f"  Pre-fetched {len(self._cached_5min_bars)} 5-min bars from Alpaca"
                )
            except Exception as e:
                logger.error(
                    f"  Failed to pre-fetch 5-min bars from Alpaca: {e}", exc_info=True
                )

        logger.info(f"Strategy initialized: {self.profile_name}")

    def _detect_model_type(self) -> str:
        """
        Query the DB to find what model_type is stored for this profile's
        current model. Returns 'xgboost' as default if anything fails.

        This is called during initialize() to determine which predictor class
        to instantiate. Avoids hardcoding XGBoostPredictor everywhere.
        """
        import sqlite3

        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=2)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(
                    """SELECT m.model_type
                       FROM models m
                       JOIN profiles p ON p.model_id = m.id
                       WHERE p.id = ?
                       LIMIT 1""",
                    (self.profile_id,),
                )
                row = cursor.fetchone()
                return row["model_type"] if row else "xgboost"
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"_detect_model_type: DB query failed: {e}")
            return "xgboost"

    def on_trading_iteration(self):
        """Main trading loop — called every sleeptime."""
        logger.info(f"--- {self.profile_name} iteration at {self.get_datetime()} ---")

        try:
            portfolio_value = self.get_portfolio_value() or 0.0

            # Record initial portfolio value on first iteration
            if self._initial_portfolio_value == 0.0 and portfolio_value > 0:
                self._initial_portfolio_value = portfolio_value
                logger.info(
                    f"Initial portfolio value recorded: ${portfolio_value:,.2f}"
                )

            # STEP 0a: Emergency stop loss check — liquidate all if portfolio
            # has lost >= EMERGENCY_STOP_LOSS_PCT since strategy start.
            # Architecture Section 11: Portfolio-Level Limits.
            if self._initial_portfolio_value > 0 and not self._backtest_mode:
                emergency = self.risk_mgr.check_emergency_stop_loss(
                    current_portfolio_value=portfolio_value,
                    initial_portfolio_value=self._initial_portfolio_value,
                )
                if emergency["triggered"]:
                    logger.critical(
                        f"EMERGENCY STOP: {emergency['message']} — "
                        f"liquidating all positions and halting entries"
                    )
                    # Close all tracked positions immediately
                    for tid in list(self._open_trades.keys()):
                        try:
                            tinfo = self._open_trades[tid]
                            asset = Asset(
                                symbol=tinfo.get("symbol", self.symbol),
                                asset_type=tinfo.get("asset_type", "option"),
                                strike=tinfo.get("strike"),
                                expiration=tinfo.get("expiration"),
                                right=tinfo.get("right"),
                            )
                            positions = self.get_positions()
                            for pos in positions:
                                if pos.asset == asset:
                                    order = self.create_order(
                                        asset, pos.quantity, side="sell_to_close"
                                    )
                                    self.submit_order(order)
                                    logger.critical(
                                        f"Emergency close submitted: {asset}"
                                    )
                                    break
                        except Exception as e:
                            logger.error(
                                f"Emergency close failed for {tid}: {e}",
                                exc_info=True,
                            )
                    return  # Stop the iteration — no entries after emergency stop

            # STEP 1: Check exits FIRST (Architecture Section 9)
            self._check_exits()

            # STEP 0b: Portfolio exposure check — block new entries if total
            # exposure across all profiles exceeds MAX_TOTAL_EXPOSURE_PCT (60%).
            # Architecture Section 11: Portfolio-Level Limits.
            if not self._backtest_mode and portfolio_value > 0:
                exposure = self.risk_mgr.check_portfolio_exposure(portfolio_value)
                if not exposure["allowed"]:
                    logger.warning(
                        f"Portfolio exposure limit reached "
                        f"({exposure['exposure_pct']:.1f}%) — skipping entries"
                    )
                    return

            # STEP 2: Check for new entries
            if self.predictor is not None:
                self._check_entries()
            else:
                logger.warning("No model loaded — skipping entries")

        except Exception as e:
            logger.error(f"Error in trading iteration: {e}", exc_info=True)

    # =========================================================================
    # EMERGENCY LIQUIDATION (Phase 2)
    # Architecture Section 11 — triggered when drawdown >= EMERGENCY_STOP_LOSS_PCT
    # =========================================================================

    def _emergency_liquidate_all(self):
        """
        Market-sell all open positions immediately.
        Called when portfolio drawdown reaches the emergency stop threshold.
        Does not log to DB — positions will be cleaned up by normal exit logging
        if fills come back through on_filled_order.
        """
        logger.critical("_emergency_liquidate_all: STARTING EMERGENCY LIQUIDATION")
        try:
            positions = self.get_positions()
            if not positions:
                logger.critical("_emergency_liquidate_all: No open positions to liquidate")
                return

            for position in positions:
                try:
                    asset = position.asset
                    quantity = abs(position.quantity)
                    logger.critical(
                        f"_emergency_liquidate_all: selling {quantity}x {asset}"
                    )

                    if asset.asset_type == "option":
                        order = self.create_order(asset, quantity, side="sell_to_close")
                    else:
                        order = self.create_order(asset, quantity, side="sell")

                    self.submit_order(order)
                    logger.critical(
                        f"_emergency_liquidate_all: sell order submitted for {asset}"
                    )
                except Exception as e:
                    logger.error(
                        f"_emergency_liquidate_all: failed to sell {position.asset}: {e}",
                        exc_info=True,
                    )

            logger.critical(
                "_emergency_liquidate_all: all liquidation orders submitted. "
                "Strategy will continue running but no new positions will open "
                "until drawdown recovers below the limit."
            )
        except Exception as e:
            logger.error(
                f"_emergency_liquidate_all: unexpected error: {e}", exc_info=True
            )

    # =========================================================================
    # EXIT LOGIC
    # Architecture Section 9 — Exit rules checked BEFORE entries, every iteration
    # Order: profit target -> stop loss -> max hold -> DTE floor -> model override
    # First match wins.
    # =========================================================================

    def _check_exits(self):
        """Check all open positions for exit conditions."""
        logger.info("_check_exits: starting")
        positions = self.get_positions()
        if not positions:
            logger.info("_check_exits: no open positions")
            return

        now = self.get_datetime()
        today = now.date()

        for position in positions:
            asset = position.asset

            # In backtest mode we trade stock; in live mode we trade options
            if self._backtest_mode:
                if asset.asset_type != "stock":
                    continue
            else:
                if asset.asset_type != "option":
                    continue

            # Find our trade record for this position
            trade_id = None
            trade_info = None
            for tid, tinfo in self._open_trades.items():
                if asset.asset_type == "stock":
                    # Stock: match by symbol
                    if (tinfo["symbol"] == asset.symbol and
                            tinfo.get("asset_type") == "stock"):
                        trade_id = tid
                        trade_info = tinfo
                        break
                else:
                    # Option: match by symbol + strike + expiration + right
                    if (tinfo["symbol"] == asset.symbol and
                            tinfo["strike"] == asset.strike and
                            tinfo["expiration"] == asset.expiration and
                            tinfo["right"] == asset.right):
                        trade_id = tid
                        trade_info = tinfo
                        break

            if not trade_info:
                logger.warning(f"_check_exits: open position not in _open_trades: {asset}")
                continue

            # Get current price
            current_price = self.get_last_price(asset)
            if current_price is None:
                logger.warning(
                    f"_check_exits: cannot get price for {asset} — skipping exit check"
                )
                continue

            entry_price = trade_info["entry_price"]
            direction = trade_info.get("direction", "call")

            # P&L calculation depends on direction
            if direction == "short":
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
            else:
                pnl_pct = ((current_price - entry_price) / entry_price) * 100

            # Get current underlying price
            underlying_price = self.get_last_price(self._stock_asset) or 0

            # ---- Exit rule evaluation (first match wins) ----
            exit_reason = None

            # Rule 1: Profit Target
            # Stock-appropriate thresholds in backtest mode (options config
            # uses 50%/30% which are unreachable for stocks in 7 days)
            if asset.asset_type == "stock":
                profit_target = 5.0
                stop_loss_threshold = 3.0
            else:
                profit_target = self.config.get("profit_target_pct", 50)
                stop_loss_threshold = self.config.get("stop_loss_pct", 30)

            if pnl_pct >= profit_target:
                exit_reason = "profit_target"
                logger.info(
                    f"_check_exits: profit target hit: pnl={pnl_pct:.1f}% >= {profit_target}%"
                )

            # Rule 2: Stop Loss
            if exit_reason is None:
                if pnl_pct <= -stop_loss_threshold:
                    exit_reason = "stop_loss"
                    logger.info(
                        f"_check_exits: stop loss hit: pnl={pnl_pct:.1f}% <= -{stop_loss_threshold}%"
                    )

            # Rule 3: Max Holding Days
            if exit_reason is None:
                max_hold = self.config.get("max_hold_days", 7)
                entry_date = datetime.datetime.fromisoformat(
                    trade_info["entry_date"]
                ).date()
                hold_days = (today - entry_date).days
                if hold_days >= max_hold:
                    exit_reason = "max_hold"
                    logger.info(
                        f"_check_exits: max hold hit: hold_days={hold_days} >= {max_hold}"
                    )

            # Rule 4: DTE Floor (options only)
            if exit_reason is None and asset.asset_type == "option":
                dte = (asset.expiration - today).days
                if dte < 3:
                    exit_reason = "dte_exit"
                    logger.info(f"_check_exits: DTE floor hit: dte={dte} < 3")

            # Rule 5: Model Override (Phase 2 — configurable, off by default)
            # Triggers if the model now predicts a direction reversal vs entry.
            # Only runs if model_override_exit = True in profile config.
            if exit_reason is None:
                model_override_enabled = self.config.get("model_override_exit", False)
                if model_override_enabled and self.predictor is not None:
                    try:
                        override_features = self._get_latest_features_for_override()
                        if override_features is not None:
                            current_prediction = self.predictor.predict(override_features)
                            entry_prediction = trade_info.get("entry_prediction", 0)
                            right = trade_info.get("right", "CALL")
                            # Reversal: entry was bullish (CALL) but model now bearish, or vice versa
                            reversal = (
                                (right == "CALL" and current_prediction < 0) or
                                (right == "PUT" and current_prediction > 0)
                            )
                            if reversal:
                                exit_reason = "model_override"
                                logger.info(
                                    f"_check_exits: model override: entry_pred={entry_prediction:.3f} "
                                    f"current_pred={current_prediction:.3f} right={right}"
                                )
                    except Exception as e:
                        # Never let model errors block the rest of exit logic
                        logger.error(
                            f"_check_exits: model override check failed for {trade_id}: {e}",
                            exc_info=True,
                        )

            # Execute exit if any rule triggered
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

        logger.info("_check_exits: complete")

    def _get_latest_features_for_override(self) -> Optional[dict]:
        """
        Fetch current bars and compute features for model override check.
        Returns the latest feature dict, or None if computation fails.
        Used only by the model override exit rule.
        """
        try:
            if self._backtest_mode and self._cached_5min_bars is not None:
                now_dt = self.get_datetime()
                bars_df = self._cached_5min_bars[self._cached_5min_bars.index <= now_dt]
                if len(bars_df) < 50:
                    logger.warning(
                        "_get_latest_features_for_override: not enough cached bars "
                        f"({len(bars_df)} < 50)"
                    )
                    return None
                bars_df = bars_df.tail(200).copy()
            else:
                bars_result = self.get_historical_prices(
                    self._stock_asset, length=200, timestep="5min"
                )
                if bars_result is None or bars_result.df is None or bars_result.df.empty:
                    logger.warning(
                        "_get_latest_features_for_override: no bars available"
                    )
                    return None
                bars_df = bars_result.df.copy()

            bars_df.columns = [c.lower() for c in bars_df.columns]

            from ml.feature_engineering.base_features import compute_base_features
            options_daily_df = None
            try:
                from data.options_data_fetcher import fetch_options_for_training
                from config import PRESET_DEFAULTS
                preset_config = PRESET_DEFAULTS.get(self.preset, {})
                bars_df.attrs["symbol"] = self.symbol
                options_daily_df = fetch_options_for_training(
                    symbol=self.symbol,
                    bars_df=bars_df,
                    min_dte=preset_config.get("min_dte", 7),
                    max_dte=preset_config.get("max_dte", 45),
                )
            except Exception:
                pass

            featured_df = compute_base_features(bars_df, options_daily_df=options_daily_df)

            if self.preset == "swing":
                from ml.feature_engineering.swing_features import compute_swing_features
                featured_df = compute_swing_features(featured_df)
            elif self.preset == "general":
                from ml.feature_engineering.general_features import compute_general_features
                featured_df = compute_general_features(featured_df)

            if featured_df.empty:
                return None

            return featured_df.iloc[-1].to_dict()

        except Exception as e:
            logger.error(
                f"_get_latest_features_for_override failed: {e}", exc_info=True
            )
            return None

    def _execute_exit(
        self,
        trade_id,
        trade_info,
        position,
        asset,
        current_price,
        underlying_price,
        exit_reason,
    ):
        """Execute a close order and log it to the database."""
        is_stock = asset.asset_type == "stock"
        direction = trade_info.get("direction", "call")

        if is_stock:
            logger.info(
                f"_execute_exit: {trade_info['symbol']} (stock {direction}) "
                f"reason={exit_reason} price=${current_price:.2f}"
            )
        else:
            logger.info(
                f"_execute_exit: {trade_info['symbol']} "
                f"strike={trade_info['strike']} right={trade_info['right']} "
                f"reason={exit_reason} price=${current_price:.2f}"
            )

        try:
            quantity = abs(position.quantity)

            if is_stock:
                # Stock exit: sell to close long, buy to close short
                side = "sell" if direction == "long" else "buy"
                order = self.create_order(asset, quantity, side=side)
            else:
                order = self.create_order(asset, quantity, side="sell_to_close")

            logger.info(f"_execute_exit: submitting order — {side if is_stock else 'sell_to_close'} {quantity}x {asset}")
            self.submit_order(order)
            logger.info(f"_execute_exit: order submitted for {trade_id}")

            # Calculate P&L
            entry_price = trade_info["entry_price"]
            if direction == "short":
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
                if is_stock:
                    pnl_dollars = (entry_price - current_price) * quantity
                else:
                    pnl_dollars = (entry_price - current_price) * quantity * 100
            else:
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                if is_stock:
                    pnl_dollars = (current_price - entry_price) * quantity
                else:
                    pnl_dollars = (current_price - entry_price) * quantity * 100

            entry_date = datetime.datetime.fromisoformat(
                trade_info["entry_date"]
            ).date()
            hold_days = (self.get_datetime().date() - entry_date).days
            was_day_trade = hold_days == 0

            # Get exit Greeks (options only)
            exit_greeks_dict = {}
            if not is_stock:
                try:
                    exit_greeks = self.get_greeks(asset, underlying_price=underlying_price)
                    if exit_greeks:
                        exit_greeks_dict = {
                            "delta": exit_greeks.get("delta"),
                            "gamma": exit_greeks.get("gamma"),
                            "theta": exit_greeks.get("theta"),
                            "vega": exit_greeks.get("vega"),
                            "iv": exit_greeks.get("implied_volatility"),
                        }
                except Exception as e:
                    logger.warning(f"_execute_exit: could not get exit Greeks: {e}")

            # Log to database
            logger.info(f"_execute_exit: logging close to DB for {trade_id}")
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
                f"_execute_exit: complete — P&L=${pnl_dollars:.2f} ({pnl_pct:.1f}%) "
                f"hold={hold_days}d reason={exit_reason}"
            )

        except Exception as e:
            logger.error(f"_execute_exit: order failed for {trade_id}: {e}", exc_info=True)

    # =========================================================================
    # ENTRY LOGIC
    # Architecture Section 9 — Entry steps 1-12
    # =========================================================================

    def _check_entries(self):
        """Evaluate whether to open a new position."""
        logger.info("_check_entries: starting")

        # Step 1: Get current underlying price
        underlying_price = self.get_last_price(self._stock_asset)
        if underlying_price is None:
            logger.warning(f"ENTRY STEP 1 FAIL: Cannot get price for {self.symbol}")
            return
        logger.info(f"  ENTRY STEP 1 OK: {self.symbol} price=${underlying_price:.2f}")

        # Step 2: Get historical 5-min bars for feature computation.
        # In backtesting, use pre-cached Alpaca bars sliced to current sim time.
        # In live trading, use Lumibot's data store.
        if self._backtest_mode and self._cached_5min_bars is not None:
            now_dt = self.get_datetime()
            bars_df = self._cached_5min_bars[self._cached_5min_bars.index <= now_dt]
            if len(bars_df) < 50:
                logger.warning(
                    f"ENTRY STEP 2 SKIP: Only {len(bars_df)} cached bars available "
                    f"(need 50+) — waiting for warmup"
                )
                return
            bars_df = bars_df.tail(200).copy()
            logger.info(
                f"  ENTRY STEP 2 OK: {len(bars_df)} cached bars used (backtest mode)"
            )
        else:
            try:
                bars_result = self.get_historical_prices(
                    self._stock_asset, length=200, timestep="5min"
                )
            except Exception as e:
                logger.error(
                    f"ENTRY STEP 2 FAIL: get_historical_prices() raised: {e}. "
                    f"This usually means the data store has no minute data.",
                    exc_info=True,
                )
                return

            if bars_result is None:
                logger.error(
                    "ENTRY STEP 2 FAIL: get_historical_prices() returned None. "
                    "No minute data available in the data store."
                )
                return

            if bars_result.df is None or bars_result.df.empty:
                logger.warning(
                    "ENTRY STEP 2 FAIL: Historical bars returned but DataFrame is empty."
                )
                return

            bars_df = bars_result.df.copy()
            logger.info(
                f"  ENTRY STEP 2 OK: Got {len(bars_df)} bars from Lumibot data store"
            )

        # Ensure lowercase column names
        bars_df.columns = [c.lower() for c in bars_df.columns]

        # Handle MultiIndex (Lumibot sometimes returns MultiIndex DataFrames)
        if hasattr(bars_df.index, "levels"):
            bars_df = (
                bars_df.droplevel(0) if len(bars_df.index.levels) > 1 else bars_df
            )

        # Step 3+4: Fetch options data from Theta + compute features
        from ml.feature_engineering.base_features import compute_base_features
        try:
            options_daily_df = None
            try:
                from data.options_data_fetcher import fetch_options_for_training
                from config import PRESET_DEFAULTS
                preset_config = PRESET_DEFAULTS.get(self.preset, {})
                bars_df.attrs["symbol"] = self.symbol
                options_daily_df = fetch_options_for_training(
                    symbol=self.symbol,
                    bars_df=bars_df,
                    min_dte=preset_config.get("min_dte", 7),
                    max_dte=preset_config.get("max_dte", 45),
                )
            except Exception as opt_err:
                logger.warning(f"  Options data fetch failed (continuing without): {opt_err}")

            featured_df = compute_base_features(bars_df.copy(), options_daily_df=options_daily_df)

            if self.preset == "swing":
                from ml.feature_engineering.swing_features import compute_swing_features
                featured_df = compute_swing_features(featured_df)
            elif self.preset == "general":
                from ml.feature_engineering.general_features import compute_general_features
                featured_df = compute_general_features(featured_df)

            logger.info(
                f"  ENTRY STEP 4 OK: Features computed — "
                f"{len(featured_df)} rows, {len(featured_df.columns)} columns"
            )
        except Exception as e:
            logger.error(
                f"ENTRY STEP 4 FAIL: Feature computation failed: {e}", exc_info=True
            )
            return

        if featured_df.empty:
            logger.warning("ENTRY STEP 4 FAIL: featured_df is empty after computation")
            return

        latest_features = featured_df.iloc[-1].to_dict()
        nan_count = sum(
            1 for v in latest_features.values()
            if isinstance(v, float) and v != v
        )
        logger.info(
            f"  Features: {len(latest_features)} total, {nan_count} NaN"
        )

        # Step 5: ML prediction
        # Build a sequence DataFrame for TFT/Ensemble predictors.
        # XGBoostPredictor.predict() accepts sequence=None and ignores it.
        # TFTPredictor and EnsemblePredictor use it for temporal inference.
        # If we can't build a full sequence, they degrade to XGBoost-only (by design).
        sequence_df = None
        try:
            from ml.tft_predictor import ENCODER_LENGTH
            predictor_type = type(self.predictor).__name__

            if predictor_type in ("TFTPredictor", "EnsemblePredictor"):
                # featured_df was computed in Step 4 — reuse it for the sequence.
                # Select only the model's expected feature columns.
                feature_cols = self.predictor.get_feature_names()
                if feature_cols and len(featured_df) >= ENCODER_LENGTH:
                    available_cols = [c for c in feature_cols if c in featured_df.columns]
                    sequence_df = featured_df[available_cols].tail(ENCODER_LENGTH).copy()
                    logger.info(
                        f"  ENTRY STEP 5: Built sequence_df "
                        f"({len(sequence_df)} rows x {len(available_cols)} features) "
                        f"for {predictor_type}"
                    )
                else:
                    logger.warning(
                        f"  ENTRY STEP 5: Cannot build full sequence for {predictor_type} "
                        f"(need {ENCODER_LENGTH} rows, have {len(featured_df)}, "
                        f"features known: {bool(feature_cols)}) — degrading to XGBoost mode"
                    )
        except Exception as seq_err:
            logger.warning(
                f"  ENTRY STEP 5: Sequence build failed ({seq_err}) — "
                f"proceeding with snapshot-only prediction"
            )

        try:
            predicted_return = self.predictor.predict(latest_features, sequence=sequence_df)
        except TypeError:
            # Fallback for predictors that don't accept 'sequence' keyword
            predicted_return = self.predictor.predict(latest_features)
        except Exception as e:
            logger.error(
                f"ENTRY STEP 5 FAIL: Model prediction failed: {e}", exc_info=True
            )
            return
        logger.info(f"  ENTRY STEP 5 OK: Predicted return={predicted_return:.3f}%")

        # Step 6: Check minimum threshold
        # Use lower threshold in backtest mode (stock moves << option moves)
        if self._backtest_mode:
            min_move = 0.5
        else:
            min_move = self.config.get("min_predicted_move_pct", 1.0)

        if abs(predicted_return) < min_move:
            logger.info(
                f"  ENTRY STEP 6 SKIP: |{predicted_return:.3f}%| < {min_move}% threshold"
            )
            return
        logger.info(
            f"  ENTRY STEP 6 OK: |{predicted_return:.3f}%| >= {min_move}% threshold"
        )

        # Step 7: Direction determined by prediction sign
        portfolio_value = self.get_portfolio_value()

        # =====================================================================
        # BACKTEST PATH: Trade underlying stock (avoids ThetaData chain download)
        # Validates model directional signal. Live trading uses full options path.
        # =====================================================================
        if self._backtest_mode:
            # Skip if we already have an open stock position
            for tinfo in self._open_trades.values():
                if tinfo.get("asset_type") == "stock":
                    logger.info(
                        "  BACKTEST: Already have open stock position — skipping"
                    )
                    return

            # Long-only in backtest — Lumibot backtester hangs on short sells
            if predicted_return <= 0:
                logger.info(
                    f"  BACKTEST: Negative prediction ({predicted_return:+.3f}%) "
                    f"— long-only mode, skipping"
                )
                return

            direction = "long"
            max_position_pct = self.config.get("max_position_pct", 20)
            position_budget = portfolio_value * (max_position_pct / 100)
            quantity = int(position_budget / underlying_price)
            if quantity < 1:
                logger.warning(
                    f"  BACKTEST: Cannot afford 1 share at ${underlying_price:.2f}"
                )
                return

            trade_id = str(uuid.uuid4())

            try:
                order = self.create_order(self._stock_asset, quantity, side="buy")
                self.submit_order(order)

                logger.info(
                    f"  BACKTEST ORDER: buy {quantity} shares {self.symbol} "
                    f"@ ${underlying_price:.2f} (pred={predicted_return:+.3f}%)"
                )

                self._open_trades[trade_id] = {
                    "symbol": self.symbol,
                    "asset_type": "stock",
                    "direction": direction,
                    "entry_price": underlying_price,
                    "entry_date": self.get_datetime().isoformat(),
                    "entry_underlying_price": underlying_price,
                    "quantity": quantity,
                    "entry_prediction": predicted_return,
                }

                # Log to database
                loggable_features = {}
                for k, v in latest_features.items():
                    if k in ["open", "high", "low", "close", "volume"]:
                        continue
                    try:
                        if v is not None and not (isinstance(v, float) and (v != v)):
                            loggable_features[k] = (
                                float(v) if isinstance(v, (int, float)) else str(v)
                            )
                    except (TypeError, ValueError):
                        pass

                active_model_type = type(self.predictor).__name__.lower().replace("predictor", "")
                # Results in: "xgboost", "tft", "ensemble" — matches DB model_type values

                self.risk_mgr.log_trade_open(
                    trade_id=trade_id,
                    profile_id=self.profile_id,
                    symbol=self.symbol,
                    direction=direction,
                    strike=0,
                    expiration="N/A",
                    quantity=quantity,
                    entry_price=underlying_price,
                    entry_underlying_price=underlying_price,
                    predicted_return=predicted_return,
                    ev_pct=0,
                    features=loggable_features,
                    greeks={},
                    model_type=active_model_type,
                )

            except Exception as e:
                logger.error(f"  BACKTEST order failed: {e}", exc_info=True)

            return  # Done — skip live options path

        # =====================================================================
        # LIVE PATH: Full options trading with EV filter
        # =====================================================================

        # Step 8: Risk manager checks (PDT + position limits + exposure)
        pdt = self.risk_mgr.check_pdt(portfolio_value)
        if not pdt["allowed"]:
            logger.warning(f"  ENTRY STEP 8 BLOCKED (PDT): {pdt['message']}")
            return

        # Step 9: Scan option chain through EV filter
        min_dte = self.config.get("min_dte", 7)
        max_dte = self.config.get("max_dte", 45)
        max_hold = self.config.get("max_hold_days", 7)
        min_ev = self.config.get("min_ev_pct", 10)

        logger.info(
            f"  ENTRY STEP 9: Scanning chain — DTE={min_dte}-{max_dte}, "
            f"min_ev={min_ev}%"
        )
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
            logger.info("  ENTRY STEP 9 SKIP: No contract meets EV threshold")
            return

        logger.info(
            f"  ENTRY STEP 9 OK: {best_contract.right} ${best_contract.strike} "
            f"exp={best_contract.expiration} EV={best_contract.ev_pct:.1f}% "
            f"premium=${best_contract.premium:.2f}"
        )

        # Step 10: Position sizing + all risk checks (includes exposure check)
        risk_check = self.risk_mgr.check_can_open_position(
            profile_id=self.profile_id,
            profile_config=self.config,
            portfolio_value=portfolio_value,
            option_price=best_contract.premium,
        )

        if not risk_check["allowed"]:
            logger.warning(
                f"  ENTRY STEP 10 BLOCKED: {'; '.join(risk_check['reasons'])}"
            )
            return

        quantity = risk_check["quantity"]
        logger.info(f"  ENTRY STEP 10 OK: {quantity} contracts approved")

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
            order = self.create_order(option_asset, quantity, side="buy_to_open")
            logger.info(
                f"  ENTRY STEP 11: Submitting order — buy_to_open {quantity}x "
                f"{best_contract.right} ${best_contract.strike} "
                f"exp={best_contract.expiration} @ ${best_contract.premium:.2f}"
            )
            self.submit_order(order)
            logger.info(f"  ENTRY STEP 11 OK: Order submitted — trade_id={trade_id}")

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
                "asset_type": "option",
                "strike": best_contract.strike,
                "expiration": best_contract.expiration,
                "right": best_contract.right,
                "direction": "long",
                "entry_price": best_contract.premium,
                "entry_date": self.get_datetime().isoformat(),
                "entry_underlying_price": underlying_price,
                "quantity": quantity,
                "entry_prediction": predicted_return,
            }

            # Step 12: Log EVERYTHING to database
            loggable_features = {}
            for k, v in latest_features.items():
                if k in ["open", "high", "low", "close", "volume"]:
                    continue
                try:
                    if v is not None and not (isinstance(v, float) and (v != v)):
                        loggable_features[k] = (
                            float(v) if isinstance(v, (int, float)) else str(v)
                        )
                except (TypeError, ValueError):
                    pass

            logger.info(f"  ENTRY STEP 12: Logging trade to DB — trade_id={trade_id}")
            active_model_type = type(self.predictor).__name__.lower().replace("predictor", "")
            # Results in: "xgboost", "tft", "ensemble" — matches DB model_type values

            self.risk_mgr.log_trade_open(
                trade_id=trade_id,
                profile_id=self.profile_id,
                symbol=self.symbol,
                direction="long",
                strike=best_contract.strike,
                expiration=str(best_contract.expiration),
                quantity=quantity,
                entry_price=best_contract.premium,
                entry_underlying_price=underlying_price,
                predicted_return=predicted_return,
                ev_pct=best_contract.ev_pct,
                features=loggable_features,
                greeks=entry_greeks,
                model_type=active_model_type,
            )
            logger.info(f"  ENTRY STEP 12 OK: Trade logged — {trade_id}")

        except Exception as e:
            logger.error(
                f"  ENTRY STEP 11 FAIL: Order submission failed: {e}", exc_info=True
            )

        logger.info("_check_entries: complete")

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
        """Return custom stats for Lumibot logging."""
        return {
            "open_trades": len(self._open_trades),
            "profile": self.profile_name,
        }