"""Execution layer — order submission paths.

Currently only exports the shadow-mode simulator. The live path is
Lumibot's submit_order invoked directly from v2_strategy and is not
wrapped here. Adding a LiveExecutor wrapper would be a fine future
refactor but is out of scope for the shadow-mode introduction.
"""

from .shadow_simulator import ShadowSimulator

__all__ = ["ShadowSimulator"]
