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


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — fixtures
# ─────────────────────────────────────────────────────────────────
#
# Float-clean values used throughout: entries/peaks/currents avoid
# decimals that drift in IEEE arithmetic. e.g. peak=2.0/current=1.30
# yields drawdown 0.35 cleanly; peak=100/current=65 also clean.

from datetime import timedelta  # noqa: E402


def _position(
    entry: float = 1.00,
    peak: float = 1.00,
    current: float = 1.00,
    side: str = "call",
    expiration_days_out: int = 10,
    trade_id: str = "t-1",
    symbol: str = "TSLA",
) -> object:
    """Build a Position. expiration_days_out is relative to date.today()
    so DTE checks are deterministic regardless of when the test runs."""
    from profiles.base_preset import Position
    contract = ContractSelection(
        symbol=symbol,
        right=side,
        strike=500.0,
        expiration=date.today() + timedelta(days=expiration_days_out),
        target_delta=0.50,
        estimated_premium=entry,
        dte=expiration_days_out,
    )
    return Position(
        trade_id=trade_id,
        symbol=symbol,
        contract=contract,
        entry_time=datetime(2026, 4, 28, 14, 30, tzinfo=timezone.utc),
        entry_premium_per_share=entry,
        entry_underlying_price=500.0,
        peak_premium_per_share=peak,
        current_premium_per_share=current,
        contracts=1,
    )


def _ss(setup_type: str = "momentum",
        score: float = 0.40,
        direction: str = "bullish") -> SetupScore:
    return SetupScore(
        setup_type=setup_type, score=score, reason="test", direction=direction,
    )


def _high_event():
    return SimpleNamespace(impact_level="HIGH", event_type="FOMC")


def _medium_event():
    return SimpleNamespace(impact_level="MEDIUM", event_type="EARNINGS")


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — trailing stop
# ─────────────────────────────────────────────────────────────────


def test_trailing_inactive_when_peak_below_activation():
    swing = _swing()
    # entry=1.0, peak=1.20 → 1.20 < 1.30 (activation) → not active
    pos = _position(entry=1.0, peak=1.20, current=1.10)
    state = _state()
    decision = swing.evaluate_exit(pos, 1.10, _market(), [], state)
    assert decision.should_exit is False


def test_trailing_active_no_drawdown_no_exit():
    swing = _swing()
    pos = _position(entry=1.0, peak=1.30, current=1.30)
    decision = swing.evaluate_exit(pos, 1.30, _market(), [], _state())
    assert decision.should_exit is False


def test_trailing_active_drawdown_below_threshold_no_exit():
    swing = _swing()
    # peak=1.50, current=1.10 → drawdown = 0.40/1.50 ≈ 0.267 < 0.35
    pos = _position(entry=1.0, peak=1.50, current=1.10)
    decision = swing.evaluate_exit(pos, 1.10, _market(), [], _state())
    assert decision.should_exit is False


def test_trailing_drawdown_at_boundary_exits():
    """peak=2.0, current=1.30 → drawdown = 0.70/2.0 = 0.35 exactly (clean
    in IEEE arithmetic on these values)."""
    swing = _swing()
    pos = _position(entry=1.0, peak=2.0, current=1.30)
    decision = swing.evaluate_exit(pos, 1.30, _market(), [], _state())
    assert decision.should_exit is True
    assert decision.reason == "trailing_stop"


def test_trailing_drawdown_above_threshold_exits():
    swing = _swing()
    pos = _position(entry=1.0, peak=1.50, current=0.90)
    decision = swing.evaluate_exit(pos, 0.90, _market(), [], _state())
    assert decision.should_exit is True
    assert decision.reason == "trailing_stop"


def test_trailing_priority_over_hard_loss():
    """Trailing condition met AND hard-loss condition met → trailing wins."""
    swing = _swing()
    # peak=1.50 (active), current=0.30 (drawdown >35%, also hard-loss vs entry=1.0)
    pos = _position(entry=1.0, peak=1.50, current=0.30)
    decision = swing.evaluate_exit(pos, 0.30, _market(), [], _state())
    assert decision.reason == "trailing_stop"


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — hard contract loss
# ─────────────────────────────────────────────────────────────────


