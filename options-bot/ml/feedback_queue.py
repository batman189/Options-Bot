"""
Closed-trade feedback queue for model retraining.

When a trade closes, its entry features and actual return are queued here.
The walk-forward trainer or incremental trainer consumes the queue when
enough samples accumulate (TRAINING_QUEUE_MIN_SAMPLES).

Uses synchronous sqlite3 (same pattern as _write_signal_log in base_strategy.py)
because it's called from Lumibot strategy threads.
"""
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("options-bot.ml.feedback_queue")


def enqueue_completed_sample(
    db_path: str,
    trade_id: str,
    profile_id: str,
    symbol: str,
    entry_features: Optional[dict],
    predicted_return: Optional[float],
    actual_return_pct: Optional[float],
):
    """
    Insert a completed trade into the training_queue table.
    Called from base_strategy._execute_exit() after log_trade_close().
    Non-fatal: errors are logged but never crash the trading loop.
    """
    try:
        features_json = json.dumps(entry_features) if entry_features else None
        now_str = datetime.now(timezone.utc).isoformat()

        con = sqlite3.connect(db_path)
        con.execute(
            """INSERT INTO training_queue
               (trade_id, profile_id, symbol, entry_features,
                predicted_return, actual_return_pct, queued_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                trade_id, profile_id, symbol, features_json,
                predicted_return, actual_return_pct, now_str,
            ),
        )
        con.commit()
        con.close()
        logger.info(
            "Enqueued training sample: trade=%s pnl=%.2f%%",
            trade_id[:8], actual_return_pct or 0,
        )
    except Exception as e:
        logger.error("enqueue_completed_sample failed (non-fatal): %s", e, exc_info=True)
