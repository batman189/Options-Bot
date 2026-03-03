"""
Options Bot entry point.
Starts the FastAPI backend and optionally launches trading strategies.

Usage:
    # Start backend only:
    python main.py

    # Start backend + paper trading (single profile from DB):
    python main.py --trade --profile-id <uuid>

    # Start backend + paper trading (multiple profiles simultaneously):
    python main.py --trade --profile-ids <uuid1> <uuid2> <uuid3>

    # Quick manual test (no DB profile required):
    python main.py --trade --symbol TSLA --preset swing --model-path models/<file>.joblib

    # Start without backend:
    python main.py --trade --symbol TSLA --preset swing --model-path models/<file>.joblib --no-backend
"""

import argparse
import json
import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import LOG_FORMAT, LOG_LEVEL, DB_PATH, LOGS_DIR, PRESET_DEFAULTS

# ---------------------------------------------------------------------------
# Logging setup: console + file (mirrors backtest.py pattern)
# ---------------------------------------------------------------------------
LOGS_DIR.mkdir(exist_ok=True)
_log_file = str(
    LOGS_DIR / f"live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# Console handler (INFO level)
_console_handler = logging.StreamHandler()
_console_handler.setLevel(LOG_LEVEL)
_console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
root_logger.addHandler(_console_handler)

# File handler (DEBUG level — captures everything)
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
root_logger.addHandler(_file_handler)

# Database handler — writes WARNING and ERROR entries to training_logs table
# so the System UI error panel can display them.
from backend.db_log_handler import DatabaseLogHandler
_db_handler = DatabaseLogHandler(str(DB_PATH))
_db_handler.setLevel(logging.WARNING)
_db_handler.setFormatter(logging.Formatter(LOG_FORMAT))
root_logger.addHandler(_db_handler)

logger = logging.getLogger("options-bot.main")
logger.info(f"Log file: {_log_file}")


def _kill_existing_on_port(port: int):
    """Kill any existing process listening on the given port (Windows only)."""
    import subprocess
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                if pid > 0:
                    logger.info(f"Killing existing process on port {port} (PID {pid})")
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True, timeout=5)
                    time.sleep(1)
                    break
    except Exception as e:
        logger.warning(f"Could not check/kill existing port {port} process: {e}")


def start_backend():
    """Start the FastAPI backend in a background thread."""
    logger.info("start_backend: starting FastAPI in background thread")
    try:
        import uvicorn
        from backend.app import app

        # Kill any leftover backend from a previous run
        _kill_existing_on_port(8000)

        def _run():
            logger.info("start_backend: uvicorn starting on port 8000")
            uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        # Give backend a moment to start before trading begins
        time.sleep(2)
        logger.info("FastAPI backend started at http://localhost:8000")
        logger.info("Swagger docs at http://localhost:8000/docs")
        return thread
    except Exception as e:
        logger.error(f"start_backend: failed to start backend: {e}", exc_info=True)
        return None


