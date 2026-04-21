"""Long-running subprocess that polls Perplexity and writes SQLite.

Spawned once by backend/app.py on startup (via backend/routes/trading.py
spawn_macro_worker). Runs completely out-of-band from the trading
processes. If it crashes, the existing watchdog restarts it. If Perplexity
is down, the fetch fails loudly in the log but the worker stays alive —
trading continues on stale data.

Invariant: this process must NEVER import anything from the trading hot
path. scorer.py, base_profile.py, v2_strategy.py are off-limits here.

Usage:
    python macro/worker.py --mode live       # long-running loop
    python macro/worker.py --mode oneshot    # single fetch + exit (ops tool)
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Allow running the module as a top-level script — Popen launches with
# python macro/worker.py, which means the parent `options-bot/` dir is not
# on sys.path by default.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiosqlite

from config import (
    DB_PATH,
    LOG_FORMAT,
    LOG_LEVEL,
    LOGS_DIR,
    MACRO_CATALYST_EXPIRY_HOURS,
    MACRO_POLL_MINUTES,
    MACRO_PREMARKET_POLL_ET,
)
from macro.allowlists import normalize_event, normalize_catalyst
from macro.perplexity_client import (
    CircuitBreakerOpen,
    PerplexityError,
    call_perplexity,
)
from macro.schema import MacroPayload

ET = ZoneInfo("America/New_York")

# Worker writes to its own log file so it does not interleave with trading logs
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"macro_worker_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("options-bot.macro.worker")

_shutdown = False


def _install_signal_handlers():
    """Graceful shutdown on SIGTERM / SIGINT."""
    def _handler(signum, frame):
        global _shutdown
        _shutdown = True
        logger.info(f"Signal {signum} received, exiting at next safe point")

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
    if sys.platform == "win32":
        try:
            signal.signal(signal.SIGBREAK, _handler)
        except (AttributeError, OSError):
            pass


async def fetch_and_write(payload: MacroPayload) -> tuple[int, int, bool]:
    """Write events/catalysts/regime in a single transaction.

    Returns (events_written, catalysts_written, regime_written).
    All-or-nothing via BEGIN IMMEDIATE / COMMIT. If anything raises, the
    rollback leaves the DB at the previous consistent snapshot.
    """
    fetched_at_utc = datetime.now(timezone.utc)
    fetched_at_str = fetched_at_utc.isoformat()

    event_rows = []
    for ev in payload.events:
        row = normalize_event(ev)
        if row is None:
            continue
        event_rows.append((
            row["symbol"], row["event_type"], row["event_time_et"],
            row["event_time_utc"],
            row["impact_level"], row["source_url"], fetched_at_str,
        ))

    catalyst_rows = []
    for c in payload.catalysts:
        row = normalize_catalyst(c, fetched_at_utc, MACRO_CATALYST_EXPIRY_HOURS)
        if row is None:
            continue
        catalyst_rows.append((
            row["symbol"], row["catalyst_type"], row["direction"],
            row["severity"], row["expires_at"], row["summary"],
            row["source_url"], fetched_at_str, row["content_hash"],
        ))

    themes_json = __import__("json").dumps(payload.regime.major_themes)
    regime_row = (
        "current", payload.regime.risk_tone,
        payload.regime.vix_context, themes_json, fetched_at_str,
    )

    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            if event_rows:
                await db.executemany(
                    """INSERT OR IGNORE INTO macro_events
                       (symbol, event_type, event_time_et, event_time_utc,
                        impact_level, source_url, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    event_rows,
                )
            if catalyst_rows:
                # Upsert by content_hash — a re-observed story refreshes its
                # TTL and severity (the newer observation may revise it)
                # rather than creating a duplicate row.
                await db.executemany(
                    """INSERT INTO macro_catalysts
                       (symbol, catalyst_type, direction, severity, expires_at,
                        summary, source_url, fetched_at, content_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(content_hash) DO UPDATE SET
                           expires_at = excluded.expires_at,
                           fetched_at = excluded.fetched_at,
                           severity = excluded.severity""",
                    catalyst_rows,
                )
            await db.execute(
                """INSERT OR REPLACE INTO macro_regime
                   (id, risk_tone, vix_context, major_themes_json, fetched_at)
                   VALUES (?, ?, ?, ?, ?)""",
                regime_row,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    return len(event_rows), len(catalyst_rows), True


async def one_cycle():
    """One fetch + write cycle. Exceptions are logged; worker stays alive."""
    logger.info("Macro fetch cycle starting")
    try:
        payload = call_perplexity()
    except CircuitBreakerOpen as e:
        logger.warning(f"Macro fetch skipped: {e}")
        return
    except PerplexityError as e:
        logger.error(f"Macro fetch failed (worker stays alive, trading unaffected): {e}")
        return

    try:
        events_written, catalysts_written, _ = await fetch_and_write(payload)
        logger.info(
            f"Macro write complete: {events_written} events, "
            f"{catalysts_written} catalysts, 1 regime row"
        )
    except Exception as e:
        logger.exception(f"Macro write failed (worker stays alive): {e}")


def _next_wake_time(now_et: datetime) -> datetime:
    """Compute the next scheduled poll time — guaranteed strictly > now_et.

    The naive "top-of-hour + MACRO_POLL_MINUTES" can land in the past when
    MACRO_POLL_MINUTES < 60 and the clock is already past that offset within
    the current hour (e.g. MACRO_POLL_MINUTES=30 and now is HH:45 — naive
    next_hour = HH:30, which is 15 minutes in the past and would make the
    worker fire instantly every cycle). Loop until the computed time is
    strictly in the future.
    """
    # Poll cadence anchored to the top of the current hour, then advanced
    # by MACRO_POLL_MINUTES until it's strictly in the future.
    next_hour = now_et.replace(minute=0, second=0, microsecond=0) + timedelta(
        minutes=MACRO_POLL_MINUTES
    )
    while next_hour <= now_et:
        next_hour += timedelta(minutes=MACRO_POLL_MINUTES)

    # Pre-market: HH:MM ET daily deep scan
    pm_h, pm_m = (int(x) for x in MACRO_PREMARKET_POLL_ET.split(":"))
    premarket = now_et.replace(hour=pm_h, minute=pm_m, second=0, microsecond=0)
    if premarket <= now_et:
        premarket = premarket + timedelta(days=1)

    return min(next_hour, premarket)


async def live_loop():
    """Long-running loop. Polls hourly + premarket. Fail-safe end-to-end."""
    logger.info("Macro worker live loop started")
    # Fire once immediately on startup so the UI/veto has data fast after a
    # restart. Subsequent cycles honor the schedule.
    await one_cycle()
    while not _shutdown:
        now_et = datetime.now(ET)
        wake = _next_wake_time(now_et)
        sleep_s = max(5.0, (wake - now_et).total_seconds())
        logger.info(f"Macro worker sleeping {sleep_s:.0f}s until {wake.isoformat()}")
        # Wake in 30s chunks so shutdown flag is responsive
        slept = 0.0
        while slept < sleep_s and not _shutdown:
            chunk = min(30.0, sleep_s - slept)
            await asyncio.sleep(chunk)
            slept += chunk
        if _shutdown:
            break
        await one_cycle()
    logger.info("Macro worker live loop exited cleanly")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["live", "oneshot"], default="live")
    args = parser.parse_args()

    _install_signal_handlers()

    if args.mode == "oneshot":
        asyncio.run(one_cycle())
    else:
        try:
            asyncio.run(live_loop())
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt — exiting")


if __name__ == "__main__":
    main()
