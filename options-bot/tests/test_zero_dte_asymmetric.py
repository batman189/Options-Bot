"""Unit tests for profiles.zero_dte_asymmetric.ZeroDteAsymmetricPreset.

Pure logic — no DB, no network, no filesystem. All four fetchers
(macro, vix_spike, bars, now) are dependency-injected, so production
data-layer modules are never imported. Mirrors the pytest style of
test_swing_preset.py.

Run via:
    python -m pytest tests/test_zero_dte_asymmetric.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from market.context import MarketSnapshot, Regime, TimeOfDay  # noqa: E402
from profiles.base_preset import (  # noqa: E402
    EntryDecision,
    ProfileState,
)
from profiles.profile_config import ProfileConfig  # noqa: E402
from profiles.zero_dte_asymmetric import (  # noqa: E402
    ET,
    ZeroDteAsymmetricPreset,
)
from scanner.setups import SetupScore  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

MIN_VALID_CONFIG = {
    "name": "0dte-test",
    "preset": "0dte_asymmetric",
    "symbols": ["SPY"],
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


def _state(
    recent_entries: dict | None = None,
) -> ProfileState:
    return ProfileState(
        current_open_positions=0,
        current_capital_deployed=0.0,
        today_account_pnl_pct=0.0,
        last_exit_at=None,
        last_entry_at=None,
        recent_exits_by_symbol={},
        recent_entries_by_symbol_direction=recent_entries or {},
    )


def _macro_event(
    impact_level: str = "HIGH",
    event_type: str = "FOMC",
    minutes_until: int = 60,
):
    """Build a duck-typed MacroEvent — only the attrs the preset reads."""
    return SimpleNamespace(
        impact_level=impact_level,
        event_type=event_type,
        minutes_until=minutes_until,
    )


def _now_at(et_time: time, et_date=None) -> datetime:
    """Build a tz-aware UTC datetime corresponding to a wall-clock ET time
    on a given ET date (default 2026-04-28, a Tuesday). The fixture date
    is non-DST-boundary (April), so US/Eastern is UTC-4."""
    et_date = et_date or datetime(2026, 4, 28).date()
    naive = datetime.combine(et_date, et_time)
    aware_et = naive.replace(tzinfo=ET)
    return aware_et.astimezone(timezone.utc)


def _now_fetcher(et_time: time, et_date=None):
    """Return a callable that, when called, returns the configured time."""
    target = _now_at(et_time, et_date)
    return lambda: target


def _bars_fetcher_for(*, daily=None, ema=None, vwap=None, one_min=None):
    """Build a bars_fetcher that dispatches by (timeframe, count).

    Each kwarg either holds a DataFrame (returned for that timeframe) or
    None (raises to simulate fetch failure when called).
    """
    def fetcher(symbol, timeframe, count):
        if timeframe == "1Day":
            if daily is None:
                return None
            return daily
        if timeframe == "5Min":
            if ema is None:
                return None
            return ema
        if timeframe == "1Min":
            # The preset uses 1Min for both VWAP (count=240), the
            # directional check (count=5), and the underlying-price
            # fetch (count=1). The same DF works for all three when we
            # construct it carefully.
            if vwap is None and one_min is None:
                return None
            return one_min if count <= 5 else vwap
        return None
    return fetcher


def _make_daily(prior_high=400.0, prior_low=395.0):
    return pd.DataFrame({
        "open":   [398.0, 401.0],
        "high":   [prior_high, 410.0],
        "low":    [prior_low, 396.0],
        "close":  [399.0, 405.0],
        "volume": [10_000_000, 8_000_000],
    })


def _make_ema_bars(closes):
    return pd.DataFrame({
        "open":   closes,
        "high":   closes,
        "low":    closes,
        "close":  closes,
        "volume": [1_000_000] * len(closes),
    })


def _make_vwap_bars(price=405.0, n=60):
    return pd.DataFrame({
        "open":   [price] * n,
        "high":   [price] * n,
        "low":    [price] * n,
        "close":  [price] * n,
        "volume": [1_000_000] * n,
    })


def _make_1min_directional(direction: str, last_close: float = 405.0, n: int = 5):
    """Build n 1-min bars with the last 3 all in the requested direction."""
    rows = []
    for i in range(n):
        c = last_close - (n - 1 - i) * 0.10
        if direction == "bullish":
            o = c - 0.05
        elif direction == "bearish":
            o = c + 0.05
        else:
            o = c
        rows.append({
            "open": o,
            "high": max(o, c) + 0.05,
            "low":  min(o, c) - 0.05,
            "close": c,
            "volume": 1_000_000,
        })
    return pd.DataFrame(rows)


def _full_bullish_setup_bars(price=405.0):
    """Bars set that produces a full bullish technical confirmation when
    price=405.0 and the prior-day high=400.0."""
    return _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 30),  # EMA stabilizes at 400 < 405
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=_make_1min_directional("bullish", last_close=price, n=5),
    )


def _full_bearish_setup_bars(price=390.0):
    """Bars set producing full bearish technical confirmation when
    price=390.0 and prior-day low=395.0."""
    return _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=_make_1min_directional("bearish", last_close=price, n=5),
    )


def _preset(
    macro_fetcher=None,
    vix_spike_fetcher=None,
    bars_fetcher=None,
    now_fetcher=None,
    config: ProfileConfig | None = None,
):
    """Default to a now_fetcher inside the entry window so tests don't have
    to pass it explicitly when they don't care about time."""
    if now_fetcher is None:
        now_fetcher = _now_fetcher(time(10, 30))
    return ZeroDteAsymmetricPreset(
        config=config or _config(),
        macro_fetcher=macro_fetcher,
        vix_spike_fetcher=vix_spike_fetcher,
        bars_fetcher=bars_fetcher,
        now_fetcher=now_fetcher,
    )


# ═════════════════════════════════════════════════════════════════
# Construction
# ═════════════════════════════════════════════════════════════════


def test_construct_with_valid_config():
    p = _preset()
    assert p.name == "0dte_asymmetric"
    assert p.config.name == "0dte-test"


