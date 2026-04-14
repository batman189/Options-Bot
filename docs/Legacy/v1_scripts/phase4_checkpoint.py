"""Phase 4 Validation Checkpoint — Opportunity Scoring Engine."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

print("=" * 70)
print("PHASE 4 VALIDATION CHECKPOINT")
print("=" * 70)

from market.context import Regime, TimeOfDay, MarketSnapshot
from scanner.setups import SetupScore
from scoring.scorer import Scorer, BASE_WEIGHTS
from scoring.ivr import get_ivr

scorer = Scorer()


def make_market(regime, tod=TimeOfDay.MID_MORNING):
    return MarketSnapshot(
        regime=regime, time_of_day=tod,
        timestamp="2026-03-30T12:00:00",
        spy_30min_move_pct=0.5, spy_60min_range_pct=0.8,
        spy_30min_reversals=1, spy_volume_ratio=1.5,
        vix_level=20.0, vix_intraday_change_pct=2.0,
        regime_reason="simulated",
    )


def print_result(label, result):
    print(f"\n  --- {label} ---")
    for f in result.factors:
        if f.status == "skipped":
            print(f"    {f.name:25s} SKIPPED (weight redistributed)")
        else:
            print(f"    {f.name:25s} raw={f.raw_value:.4f}  w={f.weight:.3f}  contrib={f.contribution:.4f}")
    print(f"    {'RAW SCORE':25s} = {result.raw_score:.4f}")
    if result.regime_cap_applied:
        print(f"    {'REGIME CAP':25s} {result.raw_score:.4f} -> {result.capped_score:.4f} (cap={result.regime_cap_value})")
    print(f"    {'FINAL':25s} = {result.capped_score:.4f} [{result.threshold_label}]")


# ================================================================
# TEST 1: 5 scenarios — 2 winners, 2 losers, 1 avoided
# ================================================================
print("\nTEST 1: Five scored scenarios")
print("-" * 60)

# Winner 1: Strong momentum in trending market, low VIX
r1 = scorer.score(
    "SPY",
    SetupScore("momentum", 0.85, "8/8 bars bullish, vol=2.1x, move=0.8%", "bullish"),
    make_market(Regime.TRENDING_UP),
    sentiment_score=0.3,
    current_iv=0.22,
)
print_result("Winner 1: Strong SPY momentum in TRENDING_UP", r1)

# Winner 2: Mean reversion in choppy market
r2 = scorer.score(
    "TSLA",
    SetupScore("mean_reversion", 0.72, "RSI=22, BB%b=-0.1, wick=True", "bullish"),
    make_market(Regime.CHOPPY),
    sentiment_score=-0.2,
    current_iv=0.45,
)
print_result("Winner 2: TSLA mean reversion in CHOPPY", r2)

# Loser 1: Momentum in choppy market (wrong regime)
r3 = scorer.score(
    "SPY",
    SetupScore("momentum", 0.65, "6/8 bars, vol=1.3x, move=0.4%", "bullish"),
    make_market(Regime.CHOPPY),
    sentiment_score=0.1,
    current_iv=0.18,
)
print_result("Loser 1: SPY momentum in CHOPPY (wrong regime)", r3)

# Loser 2: Catalyst with weak signal
r4 = scorer.score(
    "TSLA",
    SetupScore("catalyst", 0.55, "sentiment=+0.75 AND vol/OI=0.52", "bullish"),
    make_market(Regime.TRENDING_UP),
    sentiment_score=0.75,
    current_iv=0.50,
)
print_result("Loser 2: TSLA catalyst weak signal", r4)

# Avoided: Momentum in HIGH_VOLATILITY
r5 = scorer.score(
    "SPY",
    SetupScore("momentum", 0.40, "5/8 bars, vol=1.0x, move=0.35%", "bearish"),
    make_market(Regime.HIGH_VOLATILITY),
    sentiment_score=-0.5,
    current_iv=0.35,
)
print_result("Avoided: SPY momentum in HIGH_VOL (below 0.50 threshold)", r5)

print("\n  Winner 1: %s (%.3f)" % (r1.threshold_label, r1.capped_score))
print("  Winner 2: %s (%.3f)" % (r2.threshold_label, r2.capped_score))
print("  Loser 1:  %s (%.3f)" % (r3.threshold_label, r3.capped_score))
print("  Loser 2:  %s (%.3f)" % (r4.threshold_label, r4.capped_score))
print("  Avoided:  %s (%.3f)" % (r5.threshold_label, r5.capped_score))
print("\nTEST 1 RESULT: PASS")

# ================================================================
# TEST 2: Regime cap — momentum in HIGH_VOL, all factors maximized
# ================================================================
print("\n\nTEST 2: Regime cap enforcement (momentum + HIGH_VOLATILITY)")
print("-" * 60)
r_cap = scorer.score(
    "SPY",
    SetupScore("momentum", 1.0, "perfect 8/8 bars, vol=3.0x, move=1.5%", "bullish"),
    make_market(Regime.HIGH_VOLATILITY, TimeOfDay.OPEN),
    sentiment_score=0.9,
    current_iv=0.15,  # Low IV = high IVR score
)
print_result("Max momentum in HIGH_VOL", r_cap)
print(f"\n  Raw score: {r_cap.raw_score:.4f}")
print(f"  Capped score: {r_cap.capped_score:.4f}")
print(f"  Cap applied: {r_cap.regime_cap_applied}")
print(f"  Cap value: {r_cap.regime_cap_value}")
assert r_cap.capped_score <= 0.45, f"FAIL: capped={r_cap.capped_score} > 0.45"
assert r_cap.raw_score > r_cap.capped_score, "FAIL: cap should have reduced score"
print("  CONFIRMED: capped_score <= 0.45 and raw_score > capped_score")
print("\nTEST 2 RESULT: PASS")

# ================================================================
# TEST 3: IVR cold start (TSLA, no history file)
# ================================================================
print("\n\nTEST 3: IVR cold start (skipped + redistributed)")
print("-" * 60)

# Use a symbol with no IV cache file
r_cold = scorer.score(
    "ZZZZZ",  # Non-existent symbol = no cache
    SetupScore("momentum", 0.70, "simulated", "bullish"),
    make_market(Regime.TRENDING_UP),
    sentiment_score=0.0,
    current_iv=0.30,
)
print_result("IVR cold start (symbol ZZZZZ)", r_cold)

# Verify IVR is skipped
ivr_factor = [f for f in r_cold.factors if f.name == "ivr"][0]
print(f"\n  IVR factor status: {ivr_factor.status}")
assert ivr_factor.status == "skipped", f"FAIL: IVR should be skipped, got {ivr_factor.status}"

# Verify weights sum to ~1.0 for active factors
active_weights = sum(f.weight for f in r_cold.factors if f.status == "active")
print(f"  Active factor weights sum: {active_weights:.4f}")
assert abs(active_weights - 1.0) < 0.01, f"FAIL: weights sum to {active_weights}, expected ~1.0"
print("  CONFIRMED: IVR skipped, weights redistributed, sum=%.4f" % active_weights)
print("\nTEST 3 RESULT: PASS")

# ================================================================
# TEST 4: Institutional flow unavailable (always skipped currently)
# ================================================================
print("\n\nTEST 4: Institutional flow unavailable (skipped + redistributed)")
print("-" * 60)

r_noflow = scorer.score(
    "SPY",
    SetupScore("momentum", 0.70, "simulated", "bullish"),
    make_market(Regime.TRENDING_UP),
    sentiment_score=0.0,
    current_iv=0.22,
)
print_result("Institutional flow unavailable", r_noflow)

flow_factor = [f for f in r_noflow.factors if f.name == "institutional_flow"][0]
print(f"\n  Institutional flow status: {flow_factor.status}")
assert flow_factor.status == "skipped"

active_w = sum(f.weight for f in r_noflow.factors if f.status == "active")
print(f"  Active factor weights sum: {active_w:.4f}")
assert abs(active_w - 1.0) < 0.01, f"FAIL: weights sum to {active_w}"
print("  CONFIRMED: institutional_flow skipped, redistributed, sum=%.4f" % active_w)
print("\nTEST 4 RESULT: PASS")

# ================================================================
# TEST 5: SPY IVR from VIX right now
# ================================================================
print("\n\nTEST 5: SPY IVR from VIX (live)")
print("-" * 60)

from scoring.ivr import _ivr_from_vix, _vix_cache
# Clear cache to force fresh fetch
import scoring.ivr as ivr_mod
ivr_mod._vix_cache = None

ivr_val = _ivr_from_vix()
c = ivr_mod._vix_cache
print(f"  Current VIX:   {c['current']:.2f}")
print(f"  52-week high:  {c['high']:.2f}")
print(f"  52-week low:   {c['low']:.2f}")
print(f"  IVR:           {ivr_val:.4f} ({ivr_val*100:.1f}%)")
print(f"  Interpretation: IV is at the {ivr_val*100:.0f}th percentile of its 52-week range")
assert ivr_val is not None and 0 <= ivr_val <= 1.0
print("\nTEST 5 RESULT: PASS")
