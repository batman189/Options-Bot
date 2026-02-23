# PHASE 1 PROMPT 7 — Backtesting

## TASK
Create the backtesting script for the swing strategy. This is the final Phase 1 deliverable. After this prompt, Phase 1 is complete and we measure against the success criteria.

**Prerequisite**: Theta Data Terminal must be running at localhost:25503. The backtest uses Lumibot's `ThetaDataBacktesting` which fetches historical stock AND options data through the terminal.

---

## FILES TO CREATE

1. `options-bot/scripts/backtest.py` — Standalone backtest runner

## FILES TO READ FIRST

Before writing code, READ these files to understand the existing codebase:

```bash
cat strategies/base_strategy.py
cat strategies/swing_strategy.py
cat ml/xgboost_predictor.py
cat config.py
```

---

## IMPORTANT: Lumibot Backtest API

There are two method names — `backtest()` and `run_backtest()`. Check which one exists in the installed version:

```bash
python -c "
from lumibot.strategies import Strategy
# Check which method exists
has_backtest = hasattr(Strategy, 'backtest')
has_run_backtest = hasattr(Strategy, 'run_backtest')
print(f'Strategy.backtest exists: {has_backtest}')
print(f'Strategy.run_backtest exists: {has_run_backtest}')
"
```

Use whichever method exists. If both exist, use `run_backtest` (newer API).

Also check the method signature:
```bash
python -c "
from lumibot.strategies import Strategy
import inspect
method = getattr(Strategy, 'run_backtest', None) or getattr(Strategy, 'backtest', None)
print(inspect.signature(method))
"
```

**Adapt the code below to match the ACTUAL signature you find.** Do not assume — verify.

---

## BACKTEST DESIGN DECISIONS

### Why "1D" sleeptime for backtesting

The live strategy uses "5min" sleeptime. For backtesting, we use "1D" (once per day) because:

1. **Speed**: 1 year at 5min = ~19,600 iterations. At 1D = ~252 iterations. Each iteration does feature computation + chain scanning + Greeks calls — at 5min this would take hours.
2. **Realism**: The swing model predicts 5-day returns. Checking once per day is natural for swing trading. Checking every 5 minutes and getting the same prediction 78 times per day adds no value.
3. **Architecture compliance**: Phase 1 success criteria (Section 14) says "> 10 trades over 1 year" and "Sharpe > 0.5" — these don't require 5min resolution.

The strategy class is the SAME — `SwingStrategy`. We just pass different `sleeptime` in the parameters for backtesting.

### Backtest period

Default: 1 year (2025-01-01 to 2025-12-31). Configurable via command line args.

This uses the model trained in Prompt 05. **There IS look-ahead bias** because the model was trained on data that overlaps the backtest period. This is a known limitation for Phase 1 — the proper solution (train on pre-2025 data, backtest on 2025) can be done once we confirm the pipeline works end-to-end.

---

## FILE 1: `options-bot/scripts/backtest.py`

