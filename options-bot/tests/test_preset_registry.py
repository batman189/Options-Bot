"""Unit tests for profiles.preset_registry.

C5a (foundation prompt) — verifies the BasePreset registry maps the
two Phase 1a preset names to their classes, and that legacy presets
are not in the registry.

Run via:
    python -m pytest tests/test_preset_registry.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from profiles.preset_registry import (  # noqa: E402
    PRESET_REGISTRY,
    get_preset_class,
    is_new_preset,
)
from profiles.swing_preset import SwingPreset  # noqa: E402
from profiles.zero_dte_asymmetric import ZeroDteAsymmetricPreset  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# PRESET_REGISTRY contents
# ─────────────────────────────────────────────────────────────────


def test_registry_contains_swing():
    assert PRESET_REGISTRY["swing"] is SwingPreset


def test_registry_contains_zero_dte_asymmetric():
    assert PRESET_REGISTRY["0dte_asymmetric"] is ZeroDteAsymmetricPreset


def test_registry_size_matches_phase_1a_scope():
    """Phase 1a contains exactly two new presets. If this test fails
    after a future preset addition, update the count."""
    assert len(PRESET_REGISTRY) == 2


# ─────────────────────────────────────────────────────────────────
# is_new_preset
# ─────────────────────────────────────────────────────────────────


def test_is_new_preset_swing_true():
    assert is_new_preset("swing") is True


def test_is_new_preset_zero_dte_true():
    assert is_new_preset("0dte_asymmetric") is True


def test_is_new_preset_legacy_momentum_false():
    assert is_new_preset("momentum") is False


def test_is_new_preset_legacy_mean_reversion_false():
    assert is_new_preset("mean_reversion") is False


def test_is_new_preset_legacy_catalyst_false():
    assert is_new_preset("catalyst") is False


def test_is_new_preset_legacy_scalp_0dte_false():
    assert is_new_preset("scalp_0dte") is False


def test_is_new_preset_legacy_tsla_swing_false():
    assert is_new_preset("tsla_swing") is False


def test_is_new_preset_unknown_string_false():
    assert is_new_preset("nonexistent_preset_xyz") is False


def test_is_new_preset_empty_string_false():
    assert is_new_preset("") is False


# ─────────────────────────────────────────────────────────────────
# get_preset_class
# ─────────────────────────────────────────────────────────────────


def test_get_preset_class_swing_returns_class():
    assert get_preset_class("swing") is SwingPreset


def test_get_preset_class_zero_dte_returns_class():
    assert get_preset_class("0dte_asymmetric") is ZeroDteAsymmetricPreset


def test_get_preset_class_legacy_returns_none():
    assert get_preset_class("momentum") is None


def test_get_preset_class_unknown_returns_none():
    assert get_preset_class("nonexistent_preset_xyz") is None
