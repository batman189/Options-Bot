"""Profile package — exposes per-profile accepted_setup_types mapping
computed once from the profile classes themselves (single source of
truth). Prompt 26 surfaced this for the /api/profiles route so the UI
can render per-profile learning state.

Do not hand-maintain a separate dict — the mapping is computed from
the class attributes so adding a new accepted setup_type to a profile
class automatically flows through.
"""


def _compute_profile_accepted_setup_types() -> dict[str, frozenset[str]]:
    """Build {profile.name -> frozenset(accepted_setup_types)} from the
    concrete BaseProfile subclasses. Import happens lazily to avoid
    circular imports if a profile module ever imports from this
    package's __init__.
    """
    # Lazy imports — each class brings in its own module chain.
    from profiles.momentum import MomentumProfile
    from profiles.mean_reversion import MeanReversionProfile
    from profiles.catalyst import CatalystProfile
    from profiles.scalp_0dte import Scalp0DTEProfile
    from profiles.swing import SwingProfile
    from profiles.tsla_swing import TSLASwingProfile

    instances = [
        MomentumProfile(),
        MeanReversionProfile(),
        CatalystProfile(),
        Scalp0DTEProfile(),
        SwingProfile(),
        TSLASwingProfile(),
    ]
    return {p.name: frozenset(p.accepted_setup_types) for p in instances}


#: {profile.name -> accepted_setup_types}. Computed once at import.
#: Profile tests (Section 26) assert this matches instance attrs.
PROFILE_ACCEPTED_SETUP_TYPES: dict[str, frozenset[str]] = (
    _compute_profile_accepted_setup_types()
)


# Preset (the user-facing choice stored in the profiles.preset DB column)
# to the PRIMARY profile class name that represents that preset in the UI.
# A preset may instantiate multiple profile classes at trading time (see
# v2_strategy.initialize PRESET_PROFILE_MAP), but for user-visible
# grouping we collapse to the primary class — the one whose name the UI
# should treat as "this preset's identity." A scalp profile is primarily
# about scalp_0dte trades; a swing profile is primarily about swing.
_PRESET_TO_PRIMARY_PROFILE = {
    "momentum":       "momentum",
    "mean_reversion": "mean_reversion",
    "catalyst":       "catalyst",
    "scalp":          "scalp_0dte",
    "0dte_scalp":     "scalp_0dte",
    "swing":          "swing",
}

# Symbols that use tsla_swing instead of swing. Mirrors
# v2_strategy.initialize logic. Only applies to preset == "swing".
_TSLA_SWING_SYMBOLS = {"TSLA", "NVDA", "AAPL", "AMZN", "META", "MSFT"}


def accepted_setup_types_for_preset(preset: str, symbol: str = "") -> frozenset[str]:
    """Return the accepted_setup_types of the primary profile class for
    a given preset. Used by /api/profiles to scope the Learning State
    panel to just the setup_types this user-facing profile is about.

    symbol matters only for preset="swing": TSLA/NVDA/etc. map to
    tsla_swing rather than swing, per v2_strategy.initialize.
    Unknown preset returns an empty set rather than raising — callers
    can gracefully fall back to "no learning state scoped" rather than
    crashing the /api/profiles endpoint.
    """
    if preset == "swing" and symbol in _TSLA_SWING_SYMBOLS:
        return PROFILE_ACCEPTED_SETUP_TYPES.get("tsla_swing", frozenset())
    primary = _PRESET_TO_PRIMARY_PROFILE.get(preset)
    if primary is None:
        return frozenset()
    return PROFILE_ACCEPTED_SETUP_TYPES.get(primary, frozenset())
