"""Sync SELECT helpers called from the trading hot path.

No network, no LLM, no async — just SQLite reads. Every function is
fail-safe: DB lock, missing table, stale data, or any exception returns
the pre-macro baseline (empty list, None, etc) so the bot keeps trading.

Rule 4: nothing in this module calls an external system. It reads the DB
that macro/worker.py populates asynchronously out-of-band.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from config import (
    DB_PATH,
    MACRO_EVENT_BUFFER_MINUTES,
    MACRO_REGIME_STALE_MINUTES,
)

logger = logging.getLogger("options-bot.macro.reader")

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MacroEvent:
    """A row from macro_events, projected for the hot path."""
    symbol: str
    event_type: str
    event_time_et: datetime   # tz-aware, ET
    impact_level: str         # "HIGH" | "MEDIUM" | "LOW"
    source_url: str
    minutes_until: int        # computed; negative means already past


@dataclass(frozen=True)
class MacroRegime:
    """A row from macro_regime — the singleton 'current' record."""
    risk_tone: str            # "risk_on" | "risk_off" | "mixed" | "unknown"
    vix_context: str
    major_themes: list[str]
    fetched_at: datetime      # tz-aware, UTC


@dataclass(frozen=True)
class MacroContext:
    """Snapshot cached at the top of on_trading_iteration.

    Per-iteration immutable view of macro state. Passed down to scorer and
    profile so we don't query the DB per (symbol, setup, profile) combo.
    """
    events_by_symbol: dict[str, list[MacroEvent]] = field(default_factory=dict)
    regime: Optional[MacroRegime] = None
    fetched_at: Optional[datetime] = None


def _now() -> datetime:
    """UTC now. Override with unittest.mock.patch for deterministic tests."""
    return datetime.now(timezone.utc)


def _connect() -> sqlite3.Connection:
    """Open a short-lived read connection. Read-only intent, but we leave
    write permissions open since SQLite doesn't let us open the file twice
    under WAL in separate modes easily. The hot path never writes here."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _parse_event_time(raw: str) -> datetime:
    """Parse an ISO8601 string from macro_events.event_time_et into ET-aware."""
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(ET)


def get_active_events(
    symbol: str,
    lookahead_minutes: int = MACRO_EVENT_BUFFER_MINUTES,
) -> list[MacroEvent]:
    """Events for `symbol` (and market-wide '*') that are within `lookahead_minutes` of now.

    Returns an empty list on any DB error or missing table — fail-safe.

    The reader matches both the requested symbol and the market-wide bucket
    ("*") — e.g., FOMC events have symbol='*' but apply to every trade.
    """
    try:
        conn = _connect()
        try:
            now_utc = _now()
            # Keep +24h window so we can display countdowns in the UI and
            # let the caller decide how tight a buffer to use.
            horizon = (now_utc + timedelta(minutes=max(lookahead_minutes, 60))).astimezone(ET)
            rows = conn.execute(
                """SELECT symbol, event_type, event_time_et, impact_level, source_url
                   FROM macro_events
                   WHERE symbol IN (?, '*')
                     AND event_time_et <= ?
                   ORDER BY event_time_et ASC""",
                (symbol, horizon.isoformat()),
            ).fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"get_active_events failed (returning empty, fail-safe): {e}")
        return []

    now_et = now_utc.astimezone(ET)
    out: list[MacroEvent] = []
    for r in rows:
        try:
            event_time_et = _parse_event_time(r["event_time_et"])
        except Exception:
            continue
        delta_min = int((event_time_et - now_et).total_seconds() // 60)
        # Only return events still in the future-or-imminent window.
        # Events already past but inside the last minute are kept — a trade
        # placed seconds after the release is still exposed to the fallout.
        if delta_min < -1:
            continue
        if delta_min > lookahead_minutes:
            continue
        out.append(MacroEvent(
            symbol=r["symbol"],
            event_type=r["event_type"],
            event_time_et=event_time_et,
            impact_level=r["impact_level"],
            source_url=r["source_url"],
            minutes_until=delta_min,
        ))
    return out


def get_macro_regime() -> Optional[MacroRegime]:
    """Return the current macro regime, or None if missing/stale.

    Stale = fetched_at older than MACRO_REGIME_STALE_MINUTES. Stale state
    is treated as 'unknown' by returning None — the caller then applies no
    nudge (fail-safe).
    """
    try:
        conn = _connect()
        try:
            row = conn.execute(
                """SELECT risk_tone, vix_context, major_themes_json, fetched_at
                   FROM macro_regime WHERE id='current' LIMIT 1"""
            ).fetchone()
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"get_macro_regime failed (fail-safe): {e}")
        return None

    if row is None:
        return None

    try:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    except Exception:
        return None

    age = _now() - fetched_at
    if age > timedelta(minutes=MACRO_REGIME_STALE_MINUTES):
        logger.debug(f"macro_regime stale ({age.total_seconds()/60:.0f}min old); fail-safe")
        return None

    try:
        themes = json.loads(row["major_themes_json"] or "[]")
        if not isinstance(themes, list):
            themes = []
    except Exception:
        themes = []

    return MacroRegime(
        risk_tone=row["risk_tone"],
        vix_context=row["vix_context"] or "",
        major_themes=[str(t)[:100] for t in themes][:10],
        fetched_at=fetched_at,
    )


