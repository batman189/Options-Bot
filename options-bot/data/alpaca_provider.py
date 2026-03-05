"""
Alpaca stock data provider implementation.
Fetches historical stock bars from Alpaca's data API.
Matches PROJECT_ARCHITECTURE.md Section 3 — Alpaca data role.

Handles:
    - 5-minute bars back to 2016 (~10 years)
    - Automatic pagination for large date ranges
    - Rate limiting awareness (10,000 calls/min on Algo Trader Plus)
    - Retry logic for transient failures

Note: For LIVE trading, Lumibot's built-in get_last_price() and
get_historical_prices() are used instead. This provider is for
TRAINING data collection.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER
from config import (
    ALPACA_CB_FAILURE_THRESHOLD, ALPACA_CB_RESET_TIMEOUT,
    RETRY_BACKOFF_BASE, RETRY_BACKOFF_MAX,
)
from utils.circuit_breaker import CircuitBreaker, exponential_backoff
from data.provider import StockDataProvider

logger = logging.getLogger("options-bot.data.alpaca")

# Alpaca returns max 10,000 bars per request
ALPACA_MAX_BARS_PER_REQUEST = 10000
# Max retries for transient failures
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


class AlpacaStockProvider(StockDataProvider):
    """Fetches historical stock data from Alpaca."""

    def __init__(self):
        logger.info("Initializing AlpacaStockProvider")
        self._stock_client = None
        self._trading_client = None
        self._init_clients()
        self._circuit_breaker = CircuitBreaker(
            name="alpaca",
            failure_threshold=ALPACA_CB_FAILURE_THRESHOLD,
            reset_timeout=ALPACA_CB_RESET_TIMEOUT,
        )

    def _init_clients(self):
        """Initialize Alpaca API clients."""
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.trading.client import TradingClient

            if not ALPACA_API_KEY or ALPACA_API_KEY == "your_key_here":
                logger.error("Alpaca API key not configured in .env")
                return

            self._stock_client = StockHistoricalDataClient(
                ALPACA_API_KEY, ALPACA_API_SECRET
            )
            self._trading_client = TradingClient(
                ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER
            )
            logger.info("Alpaca clients initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Alpaca clients: {e}", exc_info=True)

    def _timeframe_to_alpaca(self, timeframe: str):
        """Convert our timeframe strings to Alpaca TimeFrame objects."""
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        mapping = {
            "1min": TimeFrame.Minute,
            "5min": TimeFrame(5, TimeFrameUnit.Minute),
            "15min": TimeFrame(15, TimeFrameUnit.Minute),
            "1h": TimeFrame.Hour,
            "1d": TimeFrame.Day,
        }
        if timeframe not in mapping:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Supported: {list(mapping.keys())}"
            )
        return mapping[timeframe]

    def get_historical_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "5min",
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV bars with automatic pagination.
        For large date ranges (years), this makes multiple API calls
        and concatenates results.
        """
        if not self._circuit_breaker.can_execute():
            logger.warning(
                f"Alpaca circuit breaker OPEN — skipping bar fetch for {symbol}. "
                f"Will retry in {ALPACA_CB_RESET_TIMEOUT}s."
            )
            return pd.DataFrame()

        logger.info(
            f"Fetching {timeframe} bars for {symbol}: "
            f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
        )
        start_time = time.time()

        if not self._stock_client:
            logger.error("Alpaca stock client not initialized")
            return pd.DataFrame()

        from alpaca.data.requests import StockBarsRequest

        tf = self._timeframe_to_alpaca(timeframe)
        all_bars = []
        current_start = start
        page_count = 0

        while current_start < end:
            page_count += 1
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    logger.info(
                        f"  Page {page_count}: fetching from "
                        f"{current_start.strftime('%Y-%m-%d %H:%M')} "
                        f"(attempt {attempt}/{MAX_RETRIES})"
                    )

                    request = StockBarsRequest(
                        symbol_or_symbols=symbol,
                        timeframe=tf,
                        start=current_start,
                        end=end,
                        limit=ALPACA_MAX_BARS_PER_REQUEST,
                    )
                    bars = self._stock_client.get_stock_bars(request)

                    if symbol not in bars.data or len(bars[symbol]) == 0:
                        logger.info(f"  No more bars available after {current_start}")
                        current_start = end  # Exit outer loop
                        break

                    bar_list = bars[symbol]
                    page_df = pd.DataFrame(
                        [
                            {
                                "timestamp": b.timestamp,
                                "open": float(b.open),
                                "high": float(b.high),
                                "low": float(b.low),
                                "close": float(b.close),
                                "volume": int(b.volume),
                            }
                            for b in bar_list
                        ]
                    )
                    all_bars.append(page_df)
                    self._circuit_breaker.record_success()

                    logger.info(
                        f"  Page {page_count}: got {len(page_df)} bars "
                        f"({page_df['timestamp'].iloc[0]} to "
                        f"{page_df['timestamp'].iloc[-1]})"
                    )

                    # Move past the last bar we received
                    last_ts = page_df["timestamp"].iloc[-1]
                    if isinstance(last_ts, str):
                        last_ts = pd.Timestamp(last_ts)
                    current_start = last_ts.to_pydatetime() + timedelta(seconds=1)
                    # Strip timezone to match naive start/end from caller
                    if current_start.tzinfo is not None and end.tzinfo is None:
                        current_start = current_start.replace(tzinfo=None)

                    # If we got fewer than max, we've reached the end
                    if len(bar_list) < ALPACA_MAX_BARS_PER_REQUEST:
                        current_start = end  # Exit outer loop

                    break  # Success — exit retry loop

                except Exception as e:
                    logger.warning(
                        f"  Page {page_count} attempt {attempt} failed: {e}"
                    )
                    if attempt < MAX_RETRIES:
                        delay = exponential_backoff(attempt, base=RETRY_BACKOFF_BASE, max_delay=RETRY_BACKOFF_MAX)
                        logger.warning(
                            f"  Retrying in {delay:.1f}s (attempt {attempt}/{MAX_RETRIES})"
                        )
                        time.sleep(delay)
                    else:
                        self._circuit_breaker.record_failure()
                        logger.error(
                            f"  Page {page_count} failed after {MAX_RETRIES} attempts. "
                            f"Returning data collected so far."
                        )
                        current_start = end  # Exit outer loop

        if not all_bars:
            logger.debug(f"No bars returned for {symbol}")
            return pd.DataFrame()

        result = pd.concat(all_bars, ignore_index=True)
        result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
        result = result.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        result = result.set_index("timestamp")

        elapsed = time.time() - start_time
        logger.info(
            f"Completed: {len(result)} total bars for {symbol} "
            f"in {elapsed:.1f}s ({page_count} pages)"
        )
        return result

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get the most recent price for a symbol."""
        logger.info(f"Getting latest price for {symbol}")
        if not self._stock_client:
            logger.error("Alpaca stock client not initialized")
            return None

        try:
            from alpaca.data.requests import StockLatestBarRequest

            request = StockLatestBarRequest(symbol_or_symbols=symbol)
            bars = self._stock_client.get_stock_latest_bar(request)
            if symbol in bars:
                price = float(bars[symbol].close)
                logger.info(f"Latest price for {symbol}: ${price:.2f}")
                return price
            return None
        except Exception as e:
            logger.error(f"Failed to get latest price for {symbol}: {e}")
            return None

    def test_connection(self) -> bool:
        """Test Alpaca connectivity."""
        logger.info("Testing Alpaca connection")
        try:
            if not self._trading_client:
                return False
            account = self._trading_client.get_account()
            logger.info(f"Alpaca connected: equity=${float(account.equity):,.2f}")
            return True
        except Exception as e:
            logger.error(f"Alpaca connection test failed: {e}")
            return False
