"""Setup scoring functions for the four scanner setup types.
Each returns a score 0.0-1.0 and a reason string."""

import logging
from dataclasses import dataclass
from typing import Optional

from scanner.indicators import (
    directional_bars, volume_vs_average, net_move_pct,
    rsi, bollinger_position, has_reversal_wick,
    range_pct, volume_declining,
)

logger = logging.getLogger("options-bot.scanner.setups")

# Thresholds (from architecture doc)
MOMENTUM_MIN_DIRECTIONAL = 5    # of 8 bars in same direction (was 6 — too restrictive)
MOMENTUM_MIN_VOL_RATIO = 1.5
MOMENTUM_MIN_MOVE_SPY = 0.20    # % for SPY (was 0.3 — never fired, data shows 0.20 gives 4-17/day)
MOMENTUM_MIN_MOVE_STOCK = 0.40  # % for individual stocks (was 0.6)

REVERSION_STD_THRESHOLD = 1.5   # Standard deviations from mean
REVERSION_RSI_HIGH = 75
REVERSION_RSI_LOW = 25

COMPRESSION_MAX_RANGE = 0.2     # % range over 15 bars
BREAKOUT_MIN_VOL_RATIO = 1.3

# Catalyst: unusual options volume threshold
# Total 30-min volume > 50% of prior-day OI for that strike qualifies.
CATALYST_VOL_OI_RATIO = 0.50
CATALYST_SENTIMENT_THRESHOLD = 0.70


@dataclass
class SetupScore:
    """Scored setup with reason for logging."""
    setup_type: str
    score: float      # 0.0 to 1.0
    reason: str       # What conditions drove the score
    direction: str    # "bullish", "bearish", or "neutral"


def score_momentum(bars, symbol: str) -> SetupScore:
    """Momentum: consistent directional movement with volume confirmation."""
    up_count, total = directional_bars(bars, 8)
    down_count = total - up_count
    dominant = max(up_count, down_count)
    direction = "bullish" if up_count > down_count else "bearish"
    vol_ratio = volume_vs_average(bars, 8, 60)
    move = abs(net_move_pct(bars, 8))
    min_move = MOMENTUM_MIN_MOVE_SPY if symbol == "SPY" else MOMENTUM_MIN_MOVE_STOCK

    # Score components
    directional_score = min(dominant / 8, 1.0)  # 8/8 = 1.0, 6/8 = 0.75
    vol_score = min(vol_ratio / (MOMENTUM_MIN_VOL_RATIO * 2), 1.0)
    move_score = min(move / (min_move * 2), 1.0)

    # All three must contribute
    if dominant < MOMENTUM_MIN_DIRECTIONAL:
        return SetupScore("momentum", 0.0, f"only {dominant}/8 directional bars", direction)
    if vol_ratio < 1.0:
        return SetupScore("momentum", 0.0, f"vol_ratio={vol_ratio:.2f} < 1.0", direction)
    if move < min_move:
        return SetupScore("momentum", 0.0, f"move={move:.3f}% < {min_move}%", direction)

    score = (directional_score * 0.4 + vol_score * 0.3 + move_score * 0.3)
    reason = f"{dominant}/8 bars {direction}, vol={vol_ratio:.2f}x, move={move:.3f}%"
    return SetupScore("momentum", round(score, 3), reason, direction)


def score_mean_reversion(bars, symbol: str) -> SetupScore:
    """Mean Reversion: extended move with exhaustion signals."""
    current_rsi = rsi(bars, 14)
    pctb, bandwidth = bollinger_position(bars, 20)
    move_5m = net_move_pct(bars, 5)
    has_wick = has_reversal_wick(bars)
    vol_dec = volume_declining(bars, 3)

    # Determine direction from extension
    if current_rsi > REVERSION_RSI_HIGH or pctb > 1.0:
        direction = "bearish"  # Overbought -> expect reversal down
    elif current_rsi < REVERSION_RSI_LOW or pctb < 0.0:
        direction = "bullish"  # Oversold -> expect reversal up
    else:
        return SetupScore("mean_reversion", 0.0, f"RSI={current_rsi:.1f} not extreme", "neutral")

    # Score components
    rsi_score = 0.0
    if current_rsi > REVERSION_RSI_HIGH:
        rsi_score = min((current_rsi - REVERSION_RSI_HIGH) / 25, 1.0)
    elif current_rsi < REVERSION_RSI_LOW:
        rsi_score = min((REVERSION_RSI_LOW - current_rsi) / 25, 1.0)

    bb_score = max(abs(pctb - 0.5) - 0.5, 0) * 2  # 0 if within bands, up to 1 outside
    wick_bonus = 0.15 if has_wick else 0.0
    vol_bonus = 0.10 if vol_dec else 0.0

    score = min(rsi_score * 0.4 + bb_score * 0.4 + wick_bonus + vol_bonus, 1.0)
    reason = f"RSI={current_rsi:.1f}, BB%b={pctb:.2f}, wick={has_wick}, vol_declining={vol_dec}"
    return SetupScore("mean_reversion", round(score, 3), reason, direction)


