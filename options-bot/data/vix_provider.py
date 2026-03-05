"""
VIX data provider — fetches current VIX level from Alpaca.
Used by base_strategy.py to gate entries based on volatility regime.

VIX is a market index. Alpaca provides it as a tradeable asset under
ticker "VIXY" (VIX ETF). We use the most recent daily close as a
proxy for current VIX.

Post-reverse-split, VIXY tracks VIX at roughly 1:1 ratio.
Thresholds in config.py (VIX_MIN_GATE, VIX_MAX_GATE) are set
accordingly (e.g. 15-35 range).
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

import sys
from pathlib import Path
# Add project root to sys.path — no setup.py/pyproject.toml in this project
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger("options-bot.data.vix_provider")

# Cache VIX level for this many seconds before refetching
# During live trading this avoids an API call every 5-minute iteration
VIX_CACHE_TTL_SECONDS = 300  # 5 minutes


class VIXProvider:
    """
    Fetches current VIX level from Alpaca.
    Thread-safe with internal caching to avoid hammering the API.
    """

    def __init__(self):
        self._cached_vix: Optional[float] = None
        self._cache_time: float = 0.0
        self._client = None  # Lazy-initialized Alpaca client (cached across calls)
        logger.info("VIXProvider initialized")

    def get_current_vix(self) -> Optional[float]:
        """
        Return the current VIX level (VIXY proxy). Uses cached value if fresh.

        Returns:
            VIXY price as float (e.g., 4.5), or None if unavailable.
            None is non-fatal — callers should allow trading when VIX is unavailable.
        """
        now = time.monotonic()

        # Return cached value if still fresh
        if self._cached_vix is not None and (now - self._cache_time) < VIX_CACHE_TTL_SECONDS:
            logger.debug(f"VIX cache hit: {self._cached_vix:.2f}")
            return self._cached_vix

        logger.info("Fetching VIX from Alpaca")
        t_start = time.time()

        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            from config import ALPACA_API_KEY, ALPACA_API_SECRET

            if not ALPACA_API_KEY or ALPACA_API_KEY == "your_key_here":
                logger.warning("Alpaca API key not configured — VIX unavailable")
                return None

            if self._client is None:
                self._client = StockHistoricalDataClient(
                    api_key=ALPACA_API_KEY,
                    secret_key=ALPACA_API_SECRET,
                )
            client = self._client

            end = datetime.now(timezone.utc)
            start = end - timedelta(days=5)  # 5-day buffer for weekends/holidays

            request = StockBarsRequest(
                symbol_or_symbols="VIXY",
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
            )

            bars = client.get_stock_bars(request)

            # Match exact access pattern from alpaca_provider.py (line 150-156):
            # bars[symbol] returns bar list, iterate with b.close
            if "VIXY" not in bars.data or len(bars["VIXY"]) == 0:
                logger.debug("VIX fetch: no VIXY bars returned")
                return None

            bar_list = bars["VIXY"]
            vixy_close = float(bar_list[-1].close)

            elapsed = time.time() - t_start
            logger.info(f"VIX (VIXY proxy) fetched: {vixy_close:.2f} in {elapsed:.2f}s")

            self._cached_vix = vixy_close
            self._cache_time = now
            return vixy_close

        except Exception as e:
            logger.warning(
                f"VIX fetch failed (trading will continue without gate): {e}",
                exc_info=True
            )

        return None


def fetch_vix_daily_bars(start: datetime, end: datetime) -> Optional[pd.DataFrame]:
    """
    Fetch daily VIXY + VIXM bars from Alpaca for feature engineering.

    Returns a DataFrame indexed by date with columns:
        vixy_close, vixm_close

    Used by trainer.py and base_strategy.py to populate VIX features
    in compute_base_features(). Returns None on any failure (non-fatal).
    """
    try:
        from config import (
            ALPACA_API_KEY, ALPACA_API_SECRET,
            VIX_PROXY_SHORT_TICKER, VIX_PROXY_MID_TICKER,
        )

        if not ALPACA_API_KEY or ALPACA_API_KEY == "your_key_here":
            logger.warning("Alpaca API key not configured — VIX daily bars unavailable")
            return None

        from data.alpaca_provider import AlpacaStockProvider
        provider = AlpacaStockProvider()

        t0 = time.time()

        # Fetch VIXY daily bars
        vixy_df = provider.get_historical_bars(
            symbol=VIX_PROXY_SHORT_TICKER,
            start=start,
            end=end,
            timeframe="1d",
        )

        if vixy_df is None or vixy_df.empty:
            logger.debug("No VIXY bars returned — VIX features will be NaN")
            return None

        result = pd.DataFrame(index=vixy_df.index)
        result["vixy_close"] = vixy_df["close"]

        # Fetch VIXM daily bars
        try:
            vixm_df = provider.get_historical_bars(
                symbol=VIX_PROXY_MID_TICKER,
                start=start,
                end=end,
                timeframe="1d",
            )
            if vixm_df is not None and not vixm_df.empty:
                # Align VIXM to VIXY index
                result["vixm_close"] = vixm_df["close"].reindex(result.index)
        except Exception as e:
            logger.warning(f"VIXM fetch failed (continuing with VIXY only): {e}")

        elapsed = time.time() - t0
        logger.info(
            f"VIX daily bars fetched: {len(result)} days "
            f"({VIX_PROXY_SHORT_TICKER}+{VIX_PROXY_MID_TICKER}) in {elapsed:.1f}s"
        )
        return result

    except Exception as e:
        logger.warning(f"VIX daily bars fetch failed (features will be NaN): {e}")
        return None
