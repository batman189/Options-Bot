# CLAUDE CODE PROMPT 03 — Data Provider Abstraction Layer

## TASK
Create the data abstraction layer: abstract DataProvider interface, Alpaca stock data provider, and Theta Data options provider. These sit between raw APIs and everything that consumes data (feature engineering, ML training). This is Phase 1, Step 5 from the architecture.

**Key design principle**: These providers serve TRAINING DATA COLLECTION primarily. For live trading, Lumibot's built-in methods (get_last_price, get_chains, get_greeks) handle real-time data. The providers handle the heavy lifting of fetching 6+ years of historical bars, options data, and Greeks for model training.

**CRITICAL**: Before writing ANY code, read this ENTIRE prompt. Do not improvise. Build exactly what is specified.

---

## FILES TO CREATE

1. `options-bot/data/__init__.py` — empty
2. `options-bot/data/provider.py` — Abstract DataProvider interface
3. `options-bot/data/alpaca_provider.py` — Alpaca stock data implementation
4. `options-bot/data/theta_provider.py` — Theta Data options implementation

Files NOT created in this prompt (later prompts):
- `data/validator.py` — will be created with feature engineering
- `data/greeks_calculator.py` — will be created with feature engineering

---

## FILE 1: `options-bot/data/__init__.py`

```python
```

(Empty file — makes data a Python package)

---

## FILE 2: `options-bot/data/provider.py`

```python
"""
Abstract DataProvider interface.
Matches PROJECT_ARCHITECTURE.md Section 4 — Data abstraction layer.

Design:
    - StockDataProvider: historical stock bars (Alpaca)
    - OptionsDataProvider: historical options data + Greeks (Theta Data)
    - Strategy code uses Lumibot built-in methods for live data
    - These providers are for TRAINING data collection

Adding/swapping data sources never requires touching ML or strategy code.
"""

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Optional
import pandas as pd


class StockDataProvider(ABC):
    """Abstract interface for stock price data."""

    @abstractmethod
    def get_historical_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "5min",
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV bars for a stock.

        Args:
            symbol: Ticker symbol (e.g. "TSLA")
            start: Start datetime (inclusive)
            end: End datetime (inclusive)
            timeframe: Bar size — "1min", "5min", "15min", "1h", "1d"

        Returns:
            DataFrame with columns: [open, high, low, close, volume]
            Index: DatetimeIndex (UTC)
            Empty DataFrame if no data available.
        """
        pass

    @abstractmethod
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get the most recent price for a symbol. Returns None if unavailable."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if the data source is reachable. Returns True/False."""
        pass


class OptionsDataProvider(ABC):
    """Abstract interface for options data (chains, Greeks, OI)."""

    @abstractmethod
    def get_expirations(self, symbol: str) -> list[date]:
        """
        Get all available option expiration dates for a symbol.

        Returns:
            Sorted list of expiration dates. Empty list if none available.
        """
        pass

    @abstractmethod
    def get_strikes(self, symbol: str, expiration: date) -> list[float]:
        """
        Get all available strike prices for a symbol and expiration.

        Returns:
            Sorted list of strike prices. Empty list if none available.
        """
        pass

    @abstractmethod
    def get_historical_greeks(
        self,
        symbol: str,
        expiration: date,
        strike: float,
        right: str,
        trade_date: date,
    ) -> Optional[dict]:
        """
        Get end-of-day Greeks for a specific contract on a specific date.

        Args:
            symbol: Underlying ticker
            expiration: Option expiration date
            strike: Strike price (e.g. 250.0)
            right: "call" or "put"
            trade_date: The date to fetch Greeks for

        Returns:
            Dict with keys: {delta, gamma, theta, vega, rho, implied_volatility,
                            underlying_price, bid, ask, volume, open_interest}
            Returns None if data unavailable.

        Note: Theta Data rho and vega must be divided by 100 — the provider
              handles this conversion internally.
        """
        pass

    @abstractmethod
    def get_historical_ohlc(
        self,
        symbol: str,
        expiration: date,
        strike: float,
        right: str,
        trade_date: date,
        interval: str = "5m",
    ) -> pd.DataFrame:
        """
        Get historical OHLCV bars for a specific option contract.

        Returns:
            DataFrame with columns: [open, high, low, close, volume]
            Index: DatetimeIndex
            Empty DataFrame if no data available.
        """
        pass

    @abstractmethod
    def get_historical_eod(
        self,
        symbol: str,
        expiration: date,
        strike: float,
        right: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """
        Get end-of-day option data across a date range.

        Returns:
            DataFrame with columns: [date, open, high, low, close, volume,
                                     bid, ask, open_interest]
            Empty DataFrame if no data available.
        """
        pass

    @abstractmethod
    def get_bulk_greeks_eod(
        self,
        symbol: str,
        expiration: date,
        trade_date: date,
    ) -> pd.DataFrame:
        """
        Get end-of-day Greeks for ALL strikes at an expiration on a given date.
        Used for bulk training data collection — much more efficient than
        per-contract calls.

        Returns:
            DataFrame with columns: [strike, right, delta, gamma, theta, vega,
                                     rho, implied_volatility, underlying_price]
            Empty DataFrame if no data available.
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if the data source is reachable. Returns True/False."""
        pass
```

