"""Position sizing — confidence-based with compounding halvings.

Pure calculation module. No DB, no API calls, no order submission.
All inputs provided by the integration layer.

Sizing formula (from architecture doc):
  Step 1: base_risk = account_value * 0.04 (4% max risk per trade)
  Step 2: confidence_risk = base_risk * confidence_score
  Step 3: if day down 8% -> halve: confidence_risk * 0.5
  Step 4: if PDT halving -> halve: result * 0.5
  Step 5: contracts = floor(final_risk / premium), minimum 1

Each halving is a separate multiplication applied sequentially.
A trade can be halved twice (8% drawdown + PDT) = 25% of max size.

Account survival rules (hard stops, not configurable):
  - Day down 8%:  halve all sizes for remainder of day
  - Day down 15%: no new entries for remainder of day (returns 0)
  - Down 25% from starting balance: halt all trading (returns 0)
  - Total premium at risk > 20% of account: block entry (returns 0)
"""

import logging
import math
from dataclasses import dataclass

logger = logging.getLogger("options-bot.sizing")

# Fixed constants — not configurable
MAX_RISK_PER_TRADE_PCT = 4.0     # 4% of account per trade
DAY_DRAWDOWN_HALVE_PCT = 8.0     # Halve sizes after 8% daily loss
DAY_DRAWDOWN_HALT_PCT = 15.0     # Stop all entries after 15% daily loss
TOTAL_DRAWDOWN_HALT_PCT = 25.0   # Halt trading after 25% from starting balance
MAX_EXPOSURE_PCT = 20.0          # Total open premium cannot exceed 20% of account


@dataclass
class SizingResult:
    """Output from the sizer with full audit trail."""
    contracts: int
    base_risk: float
    confidence_risk: float
    after_drawdown_halving: float
    after_pdt_halving: float
    final_risk: float
    premium_per_contract: float
    halvings_applied: list[str]
    blocked: bool
    block_reason: str