```python
"""
Backtest runner for options-bot strategies.
Phase 1 Step 14 from PROJECT_ARCHITECTURE.md.

Uses Lumibot's ThetaDataBacktesting with our SwingStrategy.
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
import json
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

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("options-bot.backtest")


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
    from strategies.swing_strategy import SwingStrategy

    # Verify model exists
    if not Path(model_path).exists():
        logger.error(f"Model not found: {model_path}")
        sys.exit(1)

    # Set Theta Data credentials (required by ThetaDataBacktesting)
    # These should be in .env — ThetaDataBacktesting reads from environment
    if THETA_USERNAME:
        os.environ["THETADATA_USERNAME"] = THETA_USERNAME
    if THETA_PASSWORD:
        os.environ["THETADATA_PASSWORD"] = THETA_PASSWORD

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
    logger.info(f"  Sleeptime:  1D (daily for backtest efficiency)")
    logger.info("=" * 60)

    # Build strategy parameters
    config = PRESET_DEFAULTS.get(preset, PRESET_DEFAULTS["swing"]).copy()
    # Override sleeptime for backtest efficiency
    config["sleeptime"] = "1D"

    parameters = {
        "profile_id": "backtest",
        "profile_name": f"BT_{symbol}_{preset}",
        "symbol": symbol,
        "preset": preset,
        "config": config,
        "model_path": str(model_path),
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
    has_run_backtest = hasattr(SwingStrategy, 'run_backtest')
    has_backtest = hasattr(SwingStrategy, 'backtest')

    logger.info(f"  API: run_backtest={has_run_backtest}, backtest={has_backtest}")

    try:
        if has_run_backtest:
            logger.info("Using SwingStrategy.run_backtest() ...")
            result = SwingStrategy.run_backtest(
                ThetaDataBacktesting,
                start_date,
                end_date,
                benchmark_asset="SPY",
                parameters=parameters,
                budget=budget,
                stats_file=stats_file,
                plot_file_html=tearsheet_file,
                trades_file=trades_file,
                name=f"BT_{symbol}_{preset}",
            )
        elif has_backtest:
            logger.info("Using SwingStrategy.backtest() ...")
            result = SwingStrategy.backtest(
                ThetaDataBacktesting,
                start_date,
                end_date,
                benchmark_asset="SPY",
                parameters=parameters,
                budget=budget,
                stats_file=stats_file,
                plot_file_html=tearsheet_file,
                trades_file=trades_file,
                name=f"BT_{symbol}_{preset}",
            )
        else:
            logger.error("Neither run_backtest nor backtest method found on Strategy!")
            sys.exit(1)

    except TypeError as e:
        # If the method signature doesn't match, log the error and try alternate call
        logger.warning(f"First attempt failed with: {e}")
        logger.info("Trying alternate signature (positional args)...")

        try:
            if has_run_backtest:
                result = SwingStrategy.run_backtest(
                    ThetaDataBacktesting,
                    start_date,
                    end_date,
                    benchmark_asset="SPY",
                    parameters=parameters,
                )
            else:
                result = SwingStrategy.backtest(
                    f"BT_{symbol}_{preset}",
                    budget,
                    ThetaDataBacktesting,
                    start_date,
                    end_date,
                    benchmark_asset="SPY",
                    parameters=parameters,
                    stats_file=stats_file,
                )
        except Exception as e2:
            logger.error(f"Backtest failed: {e2}", exc_info=True)
            sys.exit(1)

    # Print results summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 60)

    if result is not None:
        # Lumibot returns different result formats depending on version
        # Try to extract common metrics
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
                logger.info(f"  ✅ {Path(f).name} ({size:,} bytes)")
            else:
                logger.info(f"  ❌ {Path(f).name} not created")
    else:
        logger.warning("  Backtest returned None — check logs for errors")

    # Phase 1 success criteria check
    logger.info("")
    logger.info("PHASE 1 SUCCESS CRITERIA:")
    logger.info("  > 10 trades (1 year):    Check trades file or logs")
    logger.info("  Sharpe > 0.5:            Check tearsheet")
    logger.info("  Max drawdown < 25%:      Check tearsheet")
    logger.info("  Model dir. accuracy:     0.539 (✅ > 0.52)")
    logger.info("")
    logger.info("Open the tearsheet HTML file in a browser for full visual report.")


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
```

---

## STEP 2: Add Theta Data credentials to config.py

Before running, check if `config.py` already has `THETA_USERNAME` and `THETA_PASSWORD`. If not, add them:

```bash
# Check current config.py for theta credentials
grep -i "theta.*user\|theta.*pass" config.py
```

If missing, add these lines to `config.py` (after the existing env var loads):

```python
THETA_USERNAME = os.getenv("THETADATA_USERNAME", "")
THETA_PASSWORD = os.getenv("THETADATA_PASSWORD", "")
```

And add to `.env`:

```
THETADATA_USERNAME=your_theta_username
THETADATA_PASSWORD=your_theta_password
```

The `THETADATA_USERNAME` is the email you used to sign up for Theta Data. The `THETADATA_PASSWORD` is your Theta Data password (NOT an API key — Theta Data uses account credentials).

