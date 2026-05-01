"""Integration-style tests for V2Strategy's new BasePreset pipeline (C5b).

Verifies the new pipeline activates for swing / 0dte_asymmetric, routes
through evaluate_entry → select_contract → can_enter → record_signal +
send_entry_alert in signal_only mode, and stays clear for legacy presets.

V2Strategy is constructed via __new__() to bypass Lumibot init (matches
the pattern in tests/test_pipeline_trace.py for the same class). All
external services (record_signal, send_entry_alert, chain builder,
UnifiedDataClient) are patched.

Run via:
    python -m pytest tests/test_v2_strategy_new_pipeline.py -v
"""

from __future__ import annotations

import sys
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
from profiles.zero_dte_asymmetric import ZeroDteAsymmetricPreset  # noqa: E402
from scanner.setups import SetupScore  # noqa: E402
from sizing.cap_check import CapCheckResult  # noqa: E402
from strategies.v2_strategy import V2Strategy  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Fixtures — minimal V2Strategy stub
# ─────────────────────────────────────────────────────────────────


def _profile_config(
    name: str = "test-profile",
    preset: str = "swing",
    symbols: list | None = None,
    max_capital: float = 5000.0,
    mode: str = "signal_only",
) -> ProfileConfig:
    return ProfileConfig(
        name=name,
        preset=preset,
        symbols=symbols or ["TSLA"],
        max_capital_deployed=max_capital,
        mode=mode,
    )


def _scan_result(symbol: str = "TSLA", setup_type: str = "momentum",
                 score: float = 0.60, direction: str = "bullish"):
    setup = SetupScore(
        setup_type=setup_type, score=score,
        reason="test", direction=direction,
    )
    return SimpleNamespace(symbol=symbol, setups=[setup]), setup


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


def _make_chain(
    symbol: str = "TSLA",
    underlying: float = 250.0,
    right: str = "call",
    strike: float = 252.0,
    delta: float = 0.50,
) -> OptionChain:
    contract = OptionContract(
        symbol=symbol, right=right, strike=strike,
        expiration=date(2026, 5, 8),
        bid=3.95, ask=4.05, mid=4.00,
        delta=delta, iv=0.30,
        open_interest=2000, volume=1000,
    )
    return OptionChain(
        symbol=symbol, underlying_price=underlying,
        contracts=[contract],
        snapshot_time=datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc),
    )


def _build_v2_stub(
    preset_name: str = "swing",
    profile_config: ProfileConfig | None = None,
):
    """Construct a V2Strategy stub via __new__, set just the attributes
    the new-pipeline path consults. Bypasses Lumibot init."""
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
    return stub


def _attach_new_preset(stub, preset_class, profile_config: ProfileConfig):
    """Attach a real BasePreset instance to the stub. Dispatches per
    preset class because SwingPreset and ZeroDteAsymmetricPreset accept
    different fetcher kwargs (matches V2Strategy.initialize)."""
    if preset_class is SwingPreset:
        preset = SwingPreset(
            config=profile_config,
            macro_fetcher=lambda symbol, lookahead: [],
        )
    elif preset_class is ZeroDteAsymmetricPreset:
        preset = ZeroDteAsymmetricPreset(
            config=profile_config,
            macro_fetcher=lambda symbol, lookahead: [],
            bars_fetcher=stub._client.get_stock_bars,
            vix_spike_fetcher=lambda: None,
            now_fetcher=lambda: datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc),
        )
    else:
        raise AssertionError(f"unsupported preset_class {preset_class!r}")
    stub._new_preset = preset
    return preset


# ═════════════════════════════════════════════════════════════════
# Routing — is_new_preset gating
# ═════════════════════════════════════════════════════════════════


def test_routing_swing_attaches_new_preset_in_init_path():
    """Verifies the registry/gating flow used by initialize()."""
    from profiles.preset_registry import is_new_preset, get_preset_class
    assert is_new_preset("swing") is True
    cls = get_preset_class("swing")
    assert cls is SwingPreset


def test_routing_zero_dte_attaches_new_preset_in_init_path():
    from profiles.preset_registry import is_new_preset, get_preset_class
    assert is_new_preset("0dte_asymmetric") is True
    cls = get_preset_class("0dte_asymmetric")
    assert cls is ZeroDteAsymmetricPreset


def test_routing_legacy_preset_not_in_registry():
    from profiles.preset_registry import is_new_preset
    for legacy in (
        "momentum", "mean_reversion", "catalyst",
        "scalp_0dte", "tsla_swing",
    ):
        assert is_new_preset(legacy) is False