---

## FILE 3: `options-bot/data/alpaca_provider.py`

```python
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
from config import ALPACA_API_KEY, ALPACA_API_SECRET
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
                ALPACA_API_KEY, ALPACA_API_SECRET, paper=True
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

                    if symbol not in bars or len(bars[symbol]) == 0:
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

                    # If we got fewer than max, we've reached the end
                    if len(bar_list) < ALPACA_MAX_BARS_PER_REQUEST:
                        current_start = end  # Exit outer loop

                    break  # Success — exit retry loop

                except Exception as e:
                    logger.warning(
                        f"  Page {page_count} attempt {attempt} failed: {e}"
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY_SECONDS * attempt)
                    else:
                        logger.error(
                            f"  Page {page_count} failed after {MAX_RETRIES} attempts. "
                            f"Returning data collected so far."
                        )
                        current_start = end  # Exit outer loop

        if not all_bars:
            logger.warning(f"No bars returned for {symbol}")
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
```

---

## FILE 4: `options-bot/data/theta_provider.py`

```python
"""
Theta Data options data provider implementation.
Fetches historical options data, Greeks, and chain info from Theta Terminal V3.
Matches PROJECT_ARCHITECTURE.md Section 3 — Theta Data role.

Handles:
    - V3 REST API (localhost:25503) — auto-detects if terminal is running
    - Historical 1st order Greeks (delta, gamma, theta, vega, rho)
    - Historical options OHLCV
    - Historical EOD data
    - Expiration and strike listings
    - Rho/Vega division by 100 (Theta Data convention)
    - Retry logic for transient failures
    - CSV response parsing (V3 default format)

Note: For LIVE Greeks, Lumibot's built-in get_greeks() (Black-Scholes)
is the primary path. This provider is for TRAINING data collection.
"""

import logging
import time
import io
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import requests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import THETA_BASE_URL_V3
from data.provider import OptionsDataProvider

logger = logging.getLogger("options-bot.data.theta")

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
REQUEST_TIMEOUT = 60  # Theta can be slow for large requests


class ThetaOptionsProvider(OptionsDataProvider):
    """Fetches historical options data from Theta Data Terminal V3."""

    def __init__(self, base_url: str = None):
        self._base_url = base_url or THETA_BASE_URL_V3
        logger.info(f"Initializing ThetaOptionsProvider at {self._base_url}")

    def _request(
        self,
        endpoint: str,
        params: dict,
        description: str = "",
    ) -> Optional[dict]:
        """
        Make a request to Theta Terminal V3 with retry logic.
        Returns parsed JSON response or None on failure.
        """
        url = f"{self._base_url}{endpoint}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug(
                    f"  Theta request ({description}): {endpoint} "
                    f"params={params} (attempt {attempt})"
                )
                resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 200:
                    # V3 may return CSV or JSON depending on format param
                    content_type = resp.headers.get("content-type", "")
                    if "text/csv" in content_type or resp.text.startswith('"') or ',' in resp.text.split('\n')[0]:
                        # CSV response — return raw text for caller to parse
                        return {"format": "csv", "data": resp.text}
                    else:
                        return resp.json()
                elif resp.status_code == 404:
                    logger.debug(f"  No data: {endpoint} {params}")
                    return None
                elif resp.status_code == 403:
                    logger.error(
                        f"  Access denied (subscription tier?): {endpoint}. "
                        f"Response: {resp.text[:200]}"
                    )
                    return None
                elif resp.status_code == 410:
                    logger.error(
                        f"  Endpoint gone (V2 endpoint on V3 terminal?): {endpoint}"
                    )
                    return None
                else:
                    logger.warning(
                        f"  Theta status {resp.status_code}: {resp.text[:200]}"
                    )

            except requests.exceptions.ConnectionError:
                logger.warning(
                    f"  Cannot connect to Theta Terminal at {self._base_url}. "
                    f"Is it running? (attempt {attempt})"
                )
            except requests.exceptions.Timeout:
                logger.warning(
                    f"  Theta request timed out after {REQUEST_TIMEOUT}s "
                    f"(attempt {attempt})"
                )
            except Exception as e:
                logger.warning(f"  Theta request error: {e} (attempt {attempt})")

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)

        logger.error(f"Theta request failed after {MAX_RETRIES} attempts: {endpoint}")
        return None

    def _parse_csv_response(self, raw_data: dict, description: str = "") -> pd.DataFrame:
        """Parse a CSV response from Theta Terminal V3 into a DataFrame."""
        if raw_data is None:
            return pd.DataFrame()

        if raw_data.get("format") == "csv":
            csv_text = raw_data["data"]
            if not csv_text or csv_text.strip() == "":
                return pd.DataFrame()
            try:
                df = pd.read_csv(io.StringIO(csv_text))
                return df
            except Exception as e:
                logger.error(f"Failed to parse CSV response ({description}): {e}")
                return pd.DataFrame()

        # JSON response with header + response arrays
        if "header" in raw_data and "response" in raw_data:
            header = raw_data["header"]
            response = raw_data["response"]
            fmt = header.get("format", [])
            if not response or not fmt:
                return pd.DataFrame()
            try:
                df = pd.DataFrame(response, columns=fmt)
                return df
            except Exception as e:
                logger.error(f"Failed to parse JSON response ({description}): {e}")
                return pd.DataFrame()

        return pd.DataFrame()

    @staticmethod
    def _format_date(d: date) -> str:
        """Format a date as YYYYMMDD for Theta V3 API."""
        return d.strftime("%Y%m%d")

    @staticmethod
    def _format_strike(strike: float) -> str:
        """Format a strike price for Theta V3 API (decimal format)."""
        return f"{strike:.3f}"

    def get_expirations(self, symbol: str) -> list[date]:
        """Get all available option expiration dates."""
        logger.info(f"Fetching expirations for {symbol}")
        start_time = time.time()

        data = self._request(
            "/option/list/expirations",
            params={"symbol": symbol},
            description=f"expirations for {symbol}",
        )

        if data is None:
            return []

        df = self._parse_csv_response(data, "expirations")
        if df.empty:
            # Try JSON format
            if isinstance(data, dict) and "response" in data:
                raw = data["response"]
                if isinstance(raw, list):
                    try:
                        result = sorted([
                            datetime.strptime(str(d), "%Y%m%d").date()
                            if isinstance(d, (int, str)) and len(str(d)) == 8
                            else pd.Timestamp(d).date()
                            for d in raw
                        ])
                        elapsed = time.time() - start_time
                        logger.info(
                            f"Got {len(result)} expirations for {symbol} "
                            f"in {elapsed:.1f}s"
                        )
                        return result
                    except Exception as e:
                        logger.error(f"Failed to parse expirations: {e}")
                        return []
            return []

        # Parse from DataFrame
        try:
            # The column name varies — find the date-like column
            date_col = df.columns[0]
            result = sorted([
                pd.Timestamp(str(d)).date()
                for d in df[date_col]
            ])
            elapsed = time.time() - start_time
            logger.info(
                f"Got {len(result)} expirations for {symbol} in {elapsed:.1f}s"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to parse expirations DataFrame: {e}")
            return []

    def get_strikes(self, symbol: str, expiration: date) -> list[float]:
        """Get all available strike prices for a symbol and expiration."""
        logger.info(f"Fetching strikes for {symbol} exp={expiration}")

        data = self._request(
            "/option/list/strikes",
            params={
                "symbol": symbol,
                "expiration": self._format_date(expiration),
            },
            description=f"strikes for {symbol} {expiration}",
        )

        if data is None:
            return []

        df = self._parse_csv_response(data, "strikes")
        if df.empty:
            if isinstance(data, dict) and "response" in data:
                raw = data["response"]
                if isinstance(raw, list):
                    try:
                        return sorted([float(s) for s in raw])
                    except (ValueError, TypeError):
                        pass
            return []

        try:
            strike_col = df.columns[0]
            return sorted([float(s) for s in df[strike_col]])
        except Exception as e:
            logger.error(f"Failed to parse strikes: {e}")
            return []

    def get_historical_greeks(
        self,
        symbol: str,
        expiration: date,
        strike: float,
        right: str,
        trade_date: date,
    ) -> Optional[dict]:
        """
        Get end-of-day Greeks for a specific contract on a specific date.
        Uses /v3/option/history/greeks/first_order endpoint.
        Rho and Vega are divided by 100 per Theta Data convention.
        """
        logger.debug(
            f"Fetching Greeks: {symbol} {expiration} ${strike} {right} on {trade_date}"
        )

        data = self._request(
            "/option/history/greeks/first_order",
            params={
                "symbol": symbol,
                "expiration": self._format_date(expiration),
                "strike": self._format_strike(strike),
                "right": right.lower(),
                "date": self._format_date(trade_date),
            },
            description=f"greeks {symbol} {strike} {right} {trade_date}",
        )

        if data is None:
            return None

        df = self._parse_csv_response(data, "greeks")
        if df.empty:
            return None

        # Take the last row (end of day) if multiple intervals
        row = df.iloc[-1]

        # Build result dict — normalize column names (they vary by API version)
        result = {}
        col_map = {
            "delta": "delta",
            "gamma": "gamma",
            "theta": "theta",
            "vega": "vega",
            "rho": "rho",
            "implied_volatility": "implied_volatility",
            "iv": "implied_volatility",
            "underlying_price": "underlying_price",
        }
        for api_col, our_key in col_map.items():
            for df_col in df.columns:
                if api_col in df_col.lower():
                    try:
                        result[our_key] = float(row[df_col])
                    except (ValueError, TypeError):
                        result[our_key] = None
                    break

        # Apply Theta Data convention: divide rho and vega by 100
        if result.get("rho") is not None:
            result["rho"] = result["rho"] / 100.0
        if result.get("vega") is not None:
            result["vega"] = result["vega"] / 100.0

        return result if result else None

    def get_historical_ohlc(
        self,
        symbol: str,
        expiration: date,
        strike: float,
        right: str,
        trade_date: date,
        interval: str = "5m",
    ) -> pd.DataFrame:
        """Get historical OHLCV bars for a specific option contract."""
        logger.debug(
            f"Fetching options OHLC: {symbol} {expiration} ${strike} {right} "
            f"on {trade_date} interval={interval}"
        )

        data = self._request(
            "/option/history/ohlc",
            params={
                "symbol": symbol,
                "expiration": self._format_date(expiration),
                "strike": self._format_strike(strike),
                "right": right.lower(),
                "date": self._format_date(trade_date),
                "interval": interval,
            },
            description=f"ohlc {symbol} {strike} {right} {trade_date}",
        )

        if data is None:
            return pd.DataFrame()

        df = self._parse_csv_response(data, "options ohlc")
        if df.empty:
            return pd.DataFrame()

        # Normalize columns
        rename = {}
        for col in df.columns:
            cl = col.lower()
            if "open" in cl and "interest" not in cl:
                rename[col] = "open"
            elif "high" in cl:
                rename[col] = "high"
            elif "low" in cl:
                rename[col] = "low"
            elif "close" in cl:
                rename[col] = "close"
            elif "volume" in cl or "vol" in cl:
                rename[col] = "volume"

        if rename:
            df = df.rename(columns=rename)

        return df

    def get_historical_eod(
        self,
        symbol: str,
        expiration: date,
        strike: float,
        right: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Get end-of-day option data across a date range."""
        logger.info(
            f"Fetching options EOD: {symbol} {expiration} ${strike} {right} "
            f"from {start_date} to {end_date}"
        )

        data = self._request(
            "/option/history/eod",
            params={
                "symbol": symbol,
                "expiration": self._format_date(expiration),
                "strike": self._format_strike(strike),
                "right": right.lower(),
                "start_date": self._format_date(start_date),
                "end_date": self._format_date(end_date),
            },
            description=f"eod {symbol} {strike} {right} {start_date}-{end_date}",
        )

        if data is None:
            return pd.DataFrame()

        return self._parse_csv_response(data, "options eod")

    def get_bulk_greeks_eod(
        self,
        symbol: str,
        expiration: date,
        trade_date: date,
    ) -> pd.DataFrame:
        """
        Get end-of-day Greeks for ALL strikes at an expiration on a given date.
        Uses the greeks/first_order endpoint with strike=* to get bulk data.
        Much more efficient than per-contract calls for training data.

        Note: Rho and Vega are divided by 100 in the returned DataFrame.
        """
        logger.info(
            f"Fetching bulk Greeks: {symbol} exp={expiration} date={trade_date}"
        )
        start_time = time.time()

        data = self._request(
            "/option/history/greeks/first_order",
            params={
                "symbol": symbol,
                "expiration": self._format_date(expiration),
                "strike": "*",
                "right": "both",
                "date": self._format_date(trade_date),
            },
            description=f"bulk greeks {symbol} {expiration} {trade_date}",
        )

        if data is None:
            return pd.DataFrame()

        df = self._parse_csv_response(data, "bulk greeks")
        if df.empty:
            return pd.DataFrame()

        # Apply rho/vega division by 100
        for col in df.columns:
            cl = col.lower()
            if "rho" in cl or "vega" in cl:
                try:
                    df[col] = df[col].astype(float) / 100.0
                except (ValueError, TypeError):
                    pass

        elapsed = time.time() - start_time
        logger.info(
            f"Got {len(df)} rows of bulk Greeks for {symbol} exp={expiration} "
            f"date={trade_date} in {elapsed:.1f}s"
        )
        return df

    def test_connection(self) -> bool:
        """Test Theta Terminal connectivity."""
        logger.info(f"Testing Theta Terminal connection at {self._base_url}")
        try:
            resp = requests.get(
                f"{self._base_url}/stock/list/symbols",
                timeout=10,
            )
            connected = resp.status_code == 200
            if connected:
                logger.info("Theta Terminal V3 connected")
            else:
                logger.warning(
                    f"Theta Terminal returned status {resp.status_code}"
                )
            return connected
        except requests.exceptions.ConnectionError:
            logger.warning(
                f"Cannot connect to Theta Terminal at {self._base_url}. "
                f"Is it running?"
            )
            return False
        except Exception as e:
            logger.error(f"Theta connection test error: {e}")
            return False
```

