"""Pydantic schemas for the Perplexity response.

Anything that fails these validators is discarded — no regex fallback, no
"best effort" parsing. The goal is a strict contract: if the LLM can't
produce data that fits, we drop the call and let the bot continue on stale
state. See allowlists.py for post-validation gates (impact downgrade,
symbol/URL filtering).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


EventType = Literal[
    "FOMC", "CPI", "PPI", "NFP", "GDP", "PCE", "POWELL_SPEECH",
    "EARNINGS", "OTHER",
]
ImpactLevel = Literal["HIGH", "MEDIUM", "LOW"]
Direction = Literal["bullish", "bearish", "neutral"]
RiskTone = Literal["risk_on", "risk_off", "mixed", "unknown"]


class EventItem(BaseModel):
    """A scheduled macro or earnings event."""
    symbol: str = Field(min_length=1, max_length=10)
    event_type: EventType
    event_time_et: datetime
    impact_level: ImpactLevel
    source_url: HttpUrl

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class CatalystItem(BaseModel):
    """A breaking/recent observation with a decay clock."""
    symbol: str = Field(min_length=1, max_length=10)
    catalyst_type: str = Field(min_length=1, max_length=50)
    direction: Direction
    severity: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class RegimeSummary(BaseModel):
    """Current market risk tone — single row in macro_regime."""
    risk_tone: RiskTone
    vix_context: str = Field(default="", max_length=200)
    major_themes: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("major_themes")
    @classmethod
    def _trim_themes(cls, v: list[str]) -> list[str]:
        return [t[:100] for t in v if t and t.strip()]


class MacroPayload(BaseModel):
    """Top-level envelope returned by the Perplexity call."""
    events: list[EventItem] = Field(default_factory=list)
    catalysts: list[CatalystItem] = Field(default_factory=list)
    regime: RegimeSummary
