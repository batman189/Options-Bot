"""
Data Validation Script — Tests all data source connections.

Run this FIRST before building anything else. It confirms:
1. Alpaca API connection (stock bars, account info)
2. Alpaca historical stock data depth (5-min bars back to 2016)
3. Alpaca options chain availability
4. Theta Data Terminal connection (auto-detect V2/V3)
5. Theta Data historical options data depth
6. Theta Data Greeks availability

Usage:
    cd options-bot
    python scripts/validate_data.py

Requires:
    - .env file with ALPACA_API_KEY and ALPACA_API_SECRET
    - Theta Data Terminal running locally (optional — will report if not available)
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta, date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER,
    THETA_HOST, THETA_PORT, THETA_BASE_URL_V3, THETA_BASE_URL_V2,
    PHASE1_SYMBOLS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("validate_data")


# =============================================================================
# Result tracking
# =============================================================================
results = []


def record(test_name: str, passed: bool, detail: str):
    """Record a test result."""
    status = "PASS" if passed else "FAIL"
    results.append({"test": test_name, "passed": passed, "detail": detail})
    icon = "\u2705" if passed else "\u274c"
    logger.info(f"{icon} [{status}] {test_name}: {detail}")


# =============================================================================
# Test 1: Alpaca Connection
# =============================================================================
def test_alpaca_connection():
    """Test basic Alpaca API connectivity and account info."""
    logger.info("=" * 60)
    logger.info("TEST 1: Alpaca API Connection")
    logger.info("=" * 60)

    try:
        from alpaca.trading.client import TradingClient
        from alpaca.data.historical import StockHistoricalDataClient

        if not ALPACA_API_KEY or ALPACA_API_KEY == "your_key_here":
            record("Alpaca Connection", False, "API key not set in .env file")
            return False

        # Test trading client (account info)
        start = time.time()
        trading_client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)
        account = trading_client.get_account()
        elapsed = time.time() - start

        record(
            "Alpaca Connection",
            True,
            f"Connected in {elapsed:.2f}s | Account status: {account.status} | "
            f"Equity: ${float(account.equity):,.2f} | "
            f"Paper: {ALPACA_PAPER}"
        )

        # Check subscription type
        is_paid = float(account.equity) > 0 or ALPACA_PAPER
        record(
            "Alpaca Account Type",
            True,
            f"Paper={ALPACA_PAPER} | Equity=${float(account.equity):,.2f} | "
            f"Day trades (5d): {account.daytrade_count}"
        )
        return True

    except ImportError as e:
        record("Alpaca Connection", False, f"alpaca-py not installed: {e}")
        return False
    except Exception as e:
        record("Alpaca Connection", False, f"Connection failed: {e}")
        return False


# =============================================================================
# Test 2: Alpaca Historical Stock Bars
# =============================================================================
def test_alpaca_stock_bars():
    """Test Alpaca historical stock data — 5-min bars, depth check."""
    logger.info("=" * 60)
    logger.info("TEST 2: Alpaca Historical Stock Bars")
    logger.info("=" * 60)

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_API_SECRET)

        for symbol in PHASE1_SYMBOLS:
            # Test 1: Recent 5-min bars (should always work)
            logger.info(f"  Fetching recent 5-min bars for {symbol}...")
            start = time.time()
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Minute,
                start=datetime.now() - timedelta(days=5),
                end=datetime.now() - timedelta(minutes=20),
                limit=100,
            )
            bars = client.get_stock_bars(request)
            elapsed = time.time() - start

            bar_count = len(bars[symbol]) if symbol in bars.data else 0
            if bar_count > 0:
                first_bar = bars[symbol][0]
                last_bar = bars[symbol][-1]
                record(
                    f"Alpaca 5-min Bars ({symbol}, recent)",
                    True,
                    f"{bar_count} bars in {elapsed:.2f}s | "
                    f"Range: {first_bar.timestamp} to {last_bar.timestamp} | "
                    f"Sample close: ${first_bar.close}"
                )
            else:
                record(f"Alpaca 5-min Bars ({symbol}, recent)", False, "No bars returned")

            # Test 2: Historical depth — fetch one day from 2018 (6+ years ago)
            logger.info(f"  Fetching 2018 historical bars for {symbol}...")
            start = time.time()
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Minute,
                start=datetime(2018, 6, 15, 9, 30),
                end=datetime(2018, 6, 15, 16, 0),
                limit=1000,
            )
            bars = client.get_stock_bars(request)
            elapsed = time.time() - start

            bar_count = len(bars[symbol]) if symbol in bars.data else 0
            record(
                f"Alpaca Historical Depth ({symbol}, 2018)",
                bar_count > 0,
                f"{bar_count} bars from 2018-06-15 in {elapsed:.2f}s"
                + (f" | First: {bars[symbol][0].timestamp}" if bar_count > 0 else " | NO DATA")
            )

            # Test 3: Historical depth — fetch one day from 2016 (earliest expected)
            logger.info(f"  Fetching 2016 historical bars for {symbol}...")
            start = time.time()
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Minute,
                start=datetime(2016, 6, 15, 9, 30),
                end=datetime(2016, 6, 15, 16, 0),
                limit=1000,
            )
            bars = client.get_stock_bars(request)
            elapsed = time.time() - start

            bar_count = len(bars[symbol]) if symbol in bars.data else 0
            record(
                f"Alpaca Historical Depth ({symbol}, 2016)",
                bar_count > 0,
                f"{bar_count} bars from 2016-06-15 in {elapsed:.2f}s"
                + (f" | First: {bars[symbol][0].timestamp}" if bar_count > 0 else " | NO DATA")
            )

    except Exception as e:
        record("Alpaca Stock Bars", False, f"Error: {e}")


# =============================================================================
# Test 3: Alpaca Options Chain
# =============================================================================
def test_alpaca_options():
    """Test Alpaca live options chain availability."""
    logger.info("=" * 60)
    logger.info("TEST 3: Alpaca Options Chain")
    logger.info("=" * 60)

    try:
        from alpaca.data.historical import OptionHistoricalDataClient
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetOptionContractsRequest

        trading_client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)

        for symbol in PHASE1_SYMBOLS:
            logger.info(f"  Fetching options contracts for {symbol}...")
            start = time.time()

            request = GetOptionContractsRequest(
                underlying_symbols=[symbol],
                status="active",
                expiration_date_gte=date.today(),
                expiration_date_lte=date.today() + timedelta(days=60),
            )
            contracts = trading_client.get_option_contracts(request)
            elapsed = time.time() - start

            contract_count = len(contracts.option_contracts) if contracts.option_contracts else 0

            if contract_count > 0:
                sample = contracts.option_contracts[0]
                record(
                    f"Alpaca Options Chain ({symbol})",
                    True,
                    f"{contract_count} active contracts in {elapsed:.2f}s | "
                    f"Sample: {sample.symbol} {sample.expiration_date} "
                    f"${sample.strike_price} {sample.type}"
                )
            else:
                record(
                    f"Alpaca Options Chain ({symbol})",
                    False,
                    f"No contracts returned in {elapsed:.2f}s"
                )

    except Exception as e:
        record("Alpaca Options Chain", False, f"Error: {e}")


# =============================================================================
# Test 4: Theta Data Terminal Connection
# =============================================================================
def test_theta_connection():
    """Test Theta Data Terminal connectivity — auto-detect V2 vs V3."""
    logger.info("=" * 60)
    logger.info("TEST 4: Theta Data Terminal Connection")
    logger.info("=" * 60)

    import requests

    theta_version = None

    # Try V3 first (port from config, default 25503)
    try:
        logger.info(f"  Trying Theta Terminal V3 at {THETA_BASE_URL_V3}...")
        start = time.time()
        # V3 health check — try listing stock symbols
        resp = requests.get(
            f"{THETA_BASE_URL_V3}/stock/list/symbols",
            timeout=10,
        )
        elapsed = time.time() - start

        if resp.status_code == 200:
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            record(
                "Theta Terminal V3 Connection",
                True,
                f"Connected in {elapsed:.2f}s at {THETA_BASE_URL_V3} | "
                f"Status: {resp.status_code}"
            )
            theta_version = "v3"
        else:
            record(
                "Theta Terminal V3 Connection",
                False,
                f"Status {resp.status_code} at {THETA_BASE_URL_V3} | Response: {resp.text[:200]}"
            )
    except requests.exceptions.ConnectionError:
        record(
            "Theta Terminal V3 Connection",
            False,
            f"Cannot connect to {THETA_BASE_URL_V3} — Is Theta Terminal V3 running?"
        )
    except Exception as e:
        record("Theta Terminal V3 Connection", False, f"Error: {e}")

    # Try V2 if V3 failed (port 25510)
    if theta_version is None:
        try:
            logger.info(f"  Trying Theta Terminal V2 at {THETA_BASE_URL_V2}...")
            start = time.time()
            resp = requests.get(
                f"{THETA_BASE_URL_V2}/system/mdds/status",
                timeout=10,
            )
            elapsed = time.time() - start

            if resp.status_code == 200:
                record(
                    "Theta Terminal V2 Connection",
                    True,
                    f"Connected in {elapsed:.2f}s at {THETA_BASE_URL_V2} | "
                    f"Status: {resp.status_code}"
                )
                theta_version = "v2"
            else:
                record(
                    "Theta Terminal V2 Connection",
                    False,
                    f"Status {resp.status_code} at {THETA_BASE_URL_V2}"
                )
        except requests.exceptions.ConnectionError:
            record(
                "Theta Terminal V2 Connection",
                False,
                f"Cannot connect to {THETA_BASE_URL_V2} — Is Theta Terminal V2 running?"
            )
        except Exception as e:
            record("Theta Terminal V2 Connection", False, f"Error: {e}")

    if theta_version is None:
        logger.warning("  \u26a0\ufe0f  No Theta Terminal detected. Skipping Theta-dependent tests.")
        logger.warning("  \u26a0\ufe0f  Start Theta Terminal and re-run this script to validate options data.")

    return theta_version


# =============================================================================
# Test 5: Theta Data Historical Options
# =============================================================================
def test_theta_historical_options(theta_version: str):
    """Test Theta Data historical options data depth."""
    logger.info("=" * 60)
    logger.info("TEST 5: Theta Data Historical Options Data")
    logger.info("=" * 60)

    import requests
    import csv
    import io

    for symbol in PHASE1_SYMBOLS:
        if theta_version == "v3":
            # V3 endpoint: get available expirations
            # NOTE: V3 returns CSV, not JSON
            logger.info(f"  Fetching available expirations for {symbol} (V3)...")
            start = time.time()
            recent_exp = None  # Will be used by OHLC test below
            try:
                resp = requests.get(
                    f"{THETA_BASE_URL_V3}/option/list/expirations",
                    params={"symbol": symbol},
                    timeout=30,
                )
                elapsed = time.time() - start

                if resp.status_code == 200:
                    # Parse CSV response
                    reader = csv.DictReader(io.StringIO(resp.text))
                    expirations = [row["expiration"] for row in reader]
                    if expirations:
                        # Find a future expiration for later tests
                        today_str = date.today().strftime("%Y-%m-%d")
                        future_exps = [e for e in expirations if e >= today_str]
                        if future_exps:
                            recent_exp = future_exps[0]
                        record(
                            f"Theta Expirations ({symbol})",
                            True,
                            f"{len(expirations)} expirations in {elapsed:.2f}s | "
                            f"Earliest: {expirations[0]} | "
                            f"Latest: {expirations[-1]}"
                        )
                    else:
                        record(f"Theta Expirations ({symbol})", False, f"Empty response in {elapsed:.2f}s")
                else:
                    record(f"Theta Expirations ({symbol})", False, f"Status {resp.status_code}: {resp.text[:200]}")

            except Exception as e:
                record(f"Theta Expirations ({symbol})", False, f"Error: {e}")

            # V3 endpoint: fetch historical OHLC for one specific contract
            # Use a real expiration from the list above
            logger.info(f"  Fetching historical options OHLC for {symbol} (V3)...")
            start = time.time()
            try:
                # Use the real expiration we found, or fall back to a calculated one
                if recent_exp:
                    test_exp = recent_exp.replace("-", "")
                else:
                    test_exp = (date.today() + timedelta(days=30)).strftime("%Y%m%d")

                resp = requests.get(
                    f"{THETA_BASE_URL_V3}/option/list/strikes",
                    params={"symbol": symbol, "expiration": test_exp},
                    timeout=30,
                )
                if resp.status_code == 200:
                    # Strikes endpoint may also return CSV
                    content_type = resp.headers.get("content-type", "")
                    if "csv" in content_type or "text" in content_type:
                        reader = csv.DictReader(io.StringIO(resp.text))
                        strikes = [row.get("strike") or row.get("Strike") for row in reader]
                    else:
                        strikes_data = resp.json()
                        strikes = strikes_data.get("response", [])
                    if strikes:
                        # Pick a near-ATM strike
                        test_strike = strikes[len(strikes) // 2]
                        logger.info(f"    Testing with strike {test_strike}, exp {test_exp}")

                        ohlc_resp = requests.get(
                            f"{THETA_BASE_URL_V3}/option/history/ohlc",
                            params={
                                "symbol": symbol,
                                "expiration": test_exp,
                                "strike": str(test_strike),
                                "right": "call",
                                "date": date.today().strftime("%Y%m%d"),
                                "interval": "5m",
                            },
                            timeout=30,
                        )
                        elapsed = time.time() - start

                        if ohlc_resp.status_code == 200:
                            ohlc_ct = ohlc_resp.headers.get("content-type", "")
                            if "csv" in ohlc_ct or "text" in ohlc_ct:
                                ohlc_reader = csv.DictReader(io.StringIO(ohlc_resp.text))
                                rows = list(ohlc_reader)
                            else:
                                ohlc_data = ohlc_resp.json()
                                rows = ohlc_data.get("response", [])
                            record(
                                f"Theta Options OHLC ({symbol})",
                                len(rows) > 0,
                                f"{len(rows)} bars in {elapsed:.2f}s | "
                                f"Strike: {test_strike} | Exp: {test_exp}"
                            )
                        else:
                            record(
                                f"Theta Options OHLC ({symbol})",
                                False,
                                f"Status {ohlc_resp.status_code}: {ohlc_resp.text[:200]}"
                            )
                    else:
                        record(f"Theta Options OHLC ({symbol})", False, f"No strikes found for exp {test_exp}")
                else:
                    record(f"Theta Options OHLC ({symbol})", False, f"Strike list failed: {resp.status_code}")

            except Exception as e:
                record(f"Theta Options OHLC ({symbol})", False, f"Error: {e}")

        elif theta_version == "v2":
            # V2 endpoint for expirations
            logger.info(f"  Fetching available expirations for {symbol} (V2)...")
            start = time.time()
            try:
                resp = requests.get(
                    f"{THETA_BASE_URL_V2}/list/expirations",
                    params={"root": symbol, "sec": "OPTION"},
                    timeout=30,
                )
                elapsed = time.time() - start

                if resp.status_code == 200:
                    data = resp.json()
                    expirations = data.get("response", [])
                    record(
                        f"Theta Expirations ({symbol})",
                        len(expirations) > 0 if isinstance(expirations, list) else False,
                        f"Response in {elapsed:.2f}s | Data: {str(expirations)[:200]}"
                    )
                else:
                    record(f"Theta Expirations ({symbol})", False, f"Status {resp.status_code}")

            except Exception as e:
                record(f"Theta Expirations ({symbol})", False, f"Error: {e}")


# =============================================================================
# Test 6: Theta Data Greeks
# =============================================================================
def test_theta_greeks(theta_version: str):
    """Test Theta Data Greeks availability."""
    logger.info("=" * 60)
    logger.info("TEST 6: Theta Data Greeks")
    logger.info("=" * 60)

    import requests
    import csv
    import io

    for symbol in PHASE1_SYMBOLS:
        if theta_version == "v3":
            logger.info(f"  Fetching Greeks for {symbol} (V3)...")
            start = time.time()
            try:
                # Get nearest expiration first
                next_friday = date.today()
                while next_friday.weekday() != 4:  # Friday
                    next_friday += timedelta(days=1)
                test_exp = next_friday.strftime("%Y%m%d")

                # Try snapshot first_order (Standard tier), fall back to history
                resp = requests.get(
                    f"{THETA_BASE_URL_V3}/option/snapshot/greeks/first_order",
                    params={
                        "symbol": symbol,
                        "expiration": test_exp,
                    },
                    timeout=30,
                )

                # If snapshot fails, try history endpoint
                if resp.status_code != 200:
                    logger.info(f"    Snapshot returned {resp.status_code}, trying history endpoint...")
                    resp = requests.get(
                        f"{THETA_BASE_URL_V3}/option/history/greeks/first_order",
                        params={
                            "symbol": symbol,
                            "expiration": test_exp,
                            "strike": "355000",
                            "right": "call",
                            "start_date": date.today().strftime("%Y%m%d"),
                            "end_date": date.today().strftime("%Y%m%d"),
                        },
                        timeout=30,
                    )

                elapsed = time.time() - start

                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    if "csv" in content_type or "text" in content_type:
                        reader = csv.DictReader(io.StringIO(resp.text))
                        rows = list(reader)
                        fields = rows[0].keys() if rows else []
                        greeks_fields = {"delta", "gamma", "theta", "vega", "rho", "implied_volatility", "iv"}
                        found_fields = greeks_fields.intersection(set(f.lower() for f in fields))
                        record(
                            f"Theta Greeks ({symbol})",
                            len(found_fields) >= 3,
                            f"{len(rows)} rows in {elapsed:.2f}s | "
                            f"Fields: {', '.join(sorted(found_fields)) if found_fields else ', '.join(list(fields)[:10])}"
                        )
                    else:
                        data = resp.json()
                        header = data.get("header", {})
                        response = data.get("response", [])
                        format_fields = header.get("format", [])
                        greeks_fields = {"delta", "gamma", "theta", "vega", "rho", "implied_volatility"}
                        found_fields = greeks_fields.intersection(set(format_fields)) if format_fields else set()
                        record(
                            f"Theta Greeks ({symbol})",
                            len(found_fields) >= 3,
                            f"{len(response)} contracts in {elapsed:.2f}s | "
                            f"Fields: {', '.join(sorted(found_fields)) if found_fields else 'checking format...'} | "
                            f"Format: {format_fields[:10] if format_fields else 'N/A'}"
                        )
                else:
                    record(
                        f"Theta Greeks ({symbol})",
                        False,
                        f"Status {resp.status_code}: {resp.text[:200]}"
                    )

            except Exception as e:
                record(f"Theta Greeks ({symbol})", False, f"Error: {e}")

        elif theta_version == "v2":
            logger.info(f"  V2 Greeks test — checking snapshot endpoint for {symbol}...")
            start = time.time()
            try:
                resp = requests.get(
                    f"{THETA_BASE_URL_V2}/snapshot/option/greeks",
                    params={"root": symbol, "exp": "0", "right": "C"},
                    timeout=30,
                )
                elapsed = time.time() - start
                record(
                    f"Theta Greeks ({symbol})",
                    resp.status_code == 200,
                    f"Status {resp.status_code} in {elapsed:.2f}s | Response: {resp.text[:200]}"
                )
            except Exception as e:
                record(f"Theta Greeks ({symbol})", False, f"Error: {e}")


# =============================================================================
# Summary Report
# =============================================================================
def print_summary():
    """Print a summary of all test results."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 70)

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = len(results)

    for r in results:
        icon = "\u2705" if r["passed"] else "\u274c"
        logger.info(f"  {icon} {r['test']}")

    logger.info("-" * 70)
    logger.info(f"  Total: {total} | Passed: {passed} | Failed: {failed}")

    if failed > 0:
        logger.info("")
        logger.info("FAILED TESTS — Details:")
        for r in results:
            if not r["passed"]:
                logger.info(f"  \u274c {r['test']}: {r['detail']}")

    logger.info("")

    # Actionable next steps
    if failed == 0:
        logger.info("\U0001f389 All tests passed! Data sources are ready for model training.")
    else:
        logger.info("\u26a0\ufe0f  Some tests failed. Address the failures above before proceeding.")
        alpaca_failed = any(not r["passed"] for r in results if "Alpaca" in r["test"])
        theta_failed = any(not r["passed"] for r in results if "Theta" in r["test"])

        if alpaca_failed:
            logger.info("  \u2192 Check .env has valid ALPACA_API_KEY and ALPACA_API_SECRET")
            logger.info("  \u2192 Verify Algo Trader Plus subscription is active at https://app.alpaca.markets")
        if theta_failed:
            logger.info("  \u2192 Ensure Theta Terminal is running (java -jar ThetaTerminalv3.jar)")
            logger.info("  \u2192 Check creds.txt is in the same directory as the JAR")
            logger.info("  \u2192 Verify Options Standard subscription at https://www.thetadata.net")


# =============================================================================
# Main
# =============================================================================
def main():
    logger.info("Options Bot — Data Validation Script")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info(f"Symbols to validate: {PHASE1_SYMBOLS}")
    logger.info("")

    # Run tests in order
    alpaca_ok = test_alpaca_connection()

    if alpaca_ok:
        test_alpaca_stock_bars()
        test_alpaca_options()
    else:
        logger.warning("Skipping Alpaca data tests — connection failed")

    theta_version = test_theta_connection()

    if theta_version:
        test_theta_historical_options(theta_version)
        test_theta_greeks(theta_version)
    else:
        logger.warning("Skipping Theta data tests — no terminal detected")

    print_summary()


if __name__ == "__main__":
    main()
