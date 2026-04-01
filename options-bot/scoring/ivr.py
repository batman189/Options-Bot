"""Implied Volatility Rank (IVR) computation.

IVR measures where current IV sits relative to its historical range.
IVR=0.0 means IV is at its 52-week low (options are cheap).
IVR=1.0 means IV is at its 52-week high (options are expensive).

Data source varies by symbol type because ThetaData Standard does not
provide historical IV data (returns zeros). Workarounds:

  SPY: VIX IS SPY's implied volatility index. Yahoo Finance provides
       252 days of VIX history. IVR = (current - 52w_low) / (52w_high - 52w_low).
       This is exact, not a proxy.

  Individual stocks (TSLA, etc): Use current ATM IV from ThetaData
       live snapshot vs a locally cached 20-day rolling window of daily
       IV values. Cache is built over time from daily snapshots.
       Cold start: returns None (factor skipped by scorer).
"""

import logging
import time
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger("options-bot.scoring.ivr")

# Local cache file for per-symbol daily IV history
_IV_CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
_vix_cache: Optional[dict] = None
_vix_cache_time: float = 0.0
_VIX_CACHE_TTL = 3600  # Refresh VIX history hourly


def get_ivr(symbol: str, current_iv: Optional[float] = None) -> Optional[float]:
    """Compute IVR for a symbol. Returns 0.0-1.0 or None if unavailable.

    Args:
        symbol: Ticker (e.g., "SPY", "TSLA")
        current_iv: Current ATM IV from ThetaData. Required for non-SPY.

    Returns:
        IVR as float 0.0-1.0, or None on cold start / data unavailable.
    """
    if symbol == "SPY":
        return _ivr_from_vix()
    else:
        return _ivr_from_cache(symbol, current_iv)


def _ivr_from_vix() -> Optional[float]:
    """SPY IVR from VIX 52-week range via Yahoo Finance."""
    global _vix_cache, _vix_cache_time
    now = time.time()

    if _vix_cache is None or (now - _vix_cache_time) > _VIX_CACHE_TTL:
        try:
            import yfinance as yf
            hist = yf.Ticker("^VIX").history(period="1y")
            if hist.empty or len(hist) < 20:
                logger.warning("VIX history insufficient for IVR")
                return None
            _vix_cache = {
                "low": float(hist["Close"].min()),
                "high": float(hist["Close"].max()),
                "current": float(hist["Close"].iloc[-1]),
            }
            _vix_cache_time = now
        except Exception as e:
            logger.warning(f"VIX IVR fetch failed: {e}")
            return None

    rng = _vix_cache["high"] - _vix_cache["low"]
    if rng <= 0:
        return 0.5
    ivr = (_vix_cache["current"] - _vix_cache["low"]) / rng
    return round(max(0.0, min(1.0, ivr)), 4)


def _ivr_from_cache(symbol: str, current_iv: Optional[float]) -> Optional[float]:
    """Stock IVR from locally cached daily IV snapshots.

    Cold start: returns None until 20 days of data exist.
    The cache is appended daily by record_daily_iv().
    """
    if current_iv is None or current_iv <= 0:
        return None

    cache_file = _IV_CACHE_DIR / f"iv_history_{symbol}.csv"
    if not cache_file.exists():
        logger.info(f"IVR cold start for {symbol} — no history file yet")
        return None

    try:
        import csv
        with open(cache_file, "r") as f:
            rows = list(csv.reader(f))
        # Format: date,iv
        ivs = [float(r[1]) for r in rows[-20:] if len(r) >= 2 and r[1]]
        if len(ivs) < 20:
            logger.info(f"IVR cold start for {symbol} — only {len(ivs)}/20 days")
            return None
        iv_low = min(ivs)
        iv_high = max(ivs)
        rng = iv_high - iv_low
        if rng <= 0:
            return 0.5
        return round(max(0.0, min(1.0, (current_iv - iv_low) / rng)), 4)
    except Exception as e:
        logger.warning(f"IVR cache read failed for {symbol}: {e}")
        return None


def record_daily_iv(symbol: str, iv: float):
    """Append today's ATM IV to the local cache. Called once per day."""
    _IV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _IV_CACHE_DIR / f"iv_history_{symbol}.csv"
    today = date.today().isoformat()
    try:
        # Check if already recorded today
        if cache_file.exists():
            with open(cache_file, "r") as f:
                for line in f:
                    if line.startswith(today):
                        return  # Already recorded
        with open(cache_file, "a") as f:
            f.write(f"{today},{iv:.6f}\n")
        logger.info(f"Recorded daily IV for {symbol}: {iv:.4f}")
    except Exception as e:
        logger.warning(f"Failed to record daily IV for {symbol}: {e}")
