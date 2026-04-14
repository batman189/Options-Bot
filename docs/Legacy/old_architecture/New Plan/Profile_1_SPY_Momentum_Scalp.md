# Profile 1: SPY Momentum Scalp

## What This Profile Does

Detects when SPY is making a strong directional move intraday — either up or down — and rides it with ATM 0DTE options. This is the same strategy as the Reddit trader who made $41K in one hour on SPY puts. The bot doesn't predict direction in advance. It waits until a move is already happening, confirms it's real (not a fake-out), enters aggressively, and rides the momentum with a trailing stop.

## How It's Different From What We Have Now

| Aspect | Current SPY Scalp | New Momentum Scalp |
|---|---|---|
| **What the model predicts** | "Will SPY go up or down in 30 min?" | "Is a 0.5%+ directional move happening right now?" |
| **When it enters** | Every minute if confidence > threshold | Only when momentum is confirmed and accelerating |
| **Direction** | Model guesses direction | Bot reads direction from the move itself — no guessing needed |
| **Hold time** | Exits at fixed profit % or stop % | Rides the move with a trailing stop until momentum fades |
| **Trade frequency** | 5-20+ trades per day | 0-3 trades per day (most days 0-1) |
| **Win rate needed** | 50%+ (coin flip territory) | 40% is fine if winners are 3-5x losers |

## The Core Idea

The model doesn't need to predict the future. It needs to detect the present. When SPY drops $1.50 in 10 minutes on 3x average volume, that's not noise — that's a trend. A human sees this on a chart instantly. The model should too.

The edge isn't prediction accuracy. The edge is:
1. Detection speed (enter within seconds of confirmation)
2. Position sizing (go heavy when conviction is high)
3. Exit discipline (trail the stop, don't cut winners)

## Entry Logic

### Step 1: Momentum Detection (runs every 30 seconds)

Calculate in real-time:
- **Price velocity**: rate of change over last 5, 10, 15 minutes
- **Volume surge**: current 5-min volume vs 20-day average 5-min volume
- **VWAP deviation**: how far is price from VWAP and in which direction
- **Acceleration**: is the move speeding up or slowing down

A "momentum event" is detected when ALL of:
- Price has moved >= 0.3% in one direction in the last 15 minutes
- Current 5-min volume is >= 2x the 20-day average for this time of day
- Price is accelerating (the last 5-min candle moved more than the prior 5-min candle in the same direction)
- Price is on the correct side of VWAP (below VWAP for shorts, above for longs)

### Step 2: Confirmation (prevents fake-outs)

Wait for ONE of these confirmation signals before entering:
- **Break of a level**: price breaks the prior 30-min high/low
- **Failed bounce**: price attempted to reverse and failed (lower high in a downtrend, higher low in an uptrend)
- **Volume follow-through**: the next 1-min candle after detection has above-average volume in the trend direction

### Step 3: Entry

- Buy ATM calls if momentum is UP, ATM puts if momentum is DOWN
- Strike selection: nearest ATM strike (highest delta, most responsive to underlying movement)
- 0DTE only (maximum gamma = maximum responsiveness)
- Position size: 25-30% of account on high-conviction entries (volume + acceleration both strong), 15% on moderate entries

### Step 4: Scaling In (optional, for larger accounts)

If the move continues after initial entry:
- Add to position on pullbacks to VWAP in the trend direction
- Never add if position is currently losing
- Max 2 scale-in additions per trade

## Exit Logic

### Primary Exit: Trailing Stop

- **Activation**: Trailing stop activates immediately (no minimum profit needed — we want to protect capital from the start)
- **Trail distance**: 20% of current P&L when P&L > +30%, tightens to 10% when P&L > +80%
- **Example**: Entry $1.00, current $2.00 (+100%). Trail is 10% = stop at $1.80. If price goes to $2.50, stop moves to $2.25. Never moves down.

### Secondary Exit: Momentum Fade

Exit when the move is losing steam, even if trailing stop hasn't triggered:
- Volume drops below 1x average for 3 consecutive 1-min candles
- Price fails to make a new high/low for 5 minutes
- Acceleration reverses (move is decelerating)

### Hard Exits:

- **Time**: Close all positions by 3:45 PM ET (0DTE gamma risk in last 15 min)
- **Max loss**: 15% of entry price. If it's not working within the first 5 minutes, the signal was wrong.
- **Account loss**: If total day's losses exceed 5% of account, stop trading for the day

## ML Model: Momentum Classifier

### What It Predicts

Binary classification: **"Is the current price action the beginning of a move that will exceed 0.5% in the same direction within the next 30 minutes?"**

This is fundamentally different from predicting direction. By the time the model runs, the direction is already established (price is already moving). The model's job is to predict whether the move will CONTINUE or REVERSE.

### Training Data

Label construction from historical 1-minute SPY bars:
1. Find all moments where SPY moved >= 0.3% in 15 minutes (the detection threshold)
2. Label = 1 if price continued another 0.2%+ in the same direction within 30 minutes
3. Label = 0 if price reversed or stalled

This gives us a dataset of "momentum events" and whether they followed through. We're not predicting from random moments — only from moments where a move has already started.

### Features (real-time, not lagging)

**Momentum features:**
- price_velocity_5min: price change / 5 minutes
- price_velocity_10min: price change / 10 minutes
- price_velocity_15min: price change / 15 minutes
- acceleration: velocity_5min - velocity_10min (is it speeding up?)
- acceleration_of_acceleration: change in acceleration (2nd derivative)

**Volume features:**
- volume_surge_ratio: current 5-min volume / 20-day avg volume at this time
- volume_trend: is volume increasing or decreasing over last 3 candles
- buy_volume_ratio: estimated buy volume / total volume (from uptick/downtick)
- cumulative_volume_delta: running net buy - sell volume for the day

**Price structure features:**
- vwap_deviation_pct: (price - VWAP) / VWAP * 100
- distance_from_day_high_pct: how far from today's high
- distance_from_day_low_pct: how far from today's low
- broke_30min_high: 1 if price just broke the 30-min rolling high
- broke_30min_low: 1 if price just broke the 30-min rolling low
- candle_body_ratio: body size / total range of last candle (strong candles have big bodies)

**Market context features:**
- time_of_day: minutes since market open (early moves behave differently)
- vix_level: current VIX (higher VIX = bigger moves more likely to follow through)
- spy_range_today_pct: today's range so far / avg daily range (has the day's move been used up?)
- gap_from_prev_close: opening gap size and direction

