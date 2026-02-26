"""
Black-Scholes Greeks calculator for options features.
Matches PROJECT_ARCHITECTURE.md Section 4 (data/greeks_calculator.py) and Section 8a.

Computes 1st and 2nd order Greeks using closed-form Black-Scholes.
Used during training to generate 2nd order Greek features from:
    S = underlying price (from bars)
    K = S (ATM approximation)
    T = target_dte / 365
    r = risk-free rate (configurable, default 0.045)
    sigma = ATM implied volatility (from Theta Data options features)

2nd Order Greeks computed:
    vanna  = d(delta)/d(sigma) — how delta changes with IV (key for vol hedging)
    vomma  = d(vega)/d(sigma)  — convexity of vega (vol-of-vol sensitivity)
    charm  = d(delta)/d(T)     — delta decay per day (theta of delta)
    speed  = d(gamma)/d(S)     — rate of gamma change with price

Why these four:
    - Vanna: signals how much delta hedging is needed when vol moves (regime shifts)
    - Vomma: high vomma means option benefits from vol-of-vol (wings benefit)
    - Charm: shows delta drift overnight — important for multi-day holds
    - Speed: gamma convexity — high speed = gamma unstable near ATM

References:
    - Black, F. & Scholes, M. (1973). The Pricing of Options and Corporate Liabilities.
    - Hull, J.C. Options, Futures, and Other Derivatives (10th ed.), Chapter 19.
"""

import logging
import numpy as np
from scipy.stats import norm

logger = logging.getLogger("options-bot.data.greeks")


