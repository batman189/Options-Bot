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
# to the set of profile CLASS NAMES that a subprocess activates when
# the preset is selected. A preset may activate MULTIPLE classes;
# each class contributes its own accepted_setup_types. This is the
# runtime-authoritative map -- v2_strategy.initialize imports it
# from here, so there is exactly one source of truth.
#
# "scalp" / "0dte_scalp" activate four classes because a scalp
# subprocess watches for fast setups from any angle: scalp_0dte
# handles 0DTE momentum / compression / macro plays; momentum /
# mean_reversion / catalyst handle their respective longer-dated
# setups on the same symbols.
PRESET_PROFILE_MAP: dict[str, frozenset[str]] = {
    "0dte_scalp":     frozenset({"scalp_0dte", "momentum", "mean_reversion", "catalyst"}),
    "scalp":          frozenset({"scalp_0dte", "momentum", "mean_reversion", "catalyst"}),
    "swing":          frozenset({"swing", "momentum"}),
    "momentum":       frozenset({"momentum"}),
    "mean_reversion": frozenset({"mean_reversion"}),
    "catalyst":       frozenset({"catalyst"}),
}

# Symbols that additionally activate tsla_swing when preset == "swing".
# Mirrors v2_strategy.initialize line 180 semantics: `allowed | {"tsla_swing"}`
# for single-name volatile stocks. Kept here so accepted_setup_types_for_preset
# can derive the correct class set without importing v2_strategy.
_TSLA_SWING_SYMBOLS: frozenset[str] = frozenset(
    {"TSLA", "NVDA", "AAPL", "AMZN", "META", "MSFT"}
)


def accepted_setup_types_for_preset(preset: str, symbol: str = "") -> frozenset[str]:
    """Return the UNION of accepted_setup_types across every profile
    class the preset activates.

    S1.1 (Prompt 34): pre-fix returned only the primary profile's
    types, which undercounted multi-class presets. The scalp preset
    activates scalp_0dte + momentum + mean_reversion + catalyst; this
    helper now returns all four classes' setup_types unioned so the
    /api/profiles response and the UI's Learning State panel surface
    every setup_type the subprocess actually trades.

    `symbol` matters only for preset == "swing": TSLA/NVDA/etc.
    additionally activate tsla_swing alongside swing + momentum
    (mirrors v2_strategy.initialize's `allowed | {"tsla_swing"}`).

    Unknown preset returns an empty set rather than raising -- callers
    (e.g. /api/profiles) gracefully fall back to "no learning state
    scoped" rather than crashing.
    """
    classes = set(PRESET_PROFILE_MAP.get(preset, frozenset()))
    if not classes:
        return frozenset()

    if preset == "swing" and symbol in _TSLA_SWING_SYMBOLS:
        classes.add("tsla_swing")

    result: set[str] = set()
    for cls_name in classes:
        result.update(PROFILE_ACCEPTED_SETUP_TYPES.get(cls_name, frozenset()))
    return frozenset(result)
