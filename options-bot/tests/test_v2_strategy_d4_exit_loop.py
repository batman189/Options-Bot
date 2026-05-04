"""D4 tests — new-pipeline exit loop.

Covers the parts D4 added to V2Strategy:
  - _build_position_from_trade_row (frozen Position reconstruction)
  - _rebind_preset_macro_fetcher (per-iteration fetcher rebind)
  - _submit_new_pipeline_exit (sell-to-close + state tracking)
  - _handle_new_pipeline_exit_fill (trades-row UPDATE + state cleanup)
  - _run_new_preset_exit_iteration (Step 9' main loop)
  - on_filled_order / on_canceled_order / on_error_order SELL routing
  - PART 1 retrofit — entry_underlying_price column write

Run via:
    python -m pytest tests/test_v2_strategy_d4_exit_loop.py -v
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from market.context import MarketSnapshot, Regime, TimeOfDay  # noqa: E402
from profiles.base_preset import (  # noqa: E402
    ContractSelection,
    ExitDecision,
    OptionChain,
    OptionContract,
    Position,
)
from profiles.profile_config import ProfileConfig  # noqa: E402
from profiles.swing_preset import SwingPreset  # noqa: E402
from profiles.zero_dte_asymmetric import ZeroDteAsymmetricPreset  # noqa: E402
from scanner.setups import SetupScore  # noqa: E402
from strategies.v2_strategy import V2Strategy  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Fixtures — schema, DB isolation, stub builder
# ─────────────────────────────────────────────────────────────────


# Trades schema verbatim from backend/database.py:50-85. Kept inline so
# tests don't depend on init_db().
_TRADES_SCHEMA_FOR_TEST = """
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


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Redirect strategies.v2_strategy.DB_PATH to a tmp test DB. The
    D4 helpers (_run_new_preset_exit_iteration / _handle_new_pipeline_exit_fill)
    read this monkeypatched path via `from config import DB_PATH`
    (rebound in v2_strategy at import time).

    Also monkeypatches config.EXECUTION_MODE to "live" because D4's
    exit loop reads config.EXECUTION_MODE to filter the trades SELECT
    (`WHERE execution_mode = ?`). Without this monkeypatch, host .env
    values like EXECUTION_MODE=signal_only (set per the Phase 1b
    operational-readiness plan) would cause the SELECT to filter out
    the fixture's 'live' rows (the default for _insert_open_trade),
    breaking tests in environments where operators have set the env
    var. Pinning to "live" matches _insert_open_trade's default and
    isolates the test from host environment state.
    """
    db_path = tmp_path / "test.db"
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.executescript(_TRADES_SCHEMA_FOR_TEST)
        conn.commit()
    monkeypatch.setattr("strategies.v2_strategy.DB_PATH", db_path)
    monkeypatch.setattr("config.EXECUTION_MODE", "live")
    return db_path


@pytest.fixture(autouse=True)
def _cleanup_production_db_pollution():
    """Some legacy on_filled_order code paths write to a hardcoded
    production DB path that bypasses DB_PATH monkeypatching (the
    BUY-fill INSERT, lines ~1212 in v2_strategy.py — outside the
    scope of D4). Clean up any test-prefixed rows after each test
    so we don't pollute the dev DB across runs.

    Tests that exercise on_filled_order BUY against the hardcoded
    path use a "d4-test-" prefix on trade_id so this teardown can
    target them precisely.
    """
    yield
    prod_db = (
        Path(__file__).parent.parent / "db" / "options_bot.db"
    )
    if prod_db.exists():
        try:
            with closing(sqlite3.connect(str(prod_db))) as conn:
                conn.execute(
                    "DELETE FROM trades WHERE id LIKE 'd4-test-%'"
                )
                conn.commit()
        except Exception:
            # Production DB might not have the schema or might be
            # locked — non-fatal for test cleanup.
            pass


def _profile_config(
    name: str = "test-profile",
    preset: str = "swing",
    symbols: list | None = None,
    max_capital: float = 5000.0,
    mode: str = "execution",
) -> ProfileConfig:
    return ProfileConfig(
        name=name,
        preset=preset,
        symbols=symbols or ["TSLA"],
        max_capital_deployed=max_capital,
        mode=mode,
    )


def _market_snapshot(
    vix: float = 20.0,
    regime: Regime = Regime.TRENDING_UP,
    time_of_day: TimeOfDay = TimeOfDay.OPEN,
) -> MarketSnapshot:
    return MarketSnapshot(
        regime=regime, time_of_day=time_of_day,
        timestamp="2026-05-01T10:30:00+00:00",
        vix_level=vix,
    )


def _build_v2_stub(
    preset_name: str = "swing",
    profile_config: ProfileConfig | None = None,
):
    """Construct a V2Strategy stub via __new__, set just the attributes
    the D4 exit loop consults. Mirrors test_v2_strategy_new_pipeline.py's
    helper but adds D4-specific state.
    """
    stub = V2Strategy.__new__(V2Strategy)
    stub.symbol = "TSLA"
    stub.profile_name = "test-profile"
    stub._config = {"preset": preset_name}
    stub._scan_symbols = ["TSLA"]
    stub.parameters = {"profile_id": "test-profile-id"}
    stub._client = MagicMock()
    stub._last_entry_time = {}
    stub._last_exit_reason = {}
    stub._recent_entries_by_symbol_direction = {}
    stub._thesis_break_streaks = {}
    stub._recent_exits_by_symbol = {}
    stub._profile_config = profile_config or _profile_config(preset=preset_name)
    stub._new_preset = None
    stub.get_portfolio_value = MagicMock(return_value=10000.0)
    stub._day_start_value = 0.0
    stub._starting_balance = 10000.0
    stub._pdt_locked = False
    stub._pdt_day_trades = 0
    stub._pdt_buying_power = 999999.0
    stub._risk_manager = MagicMock()
    stub._risk_manager.check_portfolio_exposure.return_value = {
        "exposure_dollars": 0.0,
        "allowed": True,
        "exposure_pct": 0.0,
        "limit_pct": 20.0,
        "message": "ok",
    }
    stub.create_order = MagicMock()
    stub.create_order.return_value = MagicMock(
        identifier="alpaca-test-id",
    )
    stub.submit_order = MagicMock()
    stub._shadow_sim = MagicMock()
    stub._shadow_sim.submit_entry = MagicMock(
        return_value="shadow-test-id",
    )
    stub._shadow_sim.submit_exit = MagicMock(
        return_value="shadow-exit-id",
    )
    stub._trade_manager = MagicMock()
    stub._trade_manager._positions = {}
    stub._trade_id_map = {}
    stub._pdt_no_same_day_exit = set()
    # D4 state.
    stub._new_preset_pending_exits = {}
    stub._peak_premium_by_trade_id = {}
    # D4 deps for _submit_new_pipeline_exit live-quote tier-1.
    stub.get_last_price = MagicMock(return_value=5.0)
    stub._execution_mode = "live"
    # _scorer and other legacy-only deps for on_filled_order legacy
    # branches that should NOT be touched by D4-routed sell fills.
    stub._scorer = MagicMock()
    return stub


def _attach_swing(stub, profile_config: ProfileConfig):
    preset = SwingPreset(
        config=profile_config,
        macro_fetcher=lambda symbol, lookahead: [],
    )
    stub._new_preset = preset
    return preset


def _insert_open_trade(
    db_path: Path,
    *,
    trade_id: str = "d4-test-trade-1",
    profile_id: str = "test-profile",
    symbol: str = "TSLA",
    direction: str = "call",
    strike: float = 250.0,
    expiration: str = "2026-05-15",  # 14 days out from 2026-05-01
    quantity: int = 1,
    entry_price: float = 4.00,
    entry_underlying_price: float | None = 250.0,
    execution_mode: str = "live",
    entry_date: str | None = None,
):
    """Insert a single open trade row into the test DB. Caller picks
    entry_underlying_price=None to simulate a pre-D4 trade that the
    exit loop should skip."""
    if entry_date is None:
        entry_date = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(
            """INSERT INTO trades (
                   id, profile_id, profile_name, symbol, direction,
                   strike, expiration, quantity, entry_price, entry_date,
                   entry_underlying_price, status, execution_mode,
                   created_at, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                trade_id, profile_id, profile_id, symbol, direction,
                strike, expiration, quantity, entry_price, entry_date,
                entry_underlying_price, "open", execution_mode,
                entry_date, entry_date,
            ),
        )
        conn.commit()