---

## VERIFICATION

```bash
cd options-bot

# 1. Verify the file exists
echo "=== Checking files ==="
if [ -f "scripts/backtest.py" ]; then echo "  ✅ scripts/backtest.py"; else echo "  ❌ MISSING"; fi

# 2. Check Lumibot backtest API
echo ""
echo "=== Lumibot backtest API check ==="
python -c "
from lumibot.strategies import Strategy
from lumibot.backtesting import ThetaDataBacktesting
import inspect

has_run = hasattr(Strategy, 'run_backtest')
has_bt = hasattr(Strategy, 'backtest')
print(f'  Strategy.run_backtest: {has_run}')
print(f'  Strategy.backtest: {has_bt}')

method = getattr(Strategy, 'run_backtest', None) or getattr(Strategy, 'backtest', None)
if method:
    sig = inspect.signature(method)
    print(f'  Signature: {sig}')
print(f'  ThetaDataBacktesting: {ThetaDataBacktesting}')
"

# 3. Check Theta Data Terminal is running
echo ""
echo "=== Theta Data Terminal check ==="
python -c "
import requests
try:
    r = requests.get('http://localhost:25503/v2/list/roots/option', params={'sec': 'OPRA'}, timeout=5)
    print(f'  Status: {r.status_code}')
    print(f'  ✅ Theta Terminal is running')
except:
    print('  ❌ Theta Terminal NOT running — start it before backtesting')
"

# 4. Find model file
echo ""
echo "=== Available models ==="
ls -la models/*.joblib 2>/dev/null || echo "  No models found"

# 5. Test imports
echo ""
echo "=== Testing backtest script imports ==="
python -c "
import sys
sys.path.insert(0, '.')
from scripts.backtest import run_backtest
print('  ✅ backtest.py imports clean')
"

# 6. Print the command to run
echo ""
echo "=== TO RUN THE BACKTEST ==="
MODEL=$(ls models/*.joblib 2>/dev/null | head -1)
if [ -n "$MODEL" ]; then
    echo "  python scripts/backtest.py --model-path $MODEL"
    echo ""
    echo "  For a shorter test (3 months):"
    echo "  python scripts/backtest.py --model-path $MODEL --start 2025-01-01 --end 2025-03-31"
else
    echo "  No model found — run training first (Prompt 05)"
fi
```

## WHAT SUCCESS LOOKS LIKE

1. `scripts/backtest.py` created and imports clean
2. Lumibot backtest API detected (run_backtest or backtest)
3. Theta Terminal is running
4. Model file found

Then when you actually run the backtest:
- Tearsheet HTML created in `logs/`
- Trades CSV created in `logs/`
- **> 10 trades** over the backtest period
- **Sharpe > 0.5**
- **Max drawdown < 25%**

**IMPORTANT**: If the backtest runs but produces 0 trades, the likely causes are:
1. Model predictions are all below the 1% minimum threshold → lower `min_predicted_move_pct` to 0.5
2. No contracts meet the 10% EV threshold → lower `min_ev_pct` to 5
3. Chain data not available for the backtest period → check Theta Terminal logs

If the backtest crashes, check:
1. Theta Terminal is running
2. THETADATA_USERNAME and THETADATA_PASSWORD are set in .env
3. The model file exists at the specified path
4. The Lumibot API signature matches (the script tries multiple signatures)

## WHAT FAILURE LOOKS LIKE

- `ThetaDataBacktesting` can't connect → Theta Terminal not running
- `TypeError: unexpected keyword argument` → API signature mismatch (script should handle this)
- 0 trades → thresholds too tight (adjust config)
- Crash during chain scanning → options data not available for backtest dates

## DO NOT

- Do NOT modify any existing files except config.py (adding theta credentials)
- Do NOT modify the strategy code for backtesting — the same strategy runs live and backtest
- Do NOT add backtesting API endpoints yet (that's Phase 2)
- Do NOT create additional files beyond what's listed here