def calculate(
    account_value: float,
    confidence: float,
    premium: float,
    day_start_value: float,
    starting_balance: float,
    current_exposure: float,
    is_same_day_trade: bool,
    day_trades_remaining: int,
) -> SizingResult:
    """Calculate position size. Returns SizingResult with contract count.

    Args:
        account_value: Current portfolio value right now
        confidence: Scorer confidence (0.0 to 1.0)
        premium: Option mid price from selector (per share, not per contract)
        day_start_value: Account value at market open today
        starting_balance: Account value when bot was first started
        current_exposure: Total premium at risk across all open positions ($)
        is_same_day_trade: True if this would be closed same day (momentum, catalyst)
        day_trades_remaining: PDT day trades left this week (from risk manager)

    Returns:
        SizingResult with contracts >= 0 and full calculation trail.
    """
    halvings = []
    contract_cost = premium * 100  # Each contract = 100 shares

    if contract_cost <= 0:
        logger.warning(f"Sizer: premium={premium} <= 0, returning 0")
        return _blocked("premium is zero or negative", premium)

    # ── SURVIVAL RULE 1: Down 25% from starting balance → halt all ──
    if starting_balance > 0:
        total_dd_pct = ((starting_balance - account_value) / starting_balance) * 100
        if total_dd_pct >= TOTAL_DRAWDOWN_HALT_PCT:
            reason = (f"HALT: account down {total_dd_pct:.1f}% from starting "
                      f"${starting_balance:,.0f} (limit={TOTAL_DRAWDOWN_HALT_PCT}%). "
                      f"Current=${account_value:,.0f}. Manual restart required.")
            logger.critical(reason)
            return _blocked(reason, premium)

    # ── SURVIVAL RULE 2: Down 15% today → no new entries ──
    if day_start_value > 0:
        day_dd_pct = ((day_start_value - account_value) / day_start_value) * 100
        if day_dd_pct >= DAY_DRAWDOWN_HALT_PCT:
            reason = (f"DAY HALT: account down {day_dd_pct:.1f}% today "
                      f"(open=${day_start_value:,.0f} now=${account_value:,.0f}, "
                      f"limit={DAY_DRAWDOWN_HALT_PCT}%). No entries until tomorrow.")
            logger.warning(reason)
            return _blocked(reason, premium)

    # ── SURVIVAL RULE 3: Total exposure > 20% of account → block ──
    exposure_pct = (current_exposure / account_value * 100) if account_value > 0 else 0
    if exposure_pct >= MAX_EXPOSURE_PCT:
        reason = (f"EXPOSURE LIMIT: ${current_exposure:,.0f} open = "
                  f"{exposure_pct:.1f}% of ${account_value:,.0f} "
                  f"(limit={MAX_EXPOSURE_PCT}%)")
        logger.warning(reason)
        return _blocked(reason, premium)

    # Check that adding this trade wouldn't breach exposure
    remaining_capacity = (account_value * MAX_EXPOSURE_PCT / 100) - current_exposure
    if remaining_capacity <= 0:
        reason = f"EXPOSURE FULL: no capacity remaining (limit={MAX_EXPOSURE_PCT}%)"
        logger.warning(reason)
        return _blocked(reason, premium)

    # ── Step 1: Base risk = 4% of account ──
    base_risk = account_value * (MAX_RISK_PER_TRADE_PCT / 100)

    # ── Step 2: Scale by confidence ──
    confidence_risk = base_risk * confidence

    # ── Step 3: Drawdown halving (8% daily loss) ──
    after_dd = confidence_risk
    if day_start_value > 0:
        day_dd_pct = ((day_start_value - account_value) / day_start_value) * 100
        if day_dd_pct >= DAY_DRAWDOWN_HALVE_PCT:
            after_dd = confidence_risk * 0.5
            halvings.append(f"day_drawdown_{day_dd_pct:.1f}%")

    # ── Step 4: PDT gate (replaces halving) ──
    if is_same_day_trade and day_trades_remaining == 0:
        return _blocked("no day trades remaining", premium)
    if is_same_day_trade and day_trades_remaining == 1 and confidence < 0.75:
        reason = "last day trade reserved for high-confidence entries (>= 75%)"
        logger.info(f"Sizer: {reason}")
        return _blocked(reason, premium)

    # ── Step 5: Contracts = floor(final_risk / premium_per_contract) ──
    final_risk = after_dd

    # Also cap by remaining exposure capacity
    final_risk = min(final_risk, remaining_capacity)

    contracts = max(1, math.floor(final_risk / contract_cost))

    # ── Step 6: High-conviction 0DTE multiplier ──
    if confidence >= 0.80 and is_same_day_trade:
        base_contracts = contracts
        contracts = min(math.ceil(contracts * 2.5), math.floor(remaining_capacity / contract_cost))
        contracts = max(contracts, base_contracts)  # Never reduce
        if contracts > base_contracts:
            halvings.append(f"HIGH_CONVICTION_0DTE: {base_contracts}->{contracts} (2.5x)")
            logger.info(f"Sizer: HIGH_CONVICTION 0DTE: {base_contracts} -> {contracts} contracts (2.5x multiplier)")

    # Final check: can we actually afford 1 contract?
    if contract_cost > final_risk and contract_cost > remaining_capacity:
        reason = (f"Cannot afford 1 contract: cost=${contract_cost:.2f} > "
                  f"risk=${final_risk:.2f} and capacity=${remaining_capacity:.2f}")
        logger.warning(reason)
        return _blocked(reason, premium)

    logger.info(
        f"Sizer: acct=${account_value:,.0f} conf={confidence:.2f} "
        f"base=${base_risk:.0f} -> conf_risk=${confidence_risk:.0f} "
        f"-> dd_halve=${after_dd:.0f} "
        f"-> contracts={contracts} (premium=${premium:.2f}) "
        f"halvings={halvings or 'none'}"
    )

    return SizingResult(
        contracts=contracts,
        base_risk=round(base_risk, 2),
        confidence_risk=round(confidence_risk, 2),
        after_drawdown_halving=round(after_dd, 2),
        after_pdt_halving=round(after_dd, 2),  # PDT halving removed, same as dd
        final_risk=round(final_risk, 2),
        premium_per_contract=round(contract_cost, 2),
        halvings_applied=halvings,
        blocked=False,
        block_reason="",
    )


def _blocked(reason: str, premium: float) -> SizingResult:
    """Return a zero-contract result with the blocking reason logged."""
    return SizingResult(
        contracts=0, base_risk=0, confidence_risk=0,
        after_drawdown_halving=0, after_pdt_halving=0,
        final_risk=0, premium_per_contract=premium * 100,
        halvings_applied=[], blocked=True, block_reason=reason,
    )
