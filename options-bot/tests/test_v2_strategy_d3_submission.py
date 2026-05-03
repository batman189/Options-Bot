"""Unit tests for D3 — live entry submission for swing in the new
pipeline.

After D3, EXECUTION_MODE=live or shadow routes swing through
_submit_new_pipeline_entry → _dispatch_entry_order → real
submit_order (or _shadow_sim.submit_entry). Discord alerts fire for
both modes. record_signal stays signal_only-only.

Coverage:
  - _dispatch_entry_order helper (live + shadow paths)
  - _submit_new_pipeline_entry pre-half (asset / limit_price /
    _entry_meta shape)
  - on_filled_order BasePreset isinstance branch
  - Mode-specific behavior in _run_new_preset_iteration
  - Failure resilience (PDT rejection, submit exception, shadow
    quote-unavailable)
  - Integration flows for live, shadow, and signal_only

Run via:
    python -m pytest tests/test_v2_strategy_d3_submission.py -v
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from market.context import MarketSnapshot, Regime, TimeOfDay  # noqa: E402
from profiles.base_preset import (  # noqa: E402
    BasePreset,
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
from strategies.v2_strategy import (  # noqa: E402
    EntrySubmissionResult,
    V2Strategy,
)


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


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Per-test tmp DB with trades schema, DB_PATH patched for the
    new-pipeline DB queries (_build_live_profile_state etc.).

    Note: on_filled_order opens its own connection at v2:1212 using a
    HARDCODED `Path(__file__).parent.parent / "db" / "options_bot.db"`
    path — bypassing this DB_PATH patch. Tests that call
    on_filled_order pollute the PRODUCTION DB. The teardown below
    cleans up any test-prefixed rows so the legacy invariant test
    (test_pipeline_trace.py 27B.2) doesn't see lowercase 'call'/'put'
    rows our tests write. See PHASE_1_FOLLOWUPS.md
    "on_filled_order uses hardcoded DB path".
    """
    db_path = tmp_path / "test.db"
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.executescript(_TRADES_SCHEMA)
        conn.commit()
    monkeypatch.setattr(
        "strategies.v2_strategy.DB_PATH", db_path,
    )
    yield db_path
    # Teardown: clean up any test rows that on_filled_order wrote to
    # the production DB via its hardcoded path.
    prod_db = Path(__file__).parent.parent / "db" / "options_bot.db"
    if prod_db.exists():
        try:
            with closing(sqlite3.connect(str(prod_db))) as conn:
                conn.execute(
                    "DELETE FROM trades WHERE id LIKE 't-%' "
                    "OR id LIKE 'test-%'"
                )
                conn.commit()
        except Exception:
            pass  # Best-effort cleanup; never fail the test on this


def _profile_config(
    name: str = "test-profile",
    preset: str = "swing",
    symbols: list | None = None,
    max_capital: float = 10000.0,
) -> ProfileConfig:
    return ProfileConfig(
        name=name, preset=preset,
        symbols=symbols or ["TSLA"],
        max_capital_deployed=max_capital,
    )


def _swing_contract(strike: float = 252.0) -> ContractSelection:
    return ContractSelection(
        symbol="TSLA", right="call", strike=strike,
        expiration=date(2026, 5, 9),
        target_delta=0.50, estimated_premium=4.00, dte=7,
    )


def _market_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        regime=Regime.TRENDING_UP,
        time_of_day=TimeOfDay.OPEN,
        timestamp="2026-05-02T10:30:00+00:00",
        vix_level=20.0,
    )


def _scan_result(symbol: str = "TSLA", setup_type: str = "momentum",
                 score: float = 0.60, direction: str = "bullish"):
    setup = SetupScore(
        setup_type=setup_type, score=score,
        reason="test", direction=direction,
    )
    return SimpleNamespace(symbol=symbol, setups=[setup]), setup


