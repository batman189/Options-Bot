"""
VIX data provider — fetches current VIX level from Alpaca.
Used by base_strategy.py to gate entries based on volatility regime.

VIX is a market index. Alpaca provides it as a tradeable asset under
ticker "VIXY" (VIX ETF). We use the most recent daily close as a
proxy for current VIX.

VIXY is NOT a 1:1 proxy for VIX. Its price is ~1/5 of VIX due to ETF
structure. Use VIXY-scaled thresholds (see VIX_MIN_GATE, VIX_MAX_GATE
in config.py).
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import sys
from pathlib import Path
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

            client = StockHistoricalDataClient(
                api_key=ALPACA_API_KEY,
                secret_key=ALPACA_API_SECRET,
            )

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
                logger.warning("VIX fetch: no VIXY bars returned")
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
