"""Opportunity scoring engine — produces a single confidence score (0.0-1.0).
Seven weighted factors. Regime cap enforced post-computation. Every factor
logged with name, raw value, weight, and weighted contribution."""

import logging
from dataclasses import dataclass, field
from typing import Optional

from market.context import Regime, TimeOfDay, MarketSnapshot
from scanner.setups import SetupScore
from scoring.ivr import get_ivr

logger = logging.getLogger("options-bot.scoring")

# Architecture doc factor weights
BASE_WEIGHTS = {
    "signal_clarity":     0.25,
    "regime_fit":         0.20,
    "ivr":                0.15,
    "institutional_flow": 0.15,
    "historical_perf":    0.10,
    "sentiment":          0.10,
    "time_of_day":        0.05,
}

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
    ("compression", Regime.CHOPPY):        0.8,
    ("compression", Regime.TRENDING_UP):   0.6,
    ("compression", Regime.TRENDING_DOWN): 0.6,
    ("compression", Regime.HIGH_VOLATILITY): 0.2,
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
}

# Regime hard caps — applied AFTER weighted score computation
# Momentum in CHOPPY or HIGH_VOL cannot exceed 0.45
REGIME_CAPS = {
    ("momentum", Regime.CHOPPY):           0.45,
    ("momentum", Regime.HIGH_VOLATILITY):  0.45,
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


class Scorer:
    """Produces a confidence score from setup + market context."""

    def __init__(self):
        self._trade_history: list[dict] = []  # For historical_perf factor
        self._regime_overrides: dict = {}     # "setup_type_REGIME" -> delta float

    def set_regime_overrides(self, overrides: dict):
        """Apply learning-layer regime fit overrides. Merges with existing."""
        self._regime_overrides.update(overrides)

    def score(
        self,
        symbol: str,
        setup: SetupScore,
        market: MarketSnapshot,
        sentiment_score: float = 0.0,
        current_iv: Optional[float] = None,
    ) -> ScoringResult:
        """Score an opportunity. Returns full breakdown."""

        # --- Phase 1: Compute raw values and determine which factors are active ---
        raw_values = {}
        skipped = set()

        raw_values["signal_clarity"] = setup.score
        base_fit = REGIME_FIT.get((setup.setup_type, market.regime), 0.5)
        override_key = f"{setup.setup_type}_{market.regime.value}"
        override = self._regime_overrides.get(override_key, 0.0)
        raw_values["regime_fit"] = max(0.0, min(1.0, base_fit + override))

        ivr_val = get_ivr(symbol, current_iv)
        if ivr_val is not None:
            raw_values["ivr"] = 1.0 - ivr_val  # Low IVR = high score for buyers
        else:
            skipped.add("ivr")

        # Institutional flow: Unusual Whales not subscribed
        skipped.add("institutional_flow")

        raw_values["historical_perf"] = self._compute_historical_perf(symbol, setup.setup_type)

        sent_raw = (sentiment_score + 1.0) / 2.0  # Map -1..+1 to 0..1
        if setup.direction == "bearish":
            sent_raw = 1.0 - sent_raw
        raw_values["sentiment"] = sent_raw

        raw_values["time_of_day"] = TOD_FIT.get((setup.setup_type, market.time_of_day), 0.5)

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
        lines.append(f"  {'FINAL':25s} = {result.capped_score:.4f} [{result.threshold_label}]")
        lines.append(f"  regime={market.regime.value} tod={market.time_of_day.value}")
        logger.info("\n".join(lines))

    def record_trade_outcome(self, symbol: str, setup_type: str, pnl: float):
        """Record a closed trade for historical_perf factor."""
        self._trade_history.append({"symbol": symbol, "setup_type": setup_type, "pnl": pnl})
        # Keep last 100 per symbol
        by_symbol = [t for t in self._trade_history if t["symbol"] == symbol]
        if len(by_symbol) > 100:
            self._trade_history = [t for t in self._trade_history if t["symbol"] != symbol] + by_symbol[-100:]
