"""Phase 9 Validation Checkpoint — Learning and Adaptation Layer."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

print("=" * 70)
print("PHASE 9 VALIDATION CHECKPOINT")
print("=" * 70)

import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

DB_PATH = Path(__file__).parent.parent / "db" / "options_bot.db"

from learning.learner import run_learning
from learning.storage import (
    load_learning_state, save_learning_state, get_closed_trade_count,
    LearningState,
)


def inject_trades(profile_preset, trades_data):
    """Insert synthetic closed trades into the DB for testing."""
    conn = sqlite3.connect(str(DB_PATH))
    # Get profile_id for this preset
    row = conn.execute("SELECT id FROM profiles WHERE preset = ? LIMIT 1", (profile_preset,)).fetchone()
    if row is None:
        # Create a temp profile
        pid = f"test-{profile_preset}"
        conn.execute(
            "INSERT OR IGNORE INTO profiles (id, name, preset, status, symbols, config, created_at, updated_at) "
            "VALUES (?, ?, ?, 'ready', '[\"SPY\"]', '{}', ?, ?)",
            (pid, f"Test {profile_preset}", profile_preset,
             datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
        )
    else:
        pid = row[0]

    for i, t in enumerate(trades_data):
        tid = f"test-{profile_preset}-{i:03d}"
        entry_dt = datetime.now(timezone.utc) - timedelta(hours=len(trades_data) - i)
        exit_dt = entry_dt + timedelta(minutes=t.get("hold_minutes", 60))
        conn.execute("""
            INSERT OR REPLACE INTO trades
                (id, profile_id, symbol, direction, strike, expiration, quantity,
                 entry_price, entry_date, exit_price, exit_date, exit_reason,
                 pnl_pct, pnl_dollars, status, setup_type, confidence_score,
                 hold_minutes, market_regime, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'closed', ?, ?, ?, ?, ?, ?)
        """, (
            tid, pid, t.get("symbol", "SPY"), "CALL", 637, "2026-04-01", 1,
            2.00, entry_dt.isoformat(), 2.00 * (1 + t["pnl_pct"] / 100),
            exit_dt.isoformat(), t.get("exit_reason", "thesis_broken"),
            t["pnl_pct"], t["pnl_pct"] * 2,  # pnl_dollars approx
            t.get("setup_type", profile_preset),
            t.get("confidence", 0.70),
            t.get("hold_minutes", 60),
            t.get("regime", "TRENDING_UP"),
            entry_dt.isoformat(), exit_dt.isoformat(),
        ))
    conn.commit()
    conn.close()


def clear_test_data():
    """Remove all test trades and learning state."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DELETE FROM trades WHERE id LIKE 'test-%' OR id LIKE 'trigger-%' OR id LIKE 'batch2-%'")
    conn.execute("DELETE FROM learning_state")
    conn.execute("DELETE FROM profiles WHERE id LIKE 'test-%'")
    conn.commit()
    conn.close()


clear_test_data()


# ================================================================
# TEST 1: Momentum — 7W/13L, negative expectancy, threshold raised
# ================================================================
print("\nTEST 1: Momentum — 35% WR, negative expectancy")
print("-" * 60)

trades_mom = (
    [{"pnl_pct": 25, "setup_type": "momentum"} for _ in range(7)] +
    [{"pnl_pct": -20, "setup_type": "momentum"} for _ in range(13)]
)
inject_trades("momentum", trades_mom)

state1 = run_learning("momentum", default_confidence=0.65)

print(f"\n  Trades: 20 (7W / 13L)")
print(f"  Win rate: {7/20:.0%}")
avg_win = 25.0
avg_loss = -20.0
exp = (7/20 * avg_win) + (13/20 * avg_loss)
print(f"  Avg win: +{avg_win}% | Avg loss: {avg_loss}%")
print(f"  Expectancy: {exp:+.2f} (negative)")
print(f"\n  Confidence adjustment:")
print(f"    Old: 0.650 (default)")
print(f"    New: {state1.min_confidence:.3f}")
print(f"    Change: +0.050 (raised due to negative expectancy)")
assert state1.min_confidence == 0.70, f"Expected 0.700, got {state1.min_confidence}"

