"""Expected Value calculation for option contracts.
Pure math — no API calls, no state. Extracted from ml/ev_filter.py.

EV formula (delta-gamma approximation with theta acceleration):
    move = underlying_price * |predicted_move_pct| / 100
    expected_gain = |delta| * move + 0.5 * |gamma| * move^2
    theta_cost = |theta| * hold_days * theta_accel
    EV = (expected_gain - theta_cost) / premium * 100

Theta acceleration by DTE:
    DTE >= 21: 1.0x (linear decay)
    DTE 14-20: 1.25x (accelerating)
    DTE 7-13:  1.5x (fast decay)
    DTE < 7:   2.0x (extreme decay)
"""


def compute_ev(
    underlying_price: float,
    predicted_move_pct: float,
    delta: float,
    gamma: float,
    theta: float,
    premium: float,
    hold_days: float,
    dte: int,
) -> float:
    """Compute EV percentage for a contract. Returns EV as a percentage.

    Args:
        underlying_price: Current stock price
        predicted_move_pct: Expected % move (from scanner avg_move or scorer)
        delta: Option delta (absolute value used)
        gamma: Option gamma (absolute value used)
        theta: Option theta (daily, negative number)
        premium: Option mid price (bid+ask)/2
        hold_days: Expected holding period in days
        dte: Days to expiration

    Returns:
        EV as percentage. Positive = expected profit, negative = expected loss.
    """
    if premium <= 0:
        return -100.0

    move = underlying_price * abs(predicted_move_pct) / 100
    expected_gain = abs(delta) * move + 0.5 * abs(gamma) * move ** 2

    if dte >= 21:
        theta_accel = 1.0
    elif dte >= 14:
        theta_accel = 1.25
    elif dte >= 7:
        theta_accel = 1.5
    else:
        theta_accel = 2.0

    effective_hold = min(hold_days, max(dte, 1 / 24))  # Floor at 1 hour for 0DTE
    theta_cost = abs(theta) * effective_hold * theta_accel

    ev_pct = (expected_gain - theta_cost) / premium * 100
    return round(ev_pct, 2)
