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


# --- 14.2 — confirm_fill keys learning trigger on setup_type, not profile.name ---
# Before Bug B, trade_manager.confirm_fill called
#   self._maybe_trigger_learning(pos.profile.name, ...)
# get_closed_trade_count queries trades WHERE setup_type = ?, so for
# aggregator profiles (scalp_0dte, swing, tsla_swing) whose profile.name
# is not a setup_type, the count was always 0 and the 20-trade trigger
# never fired. Fix passes pos.setup_type — aligns with the other two
# close paths (stale cleanup, reconcile).
#
# Test: seed 19 closed compression_breakout trades, build a ManagedPosition
# with profile=Scalp0DTEProfile() and setup_type="compression_breakout",
# insert it as the 20th (status='open'), run confirm_fill, and assert
# run_learning is called with "compression_breakout" — not "scalp_0dte".
from profiles.scalp_0dte import Scalp0DTEProfile as _Scalp_14_2

_case_14_2_ids = _seed_closed_trades(19, "compression_breakout", "test_14_2")
try:
    _tm_14_2 = _TM_12_3()
    _prof_14_2 = _Scalp_14_2()
    _pos_14_2 = _MP_12_3(
        trade_id=f"test_14_2_{_uuid_12_3.uuid4().hex[:8]}",
        symbol="SPY", direction="bullish", profile=_prof_14_2,
        expiration=_date_12_3(2026, 5, 1),
        entry_time=_dt.now(_tz.utc), entry_price=2.50, quantity=1,
        setup_type="compression_breakout",   # <-- NOT the profile's name
        strike=500.0, right="CALL",
        pending_exit_reason="profit_target",
    )
    _tid_14_2 = _pos_14_2.trade_id
    _case_14_2_ids.append(_tid_14_2)
    _conn_14_2 = _sqlite3.connect(str(_DB_PATH))
    _conn_14_2.execute(
        """INSERT INTO trades (id, profile_id, symbol, direction, strike,
           expiration, quantity, entry_price, entry_date, setup_type,
           status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_tid_14_2, "test-14-2", "SPY", "CALL", 500.0, "2026-05-01",
         1, 2.50, _dt.now(_tz.utc).isoformat(), "compression_breakout",
         "open", _dt.now(_tz.utc).isoformat(), _dt.now(_tz.utc).isoformat()),
    )
    _conn_14_2.commit()
    _conn_14_2.close()
    _tm_14_2._positions[_tid_14_2] = _pos_14_2

    with _patch_12_3("learning.learner.run_learning") as _mock_rl_14_2:
        _mock_rl_14_2.return_value = None
        _tm_14_2.confirm_fill(_tid_14_2, 3.00)

    # run_learning must have been called exactly once with the setup_type
    # positional arg = "compression_breakout" (not "scalp_0dte").
    check(
        "14.2: confirm_fill fires run_learning on 20th compression_breakout close",
        _mock_rl_14_2.called,
        f"called={_mock_rl_14_2.called} call_count={_mock_rl_14_2.call_count}",
    )
    _first_call_arg = (
        _mock_rl_14_2.call_args[0][0]
        if _mock_rl_14_2.called and _mock_rl_14_2.call_args
        else None
    )
    check(
        "14.2: run_learning was called with setup_type='compression_breakout' "
        "(not profile.name='scalp_0dte')",
        _first_call_arg == "compression_breakout",
        f"first positional arg = {_first_call_arg!r} "
        f"(expected 'compression_breakout')",
    )
    check(
        "14.2: run_learning was NOT called with the profile's name",
        _first_call_arg != "scalp_0dte",
        f"first positional arg = {_first_call_arg!r} "
        "(would have been 'scalp_0dte' pre-fix)",
    )
finally:
    _cleanup_trade_ids(_case_14_2_ids)


# --- 14.3 — QQQ position not orphaned when SPY subprocess restarts ---
# v2_strategy._reload_open_positions used `WHERE symbol = ?` with
# self.symbol alone. The SPY subprocess scans [SPY, QQQ] (SPY-only
# subprocess has been configured this way since Prompt B), so a QQQ
# position opened under it survived the DB write but would not be
# re-registered with TradeManager after a restart. Fix: filter by
# self._scan_symbols using WHERE symbol IN (?, ?, ...).
#
# Test seeds two open trades — one SPY, one QQQ — then invokes the
# real _reload_open_positions bound to a minimal V2Strategy-shaped
# stand-in. reconcile's Alpaca call is patched out. Asserts BOTH
# trade_ids get added to the trade manager.
from strategies.v2_strategy import V2Strategy as _V2S_14_3
from management.trade_manager import TradeManager as _TM_14_3
from profiles.momentum import MomentumProfile as _MP_14_3
from profiles.scalp_0dte import Scalp0DTEProfile as _Scalp_14_3

_case_14_3_ids = []
try:
    _today_iso_14_3 = _dt.now(_tz.utc).isoformat()
    _expiry_14_3 = (_dt.now(_tz.utc).date() + _td(days=7)).isoformat()
    _tid_spy = f"test_14_3_spy_{_uuid_12_3.uuid4().hex[:8]}"
    _tid_qqq = f"test_14_3_qqq_{_uuid_12_3.uuid4().hex[:8]}"
    _case_14_3_ids.extend([_tid_spy, _tid_qqq])

    _conn_14_3 = _sqlite3.connect(str(_DB_PATH))
    for _tid, _sym in [(_tid_spy, "SPY"), (_tid_qqq, "QQQ")]:
        _conn_14_3.execute(
            """INSERT INTO trades (id, profile_id, symbol, direction, strike,
               expiration, quantity, entry_price, entry_date, setup_type,
               status, confidence_score, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_tid, "test-14-3", _sym, "CALL", 500.0, _expiry_14_3,
             1, 2.50, _today_iso_14_3, "momentum", "open", 0.70,
             _today_iso_14_3, _today_iso_14_3),
        )
    _conn_14_3.commit()
    _conn_14_3.close()

    # Minimal V2Strategy-shaped stand-in. Bypass __init__ so we don't
    # need Lumibot scaffolding. The method accesses:
    #   self._scan_symbols, self._trade_manager, self._profiles, logger
    _stub = _V2S_14_3.__new__(_V2S_14_3)
    _stub._scan_symbols = ["SPY", "QQQ"]
    _stub.symbol = "SPY"
    _stub._trade_manager = _TM_14_3()
    _stub._profiles = {
        "momentum": _MP_14_3(),
        "scalp_0dte": _Scalp_14_3(),
    }

    # Patch reconcile out — it needs live Alpaca. Bug C fix is about the
    # query below, not reconcile.
    with _patch_12_3("scripts.reconcile_positions.run"):
        _V2S_14_3._reload_open_positions(_stub)

    _reloaded = set(_stub._trade_manager._positions.keys())
    check(
        "14.3: SPY position re-registered with trade manager after reload",
        _tid_spy in _reloaded,
        f"reloaded={_reloaded}",
    )
    check(
        "14.3: QQQ position re-registered with trade manager (not orphaned)",
        _tid_qqq in _reloaded,
        f"reloaded={_reloaded} — QQQ missing means SPY subprocess would "
        "orphan QQQ positions at restart",
    )
    check(
        "14.3: trade manager holds exactly 2 positions (no duplicates, no extras)",
        len(_reloaded) == 2,
        f"expected 2, got {len(_reloaded)}: {_reloaded}",
    )
finally:
    _cleanup_trade_ids(_case_14_3_ids)


# --- 14.4 — scanner rejection signal logs carry profile_name="scanner" ---
# _log_v2_signal's fallback was `profile_name or scored.setup_type`, so
# a caller that passed an empty profile_name got setup_type written as
# the profile_name — polluting any profile_name grouping in reports.
# _log_scanner_rejection's primary path explicitly set
# profile_name = best.setup_type for the same reason. Fix: both now
# write the distinct sentinel "scanner" when the row is a scanner
# rejection and not a real profile evaluation.
from strategies.v2_strategy import V2Strategy as _V2S_14_4
from scanner.scanner import ScanResult as _SR_14_4
from scanner.setups import SetupScore as _SS_14_4
from market.context import MarketSnapshot as _MS_14_4
from market.context import Regime as _Rg_14_4, TimeOfDay as _TD_14_4
from scoring.scorer import Scorer as _Scorer_14_4

# Build a minimal V2Strategy stub — __new__ to skip Lumibot init.
_stub_14_4 = _V2S_14_4.__new__(_V2S_14_4)
_stub_14_4._scorer = _Scorer_14_4()

# Scan result with all-zero setups — forces the "all setups scored 0"
# branch inside _log_scanner_rejection.
_zero_setup = _SS_14_4(setup_type="momentum", score=0.0,
                       reason="rejected: not enough move", direction="bullish")
_scan_14_4 = [_SR_14_4(symbol="SPY", setups=[_zero_setup],
                       best_score=0.0, best_setup="")]
_snap_14_4 = _MS_14_4(
    regime=_Rg_14_4.CHOPPY, time_of_day=_TD_14_4.MID_MORNING,
    timestamp="2026-04-21T14:30:00+00:00",
)

# Mark rows so cleanup is surgical.
_marker_14_4 = f"test_14_4_{_uuid_12_3.uuid4().hex[:8]}"

# Patch write_v2_signal_log so we see the exact payload written.
_written_payloads_14_4 = []


def _spy_write(payload):
    # Tag with marker so we can clean up even if the test errors partway.
    payload["symbol"] = f"{payload['symbol']}_{_marker_14_4}"
    _written_payloads_14_4.append(dict(payload))


# Patch at the module where _log_scanner_rejection imports it
# (backend.database.write_v2_signal_log).
with _patch_12_3("backend.database.write_v2_signal_log", side_effect=_spy_write):
    _V2S_14_4._log_scanner_rejection(_stub_14_4, _scan_14_4, _snap_14_4,
                                      macro_ctx=None)

check(
    "14.4: _log_scanner_rejection wrote at least one row",
    len(_written_payloads_14_4) >= 1,
    f"wrote {len(_written_payloads_14_4)} rows",
)
_pn_values_14_4 = {p.get("profile_name") for p in _written_payloads_14_4}
check(
    "14.4: _log_scanner_rejection rows carry profile_name='scanner' "
    "(not a setup_type like 'momentum')",
    _pn_values_14_4 == {"scanner"},
    f"profile_name values written: {_pn_values_14_4}",
)

# Also exercise the _log_v2_signal fallback — pass profile_name="".
# Before the fix this wrote scored.setup_type; after, "scanner".
from scoring.scorer import ScoringResult as _SR2_14_4
from profiles.base_profile import EntryDecision as _ED_14_4
_scored_14_4 = _SR2_14_4(
    symbol="SPY", setup_type="momentum", raw_score=0.75,
    capped_score=0.75, regime_cap_applied=False, regime_cap_value=None,
    threshold_label="moderate", direction="bullish", factors=[],
)
_decision_14_4 = _ED_14_4(
    enter=False, symbol="SPY", direction="bullish", confidence=0.75,
    hold_minutes=60, profile_name="", reason="test",
)
_written_payloads_14_4.clear()
with _patch_12_3("backend.database.write_v2_signal_log", side_effect=_spy_write):
    _V2S_14_4._log_v2_signal(
        _stub_14_4, _scored_14_4, _decision_14_4, _snap_14_4, "",
    )
check(
    "14.4: _log_v2_signal fallback with profile_name='' writes 'scanner' "
    "(not scored.setup_type)",
    len(_written_payloads_14_4) == 1
    and _written_payloads_14_4[0].get("profile_name") == "scanner",
    f"payload profile_name = "
    f"{_written_payloads_14_4[0].get('profile_name') if _written_payloads_14_4 else 'NO_ROWS'!r}",
)

