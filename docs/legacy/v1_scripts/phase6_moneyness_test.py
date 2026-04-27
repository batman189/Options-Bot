"""Verify moneyness enforcement with synthetic chain data."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from selection.selector import OptionsSelector

selector = OptionsSelector()

print("=" * 70)
print("MONEYNESS ENFORCEMENT VERIFICATION (synthetic data)")
print("=" * 70)

# === TSLA OTM PUT (underlying=$363) ===
print("\nTEST 2 CORRECTED: TSLA OTM PUT, underlying=$363")
print("-" * 60)

chain = [
    {"strike": 355.0, "right": "PUT", "bid": 5.00, "ask": 5.20, "open_interest": 500, "volume": 200},
    {"strike": 360.0, "right": "PUT", "bid": 8.00, "ask": 8.15, "open_interest": 800, "volume": 400},
    {"strike": 362.5, "right": "PUT", "bid": 10.50, "ask": 10.65, "open_interest": 300, "volume": 150},
    {"strike": 365.0, "right": "PUT", "bid": 13.00, "ask": 13.20, "open_interest": 2400, "volume": 1400},
    {"strike": 367.5, "right": "PUT", "bid": 16.00, "ask": 16.20, "open_interest": 1000, "volume": 600},
]

underlying = 363.0
tier = selector._strike_tier(0.55)
target = selector._target_strike(underlying, tier, "PUT")
print(f"  Confidence: 0.55 -> tier: {tier}")
print(f"  Target strike: ${target} (underlying=${underlying})")
print(f"  OTM PUT requires strike < ${underlying}")
print()

filtered = selector._filter_chain(chain, "PUT", target, underlying, tier)
print(f"  Chain before filter: {len(chain)} contracts")
print(f"  Chain after filter:  {len(filtered)} contracts")
print()

for c in chain:
    in_filtered = c in filtered
    is_otm = c["strike"] < underlying
    status = "PASS" if in_filtered else "REJECT"
    reason = "OTM" if is_otm else "ITM (excluded)"
    print(f"    ${c['strike']:>6.1f} PUT | {reason:20s} | {status}")

print()
itm_leaked = [c for c in filtered if c["strike"] >= underlying]
assert len(itm_leaked) == 0, f"BUG: ITM strikes leaked: {[c['strike'] for c in itm_leaked]}"
print(f"  ITM contracts in result: 0 (CORRECT)")
print(f"  All {len(filtered)} filtered contracts have strike < ${underlying}")

# === SPY ATM CALL (underlying=$638) — confirm unaffected ===
print()
print("\nTEST 1 CORRECTED: SPY ATM CALL, underlying=$638")
print("-" * 60)

chain_spy = [
    {"strike": 636.0, "right": "CALL", "bid": 3.50, "ask": 3.55, "open_interest": 5000, "volume": 3000},
    {"strike": 637.0, "right": "CALL", "bid": 2.80, "ask": 2.85, "open_interest": 3000, "volume": 2500},
    {"strike": 638.0, "right": "CALL", "bid": 2.10, "ask": 2.15, "open_interest": 4000, "volume": 2800},
    {"strike": 639.0, "right": "CALL", "bid": 1.50, "ask": 1.55, "open_interest": 3500, "volume": 2200},
    {"strike": 640.0, "right": "CALL", "bid": 1.00, "ask": 1.05, "open_interest": 6000, "volume": 3500},
]

underlying_spy = 638.0
tier_spy = selector._strike_tier(0.75)
target_spy = selector._target_strike(underlying_spy, tier_spy, "CALL")
print(f"  Confidence: 0.75 -> tier: {tier_spy}")
print(f"  Target strike: ${target_spy} (underlying=${underlying_spy})")
print()

filtered_spy = selector._filter_chain(chain_spy, "CALL", target_spy, underlying_spy, tier_spy)
print(f"  Chain before filter: {len(chain_spy)} contracts")
print(f"  Chain after filter:  {len(filtered_spy)} contracts")
print()

for c in chain_spy:
    in_filtered = c in filtered_spy
    print(f"    ${c['strike']:>6.1f} CALL | {'PASS' if in_filtered else 'REJECT'}")

print()
print(f"  ATM tier has no directional filter — both ITM and OTM sides included")
print(f"  This is correct: ATM allows nearby strikes on either side")

# === TSLA ITM PUT (confidence=0.85) — confirm ITM enforcement ===
print()
print("\nBONUS: TSLA ITM PUT conf=0.85, underlying=$363")
print("-" * 60)

tier_itm = selector._strike_tier(0.85)
target_itm = selector._target_strike(363.0, tier_itm, "PUT")
print(f"  Confidence: 0.85 -> tier: {tier_itm}")
print(f"  Target strike: ${target_itm} (ITM PUT = strike > underlying)")

filtered_itm = selector._filter_chain(chain, "PUT", target_itm, 363.0, tier_itm)
print(f"  Filtered: {len(filtered_itm)} contracts")
for c in filtered_itm:
    assert c["strike"] > 363.0, f"BUG: ${c['strike']} is not ITM for PUT"
    print(f"    ${c['strike']:>6.1f} PUT (ITM: strike > ${363.0})")
print(f"  All filtered contracts are ITM (CORRECT)")
