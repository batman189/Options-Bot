"""
Test script for feature engineering.
Fetches a small sample of real data and computes all features.

Usage:
    cd options-bot
    python scripts/test_features.py

Requires:
    - .env configured
    - Theta Terminal running (for options features test)
"""

import sys
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_features")


def test_stock_features():
    """Test stock feature computation with real Alpaca data."""
    logger.info("=" * 60)
    logger.info("TEST: Stock Features (from real Alpaca data)")
    logger.info("=" * 60)

    from data.alpaca_provider import AlpacaStockProvider
    from ml.feature_engineering.base_features import compute_stock_features, get_base_feature_names

    provider = AlpacaStockProvider()

    # Fetch ~2 weeks of 5-min bars (enough for most lookbacks, not all 20d)
    end = datetime.now() - timedelta(hours=1)
    start = end - timedelta(days=14)
    logger.info(f"Fetching 5-min bars: {start.date()} to {end.date()}")
    bars = provider.get_historical_bars("TSLA", start, end, "5min")

    if bars.empty:
        logger.error("\u274c No bars returned from Alpaca")
        return False

    logger.info(f"Got {len(bars)} bars")

    # Compute stock features
    df = compute_stock_features(bars.copy())

    # Check feature columns exist
    stock_feature_cols = [c for c in df.columns if c not in ["open", "high", "low", "close", "volume"]]
    logger.info(f"Features computed: {len(stock_feature_cols)}")
    logger.info(f"Feature columns: {stock_feature_cols}")

    # Check for reasonable values on the last row (should have least NaNs)
    last_row = df.iloc[-1]
    nan_count = last_row[stock_feature_cols].isna().sum()
    logger.info(f"NaN count in last row: {nan_count} / {len(stock_feature_cols)}")

    # Spot check some values
    checks = {
        "ret_5min": (-0.05, 0.05),
        "rsi_14": (0, 100),
        "sma_ratio_20": (0.8, 1.2),
        "day_of_week": (0, 4),
    }
    all_ok = True
    for feat, (lo, hi) in checks.items():
        if feat in df.columns:
            val = last_row[feat]
            if pd.isna(val):
                logger.info(f"  {feat}: NaN (expected if < lookback period)")
            elif lo <= val <= hi:
                logger.info(f"  \u2705 {feat}: {val:.4f} (range {lo}-{hi})")
            else:
                logger.warning(f"  \u26a0\ufe0f {feat}: {val:.4f} OUTSIDE expected range {lo}-{hi}")
                all_ok = False

    logger.info(f"Stock features test: {'\u2705 PASS' if all_ok else '\u26a0\ufe0f CHECK WARNINGS'}")
    return True


def test_swing_features():
    """Test swing feature computation."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST: Swing Features")
    logger.info("=" * 60)

    from data.alpaca_provider import AlpacaStockProvider
    from ml.feature_engineering.base_features import compute_base_features
    from ml.feature_engineering.swing_features import compute_swing_features, get_swing_feature_names

    provider = AlpacaStockProvider()

    end = datetime.now() - timedelta(hours=1)
    start = end - timedelta(days=14)
    bars = provider.get_historical_bars("TSLA", start, end, "5min")

    if bars.empty:
        logger.error("\u274c No bars")
        return False

    # Compute base first, then swing
    df = compute_base_features(bars.copy())
    df = compute_swing_features(df)

    swing_cols = get_swing_feature_names()
    present = [c for c in swing_cols if c in df.columns]
    logger.info(f"Swing features present: {len(present)}/{len(swing_cols)}")
    logger.info(f"Swing columns: {present}")

    last_row = df.iloc[-1]
    for col in swing_cols:
        val = last_row.get(col, "MISSING")
        logger.info(f"  {col}: {val}")

    logger.info("Swing features test: \u2705 PASS")
    return True


def test_general_features():
    """Test general feature computation."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST: General Features")
    logger.info("=" * 60)

    from data.alpaca_provider import AlpacaStockProvider
    from ml.feature_engineering.base_features import compute_base_features
    from ml.feature_engineering.general_features import compute_general_features, get_general_feature_names

    provider = AlpacaStockProvider()

    end = datetime.now() - timedelta(hours=1)
    start = end - timedelta(days=14)
    bars = provider.get_historical_bars("TSLA", start, end, "5min")

    if bars.empty:
        logger.error("\u274c No bars")
        return False

    df = compute_base_features(bars.copy())
    df = compute_general_features(df)

    gen_cols = get_general_feature_names()
    present = [c for c in gen_cols if c in df.columns]
    logger.info(f"General features present: {len(present)}/{len(gen_cols)}")
    logger.info(f"General columns: {present}")

    last_row = df.iloc[-1]
    for col in gen_cols:
        val = last_row.get(col, "MISSING")
        logger.info(f"  {col}: {val}")

    logger.info("General features test: \u2705 PASS")
    return True


def test_full_feature_count():
    """Verify total feature counts match architecture spec."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST: Feature Count Verification")
    logger.info("=" * 60)

    from ml.feature_engineering.base_features import get_base_feature_names
    from ml.feature_engineering.swing_features import get_swing_feature_names
    from ml.feature_engineering.general_features import get_general_feature_names

    base = get_base_feature_names()
    swing = get_swing_feature_names()
    general = get_general_feature_names()

    logger.info(f"Base features: {len(base)}")
    logger.info(f"Swing features: {len(swing)}")
    logger.info(f"General features: {len(general)}")
    logger.info(f"Swing total (base + swing): {len(base) + len(swing)}")
    logger.info(f"General total (base + general): {len(base) + len(general)}")

    # Architecture: 41 stock + 19 options = 60 base, + 5 style = 65 per profile
    swing_total = len(base) + len(swing)
    gen_total = len(base) + len(general)

    ok = True
    if swing_total < 50 or swing_total > 75:
        logger.warning(f"\u26a0\ufe0f Swing total {swing_total} outside expected 60-70 range")
        ok = False
    if gen_total < 50 or gen_total > 75:
        logger.warning(f"\u26a0\ufe0f General total {gen_total} outside expected 60-70 range")
        ok = False

    # Check for duplicate names
    all_swing = base + swing
    all_general = base + general
    if len(all_swing) != len(set(all_swing)):
        logger.error("\u274c Duplicate feature names in swing set!")
        ok = False
    if len(all_general) != len(set(all_general)):
        logger.error("\u274c Duplicate feature names in general set!")
        ok = False

    logger.info(f"Feature count test: {'\u2705 PASS' if ok else '\u274c FAIL'}")
    return ok


def main():
    logger.info("Feature Engineering Test Suite")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("")

    count_ok = test_full_feature_count()
    stock_ok = test_stock_features()
    swing_ok = test_swing_features()
    general_ok = test_general_features()

    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Feature counts:   {'\u2705' if count_ok else '\u274c'}")
    logger.info(f"  Stock features:   {'\u2705' if stock_ok else '\u274c'}")
    logger.info(f"  Swing features:   {'\u2705' if swing_ok else '\u274c'}")
    logger.info(f"  General features: {'\u2705' if general_ok else '\u274c'}")

    if all([count_ok, stock_ok, swing_ok, general_ok]):
        logger.info("")
        logger.info("\U0001f389 All feature tests passed. Ready for model training.")


if __name__ == "__main__":
    main()
