"""Unit tests for orchestration.adapters.

C5a (foundation prompt) — verifies the three adapter functions in
isolation. None of these tests exercise V2Strategy or any production
call site; the orchestrator wire-in lands in C5b.

Run via:
    python -m pytest tests/test_orchestration_adapters.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from macro.reader import MacroContext, MacroEvent  # noqa: E402
from orchestration.adapters import (  # noqa: E402
    build_profile_state,
    macro_context_to_event_fetcher,
    resolve_preset_mode,
)
from profiles.base_preset import ProfileState  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _event(
    symbol: str = "SPY",
    event_type: str = "FOMC",
    impact_level: str = "HIGH",
    minutes_until: int = 60,
) -> MacroEvent:
    return MacroEvent(
        symbol=symbol,
        event_type=event_type,
        event_time_et=datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc),
        impact_level=impact_level,
        source_url="https://example.com",
        minutes_until=minutes_until,
    )


def _ctx(events_by_symbol: dict) -> MacroContext:
    return MacroContext(
        events_by_symbol=events_by_symbol,
        catalysts_by_symbol={},
        regime=None,
        fetched_at=datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
    )


# ═════════════════════════════════════════════════════════════════
# macro_context_to_event_fetcher
# ═════════════════════════════════════════════════════════════════


def test_event_fetcher_none_context_returns_empty():
    fetcher = macro_context_to_event_fetcher(None)
    assert fetcher("SPY", 240) == []


def test_event_fetcher_returns_symbol_bucket():
    """snapshot_macro_context already merges '*' into every per-symbol
    bucket — the adapter just looks up by symbol."""
    spy_events = [_event(symbol="SPY", minutes_until=60)]
    ctx = _ctx({"SPY": spy_events, "*": []})
    fetcher = macro_context_to_event_fetcher(ctx)
    out = fetcher("SPY", 240)
    assert len(out) == 1
    assert out[0].symbol == "SPY"


def test_event_fetcher_lookahead_filters_far_future_events():
    near = _event(symbol="SPY", minutes_until=60)
    far = _event(symbol="SPY", event_type="EARNINGS", minutes_until=300)
    ctx = _ctx({"SPY": [near, far]})
    fetcher = macro_context_to_event_fetcher(ctx)
    # lookahead 240 — `far` (300) is excluded
    out = fetcher("SPY", 240)
    assert len(out) == 1
    assert out[0].event_type == "FOMC"


def test_event_fetcher_unknown_symbol_falls_back_to_wildcard_bucket():
    """Per snapshot_macro_context's documented contract, the '*' bucket
    is preserved so callers passing an unknown symbol still see
    market-wide wildcards."""
    wildcard = _event(symbol="*", event_type="CPI", minutes_until=120)
    ctx = _ctx({"*": [wildcard]})
    fetcher = macro_context_to_event_fetcher(ctx)
    out = fetcher("XYZ", 240)
    assert len(out) == 1
    assert out[0].event_type == "CPI"


def test_event_fetcher_unknown_symbol_no_wildcard_returns_empty():
    ctx = _ctx({"SPY": [_event()]})  # no '*' bucket
    fetcher = macro_context_to_event_fetcher(ctx)
    assert fetcher("XYZ", 240) == []


def test_event_fetcher_negative_minutes_until_included_when_within_lookahead():
    """The upstream macro reader drops events older than -1 minute, so
    events_by_symbol only contains events with minutes_until >= -1.
    The adapter must include those (they're imminent/just-released,
    not stale)."""
    just_past = _event(symbol="SPY", minutes_until=-1)
    ctx = _ctx({"SPY": [just_past]})
    fetcher = macro_context_to_event_fetcher(ctx)
    out = fetcher("SPY", 240)
    assert len(out) == 1
    assert out[0].minutes_until == -1


def test_event_fetcher_zero_lookahead_excludes_future_events():
    future = _event(symbol="SPY", minutes_until=60)
    ctx = _ctx({"SPY": [future]})
    fetcher = macro_context_to_event_fetcher(ctx)
    assert fetcher("SPY", 0) == []


# ═════════════════════════════════════════════════════════════════
# build_profile_state
# ═════════════════════════════════════════════════════════════════


def test_build_state_all_defaults_yields_empty_dicts():
    state = build_profile_state(
        open_positions=[],
        capital_deployed=0.0,
        account_pnl_pct=0.0,
        last_exit_at=None,
        last_entry_at=None,
    )
    assert isinstance(state, ProfileState)
    assert state.current_open_positions == 0
    assert state.recent_exits_by_symbol == {}
    assert state.recent_entries_by_symbol_direction == {}
    assert state.thesis_break_streaks == {}


def test_build_state_passes_dicts_through():
    exits = {"SPY": datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)}
    entries = {
        "SPY:bullish": datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
    }
    streaks = {"trade-uuid-1": 1}
    state = build_profile_state(
        open_positions=[],
        capital_deployed=0.0,
        account_pnl_pct=0.0,
        last_exit_at=None,
        last_entry_at=None,
        recent_exits_by_symbol=exits,
        recent_entries_by_symbol_direction=entries,
        thesis_break_streaks=streaks,
    )
    assert state.recent_exits_by_symbol == exits
    assert state.recent_entries_by_symbol_direction == entries
    assert state.thesis_break_streaks == streaks


def test_build_state_preserves_timestamps():
    last_exit = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    last_entry = datetime(2026, 5, 1, 9, 30, tzinfo=timezone.utc)
    state = build_profile_state(
        open_positions=[],
        capital_deployed=0.0,
        account_pnl_pct=0.0,
        last_exit_at=last_exit,
        last_entry_at=last_entry,
    )
    assert state.last_exit_at == last_exit
    assert state.last_entry_at == last_entry


def test_build_state_default_factory_yields_fresh_dict_per_call():
    """When None is passed for a dict arg, default_factory creates a
    fresh dict — mutating one call's state does not leak into another
    call's defaults."""
    state1 = build_profile_state(
        open_positions=[],
        capital_deployed=0.0,
        account_pnl_pct=0.0,
        last_exit_at=None,
        last_entry_at=None,
    )
    state1.thesis_break_streaks["leaked-id"] = 99
    state2 = build_profile_state(
        open_positions=[],
        capital_deployed=0.0,
        account_pnl_pct=0.0,
        last_exit_at=None,
        last_entry_at=None,
    )
    assert "leaked-id" not in state2.thesis_break_streaks
    assert state2.thesis_break_streaks == {}