def test_accepted_setup_types_is_full_5_set():
    p = _preset()
    assert p.accepted_setup_types == frozenset({
        "momentum", "mean_reversion", "compression_breakout",
        "catalyst", "macro_trend",
    })


def test_constants_match_spec():
    p = _preset()
    assert p.ENTRY_WINDOW_START == time(9, 35)
    assert p.ENTRY_WINDOW_END == time(13, 30)
    assert p.MACRO_LOOKAHEAD_MINUTES == 240
    assert p.MAG_7_POST_EARNINGS_MINUTES == 60
    assert p.VIX_SPIKE_THRESHOLD_PCT == 15.0
    assert p.MAX_ENTRIES_PER_DAY == 2
    assert p.SAME_DIRECTION_COOLDOWN_MINUTES == 60
    assert p.MAG_7_SYMBOLS == frozenset({
        "TSLA", "NVDA", "AAPL", "MSFT", "META", "AMZN", "GOOG",
    })


def test_construct_with_no_fetchers():
    """All fetchers default to None; class still instantiates."""
    p = ZeroDteAsymmetricPreset(_config())
    assert p._macro_fetcher is None
    assert p._vix_spike_fetcher is None
    assert p._bars_fetcher is None
    assert p._now_fetcher is None


def test_now_fetcher_must_return_aware():
    p = _preset(now_fetcher=lambda: datetime(2026, 4, 28, 10, 30))
    with pytest.raises(ValueError, match="tz-aware"):
        p._now_utc()


# ═════════════════════════════════════════════════════════════════
# is_active_now / time gate
# ═════════════════════════════════════════════════════════════════


def test_is_active_now_at_window_start():
    p = _preset(now_fetcher=_now_fetcher(time(9, 35)))
    assert p.is_active_now(_market()) is True


def test_is_active_now_at_window_end():
    p = _preset(now_fetcher=_now_fetcher(time(13, 30)))
    assert p.is_active_now(_market()) is True


def test_is_active_now_just_before_open():
    p = _preset(now_fetcher=_now_fetcher(time(9, 34, 59)))
    assert p.is_active_now(_market()) is False


def test_is_active_now_just_after_close():
    p = _preset(now_fetcher=_now_fetcher(time(13, 30, 1)))
    assert p.is_active_now(_market()) is False


def test_is_active_now_premarket():
    p = _preset(now_fetcher=_now_fetcher(time(8, 0)))
    assert p.is_active_now(_market()) is False


def test_is_active_now_afternoon():
    p = _preset(now_fetcher=_now_fetcher(time(15, 0)))
    assert p.is_active_now(_market()) is False


def test_is_active_now_midwindow():
    p = _preset(now_fetcher=_now_fetcher(time(11, 0)))
    assert p.is_active_now(_market()) is True


def test_evaluate_entry_outside_window_blocks_first():
    """Time gate is checked BEFORE bars/macro/vix fetchers are touched —
    a fully-blank preset still rejects on time alone."""
    p = _preset(now_fetcher=_now_fetcher(time(8, 0)))
    decision = p.evaluate_entry("SPY", _setup(), _market(), _state())
    assert decision.should_enter is False
    assert "outside entry window" in decision.reason


# ═════════════════════════════════════════════════════════════════
# Underlying price gate
# ═════════════════════════════════════════════════════════════════


def test_evaluate_entry_no_bars_fetcher_rejects_on_price():
    p = _preset()  # no bars_fetcher
    decision = p.evaluate_entry("SPY", _setup(), _market(), _state())
    assert decision.should_enter is False
    assert decision.reason == "underlying price unavailable"


def test_evaluate_entry_bars_fetcher_returns_empty_rejects():
    def fetcher(symbol, tf, count):
        return pd.DataFrame()
    p = _preset(bars_fetcher=fetcher)
    decision = p.evaluate_entry("SPY", _setup(), _market(), _state())
    assert decision.should_enter is False
    assert "underlying price unavailable" in decision.reason


def test_evaluate_entry_bars_fetcher_raises_rejects():
    def fetcher(symbol, tf, count):
        raise RuntimeError("alpaca down")
    p = _preset(bars_fetcher=fetcher)
    decision = p.evaluate_entry("SPY", _setup(), _market(), _state())
    assert decision.should_enter is False
    assert "underlying price unavailable" in decision.reason


def test_evaluate_entry_zero_price_rejects():
    def fetcher(symbol, tf, count):
        return pd.DataFrame({"close": [0.0]})
    p = _preset(bars_fetcher=fetcher)
    decision = p.evaluate_entry("SPY", _setup(), _market(), _state())
    assert decision.should_enter is False
    assert "underlying price unavailable" in decision.reason


# ═════════════════════════════════════════════════════════════════
# Direction detection
# ═════════════════════════════════════════════════════════════════


