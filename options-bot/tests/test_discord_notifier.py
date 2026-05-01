"""Unit tests for notifications.discord.

Mocking strategy: `threading.Thread` is replaced with a synchronous-
execution fake (`_FakeThread`) so dispatch runs deterministically in
the test thread. `urllib.request.urlopen` is mocked at the source
module so HTTP behavior can be controlled. No real network calls.

Run via:
    python -m pytest tests/test_discord_notifier.py -v
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402
import urllib.request  # noqa: E402
from notifications import discord as discord_mod  # noqa: E402
from notifications.discord import (  # noqa: E402
    _DISCORD_CONTENT_MAX,
    _resolve_webhook_url,
    send_alert,
    send_entry_alert,
)
from profiles.profile_config import ProfileConfig  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


class _FakeThread:
    """Synchronous-execution Thread stand-in. start() invokes target
    immediately and the constructed instance is captured for assertions."""
    instances: list = []

    def __init__(self, target=None, daemon=False, name=None):
        self.target = target
        self.daemon = daemon
        self.name = name
        _FakeThread.instances.append(self)
        self.started = False

    def start(self):
        self.started = True
        if self.target is not None:
            self.target()


@pytest.fixture(autouse=True)
def _reset_thread_instances():
    _FakeThread.instances.clear()
    yield
    _FakeThread.instances.clear()


@pytest.fixture
def patched_thread(monkeypatch):
    """Replace threading.Thread inside notifications.discord."""
    monkeypatch.setattr(discord_mod.threading, "Thread", _FakeThread)
    return _FakeThread


@pytest.fixture
def mock_urlopen(monkeypatch):
    """Patch urlopen with a default 200 response."""
    response = MagicMock()
    response.status = 200
    response.read.return_value = b"OK"
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    mock = MagicMock(return_value=response)
    monkeypatch.setattr(urllib.request, "urlopen", mock)
    return mock


@pytest.fixture
def empty_global_url(monkeypatch):
    monkeypatch.setattr(config, "ALERT_WEBHOOK_URL", "")


@pytest.fixture
def global_url(monkeypatch):
    monkeypatch.setattr(
        config, "ALERT_WEBHOOK_URL",
        "https://discord.com/api/webhooks/global/abc",
    )


def _profile(webhook_url: str | None = None) -> ProfileConfig:
    cfg = ProfileConfig(
        name="swing-test",
        preset="swing",
        symbols=["TSLA"],
        max_capital_deployed=5000.0,
        discord_webhook_url=webhook_url,
    )
    return cfg


# ─────────────────────────────────────────────────────────────────
# _resolve_webhook_url
# ─────────────────────────────────────────────────────────────────


def test_resolve_profile_webhook_takes_priority(empty_global_url):
    cfg = _profile("https://discord.com/api/webhooks/profile/xyz")
    assert _resolve_webhook_url(cfg) == "https://discord.com/api/webhooks/profile/xyz"


def test_resolve_falls_back_to_global_when_profile_url_none(global_url):
    cfg = _profile(None)
    assert _resolve_webhook_url(cfg) == "https://discord.com/api/webhooks/global/abc"


def test_resolve_returns_global_when_profile_is_none(global_url):
    assert _resolve_webhook_url(None) == "https://discord.com/api/webhooks/global/abc"


def test_resolve_returns_none_when_both_empty(empty_global_url):
    assert _resolve_webhook_url(None) is None


def test_resolve_empty_string_profile_url_falls_through(global_url):
    """ProfileConfig validates assignment off by default; manually set the
    field to empty string to simulate the truthy-check path."""
    cfg = _profile(None)
    cfg.discord_webhook_url = ""  # bypass validator (mutable, no validate-on-assign)
    assert _resolve_webhook_url(cfg) == "https://discord.com/api/webhooks/global/abc"


# ─────────────────────────────────────────────────────────────────
# _dispatch_async / urlopen behavior
# ─────────────────────────────────────────────────────────────────


def test_dispatch_200_no_warning(patched_thread, mock_urlopen, caplog):
    caplog.set_level(logging.WARNING, logger="options-bot.notifications.discord")
    discord_mod._dispatch_async("https://x", {"content": "hi"})
    assert mock_urlopen.call_count == 1
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warns == []


def test_dispatch_204_no_warning(patched_thread, monkeypatch, caplog):
    response = MagicMock()
    response.status = 204
    response.read.return_value = b""
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(urllib.request, "urlopen", MagicMock(return_value=response))
    caplog.set_level(logging.WARNING, logger="options-bot.notifications.discord")
    discord_mod._dispatch_async("https://x", {"content": "hi"})
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warns == []


def test_dispatch_4xx_logs_warning(patched_thread, monkeypatch, caplog):
    response = MagicMock()
    response.status = 400
    response.read.return_value = b"bad request"
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(urllib.request, "urlopen", MagicMock(return_value=response))
    caplog.set_level(logging.WARNING, logger="options-bot.notifications.discord")
    discord_mod._dispatch_async("https://x", {"content": "hi"})
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("status 400" in r.getMessage() for r in warns)


def test_dispatch_5xx_logs_warning(patched_thread, monkeypatch, caplog):
    response = MagicMock()
    response.status = 502
    response.read.return_value = b"upstream"
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(urllib.request, "urlopen", MagicMock(return_value=response))
    caplog.set_level(logging.WARNING, logger="options-bot.notifications.discord")
    discord_mod._dispatch_async("https://x", {"content": "hi"})
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("status 502" in r.getMessage() for r in warns)


def test_dispatch_urlerror_logs_warning(patched_thread, monkeypatch, caplog):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        MagicMock(side_effect=urllib.error.URLError("nope")),
    )
    caplog.set_level(logging.WARNING, logger="options-bot.notifications.discord")
    discord_mod._dispatch_async("https://x", {"content": "hi"})
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("URLError" in r.getMessage() for r in warns)


def test_dispatch_httperror_logs_warning(patched_thread, monkeypatch, caplog):
    err = urllib.error.HTTPError(
        "https://x", 503, "service unavailable", {}, None,
    )
    monkeypatch.setattr(
        urllib.request, "urlopen", MagicMock(side_effect=err),
    )
    caplog.set_level(logging.WARNING, logger="options-bot.notifications.discord")
    discord_mod._dispatch_async("https://x", {"content": "hi"})
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("HTTPError" in r.getMessage() for r in warns)


def test_dispatch_generic_exception_logs_warning(patched_thread, monkeypatch, caplog):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        MagicMock(side_effect=ValueError("weird")),
    )
    caplog.set_level(logging.WARNING, logger="options-bot.notifications.discord")
    discord_mod._dispatch_async("https://x", {"content": "hi"})
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("non-fatal" in r.getMessage() for r in warns)


def test_dispatch_thread_is_daemon(patched_thread, mock_urlopen):
    discord_mod._dispatch_async("https://x", {"content": "hi"})
    assert _FakeThread.instances, "Thread should have been constructed"
    assert _FakeThread.instances[-1].daemon is True


# ─────────────────────────────────────────────────────────────────
# send_alert
# ─────────────────────────────────────────────────────────────────


def test_send_alert_empty_content_returns_false(global_url, caplog):
    caplog.set_level(logging.INFO, logger="options-bot.notifications.discord")
    assert send_alert("") is False


def test_send_alert_whitespace_content_returns_false(global_url, caplog):
    caplog.set_level(logging.INFO, logger="options-bot.notifications.discord")
    assert send_alert("   \n  \t  ") is False


def test_send_alert_oversized_content_returns_false(global_url, caplog):
    caplog.set_level(logging.WARNING, logger="options-bot.notifications.discord")
    huge = "x" * (_DISCORD_CONTENT_MAX + 1)
    assert send_alert(huge) is False
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("exceeds Discord max" in r.getMessage() for r in warns)


def test_send_alert_no_webhook_returns_false(empty_global_url, caplog):
    caplog.set_level(logging.INFO, logger="options-bot.notifications.discord")
    assert send_alert("hello") is False


def test_send_alert_dispatches_with_payload(patched_thread, mock_urlopen, global_url):
    result = send_alert("hello world")
    assert result is True
    # urlopen called once with a Request whose body is JSON {"content": "hello world"}
    assert mock_urlopen.call_count == 1
    req = mock_urlopen.call_args.args[0]
    assert req.get_full_url() == "https://discord.com/api/webhooks/global/abc"
    body = req.data.decode("utf-8")
    assert '"content": "hello world"' in body


def test_send_alert_uses_profile_url_when_set(patched_thread, mock_urlopen, empty_global_url):
    cfg = _profile("https://discord.com/api/webhooks/profile/xyz")
    send_alert("hi", profile_config=cfg)
    req = mock_urlopen.call_args.args[0]
    assert req.get_full_url() == "https://discord.com/api/webhooks/profile/xyz"


# ─────────────────────────────────────────────────────────────────
# send_entry_alert — formatting + emoji
# ─────────────────────────────────────────────────────────────────


def _entry_kwargs(**overrides) -> dict:
    defaults = {
        "profile_config": None,
        "signal_id": "sig-001",
        "symbol": "TSLA",
        "setup_type": "momentum",
        "direction": "bullish",
        "setup_score": 0.72,
        "contract_strike": 250.0,
        "contract_right": "call",
        "contract_expiration": "2026-05-15",
        "entry_premium_per_share": 4.20,
        "contracts": 1,
        "mode": "signal_only",
        "timestamp": datetime(2026, 5, 6, 18, 32, tzinfo=timezone.utc),
        # 18:32 UTC in May = 14:32 ET (DST)
    }
    return {**defaults, **overrides}


def _captured_content(mock_urlopen) -> str:
    req = mock_urlopen.call_args.args[0]
    payload = req.data.decode("utf-8")
    import json as _json
    return _json.loads(payload)["content"]


def test_entry_bullish_emoji(patched_thread, mock_urlopen, global_url):
    send_entry_alert(**_entry_kwargs(direction="bullish"))
    content = _captured_content(mock_urlopen)
    assert "🟢" in content
    assert "🔴" not in content


def test_entry_bearish_emoji(patched_thread, mock_urlopen, global_url):
    send_entry_alert(**_entry_kwargs(direction="bearish"))
    content = _captured_content(mock_urlopen)
    assert "🔴" in content


def test_entry_neutral_emoji_logs_no_warning(patched_thread, mock_urlopen, global_url, caplog):
    caplog.set_level(logging.WARNING, logger="options-bot.notifications.discord")
    send_entry_alert(**_entry_kwargs(direction="neutral"))
    content = _captured_content(mock_urlopen)
    assert "⚪" in content
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warns == []


def test_entry_garbage_direction_uses_neutral_emoji_with_warning(
    patched_thread, mock_urlopen, global_url, caplog,
):
    caplog.set_level(logging.WARNING, logger="options-bot.notifications.discord")
    result = send_entry_alert(**_entry_kwargs(direction="sideways"))
    assert result is True
    content = _captured_content(mock_urlopen)
    assert "⚪" in content
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("unexpected direction" in r.getMessage() for r in warns)


def test_entry_naive_timestamp_raises(global_url):
    naive = datetime(2026, 5, 6, 14, 32)
    with pytest.raises(ValueError, match="timezone-aware"):
        send_entry_alert(**_entry_kwargs(timestamp=naive))


def test_entry_default_timestamp_is_aware(patched_thread, mock_urlopen, global_url):
    send_entry_alert(**_entry_kwargs(timestamp=None))
    content = _captured_content(mock_urlopen)
    assert "ET" in content


def test_entry_profile_none_shows_no_profile(patched_thread, mock_urlopen, global_url):
    send_entry_alert(**_entry_kwargs(profile_config=None))
    content = _captured_content(mock_urlopen)
    assert "(no profile)" in content
    assert "SIGNAL ENTRY" in content


def test_entry_profile_label_uses_preset_uppercase(patched_thread, mock_urlopen, global_url):
    cfg = _profile(None)
    send_entry_alert(**_entry_kwargs(profile_config=cfg))
    content = _captured_content(mock_urlopen)
    assert "SWING ENTRY" in content
    assert "swing-test" in content  # profile name


def test_entry_strike_format_integer(patched_thread, mock_urlopen, global_url):
    """Integer strike (250.0) renders as '250C' (no trailing zeros)."""
    send_entry_alert(**_entry_kwargs(contract_strike=250.0, contract_right="call"))
    content = _captured_content(mock_urlopen)
    assert "250C" in content
    assert "250.0C" not in content


def test_entry_strike_format_half(patched_thread, mock_urlopen, global_url):
    """Half-strike (250.5) preserves the decimal."""
    send_entry_alert(**_entry_kwargs(contract_strike=250.5, contract_right="put"))
    content = _captured_content(mock_urlopen)
    assert "250.5P" in content


def test_entry_total_cost_single_contract(patched_thread, mock_urlopen, global_url):
    """1 contract × $4.20 premium = $420 per-contract = $420 total."""
    send_entry_alert(**_entry_kwargs(
        contracts=1, entry_premium_per_share=4.20,
    ))
    content = _captured_content(mock_urlopen)
    assert "1 contract" in content
    assert "$420" in content
    assert "= $420" in content


def test_entry_total_cost_multi_contract(patched_thread, mock_urlopen, global_url):
    """3 contracts × $4.20 = $420 per-contract × 3 = $1,260 total."""
    send_entry_alert(**_entry_kwargs(
        contracts=3, entry_premium_per_share=4.20,
    ))
    content = _captured_content(mock_urlopen)
    assert "3 contracts" in content
    assert "$1,260" in content


def test_entry_url_resolution_profile_takes_priority(
    patched_thread, mock_urlopen, global_url,
):
    cfg = _profile("https://discord.com/api/webhooks/profile/xyz")
    send_entry_alert(**_entry_kwargs(profile_config=cfg))
    req = mock_urlopen.call_args.args[0]
    assert req.get_full_url() == "https://discord.com/api/webhooks/profile/xyz"


def test_entry_url_resolution_falls_back_to_global(
    patched_thread, mock_urlopen, global_url,
):
    cfg = _profile(None)
    send_entry_alert(**_entry_kwargs(profile_config=cfg))
    req = mock_urlopen.call_args.args[0]
    assert req.get_full_url() == "https://discord.com/api/webhooks/global/abc"


def test_entry_no_url_returns_false(empty_global_url):
    """No profile webhook + no global → False, no dispatch."""
    result = send_entry_alert(**_entry_kwargs(profile_config=None))
    assert result is False


def test_entry_content_includes_signal_id_and_setup(
    patched_thread, mock_urlopen, global_url,
):
    send_entry_alert(**_entry_kwargs(
        signal_id="sig-XYZ", setup_type="compression_breakout",
        setup_score=0.65,
    ))
    content = _captured_content(mock_urlopen)
    assert "sig-XYZ" in content
    assert "compression_breakout" in content
    assert "0.65" in content


def test_entry_timestamp_displayed_in_et(patched_thread, mock_urlopen, global_url):
    """18:32 UTC (DST) → 14:32 ET on May 6 2026."""
    send_entry_alert(**_entry_kwargs(
        timestamp=datetime(2026, 5, 6, 18, 32, tzinfo=timezone.utc),
    ))
    content = _captured_content(mock_urlopen)
    assert "2026-05-06 14:32 ET" in content


def test_entry_timestamp_with_eastern_input(patched_thread, mock_urlopen, global_url):
    """ET-aware timestamp converts cleanly."""
    et = ZoneInfo("America/New_York")
    send_entry_alert(**_entry_kwargs(
        timestamp=datetime(2026, 5, 6, 14, 32, tzinfo=et),
    ))
    content = _captured_content(mock_urlopen)
    assert "2026-05-06 14:32 ET" in content


def test_entry_returns_true_on_successful_dispatch(
    patched_thread, mock_urlopen, global_url,
):
    assert send_entry_alert(**_entry_kwargs()) is True
