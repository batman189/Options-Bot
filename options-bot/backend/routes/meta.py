"""Metadata endpoints — UI filter options, constants, reference data.

Prompt 27 Commit A. Single source of truth for filter dropdowns so UI
lists can't drift when new profiles or setup_types are added. The
setup_types and profile_names are computed from profile class
attributes (via profiles.PROFILE_ACCEPTED_SETUP_TYPES) — adding a new
profile class automatically surfaces its name and accepted_setup_types
in this response.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from profiles import PROFILE_ACCEPTED_SETUP_TYPES

logger = logging.getLogger("options-bot.routes.meta")
router = APIRouter(prefix="/api/meta", tags=["Meta"])


# Non-profile sentinel values used in v2_signal_logs.profile_name.
# "scanner" is written by scanner-rejection logs (see Bug D) and
# represents scanner-level evaluations, not a profile. Include so
# UI filters can surface those rows.
_NON_PROFILE_PROFILE_NAME_SENTINELS = ["scanner"]


class FilterOptions(BaseModel):
    """UI filter dropdown options. Computed from the profile classes
    themselves — no hand-rolled lists to drift.
    """
    setup_types: list[str] = Field(
        description=(
            "All setup_types any profile accepts. Union of "
            "profile.accepted_setup_types across all profile classes. "
            "Use for signal-log and trade setup_type filters."
        ),
    )
    profile_names: list[str] = Field(
        description=(
            "All profile class names + non-profile sentinels "
            "('scanner' for scanner-rejection signal-log rows). Use "
            "for signal-log profile_name filter."
        ),
    )


def _compute_filter_options() -> FilterOptions:
    # Union of accepted_setup_types across all profile classes.
    setup_types: set[str] = set()
    for accepted in PROFILE_ACCEPTED_SETUP_TYPES.values():
        setup_types.update(accepted)

    # Profile class names + non-profile sentinels.
    profile_names = sorted(PROFILE_ACCEPTED_SETUP_TYPES.keys())
    profile_names.extend(_NON_PROFILE_PROFILE_NAME_SENTINELS)

    return FilterOptions(
        setup_types=sorted(setup_types),
        profile_names=profile_names,
    )


@router.get("/filter-options", response_model=FilterOptions)
async def get_filter_options() -> FilterOptions:
    """Filter dropdown options for UI. Computed at request time from
    profile class attributes (cheap; no DB read). Frontend caches the
    result with a long stale time — these values don't change without
    a backend restart.
    """
    return _compute_filter_options()
