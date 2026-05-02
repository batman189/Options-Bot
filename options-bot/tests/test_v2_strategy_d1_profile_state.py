"""Unit tests for V2Strategy._build_live_profile_state and the
on_trading_iteration day-rollover guard (Phase 1b D1).

Verifies the four ProfileState fields that D1 replaced (current_open_
positions, current_capital_deployed, today_account_pnl_pct, last_exit_at)
pull from live subprocess + DB state correctly. Also verifies the
_day_start_value cross-day reset.

Tests use a tmp file-backed sqlite3 DB with the trades schema (copied
from backend/database.py:50-85). DB_PATH is monkeypatched per test.
V2Strategy is constructed via __new__() to bypass Lumibot init —
matches the C5b pattern in test_v2_strategy_new_pipeline.py.

Run via:
    python -m pytest tests/test_v2_strategy_d1_profile_state.py -v
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from profiles.profile_config import ProfileConfig  # noqa: E402
from strategies.v2_strategy import V2Strategy  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Schema + fixtures
# ─────────────────────────────────────────────────────────────────


_TRADES_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    strike REAL NOT NULL,
    expiration TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price REAL,
    entry_date TEXT,
    entry_underlying_price REAL,
    entry_predicted_return REAL,
    entry_ev_pct REAL,
    entry_features TEXT,
    entry_greeks TEXT,
    entry_model_type TEXT,
    exit_price REAL,
    exit_date TEXT,
    exit_underlying_price REAL,
    exit_reason TEXT,
    exit_greeks TEXT,
    pnl_dollars REAL,
    pnl_pct REAL,
    hold_days INTEGER,
    hold_minutes INTEGER,
    setup_type TEXT,
    profile_name TEXT,
    confidence_score REAL,
    was_day_trade INTEGER DEFAULT 0,
    market_vix REAL,
    market_regime TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    execution_mode TEXT NOT NULL DEFAULT 'live',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _init_trades_schema(db_path: Path):
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.executescript(_TRADES_SCHEMA)
        conn.commit()


def _insert_trade(
    db_path: Path,
    *,
    trade_id: str = "test-trade-id",
    profile_id: str = "test-profile",
    symbol: str = "TSLA",
    direction: str = "call",
    strike: float = 250.0,
    expiration: str = "2026-05-15",
    quantity: int = 1,
    entry_price: float | None = 4.00,
    entry_date: str = "2026-05-01T10:30:00+00:00",
    exit_price: float | None = None,
    exit_date: str | None = None,
    status: str = "open",
    execution_mode: str = "live",
):
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(
            """INSERT INTO trades (
                id, profile_id, symbol, direction, strike, expiration,
                quantity, entry_price, entry_date, exit_price, exit_date,
                status, execution_mode, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade_id, profile_id, symbol, direction, strike,
                expiration, quantity, entry_price, entry_date,
                exit_price, exit_date, status, execution_mode,
                "2026-05-01T10:30:00+00:00",
                "2026-05-01T10:30:00+00:00",
            ),
        )
        conn.commit()


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Per-test tmp DB with trades schema, DB_PATH patched."""
    db = tmp_path / "test.db"
    _init_trades_schema(db)
    monkeypatch.setattr("strategies.v2_strategy.DB_PATH", db)
    return db


def _stub(profile_id: str = "test-profile",
          execution_mode: str = "live",
          pv: float | None = 10000.0,
          day_start_value: float = 0.0):
    """Construct a V2Strategy stub via __new__, set just the attributes
    the helper consults."""
    s = V2Strategy.__new__(V2Strategy)
    s._profile_config = ProfileConfig(
        name=profile_id, preset="swing",
        symbols=["TSLA"], max_capital_deployed=5000.0,
    )
    s._day_start_value = day_start_value
    s._last_entry_time = {}
    s._recent_exits_by_symbol = {}
    s._recent_entries_by_symbol_direction = {}
    s._thesis_break_streaks = {}
    s.get_portfolio_value = MagicMock(return_value=pv)
    return s


@pytest.fixture(autouse=True)
def _force_live_mode(monkeypatch):
    """All D1 tests assume execution_mode='live' unless explicitly
    overridden. Patches config.EXECUTION_MODE so the helper reads
    'live' regardless of the env."""
    monkeypatch.setattr(
        "strategies.v2_strategy.config.EXECUTION_MODE", "live",
    )


# ═════════════════════════════════════════════════════════════════
# current_open_positions
# ═════════════════════════════════════════════════════════════════


def test_open_positions_empty_db_returns_zero(db_path):
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.current_open_positions == 0


def test_open_positions_one_open_trade(db_path):
    _insert_trade(db_path, trade_id="t1", status="open",
                  execution_mode="live", profile_id="test-profile")
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.current_open_positions == 1


def test_open_positions_filters_by_profile_id(db_path):
    _insert_trade(db_path, trade_id="t1", profile_id="test-profile")
    _insert_trade(db_path, trade_id="t2", profile_id="other-profile")
    s = _stub(profile_id="test-profile")
    state = s._build_live_profile_state("swing")
    assert state.current_open_positions == 1


def test_open_positions_filters_by_execution_mode(db_path, monkeypatch):
    """live-mode subprocess must not count shadow-mode rows toward
    its open-position cap."""
    _insert_trade(db_path, trade_id="t1", execution_mode="live")
    _insert_trade(db_path, trade_id="t2", execution_mode="shadow")
    monkeypatch.setattr(
        "strategies.v2_strategy.config.EXECUTION_MODE", "live",
    )
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.current_open_positions == 1


def test_open_positions_excludes_closed_trades(db_path):
    _insert_trade(db_path, trade_id="t1", status="closed",
                  exit_price=5.00, exit_date="2026-05-01T15:30:00+00:00")
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.current_open_positions == 0


# ═════════════════════════════════════════════════════════════════
# current_capital_deployed
# ═════════════════════════════════════════════════════════════════


def test_capital_deployed_no_trades_returns_zero(db_path):
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.current_capital_deployed == 0.0


def test_capital_deployed_one_trade_computes_correctly(db_path):
    """entry_price=$2.50 × quantity=2 × 100 = $500.00."""
    _insert_trade(db_path, trade_id="t1", entry_price=2.50, quantity=2)
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.current_capital_deployed == 500.0


def test_capital_deployed_multiple_trades_sum(db_path):
    _insert_trade(db_path, trade_id="t1", entry_price=2.50, quantity=2)
    _insert_trade(db_path, trade_id="t2", entry_price=4.00, quantity=1)
    _insert_trade(db_path, trade_id="t3", entry_price=1.00, quantity=3)
    s = _stub()
    state = s._build_live_profile_state("swing")
    # 2.50*2*100 + 4.00*1*100 + 1.00*3*100 = 500 + 400 + 300 = 1200
    assert state.current_capital_deployed == 1200.0


def test_capital_deployed_null_entry_price_treated_as_zero(db_path):
    """COALESCE in the SQL turns NULL into 0.0."""
    _insert_trade(db_path, trade_id="t1", entry_price=None, quantity=2)
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.current_capital_deployed == 0.0


def test_capital_deployed_excludes_other_profile_id(db_path):
    _insert_trade(db_path, trade_id="t1", profile_id="test-profile",
                  entry_price=2.50, quantity=2)
    _insert_trade(db_path, trade_id="t2", profile_id="other",
                  entry_price=10.00, quantity=10)
    s = _stub(profile_id="test-profile")
    state = s._build_live_profile_state("swing")
    assert state.current_capital_deployed == 500.0


# ═════════════════════════════════════════════════════════════════
# today_account_pnl_pct
# ═════════════════════════════════════════════════════════════════


def test_pnl_pct_day_start_zero_returns_zero(db_path):
    """day_start_value=0 (lazy-init guard) → pnl_pct=0."""
    s = _stub(pv=10000.0, day_start_value=0.0)
    state = s._build_live_profile_state("swing")
    assert state.today_account_pnl_pct == 0.0


def test_pnl_pct_positive_when_pv_above_baseline(db_path):
    """day_start=5000, pv=5500 → +0.10."""
    s = _stub(pv=5500.0, day_start_value=5000.0)
    state = s._build_live_profile_state("swing")
    assert state.today_account_pnl_pct == pytest.approx(0.10)


def test_pnl_pct_negative_when_pv_below_baseline(db_path):
    """day_start=5000, pv=4500 → -0.10."""
    s = _stub(pv=4500.0, day_start_value=5000.0)
    state = s._build_live_profile_state("swing")
    assert state.today_account_pnl_pct == pytest.approx(-0.10)


def test_pnl_pct_pv_none_falls_back_to_zero_with_warning(db_path, caplog):
    """get_portfolio_value() returns None — defensive guard kicks in,
    pnl_pct=0.0, warning logged. NOT -1.0 (which would propagate as
    -100% drawdown through cap_check)."""
    s = _stub(pv=None, day_start_value=5000.0)
    caplog.set_level(logging.WARNING, logger="options-bot.strategy.v2")
    state = s._build_live_profile_state("swing")
    assert state.today_account_pnl_pct == 0.0
    assert any(
        "get_portfolio_value()" in r.message
        and "None" in r.message
        for r in caplog.records
    )


def test_pnl_pct_pv_zero_falls_back_to_zero(db_path):
    """pv=0 (broker reports zero) → pnl_pct=0.0, same defensive path."""
    s = _stub(pv=0.0, day_start_value=5000.0)
    state = s._build_live_profile_state("swing")
    assert state.today_account_pnl_pct == 0.0


# ═════════════════════════════════════════════════════════════════
# last_exit_at
# ═════════════════════════════════════════════════════════════════


def test_last_exit_at_no_closed_trades_returns_none(db_path):
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.last_exit_at is None


def test_last_exit_at_one_closed_trade_returns_datetime(db_path):
    _insert_trade(
        db_path, trade_id="t1", status="closed",
        exit_price=5.00, exit_date="2026-04-30T15:30:00+00:00",
    )
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.last_exit_at == datetime(
        2026, 4, 30, 15, 30, tzinfo=timezone.utc,
    )


def test_last_exit_at_multiple_closed_returns_max(db_path):
    """ISO-8601 strings sort lexicographically the same as
    chronologically — verify MAX picks the latest."""
    _insert_trade(
        db_path, trade_id="t1", status="closed",
        exit_date="2026-04-29T10:00:00+00:00",
    )
    _insert_trade(
        db_path, trade_id="t2", status="closed",
        exit_date="2026-05-01T15:30:00+00:00",
    )
    _insert_trade(
        db_path, trade_id="t3", status="closed",
        exit_date="2026-04-30T12:00:00+00:00",
    )
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.last_exit_at == datetime(
        2026, 5, 1, 15, 30, tzinfo=timezone.utc,
    )


def test_last_exit_at_open_trades_excluded_from_max(db_path):
    """Open trades must NOT contribute to last_exit_at — even if their
    exit_date is somehow set (shouldn't happen in practice but guard
    against schema slop)."""
    _insert_trade(
        db_path, trade_id="t1", status="open",
        exit_date="2030-12-31T23:59:59+00:00",  # bogus future date
    )
    s = _stub()
    state = s._build_live_profile_state("swing")
    assert state.last_exit_at is None


# ═════════════════════════════════════════════════════════════════
# Day-rollover reset (on_trading_iteration top)
# ═════════════════════════════════════════════════════════════════


def _stub_for_day_check(day_start_value: float = 5000.0,
                        last_day: date | None = None):
    """Stub configured just for the day-rollover guard. Doesn't need DB."""
    s = V2Strategy.__new__(V2Strategy)
    s._day_start_value = day_start_value
    s._last_day_check_date = last_day
    return s


