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
import time
import uuid
import logging
import datetime
from typing import Optional

import numpy as np

from lumibot.strategies import Strategy
from lumibot.entities import Asset

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH, MODELS_DIR
from config import (
    THETA_CB_FAILURE_THRESHOLD, THETA_CB_RESET_TIMEOUT,
    MAX_CONSECUTIVE_ERRORS, ITERATION_ERROR_RESET_ON_SUCCESS,
)
from config import (
    MODEL_HEALTH_WINDOW_SIZE,
    MODEL_DEGRADED_THRESHOLD,
    MODEL_HEALTH_MIN_SAMPLES,
)
from config import (
    MIN_OPEN_INTEREST, MIN_OPTION_VOLUME,
    EARNINGS_BLACKOUT_DAYS_BEFORE, EARNINGS_BLACKOUT_DAYS_AFTER,
    ALPACA_API_KEY, ALPACA_API_SECRET,
)
from utils.circuit_breaker import CircuitBreaker
from ml.xgboost_predictor import XGBoostPredictor
from ml.ev_filter import scan_chain_for_best_ev
from risk.risk_manager import RiskManager
from data.vix_provider import VIXProvider

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
                elif model_type == "lightgbm":
                    from ml.lgbm_predictor import LightGBMPredictor
                    self.predictor = LightGBMPredictor(self.model_path)
                elif model_type == "xgb_classifier":
                    from ml.scalp_predictor import ScalpPredictor
                    self.predictor = ScalpPredictor(self.model_path)
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

        # Scalp equity gate: warn if portfolio < $25K (required for unlimited day trades)
        if self.preset == "scalp":
            min_equity = self.config.get("requires_min_equity", 25000)
            if min_equity > 0:
                logger.info(
                    f"  Scalp preset: requires ${min_equity:,.0f} equity "
                    f"(PDT unlimited day trades)"
                )

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
                # Add buffer before start for lookback warmup
                bt_start = datetime.datetime.strptime(backtest_start, "%Y-%m-%d")
                bt_end = datetime.datetime.strptime(backtest_end, "%Y-%m-%d")
                # Scalp needs less warmup (1-min bars) but more data per day
                warmup_days = 10 if self.preset == "scalp" else 45
                fetch_start = bt_start - datetime.timedelta(days=warmup_days)
                fetch_end = bt_end + datetime.timedelta(days=1)
                bar_granularity = self.config.get("bar_granularity", "5min")
                logger.info(
                    f"  Pre-fetching {bar_granularity} bars from Alpaca: "
                    f"{fetch_start.date()} to {fetch_end.date()}..."
                )
                self._cached_5min_bars = provider.get_historical_bars(
                    self.symbol, fetch_start, fetch_end, timeframe=bar_granularity
                )
                logger.info(
                    f"  Pre-fetched {len(self._cached_5min_bars)} {bar_granularity} bars from Alpaca"
                )
                # Note: _cached_5min_bars may contain 1-min bars when preset=scalp.
                # Name kept for backward compatibility.
            except Exception as e:
                logger.error(
                    f"  Failed to pre-fetch 5-min bars from Alpaca: {e}", exc_info=True
                )

        # Phase 6: Resilience tracking
        self._consecutive_errors = 0
        self._total_iterations = 0
        self._total_errors = 0
        self._theta_circuit_breaker = CircuitBreaker(
            name=f"theta_{self.profile_id[:8]}",
            failure_threshold=THETA_CB_FAILURE_THRESHOLD,
            reset_timeout=THETA_CB_RESET_TIMEOUT,
        )
        self._iteration_timings = {}  # Populated each iteration for monitoring

        # VIX regime filter
        self._vix_provider = VIXProvider()

        # Phase 6: Model health tracking
        # Stores recent predictions to compare against actual outcomes
        # Format: list of {"predicted_direction": "up"|"down"|"neutral",
        #                   "predicted_value": float, "timestamp": str,
        #                   "price_at_prediction": float,
        #                   "actual_direction": "up"|"down"|"neutral"|None}
        self._prediction_history: list[dict] = []
        self._last_health_persist_time = 0.0

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
        self._total_iterations += 1
        iteration_start = time.time()

        try:
            # ── AUTO-PAUSE CHECK ──────────────────────────────────────
            if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error(
                    f"[{self.profile_name}] AUTO-PAUSED: {self._consecutive_errors} "
                    f"consecutive errors. Manual restart required. "
                    f"Total iterations: {self._total_iterations}, "
                    f"Total errors: {self._total_errors}"
                )
                try:
                    from utils.alerter import send_alert
                    send_alert(
                        level="CRITICAL",
                        message=f"Bot auto-paused after {MAX_CONSECUTIVE_ERRORS} consecutive errors on {self.symbol}",
                        profile_id=str(self.profile_id),
                        details={
                            "consecutive_errors": self._consecutive_errors,
                            "total_iterations": self._total_iterations,
                            "total_errors": self._total_errors,
                        },
                    )
                except Exception:
                    pass  # Alert failure must never crash the trading loop
                return

            # ── Update prediction outcome tracking ────────────────────
            try:
                current_price = self.get_last_price(self.symbol)
                if current_price and current_price > 0:
                    self._update_prediction_outcomes(current_price)
            except Exception:
                pass  # Non-fatal — don't let health tracking break trading

            # ══════════════════════════════════════════════════════════
            # EXISTING on_trading_iteration() BODY
            # ══════════════════════════════════════════════════════════

            logger.info(f"--- {self.profile_name} iteration at {self.get_datetime()} ---")

            # Scalp equity gate: skip trading if portfolio value < $25K
            # (PDT rule requires $25K+ for unlimited day trades)
            if self.preset == "scalp":
                _pv = self.get_portfolio_value() or 0.0
                min_equity = self.config.get("requires_min_equity", 25000)
                if min_equity > 0 and _pv < min_equity:
                    logger.warning(
                        f"SCALP EQUITY GATE: Portfolio ${_pv:,.0f} < "
                        f"${min_equity:,.0f} required — skipping all scalp trading"
                    )
                    return

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
                try:
                    self._write_signal_log(
                        step_stopped_at=0,
                        stop_reason=f"Unhandled error: {str(e)[:200]}",
                    )
                except Exception:
                    pass  # Double-fault protection — never crash the trading loop

            # ── Persist model health stats ────────────────────────────
            try:
                self._persist_health_to_db()
            except Exception:
                pass  # Non-fatal

            # ── SUCCESS: Reset error counter ──────────────────────────
            if ITERATION_ERROR_RESET_ON_SUCCESS:
                self._consecutive_errors = 0

        except Exception as e:
            self._consecutive_errors += 1
            self._total_errors += 1
            logger.error(
                f"[{self.profile_name}] ITERATION ERROR ({self._consecutive_errors}/"
                f"{MAX_CONSECUTIVE_ERRORS}): {type(e).__name__}: {e}",
                exc_info=True,
            )

        finally:
            elapsed = time.time() - iteration_start
            self._iteration_timings["total"] = elapsed
            if elapsed > 30.0:
                logger.warning(
                    f"[{self.profile_name}] Slow iteration: {elapsed:.1f}s "
                    f"(timings: {self._iteration_timings})"
                )
            elif elapsed > 10.0:
                logger.info(
                    f"[{self.profile_name}] Iteration: {elapsed:.1f}s "
                    f"(timings: {self._iteration_timings})"
                )
            self._export_circuit_state()

    def _export_circuit_state(self) -> None:
        """Write circuit breaker states to a JSON file for UI visibility."""
        import json as _json
        from config import LOGS_DIR
        state_file = LOGS_DIR / f"circuit_state_{self.profile_id}.json"
        try:
            theta_state = self._theta_circuit_breaker.state.value
            state_data = {
                "profile_id": self.profile_id,
                "theta_breaker_state": theta_state,
                "alpaca_breaker_state": "closed",  # No Alpaca circuit breaker yet
                "theta_failure_count": self._theta_circuit_breaker._failure_count,
                "alpaca_failure_count": 0,
                "last_updated": datetime.datetime.utcnow().isoformat(),
            }
            state_file.write_text(_json.dumps(state_data, indent=2))

            # Alert when circuit breaker transitions to OPEN
            if theta_state == "OPEN":
                try:
                    from utils.alerter import send_alert
                    send_alert(
                        level="WARNING",
                        message="Theta Terminal circuit breaker OPEN — bot in fail-fast mode",
                        profile_id=str(self.profile_id),
                    )
                except Exception:
                    pass  # Alert failure must never crash the trading loop
        except Exception as e:
            logger.warning(f"_export_circuit_state: failed to write state file: {e}")

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
            direction = trade_info.get("direction", "long")

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
                if self.preset == "scalp":
                    profit_target = 0.5   # Scalp: target ~0.5% intraday move
                    stop_loss_threshold = 0.3  # Scalp: tight stop
                else:
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
                        override_result = self._get_latest_features_for_override()
                        if override_result is not None:
                            override_features, override_featured_df = override_result

                            # Build sequence for TFT/Ensemble (same pattern as entry path)
                            override_sequence = None
                            try:
                                from ml.tft_predictor import ENCODER_LENGTH
                                predictor_type = type(self.predictor).__name__
                                if predictor_type in ("TFTPredictor", "EnsemblePredictor"):
                                    feature_cols = self.predictor.get_feature_names()
                                    if feature_cols and len(override_featured_df) >= ENCODER_LENGTH:
                                        available = [c for c in feature_cols if c in override_featured_df.columns]
                                        override_sequence = override_featured_df[available].tail(ENCODER_LENGTH).copy()
                            except Exception:
                                pass

                            try:
                                current_prediction = self.predictor.predict(
                                    override_features, sequence=override_sequence
                                )
                            except TypeError:
                                current_prediction = self.predictor.predict(override_features)

                            # Skip reversal check if prediction is NaN/Inf
                            if current_prediction is None or np.isnan(current_prediction) or np.isinf(current_prediction):
                                logger.warning(
                                    f"_check_exits: model override prediction is NaN/Inf — skipping reversal check"
                                )
                                current_prediction = None

                            if current_prediction is not None:
                                entry_prediction = trade_info.get("entry_prediction", 0)
                                right = trade_info.get("right", "CALL")
                                # Model override exit requires a meaningful reversal signal.
                                # A sign flip on a tiny prediction is noise, not a reversal.
                                # model_override_min_reversal_pct (default 0.5) means:
                                #   - CALL position: only exit if model now predicts < -0.5%
                                #   - PUT position:  only exit if model now predicts > +0.5%
                                override_threshold = self.config.get("model_override_min_reversal_pct", 0.5)
                                reversal = (
                                    (right == "CALL" and current_prediction < -override_threshold) or
                                    (right == "PUT" and current_prediction > override_threshold)
                                )
                                if reversal:
                                    exit_reason = "model_override"
                                    logger.info(
                                        f"_check_exits: model override TRIGGERED: "
                                        f"entry_pred={entry_prediction:.3f}% "
                                        f"current_pred={current_prediction:.3f}% "
                                        f"threshold=±{override_threshold}% right={right}"
                                    )
                                else:
                                    logger.debug(
                                        f"_check_exits: model override SKIPPED (below threshold): "
                                        f"current_pred={current_prediction:.3f}% "
                                        f"threshold=±{override_threshold}% right={right}"
                                    )
                    except Exception as e:
                        # Never let model errors block the rest of exit logic
                        logger.error(
                            f"_check_exits: model override check failed for {trade_id}: {e}",
                            exc_info=True,
                        )

            # Rule 6: Same-day exit for scalp (0DTE — must close before market close)
            # Force close at 3:45 PM ET (15 min before market close)
            if exit_reason is None and self.preset == "scalp":
                now = self.get_datetime()
                if now.tzinfo is not None:
                    now_et = now.astimezone(
                        datetime.timezone(datetime.timedelta(hours=-5))
                    )
                else:
                    # Assume UTC for backtest
                    import pytz
                    eastern = pytz.timezone("US/Eastern")
                    now_et = now.replace(tzinfo=pytz.utc).astimezone(eastern)

                market_close_cutoff_hour = 15
                market_close_cutoff_minute = 45
                if (now_et.hour > market_close_cutoff_hour or
                    (now_et.hour == market_close_cutoff_hour and
                     now_et.minute >= market_close_cutoff_minute)):
                    exit_reason = "scalp_eod"
                    logger.info(
                        f"_check_exits: scalp same-day exit: "
                        f"time={now_et.strftime('%H:%M')} ET >= 15:45 cutoff"
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

    def _get_latest_features_for_override(self) -> Optional[tuple]:
        """
        Fetch current bars and compute features for model override check.
        Returns (features_dict, featured_df) tuple, or None if computation fails.
        The featured_df is needed to build a sequence for TFT/Ensemble predictors.
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
                lookback = 4000 if self.preset == "general" else 2000
                bars_df = bars_df.tail(lookback).copy()
            else:
                lookback = 4000 if self.preset == "general" else 2000
                bars_result = self.get_historical_prices(
                    self._stock_asset, length=lookback, timestep="5min"
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

            bars_per_day = 390 if self.preset == "scalp" else 78
            featured_df = compute_base_features(bars_df, options_daily_df=options_daily_df, bars_per_day=bars_per_day)

            if self.preset == "swing":
                from ml.feature_engineering.swing_features import compute_swing_features
                featured_df = compute_swing_features(featured_df)
            elif self.preset == "general":
                from ml.feature_engineering.general_features import compute_general_features
                featured_df = compute_general_features(featured_df)
            elif self.preset == "scalp":
                from ml.feature_engineering.scalp_features import compute_scalp_features
                featured_df = compute_scalp_features(featured_df)

            if featured_df.empty:
                return None

            return (featured_df.iloc[-1].to_dict(), featured_df)

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
        direction = trade_info.get("direction", "long")

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
                            "iv": exit_greeks.get("iv", exit_greeks.get("implied_volatility")),
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

            # Enqueue for feedback loop (training queue)
            try:
                from ml.feedback_queue import enqueue_completed_sample
                enqueue_completed_sample(
                    db_path=str(DB_PATH),
                    trade_id=trade_id,
                    profile_id=self.profile_id,
                    symbol=trade_info.get("symbol", self.symbol),
                    entry_features=trade_info.get("entry_features"),
                    predicted_return=trade_info.get("entry_prediction"),
                    actual_return_pct=pnl_pct,
                )
            except Exception as eq_err:
                logger.warning(f"_execute_exit: feedback queue enqueue failed (non-fatal): {eq_err}")

            # Remove from tracking
            del self._open_trades[trade_id]

            logger.info(
                f"_execute_exit: complete — P&L=${pnl_dollars:.2f} ({pnl_pct:.1f}%) "
                f"hold={hold_days}d reason={exit_reason}"
            )

        except Exception as e:
            logger.error(f"_execute_exit: order failed for {trade_id}: {e}", exc_info=True)

    # =========================================================================
    # SIGNAL LOG — Phase 4.5
    # Writes one row per iteration to signal_logs table.
    # Called at the END of _check_entries() for every code path.
    # =========================================================================

    def _write_signal_log(
        self,
        underlying_price: float | None = None,
        predicted_return: float | None = None,
        step_stopped_at: float | None = None,
        stop_reason: str | None = None,
        entered: bool = False,
        trade_id: str | None = None,
    ):
        """
        Write a signal decision log entry to the database.
        Uses synchronous sqlite3 (not aiosqlite) because Lumibot strategies
        run in their own thread/event loop — same pattern as _detect_model_type().
        """
        import sqlite3
        try:
            from config import DB_PATH
            predictor_type = type(self.predictor).__name__ if self.predictor else None
            now_str = self.get_datetime().isoformat()

            con = sqlite3.connect(str(DB_PATH))
            con.execute(
                """INSERT INTO signal_logs
                   (profile_id, timestamp, symbol, underlying_price, predicted_return,
                    predictor_type, step_stopped_at, stop_reason, entered, trade_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.profile_id,
                    now_str,
                    self.symbol,
                    underlying_price,
                    predicted_return,
                    predictor_type,
                    step_stopped_at,
                    stop_reason,
                    1 if entered else 0,
                    trade_id,
                ),
            )
            con.commit()
            con.close()
            logger.debug(f"Signal log written: step={step_stopped_at}, entered={entered}")
        except Exception as e:
            # Signal logging must NEVER crash the trading loop
            logger.error(f"_write_signal_log failed (non-fatal): {e}", exc_info=True)

    # =========================================================================
    # ENTRY LOGIC
    # Architecture Section 9 — Entry steps 1-12
    # =========================================================================

    def _check_entries(self):
        """Evaluate whether to open a new position."""
        logger.info("_check_entries: starting")
        t_start = time.time()

        # Step 1: Get current underlying price
        underlying_price = self.get_last_price(self._stock_asset)
        if underlying_price is None:
            logger.warning(f"ENTRY STEP 1 FAIL: Cannot get price for {self.symbol}")
            self._write_signal_log(step_stopped_at=1, stop_reason="Price unavailable")
            return
        logger.info(f"  ENTRY STEP 1 OK: {self.symbol} price=${underlying_price:.2f}")

        # ENTRY STEP 1.5: Volatility regime gate (VIX)
        # Skip entries when macro volatility is outside the tradeable range.
        # High VIX: spreads blow out, correlations collapse, signal loses validity.
        # Low VIX: insufficient move magnitude to hit profit targets.
        if self.config.get("vix_gate_enabled", True):
            vix_level = self._vix_provider.get_current_vix()
            if vix_level is not None:
                vix_min = self.config.get("vix_min", 3.0)
                vix_max = self.config.get("vix_max", 7.0)
                if not (vix_min <= vix_level <= vix_max):
                    regime = "elevated" if vix_level > vix_max else "suppressed"
                    logger.info(
                        f"  ENTRY STEP 1.5 SKIP: Volatility regime {regime} "
                        f"(VIXY={vix_level:.2f}, allowed={vix_min:.2f}-{vix_max:.2f})"
                    )
                    self._write_signal_log(
                        underlying_price=underlying_price,
                        step_stopped_at=1,
                        stop_reason=f"VIX gate: VIXY={vix_level:.2f} outside [{vix_min},{vix_max}]",
                    )
                    return
                else:
                    logger.info(
                        f"  ENTRY STEP 1.5 OK: Volatility regime acceptable "
                        f"(VIXY={vix_level:.2f})"
                    )
            else:
                # VIX unavailable — allow trading (fail open, not closed)
                logger.warning("  ENTRY STEP 1.5: VIX unavailable — proceeding without gate")

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
                self._write_signal_log(
                    underlying_price=underlying_price,
                    step_stopped_at=2,
                    stop_reason="No historical bars available",
                )
                return
            # Use enough bars to cover the longest feature lookback window.
            # swing: swing_dist_sma_20d needs 1560 bars; general: general_trend_slope_50d needs 3900.
            # scalp: 1-min bars, ~1.3 trading days for feature warmup.
            if self.preset == "scalp":
                lookback = 500  # ~1.3 trading days of 1-min bars
            elif self.preset == "general":
                lookback = 4000
            else:
                lookback = 2000
            bars_df = bars_df.tail(lookback).copy()
            logger.info(
                f"  ENTRY STEP 2 OK: {len(bars_df)} cached bars used (backtest mode)"
            )
        else:
            try:
                if self.preset == "scalp":
                    lookback = 500
                elif self.preset == "general":
                    lookback = 4000
                else:
                    lookback = 2000
                bar_ts = self.config.get("bar_granularity", "5min")
                bars_result = self.get_historical_prices(
                    self._stock_asset, length=lookback, timestep=bar_ts
                )
            except Exception as e:
                logger.error(
                    f"ENTRY STEP 2 FAIL: get_historical_prices() raised: {e}. "
                    f"This usually means the data store has no minute data.",
                    exc_info=True,
                )
                self._write_signal_log(
                    underlying_price=underlying_price,
                    step_stopped_at=2,
                    stop_reason="No historical bars available",
                )
                return

            if bars_result is None:
                logger.error(
                    "ENTRY STEP 2 FAIL: get_historical_prices() returned None. "
                    "No minute data available in the data store."
                )
                self._write_signal_log(
                    underlying_price=underlying_price,
                    step_stopped_at=2,
                    stop_reason="No historical bars available",
                )
                return

            if bars_result.df is None or bars_result.df.empty:
                logger.warning(
                    "ENTRY STEP 2 FAIL: Historical bars returned but DataFrame is empty."
                )
                self._write_signal_log(
                    underlying_price=underlying_price,
                    step_stopped_at=2,
                    stop_reason="No historical bars available",
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

        t_bars = time.time()
        self._iteration_timings["bars_fetch"] = t_bars - t_start

        # Step 3+4: Fetch options data from Theta + compute features
        # Note: Theta Terminal is not called directly during live trading iterations.
        # Options data fetch (below) goes through fetch_options_for_training which has
        # its own error handling. Live EV filter uses Lumibot's get_chains/get_greeks
        # which route through Alpaca, not Theta.
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

            bars_per_day = 390 if self.preset == "scalp" else 78
            featured_df = compute_base_features(bars_df.copy(), options_daily_df=options_daily_df, bars_per_day=bars_per_day)

            if self.preset == "swing":
                from ml.feature_engineering.swing_features import compute_swing_features
                featured_df = compute_swing_features(featured_df)
            elif self.preset == "general":
                from ml.feature_engineering.general_features import compute_general_features
                featured_df = compute_general_features(featured_df)
            elif self.preset == "scalp":
                from ml.feature_engineering.scalp_features import compute_scalp_features
                featured_df = compute_scalp_features(featured_df)

            t_features = time.time()
            self._iteration_timings["feature_compute"] = t_features - t_bars

            logger.info(
                f"  ENTRY STEP 4 OK: Features computed — "
                f"{len(featured_df)} rows, {len(featured_df.columns)} columns"
            )
        except Exception as e:
            logger.error(
                f"ENTRY STEP 4 FAIL: Feature computation failed: {e}", exc_info=True
            )
            self._write_signal_log(
                underlying_price=underlying_price,
                step_stopped_at=4,
                stop_reason="Feature computation failed",
            )
            return

        if featured_df.empty:
            logger.warning("ENTRY STEP 4 FAIL: featured_df is empty after computation")
            self._write_signal_log(
                underlying_price=underlying_price,
                step_stopped_at=4,
                stop_reason="Feature computation failed",
            )
            return

        latest_features = featured_df.iloc[-1].to_dict()
        nan_count = sum(
            1 for v in latest_features.values()
            if isinstance(v, float) and v != v
        )
        total_features = len(latest_features)
        logger.info(
            f"  Features: {total_features} total, {nan_count} NaN"
        )

        # Skip prediction if >80% of features are NaN (catastrophic data failure)
        nan_pct = (nan_count / total_features * 100) if total_features > 0 else 0
        if total_features > 0 and nan_pct > 80:
            logger.error(
                f"ENTRY STEP 4 FAIL: {nan_count}/{total_features} features are NaN "
                f"(>80%) — skipping prediction"
            )
            self._write_signal_log(
                underlying_price=underlying_price,
                step_stopped_at=4,
                stop_reason=f"Too many NaN features ({nan_pct:.0f}% > 80%)",
            )
            return

        # Replace any inf values in features with NaN before passing to predictor
        for k, v in latest_features.items():
            if isinstance(v, float) and (v == float('inf') or v == float('-inf')):
                latest_features[k] = float('nan')

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
            self._write_signal_log(
                underlying_price=underlying_price,
                step_stopped_at=5,
                stop_reason="Model prediction failed",
            )
            return

        # Validate prediction is not NaN/Inf
        if predicted_return is None or np.isnan(predicted_return) or np.isinf(predicted_return):
            logger.error(
                f"ENTRY STEP 5 FAIL: Prediction is NaN/Inf ({predicted_return}) — skipping entry"
            )
            self._write_signal_log(
                underlying_price=underlying_price,
                predicted_return=float(predicted_return) if predicted_return is not None else None,
                step_stopped_at=5,
                stop_reason=f"Prediction is NaN/Inf ({predicted_return})",
            )
            return

        t_predict = time.time()
        self._iteration_timings["prediction"] = t_predict - t_features

        logger.info(f"  ENTRY STEP 5 OK: Predicted return={predicted_return:.3f}%")

        # Record prediction for health monitoring (regardless of trade outcome)
        try:
            self._record_prediction(predicted_return, underlying_price)
        except Exception:
            pass  # Non-fatal

        # Step 5.5: VIX regime confidence adjustment (Phase C)
        # Scale prediction magnitude based on current volatility regime.
        try:
            from config import VIX_REGIME_ENABLED
            if VIX_REGIME_ENABLED:
                from ml.regime_adjuster import adjust_prediction_confidence
                from config import (
                    VIX_REGIME_LOW_THRESHOLD, VIX_REGIME_HIGH_THRESHOLD,
                    VIX_REGIME_LOW_MULTIPLIER, VIX_REGIME_NORMAL_MULTIPLIER,
                    VIX_REGIME_HIGH_MULTIPLIER,
                )
                vixy_price = self._vix_provider.get_current_vixy_price()
                if vixy_price and vixy_price > 0:
                    raw_pred = predicted_return
                    predicted_return, regime = adjust_prediction_confidence(
                        predicted_return=predicted_return,
                        vix_level=vixy_price,
                        vix_low_threshold=VIX_REGIME_LOW_THRESHOLD,
                        vix_high_threshold=VIX_REGIME_HIGH_THRESHOLD,
                        low_vol_multiplier=VIX_REGIME_LOW_MULTIPLIER,
                        normal_vol_multiplier=VIX_REGIME_NORMAL_MULTIPLIER,
                        high_vol_multiplier=VIX_REGIME_HIGH_MULTIPLIER,
                    )
                    logger.info(
                        f"  ENTRY STEP 5.5: Regime={regime} VIXY={vixy_price:.2f} "
                        f"raw={raw_pred:.3f}% adjusted={predicted_return:.3f}%"
                    )
        except Exception as e:
            logger.debug(f"  ENTRY STEP 5.5: Regime adjuster skipped: {e}")

        # Step 6: Check minimum threshold
        # Scalp uses min_confidence (from classifier probability).
        # Swing/general use min_predicted_move_pct (from regressor return %).
        if self.preset == "scalp":
            min_confidence = self.config.get("min_confidence", 0.60)
            confidence = abs(predicted_return)  # ScalpPredictor returns signed confidence
            if confidence < min_confidence:
                logger.info(
                    f"  ENTRY STEP 6 SKIP: confidence {confidence:.3f} < {min_confidence} threshold"
                )
                self._write_signal_log(
                    underlying_price=underlying_price,
                    predicted_return=predicted_return,
                    step_stopped_at=6,
                    stop_reason=f"confidence {confidence:.3f} < {min_confidence} threshold",
                )
                return
            logger.info(
                f"  ENTRY STEP 6 OK: confidence {confidence:.3f} >= {min_confidence} threshold"
            )
        else:
            # Use lower threshold in backtest mode (stock moves << option moves)
            if self._backtest_mode:
                min_move = 0.5
            else:
                min_move = self.config.get("min_predicted_move_pct", 1.0)

            if abs(predicted_return) < min_move:
                logger.info(
                    f"  ENTRY STEP 6 SKIP: |{predicted_return:.3f}%| < {min_move}% threshold"
                )
                self._write_signal_log(
                    underlying_price=underlying_price,
                    predicted_return=predicted_return,
                    step_stopped_at=6,
                    stop_reason=f"|{predicted_return:.3f}%| < {min_move}% threshold",
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
                    self._write_signal_log(
                        underlying_price=underlying_price,
                        predicted_return=predicted_return,
                        step_stopped_at=7,
                        stop_reason="Already have open stock position (backtest)",
                    )
                    return

            # Long-only in backtest — Lumibot backtester hangs on short sells.
            # For scalp, predicted_return is signed confidence, not return %.
            # Positive = bullish signal, negative = bearish signal.
            if predicted_return <= 0:
                if self.preset == "scalp":
                    logger.info(
                        f"  BACKTEST: Bearish signal ({predicted_return:+.3f} confidence) "
                        f"— stock backtest is long-only, skipping PUT signal"
                    )
                else:
                    logger.info(
                        f"  BACKTEST: Negative prediction ({predicted_return:+.3f}%) "
                        f"— long-only mode, skipping"
                    )
                self._write_signal_log(
                    underlying_price=underlying_price,
                    predicted_return=predicted_return,
                    step_stopped_at=7,
                    stop_reason=f"Negative prediction ({predicted_return:+.3f}) — long-only backtest",
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
                self._write_signal_log(
                    underlying_price=underlying_price,
                    predicted_return=predicted_return,
                    step_stopped_at=10,
                    stop_reason=f"Cannot afford 1 share at ${underlying_price:.2f}",
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
                    direction="LONG",  # Uppercase for DB/UI — stock trade
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

                self._write_signal_log(
                    underlying_price=underlying_price,
                    predicted_return=predicted_return,
                    entered=True,
                    trade_id=trade_id,
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
            self._write_signal_log(
                underlying_price=underlying_price,
                predicted_return=predicted_return,
                step_stopped_at=8,
                stop_reason=f"PDT limit: {pdt['message']}",
            )
            return

        min_dte = self.config.get("min_dte", 7)
        max_dte = self.config.get("max_dte", 45)
        max_hold = self.config.get("max_hold_days", 7)
        min_ev = self.config.get("min_ev_pct", 10)

        # ENTRY STEP 8.5: Implied move vs predicted move gate
        # Only enter if the model predicts a move that exceeds or approaches
        # what the options market has already priced in.
        # If the market implies a 6% weekly move and we predict 2%, there is no edge.
        if self.config.get("implied_move_gate_enabled", True):
            from ml.ev_filter import get_implied_move_pct
            implied_move = get_implied_move_pct(
                strategy=self,
                symbol=self.symbol,
                underlying_price=underlying_price,
                target_dte_min=min_dte,
                target_dte_max=max_dte,
            )
            if implied_move is not None:
                abs_predicted = abs(predicted_return)
                implied_move_ratio_threshold = self.config.get("implied_move_ratio_min", 0.80)
                ratio = abs_predicted / implied_move if implied_move > 0 else 0
                if ratio < implied_move_ratio_threshold:
                    logger.info(
                        f"  ENTRY STEP 8.5 SKIP: Predicted move below implied move "
                        f"(predicted={abs_predicted:.2f}% vs implied={implied_move:.2f}% "
                        f"ratio={ratio:.2f} < {implied_move_ratio_threshold:.2f})"
                    )
                    self._write_signal_log(
                        underlying_price=underlying_price,
                        predicted_return=predicted_return,
                        step_stopped_at=8,
                        stop_reason=(
                            f"Implied move gate: predicted {abs_predicted:.2f}% "
                            f"< {implied_move_ratio_threshold:.0%} of implied {implied_move:.2f}%"
                        ),
                    )
                    return
                else:
                    logger.info(
                        f"  ENTRY STEP 8.5 OK: Predicted {abs_predicted:.2f}% "
                        f">= {implied_move_ratio_threshold:.0%} of implied {implied_move:.2f}%"
                    )
            else:
                # Implied move unavailable — allow entry (fail open)
                logger.warning("  ENTRY STEP 8.5: Implied move unavailable — proceeding without gate")

        # Step 8.7: Earnings calendar gate — skip if earnings fall inside the hold window
        # (IV crush risk). Fail-open: if the API is unavailable, allows the trade.
        try:
            from data.earnings_calendar import has_earnings_in_window
            entry_date = self.get_datetime().date()
            max_hold = self.config.get("max_hold_days", 7)
            has_earnings, earnings_date = has_earnings_in_window(
                symbol=self.symbol,
                entry_date=entry_date,
                hold_days=max_hold,
                blackout_days_before=EARNINGS_BLACKOUT_DAYS_BEFORE,
                blackout_days_after=EARNINGS_BLACKOUT_DAYS_AFTER,
                alpaca_api_key=ALPACA_API_KEY,
                alpaca_secret_key=ALPACA_API_SECRET,
            )
            if has_earnings:
                logger.info(
                    f"  ENTRY STEP 8.7 SKIP: Earnings on {earnings_date} within "
                    f"blackout window (before={EARNINGS_BLACKOUT_DAYS_BEFORE}, "
                    f"after={EARNINGS_BLACKOUT_DAYS_AFTER})"
                )
                self._write_signal_log(
                    underlying_price=underlying_price,
                    predicted_return=predicted_return,
                    step_stopped_at=8.7,
                    stop_reason=(
                        f"Earnings gate: {earnings_date} within hold window "
                        f"(blackout {EARNINGS_BLACKOUT_DAYS_BEFORE}d before / "
                        f"{EARNINGS_BLACKOUT_DAYS_AFTER}d after)"
                    ),
                )
                return
            logger.info("  ENTRY STEP 8.7 OK: No earnings in hold window")
        except Exception as e:
            logger.warning(f"  ENTRY STEP 8.7: Earnings check failed — proceeding (fail open): {e}")

        # Step 9: Scan option chain through EV filter
        logger.info(
            f"  ENTRY STEP 9: Scanning chain — DTE={min_dte}-{max_dte}, "
            f"min_ev={min_ev}%"
        )
        # For scalp, convert signed confidence to an estimated return for EV calculation.
        # ScalpPredictor returns signed confidence (e.g., +0.72 = 72% confident UP).
        # EV filter expects predicted_return_pct (e.g., +0.15 = predicted +0.15% move).
        # Conversion: estimated_return = confidence * avg_30min_move * sign
        if self.preset == "scalp":
            from ml.scalp_predictor import ScalpPredictor
            confidence = abs(predicted_return)
            direction_sign = 1.0 if predicted_return > 0 else -1.0
            avg_move = 0.10  # Default avg 30-min move (0.10%)
            if isinstance(self.predictor, ScalpPredictor):
                avg_move = self.predictor.get_avg_30min_move_pct()
            ev_predicted_return = confidence * avg_move * direction_sign
            logger.info(
                f"  ENTRY STEP 9: Scalp EV input: confidence={confidence:.3f} x "
                f"avg_move={avg_move:.4f}% x sign={direction_sign:+.0f} "
                f"= {ev_predicted_return:+.4f}%"
            )
        else:
            ev_predicted_return = predicted_return

        best_contract = scan_chain_for_best_ev(
            strategy=self,
            symbol=self.symbol,
            predicted_return_pct=ev_predicted_return,
            underlying_price=underlying_price,
            min_dte=min_dte,
            max_dte=max_dte,
            max_hold_days=max_hold,
            min_ev_pct=min_ev,
            max_spread_pct=self.config.get("max_spread_pct", 0.50),
        )

        t_ev = time.time()
        self._iteration_timings["ev_scan"] = t_ev - t_predict

        if best_contract is None:
            logger.info("  ENTRY STEP 9 SKIP: No contract meets EV threshold")
            self._write_signal_log(
                underlying_price=underlying_price,
                predicted_return=predicted_return,
                step_stopped_at=9,
                stop_reason="No contract meets EV threshold",
            )
            return

        logger.info(
            f"  ENTRY STEP 9 OK: {best_contract.right} ${best_contract.strike} "
            f"exp={best_contract.expiration} EV={best_contract.ev_pct:.1f}% "
            f"premium=${best_contract.premium:.2f}"
        )

        # Step 9.5: Liquidity gate — verify OI and volume on the selected contract
        # Uses Alpaca options snapshot API for the specific contract (one API call).
        try:
            from ml.liquidity_filter import check_liquidity, fetch_option_snapshot
            snapshot = fetch_option_snapshot(
                symbol=self.symbol,
                expiration=str(best_contract.expiration),
                strike=best_contract.strike,
                right=best_contract.right,
                api_key=ALPACA_API_KEY,
                api_secret=ALPACA_API_SECRET,
                paper=True,
            )
            liq_result = check_liquidity(
                open_interest=snapshot.get("open_interest"),
                daily_volume=snapshot.get("volume"),
                bid_price=snapshot.get("bid"),
                ask_price=snapshot.get("ask"),
                min_oi=MIN_OPEN_INTEREST,
                min_volume=MIN_OPTION_VOLUME,
                max_spread_pct=self.config.get("max_spread_pct", 0.12),
                symbol=self.symbol,
            )
            if not liq_result.passed:
                logger.info(
                    f"  ENTRY STEP 9.5 SKIP: Liquidity reject — {liq_result.reject_reason}"
                )
                self._write_signal_log(
                    underlying_price=underlying_price,
                    predicted_return=predicted_return,
                    step_stopped_at=9.5,
                    stop_reason=f"Liquidity: {liq_result.reject_reason}",
                )
                return
            logger.info(
                f"  ENTRY STEP 9.5 OK: oi={liq_result.open_interest} "
                f"vol={liq_result.daily_volume} spread={liq_result.bid_ask_spread_pct}"
            )
        except Exception as e:
            # Fail-safe: reject if liquidity cannot be determined
            logger.warning(f"  ENTRY STEP 9.5: Liquidity check error — rejecting: {e}")
            self._write_signal_log(
                underlying_price=underlying_price,
                predicted_return=predicted_return,
                step_stopped_at=9.5,
                stop_reason=f"Liquidity check error: {e}",
            )
            return

        # Step 9.7: Portfolio delta limit — reject if adding this trade would exceed limit
        try:
            from config import PORTFOLIO_MAX_ABS_DELTA
            positions_for_greeks = [
                {"entry_greeks": t.get("entry_greeks", {}), "quantity": t.get("quantity", 1)}
                for t in self._open_trades.values()
            ]
            port_greeks = self.risk_mgr.get_portfolio_greeks(positions_for_greeks)
            # Include the proposed new position in the check
            proposed_delta = port_greeks["total_delta"] + best_contract.delta
            if abs(proposed_delta) > PORTFOLIO_MAX_ABS_DELTA:
                reason = (
                    f"Portfolio delta {abs(proposed_delta):.2f} would exceed "
                    f"limit {PORTFOLIO_MAX_ABS_DELTA:.1f} "
                    f"(current={port_greeks['total_delta']:.2f} + new={best_contract.delta:.3f})"
                )
                logger.info(f"  ENTRY STEP 9.7 SKIP: {reason}")
                self._write_signal_log(
                    underlying_price=underlying_price,
                    predicted_return=predicted_return,
                    step_stopped_at=9.7,
                    stop_reason=f"Portfolio delta: {reason}",
                )
                return
            logger.info(
                f"  ENTRY STEP 9.7 OK: portfolio delta={port_greeks['total_delta']:.2f} "
                f"+ new={best_contract.delta:.3f} = {proposed_delta:.2f} "
                f"(limit={PORTFOLIO_MAX_ABS_DELTA:.1f})"
            )
        except Exception as e:
            # Fail open — don't block trades if Greeks check fails
            logger.warning(f"  ENTRY STEP 9.7: Portfolio delta check failed — proceeding: {e}")

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
            self._write_signal_log(
                underlying_price=underlying_price,
                predicted_return=predicted_return,
                step_stopped_at=10,
                stop_reason=f"Risk check: {'; '.join(risk_check['reasons'])}",
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
                "entry_features": None,  # Set below after loggable_features is computed
                "entry_greeks": entry_greeks,
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

            # Store entry features in _open_trades for feedback queue at exit time
            self._open_trades[trade_id]["entry_features"] = loggable_features

            logger.info(f"  ENTRY STEP 12: Logging trade to DB — trade_id={trade_id}")
            active_model_type = type(self.predictor).__name__.lower().replace("predictor", "")
            # Results in: "xgboost", "tft", "ensemble" — matches DB model_type values

            self.risk_mgr.log_trade_open(
                trade_id=trade_id,
                profile_id=self.profile_id,
                symbol=self.symbol,
                direction=best_contract.right,  # "CALL" or "PUT" for DB/UI
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

            self._write_signal_log(
                underlying_price=underlying_price,
                predicted_return=predicted_return,
                entered=True,
                trade_id=trade_id,
            )

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

    def get_health_stats(self) -> dict:
        """Return strategy health stats for monitoring."""
        stats = {
            "profile_id": self.profile_id,
            "total_iterations": self._total_iterations,
            "total_errors": self._total_errors,
            "consecutive_errors": self._consecutive_errors,
            "auto_paused": self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS,
            "last_timing": self._iteration_timings.copy(),
            "theta_circuit_breaker": self._theta_circuit_breaker.get_stats(),
        }
        # Add model health
        stats["model_health"] = self._compute_rolling_accuracy()
        return stats

    def _record_prediction(self, predicted_return: float, current_price: float):
        """
        Record a prediction for later accuracy tracking.
        Called after Step 5 (ML prediction) in _check_entries(), regardless
        of whether the trade is entered.
        """
        import datetime as dt

        if predicted_return is None or np.isnan(predicted_return) or np.isinf(predicted_return):
            return

        direction = "up" if predicted_return > 0 else "down" if predicted_return < 0 else "neutral"

        entry = {
            "predicted_direction": direction,
            "predicted_value": float(predicted_return),
            "timestamp": dt.datetime.now().isoformat(),
            "price_at_prediction": float(current_price),
            "actual_direction": None,  # Filled in by _update_prediction_outcomes
        }
        self._prediction_history.append(entry)

        # Trim to window size
        if len(self._prediction_history) > MODEL_HEALTH_WINDOW_SIZE * 2:
            self._prediction_history = self._prediction_history[-MODEL_HEALTH_WINDOW_SIZE:]

    def _update_prediction_outcomes(self, current_price: float):
        """
        Look back at recent predictions and fill in actual direction
        based on price movement since prediction time.

        Called at the start of each iteration. We compare current_price
        against price_at_prediction. A prediction is 'resolved' once we
        have the actual direction.

        For swing/general: we wait at least 1 iteration (5-15 min) before resolving.
        For scalp: resolve immediately (30-min horizon ~ 30 iterations at 1-min).
        """
        for entry in self._prediction_history:
            if entry["actual_direction"] is not None:
                continue  # Already resolved

            pred_price = entry.get("price_at_prediction")
            if pred_price is None or pred_price <= 0:
                continue

            pct_change = (current_price - pred_price) / pred_price * 100

            # Use a small threshold to avoid noise
            if abs(pct_change) < 0.01:
                entry["actual_direction"] = "neutral"
            elif pct_change > 0:
                entry["actual_direction"] = "up"
            else:
                entry["actual_direction"] = "down"

    def _compute_rolling_accuracy(self) -> dict:
        """
        Compute rolling directional accuracy from prediction history.
        Returns dict with accuracy stats for health monitoring.
        """
        resolved = [
            e for e in self._prediction_history
            if e.get("actual_direction") is not None
            and e.get("predicted_direction") != "neutral"
        ]

        total = len(resolved)
        if total < MODEL_HEALTH_MIN_SAMPLES:
            return {
                "rolling_accuracy": None,
                "total_predictions": total,
                "correct_predictions": 0,
                "status": "insufficient_data",
                "message": f"Need {MODEL_HEALTH_MIN_SAMPLES} resolved predictions, have {total}",
            }

        # Only count last WINDOW_SIZE
        recent = resolved[-MODEL_HEALTH_WINDOW_SIZE:]
        correct = sum(
            1 for e in recent
            if e["predicted_direction"] == e["actual_direction"]
        )
        accuracy = correct / len(recent) if recent else 0.0

        if accuracy < MODEL_DEGRADED_THRESHOLD:
            status = "degraded"
        elif accuracy < 0.52:
            status = "warning"
        else:
            status = "healthy"

        return {
            "rolling_accuracy": round(accuracy, 4),
            "total_predictions": len(recent),
            "correct_predictions": correct,
            "status": status,
            "message": (
                f"{correct}/{len(recent)} correct ({accuracy*100:.1f}%) "
                f"over last {len(recent)} non-neutral predictions"
            ),
        }

    def _persist_health_to_db(self):
        """
        Write model health stats to system_state table periodically.
        Called at most once per minute to avoid excessive DB writes.
        """
        import sqlite3
        import json
        import datetime as dt

        now = time.time()
        if now - self._last_health_persist_time < 60:
            return
        self._last_health_persist_time = now

        stats = self._compute_rolling_accuracy()
        stats["profile_id"] = self.profile_id
        stats["profile_name"] = getattr(self, "profile_name", "unknown")
        stats["model_type"] = type(self.predictor).__name__ if self.predictor else "none"
        stats["updated_at"] = dt.datetime.now().isoformat()

        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=2)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO system_state (key, value, updated_at) VALUES (?, ?, ?)",
                    (
                        f"model_health_{self.profile_id}",
                        json.dumps(stats),
                        stats["updated_at"],
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Failed to persist model health: {e}")

    def trace_stats(self, context, snapshot_before):
        """Return custom stats for Lumibot logging."""
        return {
            "open_trades": len(self._open_trades),
            "profile": self.profile_name,
        }