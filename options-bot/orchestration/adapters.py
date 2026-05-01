"""Adapters bridging legacy V2Strategy state and new BasePreset
interfaces.

The legacy V2Strategy holds per-profile state across in-memory
dicts (self._last_entry_time, self._last_exit_reason) and per-
iteration call sites (snapshot_macro_context() returns a
MacroContext). The new BasePreset interface expects a frozen
ProfileState dataclass and a per-symbol macro_fetcher callable.

These adapters translate:
  - macro_context_to_event_fetcher: MacroContext + lookahead_minutes
    → list[MacroEvent] (matches BasePreset's get_active_events
    signature)
  - build_profile_state: in-memory dicts → frozen ProfileState
  - resolve_preset_mode: ProfileConfig + preset name → effective
    execution mode (signal_only / live / shadow)

No state lives in this module; all functions are pure given their
inputs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from macro.reader import MacroContext, MacroEvent
from profiles.base_preset import ProfileState


_VALID_MODES = ("live", "shadow", "signal_only")


def macro_context_to_event_fetcher(
    macro_ctx: Optional[MacroContext],
) -> Callable[[str, int], list]:
    """Returns a closure matching BasePreset's macro_fetcher
    signature: (symbol, lookahead_minutes) -> list[MacroEvent].

    The returned callable filters macro_ctx.events_by_symbol to
    events for the given symbol (or '*' for market-wide) where
    minutes_until <= lookahead_minutes.

    If macro_ctx is None, the callable returns an empty list.

    Note on past events: the upstream snapshot_macro_context already
    drops events older than 1 minute past (macro/reader.py's
    delta_min < -1 filter), so the adapter does not need a lower
    bound. Imminent / just-released events with negative minutes_until
    pass through.
    """
    def _fetch(symbol: str, lookahead_minutes: int) -> list:
        if macro_ctx is None:
            return []
        # snapshot_macro_context already merges '*' (market-wide)
        # events into every per-symbol bucket. Look up by symbol;
        # fall back to the explicit '*' bucket if the symbol has no
        # events.
        bucket = macro_ctx.events_by_symbol.get(
            symbol, macro_ctx.events_by_symbol.get("*", []),
        )
        return [
            ev for ev in bucket
            if ev.minutes_until <= lookahead_minutes
        ]
    return _fetch


def build_profile_state(
    open_positions: list,
    capital_deployed: float,
    account_pnl_pct: float,
    last_exit_at: Optional[datetime],
    last_entry_at: Optional[datetime],
    recent_exits_by_symbol: Optional[dict] = None,
    recent_entries_by_symbol_direction: Optional[dict] = None,
    thesis_break_streaks: Optional[dict] = None,
) -> ProfileState:
    """Builds a frozen ProfileState from V2Strategy's in-memory
    state. The orchestrator (C5b) calls this once per iteration
    per active profile.

    Optional dicts default to empty dicts. When None is passed, the
    adapter omits the kwarg so ProfileState's default_factory creates
    a fresh dict (no shared-mutable-default leakage between calls).

    Note on open_positions: ProfileState.current_open_positions is
    typed `int` (a count). The adapter accepts the V2Strategy-level
    list of open position objects and converts via len() so callers
    don't need to compute the count themselves.
    """
    kwargs = {
        "current_open_positions": len(open_positions),
        "current_capital_deployed": capital_deployed,
        "today_account_pnl_pct": account_pnl_pct,
        "last_exit_at": last_exit_at,
        "last_entry_at": last_entry_at,
    }
    if recent_exits_by_symbol is not None:
        kwargs["recent_exits_by_symbol"] = recent_exits_by_symbol
    if recent_entries_by_symbol_direction is not None:
        kwargs["recent_entries_by_symbol_direction"] = (
            recent_entries_by_symbol_direction
        )
    if thesis_break_streaks is not None:
        kwargs["thesis_break_streaks"] = thesis_break_streaks
    return ProfileState(**kwargs)


def resolve_preset_mode(
    preset_name: str,
    global_execution_mode: str,
) -> str:
    """Determines effective execution mode for a preset.

    Per Phase 1a/1b roadmap (ARCHITECTURE.md §6 + §4.2 Phase 1a
    scope note):
      - 0dte_asymmetric: always signal_only through Phase 1b,
        regardless of global mode
      - swing: respects global mode (live/shadow/signal_only)
      - any other preset: respects global mode

    Returns one of "live", "shadow", "signal_only".
    Raises ValueError if global_execution_mode is invalid.
    """
    if global_execution_mode not in _VALID_MODES:
        raise ValueError(
            f"global_execution_mode must be one of {_VALID_MODES}, "
            f"got {global_execution_mode!r}"
        )
    if preset_name == "0dte_asymmetric":
        return "signal_only"
    return global_execution_mode
