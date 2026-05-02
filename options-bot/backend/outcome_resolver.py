"""Periodic outcome resolver — runs as a daemon thread spawned by
FastAPI's lifespan startup. On each tick, calls
learning.outcome_tracker.resolve_pending_outcomes to evaluate
ripe pending outcomes and mark expired ones.

Mirrors the watchdog pattern at backend/routes/trading.py:381-402:
  - threading.Thread, daemon=True
  - module-level _resolver_running bool flag for shutdown
  - sleep in 1s chunks so cancellation is responsive
  - idempotent start/stop

The resolver is `async def` but C5c runs it in a thread via
asyncio.run(). Each tick gets a fresh ephemeral event loop. The
resolver's sync sqlite3 body and sync UnifiedDataClient calls
thus never block any FastAPI event loop.

Failure handling:
  - UnifiedDataClient health check failure at startup → log warning,
    do not start thread (graceful degradation; outcomes accumulate
    until next restart with a healthy client)
  - Per-tick exception → log error with traceback, continue loop
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

import config
from data.unified_client import UnifiedDataClient
from learning.outcome_tracker import resolve_pending_outcomes

logger = logging.getLogger("backend.outcome_resolver")


_resolver_running: bool = False
_resolver_thread: Optional[threading.Thread] = None
_resolver_client: Optional[UnifiedDataClient] = None


def _resolver_loop():
    """Main loop body. Runs in the daemon thread."""
    global _resolver_running, _resolver_client
    interval = config.OUTCOME_RESOLVER_INTERVAL_SECONDS
    while _resolver_running:
        try:
            result = asyncio.run(
                resolve_pending_outcomes(_resolver_client)
            )
            logger.info(
                "outcome resolver tick: evaluated=%s expired=%s "
                "still_pending=%s",
                result.get("evaluated", 0),
                result.get("expired", 0),
                result.get("still_pending", 0),
            )
        except Exception as e:
            logger.error(
                "outcome resolver tick failed: %s",
                e, exc_info=True,
            )

        # Sleep in 1s chunks so shutdown is responsive
        for _ in range(interval):
            if not _resolver_running:
                break
            time.sleep(1)


def start_outcome_resolver_loop() -> bool:
    """Start the outcome resolver thread. Idempotent.

    Returns True if the thread was started (or already running).
    Returns False if UnifiedDataClient health check failed and
    the thread will not start (graceful degradation).
    """
    global _resolver_running, _resolver_thread, _resolver_client
    if _resolver_running:
        logger.debug("outcome resolver already running")
        return True

    try:
        _resolver_client = UnifiedDataClient()
        _resolver_client.health_check()
    except Exception as e:
        logger.warning(
            "outcome resolver: UnifiedDataClient construction "
            "failed (%s) — resolver will not run for this "
            "lifespan; pending outcomes will accumulate until "
            "next restart with healthy client", e,
        )
        _resolver_client = None
        return False

    _resolver_running = True
    _resolver_thread = threading.Thread(
        target=_resolver_loop,
        daemon=True,
        name="outcome-resolver",
    )
    _resolver_thread.start()
    logger.info(
        "outcome resolver thread started (interval=%ss)",
        config.OUTCOME_RESOLVER_INTERVAL_SECONDS,
    )
    return True


def stop_outcome_resolver_loop():
    """Signal the outcome resolver thread to stop. Idempotent."""
    global _resolver_running
    if not _resolver_running:
        logger.debug("outcome resolver not running")
        return
    _resolver_running = False
    logger.info("outcome resolver stop requested")
