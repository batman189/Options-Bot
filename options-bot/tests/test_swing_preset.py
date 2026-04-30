"""Unit tests for profiles.swing_preset.

Pure logic — no DB, no network, no filesystem. ivr_fetcher and
macro_fetcher are dependency-injected, so production scoring/macro
modules are never imported. Mirrors the pytest style of the other
Phase 1a test files.

Run via:
    python -m pytest tests/test_swing_preset.py -v
"""

import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from market.context import MarketSnapshot, Regime, TimeOfDay  # noqa: E402
from profiles.base_preset import (  # noqa: E402
    ContractSelection,
    EntryDecision,
    OptionChain,
    OptionContract,
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

def test_evaluate_exit_raises_not_implemented():
    swing = _swing()
    with pytest.raises(NotImplementedError, match="B4"):
        swing.evaluate_exit(
            MagicMock(),  # position
            5.50,         # current_quote
            _market(),    # market
            [],           # setups
            _state(),     # state
        )


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


# ─────────────────────────────────────────────────────────────────
# select_contract — fixtures
# ─────────────────────────────────────────────────────────────────


def _option_contract(
    strike: float,
    right: str = "call",
    delta: float = 0.45,
    bid: float = 1.00,
    ask: float = 1.04,
    mid: float = 1.02,
    oi: int = 1000,
    vol: int = 200,
    expiration: date = date(2026, 5, 15),
    iv: float = 0.25,
    symbol: str = "TSLA",
) -> OptionContract:
    return OptionContract(
        symbol=symbol,
        right=right,
        strike=strike,
        expiration=expiration,
        bid=bid,
        ask=ask,
        mid=mid,
        delta=delta,
        iv=iv,
        open_interest=oi,
        volume=vol,
    )


def _option_chain(
    contracts: list,
    underlying_price: float = 500.0,
    snapshot_time: datetime = datetime(2026, 5, 6, 14, 0, tzinfo=timezone.utc),
    symbol: str = "TSLA",
) -> OptionChain:
    return OptionChain(
        symbol=symbol,
        underlying_price=underlying_price,
        contracts=contracts,
        snapshot_time=snapshot_time,
    )


# ─────────────────────────────────────────────────────────────────
# select_contract — direction translation
# ─────────────────────────────────────────────────────────────────


def test_select_bullish_picks_call():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, right="call", delta=0.50),
    ])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.right == "call"
    assert sel.strike == 500.0


def test_select_bearish_picks_put():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, right="put", delta=-0.50),
    ])
    sel = swing.select_contract("TSLA", "bearish", chain)
    assert sel is not None
    assert sel.right == "put"


def test_select_neutral_returns_none_with_warning(caplog):
    swing = _swing()
    chain = _option_chain([_option_contract(500.0)])
    caplog.set_level(logging.WARNING, logger="options-bot.profiles.swing")
    sel = swing.select_contract("TSLA", "neutral", chain)
    assert sel is None
    assert any("non-directional" in r.getMessage() for r in caplog.records)


def test_select_none_direction_returns_none_with_warning(caplog):
    swing = _swing()
    chain = _option_chain([_option_contract(500.0)])
    caplog.set_level(logging.WARNING, logger="options-bot.profiles.swing")
    sel = swing.select_contract("TSLA", None, chain)
    assert sel is None
    assert any("non-directional" in r.getMessage() for r in caplog.records)


def test_select_garbage_direction_returns_none(caplog):
    swing = _swing()
    chain = _option_chain([_option_contract(500.0)])
    caplog.set_level(logging.WARNING, logger="options-bot.profiles.swing")
    sel = swing.select_contract("TSLA", "garbage", chain)
    assert sel is None
    assert any("non-directional" in r.getMessage() for r in caplog.records)


# ─────────────────────────────────────────────────────────────────
# select_contract — empty / no-survivor
# ─────────────────────────────────────────────────────────────────


def test_select_empty_chain_returns_none():
    swing = _swing()
    chain = _option_chain([])
    assert swing.select_contract("TSLA", "bullish", chain) is None


def test_select_only_puts_when_bullish_returns_none():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, right="put", delta=-0.50),
    ])
    assert swing.select_contract("TSLA", "bullish", chain) is None


def test_select_only_calls_when_bearish_returns_none():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, right="call", delta=0.50),
    ])
    assert swing.select_contract("TSLA", "bearish", chain) is None


def test_select_all_fail_liquidity_returns_none_with_info(caplog):
    swing = _swing()
    # All contracts fail spread gate (10% spread, max is 4%)
    chain = _option_chain([
        _option_contract(500.0, bid=0.95, ask=1.05, mid=1.00, delta=0.50),
    ])
    caplog.set_level(logging.INFO, logger="options-bot.profiles.swing")
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is None
    assert any("no qualifying contract" in r.getMessage() for r in caplog.records)


