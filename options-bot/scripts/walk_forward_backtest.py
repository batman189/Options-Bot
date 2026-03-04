"""
Walk-forward backtest orchestrator.

Splits the backtest period into multiple windows, trains a fresh model on each
training slice, then tests on the subsequent out-of-sample slice.

This avoids look-ahead bias — the model is always tested on data it has never seen.

Usage:
    python scripts/walk_forward_backtest.py \\
        --profile-id <uuid> \\
        --symbol TSLA \\
        --preset swing \\
        --start 2023-01-01 \\
        --end 2025-12-31 \\
        --windows 5 \\
        --train-pct 0.70

Output:
    Per-window metrics table (console + CSV in logs/)
"""

import argparse
import logging
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from config import LOG_FORMAT, PRESET_DEFAULTS

# Logging
logs_dir = project_root / "logs"
logs_dir.mkdir(exist_ok=True)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
root_logger.addHandler(console_handler)

logger = logging.getLogger("options-bot.walk_forward")


def run_walk_forward(
    profile_id: str,
    symbol: str,
    preset: str,
    start_date: datetime,
    end_date: datetime,
    num_windows: int = 5,
    train_pct: float = 0.70,
    budget: float = 25000,
    prediction_horizon: str = "7d",
    years_of_data: int = 6,
):
    """
    Walk-forward backtest: train on slice, test on next slice, repeat.

    Args:
        profile_id:         Profile UUID (for model storage)
        symbol:             Ticker symbol
        preset:             Trading preset (swing, general)
        start_date:         Overall backtest start
        end_date:           Overall backtest end
        num_windows:        Number of walk-forward windows
        train_pct:          Fraction of each window used for training (rest = test)
        budget:             Starting portfolio value per window
        prediction_horizon: Model prediction horizon (e.g., "7d")
        years_of_data:      Years of training data to use
    """
    total_days = (end_date - start_date).days
    window_days = total_days // num_windows
    train_days = int(window_days * train_pct)
    test_days = window_days - train_days

    logger.info("=" * 70)
    logger.info("WALK-FORWARD BACKTEST")
    logger.info("=" * 70)
    logger.info(f"  Symbol:           {symbol}")
    logger.info(f"  Preset:           {preset}")
    logger.info(f"  Period:           {start_date.date()} to {end_date.date()} ({total_days} days)")
    logger.info(f"  Windows:          {num_windows}")
    logger.info(f"  Train/Test split: {train_pct:.0%} / {1-train_pct:.0%}")
    logger.info(f"  Per window:       {train_days}d train + {test_days}d test")
    logger.info("=" * 70)

    results = []

    for i in range(num_windows):
        window_start = start_date + timedelta(days=i * window_days)
        train_end = window_start + timedelta(days=train_days)
        test_start = train_end
        test_end = window_start + timedelta(days=window_days)

        # Don't exceed overall end date
        if test_end > end_date:
            test_end = end_date

        logger.info(f"\n{'='*70}")
        logger.info(f"WINDOW {i+1}/{num_windows}")
        logger.info(f"  Train: {window_start.date()} to {train_end.date()}")
        logger.info(f"  Test:  {test_start.date()} to {test_end.date()}")
        logger.info(f"{'='*70}")

        window_result = {
            "window": i + 1,
            "train_start": str(window_start.date()),
            "train_end": str(train_end.date()),
            "test_start": str(test_start.date()),
            "test_end": str(test_end.date()),
            "model_path": None,
            "total_trades": 0,
            "win_rate": None,
            "total_return_pct": None,
            "sharpe_ratio": None,
            "max_drawdown_pct": None,
            "status": "pending",
        }

        # Step 1: Train model on the training slice
        try:
            model_path = _train_window(
                profile_id=profile_id,
                symbol=symbol,
                preset=preset,
                prediction_horizon=prediction_horizon,
                years_of_data=years_of_data,
            )
            window_result["model_path"] = model_path
            logger.info(f"  Model trained: {model_path}")
        except Exception as e:
            logger.error(f"  Training failed for window {i+1}: {e}", exc_info=True)
            window_result["status"] = "train_failed"
            results.append(window_result)
            continue

        # Step 2: Backtest on the test slice
        try:
            bt_result = _backtest_window(
                model_path=model_path,
                symbol=symbol,
                preset=preset,
                start_date=test_start,
                end_date=test_end,
                budget=budget,
            )
            window_result.update(bt_result)
            window_result["status"] = "completed"
        except Exception as e:
            logger.error(f"  Backtest failed for window {i+1}: {e}", exc_info=True)
            window_result["status"] = "backtest_failed"

        results.append(window_result)

    # Print summary table
    _print_summary(results)

    # Save to CSV
    _save_results_csv(results, symbol, preset)

    return results


