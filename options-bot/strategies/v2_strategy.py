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
        self._last_regime = None  # For change detection
        self._last_context_write = 0.0  # Epoch time of last DB write
        self._pdt_locked = False       # True when ALL entries blocked
        self._pdt_day_trades = 0       # Cached Alpaca daytrade_count
        self._pdt_buying_power = 999999  # Alpaca daytrading_buying_power
        self._pdt_no_same_day_exit = set()  # trade_ids committed to hold overnight
        self._last_entry_time = {}   # profile_name -> datetime of last entry
        self._max_positions = self._config.get("max_concurrent_positions", 3)
        self._cooldown_minutes = self._config.get("entry_cooldown_minutes", 30)
        self._paused_profiles = set()  # profile names paused by learning layer

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
        from profiles.scalp_0dte import Scalp0DTEProfile
        from profiles.swing import SwingProfile
        from profiles.tsla_swing import TSLASwingProfile
        from selection.selector import OptionsSelector
        from management.trade_manager import TradeManager

        self._context = MarketContext(data_client=self._client)
        # Always scan primary symbol. If SPY, also scan QQQ.
        scan_symbols = [self.symbol]
        if self.symbol == "SPY":
            scan_symbols = ["SPY", "QQQ"]
        self._scanner = Scanner(symbols=scan_symbols, data_client=self._client, context=self._context)
        self._scorer = Scorer()

        # Build all available profiles
        all_profiles = {
            "momentum": MomentumProfile(),
            "mean_reversion": MeanReversionProfile(),
            "catalyst": CatalystProfile(),
            "scalp_0dte": Scalp0DTEProfile(),
            "swing": SwingProfile(),
            "tsla_swing": TSLASwingProfile(),
        }

        # Filter to profiles allowed by this preset
        preset = self._config.get("preset", "") or self.parameters.get("preset", "")
        PRESET_PROFILE_MAP = {
            "0dte_scalp":     {"scalp_0dte", "momentum", "mean_reversion", "catalyst"},
            "scalp":          {"scalp_0dte", "momentum", "mean_reversion", "catalyst"},
            "swing":          {"swing", "momentum"},
            "momentum":       {"momentum"},
            "mean_reversion": {"mean_reversion"},
            "catalyst":       {"catalyst"},
        }
        if preset in PRESET_PROFILE_MAP:
            allowed = PRESET_PROFILE_MAP[preset]
        elif self.symbol == "SPY":
            allowed = {"momentum", "mean_reversion", "catalyst", "scalp_0dte", "swing"}
        elif self.symbol in ("TSLA", "NVDA", "AAPL", "AMZN", "META", "MSFT"):
            allowed = {"momentum", "mean_reversion", "catalyst", "tsla_swing"}
        else:
            allowed = {"momentum", "mean_reversion", "catalyst", "swing"}

        # For swing preset on volatile single stocks, also activate tsla_swing
        if preset == "swing" and self.symbol in ("TSLA", "NVDA", "AAPL", "AMZN", "META", "MSFT"):
            allowed = allowed | {"tsla_swing"}
            logger.info(f"V2Strategy: {self.symbol} swing — adding tsla_swing profile")

        self._profiles = {k: v for k, v in all_profiles.items() if k in allowed}
        logger.info(f"V2Strategy: preset={preset} active profiles={list(self._profiles.keys())}")

        # Apply DB profile config to all internal profiles
        for pname, profile in self._profiles.items():
            profile.apply_config(self._config)

        # Apply learning layer adjustments to profile thresholds
        try:
            from learning.storage import load_learning_state
            for pname, profile in self._profiles.items():
                state = load_learning_state(pname)
                if state is not None:
                    if state.paused_by_learning:
                        self._paused_profiles.add(pname)
                        logger.warning(f"V2Strategy: {pname} is PAUSED by learning layer — skipping entries")
                    else:
                        profile.min_confidence = state.min_confidence
                        logger.info(f"V2Strategy: {pname} threshold set to {state.min_confidence:.3f} (from learning state)")
                        if state.regime_fit_overrides:
                            self._scorer.set_regime_overrides(state.regime_fit_overrides)
                            logger.info(f"V2Strategy: {pname} regime_fit overrides applied: {state.regime_fit_overrides}")
                        if hasattr(state, 'tod_fit_overrides') and state.tod_fit_overrides:
                            self._scorer.set_tod_overrides(state.tod_fit_overrides)
                            logger.info(f"V2Strategy: {pname} tod_fit overrides applied: {state.tod_fit_overrides}")
                else:
                    logger.info(f"V2Strategy: {pname} using default threshold {profile.min_confidence:.3f} (no learning state yet)")
        except Exception as e:
            logger.warning(f"V2Strategy: failed to apply learning state (non-fatal): {e}")

        self._selector = OptionsSelector(data_client=self._client)
        self._trade_manager = TradeManager(data_client=self._client)
        from risk.risk_manager import RiskManager
        self._risk_manager = RiskManager()
        from alpaca.trading.client import TradingClient as AlpacaTradingClient
        from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER
        self._alpaca_client = AlpacaTradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)
        self.sleeptime = self._config.get("sleeptime", "1M")

        # ── Reload open trades from DB into trade manager ──
        self._reload_open_positions()

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

        # ── PDT status check (once per iteration, cached) ──
        try:
            _acct = self._alpaca_client.get_account()
            self._pdt_day_trades = int(_acct.daytrade_count)
            self._pdt_buying_power = float(_acct.daytrading_buying_power)

            # Three lock levels:
            # 1. daytrading_buying_power == 0: Alpaca blocks all same-day sells
            # 2. daytrade_count >= 3: no day trade slots left
            # 3. daytrade_count >= 2: one slot left, reserve for emergency exit
            if pv < 25000:
                # Only check buying_power when day trades have been used —
                # fresh Alpaca paper accounts report buying_power=0 with 0 day trades
                bp_problem = self._pdt_buying_power <= 0 and self._pdt_day_trades > 0
                if bp_problem or self._pdt_day_trades >= 3:
                    self._pdt_locked = True
                else:
                    self._pdt_locked = False

                if self._pdt_locked:
                    logger.info(f"  PDT: LOCKED — day_trades={self._pdt_day_trades}, "
                                f"buying_power=${self._pdt_buying_power:.0f}, equity=${pv:.0f}")
                elif self._pdt_day_trades >= 2:
                    logger.info("  PDT: CAUTION — 1 day trade remaining, "
                                "0DTE blocked, multi-day hold-only")
            else:
                self._pdt_locked = False
        except Exception:
            pass  # Keep previous state

        # ── Step 9: Trade manager — monitor open positions (ALWAYS runs) ──
        try:
            def _get_price(pos):
                """Get current option price for a managed position."""
                try:
                    if pos.strike and pos.right and pos.expiration:
                        right_str = "call" if pos.right in ("CALL", "bullish") else "put"
                        option_asset = Asset(
                            pos.symbol, asset_type="option",
                            expiration=pos.expiration,
                            strike=pos.strike,
                            right=right_str,
                        )
                        price = self.get_last_price(option_asset)
                        if price and price > 0:
                            return price
                except Exception:
                    pass
                return None

            # Cache scan results for _get_score — avoid re-scanning per position
            _cached_scan = self._scanner.scan()

            def _get_score(sym, prof):
                for r in _cached_scan:
                    if r.symbol == sym:
                        for s in r.setups:
                            if s.setup_type == prof:
                                return s.score
                return None

            self._trade_manager.run_cycle(_get_price, _get_score)

            # ── Step 10: Submit exit orders for pending exits ──
            for trade_id, pos in self._trade_manager.get_pending_exits():
                is_same_day_position = pos.entry_time.date() == datetime.now(timezone.utc).date()

                # Block 1: PDT-committed overnight trades cannot exit same day
                if trade_id in self._pdt_no_same_day_exit and is_same_day_position:
                    logger.info(f"  Step 10: HOLD {trade_id[:8]} {pos.symbol} — PDT overnight commitment")
                    pos.pending_exit = False
                    pos.pending_exit_reason = ""
                    continue

                # Block 2: PDT locked + same day entry = selling would be a day trade
                if self._pdt_locked and is_same_day_position:
                    logger.info(f"  Step 10: HOLD {trade_id[:8]} {pos.symbol} — PDT locked, same-day exit blocked")
                    pos.pending_exit = False  # Cancel the exit, try again tomorrow
                    pos.pending_exit_reason = ""
                    continue

                # Block 3: Exit order already pending — don't submit duplicate
                if pos.pending_exit_order_id and pos.pending_exit_order_id in self._trade_id_map:
                    logger.info(f"  Step 10: exit order already pending for {trade_id[:8]}")
                    continue

                self._submit_exit_order(trade_id, pos)
        except Exception as e:
            logger.error(f"V2 Step 9-10 (trade mgmt) error: {e}", exc_info=True)

        # ── Steps 1-8: Entry evaluation (skip on error, never halt) ──
        try:
            # ── Step 1: Market context ──
            snapshot = self._context.update(force=True)
            logger.info(f"  Step 1: regime={snapshot.regime.value} tod={snapshot.time_of_day.value}")

            # Persist regime to DB (throttled: on change or every 5 min)
            self._persist_context_snapshot(snapshot)

            # ── Step 2: Scanner ──
            scan_results = self._scanner.scan(force=True)
            active = [(r, s) for r in scan_results for s in r.setups if s.score > 0]
            logger.info(f"  Step 2: {len(active)} active setups from {len(scan_results)} symbols")

            # Persist scanner results to DB
            self._persist_scanner_snapshot(scan_results, snapshot)

            if not active:
                # Log the best rejected setup per symbol so the UI shows WHY nothing qualified
                self._log_scanner_rejection(scan_results, snapshot)
                return

            # Evaluate each active setup — match setup_type to correct profile
            for scan_result, setup in active:
                # Score once per setup
                from scanner.sentiment import get_sentiment
                sentiment = get_sentiment(scan_result.symbol)
                scored = self._scorer.score(
                    scan_result.symbol, setup, snapshot,
                    sentiment_score=sentiment.score,
                )
                logger.info(f"  Step 3: {scan_result.symbol} {setup.setup_type} "
                            f"score={scored.capped_score:.3f} [{scored.threshold_label}]")

                # Evaluate against ALL profiles — each decides independently
                for profile_name, profile in self._profiles.items():
                    if profile_name in self._paused_profiles:
                        continue

                    # ── Step 4: Profile decision ──
                    decision = profile.should_enter(scored, snapshot.regime)
                    logger.info(f"  Step 4 [{profile_name}]: enter={decision.enter} | {decision.reason}")

                    # ── Step 5: Log rejected signals immediately ──
                    if not decision.enter:
                        self._log_v2_signal(scored, decision, snapshot, profile_name)
                        continue

                    # ── Step 5b: Entry cooldown — shorter in strong trend ──
                    if profile_name in self._last_entry_time:
                        from market.context import Regime as _Regime
                        elapsed_since_last = (
                            datetime.now(timezone.utc) - self._last_entry_time[profile_name]
                        ).total_seconds() / 60

                        if snapshot.regime in (_Regime.TRENDING_UP, _Regime.TRENDING_DOWN):
                            effective_cooldown = 5.0
                        else:
                            effective_cooldown = self._cooldown_minutes

                        if elapsed_since_last < effective_cooldown:
                            remaining = effective_cooldown - elapsed_since_last
                            logger.info(
                                f"  Step 5b: cooldown {elapsed_since_last:.0f}min < "
                                f"{effective_cooldown:.0f}min ({snapshot.regime.value}) — "
                                f"{remaining:.0f}min remaining"
                            )
                            decision.enter = False
                            decision.reason = f"cooldown {remaining:.0f}min remaining"
                            self._log_v2_signal(scored, decision, snapshot, profile_name)
                            continue

                    # ── Step 5c: Max concurrent positions ──
                    import sqlite3 as _sql
                    from pathlib import Path as _Path
                    try:
                        _db = _sql.connect(str(_Path(__file__).parent.parent / "db" / "options_bot.db"))
                        open_count = _db.execute(
                            "SELECT COUNT(*) FROM trades WHERE status = 'open'"
                        ).fetchone()[0]
                        _db.close()
                        if open_count >= self._max_positions:
                            logger.info(f"  Step 5c: max positions reached: "
                                        f"{open_count}/{self._max_positions}")
                            decision.enter = False
                            decision.reason = f"max positions {open_count}/{self._max_positions}"
                            self._log_v2_signal(scored, decision, snapshot, profile_name)
                            continue
                    except Exception:
                        pass  # Don't block on DB error

                    # ── Step 6: Select contract ──
                    use_otm = bool(self._config.get("use_otm_strikes", False))
                    contract = self._selector.select(
                        symbol=scan_result.symbol,
                        direction=decision.direction,
                        confidence=scored.capped_score,
                        hold_minutes=profile.max_hold_minutes,
                        profile_name=profile_name,
                        predicted_move_pct=setup.score * 2,
                        use_otm=use_otm,
                    )
                    if contract is None:
                        logger.info(f"  Step 6 [{profile_name}]: no qualifying contract")
                        continue
                    logger.info(f"  Step 6 [{profile_name}]: {contract.right} ${contract.strike} "
                                f"exp={contract.expiration} EV={contract.ev_pct:.1f}%")

                    # ── Step 7: Size position + PDT gate ──
                    is_same_day = contract.expiration == str(datetime.now(timezone.utc).date())

                    # PDT gate: three levels of restriction (accounts < $25K)
                    if pv < 25000:
                        if self._pdt_locked:
                            logger.info(f"  Step 7: BLOCKED — PDT fully locked "
                                        f"(day_trades={self._pdt_day_trades}, "
                                        f"bp=${self._pdt_buying_power:.0f})")
                            continue
                        elif self._pdt_day_trades >= 2 and is_same_day:
                            logger.info("  Step 7: BLOCKED — 1 day trade left + 0DTE, "
                                        "would be trapped")
                            continue
                        elif self._pdt_day_trades >= 2:
                            logger.info("  Step 7: PDT hold-overnight mode "
                                        "(1 day trade remaining, will not exit same day)")

                    from sizing.sizer import calculate as size_calculate
                    exposure = self._risk_manager.check_portfolio_exposure(pv)

                    sizing = size_calculate(
                        account_value=pv, confidence=scored.capped_score,
                        premium=contract.mid, day_start_value=self._day_start_value,
                        starting_balance=self._starting_balance,
                        current_exposure=exposure.get("exposure_dollars", 0),
                        is_same_day_trade=is_same_day,
                        day_trades_remaining=max(0, 3 - self._pdt_day_trades),
                        growth_mode_config=bool(self._config.get("growth_mode", True)),
                    )
                    if sizing.blocked or sizing.contracts == 0:
                        logger.info(f"  Step 7: blocked — {sizing.block_reason}")
                        continue
                    logger.info(f"  Step 7: {sizing.contracts} contracts")

                    # ── Step 8: Submit entry order ──
                    self._submit_entry_order(contract, sizing.contracts, scored, setup, profile, snapshot)

                    # Log signal as entered=True only after order is submitted
                    self._log_v2_signal(scored, decision, snapshot, profile_name)

        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"V2 Steps 1-8 error ({self._consecutive_errors}): {e}", exc_info=True)
        else:
            self._consecutive_errors = 0

        elapsed = time.time() - iteration_start
        if elapsed > 10:
            logger.info(f"  Iteration: {elapsed:.1f}s")

    def on_filled_order(self, position, order, price, quantity, multiplier):
        """Handle fill — INSERT to DB on buy fill, delegate to trade manager on sell fill."""
        logger.info(f"ORDER FILLED: {order.side} {quantity}x {position.asset} @ ${price:.2f}")

        entry = self._trade_id_map.pop(id(order), None)
        if not entry:
            return

        if order.side in ("buy", "buy_to_open"):
            # entry is a dict with full trade metadata
            if not isinstance(entry, dict):
                logger.error(f"  BUY FILL: unexpected entry type {type(entry)}")
                return
            trade_id = entry["trade_id"]
            now_utc = datetime.now(timezone.utc).isoformat()

            # INSERT into trades table — only on confirmed fill
            try:
                import sqlite3
                from pathlib import Path
                db_path = Path(__file__).parent.parent / "db" / "options_bot.db"
                conn = sqlite3.connect(str(db_path))
                conn.execute(
                    """INSERT INTO trades (
                           id, profile_id, symbol, direction, strike, expiration,
                           quantity, entry_price, entry_date, setup_type,
                           confidence_score, market_regime, market_vix,
                           was_day_trade, status, created_at, updated_at
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        trade_id,
                        entry["profile_id"],
                        entry["symbol"],
                        entry["direction"],
                        entry["strike"],
                        entry["expiration"],
                        entry["quantity"],
                        price,  # Actual fill price, not estimated mid
                        now_utc,
                        entry["setup_type"],
                        entry["confidence_score"],
                        entry["regime"],
                        entry["vix_level"],
                        1 if entry["is_same_day"] else 0,
                        "open",
                        now_utc,
                        now_utc,
                    ),
                )
                conn.commit()
                # Link trade_id back to the signal log that triggered it
                try:
                    conn.execute(
                        """UPDATE v2_signal_logs SET trade_id = ?
                           WHERE entered = 1 AND trade_id IS NULL
                             AND symbol = ? AND setup_type = ?
                           ORDER BY id DESC LIMIT 1""",
                        (trade_id, entry["symbol"], entry["setup_type"]),
                    )
                    conn.commit()
                except Exception:
                    pass  # Non-fatal
                conn.close()
                logger.info(f"  BUY FILL: {trade_id[:8]} ${price:.2f} persisted to DB")
            except Exception as e:
                logger.error(f"  BUY FILL DB INSERT failed for {trade_id[:8]}: {e}")

            # Register with trade manager for exit monitoring
            self._trade_manager.add_position(
                trade_id=trade_id, symbol=entry["symbol"],
                direction="bullish" if entry["direction"] == "CALL" else "bearish",
                profile=entry["profile"],
                expiration=datetime.strptime(entry["expiration"], "%Y-%m-%d").date(),
                entry_time=datetime.now(timezone.utc),
                entry_price=price, quantity=entry["quantity"],
                confidence=entry["confidence_score"], setup_score=entry["setup_score"],
                setup_type=entry["setup_type"],
                strike=entry["strike"], right=entry["direction"],
            )

            # If PDT requires hold-overnight, mark this trade
            if self._pdt_day_trades >= 2 and (self.get_portfolio_value() or 0) < 25000:
                self._pdt_no_same_day_exit.add(trade_id)
                logger.info(f"  BUY FILL: {trade_id[:8]} marked PDT hold-overnight")

        elif order.side in ("sell", "sell_to_close"):
            # entry is a trade_id string (set by _submit_exit_order)
            trade_id = entry if isinstance(entry, str) else entry.get("trade_id", "")
            self._trade_manager.confirm_fill(trade_id, price)

            # Update scorer historical performance for this trade type
            try:
                import sqlite3
                from pathlib import Path
                db_path = Path(__file__).parent.parent / "db" / "options_bot.db"
                conn = sqlite3.connect(str(db_path))
                row = conn.execute(
                    "SELECT symbol, setup_type, pnl_pct FROM trades WHERE id = ? AND status = 'closed'",
                    (trade_id,),
                ).fetchone()
                conn.close()
                if row and row[1]:
                    self._scorer.record_trade_outcome(row[0], row[1], row[2] or 0.0)
                    logger.info(f"  Scorer: recorded {row[1]} outcome pnl={row[2]:+.1f}% for {trade_id[:8]}")
            except Exception as e:
                logger.warning(f"  Scorer: failed to record trade outcome (non-fatal): {e}")

    def _submit_entry_order(self, contract, quantity, scored, setup, profile, snapshot):
        """Submit a buy order and store metadata for DB insert on fill confirmation."""
        import uuid
        asset = Asset(
            symbol=contract.symbol, asset_type="option",
            expiration=datetime.strptime(contract.expiration, "%Y-%m-%d").date(),
            strike=contract.strike, right=contract.right,
        )
        trade_id = str(uuid.uuid4())
        try:
            limit_price = round((contract.bid + contract.ask) / 2, 2)
            order = self.create_order(
                asset, quantity, side="buy_to_open",
                limit_price=limit_price, time_in_force="day",
            )
            logger.info(f"  Step 8: limit=${limit_price:.2f} (bid={contract.bid} ask={contract.ask})")
            # Store full trade metadata — DB INSERT happens in on_filled_order()
            self._trade_id_map[id(order)] = {
                "trade_id": trade_id,
                "profile_id": self.parameters.get("profile_id", "unknown"),
                "symbol": contract.symbol,
                "direction": contract.right,
                "strike": contract.strike,
                "expiration": contract.expiration,
                "quantity": quantity,
                "estimated_price": limit_price,
                "setup_type": setup.setup_type,
                "confidence_score": scored.capped_score,
                "regime": snapshot.regime.value,
                "vix_level": getattr(snapshot, "vix_level", None),
                "is_same_day": contract.expiration == str(datetime.now(timezone.utc).date()),
                "profile": profile,
                "profile_name": setup.setup_type,
                "setup_score": setup.score,
            }
            self.submit_order(order)
            # Record cooldown on submission, not on fill — prevents multiple pending orders
            self._last_entry_time[setup.setup_type] = datetime.now(timezone.utc)
            logger.info(f"  Step 8: ORDER {trade_id[:8]} buy {quantity}x "
                        f"{contract.right} ${contract.strike} limit=${limit_price:.2f} "
                        f"(cooldown {self._cooldown_minutes}min started)")
        except Exception as e:
            error_str = str(e).lower()
            if "pattern day trading" in error_str or "40310100" in error_str:
                self._pdt_locked = True
                logger.error("  Step 8: PDT REJECTED — locking all orders until tomorrow")
            else:
                logger.error(f"  Step 8 FAILED: {e}", exc_info=True)

    def _submit_exit_order(self, trade_id, pos):
        """Submit a sell limit order for a pending exit. Sells only this trade's quantity."""
        try:
            # Build the exact option asset from the position's data
            right_str = "put" if pos.right in ("PUT", "bearish") else "call"
            asset = Asset(
                symbol=pos.symbol, asset_type="option",
                expiration=pos.expiration,
                strike=pos.strike,
                right=right_str,
            )

            # Get current option price for limit order
            current_price = self.get_last_price(asset)
            if current_price and current_price > 0:
                limit_price = round(current_price, 2)
            else:
                # Fallback: 50% below entry — prioritize getting out over price
                limit_price = round(pos.entry_price * 0.50, 2)
                logger.warning(f"  Step 10: price unavailable for {trade_id[:8]}, "
                               f"using fallback limit=${limit_price:.2f}")

            order = self.create_order(
                asset, pos.quantity, side="sell_to_close",
                limit_price=limit_price, time_in_force="day",
            )
            self._trade_id_map[id(order)] = trade_id
            pos.pending_exit_order_id = id(order)
            self.submit_order(order)
            logger.info(f"  Step 10: EXIT {trade_id[:8]} {pos.symbol} ${pos.strike} "
                        f"x{pos.quantity} limit=${limit_price:.2f} "
                        f"reason={pos.pending_exit_reason}")
        except Exception as e:
            error_str = str(e).lower()
            if "pattern day trading" in error_str or "40310100" in error_str:
                self._pdt_locked = True
                pos.pending_exit = False
                pos.pending_exit_reason = ""
                pos.exit_retry_count = 0
                logger.error(f"  Step 10: PDT REJECTED exit for {trade_id[:8]} — holding overnight")
            elif "insufficient" in error_str or "available" in error_str:
                pos.pending_exit = False
                pos.pending_exit_reason = ""
                pos.exit_retry_count = 0
                logger.error(f"  Step 10: INSUFFICIENT for {trade_id[:8]} — {str(e)[:100]}")
            else:
                # Transient error — retry up to 5 times
                pos.exit_retry_count = getattr(pos, "exit_retry_count", 0) + 1
                if pos.exit_retry_count >= 5:
                    pos.pending_exit = False
                    pos.pending_exit_reason = ""
                    logger.critical(f"  Step 10: EXIT ABANDONED after 5 retries for "
                                    f"{trade_id[:8]} — MANUAL REVIEW REQUIRED")
                else:
                    logger.error(f"  Step 10 EXIT FAILED for {trade_id[:8]} "
                                 f"(retry {pos.exit_retry_count}/5): {e}")

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

    def _log_scanner_rejection(self, scan_results, snapshot):
        """Log one signal entry per symbol when all setups score 0.
        Shows the best setup's rejection reason so the UI has data to review."""
        from backend.database import write_v2_signal_log
        for result in scan_results:
            # Build block_reason from all setup rejection reasons
            reasons = []
            for s in result.setups:
                if s.reason:
                    reasons.append(f"{s.setup_type}: {s.reason}")
            block_reason = " | ".join(reasons[:4]) if reasons else "all setups scored 0"

            # Score the best setup through the scorer even though it scored 0
            # so we get real factor values for the signal log
            best = max(result.setups, key=lambda s: s.score) if result.setups else None
            if best:
                profile_name = best.setup_type
                try:
                    from scanner.sentiment import get_sentiment
                    sentiment = get_sentiment(result.symbol)
                    scored = self._scorer.score(
                        result.symbol, best, snapshot,
                        sentiment_score=sentiment.score,
                    )
                    factors = {f.name: f.raw_value for f in scored.factors if f.status == "active"}
                    write_v2_signal_log({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "profile_name": profile_name,
                        "symbol": result.symbol,
                        "setup_type": best.setup_type,
                        "setup_score": 0.0,
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
                        "threshold_label": "scanner_reject",
                        "entered": False,
                        "trade_id": None,
                        "block_reason": block_reason,
                    })
                except Exception:
                    # Fallback: write minimal entry without scorer
                    write_v2_signal_log({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "profile_name": "scanner",
                        "symbol": result.symbol,
                        "setup_type": best.setup_type if best else None,
                        "setup_score": 0.0,
                        "confidence_score": None,
                        "raw_score": None,
                        "regime": snapshot.regime.value,
                        "regime_reason": snapshot.regime_reason,
                        "time_of_day": snapshot.time_of_day.value,
                        "signal_clarity": None, "regime_fit": None, "ivr": None,
                        "institutional_flow": None, "historical_perf": None,
                        "sentiment": None, "time_of_day_score": None,
                        "threshold_label": "scanner_reject",
                        "entered": False, "trade_id": None,
                        "block_reason": block_reason,
                    })

    def _persist_context_snapshot(self, snapshot):
        """Write regime to context_snapshots table.
        Throttled: only on regime change or every 5 minutes."""
        import sqlite3
        now = time.time()
        regime_val = snapshot.regime.value
        changed = regime_val != self._last_regime
        stale = (now - self._last_context_write) >= 300  # 5 min

        if not changed and not stale:
            return

        self._last_regime = regime_val
        self._last_context_write = now

        try:
            from pathlib import Path
            db_path = Path(__file__).parent.parent / "db" / "options_bot.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """INSERT INTO context_snapshots (
                       timestamp, symbol, regime, time_of_day,
                       spy_30min_move_pct, spy_60min_range_pct,
                       spy_30min_reversals, spy_volume_ratio,
                       vix_level, vix_intraday_change_pct, regime_reason
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    self.symbol,
                    regime_val,
                    snapshot.time_of_day.value,
                    snapshot.spy_30min_move_pct,
                    snapshot.spy_60min_range_pct,
                    snapshot.spy_30min_reversals,
                    snapshot.spy_volume_ratio,
                    snapshot.vix_level,
                    snapshot.vix_intraday_change_pct,
                    snapshot.regime_reason,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Context snapshot DB write failed (non-fatal): {e}")

    def _persist_scanner_snapshot(self, scan_results, snapshot):
        """Write scanner results to scanner_snapshots table. One row per symbol per cycle."""
        import sqlite3
        try:
            from pathlib import Path
            db_path = Path(__file__).parent.parent / "db" / "options_bot.db"
            conn = sqlite3.connect(str(db_path))
            now_utc = datetime.now(timezone.utc).isoformat()
            for result in scan_results:
                scores = {s.setup_type: s for s in result.setups}
                conn.execute(
                    """INSERT INTO scanner_snapshots (
                           timestamp, symbol, regime, best_setup, best_score,
                           momentum_score, mean_reversion_score,
                           compression_score, catalyst_score, macro_trend_score,
                           momentum_reason, mean_reversion_reason,
                           compression_reason, catalyst_reason, macro_trend_reason
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        now_utc,
                        result.symbol,
                        snapshot.regime.value,
                        result.best_setup or None,
                        result.best_score,
                        scores.get("momentum", None) and scores["momentum"].score,
                        scores.get("mean_reversion", None) and scores["mean_reversion"].score,
                        scores.get("compression_breakout", None) and scores["compression_breakout"].score,
                        scores.get("catalyst", None) and scores["catalyst"].score,
                        scores.get("macro_trend", None) and scores["macro_trend"].score,
                        scores.get("momentum", None) and scores["momentum"].reason[:200],
                        scores.get("mean_reversion", None) and scores["mean_reversion"].reason[:200],
                        scores.get("compression_breakout", None) and scores["compression_breakout"].reason[:200],
                        scores.get("catalyst", None) and scores["catalyst"].reason[:200],
                        scores.get("macro_trend", None) and scores["macro_trend"].reason[:200],
                    ),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Scanner snapshot DB write failed (non-fatal): {e}")

    def _reload_open_positions(self):
        """Reconcile DB against Alpaca, then load open trades into trade manager."""
        import sqlite3
        from pathlib import Path

        # Step 1: Reconcile DB vs Alpaca before loading
        try:
            from scripts.reconcile_positions import run as reconcile
            reconcile(fix=True)
            logger.info("V2Strategy: Alpaca reconciliation complete")
        except Exception as e:
            logger.warning(f"V2Strategy: reconciliation failed (non-fatal): {e}")

        # Step 2: Load remaining open trades into trade manager
        try:
            db_path = Path(__file__).parent.parent / "db" / "options_bot.db"
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT id, symbol, direction, strike, expiration, quantity,
                          entry_price, confidence_score, setup_type, entry_date
                   FROM trades WHERE status = 'open' AND symbol = ?""",
                (self.symbol,),
            ).fetchall()
            conn.close()

            for row in rows:
                setup = row["setup_type"] or "momentum"
                profile = self._profiles.get(setup, self._profiles.get("scalp_0dte", self._profiles["momentum"]))
                self._trade_manager.add_position(
                    trade_id=row["id"],
                    symbol=row["symbol"],
                    direction=row["direction"],
                    profile=profile,
                    expiration=datetime.strptime(row["expiration"], "%Y-%m-%d").date(),
                    entry_time=datetime.fromisoformat(row["entry_date"]) if row["entry_date"] else datetime.now(timezone.utc),
                    entry_price=row["entry_price"] or 0.0,
                    quantity=row["quantity"],
                    confidence=row["confidence_score"] or 0.0,
                    setup_score=0.0,
                    setup_type=setup,
                    strike=row["strike"] or 0.0,
                    right=row["direction"] or "",
                )
            logger.info(f"V2Strategy: reloaded {len(rows)} open positions from DB")
        except Exception as e:
            logger.error(f"V2Strategy: failed to reload open positions: {e}", exc_info=True)