# ═════════════════════════════════════════════════════════════════
# _build_position_from_trade_row
# ═════════════════════════════════════════════════════════════════


def _row_dict(**overrides):
    """Build a trade-row dict matching the SELECT columns the exit
    loop projects. Includes overrides so individual tests vary one
    field."""
    base = {
        "id": "trade-abc",
        "profile_id": "test-profile",
        "symbol": "TSLA",
        "direction": "call",
        "strike": 250.0,
        "expiration": "2026-05-15",
        "quantity": 2,
        "entry_price": 4.00,
        "entry_date": (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat(),
        "entry_underlying_price": 248.50,
    }
    base.update(overrides)
    return base


def test_build_position_from_trade_row_basic_fields():
    """Position has all the row fields wired through."""
    stub = _build_v2_stub()
    row = _row_dict()

    pos = stub._build_position_from_trade_row(row, current_quote=4.50)

    assert pos.trade_id == "trade-abc"
    assert pos.symbol == "TSLA"
    assert pos.contract.symbol == "TSLA"
    assert pos.contract.right == "call"
    assert pos.contract.strike == 250.0
    assert pos.contract.expiration == date(2026, 5, 15)
    assert pos.contracts == 2
    assert pos.entry_premium_per_share == 4.00
    assert pos.entry_underlying_price == 248.50
    assert pos.current_premium_per_share == 4.50


def test_build_position_seeds_peak_from_entry_on_first_observation():
    """First observation: peak = max(entry, current_quote)."""
    stub = _build_v2_stub()
    row = _row_dict(entry_price=4.00)

    pos = stub._build_position_from_trade_row(row, current_quote=3.00)

    # Peak ratchets up from entry, not down to current_quote.
    assert pos.peak_premium_per_share == 4.00


def test_build_position_ratchets_peak_up_on_subsequent_observations():
    """Peak is monotone non-decreasing across cycles."""
    stub = _build_v2_stub()
    stub._peak_premium_by_trade_id["trade-abc"] = 6.00
    row = _row_dict(entry_price=4.00)

    pos = stub._build_position_from_trade_row(row, current_quote=5.00)

    assert pos.peak_premium_per_share == 6.00


def test_build_position_updates_peak_when_quote_exceeds_prior():
    stub = _build_v2_stub()
    stub._peak_premium_by_trade_id["trade-abc"] = 6.00
    row = _row_dict(entry_price=4.00)

    pos = stub._build_position_from_trade_row(row, current_quote=7.00)

    assert pos.peak_premium_per_share == 7.00
    assert stub._peak_premium_by_trade_id["trade-abc"] == 7.00


def test_build_position_naive_entry_date_normalized_to_utc():
    """entry_date without tzinfo gets stamped UTC so Position's
    __post_init__ doesn't reject."""
    stub = _build_v2_stub()
    naive_iso = "2026-04-30T15:30:00"  # No tzinfo
    row = _row_dict(entry_date=naive_iso)

    pos = stub._build_position_from_trade_row(row, current_quote=4.50)

    assert pos.entry_time.tzinfo is not None


def test_build_position_rejects_zero_underlying():
    """Position.__post_init__ raises on entry_underlying_price <= 0
    even though the SELECT filter prevents this in normal flow."""
    stub = _build_v2_stub()
    row = _row_dict(entry_underlying_price=0.0)

    with pytest.raises(ValueError):
        stub._build_position_from_trade_row(row, current_quote=4.50)


# ═════════════════════════════════════════════════════════════════
# _rebind_preset_macro_fetcher
# ═════════════════════════════════════════════════════════════════


def test_rebind_macro_fetcher_no_op_when_no_new_preset():
    """No-op for legacy presets (where _new_preset is None)."""
    stub = _build_v2_stub()
    stub._new_preset = None

    # Should not raise; should not crash.
    stub._rebind_preset_macro_fetcher(macro_ctx=None)


def test_rebind_macro_fetcher_replaces_preset_fetcher():
    """The fetcher closure is replaced with one keyed on the new
    macro_ctx — verified by the closure returning empty for None."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_swing(stub, pc)
    sentinel_old = preset._macro_fetcher

    stub._rebind_preset_macro_fetcher(macro_ctx=None)

    assert preset._macro_fetcher is not sentinel_old
    # Adapter returns empty list for None macro_ctx.
    assert preset._macro_fetcher("TSLA", 60) == []


# ═════════════════════════════════════════════════════════════════
# _submit_new_pipeline_exit
# ═════════════════════════════════════════════════════════════════


def _make_position(
    trade_id: str = "trade-abc",
    symbol: str = "TSLA",
    right: str = "call",
    strike: float = 250.0,
    expiration: date = date(2026, 5, 15),
    contracts: int = 2,
    entry_premium: float = 4.00,
    peak: float = 5.00,
    current: float = 4.50,
    entry_underlying: float = 248.50,
) -> Position:
    contract = ContractSelection(
        symbol=symbol, right=right, strike=strike,
        expiration=expiration, target_delta=0.0,
        estimated_premium=entry_premium, dte=14,
    )
    return Position(
        trade_id=trade_id, symbol=symbol, contract=contract,
        entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
        entry_premium_per_share=entry_premium,
        entry_underlying_price=entry_underlying,
        peak_premium_per_share=peak,
        current_premium_per_share=current,
        contracts=contracts,
    )


def test_submit_exit_live_path_writes_pending_and_returns_true():
    """Happy path — submit_order succeeds, _trade_id_map and
    _new_preset_pending_exits both get the right entries."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    pos = _make_position()

    result = stub._submit_new_pipeline_exit(
        pos.trade_id, pos, "trailing_stop",
    )

    assert result is True
    stub.submit_order.assert_called_once()
    assert "alpaca-test-id" in stub._trade_id_map
    assert stub._trade_id_map["alpaca-test-id"] == pos.trade_id
    assert pos.trade_id in stub._new_preset_pending_exits
    meta = stub._new_preset_pending_exits[pos.trade_id]
    assert meta["alpaca_id"] == "alpaca-test-id"
    assert meta["reason"] == "trailing_stop"


def test_submit_exit_uses_live_quote_for_limit_price():
    """Tier 1: get_last_price returns a positive value → use it."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub.get_last_price.return_value = 4.42
    pos = _make_position()

    stub._submit_new_pipeline_exit(pos.trade_id, pos, "thesis_break")

    args, kwargs = stub.create_order.call_args
    assert kwargs.get("limit_price") == 4.42


def test_submit_exit_falls_back_to_peak_when_quote_unavailable():
    """Tier 2: get_last_price returns None → use peak."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub.get_last_price.return_value = None
    pos = _make_position(peak=5.50)

    stub._submit_new_pipeline_exit(pos.trade_id, pos, "trailing_stop")

    args, kwargs = stub.create_order.call_args
    assert kwargs.get("limit_price") == 5.50


def test_submit_exit_pdt_rejection_returns_false_and_locks():
    """PDT rejection returns False and sets self._pdt_locked = True."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub.submit_order.side_effect = Exception(
        "Pattern day trading violation 40310100"
    )
    pos = _make_position()

    result = stub._submit_new_pipeline_exit(
        pos.trade_id, pos, "dte_floor",
    )

    assert result is False
    assert stub._pdt_locked is True
    # No pending-exit entry was retained.
    assert pos.trade_id not in stub._new_preset_pending_exits


def test_submit_exit_unexpected_exception_returns_false():
    """Generic exception path → False, no state retained."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub.submit_order.side_effect = ConnectionError("network down")
    pos = _make_position()

    result = stub._submit_new_pipeline_exit(
        pos.trade_id, pos, "trailing_stop",
    )

    assert result is False
    assert pos.trade_id not in stub._new_preset_pending_exits


def test_submit_exit_invalid_alpaca_id_returns_false():
    """If _alpaca_id returns None, no state is retained."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    # Lumibot would normally stamp identifier; force None so the
    # invalid-id branch fires.
    stub.create_order.return_value = MagicMock(
        identifier=None,
    )
    # Unset spec so _alpaca_id sees a non-string identifier.
    pos = _make_position()

    result = stub._submit_new_pipeline_exit(
        pos.trade_id, pos, "trailing_stop",
    )

    assert result is False
    assert pos.trade_id not in stub._new_preset_pending_exits


def test_submit_exit_shadow_path_uses_shadow_sim():
    """Shadow mode: pre-seeds _trade_id_map BEFORE simulator dispatch."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._execution_mode = "shadow"
    pos = _make_position()

    result = stub._submit_new_pipeline_exit(
        pos.trade_id, pos, "trailing_stop",
    )

    assert result is True
    stub._shadow_sim.submit_exit.assert_called_once()
    # submit_order is NOT called in shadow mode.
    stub.submit_order.assert_not_called()
    assert pos.trade_id in stub._new_preset_pending_exits


def test_submit_exit_shadow_quote_unavailable_returns_false():
    """Shadow simulator returning None (quote unavailable) → False
    and full state cleanup."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._execution_mode = "shadow"
    stub._shadow_sim.submit_exit.return_value = None
    pos = _make_position()

    result = stub._submit_new_pipeline_exit(
        pos.trade_id, pos, "trailing_stop",
    )

    assert result is False
    assert pos.trade_id not in stub._new_preset_pending_exits


# ═════════════════════════════════════════════════════════════════
# _handle_new_pipeline_exit_fill
# ═════════════════════════════════════════════════════════════════


def test_handle_exit_fill_updates_trades_row(_isolate_db):
    """The trades-row UPDATE writes status=closed + exit fields."""
    _insert_open_trade(_isolate_db, trade_id="t-handle-1")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["t-handle-1"] = {
        "alpaca_id": "alpaca-id-1",
        "submitted_at": datetime.now(timezone.utc),
        "reason": "trailing_stop",
    }

    stub._handle_new_pipeline_exit_fill("t-handle-1", fill_price=5.50)

    with closing(sqlite3.connect(str(_isolate_db))) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, exit_price, exit_reason, pnl_pct "
            "FROM trades WHERE id = ?",
            ("t-handle-1",),
        ).fetchone()

    assert row["status"] == "closed"
    assert row["exit_price"] == 5.50
    assert row["exit_reason"] == "trailing_stop"
    # PnL: (5.50 - 4.00) / 4.00 * 100 = 37.5%
    assert row["pnl_pct"] == 37.5


def test_handle_exit_fill_clears_state_dicts(_isolate_db):
    """All per-trade in-memory state is cleared after the close."""
    _insert_open_trade(_isolate_db, trade_id="t-clean-1")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["t-clean-1"] = {
        "alpaca_id": "a", "submitted_at": datetime.now(timezone.utc),
        "reason": "thesis_break",
    }
    stub._peak_premium_by_trade_id["t-clean-1"] = 6.00
    stub._thesis_break_streaks["t-clean-1"] = 2

    stub._handle_new_pipeline_exit_fill("t-clean-1", fill_price=3.00)

    assert "t-clean-1" not in stub._new_preset_pending_exits
    assert "t-clean-1" not in stub._peak_premium_by_trade_id
    assert "t-clean-1" not in stub._thesis_break_streaks


def test_handle_exit_fill_unknown_trade_id_logs_warning(_isolate_db):
    """No pending-exit metadata → warning, no DB write."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)

    # Should not raise.
    stub._handle_new_pipeline_exit_fill("unknown-trade", fill_price=5.0)


def test_handle_exit_fill_records_last_exit_reason(_isolate_db):
    """_last_exit_reason is keyed by preset name."""
    _insert_open_trade(_isolate_db, trade_id="t-reason-1")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["t-reason-1"] = {
        "alpaca_id": "a", "submitted_at": datetime.now(timezone.utc),
        "reason": "pre_event_close",
    }

    stub._handle_new_pipeline_exit_fill("t-reason-1", fill_price=4.20)

    assert stub._last_exit_reason["swing"] == "pre_event_close"


def test_handle_exit_fill_marks_was_day_trade_when_intraday(_isolate_db):
    """was_day_trade=1 if entry_date and exit_date share a calendar day."""
    today_iso = datetime.now(timezone.utc).isoformat()
    _insert_open_trade(
        _isolate_db, trade_id="t-day-1",
        entry_date=today_iso,
    )

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["t-day-1"] = {
        "alpaca_id": "a", "submitted_at": datetime.now(timezone.utc),
        "reason": "trailing_stop",
    }

    stub._handle_new_pipeline_exit_fill("t-day-1", fill_price=5.00)

    with closing(sqlite3.connect(str(_isolate_db))) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT was_day_trade FROM trades WHERE id = ?",
            ("t-day-1",),
        ).fetchone()

    assert row["was_day_trade"] == 1


