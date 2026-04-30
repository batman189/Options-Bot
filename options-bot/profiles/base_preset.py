"""Phase 1a preset base class.

Defines the abstract contract every Phase 1a preset must implement
(swing, 0dte_asymmetric, future presets). The orchestrator calls
methods in this order:

    1. is_active_now()  — quick gate (time of day, regime)
    2. evaluate_entry() — preset-specific entry conditions
    3. select_contract() — strike / DTE / liquidity selection
    4. can_enter()      — wraps cap_check.evaluate
    5. evaluate_exit()  — for each open position, every cycle

Coexists with profiles/base_profile.py (the legacy interface) during
the transition. The two files have overlapping dataclass names
(EntryDecision, ExitDecision) but live in different modules, so
imports are unambiguous as long as callers reference the full path.
profiles/__init__.py re-exports neither.

The module's dataclasses live alongside the abstract class for
cohesion — every consumer of BasePreset also consumes these
shapes, and splitting them across files would only force more
imports for no benefit. They are stdlib dataclasses (frozen=True),
not Pydantic models — they're internal runtime types, not user-
facing schemas.

See ARCHITECTURE.md sections 2-4.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, final

from market.context import MarketSnapshot
from profiles.profile_config import ProfileConfig
from scanner.setups import SetupScore
from sizing.cap_check import (
    CapCheckRequest,
    CapCheckResult,
    evaluate,
)


# ─────────────────────────────────────────────────────────────────
# Decision / state dataclasses
# ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EntryDecision:
    """Preset's verdict on whether to enter a trade.

    Direction values: "bullish", "bearish", "neutral", or None.
    These match the scanner's SetupScore.direction vocabulary.
    Translation to call/put happens at contract selection
    (select_contract), where the option-side choice actually lives.
    Callers that branch on direction MUST check should_enter first.
    """
    should_enter: bool
    reason: str
    direction: Optional[str] = None


@dataclass(frozen=True)
class ExitDecision:
    """Preset's verdict on whether to exit an open position.

    reason is a short stable token (e.g. "trailing_stop",
    "thesis_break", "dte_floor") that gets persisted as the
    trade's exit_reason for analytics.
    """
    should_exit: bool
    reason: str


@dataclass(frozen=True)
class ContractSelection:
    """Concrete contract the preset wants to trade.

    estimated_premium is per-share (multiply by 100 for the
    dollar cost of one contract). target_delta is the delta the
    preset aimed for, recorded for logging — it may diverge from
    the contract's actual delta after slippage.
    """
    symbol: str
    right: str
    strike: float
    expiration: date
    target_delta: float
    estimated_premium: float
    dte: int


@dataclass(frozen=True)
class ProfileState:
    """Snapshot of profile-level state at evaluation time.

    The caller is responsible for accuracy. Stale or incorrect
    values produce wrong decisions silently.

    today_account_pnl_pct sign convention: negative = loss
    (matches the cap_check convention).

    recent_exits_by_symbol is a dict from symbol -> last exit
    datetime, used by per-symbol cooldowns. The frozen dataclass
    cannot prevent mutation of the dict itself; treat as
    read-only by convention.

    thesis_break_streaks is a dict from trade_id -> consecutive
    cycles of thesis-break candidate signal. Used by presets that
    require multi-cycle confirmation of directional reversal (per
    ARCHITECTURE.md §4.1's swing thesis-break definition). The
    frozen dataclass cannot prevent mutation of the dict itself;
    the orchestrator updates it each cycle.
    """
    current_open_positions: int
    current_capital_deployed: float
    today_account_pnl_pct: float
    last_exit_at: Optional[datetime]
    last_entry_at: Optional[datetime]
    recent_exits_by_symbol: dict[str, datetime] = field(default_factory=dict)
    thesis_break_streaks: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class OptionContract:
    """One option contract within a chain.

    bid / ask / mid are per-share. open_interest and volume may
    be 0 if the data feed didn't populate them; the wire-in
    adapter is responsible for sane defaults.
    """
    symbol: str
    right: str
    strike: float
    expiration: date
    bid: float
    ask: float
    mid: float
    delta: float
    iv: float
    open_interest: int
    volume: int


@dataclass(frozen=True)
class OptionChain:
    """Minimal option-chain shape the contract selector needs.

    The data-layer adapter (built later when the existing
    data/unified_client is wired in) is responsible for producing
    OptionChain instances. Presets read .contracts and apply
    their own filters (delta target, DTE window, liquidity gates).

    contracts is a list — the frozen dataclass cannot prevent
    mutation; treat as read-only by convention.
    """
    symbol: str
    underlying_price: float
    contracts: list[OptionContract]
    snapshot_time: datetime


@dataclass(frozen=True)
class Position:
    """Snapshot of an open position. Frozen — orchestrator constructs
    a new Position each scan cycle with updated peak_premium_per_share
    and current_premium_per_share rather than mutating in place.

    Pricing convention: all premium fields are PER-SHARE in dollars,
    matching the convention used by cap_check and ContractSelection
    elsewhere in the codebase. Multiply by 100 to get per-contract
    cost. The option side (call/put) is read from contract.right —
    there is no separate `side` field on Position to avoid duplication.
    """
    trade_id: str
    symbol: str
    contract: ContractSelection
    entry_time: datetime
    entry_premium_per_share: float
    peak_premium_per_share: float
    current_premium_per_share: float
    contracts: int

    def __post_init__(self):
        if self.entry_time.tzinfo is None:
            raise ValueError("Position.entry_time must be timezone-aware")
        if self.contracts <= 0:
            raise ValueError("Position.contracts must be > 0")
        if self.entry_premium_per_share <= 0:
            raise ValueError("Position.entry_premium_per_share must be > 0")
        if self.peak_premium_per_share <= 0:
            raise ValueError("Position.peak_premium_per_share must be > 0")
        if self.current_premium_per_share < 0:
            raise ValueError("Position.current_premium_per_share must be >= 0")


# ─────────────────────────────────────────────────────────────────
# Abstract base class
# ─────────────────────────────────────────────────────────────────


class BasePreset(ABC):
    """Abstract base class for all Phase 1a presets.

    Subclasses MUST set:
      - name: str (e.g. "swing", "0dte_asymmetric")
      - accepted_setup_types: frozenset[str]

    Subclasses MAY override:
      - is_active_now()

    The accepted_setup_types frozenset is class-level, not
    instance-level. Two profiles that share the same preset class
    on different symbols share the same setup types — intentional,
    since presets are uniform across symbols.

    is_active_now defaults to True. Presets with time gates
    (e.g. 0dte_asymmetric only fires 9:35-13:30 ET) MUST override,
    or they will be considered active 24/7.
    """

    name: str = ""
    accepted_setup_types: frozenset[str] = frozenset()

    def __init__(self, config: ProfileConfig):
        if not self.name:
            raise ValueError(
                f"{type(self).__name__}.name not set — "
                "subclass must define"
            )
        if not self.accepted_setup_types:
            raise ValueError(
                f"{type(self).__name__}.accepted_setup_types not set — "
                "subclass must define"
            )
        self.config = config
        self._logger = logging.getLogger(
            f"options-bot.profiles.{self.name}"
        )

    def is_active_now(self, market: MarketSnapshot) -> bool:
        """Default: always active. Returning False short-circuits
        the entry pipeline before evaluate_entry is called.
        """
        return True

    @abstractmethod
    def evaluate_entry(
        self,
        symbol: str,
        scanner_output: SetupScore,
        market: MarketSnapshot,
        state: ProfileState,
    ) -> EntryDecision:
        """Decide whether to enter based on preset-specific rules.

        Returns EntryDecision with should_enter and a human-
        readable reason. Direction is "call" or "put" when
        entering, None otherwise.
        """

    @abstractmethod
    def select_contract(
        self,
        symbol: str,
        direction: str,
        chain: OptionChain,
    ) -> Optional[ContractSelection]:
        """Pick the specific contract to trade.

        Returns None if no contract in the chain meets the
        preset's strike / DTE / liquidity requirements. The
        orchestrator treats None as "block this entry, no
        contract qualifies".
        """

    @abstractmethod
    def evaluate_exit(
        self,
        position: Position,
        current_quote: float,
        market: MarketSnapshot,
        setups: list[SetupScore],
        state: ProfileState,
    ) -> ExitDecision:
        """Decide whether to exit an open position.

        Called for every open position every cycle. `position` is a
        frozen Position snapshot built by the orchestrator with the
        latest peak_premium_per_share and current_premium_per_share
        values; the option side is read from position.contract.right.
        `current_quote` is the orchestrator's per-cycle quote (per-share);
        in normal operation it equals position.current_premium_per_share
        but the parameter is preserved so a preset can cross-check.

        `setups` is the full SetupScore list for position.symbol this
        cycle — used by presets implementing thesis-break per §4.1
        (which requires checking the symbol's full directional signal
        set, not just one setup).

        `state` is the profile state, including thesis_break_streaks
        for cross-cycle streak tracking (the orchestrator updates the
        per-trade-id counter between calls).

        The reason string is persisted as the trade's exit_reason for
        analytics; use stable tokens (no f-strings).
        """

    @final
    def can_enter(
        self,
        entry_decision: EntryDecision,
        contract: ContractSelection,
        state: ProfileState,
        proposed_contracts: int,
    ) -> CapCheckResult:
        """Run cap_check given a positive entry decision and a
        selected contract. Convenience wrapper.

        Marked @final; subclasses must not override — this is the
        cap enforcement boundary.

        Returns a rejecting CapCheckResult if entry_decision was
        negative (defensive — caller should not have called this
        in that case).
        """
        if not entry_decision.should_enter:
            return CapCheckResult(
                approved=False,
                approved_contracts=0,
                block_reason=(
                    "can_enter called with negative entry_decision: "
                    f"{entry_decision.reason}"
                ),
                notes=[],
            )

        request = CapCheckRequest(
            config=self.config,
            proposed_contracts=proposed_contracts,
            contract_premium=contract.estimated_premium,
            current_open_positions=state.current_open_positions,
            current_capital_deployed=state.current_capital_deployed,
            today_account_pnl_pct=state.today_account_pnl_pct,
        )
        return evaluate(request)
