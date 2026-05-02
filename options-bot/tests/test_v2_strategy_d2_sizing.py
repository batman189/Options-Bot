"""Unit tests for D2 — sizer.calculate wiring + PDT gate in
V2Strategy._run_new_preset_iteration.

After D2, non-signal_only modes (swing under live/shadow) compute
proposed_contracts via sizer.calculate after a PDT gate check.
signal_only retains the hardcoded 1.

Tests use the C5b _build_v2_stub pattern via direct attribute
attach. All external services (sizer.calculate, risk_manager,
record_signal, send_entry_alert) are patched at strategies.v2_strategy
import points.

Run via:
    python -m pytest tests/test_v2_strategy_d2_sizing.py -v
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from market.context import MarketSnapshot, Regime, TimeOfDay  # noqa: E402
from profiles.base_preset import (  # noqa: E402
    ContractSelection,
    EntryDecision,
    OptionChain,
    OptionContract,
)
from profiles.profile_config import ProfileConfig  # noqa: E402
from profiles.swing_preset import SwingPreset  # noqa: E402
from scanner.setups import SetupScore  # noqa: E402
from sizing.cap_check import CapCheckResult  # noqa: E402
from sizing.sizer import SizingResult  # noqa: E402
from strategies.v2_strategy import V2Strategy  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Schema + fixtures (mirror the C5b/D1 pattern)
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


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Per-test tmp DB with trades schema, DB_PATH patched. Empty DB
    so D1's _build_live_profile_state returns zero counts."""
    db_path = tmp_path / "test.db"
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.executescript(_TRADES_SCHEMA)
        conn.commit()
    monkeypatch.setattr(
        "strategies.v2_strategy.DB_PATH", db_path,
    )
    return db_path


def _profile_config(
    preset: str = "swing",
    name: str = "test-profile",
    symbols: list | None = None,
    max_capital: float = 10000.0,
) -> ProfileConfig:
    return ProfileConfig(
        name=name, preset=preset,
        symbols=symbols or ["TSLA"],
        max_capital_deployed=max_capital,
    )


def _scan_result(symbol: str = "TSLA", setup_type: str = "momentum",
                 score: float = 0.60, direction: str = "bullish"):
    setup = SetupScore(
        setup_type=setup_type, score=score,
        reason="test", direction=direction,
    )
    return SimpleNamespace(symbol=symbol, setups=[setup]), setup


def _market_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        regime=Regime.TRENDING_UP,
        time_of_day=TimeOfDay.OPEN,
        timestamp="2026-05-02T10:30:00+00:00",
        vix_level=20.0,
    )


def _swing_contract(
    expiration: date | None = None,
) -> ContractSelection:
    """Default contract: 7-DTE swing call (NOT same-day)."""
    if expiration is None:
        expiration = (
            datetime.now(timezone.utc).date()
            + (date(2026, 5, 9) - date(2026, 5, 2))
        )
    return ContractSelection(
        symbol="TSLA", right="call", strike=252.0,
        expiration=expiration,
        target_delta=0.50, estimated_premium=4.00, dte=7,
    )


def _make_chain() -> OptionChain:
    contract = OptionContract(
        symbol="TSLA", right="call", strike=252.0,
        expiration=date(2026, 5, 9),
        bid=3.95, ask=4.05, mid=4.00,
        delta=0.50, iv=0.30,
        open_interest=2000, volume=1000,
    )
    return OptionChain(
        symbol="TSLA", underlying_price=250.0,
        contracts=[contract],
        snapshot_time=datetime(2026, 5, 2, 14, 30, tzinfo=timezone.utc),
    )