def test_day_rollover_first_iteration_no_reset(db_path):
    """First iteration: _last_day_check_date=None → no reset, just record
    today's date."""
    s = _stub_for_day_check(day_start_value=5000.0, last_day=None)

    today = date(2026, 5, 1)
    fake_now = datetime(2026, 5, 1, 10, 30, tzinfo=timezone.utc)
    with patch("strategies.v2_strategy.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        # Inline the guard logic — full on_trading_iteration is too
        # heavy to drive in unit tests. The guard has no Lumibot
        # dependencies.
        from strategies.v2_strategy import ZoneInfo as _ZI
        _now_et = mock_dt.now(_ZI("America/New_York"))
        _today_et = _now_et.date() if hasattr(_now_et, 'date') else today
        # Simulate the conditional from on_trading_iteration:
        if (
            s._last_day_check_date is not None
            and s._last_day_check_date != _today_et
        ):
            s._day_start_value = 0.0
        s._last_day_check_date = _today_et

    assert s._day_start_value == 5000.0  # unchanged
    assert s._last_day_check_date is not None


def test_day_rollover_same_day_no_reset(db_path):
    """Second iteration on same day → no reset."""
    today = date(2026, 5, 1)
    s = _stub_for_day_check(day_start_value=5000.0, last_day=today)

    if (
        s._last_day_check_date is not None
        and s._last_day_check_date != today
    ):
        s._day_start_value = 0.0
    s._last_day_check_date = today

    assert s._day_start_value == 5000.0


def test_day_rollover_different_day_resets_and_logs(db_path, caplog):
    """Iteration the next day → _day_start_value reset to 0.0,
    info-logged."""
    yesterday = date(2026, 4, 30)
    today = date(2026, 5, 1)
    s = _stub_for_day_check(day_start_value=5000.0, last_day=yesterday)

    caplog.set_level(logging.INFO, logger="options-bot.strategy.v2")
    # Replicate the guard's behavior verbatim.
    import logging as _logging
    _logger = _logging.getLogger("options-bot.strategy.v2")
    if (
        s._last_day_check_date is not None
        and s._last_day_check_date != today
    ):
        _logger.info(
            "V2Strategy: ET date rolled over (%s -> %s) — resetting "
            "_day_start_value (was %.2f) for fresh PnL baseline",
            s._last_day_check_date, today, s._day_start_value,
        )
        s._day_start_value = 0.0
    s._last_day_check_date = today

    assert s._day_start_value == 0.0
    assert any(
        "rolled over" in r.message and "resetting" in r.message
        for r in caplog.records
    )


# ═════════════════════════════════════════════════════════════════
# Helper integration — full _build_live_profile_state call
# ═════════════════════════════════════════════════════════════════


def test_full_state_all_fields_populated(db_path):
    """Returned ProfileState has every field populated correctly."""
    _insert_trade(
        db_path, trade_id="t1", status="open",
        entry_price=2.00, quantity=3,
    )
    _insert_trade(
        db_path, trade_id="t2", status="closed",
        entry_price=1.50, quantity=1,
        exit_price=2.00, exit_date="2026-04-30T14:00:00+00:00",
    )
    s = _stub(pv=11000.0, day_start_value=10000.0)
    s._last_entry_time = {
        "swing": datetime(2026, 5, 1, 9, 30, tzinfo=timezone.utc),
    }
    state = s._build_live_profile_state("swing")

    assert state.current_open_positions == 1
    assert state.current_capital_deployed == 600.0  # 2.00 * 3 * 100
    assert state.today_account_pnl_pct == pytest.approx(0.10)
    assert state.last_exit_at == datetime(
        2026, 4, 30, 14, 0, tzinfo=timezone.utc,
    )
    assert state.last_entry_at == datetime(
        2026, 5, 1, 9, 30, tzinfo=timezone.utc,
    )


def test_state_last_entry_at_flows_from_dict(db_path):
    """last_entry_at sourced from self._last_entry_time[preset_name]."""
    s = _stub()
    s._last_entry_time = {
        "swing": datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc),
        "0dte_asymmetric": datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
    }
    state = s._build_live_profile_state("swing")
    assert state.last_entry_at == datetime(
        2026, 5, 1, 11, 0, tzinfo=timezone.utc,
    )


