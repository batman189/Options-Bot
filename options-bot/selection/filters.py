"""Liquidity gate and EV validation for options contract selection.

Liquidity gate is FIXED, NON-CONFIGURABLE:
  Open interest > 200
  Daily volume > 50
  Bid-ask spread < 15% of mid price
If no contract passes all three, no trade is placed.
"""

import logging
from selection.ev import compute_ev

logger = logging.getLogger("options-bot.selection.filters")

MIN_OPEN_INTEREST = 200
MAX_SPREAD_PCT = 15.0


def _min_volume_for_time() -> int:
    """Volume threshold scales with time of day.
    0DTE options have near-zero volume at open — relax threshold early."""
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        now_et = datetime.now(ZoneInfo("America/New_York"))
        minutes_since_open = (now_et.hour - 9) * 60 + now_et.minute - 30
        if minutes_since_open < 30:
            return 5   # First 30 min: almost no volume yet
        elif minutes_since_open < 60:
            return 20  # 30-60 min: volume building
        else:
            return 50  # After 1 hour: full requirement
    except Exception:
        return 10  # Safe default if timezone fails


def apply_liquidity_gate(candidates: list[dict]) -> list[dict]:
    """Filter contracts by OI, volume (time-aware), and spread."""
    min_vol = _min_volume_for_time()
    passed = []
    for c in candidates:
        oi = c.get("open_interest", 0)
        vol = c.get("volume", 0)
        bid = c.get("bid", 0)
        ask = c.get("ask", 0)
        mid = (bid + ask) / 2 if (bid + ask) > 0 else 0
        spread_pct = ((ask - bid) / mid * 100) if mid > 0 else 100

        if oi < MIN_OPEN_INTEREST:
            continue
        if vol < min_vol:
            continue
        if spread_pct > MAX_SPREAD_PCT:
            continue

        c["_mid"] = round(mid, 4)
        c["_spread_pct"] = round(spread_pct, 2)
        passed.append(c)
    return passed


def apply_ev_validation(candidates: list[dict], data_client, symbol: str,
                         expiration: str, right: str, underlying: float,
                         predicted_move_pct: float, hold_days: float,
                         dte: int) -> list[dict]:
    """Compute EV for each candidate. Reject if EV < 0%.
    Attaches Greeks and EV to each passing candidate."""
    validated = []
    for c in candidates:
        strike = c["strike"]
        try:
            greeks = data_client.get_greeks(symbol, expiration, strike, right.lower())
        except Exception as e:
            logger.debug(f"Greeks unavailable for {symbol} {right} ${strike}: {e}")
            continue

        ev = compute_ev(
            underlying_price=underlying,
            predicted_move_pct=predicted_move_pct,
            delta=greeks.delta, gamma=greeks.gamma,
            theta=greeks.theta, premium=c["_mid"],
            hold_days=hold_days, dte=dte,
        )

        if ev < 0:
            logger.debug(f"EV negative: {symbol} {right} ${strike} EV={ev:.1f}%")
            continue

        c["_greeks"] = greeks
        c["_ev_pct"] = ev
        validated.append(c)
    return validated
