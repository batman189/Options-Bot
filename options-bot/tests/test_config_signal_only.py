"""Tests for the EXECUTION_MODE validation in config.py.

C5a (foundation prompt) — verifies the new "signal_only" value is
accepted alongside "live" and "shadow", and that invalid values
still raise ValueError.

The config module reads EXECUTION_MODE at import time, so each test
sets the env var, then reloads the config module via importlib.

Run via:
    python -m pytest tests/test_config_signal_only.py -v
"""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _restore_execution_mode_after_test():
    """Snapshot and restore config.EXECUTION_MODE around every test in
    this file. Tests that intentionally invalidate it
    (test_execution_mode_empty_raises_value_error,
    test_execution_mode_invalid_raises_value_error) leave the
    module-level constant polluted because config.py:40 assigns the
    new value BEFORE config.py:41 raises. This fixture restores the
    snapshot so the rest of the test suite isn't affected by the
    pollution. See PHASE_1A_FOLLOWUPS.md
    "test_config_signal_only EXECUTION_MODE pollution".
    """
    import config
    snapshot = config.EXECUTION_MODE
    yield
    config.EXECUTION_MODE = snapshot


def _reload_config(monkeypatch, mode_value: str):
    """Set EXECUTION_MODE to mode_value and reload the config module.

    Returns the reloaded config module on success; the caller asserts
    on the EXECUTION_MODE constant. Failures (invalid mode) raise
    ValueError during reload — caller wraps in pytest.raises.
    """
    monkeypatch.setenv("EXECUTION_MODE", mode_value)
    if "config" in sys.modules:
        return importlib.reload(sys.modules["config"])
    import config  # noqa: F401 — first-time import path
    return sys.modules["config"]


def test_execution_mode_signal_only_accepted(monkeypatch):
    cfg = _reload_config(monkeypatch, "signal_only")
    assert cfg.EXECUTION_MODE == "signal_only"


def test_execution_mode_live_still_accepted(monkeypatch):
    cfg = _reload_config(monkeypatch, "live")
    assert cfg.EXECUTION_MODE == "live"


def test_execution_mode_shadow_still_accepted(monkeypatch):
    cfg = _reload_config(monkeypatch, "shadow")
    assert cfg.EXECUTION_MODE == "shadow"


def test_execution_mode_uppercase_normalized(monkeypatch):
    """config.py applies .lower() to the env var. SIGNAL_ONLY → signal_only."""
    cfg = _reload_config(monkeypatch, "SIGNAL_ONLY")
    assert cfg.EXECUTION_MODE == "signal_only"


def test_execution_mode_invalid_raises_value_error(monkeypatch):
    with pytest.raises(ValueError, match="must be 'live'"):
        _reload_config(monkeypatch, "invalid_mode")


def test_execution_mode_empty_raises_value_error(monkeypatch):
    """Empty env var falls through to default 'live' via os.getenv's
    default arg, which IS valid — verify the actual behavior rather
    than asserting raise. The os.getenv default kicks in only when
    the var is unset, not when it's set to empty string.

    With monkeypatch.setenv('EXECUTION_MODE', ''), os.getenv returns
    '' (not the default). The .lower() preserves it. Validation fails."""
    with pytest.raises(ValueError, match="must be 'live'"):
        _reload_config(monkeypatch, "")