def _bs_d1_d2(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
) -> tuple[float, float]:
    """
    Compute Black-Scholes d1 and d2 intermediates.

    Args:
        S: Underlying price
        K: Strike price
        T: Time to expiration in years (e.g., 21/365)
        r: Risk-free rate (e.g., 0.045)
        sigma: Implied volatility (e.g., 0.30 for 30%)

    Returns:
        (d1, d2) tuple
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0, 0.0
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2


def compute_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "call",
) -> dict:
    """
    Compute full Black-Scholes 1st and 2nd order Greeks for a single option.

    Args:
        S: Underlying price (e.g., 250.0)
        K: Strike price (e.g., 250.0 for ATM)
        T: Time to expiration in years (e.g., 21/365 ≈ 0.0575)
        r: Risk-free rate as decimal (e.g., 0.045)
        sigma: Implied volatility as decimal (e.g., 0.30)
        option_type: "call" or "put"

    Returns:
        Dict with keys:
            # 1st order
            delta, gamma, theta, vega, rho
            # 2nd order
            vanna, vomma, charm, speed
        All values are floats. Returns all-zero dict if inputs are invalid.

    Notes:
        - theta is per calendar day (divided by 365)
        - vega is per 1% move in IV (divided by 100)
        - vomma is per 1% move in IV (vega * d1*d2/sigma / 100)
        - charm is per calendar day
    """
    if T <= 1e-6 or sigma <= 1e-6 or S <= 0 or K <= 0:
        return {k: 0.0 for k in [
            "delta", "gamma", "theta", "vega", "rho",
            "vanna", "vomma", "charm", "speed",
        ]}

    d1, d2 = _bs_d1_d2(S, K, T, r, sigma)
    sqrt_T = np.sqrt(T)
    n_d1 = norm.pdf(d1)       # Standard normal PDF at d1
    N_d1 = norm.cdf(d1)       # CDF at d1
    N_d2 = norm.cdf(d2)
    N_neg_d1 = norm.cdf(-d1)
    N_neg_d2 = norm.cdf(-d2)
    disc = np.exp(-r * T)     # Discount factor

    # ─── 1st Order Greeks ───────────────────────────────────────────────────

    # Gamma is identical for calls and puts
    gamma = n_d1 / (S * sigma * sqrt_T)

    if option_type.lower() == "call":
        delta = N_d1
        theta = (
            -S * n_d1 * sigma / (2 * sqrt_T)
            - r * K * disc * N_d2
        ) / 365.0
        rho = K * T * disc * N_d2 / 100.0
    else:
        delta = N_d1 - 1.0
        theta = (
            -S * n_d1 * sigma / (2 * sqrt_T)
            + r * K * disc * N_neg_d2
        ) / 365.0
        rho = -K * T * disc * N_neg_d2 / 100.0

    # Vega is identical for calls and puts (per 1% IV move)
    vega = S * n_d1 * sqrt_T / 100.0

    # ─── 2nd Order Greeks ───────────────────────────────────────────────────

    # Vanna: d(delta)/d(sigma) = d(vega)/d(S)
    # Positive vanna: delta increases as IV rises (for calls)
    vanna = -n_d1 * d2 / sigma

    # Vomma (Volga): d(vega)/d(sigma) — vega's sensitivity to vol
    # Expressed per 1% move in IV to match vega units
    vomma = vega * d1 * d2 / sigma

    # Charm: d(delta)/d(T) — how much delta drifts per calendar day
    # Negative charm means delta decays (delta erodes toward 0 for OTM)
    if T > 1e-6:
        charm_raw = -n_d1 * (2 * r * T - d2 * sigma * sqrt_T) / (2 * T * sigma * sqrt_T)
        charm = charm_raw / 365.0  # Per calendar day
    else:
        charm = 0.0

    # Speed: d(gamma)/d(S) — how fast gamma changes with price
    # Negative speed: gamma decreases as price moves away from strike
    speed = -gamma / S * (d1 / (sigma * sqrt_T) + 1)

    return {
        "delta": float(delta),
        "gamma": float(gamma),
        "theta": float(theta),
        "vega":  float(vega),
        "rho":   float(rho),
        "vanna": float(vanna),
        "vomma": float(vomma),
        "charm": float(charm),
        "speed": float(speed),
    }


def compute_greeks_vectorized(
    S: np.ndarray,
    K: np.ndarray,
    T: np.ndarray,
    r: float,
    sigma: np.ndarray,
    option_type: str = "call",
) -> dict[str, np.ndarray]:
    """
    Vectorized Black-Scholes Greeks for arrays of values.

    Args:
        S: Array of underlying prices
        K: Array of strike prices (same length as S)
        T: Array of times to expiry in years (same length as S)
        r: Scalar risk-free rate
        sigma: Array of implied volatilities (same length as S)
        option_type: "call" or "put"

    Returns:
        Dict of arrays, same structure as compute_greeks().
        Rows where T<=0 or sigma<=0 are set to 0.0.

    Usage:
        # Compute ATM call Greeks across a time series:
        results = compute_greeks_vectorized(
            S=close_prices, K=close_prices,  # ATM: K=S
            T=np.full(len(close_prices), 21/365),
            r=0.045,
            sigma=atm_iv_series,
        )
        df['atm_call_vanna'] = results['vanna']
    """
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    T = np.asarray(T, dtype=float)
    sigma = np.asarray(sigma, dtype=float)

    # Mask invalid rows
    valid = (T > 1e-6) & (sigma > 1e-6) & (S > 0) & (K > 0)

    # Pre-allocate output arrays
    n = len(S)
    out = {k: np.zeros(n) for k in [
        "delta", "gamma", "theta", "vega", "rho",
        "vanna", "vomma", "charm", "speed",
    ]}

    if not valid.any():
        return out

    Sv = S[valid]
    Kv = K[valid]
    Tv = T[valid]
    sv = sigma[valid]
    sqrt_Tv = np.sqrt(Tv)

    d1 = (np.log(Sv / Kv) + (r + 0.5 * sv ** 2) * Tv) / (sv * sqrt_Tv)
    d2 = d1 - sv * sqrt_Tv

    n_d1 = norm.pdf(d1)
    disc = np.exp(-r * Tv)

    gamma_v = n_d1 / (Sv * sv * sqrt_Tv)
    vega_v  = Sv * n_d1 * sqrt_Tv / 100.0
    vanna_v = -n_d1 * d2 / sv
    vomma_v = vega_v * d1 * d2 / sv

    with np.errstate(invalid="ignore", divide="ignore"):
        charm_raw = -n_d1 * (2 * r * Tv - d2 * sv * sqrt_Tv) / (2 * Tv * sv * sqrt_Tv)
        charm_v = np.where(Tv > 1e-6, charm_raw / 365.0, 0.0)

    speed_v = -gamma_v / Sv * (d1 / (sv * sqrt_Tv) + 1)

    if option_type.lower() == "call":
        N_d1 = norm.cdf(d1)
        N_d2 = norm.cdf(d2)
        delta_v = N_d1
        theta_v = (-Sv * n_d1 * sv / (2 * sqrt_Tv) - r * Kv * disc * N_d2) / 365.0
        rho_v   = Kv * Tv * disc * N_d2 / 100.0
    else:
        N_d1 = norm.cdf(d1)
        N_neg_d2 = norm.cdf(-d2)
        delta_v = N_d1 - 1.0
        theta_v = (-Sv * n_d1 * sv / (2 * sqrt_Tv) + r * Kv * disc * N_neg_d2) / 365.0
        rho_v   = -Kv * Tv * disc * N_neg_d2 / 100.0

    out["delta"][valid] = delta_v
    out["gamma"][valid] = gamma_v
    out["theta"][valid] = theta_v
    out["vega"][valid]  = vega_v
    out["rho"][valid]   = rho_v
    out["vanna"][valid] = vanna_v
    out["vomma"][valid] = vomma_v
    out["charm"][valid] = charm_v
    out["speed"][valid] = speed_v

    return out


def get_second_order_feature_names() -> list[str]:
    """Return the 8 new 2nd order Greek feature column names added to base_features."""
    return [
        "atm_call_vanna", "atm_call_vomma", "atm_call_charm", "atm_call_speed",
        "atm_put_vanna",  "atm_put_vomma",  "atm_put_charm",  "atm_put_speed",
    ]