def test_neutral_direction_rejected():
    bars = _full_bullish_setup_bars()
    p = _preset(bars_fetcher=bars)
    decision = p.evaluate_entry(
        "SPY", _setup(direction="neutral"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "non-directional setup" in decision.reason


def test_unknown_direction_rejected():
    bars = _full_bullish_setup_bars()
    p = _preset(bars_fetcher=bars)
    decision = p.evaluate_entry(
        "SPY", _setup(direction="sideways"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "non-directional setup" in decision.reason


def test_detect_direction_helper_passthrough():
    p = _preset()
    assert p._detect_direction(_setup(direction="bullish")) == "bullish"
    assert p._detect_direction(_setup(direction="bearish")) == "bearish"
    assert p._detect_direction(_setup(direction="neutral")) is None


# ═════════════════════════════════════════════════════════════════
# Cooldowns
# ═════════════════════════════════════════════════════════════════


def test_cooldown_max_2_entries_today_blocks_third():
    """Two distinct entries already today; third on a NEW key still hits
    cap because the per-day cap is across all keys."""
    today = _now_at(time(10, 30))
    recent = {
        "SPY:bullish": today - timedelta(minutes=120),
        "QQQ:bearish": today - timedelta(minutes=90),
    }
    bars = _full_bullish_setup_bars()
    p = _preset(bars_fetcher=bars, now_fetcher=lambda: today)
    decision = p.evaluate_entry(
        "AAPL", _setup(direction="bullish"), _market(), _state(recent),
    )
    assert decision.should_enter is False
    assert "max entries today" in decision.reason


def test_cooldown_one_entry_today_allows_second():
    """One entry today; cooldowns clear for a different (sym, dir) key."""
    today = _now_at(time(10, 30))
    recent = {
        "SPY:bullish": today - timedelta(minutes=120),
    }
    state = _state(recent)
    bars = _full_bullish_setup_bars()
    macro = lambda sym, mins: [_macro_event(impact_level="HIGH",
                                            event_type="CPI")]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "QQQ", _setup(direction="bullish"), _market(), state,
    )
    assert decision.should_enter is True


def test_cooldown_yesterday_entries_dont_count():
    """Entries from yesterday are excluded from today's cap."""
    today = _now_at(time(10, 30))
    yesterday_et = _now_at(time(10, 30)) - timedelta(days=1)
    recent = {
        "SPY:bullish": yesterday_et,
        "QQQ:bearish": yesterday_et - timedelta(hours=1),
    }
    bars = _full_bullish_setup_bars()
    macro = lambda sym, mins: [_macro_event(impact_level="HIGH",
                                            event_type="FOMC")]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(),
        _state(recent),
    )
    assert decision.should_enter is True


def test_cooldown_same_direction_60min_blocks():
    today = _now_at(time(10, 30))
    recent = {
        "SPY:bullish": today - timedelta(minutes=30),
    }
    bars = _full_bullish_setup_bars()
    p = _preset(bars_fetcher=bars, now_fetcher=lambda: today)
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(recent),
    )
    assert decision.should_enter is False
    assert "same-direction cooldown" in decision.reason


def test_cooldown_same_direction_just_past_60min_allows():
    today = _now_at(time(11, 30))
    recent = {
        "SPY:bullish": today - timedelta(minutes=61),
    }
    bars = _full_bullish_setup_bars()
    macro = lambda sym, mins: [_macro_event(impact_level="HIGH",
                                            event_type="FOMC")]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(recent),
    )
    assert decision.should_enter is True


def test_cooldown_opposite_direction_not_blocked():
    """Same-direction cooldown is keyed on (symbol, direction). Opposite
    direction on the same symbol is not blocked by the 60-min rule."""
    today = _now_at(time(10, 30))
    recent = {
        "SPY:bullish": today - timedelta(minutes=10),
    }
    state = _state(recent)
    bars = _full_bearish_setup_bars(price=390.0)
    macro = lambda sym, mins: [_macro_event(impact_level="HIGH",
                                            event_type="CPI")]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bearish"), _market(), state,
    )
    assert decision.should_enter is True


def test_cooldown_no_recent_entries_passes():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    macro = lambda sym, mins: [_macro_event(impact_level="HIGH",
                                            event_type="FOMC")]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is True


# ═════════════════════════════════════════════════════════════════
# Catalyst gate
# ═════════════════════════════════════════════════════════════════


def test_catalyst_no_paths_active_rejects():
    """Bars/cooldowns clear; no catalyst → reject with 'no catalyst'."""
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    p = _preset(bars_fetcher=bars, now_fetcher=lambda: today)
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "no catalyst" in decision.reason


def test_catalyst_high_event_within_4h_passes():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    macro = lambda sym, mins: [_macro_event(impact_level="HIGH",
                                            event_type="FOMC",
                                            minutes_until=120)]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is True
    assert "FOMC" in decision.reason


def test_catalyst_medium_event_alone_does_not_pass():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    macro = lambda sym, mins: [_macro_event(impact_level="MEDIUM",
                                            event_type="GDP")]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "no catalyst" in decision.reason


def test_catalyst_no_macro_fetcher_no_path_a():
    """Without macro_fetcher, the scheduled-event path can't fire."""
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    p = _preset(bars_fetcher=bars, now_fetcher=lambda: today)
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "no catalyst" in decision.reason


def test_catalyst_macro_fetcher_raises_safe():
    """Macro fetcher exception is caught — falls through to other paths."""
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    def macro(sym, mins):
        raise RuntimeError("DB down")
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "no catalyst" in decision.reason


def test_catalyst_mag7_post_earnings_passes():
    """TSLA, 30 min after open, with HIGH-impact EARNINGS event in
    last 24h → Mag-7 catalyst fires."""
    today = _now_at(time(10, 0))   # 30 min after 9:30 open
    bars = _full_bullish_setup_bars()

    def macro(sym, mins):
        # Path (a): scheduled lookahead 240 min — return MEDIUM only so
        # path (a) does not fire; path (b)'s 24h lookback returns HIGH
        # earnings so it fires.
        if mins == 240:
            return [_macro_event(impact_level="MEDIUM",
                                 event_type="OTHER")]
        return [_macro_event(impact_level="HIGH",
                             event_type="EARNINGS",
                             minutes_until=-720)]

    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "TSLA", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is True
    assert "Mag-7" in decision.reason


def test_catalyst_mag7_post_earnings_too_late_rejects():
    """TSLA 90 min after open — past the 60-min post-earnings window."""
    today = _now_at(time(11, 0))  # 90 min after open
    bars = _full_bullish_setup_bars()
    def macro(sym, mins):
        if mins == 240:
            return [_macro_event(impact_level="MEDIUM", event_type="OTHER")]
        return [_macro_event(impact_level="HIGH",
                             event_type="EARNINGS",
                             minutes_until=-720)]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "TSLA", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "no catalyst" in decision.reason


