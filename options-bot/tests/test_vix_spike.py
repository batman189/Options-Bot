"""Unit tests for scoring.vix_spike.

yfinance.Ticker is patched at the module level so no real network
calls happen. The module's TTL cache globals are reset before each
test via an autouse fixture.

Run via:
    python -m pytest tests/test_vix_spike.py -v
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import scoring.vix_spike as vs  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset module-level cache state before and after each test."""
    vs._hist_cache = None
    vs._hist_cache_time = 0.0
    yield
    vs._hist_cache = None
    vs._hist_cache_time = 0.0


def _make_hist(close_prices: list[float], anchor: datetime) -> pd.DataFrame:
    """Build a tz-aware 1-min DataFrame ending at `anchor` with the
    given close-price sequence. Earliest-to-latest order; index is
    tz-aware UTC."""
    n = len(close_prices)
    timestamps = [anchor - timedelta(minutes=(n - 1 - i)) for i in range(n)]
    idx = pd.DatetimeIndex(timestamps)
    return pd.DataFrame({"Close": close_prices}, index=idx)


def _patch_yf(monkeypatch, return_value=None, side_effect=None):
    """Patch yfinance.Ticker so .history(...) returns / raises."""
    import yfinance
    ticker_mock = MagicMock()
    if side_effect is not None:
        ticker_mock.history.side_effect = side_effect
    else:
        ticker_mock.history.return_value = return_value
    factory = MagicMock(return_value=ticker_mock)
    monkeypatch.setattr(yfinance, "Ticker", factory)
    return factory, ticker_mock


# ─────────────────────────────────────────────────────────────────
# _fetch_vix_1min
# ─────────────────────────────────────────────────────────────────


def test_fetch_returns_dataframe_and_caches(monkeypatch):
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    hist = _make_hist([20.0, 20.5, 21.0], anchor)
    factory, ticker_mock = _patch_yf(monkeypatch, return_value=hist)
    out = vs._fetch_vix_1min()
    assert out is hist
    assert vs._hist_cache is hist
    assert factory.call_count == 1
    assert ticker_mock.history.call_count == 1


def test_fetch_uses_cache_within_ttl(monkeypatch):
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    hist = _make_hist([20.0, 21.0], anchor)
    factory, ticker_mock = _patch_yf(monkeypatch, return_value=hist)
    vs._fetch_vix_1min()
    vs._fetch_vix_1min()
    vs._fetch_vix_1min()
    # yfinance hit only once despite 3 calls
    assert ticker_mock.history.call_count == 1


def test_fetch_refetches_after_ttl_expires(monkeypatch):
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    hist = _make_hist([20.0, 21.0], anchor)
    _, ticker_mock = _patch_yf(monkeypatch, return_value=hist)
    vs._fetch_vix_1min()
    # Force cache to look stale
    vs._hist_cache_time -= vs._CACHE_TTL_SECONDS + 1.0
    vs._fetch_vix_1min()
    assert ticker_mock.history.call_count == 2


def test_fetch_returns_none_when_yf_returns_none(monkeypatch, caplog):
    _patch_yf(monkeypatch, return_value=None)
    caplog.set_level(logging.WARNING, logger="options-bot.scoring.vix_spike")
    assert vs._fetch_vix_1min() is None
    assert vs._hist_cache is None
    assert any("history empty" in r.getMessage() for r in caplog.records)


def test_fetch_returns_none_when_yf_returns_empty(monkeypatch, caplog):
    _patch_yf(monkeypatch, return_value=pd.DataFrame())
    caplog.set_level(logging.WARNING, logger="options-bot.scoring.vix_spike")
    assert vs._fetch_vix_1min() is None
    assert vs._hist_cache is None


def test_fetch_returns_none_when_yf_raises_runtime(monkeypatch, caplog):
    _patch_yf(monkeypatch, side_effect=RuntimeError("yahoo down"))
    caplog.set_level(logging.WARNING, logger="options-bot.scoring.vix_spike")
    assert vs._fetch_vix_1min() is None
    assert vs._hist_cache is None
    assert any("yahoo down" in r.getMessage() for r in caplog.records)


def test_fetch_returns_none_when_yf_raises_value(monkeypatch, caplog):
    _patch_yf(monkeypatch, side_effect=ValueError("bad payload"))
    caplog.set_level(logging.WARNING, logger="options-bot.scoring.vix_spike")
    assert vs._fetch_vix_1min() is None


# ─────────────────────────────────────────────────────────────────
# vix_spike_pct — happy paths
# ─────────────────────────────────────────────────────────────────


def test_spike_15pct_up(monkeypatch):
    """VIX 60 min ago = 20.0, current = 23.0 → 15.0% spike."""
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    closes = [20.0] + [20.0] * 59 + [23.0]  # 61 bars: 60 min ago=20, current=23
    hist = _make_hist(closes, anchor)
    _patch_yf(monkeypatch, return_value=hist)
    out = vs.vix_spike_pct(now=anchor)
    assert out == pytest.approx(15.0)


def test_spike_15pct_down(monkeypatch):
    """30.0 → 25.5 = -15.0%."""
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    closes = [30.0] + [30.0] * 59 + [25.5]
    hist = _make_hist(closes, anchor)
    _patch_yf(monkeypatch, return_value=hist)
    out = vs.vix_spike_pct(now=anchor)
    assert out == pytest.approx(-15.0)


def test_spike_at_exact_threshold_returned_verbatim(monkeypatch):
    """The 15% threshold is the caller's concern; this module just
    returns the measurement."""
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    closes = [20.0] + [20.0] * 59 + [23.0]
    hist = _make_hist(closes, anchor)
    _patch_yf(monkeypatch, return_value=hist)
    out = vs.vix_spike_pct(now=anchor)
    assert out == pytest.approx(15.0)
    # Float exactness: no rounding/clamping to threshold
    assert isinstance(out, float)


