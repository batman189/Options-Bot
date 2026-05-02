"""V2 Strategy — orchestrates all V2 modules inside Lumibot's trading loop.
Replaces the V1 12-step pipeline with: context → scanner → scorer → profile →
selector → sizer → order. Each step is a labeled comment."""

import logging
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from lumibot.strategies import Strategy
from lumibot.entities import Asset

import config
from config import DB_PATH

# C5b: BasePreset orchestrator pipeline (signal_only mode for swing /
# 0dte_asymmetric). Imports kept top-level for clarity; the new
# pipeline is gated by is_new_preset() in initialize() so legacy
# presets bypass the new code path.
from learning.outcome_tracker import record_signal
from notifications.discord import send_entry_alert
from orchestration.adapters import (
    build_profile_state,
    macro_context_to_event_fetcher,
    resolve_preset_mode,
)
from profiles.base_preset import BasePreset
from profiles.preset_registry import get_preset_class, is_new_preset
from scoring.vix_spike import vix_spike_pct
from sizing.sizer import calculate as size_calculate

logger = logging.getLogger("options-bot.strategy.v2")


@dataclass
class EntrySubmissionResult:
    """Outcome of _submit_entry_order. Caller gates signal-log entered=
    on .submitted.

    Finding 2: pre-fix _submit_entry_order swallowed exceptions and
    returned None implicitly. The caller ran _log_v2_signal
    unconditionally with decision.enter=True — PDT rejections and
    network errors ended up in v2_signal_logs as `entered=1,
    trade_id=NULL, block_reason=NULL`, indistinguishable from orders
    Alpaca accepted but that never filled.

    Post-fix: submitted=True on success (order reached Alpaca);
    submitted=False with a specific block_reason string attributed to
    the submit-time failure mode so daily_summary / UI can count them
    separately.
    """
    submitted: bool
    # When submitted=False, the specific rejection type for signal-log
    # attribution. None on success. Values currently produced:
    #   "pdt_rejected_at_submit" — Alpaca PDT block at submit time
    #   "submit_exception: <ExceptionType>" — any other raise, typed
    #   "invalid_alpaca_id" — submit_order returned without an id Lumibot
    #                         could stamp; callbacks won't match this trade
    block_reason: Optional[str] = None
    # Set on success so the caller can correlate with downstream fills.
    # None on failure (no uuid was generated for a trade that never left).
    trade_id: Optional[str] = None