# ═════════════════════════════════════════════════════════════════
# _run_new_preset_exit_iteration
# ═════════════════════════════════════════════════════════════════


def test_exit_iteration_no_open_trades_is_noop(_isolate_db):
    """No rows in trades → no _submit_new_pipeline_exit call."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_not_called()


def test_exit_iteration_skips_pre_d4_null_underlying_trades(_isolate_db):
    """A row with entry_underlying_price=NULL is filtered out."""
    _insert_open_trade(
        _isolate_db, trade_id="d4-test-pre", entry_underlying_price=None,
    )

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_not_called()


def test_exit_iteration_filters_by_profile_id(_isolate_db):
    """Trades with a different profile_id are skipped."""
    _insert_open_trade(
        _isolate_db, trade_id="t-other-profile",
        profile_id="other-profile",
    )

    pc = _profile_config(name="my-profile", preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_not_called()


def test_exit_iteration_filters_by_execution_mode(_isolate_db, monkeypatch):
    """Mismatched execution_mode rows are skipped."""
    monkeypatch.setattr("config.EXECUTION_MODE", "live")
    _insert_open_trade(
        _isolate_db, trade_id="t-shadow-row",
        execution_mode="shadow",
    )

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_not_called()


def test_exit_iteration_skips_trade_with_pending_exit(_isolate_db):
    """Trade already in _new_preset_pending_exits is skipped."""
    _insert_open_trade(_isolate_db, trade_id="t-pending")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["t-pending"] = {
        "alpaca_id": "a", "submitted_at": datetime.now(timezone.utc),
        "reason": "trailing_stop",
    }

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_not_called()


def test_exit_iteration_skips_when_quote_unavailable(_isolate_db):
    """get_last_price returns None → no Position built, no submit."""
    _insert_open_trade(_isolate_db, trade_id="t-no-quote")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub.get_last_price.return_value = None

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_not_called()


def test_exit_iteration_holds_when_evaluate_exit_returns_no_exit(_isolate_db):
    """evaluate_exit returns should_exit=False → no submit."""
    _insert_open_trade(_isolate_db, trade_id="t-hold")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_swing(stub, pc)
    preset.evaluate_exit = MagicMock(
        return_value=ExitDecision(should_exit=False, reason="no_exit"),
    )

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    preset.evaluate_exit.assert_called_once()
    submit.assert_not_called()


def test_exit_iteration_submits_when_evaluate_exit_signals_exit(_isolate_db):
    """evaluate_exit returns should_exit=True → submit fires with reason."""
    _insert_open_trade(_isolate_db, trade_id="t-trail")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_swing(stub, pc)
    preset.evaluate_exit = MagicMock(
        return_value=ExitDecision(
            should_exit=True, reason="trailing_stop",
        ),
    )

    with patch.object(
        stub, "_submit_new_pipeline_exit", return_value=True,
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_called_once()
    args, _ = submit.call_args
    assert args[0] == "t-trail"
    assert args[2] == "trailing_stop"


def test_exit_iteration_filters_setups_to_position_symbol(_isolate_db):
    """The setups passed to evaluate_exit are filtered to the position's
    symbol, not the full active list."""
    _insert_open_trade(
        _isolate_db, trade_id="t-setup-filter", symbol="TSLA",
    )

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_swing(stub, pc)
    preset.evaluate_exit = MagicMock(
        return_value=ExitDecision(should_exit=False, reason="no_exit"),
    )

    tsla_setup = SetupScore(
        setup_type="momentum", score=0.6, reason="t",
        direction="bullish",
    )
    qqq_setup = SetupScore(
        setup_type="momentum", score=0.5, reason="q",
        direction="bullish",
    )
    active = [
        (SimpleNamespace(symbol="TSLA"), tsla_setup),
        (SimpleNamespace(symbol="QQQ"), qqq_setup),
    ]

    stub._run_new_preset_exit_iteration(active, _market_snapshot(), None)

    args, _ = preset.evaluate_exit.call_args
    setups_arg = args[3]
    assert tsla_setup in setups_arg
    assert qqq_setup not in setups_arg


def test_exit_iteration_defensive_against_not_implemented(_isolate_db):
    """0DTE preset's evaluate_exit raises NotImplementedError; the
    loop should swallow and continue."""
    _insert_open_trade(_isolate_db, trade_id="t-0dte-stub")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_swing(stub, pc)
    preset.evaluate_exit = MagicMock(
        side_effect=NotImplementedError("0dte deferred"),
    )

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        # Should not raise.
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_not_called()


def test_exit_iteration_no_op_when_new_preset_is_none(_isolate_db):
    _insert_open_trade(_isolate_db, trade_id="t-no-preset")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    stub._new_preset = None

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_not_called()


# ═════════════════════════════════════════════════════════════════
# on_filled_order SELL routing
# ═════════════════════════════════════════════════════════════════


def test_on_filled_order_sell_routes_new_pipeline_to_handler():
    """SELL fill where trade_id is in _new_preset_pending_exits routes
    to _handle_new_pipeline_exit_fill (not confirm_fill)."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["new-trade-1"] = {
        "alpaca_id": "alpaca-x", "submitted_at": datetime.now(timezone.utc),
        "reason": "trailing_stop",
    }
    stub._trade_id_map["alpaca-x"] = "new-trade-1"

    order = MagicMock(side="sell", identifier="alpaca-x")
    pos = MagicMock(asset="TSLA")

    with patch.object(
        stub, "_handle_new_pipeline_exit_fill",
    ) as handler:
        stub.on_filled_order(pos, order, 5.0, 1, 100)

    handler.assert_called_once_with("new-trade-1", 5.0)
    stub._trade_manager.confirm_fill.assert_not_called()


