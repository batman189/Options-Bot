"""
Unified data client — single interface for all market data.

Wraps Alpaca (stock bars), ThetaData (Greeks, OI, IV, quotes),
and Yahoo Finance (VIX) into one consistent API.

Rules:
    1. Every method validates returned data via data_validation.py.
       Null/zero/missing critical fields raise DataValidationError.
    2. health_check() is blocking at startup. All three connections
       must pass before any other module initializes.
    3. Cache layer prevents API hammering (options 30s, VIX 60s).
"""

import logging
import math
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from scipy.stats import norm

from data.data_validation import validate_field, DataValidationError, DataConnectionError
from data.theta_snapshot import ThetaSnapshotClient

logger = logging.getLogger("options-bot.data.unified_client")


@dataclass
class OptionGreeks:
    """Full Greeks for a single option contract."""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    implied_vol: float
    underlying_price: float
    source: str  # "thetadata+bs_gamma"


class UnifiedDataClient:
    """Single entry point for all market data."""

    def __init__(self):
        self._theta: Optional[ThetaSnapshotClient] = None
        self._alpaca = None  # Lazy-init
        self._vix_cache: Optional[float] = None
        self._vix_cache_time: float = 0.0
        self._chain_cache: dict = {}
        self._chain_cache_time: dict = {}

    # ── HEALTH CHECK (blocking at startup) ──────────────────────

    def health_check(self) -> dict:
        """Test all three data connections.

        Raises:
            DataConnectionError: infrastructure failure (port refused, timeout).
                Bot should HALT immediately.
            DataNotReadyError: connected but data not yet available (pre-market IV=0).
                Bot should RETRY every 60 seconds until market data populates.

        Must be called before any other method. Intentionally blocking.
        """
        from data.data_validation import DataNotReadyError
        results = {}

        # 1. Alpaca — fetch 1 SPY bar
        try:
            from data.alpaca_provider import AlpacaStockProvider
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            provider = AlpacaStockProvider()
            client = provider._stock_client
            req = StockBarsRequest(symbol_or_symbols="SPY", timeframe=TimeFrame.Minute, limit=1, feed="sip")
            bars = client.get_stock_bars(req)
            try:
                test_bars = bars["SPY"]
            except (KeyError, TypeError):
                test_bars = None
            if not test_bars:
                raise Exception("Empty bars")
            results["alpaca"] = "connected"
            self._alpaca = provider
            logger.info("Health: Alpaca CONNECTED")
        except Exception as e:
            logger.error(f"Health: Alpaca FAILED: {e}")
            raise DataConnectionError(f"Alpaca: {e}")

        # 2. ThetaData — distinguish connection failure from pre-market data gap
        try:
            self._theta = ThetaSnapshotClient()
            # Use ATM strike from the last SPY price (rounded to nearest dollar)
            spy_price = round(test_bars[-1].close) if test_bars else 500
            iv = self._theta.get_implied_volatility("SPY", date.today().isoformat(), float(spy_price), "call")
            results["thetadata"] = f"IV={iv['implied_vol']:.4f}"
            logger.info("Health: ThetaData CONNECTED")
        except ConnectionError as e:
            # Port refused, timeout — genuine infrastructure failure
            logger.error(f"Health: ThetaData CONNECTION FAILED: {e}")
            raise DataConnectionError(f"ThetaData connection failed: {e}")
        except DataValidationError as e:
            error_msg = str(e)
            if "zero" in error_msg.lower() and "implied_vol" in error_msg.lower():
                # IV=0 pre-market: ThetaData is connected but cache not yet populated
                logger.warning(f"Health: ThetaData connected but data not ready (pre-market): {e}")
                raise DataNotReadyError(
                    "ThetaData connected but IV=0 (pre-market). "
                    "Data populates after market open. Retry in 60 seconds."
                )
            else:
                # Other validation failure — treat as connection problem
                logger.error(f"Health: ThetaData data validation FAILED: {e}")
                raise DataConnectionError(f"ThetaData: {e}")
        except Exception as e:
            # Catch-all for unexpected errors — check if it's a connection issue
            error_str = str(e).lower()
            if "connection" in error_str or "refused" in error_str or "timeout" in error_str:
                logger.error(f"Health: ThetaData CONNECTION FAILED: {e}")
                raise DataConnectionError(f"ThetaData connection failed: {e}")
            else:
                logger.error(f"Health: ThetaData FAILED: {e}")
                raise DataConnectionError(f"ThetaData: {e}")

        # 3. Yahoo Finance — fetch VIX
        try:
            import yfinance as yf
            hist = yf.Ticker("^VIX").history(period="1d")
            if hist.empty:
                raise Exception("Empty VIX")
            vix_val = float(hist["Close"].iloc[-1])
            validate_field(vix_val, "VIX", "Yahoo", nonzero=True)
            results["vix"] = f"VIX={vix_val:.2f}"
            logger.info(f"Health: VIX CONNECTED ({vix_val:.2f})")
        except Exception as e:
            logger.error(f"Health: Yahoo VIX FAILED: {e}")
            raise DataConnectionError(f"Yahoo VIX: {e}")

        logger.info("Health: ALL CONNECTIONS HEALTHY")
        return results

    # ── STOCK BARS ──────────────────────────────────────────────

    def get_stock_bars(self, symbol: str, timeframe: str, count: int):
        """Fetch stock bars from Alpaca. Returns validated DataFrame.

        Alpaca's StockBarsRequest with only `limit` returns the EARLIEST
        `limit` bars in history, not the most recent. Passing a `start`
        parameter makes it return bars from that point forward; tailing
        the result guarantees the most recent `count` bars.
        """
        if self._alpaca is None:
            from data.alpaca_provider import AlpacaStockProvider
            self._alpaca = AlpacaStockProvider()

        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        import pandas as pd

        tf_map = {"1Min": TimeFrame.Minute,
                  "5Min":  TimeFrame(5,  TimeFrameUnit.Minute),
                  "15Min": TimeFrame(15, TimeFrameUnit.Minute),
                  "1Hour": TimeFrame.Hour, "1Day": TimeFrame.Day}
        minutes_per_bar = {"1Min": 1, "5Min": 5, "15Min": 15,
                           "1Hour": 60, "1Day": 1440}.get(timeframe, 1)
        # 3x buffer covers weekends, holidays, and after-hours gaps. No limit
        # on the request — Alpaca with (start, limit) returns the EARLIEST
        # limit bars from start, not the latest. Pull the full window and
        # tail(count) to guarantee the most recent bars.
        start = datetime.now(timezone.utc) - timedelta(minutes=minutes_per_bar * count * 3)

        client = self._alpaca._stock_client
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf_map.get(timeframe, TimeFrame.Minute),
            start=start, feed="sip",
        )
        bars = client.get_stock_bars(req)
        try:
            bar_list = bars[symbol]
        except (KeyError, TypeError):
            bar_list = None
        if not bar_list:
            raise DataValidationError(f"[Alpaca] No bars for {symbol}")

        rows = []
        for bar in bar_list:
            validate_field(bar.close, f"{symbol} close", "Alpaca", nonzero=True)
            validate_field(bar.volume, f"{symbol} volume", "Alpaca", min_val=0)
            rows.append({"timestamp": bar.timestamp, "open": bar.open, "high": bar.high,
                          "low": bar.low, "close": bar.close, "volume": bar.volume})
        return pd.DataFrame(rows).set_index("timestamp").tail(count)

    # ── OPTIONS CHAIN ───────────────────────────────────────────

    def get_nearest_expiration(self, symbol: str) -> str:
        """Get the nearest options expiration >= today for a symbol. Cached 1 hour."""
        cache_key = f"exp_{symbol}"
        now = time.time()
        if cache_key in self._chain_cache and (now - self._chain_cache_time.get(cache_key, 0)) < 3600:
            return self._chain_cache[cache_key]

        if self._theta is None:
            self._theta = ThetaSnapshotClient()
        all_exps = self._theta.get_expirations(symbol)
        today = date.today().isoformat()
        upcoming = [e for e in all_exps if e >= today]
        if not upcoming:
            raise DataValidationError(f"No upcoming expirations for {symbol}")
        nearest = upcoming[0]
        self._chain_cache[cache_key] = nearest
        self._chain_cache_time[cache_key] = now
        return nearest

    def get_options_chain(self, symbol: str, expiration: str = None):
        """Fetch chain: ThetaData quotes + OI. Cached 30s."""
        if expiration is None:
            expiration = self.get_nearest_expiration(symbol)
        key = f"{symbol}_{expiration}"
        now = time.time()
        if key in self._chain_cache and (now - self._chain_cache_time.get(key, 0)) < 30:
            return self._chain_cache[key]

        if self._theta is None:
            self._theta = ThetaSnapshotClient()
        oi = self._theta.get_open_interest_bulk(symbol, expiration)
        quotes = self._theta.get_quotes_bulk(symbol, expiration)
        if not quotes:
            raise DataValidationError(f"[ThetaData] Empty chain {symbol} exp={expiration}")

        oi_map = {(r["strike"], r["right"]): r["open_interest"] for r in oi}
        for q in quotes:
            q["open_interest"] = oi_map.get((q["strike"], q["right"]), 0)
            q["mid"] = round((q["bid"] + q["ask"]) / 2, 4) if q["bid"] and q["ask"] else 0

        self._chain_cache[key] = quotes
        self._chain_cache_time[key] = now
        return quotes

    # ── GREEKS ──────────────────────────────────────────────────

    def get_greeks(self, symbol: str, expiration: str, strike: float, right: str) -> OptionGreeks:
        """ThetaData first_order + local gamma from IV. Never calls Alpaca."""
        if self._theta is None:
            self._theta = ThetaSnapshotClient()

        raw = self._theta.get_first_order_greeks(symbol, expiration, strike, right)
        gamma = self._compute_gamma(raw["underlying_price"], strike, expiration, raw["implied_vol"], right)

        return OptionGreeks(
            delta=raw["delta"], gamma=gamma, theta=raw["theta"],
            vega=raw["vega"], rho=raw["rho"], implied_vol=raw["implied_vol"],
            underlying_price=raw["underlying_price"], source="thetadata+bs_gamma",
        )

    def _compute_gamma(self, S: float, K: float, expiration: str, sigma: float, right: str) -> float:
        """Black-Scholes gamma from ThetaData IV."""
        from config import RISK_FREE_RATE
        exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        days = (exp_date - date.today()).days
        if days <= 0:
            hours_to_close = max((20 - datetime.utcnow().hour), 0.5)
            T = hours_to_close / (365 * 24)
        else:
            T = days / 365.0
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = (math.log(S / K) + (RISK_FREE_RATE + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        return round(norm.pdf(d1) / (S * sigma * math.sqrt(T)), 6)

    # ── VIX ─────────────────────────────────────────────────────

    def get_vix(self) -> float:
        """Yahoo Finance ^VIX. Cached 60s. Validated nonzero."""
        now = time.time()
        if self._vix_cache is not None and (now - self._vix_cache_time) < 60:
            return self._vix_cache
        import yfinance as yf
        hist = yf.Ticker("^VIX").history(period="1d")
        if hist.empty:
            raise DataValidationError("[Yahoo] VIX returned empty")
        val = float(hist["Close"].iloc[-1])
        validate_field(val, "VIX", "Yahoo", nonzero=True)
        self._vix_cache = val
        self._vix_cache_time = now
        return val