---

## STEP 5: Create a test script for the providers

**File**: `options-bot/scripts/test_providers.py`

```python
"""
Test script for data providers.
Validates that both providers can fetch data correctly.

Usage:
    cd options-bot
    python scripts/test_providers.py

Requires:
    - .env configured with API keys
    - Theta Terminal V3 running
"""

import sys
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_providers")


def test_alpaca_provider():
    """Test AlpacaStockProvider."""
    logger.info("=" * 60)
    logger.info("TEST: AlpacaStockProvider")
    logger.info("=" * 60)

    from data.alpaca_provider import AlpacaStockProvider

    provider = AlpacaStockProvider()

    # Test connection
    connected = provider.test_connection()
    logger.info(f"Connection: {'✅ PASS' if connected else '❌ FAIL'}")
    if not connected:
        return False

    # Test latest price
    price = provider.get_latest_price("TSLA")
    logger.info(
        f"Latest price: {'✅ PASS' if price else '❌ FAIL'} "
        f"(TSLA: ${price:.2f})" if price else "Latest price: ❌ FAIL"
    )

    # Test recent 5-min bars (small request)
    logger.info("Fetching 1 day of 5-min bars...")
    end = datetime.now()
    start = end - timedelta(days=3)  # 3 days to account for weekends
    df = provider.get_historical_bars("TSLA", start, end, "5min")
    logger.info(
        f"Recent bars: {'✅ PASS' if len(df) > 0 else '❌ FAIL'} "
        f"({len(df)} bars)"
    )
    if len(df) > 0:
        logger.info(f"  Columns: {list(df.columns)}")
        logger.info(f"  Date range: {df.index[0]} to {df.index[-1]}")
        logger.info(f"  Sample:\n{df.head(3)}")

    # Test historical depth (1 week from 2020)
    logger.info("Fetching 1 week of 5-min bars from 2020...")
    df_hist = provider.get_historical_bars(
        "TSLA",
        datetime(2020, 6, 15, 9, 30),
        datetime(2020, 6, 19, 16, 0),
        "5min",
    )
    logger.info(
        f"Historical bars (2020): {'✅ PASS' if len(df_hist) > 0 else '❌ FAIL'} "
        f"({len(df_hist)} bars)"
    )

    return True


def test_theta_provider():
    """Test ThetaOptionsProvider."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST: ThetaOptionsProvider")
    logger.info("=" * 60)

    from data.theta_provider import ThetaOptionsProvider

    provider = ThetaOptionsProvider()

    # Test connection
    connected = provider.test_connection()
    logger.info(f"Connection: {'✅ PASS' if connected else '❌ FAIL'}")
    if not connected:
        return False

    # Test expirations
    expirations = provider.get_expirations("TSLA")
    logger.info(
        f"Expirations: {'✅ PASS' if len(expirations) > 0 else '❌ FAIL'} "
        f"({len(expirations)} total)"
    )
    if expirations:
        logger.info(f"  Earliest: {expirations[0]}, Latest: {expirations[-1]}")

    # Test strikes (use a near-term expiration)
    if expirations:
        # Find the first expiration that's at least 7 days out
        future_exps = [e for e in expirations if e > date.today() + timedelta(days=7)]
        test_exp = future_exps[0] if future_exps else expirations[-1]

        strikes = provider.get_strikes("TSLA", test_exp)
        logger.info(
            f"Strikes (exp={test_exp}): "
            f"{'✅ PASS' if len(strikes) > 0 else '❌ FAIL'} "
            f"({len(strikes)} strikes)"
        )
        if strikes:
            logger.info(f"  Range: ${strikes[0]} to ${strikes[-1]}")

            # Test historical Greeks for a specific contract
            # Use a recent past trading day
            test_date = date.today() - timedelta(days=1)
            # Skip weekends
            while test_date.weekday() >= 5:
                test_date -= timedelta(days=1)

            mid_strike = strikes[len(strikes) // 2]
            greeks = provider.get_historical_greeks(
                "TSLA", test_exp, mid_strike, "call", test_date
            )
            logger.info(
                f"Greeks ({mid_strike} call {test_date}): "
                f"{'✅ PASS' if greeks else '❌ FAIL'}"
            )
            if greeks:
                logger.info(f"  {greeks}")

            # Test bulk Greeks EOD
            bulk_df = provider.get_bulk_greeks_eod("TSLA", test_exp, test_date)
            logger.info(
                f"Bulk Greeks (exp={test_exp}, date={test_date}): "
                f"{'✅ PASS' if len(bulk_df) > 0 else '❌ FAIL'} "
                f"({len(bulk_df)} rows)"
            )
            if len(bulk_df) > 0:
                logger.info(f"  Columns: {list(bulk_df.columns)}")
                logger.info(f"  Sample:\n{bulk_df.head(3)}")

    return True


def main():
    logger.info("Data Provider Test Suite")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("")

    alpaca_ok = test_alpaca_provider()
    theta_ok = test_theta_provider()

    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Alpaca Provider: {'✅ PASS' if alpaca_ok else '❌ FAIL'}")
    logger.info(f"  Theta Provider:  {'✅ PASS' if theta_ok else '❌ FAIL'}")

    if alpaca_ok and theta_ok:
        logger.info("")
        logger.info("🎉 Both providers working. Ready for feature engineering.")
    else:
        logger.info("")
        logger.info("⚠️  Fix failures above before proceeding.")


if __name__ == "__main__":
    main()
```