def test_catalyst_mag7_path_skipped_for_non_mag7():
    """SPY is not Mag-7 — the post-earnings path is never consulted."""
    today = _now_at(time(10, 0))
    bars = _full_bullish_setup_bars()

    seen = []
    def macro(sym, mins):
        seen.append((sym, mins))
        if mins == 240:
            return [_macro_event(impact_level="MEDIUM", event_type="OTHER")]
        return [_macro_event(impact_level="HIGH", event_type="EARNINGS")]

    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    # Only path-(a) should have been called (240 lookahead). The
    # 24-hour lookback for Mag-7 should never fire for SPY.
    assert all(mins == 240 for sym, mins in seen)


def test_catalyst_vix_spike_passes():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    p = _preset(
        bars_fetcher=bars,
        vix_spike_fetcher=lambda: 18.5,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is True
    assert "VIX +18.5" in decision.reason


def test_catalyst_vix_spike_at_threshold_passes():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    p = _preset(
        bars_fetcher=bars,
        vix_spike_fetcher=lambda: 15.0,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is True


def test_catalyst_vix_spike_below_threshold_rejects():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    p = _preset(
        bars_fetcher=bars,
        vix_spike_fetcher=lambda: 14.9,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "no catalyst" in decision.reason


def test_catalyst_vix_spike_none_treated_as_no_spike():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    p = _preset(
        bars_fetcher=bars,
        vix_spike_fetcher=lambda: None,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False


def test_catalyst_vix_spike_negative_does_not_fire():
    """A VIX drop is not a spike."""
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    p = _preset(
        bars_fetcher=bars,
        vix_spike_fetcher=lambda: -25.0,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False


def test_catalyst_vix_spike_fetcher_raises_safe():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    def vix():
        raise RuntimeError("yfinance down")
    p = _preset(
        bars_fetcher=bars,
        vix_spike_fetcher=vix,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "no catalyst" in decision.reason


# ═════════════════════════════════════════════════════════════════
# Technical confirmation — gate (1) prior-day range
# ═════════════════════════════════════════════════════════════════


def test_tech_prior_day_high_not_broken_calls():
    """Bullish: price below prior_day_high → reject."""
    today = _now_at(time(10, 30))
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=410.0, prior_low=395.0),  # high above price
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=_make_1min_directional("bullish", last_close=405.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "prior-day high not broken" in decision.reason


def test_tech_prior_day_low_not_broken_puts():
    today = _now_at(time(10, 30))
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=380.0),  # low below price
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=_make_1min_directional("bearish", last_close=390.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bearish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "prior-day low not broken" in decision.reason


def test_tech_prior_day_unavailable():
    today = _now_at(time(10, 30))
    # daily=None → returns None from fetcher
    bars = _bars_fetcher_for(
        daily=None,
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=_make_1min_directional("bullish", last_close=405.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "prior-day range unavailable" in decision.reason


def test_tech_prior_day_only_one_bar_unavailable():
    today = _now_at(time(10, 30))
    daily = pd.DataFrame({
        "open": [398.0], "high": [400.0], "low": [395.0],
        "close": [399.0], "volume": [10_000_000],
    })
    bars = _bars_fetcher_for(
        daily=daily,
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=_make_1min_directional("bullish", last_close=405.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "prior-day range unavailable" in decision.reason


# ═════════════════════════════════════════════════════════════════
# Technical confirmation — gate (2) 5-min EMA
# ═════════════════════════════════════════════════════════════════


def test_tech_ema_below_price_calls_passes():
    """Bullish: EMA(20)=400 < price=405 → passes EMA gate."""
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars(price=405.0)
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is True


def test_tech_ema_above_price_calls_rejects():
    today = _now_at(time(10, 30))
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([410.0] * 30),  # EMA > price=405
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=_make_1min_directional("bullish", last_close=405.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "below 5m EMA" in decision.reason


def test_tech_ema_above_price_puts_passes():
    today = _now_at(time(10, 30))
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 30),  # EMA=400 > price=390
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=_make_1min_directional("bearish", last_close=390.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bearish"), _market(), _state(),
    )
    assert decision.should_enter is True


def test_tech_ema_below_price_puts_rejects():
    today = _now_at(time(10, 30))
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([380.0] * 30),  # EMA < price=390
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=_make_1min_directional("bearish", last_close=390.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bearish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "above 5m EMA" in decision.reason


def test_tech_ema_unavailable_short_bars():
    """Fewer than 20 5-min bars → EMA returns None → reject."""
    today = _now_at(time(10, 30))
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 5),
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=_make_1min_directional("bullish", last_close=405.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "EMA unavailable" in decision.reason


# ═════════════════════════════════════════════════════════════════
# Technical confirmation — gate (3) VWAP
# ═════════════════════════════════════════════════════════════════


def test_tech_vwap_below_price_calls_passes():
    """Already covered by full bullish; explicit assertion: VWAP=400 <
    price=405 → passes."""
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars(price=405.0)
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is True


def test_tech_vwap_above_price_calls_rejects():
    today = _now_at(time(10, 30))
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=420.0, n=60),  # VWAP > price=405
        one_min=_make_1min_directional("bullish", last_close=405.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "below session VWAP" in decision.reason


def test_tech_vwap_above_price_puts_passes():
    today = _now_at(time(10, 30))
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=400.0, n=60),  # VWAP=400 > price=390
        one_min=_make_1min_directional("bearish", last_close=390.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bearish"), _market(), _state(),
    )
    assert decision.should_enter is True


def test_tech_vwap_below_price_puts_rejects():
    today = _now_at(time(10, 30))
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=380.0, n=60),  # VWAP < price=390
        one_min=_make_1min_directional("bearish", last_close=390.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bearish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "above session VWAP" in decision.reason


def test_tech_vwap_zero_volume_unavailable():
    today = _now_at(time(10, 30))
    zero_vol = pd.DataFrame({
        "open":   [400.0] * 60,
        "high":   [400.0] * 60,
        "low":    [400.0] * 60,
        "close":  [400.0] * 60,
        "volume": [0] * 60,
    })
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 30),
        vwap=zero_vol,
        one_min=_make_1min_directional("bullish", last_close=405.0, n=5),
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "VWAP unavailable" in decision.reason


# ═════════════════════════════════════════════════════════════════
# Technical confirmation — gate (4) directional bars
# ═════════════════════════════════════════════════════════════════


def test_tech_3_bars_all_up_calls_passes():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars()
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is True


def test_tech_3_bars_mixed_calls_rejects():
    today = _now_at(time(10, 30))
    mixed = pd.DataFrame({
        "open":   [404.0, 405.0, 406.0, 407.0, 408.0],
        "high":   [404.5, 405.5, 406.5, 407.5, 408.5],
        "low":    [403.5, 404.5, 404.5, 406.5, 407.5],
        "close":  [403.8, 404.8, 405.0, 407.5, 405.0],  # last bar = down
        "volume": [1_000_000] * 5,
    })
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=mixed,
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "1-min bars not all up" in decision.reason


def test_tech_3_bars_all_down_puts_passes():
    today = _now_at(time(10, 30))
    bars = _full_bearish_setup_bars(price=390.0)
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bearish"), _market(), _state(),
    )
    assert decision.should_enter is True


def test_tech_3_bars_mixed_puts_rejects():
    today = _now_at(time(10, 30))
    mixed = pd.DataFrame({
        "open":   [392.0, 391.0, 390.0, 389.0, 388.0],
        "high":   [392.5, 391.5, 390.5, 389.5, 388.5],
        "low":    [391.5, 390.5, 389.5, 388.5, 387.5],
        "close":  [391.0, 390.5, 391.5, 388.5, 387.7],  # one up bar in last 3
        "volume": [1_000_000] * 5,
    })
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=mixed,
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bearish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "1-min bars not all down" in decision.reason


def test_tech_directional_bars_too_few_unavailable():
    """Fewer than 3 1-min bars → directional gate marks unavailable.

    The fetcher must return the short DF only for count<=5 (the
    directional path) — the underlying-price fetch (count=1) needs at
    least one row to populate `price`."""
    today = _now_at(time(10, 30))
    short_dir = pd.DataFrame({
        "open":   [404.0, 405.0],
        "high":   [404.5, 405.5],
        "low":    [403.5, 404.5],
        "close":  [403.8, 405.2],
        "volume": [1_000_000, 1_000_000],
    })
    bars = _bars_fetcher_for(
        daily=_make_daily(prior_high=400.0, prior_low=395.0),
        ema=_make_ema_bars([400.0] * 30),
        vwap=_make_vwap_bars(price=400.0, n=60),
        one_min=short_dir,
    )
    macro = lambda sym, mins: [_macro_event()]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert "directional bars unavailable" in decision.reason


# ═════════════════════════════════════════════════════════════════
# Full success / multi-gate integration
# ═════════════════════════════════════════════════════════════════


def test_full_success_path_bullish_with_high_event():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars(price=405.0)
    macro = lambda sym, mins: [_macro_event(impact_level="HIGH",
                                            event_type="CPI")]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is True
    assert decision.direction == "bullish"
    assert "0dte_asymmetric entry" in decision.reason
    assert "405" in decision.reason


def test_full_success_path_bearish_with_vix_spike():
    today = _now_at(time(11, 0))
    bars = _full_bearish_setup_bars(price=390.0)
    p = _preset(
        bars_fetcher=bars,
        vix_spike_fetcher=lambda: 20.0,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bearish"), _market(), _state(),
    )
    assert decision.should_enter is True
    assert decision.direction == "bearish"
    assert "VIX +20.0" in decision.reason


def test_full_success_path_qqq():
    today = _now_at(time(10, 30))
    bars = _full_bullish_setup_bars(price=405.0)
    macro = lambda sym, mins: [_macro_event(impact_level="HIGH",
                                            event_type="FOMC")]
    p = _preset(
        bars_fetcher=bars,
        macro_fetcher=macro,
        now_fetcher=lambda: today,
    )
    decision = p.evaluate_entry(
        "QQQ", _setup(direction="bullish"), _market(), _state(),
    )
    assert decision.should_enter is True


def test_decision_direction_passed_through_on_reject():
    """Even on rejection, the direction field reflects the scanner's
    setup direction (matches SwingPreset behavior)."""
    p = _preset(now_fetcher=_now_fetcher(time(8, 0)))
    decision = p.evaluate_entry(
        "SPY", _setup(direction="bearish"), _market(), _state(),
    )
    assert decision.should_enter is False
    assert decision.direction == "bearish"


# ═════════════════════════════════════════════════════════════════
# Stubbed methods
# ═════════════════════════════════════════════════════════════════


def test_evaluate_exit_raises_not_implemented():
    p = _preset()
    with pytest.raises(NotImplementedError, match="Phase 2"):
        p.evaluate_exit(
            position=None,  # type: ignore[arg-type]
            current_quote=0.0,
            market=_market(),
            setups=[],
            state=_state(),
        )


# ═════════════════════════════════════════════════════════════════
# select_contract (C4c)
# ═════════════════════════════════════════════════════════════════

# (`test_select_contract_raises_not_implemented` was deleted in C4c —
# it was a stub-guard for the C4b NotImplementedError, no longer
# applicable now that the method is fully implemented. The same pattern
# was followed in commits 0954124 and 60bd8ac for SwingPreset.)


from datetime import date as _date  # noqa: E402

from profiles.base_preset import (  # noqa: E402
    ContractSelection,
    OptionChain,
    OptionContract,
)


_TODAY_ET = _date(2026, 4, 28)
_TOMORROW_ET = _date(2026, 4, 29)
_TEN_AM_UTC = _now_at(time(10, 0))


def _oc(
    strike: float = 402.0,
    right: str = "call",
    delta: float = 0.275,
    bid: float = 1.00,
    ask: float = 1.04,
    mid: float | None = None,
    oi: int = 1500,
    volume: int = 750,
    expiration: _date = _TODAY_ET,
    symbol: str = "SPY",
    iv: float = 0.30,
) -> OptionContract:
    if mid is None:
        mid = (bid + ask) / 2
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
        volume=volume,
    )


def _chain(
    underlying_price: float = 400.0,
    contracts: list | None = None,
    snapshot_time: datetime = _TEN_AM_UTC,
    symbol: str = "SPY",
) -> OptionChain:
    return OptionChain(
        symbol=symbol,
        underlying_price=underlying_price,
        contracts=list(contracts or []),
        snapshot_time=snapshot_time,
    )


def _select_preset() -> ZeroDteAsymmetricPreset:
    """Preset with now_fetcher pinned to 2026-04-28 10:00 ET so today's
    date is deterministic in select_contract."""
    return ZeroDteAsymmetricPreset(
        config=_config(),
        now_fetcher=lambda: _TEN_AM_UTC,
    )


# ─────────────────────────────────────────────────────────────────
# Construction validity
# ─────────────────────────────────────────────────────────────────


def test_select_happy_path_returns_contract_selection():
    p = _select_preset()
    chain = _chain(contracts=[_oc()])
    sel = p.select_contract("SPY", "bullish", chain)
    assert isinstance(sel, ContractSelection)
    assert sel.symbol == "SPY"
    assert sel.right == "call"
    assert sel.strike == 402.0
    assert sel.expiration == _TODAY_ET
    assert sel.target_delta == 0.275
    assert sel.estimated_premium == pytest.approx(1.02)
    assert sel.dte == 0


def test_select_raises_valueerror_on_neutral_direction():
    p = _select_preset()
    chain = _chain(contracts=[_oc()])
    with pytest.raises(ValueError, match="bullish.*bearish"):
        p.select_contract("SPY", "neutral", chain)


def test_select_raises_valueerror_on_long_direction():
    p = _select_preset()
    chain = _chain(contracts=[_oc()])
    with pytest.raises(ValueError, match="bullish.*bearish"):
        p.select_contract("SPY", "long", chain)


def test_select_raises_valueerror_on_empty_direction():
    p = _select_preset()
    chain = _chain(contracts=[_oc()])
    with pytest.raises(ValueError, match="bullish.*bearish"):
        p.select_contract("SPY", "", chain)


def test_select_returns_none_on_zero_underlying_price():
    p = _select_preset()
    chain = _chain(underlying_price=0.0, contracts=[_oc()])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_returns_none_on_negative_underlying_price():
    p = _select_preset()
    chain = _chain(underlying_price=-50.0, contracts=[_oc()])
    assert p.select_contract("SPY", "bullish", chain) is None


# ─────────────────────────────────────────────────────────────────
# Today's-expiration gate
# ─────────────────────────────────────────────────────────────────


def test_select_only_future_expirations_returns_none():
    p = _select_preset()
    chain = _chain(contracts=[_oc(expiration=_TOMORROW_ET)])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_picks_today_when_mixed_with_tomorrow():
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=402.0, expiration=_TOMORROW_ET, delta=0.275),
        _oc(strike=403.0, expiration=_TODAY_ET, delta=0.275),
    ])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None
    assert sel.strike == 403.0
    assert sel.expiration == _TODAY_ET


def test_select_only_today_expirations_uses_them():
    p = _select_preset()
    chain = _chain(contracts=[_oc(strike=403.0, expiration=_TODAY_ET)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None
    assert sel.strike == 403.0


# ─────────────────────────────────────────────────────────────────
# Right matching
# ─────────────────────────────────────────────────────────────────


def test_select_bullish_picks_call_filters_out_put():
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=402.0, right="call", delta=0.275),
        _oc(strike=398.0, right="put", delta=-0.275),
    ])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None
    assert sel.right == "call"
    assert sel.strike == 402.0


def test_select_bearish_picks_put_filters_out_call():
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=402.0, right="call", delta=0.275),
        _oc(strike=398.0, right="put", delta=-0.275),
    ])
    sel = p.select_contract("SPY", "bearish", chain)
    assert sel is not None
    assert sel.right == "put"
    assert sel.strike == 398.0


