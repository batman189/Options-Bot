# Profile 3: Iron Condor

## Related Screenshots

None of the provided screenshots show iron condor trading directly. This strategy is the opposite of what the Reddit traders are doing — they're betting on big moves, iron condors profit when the market does NOT move. It's the "house" side of the bet.

## What Is an Iron Condor

An iron condor is four options trades at once:
1. Sell an OTM call (collect premium)
2. Buy a further OTM call (cap upside risk)
3. Sell an OTM put (collect premium)
4. Buy a further OTM put (cap downside risk)

You collect a net credit upfront. If the stock stays between your two short strikes by expiration, you keep the full credit. If it moves beyond either strike, you lose — but the bought wings cap your max loss.

**Example on SPY at $660:**
- Sell $665 call / Buy $668 call (bull call spread — bearish side)
- Sell $655 put / Buy $652 put (bear put spread — bullish side)
- Net credit: $0.55 per contract
- Max profit: $55 (keep the full credit if SPY stays between $655-$665)
- Max loss: $245 (spread width $3 minus credit $0.55, times 100)

**Why it works:** SPY stays within a $10 range on most days. When it does, you win. The edge comes from selling overpriced volatility — options premiums embed a "fear premium" that statistically overstates how much the market actually moves.

## How It Works Now

We already built an iron condor strategy. Here's what exists:

### Entry
1. GEX regime filter: only enter when dealer gamma positioning says the market is range-bound (regime = "sell_premium")
2. Time window: 10:00 AM - 2:30 PM ET
3. Strike selection: target 16-delta short strikes, $3 wide spreads
4. Cooldown: 30 minutes between entries
5. Max confidence gate: if the directional model has strong conviction (> 0.35), skip the IC (trending market = bad for IC)

### Exit
1. Profit target: 75% of max credit (was 50%, updated after simulation showed negative EV)
2. Stop loss: 1x credit received (was 2x, updated after simulation)
3. Hard close: 3:30 PM ET regardless (avoid last-30-min gamma risk on 0DTE)

### Current Status
- Profile exists in DB but is **paused** (dormant until account reaches $25K)
- Strategy class is built and functional
- GEX calculator is built
- Has executed one live trade successfully ($0.56 credit, exited at $0.08 debit = $48 profit)

### Current Problems

**Problem 1: Requires $25K+ to be viable.**
With $5K and 5% risk per trade, you can afford 1 contract. One contract on a $3 spread earns $55 max profit. At 1-2 trades per day, that's $30-80/day assuming 72% win rate — about $600-1600/month. Not bad in percentage terms (12-32%) but small dollar amounts. The strategy really shines at $25K+ where you run 5-10 contracts.

**Problem 2: GEX regime accuracy is unproven.**
The GEX calculator estimates dealer gamma exposure from the options chain. The "sell_premium" vs "trending" regime classification has been running for a few days. We don't have enough data to know if it's actually correct. If the regime filter lets ICs through on trending days, the stop loss gets hit frequently.

**Problem 3: Greeks fallback reduces strike selection quality.**
Lumibot's get_greeks() returns zero for all contracts. We use fallback Black-Scholes estimation with hardcoded gamma. This means the 16-delta target for short strikes is approximate — we might be selling at 20-delta or 12-delta without knowing.

**Problem 4: Multi-leg order execution on Alpaca.**
Alpaca supports multi-leg orders but the fill quality on 4-leg spreads can be poor. Wide bid-ask on the combined spread means the actual credit received may be significantly less than the theoretical mid-price.

## What Should Change

### Change 1: Keep It Dormant Until $25K

The simulation proved that iron condors at $5K have positive but tiny EV. Not worth the complexity and risk at this account size. When the account grows to $25K (from momentum scalp and swing gains), this profile activates.

The dormancy check should be automatic — if account equity >= $25K threshold, suggest activating in the UI. Don't start trading without user confirmation.

### Change 2: Validate GEX Regime Over Time

Before trusting the GEX filter with real money:
- Log the regime classification every hour while the bot runs
- After 30 days, compare: on days the filter said "sell_premium," did SPY actually stay in a range? On days it said "trending," did SPY actually make a big move?
- If the regime accuracy is below 60%, the filter is noise and should be replaced with a simpler approach (VIX level + recent realized volatility)

### Change 3: Better Strike Selection

Instead of targeting a fixed 16-delta with fallback Greeks, use the options chain directly:
- Find the strike where the option price is approximately $0.30-0.50 (OTM enough that it has ~16-20 delta intrinsically based on price alone)
- This doesn't require accurate Greeks — just find strikes where the option premium matches what a 16-delta option should cost at current IV

### Change 4: Wider Spreads for Better Risk/Reward