def test_on_filled_order_sell_legacy_routes_to_confirm_fill():
    """Legacy SELL fill (trade_id not in _new_preset_pending_exits)
    still goes through _trade_manager.confirm_fill."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._trade_id_map["alpaca-y"] = "legacy-trade-1"

    order = MagicMock(side="sell", identifier="alpaca-y")
    pos = MagicMock(asset="TSLA")

    with patch.object(
        stub, "_handle_new_pipeline_exit_fill",
    ) as handler:
        stub.on_filled_order(pos, order, 5.0, 1, 100)

    handler.assert_not_called()
    stub._trade_manager.confirm_fill.assert_called_once_with(
        "legacy-trade-1", 5.0,
    )


# ═════════════════════════════════════════════════════════════════
# on_canceled_order SELL routing
# ═════════════════════════════════════════════════════════════════


def test_on_canceled_order_sell_clears_new_pipeline_pending():
    """SELL cancel where trade_id is in pending_exits → clears entry."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["t-cancel-1"] = {
        "alpaca_id": "alpaca-c", "submitted_at": datetime.now(timezone.utc),
        "reason": "thesis_break",
    }
    stub._trade_id_map["alpaca-c"] = "t-cancel-1"

    order = MagicMock(side="sell", identifier="alpaca-c")

    stub.on_canceled_order(order)

    assert "t-cancel-1" not in stub._new_preset_pending_exits