def _train_window(
    profile_id: str,
    symbol: str,
    preset: str,
    prediction_horizon: str,
    years_of_data: int,
) -> str:
    """
    Train a model for one walk-forward window.
    Returns the model file path.
    """
    from ml.trainer import train_model

    result = train_model(
        profile_id=profile_id,
        symbol=symbol,
        preset=preset,
        prediction_horizon=prediction_horizon,
        years_of_data=years_of_data,
    )

    if result and result.get("model_path"):
        return result["model_path"]
    raise RuntimeError(f"Training returned no model path: {result}")


def _backtest_window(
    model_path: str,
    symbol: str,
    preset: str,
    start_date: datetime,
    end_date: datetime,
    budget: float,
) -> dict:
    """
    Run a backtest for one walk-forward window.
    Returns dict with total_trades, win_rate, total_return_pct, sharpe_ratio, max_drawdown_pct.
    """
    from scripts.backtest import run_backtest

    result = run_backtest(
        model_path=model_path,
        symbol=symbol,
        preset=preset,
        start_date=start_date,
        end_date=end_date,
        budget=budget,
    )

    # Extract metrics from Lumibot result
    metrics = {}
    if result and hasattr(result, "_strategy"):
        strat = result._strategy
        tracker = getattr(strat, "_strategy_tracker", None)
        if tracker:
            metrics["total_trades"] = getattr(tracker, "total_trades", 0)
            metrics["total_return_pct"] = getattr(tracker, "total_return", None)
            metrics["sharpe_ratio"] = getattr(tracker, "sharpe_ratio", None)
            metrics["max_drawdown_pct"] = getattr(tracker, "max_drawdown", None)
            metrics["win_rate"] = getattr(tracker, "win_rate", None)

    return metrics


def _print_summary(results: list[dict]):
    """Print a formatted summary table."""
    logger.info("\n" + "=" * 90)
    logger.info("WALK-FORWARD RESULTS SUMMARY")
    logger.info("=" * 90)

    header = f"{'Win':>4} | {'Train Period':>23} | {'Test Period':>23} | {'Trades':>6} | {'Win%':>6} | {'Return':>8} | {'Sharpe':>7} | {'Status':>12}"
    logger.info(header)
    logger.info("-" * 90)

    for r in results:
        trades = r.get("total_trades", 0)
        win_rate = f"{r['win_rate']*100:.1f}%" if r.get("win_rate") is not None else "—"
        ret = f"{r['total_return_pct']:.1f}%" if r.get("total_return_pct") is not None else "—"
        sharpe = f"{r['sharpe_ratio']:.2f}" if r.get("sharpe_ratio") is not None else "—"

        line = (
            f"{r['window']:>4} | "
            f"{r['train_start']} → {r['train_end']} | "
            f"{r['test_start']} → {r['test_end']} | "
            f"{trades:>6} | {win_rate:>6} | {ret:>8} | {sharpe:>7} | {r['status']:>12}"
        )
        logger.info(line)

    logger.info("=" * 90)


def _save_results_csv(results: list[dict], symbol: str, preset: str):
    """Save results to a CSV file."""
    import csv
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = logs_dir / f"walk_forward_{symbol}_{preset}_{timestamp}.csv"

    fieldnames = [
        "window", "train_start", "train_end", "test_start", "test_end",
        "total_trades", "win_rate", "total_return_pct", "sharpe_ratio",
        "max_drawdown_pct", "status",
    ]

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    logger.info(f"Results saved to {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Walk-forward backtest orchestrator")
    parser.add_argument("--profile-id", required=True, help="Profile UUID")
    parser.add_argument("--symbol", default="TSLA", help="Ticker symbol")
    parser.add_argument("--preset", default="swing", choices=list(PRESET_DEFAULTS.keys()))
    parser.add_argument("--start", required=True, help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--windows", type=int, default=5, help="Number of walk-forward windows")
    parser.add_argument("--train-pct", type=float, default=0.70, help="Training data fraction (0-1)")
    parser.add_argument("--budget", type=float, default=25000, help="Starting budget per window")
    parser.add_argument("--prediction-horizon", default="7d", help="Model prediction horizon")
    parser.add_argument("--years-of-data", type=int, default=6, help="Years of training data")

    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")

    run_walk_forward(
        profile_id=args.profile_id,
        symbol=args.symbol,
        preset=args.preset,
        start_date=start,
        end_date=end,
        num_windows=args.windows,
        train_pct=args.train_pct,
        budget=args.budget,
        prediction_horizon=args.prediction_horizon,
        years_of_data=args.years_of_data,
    )


if __name__ == "__main__":
    main()
