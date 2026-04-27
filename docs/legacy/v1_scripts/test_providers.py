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
    logger.info(f"Connection: {'\u2705 PASS' if connected else '\u274c FAIL'}")
    if not connected:
        return False

    # Test latest price
    price = provider.get_latest_price("TSLA")
    logger.info(
        f"Latest price: {'\u2705 PASS' if price else '\u274c FAIL'} "
        f"(TSLA: ${price:.2f})" if price else "Latest price: \u274c FAIL"
    )

    # Test recent 5-min bars (small request)
    logger.info("Fetching 1 day of 5-min bars...")
    end = datetime.now()
    start = end - timedelta(days=3)  # 3 days to account for weekends
    df = provider.get_historical_bars("TSLA", start, end, "5min")
    logger.info(
        f"Recent bars: {'\u2705 PASS' if len(df) > 0 else '\u274c FAIL'} "
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
        f"Historical bars (2020): {'\u2705 PASS' if len(df_hist) > 0 else '\u274c FAIL'} "
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
    logger.info(f"Connection: {'\u2705 PASS' if connected else '\u274c FAIL'}")
    if not connected:
        return False

    # Test expirations
    expirations = provider.get_expirations("TSLA")
    logger.info(
        f"Expirations: {'\u2705 PASS' if len(expirations) > 0 else '\u274c FAIL'} "
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
            f"{'\u2705 PASS' if len(strikes) > 0 else '\u274c FAIL'} "
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
                f"{'\u2705 PASS' if greeks else '\u274c FAIL'}"
            )
            if greeks:
                logger.info(f"  {greeks}")

            # Test bulk Greeks EOD
            bulk_df = provider.get_bulk_greeks_eod("TSLA", test_exp, test_date)
            logger.info(
                f"Bulk Greeks (exp={test_exp}, date={test_date}): "
                f"{'\u2705 PASS' if len(bulk_df) > 0 else '\u274c FAIL'} "
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
    logger.info(f"  Alpaca Provider: {'\u2705 PASS' if alpaca_ok else '\u274c FAIL'}")
    logger.info(f"  Theta Provider:  {'\u2705 PASS' if theta_ok else '\u274c FAIL'}")

    if alpaca_ok and theta_ok:
        logger.info("")
        logger.info("\U0001f389 Both providers working. Ready for feature engineering.")
    else:
        logger.info("")
        logger.info("\u26a0\ufe0f  Fix failures above before proceeding.")


if __name__ == "__main__":
    main()
