"""Unit tests for profiles.base_preset.

Tests the abstract base class via a minimal concrete subclass,
plus the dataclasses and the can_enter wrapper.

Run via:
    python -m pytest tests/test_base_preset.py -v
"""

import dataclasses
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from market.context import MarketSnapshot, Regime, TimeOfDay  # noqa: E402
from profiles.base_preset import (  # noqa: E402
    BasePreset,
    ContractSelection,
    EntryDecision,
    ExitDecision,
    OptionChain,
    OptionContract,
    ProfileState,
)
from profiles.profile_config import ProfileConfig  # noqa: E402
from scanner.setups import SetupScore  # noqa: E402
from sizing.cap_check import CapCheckResult  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────

MIN_VALID_CONFIG = {
    "name": "test",
    "preset": "swing",
    "symbols": ["SPY"],
    "max_capital_deployed": 5000.0,
}


def _config(**overrides) -> ProfileConfig:
    return ProfileConfig(**{**MIN_VALID_CONFIG, **overrides})


def _state(**overrides) -> ProfileState:
    defaults = {
        "current_open_positions": 0,
        "current_capital_deployed": 0.0,
        "today_account_pnl_pct": 0.0,
        "last_exit_at": None,
        "last_entry_at": None,
        "recent_exits_by_symbol": {},
    }
    return ProfileState(**{**defaults, **overrides})


def _contract(**overrides) -> ContractSelection:
    defaults = {
        "symbol": "SPY",
        "right": "call",
        "strike": 500.0,
        "expiration": date(2026, 5, 16),
        "target_delta": 0.45,
        "estimated_premium": 5.00,  # $500 per contract
        "dte": 9,
    }
    return ContractSelection(**{**defaults, **overrides})


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        regime=Regime.TRENDING_UP,
        time_of_day=TimeOfDay.MID_MORNING,
        timestamp="2026-04-27T10:30:00",
    )


class MinimalPreset(BasePreset):
    """Concrete subclass that satisfies BasePreset's abstract API."""
    __test__ = False  # not a pytest test class
    name = "test"
    accepted_setup_types = frozenset({"momentum"})

    def evaluate_entry(self, symbol, scanner_output, market, state):
        return EntryDecision(
            should_enter=True, reason="test", direction="call"
        )

    def select_contract(self, symbol, direction, chain):
        return None

    def evaluate_exit(self, position, current_quote, market):
        return ExitDecision(should_exit=False, reason="test")


class NoNamePreset(BasePreset):
    __test__ = False
    accepted_setup_types = frozenset({"momentum"})

    def evaluate_entry(self, *a, **kw):
        return EntryDecision(should_enter=False, reason="x")

    def select_contract(self, *a, **kw):
        return None

    def evaluate_exit(self, *a, **kw):
        return ExitDecision(should_exit=False, reason="x")


class NoSetupTypesPreset(BasePreset):
    __test__ = False
    name = "no_setups"

    def evaluate_entry(self, *a, **kw):
        return EntryDecision(should_enter=False, reason="x")

    def select_contract(self, *a, **kw):
        return None

    def evaluate_exit(self, *a, **kw):
        return ExitDecision(should_exit=False, reason="x")


class CustomActivePreset(MinimalPreset):
    __test__ = False
    name = "custom_active"

    def is_active_now(self, market):
        return market.time_of_day == TimeOfDay.MID_MORNING


# ─────────────────────────────────────────────────────────────────
# Subclass requirements (constructor)
# ─────────────────────────────────────────────────────────────────

def test_subclass_without_name_raises():
    with pytest.raises(ValueError, match="name not set"):
        NoNamePreset(_config())


def test_subclass_without_accepted_setup_types_raises():
    with pytest.raises(ValueError, match="accepted_setup_types not set"):
        NoSetupTypesPreset(_config())


def test_valid_subclass_constructs():
    preset = MinimalPreset(_config())
    assert preset.name == "test"
    assert preset.accepted_setup_types == frozenset({"momentum"})
    assert preset.config.name == "test"


# ─────────────────────────────────────────────────────────────────
# is_active_now
# ─────────────────────────────────────────────────────────────────

def test_is_active_now_default_returns_true():
    preset = MinimalPreset(_config())
    assert preset.is_active_now(_market()) is True


def test_subclass_can_override_is_active_now():
    preset = CustomActivePreset(_config())
    assert preset.is_active_now(_market()) is True
    other = MarketSnapshot(
        regime=Regime.CHOPPY,
        time_of_day=TimeOfDay.OUTSIDE,
        timestamp="2026-04-27T20:00:00",
    )
    assert preset.is_active_now(other) is False


# ─────────────────────────────────────────────────────────────────
# can_enter wrapper behavior
# ─────────────────────────────────────────────────────────────────

def test_can_enter_negative_entry_decision_rejects():
    preset = MinimalPreset(_config())
    decision = EntryDecision(
        should_enter=False, reason="trend_qualifier_failed"
    )
    result = preset.can_enter(decision, _contract(), _state(), 1)
    assert result.approved is False
    assert result.approved_contracts == 0
    assert "negative entry_decision" in result.block_reason
    assert "trend_qualifier_failed" in result.block_reason


def test_can_enter_positive_flows_through_to_approval():
    preset = MinimalPreset(_config(max_capital_deployed=10_000.0))
    decision = EntryDecision(
        should_enter=True, reason="all_gates_pass", direction="call"
    )
    result = preset.can_enter(decision, _contract(), _state(), 1)
    assert result.approved is True
    assert result.approved_contracts == 1
    assert result.block_reason == ""