def test_on_canceled_order_sell_preserves_peak_and_streaks():
    """Cancel does NOT clear peak / streaks — position is still open."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["t-cancel-2"] = {
        "alpaca_id": "alpaca-d", "submitted_at": datetime.now(timezone.utc),
        "reason": "thesis_break",
    }
    stub._peak_premium_by_trade_id["t-cancel-2"] = 6.00
    stub._thesis_break_streaks["t-cancel-2"] = 1
    stub._trade_id_map["alpaca-d"] = "t-cancel-2"

    order = MagicMock(side="sell", identifier="alpaca-d")

    stub.on_canceled_order(order)

    assert stub._peak_premium_by_trade_id["t-cancel-2"] == 6.00
    assert stub._thesis_break_streaks["t-cancel-2"] == 1


# ═════════════════════════════════════════════════════════════════
# on_error_order SELL routing
# ═════════════════════════════════════════════════════════════════


def test_on_error_order_sell_clears_new_pipeline_pending():
    """SELL error where trade_id is in pending_exits → clears entry."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["t-err-1"] = {
        "alpaca_id": "alpaca-e", "submitted_at": datetime.now(timezone.utc),
        "reason": "trailing_stop",
    }
    stub._trade_id_map["alpaca-e"] = "t-err-1"

    order = MagicMock(side="sell", identifier="alpaca-e")

    stub.on_error_order(order, error="rejected")

    assert "t-err-1" not in stub._new_preset_pending_exits