def _stub(
    pv: float = 30000.0,
    pdt_locked: bool = False,
    pdt_day_trades: int = 0,
    starting_balance: float = 30000.0,
    day_start_value: float = 30000.0,
    growth_mode: bool = True,
):
    """V2Strategy stub with all D2-required attributes set."""
    s = V2Strategy.__new__(V2Strategy)
    pc = _profile_config()
    s.symbol = "TSLA"
    s.profile_name = "test-profile"
    s._config = {"preset": "swing", "growth_mode": growth_mode}
    s._scan_symbols = ["TSLA"]
    s.parameters = {"profile_id": "test-profile-id"}
    s._client = MagicMock()
    s._last_entry_time = {}
    s._last_exit_reason = {}
    s._recent_entries_by_symbol_direction = {}
    s._thesis_break_streaks = {}
    s._recent_exits_by_symbol = {}
    s._profile_config = pc
    s._new_preset = None
    s.get_portfolio_value = MagicMock(return_value=pv)
    s._day_start_value = day_start_value
    s._starting_balance = starting_balance
    s._pdt_locked = pdt_locked
    s._pdt_day_trades = pdt_day_trades
    s._pdt_buying_power = 999999.0
    s._risk_manager = MagicMock()
    s._risk_manager.check_portfolio_exposure.return_value = {
        "exposure_dollars": 0.0,
        "allowed": True,
        "exposure_pct": 0.0,
        "limit_pct": 20.0,
        "message": "ok",
    }
    # D3: dependencies for the actual-submission path. Symmetric to
    # the C5b stub extension. The D2 tests that previously asserted
    # "send NOT called" passed accidentally because missing
    # create_order/submit_order mocks caused AttributeError, swallowed
    # by D3's outer try/except. Now that the deps are present, those
    # tests' renamed counterparts assert positive submission behavior.
    s.create_order = MagicMock(
        return_value=MagicMock(identifier="alpaca-d2-test"),
    )
    s.submit_order = MagicMock()
    s._shadow_sim = MagicMock()
    s._shadow_sim.submit_entry = MagicMock(return_value="shadow-d2-test")
    s._trade_manager = MagicMock()
    s._trade_id_map = {}
    s._pdt_no_same_day_exit = set()
    return s


def _attach_swing_preset(stub, profile_config: ProfileConfig):
    preset = SwingPreset(
        config=profile_config,
        macro_fetcher=lambda symbol, lookahead: [],
    )
    preset.evaluate_entry = MagicMock(return_value=EntryDecision(
        should_enter=True, reason="ok", direction="bullish",
    ))
    preset.select_contract = MagicMock(return_value=_swing_contract())
    preset.can_enter = MagicMock(return_value=CapCheckResult(
        approved=True, approved_contracts=2,
        block_reason="", notes=[],
    ))
    stub._new_preset = preset
    stub._build_option_chain_for_new_preset = MagicMock(
        return_value=_make_chain(),
    )
    return preset


def _ok_sizing(contracts: int = 2) -> SizingResult:
    """Helper: build a non-blocked SizingResult."""
    return SizingResult(
        contracts=contracts, base_risk=1200.0,
        confidence_risk=720.0, after_drawdown_halving=720.0,
        after_pdt_halving=720.0, final_risk=720.0,
        premium_per_contract=400.0, halvings_applied=[],
        blocked=False, block_reason="",
    )


def _blocked_sizing(reason: str = "insufficient_risk_budget") -> SizingResult:
    return SizingResult(
        contracts=0, base_risk=0, confidence_risk=0,
        after_drawdown_halving=0, after_pdt_halving=0,
        final_risk=0, premium_per_contract=400.0,
        halvings_applied=[], blocked=True, block_reason=reason,
    )


# ═════════════════════════════════════════════════════════════════
# PDT gate
# ═════════════════════════════════════════════════════════════════


def test_pdt_above_25k_skips_pdt_logic():
    """pv >= 25000: PDT block paths are unreachable; sizer always runs."""
    s = _stub(pv=30000.0, pdt_locked=True, pdt_day_trades=3)
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing()) as sizer, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_called_once()


def test_pdt_below_25k_locked_blocks_skips_sizer():
    s = _stub(pv=5000.0, pdt_locked=True, pdt_day_trades=0)
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate") as sizer, \
         patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_not_called()
    preset.can_enter.assert_not_called()
    rec.assert_not_called()
    send.assert_not_called()


def test_pdt_below_25k_2trades_same_day_blocks():
    """Synthesize a same-day expiration to exercise the second PDT branch
    (defensive code — swing's DTE_MIN=7 makes this unreachable in
    reality, but the guard remains)."""
    today = datetime.now(timezone.utc).date()
    s = _stub(pv=5000.0, pdt_locked=False, pdt_day_trades=2)
    preset = _attach_swing_preset(s, s._profile_config)
    same_day_contract = ContractSelection(
        symbol="TSLA", right="call", strike=252.0,
        expiration=today,
        target_delta=0.50, estimated_premium=4.00, dte=0,
    )
    preset.select_contract = MagicMock(return_value=same_day_contract)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate") as sizer, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_not_called()
    preset.can_enter.assert_not_called()