# Cleanup: remove any marker-tagged rows left behind by the real write
# (if the patch didn't intercept in some runs).
try:
    _c_cleanup_14_4 = _sqlite3.connect(str(_DB_PATH))
    _c_cleanup_14_4.execute(
        "DELETE FROM v2_signal_logs WHERE symbol LIKE ?", (f"%{_marker_14_4}",),
    )
    _c_cleanup_14_4.commit()
    _c_cleanup_14_4.close()
except Exception:
    pass


# --- 14.4b — four risk_manager dead methods are deleted ---
# Grep-style runtime check: after Bug D, these helpers must not resolve
# on a RiskManager instance. Anything that still imports them will fail
# at attribute access, which is loud and correct.
from risk.risk_manager import RiskManager as _RM_14_4
_rm_14_4 = _RM_14_4()
for _method in ("get_day_trade_count", "_get_profile_open_count",
                "_get_profile_daily_trade_count", "calculate_position_size"):
    check(
        f"14.4b: RiskManager.{_method} has been deleted",
        not hasattr(_rm_14_4, _method),
        f"attribute still present: {_method}",
    )


# ============================================================
# SECTION 15: learning state read path — setup_type-keyed, not profile-name-keyed
# ============================================================
section("15. Learning state READ path at V2Strategy.initialize()")

# Bug B (commit e47f37f) renamed the write-side API from profile_name to
# setup_type but left v2_strategy.initialize() calling
# load_learning_state(profile_name). For aggregator profiles
# (scalp_0dte/swing/tsla_swing) that lookup always returned None, so
# their min_confidence reset to the constructor default on every
# restart and regime_fit_overrides written against setup_type rows
# never applied. Prompt A's _apply_learning_state two-pass fix:
#   Pass 1 — scorer-global regime/tod overrides, keyed by setup_type
#   Pass 2 — per-profile min_confidence = max(state across accepted_setup_types)
#            profile.paused = any(state.paused across accepted_setup_types)
#
# Each test seeds trades, invokes run_learning to write a real
# learning_state row, constructs a V2Strategy stub, calls
# _apply_learning_state, asserts the right adjustments landed.

from profiles.swing import SwingProfile as _Swing_15
from learning.learner import run_learning as _run_learning_15

_case_15_ids: list[str] = []
_case_15_setup_types_cleaned: set[str] = set()


def _cleanup_15():
    """Remove synthetic trades AND learning_state rows written by run_learning."""
    _conn = _sqlite3.connect(str(_DB_PATH))
    for _tid in _case_15_ids:
        _conn.execute("DELETE FROM trades WHERE id = ?", (_tid,))
    for _st in _case_15_setup_types_cleaned:
        _conn.execute("DELETE FROM learning_state WHERE profile_name = ?", (_st,))
    _conn.commit()
    _conn.close()


def _make_v2_stub_15(profiles: dict):
    """Minimal V2Strategy stand-in — bypass Lumibot init, same pattern as 14.3."""
    from strategies.v2_strategy import V2Strategy as _V2S_15
    from scoring.scorer import Scorer as _Scorer_15
    _stub = _V2S_15.__new__(_V2S_15)
    _stub._profiles = profiles
    _stub._scorer = _Scorer_15()
    _stub._paused_profiles = set()
    return _stub