def test_on_error_order_sell_preserves_peak_and_streaks():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["t-err-2"] = {
        "alpaca_id": "alpaca-f", "submitted_at": datetime.now(timezone.utc),
        "reason": "thesis_break",
    }
    stub._peak_premium_by_trade_id["t-err-2"] = 5.50
    stub._trade_id_map["alpaca-f"] = "t-err-2"

    order = MagicMock(side="sell", identifier="alpaca-f")

    stub.on_error_order(order, error="rejected")

    assert stub._peak_premium_by_trade_id["t-err-2"] == 5.50


# ═════════════════════════════════════════════════════════════════
# PART 1 retrofit — entry_underlying_price written to trades INSERT
# ═════════════════════════════════════════════════════════════════


def test_submit_new_pipeline_entry_threads_underlying_into_meta():
    """The _entry_meta dict includes entry_underlying_price keyed
    from the constructor arg."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)

    contract = ContractSelection(
        symbol="TSLA", right="call", strike=255.0,
        expiration=date(2026, 5, 15), target_delta=0.5,
        estimated_premium=4.10, dte=14,
    )
    setup = SetupScore(
        setup_type="momentum", score=0.6, reason="t",
        direction="bullish",
    )
    snapshot = _market_snapshot()
    decision = SimpleNamespace(
        should_enter=True, direction="bullish", reason="ok",
    )

    result = stub._submit_new_pipeline_entry(
        contract, 1, setup, stub._new_preset, snapshot, decision,
        entry_underlying_price=251.75,
    )

    assert result.submitted is True
    # _trade_id_map carries the entry_meta dict; pull it back out and
    # verify the underlying-price key.
    meta_values = list(stub._trade_id_map.values())
    assert len(meta_values) == 1
    meta = meta_values[0]
    assert meta["entry_underlying_price"] == 251.75


# ═════════════════════════════════════════════════════════════════
# Initialize state attributes
# ═════════════════════════════════════════════════════════════════


def test_initialize_creates_d4_state_attributes():
    """Sanity: a fresh stub has the D4 state dicts."""
    stub = _build_v2_stub()
    assert hasattr(stub, "_new_preset_pending_exits")
    assert isinstance(stub._new_preset_pending_exits, dict)
    assert hasattr(stub, "_peak_premium_by_trade_id")
    assert isinstance(stub._peak_premium_by_trade_id, dict)


# ═════════════════════════════════════════════════════════════════
# M2 — TestS3PerRowExceptionHandling
# Lock-in tests for the existing per-row try/except guards in
# _run_new_preset_exit_iteration (v2_strategy.py:2860-2876 around
# strptime/quote-fetch and v2_strategy.py:2889-2899 around
# _build_position_from_trade_row). The pre-Monday audit Section
# F.4 incorrectly claimed these wraps were missing; M2 verified
# they exist and adds these tests so future regressions fail CI.
# ═════════════════════════════════════════════════════════════════


def test_s3_malformed_expiration_caught_and_loop_continues(_isolate_db):
    """A row whose expiration string is unparsable raises in the
    quote-fetch try/except (v2:2860-2876, strptime path). The loop
    logs at error level and continues; _submit_new_pipeline_exit
    is never called."""
    _insert_open_trade(
        _isolate_db, trade_id="d4-test-bad-exp",
        expiration="2026/05/15",  # Slashes — strptime("%Y-%m-%d") fails
    )

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        # Should not raise.
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_not_called()


def test_s3_position_validation_failure_caught_and_loop_continues(_isolate_db):
    """A row whose entry_price=0 makes Position.__post_init__ reject
    entry_premium_per_share<=0. Caught in the v2:2889-2899 try/except;
    loop continues; _submit_new_pipeline_exit never called."""
    _insert_open_trade(
        _isolate_db, trade_id="d4-test-bad-entry",
        entry_price=0.0,  # Position rejects entry_premium_per_share<=0
    )

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    submit.assert_not_called()


def test_s3_mix_valid_and_malformed_rows_processes_valid_only(_isolate_db):
    """Mix of valid + malformed rows: malformed is logged-and-skipped,
    valid one's evaluate_exit IS called. Demonstrates the loop survives
    bad rows and continues evaluating later rows in the same iteration."""
    _insert_open_trade(
        _isolate_db, trade_id="d4-test-mix-bad",
        expiration="2026/05/15",  # malformed
    )
    _insert_open_trade(
        _isolate_db, trade_id="d4-test-mix-good",
        expiration="2026-05-15",  # valid
    )

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_swing(stub, pc)
    preset.evaluate_exit = MagicMock(
        return_value=ExitDecision(should_exit=False, reason="no_exit"),
    )

    with patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    # The valid row reached evaluate_exit; the malformed row didn't.
    preset.evaluate_exit.assert_called_once()
    submit.assert_not_called()


# ═════════════════════════════════════════════════════════════════
# M2 — TestS4QuoteGuardZeroAndPositive
# Lock-in tests for the existing quote <= 0 guard at
# v2_strategy.py:2878-2884. The pre-Monday audit Section F.6
# incorrectly claimed this guard was missing before
# _build_position_from_trade_row; M2 verified the guard exists
# and adds explicit 0.0 + sanity coverage. The existing test
# `test_exit_iteration_skips_when_quote_unavailable` (line 791
# above) covers the None case.
# ═════════════════════════════════════════════════════════════════


def test_s4_zero_quote_skips_position_build(_isolate_db):
    """get_last_price returns exactly 0.0 — guard at v2:2878 catches
    `current_quote <= 0` and continues. _build_position_from_trade_row
    is never called for this row, so a position with current=0 (which
    Position.__post_init__ accepts) doesn't reach evaluate_exit."""
    _insert_open_trade(_isolate_db, trade_id="d4-test-zero-quote")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub.get_last_price.return_value = 0.0

    with patch.object(
        stub, "_build_position_from_trade_row",
    ) as build, patch.object(
        stub, "_submit_new_pipeline_exit",
    ) as submit:
        stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    build.assert_not_called()
    submit.assert_not_called()


