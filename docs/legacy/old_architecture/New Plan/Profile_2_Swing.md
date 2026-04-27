# Profile 2: Swing

## Related Screenshots

- **Gains 1-4**: The trader holding LUNR, NBIS, ASTS, RKLB, PL calls 1-18 months out. Account value $242K (brokerage) and $372K (Roth IRA). Unrealized gains of +$81K and +$39K. This is swing/position trading — pick a direction, buy options with time, hold for weeks/months while the thesis plays out.
- **Example.webp**: (The original friend's bot screenshot showing QQQ scalping — less relevant to swing but shows directional options trading)

## How It Works Now

### Entry
1. Model: LGBMClassifier trained on 5-minute bars, predicts 1-day forward return direction (UP/DOWN)
2. Features: 83 technical indicators (RSI, MACD, Bollinger bands, OFI, etc.)
3. Confidence gate: min_confidence 0.22 (was 0.30, lowered because model rarely exceeds it)
4. VIX regime adjustment: reduces confidence in high-vol environments
5. EV filter: scans options chain for contracts with positive expected value using fallback Greeks (Lumibot Greeks return zero)
6. Strike selection: ATM ±5% moneyness range, 7-45 DTE

### Exit
1. Profit target: 100% (let winners run)
2. Stop loss: 12% (cut fast)
3. Trailing stop: activates at +15%, trails at 8% from peak
4. Underlying reversal: exit if underlying moves 1.5% against trade direction
5. Max hold: 7 days
6. DTE floor: close if < 3 DTE remaining

### Current Problems

**Problem 1: The model predicts the wrong thing.**
It predicts "will TSLA go up or down tomorrow" using 5-minute bar features. This is nearly random for swing trades — 5-minute technicals don't predict multi-day moves. The Gains 1-4 trader isn't reading 5-minute RSI to decide to buy LUNR calls 10 months out. They're reading sector momentum, news catalysts, and multi-week price trends.

**Problem 2: The model trains on the wrong timeframe.**
Training on 5-minute bars with a 78-bar (1-day) forward label creates massive label overlap — 77 consecutive bars share nearly identical forward returns. The model memorizes autocorrelated noise instead of learning real patterns.

**Problem 3: Features don't match the decision.**
A swing trade decision should be informed by:
- Is this stock in a multi-day uptrend or downtrend?
- Has the sector been gaining momentum?
- Is there unusual options activity (institutional positioning)?
- What's the earnings calendar look like?
- Is volatility contracting (good for buying) or expanding (expensive)?

None of these are captured by 5-minute RSI or 1-minute Bollinger bands.

**Problem 4: 12% stop loss is too tight for swing options.**
Multi-day options fluctuate 10-20% intraday just from normal theta decay and bid-ask spread changes. A 12% stop gets triggered by noise on day 1, before the trade thesis has any time to play out. The TSLA PUTs that bled to -42% were the opposite extreme — too loose. The right answer is somewhere in between, tied to the underlying movement, not the option price.

**Problem 5: The bot enters too many positions in the same direction on the same day.**
On March 12, the bot entered 3 CALL positions and 1 PUT on TSLA simultaneously. A swing trader picks ONE direction and commits. Multiple conflicting positions cancel each other out.

## How It Should Work

### Core Change: Daily Timeframe, Not Intraday

Swing trading operates on daily candles, not 5-minute bars. The model should:
- Run ONCE per day (not every 5 minutes)
- Use daily features (moving averages, daily volume trends, sector performance)
- Predict "will this stock move 3%+ in one direction over the next 5-10 trading days?"

### Entry Logic

#### Step 1: Daily Signal (runs once at 10:00 AM ET)

Why 10:00 AM: the opening 30 minutes are noisy (gap fills, overnight order execution). By 10:00 AM, the day's direction is usually established and we have enough price action to confirm.

The model evaluates:
- Is there a multi-day trend forming?
- Is volume supporting the trend?
- Is the sector moving in the same direction?
- Is IV at a level where buying options is favorable?

Output: UP signal, DOWN signal, or NO TRADE.

#### Step 2: Conviction Check

Minimum confidence: 0.25 (meaning the model estimates 62.5% probability of a 3%+ move in the predicted direction within 10 days).

#### Step 3: Position Check

- Only ONE open swing position per symbol at a time
- If there's already an open TSLA swing trade, skip
- No conflicting positions (don't buy puts if you already hold calls)

#### Step 4: Strike and Expiration Selection

- DTE: 14-45 days (enough time for the thesis to play out, not so much that you overpay for theta)
- Strike: ATM to slightly ITM (delta 0.50-0.65 for high responsiveness to underlying movement)
- Prefer the nearest monthly expiration over weeklies (tighter bid-ask spreads, more liquidity)

#### Step 5: Entry

- Buy calls if signal is UP, puts if signal is DOWN
- Position size: 20-30% of account (1-3 contracts depending on account size)
- Single entry, no scaling in (keep it simple for now)

### Exit Logic

#### Exit 1: Underlying-Based Trailing Stop (PRIMARY EXIT)

This is the key change. Stop loss and profit target should be based on the UNDERLYING stock movement, not the option price. Option prices are noisy (theta, IV changes, bid-ask). The underlying tells you if your thesis is right or wrong.

- **Initial stop**: underlying moves 2.5% against trade direction from entry → exit
- **Trailing activation**: underlying moves 2% in your favor → trailing stop activates
- **Trail distance**: 1.5% of underlying price from the high-water mark
- **Example**: Enter TSLA calls when TSLA is $380. Initial stop = $370.50 (2.5% below). TSLA rises to $395 (+3.9%). Trail activates, stop is now $389.08 (1.5% below $395). TSLA pulls back to $389 → exit with a winner.

Why underlying-based: A TSLA call might be -15% on option price due to theta decay even though TSLA itself is flat. That's not a reason to exit — your directional thesis hasn't been proven wrong. Exit when the STOCK moves against you, not when the option fluctuates.

#### Exit 2: Time-Based Exit

- Max hold: 10 trading days (2 weeks)
- If the trade hasn't hit the trailing stop or been stopped out in 10 days, the thesis didn't play out. Close at market.
- DTE floor: close if option has < 5 DTE remaining regardless (avoid last-week gamma acceleration)

#### Exit 3: Thesis Invalidation

- If the model's daily signal flips from UP to DOWN (or vice versa) with high confidence (> 0.30), exit the position. The model is saying the trend has reversed.

#### Exit 4: Hard Stop on Option Price

- Emergency only: if option loses 50% of premium, exit regardless of underlying. This catches scenarios where IV crush kills the option even though the underlying is flat (e.g., post-earnings).

### ML Model: Daily Trend Classifier

#### What It Predicts

"Will [SYMBOL] move 3% or more in one direction within the next 10 trading days?"

Three classes:
- UP: stock will rise 3%+ in 10 days
- DOWN: stock will fall 3%+ in 10 days
- NEUTRAL: stock will stay within ±3% (no trade)

#### Training Data

- Daily bars, 2-5 years of history
- Label: look forward 10 trading days. If max price was 3%+ above entry → UP. If min price was 3%+ below → DOWN. Otherwise → NEUTRAL.
- Subsample: one sample per trading day (no overlap issues)
- Training samples: ~500-1250 per year per symbol

#### Features

**Trend features (daily):**
- sma_10, sma_20, sma_50: simple moving averages
- price_vs_sma_10/20/50: price relative to each MA (above/below, by how much)
- sma_10_slope: is the 10-day MA trending up or down, and how steeply
- higher_highs_5d: count of days in last 5 where high > prior day high (trend strength)
- higher_lows_5d: count of days in last 5 where low > prior day low (uptrend confirmation)

**Momentum features (daily):**
- roc_5d, roc_10d, roc_20d: rate of change over 5/10/20 days
- daily_range_vs_avg: today's range vs 20-day average range (expansion = move starting)
- consecutive_up_days: how many green days in a row (mean reversion risk vs momentum)
- gap_pct: today's opening gap from yesterday's close

**Volume features (daily):**
- volume_sma_ratio: today's volume / 20-day average volume
- up_volume_ratio_5d: ratio of volume on up days vs down days over last 5 days
- obv_slope_10d: on-balance volume trend (are buyers or sellers in control)

**Volatility features:**
- atr_14: 14-day average true range (how much does this stock move daily)
- iv_rank: current implied volatility vs its 52-week range (low IV = cheap options = good time to buy)
- iv_vs_hv: implied vol vs historical vol (if IV < HV, options are underpricing actual movement)
- bollinger_width: how wide are the bands (contracting bands = breakout coming)

**Sector/market context:**
- spy_roc_5d: is the overall market trending?
- sector_etf_roc_5d: is the stock's sector trending? (XLK for tech, XLE for energy, etc.)
- stock_vs_sector_5d: is the stock outperforming or underperforming its sector?
- vix_level: overall market fear gauge
- vix_change_5d: is fear increasing or decreasing?

**Options flow features (from ThetaData):**
- put_call_ratio_5d: average daily P/C ratio over 5 days (extreme readings = institutional positioning)
- unusual_options_volume: today's options volume vs 20-day average (2x+ = unusual activity)
- large_trade_bias: are the big institutional option trades predominantly calls or puts

#### Model Type

- XGBoost or LightGBM multiclass classifier (UP/DOWN/NEUTRAL)
- Walk-forward validation with expanding window (train on 2 years, test on next 3 months, repeat)
- Isotonic calibration per class
- Expected accuracy: 55-65% on UP/DOWN calls (NEUTRAL class will be most common)

### Configuration Defaults

```
strategy_type: swing
check_frequency: once daily at 10:00 AM ET
min_dte: 14
max_dte: 45
prediction_horizon: 10 trading days
min_confidence: 0.25
max_concurrent_positions: 1 per symbol
position_size_pct: 25
max_contracts: 5
underlying_stop_pct: 2.5
underlying_trail_activation_pct: 2.0
underlying_trail_pct: 1.5
max_hold_days: 10
dte_floor: 5
option_hard_stop_pct: 50
thesis_reversal_confidence: 0.30
entry_time: "10:00"
preferred_delta_min: 0.50
preferred_delta_max: 0.65
```

### Risk Management

- Max 1 open position per symbol (no stacking)
- Max 3 total swing positions across all symbols (diversification)
- Position size 20-30% of account per trade
- Account daily loss limit: 10% (across all profiles, not just swing)
- No entries on earnings week (IV crush risk after earnings destroys option premium even if direction is correct)

### What Success Looks Like

- 1-3 new trades per week across all swing profiles
- 50-60% win rate on closed trades
- Average winner: +30-60% on option premium (underlying moved 3-5% in your favor)
- Average loser: -20-25% (stopped out by underlying reversal before theta destroys the position)
- Win/loss dollar ratio: 2:1 or better
- Monthly return: 10-20% of account (with compounding)

### What Failure Looks Like

- Trading every day (signals too loose — swing should be selective)
- Win rate below 40% (model isn't identifying trends correctly)
- Average loser > average winner (stops too wide or not tied to underlying)
- All positions in the same direction (no diversification — correlated risk)
- Entering during earnings week and getting IV crushed

### Key Differences From Current Implementation

| Aspect | Current | New |
|---|---|---|
| Model timeframe | 5-minute bars | Daily bars |
| Signal frequency | Every 5 minutes | Once per day at 10 AM |
| Features | 83 intraday technical indicators | Daily trend, volume, sector, options flow |
| Target | "UP or DOWN in 1 day" binary | "3%+ move in 10 days" three-class |
| Stop loss | 12% of option price | 2.5% of underlying price |
| Trailing stop | Based on option P&L | Based on underlying high-water mark |
| Max positions | Multiple same-direction | 1 per symbol |
| Hold time | Exits via arbitrary rules | Exits when underlying reverses or time expires |

### Open Questions

1. **Should the model incorporate news/sentiment?** Earnings surprises, analyst upgrades, FDA approvals — these drive multi-day moves. ThetaData doesn't provide news. We could add a news API later, but the base model should work without it.

2. **Sector ETF mapping** — we need a lookup table mapping stocks to their sector ETFs (TSLA → XLY or QQQ, AAPL → XLK, etc.). This is a one-time config.

3. **IV rank calculation** — requires 252 trading days of IV history. On a fresh symbol with no history, we'd need to fetch this before training. The data check step should handle this.

4. **Options flow features** — ThetaData provides trade-level data. Computing put/call ratios and unusual volume requires processing the full day's options trades. This is feasible but adds data fetch time. Could be deferred to v2.