def test_spike_flat_returns_zero(monkeypatch):
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    closes = [22.5] * 61
    hist = _make_hist(closes, anchor)
    _patch_yf(monkeypatch, return_value=hist)
    out = vs.vix_spike_pct(now=anchor)
    assert out == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────
# vix_spike_pct — edge cases
# ─────────────────────────────────────────────────────────────────


def test_spike_returns_none_when_hist_empty(monkeypatch):
    _patch_yf(monkeypatch, return_value=pd.DataFrame())
    assert vs.vix_spike_pct() is None


def test_spike_returns_none_with_one_row(monkeypatch, caplog):
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    hist = _make_hist([22.0], anchor)
    _patch_yf(monkeypatch, return_value=hist)
    caplog.set_level(logging.INFO, logger="options-bot.scoring.vix_spike")
    out = vs.vix_spike_pct(now=anchor)
    assert out is None
    assert any("insufficient" in r.getMessage() for r in caplog.records)


def test_spike_returns_none_when_no_bars_60min_old(monkeypatch, caplog):
    """History exists but every bar is < 60 min old → no past anchor."""
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    # 30 1-min bars ending at anchor — none are >=60 min old
    closes = [22.0 + i * 0.01 for i in range(30)]
    hist = _make_hist(closes, anchor)
    _patch_yf(monkeypatch, return_value=hist)
    caplog.set_level(logging.INFO, logger="options-bot.scoring.vix_spike")
    out = vs.vix_spike_pct(now=anchor)
    assert out is None
    assert any("60 min old" in r.getMessage() for r in caplog.records)


def test_spike_returns_none_when_past_close_zero(monkeypatch, caplog):
    """Divide-by-zero guard."""
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    closes = [0.0] + [22.0] * 59 + [23.0]
    hist = _make_hist(closes, anchor)
    _patch_yf(monkeypatch, return_value=hist)
    caplog.set_level(logging.WARNING, logger="options-bot.scoring.vix_spike")
    out = vs.vix_spike_pct(now=anchor)
    assert out is None
    assert any("invalid" in r.getMessage() for r in caplog.records)


def test_spike_returns_none_when_past_close_nan(monkeypatch):
    import numpy as np
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    closes = [np.nan] + [22.0] * 59 + [23.0]
    hist = _make_hist(closes, anchor)
    _patch_yf(monkeypatch, return_value=hist)
    out = vs.vix_spike_pct(now=anchor)
    assert out is None


def test_spike_returns_none_when_latest_close_nan(monkeypatch):
    import numpy as np
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    closes = [22.0] * 60 + [np.nan]
    hist = _make_hist(closes, anchor)
    _patch_yf(monkeypatch, return_value=hist)
    out = vs.vix_spike_pct(now=anchor)
    assert out is None


def test_spike_naive_now_raises(monkeypatch):
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    hist = _make_hist([20.0, 23.0], anchor)
    _patch_yf(monkeypatch, return_value=hist)
    with pytest.raises(ValueError, match="timezone-aware"):
        vs.vix_spike_pct(now=datetime(2026, 5, 6, 14, 0))


# ─────────────────────────────────────────────────────────────────
# vix_spike_pct — testability via `now` arg
# ─────────────────────────────────────────────────────────────────


def test_spike_now_param_filters_history_to_past(monkeypatch):
    """History extends 90 min back. now in middle of that history filters
    to the prefix; the 60-min-back anchor moves with `now`."""
    anchor = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    # 91 bars laid out so index 0 is anchor-90min, index 90 is anchor.
    #   indexes 0..59 (timestamps 16:30..17:29): close = 20.0
    #   indexes 60..89 (timestamps 17:30..17:59): close = 21.0..23.9
    #   index 90 (timestamp 18:00): close = 23.0
    closes = (
        [20.0] * 60
        + [21.0 + i * 0.1 for i in range(30)]
        + [23.0]
    )
    hist = _make_hist(closes, anchor)
    _patch_yf(monkeypatch, return_value=hist)
    # now = anchor: latest bar is 18:00 (close 23.0). target = 17:00.
    # Latest bar at-or-before 17:00 is index 30 (close 20.0). Spike = 15.0.
    out_now = vs.vix_spike_pct(now=anchor)
    assert out_now == pytest.approx(15.0)
    # now = anchor - 30min = 17:30. Latest filtered bar is index 60
    # (timestamp 17:30, close 21.0). target = 16:30. Latest bar at-or-
    # before 16:30 is index 0 (close 20.0). Spike = (21-20)/20*100 = 5.0.
    earlier_now = anchor - timedelta(minutes=30)
    out_earlier = vs.vix_spike_pct(now=earlier_now)
    assert out_earlier == pytest.approx(5.0)


def test_spike_default_now_uses_current_utc(monkeypatch):
    """When `now` is not passed, function defaults to datetime.now(UTC).
    With history that ends in the future relative to real now, the
    filter would return empty. Use a fresh anchor so the test is
    deterministic against real-world clock."""
    real_now = datetime.now(timezone.utc)
    closes = [20.0] + [20.0] * 59 + [23.0]
    hist = _make_hist(closes, real_now)
    _patch_yf(monkeypatch, return_value=hist)
    out = vs.vix_spike_pct()  # default now
    assert out == pytest.approx(15.0)


# ─────────────────────────────────────────────────────────────────
# Cache reset fixture sanity
# ─────────────────────────────────────────────────────────────────


def test_cache_starts_empty():
    """The autouse fixture resets module globals before each test."""
    assert vs._hist_cache is None
    assert vs._hist_cache_time == 0.0
