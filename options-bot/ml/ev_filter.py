"""
Expected Value filter for option contract selection.
Matches PROJECT_ARCHITECTURE.md Section 9 — Entry Logic step 9.

Scans the option chain, filters by DTE and moneyness,
calculates EV for each candidate, returns the best contract.

EV formula (delta-gamma approximation with theta acceleration):
    move = underlying_price * |predicted_return_pct| / 100
    expected_gain = |delta| * move + 0.5 * |gamma| * move²
    theta_cost = |theta| * min(max_hold_days, dte) * theta_accel
    EV = (expected_gain - theta_cost) / premium * 100

The contract with the highest EV above the minimum threshold wins.
"""

import logging
import datetime
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger("options-bot.ml.ev_filter")


@dataclass
class EVCandidate:
    """A scored option contract candidate."""
    expiration: datetime.date
    strike: float
    right: str  # "CALL" or "PUT"
    premium: float  # Mid price (bid+ask)/2 or last price
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_volatility: float
    ev_pct: float  # Calculated EV percentage
    expected_gain: float
    theta_cost: float


def scan_chain_for_best_ev(
    strategy,
    symbol: str,
    predicted_return_pct: float,
    underlying_price: float,
    min_dte: int,
    max_dte: int,
    max_hold_days: int,
    min_ev_pct: float,
    moneyness_range_pct: float = 5.0,
    max_spread_pct: float = 0.50,
) -> Optional[EVCandidate]:
    """
    Scan the option chain and find the contract with the highest EV.

    Args:
        strategy: The Lumibot Strategy instance (for get_chains, get_greeks, get_last_price)
        symbol: Underlying ticker (e.g., "TSLA")
        predicted_return_pct: Model's predicted forward return (e.g., 2.5 means +2.5%)
        underlying_price: Current price of the underlying
        min_dte: Minimum days to expiration (from profile config)
        max_dte: Maximum days to expiration
        max_hold_days: Maximum holding period (for theta cost calculation)
        min_ev_pct: Minimum EV percentage to accept
        moneyness_range_pct: How far from ATM to scan (default ±5%)
        max_spread_pct: Maximum bid-ask spread as ratio of mid (default 0.50 = 50%)

    Returns:
        EVCandidate with the highest EV, or None if nothing qualifies.

    Uses Lumibot's get_chains() and get_greeks() — NOT our data providers.
    """
    from lumibot.entities import Asset

    logger.info(
        f"Scanning chain for {symbol}: predicted_return={predicted_return_pct:.2f}%, "
        f"price=${underlying_price:.2f}, DTE={min_dte}-{max_dte}, "
        f"min_ev={min_ev_pct}%"
    )

    # Determine direction from prediction
    direction = "CALL" if predicted_return_pct > 0 else "PUT"
    abs_predicted_return = abs(predicted_return_pct)

    # Get option chains from Lumibot
    # Phase 6 audit: error handling verified — get_chains() is wrapped in try/except
    # returning None. All downstream code handles None/empty gracefully.
    # Uses Lumibot's broker API (Alpaca), NOT Theta Terminal directly.
    stock_asset = Asset(symbol, asset_type="stock")
    try:
        chains = strategy.get_chains(stock_asset)
    except Exception as e:
        logger.error(f"Failed to get chains for {symbol}: {e}")
        return None

    if not chains or "Chains" not in chains:
        logger.warning(f"No chains data for {symbol}")
        return None

    chain_data = chains["Chains"]
    if direction not in chain_data:
        logger.warning(f"No {direction} chains for {symbol}")
        return None

    today = strategy.get_datetime().date()
    moneyness_lo = underlying_price * (1 - moneyness_range_pct / 100)
    moneyness_hi = underlying_price * (1 + moneyness_range_pct / 100)

    candidates = []
    contracts_scanned = 0
    contracts_skipped_dte = 0
    contracts_skipped_moneyness = 0
    contracts_skipped_greeks = 0
    contracts_skipped_price = 0
    contracts_skipped_spread = 0

    for exp_date, strikes in chain_data[direction].items():
        # Normalize expiration to datetime.date
        if isinstance(exp_date, str):
            exp_date = datetime.datetime.strptime(exp_date, "%Y-%m-%d").date()
        elif isinstance(exp_date, datetime.datetime):
            exp_date = exp_date.date()

        dte = (exp_date - today).days
        if dte < min_dte or dte > max_dte:
            contracts_skipped_dte += len(strikes)
            continue

        for strike in strikes:
            contracts_scanned += 1
            strike = float(strike)

            # Filter by moneyness
            if strike < moneyness_lo or strike > moneyness_hi:
                contracts_skipped_moneyness += 1
                continue

            # Build the option asset
            option_asset = Asset(
                symbol=symbol,
                asset_type="option",
                expiration=exp_date,
                strike=strike,
                right=direction,
            )

            # Get Greeks (Lumibot Black-Scholes)
            greeks = strategy.get_greeks(
                option_asset,
                underlying_price=underlying_price,
            )
            if greeks is None:
                contracts_skipped_greeks += 1
                continue

            delta = greeks.get("delta", 0)
            gamma = greeks.get("gamma", 0)
            theta = greeks.get("theta", 0)
            vega = greeks.get("vega", 0)
            iv = greeks.get("iv", greeks.get("implied_volatility", 0))

            if abs(delta) < 0.05:
                # Skip deep OTM with negligible delta
                contracts_skipped_greeks += 1
                continue

            # Get option price
            option_price = strategy.get_last_price(option_asset)
            if option_price is None or option_price <= 0:
                contracts_skipped_price += 1
                continue

            # Bid-ask spread filter — reject illiquid contracts before EV calculation.
            # A wide spread means the round-trip transaction cost consumes the expected edge.
            # max_spread_pct = 0.50 means reject any contract where
            # (ask - bid) / mid > 0.50 (50% spread relative to mid).
            bid = None
            ask = None
            try:
                quote = strategy.get_quote(option_asset)
                if quote and isinstance(quote, dict):
                    bid = quote.get("bid")
                    ask = quote.get("ask")
            except Exception as quote_err:
                logger.debug(
                    f"  get_quote failed for {strike} {direction} "
                    f"exp={exp_date}: {quote_err} — skipping spread check"
                )

            if bid is not None and ask is not None and bid > 0 and ask > 0:
                mid = (bid + ask) / 2.0
                spread_ratio = (ask - bid) / mid if mid > 0 else float("inf")
                if spread_ratio > max_spread_pct:
                    logger.debug(
                        f"  Skipping {strike} {direction} exp={exp_date}: "
                        f"spread {spread_ratio:.1%} > max {max_spread_pct:.1%} "
                        f"(bid={bid:.2f} ask={ask:.2f})"
                    )
                    contracts_skipped_spread += 1
                    continue
                # Use mid-price as premium (best estimate of fair value)
                premium = mid
            else:
                # Quote unavailable — use last price already fetched
                premium = option_price

            # Calculate EV
            # Predicted underlying move in dollars
            predicted_move_dollars = underlying_price * abs_predicted_return / 100

            # Option gain using delta-gamma (second-order Taylor) approximation.
            # delta * move captures the linear component.
            # 0.5 * gamma * move² captures the convexity benefit — options gain
            # extra value from large moves due to positive gamma.
            # abs() on gamma because gamma is always positive for long options,
            # but the Lumibot greeks dict may return it with a sign.
            expected_gain = (
                abs(delta) * predicted_move_dollars
                + 0.5 * abs(gamma) * (predicted_move_dollars ** 2)
            )

            # Theta decay acceleration adjustment.
            # For contracts with < 21 DTE at entry, theta increases materially
            # as expiration approaches. Apply a multiplier to avoid systematically
            # underestimating decay cost on shorter-dated contracts.
            # Multiplier rationale:
            #   dte >= 21: theta relatively stable → 1.0x
            #   dte 14-20: moderate acceleration  → 1.25x
            #   dte 7-13:  significant acceleration → 1.5x
            #   dte < 7:   extreme acceleration   → 2.0x (DTE floor exit usually triggers first)
            if dte >= 21:
                theta_accel = 1.0
            elif dte >= 14:
                theta_accel = 1.25
            elif dte >= 7:
                theta_accel = 1.5
            else:
                theta_accel = 2.0

            hold_days_effective = min(max_hold_days, dte)
            theta_cost = abs(theta) * hold_days_effective * theta_accel

            # EV percentage — expected_gain is the option price increase (not total
            # value), so we only subtract theta_cost, not premium again.
            ev_pct = (expected_gain - theta_cost) / premium * 100

            candidates.append(EVCandidate(
                expiration=exp_date,
                strike=strike,
                right=direction,
                premium=premium,
                delta=delta,
                gamma=gamma,
                theta=theta,
                vega=vega,
                implied_volatility=iv,
                ev_pct=ev_pct,
                expected_gain=expected_gain,
                theta_cost=theta_cost,
            ))

    logger.info(
        f"Chain scan complete: {contracts_scanned} scanned, "
        f"{len(candidates)} candidates scored, "
        f"{contracts_skipped_dte} skipped (DTE), "
        f"{contracts_skipped_moneyness} skipped (moneyness), "
        f"{contracts_skipped_greeks} skipped (Greeks), "
        f"{contracts_skipped_price} skipped (price), "
        f"{contracts_skipped_spread} skipped (spread)"
    )

    if not candidates:
        logger.info("No EV candidates found")
        return None

    # Filter by minimum EV
    qualified = [c for c in candidates if c.ev_pct >= min_ev_pct]
    if not qualified:
        best_below = max(candidates, key=lambda c: c.ev_pct)
        logger.info(
            f"No candidates meet min EV {min_ev_pct}%. "
            f"Best was {best_below.strike} {best_below.right} "
            f"exp={best_below.expiration} EV={best_below.ev_pct:.1f}%"
        )
        return None

    # Select highest EV
    best = max(qualified, key=lambda c: c.ev_pct)
    logger.info(
        f"Best contract: {best.strike} {best.right} exp={best.expiration} "
        f"EV={best.ev_pct:.1f}% premium=${best.premium:.2f} "
        f"delta={best.delta:.3f} theta={best.theta:.4f}"
    )
    return best
