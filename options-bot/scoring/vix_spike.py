"""VIX 60-minute spike detection for §4.2 0DTE asymmetric catalyst gate.

Public API:
  vix_spike_pct(now=None) -> Optional[float]
    Returns the percentage change in VIX over the last 60 minutes.
    Positive = upward spike. None when 1-min ^VIX history is
    unavailable or insufficient.

Source: Yahoo Finance ^VIX 1-minute bars via yfinance (already a
dependency, used elsewhere in the codebase). 60-second module-level
TTL cache.

Failure mode: fail-safe. All exception paths log at warning level
and return None. Caller treats None as 'spike check unavailable
this cycle' — the 0DTE catalyst gate is OR-of-four, so a None from
here doesn't block other catalyst paths.

The 15% threshold (per ARCHITECTURE.md §4.2) lives in the consuming
preset, not here. This module is a measurement; the preset interprets.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger("options-bot.scoring.vix_spike")

_CACHE_TTL_SECONDS = 60.0
_SPIKE_WINDOW_MINUTES = 60

_hist_cache: Optional[pd.DataFrame] = None
_hist_cache_time: float = 0.0


def _fetch_vix_1min() -> Optional[pd.DataFrame]:
    """Fetch today's 1-min ^VIX bars from Yahoo. Returns DataFrame
    indexed by timestamp with at least a 'Close' column, or None on
    any failure. Cached for _CACHE_TTL_SECONDS.
    """
    global _hist_cache, _hist_cache_time
    now_t = time.time()
    if (
        _hist_cache is not None
        and (now_t - _hist_cache_time) < _CACHE_TTL_SECONDS
    ):
        return _hist_cache

    try:
        import yfinance as yf
        hist = yf.Ticker("^VIX").history(period="1d", interval="1m")
    except Exception as e:
        logger.warning("vix_spike fetch failed: %s", e)
        return None

    if hist is None or hist.empty:
        logger.warning("vix 1-min history empty")
        return None

    _hist_cache = hist
    _hist_cache_time = now_t
    return hist


def vix_spike_pct(now: Optional[datetime] = None) -> Optional[float]:
    """Compute the percentage change in VIX over the last 60 minutes.

    Returns:
        Signed percentage as a float (e.g. 18.5 means VIX rose 18.5%
        in the last 60 min). Negative for declines. None if history
        is unavailable, insufficient, or on any error.

    The caller (0DTE catalyst gate) compares against §4.2's 15%
    threshold to determine whether the spike-catalyst path fires.

    Args:
        now: Optional reference datetime (must be tz-aware UTC). Used
            for testability — defaults to datetime.now(timezone.utc).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    hist = _fetch_vix_1min()
    if hist is None:
        return None

    try:
        # Defensive: if Yahoo returned a naive index, localize to UTC so
        # the comparison with `now` (tz-aware) works without raising.
        idx = hist.index
        if getattr(idx, "tz", None) is None:
            hist = hist.copy()
            hist.index = idx.tz_localize("UTC")

        hist = hist[hist.index <= now]
        if len(hist) < 2:
            logger.info(
                "vix 1-min history insufficient (<2 bars) for spike check"
            )
            return None

        latest_ts = hist.index[-1]
        target_time = latest_ts - pd.Timedelta(minutes=_SPIKE_WINDOW_MINUTES)
        past_rows = hist[hist.index <= target_time]
        if past_rows.empty:
            logger.info("no vix bars >= 60 min old")
            return None

        past_close = past_rows.iloc[-1]["Close"]
        latest_close = hist.iloc[-1]["Close"]

        if (
            pd.isna(past_close)
            or pd.isna(latest_close)
            or past_close <= 0
        ):
            logger.warning(
                "vix close values invalid (past=%s latest=%s)",
                past_close, latest_close,
            )
            return None

        return float((latest_close - past_close) / past_close * 100.0)
    except Exception as e:
        logger.warning("vix_spike_pct computation failed: %s", e)
        return None
