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
# SECTION 8: get_stock_bars returns RECENT bars, not oldest
# Alpaca without a start param returns earliest history bars.
# This caused 938 signals, 0 trades on launch day.
# ============================================================
section("8. get_stock_bars() returns recent bars")

src = (Path(__file__).parent.parent / "data" / "unified_client.py").read_text()

fn_start = src.find("def get_stock_bars")
fn_end = src.find("\n    def ", fn_start + 1)
fn_src = src[fn_start:fn_end]

check(
    "get_stock_bars sets a start= parameter on StockBarsRequest",
    "start=" in fn_src,
    "No start= found — Alpaca will return oldest bars, not recent",
)
check(
    "get_stock_bars tails the result",
    ".tail(" in fn_src,
    "No .tail() found — result may include stale pre-market bars",
)
check(
    "get_stock_bars uses timezone-aware start time",
    "timezone.utc" in fn_src or "timedelta" in fn_src,
    "Start time must be timezone-aware",
)


# ============================================================
# SECTION 9: OTM strike distance — cheap contracts not 1-strike OTM
# The lotto-ticket thesis requires 0.5% OTM targets, not $1 OTM.
# Single-strike OTM for SPY ($1) still prices at $1.50+ and defeats
# the "buy 50 tickets, 10x on a small move" strategy.
# ============================================================
section("9. OTM strike distance — cheap contracts not 1-strike OTM")

from selection.selector import OptionsSelector
sel = OptionsSelector()

underlying = 570.0
put_strike = sel._target_strike(underlying, "otm", "PUT")
call_strike = sel._target_strike(underlying, "otm", "CALL")

check(
    "OTM PUT strike is at least $2 below underlying for SPY",
    underlying - put_strike >= 2.0,
    f"PUT strike {put_strike} is only ${underlying - put_strike:.1f} below {underlying}",
)
check(
    "OTM CALL strike is at least $2 above underlying for SPY",
    call_strike - underlying >= 2.0,
    f"CALL strike {call_strike} is only ${call_strike - underlying:.1f} above {underlying}",
)
check(
    "OTM strike is not more than $10 from underlying (still tradeable)",
    abs(underlying - put_strike) <= 10.0,
    f"Strike too far: ${abs(underlying - put_strike):.1f} OTM",
)
print(
    f"        SPY at ${underlying:.0f}: PUT target=${put_strike:.0f} "
    f"({underlying - put_strike:.1f} OTM), CALL target=${call_strike:.0f} "
    f"({call_strike - underlying:.1f} OTM)"
)

# Confidence-tier mapping: ITM must NEVER be returned by _strike_tier
for conf in [0.55, 0.65, 0.72, 0.80, 0.95]:
    tier = sel._strike_tier(conf, use_otm=False)
    check(
        f"_strike_tier({conf}) never returns 'itm'",
        tier != "itm",
        f"Got '{tier}' for confidence {conf} — ITM selection is disabled",
    )

# use_otm=True bypasses confidence mapping
for conf in [0.55, 0.80, 0.95]:
    tier = sel._strike_tier(conf, use_otm=True)
    check(
        f"_strike_tier({conf}, use_otm=True) returns 'otm'",
        tier == "otm",
        f"Got '{tier}' — OTM flag should override confidence mapping",
    )


# ============================================================
# SECTION 10: Macro awareness layer — veto fires, fail-safe, timezone
# drift, atomic cap increment. The hot path MUST NOT call any LLM or
# network code. Every check here has a before-state and an after-state
# injected via SQL so we see real values, not mocks of the reader.
# ============================================================
section("10. Macro awareness — veto, fail-safe, timezone, atomic cap")

import sqlite3 as _sqlite3
from datetime import datetime as _dt, timedelta as _td, timezone as _tz
from unittest.mock import patch as _patch
from zoneinfo import ZoneInfo as _ZoneInfo

from config import DB_PATH as _DB_PATH
from macro import reader as _macro_reader
from macro.reader import snapshot_macro_context as _snapshot_macro
from market.context import Regime as _Regime, TimeOfDay as _TimeOfDay, MarketSnapshot as _Snapshot
from profiles.momentum import MomentumProfile as _MomentumProfile
from scanner.setups import SetupScore as _SetupScore
from scoring.scorer import Scorer as _Scorer, ScoringResult as _ScoringResult

_ET = _ZoneInfo("America/New_York")


def _wipe_macro_tables():
    _conn = _sqlite3.connect(str(_DB_PATH))
    _conn.execute("DELETE FROM macro_events")
    _conn.execute("DELETE FROM macro_catalysts")
    _conn.execute("DELETE FROM macro_regime")
    _conn.execute("DELETE FROM macro_api_usage")
    _conn.commit()
    _conn.close()


def _insert_event(symbol, event_type, event_time_et, impact_level,
                  source_url="https://example.com/x"):
    # Derive event_time_utc from the ET string so tests exercise the real
    # production path (reader SELECTs filter on event_time_utc).
    _dt_obj = _dt.fromisoformat(event_time_et)
    if _dt_obj.tzinfo is None:
        _dt_obj = _dt_obj.replace(tzinfo=_ET)
    _event_time_utc = _dt_obj.astimezone(_tz.utc).isoformat()
    _conn = _sqlite3.connect(str(_DB_PATH))
    _conn.execute(
        """INSERT INTO macro_events
           (symbol, event_type, event_time_et, event_time_utc,
            impact_level, source_url, fetched_at)
           VALUES (?,?,?,?,?,?,?)""",
        (symbol, event_type, event_time_et, _event_time_utc, impact_level,
         source_url, _dt.now(_tz.utc).isoformat()),
    )
    _conn.commit()
    _conn.close()


# Ensure the schema is at the current version — the macro layer has
# extended the events table with event_time_utc and the catalysts table
# with content_hash. init_db is idempotent; skipping this on a stale DB
# makes the _insert_event helper crash with "no such column".
import asyncio as _asyncio_bootstrap
from backend.database import init_db as _init_db_bootstrap
_asyncio_bootstrap.run(_init_db_bootstrap())


def _insert_regime(risk_tone, fetched_at_utc):
    _conn = _sqlite3.connect(str(_DB_PATH))
    _conn.execute(
        """INSERT OR REPLACE INTO macro_regime
           (id, risk_tone, vix_context, major_themes_json, fetched_at)
           VALUES ('current', ?, '', '[]', ?)""",
        (risk_tone, fetched_at_utc.isoformat()),
    )
    _conn.commit()
    _conn.close()


_base_snap = _Snapshot(
    regime=_Regime.TRENDING_UP, time_of_day=_TimeOfDay.MID_MORNING,
    timestamp="2026-04-20T14:30:00",
    spy_30min_move_pct=0.6, spy_60min_range_pct=0.5,
    spy_30min_reversals=1, spy_volume_ratio=2.0,
    vix_level=16.0, vix_intraday_change_pct=0.5, regime_reason="test",
)
_setup_bull = _SetupScore("momentum", 0.85, "strong", "bullish")
_setup_bear = _SetupScore("momentum", 0.85, "strong", "bearish")


# --- 10.1 — empty table is a pre-macro baseline (fail-safe) ---
_wipe_macro_tables()
_scorer = _Scorer()
_profile = _MomentumProfile()
_ctx_empty = _snapshot_macro()

_r_empty = _scorer.score("SPY", _setup_bull, _base_snap, macro_ctx=_ctx_empty)
check(
    "empty macro tables: scorer returns non-vetoed result (fail-safe)",
    not _r_empty.macro_cap_applied and not _r_empty.macro_nudge_applied,
    f"veto={_r_empty.macro_cap_applied} nudge={_r_empty.macro_nudge_applied}",
)
check(
    "empty macro tables: score is not zero (baseline behavior preserved)",
    _r_empty.capped_score > 0.5,
    f"capped={_r_empty.capped_score}",
)
_d_empty = _profile.should_enter(_r_empty, _base_snap.regime, macro_ctx=_ctx_empty)
check(
    "empty macro tables: profile accepts (baseline)",
    _d_empty.enter,
    f"reason={_d_empty.reason}",
)


