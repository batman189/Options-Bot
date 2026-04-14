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
import math
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


def get_implied_move_pct(
    strategy,
    symbol: str,
    underlying_price: float,
    target_dte_min: int = 5,
    target_dte_max: int = 14,
) -> Optional[float]:
    """
    Estimate the market's implied move % by pricing the ATM straddle.

    An ATM straddle (buy ATM call + buy ATM put) costs approximately:
        straddle_cost = ATM_call_price + ATM_put_price

    The implied move % = straddle_cost / underlying_price * 100

    This represents the market's consensus on how much the stock could move
    over the straddle's remaining life. If the ML model predicts less than this,
    the market has already priced out the edge.

    Returns:
        Implied move as a percentage (e.g., 5.2 means ±5.2%), or None if unavailable.
    """
    from lumibot.entities import Asset

    logger.info(
        f"get_implied_move_pct: {symbol} price=${underlying_price:.2f} "
        f"DTE={target_dte_min}-{target_dte_max}"
    )

    try:
        chains = strategy.get_chains(Asset(symbol=symbol, asset_type="stock"))
        if not chains or "Chains" not in chains:
            logger.warning("get_implied_move_pct: no chains returned")
            return None

        chain_data = chains["Chains"]
        if "CALL" not in chain_data or "PUT" not in chain_data:
            logger.warning("get_implied_move_pct: CALL or PUT chains missing")
            return None

        today = strategy.get_datetime().date()

        # Find the nearest expiration within the target DTE range
        target_exp = None
        target_dte = None
        for exp_date in sorted(chain_data["CALL"].keys()):
            # Normalize expiration to datetime.date
            if isinstance(exp_date, str):
                exp_d = datetime.datetime.strptime(exp_date, "%Y-%m-%d").date()
            elif isinstance(exp_date, datetime.datetime):
                exp_d = exp_date.date()
            elif isinstance(exp_date, datetime.date):
                exp_d = exp_date
            else:
                continue

            dte = (exp_d - today).days
            if target_dte_min <= dte <= target_dte_max:
                target_exp = exp_date
                target_dte = dte
                break

        if target_exp is None:
            logger.warning(
                f"get_implied_move_pct: no expiration in {target_dte_min}-{target_dte_max} DTE range"
            )
            return None

        # Get strikes for the matching expiration
        call_strikes = sorted(float(s) for s in chain_data["CALL"].get(target_exp, []))
        put_strikes = sorted(float(s) for s in chain_data["PUT"].get(target_exp, []))

        if not call_strikes or not put_strikes:
            logger.warning("get_implied_move_pct: no strikes found for target expiration")
            return None

        # ATM = closest strike to underlying price
        atm_call_strike = min(call_strikes, key=lambda s: abs(s - underlying_price))
        atm_put_strike = min(put_strikes, key=lambda s: abs(s - underlying_price))

        # Normalize expiration for Asset constructor
        if isinstance(target_exp, str):
            exp_for_asset = datetime.datetime.strptime(target_exp, "%Y-%m-%d").date()
        elif isinstance(target_exp, datetime.datetime):
            exp_for_asset = target_exp.date()
        else:
            exp_for_asset = target_exp

        call_asset = Asset(
            symbol=symbol, asset_type="option",
            expiration=exp_for_asset, strike=atm_call_strike, right="CALL"
        )
        put_asset = Asset(
            symbol=symbol, asset_type="option",
            expiration=exp_for_asset, strike=atm_put_strike, right="PUT"
        )

        call_price = strategy.get_last_price(call_asset)
        put_price = strategy.get_last_price(put_asset)

        if call_price is None or put_price is None or call_price <= 0 or put_price <= 0:
            logger.warning("get_implied_move_pct: ATM option prices unavailable")
            return None

        straddle_cost = call_price + put_price
        implied_move_pct = (straddle_cost / underlying_price) * 100

        logger.info(
            f"get_implied_move_pct: {symbol} DTE={target_dte} "
            f"ATM call={atm_call_strike} @ ${call_price:.2f} "
            f"ATM put={atm_put_strike} @ ${put_price:.2f} "
            f"straddle=${straddle_cost:.2f} implied={implied_move_pct:.2f}%"
        )
        return implied_move_pct

    except Exception as e:
        logger.warning(f"get_implied_move_pct failed: {e}", exc_info=True)
        return None


