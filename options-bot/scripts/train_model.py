"""
Standalone model training script.

Usage:
    cd options-bot


    # Train using an existing profile (reads config from DB):
    python scripts/train_model.py --profile-id <uuid>

    # Train with explicit parameters (no profile required):
    python scripts/train_model.py --symbol TSLA --preset swing

    # Quick test with fewer years:
    python scripts/train_model.py --symbol TSLA --preset swing --years 2

Requires:
    - .env configured with ALPACA_API_KEY
    - Database initialized (run main.py once or backend must have started)
"""

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import LOG_FORMAT, DB_PATH, PRESET_DEFAULTS

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("train_model")


def get_profile_config(profile_id: str) -> dict:
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
            return {
                "id": row["id"],
                "name": row["name"],
                "preset": row["preset"],
                "symbols": json.loads(row["symbols"]),
                "config": json.loads(row["config"]),
            }

    return asyncio.run(_load())


def main():
    parser = argparse.ArgumentParser(description="Train an XGBoost model")
    parser.add_argument("--profile-id", type=str, help="Profile UUID to train for")
    parser.add_argument("--symbol", type=str, default="TSLA", help="Ticker symbol")
    parser.add_argument("--preset", type=str, default="swing", help="Trading preset")
    parser.add_argument("--years", type=int, default=6, help="Years of history")
    parser.add_argument("--bar-timeframe", type=str, default="5min",
                        help="Bar granularity: '5min' for live, '1d' for backtest models")
    args = parser.parse_args()

    from ml.trainer import train_model

    if args.profile_id:
        # Load from database
        profile = get_profile_config(args.profile_id)
        if not profile:
            logger.error(f"Profile {args.profile_id} not found in database")
            sys.exit(1)

        logger.info(f"Training for profile: {profile['name']} ({profile['preset']})")
        symbol = profile["symbols"][0]  # Use first symbol
        preset = profile["preset"]
        horizon = profile["config"].get("prediction_horizon", "5d")
        profile_id = profile["id"]
    else:
        # Use command-line args — create a temporary profile ID
        symbol = args.symbol
        preset = args.preset
        if preset not in PRESET_DEFAULTS:
            logger.error(f"Invalid preset: {preset}. Options: {list(PRESET_DEFAULTS.keys())}")
            sys.exit(1)
        horizon = PRESET_DEFAULTS[preset]["prediction_horizon"]
        profile_id = str(uuid.uuid4())
        logger.info(f"Training with explicit params (temp profile: {profile_id})")

    result = train_model(
        profile_id=profile_id,
        symbol=symbol,
        preset=preset,
        prediction_horizon=horizon,
        years_of_data=args.years,
        bar_timeframe=args.bar_timeframe,
    )

    if result["status"] == "ready":
        logger.info("")
        logger.info("\U0001f389 Training successful!")
        logger.info(f"   Model: {result['model_path']}")
        logger.info(f"   DirAcc: {result['metrics']['dir_acc']:.4f}")
        logger.info(f"   MAE: {result['metrics']['mae']:.4f}")
    else:
        logger.error(f"Training failed: {result.get('message', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