# --- 10.2 — HIGH event inside buffer: scorer veto fires ---
_wipe_macro_tables()
_now_et = _dt.now(_ET)
_event_time = (_now_et + _td(minutes=10)).isoformat()
_insert_event("*", "FOMC", _event_time, "HIGH",
              "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
_ctx_high = _snapshot_macro()

_r_high = _scorer.score("SPY", _setup_bull, _base_snap, macro_ctx=_ctx_high)
check(
    "HIGH FOMC in 10min: scorer capped_score == 0.0",
    _r_high.capped_score == 0.0,
    f"capped={_r_high.capped_score}",
)
check(
    "HIGH FOMC in 10min: threshold_label == 'no_trade'",
    _r_high.threshold_label == "no_trade",
    f"label={_r_high.threshold_label}",
)
check(
    "HIGH FOMC in 10min: macro_veto_reason names FOMC",
    _r_high.macro_veto_reason is not None and "FOMC" in _r_high.macro_veto_reason,
    f"reason={_r_high.macro_veto_reason!r}",
)


# --- 10.3 — profile-level veto fires with macro_event_veto reason ---
# Bypass the scorer veto by constructing a non-vetoed result directly so
# we can isolate the profile-side check.
_fake_scored = _ScoringResult(
    symbol="SPY", setup_type="momentum", raw_score=0.85, capped_score=0.85,
    regime_cap_applied=False, regime_cap_value=None,
    threshold_label="high_conviction", direction="bullish", factors=[],
)
_d_high = _profile.should_enter(_fake_scored, _base_snap.regime, macro_ctx=_ctx_high)
check(
    "profile veto: enter=False when HIGH event in buffer",
    not _d_high.enter,
    f"enter={_d_high.enter}",
)
check(
    "profile veto: reason starts with 'macro_event_veto:'",
    _d_high.reason.startswith("macro_event_veto:"),
    f"reason={_d_high.reason!r}",
)


# --- 10.3b — INTEGRATION: scorer veto + profile veto on the same ScoringResult ---
# Regression test for the ordering bug: without the macro check running
# BEFORE the confidence check, the scorer's capped_score=0.0 would trip
# min_confidence first and the rejection would be mislabeled as
# "confidence 0.000 < 0.550" instead of "macro_event_veto: FOMC in ...min".
# This is the production path — no fake ScoringResult, no bypass.
_wipe_macro_tables()
_insert_event("*", "FOMC", (_now_et + _td(minutes=10)).isoformat(), "HIGH")
_ctx = _snapshot_macro()
_real_scored = _scorer.score("SPY", _setup_bull, _base_snap, macro_ctx=_ctx)
# Scorer should have vetoed and set capped_score=0.0
check(
    "integration setup: scorer capped_score is 0.0 (veto fired)",
    _real_scored.capped_score == 0.0,
    f"capped={_real_scored.capped_score}",
)
_d = _profile.should_enter(_real_scored, _base_snap.regime, macro_ctx=_ctx)
check(
    "integration: profile reports macro_event_veto, not confidence",
    _d.reason.startswith("macro_event_veto:"),
    f"got reason={_d.reason!r}",
)


# --- 10.4 — HIGH event outside buffer does NOT veto ---
_wipe_macro_tables()
_event_time_far = (_now_et + _td(hours=2)).isoformat()  # 120min > 15min buffer
_insert_event("*", "FOMC", _event_time_far, "HIGH")
_ctx_far = _snapshot_macro()
_r_far = _scorer.score("SPY", _setup_bull, _base_snap, macro_ctx=_ctx_far)
check(
    "HIGH event 2h out: no veto (outside buffer)",
    not _r_far.macro_cap_applied,
    f"veto={_r_far.macro_cap_applied}",
)


# --- 10.5 — MEDIUM event at 5min does veto (smaller buffer) ---
_wipe_macro_tables()
_medium_event = (_now_et + _td(minutes=3)).isoformat()  # within MEDIUM buffer (5min)
_insert_event("*", "CPI", _medium_event, "MEDIUM")
_ctx_med = _snapshot_macro()
_r_med = _scorer.score("SPY", _setup_bull, _base_snap, macro_ctx=_ctx_med)
check(
    "MEDIUM event in 3min: veto fires (5min MEDIUM buffer)",
    _r_med.macro_cap_applied,
    f"veto={_r_med.macro_cap_applied} reason={_r_med.macro_veto_reason}",
)


# --- 10.6 — market-wide '*' events veto every symbol ---
# A HIGH event with symbol="*" must apply to TSLA, SPY, QQQ alike.
_wipe_macro_tables()
_insert_event("*", "FOMC", (_now_et + _td(minutes=8)).isoformat(), "HIGH")
_ctx_star = _snapshot_macro()
for _sym in ("SPY", "TSLA", "QQQ"):
    _r_sym = _scorer.score(_sym, _setup_bull, _base_snap, macro_ctx=_ctx_star)
    check(
        f"market-wide '*' HIGH event vetoes {_sym}",
        _r_sym.macro_cap_applied,
        f"{_sym}: veto={_r_sym.macro_cap_applied}",
    )


# --- 10.7 — fresh risk_off regime nudges bullish setup ---
_wipe_macro_tables()
_insert_regime("risk_off", _dt.now(_tz.utc))
_ctx_roff = _snapshot_macro()
_r_roff_bull = _scorer.score("SPY", _setup_bull, _base_snap, macro_ctx=_ctx_roff)
check(
    "risk_off + bullish: macro_nudge_applied True",
    _r_roff_bull.macro_nudge_applied,
    f"nudge={_r_roff_bull.macro_nudge_applied}",
)
_r_roff_bear = _scorer.score("SPY", _setup_bear, _base_snap, macro_ctx=_ctx_roff)
check(
    "risk_off + bearish: macro_nudge_applied False (not contradicting)",
    not _r_roff_bear.macro_nudge_applied,
    f"nudge={_r_roff_bear.macro_nudge_applied}",
)


# --- 10.8 — stale regime is ignored (> MACRO_REGIME_STALE_MINUTES) ---
_wipe_macro_tables()
_insert_regime("risk_off", _dt.now(_tz.utc) - _td(hours=3))  # 180min > 120min threshold
_ctx_stale = _snapshot_macro()
_r_stale = _scorer.score("SPY", _setup_bull, _base_snap, macro_ctx=_ctx_stale)
check(
    "stale regime (3h): no nudge (fail-safe)",
    not _r_stale.macro_nudge_applied,
    f"nudge={_r_stale.macro_nudge_applied}",
)
check(
    "stale regime: reader returns None for regime",
    _ctx_stale.regime is None,
    f"regime={_ctx_stale.regime}",
)


# --- 10.14 — catalyst-only nudge: bearish catalyst on bullish setup ---
# No regime row. One severity=0.9 bearish catalyst on SPY. Bullish momentum
# setup. Expected catalyst_delta = -(0.05 * 0.9) = -0.045. regime_delta = 0.
_wipe_macro_tables()
_conn_c = _sqlite3.connect(str(_DB_PATH))
from datetime import timezone as _tz_alias
_now_utc_cat = _dt.now(_tz_alias.utc)
_conn_c.execute(
    """INSERT INTO macro_catalysts
       (symbol, catalyst_type, direction, severity, expires_at, summary,
        source_url, fetched_at, content_hash)
       VALUES (?,?,?,?,?,?,?,?,?)""",
    ("SPY", "NEWS_SHOCK", "bearish", 0.9,
     (_now_utc_cat + _td(hours=2)).isoformat(),
     "Fed flags restrictive path", "https://example.com/a",
     _now_utc_cat.isoformat(), "hash_cat_10_14_000"),
)
_conn_c.commit()
_conn_c.close()

_ctx_cat = _snapshot_macro()
check(
    "10.14 setup: snapshot sees 1 catalyst for SPY",
    len(_ctx_cat.catalysts_by_symbol.get("SPY", [])) == 1,
    f"SPY catalysts: {_ctx_cat.catalysts_by_symbol.get('SPY', [])}",
)
_r_cat = _scorer.score("SPY", _setup_bull, _base_snap, macro_ctx=_ctx_cat)
check(
    "10.14: catalyst-only nudge fires (macro_nudge_applied=True, no regime row)",
    _r_cat.macro_nudge_applied and _r_cat.macro_nudge_regime == 0.0,
    f"applied={_r_cat.macro_nudge_applied} regime={_r_cat.macro_nudge_regime}",
)
check(
    "10.14: catalyst component ~ -0.045 (severity=0.9 × 0.05)",
    abs(_r_cat.macro_nudge_catalyst - (-0.045)) < 0.001,
    f"catalyst={_r_cat.macro_nudge_catalyst} (expected ~-0.045)",
)


# --- 10.15 — catalyst cap: three severity=1.0 bearish catalysts ---
# Three contradicting catalysts, each severity=1.0, would sum to -0.15
# without the cap. MACRO_CATALYST_NUDGE_CAP=0.10 means catalyst_delta
# must clamp to exactly -0.10.
_wipe_macro_tables()
_conn_c = _sqlite3.connect(str(_DB_PATH))
for i, h in enumerate(("hash_10_15_a", "hash_10_15_b", "hash_10_15_c")):
    _conn_c.execute(
        """INSERT INTO macro_catalysts
           (symbol, catalyst_type, direction, severity, expires_at, summary,
            source_url, fetched_at, content_hash)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        ("SPY", f"NEWS_{i}", "bearish", 1.0,
         (_now_utc_cat + _td(hours=2)).isoformat(),
         f"bearish story {i}", f"https://example.com/s{i}",
         _now_utc_cat.isoformat(), h),
    )
_conn_c.commit()
_conn_c.close()

_ctx_cap = _snapshot_macro()
_r_cap = _scorer.score("SPY", _setup_bull, _base_snap, macro_ctx=_ctx_cap)
check(
    "10.15: catalyst cap honored — exactly -0.10 (not -0.15)",
    _r_cap.macro_nudge_catalyst == -0.10,
    f"catalyst={_r_cap.macro_nudge_catalyst}",
)
check(
    "10.15: regime delta still 0 (no regime row inserted)",
    _r_cap.macro_nudge_regime == 0.0,
    f"regime={_r_cap.macro_nudge_regime}",
)


# --- 10.16 — stacking: regime + catalyst combined ---
# risk_off regime + 1.0-severity bearish catalyst, bullish setup.
# Expected: regime_delta = -0.10, catalyst_delta = -0.05, total = -0.15.
_wipe_macro_tables()
_insert_regime("risk_off", _dt.now(_tz.utc))
_conn_c = _sqlite3.connect(str(_DB_PATH))
_conn_c.execute(
    """INSERT INTO macro_catalysts
       (symbol, catalyst_type, direction, severity, expires_at, summary,
        source_url, fetched_at, content_hash)
       VALUES (?,?,?,?,?,?,?,?,?)""",
    ("SPY", "GEOPOL", "bearish", 1.0,
     (_now_utc_cat + _td(hours=2)).isoformat(),
     "risk-off shock", "https://example.com/r",
     _now_utc_cat.isoformat(), "hash_10_16_stack"),
)
_conn_c.commit()
_conn_c.close()

_ctx_stack = _snapshot_macro()
_r_stack = _scorer.score("SPY", _setup_bull, _base_snap, macro_ctx=_ctx_stack)
check(
    "10.16: regime delta = -0.10 (risk_off + bullish)",
    _r_stack.macro_nudge_regime == -0.10,
    f"regime={_r_stack.macro_nudge_regime}",
)
check(
    "10.16: catalyst delta = -0.05 (severity=1.0 × 0.05)",
    _r_stack.macro_nudge_catalyst == -0.05,
    f"catalyst={_r_stack.macro_nudge_catalyst}",
)
check(
    "10.16: total delta = -0.15 (stacks freely)",
    _r_stack.macro_nudge_total == -0.15,
    f"total={_r_stack.macro_nudge_total}",
)

# Cleanup before the remaining (tz + atomic) tests
_wipe_macro_tables()


# --- 10.9 — timezone drift: ET event, UTC clock, buffer honored ---
# Event at 2026-04-20 14:00 ET (18:00 UTC with DST). Mock _now() to
# 2026-04-20 17:50 UTC = 13:50 ET = 10 min before event. The reader
# must compute minutes_until correctly.
_wipe_macro_tables()
_insert_event("SPY", "FOMC", "2026-04-20T14:00:00-04:00", "HIGH")
_fake_now_utc = _dt(2026, 4, 20, 17, 50, 0, tzinfo=_tz.utc)
with _patch.object(_macro_reader, "_now", return_value=_fake_now_utc):
    _events_tz = _macro_reader.get_active_events("SPY", lookahead_minutes=15)
check(
    "tz drift: get_active_events finds the 10-min-out event",
    len(_events_tz) == 1,
    f"count={len(_events_tz)}",
)
if _events_tz:
    _delta = _events_tz[0].minutes_until
    check(
        "tz drift: minutes_until in [9, 11] (not 249 from missed offset)",
        9 <= _delta <= 11,
        f"minutes_until={_delta}",
    )


# --- 10.18 — _next_wake_time never returns a past time ---
# Bug: naive "top-of-hour + MACRO_POLL_MINUTES" can land in the past when
# the cadence is sub-hourly and now_et is already past that minute within
# the current hour. Worker would fire instantly every cycle, thrashing.
# Fix: loop until strictly in the future.
from macro import worker as _worker_mod
from zoneinfo import ZoneInfo as _ZI
_ET_zone = _ZI("America/New_York")

# Case 1 — MACRO_POLL_MINUTES=30, now at HH:45 (naive wake = HH:30, past).
with _patch.object(_worker_mod, "MACRO_POLL_MINUTES", 30):
    _now = _dt(2026, 4, 20, 10, 45, 0, tzinfo=_ET_zone)
    _wake = _worker_mod._next_wake_time(_now)
    check(
        "10.18a: sub-hourly cadence at :45 returns strictly future time",
        _wake > _now,
        f"now={_now.isoformat()} wake={_wake.isoformat()}",
    )
    # With cadence 30, the next anchor points are :00, :30, :60, :90...
    # From 10:45, next strictly-future at-or-past-anchor is 11:00.
    check(
        "10.18a: next wake is 11:00 ET (next anchor after 10:45)",
        _wake.hour == 11 and _wake.minute == 0,
        f"wake={_wake.isoformat()}",
    )

# Case 2 — MACRO_POLL_MINUTES=60 (default), now at HH:30, wake should be
# HH+1:00 (not HH:00 which is past).
with _patch.object(_worker_mod, "MACRO_POLL_MINUTES", 60):
    _now = _dt(2026, 4, 20, 10, 30, 0, tzinfo=_ET_zone)
    _wake = _worker_mod._next_wake_time(_now)
    check(
        "10.18b: hourly cadence at :30 returns 11:00 (strictly future)",
        _wake > _now and _wake.hour == 11 and _wake.minute == 0,
        f"now={_now.isoformat()} wake={_wake.isoformat()}",
    )

# Case 3 — MACRO_POLL_MINUTES=15, now at HH:50 (naive wake = HH:15, past).
with _patch.object(_worker_mod, "MACRO_POLL_MINUTES", 15):
    _now = _dt(2026, 4, 20, 10, 50, 0, tzinfo=_ET_zone)
    _wake = _worker_mod._next_wake_time(_now)
    check(
        "10.18c: tight cadence (15min) at :50 returns strictly future time",
        _wake > _now,
        f"now={_now.isoformat()} wake={_wake.isoformat()}",
    )
    check(
        "10.18c: wake is 11:00 ET (next anchor after 10:50)",
        _wake.hour == 11 and _wake.minute == 0,
        f"wake={_wake.isoformat()}",
    )


# --- 10.10 — atomic daily-cap increment ---
# INSERT ... ON CONFLICT DO UPDATE ... RETURNING call_count must be
# atomic and produce exact sequential counts (no skip, no repeat).
# The return value comes from RETURNING, not from a separate SELECT —
# verifies the race-free upsert path.
_wipe_macro_tables()
from macro.perplexity_client import _atomic_increment_usage, _current_usage, _today_et
check(
    "atomic cap start: current usage is 0",
    _current_usage() == 0,
    f"got {_current_usage()}",
)
_counts = [_atomic_increment_usage() for _ in range(5)]
check(
    "atomic cap: 5 increments produce counts 1..5",
    _counts == [1, 2, 3, 4, 5],
    f"counts={_counts}",
)
check(
    "atomic cap: final reading matches 5",
    _current_usage() == 5,
    f"got {_current_usage()}",
)
_conn_check = _sqlite3.connect(str(_DB_PATH))
_rows = _conn_check.execute(
    "SELECT COUNT(*) FROM macro_api_usage WHERE date_et = ?", (_today_et(),)
).fetchone()
_conn_check.close()
check(
    "atomic cap: single row per date_et (no duplicate inserts)",
    _rows[0] == 1,
    f"rows={_rows[0]}",
)


# --- 10.11 — no LLM or network call in the hot path ---
# Scan the hot-path modules for imports that would smell like a network
# call. scorer.py, base_profile.py, v2_strategy.py must not reference
# perplexity_client or httpx. This catches a future refactor that
# accidentally imports the worker.
_hot_files = [
    Path(__file__).parent.parent / "scoring" / "scorer.py",
    Path(__file__).parent.parent / "profiles" / "base_profile.py",
    Path(__file__).parent.parent / "strategies" / "v2_strategy.py",
]
_bad_tokens = ("perplexity_client", "httpx", "requests.get", "requests.post")
for _f in _hot_files:
    _src = _f.read_text()
    for _tok in _bad_tokens:
        check(
            f"{_f.name} does NOT import {_tok} (hot-path invariant)",
            _tok not in _src,
            f"token '{_tok}' found in {_f.name}",
        )


# --- 10.17 — DST transition: event_time_utc filters stay correct ---
# Before the fix, queries compared ISO8601 strings lex-style. Rows stored
# with one DST offset and query bounds generated with a different offset
# (because DST flipped between store and query) produced wrong results.
# Fix: all SELECT filters use event_time_utc (always +00:00), while
# event_time_et is kept for display/LLM.

# --- 10.17a — fall-back transition (November) ---
# Event stored at 02:30 EDT (-04:00) = 06:30 UTC, BEFORE DST ends at 02:00
# local on 2026-11-01. Then we freeze "now" to 06:45 UTC, which is 01:45
# EST (post-fallback, -05:00). The event is 15 minutes in the past.
_wipe_macro_tables()
_insert_event("SPY", "FOMC", "2026-11-01T02:30:00-04:00", "HIGH")
_fake_post_fallback = _dt(2026, 11, 1, 6, 45, 0, tzinfo=_tz.utc)
with _patch.object(_macro_reader, "_now", return_value=_fake_post_fallback):
    _upcoming = _macro_reader.next_upcoming_event("*")
    _active = _macro_reader.get_active_events("SPY", lookahead_minutes=15)
check(
    "10.17a DST fall-back: past event NOT returned by next_upcoming_event",
    _upcoming is None,
    f"got upcoming={_upcoming}",
)
# Bug symptom: without event_time_utc filtering, lex compare of
# '2026-11-01T02:30:00-04:00' vs the now-in-ET bound '2026-11-01T01:45:00-05:00'
# says the stored event is lex-LATER (02:30 > 01:45) even though its UTC
# instant (06:30) is BEFORE now (06:45). Pre-fix that would have returned
# the event incorrectly as "upcoming". get_active_events similarly filters
# it out — the event's minutes_until is -15 which fails the
# `minutes_until > lookahead_minutes` check only accidentally; with the
# fix it's cleanly past and not in a forward-looking window.
check(
    "10.17a DST fall-back: get_active_events does not surface past event",
    not any(e.event_type == "FOMC" for e in _active),
    f"got active: {_active}",
)

# --- 10.17b — spring-forward transition (March) ---
# Event stored at 03:30 EDT (-04:00) = 07:30 UTC on 2026-03-08, AFTER DST
# begins at 02:00 EST. Now frozen to 07:15 UTC = 02:15 EST (pre-spring-forward,
# -05:00). The event is 15 minutes IN THE FUTURE.
_wipe_macro_tables()
_insert_event("SPY", "FOMC", "2026-03-08T03:30:00-04:00", "HIGH")
_fake_pre_spring = _dt(2026, 3, 8, 7, 15, 0, tzinfo=_tz.utc)
with _patch.object(_macro_reader, "_now", return_value=_fake_pre_spring):
    _upcoming = _macro_reader.next_upcoming_event("*")
    _active = _macro_reader.get_active_events("SPY", lookahead_minutes=15)
check(
    "10.17b DST spring-forward: upcoming event IS returned",
    _upcoming is not None and _upcoming.event_type == "FOMC",
    f"got upcoming={_upcoming}",
)
check(
    "10.17b DST spring-forward: minutes_until within [14, 16]",
    _upcoming is not None and 14 <= _upcoming.minutes_until <= 16,
    f"minutes_until={_upcoming.minutes_until if _upcoming else None}",
)
check(
    "10.17b DST spring-forward: get_active_events surfaces it inside buffer",
    any(e.event_type == "FOMC" and 14 <= e.minutes_until <= 16 for e in _active),
    f"active events: {[(e.event_type, e.minutes_until) for e in _active]}",
)

_wipe_macro_tables()


# --- 10.13 — catalyst dedup via content_hash upsert ---
# Plain INSERT would produce a duplicate row every hourly poll for a slow-
# moving story. Verify ON CONFLICT(content_hash) DO UPDATE collapses
# duplicates and refreshes expires_at/fetched_at.
import asyncio as _asyncio
import time as _time

# Ensure the schema migration has been applied to the live DB before this
# test runs. init_db is idempotent — ALTER is wrapped in try/except.
from backend.database import init_db as _init_db
_asyncio.run(_init_db())

_wipe_macro_tables()

from macro.schema import CatalystItem as _CatalystItem
from macro.schema import MacroPayload as _MacroPayload
from macro.schema import RegimeSummary as _RegimeSummary
from macro.worker import fetch_and_write as _fetch_and_write


def _make_payload(summary: str) -> _MacroPayload:
    return _MacroPayload(
        events=[],
        catalysts=[
            _CatalystItem(
                symbol="SPY", catalyst_type="NEWS_SHOCK", direction="bearish",
                severity=0.5, summary=summary,
                source_url="https://example.com/x",
            ),
        ],
        regime=_RegimeSummary(risk_tone="unknown", vix_context="", major_themes=[]),
    )


# First insert
_asyncio.run(_fetch_and_write(_make_payload("Fed signals dovish tilt")))
_conn13 = _sqlite3.connect(str(_DB_PATH))
_first = _conn13.execute(
    "SELECT fetched_at, expires_at, severity FROM macro_catalysts"
).fetchone()
_conn13.close()

# Sleep 100ms so the second fetched_at is provably later
_time.sleep(0.1)

# Second insert — same summary, must upsert
_asyncio.run(_fetch_and_write(_make_payload("Fed signals dovish tilt")))
_conn13 = _sqlite3.connect(str(_DB_PATH))
_rows = _conn13.execute("SELECT COUNT(*) FROM macro_catalysts").fetchone()[0]
_second = _conn13.execute(
    "SELECT fetched_at, expires_at, severity FROM macro_catalysts"
).fetchone()
_conn13.close()

check(
    "dedup: same catalyst inserted twice produces exactly 1 row",
    _rows == 1,
    f"rows={_rows}",
)
check(
    "dedup: fetched_at refreshed to the later value",
    _second[0] > _first[0],
    f"first={_first[0]} second={_second[0]}",
)
check(
    "dedup: expires_at refreshed to the later value",
    _second[1] > _first[1],
    f"first_exp={_first[1]} second_exp={_second[1]}",
)

# Third insert — DIFFERENT summary must produce a second row
_asyncio.run(_fetch_and_write(_make_payload("Fed signals hawkish tilt")))
_conn13 = _sqlite3.connect(str(_DB_PATH))
_rows_after = _conn13.execute("SELECT COUNT(*) FROM macro_catalysts").fetchone()[0]
_distinct_hashes = _conn13.execute(
    "SELECT COUNT(DISTINCT content_hash) FROM macro_catalysts"
).fetchone()[0]
_conn13.close()
check(
    "dedup: different summaries produce 2 rows",
    _rows_after == 2,
    f"rows={_rows_after}",
)
check(
    "dedup: 2 rows have 2 distinct content_hash values",
    _distinct_hashes == 2,
    f"distinct_hashes={_distinct_hashes}",
)

_wipe_macro_tables()


# --- 10.12 — macro_ctx=None fallback works (single-call compatibility) ---
# Tests in a loop must pass macro_ctx explicitly (see plan E-b), but
# isolated callers without a ctx should still work.
_wipe_macro_tables()
_r_fallback = _scorer.score("SPY", _setup_bull, _base_snap)  # no macro_ctx kwarg
check(
    "macro_ctx=None fallback: scorer still produces a result",
    _r_fallback is not None and not _r_fallback.macro_cap_applied,
    f"result={_r_fallback}",
)


# Cleanup
_wipe_macro_tables()


# ============================================================
# SECTION 11: cross-module invariants
# Small asserts that lock down cross-file agreements which previously
# drifted silently.
# ============================================================
section("11. Cross-module invariants")

# --- 11.1 — exposure limits in config and sizer agree ---
# Previously config.MAX_TOTAL_EXPOSURE_PCT=60 and sizer.MAX_EXPOSURE_PCT=20
# contradicted each other. The sizer's 20% hard block always fired first,
# so the 60% setting was dead code. The sizer now asserts equality at
# import time; this test is belt-and-suspenders so future drift surfaces
# in a test run, not at Python-import crash time.
from config import MAX_TOTAL_EXPOSURE_PCT as _CFG_EXP
from sizing.sizer import MAX_EXPOSURE_PCT as _SIZER_EXP
check(
    "11.1: exposure limits agree across config and sizer",
    _SIZER_EXP == _CFG_EXP,
    f"sizer={_SIZER_EXP} config={_CFG_EXP}",
)


# --- 11.2 — was_day_trade PDT-count query semantics ---
# Bug B fix: v2_strategy BUY fill no longer writes `is_same_day` into
# was_day_trade. The column stays at DEFAULT 0 until the SELL fill UPDATE
# writes the correct "round-trip same calendar day" value. This test
# seeds three synthetic rows and runs the live PDT query to confirm the
# only row counted is the actual same-day round-trip.
import uuid as _uuid
_pdt_test_ids = []
_conn_11_2 = _sqlite3.connect(str(_DB_PATH))
try:
    _today_iso = _dt.now(_tz.utc).isoformat()
    _two_days_ago_iso = (_dt.now(_tz.utc) - _td(days=2)).isoformat()

    # Row A: OPEN, was_day_trade NULL (simulates the post-fix INSERT which
    # omits the column). PDT query filters on status='closed' so this is
    # invisible.
    _id_a = f"test_11_2_open_{_uuid.uuid4().hex[:8]}"
    _pdt_test_ids.append(_id_a)
    _conn_11_2.execute(
        """INSERT INTO trades
           (id, profile_id, symbol, direction, strike, expiration,
            quantity, entry_price, entry_date, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_id_a, "test-profile", "SPY", "CALL", 500.0, "2026-05-01",
         1, 2.50, _today_iso, "open", _today_iso, _today_iso),
    )
    # Row B: CLOSED, same-day round-trip, was_day_trade=1 (the way
    # trade_manager.confirm_fill writes it). MUST count.
    _id_b = f"test_11_2_b_{_uuid.uuid4().hex[:8]}"
    _pdt_test_ids.append(_id_b)
    _conn_11_2.execute(
        """INSERT INTO trades
           (id, profile_id, symbol, direction, strike, expiration, quantity,
            entry_price, entry_date, exit_price, exit_date, pnl_dollars,
            pnl_pct, was_day_trade, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_id_b, "test-profile", "SPY", "CALL", 500.0, _dt.now(_tz.utc).date().isoformat(),
         1, 2.50, _today_iso, 3.50, _today_iso, 100.0, 40.0,
         1, "closed", _today_iso, _today_iso),
    )
    # Row C: CLOSED 0DTE from the *entry* side (expiration today) but
    # entry was 2 days ago — not a same-day round-trip. was_day_trade=0.
    # MUST NOT count.
    _id_c = f"test_11_2_c_{_uuid.uuid4().hex[:8]}"
    _pdt_test_ids.append(_id_c)
    _conn_11_2.execute(
        """INSERT INTO trades
           (id, profile_id, symbol, direction, strike, expiration, quantity,
            entry_price, entry_date, exit_price, exit_date, pnl_dollars,
            pnl_pct, was_day_trade, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_id_c, "test-profile", "SPY", "CALL", 500.0, _dt.now(_tz.utc).date().isoformat(),
         1, 2.50, _two_days_ago_iso, 3.50, _today_iso, 100.0, 40.0,
         0, "closed", _two_days_ago_iso, _today_iso),
    )
    _conn_11_2.commit()

    _pdt_count = _conn_11_2.execute(
        """SELECT COUNT(*) FROM trades
           WHERE was_day_trade = 1
             AND exit_date >= date('now','-7 days')
             AND status = 'closed'
             AND id LIKE 'test_11_2_%'"""
    ).fetchone()[0]

    check(
        "11.2: PDT query counts only the same-day round-trip (1 of 3 rows)",
        _pdt_count == 1,
        f"got pdt_count={_pdt_count} (expected 1: row B only)",
    )

    # Also verify row A (open, was_day_trade=NULL) is projected as False by
    # the trades row projector (bool(NULL) is False in Python).
    _row_a = _conn_11_2.execute(
        "SELECT was_day_trade FROM trades WHERE id = ?", (_id_a,)
    ).fetchone()
    check(
        "11.2: open trade row has was_day_trade NULL or 0 (not 1)",
        _row_a[0] is None or _row_a[0] == 0,
        f"got was_day_trade={_row_a[0]!r}",
    )
finally:
    # Clean up synthetic rows
    for _tid in _pdt_test_ids:
        _conn_11_2.execute("DELETE FROM trades WHERE id = ?", (_tid,))
    _conn_11_2.commit()
    _conn_11_2.close()


# --- 11.3 — sentiment math: suppression-only per docs/ABOUT.md ---
# The scorer sentiment factor is documented as suppression-only:
# contradicting sentiment hurts the score, confirming/neutral = 0.5
# (neutral, no boost). This test pins the implementation so a future
# "optimization" cannot silently start rewarding confirming sentiment
# without breaking a visible assertion.
from market.context import Regime as _R, TimeOfDay as _TOD, MarketSnapshot as _MS
from scanner.setups import SetupScore as _SS
from scoring.scorer import Scorer as _Scorer_11_3


def _sentiment_raw(direction: str, sentiment_score: float) -> float:
    """Invoke the full scorer and extract the sentiment factor's raw_value."""
    _scorer = _Scorer_11_3()
    _setup = _SS("momentum", 0.85, "test", direction)
    _snap = _MS(
        regime=_R.TRENDING_UP, time_of_day=_TOD.MID_MORNING,
        timestamp="2026-04-21T10:30:00",
        spy_30min_move_pct=0.3, spy_60min_range_pct=0.4,
        spy_30min_reversals=1, spy_volume_ratio=1.5,
        vix_level=16.0, vix_intraday_change_pct=0.0, regime_reason="test",
    )
    # Empty MacroContext so the macro nudge path is a no-op
    _result = _scorer.score("SPY", _setup, _snap, sentiment_score=sentiment_score,
                            macro_ctx=None)
    for _f in _result.factors:
        if _f.name == "sentiment":
            return _f.raw_value
    raise AssertionError("sentiment factor missing from ScoringResult.factors")


# Bullish setup:
#   +0.8  confirming   → 0.5  (no boost)
#   -0.8  contradicting → 0.5 + (-0.8 * 0.5) = 0.1
#    0.0  neutral       → 0.5
# Bearish setup:
#   +0.8  contradicting → 0.5 - (0.8 * 0.5) = 0.1
#   -0.8  confirming   → 0.5  (no boost)
#    0.0  neutral       → 0.5
_SENTIMENT_CASES = [
    ("bullish", +0.8, 0.5, "bullish+confirming -> neutral 0.5 (no reward)"),
    ("bullish", -0.8, 0.1, "bullish+contradicting -> suppressed to 0.1"),
    ("bullish",  0.0, 0.5, "bullish+neutral -> 0.5"),
    ("bearish", +0.8, 0.1, "bearish+contradicting -> suppressed to 0.1"),
    ("bearish", -0.8, 0.5, "bearish+confirming -> neutral 0.5 (no reward)"),
    ("bearish",  0.0, 0.5, "bearish+neutral -> 0.5"),
]

for _dir, _score, _expected, _label in _SENTIMENT_CASES:
    _got = _sentiment_raw(_dir, _score)
    check(
        f"11.3: {_label}",
        abs(_got - _expected) < 1e-6,
        f"direction={_dir} score={_score:+.1f} got={_got} expected={_expected}",
    )


# ============================================================
# SECTION 12: pre-existing design issue fixes
# Issues found in a targeted audit, each non-critical in isolation but
# costs quality over time. See commit messages for trace tables.
# ============================================================
section("12. Pre-existing design issue fixes")

# --- 12.1 — growth mode honors the 8% day-drawdown halving ---
# Before the fix, growth mode computed final_risk from GROWTH_MODE_RISK_PCT
# scaled by confidence, never applying the drawdown halving. Small accounts
# ($5K-$25K) are the accounts most vulnerable to doubling down into losses,
# yet the halving was skipped. Fix: halve scaled_risk when day_dd_pct >= 8.
from sizing.sizer import calculate as _size_calc

# Scenario A: $5K account down 9.09% on day (day_start=$5500), conf=0.72,
#   premium=$0.35. Uses 9.09% (not 7.99%) to be unambiguously above the
#   8% halving threshold.
#   growth_risk = 5000 * 0.15 = $750
#   conf_scale = (0.72-0.50)/0.30 = 0.7333
#   scaled_risk = 750 * (0.70 + 0.30*0.7333) = $690
#   day_dd_pct = (5500-5000)/5500 * 100 = 9.09% >= 8% -> halve
#   scaled_risk = $345
#   final_risk = min(345, 5000*0.25=1250, remaining=5000*0.20=1000) = $345
#   contracts = floor(345 / 35) = 9  (was 19 before the fix)
_r_halved = _size_calc(
    account_value=5000, confidence=0.72, premium=0.35,
    day_start_value=5500, starting_balance=5000,
    current_exposure=0, is_same_day_trade=False,
    day_trades_remaining=3, growth_mode_config=True,
)
check(
    "12.1 scenario A: 8% drawdown halves contracts (8 <= n <= 10)",
    8 <= _r_halved.contracts <= 10,
    f"got contracts={_r_halved.contracts} (expected ~9)",
)
check(
    "12.1 scenario A: halvings_applied includes growth_mode_day_drawdown_*",
    any(h.startswith("growth_mode_day_drawdown_") for h in _r_halved.halvings_applied),
    f"halvings={_r_halved.halvings_applied}",
)

# Scenario B: same account NOT down on day — halving must NOT fire
_r_normal = _size_calc(
    account_value=5000, confidence=0.72, premium=0.35,
    day_start_value=5000, starting_balance=5000,
    current_exposure=0, is_same_day_trade=False,
    day_trades_remaining=3, growth_mode_config=True,
)
check(
    "12.1 scenario B: no drawdown -> no halving (18 <= n <= 20)",
    18 <= _r_normal.contracts <= 20,
    f"got contracts={_r_normal.contracts} (expected ~19)",
)
check(
    "12.1 scenario B: halvings_applied does NOT include day_drawdown entry",
    not any(h.startswith("growth_mode_day_drawdown_") for h in _r_normal.halvings_applied),
    f"halvings={_r_normal.halvings_applied}",
)

# Scenario C: audit-trail honesty — after_drawdown != after_pdt only matters
# in normal mode (growth mode has no PDT halving). Verify the returned
# checkpoint fields are distinct from final_risk when halving fired.
check(
    "12.1 scenario C: confidence_risk preserves pre-halving scaled_risk",
    _r_halved.confidence_risk > _r_halved.after_drawdown_halving,
    f"confidence_risk={_r_halved.confidence_risk} "
    f"after_drawdown={_r_halved.after_drawdown_halving} (expected > after halving)",
)
check(
    "12.1 scenario C: after_drawdown ~= 0.5 * confidence_risk (halving math)",
    abs(_r_halved.after_drawdown_halving - 0.5 * _r_halved.confidence_risk) < 1.0,
    f"pre={_r_halved.confidence_risk} post={_r_halved.after_drawdown_halving}",
)

# Scenario D: growth mode always has PDT-as-block semantics
#   after_pdt_halving == after_drawdown_halving (PDT is not a halving here)
check(
    "12.1 scenario D: growth mode PDT is a block, not a halving",
    _r_halved.after_pdt_halving == _r_halved.after_drawdown_halving,
    f"after_drawdown={_r_halved.after_drawdown_halving} "
    f"after_pdt={_r_halved.after_pdt_halving}",
)


# --- 12.2 — Scorer trade history loaded from DB at startup ---
# Before the fix, Scorer.__init__ started with an empty _trade_history.
# record_trade_outcome appended on SELL fills only, so every watchdog
# restart or subprocess respawn reset the history and pinned the
# historical_perf factor at 0.5 (neutral). Fix adds
# load_trade_history_from_db called from v2_strategy.initialize after
# the learning-state block.
import uuid as _uuid_12_2
_hist_test_ids = []
_conn_12_2 = _sqlite3.connect(str(_DB_PATH))
try:
    _today_iso = _dt.now(_tz.utc).isoformat()
    # Seed 10 closed SPY momentum trades: 6 wins @ +50%, 4 losses @ -30%
    # Expected win rate = 6/10 = 0.60
    _outcomes = [50.0] * 6 + [-30.0] * 4
    for _pnl in _outcomes:
        _tid = f"test_12_2_{_uuid_12_2.uuid4().hex[:8]}"
        _hist_test_ids.append(_tid)
        _conn_12_2.execute(
            """INSERT INTO trades
               (id, profile_id, symbol, direction, strike, expiration, quantity,
                entry_price, entry_date, exit_price, exit_date, pnl_dollars,
                pnl_pct, setup_type, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_tid, "test-12-2", "SPY", "CALL", 500.0, "2026-05-01",
             1, 2.50, _today_iso, 3.00 if _pnl > 0 else 2.00, _today_iso,
             _pnl, _pnl, "momentum", "closed", _today_iso, _today_iso),
        )
    _conn_12_2.commit()
    _conn_12_2.close()

    # Fresh scorer — empty history, historical_perf should return 0.5 neutral
    from scoring.scorer import Scorer as _Scorer_12_2
    _s12 = _Scorer_12_2()
    check(
        "12.2: fresh Scorer returns 0.5 (neutral) for SPY momentum",
        _s12._compute_historical_perf("SPY", "momentum") == 0.5,
        f"got {_s12._compute_historical_perf('SPY', 'momentum')}",
    )

    # Load from DB; restrict to SPY (the production call pattern).
    # Note: prod will also include other profiles' seeded data; filter on
    # symbol + setup_type below still correctly projects just our rows.
    _loaded = _s12.load_trade_history_from_db(symbols=["SPY"], limit=200)
    check(
        "12.2: load_trade_history_from_db returns positive row count",
        _loaded >= 10,
        f"loaded={_loaded} (expected >=10 including our 10 test rows)",
    )

    # Build win rate from our 10 test rows (filtering to the exact setup_type):
    # There may be pre-existing production trades for SPY momentum too.
    # Verify win rate is at least present (not still 0.5 due to insufficient
    # history), and verify our test rows are in memory.
    _our_test_pnls = [t["pnl"] for t in _s12._trade_history
                       if t.get("symbol") == "SPY"
                       and t.get("setup_type") == "momentum"
                       and any(t["pnl"] == o for o in _outcomes)]
    check(
        "12.2: all 10 test pnls are present in the loaded history",
        len(_our_test_pnls) >= 10,
        f"found {len(_our_test_pnls)} of our 10 seeded pnls",
    )

    # Trim self._trade_history to JUST our test rows so we can deterministically
    # check the win rate math. This isolates from production noise.
    _s12._trade_history = [
        t for t in _s12._trade_history
        if t.get("symbol") == "SPY"
        and t.get("setup_type") == "momentum"
        and t["pnl"] in _outcomes
    ][:10]
    _wr = _s12._compute_historical_perf("SPY", "momentum")
    check(
        "12.2: win rate on 10 seeded trades is 0.6 (6 wins / 10 total)",
        abs(_wr - 0.6) < 0.0001,
        f"got win_rate={_wr}",
    )

    # Unrelated setup_type still 0.5 (no mean_reversion seeded)
    check(
        "12.2: unrelated setup_type (mean_reversion) returns 0.5 neutral",
        _s12._compute_historical_perf("SPY", "mean_reversion") == 0.5,
        f"got {_s12._compute_historical_perf('SPY', 'mean_reversion')}",
    )
finally:
    # Cleanup — always
    _conn_cleanup = _sqlite3.connect(str(_DB_PATH))
    for _tid in _hist_test_ids:
        _conn_cleanup.execute("DELETE FROM trades WHERE id = ?", (_tid,))
    _conn_cleanup.commit()
    _conn_cleanup.close()


# --- 12.3 — Learning trigger fires from every close path ---
# Before the fix, run_learning fired only from trade_manager.confirm_fill,
# so expired_worthless / order_never_filled / alpaca_reconcile exits were
# invisible to the learner. After the fix, _maybe_trigger_learning is a
# helper called from confirm_fill, _cleanup_stale_trades, and
# reconcile_positions.py.
import uuid as _uuid_12_3
from unittest.mock import patch as _patch_12_3, MagicMock as _MagicMock_12_3
from management.trade_manager import TradeManager as _TM_12_3, ManagedPosition as _MP_12_3
from datetime import date as _date_12_3
from profiles.momentum import MomentumProfile as _MomProf_12_3


def _seed_closed_trades(count: int, setup_type: str, prefix: str) -> list[str]:
    """Seed `count` closed trades for the given setup_type. Returns the
    synthetic trade_ids so caller can clean them up. Alternates win/loss
    with varied exit_reasons per the spec."""
    ids = []
    _conn = _sqlite3.connect(str(_DB_PATH))
    _today_iso = _dt.now(_tz.utc).isoformat()
    _exit_reasons = ["trailing_stop", "expired_worthless", "order_never_filled",
                     "profit_target", "thesis_broken"]
    for i in range(count):
        _tid = f"{prefix}_{_uuid_12_3.uuid4().hex[:8]}"
        ids.append(_tid)
        _pnl = 45.0 if i % 2 == 0 else -25.0
        _er = _exit_reasons[i % len(_exit_reasons)]
        _conn.execute(
            """INSERT INTO trades
               (id, profile_id, symbol, direction, strike, expiration, quantity,
                entry_price, entry_date, exit_price, exit_date, pnl_dollars,
                pnl_pct, setup_type, status, exit_reason, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_tid, "test-12-3", "SPY", "CALL", 500.0, "2026-05-01",
             1, 2.50, _today_iso, 3.00 if _pnl > 0 else 2.00, _today_iso,
             _pnl, _pnl, setup_type, "closed", _er, _today_iso, _today_iso),
        )
    _conn.commit()
    _conn.close()
    return ids


def _cleanup_trade_ids(ids):
    _conn = _sqlite3.connect(str(_DB_PATH))
    for _tid in ids:
        _conn.execute("DELETE FROM trades WHERE id = ?", (_tid,))
    _conn.commit()
    _conn.close()


# -- 12.3 Case 1: confirm_fill still fires learning on the 20th close --
_case1_ids = _seed_closed_trades(19, "momentum", "test_12_3_case1")
try:
    _tm = _TM_12_3()
    _prof = _MomProf_12_3()
    # Synthetic ManagedPosition for the 20th trade about to close
    _pos = _MP_12_3(
        trade_id=f"test_12_3_case1_{_uuid_12_3.uuid4().hex[:8]}",
        symbol="SPY", direction="bullish", profile=_prof,
        expiration=_date_12_3(2026, 5, 1),
        entry_time=_dt.now(_tz.utc), entry_price=2.50, quantity=1,
        setup_type="momentum", strike=500.0, right="CALL",
        pending_exit_reason="profit_target",
    )
    # Insert that 20th trade as status='open' so confirm_fill's UPDATE
    # lands on a real row (count becomes 20 after the UPDATE commits).
    _tid_20 = _pos.trade_id
    _case1_ids.append(_tid_20)
    _conn_20 = _sqlite3.connect(str(_DB_PATH))
    _conn_20.execute(
        """INSERT INTO trades (id, profile_id, symbol, direction, strike,
           expiration, quantity, entry_price, entry_date, setup_type,
           status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_tid_20, "test-12-3", "SPY", "CALL", 500.0, "2026-05-01",
         1, 2.50, _dt.now(_tz.utc).isoformat(), "momentum", "open",
         _dt.now(_tz.utc).isoformat(), _dt.now(_tz.utc).isoformat()),
    )
    _conn_20.commit()
    _conn_20.close()
    _tm._positions[_tid_20] = _pos

    # Patch run_learning to prove it gets called. Patch at the trade_manager
    # module scope where _maybe_trigger_learning imports it.
    with _patch_12_3("learning.learner.run_learning") as _mock_rl:
        _mock_rl.return_value = None
        _tm.confirm_fill(_tid_20, 3.00)
    check(
        "12.3 Case 1: confirm_fill fires run_learning on 20th close",
        _mock_rl.called,
        f"run_learning.called={_mock_rl.called} call_count={_mock_rl.call_count}",
    )
finally:
    _cleanup_trade_ids(_case1_ids)


# -- 12.3 Case 2: _cleanup_stale_trades fires learning (production code
#    path, Alpaca stubbed) --
# Per the spec: do NOT patch _cleanup_stale_trades itself. Instead, stub
# the Alpaca TradingClient inside the method so the real code runs end
# to end against a synthetic expired-open trade.
_case2_ids = _seed_closed_trades(19, "momentum", "test_12_3_case2")
try:
    # Add one synthetic OPEN SPY trade with an expired date — this is the
    # row that _cleanup_stale_trades should close and then trigger learning.
    _tid_expired = f"test_12_3_case2_expired_{_uuid_12_3.uuid4().hex[:8]}"
    _case2_ids.append(_tid_expired)
    _conn_exp = _sqlite3.connect(str(_DB_PATH))
    _yesterday = (_dt.now(_tz.utc).date() - _td(days=1)).isoformat()
    _conn_exp.execute(
        """INSERT INTO trades (id, profile_id, symbol, direction, strike,
           expiration, quantity, entry_price, entry_date, setup_type,
           status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_tid_expired, "test-12-3", "SPY", "CALL", 500.0, _yesterday,
         1, 2.50, _dt.now(_tz.utc).isoformat(), "momentum", "open",
         _dt.now(_tz.utc).isoformat(), _dt.now(_tz.utc).isoformat()),
    )
    _conn_exp.commit()
    _conn_exp.close()

    _tm = _TM_12_3()

    # Stub Alpaca: empty positions, empty order history. This forces
    # _cleanup_stale_trades down the "order_never_filled" branch.
    _fake_alpaca = _MagicMock_12_3()
    _fake_alpaca.get_all_positions.return_value = []
    _fake_alpaca.get_orders.return_value = []

    with _patch_12_3("alpaca.trading.client.TradingClient", return_value=_fake_alpaca), \
         _patch_12_3("learning.learner.run_learning") as _mock_rl2:
        _mock_rl2.return_value = None
        _tm._cleanup_stale_trades()

    # Verify the expired row was closed AND that learning was triggered.
    _conn_check = _sqlite3.connect(str(_DB_PATH))
    _status = _conn_check.execute(
        "SELECT status, exit_reason FROM trades WHERE id = ?", (_tid_expired,)
    ).fetchone()
    _conn_check.close()
    check(
        "12.3 Case 2: _cleanup_stale_trades closed the expired row",
        _status is not None and _status[0] == "closed",
        f"status={_status}",
    )
    check(
        "12.3 Case 2: _cleanup_stale_trades fired run_learning on 20th close",
        _mock_rl2.called,
        f"run_learning.called={_mock_rl2.called} call_count={_mock_rl2.call_count}",
    )
finally:
    _cleanup_trade_ids(_case2_ids)


# -- 12.3 Case 3: reconcile_positions.py has the learning-trigger wiring --
# Not invoking the full run() because it needs Alpaca auth. Just verify
# the module imports run_learning and references it — a code-level proof
# that the wiring exists, checked on every suite run.
import pathlib as _pathlib_12_3
_reconcile_src = (_pathlib_12_3.Path(__file__).parent.parent /
                   "scripts" / "reconcile_positions.py").read_text()
check(
    "12.3 Case 3: reconcile_positions.py imports run_learning",
    "from learning.learner import run_learning" in _reconcile_src,
    "expected 'from learning.learner import run_learning' in script",
)
check(
    "12.3 Case 3: reconcile_positions.py invokes run_learning(setup_type, ...)",
    "run_learning(setup_type" in _reconcile_src,
    "expected 'run_learning(setup_type' invocation",
)
check(
    "12.3 Case 3: reconcile_positions.py collects closed_setup_types",
    "closed_setup_types" in _reconcile_src,
    "expected 'closed_setup_types' set in script",
)


# ============================================================
# SECTION 13: cleanup pass — duplicate sources of truth removed
# ============================================================
section("13. Cleanup: one source of truth per rule")

# --- 13.1 — SPY-hardcoded time rules moved to profile config ---
# MeanReversionProfile used to hardcode "no SPY entry after 2pm ET" and
# TradeManager hardcoded "SPY mean_reversion force-close at 3:45pm ET".
# Both rules are now config-driven on the profile instance: any profile
# can set no_entry_after_et_hour + force_close_et_hhmm. Defaults on
# MeanReversionProfile preserve the old SPY behavior.
from profiles.mean_reversion import MeanReversionProfile as _MRP_13_1

# Constructor defaults hold the old behavior
_mrp = _MRP_13_1()
check(
    "13.1: MeanReversionProfile default no_entry_after_et_hour == 14",
    _mrp.no_entry_after_et_hour == 14,
    f"got {_mrp.no_entry_after_et_hour}",
)
check(
    "13.1: MeanReversionProfile default force_close_et_hhmm == '15:45'",
    _mrp.force_close_et_hhmm == "15:45",
    f"got {_mrp.force_close_et_hhmm!r}",
)

# At 14:01 ET, the entry-time rule must fire regardless of symbol. Use the
# _FrozenDateTime pattern from Section 3 — patch datetime at the module
# level where the check's `from datetime import datetime` resolves.
import datetime as _dt_mod_13
_real_dt_13 = _dt_mod_13.datetime


class _FrozenDT_13(_real_dt_13):
    @classmethod
    def now(cls, tz=None):
        # 14:01 ET = 18:01 UTC (in EDT April)
        base = _real_dt_13(2026, 4, 21, 18, 1, 0, tzinfo=_dt_mod_13.timezone.utc)
        if tz is not None:
            return base.astimezone(tz)
        return base


_dt_mod_13.datetime = _FrozenDT_13
try:
    from scanner.setups import SetupScore as _SS13
    from scoring.scorer import ScoringResult as _SR13
    _mrp_test = _MRP_13_1()
    _ss = _SS13("mean_reversion", 0.80, "test", "bullish")
    _sr = _SR13(
        symbol="SPY", setup_type="mean_reversion", raw_score=0.80,
        capped_score=0.80, regime_cap_applied=False, regime_cap_value=None,
        threshold_label="moderate", direction="bullish", factors=[],
    )
    _d = _mrp_test.should_enter(_sr, _Regime.CHOPPY, macro_ctx=None)
    check(
        "13.1: SPY mean_reversion at 14:01 ET rejects with no_entry_after reason",
        not _d.enter and _d.reason.startswith("no_entry_after_et_hour:"),
        f"enter={_d.enter} reason={_d.reason!r}",
    )

    # A profile with the rule disabled (field=None) must not reject
    _mrp_no_rule = _MRP_13_1()
    _mrp_no_rule.no_entry_after_et_hour = None
    # also disable the 14:00 cutoff so only regime+confidence apply; the
    # macro_ctx=None fallback will take a fresh snapshot which should be
    # empty in this scratch context
    _d_off = _mrp_no_rule.should_enter(_sr, _Regime.CHOPPY, macro_ctx=None)
    # enter could be True or rejected for confidence reasons — we only care
    # that the rejection is NOT about no_entry_after.
    check(
        "13.1: disabled rule (None) does NOT reject with no_entry_after reason",
        not _d_off.reason.startswith("no_entry_after_et_hour:"),
        f"enter={_d_off.enter} reason={_d_off.reason!r}",
    )
finally:
    _dt_mod_13.datetime = _real_dt_13


# Force-close config plumbing: verify the field is reachable from
# trade_manager's code path by instantiating a profile and inspecting.
check(
    "13.1: force_close_et_hhmm is a profile attribute accessible by trade_manager",
    hasattr(_MRP_13_1(), "force_close_et_hhmm"),
    "MeanReversionProfile missing force_close_et_hhmm attribute",
)

# Non-mean_reversion profiles default to None (no rule)
from profiles.momentum import MomentumProfile as _Mom_13_1
_mom = _Mom_13_1()
check(
    "13.1: non-mean_reversion profile has no force_close rule by default",
    _mom.force_close_et_hhmm is None and _mom.no_entry_after_et_hour is None,
    f"momentum force_close={_mom.force_close_et_hhmm} "
    f"no_entry={_mom.no_entry_after_et_hour}",
)


# --- 13.2 — concurrent-same signal log race: profile_name in UPDATE WHERE ---
# Two profiles evaluated the same (symbol, setup_type) in one iteration and
# both got BUY fills in the same millisecond. Before the fix, the second
# UPDATE (ORDER BY id DESC LIMIT 1) targeted the FIRST profile's row because
# WHERE didn't filter by profile_name. Now it does. Test drives the two
# UPDATEs directly against an in-memory SQLite clone of v2_signal_logs and
# asserts each trade_id lands on the matching profile's row.
import sqlite3 as _sq13_2
import tempfile as _tmp13_2
import os as _os13_2

_race_db = _os13_2.path.join(_tmp13_2.gettempdir(), "test_pipeline_13_2_race.db")
try:
    _os13_2.remove(_race_db)
except FileNotFoundError:
    pass

_c13 = _sq13_2.connect(_race_db)
# Minimal schema — only columns the UPDATE touches + profile_name + entered.
_c13.execute("""
    CREATE TABLE v2_signal_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        profile_name TEXT NOT NULL,
        symbol TEXT NOT NULL,
        setup_type TEXT,
        entered INTEGER DEFAULT 0,
        trade_id TEXT
    )
""")
# Two signal logs: same symbol + setup_type, different profile_name.
# scalp_0dte accepts a momentum setup for SPY; mean_reversion does too via
# its own setup pipeline — both get entered=1 in the same cycle.
_c13.execute(
    "INSERT INTO v2_signal_logs (timestamp, profile_name, symbol, setup_type, entered) "
    "VALUES (?, ?, ?, ?, 1)",
    ("2026-04-21T18:01:00Z", "scalp_0dte", "SPY", "momentum"),
)
_c13.execute(
    "INSERT INTO v2_signal_logs (timestamp, profile_name, symbol, setup_type, entered) "
    "VALUES (?, ?, ?, ?, 1)",
    ("2026-04-21T18:01:00Z", "mean_reversion", "SPY", "momentum"),
)
_c13.commit()

# Replay the UPDATE logic from v2_strategy.py:532-539, once per profile, in
# the order fills arrive. The production statement also has ORDER BY id
# DESC LIMIT 1 — omitted here because Python's stdlib sqlite3 is compiled
# without ENABLE_UPDATE_DELETE_LIMIT and the tiebreaker is irrelevant when
# profile_name narrows the match to one row per profile (which is the
# property this test validates). If the WHERE is wrong (no profile_name),
# both UPDATEs race to both rows and trade_id_A overwrites them both.
_c13.execute(
    """UPDATE v2_signal_logs SET trade_id = ?
       WHERE entered = 1 AND trade_id IS NULL
         AND symbol = ? AND setup_type = ?
         AND profile_name = ?""",
    ("trade_A_scalp", "SPY", "momentum", "scalp_0dte"),
)
_c13.execute(
    """UPDATE v2_signal_logs SET trade_id = ?
       WHERE entered = 1 AND trade_id IS NULL
         AND symbol = ? AND setup_type = ?
         AND profile_name = ?""",
    ("trade_B_meanrev", "SPY", "momentum", "mean_reversion"),
)
_c13.commit()

_rows_13 = {
    r[0]: r[1] for r in _c13.execute(
        "SELECT profile_name, trade_id FROM v2_signal_logs"
    ).fetchall()
}
check(
    "13.2: scalp_0dte signal row got trade_A_scalp (not mean_reversion's)",
    _rows_13.get("scalp_0dte") == "trade_A_scalp",
    f"got {_rows_13.get('scalp_0dte')!r}",
)
check(
    "13.2: mean_reversion signal row got trade_B_meanrev (not scalp's)",
    _rows_13.get("mean_reversion") == "trade_B_meanrev",
    f"got {_rows_13.get('mean_reversion')!r}",
)
# And a null-count check: neither trade_id is None — both UPDATEs hit a row.
_null_count_13 = _c13.execute(
    "SELECT COUNT(*) FROM v2_signal_logs WHERE trade_id IS NULL"
).fetchone()[0]
check(
    "13.2: no v2_signal_logs row left with NULL trade_id after both UPDATEs",
    _null_count_13 == 0,
    f"null rows remaining: {_null_count_13}",
)

# Negative control: without the profile_name filter, the second UPDATE
# would have clobbered the first row too. Recreate the rows, run the
# pre-fix WHERE (no profile_name), and confirm the corruption.
_c13.execute("DELETE FROM v2_signal_logs")
_c13.execute(
    "INSERT INTO v2_signal_logs (timestamp, profile_name, symbol, setup_type, entered) "
    "VALUES (?, ?, ?, ?, 1)",
    ("2026-04-21T18:01:00Z", "scalp_0dte", "SPY", "momentum"),
)
_c13.execute(
    "INSERT INTO v2_signal_logs (timestamp, profile_name, symbol, setup_type, entered) "
    "VALUES (?, ?, ?, ?, 1)",
    ("2026-04-21T18:01:00Z", "mean_reversion", "SPY", "momentum"),
)
_c13.commit()
# Pre-fix WHERE: no profile_name filter. Both UPDATEs match both rows.
_c13.execute(
    """UPDATE v2_signal_logs SET trade_id = ?
       WHERE entered = 1 AND trade_id IS NULL
         AND symbol = ? AND setup_type = ?""",
    ("trade_A_scalp", "SPY", "momentum"),
)
# Second UPDATE now sees trade_id IS NULL = false on both rows, so it's
# a no-op — BUT the first UPDATE already corrupted both rows with the
# scalp trade_id. That's the failure mode the fix prevents.
_c13.execute(
    """UPDATE v2_signal_logs SET trade_id = ?
       WHERE entered = 1 AND trade_id IS NULL
         AND symbol = ? AND setup_type = ?""",
    ("trade_B_meanrev", "SPY", "momentum"),
)
_c13.commit()
_pre_fix_rows = {
    r[0]: r[1] for r in _c13.execute(
        "SELECT profile_name, trade_id FROM v2_signal_logs"
    ).fetchall()
}
check(
    "13.2: negative control — without profile_name, mean_reversion row "
    "gets scalp's trade_id (demonstrates the bug the fix prevents)",
    _pre_fix_rows.get("mean_reversion") == "trade_A_scalp",
    f"pre-fix mean_reversion trade_id = {_pre_fix_rows.get('mean_reversion')!r} "
    "(expected 'trade_A_scalp' — the corruption the fix prevents)",
)

_c13.close()
try:
    _os13_2.remove(_race_db)
except OSError:
    pass


# --- 13.3 — reconcile_positions order-fetch limit + date filter ---
# Before: GetOrdersRequest(..., limit=200) with no date window. On a busy
# day a legit sell could be order #201 and get dropped, booking the trade
# as expired_worthless at -100% instead of the real exit. Fix: limit=500
# + after=midnight-ET-today filter + WARNING log if we hit the ceiling.
# This test stubs Alpaca to return 500 orders (max fetch), puts the
# target sell as order #499 (under the limit), and verifies reconcile
# picks up the sell price correctly.
import uuid as _uuid_13_3
from unittest.mock import patch as _patch_13_3, MagicMock as _MM_13_3

_case_13_3_ids = []
_conn_13_3 = _sqlite3.connect(str(_DB_PATH))
try:
    # Synthetic open SPY trade whose sell is hidden at order index 499
    _tid_13_3 = f"test_13_3_{_uuid_13_3.uuid4().hex[:8]}"
    _case_13_3_ids.append(_tid_13_3)
    _today_iso = _dt.now(_tz.utc).isoformat()
    _conn_13_3.execute(
        """INSERT INTO trades (id, profile_id, symbol, direction, strike,
           expiration, quantity, entry_price, entry_date, setup_type,
           status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_tid_13_3, "test-13-3", "SPY", "CALL", 500.0,
         (_dt.now(_tz.utc).date() - _td(days=1)).isoformat(),
         1, 2.50, _today_iso, "momentum", "open", _today_iso, _today_iso),
    )
    _conn_13_3.commit()
    _conn_13_3.close()

    # Build 500 mock orders. Index 499 (i.e. 500th order) is the real sell
    # for SPY 500 CALL. The rest are unrelated noise orders.
    # OCC symbol for the target: SPY + YYMMDD + C + strike*1000 (8 digits)
    _yesterday = _dt.now(_tz.utc).date() - _td(days=1)
    _yymmdd = _yesterday.strftime("%y%m%d")
    _target_occ = f"SPY{_yymmdd}C00500000"

    def _make_order(symbol, side, status="OrderStatus.FILLED",
                    price=None, qty=1, filled_at=None):
        o = _MM_13_3()
        o.symbol = symbol
        o.side = side
        o.status = status
        o.filled_avg_price = price
        o.qty = qty
        o.filled_at = filled_at or _dt.now(_tz.utc)
        return o

    # 499 noise BUY orders + 1 target SELL (index 499)
    _orders = [_make_order(f"XYZ{_yymmdd}C00100000", "OrderSide.BUY",
                           price=1.0) for _ in range(499)]
    _orders.append(_make_order(_target_occ, "OrderSide.SELL", price=4.25))
    assert len(_orders) == 500

    # Stub Alpaca: returns positions=[] (so target is DB_OPEN_ALPACA_GONE),
    # and get_orders returns our 500-order list.
    _fake_client = _MM_13_3()
    _fake_client.get_all_positions.return_value = []
    _fake_client.get_orders.return_value = _orders

    # Run reconcile --fix against the live DB. Patch the TradingClient
    # at its source (alpaca.trading.client) since reconcile_positions
    # imports it lazily inside run().
    with _patch_13_3("alpaca.trading.client.TradingClient",
                     return_value=_fake_client):
        from scripts import reconcile_positions as _rp_mod_13_3
        _rp_mod_13_3.run(fix=True)

    # Verify the target row was closed with the real fill price, not -100%
    _conn_verify = _sqlite3.connect(str(_DB_PATH))
    _row = _conn_verify.execute(
        "SELECT status, exit_reason, exit_price, pnl_pct FROM trades WHERE id = ?",
        (_tid_13_3,),
    ).fetchone()
    _conn_verify.close()
    check(
        "13.3: target trade is status='closed' after reconcile with 500 orders",
        _row is not None and _row[0] == "closed",
        f"row={_row}",
    )
    check(
        "13.3: exit_reason is 'alpaca_reconcile' (sell found, not expired_worthless)",
        _row is not None and _row[1] == "alpaca_reconcile",
        f"exit_reason={_row[1] if _row else None}",
    )
    check(
        "13.3: exit_price == 4.25 (the real fill, not 0)",
        _row is not None and abs(float(_row[2]) - 4.25) < 0.01,
        f"exit_price={_row[2] if _row else None}",
    )
    check(
        "13.3: pnl_pct is NOT -100 (would indicate expired_worthless false positive)",
        _row is not None and abs(float(_row[3]) + 100.0) > 0.01,
        f"pnl_pct={_row[3] if _row else None}",
    )
finally:
    _conn_cleanup = _sqlite3.connect(str(_DB_PATH))
    for _tid in _case_13_3_ids:
        _conn_cleanup.execute("DELETE FROM trades WHERE id = ?", (_tid,))
    _conn_cleanup.commit()
    _conn_cleanup.close()


# --- 13.5 — base_profile.should_enter handles macro_ctx=None gracefully ---
# The scorer's macro_ctx=None fallback is exercised by 10.12, but the
# profile veto's fallback (_resolve_ctx inside should_enter) was not
# covered. This confirms should_enter against empty macro tables and a
# None ctx does not crash and returns enter=True when inputs permit.
_wipe_macro_tables()
from profiles.momentum import MomentumProfile as _MP_13_5
from scoring.scorer import ScoringResult as _SR_13_5
_prof_13_5 = _MP_13_5()
_scored_13_5 = _SR_13_5(
    symbol="SPY", setup_type="momentum", raw_score=0.85, capped_score=0.85,
    regime_cap_applied=False, regime_cap_value=None,
    threshold_label="high_conviction", direction="bullish", factors=[],
)
try:
    _d_13_5 = _prof_13_5.should_enter(_scored_13_5, _Regime.TRENDING_UP, macro_ctx=None)
    _ok = True
    _err = None
except Exception as _e:
    _ok = False
    _err = _e
    _d_13_5 = None
check(
    "13.5: should_enter with macro_ctx=None + empty tables does NOT crash",
    _ok,
    f"exception: {_err!r}",
)
check(
    "13.5: should_enter returns enter=True on empty macro state (no blocker)",
    _d_13_5 is not None and _d_13_5.enter,
    f"enter={_d_13_5.enter if _d_13_5 else None} reason={_d_13_5.reason if _d_13_5 else None}",
)


# --- 13.6 — regime_fit clamp: raw_value never exceeds 1.0 ---
# Cleanup 5/5 item (a) added `min(1.0, ...)` to the post-macro-nudge
# clamp on scorer.py:189. Today the ceiling is unreachable: line 176
# already clamps base_fit+override to [0, 1.0], and macro_nudge_total
# is constrained to <= 0 by _compute_macro_nudge (regime_delta ∈ {0, -0.10},
# catalyst_delta ∈ [-0.20, 0]). So `clamped[0..1] + (<=0)` can never
# exceed 1.0. Numerical trace for the hottest input in the current regime
# map (momentum × TRENDING_UP, base_fit=1.0) with an aggressive learning
# override of +0.99:
#     line 176: max(0.0, min(1.0, 1.0 + 0.99)) = min(1.0, 1.99) = 1.0
#     line 189: max(0.0, min(1.0, 1.0 + (-0.20))) = 0.80        (when nudge fires)
#     line 189: max(0.0, min(1.0, 1.0 +   0.00)) = 1.0          (when nudge absent)
# The min(1.0, ...) on line 189 is defensive — it only matters if a future
# change introduces a positive macro delta (e.g., a "bullish catalyst →
# +nudge" variant). This test pins the invariant so such a change can't
# silently leak a > 1.0 regime_fit factor into the weighted score.
from scoring.scorer import Scorer as _Scorer_13_6
from scanner.setups import SetupScore as _SS_13_6
from market.context import MarketSnapshot as _MS_13_6
from market.context import Regime as _Regime_13_6, TimeOfDay as _TOD_13_6

_s_13_6 = _Scorer_13_6()
# Aggressive positive learning override — would push base_fit to 1.99
# without the line 176 clamp.
_s_13_6.set_regime_overrides({
    "momentum_TRENDING_UP": 0.99,
})
_setup_13_6 = _SS_13_6(
    setup_type="momentum", score=0.80, reason="test-13.6", direction="bullish",
)
_market_13_6 = _MS_13_6(
    regime=_Regime_13_6.TRENDING_UP,
    time_of_day=_TOD_13_6.MID_MORNING,
    timestamp="2026-04-21T14:30:00+00:00",
)
_result_13_6 = _s_13_6.score(
    "SPY", _setup_13_6, _market_13_6, macro_ctx=None,
)
_regime_fit_factor = next(
    (f for f in _result_13_6.factors if f.name == "regime_fit"), None,
)
check(
    "13.6: regime_fit raw_value clamped to [0, 1.0] under +0.99 override",
    _regime_fit_factor is not None and 0.0 <= _regime_fit_factor.raw_value <= 1.0,
    f"regime_fit raw_value = "
    f"{_regime_fit_factor.raw_value if _regime_fit_factor else None}",
)

# Also verify the 0.0 floor with an aggressive negative override.
_s_13_6_neg = _Scorer_13_6()
_s_13_6_neg.set_regime_overrides({
    "momentum_TRENDING_UP": -0.99,
})
_result_13_6_neg = _s_13_6_neg.score(
    "SPY", _setup_13_6, _market_13_6, macro_ctx=None,
)
_regime_fit_neg = next(
    (f for f in _result_13_6_neg.factors if f.name == "regime_fit"), None,
)
check(
    "13.6: regime_fit raw_value clamped to [0, 1.0] under -0.99 override",
    _regime_fit_neg is not None and 0.0 <= _regime_fit_neg.raw_value <= 1.0,
    f"regime_fit raw_value = "
    f"{_regime_fit_neg.raw_value if _regime_fit_neg else None}",
)

# Synthetic grid check: extreme overrides across all (setup, regime)
# pairs in REGIME_FIT. The clamp invariant must hold for every one.
from scoring.scorer import REGIME_FIT as _RF_13_6
_grid_violations = []
for (setup_type, regime), _base in _RF_13_6.items():
    _s_grid = _Scorer_13_6()
    _s_grid.set_regime_overrides({f"{setup_type}_{regime.value}": 0.99})
    _setup_grid = _SS_13_6(
        setup_type=setup_type, score=0.80, reason="grid", direction="bullish",
    )
    _market_grid = _MS_13_6(
        regime=regime, time_of_day=_TOD_13_6.MID_MORNING,
        timestamp="2026-04-21T14:30:00+00:00",
    )
    try:
        _r = _s_grid.score("SPY", _setup_grid, _market_grid, macro_ctx=None)
        _rf = next((f for f in _r.factors if f.name == "regime_fit"), None)
        if _rf is None or not (0.0 <= _rf.raw_value <= 1.0):
            _grid_violations.append(
                f"{setup_type}/{regime.value}: regime_fit="
                f"{_rf.raw_value if _rf else None}"
            )
    except Exception as _e:
        _grid_violations.append(f"{setup_type}/{regime.value}: exception {_e!r}")
check(
    "13.6: grid sweep — regime_fit clamped for every (setup, regime) pair "
    "under +0.99 override",
    len(_grid_violations) == 0,
    f"violations: {_grid_violations}",
)


# ============================================================
# SECTION 14: post-Prompt-C audit — four bugs found and fixed
# ============================================================
section("14. Post-Prompt-C audit regressions")

# --- 14.1 — no_entry_after_et_hour=0 must mean "disabled", not "cutoff at 0" ---
# apply_config used `int(val) if val is not None else None`, which turned
# the integer 0 (the UI slider's "disabled" sentinel per its hint) into a
# real cutoff. et_hour >= 0 is always true, so every non-mean_reversion
# profile would reject 100% of entries if 0 ever landed in config.
# Fixed: `int(val) if val else None` treats 0 and None equivalently.
from profiles.momentum import MomentumProfile as _MP_14_1

_p14_1 = _MP_14_1()
_p14_1.apply_config({"no_entry_after_et_hour": 0})
check(
    "14.1: apply_config({no_entry_after_et_hour: 0}) -> self.field is None",
    _p14_1.no_entry_after_et_hour is None,
    f"got {_p14_1.no_entry_after_et_hour!r} (expected None)",
)

_p14_1b = _MP_14_1()
_p14_1b.apply_config({"no_entry_after_et_hour": 14})
check(
    "14.1: apply_config({no_entry_after_et_hour: 14}) -> self.field == 14",
    _p14_1b.no_entry_after_et_hour == 14,
    f"got {_p14_1b.no_entry_after_et_hour!r} (expected 14)",
)

_p14_1c = _MP_14_1()
_p14_1c.apply_config({"no_entry_after_et_hour": None})
check(
    "14.1: apply_config({no_entry_after_et_hour: None}) -> self.field is None",
    _p14_1c.no_entry_after_et_hour is None,
    f"got {_p14_1c.no_entry_after_et_hour!r} (expected None)",
)

# End-to-end: should_enter at ET hour 10 with cutoff=0 must NOT reject
# on the no_entry_after_et_hour rule. Freeze datetime so the clock read
# inside should_enter is deterministic. Pattern mirrors 13.1.
import datetime as _dt_mod_14_1
_real_dt_14_1 = _dt_mod_14_1.datetime


class _FrozenDT_14_1(_real_dt_14_1):
    @classmethod
    def now(cls, tz=None):
        # 10:30 ET = 14:30 UTC (EDT offset of -04:00 in April)
        base = _real_dt_14_1(2026, 4, 21, 14, 30, 0, tzinfo=_dt_mod_14_1.timezone.utc)
        if tz is not None:
            return base.astimezone(tz)
        return base


_dt_mod_14_1.datetime = _FrozenDT_14_1
try:
    _p14_1d = _MP_14_1()
    _p14_1d.apply_config({"no_entry_after_et_hour": 0, "min_confidence": 0.0})
    # Direction + regime must pass the earlier gates so only the cutoff
    # rule can be the rejector we care about. momentum in TRENDING_UP.
    _sr_14_1 = _SR_13_5(
        symbol="SPY", setup_type="momentum", raw_score=0.85,
        capped_score=0.85, regime_cap_applied=False, regime_cap_value=None,
        threshold_label="high_conviction", direction="bullish", factors=[],
    )
    _d_14_1 = _p14_1d.should_enter(_sr_14_1, _Regime_13_6.TRENDING_UP, macro_ctx=None)
    check(
        "14.1: should_enter at ET 10:30 with cutoff=0 does NOT reject "
        "on no_entry_after_et_hour",
        not (_d_14_1.reason or "").startswith("no_entry_after_et_hour:"),
        f"reason={_d_14_1.reason!r} enter={_d_14_1.enter}",
    )
    check(
        "14.1: should_enter with cutoff=0 returns enter=True "
        "(all other gates permissive)",
        _d_14_1.enter,
        f"enter={_d_14_1.enter} reason={_d_14_1.reason!r}",
    )
finally:
    _dt_mod_14_1.datetime = _real_dt_14_1


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
