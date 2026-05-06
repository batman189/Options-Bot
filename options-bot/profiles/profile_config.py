"""Phase 1a profile configuration schema.

This is the new profile config introduced in Phase 1a of the
rebuild (see docs/ARCHITECTURE.md sections 3 and 4). It coexists
with the existing hardcoded profile classes in profiles/ during
the transition; later prompts will wire it into v2_strategy and
the database, retiring the hardcoded classes.

Pydantic v2 schema. Validation is strict — invalid construction
raises ValidationError so the UI / API layer can surface field
errors to the user before anything reaches the runtime.
"""

import logging
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


_SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,5}$")
_DISCORD_URL_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)


class ProfileConfig(BaseModel):
    """User-configurable fields for a single profile.

    Each profile is a mini-bot pinned to one preset (locked
    strategy logic) running on a list of symbols. The fields
    here are the user-controlled knobs; preset-internal logic
    (entry conditions, strike selection, exit thresholds) is
    not exposed in this schema.
    """

    name: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description=(
            "Profile name. Used in URLs and log paths, so "
            "alphanumeric + underscore + hyphen only — no spaces "
            "or special characters."
        ),
    )

    preset: Literal["swing", "0dte_asymmetric"] = Field(
        description=(
            "Strategy template (locked at preset level). Phase 1 "
            "ships swing (multi-day directional) and "
            "0dte_asymmetric (Version B catalyst-gated 0DTE). "
            "Future presets are added by extending the Literal."
        ),
    )

    symbols: list[str] = Field(
        min_length=1,
        max_length=20,
        description=(
            "Tickers this profile trades. Each symbol is "
            "uppercased automatically by the field validator. "
            "Caller is responsible for deduplication — duplicates "
            "are NOT removed by the schema."
        ),
    )

    mode: Literal["signal_only", "execution"] = Field(
        default="signal_only",
        description=(
            "signal_only: Discord notifications, no orders. "
            "execution: real orders submitted to Alpaca. Defaults "
            "to signal_only for safety; switching to execution is "
            "an explicit user action. "
            "Note: runtime-advisory only at present; runtime "
            "authority is config.EXECUTION_MODE (env var). See "
            "PHASE_1_FOLLOWUPS.md \"ProfileConfig.mode field is "
            "advisory at runtime\"."
        ),
    )

    max_contracts_per_trade: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Cap on contracts per single entry order.",
    )

    max_concurrent_positions: int = Field(
        default=3,
        ge=1,
        le=50,
        description="Cap on simultaneous open positions in this profile.",
    )

    max_capital_deployed: float = Field(
        ge=100.0,
        le=1_000_000.0,
        description=(
            "Maximum total dollar exposure across this profile's "
            "open positions. Required field with no default — the "
            "user must explicitly set their per-profile capital "
            "limit. Any UI code that constructs ProfileConfig with "
            "partial data must supply this."
        ),
    )

    hard_contract_loss_pct: float = Field(
        default=60.0,
        ge=0.0,
        le=100.0,
        description=(
            "Hard contract-price stop loss as percent of premium "
            "paid. Used by the swing preset. The 0dte_asymmetric "
            "preset has no contract-price stop (intentional, to "
            "preserve convexity), so this field is present but "
            "ignored at runtime for that preset."
        ),
    )

    circuit_breaker_enabled: bool = Field(
        default=False,
        description=(
            "When True, halts the profile after the daily account-"
            "level loss threshold is hit. Defaults off."
        ),
    )

    circuit_breaker_threshold_pct: float = Field(
        default=10.0,
        ge=5.0,
        le=25.0,
        description=(
            "Daily account-level loss threshold (percent of equity) "
            "at which the circuit breaker fires. Only consulted "
            "when circuit_breaker_enabled is True."
        ),
    )

    discord_webhook_url: Optional[str] = Field(
        default=None,
        description=(
            "Per-profile Discord webhook URL. When None, the "
            "system falls back to the global default. Must be a "
            "Discord-hosted webhook URL (https only)."
        ),
    )

    enabled: bool = Field(
        default=True,
        description=(
            "Master on/off switch. Disabled profiles do not scan, "
            "decide, or trade."
        ),
    )

    @field_validator("symbols")
    @classmethod
    def _normalize_symbols(cls, v: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in v:
            if not isinstance(raw, str):
                raise ValueError(
                    f"symbol must be a string, got {type(raw).__name__}"
                )
            sym = raw.strip().upper()
            if not _SYMBOL_PATTERN.match(sym):
                raise ValueError(
                    f"invalid symbol {raw!r}: must be 1-5 uppercase "
                    "letters (basic ticker format)"
                )
            normalized.append(sym)
        return normalized

    @field_validator("discord_webhook_url")
    @classmethod
    def _check_webhook(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not v.startswith(_DISCORD_URL_PREFIXES):
            raise ValueError(
                "discord_webhook_url must be an https Discord "
                f"webhook URL (must start with one of "
                f"{_DISCORD_URL_PREFIXES})"
            )
        return v

    @model_validator(mode="after")
    def _warn_on_execution_mode(self) -> "ProfileConfig":
        if self.mode == "execution":
            logger.warning(
                "ProfileConfig name=%r constructed with "
                "mode='execution'. Real orders will be placed. "
                "Validate the profile in signal_only mode before "
                "enabling execution.",
                self.name,
            )
        return self
