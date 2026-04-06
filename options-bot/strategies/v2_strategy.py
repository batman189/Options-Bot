"""V2 Strategy — orchestrates all V2 modules inside Lumibot's trading loop.
Replaces the V1 12-step pipeline with: context → scanner → scorer → profile →
selector → sizer → order. Each step is a labeled comment."""

import logging
import time
from datetime import datetime, timezone

from lumibot.strategies import Strategy
from lumibot.entities import Asset

logger = logging.getLogger("options-bot.strategy.v2")


class V2Strategy(Strategy):
    """Lumibot strategy that delegates all decisions to V2 modules."""

    parameters = {
        "symbol": "SPY",
        "profile_name": "momentum",
        "config": {},
    }

    def send_update_to_cloud(self):
        pass  # No LumiWealth/BotSpot

    def initialize(self):
        """Set up all V2 modules with dependency injection."""
        self.symbol = self.parameters.get("symbol", "SPY")
        self.profile_name = self.parameters.get("profile_name", "momentum")
        self._config = self.parameters.get("config", {})
        self._stock_asset = Asset(self.symbol, asset_type="stock")
        self._consecutive_errors = 0
        self._day_start_value = 0.0
        self._starting_balance = 0.0
        self._trade_id_map = {}  # Lumibot order -> trade_id mapping

        # ── Step 0: Health check (blocking — halts if connections fail) ──
        from data.unified_client import UnifiedDataClient
        from data.data_validation import DataNotReadyError
        self._client = UnifiedDataClient()
        for attempt in range(30):  # Retry up to 30 minutes for pre-market IV=0
            try:
                self._client.health_check()
                break
            except DataNotReadyError as e:
                logger.warning(f"V2Strategy: data not ready (attempt {attempt+1}/30): {e}")
                if attempt < 29:
                    time.sleep(60)
                else:
                    raise  # Give up after 30 minutes
        logger.info("V2Strategy: health check passed")

        # ── Instantiate all V2 modules ──
        from market.context import MarketContext
        from scanner.scanner import Scanner
        from scoring.scorer import Scorer
        from profiles.momentum import MomentumProfile
        from profiles.mean_reversion import MeanReversionProfile
        from profiles.catalyst import CatalystProfile
        from selection.selector import OptionsSelector
        from management.trade_manager import TradeManager

        self._context = MarketContext(data_client=self._client)
        self._scanner = Scanner(symbols=[self.symbol], data_client=self._client, context=self._context)
        self._scorer = Scorer()
        self._profiles = {
            "momentum": MomentumProfile(),
            "mean_reversion": MeanReversionProfile(),
            "catalyst": CatalystProfile(),
        }
        # Map scanner setup_type to profile name
        self._setup_to_profile = {
            "momentum": "momentum",
            "mean_reversion": "mean_reversion",
            "catalyst": "catalyst",
            # compression_breakout has no profile yet — will be skipped and logged
        }
        self._selector = OptionsSelector(data_client=self._client)
        self._trade_manager = TradeManager(data_client=self._client)
        self.sleeptime = self._config.get("sleeptime", "1M")

        logger.info(f"V2Strategy initialized: profiles={list(self._profiles.keys())} symbol={self.symbol}")

    def on_trading_iteration(self):
        """Main loop — calls V2 modules in sequence."""
        iteration_start = time.time()
        logger.info(f"--- V2 {self.profile_name}/{self.symbol} at {self.get_datetime()} ---")

        # Record portfolio values for sizer survival rules
        pv = self.get_portfolio_value() or 0.0
        if self._starting_balance == 0.0 and pv > 0:
            self._starting_balance = pv
        if self._day_start_value == 0.0 and pv > 0:
            self._day_start_value = pv

        # ── Step 9: Trade manager — monitor open positions (ALWAYS runs) ──
        try:
            def _get_price(sym):
                return self.get_last_price(Asset(sym, asset_type="stock"))

            def _get_score(sym, prof):
                results = self._scanner.scan()
                for r in results:
                    if r.symbol == sym:
                        for s in r.setups:
                            if s.setup_type == prof:
                                return s.score
                return None

            cycle_logs = self._trade_manager.run_cycle(_get_price, _get_score)

            # ── Step 10: Submit exit orders for pending exits ──
            for trade_id, pos in self._trade_manager.get_pending_exits():
                self._submit_exit_order(trade_id, pos)
        except Exception as e:
            logger.error(f"V2 Step 9-10 (trade mgmt) error: {e}", exc_info=True)

        # ── Steps 1-8: Entry evaluation (skip on error, never halt) ──
        try:
            # ── Step 1: Market context ──
            snapshot = self._context.update(force=False)
            logger.info(f"  Step 1: regime={snapshot.regime.value} tod={snapshot.time_of_day.value}")

            # ── Step 2: Scanner ──
            scan_results = self._scanner.scan(force=True)
            active = [(r, s) for r in scan_results for s in r.setups if s.score > 0]
            logger.info(f"  Step 2: {len(active)} active setups from {len(scan_results)} symbols")

            if not active:
                logger.info("  No active setups — skipping entry evaluation")
                self._log_no_setup(snapshot)
                return

            # Evaluate each active setup — match setup_type to correct profile
            for scan_result, setup in active:
                # Match setup to profile
                profile_name = self._setup_to_profile.get(setup.setup_type)
                if profile_name is None:
                    logger.info(f"  setup_type={setup.setup_type} has no registered profile — skipping (not an error)")
                    continue
                profile = self._profiles[profile_name]

                # ── Step 3: Score ──
                from scanner.sentiment import get_sentiment
                sentiment = get_sentiment(scan_result.symbol)
                scored = self._scorer.score(
                    scan_result.symbol, setup, snapshot,
                    sentiment_score=sentiment.score,
                )
                logger.info(f"  Step 3: {scan_result.symbol} {setup.setup_type} "
                            f"score={scored.capped_score:.3f} [{scored.threshold_label}]")

                # ── Step 4: Profile decision ──
                decision = profile.should_enter(scored, snapshot.regime)
                logger.info(f"  Step 4: enter={decision.enter} | {decision.reason}")

                # ── Step 5: Log signal (always, regardless of entry) ──
                self._log_v2_signal(scored, decision, snapshot, profile_name)

                if not decision.enter:
                    continue

                # ── Step 6: Select contract ──
                contract = self._selector.select(
                    symbol=scan_result.symbol,
                    direction=decision.direction,
                    confidence=scored.capped_score,
                    hold_minutes=profile.max_hold_minutes,
                    profile_name=profile_name,
                    predicted_move_pct=setup.score * 2,  # Rough move estimate from setup score
                )
                if contract is None:
                    logger.info("  Step 6: no qualifying contract")
                    continue
                logger.info(f"  Step 6: {contract.right} ${contract.strike} "
                            f"exp={contract.expiration} EV={contract.ev_pct:.1f}%")

                # ── Step 7: Size position ──
                from sizing.sizer import calculate as size_calculate
                from risk.risk_manager import RiskManager
                rm = RiskManager()
                exposure = rm.check_portfolio_exposure(pv)
                day_trades = rm.get_day_trade_count(pv)
                is_same_day = contract.expiration == str(datetime.now(timezone.utc).date())

                sizing = size_calculate(
                    account_value=pv, confidence=scored.capped_score,
                    premium=contract.mid, day_start_value=self._day_start_value,
                    starting_balance=self._starting_balance,
                    current_exposure=exposure.get("exposure_dollars", 0),
                    is_same_day_trade=is_same_day,
                    day_trades_remaining=max(0, 3 - day_trades),
                )
                if sizing.blocked or sizing.contracts == 0:
                    logger.info(f"  Step 7: blocked — {sizing.block_reason}")
                    continue
                logger.info(f"  Step 7: {sizing.contracts} contracts")

                # ── Step 8: Submit entry order ──
                self._submit_entry_order(contract, sizing.contracts, scored, setup, profile)

        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"V2 Steps 1-8 error ({self._consecutive_errors}): {e}", exc_info=True)
        else:
            self._consecutive_errors = 0

        elapsed = time.time() - iteration_start
        if elapsed > 10:
            logger.info(f"  Iteration: {elapsed:.1f}s")

    def on_filled_order(self, position, order, price, quantity, multiplier):
        """Handle fill — delegate to trade manager for exits, record entries."""
        logger.info(f"ORDER FILLED: {order.side} {quantity}x {position.asset} @ ${price:.2f}")

        trade_id = self._trade_id_map.pop(id(order), None)
        if trade_id and order.side in ("sell", "sell_to_close"):
            self._trade_manager.confirm_fill(trade_id, price)

    def _submit_entry_order(self, contract, quantity, scored, setup, profile):
        """Submit a buy order and register with trade manager."""
        import uuid
        asset = Asset(
            symbol=contract.symbol, asset_type="option",
            expiration=datetime.strptime(contract.expiration, "%Y-%m-%d").date(),
            strike=contract.strike, right=contract.right,
        )
        trade_id = str(uuid.uuid4())
        try:
            order = self.create_order(asset, quantity, side="buy_to_open")
            self._trade_id_map[id(order)] = trade_id
            self.submit_order(order)
            logger.info(f"  Step 8: ORDER {trade_id[:8]} buy {quantity}x "
                        f"{contract.right} ${contract.strike}")

            self._trade_manager.add_position(
                trade_id=trade_id, symbol=contract.symbol,
                direction="bullish" if contract.right == "CALL" else "bearish",
                profile=profile,
                expiration=datetime.strptime(contract.expiration, "%Y-%m-%d").date(),
                entry_time=datetime.now(timezone.utc),
                entry_price=contract.mid, quantity=quantity,
                confidence=scored.capped_score, setup_score=setup.score,
                setup_type=setup.setup_type,
            )
        except Exception as e:
            logger.error(f"  Step 8 FAILED: {e}", exc_info=True)

    def _submit_exit_order(self, trade_id, pos):
        """Submit a sell order for a pending exit."""
        try:
            asset = Asset(
                symbol=pos.symbol, asset_type="option",
                expiration=pos.expiration, strike=0, right="CALL",
            )
            # Find the actual position from broker
            for broker_pos in self.get_positions():
                if (broker_pos.asset.symbol == pos.symbol and
                        hasattr(broker_pos.asset, "expiration") and
                        broker_pos.asset.expiration == pos.expiration):
                    order = self.create_order(broker_pos.asset, broker_pos.quantity, side="sell_to_close")
                    self._trade_id_map[id(order)] = trade_id
                    self.submit_order(order)
                    logger.info(f"  Step 10: EXIT {trade_id[:8]} {pos.symbol} reason={pos.pending_exit_reason}")
                    return
            logger.warning(f"  Step 10: no broker position found for {trade_id[:8]}")
        except Exception as e:
            logger.error(f"  Step 10 EXIT FAILED for {trade_id[:8]}: {e}", exc_info=True)

    def _log_v2_signal(self, scored, decision, snapshot, profile_name: str = ""):
        """Write V2 signal log entry for every evaluation."""
        from backend.database import write_v2_signal_log
        factors = {f.name: f.raw_value for f in scored.factors if f.status == "active"}
        write_v2_signal_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profile_name": profile_name or scored.setup_type,
            "symbol": scored.symbol,
            "setup_type": scored.setup_type,
            "setup_score": next((f.raw_value for f in scored.factors if f.name == "signal_clarity"), None),
            "confidence_score": scored.capped_score,
            "raw_score": scored.raw_score,
            "regime": snapshot.regime.value,
            "regime_reason": snapshot.regime_reason,
            "time_of_day": snapshot.time_of_day.value,
            "signal_clarity": factors.get("signal_clarity"),
            "regime_fit": factors.get("regime_fit"),
            "ivr": factors.get("ivr"),
            "institutional_flow": factors.get("institutional_flow"),
            "historical_perf": factors.get("historical_perf"),
            "sentiment": factors.get("sentiment"),
            "time_of_day_score": factors.get("time_of_day"),
            "threshold_label": scored.threshold_label,
            "entered": decision.enter,
            "trade_id": None,  # Set after order fills
            "block_reason": decision.reason if not decision.enter else None,
        })

    def _log_no_setup(self, snapshot):
        """Log a single entry when the scanner finds no active setups.
        Ensures every iteration is visible in signal logs for review."""
        from backend.database import write_v2_signal_log
        write_v2_signal_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profile_name": "scanner",
            "symbol": self.symbol,
            "setup_type": None,
            "setup_score": None,
            "confidence_score": None,
            "raw_score": None,
            "regime": snapshot.regime.value,
            "regime_reason": snapshot.regime_reason,
            "time_of_day": snapshot.time_of_day.value,
            "signal_clarity": None,
            "regime_fit": None,
            "ivr": None,
            "institutional_flow": None,
            "historical_perf": None,
            "sentiment": None,
            "time_of_day_score": None,
            "threshold_label": None,
            "entered": False,
            "trade_id": None,
            "block_reason": "scanner: no active setups",
        })
