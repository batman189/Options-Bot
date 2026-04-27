"""Unit tests for sizing.cap_check.

Pure logic — no DB, no network, no filesystem. Mirrors the
pytest style established in tests/test_profile_config.py
(MIN_VALID + _make/_request helpers, parametrize for ranges).

Run via:
    python -m pytest tests/test_cap_check.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from profiles.profile_config import ProfileConfig  # noqa: E402
from sizing.cap_check import (  # noqa: E402
    CapCheckRequest,
    CapCheckResult,
    evaluate,
)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

MIN_VALID_CONFIG = {
    "name": "test",
    "preset": "swing",
    "symbols": ["SPY"],
    "max_capital_deployed": 5000.0,
}


def _config(**overrides) -> ProfileConfig:
    return ProfileConfig(**{**MIN_VALID_CONFIG, **overrides})


def _request(**overrides) -> CapCheckRequest:
    defaults = {
        "config": _config(),
        "proposed_contracts": 1,
        "contract_premium": 5.00,   # $500 per contract
        "current_open_positions": 0,
        "current_capital_deployed": 0.0,
        "today_account_pnl_pct": 0.0,
    }
    return CapCheckRequest(**{**defaults, **overrides})


# ─────────────────────────────────────────────────────────────────
# Approval path
# ─────────────────────────────────────────────────────────────────

def test_default_request_approves():
    res = evaluate(_request())
    assert res.approved is True
    assert res.approved_contracts == 1
    assert res.block_reason == ""
    assert res.notes == []


def test_approval_returns_full_proposed_count():
    cfg = _config(max_contracts_per_trade=10, max_capital_deployed=100_000.0)
    res = evaluate(_request(config=cfg, proposed_contracts=3))
    assert res.approved is True
    assert res.approved_contracts == 3
    assert res.notes == []


# ─────────────────────────────────────────────────────────────────
# Step 1: profile_enabled
# ─────────────────────────────────────────────────────────────────

def test_disabled_profile_rejects():
    cfg = _config(enabled=False)
    res = evaluate(_request(config=cfg))
    assert res.approved is False
    assert res.approved_contracts == 0
    assert res.block_reason == "profile_disabled"


# ─────────────────────────────────────────────────────────────────
# Step 2: circuit breaker
# ─────────────────────────────────────────────────────────────────

def test_disabled_breaker_ignores_loss():
    res = evaluate(_request(today_account_pnl_pct=-50.0))
    assert res.approved is True


def test_enabled_breaker_loss_above_threshold_rejects():
    cfg = _config(
        circuit_breaker_enabled=True,
        circuit_breaker_threshold_pct=10.0,
    )
    res = evaluate(_request(config=cfg, today_account_pnl_pct=-12.0))
    assert res.approved is False
    assert res.block_reason.startswith("circuit_breaker_tripped:")
    assert "12.0%" in res.block_reason
    assert "10.0%" in res.block_reason


def test_enabled_breaker_loss_equals_threshold_rejects_boundary():
    """Predicate is <=, so exactly -threshold trips the breaker."""
    cfg = _config(
        circuit_breaker_enabled=True,
        circuit_breaker_threshold_pct=10.0,
    )
    res = evaluate(_request(config=cfg, today_account_pnl_pct=-10.0))
    assert res.approved is False
    assert res.block_reason.startswith("circuit_breaker_tripped:")


def test_enabled_breaker_loss_below_threshold_approves():
    cfg = _config(
        circuit_breaker_enabled=True,
        circuit_breaker_threshold_pct=10.0,
    )
    res = evaluate(_request(config=cfg, today_account_pnl_pct=-9.9))
    assert res.approved is True


def test_enabled_breaker_positive_pnl_approves():
    cfg = _config(
        circuit_breaker_enabled=True,
        circuit_breaker_threshold_pct=10.0,
    )
    res = evaluate(_request(config=cfg, today_account_pnl_pct=5.0))
    assert res.approved is True


# ─────────────────────────────────────────────────────────────────
# Step 3: position count ceiling
# ─────────────────────────────────────────────────────────────────

def test_at_max_positions_rejects():
    cfg = _config(max_concurrent_positions=3)
    res = evaluate(_request(config=cfg, current_open_positions=3))
    assert res.approved is False
    assert res.block_reason.startswith("max_concurrent_positions_reached:")
    assert "3/3" in res.block_reason


def test_below_max_positions_approves():
    cfg = _config(max_concurrent_positions=3)
    res = evaluate(_request(config=cfg, current_open_positions=2))
    assert res.approved is True


def test_above_max_positions_rejects_with_actual_count():
    """Defensive: caller passes an inflated count."""
    cfg = _config(max_concurrent_positions=3)
    res = evaluate(_request(config=cfg, current_open_positions=5))
    assert res.approved is False
    assert "5/3" in res.block_reason


# ─────────────────────────────────────────────────────────────────
# Step 4: per-trade contract cap
# ─────────────────────────────────────────────────────────────────

def test_within_max_contracts_approves_full():
    cfg = _config(max_contracts_per_trade=5, max_capital_deployed=100_000.0)
    res = evaluate(_request(config=cfg, proposed_contracts=3))
    assert res.approved is True
    assert res.approved_contracts == 3
    assert res.notes == []


def test_exceeds_max_contracts_reduces_with_note():
    cfg = _config(max_contracts_per_trade=2, max_capital_deployed=100_000.0)
    res = evaluate(_request(config=cfg, proposed_contracts=5))
    assert res.approved is True
    assert res.approved_contracts == 2
    assert any(
        "reduced 5->2 per max_contracts_per_trade" in n
        for n in res.notes
    )


@pytest.mark.parametrize("bad", [0, -1, -100])
def test_invalid_proposed_contracts_rejects(bad):
    res = evaluate(_request(proposed_contracts=bad))
    assert res.approved is False
    assert res.block_reason.startswith("invalid_proposed_contracts:")
    assert f"proposed={bad}" in res.block_reason


# ─────────────────────────────────────────────────────────────────
# Step 5: capital ceiling
# ─────────────────────────────────────────────────────────────────

def test_all_contracts_fit_approves():
    cfg = _config(max_capital_deployed=10_000.0, max_contracts_per_trade=10)
    # 3 * $500 = $1500, well within $10000 limit
    res = evaluate(_request(
        config=cfg,
        proposed_contracts=3,
        contract_premium=5.00,
    ))
    assert res.approved is True
    assert res.approved_contracts == 3
    assert res.notes == []


def test_some_contracts_exceed_capital_reduces():
    cfg = _config(max_capital_deployed=2_500.0, max_contracts_per_trade=10)
    # Want 5 * $500 = $2500. Available: $2500 - $1000 = $1500.
    # 1500 / 500 = 3 contracts fit.
    res = evaluate(_request(
        config=cfg,
        proposed_contracts=5,
        contract_premium=5.00,
        current_capital_deployed=1000.0,
    ))
    assert res.approved is True
    assert res.approved_contracts == 3
    assert any(
        "reduced 5->3 to fit max_capital_deployed" in n
        for n in res.notes
    )


def test_one_contract_does_not_fit_rejects():
    cfg = _config(max_capital_deployed=400.0)
    # $500 contract cost > $400 capital ceiling
    res = evaluate(_request(
        config=cfg,
        proposed_contracts=1,
        contract_premium=5.00,
    ))
    assert res.approved is False
    assert res.block_reason.startswith("cannot_fit_one_contract:")


def test_capital_already_at_max_rejects():
    cfg = _config(max_capital_deployed=5000.0)
    res = evaluate(_request(
        config=cfg,
        current_capital_deployed=5000.0,
    ))
    assert res.approved is False
    assert res.block_reason.startswith("max_capital_deployed_reached:")
    assert "$5000.00" in res.block_reason


def test_capital_near_max_premium_too_high_rejects():
    """$4900 deployed, $100 remaining; $500 contract can't fit."""
    cfg = _config(max_capital_deployed=5000.0)
    res = evaluate(_request(
        config=cfg,
        current_capital_deployed=4900.0,
        contract_premium=5.00,
    ))
    assert res.approved is False
    assert res.block_reason.startswith("cannot_fit_one_contract:")