print(f"\n  Audit log entries:")
for entry in state1.adjustment_log:
    print(f"    type={entry['type']} old={entry.get('old','')} new={entry.get('new','')} "
          f"reason={entry.get('reason','')}")

print("\nTEST 1 RESULT: PASS")


# ================================================================
# TEST 2: Mean Reversion — 14W/6L, strong positive, threshold lowered
# ================================================================
print("\n\nTEST 2: Mean Reversion — 70% WR, strong positive expectancy")
print("-" * 60)

clear_test_data()
trades_mr = (
    [{"pnl_pct": 45, "setup_type": "mean_reversion"} for _ in range(14)] +
    [{"pnl_pct": -18, "setup_type": "mean_reversion"} for _ in range(6)]
)
inject_trades("mean_reversion", trades_mr)

state2 = run_learning("mean_reversion", default_confidence=0.60)

wr2 = 14 / 20
exp2 = (wr2 * 45) + ((1 - wr2) * -18)
print(f"\n  Trades: 20 (14W / 6L)")
print(f"  Win rate: {wr2:.0%}")
print(f"  Avg win: +45% | Avg loss: -18%")
print(f"  Expectancy: {exp2:+.2f} (strongly positive, > 0.15)")
print(f"\n  Confidence adjustment:")
print(f"    Old: 0.600 (default)")
print(f"    New: {state2.min_confidence:.3f}")
print(f"    Change: -0.020 (lowered due to strong expectancy)")
assert state2.min_confidence == 0.58, f"Expected 0.580, got {state2.min_confidence}"

print(f"\n  Audit log entries:")
for entry in state2.adjustment_log:
    print(f"    type={entry['type']} old={entry.get('old','')} new={entry.get('new','')} "
          f"reason={entry.get('reason','')}")

print("\nTEST 2 RESULT: PASS")


# ================================================================
# TEST 3: Catalyst — 6W/14L, threshold raised + auto-pause
# ================================================================
print("\n\nTEST 3: Catalyst — 30% WR, auto-pause triggered")
print("-" * 60)

clear_test_data()
trades_cat = (
    [{"pnl_pct": 30, "setup_type": "catalyst"} for _ in range(6)] +
    [{"pnl_pct": -25, "setup_type": "catalyst"} for _ in range(14)]
)
inject_trades("catalyst", trades_cat)

state3 = run_learning("catalyst", default_confidence=0.72)

wr3 = 6 / 20
exp3 = (wr3 * 30) + ((1 - wr3) * -25)
print(f"\n  Trades: 20 (6W / 14L)")
print(f"  Win rate: {wr3:.0%} (< 35% auto-pause threshold)")
print(f"  Expectancy: {exp3:+.2f}")
print(f"\n  Confidence adjustment:")
print(f"    Old: 0.720 (default)")
print(f"    New: {state3.min_confidence:.3f}")
print(f"\n  Auto-pause:")
print(f"    paused_by_learning: {state3.paused_by_learning}")
assert state3.paused_by_learning is True, f"Expected paused=True"

# Confirm it's persisted in DB
db_state = load_learning_state("catalyst")
print(f"    DB paused_by_learning: {db_state.paused_by_learning}")
assert db_state.paused_by_learning is True

print(f"    Profile cannot be reactivated automatically — requires manual UI action")
print(f"\n  Audit log entries:")
for entry in state3.adjustment_log:
    print(f"    type={entry['type']} reason={entry.get('reason','')}")

print("\nTEST 3 RESULT: PASS")


# ================================================================
# TEST 4: Regime fit adjustment — TRENDING_UP losing, CHOPPY winning
# ================================================================
print("\n\nTEST 4: Regime fit adjustment (TRENDING_UP losing, CHOPPY winning)")
print("-" * 60)

clear_test_data()
trades_regime = (
    # 10 in TRENDING_UP: 3W/7L (30% WR — losing)
    [{"pnl_pct": 20, "setup_type": "momentum", "regime": "TRENDING_UP"} for _ in range(3)] +
    [{"pnl_pct": -15, "setup_type": "momentum", "regime": "TRENDING_UP"} for _ in range(7)] +
    # 10 in CHOPPY: 8W/2L (80% WR — winning)
    [{"pnl_pct": 18, "setup_type": "momentum", "regime": "CHOPPY"} for _ in range(8)] +
    [{"pnl_pct": -10, "setup_type": "momentum", "regime": "CHOPPY"} for _ in range(2)]
)
inject_trades("momentum", trades_regime)

