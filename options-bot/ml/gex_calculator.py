"""
Gamma Exposure (GEX) and market regime calculator.

Computes regime indicators from the live SPY options chain to determine:
- Is the market in a mean-reverting or trending regime?
- Is it safe to sell premium (iron condors) or should we sit out?
- Is it a good time for OTM gamma plays?

Features computed:
  - atm_straddle_pct: ATM straddle price as % of underlying (implied expected move)
  - iv_skew: OTM put IV minus OTM call IV (fear gauge)
  - put_call_premium_ratio: total put premium / total call premium
  - gamma_concentration: how concentrated gamma is near ATM vs spread out
  - regime: 'sell_premium' (safe for iron condors) or 'trending' (sit out / OTM plays)

Data source: Alpaca OptionChainRequest (get_option_chain) which returns
snapshots with IV and bid/ask for all contracts.
"""

import logging
import time
from datetime import date, datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.stats import norm

logger = logging.getLogger("options-bot.ml.gex_calculator")


@dataclass
class GEXResult:
    """Result of a GEX/regime calculation."""
    timestamp: str
    underlying_price: float
    atm_straddle_pct: float          # ATM straddle as % of underlying
    iv_skew: float                   # OTM put IV - OTM call IV (positive = fear)
    put_call_premium_ratio: float    # Total put premium / total call premium
    gamma_concentration: float       # 0-1: how concentrated gamma is near ATM
    mean_iv: float                   # Average IV across chain
    regime: str                      # 'sell_premium' or 'trending' or 'uncertain'
    confidence: float                # 0-1 regime confidence
    details: dict = field(default_factory=dict)


