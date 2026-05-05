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
  - FIX-2: UnifiedDataClient health check failure at startup spawns
    the thread anyway in a "waiting" state (_resolver_client=None).
    Each tick retries client initialization via
    _try_initialize_client; first successful reconnect promotes the
    thread to active state and starts evaluating pending outcomes.
    Designed for the operator's daily pre-market start pattern:
    ThetaData IV=0 before market open raises DataNotReadyError, then
    populates ~5 min after open; the next tick after that succeeds.
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


def _try_initialize_client() -> Optional[UnifiedDataClient]:
    """FIX-2: single-source-of-truth for client construction.

    Attempts to construct a UnifiedDataClient and run its health
    check. Returns the client on success, None on failure.

    Exceptions are caught broadly because both DataNotReadyError
    (pre-market IV=0) and DataConnectionError (transient network
    issues) are recoverable — the next tick retries either way.
    A richer exception taxonomy is Phase 2 work.

    Caller logging responsibility:
      - start_outcome_resolver_loop logs INFO on initial-attempt
        outcome (whether the thread spawns active or in waiting).
      - _resolver_loop logs DEBUG on retry failure (pre-market is
        expected; don't spam) and INFO on the first successful
        reconnect after waiting (state transition is significant).
    """
    try:
        client = UnifiedDataClient()
        client.health_check()
        return client
    except Exception:
        return None


def _resolver_loop():
    """Main loop body. Runs in the daemon thread.

    FIX-2: each tick first checks _resolver_client. If None, attempts
    reconnect via _try_initialize_client. On reconnect failure, logs
    DEBUG and sleeps until the next tick. On reconnect success, logs
    INFO state-transition message and falls through to normal
    evaluation. When client is non-None (steady state), proceeds
    directly to resolve_pending_outcomes.
    """
    global _resolver_running, _resolver_client
    interval = config.OUTCOME_RESOLVER_INTERVAL_SECONDS
    while _resolver_running:
        # FIX-2: client-not-yet-initialized retry path. If startup
        # health check failed (e.g. pre-market IV=0), the thread
        # spawns with _resolver_client=None; each tick retries until
        # the data feed is ready.
        if _resolver_client is None:
            client = _try_initialize_client()
            if client is None:
                logger.debug(
                    "outcome resolver: client not ready; "
                    "will retry next tick"
                )
                # Sleep then retry; do NOT call resolve_pending_outcomes
                # with a None client.
                for _ in range(interval):
                    if not _resolver_running:
                        break
                    time.sleep(1)
                continue
            _resolver_client = client
            logger.info(
                "outcome resolver: client healthy; resuming "
                "normal operation"
            )
            # Fall through to evaluation on this same tick.

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

    FIX-2: always spawns the thread (unless thread spawn itself
    raises). If the initial UnifiedDataClient health check fails,
    the thread is spawned in a "waiting" state — each tick retries
    client initialization until it succeeds, then transitions to
    normal operation. Designed for the operator's daily pre-market
    start pattern (ThetaData IV=0 before open).

    Returns True if the thread was started (or already running),
    whether immediately healthy or in waiting state. Returns False
    only if Python's threading subsystem itself fails — extremely
    rare and would indicate a fundamental runtime problem.
    """
    global _resolver_running, _resolver_thread, _resolver_client
    if _resolver_running:
        logger.debug("outcome resolver already running")
        return True

    # FIX-2: client may be None if initial health check fails;
    # the thread spawns anyway and retries each tick.
    _resolver_client = _try_initialize_client()
    initial_state = "active" if _resolver_client is not None else "waiting"

    _resolver_running = True
    try:
        _resolver_thread = threading.Thread(
            target=_resolver_loop,
            daemon=True,
            name="outcome-resolver",
        )
        _resolver_thread.start()
    except Exception as e:
        # Extremely rare — Python threading subsystem failure.
        logger.error(
            "outcome resolver: thread spawn failed (%s) — "
            "resolver will NOT run this lifespan", e,
        )
        _resolver_running = False
        _resolver_thread = None
        _resolver_client = None
        return False

    if initial_state == "active":
        logger.info(
            "outcome resolver thread started (interval=%ss)",
            config.OUTCOME_RESOLVER_INTERVAL_SECONDS,
        )
    else:
        logger.info(
            "outcome resolver thread spawned in waiting state "
            "(interval=%ss) — will retry client initialization "
            "each tick until UnifiedDataClient health check "
            "succeeds (e.g. after market open populates "
            "ThetaData IV)",
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