def test_hard_loss_exact_boundary_exits():
    """entry=1.0, current=0.40 → gain = -0.60 exactly. Predicate is <=."""
    swing = _swing()
    pos = _position(entry=1.0, peak=1.0, current=0.40)
    decision = swing.evaluate_exit(pos, 0.40, _market(), [], _state())
    assert decision.should_exit is True
    assert decision.reason == "hard_contract_loss"


def test_hard_loss_just_above_boundary_no_exit():
    swing = _swing()
    pos = _position(entry=1.0, peak=1.0, current=0.41)  # gain = -0.59
    decision = swing.evaluate_exit(pos, 0.41, _market(), [], _state())
    assert decision.should_exit is False


def test_hard_loss_just_below_boundary_exits():
    swing = _swing()
    pos = _position(entry=1.0, peak=1.0, current=0.39)  # gain ≈ -0.61
    decision = swing.evaluate_exit(pos, 0.39, _market(), [], _state())
    assert decision.should_exit is True
    assert decision.reason == "hard_contract_loss"


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — hard contract loss ProfileConfig bridge (CLEAN-1)
# ─────────────────────────────────────────────────────────────────


def test_hard_loss_uses_profile_config_when_available():
    """CLEAN-1: evaluate_exit reads self.config.hard_contract_loss_pct
    when set, divides by 100 to convert percent → fraction. With
    config=80.0 (percent → 0.80 fraction), entry=1.0, current=0.25
    → gain=-0.75 → 0.75 < 0.80 → no exit (would have exited at
    default 0.60 threshold)."""
    swing = _swing(config=_config(hard_contract_loss_pct=80.0))
    pos = _position(entry=1.0, peak=1.0, current=0.25)  # gain = -0.75
    decision = swing.evaluate_exit(pos, 0.25, _market(), [], _state())
    assert decision.should_exit is False, (
        "config 80% should override default 60%; gain=-75% does not "
        "trigger exit at -80% threshold"
    )


def test_hard_loss_falls_back_to_default_when_config_missing_attr():
    """CLEAN-1: defensive fallback path. If self.config has no
    hard_contract_loss_pct attribute (e.g. a future ProfileConfig
    without the field, or a stub with hasattr=False), evaluate_exit
    must use HARD_LOSS_PCT_DEFAULT (0.60). Verified by stripping
    the attribute via a lightweight stub and checking that the
    default-threshold behavior fires at -60% gain."""
    swing = _swing()
    # Replace self.config with a stub lacking hard_contract_loss_pct
    # to exercise the hasattr-False branch.

    class _StubConfig:
        name = "stub"
        # No hard_contract_loss_pct attribute.

    swing.config = _StubConfig()
    pos = _position(entry=1.0, peak=1.0, current=0.40)  # gain = -0.60
    decision = swing.evaluate_exit(pos, 0.40, _market(), [], _state())
    assert decision.should_exit is True
    assert decision.reason == "hard_contract_loss"


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — thesis break (single-cycle behavior)
# ─────────────────────────────────────────────────────────────────


def test_thesis_candidate_increments_streak_no_exit():
    """Call position; bearish setup ≥ 0.30 + no qualifying bullish setup
    → candidate; streak goes 0→1; no exit yet."""
    swing = _swing()
    pos = _position()  # call
    state = _state()
    setups = [_ss(score=0.40, direction="bearish")]
    decision = swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert decision.should_exit is False
    assert state.thesis_break_streaks.get("t-1") == 1


def test_thesis_qualifying_entry_dir_setup_resets_streak():
    swing = _swing()
    pos = _position()  # call
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    setups = [_ss(score=0.40, direction="bullish")]  # entry-dir present
    decision = swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert decision.should_exit is False
    assert "t-1" not in state.thesis_break_streaks