def load_profile_from_db(profile_id: str) -> dict:
    """
    Load a single profile's trading parameters from the database.

    Returns a dict suitable for passing as `parameters` to a strategy class,
    or None if the profile is not found.
    """
    logger.info(f"load_profile_from_db: loading profile {profile_id}")
    import aiosqlite
    import asyncio

    async def _load():
        try:
            async with aiosqlite.connect(str(DB_PATH)) as db:
                db.row_factory = aiosqlite.Row

                cursor = await db.execute(
                    "SELECT * FROM profiles WHERE id = ?", (profile_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    logger.error(f"load_profile_from_db: profile {profile_id} not found")
                    return None

                # Load model path from models table
                model_path = None
                if row["model_id"]:
                    cursor2 = await db.execute(
                        "SELECT file_path FROM models WHERE id = ?",
                        (row["model_id"],),
                    )
                    mrow = await cursor2.fetchone()
                    if mrow:
                        model_path = mrow["file_path"]
                        logger.info(
                            f"load_profile_from_db: model path = {model_path}"
                        )
                    else:
                        logger.warning(
                            f"load_profile_from_db: model_id set but no model row found"
                        )

                symbols = json.loads(row["symbols"])
                symbol = symbols[0] if symbols else "TSLA"

                params = {
                    "profile_id": row["id"],
                    "profile_name": row["name"],
                    "symbol": symbol,
                    "preset": row["preset"],
                    "config": json.loads(row["config"]),
                    "model_path": model_path,
                }
                logger.info(
                    f"load_profile_from_db: loaded '{row['name']}' "
                    f"preset={row['preset']} symbol={symbol} "
                    f"model={'yes' if model_path else 'NONE'}"
                )
                return params
        except Exception as e:
            logger.error(
                f"load_profile_from_db: error loading {profile_id}: {e}",
                exc_info=True,
            )
            return None

    try:
        return asyncio.run(_load())
    except Exception as e:
        logger.error(
            f"load_profile_from_db: asyncio.run failed: {e}", exc_info=True
        )
        return None


def _get_strategy_class(preset: str):
    """
    Return the correct strategy class for the given preset.
    All presets map to named subclasses of BaseOptionsStrategy.
    """
    logger.info(f"_get_strategy_class: preset={preset}")
    if preset == "swing":
        from strategies.swing_strategy import SwingStrategy
        return SwingStrategy
    elif preset == "general":
        from strategies.general_strategy import GeneralStrategy
        return GeneralStrategy
    elif preset == "scalp":
        from strategies.scalp_strategy import ScalpStrategy
        return ScalpStrategy
    else:
        logger.warning(
            f"_get_strategy_class: unknown preset '{preset}', "
            f"falling back to BaseOptionsStrategy"
        )
        from strategies.base_strategy import BaseOptionsStrategy
        return BaseOptionsStrategy


def start_trading_single(params: dict):
    """
    Launch a single Lumibot strategy for paper trading.
    Used by --profile-id and --symbol/--preset/--model-path paths.
    Blocks until the strategy is stopped.
    """
    logger.info(
        f"start_trading_single: launching "
        f"profile='{params.get('profile_name', 'Manual')}' "
        f"preset={params.get('preset')} symbol={params.get('symbol')}"
    )
    try:
        from lumibot.brokers import Alpaca
        from lumibot.traders import Trader
        from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER

        broker = Alpaca({
            "API_KEY": ALPACA_API_KEY,
            "API_SECRET": ALPACA_API_SECRET,
            "PAPER": ALPACA_PAPER,
        })

        strategy_class = _get_strategy_class(params.get("preset", "swing"))
        strategy_name = params.get(
            "profile_name",
            f"{params.get('preset', 'swing')}_{params.get('symbol', 'TSLA')}",
        )

        logger.info(
            f"start_trading_single: creating {strategy_class.__name__} "
            f"named '{strategy_name}'"
        )
        strategy = strategy_class(
            broker=broker,
            name=strategy_name,
            parameters=params,
        )

        trader = Trader()
        trader.add_strategy(strategy)

        logger.info("start_trading_single: calling trader.run_all()")
        trader.run_all()

    except Exception as e:
        logger.error(f"start_trading_single: failed: {e}", exc_info=True)
        raise


def start_trading_multi(all_params: list):
    """
    Launch multiple Lumibot strategies simultaneously using one Trader instance.
    Each profile gets its own strategy instance added to the same Trader.
    Trader.run_all() runs them concurrently in separate threads.

    Architecture Section 4: One Lumibot Strategy instance per active profile.
    Architecture Section 13 Phase 2: Multiple simultaneous strategies via Trader class.

    Args:
        all_params: List of parameter dicts, one per profile.
    """
    logger.info(
        f"start_trading_multi: launching {len(all_params)} strategies simultaneously"
    )
    try:
        from lumibot.brokers import Alpaca
        from lumibot.traders import Trader
        from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER

        broker = Alpaca({
            "API_KEY": ALPACA_API_KEY,
            "API_SECRET": ALPACA_API_SECRET,
            "PAPER": ALPACA_PAPER,
        })

        trader = Trader()

        for i, params in enumerate(all_params):
            try:
                strategy_class = _get_strategy_class(params.get("preset", "swing"))
                strategy_name = params.get(
                    "profile_name",
                    f"{params.get('preset', 'swing')}_{params.get('symbol', 'TSLA')}",
                )

                logger.info(
                    f"start_trading_multi: adding strategy {i+1}/{len(all_params)} — "
                    f"{strategy_class.__name__} named '{strategy_name}' "
                    f"symbol={params.get('symbol')}"
                )
                strategy = strategy_class(
                    broker=broker,
                    name=strategy_name,
                    parameters=params,
                )
                trader.add_strategy(strategy)
                logger.info(
                    f"start_trading_multi: strategy {i+1} added successfully"
                )
            except Exception as e:
                logger.error(
                    f"start_trading_multi: failed to create strategy {i+1} "
                    f"(profile={params.get('profile_name', 'unknown')}): {e}",
                    exc_info=True,
                )
                # Continue adding other strategies even if one fails
                continue

        logger.info("start_trading_multi: calling trader.run_all()")
        trader.run_all()

    except Exception as e:
        logger.error(f"start_trading_multi: failed: {e}", exc_info=True)
        raise


def main():
    parser = argparse.ArgumentParser(description="Options Bot")
    parser.add_argument(
        "--trade", action="store_true",
        help="Start paper trading",
    )
    parser.add_argument(
        "--profile-id", type=str,
        help="Single profile UUID to trade (loads from DB)",
    )
    parser.add_argument(
        "--profile-ids", type=str, nargs="+",
        help="One or more profile UUIDs to trade simultaneously (loads each from DB)",
    )
    parser.add_argument(
        "--symbol", type=str, default="TSLA",
        help="Ticker symbol (manual mode only — no DB profile)",
    )
    parser.add_argument(
        "--preset", type=str, default="swing",
        help="Trading preset: swing or general (manual mode only)",
    )
    parser.add_argument(
        "--model-path", type=str,
        help="Path to .joblib model file (manual mode only)",
    )
    parser.add_argument(
        "--no-backend", action="store_true",
        help="Skip starting the FastAPI backend",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OPTIONS BOT STARTING")
    logger.info("=" * 60)
    logger.info(f"  --trade: {args.trade}")
    logger.info(f"  --profile-id: {args.profile_id}")
    logger.info(f"  --profile-ids: {args.profile_ids}")
    logger.info(f"  --symbol: {args.symbol}")
    logger.info(f"  --preset: {args.preset}")
    logger.info(f"  --model-path: {args.model_path}")
    logger.info(f"  --no-backend: {args.no_backend}")

    # Start backend unless disabled
    if not args.no_backend:
        start_backend()

    if not args.trade:
        logger.info("No --trade flag — running backend only. Use Swagger at http://localhost:8000/docs")
        # Keep process alive for backend-only mode
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down.")
        return

    # -------------------------------------------------------------------------
    # MULTI-PROFILE MODE: --profile-ids uuid1 uuid2 ...
    # -------------------------------------------------------------------------
    if args.profile_ids:
        logger.info(
            f"Multi-profile mode: loading {len(args.profile_ids)} profiles from DB"
        )
        all_params = []
        for pid in args.profile_ids:
            logger.info(f"  Loading profile: {pid}")
            params = load_profile_from_db(pid)
            if not params:
                logger.error(
                    f"  Profile {pid} not found in database — skipping"
                )
                continue
            if not params.get("model_path"):
                logger.warning(
                    f"  Profile '{params.get('profile_name', pid)}' has no trained model — "
                    f"it will run but skip all entries"
                )
            all_params.append(params)

        if not all_params:
            logger.error("No valid profiles loaded — nothing to trade. Exiting.")
            sys.exit(1)

        logger.info(
            f"Launching {len(all_params)} strategies: "
            + ", ".join(p.get("profile_name", "unnamed") for p in all_params)
        )
        start_trading_multi(all_params)
        return

    # -------------------------------------------------------------------------
    # SINGLE PROFILE MODE: --profile-id uuid
    # -------------------------------------------------------------------------
    if args.profile_id:
        logger.info(f"Single profile mode: loading profile {args.profile_id} from DB")
        params = load_profile_from_db(args.profile_id)
        if not params:
            logger.error(f"Profile {args.profile_id} not found in database")
            sys.exit(1)
        if not params.get("model_path"):
            logger.warning(
                f"Profile '{params.get('profile_name')}' has no trained model — "
                f"bot will run but skip all entries"
            )
        start_trading_single(params)
        return

    # -------------------------------------------------------------------------
    # MANUAL MODE: --symbol --preset --model-path (no DB required)
    # -------------------------------------------------------------------------
    logger.info("Manual mode: using --symbol/--preset/--model-path directly")
    preset = args.preset
    if preset not in PRESET_DEFAULTS:
        logger.error(
            f"Unknown preset '{preset}'. Must be one of: {list(PRESET_DEFAULTS.keys())}"
        )
        sys.exit(1)

    config = dict(PRESET_DEFAULTS[preset])

    params = {
        "profile_id": "manual",
        "profile_name": f"Manual_{preset}_{args.symbol}",
        "symbol": args.symbol,
        "preset": preset,
        "config": config,
        "model_path": args.model_path,
    }

    if not args.model_path:
        logger.warning(
            "No --model-path provided — bot will run but skip all entries"
        )

    start_trading_single(params)


if __name__ == "__main__":
    main()
