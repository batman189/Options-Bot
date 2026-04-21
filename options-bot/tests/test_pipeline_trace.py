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