# ─────────────────────────────────────────────────────────────────
# Reduction stacking (Step 4 + Step 5 both fire)
# ─────────────────────────────────────────────────────────────────

def test_both_caps_reduce_in_order():
    """max_contracts_per_trade reduces 10 -> 5, then capital
    reduces 5 -> 3. Both notes present, in order."""
    cfg = _config(
        max_contracts_per_trade=5,
        max_capital_deployed=2500.0,
    )
    res = evaluate(_request(
        config=cfg,
        proposed_contracts=10,
        contract_premium=5.00,
        current_capital_deployed=1000.0,
    ))
    assert res.approved is True
    assert res.approved_contracts == 3
    assert len(res.notes) == 2
    assert "reduced 10->5 per max_contracts_per_trade" in res.notes[0]
    assert "reduced 5->3 to fit max_capital_deployed" in res.notes[1]


# ─────────────────────────────────────────────────────────────────
# Boundary / off-by-one
# ─────────────────────────────────────────────────────────────────

def test_max_contracts_exactly_equals_proposed_approves_full():
    cfg = _config(max_contracts_per_trade=4, max_capital_deployed=100_000.0)
    res = evaluate(_request(config=cfg, proposed_contracts=4))
    assert res.approved is True
    assert res.approved_contracts == 4
    assert res.notes == []


