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
