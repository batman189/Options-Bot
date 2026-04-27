"""
Iron Condor strategy for 0DTE SPY premium selling.

Architecture:
  1. GEX regime filter determines if conditions are safe to sell premium
  2. If safe: construct a 0DTE iron condor with ~16 delta short strikes
  3. Exit: close at 50% max profit, 2x credit stop loss, or 3:30 PM hard close

An iron condor consists of 4 legs:
  - Sell OTM put  (short put)  — collects premium
  - Buy further OTM put (long put) — defines max loss on downside
  - Sell OTM call (short call) — collects premium
  - Buy further OTM call (long call) — defines max loss on upside

Max profit = net credit received
Max loss = spread width - net credit
"""

import logging
import time
from datetime import date, datetime, timezone
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.stats import norm

logger = logging.getLogger("options-bot.strategies.iron_condor")


@dataclass
class IronCondorLegs:
    """Describes the 4 legs of an iron condor."""
    short_put_strike: float
    long_put_strike: float
    short_call_strike: float
    long_call_strike: float
    expiration: date
    spread_width: float       # distance between short and long strikes
    estimated_credit: float   # net credit received per contract
    max_loss: float           # spread_width - credit, per contract
    short_put_delta: float
    short_call_delta: float


def _bs_delta(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float:
    """Black-Scholes delta."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    if right.upper() in ("CALL", "C"):
        return norm.cdf(d1)
    else:
        return norm.cdf(d1) - 1.0


def select_iron_condor_strikes(
    underlying_price: float,
    available_strikes: list[float],
    iv: float,
    hours_remaining: float,
    target_delta: float = 0.16,
    spread_width_dollars: float = 3.0,
    chain_data: dict = None,
) -> Optional[IronCondorLegs]:
    """
    Select optimal iron condor strikes based on target delta.

    Args:
        underlying_price: Current price of underlying
        available_strikes: List of available strike prices for today's expiration
        iv: Implied volatility (annualized, e.g. 0.20 for 20%)
        hours_remaining: Hours until market close
        target_delta: Target absolute delta for short strikes (default 0.16 = ~1 SD)
        spread_width_dollars: Distance between short and long strikes (default $3)
        chain_data: Optional dict of {strike: {bid, ask, mid}} for price estimates

    Returns:
        IronCondorLegs or None if suitable strikes not found.
    """
    if not available_strikes or iv <= 0 or underlying_price <= 0:
        return None

    sorted_strikes = sorted(available_strikes)
    r = 0.05
    T = max(hours_remaining / (252 * 6.5), 0.0001)

    # Find put strikes below ATM and call strikes above ATM
    put_strikes = [s for s in sorted_strikes if s < underlying_price]
    call_strikes = [s for s in sorted_strikes if s > underlying_price]

    if len(put_strikes) < 2 or len(call_strikes) < 2:
        logger.warning("Not enough OTM strikes for iron condor")
        return None

    # Find short put: highest put strike with |delta| <= target_delta
    short_put = None
    short_put_delta = 0
    for strike in reversed(put_strikes):  # start nearest ATM, go further OTM
        delta = abs(_bs_delta(underlying_price, strike, T, r, iv, "PUT"))
        if delta <= target_delta:
            short_put = strike
            short_put_delta = -delta  # puts have negative delta
            break

    # Find short call: lowest call strike with delta <= target_delta
    short_call = None
    short_call_delta = 0
    for strike in call_strikes:  # start nearest ATM, go further OTM
        delta = _bs_delta(underlying_price, strike, T, r, iv, "CALL")
        if delta <= target_delta:
            short_call = strike
            short_call_delta = delta
            break

    if short_put is None or short_call is None:
        logger.warning(
            f"Could not find {target_delta:.0%} delta strikes. "
            f"Put strikes: {len(put_strikes)}, Call strikes: {len(call_strikes)}"
        )
        return None

    # Long strikes: further OTM by spread_width_dollars
    long_put = short_put - spread_width_dollars
    long_call = short_call + spread_width_dollars

    # Snap to nearest available strikes
    long_put = min(put_strikes, key=lambda s: abs(s - long_put)) if put_strikes else short_put - spread_width_dollars
    long_call = min(call_strikes + [short_call + spread_width_dollars],
                    key=lambda s: abs(s - (short_call + spread_width_dollars)))

    # Ensure long strikes are further OTM than short strikes
    if long_put >= short_put:
        long_put = short_put - 1.0  # minimum $1 spread
    if long_call <= short_call:
        long_call = short_call + 1.0

    actual_spread = min(short_put - long_put, long_call - short_call)

    # Estimate credit from chain data if available
    estimated_credit = 0
    if chain_data:
        sp_mid = chain_data.get(short_put, {}).get("put_mid", 0)
        lp_mid = chain_data.get(long_put, {}).get("put_mid", 0)
        sc_mid = chain_data.get(short_call, {}).get("call_mid", 0)
        lc_mid = chain_data.get(long_call, {}).get("call_mid", 0)
        # Credit = sell short legs - buy long legs
        estimated_credit = (sp_mid - lp_mid) + (sc_mid - lc_mid)
    else:
        # Rough estimate from Black-Scholes
        from ml.gex_calculator import _bs_price
        sp_price = _bs_price(underlying_price, short_put, T, r, iv, "PUT")
        lp_price = _bs_price(underlying_price, long_put, T, r, iv, "PUT")
        sc_price = _bs_price(underlying_price, short_call, T, r, iv, "CALL")
        lc_price = _bs_price(underlying_price, long_call, T, r, iv, "CALL")
        estimated_credit = (sp_price - lp_price) + (sc_price - lc_price)

    max_loss = actual_spread - estimated_credit

    logger.info(
        f"Iron condor strikes selected: "
        f"PUT {long_put}/{short_put} | CALL {short_call}/{long_call} | "
        f"credit=${estimated_credit:.2f} max_loss=${max_loss:.2f} "
        f"short_deltas=({short_put_delta:.3f}, {short_call_delta:.3f})"
    )

    return IronCondorLegs(
        short_put_strike=short_put,
        long_put_strike=long_put,
        short_call_strike=short_call,
        long_call_strike=long_call,
        expiration=date.today(),
        spread_width=actual_spread,
        estimated_credit=estimated_credit,
        max_loss=max_loss,
        short_put_delta=short_put_delta,
        short_call_delta=short_call_delta,
    )


def build_iron_condor_orders(strategy, legs: IronCondorLegs, quantity: int):
    """
    Build the 4 Lumibot Order objects for an iron condor.

    Args:
        strategy: Lumibot Strategy instance
        legs: IronCondorLegs from select_iron_condor_strikes
        quantity: Number of contracts per leg

    Returns:
        List of 4 Order objects [sell_put, buy_put, sell_call, buy_call]
    """
    from lumibot.entities import Asset

    symbol = strategy.symbol
    exp = legs.expiration

    # 4 legs
    short_put_asset = Asset(symbol, asset_type="option", expiration=exp,
                            strike=legs.short_put_strike, right="PUT")
    long_put_asset = Asset(symbol, asset_type="option", expiration=exp,
                           strike=legs.long_put_strike, right="PUT")
    short_call_asset = Asset(symbol, asset_type="option", expiration=exp,
                             strike=legs.short_call_strike, right="CALL")
    long_call_asset = Asset(symbol, asset_type="option", expiration=exp,
                            strike=legs.long_call_strike, right="CALL")

    orders = [
        strategy.create_order(short_put_asset, quantity, side="sell_to_open"),
        strategy.create_order(long_put_asset, quantity, side="buy_to_open"),
        strategy.create_order(short_call_asset, quantity, side="sell_to_open"),
        strategy.create_order(long_call_asset, quantity, side="buy_to_open"),
    ]

    logger.info(
        f"Iron condor orders built: {quantity}x "
        f"sell P{legs.short_put_strike} / buy P{legs.long_put_strike} / "
        f"sell C{legs.short_call_strike} / buy C{legs.long_call_strike} "
        f"exp={exp}"
    )

    return orders


def build_iron_condor_close_orders(strategy, legs: IronCondorLegs, quantity: int):
    """
    Build the 4 closing orders to exit an iron condor position.

    Returns:
        List of 4 Order objects that reverse the opening orders.
    """
    from lumibot.entities import Asset

    symbol = strategy.symbol
    exp = legs.expiration

    short_put_asset = Asset(symbol, asset_type="option", expiration=exp,
                            strike=legs.short_put_strike, right="PUT")
    long_put_asset = Asset(symbol, asset_type="option", expiration=exp,
                           strike=legs.long_put_strike, right="PUT")
    short_call_asset = Asset(symbol, asset_type="option", expiration=exp,
                             strike=legs.short_call_strike, right="CALL")
    long_call_asset = Asset(symbol, asset_type="option", expiration=exp,
                            strike=legs.long_call_strike, right="CALL")

    orders = [
        strategy.create_order(short_put_asset, quantity, side="buy_to_close"),
        strategy.create_order(long_put_asset, quantity, side="sell_to_close"),
        strategy.create_order(short_call_asset, quantity, side="buy_to_close"),
        strategy.create_order(long_call_asset, quantity, side="sell_to_close"),
    ]

    return orders