def test_routing_new_preset_attribute_starts_none_for_legacy():
    """Bare V2Strategy stub for a legacy preset has _new_preset=None.
    Legacy preset names are not in PRESET_REGISTRY and don't trigger
    ProfileConfig construction at all (which would also fail since
    ProfileConfig.preset is a Literal of swing/0dte_asymmetric only).
    Stub bypasses _build_v2_stub's profile_config default and sets
    _profile_config=None to mirror initialize() behavior for legacy."""
    stub = V2Strategy.__new__(V2Strategy)
    stub.symbol = "TSLA"
    stub.profile_name = "test-profile"
    stub._config = {"preset": "momentum"}
    stub._scan_symbols = ["TSLA"]
    stub.parameters = {"profile_id": "test-profile-id"}
    stub._client = MagicMock()
    stub._last_entry_time = {}
    stub._last_exit_reason = {}
    stub._recent_entries_by_symbol_direction = {}
    stub._thesis_break_streaks = {}
    stub._recent_exits_by_symbol = {}
    stub._profile_config = None
    stub._new_preset = None
    assert stub._new_preset is None


def test_routing_new_preset_attribute_set_for_swing():
    """When the test fixture attaches the preset, _new_preset is the
    BasePreset instance."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    assert stub._new_preset is preset
    assert isinstance(stub._new_preset, SwingPreset)


# ═════════════════════════════════════════════════════════════════
# is_active_now gate
# ═════════════════════════════════════════════════════════════════


def test_is_active_now_false_skips_processing():
    """ZeroDteAsymmetricPreset returns False outside 9:35-13:30 ET.
    The orchestrator must skip the per-symbol loop entirely."""
    pc = _profile_config(preset="0dte_asymmetric", symbols=["SPY"])
    stub = _build_v2_stub(preset_name="0dte_asymmetric", profile_config=pc)
    preset = ZeroDteAsymmetricPreset(
        config=pc,
        # 8:00 ET (before window opens at 9:35)
        now_fetcher=lambda: datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
    )
    stub._new_preset = preset
    sr, setup = _scan_result(symbol="SPY")

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send:
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    rec.assert_not_called()
    send.assert_not_called()


def test_is_active_now_true_runs_processing():
    """SwingPreset.is_active_now is always True. With evaluate_entry
    rejecting (default _scan_result has no fetchers configured),
    record_signal still shouldn't fire — but the loop should at least
    invoke evaluate_entry."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    sr, setup = _scan_result()

    spy_evaluate = MagicMock(wraps=preset.evaluate_entry)
    preset.evaluate_entry = spy_evaluate

    with patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    spy_evaluate.assert_called_once()


# ═════════════════════════════════════════════════════════════════
# evaluate_entry rejection path
# ═════════════════════════════════════════════════════════════════


def test_evaluate_entry_rejection_skips_chain_build():
    """When evaluate_entry returns should_enter=False, the chain
    builder must not be called."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    preset.evaluate_entry = MagicMock(return_value=EntryDecision(
        should_enter=False, reason="setup score too low",
        direction="bullish",
    ))
    sr, setup = _scan_result()

    spy_chain = MagicMock(wraps=stub._build_option_chain_for_new_preset)
    stub._build_option_chain_for_new_preset = spy_chain

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send:
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    spy_chain.assert_not_called()
    rec.assert_not_called()
    send.assert_not_called()


def test_evaluate_entry_exception_continues_loop():
    """An exception inside evaluate_entry is caught and the next
    symbol still gets processed."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    call_count = {"n": 0}

    def maybe_raise(symbol, setup, snap, state):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return EntryDecision(
            should_enter=False, reason="ok", direction="bullish",
        )
    preset.evaluate_entry = maybe_raise

    sr1, s1 = _scan_result(symbol="TSLA")
    sr2, s2 = _scan_result(symbol="NVDA")

    with patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert"):
        stub._run_new_preset_iteration(
            [(sr1, s1), (sr2, s2)], _market_snapshot(), None,
        )

    assert call_count["n"] == 2


# ═════════════════════════════════════════════════════════════════
# select_contract rejection path
# ═════════════════════════════════════════════════════════════════


