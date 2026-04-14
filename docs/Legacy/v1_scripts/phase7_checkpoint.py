"""Phase 7 Validation Checkpoint — Position Sizing."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

print("=" * 70)
print("PHASE 7 VALIDATION CHECKPOINT")
print("=" * 70)

from sizing.sizer import calculate

def show(label, r):
    print(f"\n  --- {label} ---")
    print(f"    Step 1: base_risk       = account * 4%         = ${r.base_risk:,.2f}")
    print(f"    Step 2: confidence_risk  = base * confidence    = ${r.confidence_risk:,.2f}")
    print(f"    Step 3: after_dd_halving = {'* 0.5 (8%% drawdown)' if r.after_drawdown_halving != r.confidence_risk else '(no halving)':<30s} = ${r.after_drawdown_halving:,.2f}")
    print(f"    Step 4: after_pdt_halving= {'* 0.5 (PDT)' if r.after_pdt_halving != r.after_drawdown_halving else '(no halving)':<30s} = ${r.after_pdt_halving:,.2f}")
    print(f"    Step 5: final_risk       = ${r.final_risk:,.2f}")
    print(f"            premium/contract = ${r.premium_per_contract:,.2f}")
    print(f"            contracts        = floor({r.final_risk:.2f} / {r.premium_per_contract:.2f}) = {r.contracts}")
    print(f"    Halvings: {r.halvings_applied or 'none'}")
    if r.blocked:
        print(f"    BLOCKED: {r.block_reason}")


# ================================================================
# TEST 1: $10K, conf=0.72, premium=$1.20, no halvings
# ================================================================
print("\nTEST 1: $10K, conf=0.72, premium=$1.20, no halvings")
print("-" * 60)
r1 = calculate(
    account_value=10000, confidence=0.72, premium=1.20,
    day_start_value=10000, starting_balance=10000,
    current_exposure=0, is_same_day_trade=False, day_trades_remaining=3,
)
show("No halvings", r1)
print(f"\n  Arithmetic:")
print(f"    base_risk       = $10,000 * 0.04 = $400.00")
print(f"    confidence_risk = $400 * 0.72    = $288.00")
print(f"    no halvings applied")
print(f"    contracts       = floor($288.00 / $120.00) = {288 // 120} = {r1.contracts}")
assert r1.contracts == 2
assert r1.base_risk == 400.0
assert r1.confidence_risk == 288.0
print("\nTEST 1 RESULT: PASS")

# ================================================================
# TEST 2: $10K, conf=0.85, premium=$2.10, no halvings
# ================================================================
print("\n\nTEST 2: $10K, conf=0.85, premium=$2.10, no halvings")
print("-" * 60)
r2 = calculate(
    account_value=10000, confidence=0.85, premium=2.10,
    day_start_value=10000, starting_balance=10000,
    current_exposure=0, is_same_day_trade=False, day_trades_remaining=3,
)
show("No halvings, higher confidence", r2)
print(f"\n  Arithmetic:")
print(f"    base_risk       = $10,000 * 0.04 = $400.00")
print(f"    confidence_risk = $400 * 0.85    = $340.00")
print(f"    no halvings applied")
print(f"    contracts       = floor($340.00 / $210.00) = {340 // 210} = {r2.contracts}")
assert r2.contracts == 1
assert r2.confidence_risk == 340.0
print("\nTEST 2 RESULT: PASS")

# ================================================================
# TEST 3: $10K, conf=0.72, premium=$1.20, down 8% today
# ================================================================
print("\n\nTEST 3: $10K (was $10,870 at open), conf=0.72, premium=$1.20, down 8%")
print("-" * 60)
# Account was $10,870 at open, now $10,000 -> down 8.0%
r3 = calculate(
    account_value=10000, confidence=0.72, premium=1.20,
    day_start_value=10870, starting_balance=10870,
    current_exposure=0, is_same_day_trade=False, day_trades_remaining=3,
)
show("8% daily drawdown halving", r3)
day_dd = ((10870 - 10000) / 10870) * 100
print(f"\n  Arithmetic:")
print(f"    day_drawdown    = (${10870} - ${10000}) / ${10870} = {day_dd:.1f}% >= 8%")
print(f"    base_risk       = $10,000 * 0.04 = $400.00")
print(f"    confidence_risk = $400 * 0.72    = $288.00")
print(f"    Step 3 halving  = $288.00 * 0.5  = $144.00")
print(f"    contracts       = floor($144.00 / $120.00) = {144 // 120} = {r3.contracts}")
print(f"    Test 1 had {r1.contracts} contracts, Test 3 has {r3.contracts} (halved)")
assert r3.contracts == 1
assert r3.after_drawdown_halving == 144.0
assert "day_drawdown" in r3.halvings_applied[0]
print("\nTEST 3 RESULT: PASS")

# ================================================================
# TEST 4: $10K, conf=0.72, premium=$1.20, down 8% AND PDT halving
# ================================================================
print("\n\nTEST 4: Both halvings — 8% drawdown + PDT (<2 remaining, same-day)")
print("-" * 60)
r4 = calculate(
    account_value=10000, confidence=0.72, premium=1.20,
    day_start_value=10870, starting_balance=10870,
    current_exposure=0, is_same_day_trade=True, day_trades_remaining=1,
)
show("Both halvings compounded", r4)
print(f"\n  Arithmetic:")
print(f"    base_risk       = $10,000 * 0.04 = $400.00")
print(f"    confidence_risk = $400 * 0.72    = $288.00")
print(f"    Step 3 halving  = $288.00 * 0.5  = $144.00 (8% daily drawdown)")
print(f"    Step 4 halving  = $144.00 * 0.5  = $72.00  (PDT, 1 trade remaining)")
print(f"    contracts       = floor($72.00 / $120.00) = 0 -> minimum 1")
print(f"    Test 1={r1.contracts}, Test 4={r4.contracts} (quarter of max, min 1 enforced)")
assert r4.contracts == 1
assert r4.after_pdt_halving == 72.0
assert len(r4.halvings_applied) == 2
assert "day_drawdown" in r4.halvings_applied[0]
assert "pdt" in r4.halvings_applied[1]
print("\nTEST 4 RESULT: PASS")

# ================================================================
# TEST 5: Three survival rule blocks
# ================================================================
print("\n\nTEST 5: Three survival rule blocks")
print("-" * 60)

# 5a: Down 25% from starting balance
print("\n  5a: Down 25% from starting balance")
r5a = calculate(
    account_value=7500, confidence=0.80, premium=1.00,
    day_start_value=8000, starting_balance=10000,
    current_exposure=0, is_same_day_trade=False, day_trades_remaining=3,
)
dd_total = ((10000 - 7500) / 10000) * 100
print(f"    Starting balance: $10,000 | Current: $7,500 | Drawdown: {dd_total:.0f}%")
print(f"    Contracts: {r5a.contracts}")
print(f"    Blocked: {r5a.blocked}")
print(f"    Reason: {r5a.block_reason}")
assert r5a.contracts == 0 and r5a.blocked

# 5b: Down 15% today
print("\n  5b: Down 15% today")
r5b = calculate(
    account_value=8500, confidence=0.80, premium=1.00,
    day_start_value=10000, starting_balance=12000,
    current_exposure=0, is_same_day_trade=False, day_trades_remaining=3,
)
dd_day = ((10000 - 8500) / 10000) * 100
print(f"    Day open: $10,000 | Current: $8,500 | Day drawdown: {dd_day:.0f}%")
print(f"    Contracts: {r5b.contracts}")
print(f"    Blocked: {r5b.blocked}")
print(f"    Reason: {r5b.block_reason}")
assert r5b.contracts == 0 and r5b.blocked

# 5c: Exposure at 20%
print("\n  5c: Total exposure at 20% of account")
r5c = calculate(
    account_value=10000, confidence=0.80, premium=1.00,
    day_start_value=10000, starting_balance=10000,
    current_exposure=2000, is_same_day_trade=False, day_trades_remaining=3,
)
exp_pct = (2000 / 10000) * 100
print(f"    Account: $10,000 | Open exposure: $2,000 | Exposure: {exp_pct:.0f}%")
print(f"    Contracts: {r5c.contracts}")
print(f"    Blocked: {r5c.blocked}")
print(f"    Reason: {r5c.block_reason}")
assert r5c.contracts == 0 and r5c.blocked

print("\n  All three survival rules correctly block with logged reasons")
print("\nTEST 5 RESULT: PASS")

# ================================================================
# TEST 6: Low confidence, cheap premium — minimum 1 contract
# ================================================================
print("\n\nTEST 6: $10K, conf=0.55, premium=$0.85, no halvings")
print("-" * 60)
r6 = calculate(
    account_value=10000, confidence=0.55, premium=0.85,
    day_start_value=10000, starting_balance=10000,
    current_exposure=0, is_same_day_trade=False, day_trades_remaining=3,
)
show("Low confidence, cheap premium", r6)
print(f"\n  Arithmetic:")
print(f"    base_risk       = $10,000 * 0.04 = $400.00")
print(f"    confidence_risk = $400 * 0.55    = $220.00")
print(f"    no halvings applied")
print(f"    premium/contract= $0.85 * 100    = $85.00")
print(f"    contracts       = floor($220.00 / $85.00) = {220 // 85} = {r6.contracts}")
assert r6.contracts == 2
assert r6.confidence_risk == 220.0
print(f"    Minimum 1 enforced: N/A (formula produced {r6.contracts} >= 1)")
print("\nTEST 6 RESULT: PASS")

# Bonus: prove minimum 1 with even lower values
print("\n  BONUS: minimum 1 enforcement")
r6b = calculate(
    account_value=3000, confidence=0.50, premium=1.50,
    day_start_value=3000, starting_balance=3000,
    current_exposure=0, is_same_day_trade=False, day_trades_remaining=3,
)
print(f"    $3K account, conf=0.50, premium=$1.50")
print(f"    base_risk=$120, conf_risk=$60, contract_cost=$150")
print(f"    floor($60 / $150) = 0 -> minimum 1 enforced")
print(f"    Result: {r6b.contracts} contract(s)")
assert r6b.contracts == 1

print("\nTEST 6 RESULT: PASS")