def test_thesis_opposite_below_threshold_resets_streak():
    swing = _swing()
    pos = _position()  # call
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    setups = [_ss(score=0.29, direction="bearish")]  # below 0.30 threshold
    decision = swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert decision.should_exit is False
    assert "t-1" not in state.thesis_break_streaks


def test_thesis_candidate_then_absent_resets():
    swing = _swing()
    pos = _position()
    state = _state()
    # Cycle 1 — candidate
    swing.evaluate_exit(
        pos, 1.0, _market(),
        [_ss(score=0.40, direction="bearish")], state,
    )
    assert state.thesis_break_streaks.get("t-1") == 1
    # Cycle 2 — bullish setup, candidate False
    swing.evaluate_exit(
        pos, 1.0, _market(),
        [_ss(score=0.40, direction="bullish")], state,
    )
    assert "t-1" not in state.thesis_break_streaks


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — thesis break (multi-cycle confirmation)
# ─────────────────────────────────────────────────────────────────


def test_thesis_two_consecutive_candidate_cycles_exits():
    swing = _swing()
    pos = _position()
    state = _state()
    setups = [_ss(score=0.40, direction="bearish")]
    # Cycle 1 — streak 0→1, no exit
    d1 = swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert d1.should_exit is False
    assert state.thesis_break_streaks.get("t-1") == 1
    # Cycle 2 — streak 1→2, exit
    d2 = swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert d2.should_exit is True
    assert d2.reason == "thesis_break"
    assert "t-1" not in state.thesis_break_streaks


def test_thesis_break_in_streak_prevents_exit():
    """Candidate, non-candidate, candidate → no exit (streak resets in middle)."""
    swing = _swing()
    pos = _position()
    state = _state()
    bearish = [_ss(score=0.40, direction="bearish")]
    bullish = [_ss(score=0.40, direction="bullish")]
    swing.evaluate_exit(pos, 1.0, _market(), bearish, state)  # streak=1
    swing.evaluate_exit(pos, 1.0, _market(), bullish, state)  # reset
    decision = swing.evaluate_exit(pos, 1.0, _market(), bearish, state)  # streak=1
    assert decision.should_exit is False
    assert state.thesis_break_streaks.get("t-1") == 1


def test_thesis_preexisting_streak_one_more_cycle_exits():
    swing = _swing()
    pos = _position()
    state = _state()
    state.thesis_break_streaks["t-1"] = 1  # carried over
    setups = [_ss(score=0.40, direction="bearish")]
    decision = swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert decision.should_exit is True
    assert decision.reason == "thesis_break"
    assert "t-1" not in state.thesis_break_streaks


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — thesis break direction translation
# ─────────────────────────────────────────────────────────────────


def test_thesis_call_position_treats_bearish_as_opposite():
    swing = _swing()
    pos = _position(side="call")
    state = _state()
    state.thesis_break_streaks["t-1"] = 1  # one cycle already
    setups = [_ss(score=0.35, direction="bearish")]  # bearish ≥ 0.30
    decision = swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert decision.should_exit is True
    assert decision.reason == "thesis_break"


def test_thesis_put_position_treats_bullish_as_opposite():
    swing = _swing()
    pos = _position(side="put")
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    setups = [_ss(score=0.35, direction="bullish")]  # bullish ≥ 0.30
    decision = swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert decision.should_exit is True
    assert decision.reason == "thesis_break"


def test_thesis_garbage_right_skips_check_with_warning(caplog):
    """Defensive: position with right='garbage' skips thesis-break check
    but other triggers still proceed. Pair with a no-trigger scenario and
    confirm we end at no_exit + warning logged."""
    swing = _swing()
    pos = _position(side="garbage")
    caplog.set_level(logging.WARNING, logger="options-bot.profiles.swing")
    decision = swing.evaluate_exit(
        pos, 1.0, _market(),
        [_ss(score=0.40, direction="bearish")],  # would be candidate for valid right
        _state(),
    )
    assert decision.should_exit is False
    assert decision.reason == "no_exit"
    assert any(
        "unexpected contract.right" in r.getMessage()
        for r in caplog.records
    )


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — DTE floor
# ─────────────────────────────────────────────────────────────────