def test_select_contract_none_skips_can_enter():
    """When select_contract returns None, can_enter must not be called."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    preset.evaluate_entry = MagicMock(return_value=EntryDecision(
        should_enter=True, reason="ok", direction="bullish",
    ))
    preset.select_contract = MagicMock(return_value=None)
    spy_can_enter = MagicMock(wraps=preset.can_enter)
    preset.can_enter = spy_can_enter

    stub._build_option_chain_for_new_preset = MagicMock(
        return_value=_make_chain(),
    )
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send:
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    spy_can_enter.assert_not_called()
    rec.assert_not_called()
    send.assert_not_called()


def test_chain_build_failure_skips_select_contract():
    """When the chain builder returns None, select_contract must
    not be called."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    preset.evaluate_entry = MagicMock(return_value=EntryDecision(
        should_enter=True, reason="ok", direction="bullish",
    ))
    spy_select = MagicMock(wraps=preset.select_contract)
    preset.select_contract = spy_select

    stub._build_option_chain_for_new_preset = MagicMock(return_value=None)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send:
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    spy_select.assert_not_called()
    rec.assert_not_called()
    send.assert_not_called()


# ═════════════════════════════════════════════════════════════════
# cap_check rejection path
# ═════════════════════════════════════════════════════════════════


def _good_contract() -> ContractSelection:
    return ContractSelection(
        symbol="TSLA", right="call", strike=252.0,
        expiration=date(2026, 5, 8),
        target_delta=0.50, estimated_premium=4.00, dte=7,
    )


def test_cap_check_rejection_blocks_emission():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    preset.evaluate_entry = MagicMock(return_value=EntryDecision(
        should_enter=True, reason="ok", direction="bullish",
    ))
    preset.select_contract = MagicMock(return_value=_good_contract())
    preset.can_enter = MagicMock(return_value=CapCheckResult(
        approved=False, approved_contracts=0,
        block_reason="profile_disabled", notes=[],
    ))

    stub._build_option_chain_for_new_preset = MagicMock(
        return_value=_make_chain(),
    )
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send:
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    rec.assert_not_called()
    send.assert_not_called()