def test_select_bullish_no_calls_returns_none():
    p = _select_preset()
    chain = _chain(contracts=[_oc(strike=398.0, right="put", delta=-0.275)])
    assert p.select_contract("SPY", "bullish", chain) is None


# ─────────────────────────────────────────────────────────────────
# OTM strike band — calls
# ─────────────────────────────────────────────────────────────────


def test_select_call_strike_at_lower_boundary_kept():
    """Underlying=400, strike=402.0 = 0.5% OTM = lower boundary → kept."""
    p = _select_preset()
    chain = _chain(contracts=[_oc(strike=402.0)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None
    assert sel.strike == 402.0


def test_select_call_strike_atm_below_band_rejected():
    p = _select_preset()
    chain = _chain(contracts=[_oc(strike=400.0)])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_call_strike_midband_kept():
    """Strike=405.0 is 1.25% OTM, mid of [402, 406] → kept."""
    p = _select_preset()
    chain = _chain(contracts=[_oc(strike=405.0)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None
    assert sel.strike == 405.0


def test_select_call_strike_at_upper_boundary_kept():
    """Strike=406.0 = 1.5% OTM = upper boundary → kept."""
    p = _select_preset()
    chain = _chain(contracts=[_oc(strike=406.0)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None
    assert sel.strike == 406.0


def test_select_call_strike_above_band_rejected():
    """Strike=410.0 = 2.5% OTM > 1.5% upper bound → rejected."""
    p = _select_preset()
    chain = _chain(contracts=[_oc(strike=410.0)])
    assert p.select_contract("SPY", "bullish", chain) is None


# ─────────────────────────────────────────────────────────────────
# OTM strike band — puts
# ─────────────────────────────────────────────────────────────────


def test_select_put_strike_at_upper_boundary_kept():
    """Underlying=400, strike=398.0 = 0.5% OTM (puts) = upper boundary → kept."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=398.0, right="put", delta=-0.275),
    ])
    sel = p.select_contract("SPY", "bearish", chain)
    assert sel is not None
    assert sel.strike == 398.0


def test_select_put_strike_atm_above_band_rejected():
    """Strike=400.0 is ATM — for puts the band is [394, 398], so ATM is
    above the band → rejected."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=400.0, right="put", delta=-0.275),
    ])
    assert p.select_contract("SPY", "bearish", chain) is None


def test_select_put_strike_midband_kept():
    """Strike=395.0 is 1.25% OTM (puts) → kept."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=395.0, right="put", delta=-0.275),
    ])
    sel = p.select_contract("SPY", "bearish", chain)
    assert sel is not None
    assert sel.strike == 395.0


def test_select_put_strike_at_lower_boundary_kept():
    """Strike=394.0 = 1.5% OTM (puts) = lower boundary → kept."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=394.0, right="put", delta=-0.275),
    ])
    sel = p.select_contract("SPY", "bearish", chain)
    assert sel is not None
    assert sel.strike == 394.0


def test_select_put_strike_below_band_rejected():
    """Strike=390.0 = 2.5% OTM (puts) below the band → rejected."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=390.0, right="put", delta=-0.275),
    ])
    assert p.select_contract("SPY", "bearish", chain) is None


# ─────────────────────────────────────────────────────────────────
# Delta band
# ─────────────────────────────────────────────────────────────────


def test_select_call_delta_at_min_boundary_kept():
    p = _select_preset()
    chain = _chain(contracts=[_oc(delta=0.20)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None


def test_select_call_delta_at_max_boundary_kept():
    p = _select_preset()
    chain = _chain(contracts=[_oc(delta=0.35)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None


def test_select_call_delta_at_midpoint_kept():
    p = _select_preset()
    chain = _chain(contracts=[_oc(delta=0.275)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None


def test_select_call_delta_below_band_rejected():
    p = _select_preset()
    chain = _chain(contracts=[_oc(delta=0.15)])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_call_delta_above_band_rejected():
    p = _select_preset()
    chain = _chain(contracts=[_oc(delta=0.40)])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_put_delta_negative_midpoint_kept():
    """abs(-0.275) = 0.275 ∈ [0.20, 0.35] → kept."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=395.0, right="put", delta=-0.275),
    ])
    sel = p.select_contract("SPY", "bearish", chain)
    assert sel is not None


