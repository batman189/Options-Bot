"""Opportunity scoring engine — produces a single confidence score (0.0-1.0).
Seven weighted factors. Regime cap enforced post-computation. Every factor
logged with name, raw value, weight, and weighted contribution."""

import logging
from dataclasses import dataclass, field
from typing import Optional

from config import (
    MACRO_CATALYST_NUDGE_CAP,
    MACRO_CATALYST_NUDGE_PER_POINT,
    MACRO_EVENT_BUFFER_MINUTES,
    MACRO_EVENT_BUFFER_MEDIUM_MIN,
)
from market.context import Regime, TimeOfDay, MarketSnapshot
from macro.reader import (
    MacroContext,
    catalysts_for_symbol,
    events_for_symbol,
    snapshot_macro_context,
)
from scanner.setups import SetupScore
from scoring.ivr import get_ivr

logger = logging.getLogger("options-bot.scoring")

# Factor weights. Values redistributed in Prompt 25 — removed
# institutional_flow (never implemented; always skipped at runtime,
# UI rendered a permanent "n/a" bar). The runtime _redistribute
# helper was already multiplying each remaining weight by
# 1/(1 - 0.15) = 1.17647 on every score() call; this declaration
# makes that explicit so BASE_WEIGHTS matches the weights actually
# applied. Purely declarative change — no scoring behavior diff.
# Sum asserted to 1.0 below so future edits can't silently drift.
BASE_WEIGHTS = {
    "signal_clarity":  0.2941,   # was 0.25  -> 0.25  / 0.85
    "regime_fit":      0.2353,   # was 0.20  -> 0.20  / 0.85
    "ivr":             0.1765,   # was 0.15  -> 0.15  / 0.85
    "historical_perf": 0.1765,   # was 0.15  -> 0.15  / 0.85
    "sentiment":       0.0588,   # was 0.05  -> 0.05  / 0.85 (still suppression-only)
    "time_of_day":     0.0588,   # was 0.05  -> 0.05  / 0.85
}

# Invariant: weights must sum to 1.0 exactly (within float tolerance).
# Caught by tests/test_pipeline_trace.py test 25.1 and at import time
# below. Any future edit that breaks the sum fails here loudly.
assert abs(sum(BASE_WEIGHTS.values()) - 1.0) < 1e-9, (
    f"BASE_WEIGHTS must sum to 1.0, got {sum(BASE_WEIGHTS.values())}"
)

# Regime-setup compatibility (1.0 = ideal, 0.0 = hostile)
REGIME_FIT = {
    ("momentum", Regime.TRENDING_UP):      1.0,
    ("momentum", Regime.TRENDING_DOWN):    1.0,
    ("momentum", Regime.CHOPPY):           0.1,
    ("momentum", Regime.HIGH_VOLATILITY):  0.3,
    ("mean_reversion", Regime.CHOPPY):     1.0,
    ("mean_reversion", Regime.TRENDING_UP):   0.2,
    ("mean_reversion", Regime.TRENDING_DOWN): 0.2,
    ("mean_reversion", Regime.HIGH_VOLATILITY): 0.5,
    # Compression breakout — valid in any regime (compression breaking with
    # volume is a signal regardless of macro regime classification).
    ("compression_breakout", Regime.CHOPPY):           0.85,
    ("compression_breakout", Regime.TRENDING_UP):      0.75,
    ("compression_breakout", Regime.TRENDING_DOWN):    0.75,
    ("compression_breakout", Regime.HIGH_VOLATILITY):  0.30,
    # Macro trend — only valid in trending regimes
    ("macro_trend", Regime.TRENDING_UP):               1.0,
    ("macro_trend", Regime.TRENDING_DOWN):             1.0,
    ("macro_trend", Regime.CHOPPY):                    0.20,
    ("macro_trend", Regime.HIGH_VOLATILITY):           0.20,
    ("catalyst", Regime.TRENDING_UP):      0.8,
    ("catalyst", Regime.TRENDING_DOWN):    0.8,
    ("catalyst", Regime.CHOPPY):           0.7,
    ("catalyst", Regime.HIGH_VOLATILITY):  0.3,
}

