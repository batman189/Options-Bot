"""
Lightweight alert system for critical trading events.
Sends alerts via webhook (Discord, Slack, Pushover, etc.).

Configure by setting ALERT_WEBHOOK_URL in .env.
If not configured, alerts are logged but not sent — no crash.

Usage:
    from utils.alerter import send_alert
    send_alert("CRITICAL", "Circuit breaker OPEN on Theta Terminal", profile_id="abc123")
"""

import json
import logging
import threading
import time
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger("options-bot.utils.alerter")


def send_alert(
    level: str,
    message: str,
    profile_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> bool:
    """
    Send an alert via configured webhook.

    Args:
        level:      "CRITICAL", "WARNING", or "INFO"
        message:    Human-readable alert message
        profile_id: Optional profile identifier for context
        details:    Optional dict of additional key-value context

    Returns:
        True if alert was sent successfully, False otherwise.
        Never raises — failures are logged and swallowed.
    """
    from config import ALERT_WEBHOOK_URL

    # Always log the alert regardless of webhook availability
    log_message = f"[ALERT:{level}]"
    if profile_id:
        log_message += f" [{profile_id}]"
    log_message += f" {message}"
    if details:
        log_message += f" | {details}"

    if level == "CRITICAL":
        logger.critical(log_message)
    elif level == "WARNING":
        logger.warning(log_message)
    else:
        logger.info(log_message)

    if not ALERT_WEBHOOK_URL:
        logger.debug("ALERT_WEBHOOK_URL not configured — alert logged only")
        return False

    # Send in background thread to never block the trading loop
    def _send():
        try:
            import urllib.request
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            payload_lines = [
                f"**[{level}] Options Bot Alert**",
                f"Time: {timestamp}",
            ]
            if profile_id:
                payload_lines.append(f"Profile: {profile_id}")
            payload_lines.append(f"Message: {message}")
            if details:
                for k, v in details.items():
                    payload_lines.append(f"{k}: {v}")

            # Discord/Slack compatible payload
            payload = json.dumps({"content": "\n".join(payload_lines)}).encode("utf-8")

            req = urllib.request.Request(
                ALERT_WEBHOOK_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status not in (200, 204):
                    logger.warning(
                        f"Alert webhook returned status {resp.status}"
                    )
                else:
                    logger.debug("Alert sent successfully")
        except Exception as e:
            logger.warning(f"Alert send failed (non-fatal): {e}")

    t = threading.Thread(target=_send, daemon=True, name="alerter")
    t.start()
    return True