---

## VERIFICATION

After creating all files, run these commands:

```bash
cd options-bot

# 1. Verify files exist
echo "=== Checking files ==="
for f in \
    data/__init__.py \
    data/provider.py \
    data/alpaca_provider.py \
    data/theta_provider.py \
    scripts/test_providers.py; do
    if [ -f "$f" ]; then echo "  ✅ $f"; else echo "  ❌ MISSING: $f"; fi
done

# 2. Verify imports work
echo ""
echo "=== Testing imports ==="
python -c "from data.provider import StockDataProvider, OptionsDataProvider; print('  ✅ provider.py imports OK')"
python -c "from data.alpaca_provider import AlpacaStockProvider; print('  ✅ alpaca_provider.py imports OK')"
python -c "from data.theta_provider import ThetaOptionsProvider; print('  ✅ theta_provider.py imports OK')"

# 3. Run the provider test suite
echo ""
echo "=== Running provider tests ==="
python scripts/test_providers.py
```

## WHAT SUCCESS LOOKS LIKE

1. All 5 files created in correct locations
2. All imports resolve without errors
3. `test_providers.py` shows:
   - AlpacaStockProvider: connection OK, latest price returned, recent bars returned, 2020 historical bars returned
   - ThetaOptionsProvider: connection OK, expirations returned, strikes returned, historical Greeks returned with delta/gamma/theta/vega, bulk Greeks returned
4. DataFrames have correct column names and reasonable values
5. No files created outside of what's listed here

## WHAT FAILURE LOOKS LIKE

- Import errors
- Connection failures (check .env and Theta Terminal)
- Empty DataFrames where data was expected
- Greeks values that seem wrong (e.g. delta > 1, which might mean rho/vega division wasn't applied)

## DO NOT

- Do NOT create `data/validator.py` or `data/greeks_calculator.py` yet (later prompt)
- Do NOT create any files not listed in this prompt
- Do NOT modify any files from Prompts 01 or 02
- Do NOT add live trading data methods — Lumibot handles that
- Do NOT add caching or database storage of fetched data — that comes with feature engineering
- Do NOT attempt to fetch years of data in the test — keep tests to small samples
