"""Unit tests for the new Phase 1a profile config schema.

Pure Pydantic validation — no DB, no network, no filesystem.
The new schema is independent of the legacy hardcoded profile
classes; these tests verify both the validation rules and that
independence.

Run via:
    python -m pytest tests/test_profile_config.py -v

This file is pytest-style. The repo's other test file
(test_pipeline_trace.py) is a custom runnable script using
check()/section() helpers; that file remains unchanged.
"""

import logging
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from profiles.profile_config import ProfileConfig  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

MIN_VALID = {
    "name": "test",
    "preset": "swing",
    "symbols": ["SPY"],
    "max_capital_deployed": 5000.0,
}


def _make(**overrides) -> ProfileConfig:
    """Build a ProfileConfig from MIN_VALID with overrides."""
    return ProfileConfig(**{**MIN_VALID, **overrides})


# ─────────────────────────────────────────────────────────────────
# Construction tests
# ─────────────────────────────────────────────────────────────────

def test_construct_minimum_valid():
    cfg = _make()
    assert cfg.name == "test"
    assert cfg.preset == "swing"
    assert cfg.symbols == ["SPY"]
    assert cfg.max_capital_deployed == 5000.0


def test_construct_full_config():
    cfg = ProfileConfig(
        name="my_profile",
        preset="0dte_asymmetric",
        symbols=["SPY", "QQQ"],
        mode="signal_only",
        max_contracts_per_trade=5,
        max_concurrent_positions=10,
        max_capital_deployed=50_000.0,
        hard_contract_loss_pct=50.0,
        circuit_breaker_enabled=True,
        circuit_breaker_threshold_pct=15.0,
        discord_webhook_url="https://discord.com/api/webhooks/123/abc",
        enabled=False,
    )
    assert cfg.preset == "0dte_asymmetric"
    assert cfg.circuit_breaker_enabled is True
    assert cfg.discord_webhook_url == "https://discord.com/api/webhooks/123/abc"
    assert cfg.enabled is False


def test_defaults_match_architecture_doc():
    cfg = _make()
    assert cfg.mode == "signal_only"
    assert cfg.max_contracts_per_trade == 1
    assert cfg.max_concurrent_positions == 3
    assert cfg.hard_contract_loss_pct == 60.0
    assert cfg.circuit_breaker_enabled is False
    assert cfg.circuit_breaker_threshold_pct == 10.0
    assert cfg.discord_webhook_url is None
    assert cfg.enabled is True


# ─────────────────────────────────────────────────────────────────
# name validation
# ─────────────────────────────────────────────────────────────────

def test_name_rejects_empty():
    with pytest.raises(ValidationError):
        _make(name="")


def test_name_rejects_too_long():
    with pytest.raises(ValidationError):
        _make(name="a" * 65)


def test_name_rejects_spaces():
    with pytest.raises(ValidationError):
        _make(name="my profile")


def test_name_rejects_special_chars():
    with pytest.raises(ValidationError):
        _make(name="my/profile")


def test_name_accepts_underscore_and_hyphen():
    cfg = _make(name="my_profile-v2")
    assert cfg.name == "my_profile-v2"


# ─────────────────────────────────────────────────────────────────
# preset validation
# ─────────────────────────────────────────────────────────────────

def test_preset_accepts_swing():
    assert _make(preset="swing").preset == "swing"


def test_preset_accepts_0dte_asymmetric():
    assert _make(preset="0dte_asymmetric").preset == "0dte_asymmetric"


def test_preset_rejects_scalp():
    with pytest.raises(ValidationError):
        _make(preset="scalp")


def test_preset_rejects_momentum():
    with pytest.raises(ValidationError):
        _make(preset="momentum")


def test_preset_rejects_empty():
    with pytest.raises(ValidationError):
        _make(preset="")


# ─────────────────────────────────────────────────────────────────
# symbols validation
# ─────────────────────────────────────────────────────────────────

def test_symbols_rejects_empty_list():
    with pytest.raises(ValidationError):
        _make(symbols=[])


def test_symbols_rejects_too_many():
    with pytest.raises(ValidationError):
        _make(symbols=[f"SY{i}" for i in range(21)])


def test_symbols_uppercases_lowercase_input():
    cfg = _make(symbols=["spy", "Tsla"])
    assert cfg.symbols == ["SPY", "TSLA"]


def test_symbols_accepts_basic_tickers():
    cfg = _make(symbols=["SPY", "TSLA", "AAPL"])
    assert cfg.symbols == ["SPY", "TSLA", "AAPL"]


def test_symbols_rejects_digits():
    with pytest.raises(ValidationError):
        _make(symbols=["TSLA1"])


def test_symbols_rejects_too_long_ticker():
    with pytest.raises(ValidationError):
        _make(symbols=["TOOLONG"])


# ─────────────────────────────────────────────────────────────────
# mode validation
# ─────────────────────────────────────────────────────────────────

def test_mode_accepts_signal_only():
    assert _make(mode="signal_only").mode == "signal_only"