def test_capital_exactly_equals_max_rejects():
    cfg = _config(max_capital_deployed=5000.0)
    res = evaluate(_request(config=cfg, current_capital_deployed=5000.0))
    assert res.approved is False
    assert res.block_reason.startswith("max_capital_deployed_reached:")


def test_capital_remaining_exactly_one_contract_approves_one():
    """$4500 deployed, $500 remaining; $500 contract fits exactly."""
    cfg = _config(max_capital_deployed=5000.0)
    res = evaluate(_request(
        config=cfg,
        proposed_contracts=1,
        contract_premium=5.00,
        current_capital_deployed=4500.0,
    ))
    assert res.approved is True
    assert res.approved_contracts == 1


# ─────────────────────────────────────────────────────────────────
# Order-of-checks / first-failure-wins
# ─────────────────────────────────────────────────────────────────

def test_disabled_takes_priority_over_breaker():
    cfg = _config(
        enabled=False,
        circuit_breaker_enabled=True,
        circuit_breaker_threshold_pct=10.0,
    )
    res = evaluate(_request(config=cfg, today_account_pnl_pct=-50.0))
    assert res.block_reason == "profile_disabled"


def test_breaker_takes_priority_over_position_cap():
    cfg = _config(
        circuit_breaker_enabled=True,
        circuit_breaker_threshold_pct=10.0,
        max_concurrent_positions=3,
    )
    res = evaluate(_request(
        config=cfg,
        today_account_pnl_pct=-15.0,
        current_open_positions=3,
    ))
    assert res.block_reason.startswith("circuit_breaker_tripped:")


# ─────────────────────────────────────────────────────────────────
# Independence checks
# ─────────────────────────────────────────────────────────────────

def test_module_does_not_reference_legacy_sizer():
    import sizing.cap_check as cc
    text = Path(cc.__file__).read_text(encoding="utf-8")
    for forbidden in ("sizing.sizer", "from .sizer", "import sizer"):
        assert forbidden not in text, (
            f"cap_check.py must not reference {forbidden}"
        )


def test_module_does_not_touch_db():
    import sizing.cap_check as cc
    text = Path(cc.__file__).read_text(encoding="utf-8")
    for forbidden in ("sqlite", "aiosqlite", "backend.database"):
        assert forbidden not in text, (
            f"cap_check.py must not reference {forbidden}"
        )


def test_module_does_not_reference_strategy_or_legacy_profiles():
    import sizing.cap_check as cc
    text = Path(cc.__file__).read_text(encoding="utf-8")
    for forbidden in ("v2_strategy", "profiles.swing",
                      "profiles.scalp_0dte", "profiles.momentum",
                      "profiles.catalyst", "profiles.mean_reversion",
                      "profiles.tsla_swing"):
        assert forbidden not in text, (
            f"cap_check.py must not reference {forbidden}"
        )