def test_dte_above_floor_no_exit():
    swing = _swing()
    pos = _position(expiration_days_out=4)  # DTE=4 > 3
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], _state())
    assert decision.should_exit is False


def test_dte_at_floor_exits():
    swing = _swing()
    pos = _position(expiration_days_out=3)
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], _state())
    assert decision.should_exit is True
    assert decision.reason == "dte_floor"


def test_dte_zero_exits():
    swing = _swing()
    pos = _position(expiration_days_out=0)
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], _state())
    assert decision.should_exit is True
    assert decision.reason == "dte_floor"


def test_dte_negative_exits():
    """Position past expiration — still fires DTE floor."""
    swing = _swing()
    pos = _position(expiration_days_out=-1)
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], _state())
    assert decision.should_exit is True
    assert decision.reason == "dte_floor"


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — pre-event close
# ─────────────────────────────────────────────────────────────────


def test_pre_event_no_high_events_no_exit():
    macro = MagicMock(return_value=[])
    swing = _swing(macro_fetcher=macro)
    pos = _position()
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], _state())
    assert decision.should_exit is False
    macro.assert_called_once_with("TSLA", 1440)


def test_pre_event_high_event_exits():
    macro = MagicMock(return_value=[_high_event()])
    swing = _swing(macro_fetcher=macro)
    pos = _position()
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], _state())
    assert decision.should_exit is True
    assert decision.reason == "pre_event_close"


def test_pre_event_only_medium_low_no_exit():
    macro = MagicMock(return_value=[_medium_event()])
    swing = _swing(macro_fetcher=macro)
    pos = _position()
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], _state())
    assert decision.should_exit is False


def test_pre_event_macro_fetcher_unset_skips_check():
    swing = _swing(macro_fetcher=None)
    pos = _position()
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], _state())
    assert decision.should_exit is False
    assert decision.reason == "no_exit"


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — priority order
# ─────────────────────────────────────────────────────────────────


def test_priority_trailing_beats_hard_loss():
    swing = _swing()
    # peak=1.50 (active), current=0.30 → drawdown >35% AND hard-loss vs entry=1.0
    pos = _position(entry=1.0, peak=1.50, current=0.30)
    decision = swing.evaluate_exit(pos, 0.30, _market(), [], _state())
    assert decision.reason == "trailing_stop"


def test_priority_trailing_beats_thesis_break():
    swing = _swing()
    pos = _position(entry=1.0, peak=2.0, current=1.30)  # trailing fires
    state = _state()
    state.thesis_break_streaks["t-1"] = 1  # would push to 2 if checked
    setups = [_ss(score=0.40, direction="bearish")]
    decision = swing.evaluate_exit(pos, 1.30, _market(), setups, state)
    assert decision.reason == "trailing_stop"
    # Trailing's pop runs before thesis check, so streak is cleared.
    assert "t-1" not in state.thesis_break_streaks


def test_priority_trailing_beats_dte_floor():
    swing = _swing()
    pos = _position(entry=1.0, peak=2.0, current=1.30,
                    expiration_days_out=2)  # both fire
    decision = swing.evaluate_exit(pos, 1.30, _market(), [], _state())
    assert decision.reason == "trailing_stop"


def test_priority_trailing_beats_pre_event():
    macro = MagicMock(return_value=[_high_event()])
    swing = _swing(macro_fetcher=macro)
    pos = _position(entry=1.0, peak=2.0, current=1.30)
    decision = swing.evaluate_exit(pos, 1.30, _market(), [], _state())
    assert decision.reason == "trailing_stop"