# Time-of-day suitability per setup type (0.0-1.0)
TOD_FIT = {
    ("momentum", TimeOfDay.OPEN):        0.9,
    ("momentum", TimeOfDay.MID_MORNING): 0.7,
    ("momentum", TimeOfDay.MIDDAY):      0.3,
    ("momentum", TimeOfDay.POWER_HOUR):  0.8,
    ("momentum", TimeOfDay.CLOSE):       0.4,
    ("mean_reversion", TimeOfDay.OPEN):        0.5,
    ("mean_reversion", TimeOfDay.MID_MORNING): 0.7,
    ("mean_reversion", TimeOfDay.MIDDAY):      0.8,
    ("mean_reversion", TimeOfDay.POWER_HOUR):  0.6,
    ("mean_reversion", TimeOfDay.CLOSE):       0.4,
    ("compression_breakout", TimeOfDay.OPEN):        0.8,
    ("compression_breakout", TimeOfDay.MID_MORNING): 0.9,
    ("compression_breakout", TimeOfDay.MIDDAY):      0.6,
    ("compression_breakout", TimeOfDay.POWER_HOUR):  0.7,
    ("compression_breakout", TimeOfDay.CLOSE):       0.3,
    ("macro_trend", TimeOfDay.OPEN):                 1.0,
    ("macro_trend", TimeOfDay.MID_MORNING):          0.9,
    ("macro_trend", TimeOfDay.MIDDAY):               0.5,
    ("macro_trend", TimeOfDay.POWER_HOUR):           0.7,
    ("macro_trend", TimeOfDay.CLOSE):                0.2,
}

# Regime hard caps — applied AFTER weighted score computation
# Momentum in CHOPPY or HIGH_VOL cannot exceed 0.45
REGIME_CAPS = {
    ("momentum", Regime.CHOPPY):           0.45,
    ("momentum", Regime.HIGH_VOLATILITY):  0.45,
    ("macro_trend", Regime.HIGH_VOLATILITY): 0.35,
    ("macro_trend", Regime.CHOPPY):          0.35,
}


@dataclass
class FactorDetail:
    """One factor's contribution to the score."""
    name: str
    raw_value: float
    weight: float
    contribution: float  # raw_value * weight
    status: str = "active"  # "active" or "skipped"


@dataclass
class ScoringResult:
    """Full scoring output with factor breakdown."""
    symbol: str
    setup_type: str
    raw_score: float          # Before regime cap
    capped_score: float       # After regime cap (may equal raw_score)
    regime_cap_applied: bool
    regime_cap_value: Optional[float]
    threshold_label: str      # "no_trade", "swing_only", "moderate", "high_conviction"
    direction: str
    factors: list[FactorDetail] = field(default_factory=list)
    # Macro awareness layer (see macro/reader.py). Defaults preserve backward
    # compatibility — existing test call sites that construct ScoringResult
    # without these fields still work.
    macro_cap_applied: bool = False
    macro_veto_reason: Optional[str] = None
    macro_nudge_applied: bool = False   # True if any regime_fit nudge delta fired
    macro_nudge_total: float = 0.0      # Sum of regime + catalyst deltas (always <= 0)
    macro_nudge_regime: float = 0.0     # Regime-tone component (for log transparency)
    macro_nudge_catalyst: float = 0.0   # Catalyst-contradiction component (capped)


