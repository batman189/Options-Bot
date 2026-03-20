"""
Base strategy class with shared logic for all profile types.
Matches PROJECT_ARCHITECTURE.md Section 4 — One Strategy instance per profile.

Phase 2 additions:
    - Emergency stop loss check at top of on_trading_iteration()
    - _initial_portfolio_value recorded at startup for drawdown tracking
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
import re
import sqlite3
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

from config import DB_PATH, DTE_EXIT_FLOOR
from config import (
    THETA_CB_FAILURE_THRESHOLD, THETA_CB_RESET_TIMEOUT,
    MAX_CONSECUTIVE_ERRORS, ITERATION_ERROR_RESET_ON_SUCCESS,
)
from config import (
    MODEL_HEALTH_WINDOW_SIZE,
    MODEL_DEGRADED_THRESHOLD,
    MODEL_HEALTH_MIN_SAMPLES,
    PREDICTION_RESOLVE_MINUTES_SWING,
    PREDICTION_RESOLVE_MINUTES_SCALP,
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

    def send_update_to_cloud(self):
        """Override Lumibot cloud reporting — we don't use LumiWealth/BotSpot."""
        pass

    @staticmethod
    def _normalize_sleeptime(raw: str) -> str:
        """Normalize sleeptime to Lumibot format (e.g. '5M', '1M', '15M', '1D').
        Lumibot expects '<int><single-char>' where char is S/M/H/D.
        Handles common variants like '5min', '1hour', '15minutes', etc.
        """
        raw = raw.strip()
        # Already valid single-char suffix
        if len(raw) >= 2 and raw[-1].isalpha() and raw[:-1].isdigit():
            return raw.upper() if raw[-1].upper() in ("S", "M", "H", "D") else raw
        # Extract number and unit text
        m = re.match(r"(\d+)\s*(.*)", raw, re.IGNORECASE)
        if not m:
            logger.warning(f"Cannot parse sleeptime '{raw}', defaulting to '5M'")
            return "5M"
        num = m.group(1)
        unit = m.group(2).lower().strip()
        unit_map = {
            "": "M", "m": "M", "min": "M", "mins": "M", "minute": "M", "minutes": "M",
            "s": "S", "sec": "S", "secs": "S", "second": "S", "seconds": "S",
            "h": "H", "hr": "H", "hrs": "H", "hour": "H", "hours": "H",
            "d": "D", "day": "D", "days": "D",
        }
        suffix = unit_map.get(unit)
        if suffix is None:
            logger.warning(f"Unknown sleeptime unit '{unit}' in '{raw}', defaulting to '5M'")
            return "5M"
        return f"{num}{suffix}"

    def initialize(self):
        """Called once at startup."""
        logger.info("BaseOptionsStrategy.initialize() starting")

        self.profile_id = self.parameters.get("profile_id", "unknown")
        self.profile_name = self.parameters.get("profile_name", "Unnamed")
        self.symbol = self.parameters.get("symbol", "TSLA")
        self.preset = self.parameters.get("preset", "swing")
        self._is_scalp = self.preset in ("scalp", "otm_scalp")
        self.config = self.parameters.get("config", {})
        self.model_path = self.parameters.get("model_path")

        # Set sleep time from config — normalize to Lumibot format (e.g. "5M", "1M", "15M")
        raw_sleep = self.config.get("sleeptime", "5M")
        self.sleeptime = self._normalize_sleeptime(raw_sleep)

        logger.info(f"Initializing {self.profile_name} ({self.preset}) on {self.symbol}")
        logger.info(f"  Profile ID: {self.profile_id}")
        logger.info(f"  Sleep time: {self.sleeptime}")
        logger.info(f"  Config: {json.dumps(self.config, indent=2)}")

        # Load ML model — detect type from DB to load correct predictor class
        self.predictor = None
        if self.model_path:
            try:
                model_type = self._detect_model_type()
                self._cached_model_type = model_type  # Cache for Step 6/8.5/9
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
                elif model_type in ("xgb_swing_classifier", "lgbm_classifier"):
                    from ml.swing_classifier_predictor import SwingClassifierPredictor
                    self.predictor = SwingClassifierPredictor(self.model_path)
                else:
                    # Default: xgboost (covers 'xgboost' and any unknown type)
                    self.predictor = XGBoostPredictor(self.model_path)
                logger.info(
                    f"  Predictor loaded: {type(self.predictor).__name__}"
                )
            except Exception as e:
                logger.error(
                    f"  Failed to load model (type={model_type}): {e}. "
                    f"Strategy will run WITHOUT a predictor — no trades will fire.",
                    exc_info=True,
                )
                self.predictor = None

        # Initialize risk manager
        logger.info("  Initializing RiskManager")
        self.risk_mgr = RiskManager()

        # Track our open positions: {trade_id: {asset, entry_price, entry_date, ...}}
        self._open_trades = {}
        self._recover_open_trades()

        # Stock asset for price lookups
        self._stock_asset = Asset(self.symbol, asset_type="stock")

        # Scalp equity gate: warn if portfolio < $25K (required for unlimited day trades)
        if self._is_scalp:
            min_equity = self.config.get("requires_min_equity", 25000)
            if min_equity > 0:
                logger.info(
                    f"  Scalp preset: requires ${min_equity:,.0f} equity "
                    f"(PDT unlimited day trades)"
                )

        # Record initial portfolio value for emergency stop loss calculation
        self._initial_portfolio_value = 0.0  # Set on first iteration

        # Pre-fetch intraday bars from Alpaca for backtesting.
        # ThetaData Standard only provides EOD stock data, so we use Alpaca
        # for intraday bars needed by the ML feature pipeline.
        self._cached_bars = None
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
                warmup_days = 10 if self._is_scalp else 45
                fetch_start = bt_start - datetime.timedelta(days=warmup_days)
                fetch_end = bt_end + datetime.timedelta(days=1)
                bar_granularity = self.config.get("bar_granularity", "5min")
                logger.info(
                    f"  Pre-fetching {bar_granularity} bars from Alpaca: "
                    f"{fetch_start.date()} to {fetch_end.date()}..."
                )
                self._cached_bars = provider.get_historical_bars(
                    self.symbol, fetch_start, fetch_end, timeframe=bar_granularity
                )
                logger.info(
                    f"  Pre-fetched {len(self._cached_bars)} {bar_granularity} bars from Alpaca"
                )
                # Note: _cached_bars may contain 1-min bars when preset=scalp.
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

        # Cache options daily data per calendar day to avoid re-fetching every iteration.
        # Options features are daily resolution — no need to refetch within the same day.
        self._cached_options_daily_df = None
        self._cached_options_date: str | None = None

        # Phase 6: Model health tracking
        # Stores recent predictions to compare against actual outcomes
        # Format: list of {"predicted_direction": "up"|"down"|"neutral",
        #                   "predicted_value": float, "timestamp": str,
        #                   "price_at_prediction": float,
        #                   "actual_direction": "up"|"down"|"neutral"|None}
        self._prediction_history: list[dict] = []
        self._last_health_persist_time = 0.0

        logger.info(f"Strategy initialized: {self.profile_name}")

    def _get_classifier_avg_move(self) -> float:
        """Get the average move % from the loaded classifier predictor.
        ScalpPredictor uses get_avg_30min_move_pct(), SwingClassifierPredictor uses get_avg_daily_move_pct().
        """
        from ml.scalp_predictor import ScalpPredictor
        from ml.swing_classifier_predictor import SwingClassifierPredictor
        if isinstance(self.predictor, ScalpPredictor):
            return self.predictor.get_avg_30min_move_pct()
        elif isinstance(self.predictor, SwingClassifierPredictor):
            return self.predictor.get_avg_daily_move_pct()
        return 1.0  # Default fallback

    def _detect_model_type(self) -> str:
        """
        Query the DB to find what model_type is stored for this profile's
        current model. Returns 'xgboost' as default if anything fails.

        This is called during initialize() to determine which predictor class
        to instantiate. Avoids hardcoding XGBoostPredictor everywhere.
        """

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
                if row:
                    return row["model_type"]
                logger.warning(
                    f"_detect_model_type: No model row found for profile {self.profile_id}, "
                    f"defaulting to 'xgboost'"
                )
                return "xgboost"
            finally:
                conn.close()
        except Exception as e:
            logger.error(
                f"_detect_model_type: DB query failed for profile {self.profile_id}: {e}. "
                f"Defaulting to 'xgboost' — this may load the WRONG predictor class."
            )
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
                try:
                    self._write_signal_log(
                        step_stopped_at=0,
                        stop_reason=f"Auto-paused: {self._consecutive_errors} consecutive errors",
                    )
                except Exception:
                    pass
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

            # Fetch underlying price early so all signal log paths can include it
            _underlying_price = None
            try:
                _underlying_price = self.get_last_price(self._stock_asset)
            except Exception:
                pass

            # Scalp equity gate: skip trading if portfolio value < $25K
            # (PDT rule requires $25K+ for unlimited day trades)
            if self._is_scalp:
                _pv = self.get_portfolio_value() or 0.0
                min_equity = self.config.get("requires_min_equity", 25000)
                if min_equity > 0 and _pv < min_equity:
                    logger.warning(
                        f"SCALP EQUITY GATE: Portfolio ${_pv:,.0f} < "
                        f"${min_equity:,.0f} required — skipping all scalp trading"
                    )
                    try:
                        self._write_signal_log(
                            underlying_price=_underlying_price,
                            step_stopped_at=0,
                            stop_reason=f"Scalp equity gate: ${_pv:,.0f} < ${min_equity:,.0f}",
                        )
                    except Exception:
                        pass
                    return

            try:
                portfolio_value = self.get_portfolio_value() or 0.0

                # Record initial portfolio value — retries every iteration until
                # a valid (>0) value is obtained so emergency stop is never
                # permanently disabled by a transient broker API failure.
                if self._initial_portfolio_value == 0.0:
                    if portfolio_value > 0:
                        self._initial_portfolio_value = portfolio_value
                        logger.info(
                            f"Initial portfolio value recorded: ${portfolio_value:,.2f}"
                        )
                    elif self._total_iterations > 1:
                        logger.warning(
                            f"Portfolio value still $0 after {self._total_iterations} iterations "
                            f"— emergency stop disabled until a valid value is obtained"
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
                        try:
                            self._write_signal_log(
                                underlying_price=_underlying_price,
                                step_stopped_at=0,
                                stop_reason=f"Portfolio exposure limit: {exposure['exposure_pct']:.1f}%",
                            )
                        except Exception:
                            pass
                        return

                # STEP 2: Check for new entries
                if self.predictor is not None:
                    self._check_entries()
                else:
                    logger.warning("No model loaded — skipping entries")
                    try:
                        self._write_signal_log(
                            underlying_price=_underlying_price,
                            step_stopped_at=0,
                            stop_reason="No model loaded",
                        )
                    except Exception:
                        pass

            except Exception as e:
                self._consecutive_errors += 1
                self._total_errors += 1
                logger.error(
                    f"[{self.profile_name}] TRADING ERROR ({self._consecutive_errors}/"
                    f"{MAX_CONSECUTIVE_ERRORS}): {type(e).__name__}: {e}",
                    exc_info=True,
                )
                try:
                    self._write_signal_log(
                        underlying_price=_underlying_price,
                        step_stopped_at=0,
                        stop_reason=f"Unhandled error: {str(e)[:200]}",
                    )
                except Exception:
                    pass  # Double-fault protection — never crash the trading loop
            else:
                # Trading logic succeeded — reset error counter
                if ITERATION_ERROR_RESET_ON_SUCCESS:
                    self._consecutive_errors = 0

            # ── Persist model health stats ────────────────────────────
            try:
                self._persist_health_to_db()
            except Exception:
                pass  # Non-fatal

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
                "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            state_file.write_text(json.dumps(state_data, indent=2))

            # Alert when circuit breaker transitions to OPEN
            if theta_state == "open":
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

            # Skip positions belonging to other strategies/profiles.
            # Both strategies share the same Alpaca account so get_positions()
            # returns ALL open positions, including those opened by a different
            # profile (e.g. Spy Scalp would otherwise try to exit TSLA positions).
            if asset.symbol != self.symbol:
                continue

            # In backtest mode we trade stock; in live mode we trade options
            if self._backtest_mode:
                if asset.asset_type != "stock":
                    continue
            else:
                if asset.asset_type != "option":
                    continue

            # Find ALL trade records that match this broker position.
            # Multiple DB records can exist for the same contract when the bot
            # entered separate trades (e.g. 4 contracts then 2 more contracts).
            # The broker reports one combined position; we must update all records.
            matching_trades = []  # list of (trade_id, trade_info)
            for tid, tinfo in self._open_trades.items():
                if asset.asset_type == "stock":
                    if (tinfo["symbol"] == asset.symbol and
                            tinfo.get("asset_type") == "stock"):
                        matching_trades.append((tid, tinfo))
                else:
                    if (tinfo["symbol"] == asset.symbol and
                            tinfo["strike"] == asset.strike and
                            tinfo["expiration"] == asset.expiration and
                            tinfo["right"] == asset.right):
                        matching_trades.append((tid, tinfo))

            if not matching_trades:
                logger.warning(f"_check_exits: open position not in _open_trades: {asset}")
                continue

            # Primary match drives exit decisions (entry_price, hold_days, etc.)
            trade_id, trade_info = matching_trades[0]
            if len(matching_trades) > 1:
                logger.debug(
                    f"_check_exits: {len(matching_trades)} DB trades map to one broker "
                    f"position for {asset} — updating all"
                )

            # Get current price
            current_price = self.get_last_price(asset)
            if current_price is None:
                logger.warning(
                    f"_check_exits: cannot get price for {asset} — skipping exit check"
                )
                continue

            entry_price = trade_info["entry_price"]
            direction = trade_info.get("direction", "long")

            # P&L calculation — currently all options use direction="long".
            # Short branch reserved for future short-selling support.
            if direction == "short":
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
            else:
                pnl_pct = ((current_price - entry_price) / entry_price) * 100

            # Write unrealized P&L to DB for ALL matching trades (each uses its
            # own entry_price/quantity so the UI shows correct per-trade values).
            try:
                conn = sqlite3.connect(str(DB_PATH), timeout=5)
                now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
                for tid_i, tinfo_i in matching_trades:
                    ep_i = tinfo_i["entry_price"]
                    dir_i = tinfo_i.get("direction", "long")
                    qty_i = tinfo_i.get("quantity", 0)
                    if dir_i == "short":
                        pnl_pct_i = ((ep_i - current_price) / ep_i) * 100
                        unreal_i = (ep_i - current_price) * qty_i
                    else:
                        pnl_pct_i = ((current_price - ep_i) / ep_i) * 100
                        unreal_i = (current_price - ep_i) * qty_i
                    if asset.asset_type == "option":
                        unreal_i *= 100
                    conn.execute(
                        "UPDATE trades SET unrealized_pnl = ?, unrealized_pnl_pct = ?, updated_at = ? WHERE id = ?",
                        (round(unreal_i, 2), round(pnl_pct_i, 2), now_utc, tid_i),
                    )
                conn.commit()
                conn.close()
            except Exception as e:
                logger.warning(f"_check_exits: failed to update unrealized P&L: {e}")

            # Get current underlying price
            underlying_price = self.get_last_price(self._stock_asset) or 0

            # ---- Exit rule evaluation (first match wins) ----
            exit_reason = None

            # Rule 1: Profit Target
            # Stock-appropriate thresholds in backtest mode (options config
            # uses 50%/30% which are unreachable for stocks in 7 days)
            if asset.asset_type == "stock":
                if self._is_scalp:
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
                if dte < DTE_EXIT_FLOOR:
                    exit_reason = "dte_exit"
                    logger.info(f"_check_exits: DTE floor hit: dte={dte} < {DTE_EXIT_FLOOR}")

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
                                # For options, use right (CALL/PUT).
                                # For backtest stocks (no "right" key), derive from direction.
                                right = trade_info.get("right")
                                if right is None:
                                    right = "CALL" if trade_info.get("direction", "long") == "long" else "PUT"
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
            if exit_reason is None and self._is_scalp:
                from zoneinfo import ZoneInfo
                now = self.get_datetime()
                eastern = ZoneInfo("America/New_York")
                if now.tzinfo is not None:
                    now_et = now.astimezone(eastern)
                else:
                    # Assume UTC for backtest
                    now_et = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(eastern)

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
                    matching_trades=matching_trades,
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
            if self._backtest_mode and self._cached_bars is not None:
                now_dt = self.get_datetime()
                bars_df = self._cached_bars[self._cached_bars.index <= now_dt]
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
            # Reuse strategy-level options cache (daily resolution)
            import datetime as _dt
            today_str = _dt.date.today().isoformat()
            if self._cached_options_date == today_str:
                options_daily_df = self._cached_options_daily_df
            else:
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
                self._cached_options_daily_df = options_daily_df
                self._cached_options_date = today_str

            # Fetch VIX daily bars for VIX features
            vix_daily_df = None
            try:
                from data.vix_provider import fetch_vix_daily_bars
                vix_daily_df = fetch_vix_daily_bars(
                    bars_df.index.min().to_pydatetime(),
                    bars_df.index.max().to_pydatetime(),
                )
            except Exception:
                pass

            bars_per_day = 390 if self._is_scalp else 78
            featured_df = compute_base_features(bars_df, options_daily_df=options_daily_df, vix_daily_df=vix_daily_df, bars_per_day=bars_per_day)

            if self.preset == "swing":
                from ml.feature_engineering.swing_features import compute_swing_features
                featured_df = compute_swing_features(featured_df)
            elif self.preset == "general":
                from ml.feature_engineering.general_features import compute_general_features
                featured_df = compute_general_features(featured_df)
            elif self._is_scalp:
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
        matching_trades,
        position,
        asset,
        current_price,
        underlying_price,
        exit_reason,
    ):
        """Execute a close order and log it to the database.

        matching_trades: list of (trade_id, trade_info) for all DB records that
        correspond to this broker position. The broker order is submitted once
        (closing the full combined position), then each DB record is logged and
        removed from tracking individually using its own entry_price/quantity.
        """
        # Primary trade drives logging and feedback
        trade_id, trade_info = matching_trades[0]
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
                f"reason={exit_reason} price=${current_price:.2f} "
                f"db_trades={len(matching_trades)}"
            )

        try:
            quantity = abs(position.quantity)

            if is_stock:
                side = "sell" if direction == "long" else "buy"
                order = self.create_order(asset, quantity, side=side)
            else:
                order = self.create_order(asset, quantity, side="sell_to_close")

            logger.info(f"_execute_exit: submitting order — {side if is_stock else 'sell_to_close'} {quantity}x {asset}")
            self.submit_order(order)
            logger.info(f"_execute_exit: order submitted for {trade_id}")

            # Get exit Greeks once (shared across all DB records for this position)
            exit_greeks_dict = {}
            if not is_stock:
                try:
                    exit_greeks = self.get_greeks(asset, underlying_price=underlying_price)
                    if exit_greeks:
                        exit_greeks_dict = {
                            "delta": getattr(exit_greeks, "delta", None),
                            "gamma": getattr(exit_greeks, "gamma", None),
                            "theta": getattr(exit_greeks, "theta", None),
                            "vega": getattr(exit_greeks, "vega", None),
                            "iv": getattr(exit_greeks, "implied_volatility", None),
                        }
                except Exception as e:
                    logger.warning(f"_execute_exit: could not get exit Greeks: {e}")

            # Log close and remove tracking for ALL matching DB trades
            for tid_i, tinfo_i in matching_trades:
                ep_i = tinfo_i["entry_price"]
                dir_i = tinfo_i.get("direction", "long")
                qty_i = tinfo_i.get("quantity", 0)

                if dir_i == "short":
                    pnl_pct_i = ((ep_i - current_price) / ep_i) * 100
                    pnl_dollars_i = (ep_i - current_price) * qty_i * (1 if is_stock else 100)
                else:
                    pnl_pct_i = ((current_price - ep_i) / ep_i) * 100
                    pnl_dollars_i = (current_price - ep_i) * qty_i * (1 if is_stock else 100)

                entry_date_i = datetime.datetime.fromisoformat(tinfo_i["entry_date"]).date()
                hold_days_i = (self.get_datetime().date() - entry_date_i).days
                was_day_trade_i = hold_days_i == 0

                logger.info(f"_execute_exit: logging close to DB for {tid_i}")
                self.risk_mgr.log_trade_close(
                    trade_id=tid_i,
                    exit_price=current_price,
                    exit_underlying_price=underlying_price,
                    exit_reason=exit_reason,
                    exit_greeks=exit_greeks_dict,
                    pnl_dollars=pnl_dollars_i,
                    pnl_pct=pnl_pct_i,
                    hold_days=hold_days_i,
                    was_day_trade=was_day_trade_i,
                )

                # Enqueue for feedback loop — use underlying return, not option P&L
                try:
                    from ml.feedback_queue import enqueue_completed_sample
                    entry_underlying = tinfo_i.get("entry_underlying_price", 0)
                    if entry_underlying and entry_underlying > 0 and underlying_price and underlying_price > 0:
                        underlying_return_pct = ((underlying_price - entry_underlying) / entry_underlying) * 100
                    else:
                        underlying_return_pct = None
                    enqueue_completed_sample(
                        db_path=str(DB_PATH),
                        trade_id=tid_i,
                        profile_id=self.profile_id,
                        symbol=tinfo_i.get("symbol", self.symbol),
                        entry_features=tinfo_i.get("entry_features"),
                        predicted_return=tinfo_i.get("entry_prediction"),
                        actual_return_pct=underlying_return_pct,
                    )
                except Exception as eq_err:
                    logger.warning(f"_execute_exit: feedback queue enqueue failed (non-fatal): {eq_err}")

                del self._open_trades[tid_i]
                logger.info(
                    f"_execute_exit: {tid_i} closed — P&L=${pnl_dollars_i:.2f} ({pnl_pct_i:.1f}%) "
                    f"hold={hold_days_i}d reason={exit_reason}"
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
        try:
            from config import DB_PATH
            predictor_type = type(self.predictor).__name__ if self.predictor else None
            now_str = self.get_datetime().isoformat()

            with sqlite3.connect(str(DB_PATH)) as con:
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
            logger.debug(f"Signal log written: step={step_stopped_at}, entered={entered}")
        except Exception as e:
            # Signal logging must NEVER crash the trading loop
            logger.error(f"_write_signal_log failed (non-fatal): {e}", exc_info=True)

    # =========================================================================
    # OPEN TRADE RECOVERY (on startup)
    # =========================================================================

    def _recover_open_trades(self):
        """
        Reload open trades from the DB so positions from prior bot sessions
        can still be managed (exit checks, stop losses, etc.).
        """
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT id, symbol, direction, strike, expiration, quantity,
                          entry_price, entry_date, entry_underlying_price,
                          entry_predicted_return, entry_greeks, entry_features
                   FROM trades
                   WHERE profile_id = ? AND exit_date IS NULL""",
                (self.profile_id,),
            ).fetchall()
            conn.close()

            for row in rows:
                trade_id = row["id"]
                greeks = {}
                if row["entry_greeks"]:
                    try:
                        greeks = json.loads(row["entry_greeks"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                features = {}
                if row["entry_features"]:
                    try:
                        features = json.loads(row["entry_features"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                expiration = row["expiration"]
                # Parse expiration to date object to match EVCandidate format
                if isinstance(expiration, str) and expiration != "N/A":
                    try:
                        expiration = datetime.datetime.strptime(
                            expiration.split("T")[0], "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        pass

                # direction in DB is "CALL", "PUT", or "LONG"
                direction_raw = row["direction"]
                if direction_raw in ("CALL", "PUT"):
                    right = direction_raw
                    asset_type = "option"
                else:
                    right = None
                    asset_type = "stock"

                self._open_trades[trade_id] = {
                    "symbol": row["symbol"],
                    "asset_type": asset_type,
                    "strike": row["strike"],
                    "expiration": expiration,
                    "right": right,
                    "direction": "long",
                    "entry_price": row["entry_price"],
                    "entry_date": row["entry_date"],
                    "entry_underlying_price": row["entry_underlying_price"],
                    "quantity": row["quantity"],
                    "entry_prediction": row["entry_predicted_return"],
                    "entry_features": features,
                    "entry_greeks": greeks,
                }

            if rows:
                logger.info(
                    f"  Recovered {len(rows)} open trade(s) from DB: "
                    + ", ".join(r["id"][:8] for r in rows)
                )
            else:
                logger.info("  No open trades to recover from DB")

        except Exception as e:
            logger.error(f"  Failed to recover open trades from DB: {e}", exc_info=True)

        # --- Broker-DB reconciliation ---
        # Cross-check recovered DB trades against actual broker positions
        # to detect orphaned trades or unknown positions.
        try:
            broker_positions = self.get_positions()
            broker_keys = set()
            for pos in broker_positions:
                asset = pos.asset
                if hasattr(asset, "strike") and hasattr(asset, "right"):
                    key = (asset.symbol, asset.strike, str(getattr(asset, "expiration", "")), asset.right)
                    broker_keys.add(key)

            # Check each DB trade has a matching broker position
            for trade_id, tinfo in list(self._open_trades.items()):
                if tinfo.get("asset_type") != "option":
                    continue
                db_key = (tinfo["symbol"], tinfo["strike"],
                          str(tinfo["expiration"]), tinfo["right"])
                if db_key not in broker_keys:
                    logger.warning(
                        f"  RECONCILIATION: DB trade {trade_id[:8]} "
                        f"({tinfo['symbol']} {tinfo['right']} {tinfo['strike']} "
                        f"exp={tinfo['expiration']}) has NO matching broker position. "
                        f"Position may have been closed externally."
                    )

            # Check for broker positions not in DB
            db_keys = set()
            for tinfo in self._open_trades.values():
                if tinfo.get("asset_type") == "option":
                    db_keys.add((tinfo["symbol"], tinfo["strike"],
                                 str(tinfo["expiration"]), tinfo["right"]))
            for bk in broker_keys:
                if bk not in db_keys:
                    logger.warning(
                        f"  RECONCILIATION: Broker position {bk[0]} {bk[3]} "
                        f"{bk[1]} exp={bk[2]} has NO matching DB trade for "
                        f"this profile. May belong to another profile or "
                        f"was opened externally."
                    )

            if broker_keys and not (broker_keys - db_keys) and not any(
                (tinfo["symbol"], tinfo["strike"], str(tinfo["expiration"]), tinfo["right"])
                not in broker_keys
                for tinfo in self._open_trades.values()
                if tinfo.get("asset_type") == "option"
            ):
                logger.info(f"  RECONCILIATION: All {len(self._open_trades)} DB trades match broker positions")
        except Exception as e:
            logger.warning(f"  RECONCILIATION: Could not verify broker positions: {e}")

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
                vix_min = self.config.get("vix_min", 15.0)
                vix_max = self.config.get("vix_max", 35.0)
                if not (vix_min <= vix_level <= vix_max):
                    regime = "elevated" if vix_level > vix_max else "suppressed"
                    logger.info(
                        f"  ENTRY STEP 1.5 SKIP: Volatility regime {regime} "
                        f"(VIXY={vix_level:.2f}, allowed={vix_min:.2f}-{vix_max:.2f})"
                    )
                    self._write_signal_log(
                        underlying_price=underlying_price,
                        step_stopped_at=1.5,
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
        if self._backtest_mode and self._cached_bars is not None:
            now_dt = self.get_datetime()
            bars_df = self._cached_bars[self._cached_bars.index <= now_dt]
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
            if self._is_scalp:
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
                if self._is_scalp:
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
            # Use strategy-level cache for options data (daily resolution —
            # no need to refetch within the same calendar day).
            import datetime as _dt
            today_str = _dt.date.today().isoformat()
            if self._cached_options_date == today_str:
                options_daily_df = self._cached_options_daily_df
            else:
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
                self._cached_options_daily_df = options_daily_df
                self._cached_options_date = today_str

            # Fetch VIX daily bars for VIX features
            vix_daily_df = None
            try:
                from data.vix_provider import fetch_vix_daily_bars
                vix_daily_df = fetch_vix_daily_bars(
                    bars_df.index.min().to_pydatetime(),
                    bars_df.index.max().to_pydatetime(),
                )
            except Exception as vix_err:
                logger.warning(f"  VIX daily bars fetch failed (continuing without): {vix_err}")

            bars_per_day = 390 if self._is_scalp else 78
            featured_df = compute_base_features(bars_df.copy(), options_daily_df=options_daily_df, vix_daily_df=vix_daily_df, bars_per_day=bars_per_day)

            if self.preset == "swing":
                from ml.feature_engineering.swing_features import compute_swing_features
                featured_df = compute_swing_features(featured_df)
            elif self.preset == "general":
                from ml.feature_engineering.general_features import compute_general_features
                featured_df = compute_general_features(featured_df)
            elif self._is_scalp:
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

        # BUG-006: Log top feature values for live vs training drift analysis.
        # Only log the top 10 most important features to keep logs manageable.
        try:
            top_features = ["gap_from_prev_close", "intraday_return", "scalp_orb_distance",
                            "time_bucket", "volume_ratio", "rsi_14", "bb_position",
                            "atr_pct", "vwap_distance", "momentum_5"]
            drift_vals = {k: float(latest_features.get(k, float("nan")))
                          for k in top_features if k in latest_features}
            if drift_vals:
                logger.info(f"  DRIFT CHECK: {drift_vals}")
        except Exception:
            pass  # Non-fatal

        # Record prediction for health monitoring (regardless of trade outcome)
        try:
            self._record_prediction(predicted_return, underlying_price)
        except Exception:
            pass  # Non-fatal

        # Step 5.5: VIX regime confidence adjustment (Phase C)
        # Scale prediction magnitude based on current volatility regime.
        # SKIP for scalp: high VIX = bigger intraday moves = MORE opportunity
        # for 0DTE options, not less. The 0.7x high-vol penalty was killing
        # signals (e.g., 0.14 confidence → 0.098 → below 0.10 threshold).
        try:
            from config import VIX_REGIME_ENABLED
            if VIX_REGIME_ENABLED and not self._is_scalp:
                from ml.regime_adjuster import adjust_prediction_confidence
                from config import (
                    VIX_REGIME_LOW_THRESHOLD, VIX_REGIME_HIGH_THRESHOLD,
                    VIX_REGIME_LOW_MULTIPLIER, VIX_REGIME_NORMAL_MULTIPLIER,
                    VIX_REGIME_HIGH_MULTIPLIER,
                )
                vixy_price = self._vix_provider.get_current_vix()
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
        # Classifier models (scalp, swing classifier, lgbm classifier) use min_confidence.
        # Regression models (swing/general xgboost/lightgbm) use min_predicted_move_pct.
        _model_type = getattr(self, '_cached_model_type', None) or self._detect_model_type()
        _is_classifier = _model_type in ("xgb_classifier", "xgb_swing_classifier", "lgbm_classifier")

        if _is_classifier:
            min_confidence = self.config.get("min_confidence", 0.10)
            confidence = abs(predicted_return)  # Classifier returns signed confidence
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
                if self._is_scalp:
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
            quantity = max(1, int(position_budget / underlying_price))
            if position_budget < underlying_price:
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

                active_model_type = getattr(self, "_cached_model_type", None) or type(self.predictor).__name__.lower().replace("predictor", "")

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
                    step_stopped_at=None,  # None = all steps passed, trade entered
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
        #
        # SKIP for classifier models: classifiers output directional confidence (0-1),
        # not predicted return magnitudes. Converting confidence * avg_move gives tiny
        # numbers (e.g., 0.01%) that can NEVER exceed the ATM straddle implied move
        # (e.g., 0.35%). This gate is only meaningful for regression models that
        # predict actual return percentages.
        if _is_classifier:
            logger.info(
                "  ENTRY STEP 8.5 SKIP (N/A): Implied move gate not applicable "
                "for classifier models — confidence is directional, not magnitude-based"
            )
        elif self.config.get("implied_move_gate_enabled", True):
            from ml.ev_filter import get_implied_move_pct
            implied_move = get_implied_move_pct(
                strategy=self,
                symbol=self.symbol,
                underlying_price=underlying_price,
                target_dte_min=min_dte,
                target_dte_max=max_dte,
            )
            if implied_move is not None:
                # For classifier models, convert confidence to estimated return
                if _is_classifier:
                    _confidence = abs(predicted_return)
                    _avg_move = self._get_classifier_avg_move()
                    abs_predicted = _confidence * _avg_move
                else:
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
                        step_stopped_at=8.5,
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
        # For classifier models, convert signed confidence to an estimated return for EV calculation.
        # Classifiers return signed confidence (e.g., +0.72 = 72% confident UP).
        # EV filter expects predicted_return_pct (e.g., +0.15 = predicted +0.15% move).
        #
        # Use avg_move as the predicted return — NOT confidence * avg_move.
        # Confidence already gates at step 6 (low-confidence signals filtered out).
        # Once past that gate, the expected move magnitude is the full avg_move.
        # The old formula (confidence * avg_move) produced numbers like 0.01% which
        # are too small for the EV formula to ever produce positive results with
        # real option premiums.
        if _is_classifier:
            confidence = abs(predicted_return)
            direction_sign = 1.0 if predicted_return > 0 else -1.0
            avg_move = self._get_classifier_avg_move()
            ev_predicted_return = avg_move * direction_sign
            logger.info(
                f"  ENTRY STEP 9: Classifier EV input: avg_move={avg_move:.4f}% x "
                f"sign={direction_sign:+.0f} = {ev_predicted_return:+.4f}% "
                f"(confidence={confidence:.3f} already gated at step 6)"
            )
        else:
            ev_predicted_return = predicted_return

        # Gate Theta data fetch with circuit breaker (L3 fix)
        if not self._theta_circuit_breaker.can_execute():
            logger.warning(
                f"  ENTRY STEP 9 SKIP: Theta circuit breaker OPEN — "
                f"failures={self._theta_circuit_breaker._failure_count}"
            )
            self._write_signal_log(
                underlying_price=underlying_price,
                predicted_return=predicted_return,
                step_stopped_at=9,
                stop_reason="Theta circuit breaker open",
            )
            return

        try:
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
                min_premium=self.config.get("min_premium", 0.0),
                max_premium=self.config.get("max_premium", 0.0),
                prefer_atm=self.config.get("prefer_atm", False),
                moneyness_range_pct=self.config.get("moneyness_range_pct", 5.0),
            )
            self._theta_circuit_breaker.record_success()
        except Exception as e:
            self._theta_circuit_breaker.record_failure()
            logger.error(f"  ENTRY STEP 9 ERROR: EV scan failed: {e}", exc_info=True)
            self._write_signal_log(
                underlying_price=underlying_price,
                predicted_return=predicted_return,
                step_stopped_at=9,
                stop_reason=f"EV scan error: {str(e)[:200]}",
            )
            return

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

        # Confidence-weighted sizing for classifier models:
        # Scale quantity based on confidence level. Low confidence (near threshold)
        # gets fewer contracts; high confidence gets the full allocation.
        # This ensures we bet more when the model is more sure.
        if _is_classifier and quantity > 1:
            conf = abs(predicted_return)
            min_conf = self.config.get("min_confidence", 0.10)
            # Scale: at min_confidence → 40% of max quantity, at 0.50+ → 100%
            # Linear interpolation between min_confidence and 0.50
            conf_cap = 0.50
            scale = 0.4 + 0.6 * min((conf - min_conf) / (conf_cap - min_conf), 1.0)
            scaled_qty = max(1, int(quantity * scale))
            if scaled_qty != quantity:
                logger.info(
                    f"  ENTRY STEP 10: Confidence-weighted sizing: "
                    f"conf={conf:.3f} scale={scale:.2f} "
                    f"qty={quantity}→{scaled_qty}"
                )
                quantity = scaled_qty

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
            # Use cached DB model_type (e.g. "xgb_classifier", "xgb_swing_classifier") rather
            # than deriving from class name which produces mismatches ("scalp", "swingclassifier").
            active_model_type = getattr(self, "_cached_model_type", None) or \
                type(self.predictor).__name__.lower().replace("predictor", "")

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
                step_stopped_at=None,  # None = all steps passed, trade entered
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
        """Called when an order fills. Updates DB entry_price with actual fill."""
        logger.info(
            f"ORDER FILLED: {order.side} {quantity}x {position.asset} @ ${price:.2f}"
        )
        # Update entry_price in DB and _open_trades with actual fill price
        if order.side == "buy" and price and price > 0:
            for trade_id, tinfo in self._open_trades.items():
                asset = position.asset
                if (tinfo.get("strike") == getattr(asset, "strike", None)
                        and tinfo.get("right") == getattr(asset, "right", None)
                        and tinfo.get("expiration") == getattr(asset, "expiration", None)
                        and tinfo.get("entry_price") != price):
                    old_price = tinfo["entry_price"]
                    tinfo["entry_price"] = price
                    try:
                        import sqlite3
                        conn = sqlite3.connect(str(DB_PATH), timeout=2)
                        conn.execute(
                            "UPDATE trades SET entry_price = ? WHERE id = ?",
                            (price, trade_id),
                        )
                        conn.commit()
                        conn.close()
                        logger.info(
                            f"  Fill price updated: trade={trade_id[:8]} "
                            f"${old_price:.2f} -> ${price:.2f}"
                        )
                    except Exception as e:
                        logger.warning(f"  Failed to update fill price: {e}")
                    break

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
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "price_at_prediction": float(current_price),
            "actual_direction": None,  # Filled in by _update_prediction_outcomes
        }
        self._prediction_history.append(entry)

        # Trim to window size (keep last MODEL_HEALTH_WINDOW_SIZE entries)
        if len(self._prediction_history) > MODEL_HEALTH_WINDOW_SIZE:
            self._prediction_history = self._prediction_history[-MODEL_HEALTH_WINDOW_SIZE:]

    def _update_prediction_outcomes(self, current_price: float):
        """
        Look back at recent predictions and fill in actual direction
        based on price movement since prediction time.

        Called at the start of each iteration. We compare current_price
        against price_at_prediction. A prediction is 'resolved' only after
        enough time has elapsed (PREDICTION_RESOLVE_MINUTES) to allow the
        predicted move to materialize.
        """
        import datetime as dt

        resolve_minutes = (
            PREDICTION_RESOLVE_MINUTES_SCALP if self._is_scalp
            else PREDICTION_RESOLVE_MINUTES_SWING
        )
        now_utc = dt.datetime.now(dt.timezone.utc)

        for entry in self._prediction_history:
            if entry["actual_direction"] is not None:
                continue  # Already resolved

            # Only resolve predictions that are old enough
            try:
                pred_time = dt.datetime.fromisoformat(entry["timestamp"])
                if pred_time.tzinfo is None:
                    pred_time = pred_time.replace(tzinfo=dt.timezone.utc)
                age_minutes = (now_utc - pred_time).total_seconds() / 60.0
                if age_minutes < resolve_minutes:
                    continue  # Too young — wait for prediction horizon
            except (KeyError, ValueError):
                continue  # Malformed timestamp — skip

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
        import datetime as dt

        now = time.time()
        if now - self._last_health_persist_time < 60:
            return
        self._last_health_persist_time = now

        stats = self._compute_rolling_accuracy()
        stats["profile_id"] = self.profile_id
        stats["profile_name"] = getattr(self, "profile_name", "unknown")
        stats["model_type"] = getattr(self, "_cached_model_type", None) or \
            (type(self.predictor).__name__ if self.predictor else "none")
        stats["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

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