def test_pdt_below_25k_2trades_not_same_day_runs_sizer():
    """Swing's reality: 7+ DTE → is_same_day=False → PDT day-trades-2
    branch doesn't fire. Sizer runs."""
    s = _stub(pv=5000.0, pdt_locked=False, pdt_day_trades=2)
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing()) as sizer, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_called_once()


def test_pdt_below_25k_unlocked_zero_trades_runs_sizer():
    s = _stub(pv=5000.0, pdt_locked=False, pdt_day_trades=0)
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing()) as sizer, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_called_once()


# ═════════════════════════════════════════════════════════════════
# Sizer wiring — kwargs pass-through
# ═════════════════════════════════════════════════════════════════


def test_sizer_called_with_setup_score_as_confidence():
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result(score=0.72)

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing()) as sizer, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    kwargs = sizer.call_args.kwargs
    assert kwargs["confidence"] == 0.72


def test_sizer_called_with_is_same_day_false_for_swing():
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing()) as sizer, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    kwargs = sizer.call_args.kwargs
    assert kwargs["is_same_day_trade"] is False


def test_sizer_called_with_day_trades_remaining():
    s = _stub(pdt_day_trades=1)
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing()) as sizer, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    kwargs = sizer.call_args.kwargs
    assert kwargs["day_trades_remaining"] == 2  # 3 - 1


def test_sizer_called_with_growth_mode_from_config():
    s = _stub(growth_mode=False)
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing()) as sizer, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    kwargs = sizer.call_args.kwargs
    assert kwargs["growth_mode_config"] is False


def test_sizer_called_with_exposure_from_risk_manager():
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    s._risk_manager.check_portfolio_exposure.return_value = {
        "exposure_dollars": 1234.56,
        "allowed": True, "exposure_pct": 4.1,
        "limit_pct": 20.0, "message": "ok",
    }
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing()) as sizer, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    kwargs = sizer.call_args.kwargs
    assert kwargs["current_exposure"] == 1234.56


def test_risk_manager_exception_falls_back_to_zero_exposure():
    """If risk_manager.check_portfolio_exposure raises, sizer still runs
    with exposure_dollars=0.0."""
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    s._risk_manager.check_portfolio_exposure.side_effect = (
        RuntimeError("DB down")
    )
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing()) as sizer, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_called_once()
    kwargs = sizer.call_args.kwargs
    assert kwargs["current_exposure"] == 0.0


# ═════════════════════════════════════════════════════════════════
# Sizer rejection
# ═════════════════════════════════════════════════════════════════


def test_sizer_blocked_skips_can_enter():
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_blocked_sizing(reason="HALT: drawdown")), \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    preset.can_enter.assert_not_called()


def test_sizer_zero_contracts_skips_can_enter():
    """A non-blocked-but-zero-contracts result is still treated as
    a skip-with-log (the sizer's `_blocked` helper sets blocked=True
    and contracts=0 together, but D2's check is `or` so either flag
    skips)."""
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    zero_unblocked = SizingResult(
        contracts=0, base_risk=0, confidence_risk=0,
        after_drawdown_halving=0, after_pdt_halving=0,
        final_risk=0, premium_per_contract=400.0,
        halvings_applied=[], blocked=False, block_reason="",
    )
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=zero_unblocked), \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    preset.can_enter.assert_not_called()


def test_sizer_approves_then_can_enter_runs():
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing(contracts=3)), \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    preset.can_enter.assert_called_once()


def test_sizer_block_reason_in_log(caplog):
    import logging
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_blocked_sizing(
                   reason="DAY HALT: down 16% today")), \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        caplog.set_level(logging.INFO, logger="options-bot.strategy.v2")
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    assert any(
        "DAY HALT" in r.message and "sizer blocked" in r.message
        for r in caplog.records
    )


# ═════════════════════════════════════════════════════════════════
# can_enter wiring
# ═════════════════════════════════════════════════════════════════


def test_can_enter_proposed_contracts_from_sizer_in_live():
    """In live mode, proposed_contracts == sizing.contracts (not 1)."""
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing(contracts=4)), \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    kwargs = preset.can_enter.call_args.kwargs
    assert kwargs["proposed_contracts"] == 4


