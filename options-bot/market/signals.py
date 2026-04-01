"""Market signal computations for regime classification.
Pure functions — no state, no API calls. Takes bars DataFrame as input."""

import logging
from typing import Optional

logger = logging.getLogger("options-bot.market.signals")


def compute_directional_move(bars, minutes: int) -> float:
    """Net % move over last N minutes. Positive = up, negative = down."""
    if len(bars) < minutes:
        return 0.0
    recent = bars.tail(minutes)
    start_price = recent.iloc[0]["close"]
    end_price = recent.iloc[-1]["close"]
    if start_price == 0:
        return 0.0
    return ((end_price - start_price) / start_price) * 100


def compute_range(bars, minutes: int) -> float:
    """High-low range as % of mean price over last N minutes."""
    if len(bars) < minutes:
        return 0.0
    recent = bars.tail(minutes)
    high = recent["high"].max()
    low = recent["low"].min()
    mid = (high + low) / 2
    if mid == 0:
        return 0.0
    return ((high - low) / mid) * 100


def count_reversals(bars, minutes: int) -> int:
    """Count direction changes in 5-min buckets over last N minutes."""
    if len(bars) < minutes:
        return 0
    recent = bars.tail(minutes)
    bucket_size = 5
    changes = recent["close"].diff()
    reversals = 0
    prev_direction = None
    for i in range(0, len(changes), bucket_size):
        bucket = changes.iloc[i:i + bucket_size]
        net = bucket.sum()
        direction = "up" if net > 0 else "down" if net < 0 else None
        if direction and prev_direction and direction != prev_direction:
            reversals += 1
        if direction:
            prev_direction = direction
    return reversals


def compute_volume_ratio(bars) -> float:
    """Current volume vs simple average (proxy for 20-day avg)."""
    if len(bars) < 30:
        return 1.0
    recent_vol = bars.tail(10)["volume"].mean()
    avg_vol = bars["volume"].mean()
    if avg_vol == 0:
        return 1.0
    return recent_vol / avg_vol


def fetch_vix_open() -> Optional[float]:
    """Fetch today's VIX opening value (9:30 AM ET) from Yahoo Finance."""
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="1d", interval="1m")
        if hist.empty:
            return None
        rth = hist[hist.index.hour * 60 + hist.index.minute >= 570]
        if rth.empty:
            return float(hist.iloc[0]["Open"])
        return float(rth.iloc[0]["Open"])
    except Exception as e:
        logger.warning(f"Failed to fetch VIX open: {e}")
        return None
