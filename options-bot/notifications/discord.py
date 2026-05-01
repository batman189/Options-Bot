"""Discord notifier for trading signals.

Phase 1a entry-signal alerts; future support for fill confirmations,
exits, and position events per ARCHITECTURE.md §32.

URL resolution chain:
  1. profile_config.discord_webhook_url (per-profile override)
  2. config.ALERT_WEBHOOK_URL (global default)
  3. None — log the alert and skip the HTTP call

Transport: urllib.request stdlib in a daemon thread. Matches the
utils/alerter.py pattern. No new dependency.

Failure mode: fail-safe. Logs at warning level on HTTP failure or
non-2xx response, returns False. Never raises. A missing Discord
alert costs the operator a notification; the signal is still in
signal_outcomes and any DB log.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import config
from profiles.profile_config import ProfileConfig

logger = logging.getLogger("options-bot.notifications.discord")

_HTTP_TIMEOUT_SECONDS = 10
_DISCORD_CONTENT_MAX = 2000  # Discord webhook content character cap
_ET = ZoneInfo("America/New_York")


def _resolve_webhook_url(
    profile_config: Optional[ProfileConfig],
) -> Optional[str]:
    """Return the webhook URL to use, or None if neither per-profile
    nor global is configured. Empty strings count as not-configured."""
    if profile_config is not None:
        url = profile_config.discord_webhook_url
        if url:
            return url
    fallback = config.ALERT_WEBHOOK_URL
    if fallback:
        return fallback
    return None


def _dispatch_async(url: str, payload: dict) -> threading.Thread:
    """Fire the webhook in a daemon thread. Logs warning on any failure;
    never raises. Returns the spawned thread (for testability)."""

    body = json.dumps(payload).encode("utf-8")

    def _send() -> None:
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
                if resp.status not in (200, 204):
                    snippet = b""
                    try:
                        snippet = resp.read(200)
                    except Exception:
                        pass
                    logger.warning(
                        "discord webhook returned status %s body=%r",
                        resp.status, snippet[:200],
                    )
        except urllib.error.HTTPError as e:
            logger.warning("discord webhook HTTPError: %s", e)
        except urllib.error.URLError as e:
            logger.warning("discord webhook URLError: %s", e)
        except Exception as e:
            logger.warning("discord webhook failed (non-fatal): %s", e)

    t = threading.Thread(target=_send, daemon=True, name="discord-notifier")
    t.start()
    return t


def send_alert(
    content: str,
    profile_config: Optional[ProfileConfig] = None,
) -> bool:
    """Send a free-form Markdown alert to Discord.

    For non-entry-decision alerts (future: exits, fills, position
    events). Caller is responsible for formatting the content string.

    Returns True if dispatch was started (does NOT confirm Discord
    delivery — that happens asynchronously in the daemon thread).
    Returns False if no webhook URL is configured, or if content is
    empty / whitespace-only / exceeds Discord's 2000-char limit.
    """
    if not content or not content.strip():
        logger.info("send_alert: empty content")
        return False
    if len(content) > _DISCORD_CONTENT_MAX:
        logger.warning(
            "send_alert: content exceeds Discord max (%d > %d)",
            len(content), _DISCORD_CONTENT_MAX,
        )
        return False

    url = _resolve_webhook_url(profile_config)
    if url is None:
        logger.info("send_alert: no webhook URL configured")
        return False

    _dispatch_async(url, {"content": content})
    return True


def _direction_emoji(direction: str) -> str:
    if direction == "bullish":
        return "🟢"
    if direction == "bearish":
        return "🔴"
    if direction != "neutral":
        logger.warning(
            "send_entry_alert: unexpected direction=%r — using neutral emoji",
            direction,
        )
    return "⚪"


def send_entry_alert(
    profile_config: Optional[ProfileConfig],
    signal_id: str,
    symbol: str,
    setup_type: str,
    direction: str,
    setup_score: float,
    contract_strike: float,
    contract_right: str,
    contract_expiration: str,
    entry_premium_per_share: float,
    contracts: int,
    mode: str = "signal_only",
    timestamp: Optional[datetime] = None,
) -> bool:
    """Format and dispatch a structured entry-signal alert.

    Format (Discord Markdown):

        **🟢 SWING ENTRY — TSLA**
        Setup: momentum (score 0.72, bullish)
        Contract: TSLA 2026-05-15 250C @ ~$4.20
        Position: 1 contract × $420 = $420
        Profile: tsla-swing  |  Mode: signal_only
        Signal ID: <signal_id>  |  2026-05-06 10:32 ET

    Header preset label is `profile_config.preset.upper()` when a
    profile_config is provided, "SIGNAL" otherwise. Direction emoji:
    🟢 bullish, 🔴 bearish, ⚪ for neutral or unrecognized values
    (warning logged).

    Returns the result of send_alert (True if dispatch started, False
    on missing URL or content issue).

    Raises ValueError if timestamp is provided but naive. timestamp=None
    defaults to current UTC, displayed in ET.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    elif timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")

    emoji = _direction_emoji(direction)
    preset_label = (
        profile_config.preset.upper() if profile_config is not None
        else "SIGNAL"
    )
    profile_name = (
        profile_config.name if profile_config is not None
        else "(no profile)"
    )

    cp = "C" if contract_right == "call" else "P"
    per_contract_cost = entry_premium_per_share * 100
    total_cost = per_contract_cost * contracts
    contract_word = "contract" if contracts == 1 else "contracts"

    ts_et = timestamp.astimezone(_ET).strftime("%Y-%m-%d %H:%M ET")

    content = (
        f"**{emoji} {preset_label} ENTRY — {symbol}**\n"
        f"Setup: {setup_type} (score {setup_score:.2f}, {direction})\n"
        f"Contract: {symbol} {contract_expiration} "
        f"{contract_strike:g}{cp} @ ~${entry_premium_per_share:.2f}\n"
        f"Position: {contracts} {contract_word} × "
        f"${per_contract_cost:,.0f} = ${total_cost:,.0f}\n"
        f"Profile: {profile_name}  |  Mode: {mode}\n"
        f"Signal ID: {signal_id}  |  {ts_et}"
    )

    return send_alert(content, profile_config=profile_config)
