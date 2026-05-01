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


def test_select_contract_raises_not_implemented():
    p = _preset()
    with pytest.raises(NotImplementedError, match="C4c"):
        p.select_contract(
            "SPY", "bullish",
            # OptionChain not constructed — method raises before reading.
            chain=None,  # type: ignore[arg-type]
        )


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
