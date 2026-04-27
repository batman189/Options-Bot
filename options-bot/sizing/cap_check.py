"""Phase 1a sizing cap-check.

Replaces the legacy sizing/sizer.py in the new architecture.
The legacy sizer computed contract counts from drawdown halvings,
confidence multipliers, and PDT reservations. The new model
puts sizing decisions in the user's hands (max_contracts_per_trade,
max_concurrent_positions, max_capital_deployed are profile fields)
and the bot's job is only to enforce that proposed trades fit
within those caps and a daily account circuit breaker.

Coexists with sizing/sizer.py during the transition. A later
prompt will wire this into the strategy runtime and migrate the
legacy sizer to docs/legacy/. See ARCHITECTURE.md sections 3
and 7.

Order of checks (first failure wins; capital cap reduces rather
than rejects when at least one contract still fits):

  1. profile_disabled            -- config.enabled is False
  2. circuit_breaker_tripped     -- breaker enabled and loss hits threshold
  3. max_concurrent_positions    -- already at the position cap
  4. invalid_proposed_contracts  -- proposed <= 0
     (otherwise reduce to max_contracts_per_trade if needed)
  5. max_capital_deployed_reached / cannot_fit_one_contract
     (otherwise reduce to fit remaining capital if needed)
  6. approve

The cap-check is intentionally narrow:

  - Does NOT consider liquidity, IV, regime, or any market state.
    Those are entry-condition concerns handled elsewhere.
  - Does NOT open the database, network, or filesystem.
  - Does NOT call into the legacy sizer or any strategy runtime.

The caller is responsible for passing accurate state
(current_open_positions, current_capital_deployed,
today_account_pnl_pct). Wrong inputs produce wrong decisions.

Float arithmetic in the capital-ceiling step rounds to cents
to avoid spurious ceiling rejections from accumulated rounding
error.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from profiles.profile_config import ProfileConfig

logger = logging.getLogger("options-bot.sizing.cap_check")


@dataclass(frozen=True)
class CapCheckRequest:
    """Inputs for one cap-check evaluation.

    contract_premium is per-share. Multiply by 100 to get the
    dollar cost of one contract -- the cap-check applies the
    multiplier itself. Callers MUST NOT pre-multiply by 100.

    today_account_pnl_pct sign convention: negative numbers mean
    the account is down. A 12% loss is passed as -12.0, not
    +12.0. The breaker fires when pnl_pct <= -threshold.

    current_capital_deployed and current_open_positions are inputs
    from the caller, not computed here. Wrong inputs produce wrong
    decisions.
    """
    config: ProfileConfig
    proposed_contracts: int
    contract_premium: float
    current_open_positions: int
    current_capital_deployed: float
    today_account_pnl_pct: float


@dataclass(frozen=True)
class CapCheckResult:
    """Outcome of a cap-check evaluation.

    The dataclass is frozen, but the notes list is a mutable
    collection -- callers can technically append to it. Treat as
    read-only by convention.
    """
    approved: bool
    approved_contracts: int
    block_reason: str
    notes: list[str] = field(default_factory=list)


def _reject(reason: str, notes: list[str]) -> CapCheckResult:
    logger.info("cap_check rejected: %s", reason)
    return CapCheckResult(
        approved=False,
        approved_contracts=0,
        block_reason=reason,
        notes=notes,
    )


def evaluate(request: CapCheckRequest) -> CapCheckResult:
    """Run the cap-check checks in order.

    Returns approve/reject + the final contract count to trade.
    First failure wins -- callers wanting all rejection reasons
    would need to extend this.
    """
    cfg = request.config
    notes: list[str] = []

    # Step 1: profile enabled
    if not cfg.enabled:
        return _reject("profile_disabled", notes)

    # Step 2: circuit breaker
    if cfg.circuit_breaker_enabled:
        threshold = cfg.circuit_breaker_threshold_pct
        if request.today_account_pnl_pct <= -threshold:
            reason = (
                f"circuit_breaker_tripped: account down "
                f"{abs(request.today_account_pnl_pct):.1f}% "
                f"(threshold {threshold:.1f}%)"
            )
            return _reject(reason, notes)

    # Step 3: position count ceiling
    if request.current_open_positions >= cfg.max_concurrent_positions:
        reason = (
            f"max_concurrent_positions_reached: "
            f"{request.current_open_positions}/"
            f"{cfg.max_concurrent_positions} positions open"
        )
        return _reject(reason, notes)

    # Step 4: per-trade contract cap
    proposed = request.proposed_contracts
    if proposed <= 0:
        return _reject(
            f"invalid_proposed_contracts: proposed={proposed}",
            notes,
        )

    contracts = min(proposed, cfg.max_contracts_per_trade)
    if contracts < proposed:
        note = (
            f"reduced {proposed}->{contracts} per "
            "max_contracts_per_trade"
        )
        notes.append(note)
        logger.info("cap_check: %s", note)

    # Step 5: capital ceiling
    cost_per_contract = round(request.contract_premium * 100, 2)
    proposed_cost = round(contracts * cost_per_contract, 2)
    remaining_capital = round(
        cfg.max_capital_deployed - request.current_capital_deployed,
        2,
    )

    if remaining_capital <= 0:
        reason = (
            f"max_capital_deployed_reached: "
            f"${request.current_capital_deployed:.2f} deployed of "
            f"${cfg.max_capital_deployed:.2f} limit"
        )
        return _reject(reason, notes)

    if proposed_cost > remaining_capital:
        if cost_per_contract <= 0:
            # Defensive: zero/negative premium can't fit anywhere.
            reason = (
                f"cannot_fit_one_contract: "
                f"cost=${cost_per_contract:.2f} "
                f"remaining=${remaining_capital:.2f}"
            )
            return _reject(reason, notes)

        contracts_that_fit = math.floor(
            remaining_capital / cost_per_contract
        )
        if contracts_that_fit < 1:
            reason = (
                f"cannot_fit_one_contract: "
                f"cost=${cost_per_contract:.2f} "
                f"remaining=${remaining_capital:.2f}"
            )
            return _reject(reason, notes)

        prev = contracts
        contracts = contracts_that_fit
        note = (
            f"reduced {prev}->{contracts} to fit "
            "max_capital_deployed"
        )
        notes.append(note)
        logger.info("cap_check: %s", note)

    return CapCheckResult(
        approved=True,
        approved_contracts=contracts,
        block_reason="",
        notes=notes,
    )