def test_priority_hard_loss_beats_thesis_break():
    swing = _swing()
    pos = _position(entry=1.0, peak=1.0, current=0.40)  # hard loss
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    setups = [_ss(score=0.40, direction="bearish")]
    decision = swing.evaluate_exit(pos, 0.40, _market(), setups, state)
    assert decision.reason == "hard_contract_loss"
    assert "t-1" not in state.thesis_break_streaks


def test_priority_hard_loss_beats_dte_floor():
    swing = _swing()
    pos = _position(entry=1.0, peak=1.0, current=0.40, expiration_days_out=2)
    decision = swing.evaluate_exit(pos, 0.40, _market(), [], _state())
    assert decision.reason == "hard_contract_loss"


def test_priority_hard_loss_beats_pre_event():
    macro = MagicMock(return_value=[_high_event()])
    swing = _swing(macro_fetcher=macro)
    pos = _position(entry=1.0, peak=1.0, current=0.40)
    decision = swing.evaluate_exit(pos, 0.40, _market(), [], _state())
    assert decision.reason == "hard_contract_loss"


def test_priority_thesis_break_beats_dte_floor():
    swing = _swing()
    pos = _position(expiration_days_out=2)  # DTE would fire
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    setups = [_ss(score=0.40, direction="bearish")]
    decision = swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert decision.reason == "thesis_break"


def test_priority_thesis_break_beats_pre_event():
    macro = MagicMock(return_value=[_high_event()])
    swing = _swing(macro_fetcher=macro)
    pos = _position()
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    setups = [_ss(score=0.40, direction="bearish")]
    decision = swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert decision.reason == "thesis_break"


def test_priority_dte_floor_beats_pre_event():
    macro = MagicMock(return_value=[_high_event()])
    swing = _swing(macro_fetcher=macro)
    pos = _position(expiration_days_out=2)  # DTE fires
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], _state())
    assert decision.reason == "dte_floor"


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — streak cleanup on exit
# ─────────────────────────────────────────────────────────────────


def test_streak_cleared_when_trailing_fires():
    swing = _swing()
    pos = _position(entry=1.0, peak=2.0, current=1.30)
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    swing.evaluate_exit(pos, 1.30, _market(), [], state)
    assert "t-1" not in state.thesis_break_streaks


def test_streak_cleared_when_hard_loss_fires():
    swing = _swing()
    pos = _position(entry=1.0, peak=1.0, current=0.40)
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    swing.evaluate_exit(pos, 0.40, _market(), [], state)
    assert "t-1" not in state.thesis_break_streaks


def test_streak_cleared_when_dte_floor_fires():
    swing = _swing()
    pos = _position(expiration_days_out=3)
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    swing.evaluate_exit(pos, 1.0, _market(), [], state)
    assert "t-1" not in state.thesis_break_streaks


def test_streak_cleared_when_pre_event_fires():
    macro = MagicMock(return_value=[_high_event()])
    swing = _swing(macro_fetcher=macro)
    pos = _position()
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    swing.evaluate_exit(pos, 1.0, _market(), [], state)
    assert "t-1" not in state.thesis_break_streaks


def test_streak_cleared_when_thesis_break_fires():
    swing = _swing()
    pos = _position()
    state = _state()
    state.thesis_break_streaks["t-1"] = 1
    setups = [_ss(score=0.40, direction="bearish")]
    swing.evaluate_exit(pos, 1.0, _market(), setups, state)
    assert "t-1" not in state.thesis_break_streaks


# ─────────────────────────────────────────────────────────────────
# evaluate_exit — no-exit terminal case
# ─────────────────────────────────────────────────────────────────


def test_no_exit_when_no_trigger_fires():
    swing = _swing()
    pos = _position()
    state = _state()
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], state)
    assert decision.should_exit is False
    assert decision.reason == "no_exit"
    assert "t-1" not in state.thesis_break_streaks


def test_no_exit_returns_exit_decision_type():
    swing = _swing()
    pos = _position()
    decision = swing.evaluate_exit(pos, 1.0, _market(), [], _state())
    from profiles.base_preset import ExitDecision
    assert isinstance(decision, ExitDecision)