def _estimate_delta(
    underlying_price: float,
    strike: float,
    dte: int,
    direction: str,
    risk_free_rate: float = None,
    default_vol: float = 0.35,
) -> float:
    """
    Estimate option delta from moneyness using simplified Black-Scholes.
    Used as fallback when broker Greeks are unavailable or return garbage.

    Returns estimated delta (positive for calls, negative for puts).
    """
    if risk_free_rate is None:
        from config import RISK_FREE_RATE
        risk_free_rate = RISK_FREE_RATE
    T = max(dte, 1) / 365.0  # Time to expiry in years (floor 1 day for 0DTE)
    sigma = default_vol
    sqrt_T = math.sqrt(T)

    try:
        d1 = (math.log(underlying_price / strike) + (risk_free_rate + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        # Standard normal CDF approximation (Abramowitz & Stegun)
        nd1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))

        if direction == "CALL":
            return nd1  # Call delta: N(d1), 0 to 1
        else:
            return nd1 - 1.0  # Put delta: N(d1) - 1, -1 to 0
    except (ValueError, ZeroDivisionError):
        # Fallback for edge cases
        moneyness = underlying_price / strike
        if direction == "CALL":
            return max(0.05, min(0.95, 0.5 + (moneyness - 1.0) * 5.0))
        else:
            return min(-0.05, max(-0.95, -0.5 + (moneyness - 1.0) * 5.0))


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
    min_premium: float = 0.0,
    max_premium: float = 0.0,
    prefer_atm: bool = False,
) -> Optional[EVCandidate]:
    """
    Scan the option chain and find the best contract to trade.

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
        min_premium: Minimum option price to consider (filters out penny contracts)
        prefer_atm: If True, rank by distance-to-ATM among EV-qualified contracts
                     instead of by raw EV%. Prevents the EV formula from always
                     picking the cheapest deep-OTM contract.

    Returns:
        EVCandidate with the highest EV (or nearest ATM if prefer_atm), or None.

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
    contracts_skipped_premium = 0
    contracts_fallback_greeks = 0

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

            delta = (getattr(greeks, "delta", 0) or 0) if greeks else 0
            gamma = (getattr(greeks, "gamma", 0) or 0) if greeks else 0
            theta = (getattr(greeks, "theta", 0) or 0) if greeks else 0
            vega = (getattr(greeks, "vega", 0) or 0) if greeks else 0
            iv = (getattr(greeks, "implied_volatility", 0) or 0) if greeks else 0

            # Fallback: estimate delta from moneyness when broker Greeks are bad.
            # Lumibot's get_greeks() can return near-zero delta for all contracts
            # when market data (IV, quotes) is unavailable or stale.
            if abs(delta) < 0.05:
                estimated_delta = _estimate_delta(
                    underlying_price, strike, dte, direction
                )
                if abs(estimated_delta) >= 0.10:
                    contracts_fallback_greeks += 1
                    logger.debug(
                        f"  Greeks fallback: {strike} {direction} — broker delta={delta:.4f}, "
                        f"estimated delta={estimated_delta:.3f}"
                    )
                    delta = estimated_delta
                    # Estimate gamma from delta curve slope (~0.01 for ATM)
                    moneyness = underlying_price / strike
                    gamma = 0.015 if 0.95 <= moneyness <= 1.05 else 0.005
                    # Estimate theta (rough: ATM option loses ~0.05-0.10% of underlying per day)
                    # For 0DTE, use higher rate (0.3%) to reflect accelerated intraday decay
                    theta = -(underlying_price * 0.0007) if dte > 0 else -(underlying_price * 0.003)
                else:
                    # Genuinely deep OTM — skip
                    contracts_skipped_greeks += 1
                    continue

            # BUG-010 fix: broker can return valid delta but theta=0/vega=0/iv=0
            # on some 0DTE options. Estimate theta when it's suspiciously zero.
            if abs(delta) >= 0.05 and theta == 0 and dte <= 7:
                theta = -(underlying_price * 0.0007) if dte > 0 else -(underlying_price * 0.003)
                logger.debug(
                    f"  Theta fallback: {strike} {direction} — broker theta=0, "
                    f"estimated theta={theta:.4f}"
                )

            # Get option price
            option_price = strategy.get_last_price(option_asset)
            if option_price is None or option_price <= 0:
                contracts_skipped_price += 1
                continue

            # Minimum premium filter — reject penny contracts that have
            # massive spreads, zero liquidity, and don't move with the underlying.
            if min_premium > 0 and option_price < min_premium:
                contracts_skipped_premium += 1
                continue

            if max_premium > 0 and option_price > max_premium:
                contracts_skipped_premium += 1
                continue

            # Spread filtering is handled post-scan by the liquidity gate
            # (base_strategy step 9.5) via Alpaca snapshot API. Lumibot's
            # get_chains() does not expose bid/ask quotes in-scanner.
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

            # Floor at 30min (~0.021 days) so 0DTE scalps never get theta_cost=0.
            # Before this fix: min(0, 0) = 0 → zero theta cost on ALL 0DTE trades.
            hold_days_effective = max(min(max_hold_days, dte), 30 / 1440)
            theta_cost = abs(theta) * hold_days_effective * theta_accel

            # EV percentage — expected_gain is the option price increase (not total
            # value), so we subtract theta_cost, not premium again.
            # Spread cost is handled by the post-scan liquidity gate.
            ev_pct = (expected_gain - theta_cost) / premium * 100

            # Cap EV at 500% to prevent inflated values from penny options
            # (e.g. $0.05 premium produces 300%+ EV from tiny expected gains)
            ev_pct = min(ev_pct, 500.0)

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
        f"{contracts_fallback_greeks} used fallback Greeks, "
        f"{contracts_skipped_price} skipped (price), "
        f"{contracts_skipped_premium} skipped (premium < ${min_premium:.2f})"
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
            f"exp={best_below.expiration} EV={best_below.ev_pct:.1f}% "
            f"premium=${best_below.premium:.2f}"
        )
        return None

    # Select best contract
    if prefer_atm:
        # For scalp/0DTE: among EV-qualified contracts, pick the one nearest ATM.
        # The EV formula (gain/premium*100) favors cheap OTM options with high
        # percentage return but tiny dollar movement. For scalping, we want
        # contracts with high delta that actually move with the underlying.
        best = min(qualified, key=lambda c: abs(c.strike - underlying_price))
    else:
        # For swing/general: pick highest EV
        best = max(qualified, key=lambda c: c.ev_pct)

    logger.info(
        f"Best contract: {best.strike} {best.right} exp={best.expiration} "
        f"EV={best.ev_pct:.1f}% premium=${best.premium:.2f} "
        f"delta={best.delta:.3f} theta={best.theta:.4f} "
        f"{'(nearest ATM)' if prefer_atm else '(highest EV)'}"
    )
    return best
