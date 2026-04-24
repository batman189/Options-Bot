"""Execution-mode endpoint.

Reports the process-wide EXECUTION_MODE set from config.py. The UI
polls this at app load and renders a banner / tag on every page so
an operator glancing at the dashboard cannot miss that shadow mode
is active. The mode is immutable within the lifetime of this
process — switching requires setting the env var and restarting.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

import config

logger = logging.getLogger("options-bot.routes.execution")
router = APIRouter(prefix="/api/execution", tags=["Execution"])


class ExecutionMode(BaseModel):
    """Process-wide execution mode state."""

    mode: str = Field(description="Either 'live' or 'shadow'.")
    slippage_pct: float = Field(
        description=(
            "Synthetic-fill slippage applied when mode=shadow. "
            "Ignored in live mode (reported for transparency)."
        ),
    )


@router.get("/mode", response_model=ExecutionMode)
async def get_execution_mode() -> ExecutionMode:
    """Current execution mode. UI caches the result for the session.

    Shadow Mode: the UI must render a prominent banner when this
    returns mode='shadow'. See ui/src/components/ExecutionModeBanner.tsx.
    """
    return ExecutionMode(
        mode=config.EXECUTION_MODE,
        slippage_pct=config.SHADOW_FILL_SLIPPAGE_PCT,
    )
