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
from datetime import date, datetime
from typing import Optional

import pandas as pd
import requests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import THETA_BASE_URL_V3
from data.provider import OptionsDataProvider

logger = logging.getLogger("options-bot.data.theta")

# Retry constants are intentionally local to this module rather than imported
# from config.py. Theta Terminal uses simple linear backoff (delay * attempt)
# rather than the exponential backoff used for Alpaca. The 60s timeout is
# higher than options_data_fetcher's 30s because bulk Greeks requests are larger.
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
REQUEST_TIMEOUT = 60


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
                    # V3 may return CSV or JSON depending on format param.
                    # Check JSON first — JSON responses start with { or [
                    # and would be misclassified by the CSV comma heuristic.
                    content_type = resp.headers.get("content-type", "")
                    stripped = resp.text.lstrip()
                    if "application/json" in content_type or stripped.startswith("{") or stripped.startswith("["):
                        return resp.json()
                    elif "text/csv" in content_type or stripped.startswith('"') or ',' in resp.text.split('\n')[0]:
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
            # Find the expiration/date column (skip symbol columns)
            date_col = None
            for col in df.columns:
                if "expir" in col.lower() or "date" in col.lower():
                    date_col = col
                    break
            if date_col is None:
                # Fallback: use last column (first is usually symbol)
                date_col = df.columns[-1] if len(df.columns) > 1 else df.columns[0]
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
            # Find the strike column (skip symbol columns)
            strike_col = None
            for col in df.columns:
                if "strike" in col.lower():
                    strike_col = col
                    break
            if strike_col is None:
                strike_col = df.columns[-1] if len(df.columns) > 1 else df.columns[0]
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
            cl = col.lower().strip()
            # Use exact match to prevent "high_ask" matching "high", etc.
            if cl == "open":
                rename[col] = "open"
            elif cl == "high":
                rename[col] = "high"
            elif cl == "low":
                rename[col] = "low"
            elif cl == "close":
                rename[col] = "close"
            elif cl == "volume" or cl == "vol":
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
