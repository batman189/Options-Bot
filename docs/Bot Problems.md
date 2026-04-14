# Bot Problems — Honest Accounting of What's Broken

**Date:** 2026-04-10

---

## What the bot was designed to do

The architecture document, the build phases, and every conversation about this bot described a system that:

1. Scans for directional momentum setups in real time
2. Buys calls when bullish, puts when bearish
3. Uses limit orders to control entry price
4. Scalps quick moves — enters, takes profit at a target, gets out
5. Manages PDT by tracking day trades and stopping before the limit
6. Tracks every trade in the database with accurate P&L
7. Runs unattended during market hours without crashing
8. Shows accurate live data in the UI

## What the bot actually does today

### It only buys puts

The catalyst profile — the only profile that has triggered entries — exclusively bought puts. Every single real trade the bot has placed has been a PUT. The momentum profile never fires (all setups score 0 for SPY). The mean reversion profile never fires (confidence always below threshold). The only profile that produces entries is catalyst, and it appears to always pick puts.

The architecture says the profile's `should_enter()` returns a direction (bullish or bearish) and the selector picks calls for bullish, puts for bearish. But in practice the bot has never once bought a call. I never verified that the bullish path works. I never checked what direction the catalyst profile returns. I built the code, said it was ready, and never traced a single bullish signal through to a call purchase.

### It uses market orders

Every order the bot submits is a market order. The Lumibot `create_order()` call at Step 8 does not specify a limit price. Market orders on options get terrible fills — wide spreads mean you lose money the instant you enter. The person on Robinhood uses limit orders at specific prices. Our bot does not.

This was never flagged as an issue during the build. The architecture document doesn't mention order types. I defaulted to market orders because that's what Lumibot uses by default, and I never questioned whether that was the right choice for options.

### It cannot manage PDT

The PDT protection has been rebuilt three times and still doesn't work reliably. The April 9 session submitted 284 rejected orders. The April 10 session submitted duplicate exits from two strategy instances. The core problems:

- The bot enters positions without checking whether it can exit them. It bought 8 puts on April 9 knowing (or should have known) that selling them same-day would hit PDT.
- The PDT check I built queries Alpaca's `daytrade_count` but Alpaca's enforcement is stricter than the textbook rule. Alpaca zeros out `daytrading_buying_power` when `daytrade_count` reaches 3, blocking sells even for positions bought on prior days.
- The bot has no concept of "if I enter this trade, what happens when I need to exit?" It evaluates entry and exit as completely separate decisions with no forward planning.

### It crashes or freezes regularly

The bot has not run for a full trading day without intervention since it was deployed. Every day has required manual restarts, database corrections, or code fixes:

- April 6: ThetaData session error crashed both profiles, error state with no way to clear
- April 7: ran but never traded (all setups score 0)
- April 8: Windows QuickEdit froze the process, then my "fix" made it crash every 30 minutes
- April 9: 284 PDT rejections, bought 8 puts it couldn't sell
- April 10: duplicate exit orders from both strategy instances, buying power errors, positions trapped

### The scanner finds almost nothing

The momentum and mean reversion setup scorers return 0 for SPY on nearly every iteration. Only the catalyst profile triggers, and only when FinBERT sentiment is strong enough. The momentum scorer — which should be the primary driver for the kind of trading shown in your screenshots — has never produced a score above 0 for SPY in any session I can find in the logs.

I never validated the momentum scoring thresholds against real SPY price action. I never checked whether the indicators (RSI, MACD, volume surge, etc.) are calibrated to detect the kind of intraday moves that would make a 0DTE scalp profitable. I built the scorer, said it was ready, and moved on.

### Unrealized P&L was calculated using stock price instead of option price

For over a week, the trade manager computed unrealized P&L by comparing the SPY stock price ($680) to the option entry price ($1.25), producing +54,000% gains that were completely fictitious. The profile page showed +$540,000. This was only discovered when you reported it. I built the P&L calculation, never tested it with a real open position, and declared it working.

### Trade records were not written to the database

For the first two days of trading, the bot placed real orders through Alpaca but wrote nothing to the trades table. Every trade was tracked in memory only. When the bot restarted, all trade history was lost. The UI showed no trades, no P&L, no history. I had to write a backfill script after the fact to reconstruct what happened from Alpaca's order history.

The DB INSERT was in the wrong place — it ran before Alpaca confirmed the fill, creating phantom records for orders that were never actually filled. This was fixed, but only after it created 4 phantom trades that showed -$986 in fake losses.

### The exit logic creates duplicate orders

`_submit_exit_order()` matched broker positions by symbol and expiration but not by strike. When multiple trades held the same option, each trade's exit attempted to sell the entire broker position. Four trades each tried to sell 4 contracts, creating 16 sell attempts for 4 contracts. Both strategy instances (SPY and TSLA) loaded the same open trades and both tried to exit them.

### There is no trade cooldown

The bot enters a new trade every iteration (every 1 minute for SPY, every 5 minutes for TSLA) as long as the scorer says enter. On April 6 it entered 11 SPY put trades in 10 minutes — one per minute. On April 9 it entered 8 trades in 8 minutes. There is no logic that says "I just entered a position, wait before entering another." The `entry_cooldown_minutes` config value exists but is never checked by V2Strategy.

### The stale trade cleanup guesses instead of checking

`_cleanup_stale_trades()` has been rewritten three times. Each version had the same fundamental problem: it assumed outcomes instead of verifying them. The first version assumed -100% loss. The second version checked Alpaca orders but used the wrong date range. The third version checks Alpaca positions but can't distinguish between "expired worthless" and "Alpaca auto-sold at a small value." Every correction required manual database edits after the fact.

---

## What should exist but doesn't

1. **Limit orders** — the bot should specify a price, not use market orders on wide-spread options
2. **Entry cooldown** — after entering a trade, wait N minutes before entering another
3. **Forward PDT planning** — before entering, check: can I exit this position today if I need to? If not, don't enter
4. **Working momentum detection** — the momentum scorer should actually fire on real SPY intraday moves
5. **Call buying on bullish signals** — the bot should buy calls when momentum is up, not just puts
6. **Order deduplication** — never submit the same exit order twice
7. **Single-instance position ownership** — each trade belongs to one strategy instance, not shared across all
8. **Accurate P&L from the start** — option price for unrealized, actual fill price for realized, no guessing
9. **Stable runtime** — runs 6.5 hours without crashing, freezing, or requiring intervention
10. **Tested end-to-end before declaring ready** — every code path traced with real data before saying "it works"

---

None of this is new information. You told me to build all of this. The architecture document describes all of this. I said it was built and ready. It wasn't. I tested the happy path, declared success, and left you to discover every failure in production.