def score_compression_breakout(bars, symbol: str) -> SetupScore:
    """Compression Breakout: tight range breaking on volume."""
    compression_range = range_pct(bars, 15)
    last_bar_range = range_pct(bars, 1)
    vol_ratio = volume_vs_average(bars, 1, 15)
    _, bandwidth = bollinger_position(bars, 20)
    last_move = net_move_pct(bars, 1)
    direction = "bullish" if last_move > 0 else "bearish"

    # Must have tight compression first
    if compression_range > COMPRESSION_MAX_RANGE:
        return SetupScore("compression", 0.0, f"range={compression_range:.3f}% > {COMPRESSION_MAX_RANGE}%", "neutral")

    # Must break with volume
    if vol_ratio < BREAKOUT_MIN_VOL_RATIO:
        return SetupScore("compression", 0.0, f"breakout vol={vol_ratio:.2f}x < {BREAKOUT_MIN_VOL_RATIO}x", "neutral")

    # Must actually break outside the range
    if last_bar_range < compression_range * 0.5:
        return SetupScore("compression", 0.0, "no breakout bar yet", "neutral")

    compression_score = min((COMPRESSION_MAX_RANGE - compression_range) / COMPRESSION_MAX_RANGE, 1.0)
    vol_score = min(vol_ratio / 3.0, 1.0)
    breakout_score = min(last_bar_range / (compression_range + 0.001), 1.0)

    score = compression_score * 0.3 + vol_score * 0.4 + breakout_score * 0.3
    reason = f"range={compression_range:.3f}%, breakout vol={vol_ratio:.2f}x, last_bar={last_bar_range:.3f}%"
    return SetupScore("compression", round(score, 3), reason, direction)


def score_catalyst(
    bars, symbol: str,
    sentiment_score: float,
    options_vol_oi_ratio: Optional[float],
) -> SetupScore:
    """Catalyst: FinBERT sentiment + unusual options volume.

    BOTH conditions must be true:
      1. FinBERT sentiment magnitude > 0.65 (strongly directional)
      2. Options volume in last 30 min > 50% of prior-day OI

    Neither condition alone produces a score. This is enforced below
    with an explicit AND check — not an additive score.

    The 50% OI threshold means: if SPY $637 CALL had OI=2,984 yesterday,
    then 1,492+ contracts traded in 30 min qualifies as unusual.
    This threshold is adjustable via CATALYST_VOL_OI_RATIO.
    """
    direction = "bullish" if sentiment_score > 0 else "bearish" if sentiment_score < 0 else "neutral"
    sent_strong = abs(sentiment_score) >= CATALYST_SENTIMENT_THRESHOLD
    vol_unusual = (options_vol_oi_ratio is not None and options_vol_oi_ratio >= CATALYST_VOL_OI_RATIO)

    # BOTH conditions required — explicit AND
    if not sent_strong:
        return SetupScore("catalyst", 0.0, f"sentiment={sentiment_score:+.3f} < {CATALYST_SENTIMENT_THRESHOLD}", direction)
    if not vol_unusual:
        ratio_str = f"{options_vol_oi_ratio:.2f}" if options_vol_oi_ratio is not None else "unavailable"
        return SetupScore("catalyst", 0.0, f"options vol/OI={ratio_str} < {CATALYST_VOL_OI_RATIO}", direction)

    # Both met — score based on strength
    sent_score = min(abs(sentiment_score) / 1.0, 1.0)
    vol_score = min(options_vol_oi_ratio / 1.0, 1.0) if options_vol_oi_ratio else 0.0
    score = sent_score * 0.5 + vol_score * 0.5

    reason = f"sentiment={sentiment_score:+.3f} AND vol/OI={options_vol_oi_ratio:.2f} (both conditions met)"
    return SetupScore("catalyst", round(score, 3), reason, direction)