def _stub(execution_mode: str = "live"):
    """V2Strategy stub with all D3-required attributes set."""
    s = V2Strategy.__new__(V2Strategy)
    pc = _profile_config()
    s.symbol = "TSLA"
    s.profile_name = "test-profile"
    s._config = {"preset": "swing", "growth_mode": True}
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
    s._execution_mode = execution_mode
    s.get_portfolio_value = MagicMock(return_value=30000.0)
    s._day_start_value = 30000.0
    s._starting_balance = 30000.0
    s._pdt_locked = False
    s._pdt_day_trades = 0
    s._pdt_buying_power = 999999.0
    s._pdt_no_same_day_exit = set()
    s._risk_manager = MagicMock()
    s._risk_manager.check_portfolio_exposure.return_value = {
        "exposure_dollars": 0.0, "allowed": True,
        "exposure_pct": 0.0, "limit_pct": 20.0, "message": "ok",
    }
    s.create_order = MagicMock(
        return_value=MagicMock(identifier="alpaca-d3-test"),
    )
    s.submit_order = MagicMock()
    s._shadow_sim = MagicMock()
    s._shadow_sim.submit_entry = MagicMock(return_value="shadow-d3-test")
    s._trade_manager = MagicMock()
    s._trade_id_map = {}
    s._scorer = MagicMock()
    return s


def _attach_swing(stub):
    preset = SwingPreset(
        config=stub._profile_config,
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
        return_value=MagicMock(),  # the chain itself isn't read again
    )
    return preset


def _ok_sizing(contracts: int = 2) -> SizingResult:
    return SizingResult(
        contracts=contracts, base_risk=1200.0,
        confidence_risk=720.0, after_drawdown_halving=720.0,
        after_pdt_halving=720.0, final_risk=720.0,
        premium_per_contract=400.0, halvings_applied=[],
        blocked=False, block_reason="",
    )


def _entry_meta_for(
    contract: ContractSelection,
    quantity: int = 2,
    profile=None,
    profile_name: str = "swing",
    trade_id: str = "test-trade-id",
) -> dict:
    """Build a minimal _entry_meta for _dispatch_entry_order tests."""
    return {
        "trade_id": trade_id,
        "profile_id": "test-profile-id",
        "symbol": contract.symbol,
        "direction": contract.right,
        "strike": contract.strike,
        "expiration": contract.expiration.isoformat(),
        "quantity": quantity,
        "estimated_price": round(contract.estimated_premium, 2),
        "setup_type": "momentum",
        "confidence_score": 0.60,
        "regime": "TRENDING_UP",
        "vix_level": 20.0,
        "is_same_day": False,
        "profile": profile or MagicMock(),
        "profile_name": profile_name,
        "setup_score": 0.60,
    }


# ═════════════════════════════════════════════════════════════════
# _dispatch_entry_order helper
# ═════════════════════════════════════════════════════════════════


def test_dispatch_live_calls_submit_order_and_seeds_map():
    s = _stub(execution_mode="live")
    order = MagicMock(identifier="alpaca-live-1")
    s.create_order.return_value = order
    meta = _entry_meta_for(_swing_contract())

    result = s._dispatch_entry_order(order, meta, "swing", "trade-1")

    assert result.submitted is True
    assert result.trade_id == "trade-1"
    s.submit_order.assert_called_once_with(order)
    assert "alpaca-live-1" in s._trade_id_map
    assert s._trade_id_map["alpaca-live-1"] is meta
    assert s._last_entry_time["swing"] is not None


def test_dispatch_shadow_pre_seeds_map_then_submits():
    s = _stub(execution_mode="shadow")
    order = MagicMock(identifier="alpaca-shadow-1")
    meta = _entry_meta_for(_swing_contract())

    result = s._dispatch_entry_order(order, meta, "swing", "trade-2")

    assert result.submitted is True
    s._shadow_sim.submit_entry.assert_called_once()
    # Shadow pre-seeds with the synthetic shadow id.
    shadow_seeded_keys = [
        k for k in s._trade_id_map if k.startswith("shadow-")
    ]
    assert len(shadow_seeded_keys) == 1


def test_dispatch_returns_entry_submission_result_with_trade_id():
    s = _stub()
    order = MagicMock(identifier="x")
    meta = _entry_meta_for(_swing_contract())

    result = s._dispatch_entry_order(order, meta, "swing", "trade-3")

    assert isinstance(result, EntrySubmissionResult)
    assert result.trade_id == "trade-3"


def test_dispatch_invalid_alpaca_id_blocks():
    """submit_order returns but order has no usable identifier →
    block with reason invalid_alpaca_id."""
    s = _stub(execution_mode="live")
    order = MagicMock(identifier=None)  # not a usable string
    s.create_order.return_value = order
    meta = _entry_meta_for(_swing_contract())

    result = s._dispatch_entry_order(order, meta, "swing", "trade-4")

    assert result.submitted is False
    assert result.block_reason == "invalid_alpaca_id"