def test_can_enter_proposed_contracts_one_in_signal_only():
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate") as sizer, \
         patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert"), \
         patch("strategies.v2_strategy.config.EXECUTION_MODE",
               "signal_only"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_not_called()
    kwargs = preset.can_enter.call_args.kwargs
    assert kwargs["proposed_contracts"] == 1


def test_can_enter_rejection_after_sizer_ran():
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    preset.can_enter.return_value = CapCheckResult(
        approved=False, approved_contracts=0,
        block_reason="max_concurrent_positions", notes=[],
    )
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing()) as sizer, \
         patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_called_once()  # sizer DID run
    preset.can_enter.assert_called_once()
    rec.assert_not_called()  # but record_signal didn't


# ═════════════════════════════════════════════════════════════════
# Mode-specific behavior
# ═════════════════════════════════════════════════════════════════


def test_signal_only_skips_sizer_and_pdt():
    s = _stub(pv=5000.0, pdt_locked=True)  # would block live; doesn't here
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate") as sizer, \
         patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE",
               "signal_only"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_not_called()
    rec.assert_called_once()
    send.assert_called_once()


def test_live_mode_full_path_submits_and_alerts():
    """D2 sizing → cap_check → D3 submission → send_entry_alert.

    Pre-D3 this asserted send.assert_not_called() — that held by
    accident because missing create_order/submit_order caused
    AttributeError, swallowed by the outer try/except. With D3's
    stub extension in place, the live path actually submits and
    fires Discord, so the assertion is now positive."""
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing(contracts=3)) as sizer, \
         patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_called_once()
    preset.can_enter.assert_called_once()
    s.submit_order.assert_called_once()
    send.assert_called_once()
    assert send.call_args.kwargs["mode"] == "live"
    # record_signal still NOT called for live (executed trades use
    # the trades table + scorer for learning, not signal_outcomes).
    rec.assert_not_called()


def test_shadow_mode_full_path_submits_and_alerts():
    """Shadow mirror of live: submit goes through the simulator,
    send_entry_alert fires with mode='shadow'.

    Note: _dispatch_entry_order reads self._execution_mode (set in
    initialize()) to choose shadow vs live. The D2 stub doesn't set
    it (defaults to 'live'); shadow tests must set it explicitly."""
    s = _stub()
    s._execution_mode = "shadow"
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing(contracts=3)) as sizer, \
         patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "shadow"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_called_once()
    preset.can_enter.assert_called_once()
    s._shadow_sim.submit_entry.assert_called_once()
    send.assert_called_once()
    assert send.call_args.kwargs["mode"] == "shadow"
    rec.assert_not_called()


# ═════════════════════════════════════════════════════════════════
# Integration
# ═════════════════════════════════════════════════════════════════


def test_full_flow_live_submits_order_and_alerts():
    """End-to-end live: PDT clear, sizer approves, cap_check approves,
    effective_mode=live → submit_order + create_order called,
    send_entry_alert fired with mode='live', record_signal NOT
    called, _recent_entries_by_symbol_direction updated.

    Pre-D3 this test asserted on a "deferred to Phase 1b" warning
    message that no longer exists — D3 replaced the warning-and-skip
    block with actual submission. Renamed and rewritten to match
    the new behavior."""
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing(contracts=3)), \
         patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    s.create_order.assert_called_once()
    s.submit_order.assert_called_once()
    send.assert_called_once()
    assert send.call_args.kwargs["mode"] == "live"
    rec.assert_not_called()
    # _recent_entries_by_symbol_direction updated for the symbol
    # via the post-submit state-tracking in D3.
    assert "TSLA:bullish" in s._recent_entries_by_symbol_direction


def test_full_flow_signal_only_records_and_sends():
    s = _stub()
    preset = _attach_swing_preset(s, s._profile_config)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate") as sizer, \
         patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE",
               "signal_only"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sizer.assert_not_called()
    rec.assert_called_once()
    send.assert_called_once()
    # Verify proposed_contracts=1 made it through to send_entry_alert
    # via cap_result.approved_contracts (the default _attach helper
    # returns approved_contracts=2; the alert reads from cap_result,
    # not proposed_contracts directly — so we verify the cap_check
    # call was the one with proposed=1).
    kwargs = preset.can_enter.call_args.kwargs
    assert kwargs["proposed_contracts"] == 1
