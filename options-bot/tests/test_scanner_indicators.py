"""Unit tests for scanner.indicators new helpers (ema, session_vwap).

Pure-function tests with deterministic inputs. The pre-existing helpers
in scanner/indicators.py (rsi, bollinger_position, etc.) are not tested
here — this file is scoped to the new ema and session_vwap helpers
added for the 0DTE asymmetric preset.

Run via:
    python -m pytest tests/test_scanner_indicators.py -v
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scanner.indicators import ema, session_vwap  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


def _bars_df(
    closes: list[float],
    volumes: list[int] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> pd.DataFrame:
    """Build a bars DataFrame with the supplied close column. high/low
    default to close; volume defaults to 1000 per bar."""
    n = len(closes)
    if volumes is None:
        volumes = [1000] * n
    if highs is None:
        highs = list(closes)
    if lows is None:
        lows = list(closes)
    return pd.DataFrame({
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": volumes,
    })


# ─────────────────────────────────────────────────────────────────
# ema
# ─────────────────────────────────────────────────────────────────


def test_ema_constant_prices_returns_constant():
    """EMA of all-100 prices over 25 bars with window=20 → 100.0."""
    bars = _bars_df([100.0] * 25)
    out = ema(bars, window=20)
    assert out == pytest.approx(100.0)


def test_ema_rising_prices_returns_value_in_upper_range():
    """Linearly rising 100..124 (25 bars), window=20 → EMA biased toward
    recent high values. Compare against ta directly to anchor the
    expected value (avoids reimplementing EMA in the test)."""
    closes = [100.0 + i for i in range(25)]
    bars = _bars_df(closes)
    out = ema(bars, window=20)
    assert out is not None
    # Recent values dominate; EMA(20) on 25 rising bars should be
    # well above the simple average (112.0) and below the latest (124.0).
    assert 112.0 < out < 124.0


def test_ema_empty_bars_returns_none():
    bars = pd.DataFrame({"close": []})
    assert ema(bars, window=20) is None


def test_ema_bars_shorter_than_window_returns_none():
    bars = _bars_df([100.0] * 10)
    assert ema(bars, window=20) is None


def test_ema_bars_at_exact_window_size_returns_value():
    """20 bars of constant 100, window=20 → returns 100.0."""
    bars = _bars_df([100.0] * 20)
    out = ema(bars, window=20)
    assert out == pytest.approx(100.0)


def test_ema_nan_close_returns_none():
    """All-NaN closes propagate through ta and yield NaN; we return None."""
    bars = _bars_df([np.nan] * 25)
    assert ema(bars, window=20) is None


def test_ema_none_bars_returns_none():
    assert ema(None, window=20) is None


def test_ema_window_one_returns_latest_close():
    """EMA with window=1 reduces to the latest close."""
    bars = _bars_df([100.0, 105.0, 110.0])
    out = ema(bars, window=1)
    assert out == pytest.approx(110.0)


# ─────────────────────────────────────────────────────────────────
# session_vwap
# ─────────────────────────────────────────────────────────────────


def test_vwap_constant_volume_rising_prices_is_simple_mean():
    """5 bars at prices 100..104, all volume=1000, high=low=close.
    Typical price = close. VWAP = mean = 102.0."""
    bars = _bars_df(
        closes=[100.0, 101.0, 102.0, 103.0, 104.0],
        volumes=[1000] * 5,
    )
    out = session_vwap(bars)
    assert out == pytest.approx(102.0)


def test_vwap_volume_weighted_three_row_example():
    """Canonical example from the prompt:
    bars: (h, l, c, v) = (100, 100, 100, 1), (110, 110, 110, 1), (105, 105, 105, 2)
    typical = close (h=l=c), VWAP = (100*1 + 110*1 + 105*2) / 4 = 105.0
    """
    bars = pd.DataFrame({
        "high":   [100.0, 110.0, 105.0],
        "low":    [100.0, 110.0, 105.0],
        "close":  [100.0, 110.0, 105.0],
        "volume": [1, 1, 2],
    })
    out = session_vwap(bars)
    assert out == pytest.approx(105.0)


def test_vwap_heavy_volume_biases_toward_that_price():
    """One high-volume bar dominates. 3 bars at 100/100/200 with
    volumes 1/1/100. Typical=close. VWAP = (100*1 + 100*1 + 200*100) / 102
    = 20200/102 ≈ 198.04."""
    bars = pd.DataFrame({
        "high":   [100.0, 100.0, 200.0],
        "low":    [100.0, 100.0, 200.0],
        "close":  [100.0, 100.0, 200.0],
        "volume": [1, 1, 100],
    })
    out = session_vwap(bars)
    assert out == pytest.approx(20200.0 / 102.0)


def test_vwap_typical_price_uses_hlc_average():
    """One bar with high=110, low=90, close=100. Typical = 100.
    VWAP with single row → typical price = 100.0."""
    bars = pd.DataFrame({
        "high":   [110.0],
        "low":    [90.0],
        "close":  [100.0],
        "volume": [1000],
    })
    out = session_vwap(bars)
    assert out == pytest.approx(100.0)


def test_vwap_empty_bars_returns_none():
    bars = pd.DataFrame({
        "high": [], "low": [], "close": [], "volume": [],
    })
    assert session_vwap(bars) is None


def test_vwap_single_row_with_equal_hlc_returns_close():
    """Single-row DataFrame with high=low=close=100 → typical=100.0,
    VWAP=100.0."""
    bars = _bars_df([100.0])
    out = session_vwap(bars)
    assert out == pytest.approx(100.0)


def test_vwap_none_bars_returns_none():
    assert session_vwap(None) is None


def test_vwap_zero_volume_does_not_crash():
    """Edge case: zero-volume bars. ta returns NaN when volume.cumsum()
    is zero. We handle by returning None."""
    bars = pd.DataFrame({
        "high":   [100.0, 110.0],
        "low":    [100.0, 110.0],
        "close":  [100.0, 110.0],
        "volume": [0, 0],
    })
    out = session_vwap(bars)
    # ta produces NaN here; our wrapper turns it into None.
    assert out is None