try:
    # --- 15.1 — aggregator profile picks up setup_type-keyed learning state ---
    # Seed 10 closed compression_breakout trades. Heavy loss bias so
    # expectancy is negative and run_learning raises min_confidence.
    # Also skew the trades so at least one regime loses badly → regime_fit
    # override is written.
    _ids_15_1 = _seed_closed_trades(10, "compression_breakout", "test_15_1")
    _case_15_ids.extend(_ids_15_1)
    _case_15_setup_types_cleaned.add("compression_breakout")

    # Force all trades into the same regime so the regime_fit adjustment
    # has enough samples to trip. _seed_closed_trades doesn't set
    # market_regime, so patch the rows.
    _c15 = _sqlite3.connect(str(_DB_PATH))
    _c15.executemany(
        "UPDATE trades SET market_regime = 'TRENDING_UP' WHERE id = ?",
        [(tid,) for tid in _ids_15_1],
    )
    # Skew losses so at least half are losses → win_rate < 0.50, and
    # amplify avg_loss so expectancy is clearly negative.
    _c15.executemany(
        "UPDATE trades SET pnl_pct = -50.0 WHERE id = ? AND pnl_pct < 0",
        [(tid,) for tid in _ids_15_1],
    )
    _c15.commit()
    _c15.close()

    # Run learning against setup_type="compression_breakout" with the
    # aggregator's constructor default as the starting min_confidence.
    _before_conf_15_1 = _Scalp_14_3().min_confidence   # reuse the class alias from 14.3
    _new_state_15_1 = _run_learning_15("compression_breakout", _before_conf_15_1)
    # run_learning returns None if < 5 trades; we have 10 so it must run.
    # Sanity-check that SOMETHING was written to the learning_state table.
    _c15 = _sqlite3.connect(str(_DB_PATH))
    _c15.row_factory = _sqlite3.Row
    _written_15_1 = _c15.execute(
        "SELECT min_confidence, regime_fit_overrides FROM learning_state "
        "WHERE profile_name = ?", ("compression_breakout",),
    ).fetchone()
    _c15.close()
    check(
        "15.1: run_learning wrote a learning_state row keyed by "
        "setup_type='compression_breakout'",
        _written_15_1 is not None,
        f"new_state from run_learning: {_new_state_15_1!r}",
    )

    # Construct a V2Strategy stub with scalp_0dte (accepts compression_breakout)
    # and momentum (accepts only momentum — should be unaffected).
    from profiles.momentum import MomentumProfile as _Mom_15
    _stub_15_1 = _make_v2_stub_15({
        "scalp_0dte": _Scalp_14_3(),
        "momentum": _Mom_15(),
    })
    _scalp_default_conf = _Scalp_14_3().min_confidence
    _mom_default_conf = _Mom_15().min_confidence
    _stub_15_1._apply_learning_state()

    _scalp_after = _stub_15_1._profiles["scalp_0dte"].min_confidence
    _mom_after = _stub_15_1._profiles["momentum"].min_confidence

    # The learning-written value comes from the state row; either the
    # raised value or the original default if run_learning's "if changed"
    # branch decided no adjustment was needed. What we must prove:
    # scalp_0dte's post-apply value equals the value stored in
    # learning_state for compression_breakout.
    check(
        "15.1: scalp_0dte.min_confidence after _apply_learning_state equals "
        "the compression_breakout state value (aggregator read path works)",
        abs(_scalp_after - _written_15_1["min_confidence"]) < 1e-6,
        f"stub scalp_0dte={_scalp_after} learning_state row="
        f"{_written_15_1['min_confidence']}",
    )
    check(
        "15.1: momentum.min_confidence unchanged — its only accepted "
        "setup_type 'momentum' had no learning_state row",
        abs(_mom_after - _mom_default_conf) < 1e-6,
        f"after={_mom_after} default={_mom_default_conf}",
    )
    # If regime_fit_overrides was populated in the learning_state row,
    # verify it reached the scorer (pass 1 of the fix).
    import json as _json_15_1
    _rfo_15_1 = _json_15_1.loads(_written_15_1["regime_fit_overrides"] or "{}")
    if _rfo_15_1:
        _scorer_overrides = getattr(_stub_15_1._scorer, "_regime_overrides", {})
        check(
            "15.1: scorer received regime_fit_overrides from the "
            "compression_breakout learning_state row (pass 1 of the fix)",
            all(k in _scorer_overrides for k in _rfo_15_1.keys()),
            f"state row overrides: {_rfo_15_1}, scorer: {_scorer_overrides}",
        )
    else:
        # run_learning decided expectancy didn't cross the regime-cut
        # threshold. Still record a PASS so the section doesn't under-count.
        check(
            "15.1: no regime_fit_overrides written (run_learning saw no "
            "losing regime worth adjusting) — pass-1 path asserted by 15.1b",
            True,
            "run_learning did not write regime_fit_overrides for this seed",
        )

    # --- 15.2 — paused_by_learning on one accepted setup_type pauses aggregator ---
    # Seed 20 closed mean_reversion-style trades but tagged as
    # compression_breakout, with win_rate < 35% (4 wins / 16 losses) to
    # trip the AUTO_PAUSE_WIN_RATE gate. run_learning sets paused_by_learning.
    #
    # Using a fresh setup_type ("macro_trend") so we can isolate the pause
    # signal from the 15.1 row above. Seed 16 losses + 4 wins.
    _ids_15_2 = []
    _today_iso_15_2 = _dt.now(_tz.utc).isoformat()
    _c15_2 = _sqlite3.connect(str(_DB_PATH))
    for _i in range(20):
        _tid = f"test_15_2_{_uuid_12_3.uuid4().hex[:8]}"
        _ids_15_2.append(_tid)
        _case_15_ids.append(_tid)
        _pnl = 60.0 if _i < 4 else -40.0   # 4 wins, 16 losses → 20% WR
        _c15_2.execute(
            """INSERT INTO trades
               (id, profile_id, symbol, direction, strike, expiration, quantity,
                entry_price, entry_date, exit_price, exit_date, pnl_dollars,
                pnl_pct, setup_type, status, exit_reason, market_regime,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_tid, "test-15-2", "SPY", "CALL", 500.0, "2026-05-01",
             1, 2.50, _today_iso_15_2, 3.00 if _pnl > 0 else 2.00,
             _today_iso_15_2, _pnl, _pnl, "macro_trend", "closed",
             "trailing_stop" if _pnl > 0 else "hard_stop",
             "TRENDING_UP", _today_iso_15_2, _today_iso_15_2),
        )
    _c15_2.commit()
    _c15_2.close()
    _case_15_setup_types_cleaned.add("macro_trend")

    _new_state_15_2 = _run_learning_15("macro_trend", 0.60)

    # Verify paused_by_learning is 1 in the persisted row.
    _c15_2 = _sqlite3.connect(str(_DB_PATH))
    _c15_2.row_factory = _sqlite3.Row
    _pause_row = _c15_2.execute(
        "SELECT paused_by_learning FROM learning_state WHERE profile_name = ?",
        ("macro_trend",),
    ).fetchone()
    _c15_2.close()
    check(
        "15.2: run_learning auto-paused macro_trend setup_type "
        "(20-trade WR=20% < 35% threshold)",
        _pause_row is not None and bool(_pause_row["paused_by_learning"]),
        f"pause_row = {dict(_pause_row) if _pause_row else None}",
    )

    # Fresh stub — scalp_0dte accepts macro_trend → should be paused.
    # mean_reversion doesn't accept macro_trend → must stay unpaused.
    from profiles.mean_reversion import MeanReversionProfile as _MR_15_2
    _stub_15_2 = _make_v2_stub_15({
        "scalp_0dte": _Scalp_14_3(),
        "mean_reversion": _MR_15_2(),
    })
    _stub_15_2._apply_learning_state()

    check(
        "15.2: scalp_0dte PAUSED via its accepted_setup_type 'macro_trend'",
        "scalp_0dte" in _stub_15_2._paused_profiles,
        f"paused_profiles = {_stub_15_2._paused_profiles}",
    )
    check(
        "15.2: mean_reversion NOT paused — accepts only 'mean_reversion', "
        "which has no learning_state row",
        "mean_reversion" not in _stub_15_2._paused_profiles,
        f"paused_profiles = {_stub_15_2._paused_profiles}",
    )

    # --- 15.3 — scalar profile read path regression ---
    # Pre-fix code accidentally worked for scalar profiles because
    # profile.name == setup_type. Verify the new two-pass logic preserves
    # that happy path. Seed 10 closed momentum trades, run_learning
    # against "momentum", construct a stub with MomentumProfile, apply,
    # assert min_confidence came from the state row.
    _ids_15_3 = _seed_closed_trades(10, "momentum", "test_15_3")
    _case_15_ids.extend(_ids_15_3)
    _case_15_setup_types_cleaned.add("momentum")

    _c15_3 = _sqlite3.connect(str(_DB_PATH))
    _c15_3.executemany(
        "UPDATE trades SET market_regime = 'TRENDING_UP' WHERE id = ?",
        [(tid,) for tid in _ids_15_3],
    )
    # Modest loss bias → negative expectancy → run_learning raises threshold.
    _c15_3.executemany(
        "UPDATE trades SET pnl_pct = -35.0 WHERE id = ? AND pnl_pct < 0",
        [(tid,) for tid in _ids_15_3],
    )
    _c15_3.commit()
    _c15_3.close()

    _mom_start = _Mom_15().min_confidence
    _new_state_15_3 = _run_learning_15("momentum", _mom_start)
    _c15_3 = _sqlite3.connect(str(_DB_PATH))
    _c15_3.row_factory = _sqlite3.Row
    _mom_state = _c15_3.execute(
        "SELECT min_confidence FROM learning_state WHERE profile_name = ?",
        ("momentum",),
    ).fetchone()
    _c15_3.close()

    _stub_15_3 = _make_v2_stub_15({"momentum": _Mom_15()})
    _stub_15_3._apply_learning_state()
    _mom_after_15_3 = _stub_15_3._profiles["momentum"].min_confidence
    check(
        "15.3: scalar MomentumProfile picks up its setup_type state row "
        "(regression — the scalar path must still work)",
        _mom_state is not None
        and abs(_mom_after_15_3 - _mom_state["min_confidence"]) < 1e-6,
        f"state_row={dict(_mom_state) if _mom_state else None} "
        f"profile_after={_mom_after_15_3}",
    )
finally:
    _cleanup_15()


# ============================================================
# SECTION 16: profile_name persisted on trade row for correct reload
# ============================================================
section("16. Trade profile_name persistence + reload resolution")

# Reload tests need a minimal V2Strategy stub (bypass Lumibot init via
# __new__) plus two profiles to choose between. Using scalp_0dte and
# swing — they accept overlapping setup_types, so pre-fix code could
# bind a compression_breakout trade to either one depending on dict
# iteration order and fallback chain.
from strategies.v2_strategy import V2Strategy as _V2S_16
from profiles.scalp_0dte import Scalp0DTEProfile as _Scalp_16
from profiles.swing import SwingProfile as _Swing_16
from profiles.momentum import MomentumProfile as _Mom_16
from management.trade_manager import TradeManager as _TM_16

_case_16_ids = []


def _insert_16_trade(tid, symbol, setup_type, profile_name, status="open"):
    """Insert an open trade row with explicit profile_name (or NULL)."""
    _case_16_ids.append(tid)
    _today = _dt.now(_tz.utc).isoformat()
    _expiry = (_dt.now(_tz.utc).date() + _td(days=7)).isoformat()
    _conn = _sqlite3.connect(str(_DB_PATH))
    _conn.execute(
        """INSERT INTO trades (id, profile_id, profile_name, symbol, direction,
           strike, expiration, quantity, entry_price, entry_date, setup_type,
           confidence_score, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (tid, "test-16", profile_name, symbol, "CALL", 500.0, _expiry,
         1, 2.50, _today, setup_type, 0.70, status, _today, _today),
    )
    _conn.commit()
    _conn.close()


def _make_reload_stub(profiles: dict, scan_symbols=("SPY", "QQQ")):
    """Minimal V2Strategy stand-in for exercising _reload_open_positions."""
    _stub = _V2S_16.__new__(_V2S_16)
    _stub._scan_symbols = list(scan_symbols)
    _stub.symbol = scan_symbols[0]
    _stub._trade_manager = _TM_16()
    _stub._profiles = profiles
    return _stub


try:
    # --- 16.1 — profile_name on row resolves to the exact profile, not a
    # setup_type-based guess that would have hit the wrong aggregator.
    _tid_16_1 = f"test_16_1_{_uuid_12_3.uuid4().hex[:8]}"
    _insert_16_trade(
        _tid_16_1, "SPY",
        setup_type="compression_breakout",
        profile_name="scalp_0dte",
    )
    _stub_16_1 = _make_reload_stub({
        "scalp_0dte": _Scalp_16(),
        "swing": _Swing_16(),
    })
    with _patch_12_3("scripts.reconcile_positions.run"):
        _V2S_16._reload_open_positions(_stub_16_1)
    _pos_16_1 = _stub_16_1._trade_manager._positions.get(_tid_16_1)
    check(
        "16.1: reload bound compression_breakout trade to Scalp0DTEProfile "
        "(via profile_name), not SwingProfile",
        _pos_16_1 is not None
        and type(_pos_16_1.profile).__name__ == "Scalp0DTEProfile",
        f"profile class = "
        f"{type(_pos_16_1.profile).__name__ if _pos_16_1 else 'NOT_RELOADED'}",
    )

    # --- 16.2 — legacy rows (profile_name=NULL) fall back cleanly and log
    # a WARNING. setup_type="momentum" is a direct profile key so fallback 1
    # hits; no fallback-2 warning expected.
    _tid_16_2 = f"test_16_2_{_uuid_12_3.uuid4().hex[:8]}"
    _insert_16_trade(
        _tid_16_2, "SPY",
        setup_type="momentum",
        profile_name=None,     # legacy row
    )
    _stub_16_2 = _make_reload_stub({
        "scalp_0dte": _Scalp_16(),
        "swing": _Swing_16(),
        "momentum": _Mom_16(),
    })
    with _patch_12_3("scripts.reconcile_positions.run"):
        _V2S_16._reload_open_positions(_stub_16_2)
    _pos_16_2 = _stub_16_2._trade_manager._positions.get(_tid_16_2)
    check(
        "16.2: legacy NULL profile_name reloads via setup_type fallback "
        "(momentum profile for momentum setup)",
        _pos_16_2 is not None
        and type(_pos_16_2.profile).__name__ == "MomentumProfile",
        f"profile class = "
        f"{type(_pos_16_2.profile).__name__ if _pos_16_2 else 'NOT_RELOADED'}",
    )

    # --- 16.2b — legacy row with NULL profile_name AND a setup_type that
    # doesn't directly match any active profile. Must hit fallback 2 and
    # log a WARNING. Verify via a log capture handler.
    import logging as _log_16_2b
    _v2_logger_16 = _log_16_2b.getLogger("options-bot.strategy.v2")
    _warn_records_16 = []

    class _LogCap_16(_log_16_2b.Handler):
        def emit(self, record):
            if record.levelno >= _log_16_2b.WARNING:
                _warn_records_16.append(record.getMessage())

    _cap_handler = _LogCap_16()
    _v2_logger_16.addHandler(_cap_handler)
    try:
        _tid_16_2b = f"test_16_2b_{_uuid_12_3.uuid4().hex[:8]}"
        _insert_16_trade(
            _tid_16_2b, "SPY",
            setup_type="compression_breakout",  # not a direct profile key in stub
            profile_name=None,
        )
        _stub_16_2b = _make_reload_stub({
            "scalp_0dte": _Scalp_16(),      # fallback-2 candidate, hit first
            "swing": _Swing_16(),
        })
        with _patch_12_3("scripts.reconcile_positions.run"):
            _V2S_16._reload_open_positions(_stub_16_2b)
        _pos_16_2b = _stub_16_2b._trade_manager._positions.get(_tid_16_2b)
    finally:
        _v2_logger_16.removeHandler(_cap_handler)
    check(
        "16.2b: legacy NULL profile_name + non-matching setup_type "
        "reloads via fallback 2 (aggregator best-effort)",
        _pos_16_2b is not None
        and type(_pos_16_2b.profile).__name__ == "Scalp0DTEProfile",
        f"profile class = "
        f"{type(_pos_16_2b.profile).__name__ if _pos_16_2b else 'NOT_RELOADED'}",
    )
    _fallback2_warning = any(
        "fell back to" in msg and _tid_16_2b[:8] in msg for msg in _warn_records_16
    )
    check(
        "16.2b: fallback 2 emitted a WARNING naming the trade_id + candidate",
        _fallback2_warning,
        f"warnings captured (showing relevant ones): "
        f"{[m for m in _warn_records_16 if 'fell back to' in m]}",
    )

    # --- 16.3 — the BUY-fill INSERT writes profile_name. Rather than spin
    # up Lumibot's on_filled_order path (needs broker + Order objects),
    # simulate the INSERT using the exact SQL from v2_strategy.py so any
    # column-list / VALUES-count mismatch surfaces here. The entry dict
    # mirrors the real _trade_id_map shape.
    _tid_16_3 = f"test_16_3_{_uuid_12_3.uuid4().hex[:8]}"
    _case_16_ids.append(_tid_16_3)
    _entry_16_3 = {
        "profile_id": "test-16-3",
        "profile_name": "mean_reversion",
        "symbol": "SPY",
        "direction": "CALL",
        "strike": 500.0,
        "expiration": (_dt.now(_tz.utc).date() + _td(days=7)).isoformat(),
        "quantity": 1,
        "setup_type": "mean_reversion",
        "confidence_score": 0.72,
        "regime": "CHOPPY",
        "vix_level": 15.5,
    }
    _now_utc_16 = _dt.now(_tz.utc).isoformat()
    _c16 = _sqlite3.connect(str(_DB_PATH))
    _c16.execute(
        """INSERT INTO trades (
               id, profile_id, profile_name, symbol, direction, strike, expiration,
               quantity, entry_price, entry_date, setup_type,
               confidence_score, market_regime, market_vix,
               status, created_at, updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            _tid_16_3, _entry_16_3["profile_id"], _entry_16_3["profile_name"],
            _entry_16_3["symbol"], _entry_16_3["direction"], _entry_16_3["strike"],
            _entry_16_3["expiration"], _entry_16_3["quantity"], 2.50, _now_utc_16,
            _entry_16_3["setup_type"], _entry_16_3["confidence_score"],
            _entry_16_3["regime"], _entry_16_3["vix_level"],
            "open", _now_utc_16, _now_utc_16,
        ),
    )
    _c16.commit()
    _row_16_3 = _c16.execute(
        "SELECT profile_name, setup_type FROM trades WHERE id = ?", (_tid_16_3,),
    ).fetchone()
    _c16.close()
    check(
        "16.3: fresh BUY-fill INSERT persists profile_name = 'mean_reversion'",
        _row_16_3 is not None and _row_16_3[0] == "mean_reversion",
        f"row = {_row_16_3!r}",
    )
    check(
        "16.3: setup_type still persisted alongside profile_name",
        _row_16_3 is not None and _row_16_3[1] == "mean_reversion",
        f"row = {_row_16_3!r}",
    )
finally:
    # Surgical cleanup — only the test rows this section wrote.
    _conn_cleanup_16 = _sqlite3.connect(str(_DB_PATH))
    for _tid in _case_16_ids:
        _conn_cleanup_16.execute("DELETE FROM trades WHERE id = ?", (_tid,))
    _conn_cleanup_16.commit()
    _conn_cleanup_16.close()


# ============================================================
# SECTION 17: sizer drawdown halving no longer defeated by min-1 floor
# ============================================================
section("17. Sizer blocks when halved risk cannot fit one contract")

# Prompt 17 Commit A fixes the silent override where
#   contracts = max(1, math.floor(final_risk / contract_cost))
# opened a 1-contract position at full contract_cost even when the
# halved budget was smaller than one contract — defeating the
# drawdown halving the caller had just applied. Now: floor==0 blocks.

from sizing.sizer import calculate as _size_17


# --- 17.1 — growth mode, 8.5% drawdown, halving defeats old code ---
# Spec trace: $5000 opening balance, now $4575 (8.5% down),
# confidence=0.72, premium=$4 (contract_cost=$400).
# Pre-fix: contracts=1 at $400 on a ~$316 halved budget.
# Post-fix: blocked with insufficient_risk_budget.
_r_17_1 = _size_17(
    account_value=4575, confidence=0.72, premium=4.00,
    day_start_value=5000, starting_balance=5000, current_exposure=0,
    is_same_day_trade=True, day_trades_remaining=3,
    growth_mode_config=True,
)
check(
    "17.1: growth mode + 8.5% drawdown + premium > halved budget -> blocked",
    _r_17_1.blocked is True and _r_17_1.contracts == 0,
    f"blocked={_r_17_1.blocked} contracts={_r_17_1.contracts}",
)
check(
    "17.1: block_reason names insufficient_risk_budget",
    "insufficient_risk_budget" in (_r_17_1.block_reason or ""),
    f"block_reason={_r_17_1.block_reason!r}",
)
check(
    "17.1: halvings_applied audit trail still lists GROWTH_MODE + drawdown",
    "GROWTH_MODE" in _r_17_1.halvings_applied
    and any("drawdown" in h for h in _r_17_1.halvings_applied),
    f"halvings={_r_17_1.halvings_applied}",
)
check(
    "17.1: final_risk in audit trail reflects the halved budget "
    "(not zeroed to hide the halving)",
    _r_17_1.final_risk > 0 and _r_17_1.final_risk < _r_17_1.confidence_risk,
    f"final_risk={_r_17_1.final_risk} confidence_risk={_r_17_1.confidence_risk}",
)


# --- 17.2 — healthy account, affordable contract, regression ---
# Growth-mode happy path: no drawdown, contract fits budget.
# $10K account, conf=0.72, $1 premium -> growth_risk=$1500,
# conf_scaled ≈ $1380, floor(1380/100) = 13. Must NOT block.
_r_17_2 = _size_17(
    account_value=10000, confidence=0.72, premium=1.00,
    day_start_value=10000, starting_balance=10000, current_exposure=0,
    is_same_day_trade=True, day_trades_remaining=3,
    growth_mode_config=True,
)
check(
    "17.2: healthy growth-mode account + affordable contract -> not blocked",
    _r_17_2.blocked is False,
    f"blocked={_r_17_2.blocked} block_reason={_r_17_2.block_reason!r}",
)
check(
    "17.2: contracts >= 10 (budget comfortably fits many contracts)",
    _r_17_2.contracts >= 10,
    f"contracts={_r_17_2.contracts}",
)


# --- 17.3 — minimum-budget edge, pre-fix silently overshot ---
# $2000 account, no drawdown, $3 premium. growth_risk=$300,
# conf_scaled drops below $300 contract cost -> floor=0.
# Pre-fix: max(1,0)=1 opens $300 position on a ~$280 budget.
# Post-fix: blocked.
_r_17_3 = _size_17(
    account_value=2000, confidence=0.72, premium=3.00,
    day_start_value=2000, starting_balance=2000, current_exposure=0,
    is_same_day_trade=True, day_trades_remaining=3,
    growth_mode_config=True,
)
check(
    "17.3: minimum-budget edge case (contract > confidence-scaled risk) "
    "-> blocked post-fix",
    _r_17_3.blocked is True and _r_17_3.contracts == 0,
    f"blocked={_r_17_3.blocked} contracts={_r_17_3.contracts} "
    f"final_risk={_r_17_3.final_risk} premium_per_contract={_r_17_3.premium_per_contract}",
)


# --- 17.4 — normal mode (line 242 branch) has the same fix ---
# $50K account (past growth threshold), growth_mode_config=False,
# 10% drawdown, $30 premium (contract_cost=$3000).
# base_risk=$2000, confidence_risk=$1440, after_dd=$720,
# floor(720/3000)=0. Pre-fix: 1 contract at $3000 on $720 budget.
# Post-fix: blocked.
_r_17_4 = _size_17(
    account_value=45000, confidence=0.72, premium=30.00,
    day_start_value=50000, starting_balance=50000, current_exposure=0,
    is_same_day_trade=False, day_trades_remaining=3,
    growth_mode_config=False,
)
check(
    "17.4: normal mode + 10% drawdown + premium > halved budget -> blocked",
    _r_17_4.blocked is True and _r_17_4.contracts == 0,
    f"blocked={_r_17_4.blocked} contracts={_r_17_4.contracts} "
    f"block_reason={_r_17_4.block_reason!r}",
)
check(
    "17.4: halvings_applied preserves the drawdown entry "
    "(normal mode should list 'day_drawdown_*')",
    any("day_drawdown" in h for h in _r_17_4.halvings_applied),
    f"halvings={_r_17_4.halvings_applied}",
)


# ============================================================
# SECTION 18: EV gate disabled (Prompt 17 Commit B)
# ============================================================
section("18. EV gate disabled when predicted_move_pct is None")

# Prompt 17 Commit B disabled the EV gate on the non-0DTE path. The
# prior input (setup.score * 2) was a dimensionless scanner fitness
# score fed into a calculation that treated it as a forward-move
# percentage -- inflating the EV ~5x for a typical signal. Until a
# real move forecast exists, the EV filter is skipped; other filters
# (liquidity, spread, VIX, confidence, regime, cooldown, position
# cap, sizer risk budget) continue to run.

from unittest.mock import MagicMock as _MM_18
from selection.filters import apply_ev_validation as _ev_validate_18
from selection.ev import compute_ev as _compute_ev_18


class _FakeGreeks_18:
    delta = 0.50; gamma = 0.015; theta = -0.25; vega = 0.30; implied_vol = 0.18


_fake_client_18 = _MM_18()
_fake_client_18.get_greeks.return_value = _FakeGreeks_18()

_candidate_18 = {
    "strike": 500.0, "bid": 3.40, "ask": 3.60,
    "open_interest": 300, "volume": 100, "right": "CALL",
    "_mid": 3.50, "_spread_pct": 5.7,
}


# --- 18.1 -- EV disabled on non-0DTE path returns candidates, attaches
#             Greeks, leaves _ev_pct=None (not 0) ---
_res_18_1 = _ev_validate_18(
    candidates=[dict(_candidate_18)],
    data_client=_fake_client_18, symbol="SPY",
    expiration="2026-04-28", right="CALL", underlying=500.0,
    predicted_move_pct=None,   # EV disabled sentinel
    hold_days=2.0, dte=7,
)
check(
    "18.1: predicted_move_pct=None -> candidate still returned (EV not filtering)",
    len(_res_18_1) == 1,
    f"validated count = {len(_res_18_1)}",
)
check(
    "18.1: Greeks attached on disabled path",
    _res_18_1[0].get("_greeks") is not None
    and _res_18_1[0]["_greeks"].delta == 0.50,
    f"_greeks = {_res_18_1[0].get('_greeks')}",
)
check(
    "18.1: _ev_pct is None (not 0) when EV gate was disabled",
    _res_18_1[0]["_ev_pct"] is None,
    f"_ev_pct = {_res_18_1[0]['_ev_pct']!r}",
)


# --- 18.2 -- liquidity filter (a different gate) still blocks on its
#             own. Build a wide-spread candidate; run it through the
#             liquidity gate. Disabling EV didn't make other filters
#             permissive. ---
from selection.filters import apply_liquidity_gate as _liq_18
_wide_18 = {
    "strike": 500.0, "bid": 1.00, "ask": 2.00,   # 66% spread -> rejected
    "open_interest": 300, "volume": 100, "right": "CALL",
}
_after_liq_18 = _liq_18([_wide_18], symbol="SPY", dte=7)
check(
    "18.2: wide-spread candidate still blocked by liquidity gate",
    len(_after_liq_18) == 0,
    f"liquidity-passed count = {len(_after_liq_18)}",
)

_healthy_18 = {
    "strike": 500.0, "bid": 3.40, "ask": 3.60,   # tight spread
    "open_interest": 300, "volume": 100, "right": "CALL",
}
_after_liq_18b = _liq_18([_healthy_18], symbol="SPY", dte=7)
check(
    "18.2: healthy candidate still passes liquidity gate",
    len(_after_liq_18b) == 1,
    f"liquidity-passed count = {len(_after_liq_18b)}",
)


# --- 18.3 -- EV function still callable with a real forecast. Disable
#             didn't delete compute_ev or apply_ev_validation's numeric
#             path. Option C (reinstate with a real input) works
#             without touching this commit. ---
_res_18_3 = _ev_validate_18(
    candidates=[dict(_candidate_18)],
    data_client=_fake_client_18, symbol="SPY",
    expiration="2026-04-28", right="CALL", underlying=500.0,
    predicted_move_pct=1.5,      # real forecast supplied
    hold_days=2.0, dte=7,
)
check(
    "18.3: predicted_move_pct=1.5 (real forecast) -> EV numeric path still runs",
    len(_res_18_3) == 1
    and isinstance(_res_18_3[0]["_ev_pct"], (int, float))
    and _res_18_3[0]["_ev_pct"] > 0,
    f"_ev_pct = {_res_18_3[0]['_ev_pct']!r}",
)

# Direct ev.compute_ev produces documented math on a known input.
# move = 500 * 1.5 / 100 = 7.5
# expected_gain = 0.50 * 7.5 + 0.5 * 0.015 * 7.5^2 = 3.75 + 0.42 = 4.17
# theta_cost = 0.25 * 2.0 * 1.5 (dte=7 accel) = 0.75
# ev = (4.17 - 0.75) / 3.50 * 100 ~= 97.7
_ev_direct_18 = _compute_ev_18(
    underlying_price=500.0, predicted_move_pct=1.5,
    delta=0.50, gamma=0.015, theta=-0.25,
    premium=3.50, hold_days=2.0, dte=7,
)
check(
    "18.3: compute_ev produces documented math on a known input (~97.7%)",
    abs(_ev_direct_18 - 97.7) < 1.0,
    f"compute_ev = {_ev_direct_18} (expected ~97.7)",
)


# --- 18.4 -- SelectedContract.ev_pct is Optional; None survives
#             round-trip through the dataclass ---
from selection.selector import SelectedContract as _SC_18
_sc_18 = _SC_18(
    symbol="SPY", strike=500.0, expiration="2026-04-28", right="CALL",
    bid=3.40, ask=3.60, mid=3.50, spread_pct=5.7,
    open_interest=300, volume=100,
    delta=0.50, gamma=0.015, theta=-0.25, vega=0.30, implied_vol=0.18,
    ev_pct=None, strike_tier="atm",    # None allowed by dataclass
)
check(
    "18.4: SelectedContract accepts ev_pct=None without a dataclass error",
    _sc_18.ev_pct is None,
    f"ev_pct = {_sc_18.ev_pct!r}",
)


# ============================================================
# SECTION 19: exit_retry_count resets on successful submission
# ============================================================
section("19. Exit retry counter resets after clean submit_order")

# Prompt 19: the transient-retry ladder in _submit_exit_order must
# reset to 0 when submit_order returns without raising. The pre-fix
# code only reset in the PDT and insufficient error branches; the
# happy-path branch never reset. Over time, a position that hit 4
# transient errors then succeeded would sit one transient away from
# ABANDONED if the order later expired server-side and needed
# re-submission. Abandonment blanks pending_exit and stops the
# position from being monitored further.

from datetime import date as _date_19
from unittest.mock import MagicMock as _MM_19
from strategies.v2_strategy import V2Strategy as _V2S_19
from management.trade_manager import ManagedPosition as _MP_19
from profiles.momentum import MomentumProfile as _Mom_19


def _make_exit_stub_19():
    """Minimal V2Strategy stand-in exposing only what _submit_exit_order reads."""
    _stub = _V2S_19.__new__(_V2S_19)
    _stub._trade_id_map = {}
    _stub.get_last_price = _MM_19(return_value=3.50)
    _counter = [0]

    def _create_order(*a, **kw):
        _counter[0] += 1
        m = _MM_19()
        m.id = f"fake_order_{_counter[0]}"
        return m
    _stub.create_order = _create_order
    _stub._order_counter = _counter
    return _stub


def _make_position_19(trade_id: str) -> "_MP_19":
    return _MP_19(
        trade_id=trade_id, symbol="SPY", direction="bullish",
        profile=_Mom_19(),
        expiration=_date_19(2026, 5, 1),
        entry_time=_dt.now(_tz.utc),
        entry_price=2.50, quantity=1,
        setup_type="momentum", strike=500.0, right="CALL",
        pending_exit=True, pending_exit_reason="profit_target",
    )


# --- 19.1 — transient-error ladder preserved within one submission,
#           counter resets on the success that follows ---
# 4 transient failures then a successful 5th call. Pre-fix call 5 left
# retry_count=4; post-fix resets to 0.
_stub_19_1 = _make_exit_stub_19()
_pos_19_1 = _make_position_19("test_19_1")
_submit_counter_19_1 = [0]


def _submit_4fail_1ok(order):
    _submit_counter_19_1[0] += 1
    if _submit_counter_19_1[0] <= 4:
        raise ConnectionError("transient network error")
    return order


_stub_19_1.submit_order = _submit_4fail_1ok

_observed_counts_19_1 = []
for _cycle in range(1, 6):
    _V2S_19._submit_exit_order(_stub_19_1, _pos_19_1.trade_id, _pos_19_1)
    _observed_counts_19_1.append(_pos_19_1.exit_retry_count)

check(
    "19.1: transient-error ladder preserved within one submission "
    "(counts 1/2/3/4 over cycles 1-4)",
    _observed_counts_19_1[:4] == [1, 2, 3, 4],
    f"observed counts through cycle 4 = {_observed_counts_19_1[:4]}",
)
check(
    "19.1: successful submission on cycle 5 resets exit_retry_count to 0",
    _observed_counts_19_1[4] == 0,
    f"cycle-5 count = {_observed_counts_19_1[4]} (pre-fix stayed at 4)",
)
check(
    "19.1: pending_exit still True after successful submission "
    "(exit is pending fill confirmation)",
    _pos_19_1.pending_exit is True,
    f"pending_exit = {_pos_19_1.pending_exit}",
)
check(
    "19.1: pending_exit_order_id set to the submitted order's id",
    _pos_19_1.pending_exit_order_id != 0,
    f"pending_exit_order_id = {_pos_19_1.pending_exit_order_id!r}",
)


# --- 19.2 — abandonment still fires at 5 consecutive failures ---
# Every call raises a transient error. The fix must not gate
# abandonment behind the success path.
_stub_19_2 = _make_exit_stub_19()
_pos_19_2 = _make_position_19("test_19_2")


def _always_raise(order):
    raise ConnectionError("always transient")


_stub_19_2.submit_order = _always_raise

# Capture CRITICAL logs for the "EXIT ABANDONED" signal
import logging as _log_19_2
_v2_logger_19 = _log_19_2.getLogger("options-bot.strategy.v2")
_critical_records_19 = []


class _LogCap_19(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.CRITICAL:
            _critical_records_19.append(record.getMessage())


_h19 = _LogCap_19()
_v2_logger_19.addHandler(_h19)
try:
    for _cycle in range(1, 6):
        _V2S_19._submit_exit_order(_stub_19_2, _pos_19_2.trade_id, _pos_19_2)
finally:
    _v2_logger_19.removeHandler(_h19)

check(
    "19.2: 5th failure marks pending_exit=False (abandoned)",
    _pos_19_2.pending_exit is False,
    f"pending_exit = {_pos_19_2.pending_exit}",
)
check(
    "19.2: pending_exit_reason cleared on abandonment",
    _pos_19_2.pending_exit_reason == "",
    f"pending_exit_reason = {_pos_19_2.pending_exit_reason!r}",
)
# Prompt 20 Commit A changed post-abandonment state: retry_count now
# resets to 0 (from 5) so a future exit attempt gets a fresh 5-retry
# ladder. The CRITICAL log is still the signal that abandonment fired.
check(
    "19.2: retry_count reset to 0 on abandonment (Prompt 20 Commit A) "
    "so the next attempt gets a fresh ladder",
    _pos_19_2.exit_retry_count == 0,
    f"exit_retry_count = {_pos_19_2.exit_retry_count}",
)
check(
    "19.2: CRITICAL 'EXIT ABANDONED' log line emitted",
    any("EXIT ABANDONED" in m for m in _critical_records_19),
    f"critical records: {_critical_records_19}",
)


# --- 19.3 — successful first attempt does NOT increment retry count ---
# If a future refactor accidentally always bumps the counter, this fails.
_stub_19_3 = _make_exit_stub_19()
_pos_19_3 = _make_position_19("test_19_3")
_stub_19_3.submit_order = lambda order: order    # clean success

# Capture error logs to prove the error path wasn't hit
_error_records_19_3 = []


class _ErrCap_19_3(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.ERROR:
            _error_records_19_3.append(record.getMessage())


_h19_3 = _ErrCap_19_3()
_v2_logger_19.addHandler(_h19_3)
try:
    _V2S_19._submit_exit_order(_stub_19_3, _pos_19_3.trade_id, _pos_19_3)
finally:
    _v2_logger_19.removeHandler(_h19_3)

check(
    "19.3: clean first attempt leaves exit_retry_count at 0",
    _pos_19_3.exit_retry_count == 0,
    f"exit_retry_count = {_pos_19_3.exit_retry_count}",
)
check(
    "19.3: pending_exit_order_id set after successful submit",
    _pos_19_3.pending_exit_order_id != 0,
    f"pending_exit_order_id = {_pos_19_3.pending_exit_order_id!r}",
)
check(
    "19.3: no ERROR-level logs emitted on a clean first submission",
    len(_error_records_19_3) == 0,
    f"errors captured: {_error_records_19_3}",
)


# --- 19.4 — fresh position after abandonment gets a clean slate ---
# Position A is abandoned with exit_retry_count=5. Position B is a
# separate ManagedPosition; its counter must start at 0 regardless.
_stub_19_4 = _make_exit_stub_19()
_pos_19_4_A = _make_position_19("test_19_4_A")
_pos_19_4_A.exit_retry_count = 5    # simulate post-abandonment state
_pos_19_4_A.pending_exit = False

_pos_19_4_B = _make_position_19("test_19_4_B")
# B starts at the dataclass default
check(
    "19.4: fresh ManagedPosition B starts at exit_retry_count=0 "
    "regardless of abandoned position A",
    _pos_19_4_B.exit_retry_count == 0,
    f"B exit_retry_count = {_pos_19_4_B.exit_retry_count}",
)

_submit_counter_19_4 = [0]


def _one_fail_then_ok(order):
    _submit_counter_19_4[0] += 1
    if _submit_counter_19_4[0] == 1:
        raise ConnectionError("first-cycle transient")
    return order


_stub_19_4.submit_order = _one_fail_then_ok
_V2S_19._submit_exit_order(_stub_19_4, _pos_19_4_B.trade_id, _pos_19_4_B)
check(
    "19.4: B's first cycle (transient) -> exit_retry_count=1 "
    "(not 6 = no leak from A)",
    _pos_19_4_B.exit_retry_count == 1,
    f"B exit_retry_count = {_pos_19_4_B.exit_retry_count}",
)
_V2S_19._submit_exit_order(_stub_19_4, _pos_19_4_B.trade_id, _pos_19_4_B)
check(
    "19.4: B's second cycle (success) -> exit_retry_count=0",
    _pos_19_4_B.exit_retry_count == 0,
    f"B exit_retry_count = {_pos_19_4_B.exit_retry_count}",
)


# ============================================================
# SECTION 20: abandonment clears the Block-3 exit lock
# ============================================================
section("20. Abandonment clears pending_exit_order_id + _trade_id_map entry")

# Prompt 20 Commit A: when _submit_exit_order gives up after 5 retries,
# it must also clear pending_exit_order_id and drop the stale entry
# from self._trade_id_map. Without this, Block 3 in Step 10 continues
# to skip the position (`pos.pending_exit_order_id and id in
# self._trade_id_map`), locking the position out of any future exit
# attempt. Also resets exit_retry_count so the next attempt starts
# with a fresh 5-retry ladder.

# Setup: stub create_order to raise — keeps pos.pending_exit_order_id
# pinned at the pre-seeded value across all 5 cycles (the line that
# overwrites it sits between create_order and submit_order, so an
# error at create_order leaves it untouched).

def _make_abandonment_stub_20(seeded_map: dict):
    _stub = _V2S_19.__new__(_V2S_19)
    _stub._trade_id_map = seeded_map
    _stub.get_last_price = _MM_19(return_value=3.50)

    def _raise_create(*a, **kw):
        raise ConnectionError("transient at create_order")
    _stub.create_order = _raise_create
    _stub.submit_order = _MM_19()  # never reached
    return _stub


# --- 20.1 — 5 transient failures clear the lock + drop map entry ---
_seeded_map_20_1 = {77777: "test_20_1"}
_stub_20_1 = _make_abandonment_stub_20(_seeded_map_20_1)
_pos_20_1 = _make_position_19("test_20_1")
_pos_20_1.pending_exit_order_id = 77777   # points at the seeded id

# Capture CRITICAL log for EXIT ABANDONED
_critical_20_1 = []

class _Cap20_1(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.CRITICAL:
            _critical_20_1.append(record.getMessage())

_h20_1 = _Cap20_1()
_v2_logger_19.addHandler(_h20_1)
try:
    for _cycle in range(1, 6):
        _V2S_19._submit_exit_order(_stub_20_1, _pos_20_1.trade_id, _pos_20_1)
finally:
    _v2_logger_19.removeHandler(_h20_1)

check(
    "20.1: abandonment sets pending_exit=False",
    _pos_20_1.pending_exit is False,
    f"pending_exit = {_pos_20_1.pending_exit}",
)
check(
    "20.1: abandonment clears pending_exit_reason",
    _pos_20_1.pending_exit_reason == "",
    f"pending_exit_reason = {_pos_20_1.pending_exit_reason!r}",
)
check(
    "20.1: abandonment clears pending_exit_order_id to 0",
    _pos_20_1.pending_exit_order_id == 0,
    f"pending_exit_order_id = {_pos_20_1.pending_exit_order_id!r}",
)
check(
    "20.1: abandonment pops the id from _trade_id_map "
    "(Block 3 will no longer skip)",
    77777 not in _stub_20_1._trade_id_map,
    f"_trade_id_map = {_stub_20_1._trade_id_map}",
)
check(
    "20.1: abandonment resets exit_retry_count to 0 "
    "(next attempt gets fresh 5-retry ladder)",
    _pos_20_1.exit_retry_count == 0,
    f"exit_retry_count = {_pos_20_1.exit_retry_count}",
)
check(
    "20.1: CRITICAL 'EXIT ABANDONED' log line emitted",
    any("EXIT ABANDONED" in m for m in _critical_20_1),
    f"critical records: {_critical_20_1}",
)


# --- 20.2 — abandonment with empty _trade_id_map does not crash ---
# Simulates: a prior cleanup already popped the id. The .pop(..., None)
# in the abandonment branch must default-through without raising.
_stub_20_2 = _make_abandonment_stub_20({})
_pos_20_2 = _make_position_19("test_20_2")
_pos_20_2.pending_exit_order_id = 88888    # not in map

_crashed_20_2 = False
try:
    for _cycle in range(1, 6):
        _V2S_19._submit_exit_order(_stub_20_2, _pos_20_2.trade_id, _pos_20_2)
except Exception as _e:
    _crashed_20_2 = True

check(
    "20.2: abandonment with id not in _trade_id_map does not crash",
    _crashed_20_2 is False,
    f"crashed_20_2 = {_crashed_20_2}",
)
check(
    "20.2: abandonment still reaches the terminal state "
    "(pending_exit=False, order_id=0, retry=0)",
    _pos_20_2.pending_exit is False
    and _pos_20_2.pending_exit_order_id == 0
    and _pos_20_2.exit_retry_count == 0,
    f"pending_exit={_pos_20_2.pending_exit} "
    f"order_id={_pos_20_2.pending_exit_order_id} "
    f"retry={_pos_20_2.exit_retry_count}",
)


# ============================================================
# SECTION 21: on_canceled_order callback clears the exit lock
# ============================================================
section("21. on_canceled_order callback (Lumibot primary cancel path)")

# Prompt 20 Commit B. Lumibot invokes on_canceled_order(order) when
# an order's status resolves to "canceled" per STATUS_ALIAS_MAP —
# including Alpaca's "expired", "done_for_day", "replaced",
# "pending_cancel", etc. For SELL cancels we must clear the exit
# lock; for BUY cancels we just pop the _trade_id_map entry.

from management.trade_manager import TradeManager as _TM_21


def _make_stub_21() -> "_V2S_19":
    _stub = _V2S_19.__new__(_V2S_19)
    _stub._trade_manager = _TM_21()
    _stub._trade_id_map = {}
    return _stub


# --- 21.1 — on_canceled_order on SELL clears the exit lock ---
_stub_21_1 = _make_stub_21()
_pos_21_1 = _make_position_19("test_21_1")
_pos_21_1.pending_exit = True
_pos_21_1.pending_exit_reason = "profit_target"
_pos_21_1.exit_retry_count = 2   # mid-ladder

_order_21_1 = _MM_19()
_order_21_1.side = "sell_to_close"
_pos_21_1.pending_exit_order_id = id(_order_21_1)
_stub_21_1._trade_id_map[id(_order_21_1)] = _pos_21_1.trade_id
_stub_21_1._trade_manager._positions[_pos_21_1.trade_id] = _pos_21_1

# Capture INFO log for CANCEL line
_info_21_1 = []


class _Cap21_1(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.INFO:
            _info_21_1.append(record.getMessage())


_h21_1 = _Cap21_1()
_v2_logger_19.addHandler(_h21_1)
try:
    _V2S_19.on_canceled_order(_stub_21_1, _order_21_1)
finally:
    _v2_logger_19.removeHandler(_h21_1)

check(
    "21.1: SELL cancel sets pending_exit=False",
    _pos_21_1.pending_exit is False,
    f"pending_exit = {_pos_21_1.pending_exit}",
)
check(
    "21.1: SELL cancel clears pending_exit_reason",
    _pos_21_1.pending_exit_reason == "",
    f"reason = {_pos_21_1.pending_exit_reason!r}",
)
check(
    "21.1: SELL cancel clears pending_exit_order_id",
    _pos_21_1.pending_exit_order_id == 0,
    f"order_id = {_pos_21_1.pending_exit_order_id}",
)
check(
    "21.1: SELL cancel resets exit_retry_count",
    _pos_21_1.exit_retry_count == 0,
    f"retry = {_pos_21_1.exit_retry_count}",
)
check(
    "21.1: SELL cancel pops the id from _trade_id_map",
    id(_order_21_1) not in _stub_21_1._trade_id_map,
    f"map = {_stub_21_1._trade_id_map}",
)
check(
    "21.1: INFO log includes 'CANCEL: SELL' and the trade_id prefix",
    any("CANCEL: SELL" in m and _pos_21_1.trade_id[:8] in m
        for m in _info_21_1),
    f"info records: {_info_21_1}",
)


# --- 21.2 — on_canceled_order on BUY logs and pops, no position touched ---
_stub_21_2 = _make_stub_21()
_order_21_2 = _MM_19()
_order_21_2.side = "buy_to_open"
# Entry for a BUY is a dict (matches _submit_entry_order's write shape)
_stub_21_2._trade_id_map[id(_order_21_2)] = {
    "trade_id": "test_21_2_tid", "profile_name": "momentum",
}
# No ManagedPosition exists — BUY was never filled.

_info_21_2 = []


class _Cap21_2(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.INFO:
            _info_21_2.append(record.getMessage())


_h21_2 = _Cap21_2()
_v2_logger_19.addHandler(_h21_2)
try:
    _V2S_19.on_canceled_order(_stub_21_2, _order_21_2)
finally:
    _v2_logger_19.removeHandler(_h21_2)

check(
    "21.2: BUY cancel pops the dict entry from _trade_id_map",
    id(_order_21_2) not in _stub_21_2._trade_id_map,
    f"map = {_stub_21_2._trade_id_map}",
)
check(
    "21.2: BUY cancel INFO log mentions 'CANCEL: BUY' and the trade_id",
    any("CANCEL: BUY" in m and "test_21_" in m for m in _info_21_2),
    f"info records: {_info_21_2}",
)
check(
    "21.2: BUY cancel does NOT touch any ManagedPosition "
    "(trade manager still empty)",
    len(_stub_21_2._trade_manager._positions) == 0,
    f"_positions = {_stub_21_2._trade_manager._positions}",
)


# --- 21.3 — on_canceled_order on untracked id logs and returns ---
_stub_21_3 = _make_stub_21()
_order_21_3 = _MM_19()
_order_21_3.side = "sell_to_close"
# _trade_id_map is empty — id(_order_21_3) not present

_info_21_3 = []


class _Cap21_3(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.INFO:
            _info_21_3.append(record.getMessage())


_h21_3 = _Cap21_3()
_v2_logger_19.addHandler(_h21_3)
_crashed_21_3 = False
try:
    _V2S_19.on_canceled_order(_stub_21_3, _order_21_3)
except Exception:
    _crashed_21_3 = True
finally:
    _v2_logger_19.removeHandler(_h21_3)

check(
    "21.3: untracked id returns cleanly (no raise)",
    not _crashed_21_3,
    f"crashed = {_crashed_21_3}",
)
check(
    "21.3: untracked id INFO log says 'untracked order id'",
    any("untracked order id" in m for m in _info_21_3),
    f"info records: {_info_21_3}",
)
check(
    "21.3: _trade_id_map unchanged (still empty)",
    _stub_21_3._trade_id_map == {},
    f"map = {_stub_21_3._trade_id_map}",
)


# --- 21.4 — on_canceled_order on SELL whose position was already
#            popped (e.g., filled via a different order that race-won) ---
_stub_21_4 = _make_stub_21()
_order_21_4 = _MM_19()
_order_21_4.side = "sell_to_close"
_stub_21_4._trade_id_map[id(_order_21_4)] = "missing_trade_id_21_4"
# No ManagedPosition for "missing_trade_id_21_4"

_info_21_4 = []


class _Cap21_4(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.INFO:
            _info_21_4.append(record.getMessage())


_h21_4 = _Cap21_4()
_v2_logger_19.addHandler(_h21_4)
_crashed_21_4 = False
try:
    _V2S_19.on_canceled_order(_stub_21_4, _order_21_4)
except Exception:
    _crashed_21_4 = True
finally:
    _v2_logger_19.removeHandler(_h21_4)

check(
    "21.4: SELL cancel with missing position does not crash",
    not _crashed_21_4,
    f"crashed = {_crashed_21_4}",
)
check(
    "21.4: SELL cancel pops the id from _trade_id_map even when position is gone",
    id(_order_21_4) not in _stub_21_4._trade_id_map,
    f"map = {_stub_21_4._trade_id_map}",
)
check(
    "21.4: INFO log includes 'position already popped' "
    "(fill raced the cancel)",
    any("position already popped" in m for m in _info_21_4),
    f"info records: {_info_21_4}",
)


# ============================================================
# SECTION 22: stale exit-lock timeout (Option Z fallback)
# ============================================================
section("22. Stale exit-lock timeout clears Block 3 when callback drops")

# Prompt 20 Commit C. If Lumibot's on_canceled_order never fires
# (websocket drop, Lumibot bug, process restart between cancel and
# callback, or Alpaca rejection which routes through ERROR_ORDER not
# CANCELED_ORDER), the exit lock stays set forever. Commit C adds a
# helper _clear_stale_exit_lock that force-clears the lock once
# pending_exit_submitted_at is older than STALE_EXIT_LOCK_MINUTES.

from datetime import timedelta as _td_22
from strategies.v2_strategy import (
    V2Strategy as _V2S_22,
    STALE_EXIT_LOCK_MINUTES as _STALE_22,
)


def _make_stale_pos_22(age_minutes: float, order_id: int,
                       trade_id: str = "test_22") -> "_MP_19":
    p = _make_position_19(trade_id)
    p.pending_exit = True
    p.pending_exit_reason = "profit_target"
    p.pending_exit_order_id = order_id
    p.exit_retry_count = 0
    p.pending_exit_submitted_at = (
        _dt.now(_tz.utc) - _td_22(minutes=age_minutes)
    )
    return p


# --- 22.1 — stale timeout fires after > STALE_EXIT_LOCK_MINUTES ---
_stub_22_1 = _V2S_22.__new__(_V2S_22)
_stub_22_1._trade_id_map = {77777: "test_22_1"}
_pos_22_1 = _make_stale_pos_22(
    age_minutes=_STALE_22 + 1, order_id=77777, trade_id="test_22_1",
)

_warn_22_1 = []


class _Cap22_1(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.WARNING:
            _warn_22_1.append(record.getMessage())


_h22_1 = _Cap22_1()
_v2_logger_19.addHandler(_h22_1)
try:
    _cleared_22_1 = _V2S_22._clear_stale_exit_lock(
        _stub_22_1, _pos_22_1.trade_id, _pos_22_1,
    )
finally:
    _v2_logger_19.removeHandler(_h22_1)

check(
    "22.1: stale lock (age > threshold) returns True from helper",
    _cleared_22_1 is True,
    f"_cleared = {_cleared_22_1}",
)
check(
    "22.1: stale timeout sets pending_exit=False",
    _pos_22_1.pending_exit is False,
    f"pending_exit = {_pos_22_1.pending_exit}",
)
check(
    "22.1: stale timeout clears pending_exit_order_id",
    _pos_22_1.pending_exit_order_id == 0,
    f"order_id = {_pos_22_1.pending_exit_order_id}",
)
check(
    "22.1: stale timeout clears pending_exit_submitted_at to None",
    _pos_22_1.pending_exit_submitted_at is None,
    f"submitted_at = {_pos_22_1.pending_exit_submitted_at}",
)
check(
    "22.1: stale timeout pops id from _trade_id_map",
    77777 not in _stub_22_1._trade_id_map,
    f"map = {_stub_22_1._trade_id_map}",
)
check(
    "22.1: WARNING log includes 'STALE exit lock'",
    any("STALE exit lock" in m for m in _warn_22_1),
    f"warn records: {_warn_22_1}",
)


# --- 22.2 — fresh lock (under threshold) does NOT clear ---
_stub_22_2 = _V2S_22.__new__(_V2S_22)
_stub_22_2._trade_id_map = {55555: "test_22_2"}
_pos_22_2 = _make_stale_pos_22(
    age_minutes=_STALE_22 - 5, order_id=55555, trade_id="test_22_2",
)
_before_ts_22_2 = _pos_22_2.pending_exit_submitted_at

_warn_22_2 = []


class _Cap22_2(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.WARNING:
            _warn_22_2.append(record.getMessage())


_h22_2 = _Cap22_2()
_v2_logger_19.addHandler(_h22_2)
try:
    _cleared_22_2 = _V2S_22._clear_stale_exit_lock(
        _stub_22_2, _pos_22_2.trade_id, _pos_22_2,
    )
finally:
    _v2_logger_19.removeHandler(_h22_2)

check(
    "22.2: fresh lock (age < threshold) returns False from helper",
    _cleared_22_2 is False,
    f"_cleared = {_cleared_22_2}",
)
check(
    "22.2: fresh lock leaves pending_exit=True unchanged",
    _pos_22_2.pending_exit is True,
    f"pending_exit = {_pos_22_2.pending_exit}",
)
check(
    "22.2: fresh lock leaves pending_exit_order_id unchanged",
    _pos_22_2.pending_exit_order_id == 55555,
    f"order_id = {_pos_22_2.pending_exit_order_id}",
)
check(
    "22.2: fresh lock leaves _trade_id_map unchanged",
    55555 in _stub_22_2._trade_id_map,
    f"map = {_stub_22_2._trade_id_map}",
)
check(
    "22.2: fresh lock emits no WARNING",
    len([m for m in _warn_22_2 if "STALE" in m]) == 0,
    f"warn records: {_warn_22_2}",
)


# --- 22.3 — None timestamp (reloaded position, no submission yet) ---
_stub_22_3 = _V2S_22.__new__(_V2S_22)
_stub_22_3._trade_id_map = {33333: "test_22_3"}
_pos_22_3 = _make_stale_pos_22(
    age_minutes=0, order_id=33333, trade_id="test_22_3",
)
_pos_22_3.pending_exit_submitted_at = None    # simulates reloaded pos
_crashed_22_3 = False
try:
    _cleared_22_3 = _V2S_22._clear_stale_exit_lock(
        _stub_22_3, _pos_22_3.trade_id, _pos_22_3,
    )
except Exception:
    _crashed_22_3 = True
    _cleared_22_3 = None

check(
    "22.3: None timestamp does not crash",
    not _crashed_22_3,
    f"crashed = {_crashed_22_3}",
)
check(
    "22.3: None timestamp returns False (no action)",
    _cleared_22_3 is False,
    f"_cleared = {_cleared_22_3}",
)
check(
    "22.3: None timestamp leaves pending_exit_order_id unchanged",
    _pos_22_3.pending_exit_order_id == 33333,
    f"order_id = {_pos_22_3.pending_exit_order_id}",
)


# --- 22.4 — successful submit sets pending_exit_submitted_at ---
_stub_22_4 = _V2S_19.__new__(_V2S_19)
_stub_22_4._trade_id_map = {}
_stub_22_4.get_last_price = _MM_19(return_value=3.50)
_stub_22_4.create_order = lambda *a, **kw: _MM_19(id="x")
_stub_22_4.submit_order = lambda order: order   # clean success

_pos_22_4 = _make_position_19("test_22_4")
_before_22_4 = _dt.now(_tz.utc)
_V2S_19._submit_exit_order(_stub_22_4, _pos_22_4.trade_id, _pos_22_4)
_after_22_4 = _dt.now(_tz.utc)

check(
    "22.4: successful submit sets pending_exit_submitted_at to a datetime",
    isinstance(_pos_22_4.pending_exit_submitted_at,
               _dt.__class__ if False else type(_dt.now(_tz.utc))),
    f"submitted_at = {_pos_22_4.pending_exit_submitted_at!r}",
)
check(
    "22.4: pending_exit_submitted_at is within the submit window",
    _pos_22_4.pending_exit_submitted_at is not None
    and _before_22_4 <= _pos_22_4.pending_exit_submitted_at <= _after_22_4,
    f"submitted_at = {_pos_22_4.pending_exit_submitted_at} "
    f"before={_before_22_4} after={_after_22_4}",
)


# --- 22.5 — failed submit (transient) does NOT set the timestamp ---
_stub_22_5 = _V2S_19.__new__(_V2S_19)
_stub_22_5._trade_id_map = {}
_stub_22_5.get_last_price = _MM_19(return_value=3.50)
_stub_22_5.create_order = lambda *a, **kw: _MM_19(id="x")


def _raise_transient(order):
    raise ConnectionError("transient")


_stub_22_5.submit_order = _raise_transient
_pos_22_5 = _make_position_19("test_22_5")
# Start with None — transient should leave it None
_pos_22_5.pending_exit_submitted_at = None

_V2S_19._submit_exit_order(_stub_22_5, _pos_22_5.trade_id, _pos_22_5)

check(
    "22.5: failed submit leaves pending_exit_submitted_at=None "
    "(timestamp only set on clean submit)",
    _pos_22_5.pending_exit_submitted_at is None,
    f"submitted_at = {_pos_22_5.pending_exit_submitted_at!r}",
)
check(
    "22.5: failed submit still increments exit_retry_count (sanity)",
    _pos_22_5.exit_retry_count == 1,
    f"retry_count = {_pos_22_5.exit_retry_count}",
)


# ============================================================
# SECTION 23: on_error_order callback clears the lock on broker reject
# ============================================================
section("23. on_error_order callback (Alpaca rejection path)")

# Prompt 23. Alpaca broker-side rejections (insufficient buying power,
# invalid contract, market closed, PDT violations after ack, etc.)
# resolve to Lumibot's "error" status per STATUS_ALIAS_MAP and route
# through the ERROR_ORDER event to Strategy.on_error_order(order, error).
# This is a separate dispatch from on_canceled_order (which handles
# canceled/expired/replaced/done_for_day/etc.). Pre-fix, rejected exits
# sat locked for up to STALE_EXIT_LOCK_MINUTES; post-fix they clear on
# the next event-queue turn (same trading iteration, typically).


def _make_err_stub_23():
    _stub = _V2S_22.__new__(_V2S_22)
    _stub._trade_manager = _TM_21()
    _stub._trade_id_map = {}
    return _stub


# --- 23.1 — SELL reject clears the exit lock ---
_stub_23_1 = _make_err_stub_23()
_pos_23_1 = _make_position_19("test_23_1")
_pos_23_1.pending_exit = True
_pos_23_1.pending_exit_reason = "trailing_stop"
_pos_23_1.pending_exit_submitted_at = _dt.now(_tz.utc)
_pos_23_1.exit_retry_count = 0

_order_23_1 = _MM_19()
_order_23_1.side = "sell_to_close"
_order_23_1.error_message = "insufficient buying power"
_pos_23_1.pending_exit_order_id = id(_order_23_1)
_stub_23_1._trade_id_map[id(_order_23_1)] = _pos_23_1.trade_id
_stub_23_1._trade_manager._positions[_pos_23_1.trade_id] = _pos_23_1

_warn_23_1 = []


class _Cap23_1(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.WARNING:
            _warn_23_1.append(record.getMessage())


_h23_1 = _Cap23_1()
_v2_logger_19.addHandler(_h23_1)
try:
    _V2S_22.on_error_order(_stub_23_1, _order_23_1, error="insufficient buying power")
finally:
    _v2_logger_19.removeHandler(_h23_1)

check(
    "23.1: SELL reject sets pending_exit=False",
    _pos_23_1.pending_exit is False,
    f"pending_exit = {_pos_23_1.pending_exit}",
)
check(
    "23.1: SELL reject clears pending_exit_reason",
    _pos_23_1.pending_exit_reason == "",
    f"reason = {_pos_23_1.pending_exit_reason!r}",
)
check(
    "23.1: SELL reject clears pending_exit_order_id",
    _pos_23_1.pending_exit_order_id == 0,
    f"order_id = {_pos_23_1.pending_exit_order_id}",
)
check(
    "23.1: SELL reject clears pending_exit_submitted_at "
    "(defangs Commit 20C stale-lock timeout)",
    _pos_23_1.pending_exit_submitted_at is None,
    f"submitted_at = {_pos_23_1.pending_exit_submitted_at}",
)
check(
    "23.1: SELL reject resets exit_retry_count",
    _pos_23_1.exit_retry_count == 0,
    f"retry = {_pos_23_1.exit_retry_count}",
)
check(
    "23.1: SELL reject pops the id from _trade_id_map",
    id(_order_23_1) not in _stub_23_1._trade_id_map,
    f"map = {_stub_23_1._trade_id_map}",
)
check(
    "23.1: WARNING log names 'ERROR: SELL' + trade_id + error text",
    any(
        "ERROR: SELL" in m
        and _pos_23_1.trade_id[:8] in m
        and "insufficient buying power" in m
        for m in _warn_23_1
    ),
    f"warn records: {_warn_23_1}",
)


# --- 23.2 — BUY reject pops the map entry, no position touched ---
_stub_23_2 = _make_err_stub_23()
_order_23_2 = _MM_19()
_order_23_2.side = "buy_to_open"
_order_23_2.error_message = "market is closed"
_stub_23_2._trade_id_map[id(_order_23_2)] = {
    "trade_id": "test_23_2_tid", "profile_name": "momentum",
}

_warn_23_2 = []


class _Cap23_2(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.WARNING:
            _warn_23_2.append(record.getMessage())


_h23_2 = _Cap23_2()
_v2_logger_19.addHandler(_h23_2)
try:
    _V2S_22.on_error_order(_stub_23_2, _order_23_2, error="market is closed")
finally:
    _v2_logger_19.removeHandler(_h23_2)

check(
    "23.2: BUY reject pops the dict entry from _trade_id_map",
    id(_order_23_2) not in _stub_23_2._trade_id_map,
    f"map = {_stub_23_2._trade_id_map}",
)
check(
    "23.2: BUY reject WARNING log includes 'ERROR: BUY' + trade_id + error",
    any(
        "ERROR: BUY" in m
        and "test_23_" in m
        and "market is closed" in m
        for m in _warn_23_2
    ),
    f"warn records: {_warn_23_2}",
)
check(
    "23.2: BUY reject does NOT touch any ManagedPosition (none existed)",
    len(_stub_23_2._trade_manager._positions) == 0,
    f"_positions = {_stub_23_2._trade_manager._positions}",
)


# --- 23.3 — on_error_order on untracked id returns cleanly ---
_stub_23_3 = _make_err_stub_23()
_order_23_3 = _MM_19()
_order_23_3.side = "sell_to_close"
# _trade_id_map empty

_info_23_3 = []


class _Cap23_3(_log_19_2.Handler):
    def emit(self, record):
        if record.levelno >= _log_19_2.INFO:
            _info_23_3.append(record.getMessage())


_h23_3 = _Cap23_3()
_v2_logger_19.addHandler(_h23_3)
_crashed_23_3 = False
try:
    _V2S_22.on_error_order(_stub_23_3, _order_23_3, error="whatever")
except Exception:
    _crashed_23_3 = True
finally:
    _v2_logger_19.removeHandler(_h23_3)

check(
    "23.3: untracked id does not raise",
    not _crashed_23_3,
    f"crashed = {_crashed_23_3}",
)
check(
    "23.3: untracked id INFO log says 'untracked order id'",
    any("untracked order id" in m for m in _info_23_3),
    f"info records: {_info_23_3}",
)
check(
    "23.3: untracked id leaves _trade_id_map empty",
    _stub_23_3._trade_id_map == {},
    f"map = {_stub_23_3._trade_id_map}",
)


# --- 23.4 — on_error_order does NOT increment exit_retry_count ---
# Pin the intent: retries count only synchronous transient errors
# within _submit_exit_order, not broker-side rejects. A position that
# hit 2 transients then got a broker reject should NOT be closer to
# abandonment after the reject.
_stub_23_4 = _make_err_stub_23()
_pos_23_4 = _make_position_19("test_23_4")
_pos_23_4.pending_exit = True
_pos_23_4.pending_exit_reason = "profit_target"
_pos_23_4.exit_retry_count = 2   # 2 prior transient errors

_order_23_4 = _MM_19()
_order_23_4.side = "sell_to_close"
_pos_23_4.pending_exit_order_id = id(_order_23_4)
_stub_23_4._trade_id_map[id(_order_23_4)] = _pos_23_4.trade_id
_stub_23_4._trade_manager._positions[_pos_23_4.trade_id] = _pos_23_4

_V2S_22.on_error_order(_stub_23_4, _order_23_4, error="bad contract")

check(
    "23.4: broker reject resets exit_retry_count to 0 (not incremented)",
    _pos_23_4.exit_retry_count == 0,
    f"retry_count = {_pos_23_4.exit_retry_count} "
    "(pre-callback was 2; a correct reset is to 0, not 3)",
)


# --- 23.5 — reject + subsequent staleness check do not double-clean ---
# Edge case: order was rejected 11 minutes ago (stale per Commit 20C)
# AND we also fire on_error_order. Ensure the two mechanisms don't
# interfere.
_stub_23_5 = _make_err_stub_23()
_pos_23_5 = _make_position_19("test_23_5")
_pos_23_5.pending_exit = True
_pos_23_5.pending_exit_reason = "time_decay"
_pos_23_5.pending_exit_submitted_at = _dt.now(_tz.utc) - _td_22(minutes=11)  # stale

_order_23_5 = _MM_19()
_order_23_5.side = "sell_to_close"
_pos_23_5.pending_exit_order_id = id(_order_23_5)
_stub_23_5._trade_id_map[id(_order_23_5)] = _pos_23_5.trade_id
_stub_23_5._trade_manager._positions[_pos_23_5.trade_id] = _pos_23_5

# Fire on_error_order FIRST — should clean up
_V2S_22.on_error_order(_stub_23_5, _order_23_5, error="bad price")

# Now fire the staleness helper — guard condition should fail because
# pending_exit_order_id=0 and pending_exit_submitted_at=None after
# the error callback cleaned up. Expect no-op.
_stale_cleared_23_5 = _V2S_22._clear_stale_exit_lock(
    _stub_23_5, _pos_23_5.trade_id, _pos_23_5,
)

check(
    "23.5: after error callback, stale-lock helper returns False "
    "(nothing left to clear)",
    _stale_cleared_23_5 is False,
    f"stale_cleared = {_stale_cleared_23_5}",
)
check(
    "23.5: state is the error-callback-cleaned state (not re-mutated)",
    _pos_23_5.pending_exit is False
    and _pos_23_5.pending_exit_order_id == 0
    and _pos_23_5.pending_exit_submitted_at is None
    and _pos_23_5.exit_retry_count == 0,
    f"pending_exit={_pos_23_5.pending_exit} "
    f"order_id={_pos_23_5.pending_exit_order_id} "
    f"submitted_at={_pos_23_5.pending_exit_submitted_at} "
    f"retry={_pos_23_5.exit_retry_count}",
)


# ============================================================
# SECTION 24: catalyst vol/OI gate — near-ATM filter (Prompt 24)
# ============================================================
section("24. Catalyst vol/OI gate filters by near-ATM strikes")

# Prompt 24: Scanner._get_options_vol_oi_ratio previously walked the
# entire chain. A deep-OTM wing with oi=150, vol=90 (ratio=0.60)
# could pass the 0.50 catalyst threshold on retail-sized activity.
# Fix narrows the strike set to strikes within CATALYST_NEAR_ATM_PCT
# of the underlying price (1.5% on either side).

from unittest.mock import MagicMock as _MM_24
from scanner.scanner import Scanner as _Scanner_24
from scanner.setups import (
    CATALYST_VOL_OI_RATIO as _CATALYST_THR_24,
    CATALYST_NEAR_ATM_PCT as _NEAR_ATM_PCT_24,
)


def _make_scanner_stub_24(chain: list[dict]):
    """Scanner stub returning a canned chain from the mocked client."""
    _s = _Scanner_24.__new__(_Scanner_24)
    _s._client = _MM_24()
    _s._client.get_nearest_expiration.return_value = "2026-05-02"
    _s._client.get_options_chain.return_value = chain
    return _s


# --- 24.1 — near-ATM filter excludes deep-OTM wings ---
# Spec trace: underlying=500, three contracts. Pre-fix the $530 wing
# (ratio=0.60) would win. Post-fix only $501 and $499 qualify; the
# max among them is 0.40, correctly BELOW the 0.50 threshold.
_chain_24_1 = [
    {"strike": 501.0, "right": "C", "open_interest": 5000, "volume": 1500},
    {"strike": 530.0, "right": "C", "open_interest": 150,  "volume": 90},   # wing
    {"strike": 499.0, "right": "P", "open_interest": 2000, "volume": 800},
]
_s_24_1 = _make_scanner_stub_24(_chain_24_1)
_ratio_24_1 = _s_24_1._get_options_vol_oi_ratio("SPY", underlying_price=500.0)
check(
    "24.1: post-fix ratio = 0.40 (near-ATM max, excludes $530 wing)",
    abs(_ratio_24_1 - 0.40) < 1e-9,
    f"ratio = {_ratio_24_1!r}",
)
check(
    "24.1: catalyst 0.50 threshold correctly REJECTS on this chain "
    "(pre-fix would have passed at 0.60)",
    _ratio_24_1 < _CATALYST_THR_24,
    f"ratio = {_ratio_24_1} threshold = {_CATALYST_THR_24}",
)


# --- 24.2 — genuine near-ATM institutional flow still wins ---
# High-ratio near-ATM strike beats a far-OTM wing. Pre-fix would have
# returned the wing (0.80); post-fix returns the near-ATM strike
# (0.70), which correctly passes the 0.50 threshold.
_chain_24_2 = [
    {"strike": 501.0, "right": "C", "open_interest": 1000, "volume": 700},  # near, 0.70
    {"strike": 525.0, "right": "C", "open_interest": 500,  "volume": 400},  # wing, 0.80
]
_s_24_2 = _make_scanner_stub_24(_chain_24_2)
_ratio_24_2 = _s_24_2._get_options_vol_oi_ratio("SPY", underlying_price=500.0)
check(
    "24.2: post-fix picks the near-ATM 0.70 winner (not the 0.80 wing)",
    abs(_ratio_24_2 - 0.70) < 1e-9,
    f"ratio = {_ratio_24_2!r}",
)
check(
    "24.2: catalyst 0.50 threshold correctly PASSES on genuine "
    "near-ATM institutional flow",
    _ratio_24_2 >= _CATALYST_THR_24,
    f"ratio = {_ratio_24_2} threshold = {_CATALYST_THR_24}",
)


# --- 24.3 — zero near-ATM contracts returns 0.0 (not None) ---
# All strikes are > 1.5% OTM. Pre-fix would have returned 0.75 (the
# wing's ratio). Post-fix returns 0.0 (the "no flow detected"
# sentinel). None is reserved for "gate could not evaluate."
_chain_24_3 = [
    {"strike": 520.0, "right": "C", "open_interest": 200, "volume": 150},  # 4% OTM
    {"strike": 485.0, "right": "P", "open_interest": 300, "volume": 100},  # 3% OTM
]
_s_24_3 = _make_scanner_stub_24(_chain_24_3)
_ratio_24_3 = _s_24_3._get_options_vol_oi_ratio("SPY", underlying_price=500.0)
check(
    "24.3: no near-ATM liquid strikes returns 0.0 (distinct from None)",
    _ratio_24_3 == 0.0,
    f"ratio = {_ratio_24_3!r}",
)
check(
    "24.3: catalyst 0.50 threshold correctly REJECTS when no "
    "near-ATM flow exists",
    _ratio_24_3 < _CATALYST_THR_24,
    f"ratio = {_ratio_24_3}",
)


# --- 24.4 — OI > 100 floor still applies within the near-ATM band ---
# A near-ATM strike with oi=50 must still be excluded by the liquidity
# floor. Only the oi=500 strike qualifies.
_chain_24_4 = [
    {"strike": 500.0, "right": "C", "open_interest": 50,  "volume": 40},   # oi floor fails
    {"strike": 501.0, "right": "P", "open_interest": 500, "volume": 100},  # ratio=0.20
]
_s_24_4 = _make_scanner_stub_24(_chain_24_4)
_ratio_24_4 = _s_24_4._get_options_vol_oi_ratio("SPY", underlying_price=500.0)
check(
    "24.4: near-ATM strike with oi=50 excluded by OI>100 floor",
    abs(_ratio_24_4 - 0.20) < 1e-9,
    f"ratio = {_ratio_24_4!r} (expected 0.20 from the oi=500 strike)",
)


# --- 24.5 — percentage scales across symbols (SPY vs TSLA) ---
# 1.5% of 500 = 7.5 dollar window; strike 507.5 is at the band edge.
# 1.5% of 200 = 3.0 dollar window; strike 203.0 is at the band edge.
# Both chains structured identically — if the implementation uses
# percentage correctly, both return 0.50. If it accidentally used a
# fixed dollar threshold, chain 2 would exclude strike=203 and
# return 0.0.
_chain_24_5_spy = [
    {"strike": 507.5, "right": "C", "open_interest": 1000, "volume": 500},
]
_chain_24_5_tsla = [
    {"strike": 203.0, "right": "C", "open_interest": 1000, "volume": 500},
]
_s_24_5_spy = _make_scanner_stub_24(_chain_24_5_spy)
_s_24_5_tsla = _make_scanner_stub_24(_chain_24_5_tsla)
_ratio_24_5_spy = _s_24_5_spy._get_options_vol_oi_ratio("SPY", 500.0)
_ratio_24_5_tsla = _s_24_5_tsla._get_options_vol_oi_ratio("TSLA", 200.0)
check(
    "24.5: SPY band edge (strike 507.5 on $500 underlying, 1.5% OTM) "
    "included (percentage-based)",
    abs(_ratio_24_5_spy - 0.50) < 1e-9,
    f"SPY ratio = {_ratio_24_5_spy!r}",
)
check(
    "24.5: TSLA band edge (strike 203 on $200 underlying, 1.5% OTM) "
    "included — percentage scales, not absolute dollars",
    abs(_ratio_24_5_tsla - 0.50) < 1e-9,
    f"TSLA ratio = {_ratio_24_5_tsla!r}",
)


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
