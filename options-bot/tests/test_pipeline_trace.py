"""
Pipeline trace tests — catches integration bugs that code review misses.
These tests trace actual string values, return types, and data flow
through connected modules. Run before every bot start.

Usage:
    python tests/test_pipeline_trace.py

All tests must pass. Any failure means a bug exists in the pipeline,
regardless of whether individual modules look correct in isolation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")
        if detail:
            print(f"        {detail}")


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# SECTION 1: Scanner setup_type string consistency
# ============================================================
section("1. Scanner -> setup_type string consistency")

import pandas as pd
from scanner.setups import (
    score_momentum, score_mean_reversion,
    score_compression_breakout, score_catalyst, score_macro_trend,
)

EXPECTED_SETUP_TYPES = {
    "momentum", "mean_reversion", "compression_breakout",
    "catalyst", "macro_trend",
}

n = 60
prices_up = [570.0 + i * 0.05 for i in range(n)]
bars_up = pd.DataFrame({
    "open":   [p - 0.01 for p in prices_up],
    "high":   [p + 0.05 for p in prices_up],
    "low":    [p - 0.03 for p in prices_up],
    "close":  prices_up,
    "volume": [2000000 + i * 30000 for i in range(n)],
})
bars_15min = pd.DataFrame({
    "open":  [570.0, 571.0, 572.0, 573.0],
    "high":  [571.5, 572.5, 573.5, 574.5],
    "low":   [569.5, 570.5, 571.5, 572.5],
    "close": [571.0, 572.0, 573.0, 574.5],
    "volume": [5000000, 5500000, 6000000, 6500000],
})

for fn, args, label in [
    (score_momentum, (bars_up, "SPY"), "momentum"),
    (score_mean_reversion, (bars_up, "SPY"), "mean_reversion"),
    (score_compression_breakout, (bars_up, "SPY"), "compression_breakout"),
    (score_catalyst, (bars_up, "SPY", 0.8, 0.6), "catalyst"),
    (score_macro_trend, (bars_15min, "SPY"), "macro_trend"),
]:
    try:
        result = fn(*args)
        check(
            f"score_{label}() returns setup_type='{label}'",
            result.setup_type == label,
            f"Got '{result.setup_type}', expected '{label}'",
        )
        check(
            f"score_{label}() setup_type in EXPECTED_SETUP_TYPES",
            result.setup_type in EXPECTED_SETUP_TYPES,
            f"'{result.setup_type}' not in expected set",
        )
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  score_{label}() raised: {e}")


# ============================================================
# SECTION 2: setup_type -> REGIME_FIT / TOD_FIT key coverage
# ============================================================
section("2. setup_type -> REGIME_FIT / TOD_FIT coverage")

from scoring.scorer import REGIME_FIT, TOD_FIT
from market.context import Regime, TimeOfDay

for setup_type in EXPECTED_SETUP_TYPES:
    for regime in Regime:
        key = (setup_type, regime)
        check(
            f"REGIME_FIT has ({setup_type}, {regime.value})",
            key in REGIME_FIT,
            f"Missing key {key} — scorer will use 0.5 default",
        )

for setup_type in ["momentum", "mean_reversion", "compression_breakout", "macro_trend"]:
    for tod in [TimeOfDay.OPEN, TimeOfDay.MID_MORNING, TimeOfDay.MIDDAY,
                TimeOfDay.POWER_HOUR, TimeOfDay.CLOSE]:
        key = (setup_type, tod)
        check(
            f"TOD_FIT has ({setup_type}, {tod.value})",
            key in TOD_FIT,
            f"Missing key {key} — scorer will use 0.5 default",
        )


# ============================================================
# SECTION 3: Profile _profile_specific_entry_check accepts the
# setup_types it is designed for. Swing/TSLA have a time-of-day
# gate; the test freezes time to a safe 10:30 ET morning window
# so results are deterministic regardless of when the test runs.
# ============================================================
section("3. Profile entry check accepts expected setup_types")

import datetime as _dt_module
_real_datetime = _dt_module.datetime


class _FrozenDateTime(_real_datetime):
    """Freeze now() to Monday 2026-04-20 10:30 ET for profile time gates."""
    @classmethod
    def now(cls, tz=None):
        base = _real_datetime(2026, 4, 20, 14, 30)  # 10:30 ET = 14:30 UTC
        if tz is not None:
            return base.replace(tzinfo=_dt_module.timezone.utc).astimezone(tz)
        return base

_dt_module.datetime = _FrozenDateTime
try:
    from profiles.scalp_0dte import Scalp0DTEProfile
    from profiles.swing import SwingProfile
    from profiles.momentum import MomentumProfile
    from profiles.tsla_swing import TSLASwingProfile
    from scoring.scorer import Scorer
    from scanner.setups import SetupScore
    from market.context import MarketSnapshot

    scorer = Scorer()
    snap_trending = MarketSnapshot(
        regime=Regime.TRENDING_UP, time_of_day=TimeOfDay.MID_MORNING,
        timestamp="2026-04-17T10:30:00",
        spy_30min_move_pct=0.6, spy_60min_range_pct=0.5,
        spy_30min_reversals=1, spy_volume_ratio=2.0,
        vix_level=16.0, vix_intraday_change_pct=0.5, regime_reason="test",
    )
    snap_choppy = MarketSnapshot(
        regime=Regime.CHOPPY, time_of_day=TimeOfDay.MID_MORNING,
        timestamp="2026-04-17T10:30:00",
        spy_30min_move_pct=0.1, spy_60min_range_pct=0.15,
        spy_30min_reversals=4, spy_volume_ratio=1.2,
        vix_level=18.0, vix_intraday_change_pct=1.0, regime_reason="test",
    )

    PROFILE_SETUP_EXPECTATIONS = [
        (Scalp0DTEProfile(), snap_trending, "momentum",             True,  "scalp accepts momentum in TRENDING"),
        (Scalp0DTEProfile(), snap_choppy,   "compression_breakout", True,  "scalp accepts compression in CHOPPY"),
        (Scalp0DTEProfile(), snap_trending, "macro_trend",          True,  "scalp accepts macro_trend in TRENDING"),
        (Scalp0DTEProfile(), snap_trending, "mean_reversion",       False, "scalp rejects mean_reversion"),
        (Scalp0DTEProfile(), snap_trending, "catalyst",             False, "scalp rejects catalyst"),
        (SwingProfile(),     snap_trending, "momentum",             True,  "swing accepts momentum in TRENDING"),
        (SwingProfile(),     snap_trending, "compression_breakout", True,  "swing accepts compression in TRENDING"),
        (SwingProfile(),     snap_trending, "macro_trend",          True,  "swing accepts macro_trend in TRENDING"),
        (MomentumProfile(),  snap_trending, "momentum",             True,  "momentum accepts momentum in TRENDING"),
        (MomentumProfile(),  snap_choppy,   "momentum",             False, "momentum rejects CHOPPY regime"),
        (TSLASwingProfile(), snap_trending, "momentum",             True,  "tsla_swing accepts momentum"),
        (TSLASwingProfile(), snap_trending, "macro_trend",          True,  "tsla_swing accepts macro_trend"),
        (TSLASwingProfile(), snap_trending, "compression_breakout", False, "tsla_swing rejects compression"),
    ]

    for profile, snap, setup_type, expected_enter, desc in PROFILE_SETUP_EXPECTATIONS:
        try:
            setup = SetupScore(setup_type, 0.78, "test", "bullish")
            scored = scorer.score("SPY", setup, snap)
            decision = profile.should_enter(scored, snap.regime)
            check(desc, decision.enter == expected_enter,
                  f"expected enter={expected_enter}, got enter={decision.enter} ({decision.reason})")
        except Exception as e:
            FAIL += 1
            print(f"  FAIL  {desc}: {e}")
finally:
    _dt_module.datetime = _real_datetime


# ============================================================
# SECTION 4: _last_entry_time key consistency (source audit)
# ============================================================
section("4. _last_entry_time key consistency (source audit)")

import re

src = Path(__file__).parent.parent.joinpath("strategies/v2_strategy.py").read_text()
lines = src.split("\n")

write_keys = []
read_keys = []
for i, line in enumerate(lines):
    stripped = line.strip()
    if "_last_entry_time[" in stripped and "=" in stripped and not stripped.startswith("#"):
        m = re.search(r"_last_entry_time\[([^\]]+)\]", stripped)
        if not m:
            continue
        key_expr = m.group(1)
        if stripped.index("_last_entry_time") < stripped.index("="):
            write_keys.append((i + 1, key_expr, stripped[:80]))
        else:
            read_keys.append((i + 1, key_expr, stripped[:80]))

for lineno, key, line in write_keys:
    print(f"        Write at line {lineno}: key={key}")
for lineno, key, line in read_keys:
    print(f"        Read  at line {lineno}: key={key}")

all_keys = write_keys + read_keys
for lineno, key, line in all_keys:
    check(
        f"_last_entry_time key at line {lineno} uses profile name not setup_type",
        "setup_type" not in key and "setup.setup_type" not in key,
        f"Key '{key}' uses setup_type — will never match on read",
    )


# ============================================================
# SECTION 5: Sizer survival rules
# ============================================================
section("5. Sizer survival rules")

from sizing.sizer import calculate

r = calculate(4250, 0.72, 0.35, 5000, 5000, 0, True, 3)
check("Day down 15% blocks entry", r.blocked,
      f"Expected blocked=True, got blocked={r.blocked}")

r = calculate(3700, 0.72, 0.35, 3700, 5000, 0, True, 3)
check("Total down 25% blocks entry", r.blocked)

r = calculate(5000, 0.72, 0.35, 5000, 5000, 0, True, 0)
check("0 day trades blocks same-day entry", r.blocked)

r = calculate(5000, 0.72, 0.35, 5000, 5000, 0, True, 3)
check("Growth mode active at 5K", "GROWTH_MODE" in r.halvings_applied)
check("Growth mode gives >= 10 contracts at 5K OTM", r.contracts >= 10,
      f"Got {r.contracts} contracts")

r = calculate(26000, 0.72, 0.35, 26000, 26000, 0, True, 3)
check("Growth mode inactive at 26K", "GROWTH_MODE" not in r.halvings_applied)


# ============================================================
# SECTION 6: Exit logic — trailing stop not killed by profit lock
# ============================================================
section("6. Exit logic — trailing stop runs uninterrupted")

from profiles.scalp_0dte import Scalp0DTEProfile

p = Scalp0DTEProfile()
p.apply_config({"profit_target_pct": 60.0, "trailing_stop_pct": 25.0,
                "stop_loss_pct": 25.0, "max_hold_minutes": 45})
p.record_entry("t1", "SPY", "bullish", 0.72, 0.75, "2026-04-17T10:00:00", 0.35)

r = p.check_exit("t1", 65.0, 0.5, 10)
check("At 65% profit: trailing active, not triggered -> hold", not r.exit,
      f"Expected hold, got exit={r.exit} reason={r.reason}")

r = p.check_exit("t1", 85.0, 0.5, 15)
check("At 85% profit: profit_lock_80 does NOT fire when trail active",
      not r.exit or r.reason != "profit_lock_80",
      "profit_lock_80 fired at 85% — trailing stop bypassed")

for pnl in [120, 200, 300, 400]:
    p.check_exit("t1", float(pnl), 0.5, 20)

r = p.check_exit("t1", 374.0, 0.5, 25)
check("At 374% (26% from 400 peak): trailing stop fires",
      r.exit and r.reason == "trailing_stop",
      f"Expected trailing_stop, got exit={r.exit} reason={r.reason}")


# ============================================================
# SECTION 7: DB schema has all required columns
# ============================================================
section("7. DB schema — required columns present")

db_path = Path(__file__).parent.parent / "db" / "options_bot.db"
if not db_path.exists():
    print("  SKIP  DB does not exist yet (will be checked after first run)")
else:
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    required_cols = {
        "scanner_snapshots": ["macro_trend_score", "macro_trend_reason"],
        "learning_state":    ["tod_fit_overrides"],
        "trades":            ["hold_minutes", "setup_type", "confidence_score", "unrealized_pnl"],
        "profiles":          ["error_reason"],
        "v2_signal_logs":    ["block_reason", "entered", "trade_id"],
    }
    for table, cols in required_cols.items():
        cursor = conn.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        for col in cols:
            check(f"{table}.{col} exists", col in existing,
                  f"Column {col} missing from {table}")
    conn.close()


# ============================================================
# FINAL RESULT
# ============================================================
print(f"\n{'='*60}")
print(f"  RESULT: {PASS} passed, {FAIL} failed")
print(f"{'='*60}")
if FAIL > 0:
    print(f"\n  {FAIL} test(s) FAILED — do not start the bot until all pass.")
    sys.exit(1)
else:
    print("\n  All tests passed. Bot is clear to start.")
    sys.exit(0)
