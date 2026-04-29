"""Unit tests for UnifiedDataClient.get_expirations.

Mocks the underlying ThetaSnapshotClient so no network calls are made.
Mirrors the unittest.mock pattern used in tests/test_pipeline_trace.py.

Run via:
    python -m pytest tests/test_unified_client_expirations.py -v
"""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.unified_client import UnifiedDataClient  # noqa: E402


def _client_with_theta(side_effect=None, return_value=None) -> UnifiedDataClient:
    """Build a UnifiedDataClient with a mocked _theta whose
    get_expirations either raises (side_effect) or returns
    (return_value)."""
    client = UnifiedDataClient()
    mock_theta = MagicMock()
    if side_effect is not None:
        mock_theta.get_expirations.side_effect = side_effect
    else:
        mock_theta.get_expirations.return_value = return_value
    client._theta = mock_theta
    return client


# ─────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────

def test_returns_underlying_list_when_succeeds():
    expected = ["2026-05-01", "2026-05-08", "2026-05-15"]
    client = _client_with_theta(return_value=expected)
    result = client.get_expirations("SPY")
    assert result == expected


def test_returned_list_is_sorted_ascending():
    """Even if the underlying client returns unsorted, the wrapper sorts."""
    unsorted = ["2026-05-15", "2026-05-01", "2026-05-08"]
    client = _client_with_theta(return_value=unsorted)
    result = client.get_expirations("SPY")
    assert result == ["2026-05-01", "2026-05-08", "2026-05-15"]


# ─────────────────────────────────────────────────────────────────
# Fail-safe paths
# ─────────────────────────────────────────────────────────────────

def test_returns_empty_when_underlying_raises():
    client = _client_with_theta(side_effect=RuntimeError("ThetaData down"))
    result = client.get_expirations("SPY")
    assert result == []


def test_returns_empty_when_underlying_returns_none():
    client = _client_with_theta(return_value=None)
    result = client.get_expirations("SPY")
    assert result == []


def test_returns_empty_when_underlying_returns_empty_list():
    client = _client_with_theta(return_value=[])
    result = client.get_expirations("SPY")
    assert result == []


def test_exception_path_logs_warning(caplog):
    caplog.set_level(logging.WARNING, logger="options-bot.data.unified_client")
    client = _client_with_theta(side_effect=RuntimeError("ThetaData down"))
    client.get_expirations("SPY")
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("get_expirations failed for SPY" in r.getMessage() for r in warns), (
        f"expected a warning mentioning the failure, got: "
        f"{[r.getMessage() for r in warns]}"
    )


# ─────────────────────────────────────────────────────────────────
# Lazy theta init
# ─────────────────────────────────────────────────────────────────

def test_lazy_theta_init_when_none(monkeypatch):
    """If self._theta is None on entry, the wrapper constructs a fresh
    ThetaSnapshotClient. We patch the class so no real client is built."""
    fake_theta = MagicMock()
    fake_theta.get_expirations.return_value = ["2026-05-01"]

    import data.unified_client as uc
    monkeypatch.setattr(uc, "ThetaSnapshotClient", lambda: fake_theta)

    client = UnifiedDataClient()
    assert client._theta is None  # confirm starting state
    result = client.get_expirations("SPY")
    assert result == ["2026-05-01"]
    assert client._theta is fake_theta