def test_build_state_capital_and_pnl_passthrough():
    state = build_profile_state(
        open_positions=[SimpleNamespace(), SimpleNamespace()],  # 2 positions
        capital_deployed=1234.56,
        account_pnl_pct=-2.5,
        last_exit_at=None,
        last_entry_at=None,
    )
    assert state.current_open_positions == 2
    assert state.current_capital_deployed == 1234.56
    assert state.today_account_pnl_pct == -2.5


def test_build_state_open_positions_list_converted_to_count():
    """Verifies the list → int conversion documented in the adapter
    docstring."""
    positions = [object(), object(), object()]
    state = build_profile_state(
        open_positions=positions,
        capital_deployed=0.0,
        account_pnl_pct=0.0,
        last_exit_at=None,
        last_entry_at=None,
    )
    assert state.current_open_positions == 3


# ═════════════════════════════════════════════════════════════════
# resolve_preset_mode
# ═════════════════════════════════════════════════════════════════


def test_resolve_zero_dte_with_live_returns_signal_only():
    assert resolve_preset_mode("0dte_asymmetric", "live") == "signal_only"


def test_resolve_zero_dte_with_shadow_returns_signal_only():
    assert resolve_preset_mode("0dte_asymmetric", "shadow") == "signal_only"


def test_resolve_zero_dte_with_signal_only_returns_signal_only():
    assert (
        resolve_preset_mode("0dte_asymmetric", "signal_only")
        == "signal_only"
    )


def test_resolve_swing_with_live_returns_live():
    assert resolve_preset_mode("swing", "live") == "live"


def test_resolve_swing_with_shadow_returns_shadow():
    assert resolve_preset_mode("swing", "shadow") == "shadow"


def test_resolve_swing_with_signal_only_returns_signal_only():
    assert resolve_preset_mode("swing", "signal_only") == "signal_only"


def test_resolve_legacy_preset_passes_through():
    """momentum / mean_reversion / catalyst / scalp_0dte / tsla_swing
    are not in the new pipeline yet; the adapter respects the global
    mode for them so call sites can use one resolver across legacy
    and new presets uniformly."""
    assert resolve_preset_mode("momentum", "live") == "live"
    assert resolve_preset_mode("mean_reversion", "shadow") == "shadow"


def test_resolve_invalid_global_mode_raises():
    with pytest.raises(ValueError, match="must be one of"):
        resolve_preset_mode("swing", "invalid")


def test_resolve_empty_global_mode_raises():
    with pytest.raises(ValueError, match="must be one of"):
        resolve_preset_mode("swing", "")