def test_can_enter_propagates_profile_disabled():
    preset = MinimalPreset(_config(enabled=False))
    decision = EntryDecision(
        should_enter=True, reason="x", direction="call"
    )
    result = preset.can_enter(decision, _contract(), _state(), 1)
    assert result.approved is False
    assert result.block_reason == "profile_disabled"


def test_can_enter_propagates_circuit_breaker():
    preset = MinimalPreset(_config(
        circuit_breaker_enabled=True,
        circuit_breaker_threshold_pct=10.0,
    ))
    decision = EntryDecision(
        should_enter=True, reason="x", direction="call"
    )
    result = preset.can_enter(
        decision,
        _contract(),
        _state(today_account_pnl_pct=-15.0),
        1,
    )
    assert result.approved is False
    assert result.block_reason.startswith("circuit_breaker_tripped:")


def test_can_enter_propagates_max_positions():
    preset = MinimalPreset(_config(max_concurrent_positions=2))
    decision = EntryDecision(
        should_enter=True, reason="x", direction="call"
    )
    result = preset.can_enter(
        decision,
        _contract(),
        _state(current_open_positions=2),
        1,
    )
    assert result.approved is False
    assert "max_concurrent_positions_reached" in result.block_reason


def test_can_enter_preserves_reduction_notes():
    preset = MinimalPreset(_config(
        max_contracts_per_trade=2,
        max_capital_deployed=10_000.0,
    ))
    decision = EntryDecision(
        should_enter=True, reason="x", direction="call"
    )
    result = preset.can_enter(decision, _contract(), _state(), 5)
    assert result.approved is True
    assert result.approved_contracts == 2
    assert any(
        "reduced 5->2 per max_contracts_per_trade" in n
        for n in result.notes
    )


def test_can_enter_invalid_proposed_count_propagates():
    preset = MinimalPreset(_config())
    decision = EntryDecision(
        should_enter=True, reason="x", direction="call"
    )
    result = preset.can_enter(decision, _contract(), _state(), 0)
    assert result.approved is False
    assert result.block_reason.startswith("invalid_proposed_contracts:")


# ─────────────────────────────────────────────────────────────────
# Logger naming
# ─────────────────────────────────────────────────────────────────

def test_logger_name_uses_preset_namespace():
    preset = MinimalPreset(_config())
    assert preset._logger.name == "options-bot.profiles.test"


# ─────────────────────────────────────────────────────────────────
# Dataclass shape tests
# ─────────────────────────────────────────────────────────────────

def test_entry_decision_with_direction():
    d = EntryDecision(should_enter=True, reason="x", direction="call")
    assert d.direction == "call"


def test_entry_decision_default_direction_is_none():
    d = EntryDecision(should_enter=False, reason="x")
    assert d.direction is None


def test_entry_decision_is_frozen():
    d = EntryDecision(should_enter=True, reason="x", direction="call")
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.reason = "mutated"


def test_exit_decision_is_frozen():
    d = ExitDecision(should_exit=False, reason="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.reason = "mutated"


def test_contract_selection_is_frozen():
    c = _contract()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.strike = 999.0


def test_profile_state_is_frozen():
    s = _state()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.current_open_positions = 99


def test_option_chain_is_frozen():
    chain = OptionChain(
        symbol="SPY",
        underlying_price=500.0,
        contracts=[],
        snapshot_time=datetime(2026, 4, 27, 10, 30),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        chain.symbol = "QQQ"


def test_option_contract_is_frozen():
    c = OptionContract(
        symbol="SPY260516C00500000",
        right="call",
        strike=500.0,
        expiration=date(2026, 5, 16),
        bid=4.95, ask=5.05, mid=5.00,
        delta=0.45, iv=0.20,
        open_interest=1000, volume=500,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.strike = 999.0


def test_dataclasses_round_trip_via_asdict():
    """asdict produces a dict that re-constructs into an equal object."""
    contract = _contract()
    as_dict = dataclasses.asdict(contract)
    assert isinstance(as_dict, dict)
    rebuilt = ContractSelection(**as_dict)
    assert rebuilt == contract


def test_profile_state_default_recent_exits_is_empty_dict():
    s = ProfileState(
        current_open_positions=0,
        current_capital_deployed=0.0,
        today_account_pnl_pct=0.0,
        last_exit_at=None,
        last_entry_at=None,
    )
    assert s.recent_exits_by_symbol == {}


# ─────────────────────────────────────────────────────────────────
# Independence checks
# ─────────────────────────────────────────────────────────────────

def test_module_does_not_reference_legacy_strategy():
    import profiles.base_preset as bp
    text = Path(bp.__file__).read_text(encoding="utf-8")
    assert "v2_strategy" not in text


def test_module_does_not_reference_legacy_preset_classes():
    import profiles.base_preset as bp
    text = Path(bp.__file__).read_text(encoding="utf-8")
    for forbidden in ("from .swing", "from .momentum",
                      "from .scalp_0dte", "from .catalyst",
                      "from .mean_reversion", "from .tsla_swing",
                      "profiles.swing", "profiles.scalp_0dte",
                      "profiles.momentum", "profiles.catalyst",
                      "profiles.mean_reversion", "profiles.tsla_swing"):
        assert forbidden not in text, (
            f"base_preset.py must not reference {forbidden}"
        )


def test_module_does_not_touch_db():
    import profiles.base_preset as bp
    text = Path(bp.__file__).read_text(encoding="utf-8")
    for forbidden in ("sqlite", "aiosqlite", "backend.database"):
        assert forbidden not in text, (
            f"base_preset.py must not reference {forbidden}"
        )
