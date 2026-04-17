# Bot Problems — Status Tracker

**Last updated:** 2026-04-17

## Issues FIXED since April 10

| Issue | Fix Date | What was done |
|-------|----------|---------------|
| Only buys puts | Apr 14 | Catalyst direction was correct (sentiment-driven). Added momentum/macro_trend setups that buy calls on bullish signals. |
| Market orders | Apr 14 | All orders now use limit prices (mid for entry, current price for exit). time_in_force="day". |
| PDT not working | Apr 14 | 3-level PDT gate: checks daytrading_buying_power, reserves last day trade for high confidence, catches Alpaca rejections. |
| No entry cooldown | Apr 14 | 30min cooldown in CHOPPY, 5min in TRENDING. Per-profile, recorded on submission. |
| No position cap | Apr 14 | Max 3 concurrent open positions (configurable). |
| Scanner finds nothing | Apr 14 | Momentum thresholds lowered (5/8 bars, 0.20% move). Mean reversion RSI 65/35. Added macro_trend (15-min bars). |
| Unrealized P&L wrong | Apr 10 | Uses option price, not stock price. |
| Trade records not written | Apr 7 | INSERT on fill confirmation only. Prevents phantom trades. |
| Signal logs empty | Apr 16 | Scanner rejections now logged with factor values and block reasons. |
| Crashes/freezes | Apr 8 | Registry key disables QuickEdit. ThetaData retry loop. Error state reset button. |
| Learning layer broken | Apr 14 | Fixed query (removed broken profiles join). Added TOD-aware bucketing. |
| Profit lock kills winners | Apr 17 | Profit lock (Priority 4) skipped when trailing stop is active. |
| Mean reversion accepts wrong setups | Apr 17 | All profiles now filter by setup_type in _profile_specific_entry_check. |
| Exit score lookup wrong | Apr 17 | Uses pos.setup_type instead of pos.profile.name. |
| SPY always CHOPPY | Apr 17 | TRENDING threshold lowered from 0.4% to 0.25% (30-min move). |

## Issues REMAINING

1. **No multi-timeframe confirmation.** The 1-minute scanner can't see daily trends. The macro_trend (15-min) helps but doesn't capture gap-and-run days where the move happens at open.

2. **Sentiment is weak.** FinBERT processes cached headlines, not real-time. TSLA often returns 0.000 sentiment when major news is happening. Sentiment is suppression-only (5% weight) until validated.

3. **No compounding.** The bot doesn't scale position size after wins within a session. The person who turned $700 into $70K compounded every win into the next trade. Our bot uses fixed % of account value per trade.

4. **Single-broker limitation.** Alpaca doesn't offer SPX/NDX index options. SPX options are cash-settled and PDT-exempt on some brokers — a major advantage our bot can't access.

5. **Reconciliation gap.** When Alpaca auto-closes positions with no order record (expiration, margin call), the cleanup marks them as order_never_filled at $0 P&L. The actual exit may have been at a non-zero value.