def _bs_price(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float:
    """Black-Scholes price for a European option."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(S - K, 0) if right.upper() in ("CALL", "C") else max(K - S, 0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if right.upper() in ("CALL", "C"):
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def _bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes vega (sensitivity to IV change)."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return S * norm.pdf(d1) * np.sqrt(T)


def _implied_vol(S: float, K: float, T: float, r: float, market_price: float,
                 right: str, max_iter: int = 50, tol: float = 1e-6) -> float:
    """Compute implied volatility from market price using Newton-Raphson."""
    if market_price <= 0 or T <= 0 or S <= 0:
        return 0.0
    # Initial guess
    sigma = 0.25
    for _ in range(max_iter):
        price = _bs_price(S, K, T, r, sigma, right)
        vega = _bs_vega(S, K, T, r, sigma)
        if vega < 1e-10:
            break
        diff = price - market_price
        if abs(diff) < tol:
            return sigma
        sigma -= diff / vega
        sigma = max(0.01, min(sigma, 5.0))  # clamp to reasonable range
    return max(sigma, 0.01)


def _bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes gamma for a European option."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))


def _bs_delta(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float:
    """Black-Scholes delta for a European option."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    if right.upper() in ("CALL", "C"):
        return norm.cdf(d1)
    else:
        return norm.cdf(d1) - 1.0


def compute_gex_features(strategy, symbol: str = "SPY") -> Optional[GEXResult]:
    """
    Compute GEX regime features from the live options chain.

    Args:
        strategy: Lumibot strategy instance (for get_option_chain, get_last_price)
        symbol: Underlying symbol (default SPY)

    Returns:
        GEXResult with all computed features, or None if data unavailable.
    """
    t_start = time.time()

    try:
        from lumibot.entities import Asset
        stock_asset = Asset(symbol, asset_type="stock")
        underlying_price = strategy.get_last_price(stock_asset)
        if not underlying_price or underlying_price <= 0:
            logger.warning("GEX: cannot get underlying price")
            return None

        # Get the full options chain for today's expiration (0DTE)
        from alpaca.data.historical.option import OptionHistoricalDataClient
        from alpaca.data.requests import OptionChainRequest
        import os

        api_key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
        api_secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY")
        if not api_key or not api_secret:
            logger.warning("GEX: Alpaca credentials not available")
            return None

        client = OptionHistoricalDataClient(api_key, api_secret)

        today = date.today()
        # Scan ±8% from ATM for comprehensive chain coverage
        strike_low = underlying_price * 0.92
        strike_high = underlying_price * 1.08

        chain_request = OptionChainRequest(
            underlying_symbol=symbol,
            expiration_date=today,
            strike_price_gte=strike_low,
            strike_price_lte=strike_high,
        )
        chain = client.get_option_chain(chain_request)

        if not chain or len(chain) < 10:
            logger.warning(f"GEX: insufficient chain data ({len(chain) if chain else 0} contracts)")
            return None

        # Parse chain into calls and puts with their data
        calls = {}  # strike -> {iv, bid, ask, mid, gamma, delta}
        puts = {}

        r = 0.05  # risk-free rate approximation
        # T in years — for 0DTE, use hours remaining / (252 * 6.5)
        now = datetime.now(timezone.utc)
        market_close_utc = now.replace(hour=20, minute=0, second=0, microsecond=0)
        hours_remaining = max((market_close_utc - now).total_seconds() / 3600, 0.01)
        T = hours_remaining / (252 * 6.5)  # fraction of a trading year

        for occ_symbol, snap in chain.items():
            # Parse OCC symbol: SPY260324C00577000
            try:
                right_char = occ_symbol[-9]  # C or P
                strike_raw = int(occ_symbol[-8:]) / 1000.0
            except (IndexError, ValueError):
                continue

            right = "CALL" if right_char == "C" else "PUT"
            iv = snap.implied_volatility or 0
            bid = snap.latest_quote.bid_price if snap.latest_quote else 0
            ask = snap.latest_quote.ask_price if snap.latest_quote else 0
            mid = (bid + ask) / 2 if bid and ask else 0

            # Skip contracts with no meaningful price
            if mid <= 0.005:
                continue

            # Compute IV from market price if Alpaca doesn't provide it
            if iv <= 0 and mid > 0.01:
                iv = _implied_vol(underlying_price, strike_raw, T, r, mid, right)

            sigma = iv if iv > 0 else 0.20  # last-resort fallback
            gamma = _bs_gamma(underlying_price, strike_raw, T, r, sigma)
            delta = _bs_delta(underlying_price, strike_raw, T, r, sigma, right)

            entry = {
                "iv": iv, "bid": bid, "ask": ask, "mid": mid,
                "gamma": gamma, "delta": delta, "strike": strike_raw,
            }

            if right == "CALL":
                calls[strike_raw] = entry
            else:
                puts[strike_raw] = entry

        if len(calls) < 3 or len(puts) < 3:
            logger.warning(f"GEX: too few contracts (calls={len(calls)}, puts={len(puts)})")
            return None

        # --- Compute features ---

        # 1. ATM Straddle Price (implied expected move)
        # Find the strike closest to ATM
        all_strikes = sorted(set(calls.keys()) & set(puts.keys()))
        if not all_strikes:
            logger.warning("GEX: no overlapping call/put strikes")
            return None

        atm_strike = min(all_strikes, key=lambda s: abs(s - underlying_price))
        atm_call_mid = calls[atm_strike]["mid"]
        atm_put_mid = puts[atm_strike]["mid"]
        atm_straddle = atm_call_mid + atm_put_mid
        atm_straddle_pct = (atm_straddle / underlying_price) * 100 if underlying_price > 0 else 0

        # 2. IV Skew (fear gauge)
        # Compare IV of ~5% OTM puts vs ~5% OTM calls
        otm_put_target = underlying_price * 0.97  # 3% OTM
        otm_call_target = underlying_price * 1.03
        otm_put_strike = min(puts.keys(), key=lambda s: abs(s - otm_put_target)) if puts else atm_strike
        otm_call_strike = min(calls.keys(), key=lambda s: abs(s - otm_call_target)) if calls else atm_strike
        otm_put_iv = puts.get(otm_put_strike, {}).get("iv", 0)
        otm_call_iv = calls.get(otm_call_strike, {}).get("iv", 0)
        iv_skew = otm_put_iv - otm_call_iv  # positive = fear/put demand

        # 3. Put/Call Premium Ratio
        total_call_premium = sum(c["mid"] for c in calls.values() if c["mid"] > 0)
        total_put_premium = sum(p["mid"] for p in puts.values() if p["mid"] > 0)
        put_call_premium_ratio = (
            total_put_premium / total_call_premium
            if total_call_premium > 0 else 1.0
        )

        # 4. Gamma Concentration
        # How much of total gamma is within ±1% of ATM?
        total_gamma = sum(c["gamma"] for c in calls.values()) + sum(p["gamma"] for p in puts.values())
        near_atm_gamma = 0
        for contracts in [calls, puts]:
            for strike, data in contracts.items():
                if abs(strike - underlying_price) / underlying_price <= 0.01:
                    near_atm_gamma += data["gamma"]
        gamma_concentration = near_atm_gamma / total_gamma if total_gamma > 0 else 0

        # 5. Mean IV
        all_ivs = [c["iv"] for c in calls.values() if c["iv"] > 0]
        all_ivs += [p["iv"] for p in puts.values() if p["iv"] > 0]
        mean_iv = np.mean(all_ivs) if all_ivs else 0

        # --- Determine Regime ---
        # Sell premium conditions:
        #   - Low straddle price (market expects small move)
        #   - Low IV skew (no fear)
        #   - High gamma concentration near ATM (dealers stabilizing)
        # Trending conditions:
        #   - High straddle price (market expects big move)
        #   - High IV skew (fear/demand for protection)
        #   - Low gamma concentration (gamma spread across strikes)

        sell_score = 0
        trend_score = 0

        # Straddle: < 0.8% of underlying is low vol, > 1.5% is high vol
        if atm_straddle_pct < 0.8:
            sell_score += 2
        elif atm_straddle_pct < 1.2:
            sell_score += 1
        elif atm_straddle_pct > 1.5:
            trend_score += 2
        else:
            trend_score += 1

        # IV Skew: < 0.03 is calm, > 0.08 is fearful
        if abs(iv_skew) < 0.03:
            sell_score += 1
        elif abs(iv_skew) > 0.08:
            trend_score += 1

        # Gamma concentration: > 0.5 means stabilizing, < 0.3 means spread out
        if gamma_concentration > 0.5:
            sell_score += 1
        elif gamma_concentration < 0.3:
            trend_score += 1

        # Put/Call ratio: 0.7-1.3 is balanced, outside = directional bias
        if 0.7 <= put_call_premium_ratio <= 1.3:
            sell_score += 1
        else:
            trend_score += 1

        total_score = sell_score + trend_score
        if sell_score > trend_score:
            regime = "sell_premium"
            confidence = sell_score / total_score if total_score > 0 else 0.5
        elif trend_score > sell_score:
            regime = "trending"
            confidence = trend_score / total_score if total_score > 0 else 0.5
        else:
            regime = "uncertain"
            confidence = 0.5

        elapsed = time.time() - t_start
        logger.info(
            f"GEX: regime={regime} (conf={confidence:.2f}) "
            f"straddle={atm_straddle_pct:.2f}% skew={iv_skew:.4f} "
            f"pc_ratio={put_call_premium_ratio:.2f} gamma_conc={gamma_concentration:.2f} "
            f"mean_iv={mean_iv:.4f} ({elapsed:.1f}s)"
        )

        return GEXResult(
            timestamp=datetime.now(timezone.utc).isoformat(),
            underlying_price=underlying_price,
            atm_straddle_pct=atm_straddle_pct,
            iv_skew=iv_skew,
            put_call_premium_ratio=put_call_premium_ratio,
            gamma_concentration=gamma_concentration,
            mean_iv=mean_iv,
            regime=regime,
            confidence=confidence,
            details={
                "atm_strike": atm_strike,
                "atm_call_mid": atm_call_mid,
                "atm_put_mid": atm_put_mid,
                "calls_count": len(calls),
                "puts_count": len(puts),
                "otm_put_iv": otm_put_iv,
                "otm_call_iv": otm_call_iv,
                "hours_remaining": hours_remaining,
                "sell_score": sell_score,
                "trend_score": trend_score,
            },
        )

    except Exception as e:
        logger.error(f"GEX calculation failed: {e}", exc_info=True)
        return None
