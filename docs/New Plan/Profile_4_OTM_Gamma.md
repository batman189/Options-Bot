# Profile 4: OTM Gamma

## Related Screenshots

- **Scalping.webp**: The original screenshot that inspired this profile — showing a trader capitalizing on cheap far-OTM contracts during a sudden move
- **Example 2-4**: The SPY put trader who made $41K buying 350 contracts of slightly ITM puts and riding a 1-hour drop. While those were ATM not OTM, the concept is the same — cheap contracts that multiply during a fast directional move
- **The friend's QQQ bot**: Showed $122K gains on 0DTE scalping — likely a combination of ATM and OTM plays

## What This Profile Does

Buys cheap far-OTM 0DTE options — typically $0.03 to $0.20 per contract — in bulk. Holds for minutes. Waits for a sudden violent move in SPY that causes these options to spike 5-50x in value. Sells into the spike.

This is the "lottery ticket" strategy. Most trades lose the full premium (the options expire worthless). But when it hits, a $200 position becomes $2,000-$10,000. The math works if even 1 in 10 trades is a big winner, because the winners are so much larger than the losers.

**Real-world example:**
- SPY at $660, buy 100 contracts of $655 puts at $0.05 each = $500 total risk
- SPY drops $3 in 15 minutes to $657
- Those $655 puts go from $0.05 to $0.80 (16x)
- Sell all 100 contracts = $8,000. Profit: $7,500

This happens 2-3 times per month on SPY. The challenge is being positioned BEFORE the move, not after.

## How It Works Now

### Entry
1. Model: same ScalpPredictor as SPY Scalp (XGBoost classifier on 1-min bars)
2. Confidence gate: 0.30 (rarely triggered)
3. GEX gate: only enters when regime = "trending" (dealers will amplify moves, not dampen)
4. Moneyness: 3-10% OTM
5. Min premium: $0.03, max premium: $1.50
6. Cooldown: 60 minutes between entries

### Exit
1. Trailing stop: activates at +50%, trails at 30% from peak
2. Profit target: 300%
3. Stop loss: 80%
4. DTE exit: 3:45 PM ET

### Current Problems

**Problem 1: It traded 133 times in one day for -$86.**
Instead of waiting for the rare explosive setup, it fired on every weak signal and bought penny options that expired worthless the same day. 133 round-trips at $0.03-0.10 per contract with 50-100% bid-ask spread means you lose half your money just entering and exiting.

**Problem 2: The model doesn't detect gamma explosion setups.**
The current model predicts "UP or DOWN in 30 minutes" which has nothing to do with "is a large sudden move about to happen." The model needs to detect the CONDITIONS for a spike — not predict direction.

**Problem 3: Most OTM options expire worthless even if you pick direction correctly.**
Buying $0.05 puts when SPY is at $660 means the $655 put needs SPY to drop below $655 PLUS recover the premium. A 0.3% move in your favor does nothing to a far-OTM option — you need a 0.8%+ move minimum. The entry timing has to be precise.

**Problem 4: Bid-ask spread on penny options is catastrophic.**
A $0.05 option might have a bid of $0.03 and ask of $0.07. You buy at $0.07, try to sell at $0.03. You've lost 57% before the underlying moves at all. This kills any strategy that trades frequently.

## What Should Change

### Core Change: Event Detection, Not Direction Prediction

This profile should NOT trade frequently. It should detect the specific market microstructure conditions that precede large sudden moves and ONLY enter then. The model's question changes from "which direction?" to "is a large move about to happen in either direction?"