def test_dispatch_shadow_quote_unavailable_rolls_back():
    """_shadow_sim.submit_entry returns None (quote unavailable) →
    map entry rolled back, blocked result."""
    s = _stub(execution_mode="shadow")
    s._shadow_sim.submit_entry.return_value = None
    order = MagicMock(identifier="x")
    meta = _entry_meta_for(_swing_contract())

    pre_map_size = len(s._trade_id_map)
    result = s._dispatch_entry_order(order, meta, "swing", "trade-5")

    assert result.submitted is False
    assert result.block_reason == "shadow_quote_unavailable"
    assert len(s._trade_id_map) == pre_map_size  # rolled back


# ═════════════════════════════════════════════════════════════════
# _submit_new_pipeline_entry pre-half
# ═════════════════════════════════════════════════════════════════


def test_submit_new_pipeline_constructs_asset_from_contract_selection():
    """Asset built with contract.expiration as date (no strptime)."""
    s = _stub()
    preset = _attach_swing(s)
    contract = _swing_contract()
    setup = SetupScore(setup_type="momentum", score=0.6,
                       reason="t", direction="bullish")
    decision = EntryDecision(should_enter=True, reason="ok",
                             direction="bullish")

    s._submit_new_pipeline_entry(
        contract, 2, setup, preset, _market_snapshot(), decision,
        entry_underlying_price=250.0,
    )

    # First positional arg to create_order is the Asset.
    call_args = s.create_order.call_args
    asset = call_args.args[0]
    assert asset.symbol == "TSLA"
    assert asset.expiration == contract.expiration  # date passed through


def test_submit_new_pipeline_limit_price_from_estimated_premium():
    """limit_price = round(contract.estimated_premium, 2)."""
    s = _stub()
    preset = _attach_swing(s)
    contract = ContractSelection(
        symbol="TSLA", right="call", strike=252.0,
        expiration=date(2026, 5, 9),
        target_delta=0.50, estimated_premium=4.123456, dte=7,
    )
    setup = SetupScore(setup_type="momentum", score=0.6,
                       reason="t", direction="bullish")
    decision = EntryDecision(should_enter=True, reason="ok",
                             direction="bullish")

    s._submit_new_pipeline_entry(
        contract, 2, setup, preset, _market_snapshot(), decision,
        entry_underlying_price=250.0,
    )

    kwargs = s.create_order.call_args.kwargs
    assert kwargs["limit_price"] == 4.12  # rounded


def test_submit_new_pipeline_create_order_kwargs():
    s = _stub()
    preset = _attach_swing(s)
    contract = _swing_contract()
    setup = SetupScore(setup_type="momentum", score=0.6,
                       reason="t", direction="bullish")
    decision = EntryDecision(should_enter=True, reason="ok",
                             direction="bullish")

    s._submit_new_pipeline_entry(
        contract, 3, setup, preset, _market_snapshot(), decision,
        entry_underlying_price=250.0,
    )

    call_args = s.create_order.call_args
    # Positional: (asset, proposed_contracts)
    assert call_args.args[1] == 3
    kwargs = call_args.kwargs
    assert kwargs["side"] == "buy_to_open"
    assert kwargs["time_in_force"] == "day"


def test_submit_new_pipeline_entry_meta_keys():
    """_entry_meta has all 16 keys the legacy on_filled_order expects."""
    s = _stub()
    preset = _attach_swing(s)
    contract = _swing_contract()
    setup = SetupScore(setup_type="momentum", score=0.72,
                       reason="t", direction="bullish")
    decision = EntryDecision(should_enter=True, reason="ok",
                             direction="bullish")

    s._submit_new_pipeline_entry(
        contract, 2, setup, preset, _market_snapshot(), decision,
        entry_underlying_price=250.0,
    )

    # The meta dict is the value associated with the alpaca id key in
    # _trade_id_map (the live path writes it post-submit).
    written = list(s._trade_id_map.values())
    assert len(written) == 1
    meta = written[0]
    # D4 added entry_underlying_price; 17 keys total post-D4.
    expected_keys = {
        "trade_id", "profile_id", "symbol", "direction", "strike",
        "expiration", "quantity", "estimated_price", "setup_type",
        "confidence_score", "regime", "vix_level", "is_same_day",
        "profile", "profile_name", "setup_score",
        "entry_underlying_price",
    }
    assert set(meta.keys()) == expected_keys