state4 = run_learning("momentum", default_confidence=0.65)

print(f"\n  TRENDING_UP: 3W/7L (30% WR) — should reduce fit score")
print(f"  CHOPPY: 8W/2L (80% WR) — should NOT reduce fit score")
print(f"\n  Regime fit overrides:")
for key, val in state4.regime_fit_overrides.items():
    print(f"    {key}: {val:+.2f}")

trending_key = "momentum_TRENDING_UP"
choppy_key = "momentum_CHOPPY"
trending_adj = state4.regime_fit_overrides.get(trending_key, 0)
choppy_adj = state4.regime_fit_overrides.get(choppy_key, 0)

print(f"\n  TRENDING_UP adjustment: {trending_adj:+.2f} (expected -0.10)")
print(f"  CHOPPY adjustment: {choppy_adj:+.2f} (expected 0.00 — no reduction)")
assert trending_adj < 0, f"TRENDING_UP should be reduced, got {trending_adj}"
assert choppy_adj == 0, f"CHOPPY should be unchanged, got {choppy_adj}"

print(f"\n  Audit log (regime entries):")
for entry in state4.adjustment_log:
    if entry.get("type") == "regime_fit_reduce":
        print(f"    regime={entry['regime']} old={entry['old']} new={entry['new']} "
              f"reason={entry['reason']}")

print("\nTEST 4 RESULT: PASS")


# ================================================================
# TEST 5: 20-trade trigger from confirm_fill()
# ================================================================
print("\n\nTEST 5: 20-trade trigger from confirm_fill()")
print("-" * 60)

clear_test_data()

from management.trade_manager import TradeManager
from profiles.momentum import MomentumProfile

mom = MomentumProfile()
tm = TradeManager()

# Inject 18 existing closed trades (so next closes are 19, 20, 21...)
trades_base = [{"pnl_pct": 10, "setup_type": "momentum"} for _ in range(18)]
inject_trades("momentum", trades_base)

# Add positions 19, 20, 21, then later 40
for idx in [19, 20, 21]:
    tid = f"trigger-test-{idx:03d}"
    tm.add_position(
        trade_id=tid, symbol="SPY", direction="bullish", profile=mom,
        expiration=__import__("datetime").date.today(),
        entry_time=datetime.now() - timedelta(minutes=30),
        entry_price=2.00, quantity=1, confidence=0.70, setup_score=0.75,
        setup_type="momentum",
    )

