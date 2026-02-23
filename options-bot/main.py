"""
Options Bot entry point.
Starts the FastAPI backend and optionally launches a trading strategy.

Usage:
    # Start backend only:
    python main.py

    # Start backend + paper trading:
    python main.py --trade --profile-id <uuid>

    # Quick test with TSLA swing (no profile required):
    python main.py --trade --symbol TSLA --preset swing --model-path models/<file>.joblib
"""

import argparse
import json
import logging
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import LOG_FORMAT, LOG_LEVEL, DB_PATH, PRESET_DEFAULTS

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("options-bot.main")


def start_backend():
    """Start the FastAPI backend in a background thread."""
    import uvicorn
    from backend.app import app

    def _run():
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info("FastAPI backend started at http://localhost:8000")
    return thread


def load_profile_from_db(profile_id: str) -> dict:
    """Load profile config from database."""
    import aiosqlite
    import asyncio

    async def _load():
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM profiles WHERE id = ?", (profile_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None

            # Also load model path
            model_path = None
            if row["model_id"]:
                cursor2 = await db.execute(
                    "SELECT file_path FROM models WHERE id = ?",
                    (row["model_id"],),
                )
                mrow = await cursor2.fetchone()
                if mrow:
                    model_path = mrow["file_path"]

            return {
                "profile_id": row["id"],
                "profile_name": row["name"],
                "symbol": json.loads(row["symbols"])[0],
                "preset": row["preset"],
                "config": json.loads(row["config"]),
                "model_path": model_path,
            }

    return asyncio.run(_load())


def start_trading(params: dict):
    """Launch a Lumibot strategy for paper trading."""
    from lumibot.brokers import Alpaca
    from lumibot.traders import Trader
    from config import ALPACA_API_KEY, ALPACA_API_SECRET

    logger.info(f"Starting paper trading: {params.get('profile_name', 'Manual')}")

    broker = Alpaca({
        "API_KEY": ALPACA_API_KEY,
        "API_SECRET": ALPACA_API_SECRET,
        "PAPER": True,
    })

    preset = params.get("preset", "swing")
    if preset == "swing":
        from strategies.swing_strategy import SwingStrategy
        strategy_class = SwingStrategy
    elif preset == "general":
        # GeneralStrategy not yet created — use base for now
        from strategies.base_strategy import BaseOptionsStrategy
        strategy_class = BaseOptionsStrategy
    else:
        from strategies.base_strategy import BaseOptionsStrategy
        strategy_class = BaseOptionsStrategy

    strategy = strategy_class(
        broker=broker,
        name=params.get("profile_name", f"{preset}_{params.get('symbol', 'TSLA')}"),
        parameters=params,
    )

    trader = Trader()
    trader.add_strategy(strategy)

    logger.info("Launching Lumibot trader...")
    trader.run_all()


def main():
    parser = argparse.ArgumentParser(description="Options Bot")
    parser.add_argument("--trade", action="store_true", help="Start paper trading")
    parser.add_argument("--profile-id", type=str, help="Profile UUID to trade")
    parser.add_argument("--symbol", type=str, default="TSLA", help="Ticker symbol")
    parser.add_argument("--preset", type=str, default="swing", help="Trading preset")
    parser.add_argument("--model-path", type=str, help="Path to model .joblib file")
    parser.add_argument("--no-backend", action="store_true", help="Skip starting FastAPI")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OPTIONS BOT STARTING")
    logger.info("=" * 60)

    # Start backend unless disabled
    if not args.no_backend:
        start_backend()

    if args.trade:
        if args.profile_id:
            # Load from database
            params = load_profile_from_db(args.profile_id)
            if not params:
                logger.error(f"Profile {args.profile_id} not found")
                sys.exit(1)
            if not params.get("model_path"):
                logger.error("Profile has no trained model. Run training first.")
                sys.exit(1)
        else:
            # Manual params
            if not args.model_path:
                logger.error("--model-path required when not using --profile-id")
                sys.exit(1)
            preset = args.preset
            if preset not in PRESET_DEFAULTS:
                logger.error(f"Invalid preset: {preset}")
                sys.exit(1)
            params = {
                "profile_id": "manual",
                "profile_name": f"{args.symbol} {preset.title()}",
                "symbol": args.symbol,
                "preset": preset,
                "config": PRESET_DEFAULTS[preset],
                "model_path": args.model_path,
            }

        start_trading(params)
    else:
        logger.info("Backend-only mode. Use --trade to start paper trading.")
        logger.info("Swagger docs: http://localhost:8000/docs")
        # Keep main thread alive
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down...")


if __name__ == "__main__":
    main()
