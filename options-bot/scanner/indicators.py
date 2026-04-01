"""Technical indicator helpers for scanner setup detection.
Pure functions operating on 1-minute bar DataFrames."""

import numpy as np
import ta


def directional_bars(bars, n: int) -> tuple[int, int]:
    """Count up/down bars in last N bars. Returns (up_count, total)."""
    recent = bars.tail(n)
    changes = recent["close"].diff().dropna()
    up = (changes > 0).sum()
    return int(up), len(changes)


def volume_vs_average(bars, recent_n: int = 8, avg_n: int = 60) -> float:
    """Ratio of recent volume to historical average for same period."""
    if len(bars) < avg_n:
        return 1.0
    recent = bars.tail(recent_n)["volume"].mean()
    avg = bars.tail(avg_n)["volume"].mean()
    return recent / avg if avg > 0 else 1.0


def net_move_pct(bars, n: int) -> float:
    """Net % move over last N bars."""
    if len(bars) < n:
        return 0.0
    start = bars.iloc[-n]["close"]
    end = bars.iloc[-1]["close"]
    return ((end - start) / start) * 100 if start > 0 else 0.0


def rsi(bars, window: int = 14) -> float:
    """Current RSI value."""
    series = ta.momentum.rsi(bars["close"], window=window)
    return float(series.iloc[-1]) if not series.empty and not np.isnan(series.iloc[-1]) else 50.0


def bollinger_position(bars, window: int = 20) -> tuple[float, float]:
    """Returns (pctb, bandwidth). pctb: 0=lower band, 1=upper band."""
    bb = ta.volatility.BollingerBands(bars["close"], window=window, window_dev=2)
    pctb = bb.bollinger_pband()
    bw = bb.bollinger_wband()
    p = float(pctb.iloc[-1]) if not pctb.empty and not np.isnan(pctb.iloc[-1]) else 0.5
    w = float(bw.iloc[-1]) if not bw.empty and not np.isnan(bw.iloc[-1]) else 0.02
    return p, w


def has_reversal_wick(bars) -> bool:
    """Check if most recent bar has a wick suggesting reversal."""
    if len(bars) < 2:
        return False
    last = bars.iloc[-1]
    body = abs(last["close"] - last["open"])
    full_range = last["high"] - last["low"]
    if full_range == 0:
        return False
    # Wick is significant if body is < 40% of full range
    return (body / full_range) < 0.4


def range_pct(bars, n: int) -> float:
    """High-low range as % of mean over last N bars."""
    if len(bars) < n:
        return 0.0
    recent = bars.tail(n)
    h, l = recent["high"].max(), recent["low"].min()
    mid = (h + l) / 2
    return ((h - l) / mid) * 100 if mid > 0 else 0.0


def volume_declining(bars, n: int = 3) -> bool:
    """Check if volume is declining over last N bars."""
    if len(bars) < n + 1:
        return False
    vols = bars.tail(n + 1)["volume"].values
    return all(vols[i] >= vols[i + 1] for i in range(len(vols) - 1))