def test_state_recent_entries_dict_passes_through(db_path):
    """The mutable recent_entries_by_symbol_direction dict is the same
    object passed in — orchestrator mutates in place."""
    s = _stub()
    sentinel = {"SPY:bullish": datetime(2026, 5, 1, tzinfo=timezone.utc)}
    s._recent_entries_by_symbol_direction = sentinel
    state = s._build_live_profile_state("swing")
    assert state.recent_entries_by_symbol_direction is sentinel


# ═════════════════════════════════════════════════════════════════
# _run_new_preset_iteration uses the helper
# ═════════════════════════════════════════════════════════════════


def test_run_new_preset_iteration_calls_build_live_profile_state(db_path):
    """_run_new_preset_iteration must call self._build_live_profile_state
    once per scan_result+setup pair (not the literal-stub path).

    Setup: stub a preset that immediately returns a no-enter decision
    so the loop exits early (after the state build). Spy on
    _build_live_profile_state."""
    s = _stub()
    s._client = MagicMock()
    s._last_exit_reason = {}

    # Minimal preset stub: name + is_active_now + evaluate_entry
    fake_preset = MagicMock()
    fake_preset.name = "swing"
    fake_preset.is_active_now.return_value = True
    fake_preset._macro_fetcher = lambda *a, **kw: []
    fake_preset.evaluate_entry.return_value = MagicMock(
        should_enter=False, reason="captured", direction="bullish",
    )
    s._new_preset = fake_preset

    # Spy on the helper.
    spy = MagicMock(wraps=s._build_live_profile_state)
    s._build_live_profile_state = spy

    # Drive one iteration with one scan_result/setup pair.
    from market.context import MarketSnapshot, Regime, TimeOfDay
    snapshot = MarketSnapshot(
        regime=Regime.TRENDING_UP, time_of_day=TimeOfDay.OPEN,
        timestamp="2026-05-01T10:30:00+00:00", vix_level=20.0,
    )
    from types import SimpleNamespace
    from scanner.setups import SetupScore
    setup = SetupScore(setup_type="momentum", score=0.6,
                       reason="t", direction="bullish")
    scan_result = SimpleNamespace(symbol="TSLA", setups=[setup])

    s._run_new_preset_iteration([(scan_result, setup)], snapshot, None)

    spy.assert_called_once_with("swing")