def test_select_put_delta_negative_min_kept():
    """abs(-0.20) = 0.20 = boundary → kept."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=395.0, right="put", delta=-0.20),
    ])
    sel = p.select_contract("SPY", "bearish", chain)
    assert sel is not None


def test_select_delta_none_rejected():
    """Delta=None is malformed data — exclude rather than raise."""
    p = _select_preset()
    chain = _chain(contracts=[_oc(delta=None)])  # type: ignore[arg-type]
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_delta_nan_rejected():
    p = _select_preset()
    chain = _chain(contracts=[_oc(delta=float("nan"))])
    assert p.select_contract("SPY", "bullish", chain) is None


# ─────────────────────────────────────────────────────────────────
# Liquidity gates
# ─────────────────────────────────────────────────────────────────


def test_select_spread_at_7pct_kept():
    """spread = 7% of mid → kept (under 8% ceiling)."""
    p = _select_preset()
    # bid=1.00, ask=1.075, mid=1.0375, spread/mid = 0.075/1.0375 ≈ 7.23%
    chain = _chain(contracts=[_oc(bid=1.00, ask=1.075)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None


def test_select_spread_at_8pct_boundary_kept():
    """spread/mid = 0.08 exactly → kept (≤ ceiling)."""
    p = _select_preset()
    # bid=0.96, ask=1.04 → mid=1.00, spread/mid=0.08 exactly
    chain = _chain(contracts=[_oc(bid=0.96, ask=1.04, mid=1.00)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None


def test_select_spread_above_8pct_rejected():
    """spread/mid > 0.08 → rejected."""
    p = _select_preset()
    # bid=0.95, ask=1.05 → mid=1.00, spread/mid=0.10
    chain = _chain(contracts=[_oc(bid=0.95, ask=1.05, mid=1.00)])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_zero_mid_rejected():
    p = _select_preset()
    chain = _chain(contracts=[_oc(bid=0.0, ask=0.0, mid=0.0)])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_negative_mid_rejected():
    p = _select_preset()
    chain = _chain(contracts=[_oc(bid=-0.5, ask=0.5, mid=-0.1)])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_crossed_market_bid_above_ask_rejected():
    """JUDGMENT CALL: bid > ask is a crossed/malformed market. The C4c
    prompt left this 'up to implementer'; this implementation rejects
    it explicitly per the project's fail-safe rule (malformed data is
    excluded, not raised)."""
    p = _select_preset()
    chain = _chain(contracts=[_oc(bid=1.10, ask=1.00, mid=1.05)])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_oi_below_threshold_rejected():
    p = _select_preset()
    chain = _chain(contracts=[_oc(oi=999)])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_oi_at_threshold_kept():
    p = _select_preset()
    chain = _chain(contracts=[_oc(oi=1000)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None


def test_select_volume_below_threshold_rejected():
    p = _select_preset()
    chain = _chain(contracts=[_oc(volume=499)])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_volume_at_threshold_kept():
    p = _select_preset()
    chain = _chain(contracts=[_oc(volume=500)])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None


# ─────────────────────────────────────────────────────────────────
# Tie-breakers
# ─────────────────────────────────────────────────────────────────


def test_select_tiebreak_closer_to_midpoint_wins():
    """Two contracts pass: deltas 0.22 and 0.30. |0.30-0.275|=0.025 vs
    |0.22-0.275|=0.055 → 0.30 wins."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=403.0, delta=0.22),
        _oc(strike=405.0, delta=0.30),
    ])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None
    assert sel.strike == 405.0