**Microstructure features (from options chain):**
- put_call_volume_ratio: real-time P/C ratio (extreme readings = institutional activity)
- atm_iv_change_5min: is implied vol spiking (someone knows something)
- dealer_gamma_exposure: GEX sign (positive = dealers dampen moves, negative = dealers amplify)

### Model Type

XGBoost classifier with:
- Isotonic calibration (so 0.80 confidence actually means 80% probability)
- Walk-forward validation on 6 months of 1-minute data
- Class weighting to handle imbalanced labels (momentum follow-throughs are less common than reversals)

### Expected Performance

- Training samples: ~500-1000 momentum events per month in SPY
- Expected accuracy on follow-through prediction: 60-70%
- With 3:1 win/loss ratio from trailing stops, 60% accuracy produces strong positive EV

## Risk Management

- **Max 1 open position at a time** (no stacking directional bets)
- **Max 3 trades per day** (if 3 trades fail, the market is choppy — stop trying)
- **Max daily loss: 5% of account** (hard stop)
- **No trading first 5 minutes** (opening auction creates false signals)
- **No trading last 15 minutes** (gamma risk on 0DTE)
- **Position size scales with confidence**: 15% at min threshold, 30% at high confidence

## What Success Looks Like

- 0-3 trades per day (many days will have 0 trades — that's correct)
- 50-60% win rate on entries
- Average winner: +40-80% of option premium
- Average loser: -15% of option premium (fast stop)
- Win/loss dollar ratio: 3:1 or better
- Monthly return: 15-30% of account (with compounding)

## What Failure Looks Like

- More than 5 trades per day (overtrading — signals are too loose)
- Win rate below 40% (fake-outs not being filtered)
- Average loser bigger than average winner (stops too wide or not firing)
- Entering on low-volume moves (no confirmation step)

## Dependencies

- ThetaData for real-time 1-minute bars and options chain data
- Alpaca for order execution
- Model trained on 6+ months of 1-minute SPY data with momentum labels
- GEX calculator for dealer positioning context

## Open Questions

1. Should the model run every 30 seconds or every minute? Faster = earlier entry but more false signals.
2. What's the minimum volume surge ratio? 2x is the starting point but may need tuning.
3. Should we scale in on larger accounts, or keep it simple with one entry per trade?
4. How much historical data is needed for training? 6 months of 1-min data = ~50K bars = ~3-5K momentum events.