# Prompt 20 Commit C. Fallback timeout when Lumibot's on_canceled_order
# silently drops (websocket reconnect, broker-side glitch, process
# restart between cancel and callback delivery). After this many
# minutes with no fill/cancel event, Step 10 force-clears the exit
# lock so the next iteration's Step 9 can re-evaluate. Tradeoff:
# lower values = more false-positive lock clears (duplicate submits
# when the real order is just slow to fill); higher values = longer
# lock-in when the callback truly failed. 10 min covers typical
# Alpaca options fill latency with headroom and is short enough that
# a genuinely stuck position gets back into circulation same session.
# Do not lower below 5 (market open/close volatility inflates fill
# latency).
STALE_EXIT_LOCK_MINUTES = 10


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
        # D1: ET date of the most recent on_trading_iteration tick.
        # None at startup; populated on the first iteration. Used to
        # detect calendar-day rollover and reset _day_start_value so
        # PnL baseline doesn't carry over from yesterday.
        self._last_day_check_date = None
        # Prompt 30 Commit B: keyed EXCLUSIVELY by the Alpaca-assigned
        # order.identifier string. Writes happen AFTER submit_order
        # returns so the identifier has already been mutated from
        # Lumibot's construction-time UUID (order.py:433) to the
        # Alpaca server id (alpaca.py:939
        # `order.set_identifier(response.id)`). Callbacks read
        # order.identifier on the same mutated object. See
        # _alpaca_id / _pop_order_entry for the helpers. Commit A
        # was a transitional dual-key (python_id + alpaca_id) to
        # de-risk the cutover; Commit B removes the python-id side
        # entirely. pos.pending_exit_order_id holds the same Alpaca
        # id so staleness / abandonment can pop without the order
        # object.
        self._trade_id_map = {}
        self._last_regime = None  # For change detection
        self._last_context_write = 0.0  # Epoch time of last DB write
        self._pdt_locked = False       # True when ALL entries blocked
        self._pdt_day_trades = 0       # Cached Alpaca daytrade_count
        self._pdt_buying_power = 999999  # Alpaca daytrading_buying_power
        self._pdt_no_same_day_exit = set()  # trade_ids committed to hold overnight
        self._last_entry_time = {}   # profile_name -> datetime of last entry
        self._last_exit_reason = {}  # profile_name -> last exit reason string
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
        # Always scan primary symbol. If SPY, also scan QQQ. Stored on
        # self so _reload_open_positions can use the same set — positions
        # opened on secondary scan symbols (e.g. QQQ under SPY subprocess)
        # would otherwise be orphaned at restart because the filter used
        # self.symbol alone.
        scan_symbols = [self.symbol]
        if self.symbol == "SPY":
            scan_symbols = ["SPY", "QQQ"]
        self._scan_symbols = scan_symbols
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

        # Filter to profiles allowed by this preset.
        # S1.1 (Prompt 34): PRESET_PROFILE_MAP is now the single source
        # of truth in profiles.__init__ so the /api/profiles route and
        # v2_strategy agree on what a preset activates. Pre-fix the map
        # was duplicated here and in profiles.__init__'s primary-profile
        # table, and the API's accepted_setup_types undercounted
        # multi-class presets (scalp, 0dte_scalp, swing/TSLA).
        from profiles import PRESET_PROFILE_MAP
        preset = self._config.get("preset", "") or self.parameters.get("preset", "")
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

        # Apply learning layer adjustments to profile thresholds.
        # Prompt 15 (Bug B read-side fix): learning_state rows are keyed
        # by setup_type (the trades.setup_type grouping that the write
        # path uses). Scalar profiles have profile.name == one setup_type,
        # so the old load_learning_state(pname) pattern accidentally worked
        # for them. Aggregator profiles (scalp_0dte / swing / tsla_swing)
        # accept multiple setup_types, so load_learning_state(pname)
        # always returned None and their state was silently lost on every
        # restart.
        #
        # Two-pass resolution:
        #   Pass 1 — scorer-global overrides (regime_fit, tod_fit) per
        #     setup_type. Applied once per distinct setup_type across
        #     all active profiles (the scorer is shared).
        #   Pass 2 — per-profile state (min_confidence, paused). Option 1
        #     from the spec: max(min_confidence) across the profile's
        #     accepted_setup_types wins (most-restrictive), and if ANY
        #     accepted setup_type is paused, the profile is paused.
        self._apply_learning_state()

        # Load historical trade outcomes from DB into the scorer. Without
        # this the historical_perf factor (15% weight) resets to 0.5
        # neutral on every subprocess restart. Filter to the symbols this
        # subprocess actually scans — matches scan_symbols computed above.
        try:
            self._scorer.load_trade_history_from_db(symbols=scan_symbols, limit=200)
        except Exception as e:
            logger.warning(f"V2Strategy: load_trade_history_from_db failed (non-fatal): {e}")

        self._selector = OptionsSelector(data_client=self._client)
        self._trade_manager = TradeManager(data_client=self._client)
        from risk.risk_manager import RiskManager
        self._risk_manager = RiskManager()
        from alpaca.trading.client import TradingClient as AlpacaTradingClient
        from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER
        self._alpaca_client = AlpacaTradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)
        self.sleeptime = self._config.get("sleeptime", "1M")

        # Shadow Mode simulator — only used when EXECUTION_MODE=shadow.
        # Instantiated unconditionally so tests / introspection can see
        # the attribute even in live mode; the divert at
        # _submit_entry_order / _submit_exit_order is the actual gate.
        # Snapshot the mode on the instance so callers reference a
        # stable attribute rather than re-reading config on every submit.
        from execution.shadow_simulator import ShadowSimulator
        self._execution_mode = config.EXECUTION_MODE
        self._shadow_sim = ShadowSimulator(self, self.get_last_price)
        if self._execution_mode == "shadow":
            logger.warning(
                "V2Strategy: EXECUTION_MODE=shadow — orders will be "
                "simulated locally, NO submissions to Alpaca. "
                f"slippage={config.SHADOW_FILL_SLIPPAGE_PCT}%"
            )

        # ── Reload open trades from DB into trade manager ──
        self._reload_open_positions()

        # ── C5b: BasePreset pipeline state + preset construction ──
        # State dicts the new ProfileState reads via the build_profile_state
        # adapter. Kept on the V2Strategy instance for cross-iteration
        # continuity. Mutated by _run_new_preset_iteration; legacy code
        # path does not touch them.
        self._recent_entries_by_symbol_direction: dict = {}
        self._thesis_break_streaks: dict = {}
        self._recent_exits_by_symbol: dict = {}

        # D4: state for the new-pipeline exit loop.
        # _new_preset_pending_exits: trade_id -> dict with keys
        #   {alpaca_id, submitted_at: datetime UTC, reason: str}
        # Mirrors the (pos.pending_exit_*) fields the legacy
        # ManagedPosition carries. Frozen Position cannot hold
        # mutable per-trade exit state, so the orchestrator owns it.
        # An entry exists between exit-submit and the matching
        # on_filled_order / on_canceled_order / on_error_order.
        self._new_preset_pending_exits: dict = {}
        # _peak_premium_by_trade_id: trade_id -> float (per-share)
        # The high-water mark observed for each open new-pipeline
        # position. Updated each cycle from the live quote and fed
        # into Position.peak_premium_per_share so trailing-stop
        # logic in evaluate_exit can compare to the peak even
        # though Position is frozen and built fresh each cycle.
        # In-memory only; lost on subprocess restart (acceptable —
        # peak resets to current quote on restart, which only
        # over-restricts trailing exits, never under-restricts).
        self._peak_premium_by_trade_id: dict = {}

        # New-preset gating. _new_preset is None for legacy presets;
        # set to a constructed BasePreset subclass for swing /
        # 0dte_asymmetric. _profile_config is the Pydantic instance the
        # preset constructor requires (built from self._config dict).
        self._new_preset = None
        self._profile_config = None

        preset_name_for_registry = (
            self._config.get("preset", "")
            or self.parameters.get("preset", "")
        )
        if is_new_preset(preset_name_for_registry):
            try:
                self._profile_config = self._build_profile_config()
            except Exception as e:
                logger.error(
                    "V2Strategy: _build_profile_config failed for preset=%r — "
                    "new pipeline disabled (legacy loop will run): %s",
                    preset_name_for_registry, e,
                )
            else:
                # macro_fetcher is rebound each iteration with that
                # iteration's MacroContext; placeholder here so the
                # constructor stores the kwarg slot. Dispatch per
                # preset class because SwingPreset and
                # ZeroDteAsymmetricPreset accept different fetcher
                # kwargs (ivr+macro vs macro+vix+bars+now).
                from profiles.swing_preset import SwingPreset as _SwingPreset
                from profiles.zero_dte_asymmetric import (
                    ZeroDteAsymmetricPreset as _ZeroDteAsymmetricPreset,
                )

                _empty_macro = lambda symbol, lookahead: []
                _now_et = lambda: datetime.now(ZoneInfo("America/New_York"))
                preset_class = get_preset_class(preset_name_for_registry)

                if preset_class is _SwingPreset:
                    self._new_preset = _SwingPreset(
                        config=self._profile_config,
                        macro_fetcher=_empty_macro,
                        # ivr_fetcher left None — IVR cold-start
                        # behavior per §4.1 is to skip the IVR gate.
                        # Production wire-in (Phase 1b) supplies
                        # scoring.ivr.get_ivr.
                    )
                elif preset_class is _ZeroDteAsymmetricPreset:
                    self._new_preset = _ZeroDteAsymmetricPreset(
                        config=self._profile_config,
                        macro_fetcher=_empty_macro,
                        bars_fetcher=self._client.get_stock_bars,
                        vix_spike_fetcher=vix_spike_pct,
                        now_fetcher=_now_et,
                    )
                else:
                    logger.warning(
                        "V2Strategy: preset=%r in registry but no "
                        "construction dispatch — new pipeline disabled",
                        preset_name_for_registry,
                    )
                    self._new_preset = None

                if self._new_preset is not None:
                    logger.info(
                        "V2Strategy: new-preset pipeline active for "
                        "preset=%r (%s)",
                        preset_name_for_registry,
                        type(self._new_preset).__name__,
                    )

        logger.info(f"V2Strategy initialized: profiles={list(self._profiles.keys())} symbol={self.symbol}")

    def _build_profile_config(self):
        """Build a ProfileConfig from V2Strategy's JSON config dict.

        Phase 1a signal_only: required fields are 'preset', 'symbols',
        'max_capital_deployed', 'name'. Optional: 'discord_webhook_url'.
        Mode is derived from config.EXECUTION_MODE: live/shadow →
        'execution', signal_only → 'signal_only'.

        max_capital_deployed defaults to $5,000 (Alpaca paper account)
        if absent. See PHASE_1A_FOLLOWUPS.md ("max_capital_deployed
        default in V2Strategy._build_profile_config") — this default
        belongs at the profile-creation API, not the orchestrator.

        Raises ValidationError if the resulting dict cannot satisfy
        ProfileConfig's strict validation; caller catches and disables
        the new pipeline rather than failing subprocess startup.
        """
        from profiles.profile_config import ProfileConfig

        name = self.profile_name or self._config.get("name") or "unnamed"
        # ProfileConfig.name regex rejects spaces — sanitize defensively
        name = name.replace(" ", "_")

        mode_map = {
            "live": "execution",
            "shadow": "execution",
            "signal_only": "signal_only",
        }
        mode = mode_map.get(config.EXECUTION_MODE, "execution")

        return ProfileConfig(
            name=name,
            preset=self._config.get("preset", ""),
            symbols=(
                self._scan_symbols
                or self._config.get("symbols", [])
            ),
            max_capital_deployed=float(
                self._config.get("max_capital_deployed", 5000.0)
            ),
            mode=mode,
            discord_webhook_url=self._config.get("discord_webhook_url"),
        )

    def _build_live_profile_state(self, preset_name: str):
        """Build a ProfileState from live subprocess + DB state.

        Phase 1b D1: replaces the C5b stubbed fields with real
        computations. Used by _run_new_preset_iteration.

        Queries (all scoped to this profile_id and execution_mode):
          - current_open_positions: COUNT trades WHERE status='open'
          - current_capital_deployed: SUM(entry_price * quantity * 100)
          - last_exit_at: MAX(exit_date) FROM closed trades

        today_account_pnl_pct = (pv - day_start_value) / day_start_value,
        with pv from self.get_portfolio_value(). Defensive guard on
        pv=None / pv<=0 returns 0.0 with a warning rather than the
        spurious -100% that propagating through cap_check would produce.

        For Phase 1a signal_only mode no rows exist with profile_id in
        trades (signals don't insert), so the queries return zero / None
        — matching the previous stub behavior naturally.

        Per-call sqlite3.connect (matches the codebase pattern at
        v2:744-760, 1085, 1177, etc.) — long-lived connections aren't
        thread-safe with Lumibot's order-stream callbacks.
        """
        from orchestration.adapters import build_profile_state

        profile_id = self._profile_config.name

        # The runtime execution_mode for the preset. resolve_preset_mode's
        # signal_only result corresponds to no DB rows existing; we still
        # filter by config.EXECUTION_MODE since that's the value the
        # eventual D3 submission path will write.
        execution_mode = config.EXECUTION_MODE

        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM trades "
                "WHERE status = 'open' AND execution_mode = ? "
                "AND profile_id = ?",
                (execution_mode, profile_id),
            )
            open_count = cur.fetchone()[0] or 0

            cur = conn.execute(
                "SELECT COALESCE(SUM(entry_price * quantity * 100), 0.0) "
                "FROM trades WHERE status = 'open' "
                "AND execution_mode = ? AND profile_id = ?",
                (execution_mode, profile_id),
            )
            capital_deployed = float(cur.fetchone()[0] or 0.0)

            cur = conn.execute(
                "SELECT MAX(exit_date) FROM trades "
                "WHERE profile_id = ? AND status = 'closed'",
                (profile_id,),
            )
            last_exit_iso = cur.fetchone()[0]

        last_exit_at = (
            datetime.fromisoformat(last_exit_iso)
            if last_exit_iso else None
        )

        # today_account_pnl_pct with defensive pv guard.
        pv = self.get_portfolio_value()
        if pv is None or pv <= 0.0:
            if self._day_start_value > 0.0:
                logger.warning(
                    "_build_live_profile_state: get_portfolio_value() "
                    "returned %r — using pnl_pct=0.0 instead of computing "
                    "against day_start_value=%.2f",
                    pv, self._day_start_value,
                )
            pnl_pct = 0.0
        elif self._day_start_value > 0.0:
            pnl_pct = (pv - self._day_start_value) / self._day_start_value
        else:
            pnl_pct = 0.0  # day_start_value not yet seeded

        return build_profile_state(
            # build_profile_state takes a list and converts via len();
            # placeholder list of None * count is the cheapest path
            # that doesn't require changing the adapter's signature.
            # See PHASE_1A_FOLLOWUPS.md "open_positions list-padding
            # in _build_live_profile_state".
            open_positions=[None] * open_count,
            capital_deployed=capital_deployed,
            account_pnl_pct=pnl_pct,
            last_exit_at=last_exit_at,
            last_entry_at=self._last_entry_time.get(preset_name),
            recent_exits_by_symbol=self._recent_exits_by_symbol,
            recent_entries_by_symbol_direction=(
                self._recent_entries_by_symbol_direction
            ),
            thesis_break_streaks=self._thesis_break_streaks,
        )

    def _apply_learning_state(self):
        """Read learning_state rows per setup_type and apply them.

        Two-pass Prompt-15 design:
          Pass 1 loads rows for every setup_type across all active profiles
            and forwards regime_fit_overrides / tod_fit_overrides to the
            scorer (scorer is shared across profiles; those deltas are
            scorer-global).
          Pass 2 iterates the profiles, reads rows for each profile's
            accepted_setup_types, and:
              - pauses the profile if ANY of its setup_types is paused
              - sets min_confidence = max(state.min_confidence across its
                accepted_setup_types) — Option 1 from the spec, the
                most-restrictive threshold wins.

        Non-fatal: any exception falls through to a WARN and trading
        continues on constructor defaults.

        Extracted as a helper so tests can exercise the logic directly
        without spinning up the full initialize() path.
        """
        # Collect the distinct setup_types this subprocess will consult.
        accepted_setup_types: set[str] = set()
        for profile in self._profiles.values():
            accepted = getattr(profile, "accepted_setup_types", None)
            if accepted:
                accepted_setup_types.update(accepted)
            else:
                accepted_setup_types.add(profile.name)

        # Pass 1 — scorer-global deltas per setup_type.
        try:
            from learning.storage import load_learning_state
            for setup_type in sorted(accepted_setup_types):
                state = load_learning_state(setup_type)
                if state is None:
                    continue
                if state.regime_fit_overrides:
                    self._scorer.set_regime_overrides(state.regime_fit_overrides)
                    logger.info(
                        f"V2Strategy: applied regime_fit_overrides from "
                        f"{setup_type} state: {state.regime_fit_overrides}"
                    )
                if state.tod_fit_overrides:
                    self._scorer.set_tod_overrides(state.tod_fit_overrides)
                    logger.info(
                        f"V2Strategy: applied tod_fit_overrides from "
                        f"{setup_type} state: {state.tod_fit_overrides}"
                    )
        except Exception as e:
            logger.warning(
                f"V2Strategy: failed to apply scorer-side learning state "
                f"(non-fatal): {e}"
            )

        # Pass 2 — per-profile min_confidence + paused.
        try:
            from learning.storage import load_learning_state
            for pname, profile in self._profiles.items():
                accepted = (
                    getattr(profile, "accepted_setup_types", None) or {profile.name}
                )
                min_confidences: list[float] = []
                is_paused = False
                paused_by: Optional[str] = None
                for setup_type in accepted:
                    state = load_learning_state(setup_type)
                    if state is None:
                        continue
                    if state.paused_by_learning:
                        is_paused = True
                        paused_by = setup_type
                    min_confidences.append(state.min_confidence)
                if is_paused:
                    self._paused_profiles.add(pname)
                    logger.warning(
                        f"V2Strategy: {pname} PAUSED by learning "
                        f"(setup_type={paused_by} is paused)"
                    )
                elif min_confidences:
                    profile.min_confidence = max(min_confidences)
                    logger.info(
                        f"V2Strategy: {pname} threshold "
                        f"{profile.min_confidence:.3f} "
                        f"(max across {sorted(accepted)})"
                    )
                else:
                    logger.info(
                        f"V2Strategy: {pname} using default threshold "
                        f"{profile.min_confidence:.3f} (no learning state yet)"
                    )
        except Exception as e:
            logger.warning(
                f"V2Strategy: failed to apply per-profile learning state "
                f"(non-fatal): {e}"
            )

    def on_trading_iteration(self):
        """Main loop — calls V2 modules in sequence.

        Prompt 31 (O18) -- step numbering note: Steps 9-10 (exit
        management) run BEFORE Steps 1-8 (entry evaluation) within a
        single iteration. Intentional -- we want to free up capital
        from exits before evaluating new entries, and we want exits
        to fire regardless of whether entry evaluation succeeds
        (exit is wrapped in its own try/except). Logs will show
        "Step 9 -> Step 10 -> Step 1 -> Step 2 -> ..." per iteration;
        reading them top-to-bottom is expected. Do not renumber --
        doing so would break every downstream log-parsing tool that
        keys off these prefixes.
        """
        iteration_start = time.time()
        logger.info(f"--- V2 {self.profile_name}/{self.symbol} at {self.get_datetime()} ---")

        # D1: ET-date rollover guard. _day_start_value was previously
        # set lazily on first iteration but never reset across calendar
        # days — a subprocess running across midnight ET would compute
        # today_account_pnl_pct against yesterday's baseline. Reset to
        # 0.0 when the date changes; the lazy init below re-seeds it
        # from current pv on this same iteration.
        _now_et_d1 = datetime.now(ZoneInfo("America/New_York"))
        _today_et_d1 = _now_et_d1.date()
        if (
            self._last_day_check_date is not None
            and self._last_day_check_date != _today_et_d1
        ):
            logger.info(
                "V2Strategy: ET date rolled over (%s -> %s) — resetting "
                "_day_start_value (was %.2f) for fresh PnL baseline",
                self._last_day_check_date, _today_et_d1,
                self._day_start_value,
            )
            self._day_start_value = 0.0
        self._last_day_check_date = _today_et_d1

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

            # Use the cached scan (force=False). Prompt 31 (O15):
            # exit thesis evaluation tolerates <=60s stale setup
            # scores -- the outer loop runs every 60s anyway, and
            # forcing a second live scan here would double the
            # scanner cost per iteration. The second scan at Step 2
            # below IS forced because entry decisions need
            # current-bar data; see that site's comment.
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

                # Block 2.5 (Prompt 20 Commit C): stale-lock timeout.
                # If the exit order was submitted > STALE_EXIT_LOCK_MINUTES
                # ago and neither a fill nor a cancel callback cleared
                # the lock, treat the lock as stale and reset it. The
                # next iteration's Step 9 re-evaluates whether an exit
                # is still warranted. This cycle does NOT submit a new
                # order (pending_exit is flipped to False, so the pos
                # drops out of get_pending_exits and this iteration ends
                # for it). That's intentional: avoid duplicate submits
                # if the original order is actually live and just late.
                if self._clear_stale_exit_lock(trade_id, pos):
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

            # Macro awareness snapshot — ONE read per iteration, threaded
            # through every score() and should_enter() call below. Avoids
            # ~180 per-combination SELECTs (see plan section D). Fail-safe:
            # a DB error inside the reader returns an empty MacroContext
            # which is a no-op for downstream veto/nudge logic.
            from macro.reader import snapshot_macro_context
            macro_ctx = snapshot_macro_context()

            # Build Step 1 log suffix from macro state (omitted when stale)
            macro_tag = ""
            if macro_ctx.regime is not None:
                macro_tag += f" | macro={macro_ctx.regime.risk_tone}"
            upcoming_events = []
            for _sym, _evs in macro_ctx.events_by_symbol.items():
                upcoming_events.extend(_evs)
            upcoming_events.sort(key=lambda e: e.minutes_until)
            if upcoming_events:
                nxt = upcoming_events[0]
                macro_tag += f" event_in={nxt.minutes_until}m:{nxt.event_type}"

            logger.info(
                f"  Step 1: regime={snapshot.regime.value} "
                f"tod={snapshot.time_of_day.value}{macro_tag}"
            )

            # Persist regime to DB (throttled: on change or every 5 min)
            self._persist_context_snapshot(snapshot)

            # ── Step 2: Scanner ──
            # force=True on purpose (Prompt 31 / O15). Entry decisions
            # read current-bar setup scores; a cached scan could be up
            # to 60s old, during which a TRENDING_UP -> CHOPPY regime
            # flip or an intrabar price reversal could materially change
            # the decision. Step 9's exit thesis above uses the cached
            # scan to avoid doubling the per-iteration scan cost --
            # the two scans can therefore disagree by one bar, which
            # shows up in logs as microsecond-apart scores. Not a bug.
            scan_results = self._scanner.scan(force=True)
            active = [(r, s) for r in scan_results for s in r.setups if s.score > 0]
            logger.info(f"  Step 2: {len(active)} active setups from {len(scan_results)} symbols")

            # Persist scanner results to DB
            self._persist_scanner_snapshot(scan_results, snapshot)

            if not active:
                # Log the best rejected setup per symbol so the UI shows WHY nothing qualified
                self._log_scanner_rejection(scan_results, snapshot, macro_ctx=macro_ctx)
                return

            # ── C5b: New-preset pipeline short-circuit ──
            # When this subprocess is configured for a BasePreset preset
            # (swing / 0dte_asymmetric), the legacy Steps 4-8 below are
            # skipped — the new pipeline takes over. Legacy presets fall
            # through and the per-profile loop runs unchanged.
            #
            # D4: rebind macro_fetcher ONCE per iteration so both the
            # exit loop (Step 9') and the entry loop see the same
            # MacroContext snapshot. Then run Step 9' (new-pipeline
            # exit evaluation) followed by the entry loop. Legacy
            # Step 9-10 above is a no-op for new-pipeline trades (they
            # are never added to TradeManager._positions per the
            # isinstance bypass in on_filled_order); running both
            # harmlessly side-by-side.
            if self._new_preset is not None:
                self._rebind_preset_macro_fetcher(macro_ctx)
                self._run_new_preset_exit_iteration(
                    active, snapshot, macro_ctx,
                )
                self._run_new_preset_iteration(active, snapshot, macro_ctx)
                return

            # Evaluate each active setup — match setup_type to correct profile
            for scan_result, setup in active:
                # Score once per setup
                from scanner.sentiment import get_sentiment
                sentiment = get_sentiment(scan_result.symbol)
                scored = self._scorer.score(
                    scan_result.symbol, setup, snapshot,
                    sentiment_score=sentiment.score,
                    macro_ctx=macro_ctx,
                )
                logger.info(f"  Step 3: {scan_result.symbol} {setup.setup_type} "
                            f"score={scored.capped_score:.3f} [{scored.threshold_label}]")

                # Evaluate against ALL profiles — each decides independently
                for profile_name, profile in self._profiles.items():
                    if profile_name in self._paused_profiles:
                        continue

                    # ── Step 4: Profile decision ──
                    decision = profile.should_enter(scored, snapshot.regime, macro_ctx=macro_ctx)
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

                        # Trailing-stop re-entry: if the previous exit was a
                        # trailing stop (winner) and the setup is still strong,
                        # cut cooldown to 2 min — the trend is still going.
                        last_exit = self._last_exit_reason.get(profile_name, "")
                        if last_exit == "trailing_stop" and setup.score >= 0.60:
                            effective_cooldown = min(effective_cooldown, 2.0)
                            logger.info(
                                "  Step 5b: trailing stop re-entry — cooldown reduced to 2min"
                            )

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
                        # Shadow Mode: max-concurrent applies per mode.
                        # A live subprocess must not count shadow ghost
                        # positions toward its cap, and vice versa.
                        # getattr fallback for minimal test stubs.
                        _mode_for_count = getattr(
                            self, "_execution_mode", "live"
                        )
                        open_count = _db.execute(
                            "SELECT COUNT(*) FROM trades "
                            "WHERE status = 'open' AND execution_mode = ?",
                            (_mode_for_count,),
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
                    # EV gate disabled 2026-04-21 (Prompt 17 Commit B). The
                    # prior input — setup.score * 2 — was a dimensionless
                    # scanner fitness score passed into a calculation
                    # (selection/ev.py) that treats predicted_move_pct as
                    # a forward-move percentage. For a typical signal
                    # (setup.score=0.95) this fabricated a 1.9% move on
                    # SPY, ~5x the actual observed move; the EV filter
                    # was gating trades on fiction. Option A per the
                    # spec: pass None, skip EV, keep every other filter.
                    # Other filters continue to run: spread, liquidity,
                    # VIX, confidence, regime, cooldown, position cap,
                    # sizer risk budget. See docs/Bot Problems.md Issue 7
                    # for Option C (reinstate with a real forecast).
                    use_otm = bool(self._config.get("use_otm_strikes", False))
                    contract = self._selector.select(
                        symbol=scan_result.symbol,
                        direction=decision.direction,
                        confidence=scored.capped_score,
                        hold_minutes=profile.max_hold_minutes,
                        profile_name=profile_name,
                        predicted_move_pct=None,   # EV disabled
                        use_otm=use_otm,
                        config=self._config,
                    )
                    if contract is None:
                        logger.info(f"  Step 6 [{profile_name}]: no qualifying contract")
                        # S3.1 (Prompt 34 Commit B): emit signal log so
                        # "no contract" rejects show up in v2_signal_logs
                        # alongside Step 4/5b/5c rejections. Same mutate-
                        # decision + log pattern used at lines 542-544.
                        decision.enter = False
                        decision.reason = "no_qualifying_contract"
                        self._log_v2_signal(scored, decision, snapshot, profile_name)
                        continue
                    ev_str = (f"{contract.ev_pct:.1f}%"
                              if contract.ev_pct is not None else "disabled")
                    logger.info(f"  Step 6 [{profile_name}]: {contract.right} ${contract.strike} "
                                f"exp={contract.expiration} EV={ev_str}")

                    # ── Step 7: Size position + PDT gate ──
                    is_same_day = contract.expiration == str(datetime.now(timezone.utc).date())

                    # PDT gate: three levels of restriction (accounts < $25K)
                    if pv < 25000:
                        if self._pdt_locked:
                            logger.info(f"  Step 7: BLOCKED — PDT fully locked "
                                        f"(day_trades={self._pdt_day_trades}, "
                                        f"bp=${self._pdt_buying_power:.0f})")
                            # S3.1: signal log for PDT-locked rejection.
                            decision.enter = False
                            decision.reason = "pdt_locked"
                            self._log_v2_signal(scored, decision, snapshot, profile_name)
                            continue
                        elif self._pdt_day_trades >= 2 and is_same_day:
                            logger.info("  Step 7: BLOCKED — 1 day trade left + 0DTE, "
                                        "would be trapped")
                            # S3.1: signal log for day-trades-exhausted-vs-0DTE reject.
                            decision.enter = False
                            decision.reason = "pdt_day_trades_exhausted"
                            self._log_v2_signal(scored, decision, snapshot, profile_name)
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
                        # S3.1: signal log for sizer rejection. Use the
                        # sizer's detailed block_reason verbatim so
                        # analytics can tell apart drawdown halts,
                        # exposure limits, and insufficient_risk_budget
                        # without parsing stdout. Fall back to
                        # "sizer_blocked" only if the sizer's string
                        # was None (shouldn't happen per sizer contract,
                        # but defensive).
                        decision.enter = False
                        decision.reason = sizing.block_reason or "sizer_blocked"
                        self._log_v2_signal(scored, decision, snapshot, profile_name)
                        continue
                    logger.info(f"  Step 7: {sizing.contracts} contracts")

                    # ── Step 8: Submit entry order ──
                    submission = self._submit_entry_order(
                        contract, sizing.contracts, scored, setup, profile, snapshot
                    )

                    # Finding 2: gate entered= on actual submission. Pre-fix
                    # this site ran _log_v2_signal unconditionally with
                    # decision.enter=True, even when _submit_entry_order
                    # internally caught a PDT rejection or network error.
                    # Signal log rows for failed submissions looked identical
                    # to accepted-but-unfilled orders (entered=1, trade_id=NULL,
                    # block_reason=NULL). Post-fix: flip decision.enter=False
                    # with a specific block_reason so analytics can count
                    # submit-time rejections separately. Pattern matches the
                    # cooldown / max-positions mutation sites above (Step 5b,
                    # Step 5c) which already mutate `decision` rather than
                    # constructing a new EntryDecision.
                    if not submission.submitted:
                        decision.enter = False
                        decision.reason = submission.block_reason or "submit_failed"
                    self._log_v2_signal(scored, decision, snapshot, profile_name)

        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"V2 Steps 1-8 error ({self._consecutive_errors}): {e}", exc_info=True)
        else:
            self._consecutive_errors = 0

        elapsed = time.time() - iteration_start
        if elapsed > 10:
            logger.info(f"  Iteration: {elapsed:.1f}s")

    def on_canceled_order(self, order):
        """Lumibot callback when an order is canceled.

        Prompt 20 Commit B. Lumibot invokes this on any status that
        STATUS_ALIAS_MAP resolves to "canceled" — the full list per
        lumibot/entities/order.py:103-128:
            canceled, cancelled, cancel, expired, done_for_day,
            replaced, pending_replace, stopped, suspended,
            pending_cancel, apicancelled
        Alpaca GTD expiry at market close emits "expired" which maps
        here; user or programmatic cancels emit "canceled"; modifies
        emit "replaced". Status "rejected" does NOT route through
        this callback — it hits broker's ERROR_ORDER path. Rejections
        will only be cleared by Commit C's stale-lock timeout.

        For BUY cancels: the trade was never persisted (the DB INSERT
        only runs in on_filled_order). Just pop the _trade_id_map
        entry so the stale dict doesn't leak.

        For SELL cancels: the position is still open in Alpaca and
        in the DB. Clear the exit lock on the matching
        ManagedPosition so the next iteration's Step 9 re-evaluates
        the exit from scratch. pending_exit stays False so we do NOT
        immediately re-submit this iteration.
        """
        # Prompt 30 Commit B: single-key pop by order.identifier
        # (the Alpaca server id, post-mutation inside submit_order).
        entry = self._pop_order_entry(order)
        if entry is None:
            # Unknown order — possibly an exit submitted before this
            # subprocess started, or an id already popped by another
            # path (Commit A's abandonment, Commit C's stale timeout,
            # or on_filled_order racing the cancel callback).
            logger.info("  CANCEL: untracked order id — ignored")
            return

        side = getattr(order, "side", "")
        if side in ("buy", "buy_to_open"):
            trade_id = (entry["trade_id"]
                        if isinstance(entry, dict) else str(entry))
            logger.info(
                f"  CANCEL: BUY {trade_id[:8]} — no DB cleanup needed "
                "(INSERT happens on fill only)"
            )
            return

        if side in ("sell", "sell_to_close"):
            trade_id = (entry if isinstance(entry, str)
                        else entry.get("trade_id", ""))

            # D4: route new-pipeline exit cancels. The pending-exit
            # entry must be cleared so the next iteration's Step 9'
            # re-evaluates and may re-submit. _peak_premium and
            # thesis_break_streaks are NOT cleared — the position
            # is still open. getattr-default keeps legacy tests that
            # build minimal V2Strategy stubs via __new__() (without
            # running initialize) from AttributeError'ing here.
            _pending = getattr(self, "_new_preset_pending_exits", None)
            if _pending is not None and trade_id in _pending:
                _pending.pop(trade_id, None)
                logger.info(
                    f"  CANCEL: SELL {trade_id[:8]} (new-pipeline) — "
                    "pending-exit cleared, re-evaluation on next cycle"
                )
                return

            pos = self._trade_manager._positions.get(trade_id)
            if pos is None:
                # Position already popped — fill raced the cancel, or
                # confirm_fill ran first via a different order id.
                logger.info(
                    f"  CANCEL: SELL {trade_id[:8]} — position already "
                    "popped (probably filled via a different order); no-op"
                )
                return

            # Clear the exit lock. pending_exit=False means Step 10
            # does not re-submit this iteration; next iteration's
            # Step 9 decides whether the exit is still warranted.
            pos.pending_exit = False
            pos.pending_exit_reason = ""
            pos.pending_exit_order_id = None
            pos.exit_retry_count = 0
            pos.pending_exit_submitted_at = None   # Prompt 20 Commit C
            logger.info(
                f"  CANCEL: SELL {trade_id[:8]} — exit lock cleared, "
                "re-evaluation on next cycle"
            )
            return

        # Unknown side — log and leave state alone. Shouldn't happen
        # on Alpaca live (buy/sell only) but be defensive.
        logger.warning(f"  CANCEL: unrecognized order.side={side!r} — ignored")

    def on_error_order(self, order, error=None):
        """Lumibot callback when the broker rejects an order.

        Prompt 23. Alpaca broker-side rejections (insufficient buying
        power, invalid contract, market closed, bad price, PDT
        violations after ack) map to Lumibot's "error" status per
        STATUS_ALIAS_MAP (order.py:117 `"rejected": "error"`). These
        orders enqueue an ERROR_ORDER event that dispatches to this
        callback asynchronously (strategy_executor.py:614-616) — no
        overlap with the synchronous exception handler in
        _submit_exit_order, because Alpaca's _submit_order (alpaca.py:
        944-976) catches its API errors and returns the order with
        set_error() rather than re-raising.

        Lumibot dispatch (strategy_executor.py:1216-1224) prefers the
        two-arg form on_error_order(order, error) and falls back to
        the one-arg form if we TypeError — we implement the two-arg
        form.

        Cleanup mirrors on_canceled_order (Commit 20B). The only
        semantic difference is log level (WARNING here vs INFO
        there — rejections deserve operator visibility) and the
        error message getting logged.

        Critically, we do NOT increment exit_retry_count here. That
        counter caps the in-_submit_exit_order transient-error ladder
        (max 5 attempts within a single submission). A broker-side
        reject is a different class of failure; the position should
        re-evaluate fresh on the next iteration with its own 5-retry
        budget.

        Rejections were previously only cleaned up by Commit 20C's
        10-minute stale-lock timeout. This callback closes that
        window to roughly one trading iteration (the next Step 9
        re-evaluation decides whether to retry the exit).
        """
        err_str = str(error) if error is not None else (
            getattr(order, "error_message", None) or "unknown"
        )
        # Prompt 30 Commit B: single-key pop by order.identifier.
        entry = self._pop_order_entry(order)
        if entry is None:
            logger.info(
                f"  ERROR: untracked order id — ignored (error={err_str!r})"
            )
            return

        side = getattr(order, "side", "")
        if side in ("buy", "buy_to_open"):
            trade_id = (entry["trade_id"]
                        if isinstance(entry, dict) else str(entry))
            logger.warning(
                f"  ERROR: BUY {trade_id[:8]} rejected — no DB cleanup "
                f"needed (INSERT happens on fill only). Error: {err_str}"
            )
            return

        if side in ("sell", "sell_to_close"):
            trade_id = (entry if isinstance(entry, str)
                        else entry.get("trade_id", ""))

            # D4: route new-pipeline exit errors. Same shape as the
            # cancel branch — clear the pending-exit dict entry so
            # Step 9' re-evaluates next cycle. The position itself
            # remains open (peak / streaks preserved). getattr-default
            # for legacy stubs (see on_canceled_order parallel branch).
            _pending = getattr(self, "_new_preset_pending_exits", None)
            if _pending is not None and trade_id in _pending:
                _pending.pop(trade_id, None)
                logger.warning(
                    f"  ERROR: SELL {trade_id[:8]} (new-pipeline) "
                    "rejected — pending-exit cleared, re-evaluation "
                    f"on next cycle. Error: {err_str}"
                )
                return

            pos = self._trade_manager._positions.get(trade_id)
            if pos is None:
                logger.warning(
                    f"  ERROR: SELL {trade_id[:8]} rejected but position "
                    "already popped (probably filled via a different "
                    f"order); no-op. Error: {err_str}"
                )
                return

            # Clear the exit lock. Next iteration's Step 9 decides
            # whether the exit is still warranted — if so, Step 10
            # resubmits. exit_retry_count reset to 0 (this was not one
            # of our transient retries; it's a broker reject).
            pos.pending_exit = False
            pos.pending_exit_reason = ""
            pos.pending_exit_order_id = None
            pos.pending_exit_submitted_at = None
            pos.exit_retry_count = 0
            logger.warning(
                f"  ERROR: SELL {trade_id[:8]} rejected — exit lock "
                f"cleared, re-evaluation on next cycle. Error: {err_str}"
            )
            return

        logger.warning(
            f"  ERROR: unrecognized order.side={side!r} — "
            f"ignored (error={err_str!r})"
        )

    def on_filled_order(self, position, order, price, quantity, multiplier):
        """Handle fill — INSERT to DB on buy fill, delegate to trade manager on sell fill."""
        logger.info(f"ORDER FILLED: {order.side} {quantity}x {position.asset} @ ${price:.2f}")

        # Prompt 30 Commit B: single-key pop by order.identifier.
        entry = self._pop_order_entry(order)
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
                # was_day_trade intentionally omitted — it cannot be known at
                # BUY time (it means "round-trip closed the same calendar day"
                # per the PDT rule, not "0DTE contract"). The column has
                # DEFAULT 0 in the schema; trade_manager.confirm_fill() will
                # UPDATE it to 1 on SELL fill when the round-trip was in-day.
                # D4: entry_underlying_price is sourced from
                # chain.underlying_price by the new-pipeline entry path
                # (_submit_new_pipeline_entry). Legacy entries do not
                # populate this key; .get() returns None which sqlite3
                # writes as NULL — preserving pre-D4 schema behavior.
                conn.execute(
                    """INSERT INTO trades (
                           id, profile_id, profile_name, symbol, direction, strike, expiration,
                           quantity, entry_price, entry_date, entry_underlying_price,
                           setup_type, confidence_score, market_regime, market_vix,
                           status, execution_mode, created_at, updated_at
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        trade_id,
                        entry["profile_id"],
                        entry["profile_name"],  # Prompt 16: owning profile for reload binding
                        entry["symbol"],
                        entry["direction"],
                        entry["strike"],
                        entry["expiration"],
                        entry["quantity"],
                        price,  # Actual fill price, not estimated mid
                        now_utc,
                        entry.get("entry_underlying_price"),
                        entry["setup_type"],
                        entry["confidence_score"],
                        entry["regime"],
                        entry["vix_level"],
                        "open",
                        # Shadow Mode: the trade row must carry the mode that
                        # produced it so P&L / learning queries can filter.
                        config.EXECUTION_MODE,
                        now_utc,
                        now_utc,
                    ),
                )
                conn.commit()
                # Link trade_id back to the signal log that triggered it.
                # profile_name is included in the WHERE clause so two profiles
                # trading the same (symbol, setup_type) in one iteration cycle
                # cannot update each other's row — each signal log carries the
                # profile_name of the profile that evaluated it, matched here
                # against the BUY-fill's originating profile.name.
                try:
                    conn.execute(
                        """UPDATE v2_signal_logs SET trade_id = ?
                           WHERE entered = 1 AND trade_id IS NULL
                             AND symbol = ? AND setup_type = ?
                             AND profile_name = ?
                           ORDER BY id DESC LIMIT 1""",
                        (trade_id, entry["symbol"], entry["setup_type"],
                         entry["profile_name"]),
                    )
                    conn.commit()
                except Exception:
                    pass  # Non-fatal
                conn.close()
                logger.info(f"  BUY FILL: {trade_id[:8]} ${price:.2f} persisted to DB")
            except Exception as e:
                logger.error(f"  BUY FILL DB INSERT failed for {trade_id[:8]}: {e}")

            # D3: Bypass TradeManager.add_position for new-pipeline
            # trades. ManagedPosition is legacy-only; the trades INSERT
            # above already persists the row, and D4 reads open
            # positions from the trades DB for the new-pipeline exit
            # loop. BasePreset has no record_entry method, so calling
            # add_position would AttributeError on profile.record_entry.
            profile_obj = entry["profile"]
            if not isinstance(profile_obj, BasePreset):
                # Legacy path — register with trade manager for exit
                # monitoring (TradeManager.run_cycle calls
                # profile.check_exit on this).
                self._trade_manager.add_position(
                    trade_id=trade_id, symbol=entry["symbol"],
                    profile=profile_obj,
                    expiration=datetime.strptime(entry["expiration"], "%Y-%m-%d").date(),
                    entry_time=datetime.now(timezone.utc),
                    entry_price=price, quantity=entry["quantity"],
                    confidence=entry["confidence_score"],
                    setup_type=entry["setup_type"],
                    strike=entry["strike"], right=entry["direction"],
                )

            # If PDT requires hold-overnight, mark this trade
            if self._pdt_day_trades >= 2 and (self.get_portfolio_value() or 0) < 25000:
                self._pdt_no_same_day_exit.add(trade_id)
                logger.info(f"  BUY FILL: {trade_id[:8]} marked PDT hold-overnight")

        elif order.side in ("sell", "sell_to_close"):
            # entry is a trade_id string (set by _submit_exit_order or
            # by _submit_new_pipeline_exit).
            trade_id = entry if isinstance(entry, str) else entry.get("trade_id", "")

            # D4: route new-pipeline exits to the new fill handler.
            # Detection: presence of the trade_id key in
            # self._new_preset_pending_exits — installed by
            # _submit_new_pipeline_exit on submit. New-pipeline trades
            # are never in self._trade_manager._positions (the D3
            # isinstance bypass in the BUY branch above keeps them out),
            # so confirm_fill would no-op and the legacy scorer-update
            # SELECT would see status='open' (no row returned). Routing
            # explicitly is cleaner and avoids the wasted DB query.
            # getattr-default for legacy stubs (see on_canceled_order
            # parallel branch).
            _pending = getattr(self, "_new_preset_pending_exits", None)
            if _pending is not None and trade_id in _pending:
                self._handle_new_pipeline_exit_fill(trade_id, price)
                return

            # Capture exit reason + profile before confirm_fill pops the position
            _exited_pos = self._trade_manager._positions.get(trade_id)
            if _exited_pos is not None:
                self._last_exit_reason[_exited_pos.profile.name] = _exited_pos.pending_exit_reason
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

    def _submit_entry_order(self, contract, quantity, scored, setup, profile, snapshot) -> EntrySubmissionResult:
        """Submit a buy order and store metadata for DB insert on fill confirmation.

        Returns EntrySubmissionResult so the caller can gate the
        signal-log entered= flag on actual submission success. Pre-
        Finding-2 this method swallowed exceptions and returned None
        implicitly; the caller logged entered=True unconditionally,
        poisoning v2_signal_logs with phantom entries for orders that
        never reached Alpaca.
        """
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
            # Build entry metadata (written to the map AFTER submit_order
            # returns, keyed by the Alpaca id that Lumibot stamps onto
            # order.identifier inside submit_order).
            _entry_meta = {
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
                # profile.name is the profile KEY (e.g. "scalp_0dte"), which is
                # what _log_v2_signal stores on the signal row. setup.setup_type
                # is the setup CLASS (e.g. "momentum") — same thing only for
                # profiles whose name == setup_type (momentum, mean_reversion,
                # catalyst). scalp_0dte accepts multiple setup_types, so using
                # setup_type here would cause the UPDATE-to-link filter below
                # to miss the real signal-log row.
                "profile_name": profile.name,
                "setup_score": setup.score,
            }
            return self._dispatch_entry_order(
                order, _entry_meta, profile.name, trade_id,
            )
        except Exception as e:
            error_str = str(e).lower()
            if "pattern day trading" in error_str or "40310100" in error_str:
                self._pdt_locked = True
                logger.error("  Step 8: PDT REJECTED — locking all orders until tomorrow")
                return EntrySubmissionResult(
                    submitted=False,
                    block_reason="pdt_rejected_at_submit",
                )
            # Typed so post-hoc analysis can tell a ConnectionError apart
            # from a validation error or anything else. Keep the full
            # exc_info in logs; block_reason is the structured handle.
            etype = type(e).__name__
            logger.error(f"  Step 8 FAILED ({etype}): {e}", exc_info=True)
            return EntrySubmissionResult(
                submitted=False,
                block_reason=f"submit_exception: {etype}",
            )

    def _dispatch_entry_order(
        self,
        order,
        _entry_meta: dict,
        profile_name: str,
        trade_id: str,
    ) -> EntrySubmissionResult:
        """D3: Shared post-create_order dispatch path. Both legacy
        _submit_entry_order and the new pipeline's
        _submit_new_pipeline_entry call this after create_order
        returns. Handles shadow vs live divert, _trade_id_map
        seeding (with correct timing per pipeline), single-shot
        submission (no retries — failures fall through to caller's
        except), _last_entry_time update, and exception
        classification (PDT vs other) on the inner errors that
        happen post-create.

        The outer except — PDT detection + classification — stays
        at the caller (legacy _submit_entry_order) because PDT
        rejection raises BEFORE this helper if create_order itself
        triggers it; the typical post-submit PDT case routes through
        submit_order's exception which this helper re-raises for the
        caller's outer except to classify.
        """
        # Shadow Mode divert. Ordering differs from live: we write
        # _trade_id_map BEFORE dispatching because the simulator
        # invokes on_filled_order synchronously, and the callback
        # pops from _trade_id_map. Live mode writes AFTER
        # submit_order returns because Alpaca's id isn't known
        # until then. Both paths converge on the same observable
        # state by function return.
        # Shadow divert — gated on the instance attribute set at
        # __init__. Tests may instantiate minimal stubs via
        # V2Strategy.__new__ without running __init__; fall back
        # to "live" for those (explicit default > KeyError).
        if getattr(self, "_execution_mode", "live") == "shadow":
            # Pre-seed _trade_id_map before dispatching because the
            # simulator invokes on_filled_order SYNCHRONOUSLY and
            # the callback pops from the map. Live mode writes
            # AFTER submit_order returns (Alpaca id only known
            # then). Both paths converge on the same observable
            # state by function return.
            import uuid as _uuid_shadow
            _shadow_id_pre = f"shadow-{_uuid_shadow.uuid4()}"
            self._trade_id_map[_shadow_id_pre] = _entry_meta
            self._last_entry_time[profile_name] = datetime.now(timezone.utc)
            try:
                shadow_id = self._shadow_sim.submit_entry(
                    order, profile_name, trade_id,
                    preassigned_id=_shadow_id_pre,
                )
            except Exception:
                # Roll back the map entry on simulator error. The
                # cooldown is left set (strictly safer to over-
                # restrict than under — mirrors the inner-try
                # rollback policy in the live path below).
                self._trade_id_map.pop(_shadow_id_pre, None)
                raise
            if shadow_id is None:
                # Quote unavailable — treat like a submit_exception.
                self._trade_id_map.pop(_shadow_id_pre, None)
                logger.warning(
                    f"  Step 8: SHADOW ENTRY {trade_id[:8]} aborted "
                    "— quote unavailable"
                )
                return EntrySubmissionResult(
                    submitted=False,
                    block_reason="shadow_quote_unavailable",
                    trade_id=trade_id,
                )
            quantity = _entry_meta["quantity"]
            right = _entry_meta["direction"]
            strike = _entry_meta["strike"]
            logger.info(
                f"  Step 8: SHADOW ORDER {trade_id[:8]} buy "
                f"{quantity}x {right} ${strike} "
                f"(cooldown started)"
            )
            return EntrySubmissionResult(submitted=True, trade_id=trade_id)

        # Live path — unchanged from pre-shadow behavior.
        self.submit_order(order)
        # Prompt 30 Commit B: keyed EXCLUSIVELY by the Alpaca id.
        # Lumibot mutates order.identifier inside submit_order
        # (alpaca.py:939 `order.set_identifier(response.id)`).
        # Post-30B the python-id side of the dual-keyed map is
        # gone so GC-reuse collisions are no longer a concern.
        # If submit_order raised before Lumibot mutated the
        # identifier, the write never happened -- no leak to
        # clean up in the except branch below.
        _alpaca_id_30b = self._alpaca_id(order)
        if _alpaca_id_30b is None:
            logger.warning(
                f"  Step 8: entry for {trade_id[:8]} submitted but "
                "order.identifier is not a valid string -- "
                "on_filled_order callback will not match this trade. "
                "Manual DB reconciliation may be needed."
            )
            # Distinct from a broker reject: the order may actually
            # be live at Alpaca, we just can't match a callback to
            # it. Flag so the caller's signal row is attributed
            # correctly and the UI doesn't double-count.
            return EntrySubmissionResult(
                submitted=False,
                block_reason="invalid_alpaca_id",
                trade_id=trade_id,
            )
        # S2.1 (Prompt 34 Commit C): nest a cleanup try around the
        # three-write sequence (map + cooldown + log). submit_order
        # already succeeded at this point -- the order IS at
        # Alpaca. If anything raises between the map write and the
        # success return, the outer except branch will classify it
        # into a submit_exception: <Type> block_reason, but
        # WITHOUT this inner try the map entry leaks and the
        # cooldown stays unset. Cleanup here pops the map entry so
        # the fill callback takes the "unknown order id" no-op path
        # and reconcile_positions handles the ghost at broker.
        try:
            self._trade_id_map[_alpaca_id_30b] = _entry_meta
            # Record cooldown on submission, not on fill -- prevents
            # multiple pending orders. Key by profile_name to match
            # the read-side in Step 5b.
            self._last_entry_time[profile_name] = datetime.now(timezone.utc)
            quantity = _entry_meta["quantity"]
            right = _entry_meta["direction"]
            strike = _entry_meta["strike"]
            limit_price = _entry_meta.get("estimated_price", 0.0)
            logger.info(
                f"  Step 8: ORDER {trade_id[:8]} buy {quantity}x "
                f"{right} ${strike} limit=${limit_price:.2f} "
                f"(cooldown started)"
            )
            return EntrySubmissionResult(submitted=True, trade_id=trade_id)
        except Exception as _inner_e:
            # Roll back the map entry so the fill callback doesn't
            # match a half-written state. _last_entry_time is NOT
            # rolled back -- leaving a stale cooldown is strictly
            # safer than unsetting it.
            self._trade_id_map.pop(_alpaca_id_30b, None)
            logger.warning(
                f"  Step 8: exception after successful submit_order "
                f"for {trade_id[:8]} -- rolled back map entry "
                f"alpaca_id={_alpaca_id_30b[:12]}... "
                f"({type(_inner_e).__name__}: {_inner_e}). The order "
                "may be live at Alpaca with no local bookkeeping; "
                "check broker dashboard / reconcile_positions."
            )
            # Re-raise so the caller's outer except classifies this
            # into a submit_exception: <Type> block_reason.
            raise

    def _submit_new_pipeline_entry(
        self,
        contract,
        proposed_contracts: int,
        setup,
        preset,
        snapshot,
        decision,
        entry_underlying_price: float,
    ) -> EntrySubmissionResult:
        """D3: New-pipeline entry submission.

        Mirrors the legacy _submit_entry_order pre-half but for the
        BasePreset surface:
          - ContractSelection.expiration is datetime.date (legacy is
            string); pass through to Asset directly, ISO-format for
            _entry_meta storage.
          - limit_price = round(estimated_premium, 2) since
            ContractSelection has no bid/ask. The midpoint was
            computed at chain-build time by chain_adapter; staleness
            window is small (chain build → contract selection →
            submission). See PHASE_1A_FOLLOWUPS.md "limit_price uses
            chain-build estimated_premium in D3".
          - confidence_score = setup.score (no Scorer in new pipeline;
            matches D2's confidence input).
          - profile = preset (BasePreset instance, not BaseProfile).

        D4: entry_underlying_price is captured at chain-build time
        (chain.underlying_price) and persisted to the trades row so
        the D4 exit loop can reconstruct a Position dataclass on
        subprocess restart. Required because Position.__post_init__
        rejects entry_underlying_price <= 0; pre-D4 trades created
        without this field cannot participate in the new exit loop
        and remain managed by TradeManager (legacy path).

        Outer try/except classifies PDT vs other rejections — same
        shape as _submit_entry_order's outer except.
        """
        trade_id = str(uuid4())
        asset = Asset(
            symbol=contract.symbol, asset_type="option",
            expiration=contract.expiration,
            strike=contract.strike, right=contract.right,
        )
        try:
            limit_price = round(contract.estimated_premium, 2)
            order = self.create_order(
                asset, proposed_contracts, side="buy_to_open",
                limit_price=limit_price, time_in_force="day",
            )
            logger.info(
                f"  Step 8 [{preset.name}]: limit=${limit_price:.2f} "
                f"(estimated_premium=${contract.estimated_premium:.2f})"
            )
            _entry_meta = {
                "trade_id": trade_id,
                "profile_id": self._profile_config.name,
                "symbol": contract.symbol,
                "direction": contract.right,
                "strike": contract.strike,
                # New pipeline stores ISO string for symmetry with
                # legacy on_filled_order, which strptime-parses
                # entry["expiration"] as "%Y-%m-%d".
                "expiration": contract.expiration.isoformat(),
                "quantity": proposed_contracts,
                "estimated_price": limit_price,
                "setup_type": setup.setup_type,
                "confidence_score": setup.score,
                "regime": snapshot.regime.value,
                "vix_level": getattr(snapshot, "vix_level", None),
                "is_same_day": (
                    contract.expiration
                    == datetime.now(timezone.utc).date()
                ),
                "profile": preset,
                "profile_name": preset.name,
                "setup_score": setup.score,
                # D4: persisted by on_filled_order's BUY-INSERT into
                # trades.entry_underlying_price. The exit loop reads
                # the column back and rejects rows where the value
                # is NULL or <= 0 (pre-D4 trades).
                "entry_underlying_price": entry_underlying_price,
            }
            return self._dispatch_entry_order(
                order, _entry_meta, preset.name, trade_id,
            )
        except Exception as e:
            error_str = str(e).lower()
            if "pattern day trading" in error_str or "40310100" in error_str:
                self._pdt_locked = True
                logger.error(
                    "  Step 8 [%s]: PDT REJECTED — locking all orders",
                    preset.name,
                )
                return EntrySubmissionResult(
                    submitted=False,
                    block_reason="pdt_rejected_at_submit",
                    trade_id=trade_id,
                )
            etype = type(e).__name__
            logger.error(
                "  Step 8 [%s] FAILED (%s): %s",
                preset.name, etype, e, exc_info=True,
            )
            return EntrySubmissionResult(
                submitted=False,
                block_reason=f"submit_exception: {etype}",
                trade_id=trade_id,
            )

    def _clear_stale_exit_lock(self, trade_id, pos) -> bool:
        """Force-clear the exit lock if the submitted-at timestamp is
        older than STALE_EXIT_LOCK_MINUTES.

        Returns True if the lock was cleared (caller should `continue`
        the current iteration — don't submit a new exit this cycle).
        Returns False if no action was taken (lock is fresh, not set,
        or no timestamp recorded).

        Prompt 20 Commit C. Fallback for cases where Lumibot's
        on_canceled_order didn't fire: websocket reconnect, Lumibot
        internal bug, process restart between cancel and callback
        delivery, rejected orders (which hit the ERROR_ORDER path,
        not on_canceled_order).

        Does not re-submit immediately. Flipping pending_exit=False
        drops the position from get_pending_exits() for this
        iteration. Next iteration's Step 9 re-evaluates exit
        conditions — if the thesis still says exit, it'll flip
        pending_exit back on and Step 10 submits fresh.
        """
        if not pos.pending_exit_order_id or not pos.pending_exit_submitted_at:
            return False

        age_minutes = (
            datetime.now(timezone.utc) - pos.pending_exit_submitted_at
        ).total_seconds() / 60.0
        if age_minutes <= STALE_EXIT_LOCK_MINUTES:
            return False

        logger.warning(
            f"  Step 10: STALE exit lock for {trade_id[:8]} — submitted "
            f"{age_minutes:.1f}min ago, clearing lock. If the order was "
            "actually live at the broker, expect a duplicate-submit "
            "warning on the next iteration's submit_order path."
        )
        self._trade_id_map.pop(pos.pending_exit_order_id, None)
        pos.pending_exit_order_id = None
        pos.pending_exit_submitted_at = None
        pos.pending_exit = False
        pos.pending_exit_reason = ""
        pos.exit_retry_count = 0
        return True

    def _alpaca_id(self, order):
        """Return order.identifier if it looks like a usable string
        (non-empty), else None. Prompt 30 Commit A helper -- Lumibot
        always assigns SOME identifier (a uuid4 hex at construction,
        replaced by the Alpaca server id after submit_order returns)
        but we stay defensive against unknown future broker shapes."""
        val = getattr(order, "identifier", None)
        if isinstance(val, str) and val:
            return val
        return None

    def _pop_order_entry(self, order):
        """Pop the entry associated with ``order`` from _trade_id_map.
        Keyed by the Alpaca server id Lumibot stamps onto
        order.identifier inside submit_order. Returns the entry (dict
        for BUYs, str for SELLs) or None if the id was not present.

        Prompt 30 Commit B simplification of _dual_pop_order_entry
        (Commit A): the python-id fallback is gone because writes no
        longer populate it. If order.identifier is not a usable
        string (extremely unlikely -- Lumibot always assigns one),
        the pop no-ops and returns None.
        """
        alpaca_id = self._alpaca_id(order)
        if alpaca_id is None:
            return None
        return self._trade_id_map.pop(alpaca_id, None)

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

            # Get current option price for limit order. Three-tier
            # fallback (Prompt 29):
            #   1. Fresh quote from get_last_price  -> use as-is, quiet.
            #   2. Last known mark from run_cycle   -> WARNING, note the
            #      degraded source so operators can grep it.
            #   3. 50% of entry (pre-fix floor)     -> CRITICAL; fires
            #      only for freshly-added or reloaded positions with no
            #      mark observation yet, AND a simultaneous data outage.
            # Each step drops to the next only when the prior returns
            # unusable data (None or <= 0 — Alpaca occasionally returns
            # 0.0 on illiquid contracts and that is not a valid price).
            current_price = self.get_last_price(asset)
            last_mark = getattr(pos, "last_mark_price", None)
            if current_price and current_price > 0:
                limit_price = round(current_price, 2)
            elif last_mark and last_mark > 0:
                limit_price = round(last_mark, 2)
                logger.warning(
                    f"  Step 10: current price unavailable for {trade_id[:8]}, "
                    f"using last known mark ${limit_price:.2f} "
                    f"(entry was ${pos.entry_price:.2f})"
                )
            else:
                # Final fallback: 50% below entry. Only fires when we
                # have NO recent mark data -- typically a freshly-
                # entered position hitting an instant exit, or a
                # reloaded position during a ThetaData outage before
                # any valid fetch. Aggressive give-up is intentional:
                # "get out at any reasonable price" beats holding
                # through a data outage.
                limit_price = round(pos.entry_price * 0.50, 2)
                logger.critical(
                    f"  Step 10: no price data for {trade_id[:8]} "
                    f"(current=None, last_mark=None), using 50%-of-entry "
                    f"fallback ${limit_price:.2f} -- DEGRADED EXIT"
                )

            order = self.create_order(
                asset, pos.quantity, side="sell_to_close",
                limit_price=limit_price, time_in_force="day",
            )
            # Shadow Mode divert for exits. Same pre-seed pattern as
            # entries: write _trade_id_map BEFORE the simulator
            # dispatches on_filled_order synchronously. If the quote
            # is unavailable, the exit is held exactly like an
            # "insufficient" live rejection (pending_exit cleared,
            # re-evaluation next cycle). getattr fallback mirrors
            # the entry divert — tests may stub V2Strategy without
            # running __init__.
            if getattr(self, "_execution_mode", "live") == "shadow":
                import uuid as _uuid_shadow_exit
                _shadow_id_pre = f"shadow-{_uuid_shadow_exit.uuid4()}"
                self._trade_id_map[_shadow_id_pre] = trade_id
                pos.pending_exit_order_id = _shadow_id_pre
                try:
                    shadow_id = self._shadow_sim.submit_exit(
                        order, trade_id, preassigned_id=_shadow_id_pre,
                    )
                except Exception:
                    self._trade_id_map.pop(_shadow_id_pre, None)
                    pos.pending_exit_order_id = None
                    raise
                if shadow_id is None:
                    # Quote unavailable — clear pending_exit so the
                    # next iteration re-evaluates. Matches the
                    # "insufficient" branch below in shape.
                    self._trade_id_map.pop(_shadow_id_pre, None)
                    pos.pending_exit = False
                    pos.pending_exit_reason = ""
                    pos.pending_exit_order_id = None
                    pos.exit_retry_count = 0
                    logger.warning(
                        f"  Step 10: SHADOW EXIT {trade_id[:8]} aborted "
                        "— quote unavailable, re-evaluating next cycle"
                    )
                    return
                pos.exit_retry_count = 0
                pos.pending_exit_submitted_at = datetime.now(timezone.utc)
                logger.info(
                    f"  Step 10: SHADOW EXIT {trade_id[:8]} "
                    f"{pos.symbol} ${pos.strike} x{pos.quantity} "
                    f"reason={pos.pending_exit_reason}"
                )
                return

            # Live path — unchanged from pre-shadow behavior.
            self.submit_order(order)
            # Prompt 30 Commit B: write AFTER submit_order so the key
            # is the Alpaca server id. pos.pending_exit_order_id gets
            # the same string; staleness/abandonment pop by that
            # string. If submit_order raised, nothing is written --
            # the except branch below no-ops on the map cleanup.
            _alpaca_id_30b = self._alpaca_id(order)
            if _alpaca_id_30b is not None:
                self._trade_id_map[_alpaca_id_30b] = trade_id
                pos.pending_exit_order_id = _alpaca_id_30b
            else:
                # Finding 3: Lumibot should always stamp an identifier
                # after submit_order returns, but stay defensive. The
                # pre-fix code left pending_exit_order_id=None here,
                # which defeated BOTH recovery paths:
                #   - _clear_stale_exit_lock requires both order_id AND
                #     submitted_at truthy (returns False otherwise)
                #   - Block 3 dedup at v2_strategy:424 requires order_id
                #     truthy (skipped otherwise, so every cycle re-submits)
                # Fix: assign a local sentinel keyed in _trade_id_map so
                # Block 3 correctly dedups AND stale-lock becomes reachable.
                # "invalid-id-" prefix guarantees no collision with real
                # Alpaca identifiers (lowercase hex UUID format).
                import uuid as _uuid
                _sentinel = f"invalid-id-{_uuid.uuid4()}"
                self._trade_id_map[_sentinel] = trade_id
                pos.pending_exit_order_id = _sentinel
                logger.warning(
                    f"  Step 10: exit for {trade_id[:8]} submitted but "
                    "order.identifier is not a valid string -- using "
                    f"sentinel {_sentinel[:24]}... Lumibot callbacks will "
                    "NOT match this order. Recovery paths: "
                    "5-retry abandonment (~5min) OR "
                    f"{STALE_EXIT_LOCK_MINUTES}min stale-lock timeout, "
                    "whichever fires first. If this warning appears, "
                    "check the Alpaca dashboard -- the order may still "
                    "be live at the broker."
                )
            # Reset the transient-retry ladder on clean submission. The ladder
            # is meant to cap retries within one submission attempt — without
            # this reset, a position that hit 4 transient errors then
            # succeeded would be one transient error away from abandonment
            # on any future re-submission (e.g. after the order expires
            # server-side). PDT / insufficient paths already reset above.
            # Prompt 19.
            pos.exit_retry_count = 0
            # Prompt 20 Commit C: mark the moment submit_order accepted
            # the order. Step 10's stale-lock check uses this to decide
            # whether to force-clear the Block 3 lock when on_canceled_order
            # silently fails (websocket drop, Lumibot bug, process restart).
            # Set AFTER submit_order returns cleanly — if submit_order
            # raises, the transient-error branch runs and we leave the
            # timestamp untouched (stays at whatever prior attempt left
            # it, typically None). STALE_EXIT_LOCK_MINUTES is the window.
            pos.pending_exit_submitted_at = datetime.now(timezone.utc)
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
                    # Prompt 20 Commit A: clear the Block-3 lock on
                    # abandonment. Without this, pending_exit_order_id
                    # stays set and — if _trade_id_map still contains
                    # the id — Block 3 at line ~366 silently skips the
                    # position forever, preventing any future exit
                    # attempt. Pop the map entry (defensive: the id
                    # may already be gone if some other path cleaned
                    # it) and zero the field. Also reset the retry
                    # counter so the next exit attempt (minutes/hours
                    # later, after the next Step 9 evaluation) gets a
                    # fresh 5-retry ladder instead of starting at 5.
                    if pos.pending_exit_order_id:
                        self._trade_id_map.pop(pos.pending_exit_order_id, None)
                    pos.pending_exit_order_id = None
                    pos.exit_retry_count = 0
                    pos.pending_exit_submitted_at = None   # Prompt 20 Commit C
                    logger.critical(f"  Step 10: EXIT ABANDONED after 5 retries for "
                                    f"{trade_id[:8]} — MANUAL REVIEW REQUIRED")
                else:
                    logger.error(f"  Step 10 EXIT FAILED for {trade_id[:8]} "
                                 f"(retry {pos.exit_retry_count}/5): {e}")

    def _log_v2_signal(self, scored, decision, snapshot, profile_name: str = ""):
        """Write V2 signal log entry for every evaluation.

        Falls back to the sentinel "scanner" when profile_name is empty
        rather than the old `scored.setup_type` fallback. Setup-type
        values ("momentum", "mean_reversion", etc.) pollute any
        profile_name grouping — scanner rejection rows would appear as
        though the momentum profile had evaluated them.
        """
        from backend.database import write_v2_signal_log
        factors = {f.name: f.raw_value for f in scored.factors if f.status == "active"}
        write_v2_signal_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profile_name": profile_name if profile_name else "scanner",
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
            # institutional_flow removed in Prompt 25 — write_v2_signal_log
            # writes NULL for the column when the key is absent.
            "historical_perf": factors.get("historical_perf"),
            "sentiment": factors.get("sentiment"),
            "time_of_day_score": factors.get("time_of_day"),
            "threshold_label": scored.threshold_label,
            "entered": decision.enter,
            "trade_id": None,  # Set after order fills
            "block_reason": decision.reason if not decision.enter else None,
            # Shadow Mode: tag the row with the mode the subprocess is
            # running in so downstream P&L / learning queries can filter.
            "execution_mode": config.EXECUTION_MODE,
        })

    def _log_scanner_rejection(self, scan_results, snapshot, macro_ctx=None):
        """Log one signal entry per symbol when all setups score 0.
        Shows the best setup's rejection reason so the UI has data to review.

        macro_ctx: optional — callers in on_trading_iteration should pass the
        cached snapshot so the scorer call here reuses it. Without it, each
        rejected symbol would trigger a fresh snapshot_macro_context() call
        inside scorer.score (the fail-safe fallback in _resolve_ctx), which
        adds one avoidable SQLite read per symbol per cycle.
        """
        from backend.database import write_v2_signal_log
        for result in scan_results:
            # Build block_reason from all setup rejection reasons
            reasons = []
            for s in result.setups:
                if s.reason:
                    reasons.append(f"{s.setup_type}: {s.reason}")
            block_reason = " | ".join(reasons[:4]) if reasons else "all setups scored 0"

            # Score the best setup through the scorer even though it scored 0
            # so we get real factor values for the signal log. profile_name
            # is the distinct sentinel "scanner" — these rows record a
            # scanner rejection, not a profile evaluation, so grouping
            # by profile_name must not lump them in with any real profile.
            best = max(result.setups, key=lambda s: s.score) if result.setups else None
            if best:
                profile_name = "scanner"
                try:
                    from scanner.sentiment import get_sentiment
                    sentiment = get_sentiment(result.symbol)
                    scored = self._scorer.score(
                        result.symbol, best, snapshot,
                        sentiment_score=sentiment.score,
                        macro_ctx=macro_ctx,
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
                        # institutional_flow removed in Prompt 25.
                        "historical_perf": factors.get("historical_perf"),
                        "sentiment": factors.get("sentiment"),
                        "time_of_day_score": factors.get("time_of_day"),
                        "threshold_label": "scanner_reject",
                        "entered": False,
                        "trade_id": None,
                        "block_reason": block_reason,
                        "execution_mode": config.EXECUTION_MODE,
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
                        # institutional_flow removed in Prompt 25.
                        "historical_perf": None,
                        "sentiment": None, "time_of_day_score": None,
                        "threshold_label": "scanner_reject",
                        "entered": False, "trade_id": None,
                        "block_reason": block_reason,
                        "execution_mode": config.EXECUTION_MODE,
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
            # Filter by every symbol this subprocess scans — not just
            # self.symbol — so a QQQ position opened under the SPY
            # subprocess gets re-registered with the trade manager on
            # restart. Without this, secondary-symbol positions were
            # orphaned and only picked up by _cleanup_stale_trades or
            # reconcile at expiration (no trailing stop, no profile exits
            # in the interim).
            placeholders = ",".join("?" for _ in self._scan_symbols)
            # Shadow Mode: a live subprocess must only reload live
            # positions on restart, and a shadow subprocess only
            # shadow positions. Mixing would e.g. let a live restart
            # try to exit a shadow-ghost position against Alpaca
            # (which doesn't know about it) and crash the reconcile.
            _mode_reload = getattr(self, "_execution_mode", "live")
            rows = conn.execute(
                f"""SELECT id, symbol, direction, strike, expiration, quantity,
                           entry_price, confidence_score, setup_type, profile_name,
                           entry_date
                    FROM trades WHERE status = 'open'
                      AND execution_mode = ?
                      AND symbol IN ({placeholders})""",
                (_mode_reload, *self._scan_symbols),
            ).fetchall()
            conn.close()

            for row in rows:
                # Prompt 16: resolve the owning profile by profile_name (stored
                # at BUY fill) rather than guessing from setup_type. Aggregator
                # profiles (scalp_0dte / swing / tsla_swing) accept multiple
                # setup_types, so setup_type alone can't identify them — the
                # old code sometimes bound compression_breakout trades opened
                # by scalp_0dte to swing instead, applying the wrong exit
                # rules, max_hold, and trailing stop.
                setup = row["setup_type"] or "momentum"
                profile_name = row["profile_name"] if "profile_name" in row.keys() else None

                # Primary: exact profile_name match — new rows written post-migration.
                profile = self._profiles.get(profile_name) if profile_name else None

                # Fallback 1: setup_type match — works for scalar profiles
                # (momentum / mean_reversion / catalyst) and for pre-migration
                # rows whose setup_type equals a profile key.
                if profile is None:
                    profile = self._profiles.get(setup)

                # Fallback 2: best-effort aggregator pick. Only hit by legacy
                # rows with NULL profile_name AND a setup_type that isn't a
                # direct profile key (e.g. compression_breakout under a
                # subprocess that only has scalp_0dte active). Log a WARNING
                # so we notice if these keep showing up after migration —
                # they shouldn't for new trades.
                if profile is None:
                    for candidate in ("scalp_0dte", "swing", "tsla_swing", "momentum"):
                        if candidate in self._profiles:
                            profile = self._profiles[candidate]
                            logger.warning(
                                f"V2Strategy: reload of {row['id'][:8]} {row['symbol']} "
                                f"fell back to {candidate} profile — no profile_name "
                                f"stored and setup_type={setup!r} not a direct match"
                            )
                            break

                if profile is None:
                    logger.error(
                        f"V2Strategy: cannot resolve profile for reloaded trade "
                        f"{row['id'][:8]} — no profile_name, setup_type={setup!r}, "
                        f"active profiles={list(self._profiles.keys())}. Skipping."
                    )
                    continue

                self._trade_manager.add_position(
                    trade_id=row["id"],
                    symbol=row["symbol"],
                    profile=profile,
                    expiration=datetime.strptime(row["expiration"], "%Y-%m-%d").date(),
                    entry_time=datetime.fromisoformat(row["entry_date"]) if row["entry_date"] else datetime.now(timezone.utc),
                    entry_price=row["entry_price"] or 0.0,
                    quantity=row["quantity"],
                    confidence=row["confidence_score"] or 0.0,
                    setup_type=setup,
                    strike=row["strike"] or 0.0,
                    right=row["direction"] or "",
                )
            logger.info(f"V2Strategy: reloaded {len(rows)} open positions from DB")
        except Exception as e:
            logger.error(f"V2Strategy: failed to reload open positions: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────
    # C5b: BasePreset orchestrator pipeline (signal_only mode)
    # ─────────────────────────────────────────────────────────────

    def _build_option_chain_for_new_preset(self, symbol: str, direction: str):
        """Build an OptionChain for the configured new preset's
        strike-selection step.

        Uses the preset's DTE_MIN / DTE_MAX class attributes to filter
        expirations. Returns None on any data fetch failure (caller
        treats as 'skip this entry').

        The new pipeline calls evaluate_entry FIRST (which determines
        direction), THEN this builder, THEN select_contract — chain is
        right-filtered to call/put per the direction.
        """
        from data.chain_adapter import (
            build_option_chain,
            expirations_in_dte_window,
            snapshot_underlying_price,
        )

        preset = self._new_preset
        today_et = datetime.now(ZoneInfo("America/New_York")).date()
        right = "call" if direction == "bullish" else "put"

        try:
            expirations = expirations_in_dte_window(
                self._client, symbol,
                min_dte=preset.DTE_MIN, max_dte=preset.DTE_MAX,
                today=today_et,
            )
        except Exception:
            logger.exception(
                "%s: expirations fetch failed for %s",
                preset.name, symbol,
            )
            return None

        if not expirations:
            return None

        # Pick the nearest expiration in the window. expirations_in_dte_window
        # returns sorted ascending by DTE.
        exp_str, exp_date, _dte = expirations[0]

        try:
            underlying_price = snapshot_underlying_price(self._client, symbol)
        except Exception:
            logger.exception(
                "%s: underlying price fetch failed for %s",
                preset.name, symbol,
            )
            return None

        try:
            return build_option_chain(
                self._client, symbol, exp_str, exp_date,
                right_filter=right,
                underlying_price=underlying_price,
            )
        except Exception:
            logger.exception(
                "%s: chain build failed for %s",
                preset.name, symbol,
            )
            return None

    def _rebind_preset_macro_fetcher(self, macro_ctx):
        """D4: rebind self._new_preset._macro_fetcher to a fresh closure
        over this iteration's MacroContext.

        Pre-D4 the rebind happened inline at the top of
        _run_new_preset_iteration. D4 hoists it into on_trading_iteration
        (before both exit and entry helpers) so the exit loop sees the
        same macro_fetcher the entry loop will see this cycle.

        No-op when self._new_preset is None (legacy preset path).

        Idempotent: safe to call more than once per iteration. Tests
        that invoke _run_new_preset_iteration / _run_new_preset_exit_iteration
        directly without going through on_trading_iteration are
        responsible for their own rebind, OR they rely on the
        placeholder fetcher set in initialize() returning empty lists
        — which it does for the None-macro_ctx case (matches the
        adapter's behavior).
        """
        if self._new_preset is None:
            return
        self._new_preset._macro_fetcher = (
            macro_context_to_event_fetcher(macro_ctx)
        )

    def _build_position_from_trade_row(self, row, current_quote: float):
        """D4: reconstruct a frozen Position from a trades-row dict.

        `row` is a dict (sqlite3.Row converted via dict()) with the
        columns the SELECT in _run_new_preset_exit_iteration projects:
          id, profile_id, symbol, direction, strike, expiration,
          quantity, entry_price, entry_date, entry_underlying_price.

        Why a stub ContractSelection: BasePreset.evaluate_exit reads
        position.contract for `right` (call/put), `expiration` (date),
        and the symbol passes through position.symbol. SwingPreset's
        evaluate_exit body (verified) does NOT read target_delta /
        estimated_premium / dte from contract — those are entry-time
        artifacts of select_contract. A 0.0 target_delta and
        entry-equivalent estimated_premium / computed dte are safe
        stubs because the ContractSelection dataclass has no validation
        enforcing realism, and downstream readers in evaluate_exit
        scope ignore these fields.

        Peak premium is read from self._peak_premium_by_trade_id and
        clamped to >= current_quote (the high-water mark can only
        increase). Pre-existing key absent => seed with current_quote.

        Raises ValueError if row's entry_underlying_price <= 0; the
        caller (exit loop) filters those rows out at SELECT time, so
        this is a defensive guard that should never fire in practice.
        """
        from datetime import date as _date_cls
        from profiles.base_preset import ContractSelection, Position

        trade_id = row["id"]
        symbol = row["symbol"]
        right = row["direction"]
        strike = float(row["strike"])
        expiration_date = datetime.strptime(
            row["expiration"], "%Y-%m-%d",
        ).date()
        contracts = int(row["quantity"])
        entry_premium = float(row["entry_price"])
        entry_underlying = float(row["entry_underlying_price"])

        # entry_date is ISO-8601 in UTC (on_filled_order writes
        # datetime.now(timezone.utc).isoformat()). fromisoformat
        # round-trips the tz-aware value; assert tz-aware so
        # Position.__post_init__ doesn't reject.
        entry_time = datetime.fromisoformat(row["entry_date"])
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)

        # Peak high-water: monotone non-decreasing. Seed with the
        # entry premium on first observation (rather than the live
        # quote) so a position that opens deeply ITM and immediately
        # rallies still has a meaningful trailing-stop reference
        # rooted at entry. Subsequent cycles ratchet up via max().
        prior_peak = self._peak_premium_by_trade_id.get(
            trade_id, entry_premium,
        )
        peak = max(prior_peak, current_quote)
        self._peak_premium_by_trade_id[trade_id] = peak

        today = _date_cls.today()
        dte = (expiration_date - today).days

        contract = ContractSelection(
            symbol=symbol,
            right=right,
            strike=strike,
            expiration=expiration_date,
            target_delta=0.0,
            estimated_premium=entry_premium,
            dte=dte,
        )

        return Position(
            trade_id=trade_id,
            symbol=symbol,
            contract=contract,
            entry_time=entry_time,
            entry_premium_per_share=entry_premium,
            entry_underlying_price=entry_underlying,
            peak_premium_per_share=peak,
            current_premium_per_share=current_quote,
            contracts=contracts,
        )

    def _submit_new_pipeline_exit(self, trade_id: str, position, reason: str) -> bool:
        """D4: submit a sell-to-close limit order for a new-pipeline
        position.

        Parallel to legacy _submit_exit_order but works against a
        frozen Position (no mutable pos.pending_exit_* fields).
        Tracks per-trade exit state in
        self._new_preset_pending_exits — a parallel dict to the
        legacy ManagedPosition fields.

        Quote three-tier fallback (matches legacy):
          1. get_last_price(option_asset) — use as-is
          2. position.peak_premium_per_share — last in-memory mark
          3. 50% of entry_premium — degraded "get out at any price"

        Returns True on successful submission, False on submit-time
        rejection (PDT, insufficient, exception). False does NOT
        retain a pending-exit entry; the next iteration's exit loop
        will re-evaluate and may re-submit if the trigger is still
        warranted.
        """
        right_str = "put" if position.contract.right in ("PUT", "bearish", "put") else "call"
        asset = Asset(
            symbol=position.symbol, asset_type="option",
            expiration=position.contract.expiration,
            strike=position.contract.strike,
            right=right_str,
        )

        try:
            current_price = self.get_last_price(asset)
        except Exception:
            current_price = None
        last_mark = position.peak_premium_per_share
        if current_price and current_price > 0:
            limit_price = round(current_price, 2)
        elif last_mark and last_mark > 0:
            limit_price = round(last_mark, 2)
            logger.warning(
                "  Step 9' [%s]: current price unavailable for %s, "
                "using last known mark $%.2f (entry was $%.2f)",
                self._new_preset.name, trade_id[:8],
                limit_price, position.entry_premium_per_share,
            )
        else:
            limit_price = round(
                position.entry_premium_per_share * 0.50, 2,
            )
            logger.critical(
                "  Step 9' [%s]: no price data for %s "
                "(current=None, last_mark=None), using 50%%-of-entry "
                "fallback $%.2f -- DEGRADED EXIT",
                self._new_preset.name, trade_id[:8], limit_price,
            )

        try:
            order = self.create_order(
                asset, position.contracts, side="sell_to_close",
                limit_price=limit_price, time_in_force="day",
            )

            # Shadow Mode divert. Mirrors legacy _submit_exit_order:
            # pre-seed _trade_id_map BEFORE simulator dispatch
            # because shadow on_filled_order fires synchronously.
            if getattr(self, "_execution_mode", "live") == "shadow":
                import uuid as _uuid_shadow_exit
                _shadow_id_pre = f"shadow-{_uuid_shadow_exit.uuid4()}"
                self._trade_id_map[_shadow_id_pre] = trade_id
                self._new_preset_pending_exits[trade_id] = {
                    "alpaca_id": _shadow_id_pre,
                    "submitted_at": datetime.now(timezone.utc),
                    "reason": reason,
                }
                try:
                    shadow_id = self._shadow_sim.submit_exit(
                        order, trade_id, preassigned_id=_shadow_id_pre,
                    )
                except Exception:
                    self._trade_id_map.pop(_shadow_id_pre, None)
                    self._new_preset_pending_exits.pop(trade_id, None)
                    raise
                if shadow_id is None:
                    self._trade_id_map.pop(_shadow_id_pre, None)
                    self._new_preset_pending_exits.pop(trade_id, None)
                    logger.warning(
                        "  Step 9' [%s]: SHADOW EXIT %s aborted "
                        "— quote unavailable, re-evaluating next cycle",
                        self._new_preset.name, trade_id[:8],
                    )
                    return False
                logger.info(
                    "  Step 9' [%s]: SHADOW EXIT %s %s $%s x%d "
                    "reason=%s",
                    self._new_preset.name, trade_id[:8],
                    position.symbol, position.contract.strike,
                    position.contracts, reason,
                )
                return True

            # Live path.
            self.submit_order(order)
            _alpaca_id_30b = self._alpaca_id(order)
            if _alpaca_id_30b is None:
                # Defensive: matches legacy invalid-id sentinel pattern
                # (Finding 3). Without a usable Alpaca id Lumibot
                # callbacks will not match this order; we can't track
                # the exit. Treat as an immediate failure so the next
                # iteration re-evaluates from scratch.
                logger.warning(
                    "  Step 9' [%s]: exit for %s submitted but "
                    "order.identifier is not a valid string -- "
                    "callbacks will NOT match. Manual reconciliation "
                    "may be needed.",
                    self._new_preset.name, trade_id[:8],
                )
                return False

            self._trade_id_map[_alpaca_id_30b] = trade_id
            self._new_preset_pending_exits[trade_id] = {
                "alpaca_id": _alpaca_id_30b,
                "submitted_at": datetime.now(timezone.utc),
                "reason": reason,
            }
            logger.info(
                "  Step 9' [%s]: EXIT %s %s $%s x%d limit=$%.2f "
                "reason=%s",
                self._new_preset.name, trade_id[:8],
                position.symbol, position.contract.strike,
                position.contracts, limit_price, reason,
            )
            return True
        except Exception as e:
            error_str = str(e).lower()
            if "pattern day trading" in error_str or "40310100" in error_str:
                self._pdt_locked = True
                logger.error(
                    "  Step 9' [%s]: PDT REJECTED exit for %s — "
                    "holding overnight",
                    self._new_preset.name, trade_id[:8],
                )
                return False
            etype = type(e).__name__
            logger.error(
                "  Step 9' [%s] EXIT FAILED for %s (%s): %s",
                self._new_preset.name, trade_id[:8], etype, e,
                exc_info=True,
            )
            return False

    def _handle_new_pipeline_exit_fill(self, trade_id: str, fill_price: float):
        """D4: handle the SELL fill for a new-pipeline trade.

        Parallel to TradeManager.confirm_fill (which no-ops for trades
        not in self._trade_manager._positions — i.e. new-pipeline
        trades).

        Reads the originating exit reason from
        self._new_preset_pending_exits, computes pnl_dollars / pnl_pct
        / hold_minutes / was_day_trade, writes the trades-row UPDATE
        (status='closed', exit_price, exit_date, exit_reason,
        pnl_dollars, pnl_pct, hold_minutes, was_day_trade,
        updated_at), and clears all per-trade orchestrator state:
        _new_preset_pending_exits, _peak_premium_by_trade_id, and the
        thesis_break_streaks entry (per swing_preset.py:378-386's
        orchestrator-cleanup contract — the streak entry must be
        cleared on ANY position close, not just thesis-break exits).

        DB write uses config.DB_PATH (the test fixture monkeypatches
        this). Wrapped in try/except so a DB failure does not corrupt
        in-memory state (the DB row is the source of truth for closed
        trades; if the UPDATE fails we leave it open for a future
        reconcile).
        """
        meta = self._new_preset_pending_exits.pop(trade_id, None)
        if meta is None:
            logger.warning(
                "  Step 9' fill: unknown new-pipeline trade_id %s "
                "(no pending-exit metadata)",
                trade_id[:8],
            )
            return

        reason = meta.get("reason", "unknown")

        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT entry_price, quantity, entry_date "
                "FROM trades WHERE id = ?",
                (trade_id,),
            ).fetchone()
            if row is None:
                logger.error(
                    "  Step 9' fill: trades row not found for %s — "
                    "cannot UPDATE close",
                    trade_id[:8],
                )
                # Still drop in-memory state to prevent leaks.
                self._peak_premium_by_trade_id.pop(trade_id, None)
                self._thesis_break_streaks.pop(trade_id, None)
                return

            entry_price = float(row["entry_price"])
            quantity = int(row["quantity"])
            entry_date_iso = row["entry_date"]

        entry_time = datetime.fromisoformat(entry_date_iso)
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        hold_minutes = max(
            0, int((now_utc - entry_time).total_seconds() / 60),
        )

        pnl_dollars = (fill_price - entry_price) * quantity * 100
        pnl_pct = (
            ((fill_price - entry_price) / entry_price) * 100
            if entry_price > 0 else 0.0
        )
        is_day_trade = (
            entry_time.date() == now_utc.date()
        )

        try:
            with closing(sqlite3.connect(str(DB_PATH))) as conn:
                conn.execute(
                    """UPDATE trades SET
                          status = 'closed',
                          exit_price = ?,
                          exit_date = ?,
                          exit_reason = ?,
                          pnl_dollars = ?,
                          pnl_pct = ?,
                          hold_minutes = ?,
                          was_day_trade = ?,
                          updated_at = ?
                       WHERE id = ?""",
                    (
                        fill_price,
                        now_utc.isoformat(),
                        reason,
                        round(pnl_dollars, 2),
                        round(pnl_pct, 2),
                        hold_minutes,
                        1 if is_day_trade else 0,
                        now_utc.isoformat(),
                        trade_id,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(
                "  Step 9' fill: trades UPDATE failed for %s: %s",
                trade_id[:8], e,
            )

        # Drop all in-memory state for the closed trade.
        self._peak_premium_by_trade_id.pop(trade_id, None)
        self._thesis_break_streaks.pop(trade_id, None)
        self._last_exit_reason[self._new_preset.name] = reason

        logger.info(
            "  Step 9' fill: CLOSED %s entry=$%.2f exit=$%.2f "
            "pnl=%+.1f%% hold=%dmin reason=%s",
            trade_id[:8], entry_price, fill_price,
            pnl_pct, hold_minutes, reason,
        )

    def _run_new_preset_exit_iteration(self, active, snapshot, macro_ctx):
        """D4: BasePreset exit pipeline. Runs BEFORE the entry loop
        each iteration — Step 9' in the trading-iteration sequence.

        Iterates open trades belonging to this profile that have a
        valid entry_underlying_price (pre-D4 trades have NULL and
        are managed by the legacy TradeManager path via
        _trade_manager.run_cycle / _submit_exit_order). For each:
          1. Fetch the current option quote (skip on quote failure)
          2. Build a frozen Position via _build_position_from_trade_row
          3. Filter scanner setups to position.symbol
          4. Build ProfileState from live subprocess + DB
          5. Call preset.evaluate_exit
          6. If should_exit AND no exit currently pending for this
             trade_id, submit via _submit_new_pipeline_exit

        0DTE NotImplementedError: ZeroDteAsymmetricPreset.evaluate_exit
        raises (Phase 1b forces signal_only, so DB returns 0 rows in
        practice). Defensive try/except keeps the loop alive if a
        future change ever surfaces such a row.
        """
        preset = self._new_preset
        if preset is None:
            return

        # Pull open new-pipeline trades from the trades table. Filter:
        #   - status = 'open'
        #   - profile_id = this subprocess's profile name
        #   - execution_mode = current EXECUTION_MODE (D1 invariant)
        #   - entry_underlying_price IS NOT NULL AND > 0 (pre-D4
        #     legacy trades skipped)
        profile_id = self._profile_config.name
        execution_mode = config.EXECUTION_MODE

        try:
            with closing(sqlite3.connect(str(DB_PATH))) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT id, profile_id, symbol, direction, strike,
                              expiration, quantity, entry_price,
                              entry_date, entry_underlying_price
                       FROM trades
                       WHERE status = 'open'
                         AND profile_id = ?
                         AND execution_mode = ?
                         AND entry_underlying_price IS NOT NULL
                         AND entry_underlying_price > 0""",
                    (profile_id, execution_mode),
                ).fetchall()
        except Exception:
            logger.exception(
                "%s: open-trade query failed in exit loop — skipping",
                preset.name,
            )
            return

        if not rows:
            return

        for row in rows:
            row_dict = dict(row)
            trade_id = row_dict["id"]
            symbol = row_dict["symbol"]
            right_str = (
                "put"
                if row_dict["direction"] in ("PUT", "bearish", "put")
                else "call"
            )

            # Skip if an exit is already pending — don't duplicate-submit
            # while the prior exit order is still alive at Alpaca.
            if trade_id in self._new_preset_pending_exits:
                logger.info(
                    "  Step 9' [%s]: exit already pending for %s — "
                    "skip re-evaluation",
                    preset.name, trade_id[:8],
                )
                continue

            # Fetch current quote.
            try:
                expiration_date = datetime.strptime(
                    row_dict["expiration"], "%Y-%m-%d",
                ).date()
                option_asset = Asset(
                    symbol=symbol, asset_type="option",
                    expiration=expiration_date,
                    strike=float(row_dict["strike"]),
                    right=right_str,
                )
                current_quote = self.get_last_price(option_asset)
            except Exception:
                logger.exception(
                    "%s: quote fetch failed for %s — skipping cycle",
                    preset.name, trade_id[:8],
                )
                continue

            if current_quote is None or current_quote <= 0:
                logger.info(
                    "  Step 9' [%s]: quote unavailable for %s — "
                    "skip this cycle",
                    preset.name, trade_id[:8],
                )
                continue

            # Build the frozen Position. Position.__post_init__ may
            # raise if any invariant is violated (entry_underlying_price
            # <= 0 etc.) — defensive on top of the SELECT filter.
            try:
                position = self._build_position_from_trade_row(
                    row_dict, float(current_quote),
                )
            except Exception:
                logger.exception(
                    "%s: Position reconstruction failed for %s — "
                    "skipping",
                    preset.name, trade_id[:8],
                )
                continue

            # Filter scanner setups to this position's symbol.
            symbol_setups = [s for r, s in active if r.symbol == symbol]

            # Build ProfileState (same builder the entry loop uses).
            state = self._build_live_profile_state(preset.name)

            # evaluate_exit — defensive against NotImplementedError
            # (0DTE preset's stub) so the loop survives.
            try:
                exit_decision = preset.evaluate_exit(
                    position, float(current_quote), snapshot,
                    symbol_setups, state,
                )
            except NotImplementedError:
                # 0DTE preset is signal_only through Phase 1b; live
                # rows shouldn't exist. Defensive log & continue.
                logger.info(
                    "%s: evaluate_exit not implemented (signal_only "
                    "preset has live trade %s — defensive skip)",
                    preset.name, trade_id[:8],
                )
                continue
            except Exception:
                logger.exception(
                    "%s: evaluate_exit raised for %s — skipping cycle",
                    preset.name, trade_id[:8],
                )
                continue

            if not exit_decision.should_exit:
                logger.debug(
                    "%s: HOLD %s reason=%s",
                    preset.name, trade_id[:8], exit_decision.reason,
                )
                continue

            # Submit the exit. _submit_new_pipeline_exit installs
            # the _new_preset_pending_exits entry on success; on
            # failure no entry is added so the next cycle re-evaluates.
            self._submit_new_pipeline_exit(
                trade_id, position, exit_decision.reason,
            )

    def _run_new_preset_iteration(self, active, snapshot, macro_ctx):
        """C5b: BasePreset entry pipeline for swing / 0dte_asymmetric.

        Iterates scanner results for the configured preset. For each
        ScanResult+setup pair:
          1. is_active_now gate (preset-level — checked once)
          2. evaluate_entry → EntryDecision
          3. select_contract → ContractSelection (after chain build)
          4. can_enter → CapCheckResult
          5. resolve_preset_mode → "signal_only" / "live" / "shadow"
          6. signal_only path: record_signal + send_entry_alert
          7. live/shadow path: log "execution wires in Phase 1b" and
             skip (Phase 1b adds order submission)

        Per Phase 1a scope (DECISION 3 in the C5b prompt):
          - current_open_positions stubbed to 0
          - current_capital_deployed stubbed to 0.0
          - today_account_pnl_pct stubbed to 0.0
          - last_exit_at stubbed to None
        Phase 1b execution wire-in must replace these — see
        PHASE_1A_FOLLOWUPS.md.

        D4: macro_fetcher rebind hoisted to on_trading_iteration's
        _rebind_preset_macro_fetcher call so the exit loop runs
        against the same per-iteration MacroContext. This helper no
        longer rebinds; tests calling it directly rely on the
        placeholder set in initialize() which returns empty events
        for the None-macro_ctx case (matches the adapter's behavior).
        """
        preset = self._new_preset

        # Preset-level is_active_now gate (e.g. 0DTE 9:35-13:30 ET window).
        if not preset.is_active_now(snapshot):
            return

        for scan_result, setup in active:
            symbol = scan_result.symbol

            # Build ProfileState from live subprocess + DB state (D1).
            # Replaces the C5b stubs (current_open_positions=0,
            # current_capital_deployed=0.0, today_account_pnl_pct=0.0,
            # last_exit_at=None) with real computations that gate
            # cap_check meaningfully.
            state = self._build_live_profile_state(preset.name)

            # evaluate_entry
            try:
                decision = preset.evaluate_entry(
                    symbol, setup, snapshot, state,
                )
            except Exception:
                logger.exception(
                    "%s: evaluate_entry raised for %s — skipping",
                    preset.name, symbol,
                )
                continue
            if not decision.should_enter:
                logger.debug(
                    "%s: no-entry %s (%s)",
                    preset.name, symbol, decision.reason,
                )
                continue

            # Build OptionChain (right-filtered by direction)
            chain = self._build_option_chain_for_new_preset(
                symbol, decision.direction,
            )
            if chain is None:
                logger.info(
                    "%s: chain unavailable for %s — skipping entry",
                    preset.name, symbol,
                )
                continue

            # select_contract
            try:
                contract = preset.select_contract(
                    symbol, decision.direction, chain,
                )
            except Exception:
                logger.exception(
                    "%s: select_contract raised for %s — skipping",
                    preset.name, symbol,
                )
                continue
            if contract is None:
                logger.info(
                    "%s: no qualifying contract for %s",
                    preset.name, symbol,
                )
                continue

            # D2: Resolve effective execution mode early so we can
            # branch on sizing. signal_only retains proposed_contracts=1
            # (outcome rows don't need a real size). Live/shadow runs
            # the PDT gate + sizer.
            effective_mode = resolve_preset_mode(
                preset.name, config.EXECUTION_MODE,
            )

            if effective_mode == "signal_only":
                proposed_contracts = 1
            else:
                # D2 PDT gate (mirrors legacy v2:937-961, defensive
                # double-branch). For SwingPreset's 7-14 DTE window the
                # is_same_day branch is structurally unreachable, but a
                # future preset that allows shorter DTE would otherwise
                # silently bypass PDT — keep the check.
                pv = self.get_portfolio_value() or 0.0
                is_same_day = (
                    contract.expiration
                    == datetime.now(timezone.utc).date()
                )
                if pv < 25000.0:
                    if self._pdt_locked:
                        logger.info(
                            "%s: PDT blocked %s — fully locked "
                            "(day_trades=%d, bp=$%.0f)",
                            preset.name, symbol,
                            self._pdt_day_trades,
                            self._pdt_buying_power,
                        )
                        continue
                    if self._pdt_day_trades >= 2 and is_same_day:
                        logger.info(
                            "%s: PDT blocked %s — 1 day trade left + "
                            "same-day expiration would trap position",
                            preset.name, symbol,
                        )
                        continue

                # D2 sizer. risk_manager is consulted for current
                # exposure ($ across all open positions on this
                # execution_mode). Defensive on its DB error path.
                try:
                    exposure = self._risk_manager.check_portfolio_exposure(pv)
                except Exception:
                    logger.exception(
                        "%s: risk_manager.check_portfolio_exposure "
                        "failed for %s — using exposure_dollars=0.0",
                        preset.name, symbol,
                    )
                    exposure = {"exposure_dollars": 0.0}

                # D2: confidence=setup.score (raw scanner score) rather
                # than scored.capped_score (legacy). The new pipeline
                # doesn't run the Scorer — see PHASE_1A_FOLLOWUPS.md
                # "Confidence input divergence in D2".
                sizing = size_calculate(
                    account_value=pv,
                    confidence=setup.score,
                    premium=contract.estimated_premium,
                    day_start_value=self._day_start_value,
                    starting_balance=self._starting_balance,
                    current_exposure=exposure.get(
                        "exposure_dollars", 0.0,
                    ),
                    is_same_day_trade=is_same_day,
                    day_trades_remaining=max(
                        0, 3 - self._pdt_day_trades,
                    ),
                    growth_mode_config=bool(
                        self._config.get("growth_mode", True),
                    ),
                )

                if sizing.blocked or sizing.contracts == 0:
                    logger.info(
                        "%s: sizer blocked %s — %s",
                        preset.name, symbol, sizing.block_reason,
                    )
                    continue

                proposed_contracts = sizing.contracts

            # can_enter (cap_check via @final wrapper). Uses sized
            # count for non-signal_only; 1 for signal_only.
            cap_result = preset.can_enter(
                entry_decision=decision,
                contract=contract,
                state=state,
                proposed_contracts=proposed_contracts,
            )
            if not cap_result.approved:
                logger.info(
                    "%s: cap_check blocked %s — %s",
                    preset.name, symbol, cap_result.block_reason,
                )
                continue

            now_utc = datetime.now(timezone.utc)

            if effective_mode == "signal_only":
                # signal_only path: emit + record (D2 unchanged).
                signal_id = str(uuid4())

                try:
                    record_signal(
                        signal_id=signal_id,
                        profile_id=self._profile_config.name,
                        symbol=symbol,
                        setup_type=setup.setup_type,
                        direction=decision.direction,
                        contract_symbol=contract.symbol,
                        contract_strike=contract.strike,
                        contract_right=contract.right,
                        contract_expiration=contract.expiration.isoformat(),
                        entry_premium=contract.estimated_premium,
                        predicted_at=now_utc,
                    )
                except Exception:
                    logger.exception(
                        "%s: record_signal failed for %s — continuing",
                        preset.name, symbol,
                    )

                try:
                    send_entry_alert(
                        profile_config=self._profile_config,
                        signal_id=signal_id,
                        symbol=symbol,
                        setup_type=setup.setup_type,
                        direction=decision.direction,
                        setup_score=setup.score,
                        contract_strike=contract.strike,
                        contract_right=contract.right,
                        contract_expiration=contract.expiration.isoformat(),
                        entry_premium_per_share=contract.estimated_premium,
                        contracts=cap_result.approved_contracts,
                        mode="signal_only",
                        timestamp=now_utc,
                    )
                except Exception:
                    logger.exception(
                        "%s: send_entry_alert failed for %s — continuing",
                        preset.name, symbol,
                    )

                # Update orchestrator state.
                self._recent_entries_by_symbol_direction[
                    f"{symbol}:{decision.direction}"
                ] = now_utc
                self._last_entry_time[preset.name] = now_utc
                logger.info(
                    "%s: signal_only entry recorded — symbol=%s "
                    "direction=%s strike=%s signal_id=%s",
                    preset.name, symbol, decision.direction,
                    contract.strike, signal_id,
                )
            else:
                # D3: live / shadow path — actual order submission.
                # record_signal NOT called for live/shadow (the trades
                # table + _scorer.record_trade_outcome from
                # on_filled_order handle learning for executed trades).
                # send_entry_alert IS called so users still get Discord
                # alerts.
                try:
                    result = self._submit_new_pipeline_entry(
                        contract, proposed_contracts, setup, preset,
                        snapshot, decision,
                        entry_underlying_price=chain.underlying_price,
                    )
                except Exception:
                    logger.exception(
                        "%s: submission raised for %s — continuing",
                        preset.name, symbol,
                    )
                    continue

                if not result.submitted:
                    logger.info(
                        "%s: submission blocked %s — %s",
                        preset.name, symbol,
                        result.block_reason or "unknown",
                    )
                    continue

                # Submission accepted — fire Discord alert.
                try:
                    send_entry_alert(
                        profile_config=self._profile_config,
                        signal_id=result.trade_id,
                        symbol=symbol,
                        setup_type=setup.setup_type,
                        direction=decision.direction,
                        setup_score=setup.score,
                        contract_strike=contract.strike,
                        contract_right=contract.right,
                        contract_expiration=contract.expiration.isoformat(),
                        entry_premium_per_share=contract.estimated_premium,
                        contracts=proposed_contracts,
                        mode=effective_mode,
                        timestamp=now_utc,
                    )
                except Exception:
                    logger.exception(
                        "%s: send_entry_alert failed for %s — continuing",
                        preset.name, symbol,
                    )

                # _last_entry_time was updated inside
                # _dispatch_entry_order; just track the
                # symbol/direction cooldown dict here.
                self._recent_entries_by_symbol_direction[
                    f"{symbol}:{decision.direction}"
                ] = now_utc
                logger.info(
                    "%s: %s entry submitted — symbol=%s direction=%s "
                    "strike=%s contracts=%d trade_id=%s",
                    preset.name, effective_mode, symbol,
                    decision.direction, contract.strike,
                    proposed_contracts, result.trade_id,
                )

