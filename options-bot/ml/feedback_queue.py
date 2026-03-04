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
from datetime import datetime
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
        now_str = datetime.utcnow().isoformat()

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


def get_pending_count(db_path: str, profile_id: Optional[str] = None) -> int:
    """
    Count unconsumed samples in the training queue.
    If profile_id is given, count only that profile's samples.
    """
    try:
        con = sqlite3.connect(db_path)
        if profile_id:
            cursor = con.execute(
                "SELECT COUNT(*) FROM training_queue WHERE consumed = 0 AND profile_id = ?",
                (profile_id,),
            )
        else:
            cursor = con.execute(
                "SELECT COUNT(*) FROM training_queue WHERE consumed = 0"
            )
        count = cursor.fetchone()[0]
        con.close()
        return count
    except Exception as e:
        logger.error("get_pending_count failed: %s", e)
        return 0


def consume_queue(
    db_path: str,
    profile_id: Optional[str] = None,
    limit: int = 1000,
) -> list[dict]:
    """
    Consume (mark as consumed) pending samples and return them.
    Each row is returned as a dict with keys:
        trade_id, profile_id, symbol, entry_features, predicted_return,
        actual_return_pct, queued_at
    """
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row

        if profile_id:
            cursor = con.execute(
                """SELECT id, trade_id, profile_id, symbol, entry_features,
                          predicted_return, actual_return_pct, queued_at
                   FROM training_queue
                   WHERE consumed = 0 AND profile_id = ?
                   ORDER BY queued_at ASC
                   LIMIT ?""",
                (profile_id, limit),
            )
        else:
            cursor = con.execute(
                """SELECT id, trade_id, profile_id, symbol, entry_features,
                          predicted_return, actual_return_pct, queued_at
                   FROM training_queue
                   WHERE consumed = 0
                   ORDER BY queued_at ASC
                   LIMIT ?""",
                (limit,),
            )

        rows = cursor.fetchall()
        if not rows:
            con.close()
            return []

        results = []
        row_ids = []
        for row in rows:
            row_ids.append(row["id"])
            features = None
            if row["entry_features"]:
                try:
                    features = json.loads(row["entry_features"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append({
                "trade_id": row["trade_id"],
                "profile_id": row["profile_id"],
                "symbol": row["symbol"],
                "entry_features": features,
                "predicted_return": row["predicted_return"],
                "actual_return_pct": row["actual_return_pct"],
                "queued_at": row["queued_at"],
            })

        # Mark as consumed
        now_str = datetime.utcnow().isoformat()
        placeholders = ",".join("?" * len(row_ids))
        con.execute(
            f"UPDATE training_queue SET consumed = 1, consumed_at = ? WHERE id IN ({placeholders})",
            [now_str] + row_ids,
        )
        con.commit()
        con.close()

        logger.info("Consumed %d training queue samples", len(results))
        return results

    except Exception as e:
        logger.error("consume_queue failed: %s", e, exc_info=True)
        return []