def test_mode_accepts_execution():
    assert _make(mode="execution").mode == "execution"


@pytest.mark.parametrize("bad", ["live", "shadow", "signal_mode", "off", ""])
def test_mode_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        _make(mode=bad)


# ─────────────────────────────────────────────────────────────────
# numeric range validation
# ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [0, -1, 101])
def test_max_contracts_per_trade_rejects_out_of_range(bad):
    with pytest.raises(ValidationError):
        _make(max_contracts_per_trade=bad)


def test_max_capital_deployed_required():
    with pytest.raises(ValidationError):
        ProfileConfig(name="t", preset="swing", symbols=["SPY"])


def test_max_capital_deployed_rejects_below_floor():
    with pytest.raises(ValidationError):
        _make(max_capital_deployed=50.0)


def test_max_capital_deployed_rejects_above_ceiling():
    with pytest.raises(ValidationError):
        _make(max_capital_deployed=2_000_000.0)


def test_max_capital_deployed_accepts_5000():
    assert _make(max_capital_deployed=5000.0).max_capital_deployed == 5000.0


def test_hard_contract_loss_pct_rejects_negative():
    with pytest.raises(ValidationError):
        _make(hard_contract_loss_pct=-1)


def test_hard_contract_loss_pct_rejects_above_100():
    with pytest.raises(ValidationError):
        _make(hard_contract_loss_pct=101)


def test_hard_contract_loss_pct_accepts_60():
    assert _make(hard_contract_loss_pct=60.0).hard_contract_loss_pct == 60.0


def test_circuit_breaker_threshold_rejects_below_5():
    with pytest.raises(ValidationError):
        _make(circuit_breaker_threshold_pct=4.9)


def test_circuit_breaker_threshold_rejects_above_25():
    with pytest.raises(ValidationError):
        _make(circuit_breaker_threshold_pct=25.1)


def test_circuit_breaker_threshold_accepts_10():
    assert _make(circuit_breaker_threshold_pct=10.0).circuit_breaker_threshold_pct == 10.0


# ─────────────────────────────────────────────────────────────────
# discord_webhook_url validation
# ─────────────────────────────────────────────────────────────────

def test_webhook_accepts_none():
    assert _make().discord_webhook_url is None


def test_webhook_accepts_valid_discord_url():
    url = "https://discord.com/api/webhooks/123456/abc-token_xyz"
    assert _make(discord_webhook_url=url).discord_webhook_url == url


def test_webhook_accepts_discordapp_legacy_domain():
    url = "https://discordapp.com/api/webhooks/123/abc"
    assert _make(discord_webhook_url=url).discord_webhook_url == url


def test_webhook_rejects_non_discord_host():
    with pytest.raises(ValidationError):
        _make(discord_webhook_url="https://example.com/webhook")


def test_webhook_rejects_http_not_https():
    with pytest.raises(ValidationError):
        _make(discord_webhook_url="http://discord.com/api/webhooks/123/abc")


# ─────────────────────────────────────────────────────────────────
# Behavior tests
# ─────────────────────────────────────────────────────────────────

def test_execution_mode_emits_warning(caplog):
    caplog.set_level(logging.WARNING, logger="profiles.profile_config")
    cfg = _make(mode="execution")
    assert cfg.mode == "execution"
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("execution" in r.getMessage() for r in warns), (
        f"expected an execution-mode warning, got: {[r.getMessage() for r in warns]}"
    )


def test_signal_only_mode_emits_no_warning(caplog):
    caplog.set_level(logging.WARNING, logger="profiles.profile_config")
    _make()  # default mode is signal_only
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert not warns, f"unexpected warnings: {[r.getMessage() for r in warns]}"


def test_round_trip_json():
    original = _make(symbols=["SPY", "QQQ"], max_contracts_per_trade=3)
    payload = original.model_dump_json()
    restored = ProfileConfig.model_validate_json(payload)
    assert restored == original


# ─────────────────────────────────────────────────────────────────
# Integration with existing infra (independence checks)
# ─────────────────────────────────────────────────────────────────

def test_module_does_not_reference_legacy_profile_classes():
    """profile_config must stand alone — no imports of legacy
    hardcoded profile modules."""
    import profiles.profile_config as pc
    text = Path(pc.__file__).read_text(encoding="utf-8")
    for legacy in ("profiles.swing", "profiles.momentum",
                   "profiles.scalp_0dte", "profiles.catalyst",
                   "profiles.mean_reversion", "profiles.tsla_swing",
                   "from .swing", "from .momentum", "from .scalp_0dte"):
        assert legacy not in text, (
            f"profile_config.py must not reference {legacy}"
        )


def test_module_does_not_touch_db():
    """Construction must not open or import any database layer."""
    import profiles.profile_config as pc
    text = Path(pc.__file__).read_text(encoding="utf-8")
    for forbidden in ("sqlite", "aiosqlite", "backend.database"):
        assert forbidden not in text, (
            f"profile_config.py must not reference {forbidden}"
        )