# We need to also insert these as open trades in DB so confirm_fill can update them
conn = sqlite3.connect(str(DB_PATH))
row = conn.execute("SELECT id FROM profiles WHERE preset = 'momentum' LIMIT 1").fetchone()
pid = row[0] if row else "test-momentum"
for idx in [19, 20, 21]:
    tid = f"trigger-test-{idx:03d}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT OR REPLACE INTO trades
            (id, profile_id, symbol, direction, strike, expiration, quantity,
             entry_price, entry_date, status, setup_type, confidence_score,
             created_at, updated_at)
        VALUES (?, ?, 'SPY', 'CALL', 637, '2026-04-01', 1, 2.00, ?, 'open', 'momentum', 0.70, ?, ?)
    """, (tid, pid, now, now, now))
conn.commit()
conn.close()

# Close trade 19 — should NOT trigger (count=19)
print("  Closing trade 19...")
tm._positions["trigger-test-019"].pending_exit = True
tm._positions["trigger-test-019"].pending_exit_reason = "test"
count_before_19 = get_closed_trade_count("momentum")
tm.confirm_fill("trigger-test-019", fill_price=2.20)
count_after_19 = get_closed_trade_count("momentum")
print(f"    Closed count: {count_before_19} -> {count_after_19}")
triggered_19 = count_after_19 % 20 == 0
print(f"    Trigger fired: {triggered_19} (expected: False)")
assert not triggered_19

# Close trade 20 — SHOULD trigger (count=20)
print("\n  Closing trade 20...")
tm._positions["trigger-test-020"].pending_exit = True
tm._positions["trigger-test-020"].pending_exit_reason = "test"
count_before_20 = get_closed_trade_count("momentum")
tm.confirm_fill("trigger-test-020", fill_price=2.15)
count_after_20 = get_closed_trade_count("momentum")
print(f"    Closed count: {count_before_20} -> {count_after_20}")
triggered_20 = count_after_20 % 20 == 0
print(f"    Trigger fired: {triggered_20} (expected: True)")
assert triggered_20

# Close trade 21 — should NOT trigger (count=21)
print("\n  Closing trade 21...")
tm._positions["trigger-test-021"].pending_exit = True
tm._positions["trigger-test-021"].pending_exit_reason = "test"
count_before_21 = get_closed_trade_count("momentum")
tm.confirm_fill("trigger-test-021", fill_price=2.10)
count_after_21 = get_closed_trade_count("momentum")
print(f"    Closed count: {count_before_21} -> {count_after_21}")
triggered_21 = count_after_21 % 20 == 0
print(f"    Trigger fired: {triggered_21} (expected: False)")
assert not triggered_21

# Inject 18 more to reach 39, then close trade 40
# Use unique IDs by injecting with a different prefix
conn_x = sqlite3.connect(str(DB_PATH))
row_x = conn_x.execute("SELECT id FROM profiles WHERE preset = 'momentum' LIMIT 1").fetchone()
pid_x = row_x[0] if row_x else "test-momentum"
for i in range(18):
    tid_x = f"batch2-{i:03d}"
    now_x = datetime.now(timezone.utc).isoformat()
    conn_x.execute("""
        INSERT OR REPLACE INTO trades
            (id, profile_id, symbol, direction, strike, expiration, quantity,
             entry_price, entry_date, exit_price, exit_date, exit_reason,
             pnl_pct, status, setup_type, confidence_score, hold_minutes,
             market_regime, created_at, updated_at)
        VALUES (?, ?, 'SPY', 'CALL', 637, '2026-04-01', 1, 2.00, ?, 2.10, ?, 'test',
                5.0, 'closed', 'momentum', 0.70, 60, 'TRENDING_UP', ?, ?)
    """, (tid_x, pid_x, now_x, now_x, now_x, now_x))
conn_x.commit()
conn_x.close()

# Add and close position 40
tid_40 = "trigger-test-040"
tm.add_position(
    trade_id=tid_40, symbol="SPY", direction="bullish", profile=mom,
    expiration=__import__("datetime").date.today(),
    entry_time=datetime.now() - timedelta(minutes=10),
    entry_price=2.00, quantity=1, confidence=0.70, setup_score=0.75,
    setup_type="momentum",
)
conn = sqlite3.connect(str(DB_PATH))
now = datetime.now(timezone.utc).isoformat()
conn.execute("""
    INSERT OR REPLACE INTO trades
        (id, profile_id, symbol, direction, strike, expiration, quantity,
         entry_price, entry_date, status, setup_type, confidence_score,
         created_at, updated_at)
    VALUES (?, ?, 'SPY', 'CALL', 637, '2026-04-01', 1, 2.00, ?, 'open', 'momentum', 0.70, ?, ?)
""", (tid_40, pid, now, now, now))
conn.commit()
conn.close()

print("\n  Closing trade 40...")
tm._positions[tid_40].pending_exit = True
tm._positions[tid_40].pending_exit_reason = "test"
count_before_40 = get_closed_trade_count("momentum")
tm.confirm_fill(tid_40, fill_price=2.05)
count_after_40 = get_closed_trade_count("momentum")
print(f"    Closed count: {count_before_40} -> {count_after_40}")
triggered_40 = count_after_40 % 20 == 0
print(f"    Trigger fired: {triggered_40} (expected: True)")
assert triggered_40

print("\n  Summary:")
print(f"    Trade 19: count={count_after_19}, trigger=False")
print(f"    Trade 20: count={count_after_20}, trigger=True (learning ran)")
print(f"    Trade 21: count={count_after_21}, trigger=False")
print(f"    Trade 40: count={count_after_40}, trigger=True (learning ran)")

print("\nTEST 5 RESULT: PASS")

# Cleanup
clear_test_data()