def test_cap_check_called_with_proposed_contracts_one():
    """C5b decision: proposed_contracts hardcoded to 1 in Phase 1a."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    preset.evaluate_entry = MagicMock(return_value=EntryDecision(
        should_enter=True, reason="ok", direction="bullish",
    ))
    preset.select_contract = MagicMock(return_value=_good_contract())
    spy_can_enter = MagicMock(return_value=CapCheckResult(
        approved=False, approved_contracts=0,
        block_reason="any", notes=[],
    ))
    preset.can_enter = spy_can_enter

    stub._build_option_chain_for_new_preset = MagicMock(
        return_value=_make_chain(),
    )
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    call_kwargs = spy_can_enter.call_args.kwargs
    assert call_kwargs["proposed_contracts"] == 1


# ═════════════════════════════════════════════════════════════════
# Mode resolution
# ═════════════════════════════════════════════════════════════════


def _wire_happy_path(stub, preset, contract: ContractSelection | None = None):
    """Drive evaluate_entry/select_contract/can_enter to the cap-approved
    state — caller supplies external mocks for record/send. Returns the
    contract used (so the caller can assert against it)."""
    contract = contract or _good_contract()
    preset.evaluate_entry = MagicMock(return_value=EntryDecision(
        should_enter=True, reason="ok", direction="bullish",
    ))
    preset.select_contract = MagicMock(return_value=contract)
    preset.can_enter = MagicMock(return_value=CapCheckResult(
        approved=True, approved_contracts=1,
        block_reason="", notes=[],
    ))
    stub._build_option_chain_for_new_preset = MagicMock(
        return_value=_make_chain(),
    )
    return contract


def test_signal_only_mode_swing_calls_record_and_send():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    _wire_happy_path(stub, preset)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    rec.assert_called_once()
    send.assert_called_once()


def test_live_mode_swing_logs_warning_skips_emission():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    _wire_happy_path(stub, preset)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    rec.assert_not_called()
    send.assert_not_called()


def test_shadow_mode_swing_skips_emission():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    _wire_happy_path(stub, preset)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "shadow"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    rec.assert_not_called()
    send.assert_not_called()


def test_zero_dte_in_live_mode_still_routes_signal_only():
    """resolve_preset_mode forces 0dte_asymmetric to signal_only
    regardless of global mode (per ARCHITECTURE.md §4.2 Phase 1a scope).
    """
    pc = _profile_config(preset="0dte_asymmetric", symbols=["SPY"])
    stub = _build_v2_stub(preset_name="0dte_asymmetric", profile_config=pc)
    # Construct preset with now_fetcher inside the 9:35-13:30 ET window
    preset = ZeroDteAsymmetricPreset(
        config=pc,
        # 14:30 UTC = 10:30 ET (April-May, no DST boundary)
        now_fetcher=lambda: datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc),
    )
    stub._new_preset = preset
    _wire_happy_path(stub, preset)
    sr, setup = _scan_result(symbol="SPY")

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    rec.assert_called_once()
    send.assert_called_once()


# ═════════════════════════════════════════════════════════════════
# signal_only happy path — kwargs / signal_id correlation
# ═════════════════════════════════════════════════════════════════


def test_record_signal_kwargs_correct():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    contract = _wire_happy_path(stub, preset)
    sr, setup = _scan_result(setup_type="momentum", direction="bullish")

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert"), \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    kwargs = rec.call_args.kwargs
    assert kwargs["profile_id"] == "test-profile"
    assert kwargs["symbol"] == "TSLA"
    assert kwargs["setup_type"] == "momentum"
    assert kwargs["direction"] == "bullish"
    assert kwargs["contract_strike"] == contract.strike
    assert kwargs["contract_right"] == contract.right
    assert kwargs["entry_premium"] == contract.estimated_premium
    assert kwargs["predicted_at"].tzinfo is not None


def test_send_entry_alert_kwargs_correct():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    contract = _wire_happy_path(stub, preset)
    sr, setup = _scan_result(setup_type="momentum", direction="bullish",
                             score=0.72)

    with patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    kwargs = send.call_args.kwargs
    assert kwargs["profile_config"] is pc
    assert kwargs["symbol"] == "TSLA"
    assert kwargs["setup_type"] == "momentum"
    assert kwargs["direction"] == "bullish"
    assert kwargs["setup_score"] == 0.72
    assert kwargs["contract_strike"] == contract.strike
    assert kwargs["mode"] == "signal_only"
    assert kwargs["contracts"] == 1  # cap_result.approved_contracts


def test_signal_id_is_uuid_v4():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    _wire_happy_path(stub, preset)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert"), \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    sid = rec.call_args.kwargs["signal_id"]
    # UUID v4: 36 chars, version-4 marker at position 14
    assert len(sid) == 36
    assert sid[14] == "4"


def test_signal_id_correlates_record_and_send():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    _wire_happy_path(stub, preset)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal") as rec, \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    rec_sid = rec.call_args.kwargs["signal_id"]
    send_sid = send.call_args.kwargs["signal_id"]
    assert rec_sid == send_sid


def test_recent_entries_dict_updated_on_emission():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    _wire_happy_path(stub, preset)
    sr, setup = _scan_result(symbol="TSLA", direction="bullish")

    with patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert"), \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    assert "TSLA:bullish" in stub._recent_entries_by_symbol_direction


def test_last_entry_time_updated_per_preset():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    _wire_happy_path(stub, preset)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert"), \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    assert preset.name in stub._last_entry_time
    assert stub._last_entry_time[preset.name].tzinfo is not None


# ═════════════════════════════════════════════════════════════════
# Failure resilience
# ═════════════════════════════════════════════════════════════════


def test_record_signal_raises_caught_send_still_called():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    _wire_happy_path(stub, preset)
    sr, setup = _scan_result()

    with patch("strategies.v2_strategy.record_signal",
               side_effect=RuntimeError("db down")), \
         patch("strategies.v2_strategy.send_entry_alert") as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    # Send is independent — record's failure doesn't prevent it.
    send.assert_called_once()


def test_send_entry_alert_raises_caught_loop_continues():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    _wire_happy_path(stub, preset)
    sr1, s1 = _scan_result(symbol="TSLA")
    sr2, s2 = _scan_result(symbol="NVDA")

    with patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert",
               side_effect=RuntimeError("webhook down")) as send, \
         patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        stub._run_new_preset_iteration(
            [(sr1, s1), (sr2, s2)], _market_snapshot(), None,
        )

    # Both iterations attempted to send despite the first raising.
    assert send.call_count == 2


def test_select_contract_raises_caught_loop_continues():
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)
    preset.evaluate_entry = MagicMock(return_value=EntryDecision(
        should_enter=True, reason="ok", direction="bullish",
    ))
    call_count = {"n": 0}

    def maybe_raise(symbol, direction, chain):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("chain parse error")
        return None
    preset.select_contract = maybe_raise

    stub._build_option_chain_for_new_preset = MagicMock(
        return_value=_make_chain(),
    )

    sr1, s1 = _scan_result(symbol="TSLA")
    sr2, s2 = _scan_result(symbol="NVDA")

    with patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert"):
        stub._run_new_preset_iteration(
            [(sr1, s1), (sr2, s2)], _market_snapshot(), None,
        )

    assert call_count["n"] == 2


# ═════════════════════════════════════════════════════════════════
# _build_profile_config helper
# ═════════════════════════════════════════════════════════════════


def test_build_profile_config_max_capital_default():
    """Per DECISION 1: default to 5000.0 when absent from config dict."""
    stub = V2Strategy.__new__(V2Strategy)
    stub.profile_name = "test-profile"
    stub._config = {"preset": "swing"}
    stub._scan_symbols = ["TSLA"]
    stub.parameters = {}

    with patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        pc = stub._build_profile_config()
    assert pc.max_capital_deployed == 5000.0


def test_build_profile_config_max_capital_from_dict():
    stub = V2Strategy.__new__(V2Strategy)
    stub.profile_name = "test-profile"
    stub._config = {"preset": "swing", "max_capital_deployed": 12000.0}
    stub._scan_symbols = ["TSLA"]
    stub.parameters = {}

    with patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        pc = stub._build_profile_config()
    assert pc.max_capital_deployed == 12000.0


def test_build_profile_config_mode_translation_live_to_execution():
    stub = V2Strategy.__new__(V2Strategy)
    stub.profile_name = "test-profile"
    stub._config = {"preset": "swing"}
    stub._scan_symbols = ["TSLA"]
    stub.parameters = {}

    with patch("strategies.v2_strategy.config.EXECUTION_MODE", "live"):
        pc = stub._build_profile_config()
    assert pc.mode == "execution"


def test_build_profile_config_mode_translation_shadow_to_execution():
    stub = V2Strategy.__new__(V2Strategy)
    stub.profile_name = "test-profile"
    stub._config = {"preset": "swing"}
    stub._scan_symbols = ["TSLA"]
    stub.parameters = {}

    with patch("strategies.v2_strategy.config.EXECUTION_MODE", "shadow"):
        pc = stub._build_profile_config()
    assert pc.mode == "execution"


def test_build_profile_config_mode_translation_signal_only_passthrough():
    stub = V2Strategy.__new__(V2Strategy)
    stub.profile_name = "test-profile"
    stub._config = {"preset": "swing"}
    stub._scan_symbols = ["TSLA"]
    stub.parameters = {}

    with patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        pc = stub._build_profile_config()
    assert pc.mode == "signal_only"


def test_build_profile_config_name_sanitized_for_spaces():
    """ProfileConfig.name regex rejects spaces; helper replaces with _."""
    stub = V2Strategy.__new__(V2Strategy)
    stub.profile_name = "Manual swing TSLA"
    stub._config = {"preset": "swing"}
    stub._scan_symbols = ["TSLA"]
    stub.parameters = {}

    with patch("strategies.v2_strategy.config.EXECUTION_MODE", "signal_only"):
        pc = stub._build_profile_config()
    assert pc.name == "Manual_swing_TSLA"


# ═════════════════════════════════════════════════════════════════
# ProfileState stubbed defaults (DECISION 3)
# ═════════════════════════════════════════════════════════════════


def test_profile_state_has_zero_open_positions_in_signal_only():
    """Phase 1a stubs current_open_positions to 0 — verify by spying
    on evaluate_entry's `state` argument."""
    pc = _profile_config(preset="swing")
    stub = _build_v2_stub(preset_name="swing", profile_config=pc)
    preset = _attach_new_preset(stub, SwingPreset, pc)

    captured = {}
    def capture(symbol, setup, snap, state):
        captured["state"] = state
        return EntryDecision(
            should_enter=False, reason="captured", direction="bullish",
        )
    preset.evaluate_entry = capture

    sr, setup = _scan_result()
    with patch("strategies.v2_strategy.record_signal"), \
         patch("strategies.v2_strategy.send_entry_alert"):
        stub._run_new_preset_iteration(
            [(sr, setup)], _market_snapshot(), None,
        )

    state = captured["state"]
    assert state.current_open_positions == 0
    assert state.current_capital_deployed == 0.0
    assert state.today_account_pnl_pct == 0.0
    assert state.last_exit_at is None