class Scorer:
    """Produces a confidence score from setup + market context."""

    def __init__(self):
        self._trade_history: list[dict] = []  # For historical_perf factor
        self._regime_overrides: dict = {}     # "setup_type_REGIME" -> delta float
        self._tod_overrides: dict = {}        # "setup_type_TOD" -> delta float

    def set_regime_overrides(self, overrides: dict):
        """Apply learning-layer regime fit overrides. Merges with existing."""
        self._regime_overrides.update(overrides)

    def set_tod_overrides(self, overrides: dict):
        """Apply learning-layer time-of-day fit overrides. Merges with existing."""
        self._tod_overrides.update(overrides)

    def score(
        self,
        symbol: str,
        setup: SetupScore,
        market: MarketSnapshot,
        sentiment_score: float = 0.0,
        current_iv: Optional[float] = None,
        macro_ctx: Optional[MacroContext] = None,
    ) -> ScoringResult:
        """Score an opportunity. Returns full breakdown.

        macro_ctx: per-iteration snapshot of macro events + regime. Callers
        should construct one snapshot at the top of on_trading_iteration via
        macro.reader.snapshot_macro_context() and pass it to every score()
        call in that iteration (matches the pattern in v2_strategy.py).
        If None, a fresh snapshot is taken — convenient for isolated tests,
        wasteful if called in a loop.
        """

        # --- Phase 1: Compute raw values and determine which factors are active ---
        raw_values = {}
        skipped = set()

        raw_values["signal_clarity"] = setup.score
        base_fit = REGIME_FIT.get((setup.setup_type, market.regime), 0.5)
        override_key = f"{setup.setup_type}_{market.regime.value}"
        override = self._regime_overrides.get(override_key, 0.0)
        raw_values["regime_fit"] = max(0.0, min(1.0, base_fit + override))

        # Macro nudge — two independent deltas applied to regime_fit:
        #   regime_delta:   −0.10 if risk_tone contradicts trade direction
        #   catalyst_delta: sum of −(severity × MACRO_CATALYST_NUDGE_PER_POINT)
        #                   across contradicting catalysts, capped at the
        #                   absolute value of MACRO_CATALYST_NUDGE_CAP
        # Total stacks with the learning-layer `override` above; stacking is
        # intentional (plan E-c). Max possible combined nudge = −0.20.
        regime_delta, catalyst_delta = self._compute_macro_nudge(symbol, setup, macro_ctx)
        macro_nudge_total = regime_delta + catalyst_delta
        macro_nudge_applied = macro_nudge_total < 0
        if macro_nudge_applied:
            raw_values["regime_fit"] = max(0.0, min(1.0, raw_values["regime_fit"] + macro_nudge_total))

        ivr_val = get_ivr(symbol, current_iv)
        if ivr_val is not None:
            raw_values["ivr"] = 1.0 - ivr_val  # Low IVR = high score for buyers
        else:
            skipped.add("ivr")

        # institutional_flow factor removed in Prompt 25. Was always
        # added to `skipped` (Unusual Whales never subscribed) and
        # redistributed at runtime. Now declared out of BASE_WEIGHTS
        # entirely.

        raw_values["historical_perf"] = self._compute_historical_perf(symbol, setup.setup_type)

        # Sentiment is suppression-only: contradicting sentiment hurts the score,
        # but confirming/neutral sentiment scores 0.5 (neutral). We don't reward
        # positive sentiment until 200+ trades validate it correlates with outcomes.
        # The 0.3 threshold filters noise — only meaningful sentiment suppresses.
        if setup.direction == "bearish":
            # Bearish trade: positive sentiment is contradicting → suppression
            if sentiment_score > 0.3:
                sent_raw = max(0.0, 0.5 - (sentiment_score * 0.5))
            else:
                sent_raw = 0.5  # Neutral or confirming → no effect
        else:
            # Bullish trade: negative sentiment is contradicting → suppression
            if sentiment_score < -0.3:
                sent_raw = max(0.0, 0.5 + (sentiment_score * 0.5))
            else:
                sent_raw = 0.5  # Neutral or confirming → no effect
        raw_values["sentiment"] = round(sent_raw, 4)

        base_tod = TOD_FIT.get((setup.setup_type, market.time_of_day), 0.5)
        tod_override_key = f"{setup.setup_type}_{market.time_of_day.value}"
        tod_override = self._tod_overrides.get(tod_override_key, 0.0)
        raw_values["time_of_day"] = max(0.0, min(1.0, base_tod + tod_override))

        # --- Phase 2: Redistribute skipped weights, then assign final weights ---
        active_weights = dict(BASE_WEIGHTS)
        for key in skipped:
            self._redistribute(active_weights, key)

        # --- Phase 3: Build factor details with final redistributed weights ---
        factors = []
        for name in BASE_WEIGHTS:
            if name in skipped:
                factors.append(FactorDetail(name, 0.0, 0.0, 0.0, status="skipped"))
            else:
                rv = round(raw_values[name], 4)
                w = active_weights[name]
                factors.append(FactorDetail(name, rv, round(w, 3), 0.0))

        # --- Phase 4: Compute weighted score ---
        raw_score = 0.0
        for f in factors:
            if f.status == "active":
                f.contribution = round(f.raw_value * f.weight, 6)
                raw_score += f.contribution
        raw_score = round(min(raw_score, 1.0), 4)

        # --- Regime cap: hard enforcement AFTER weighted computation ---
        cap_key = (setup.setup_type, market.regime)
        cap_value = REGIME_CAPS.get(cap_key)
        cap_applied = False
        capped = raw_score
        if cap_value is not None and raw_score > cap_value:
            capped = cap_value
            cap_applied = True

        # --- Macro veto cap: zero the score if a HIGH event is imminent ---
        # Belt-and-suspenders with the profile veto in base_profile.should_enter;
        # both must fire for a complete block. Fail-safe when macro_ctx is empty.
        macro_cap_applied = False
        macro_veto_reason: Optional[str] = None
        veto_hit, veto_reason = self._compute_macro_veto(symbol, macro_ctx)
        if veto_hit:
            capped = 0.0
            macro_cap_applied = True
            macro_veto_reason = veto_reason

        # --- Threshold classification ---
        if capped < 0.50:
            label = "no_trade"
        elif capped < 0.65:
            label = "swing_only"
        elif capped < 0.80:
            label = "moderate"
        else:
            label = "high_conviction"

        result = ScoringResult(
            symbol=symbol, setup_type=setup.setup_type,
            raw_score=raw_score, capped_score=round(capped, 4),
            regime_cap_applied=cap_applied, regime_cap_value=cap_value,
            threshold_label=label, direction=setup.direction,
            factors=factors,
            macro_cap_applied=macro_cap_applied,
            macro_veto_reason=macro_veto_reason,
            macro_nudge_applied=macro_nudge_applied,
            macro_nudge_total=round(macro_nudge_total, 4),
            macro_nudge_regime=round(regime_delta, 4),
            macro_nudge_catalyst=round(catalyst_delta, 4),
        )

        # --- Log every factor ---
        self._log_scoring(result, market)
        return result

    def _redistribute(self, weights: dict, skip_key: str):
        """Redistribute a skipped factor's weight proportionally."""
        skipped_weight = weights.pop(skip_key, 0)
        if not weights or skipped_weight == 0:
            return
        remaining_total = sum(weights.values())
        if remaining_total == 0:
            return
        for k in weights:
            weights[k] += skipped_weight * (weights[k] / remaining_total)

    def _compute_historical_perf(self, symbol: str, setup_type: str) -> float:
        """Win rate of this setup type on this symbol from trade history.
        Returns 0.5 (neutral) if insufficient history."""
        relevant = [t for t in self._trade_history
                    if t.get("symbol") == symbol and t.get("setup_type") == setup_type]
        if len(relevant) < 5:
            return 0.5  # Neutral until enough data
        wins = sum(1 for t in relevant if t.get("pnl", 0) > 0)
        return wins / len(relevant)

    def _log_scoring(self, result: ScoringResult, market: MarketSnapshot):
        """Log full factor breakdown for auditability."""
        lines = [f"Score {result.symbol} {result.setup_type} ({result.direction}):"]
        for f in result.factors:
            if f.status == "skipped":
                lines.append(f"  {f.name:25s} SKIPPED (data unavailable, weight redistributed)")
            else:
                lines.append(f"  {f.name:25s} raw={f.raw_value:.4f} w={f.weight:.3f} contrib={f.contribution:.4f}")
        lines.append(f"  {'RAW SCORE':25s} = {result.raw_score:.4f}")
        if result.regime_cap_applied:
            lines.append(f"  {'REGIME CAP':25s} {result.raw_score:.4f} -> {result.capped_score:.4f} (cap={result.regime_cap_value})")
        if result.macro_nudge_applied:
            lines.append(
                f"  {'MACRO NUDGE':25s} regime_fit {result.macro_nudge_total:+.3f} applied "
                f"(regime={result.macro_nudge_regime:+.3f} catalyst={result.macro_nudge_catalyst:+.3f})"
            )
        if result.macro_cap_applied:
            lines.append(f"  {'MACRO VETO':25s} -> 0.0 ({result.macro_veto_reason})")
        lines.append(f"  {'FINAL':25s} = {result.capped_score:.4f} [{result.threshold_label}]")
        lines.append(f"  regime={market.regime.value} tod={market.time_of_day.value}")
        logger.info("\n".join(lines))

    # ── Macro awareness layer helpers ──────────────────────────────────
    def _resolve_ctx(self, macro_ctx: Optional[MacroContext]) -> MacroContext:
        """Return the provided context or take a fresh snapshot.

        Tests inside a loop MUST pass a ctx (see plan E-b) — this fallback
        exists only for isolated single-call callers that don't want the
        ceremony of constructing one.
        """
        if macro_ctx is not None:
            return macro_ctx
        return snapshot_macro_context()

    def _compute_macro_nudge(
        self,
        symbol: str,
        setup: SetupScore,
        macro_ctx: Optional[MacroContext],
    ) -> tuple[float, float]:
        """Return (regime_delta, catalyst_delta) — both <= 0.

        Regime contradiction:
          - risk_off + direction='bullish'  → −0.10 (buyers pulling back)
          - risk_on  + direction='bearish'  → −0.10 (sellers buying dips)
          Stale/missing regime → 0.0 (fail-safe).

        Catalyst contradiction: for each catalyst on `symbol` (already
        merged with market-wide '*' in the snapshot) whose direction
        opposes setup.direction, add −(severity × PER_POINT). Total is
        clamped to a magnitude of MACRO_CATALYST_NUDGE_CAP (default −0.10).
        Neutral catalysts and directionally aligned catalysts contribute
        nothing. Empty catalyst list → 0.0 (fail-safe).
        """
        ctx = self._resolve_ctx(macro_ctx)

        # --- Regime component ---
        regime_delta = 0.0
        if ctx.regime is not None:
            tone = ctx.regime.risk_tone
            if tone == "risk_off" and setup.direction == "bullish":
                regime_delta = -0.10
            elif tone == "risk_on" and setup.direction == "bearish":
                regime_delta = -0.10

        # --- Catalyst component ---
        catalyst_delta = 0.0
        contra: str = (
            "bearish" if setup.direction == "bullish"
            else "bullish" if setup.direction == "bearish"
            else ""
        )
        if contra:
            for cat in catalysts_for_symbol(ctx, symbol):
                if cat.direction == contra:
                    catalyst_delta -= MACRO_CATALYST_NUDGE_PER_POINT * float(cat.severity)
            if catalyst_delta < -MACRO_CATALYST_NUDGE_CAP:
                catalyst_delta = -MACRO_CATALYST_NUDGE_CAP

        return round(regime_delta, 4), round(catalyst_delta, 4)

    def _compute_macro_veto(self, symbol: str,
                             macro_ctx: Optional[MacroContext]) -> tuple[bool, Optional[str]]:
        """Return (True, reason) if a HIGH event is within MACRO_EVENT_BUFFER_MINUTES
        or a MEDIUM event is within MACRO_EVENT_BUFFER_MEDIUM_MIN. Else (False, None)."""
        ctx = self._resolve_ctx(macro_ctx)
        events = events_for_symbol(ctx, symbol)
        for ev in events:
            if ev.impact_level == "HIGH" and ev.minutes_until <= MACRO_EVENT_BUFFER_MINUTES:
                return True, f"{ev.event_type} in {ev.minutes_until}min (HIGH)"
        for ev in events:
            if ev.impact_level == "MEDIUM" and ev.minutes_until <= MACRO_EVENT_BUFFER_MEDIUM_MIN:
                return True, f"{ev.event_type} in {ev.minutes_until}min (MEDIUM)"
        return False, None

    def record_trade_outcome(self, symbol: str, setup_type: str, pnl: float):
        """Record a closed trade for historical_perf factor."""
        self._trade_history.append({"symbol": symbol, "setup_type": setup_type, "pnl": pnl})
        # Keep last 100 per symbol
        by_symbol = [t for t in self._trade_history if t["symbol"] == symbol]
        if len(by_symbol) > 100:
            self._trade_history = [t for t in self._trade_history if t["symbol"] != symbol] + by_symbol[-100:]

    def load_trade_history_from_db(
        self,
        symbols: Optional[list[str]] = None,
        limit: int = 200,
    ) -> int:
        """Populate self._trade_history from closed trades in the DB.

        Called once at subprocess startup after the learning-state block.
        Without this, every watchdog restart zeroed out the in-memory
        trade history and the historical_perf factor (15% weight) stayed
        pinned at 0.5 neutral until new trades accumulated.

        Args:
            symbols: list of symbols this subprocess scans. In production
                     that's typically [self.symbol], expanded to
                     ["SPY", "QQQ"] for the SPY subprocess (see
                     v2_strategy.py scan_symbols). Pass None to load all
                     symbols (useful for tests).
            limit: max rows to fetch. 200 gives headroom for multiple
                   setup_types per symbol; record_trade_outcome trims to
                   last 100 per symbol anyway.

        Returns:
            Number of rows loaded into self._trade_history.
        """
        import sqlite3
        from config import DB_PATH
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            if symbols:
                placeholders = ",".join("?" for _ in symbols)
                cursor = conn.execute(
                    f"""SELECT symbol, setup_type, pnl_pct FROM trades
                        WHERE status = 'closed'
                          AND pnl_pct IS NOT NULL
                          AND setup_type IS NOT NULL
                          AND symbol IN ({placeholders})
                        ORDER BY exit_date DESC LIMIT ?""",
                    (*symbols, limit),
                )
            else:
                cursor = conn.execute(
                    """SELECT symbol, setup_type, pnl_pct FROM trades
                       WHERE status = 'closed'
                         AND pnl_pct IS NOT NULL
                         AND setup_type IS NOT NULL
                       ORDER BY exit_date DESC LIMIT ?""",
                    (limit,),
                )
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            logger.warning(f"Scorer: load_trade_history_from_db failed (non-fatal): {e}")
            return 0

        loaded = 0
        for r in rows:
            self._trade_history.append({
                "symbol": r["symbol"],
                "setup_type": r["setup_type"],
                "pnl": float(r["pnl_pct"]),
            })
            loaded += 1
        label = ",".join(symbols) if symbols else "all"
        logger.info(f"Scorer: loaded {loaded} historical trades for {label}")
        return loaded
