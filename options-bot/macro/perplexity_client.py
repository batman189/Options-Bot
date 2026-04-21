"""Thin Perplexity API client with a daily cost circuit breaker.

The client requests strict JSON structured output against macro.schema. If
the response cannot be parsed, the call is treated as a failure — no regex
fallback. Every outbound call increments a per-ET-day counter atomically;
once the counter hits MACRO_DAILY_CALL_CAP, further calls are refused
without hitting the network. This guards against runaway watchdog-restart
loops racking up cost.

Rule 4: the client never assumes what Perplexity will return. The JSON is
fed through MacroPayload and anything off-contract is discarded.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from config import (
    DB_PATH,
    MACRO_DAILY_CALL_CAP,
    PERPLEXITY_API_KEY_ENV,
    PERPLEXITY_MAX_RETRIES,
    PERPLEXITY_MODEL,
    PERPLEXITY_TIMEOUT_SECONDS,
    TRADABLE_SYMBOLS,
)
from macro.schema import MacroPayload

logger = logging.getLogger("options-bot.macro.perplexity")

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
ET = ZoneInfo("America/New_York")


class CircuitBreakerOpen(RuntimeError):
    """Raised when the daily call cap has been reached."""


class PerplexityError(RuntimeError):
    """Raised for any API / parsing failure. Worker catches and stays alive."""


def _today_et() -> str:
    return datetime.now(ET).date().isoformat()


def _atomic_increment_usage() -> int:
    """Increment today's counter and return the new count in one statement.

    INSERT...ON CONFLICT DO UPDATE...RETURNING is atomic under SQLite's
    implicit transaction — no read-then-write window where a concurrent
    writer could slip in and skew the count. Requires SQLite 3.35+
    (Python 3.11+ ships with 3.37+; checked live at 3.50.4).
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    today = _today_et()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            """INSERT INTO macro_api_usage (date_et, call_count, last_call_at)
               VALUES (?, 1, ?)
               ON CONFLICT(date_et) DO UPDATE SET
                   call_count = call_count + 1,
                   last_call_at = excluded.last_call_at
               RETURNING call_count""",
            (today, now_utc),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    return int(row[0]) if row else 1


def _current_usage() -> int:
    """Read today's count without mutating it. Returns 0 on missing row / error."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            row = conn.execute(
                "SELECT call_count FROM macro_api_usage WHERE date_et = ?",
                (_today_et(),),
            ).fetchone()
        finally:
            conn.close()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _build_prompt() -> str:
    """The user prompt — asks Perplexity for structured macro state."""
    symbols = ", ".join(sorted(TRADABLE_SYMBOLS))
    return (
        "Return ONLY valid JSON matching this schema, no prose:\n"
        "{\n"
        '  "events": [{"symbol": "<ticker or *>", "event_type": "FOMC|CPI|PPI|NFP|GDP|PCE|POWELL_SPEECH|EARNINGS|OTHER",'
        ' "event_time_et": "<ISO8601 with offset>", "impact_level": "HIGH|MEDIUM|LOW", "source_url": "<https://...>"}],\n'
        '  "catalysts": [{"symbol": "<ticker or *>", "catalyst_type": "<short label>", "direction": "bullish|bearish|neutral",'
        ' "severity": <0.0-1.0>, "summary": "<<=200 chars>", "source_url": "<https://...>"}],\n'
        '  "regime": {"risk_tone": "risk_on|risk_off|mixed|unknown", "vix_context": "<short>",'
        ' "major_themes": ["<<=100 chars>", ...]}\n'
        "}\n\n"
        "Scope:\n"
        f"  - Tradable symbols: {symbols}. Market-wide events use symbol=\"*\".\n"
        "  - events: scheduled within the next 7 days. Include FOMC, CPI, PPI, NFP, GDP, PCE,\n"
        "    Powell speeches, earnings for the tradable symbols, plus any other known\n"
        "    high-impact releases.\n"
        "  - catalysts: breaking developments (news shocks, Fed commentary, geopolitical\n"
        "    events) from the last 4 hours that move US equity index options.\n"
        "    Catalyst severity IS used by the bot's scoring layer — when there is\n"
        "    strong confluence (multiple sources, clear market reaction), lean toward\n"
        "    higher severity (0.7-1.0). Reserve low severity (0.1-0.4) for weak or\n"
        "    single-source stories.\n"
        "  - regime: current macro risk tone with VIX context and the 3-5 dominant themes\n"
        "    driving positioning right now.\n"
        "  - Every event and catalyst MUST include a source_url. Drop any item you cannot\n"
        "    cite.\n"
        "  - All timestamps in America/New_York with explicit offset."
    )


def _parse_response(raw_text: str) -> MacroPayload:
    """Extract JSON from the Perplexity response and validate via Pydantic.

    Perplexity sometimes wraps JSON in code fences or leading whitespace.
    We do minimal cleanup — find the first '{' and last '}' — then hand to
    MacroPayload. Any deviation raises ValidationError which the caller
    translates to PerplexityError.
    """
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end < 0 or end < start:
        raise PerplexityError("no JSON object in response")
    body = raw_text[start:end + 1]
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise PerplexityError(f"JSON decode failed: {e}") from e
    try:
        return MacroPayload.model_validate(data)
    except Exception as e:
        raise PerplexityError(f"schema validation failed: {e}") from e


def call_perplexity() -> MacroPayload:
    """Make one Perplexity call. Raises CircuitBreakerOpen or PerplexityError.

    Cost breaker check is before the network call, increment is also before —
    we charge for the attempt, not for success, to prevent a loop that fails
    after the response lands from bypassing the cap.
    """
    api_key = os.environ.get(PERPLEXITY_API_KEY_ENV)
    if not api_key:
        raise PerplexityError(f"env var {PERPLEXITY_API_KEY_ENV} not set")

    current = _current_usage()
    if current >= MACRO_DAILY_CALL_CAP:
        raise CircuitBreakerOpen(
            f"daily call cap reached ({current} >= {MACRO_DAILY_CALL_CAP}); "
            f"no outbound call until next ET day"
        )

    new_count = _atomic_increment_usage()
    logger.info(f"Perplexity call {new_count}/{MACRO_DAILY_CALL_CAP} for {_today_et()}")

    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {"role": "system", "content": "You are a macro data assistant. Respond with valid JSON only."},
            {"role": "user", "content": _build_prompt()},
        ],
        "temperature": 0.0,
        "max_tokens": 2000,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_err: Optional[Exception] = None
    for attempt in range(PERPLEXITY_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=PERPLEXITY_TIMEOUT_SECONDS) as client:
                resp = client.post(PERPLEXITY_URL, json=payload, headers=headers)
            if resp.status_code >= 500:
                last_err = PerplexityError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                logger.warning(f"Perplexity 5xx on attempt {attempt + 1}: {last_err}")
                continue
            if resp.status_code != 200:
                raise PerplexityError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            body = resp.json()
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise PerplexityError("empty content in response")
            return _parse_response(content)
        except (httpx.HTTPError, PerplexityError) as e:
            last_err = e
            if isinstance(e, PerplexityError) and "schema validation" in str(e):
                raise  # Don't retry schema failures — the response shape is wrong
            logger.warning(f"Perplexity attempt {attempt + 1} failed: {e}")
    raise PerplexityError(f"all attempts failed: {last_err}")
