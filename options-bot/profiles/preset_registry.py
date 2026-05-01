"""BasePreset registry — maps preset name strings to the new
BasePreset subclass that implements them. Used by the orchestrator
wire-in (C5b) to detect 'new' presets vs legacy ones.

Phase 1a contains:
  - "swing" → SwingPreset
  - "0dte_asymmetric" → ZeroDteAsymmetricPreset

Legacy presets (momentum, mean_reversion, catalyst, scalp_0dte,
tsla_swing) are NOT in this registry — they continue to use the
legacy BaseProfile interface.
"""

from __future__ import annotations

from typing import Optional, Type

from profiles.base_preset import BasePreset
from profiles.swing_preset import SwingPreset
from profiles.zero_dte_asymmetric import ZeroDteAsymmetricPreset


PRESET_REGISTRY: dict[str, Type[BasePreset]] = {
    "swing": SwingPreset,
    "0dte_asymmetric": ZeroDteAsymmetricPreset,
}


def is_new_preset(preset_name: str) -> bool:
    """Returns True if preset_name maps to a BasePreset subclass —
    i.e. should run via the new pipeline.
    """
    return preset_name in PRESET_REGISTRY


def get_preset_class(preset_name: str) -> Optional[Type[BasePreset]]:
    """Returns the preset class for instantiation, or None if the
    preset is not in the registry.
    """
    return PRESET_REGISTRY.get(preset_name)