def test_select_tiebreak_tied_delta_distance_tighter_spread_wins():
    """Both contracts at delta=0.275 → delta_dist = 0 for both (genuine
    tie). Tighter spread wins.

    Note: the original draft used deltas 0.25 and 0.30 (equidistant from
    0.275 in nominal arithmetic). In IEEE float, |0.30-0.275|=0.024999...
    and |0.25-0.275|=0.025000..., so 0.30 wins on the first sort key
    alone — never reaching spread. Fixed by setting both deltas equal so
    the tie genuinely engages on spread."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=403.0, delta=0.275, bid=0.97, ask=1.03, mid=1.00),  # 6% spread
        _oc(strike=405.0, delta=0.275, bid=0.99, ask=1.01, mid=1.00),  # 2% spread
    ])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None
    assert sel.strike == 405.0


def test_select_tiebreak_tied_delta_and_spread_higher_oi_wins():
    """Same delta, same spread → higher OI wins."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=403.0, delta=0.275, bid=0.99, ask=1.01, mid=1.00, oi=1500),
        _oc(strike=405.0, delta=0.275, bid=0.99, ask=1.01, mid=1.00, oi=3000),
    ])
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None
    assert sel.strike == 405.0


def test_select_tiebreak_input_order_doesnt_change_winner():
    """Reverse contract order; same winner."""
    p = _select_preset()
    a = _oc(strike=403.0, delta=0.22)
    b = _oc(strike=405.0, delta=0.30)  # closer to midpoint
    chain1 = _chain(contracts=[a, b])
    chain2 = _chain(contracts=[b, a])
    s1 = p.select_contract("SPY", "bullish", chain1)
    s2 = p.select_contract("SPY", "bullish", chain2)
    assert s1 is not None and s2 is not None
    assert s1.strike == s2.strike == 405.0


