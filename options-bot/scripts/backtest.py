"""
Backtest runner for options-bot strategies.
Phase 1 Step 14 from PROJECT_ARCHITECTURE.md.

Uses Lumibot's ThetaDataBacktesting with our StrategyClass.
Requires Theta Data Terminal running at localhost:25503.

Usage:
    python scripts/backtest.py --model-path models/<file>.joblib
    python scripts/backtest.py --model-path models/<file>.joblib --start 2025-03-01 --end 2025-12-31
    python scripts/backtest.py --model-path models/<file>.joblib --symbol TSLA --budget 25000

Output:
    - Tearsheet HTML (visual performance report) in logs/
    - Trades CSV in logs/
    - Console summary with Sharpe, max drawdown, trade count
"""

import argparse
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from config import (
    LOG_FORMAT, LOG_LEVEL, PRESET_DEFAULTS,
    THETA_USERNAME, THETA_PASSWORD,
)

# Set up logging to both console AND file
logs_dir = project_root / "logs"
logs_dir.mkdir(exist_ok=True)
log_file = str(logs_dir / f"backtest_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# Console handler (INFO level)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
root_logger.addHandler(console_handler)

# File handler (DEBUG level — captures everything)
file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
root_logger.addHandler(file_handler)

logger = logging.getLogger("options-bot.backtest")
logger.info(f"Debug log file: {log_file}")


def run_backtest(
    model_path: str,
    symbol: str = "TSLA",
    preset: str = "swing",
    start_date: datetime = None,
    end_date: datetime = None,
    budget: float = 25000,
):
    """
    Run a backtest using Lumibot's ThetaDataBacktesting.

    Args:
        model_path: Path to the trained .joblib model file
        symbol: Ticker symbol
        preset: Trading preset (swing, general)
        start_date: Backtest start date
        end_date: Backtest end date
        budget: Starting portfolio value
    """
    from lumibot.backtesting import ThetaDataBacktesting

    # Select correct strategy class based on preset (H3 fix)
    if preset == "scalp":
        from strategies.scalp_strategy import ScalpStrategy as StrategyClass
    elif preset == "general":
        from strategies.general_strategy import GeneralStrategy as StrategyClass
    else:
        from strategies.swing_strategy import SwingStrategy as StrategyClass

    # Verify model exists
    if not Path(model_path).exists():
        logger.error(f"Model not found: {model_path}")
        raise FileNotFoundError(f"Model not found: {model_path}")

    # Default dates
    if start_date is None:
        start_date = datetime(2025, 1, 1)
    if end_date is None:
        end_date = datetime(2025, 12, 31)

    logger.info("=" * 60)
    logger.info("BACKTEST CONFIGURATION")
    logger.info("=" * 60)
    logger.info(f"  Symbol:     {symbol}")
    logger.info(f"  Preset:     {preset}")
    logger.info(f"  Model:      {model_path}")
    logger.info(f"  Period:     {start_date.date()} to {end_date.date()}")
    logger.info(f"  Budget:     ${budget:,.2f}")
    logger.info(f"  Sleeptime:  1D (daily iteration; 5-min features from Alpaca)")
    logger.info("=" * 60)

    # Build strategy parameters
    config = PRESET_DEFAULTS.get(preset, PRESET_DEFAULTS["swing"]).copy()
    # Use 1D for backtest iteration — features use pre-cached 5-min Alpaca bars
    config["sleeptime"] = "1D"

    parameters = {
        "profile_id": "backtest",
        "profile_name": f"BT_{symbol}_{preset}",
        "symbol": symbol,
        "preset": preset,
        "config": config,
        "model_path": str(model_path),
        "backtest_start": str(start_date.date()),
        "backtest_end": str(end_date.date()),
    }

    # Output file paths
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats_file = str(logs_dir / f"backtest_{symbol}_{preset}_{timestamp}.csv")
    tearsheet_file = str(logs_dir / f"backtest_{symbol}_{preset}_{timestamp}.html")
    trades_file = str(logs_dir / f"backtest_{symbol}_{preset}_{timestamp}_trades.csv")

    logger.info(f"  Stats file:     {stats_file}")
    logger.info(f"  Tearsheet:      {tearsheet_file}")
    logger.info(f"  Trades file:    {trades_file}")

    # Determine which backtest method to use
    has_run_backtest = hasattr(StrategyClass, 'run_backtest')
    has_backtest = hasattr(StrategyClass, 'backtest')

    logger.info(f"  API: run_backtest={has_run_backtest}, backtest={has_backtest}")

    # Resolve Theta credentials
    theta_user = THETA_USERNAME or None
    theta_pass = THETA_PASSWORD or None

    try:
        if has_run_backtest:
            logger.info("Using StrategyClass.run_backtest() ...")
            result = StrategyClass.run_backtest(
                ThetaDataBacktesting,
                backtesting_start=start_date,
                backtesting_end=end_date,
                benchmark_asset="SPY",
                parameters=parameters,
                budget=budget,
                stats_file=stats_file,
                plot_file_html=tearsheet_file,
                trades_file=trades_file,
                name=f"BT_{symbol}_{preset}",
                sleeptime="1D",
                thetadata_username=theta_user,
                thetadata_password=theta_pass,
                show_plot=False,
                show_tearsheet=False,
                save_tearsheet=True,
                tearsheet_file=tearsheet_file,
            )
        elif has_backtest:
            logger.info("Using StrategyClass.backtest() ...")
            result = StrategyClass.backtest(
                ThetaDataBacktesting,
                backtesting_start=start_date,
                backtesting_end=end_date,
                benchmark_asset="SPY",
                parameters=parameters,
                budget=budget,
                stats_file=stats_file,
                plot_file_html=tearsheet_file,
                trades_file=trades_file,
                name=f"BT_{symbol}_{preset}",
                sleeptime="1D",
                thetadata_username=theta_user,
                thetadata_password=theta_pass,
                show_plot=False,
                show_tearsheet=False,
                save_tearsheet=True,
                tearsheet_file=tearsheet_file,
            )
        else:
            raise RuntimeError("Neither run_backtest nor backtest method found on Strategy!")

    except TypeError as e:
        # If the method signature doesn't match, log the error and try alternate call
        logger.warning(f"First attempt failed with: {e}")
        logger.info("Trying alternate signature (minimal args)...")

        method = getattr(StrategyClass, 'run_backtest', None) or getattr(StrategyClass, 'backtest')
        result = method(
            ThetaDataBacktesting,
            backtesting_start=start_date,
            backtesting_end=end_date,
            benchmark_asset="SPY",
            parameters=parameters,
            budget=budget,
            name=f"BT_{symbol}_{preset}",
        )

    # Print results summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 60)

    if result is not None:
        # Lumibot returns different result formats depending on version
        if isinstance(result, dict):
            for key, value in result.items():
                logger.info(f"  {key}: {value}")
        else:
            logger.info(f"  Result type: {type(result)}")
            logger.info(f"  Result: {result}")

        # Check output files
        for f in [stats_file, tearsheet_file, trades_file]:
            if Path(f).exists():
                size = Path(f).stat().st_size
                logger.info(f"  {Path(f).name} ({size:,} bytes)")
            else:
                logger.info(f"  {Path(f).name} not created")
    else:
        logger.warning("  Backtest returned None -- check logs for errors")

    # Phase 1 success criteria check
    logger.info("")
    logger.info("PHASE 1 SUCCESS CRITERIA:")
    logger.info("  > 10 trades (1 year):    Check trades file or logs")
    logger.info("  Sharpe > 0.5:            Check tearsheet")
    logger.info("  Max drawdown < 25%:      Check tearsheet")
    logger.info("  Model dir. accuracy:     0.539 (> 0.52)")
    logger.info("")
    logger.info("Open the tearsheet HTML file in a browser for full visual report.")

    return result


def main():
    parser = argparse.ArgumentParser(description="Options Bot Backtester")
    parser.add_argument(
        "--model-path", type=str, required=True,
        help="Path to trained .joblib model file"
    )
    parser.add_argument("--symbol", type=str, default="TSLA", help="Ticker symbol")
    parser.add_argument("--preset", type=str, default="swing", help="Trading preset")
    parser.add_argument(
        "--start", type=str, default="2025-01-01",
        help="Backtest start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end", type=str, default="2025-12-31",
        help="Backtest end date (YYYY-MM-DD)"
    )
    parser.add_argument("--budget", type=float, default=25000, help="Starting budget")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")

    run_backtest(
        model_path=args.model_path,
        symbol=args.symbol,
        preset=args.preset,
        start_date=start,
        end_date=end,
        budget=args.budget,
    )


if __name__ == "__main__":
    main()