When a large move IS detected as imminent:
- Check which direction momentum is already pointing (from the first few seconds/minutes of the move)
- Buy in THAT direction (ride the move, don't predict it)
- The OTM contracts are so cheap that even 5-10x on a small position is a big win

### Entry Logic

#### Step 1: Calm Before the Storm Detection (runs every minute)

The best gamma explosion setups happen when:
- Volatility has been compressing (narrow range morning, Bollinger bands squeezing)
- Volume suddenly spikes (2-3x normal) within a 5-minute window
- GEX is negative (dealers are short gamma — they will AMPLIFY any move, not dampen it)
- VIX term structure inverts or spikes (fear is entering the market)

The model should predict: "Will SPY's next 30-minute range exceed 0.8%?"

If yes → prepare to enter.

#### Step 2: Direction Confirmation (runs every 30 seconds when Step 1 triggers)

Once we know a big move is likely:
- Wait for the first 1-2 minutes of the move to establish direction
- Confirm with volume (is volume in the direction of the move?)
- Confirm with VWAP (did price break away from VWAP?)

This means we enter 1-2 minutes INTO the move, not before it. That's fine — a 0.8% SPY move takes 10-30 minutes. Missing the first 1-2 minutes and catching the remaining 8-28 minutes is still hugely profitable on far-OTM options.

#### Step 3: Strike Selection

- Buy OTM in the direction of the move:
  - SPY dropping → buy puts 1-2% below current price
  - SPY rising → buy calls 1-2% above current price
- Target contracts priced $0.10-0.50 (not the absolute cheapest pennies — those have the worst spreads)
- 0DTE ONLY (maximum gamma, maximum responsiveness)
- Select strikes with the tightest bid-ask spread within the target range

#### Step 4: Position Size

- Max 10% of account on any single OTM play
- With $5K: max $500 at risk
- At $0.10/contract: 50 contracts. At $0.30/contract: ~16 contracts
- This is a defined-risk bet: you lose $500 or you make $2,000-$10,000

### Exit Logic

#### Exit 1: Trailing Stop (PRIMARY)

- Activates at +100% (option has doubled)
- Trail: 30% from peak
- Example: Buy at $0.15, spikes to $1.50 (+900%). Trail stop at $1.05. If it pulls back to $1.05, exit with +600%.
- Why 30% trail: OTM options are extremely volatile. A 20% pullback during a continued move is normal. 30% allows for noise while protecting most gains.

#### Exit 2: Momentum Fade

- The move is over when volume drops back to normal levels for 3 consecutive minutes
- Exit at market regardless of P&L — the spike is done, holding longer only loses theta

#### Exit 3: Time Exits

- If not in profit after 10 minutes → exit. The move didn't materialize or has already passed.
- Hard close at 3:45 PM ET (0DTE gamma risk in last 15 minutes)

#### Exit 4: Full Loss Accepted

- If the option goes to $0.01 or becomes worthless, that's expected. The $500 was the defined risk.
- No stop loss on the downside — the premium paid IS the max loss. Putting a stop at -80% on a $0.10 option ($0.02) just guarantees a loss on every trade. Let it ride or expire.

### ML Model: Volatility Spike Predictor

#### What It Predicts

Binary: "Will SPY's price range over the next 30 minutes exceed 0.8%?"

This is NOT direction prediction. It predicts whether a large move of ANY kind is coming. Direction is determined after the move starts (Step 2).

#### Why 0.8%?

- SPY's average 30-minute range is about 0.2-0.3%
- 0.8% is roughly 3 standard deviations — a significant outlier
- A 0.8% move on SPY ($660) = $5.28. That's enough to take a $655 put from $0.05 to $0.50-2.00+
- These events happen 2-5 times per week (not daily, but not rare)

#### Training Data

- 1-minute SPY bars, 6+ months
- For every minute during trading hours, label:
  - 1 if the max range over the NEXT 30 minutes exceeded 0.8% of the price at that minute
  - 0 otherwise
- Positive class will be rare (~5-10% of samples) → class weighting needed

#### Features

**Volatility compression features:**
- bollinger_width_5min: how tight are 5-min Bollinger bands (tighter = more explosive potential)
- atr_5min_vs_atr_20d: is 5-min ATR contracting relative to normal (low reading = coiling)
- range_last_30min_vs_avg: has the last 30 min been unusually calm (calm before storm)
- consecutive_narrow_candles: how many 1-min candles in a row were below-average range

**Volume surge features:**
- volume_1min_vs_avg: is current 1-min volume elevated
- volume_acceleration: is volume increasing rapidly (derivative of volume)
- cumulative_volume_vs_expected: total volume so far today vs what's normal for this time of day
- large_print_detected: did a block trade just execute (institutional activity)

**Options market features:**
- vix_1min_change: is VIX spiking in real-time
- spy_0dte_volume_surge: is 0DTE options volume spiking (traders positioning for a move)
- put_call_ratio_intraday: extreme intraday readings (panic or euphoria building)
- atm_iv_change_5min: is ATM implied volatility rising (market pricing in a move)

**Dealer positioning:**
- net_gex: dealer gamma exposure (negative = dealers amplify moves)
- gex_regime: sell_premium vs trending (from GEX calculator)
- dix_proxy: dark pool activity indicator if available

**Market context:**
- time_of_day: spikes cluster around 10:00-10:30, 14:00-14:30, and 15:00-15:30
- minutes_since_last_spike: when was the last 0.8% move (they tend to cluster)
- spy_gap_from_prev_close: large gaps increase intraday reversal probability
- fomc_today: FOMC announcements cause massive spikes

#### Model Type

- XGBoost classifier with heavy class weighting (positive class is rare)
- Optimize for RECALL on the positive class — it's better to have false positives (enter and lose $500 on a false alarm) than false negatives (miss a $5,000 winner)
- Isotonic calibration
- Walk-forward validation on 3-6 months of 1-minute data

#### Expected Performance

- Positive class is ~5-10% of samples
- Target: 30-40% precision at 70%+ recall
- Meaning: of the times the model says "spike coming," 30-40% actually produce a large move. But we catch 70%+ of all large moves.
- At 30% precision with 10% account risk: 3 out of 10 signals hit, 7 lose $500 each ($3,500 total losses), 3 produce $2,000-5,000 each ($6,000-15,000 total wins). Net positive.

## Configuration Defaults

```
strategy_type: otm_gamma
check_frequency: every 1 minute during trading hours
min_account_equity: 10000
trading_window_start: "09:35"
trading_window_end: "15:30"
hard_close_time: "15:45"
spike_threshold_pct: 0.8
min_premium: 0.10
max_premium: 0.50
otm_range_pct: 1.0 to 2.0 (1-2% OTM from current price)
position_size_pct: 10
max_contracts: 100
max_daily_trades: 3
trailing_stop_activation_pct: 100
trailing_stop_pct: 30
max_hold_minutes: 10 (if not in profit)
momentum_fade_exit: true (exit when volume normalizes)
no_downside_stop: true (premium paid is the max loss)
```

## Risk Management

- Max 10% of account per trade ($500 on $5K, $1,000 on $10K)
- Max 3 trades per day (3 false alarms = 30% of account lost — hard limit)
- Max 20% of account at risk across all OTM positions in a single day
- No entries in the first 5 minutes (opening noise) or last 15 minutes (gamma chaos)
- Account-level circuit breaker: if OTM losses exceed 20% of account for the week, pause OTM trading until next Monday

## What Success Looks Like

- 0-2 entries per day (many days will have 0 — that's correct)
- 6-10 entries per month
- 2-3 of those entries catch real spikes: +300% to +2000% on the position
- 7-8 of those entries lose most or all of premium: -80% to -100%
- Net monthly P&L: positive due to the massive asymmetry of winners
- Monthly return: highly variable. Some months +50%, some months -15%. Average over 6 months: +10-20% monthly

## What Failure Looks Like

- More than 5 entries per day (model is generating too many false positives)
- No winners in 20 consecutive trades (model isn't detecting real spikes)
- Entering on low-volume, slow drift moves (not actual gamma spikes)
- Winners only producing +50-100% instead of +300%+ (entering too late or exiting too early)
- Bid-ask spread consuming all profits (trading options priced below $0.10)

## When to Activate

Currently paused due to $5K account. Recommended activation at $10K+. At $5K, the $500 max risk per trade is tight — 3 losses in a day is $1,500 (30% of account). At $10K, that same scenario is 15% — more manageable.

However, if the user wants to run it at $5K with reduced position size (5% = $250 per trade), that's viable. The max daily loss becomes $750 (15% of account) which is aggressive but survivable.

## Open Questions

1. **$5K activation or wait for $10K?** The user previously wanted this active. At 5% sizing ($250/trade, max 3/day = $750 max daily loss = 15% of account), it's doable but aggressive. User's call.

2. **Should direction come from the momentum model or from real-time price action?** The plan says "wait for the move to start, then enter in that direction." An alternative is using the scalp model's directional prediction to pre-position BEFORE the move. Pre-positioning has more upside (catch the full move) but more false positives (direction wrong + no move = double wrong).

3. **Minimum viable spike data** — how many real spike events are in 6 months of 1-min data? If SPY has 2-5 events per week that exceed 0.8% in 30 minutes, that's ~50-130 positive samples in 6 months. Is that enough to train a model? May need 12 months of data or a lower spike threshold (0.6%).

4. **Should this use the same model as Momentum Scalp?** Both detect "is a move happening." The difference is Momentum Scalp rides the move with ATM options and OTM Gamma rides it with cheap far-OTM. Could share the same detection model with different trade execution. Worth considering to reduce complexity.