def next_upcoming_event(symbol: str = "*") -> Optional[MacroEvent]:
    """Convenience — the single nearest upcoming event, or None.

    Used by the Step 1 log extension in v2_strategy. Looks across all
    tradable symbols + market-wide by default.
    """
    try:
        conn = _connect()
        try:
            now_et = _now().astimezone(ET)
            row = conn.execute(
                """SELECT symbol, event_type, event_time_et, impact_level, source_url
                   FROM macro_events
                   WHERE event_time_et >= ?
                   ORDER BY event_time_et ASC LIMIT 1""",
                (now_et.isoformat(),),
            ).fetchone()
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"next_upcoming_event failed (fail-safe): {e}")
        return None

    if row is None:
        return None

    try:
        event_time_et = _parse_event_time(row["event_time_et"])
    except Exception:
        return None

    now_et = _now().astimezone(ET)
    delta_min = int((event_time_et - now_et).total_seconds() // 60)
    return MacroEvent(
        symbol=row["symbol"],
        event_type=row["event_type"],
        event_time_et=event_time_et,
        impact_level=row["impact_level"],
        source_url=row["source_url"],
        minutes_until=delta_min,
    )


def snapshot_macro_context(
    lookahead_minutes: int = MACRO_EVENT_BUFFER_MINUTES,
) -> MacroContext:
    """One-shot snapshot for an entire trading iteration.

    Called at the top of on_trading_iteration. Two SELECTs total. Result is
    passed as `macro_ctx=` to scorer.score and profile.should_enter so the
    per-(symbol, setup, profile) combinations don't each re-query the DB.

    Events are bucketed by symbol — market-wide ('*') events are merged
    into every tradable symbol's bucket so callers can look up by symbol
    without worrying about the wildcard row.
    """
    try:
        conn = _connect()
        try:
            now_utc = _now()
            horizon = (now_utc + timedelta(minutes=max(lookahead_minutes, 60))).astimezone(ET)
            event_rows = conn.execute(
                """SELECT symbol, event_type, event_time_et, impact_level, source_url
                   FROM macro_events
                   WHERE event_time_et <= ?
                   ORDER BY event_time_et ASC""",
                (horizon.isoformat(),),
            ).fetchall()
            regime_row = conn.execute(
                """SELECT risk_tone, vix_context, major_themes_json, fetched_at
                   FROM macro_regime WHERE id='current' LIMIT 1"""
            ).fetchone()
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"snapshot_macro_context failed (fail-safe): {e}")
        return MacroContext()

    # Build events-by-symbol with market-wide ('*') merged into every tradable bucket
    now_et = _now().astimezone(ET)
    market_wide: list[MacroEvent] = []
    per_symbol: dict[str, list[MacroEvent]] = {}
    for r in event_rows:
        try:
            event_time_et = _parse_event_time(r["event_time_et"])
        except Exception:
            continue
        delta_min = int((event_time_et - now_et).total_seconds() // 60)
        if delta_min < -1 or delta_min > lookahead_minutes:
            continue
        ev = MacroEvent(
            symbol=r["symbol"],
            event_type=r["event_type"],
            event_time_et=event_time_et,
            impact_level=r["impact_level"],
            source_url=r["source_url"],
            minutes_until=delta_min,
        )
        if r["symbol"] == "*":
            market_wide.append(ev)
        else:
            per_symbol.setdefault(r["symbol"], []).append(ev)

    # Merge market-wide into every per-symbol bucket (and keep a "*" bucket
    # so callers that pass an unknown symbol still see the wildcards).
    events_by_symbol: dict[str, list[MacroEvent]] = {"*": list(market_wide)}
    for sym, evs in per_symbol.items():
        events_by_symbol[sym] = evs + market_wide

    # Regime with staleness check
    regime: Optional[MacroRegime] = None
    fetched_at: Optional[datetime] = None
    if regime_row is not None:
        try:
            fetched_at = datetime.fromisoformat(regime_row["fetched_at"])
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            age = _now() - fetched_at
            if age <= timedelta(minutes=MACRO_REGIME_STALE_MINUTES):
                themes_raw = regime_row["major_themes_json"] or "[]"
                try:
                    themes = json.loads(themes_raw)
                    if not isinstance(themes, list):
                        themes = []
                except Exception:
                    themes = []
                regime = MacroRegime(
                    risk_tone=regime_row["risk_tone"],
                    vix_context=regime_row["vix_context"] or "",
                    major_themes=[str(t)[:100] for t in themes][:10],
                    fetched_at=fetched_at,
                )
        except Exception:
            regime = None

    return MacroContext(
        events_by_symbol=events_by_symbol,
        regime=regime,
        fetched_at=fetched_at,
    )


def events_for_symbol(ctx: MacroContext, symbol: str) -> list[MacroEvent]:
    """Lookup helper matching the scorer/profile callsite pattern.

    Returns events for `symbol` merged with market-wide ('*') events. If
    the context has no bucket for this symbol (rare — means the scanner
    saw a symbol that had no row at snapshot time), returns only the
    market-wide bucket.
    """
    if symbol in ctx.events_by_symbol:
        return ctx.events_by_symbol[symbol]
    return ctx.events_by_symbol.get("*", [])
