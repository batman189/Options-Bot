"""Unit tests for profiles.swing_preset.

Pure logic — no DB, no network, no filesystem. ivr_fetcher and
macro_fetcher are dependency-injected, so production scoring/macro
modules are never imported. Mirrors the pytest style of the other
Phase 1a test files.

Run via:
    python -m pytest tests/test_swing_preset.py -v
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from market.context import MarketSnapshot, Regime, TimeOfDay  # noqa: E402
from profiles.base_preset import (  # noqa: E402
    EntryDecision,
    ProfileState,
)
from profiles.profile_config import ProfileConfig  # noqa: E402
from profiles.swing_preset import SwingPreset  # noqa: E402
from scanner.setups import SetupScore  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

MIN_VALID_CONFIG = {
    "name": "swing-test",
    "preset": "swing",
    "symbols": ["TSLA"],
    "max_capital_deployed": 10_000.0,
}


def _config(**overrides) -> ProfileConfig:
    return ProfileConfig(**{**MIN_VALID_CONFIG, **overrides})


def _setup(
    setup_type: str = "momentum",
    score: float = 0.60,
    direction: str = "bullish",
    reason: str = "test",
) -> SetupScore:
    return SetupScore(
        setup_type=setup_type,
        score=score,
        reason=reason,
        direction=direction,
    )


def _market(
    vix: float = 20.0,
    regime: Regime = Regime.TRENDING_UP,
    time_of_day: TimeOfDay = TimeOfDay.OPEN,
) -> MarketSnapshot:
    return MarketSnapshot(
        regime=regime,
        time_of_day=time_of_day,
        timestamp="2026-04-28T10:30:00",
        vix_level=vix,
    )


def _state() -> ProfileState:
    return ProfileState(
        current_open_positions=0,
        current_capital_deployed=0.0,
        today_account_pnl_pct=0.0,
        last_exit_at=None,
        last_entry_at=None,
        recent_exits_by_symbol={},
    )


def _swing(
    ivr_fetcher=None,
    macro_fetcher=None,
    config: ProfileConfig | None = None,
) -> SwingPreset:
    return SwingPreset(
        config=config or _config(),
        ivr_fetcher=ivr_fetcher,
        macro_fetcher=macro_fetcher,
    )


# ─────────────────────────────────────────────────────────────────
# Construction
# ─────────────────────────────────────────────────────────────────

def test_construct_with_valid_config():
    swing = _swing()
    assert swing.name == "swing"
    assert swing.config.name == "swing-test"


def test_accepted_setup_types():
    swing = _swing()
    assert swing.accepted_setup_types == frozenset({
        "momentum", "compression_breakout", "macro_trend",
    })


def test_is_active_now_always_true():
    swing = _swing()
    for tod in TimeOfDay:
        m = _market(time_of_day=tod)
        assert swing.is_active_now(m) is True


# ─────────────────────────────────────────────────────────────────
# Gate (a) — setup type
# ─────────────────────────────────────────────────────────────────

def test_rejects_mean_reversion_setup_type():
    swing = _swing()
    decision = swing.evaluate_entry(
        "TSLA", _setup(setup_type="mean_reversion"),
        _market(), _state(),
    )
    assert decision.should_enter is False
    assert "not accepted" in decision.reason
    assert "'mean_reversion'" in decision.reason


def test_rejects_catalyst_setup_type():
    swing = _swing()
    decision = swing.evaluate_entry(
        "TSLA", _setup(setup_type="catalyst"),
        _market(), _state(),
    )
    assert decision.should_enter is False
    assert "not accepted" in decision.reason


# ─────────────────────────────────────────────────────────────────
# Gate (b) — score floor
# ─────────────────────────────────────────────────────────────────

def test_rejects_score_below_minimum():
    swing = _swing()
    decision = swing.evaluate_entry(
        "TSLA", _setup(score=0.30), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "below min" in decision.reason


def test_accepts_score_at_minimum_boundary():
    """Exactly 0.35 should pass (>= MIN_SETUP_SCORE)."""
    swing = _swing()
    decision = swing.evaluate_entry(
        "TSLA", _setup(score=0.35), _market(), _state(),
    )
    # Score gate passes; remaining gates fail downstream only on other
    # conditions. With default _market(VIX=20) and no fetchers, this
    # should reach the success path.
    assert decision.should_enter is True


# ─────────────────────────────────────────────────────────────────
# Gate (c) — direction
# ─────────────────────────────────────────────────────────────────

def test_rejects_neutral_direction():
    swing = _swing()
    decision = swing.evaluate_entry(
        "TSLA", _setup(direction="neutral"),
        _market(), _state(),
    )
    assert decision.should_enter is False
    assert "neutral" in decision.reason


# ─────────────────────────────────────────────────────────────────
# Gate (d) — VIX
# ─────────────────────────────────────────────────────────────────

def test_rejects_vix_below_min():
    swing = _swing()
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(vix=12.5), _state(),
    )
    assert decision.should_enter is False
    assert "VIX" in decision.reason
    assert "12.50" in decision.reason


def test_rejects_vix_above_max():
    swing = _swing()
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(vix=30.5), _state(),
    )
    assert decision.should_enter is False
    assert "VIX" in decision.reason
    assert "30.50" in decision.reason


def test_accepts_vix_at_low_boundary():
    swing = _swing()
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(vix=13.0), _state(),
    )
    assert decision.should_enter is True


def test_accepts_vix_at_high_boundary():
    swing = _swing()
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(vix=30.0), _state(),
    )
    assert decision.should_enter is True


# ─────────────────────────────────────────────────────────────────
# Gate (e) — IVR
# ─────────────────────────────────────────────────────────────────

def test_rejects_ivr_above_max():
    fetcher = MagicMock(return_value=85.0)
    swing = _swing(ivr_fetcher=fetcher)
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "IVR 85.0" in decision.reason


def test_rejects_ivr_at_max_boundary():
    """80.0 trips because predicate is >= max."""
    fetcher = MagicMock(return_value=80.0)
    swing = _swing(ivr_fetcher=fetcher)
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "IVR 80.0" in decision.reason


def test_accepts_ivr_below_max():
    fetcher = MagicMock(return_value=50.0)
    swing = _swing(ivr_fetcher=fetcher)
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(), _state(),
    )
    assert decision.should_enter is True
    assert "IVR 50.0" in decision.reason


def test_ivr_fetcher_returns_none_skips_check():
    """Cold-start: IVR check is skipped, success reason notes the skip."""
    fetcher = MagicMock(return_value=None)
    swing = _swing(ivr_fetcher=fetcher)
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(), _state(),
    )
    assert decision.should_enter is True
    assert "IVR unavailable — check skipped" in decision.reason


def test_ivr_fetcher_unset_skips_check():
    swing = _swing(ivr_fetcher=None)
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(), _state(),
    )
    assert decision.should_enter is True
    assert "IVR fetcher not configured" in decision.reason


# ─────────────────────────────────────────────────────────────────
# Gate (f) — macro events
# ─────────────────────────────────────────────────────────────────

def test_rejects_high_impact_event():
    high_event = SimpleNamespace(impact_level="HIGH", event_type="FOMC")
    fetcher = MagicMock(return_value=[high_event])
    swing = _swing(macro_fetcher=fetcher)
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "HIGH-impact macro event" in decision.reason
    assert "1 event" in decision.reason


def test_accepts_when_macro_fetcher_returns_empty():
    fetcher = MagicMock(return_value=[])
    swing = _swing(macro_fetcher=fetcher)
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(), _state(),
    )
    assert decision.should_enter is True
    assert "no HIGH-impact events within 48h" in decision.reason


def test_accepts_when_only_medium_or_low_events():
    """Filter for HIGH only — MEDIUM/LOW pass through."""
    events = [
        SimpleNamespace(impact_level="MEDIUM", event_type="EARNINGS"),
        SimpleNamespace(impact_level="LOW", event_type="OTHER"),
    ]
    fetcher = MagicMock(return_value=events)
    swing = _swing(macro_fetcher=fetcher)
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(), _state(),
    )
    assert decision.should_enter is True
    assert "no HIGH-impact events within 48h" in decision.reason


def test_macro_fetcher_unset_passes_gate():
    swing = _swing(macro_fetcher=None)
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(), _state(),
    )
    assert decision.should_enter is True
    assert "macro fetcher not configured" in decision.reason


def test_macro_fetcher_called_with_48h_lookahead():
    fetcher = MagicMock(return_value=[])
    swing = _swing(macro_fetcher=fetcher)
    swing.evaluate_entry("TSLA", _setup(), _market(), _state())
    fetcher.assert_called_once_with("TSLA", 2880)


# ─────────────────────────────────────────────────────────────────
# Full success path
# ─────────────────────────────────────────────────────────────────

def test_full_success_all_gates_pass():
    ivr = MagicMock(return_value=45.0)
    macro = MagicMock(return_value=[])
    swing = _swing(ivr_fetcher=ivr, macro_fetcher=macro)
    decision = swing.evaluate_entry(
        "TSLA",
        _setup(setup_type="momentum", score=0.72, direction="bullish"),
        _market(vix=18.5),
        _state(),
    )
    assert decision.should_enter is True
    assert decision.direction == "bullish"
    # Reason carries the full audit trail
    assert "momentum" in decision.reason
    assert "0.720" in decision.reason
    assert "bullish" in decision.reason
    assert "VIX=18.50" in decision.reason
    assert "IVR 45.0" in decision.reason
    assert "no HIGH-impact events within 48h" in decision.reason


def test_full_success_returns_entry_decision_type():
    swing = _swing()
    decision = swing.evaluate_entry(
        "TSLA", _setup(), _market(), _state(),
    )
    assert isinstance(decision, EntryDecision)


# ─────────────────────────────────────────────────────────────────
# Stub methods raise NotImplementedError
# ─────────────────────────────────────────────────────────────────

def test_select_contract_raises_not_implemented():
    swing = _swing()
    with pytest.raises(NotImplementedError, match="B3"):
        swing.select_contract("TSLA", "bullish", MagicMock())


def test_evaluate_exit_raises_not_implemented():
    swing = _swing()
    with pytest.raises(NotImplementedError, match="B4"):
        swing.evaluate_exit(MagicMock(), 5.50, _market())


# ─────────────────────────────────────────────────────────────────
# Independence — no production scoring/macro imports
# ─────────────────────────────────────────────────────────────────

def test_module_does_not_import_scoring_ivr_or_macro_reader():
    """The whole point of dependency-injected fetchers is testability
    without those imports. The wire-in happens at the orchestrator,
    not in this preset module."""
    import profiles.swing_preset as sp
    text = Path(sp.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "from scoring.ivr",
        "import scoring.ivr",
        "from scoring import ivr",
        "from macro.reader",
        "import macro.reader",
        "from macro import reader",
    ):
        assert forbidden not in text, (
            f"swing_preset.py must not reference {forbidden}"
        )