def test_s4_positive_quote_proceeds_to_build(_isolate_db):
    """Sanity: a healthy positive quote passes the guard and reaches
    _build_position_from_trade_row. Asserts the guard isn't over-broad."""
    _insert_open_trade(_isolate_db, trade_id="d4-test-positive-quote")

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_swing(stub, pc)
    preset.evaluate_exit = MagicMock(
        return_value=ExitDecision(should_exit=False, reason="no_exit"),
    )
    stub.get_last_price.return_value = 4.50

    stub._run_new_preset_exit_iteration([], _market_snapshot(), None)

    # evaluate_exit was reached — proves _build_position_from_trade_row
    # ran (it's the only path to evaluate_exit in the loop).
    preset.evaluate_exit.assert_called_once()


# ═════════════════════════════════════════════════════════════════
# M2 — TestS5WasDayTradeET
# Tests the M2 fix at _handle_new_pipeline_exit_fill: was_day_trade
# is now computed via ET date comparison rather than UTC date
# comparison, matching legacy trade_manager.py confirm_fill (which
# uses get_et_now()). PDT day-trade counter feeds off this column;
# UTC-vs-ET divergence misclassified pre/post-market entries that
# crossed UTC midnight but stayed within the same ET day.
# ═════════════════════════════════════════════════════════════════