$3 wide spreads have poor reward/risk ($55 max profit vs $245 max loss = 0.22 ratio). Consider:
- $5 wide spreads: credit ~$0.80, max loss ~$420, ratio 0.19 — worse ratio but higher absolute profit
- $2 wide spreads: credit ~$0.40, max loss ~$160, ratio 0.25 — better ratio, lower profit

For $25K accounts, $3-5 wide with 5-10 contracts is the sweet spot. The current $3 default is fine.

### Change 5: Profit Target and Stop Based on Simulation

Already updated:
- Profit target: 75% of max credit (take $41 of $55 on a $3 spread)
- Stop loss: 1x credit ($55 loss, not $147)
- These parameters produce +EV at 72% win rate

No further changes needed — the simulation validated these numbers.

## Configuration Defaults

```
strategy_type: iron_condor
min_account_equity: 25000
check_frequency: every 5 minutes during trading window
trading_window_start: "10:00"
trading_window_end: "14:30"
hard_close_time: "15:30"
ic_target_delta: 0.16
ic_spread_width: 3.0
ic_profit_target_pct: 75
ic_stop_multiplier: 1.0
entry_cooldown_minutes: 30
max_concurrent_ic_positions: 3
max_daily_trades: 5
max_daily_loss_pct: 5
gex_regime_required: "sell_premium"
max_directional_confidence: 0.35
position_size_pct: 5
```

## ML Model: Regime Classifier

### What It Predicts

Binary: "Is the market likely to stay range-bound today?"
- YES → safe to sell premium (iron condor)
- NO → sit out (trending day, IC will get stopped)

### Features

**Volatility features:**
- vix_level: current VIX
- vix_change_1d: did VIX go up or down yesterday
- iv_rank_spy: where is SPY's IV relative to its 52-week range
- realized_vol_5d vs implied_vol: if RV < IV, options are overpriced (good for selling)

**GEX features:**
- net_gex: net dealer gamma exposure (positive = dealers dampen moves)
- gex_flip_distance: how far is SPY from the "zero gamma" level
- put_wall_distance: how far from the largest put open interest strike
- call_wall_distance: how far from the largest call open interest strike

**Market structure:**
- spy_range_3d: average daily range over last 3 days (narrow = range-bound)
- overnight_move: how much did futures move overnight (small = calm day likely)
- day_of_week: some days are statistically calmer than others
- fomc_this_week: binary — FOMC weeks are volatile, don't sell premium
- opex_this_week: monthly options expiration week — gamma effects amplified

### Training Data

- Daily labels: was SPY's intraday range < 0.8%? If yes → range_bound (sell premium). If > 0.8% → trending (sit out).
- 2-3 years of daily data
- ~500-750 samples per year

### Expected Performance

- 65-75% accuracy on regime classification
- Even at 65%, combined with the simulation-validated exit rules, the strategy is profitable

## Risk Management

- Max loss per IC position: defined by spread width minus credit ($245 on a $3 spread at $0.55 credit)
- Max 3 open IC positions at once
- Max 5% of account risked per trade
- Max 15% of account in total IC exposure
- Hard close all positions by 3:30 PM on 0DTE
- No entries on FOMC days, NFP days, or CPI release days (scheduled vol events)

## What Success Looks Like

- 1-2 trades per favorable day, 3-4 favorable days per week
- 65-75% win rate
- Average winner: +$41 per contract (75% of credit)
- Average loser: -$55 per contract (1x credit stop)
- Monthly return: 5-10% of account at $25K+ (compounding with 5-10 contracts)
- Steady, boring income — no home runs, just consistent small wins

## What Failure Looks Like

- Win rate below 60% (regime filter is wrong too often)
- Average loser bigger than 1x credit (stop not executing properly)
- Trading on trending days (regime filter broken)
- Trading on FOMC/CPI days (event calendar not implemented)
- Slippage eating the credit on entry (fill quality too poor)

## When to Activate

This profile stays dormant until:
1. Account equity exceeds $25,000
2. GEX regime filter has been validated over 30+ days of logging
3. User manually confirms activation

The UI should show a status like: "Iron Condor — Dormant (requires $25K equity, currently $X,XXX)"

## Open Questions

1. **0DTE vs weekly expirations?** 0DTE has the fastest theta decay (most profit potential) but also the most gamma risk. Weekly (2-5 DTE) is safer but lower premium. Starting with 0DTE as designed, but could add a "conservative" mode with weeklies.

2. **Alpaca multi-leg fill quality** — we've had one successful fill. Need more data on how often fills get partially filled or rejected.

3. **Should GEX be required or advisory?** Currently required (no GEX sell_premium = no trade). Could downgrade to a confidence multiplier — trade on any regime but reduce size on unfavorable regimes.

4. **Event calendar integration** — FOMC, CPI, NFP, earnings dates. We need a data source for these. Could hardcode major dates or use an API.