def test_select_all_fail_delta_band_returns_none():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, delta=0.30),
        _option_contract(505.0, delta=0.32),
    ])
    assert swing.select_contract("TSLA", "bullish", chain) is None


def test_select_pass_liquidity_fail_delta_returns_none():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, delta=0.30),  # ok liquidity, bad delta
    ])
    assert swing.select_contract("TSLA", "bullish", chain) is None


# ─────────────────────────────────────────────────────────────────
# select_contract — liquidity gates (boundaries)
# ─────────────────────────────────────────────────────────────────


def test_liquidity_spread_at_max_boundary_accepted():
    """spread/mid = 0.04 exactly is accepted (predicate is >, not >=).

    Use bid/ask/mid values that produce exactly 0.04 in IEEE float —
    bid=98, ask=102, mid=100 gives (102.0-98.0)/100.0 == 0.04 cleanly.
    Using e.g. (1.02-0.98)/1.00 drifts to 0.04000...036.
    """
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, bid=98.0, ask=102.0, mid=100.0, delta=0.50),
    ])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None


def test_liquidity_spread_above_max_rejected():
    swing = _swing()
    # spread_pct = 0.10 > 0.04
    chain = _option_chain([
        _option_contract(500.0, bid=0.95, ask=1.05, mid=1.00, delta=0.50),
    ])
    assert swing.select_contract("TSLA", "bullish", chain) is None


def test_liquidity_mid_zero_rejected():
    """mid=0 must be rejected before division (zero-division guard)."""
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, bid=0.0, ask=0.0, mid=0.0, delta=0.50),
    ])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is None  # rejected, no exception


def test_liquidity_mid_negative_rejected():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, bid=0.0, ask=0.0, mid=-0.01, delta=0.50),
    ])
    assert swing.select_contract("TSLA", "bullish", chain) is None


def test_liquidity_oi_at_min_boundary_accepted():
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, oi=500, delta=0.50)])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None


def test_liquidity_oi_below_min_rejected():
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, oi=499, delta=0.50)])
    assert swing.select_contract("TSLA", "bullish", chain) is None


def test_liquidity_volume_at_min_boundary_accepted():
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, vol=100, delta=0.50)])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None


def test_liquidity_volume_below_min_rejected():
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, vol=99, delta=0.50)])
    assert swing.select_contract("TSLA", "bullish", chain) is None


# ─────────────────────────────────────────────────────────────────
# select_contract — delta band (boundaries)
# ─────────────────────────────────────────────────────────────────


def test_call_delta_at_min_boundary_accepted():
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, delta=0.40)])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None


def test_call_delta_at_max_boundary_accepted():
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, delta=0.55)])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None


def test_call_delta_below_band_rejected():
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, delta=0.39)])
    assert swing.select_contract("TSLA", "bullish", chain) is None


def test_call_delta_above_band_rejected():
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, delta=0.56)])
    assert swing.select_contract("TSLA", "bullish", chain) is None


def test_put_delta_at_min_boundary_accepted():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, right="put", delta=-0.40),
    ])
    sel = swing.select_contract("TSLA", "bearish", chain)
    assert sel is not None


def test_put_delta_at_max_boundary_accepted():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, right="put", delta=-0.55),
    ])
    sel = swing.select_contract("TSLA", "bearish", chain)
    assert sel is not None


def test_put_delta_below_band_rejected():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, right="put", delta=-0.39),
    ])
    assert swing.select_contract("TSLA", "bearish", chain) is None


def test_put_delta_above_band_rejected():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, right="put", delta=-0.56),
    ])
    assert swing.select_contract("TSLA", "bearish", chain) is None


def test_pathological_negative_delta_on_call_rejected():
    """A call with negative delta is outside [0.40, 0.55] (signed check)."""
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, right="call", delta=-0.45),
    ])
    assert swing.select_contract("TSLA", "bullish", chain) is None


# ─────────────────────────────────────────────────────────────────
# select_contract — winner picking
# ─────────────────────────────────────────────────────────────────


def test_winner_minimizes_distance_to_target_delta():
    """3 calls: deltas 0.42, 0.50, 0.54. Winner is 0.50 (distance 0)."""
    swing = _swing()
    chain = _option_chain([
        _option_contract(495.0, delta=0.42),
        _option_contract(500.0, delta=0.50),
        _option_contract(505.0, delta=0.54),
    ])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.strike == 500.0


def test_winner_uses_abs_delta_for_puts():
    """2 puts: -0.45, -0.50. Winner is -0.50 (closer to abs target 0.50)."""
    swing = _swing()
    chain = _option_chain([
        _option_contract(495.0, right="put", delta=-0.45),
        _option_contract(490.0, right="put", delta=-0.50),
    ])
    sel = swing.select_contract("TSLA", "bearish", chain)
    assert sel is not None
    assert sel.strike == 490.0