class _FrozenDateTime(datetime):
    """datetime subclass with a controllable .now() — the rest of
    datetime's API (fromisoformat, replace, astimezone, etc.) is
    inherited unchanged, so patching `strategies.v2_strategy.datetime`
    with this class only diverts .now() calls."""
    _frozen_utc: datetime | None = None

    @classmethod
    def now(cls, tz=None):
        if cls._frozen_utc is None:
            raise RuntimeError("_FrozenDateTime._frozen_utc not set")
        if tz is None:
            return cls._frozen_utc.replace(tzinfo=None)
        return cls._frozen_utc.astimezone(tz)


def test_s5_was_day_trade_true_when_same_et_day_crosses_utc_midnight(_isolate_db):
    """Entry 23:00 UTC Tuesday (= 19:00 ET Tuesday); exit fill 02:00
    UTC Wednesday (= 22:00 ET Tuesday). Same ET day, different UTC
    days. M2's fix: was_day_trade = 1 (ET-correct). Pre-M2 code
    would have written 0 (UTC-incorrect)."""
    entry_iso = "2026-05-05T23:00:00+00:00"  # 23:00 UTC Tue = 19:00 ET Tue
    _insert_open_trade(
        _isolate_db, trade_id="d4-test-s5-cross",
        entry_date=entry_iso,
    )

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["d4-test-s5-cross"] = {
        "alpaca_id": "a", "submitted_at": datetime.now(timezone.utc),
        "reason": "trailing_stop",
    }

    # Freeze "now" at 02:00 UTC Wednesday = 22:00 ET Tuesday.
    _FrozenDateTime._frozen_utc = datetime(
        2026, 5, 6, 2, 0, tzinfo=timezone.utc,
    )
    with patch(
        "strategies.v2_strategy.datetime", _FrozenDateTime,
    ):
        stub._handle_new_pipeline_exit_fill(
            "d4-test-s5-cross", fill_price=5.00,
        )

    with closing(sqlite3.connect(str(_isolate_db))) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT was_day_trade FROM trades WHERE id = ?",
            ("d4-test-s5-cross",),
        ).fetchone()

    # ET says same day → was_day_trade=1.
    assert row["was_day_trade"] == 1


def test_s5_was_day_trade_false_when_different_et_days(_isolate_db):
    """Entry 16:00 ET Tuesday (= 21:00 UTC Tuesday); exit fill 09:00
    ET Wednesday (= 14:00 UTC Wednesday). Different ET days, different
    UTC days. M2's fix and pre-M2 code agree here: was_day_trade = 0.
    Sanity check that the ET fix doesn't over-classify."""
    entry_iso = "2026-05-05T21:00:00+00:00"  # 21:00 UTC Tue = 17:00 ET Tue
    _insert_open_trade(
        _isolate_db, trade_id="d4-test-s5-overnight",
        entry_date=entry_iso,
    )

    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    _attach_swing(stub, pc)
    stub._new_preset_pending_exits["d4-test-s5-overnight"] = {
        "alpaca_id": "a", "submitted_at": datetime.now(timezone.utc),
        "reason": "trailing_stop",
    }

    # Freeze "now" at 14:00 UTC Wednesday = 10:00 ET Wednesday.
    _FrozenDateTime._frozen_utc = datetime(
        2026, 5, 6, 14, 0, tzinfo=timezone.utc,
    )
    with patch(
        "strategies.v2_strategy.datetime", _FrozenDateTime,
    ):
        stub._handle_new_pipeline_exit_fill(
            "d4-test-s5-overnight", fill_price=5.00,
        )

    with closing(sqlite3.connect(str(_isolate_db))) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT was_day_trade FROM trades WHERE id = ?",
            ("d4-test-s5-overnight",),
        ).fetchone()

    # Different ET days → was_day_trade=0.
    assert row["was_day_trade"] == 0