def test_submit_new_pipeline_entry_meta_profile_is_basepreset():
    s = _stub()
    preset = _attach_swing(s)
    contract = _swing_contract()
    setup = SetupScore(setup_type="momentum", score=0.6,
                       reason="t", direction="bullish")
    decision = EntryDecision(should_enter=True, reason="ok",
                             direction="bullish")

    s._submit_new_pipeline_entry(
        contract, 2, setup, preset, _market_snapshot(), decision,
        entry_underlying_price=250.0,
    )

    meta = list(s._trade_id_map.values())[0]
    assert isinstance(meta["profile"], BasePreset)
    assert meta["profile"] is preset


def test_submit_new_pipeline_entry_meta_expiration_is_iso_string():
    s = _stub()
    preset = _attach_swing(s)
    contract = _swing_contract()
    setup = SetupScore(setup_type="momentum", score=0.6,
                       reason="t", direction="bullish")
    decision = EntryDecision(should_enter=True, reason="ok",
                             direction="bullish")

    s._submit_new_pipeline_entry(
        contract, 2, setup, preset, _market_snapshot(), decision,
        entry_underlying_price=250.0,
    )

    meta = list(s._trade_id_map.values())[0]
    # Date 2026-05-09 → ISO "2026-05-09" so on_filled_order's
    # strptime parser handles it.
    assert meta["expiration"] == "2026-05-09"
    assert isinstance(meta["expiration"], str)


def test_submit_new_pipeline_entry_meta_confidence_is_setup_score():
    """D2 decision: confidence=setup.score (no Scorer)."""
    s = _stub()
    preset = _attach_swing(s)
    contract = _swing_contract()
    setup = SetupScore(setup_type="momentum", score=0.83,
                       reason="t", direction="bullish")
    decision = EntryDecision(should_enter=True, reason="ok",
                             direction="bullish")

    s._submit_new_pipeline_entry(
        contract, 2, setup, preset, _market_snapshot(), decision,
        entry_underlying_price=250.0,
    )

    meta = list(s._trade_id_map.values())[0]
    assert meta["confidence_score"] == 0.83


# ═════════════════════════════════════════════════════════════════
# Failure resilience
# ═════════════════════════════════════════════════════════════════


def test_submit_pdt_rejection_sets_lock():
    s = _stub()
    preset = _attach_swing(s)
    s.submit_order.side_effect = RuntimeError(
        "Pattern Day Trading rule violation"
    )
    contract = _swing_contract()
    setup = SetupScore(setup_type="momentum", score=0.6,
                       reason="t", direction="bullish")
    decision = EntryDecision(should_enter=True, reason="ok",
                             direction="bullish")

    result = s._submit_new_pipeline_entry(
        contract, 2, setup, preset, _market_snapshot(), decision,
        entry_underlying_price=250.0,
    )

    assert result.submitted is False
    assert result.block_reason == "pdt_rejected_at_submit"
    assert s._pdt_locked is True


def test_submit_other_exception_returns_typed_block_reason():
    s = _stub()
    preset = _attach_swing(s)
    s.submit_order.side_effect = ConnectionError("alpaca down")
    contract = _swing_contract()
    setup = SetupScore(setup_type="momentum", score=0.6,
                       reason="t", direction="bullish")
    decision = EntryDecision(should_enter=True, reason="ok",
                             direction="bullish")

    result = s._submit_new_pipeline_entry(
        contract, 2, setup, preset, _market_snapshot(), decision,
        entry_underlying_price=250.0,
    )

    assert result.submitted is False
    assert result.block_reason == "submit_exception: ConnectionError"
    assert s._pdt_locked is False  # not a PDT exception


# ═════════════════════════════════════════════════════════════════
# on_filled_order BasePreset isinstance branch
# ═════════════════════════════════════════════════════════════════


def test_on_filled_order_skips_add_position_for_basepreset():
    s = _stub()
    preset = SwingPreset(
        config=s._profile_config,
        macro_fetcher=lambda symbol, lookahead: [],
    )
    # Pre-seed _trade_id_map with new-pipeline entry meta.
    meta = _entry_meta_for(_swing_contract(), profile=preset,
                           profile_name="swing", trade_id="t-new-1")
    s._trade_id_map["alpaca-fill-1"] = meta
    fake_order = MagicMock(identifier="alpaca-fill-1", side="buy_to_open")
    fake_position = MagicMock(asset=MagicMock())

    s.on_filled_order(fake_position, fake_order, 4.10, 2, 100)

    s._trade_manager.add_position.assert_not_called()