def test_select_tiebreak_uses_abs_delta_for_puts():
    """Puts with delta -0.22 vs -0.30 → -0.30 wins (closer to |0.275|)."""
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=395.0, right="put", delta=-0.30),
        _oc(strike=397.0, right="put", delta=-0.22),
    ])
    sel = p.select_contract("SPY", "bearish", chain)
    assert sel is not None
    # |abs(-0.30) - 0.275| = 0.025 < |abs(-0.22) - 0.275| = 0.055
    assert sel.strike == 395.0


# ─────────────────────────────────────────────────────────────────
# No-contracts paths
# ─────────────────────────────────────────────────────────────────


def test_select_all_filtered_by_today_expiration_returns_none():
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=402.0, expiration=_TOMORROW_ET),
        _oc(strike=403.0, expiration=_TOMORROW_ET),
    ])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_all_filtered_by_otm_band_returns_none():
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=400.0),  # ATM, below call band
        _oc(strike=410.0),  # 2.5% OTM, above band
    ])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_all_filtered_by_delta_returns_none():
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=403.0, delta=0.10),
        _oc(strike=405.0, delta=0.50),
    ])
    assert p.select_contract("SPY", "bullish", chain) is None


def test_select_all_filtered_by_liquidity_returns_none():
    p = _select_preset()
    chain = _chain(contracts=[
        _oc(strike=403.0, oi=500),         # OI too low
        _oc(strike=405.0, volume=100),     # volume too low
    ])
    assert p.select_contract("SPY", "bullish", chain) is None


# ─────────────────────────────────────────────────────────────────
# Integration with full chain
# ─────────────────────────────────────────────────────────────────


def test_select_realistic_chain_picks_expected_winner():
    """50-contract chain mixing rights, expirations, strikes, deltas,
    liquidity. Exactly one contract should clear every gate AND be the
    closest to delta 0.275."""
    p = _select_preset()
    contracts: list[OptionContract] = []

    # Today calls — full strike grid
    for i, strike in enumerate([400.0, 401.0, 402.0, 403.0, 404.0,
                                405.0, 406.0, 407.0, 408.0, 410.0]):
        contracts.append(_oc(
            strike=strike, right="call",
            # Deltas decrease as strikes go further OTM; only some land
            # in [0.20, 0.35]:
            #   400 → 0.50 (ATM)
            #   401 → 0.45
            #   402 → 0.40 (above band, but in OTM band)
            #   403 → 0.32 (in delta band, in OTM band)
            #   404 → 0.27 (in delta band, in OTM band)  ← winner
            #   405 → 0.25 (in delta band, in OTM band)
            #   406 → 0.20 (in delta band, at boundary, in OTM band)
            #   407 → 0.18 (below delta band, OTM band already exceeded)
            #   408, 410 → far OTM
            delta={
                400.0: 0.50, 401.0: 0.45, 402.0: 0.40, 403.0: 0.32,
                404.0: 0.27, 405.0: 0.25, 406.0: 0.20, 407.0: 0.18,
                408.0: 0.15, 410.0: 0.10,
            }[strike],
        ))

    # Today puts — symmetric to calls
    for strike in [400.0, 399.0, 398.0, 397.0, 396.0, 395.0, 394.0,
                   393.0, 392.0, 390.0]:
        contracts.append(_oc(
            strike=strike, right="put",
            delta={
                400.0: -0.50, 399.0: -0.40, 398.0: -0.35, 397.0: -0.32,
                396.0: -0.30, 395.0: -0.27, 394.0: -0.20, 393.0: -0.18,
                392.0: -0.15, 390.0: -0.10,
            }[strike],
        ))

    # Tomorrow's expiration — should be filtered out
    for strike in [403.0, 404.0, 405.0]:
        contracts.append(_oc(
            strike=strike, right="call", delta=0.275,
            expiration=_TOMORROW_ET,
        ))

    # Today calls with bad liquidity — should be filtered
    contracts.append(_oc(strike=404.5, right="call", delta=0.27, oi=100))
    contracts.append(_oc(strike=404.7, right="call", delta=0.27, volume=50))

    chain = _chain(contracts=contracts)
    sel = p.select_contract("SPY", "bullish", chain)
    assert sel is not None
    # Strike 404 has delta 0.27 → |0.27 - 0.275| = 0.005 (closest)
    assert sel.strike == 404.0
    assert sel.right == "call"
    assert sel.expiration == _TODAY_ET


def test_select_empty_chain_returns_none():
    p = _select_preset()
    chain = _chain(contracts=[])
    assert p.select_contract("SPY", "bullish", chain) is None