def test_winner_tie_broken_by_tighter_spread():
    """Two equally-distant calls (0.48, 0.52) with different spreads.
    The tighter spread wins."""
    swing = _swing()
    # 0.48 strike has wider spread (3% of mid)
    # 0.52 strike has tighter spread (1% of mid)
    chain = _option_chain([
        _option_contract(
            495.0, delta=0.48, bid=0.985, ask=1.015, mid=1.00,
        ),  # spread = 0.03
        _option_contract(
            505.0, delta=0.52, bid=0.995, ask=1.005, mid=1.00,
        ),  # spread = 0.01
    ])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.strike == 505.0


def test_winner_tie_broken_by_higher_oi_when_spread_equal():
    """Two equally-distant calls with equal spreads — higher OI wins."""
    swing = _swing()
    chain = _option_chain([
        _option_contract(495.0, delta=0.48, oi=600),
        _option_contract(505.0, delta=0.52, oi=2000),
    ])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.strike == 505.0


def test_winner_target_delta_is_constant_not_actual():
    """ContractSelection.target_delta is DELTA_TARGET regardless of
    winner's actual delta."""
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, delta=0.42)])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.target_delta == 0.50
    # winner's actual delta is 0.42; the field records the *target*


def test_winner_estimated_premium_is_mid():
    swing = _swing()
    # bid=2.49/ask=2.51/mid=2.50 keeps spread at 0.008 (under 0.04 limit).
    # Earlier draft used bid=2.40/ask=2.60 which was 8% spread and got
    # rejected by the liquidity gate before reaching the winner step.
    chain = _option_chain([
        _option_contract(500.0, delta=0.50, bid=2.49, ask=2.51, mid=2.50),
    ])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.estimated_premium == 2.50


def test_dte_computed_from_snapshot_time_date():
    """DTE uses chain.snapshot_time.date(), not datetime.today()."""
    snap = datetime(2026, 5, 6, 14, 0, tzinfo=timezone.utc)  # Wed
    expiration = date(2026, 5, 15)  # Fri, +9 days
    chain = _option_chain(
        [_option_contract(500.0, delta=0.50, expiration=expiration)],
        snapshot_time=snap,
    )
    swing = _swing()
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.dte == 9


def test_lone_low_delta_qualifier_still_wins():
    """Single qualifier at delta 0.41 (low but in-band) wins —
    closer-to-target is not required, just in-band."""
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, delta=0.41)])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.strike == 500.0


# ─────────────────────────────────────────────────────────────────
# select_contract — ContractSelection shape
# ─────────────────────────────────────────────────────────────────


def test_returned_right_is_lowercase_call():
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, delta=0.50)])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.right == "call"


def test_returned_right_is_lowercase_put():
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, right="put", delta=-0.50),
    ])
    sel = swing.select_contract("TSLA", "bearish", chain)
    assert sel is not None
    assert sel.right == "put"


def test_returned_expiration_is_date_object():
    exp = date(2026, 5, 15)
    swing = _swing()
    chain = _option_chain([
        _option_contract(500.0, delta=0.50, expiration=exp),
    ])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.expiration == exp
    assert isinstance(sel.expiration, date)


def test_returned_is_contract_selection_type():
    swing = _swing()
    chain = _option_chain([_option_contract(500.0, delta=0.50)])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert isinstance(sel, ContractSelection)


# ─────────────────────────────────────────────────────────────────
# select_contract — golden-path mixed chain
# ─────────────────────────────────────────────────────────────────


def test_golden_path_picks_only_qualifier_from_mixed_chain():
    """5 candidates — only 1 should clear every gate."""
    swing = _swing()
    chain = _option_chain([
        # wrong right
        _option_contract(500.0, right="put", delta=-0.50),
        # fail spread
        _option_contract(495.0, delta=0.50, bid=0.90, ask=1.10, mid=1.00),
        # fail OI
        _option_contract(505.0, delta=0.50, oi=400),
        # fail delta band
        _option_contract(510.0, delta=0.30),
        # the winner — clears every gate
        _option_contract(498.0, delta=0.48, oi=2000, vol=500),
    ])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.strike == 498.0


def test_golden_path_lone_low_delta_qualifier_wins_among_disqualified():
    """In a chain where the winner is at delta=0.41 (low but in-band) and
    every other contract is disqualified, the algorithm still selects."""
    swing = _swing()
    chain = _option_chain([
        # fail delta band
        _option_contract(495.0, delta=0.30),
        # fail liquidity
        _option_contract(505.0, delta=0.50, oi=400),
        # the winner, delta 0.41
        _option_contract(500.0, delta=0.41),
    ])
    sel = swing.select_contract("TSLA", "bullish", chain)
    assert sel is not None
    assert sel.strike == 500.0