def test_on_filled_order_calls_add_position_for_baseprofile():
    """Legacy BaseProfile path unchanged: add_position is called."""
    from profiles.base_profile import BaseProfile
    s = _stub()
    legacy_profile = MagicMock(spec=BaseProfile)
    legacy_profile.name = "momentum"
    meta = _entry_meta_for(_swing_contract(), profile=legacy_profile,
                           profile_name="momentum", trade_id="t-leg-1")
    s._trade_id_map["alpaca-fill-leg-1"] = meta
    fake_order = MagicMock(
        identifier="alpaca-fill-leg-1", side="buy_to_open",
    )
    fake_position = MagicMock(asset=MagicMock())

    s.on_filled_order(fake_position, fake_order, 4.10, 2, 100)

    s._trade_manager.add_position.assert_called_once()


def test_on_filled_order_pdt_mark_applies_to_basepreset(_isolate_db):
    s = _stub()
    s._pdt_day_trades = 2  # triggers hold-overnight mark
    s.get_portfolio_value = MagicMock(return_value=10000.0)  # < 25k
    preset = SwingPreset(
        config=s._profile_config,
        macro_fetcher=lambda symbol, lookahead: [],
    )
    meta = _entry_meta_for(_swing_contract(), profile=preset,
                           profile_name="swing", trade_id="t-pdt-1")
    s._trade_id_map["alpaca-pdt-1"] = meta
    fake_order = MagicMock(identifier="alpaca-pdt-1", side="buy_to_open")
    fake_position = MagicMock(asset=MagicMock())

    s.on_filled_order(fake_position, fake_order, 4.00, 2, 100)

    assert "t-pdt-1" in s._pdt_no_same_day_exit


# ═════════════════════════════════════════════════════════════════
# Mode-specific behavior in _run_new_preset_iteration
# ═════════════════════════════════════════════════════════════════


def test_live_mode_submits_alerts_no_record():
    s = _stub(execution_mode="live")
    preset = _attach_swing(s)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing(contracts=2)), \
         patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    s.submit_order.assert_called_once()
    send.assert_called_once()
    assert send.call_args.kwargs["mode"] == "live"
    rec.assert_not_called()


def test_shadow_mode_submits_alerts_no_record():
    s = _stub(execution_mode="shadow")
    preset = _attach_swing(s)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing(contracts=2)), \
         patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "shadow"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    s._shadow_sim.submit_entry.assert_called_once()
    send.assert_called_once()
    assert send.call_args.kwargs["mode"] == "shadow"
    rec.assert_not_called()


def test_signal_only_does_not_submit():
    s = _stub(execution_mode="signal_only")
    preset = _attach_swing(s)
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
    s.submit_order.assert_not_called()
    s._shadow_sim.submit_entry.assert_not_called()
    rec.assert_called_once()
    send.assert_called_once()
    assert send.call_args.kwargs["mode"] == "signal_only"


def test_submission_failure_skips_alert():
    s = _stub(execution_mode="live")
    preset = _attach_swing(s)
    s.submit_order.side_effect = ConnectionError("alpaca down")
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing(contracts=2)), \
         patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    rec.assert_not_called()
    send.assert_not_called()
    # State NOT updated when submission fails.
    assert "TSLA:bullish" not in s._recent_entries_by_symbol_direction


# ═════════════════════════════════════════════════════════════════
# Integration
# ═════════════════════════════════════════════════════════════════


def test_integration_live_happy_path():
    s = _stub(execution_mode="live")
    preset = _attach_swing(s)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing(contracts=2)), \
         patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    s.create_order.assert_called_once()
    s.submit_order.assert_called_once()
    send.assert_called_once()
    assert "alpaca-d3-test" in s._trade_id_map
    assert "TSLA:bullish" in s._recent_entries_by_symbol_direction


def test_integration_shadow_happy_path():
    s = _stub(execution_mode="shadow")
    preset = _attach_swing(s)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.size_calculate",
               return_value=_ok_sizing(contracts=2)), \
         patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "shadow"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    s._shadow_sim.submit_entry.assert_called_once()
    send.assert_called_once()
    assert "TSLA:bullish" in s._recent_entries_by_symbol_direction


def test_integration_signal_only_happy_path():
    """signal_only path (D2 unchanged): record + send, no submit."""
    s = _stub(execution_mode="signal_only")
    preset = _attach_swing(s)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE",
               "signal_only"):
        s._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    s.submit_order.assert_not_called()
    rec.assert_called_once()
    send.assert_called_once()
    assert send.call_args.kwargs["mode"] == "signal_only"
