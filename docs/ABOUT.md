# Options Bot V2 - System Documentation

**Last updated:** 2026-04-21
**Version:** 0.4.0 — macro awareness layer (Perplexity-backed events + catalysts, scorer veto cap, regime/catalyst nudge)

---

## What This Bot Does

Rule-based options trading bot that scans for directional setups, scores them through a 7-factor weighted system, and trades via Alpaca with automated position management. No ML models — all decisions are rule-based through the scanner + scorer + profile system.

Key capabilities:
- Scans SPY, QQQ, and TSLA for 5 setup types (momentum, mean reversion, compression, catalyst, macro trend)
- 6 independent profile strategies evaluate each setup with their own rules
- Growth mode sizing (15% risk per trade under $25K) for aggressive account building
- Trailing stops let winners run instead of hard profit targets
- Config-driven: all trading values (profit target, stop loss, DTE, sizing) adjustable from the UI
- Learning layer adjusts confidence thresholds and regime/TOD fit every 20 trades
- Equity curve chart on Dashboard

---

## Presets

Presets define the trading behavior. Symbols are separate — any preset can trade any symbol.

| Preset | Description | Key Settings |
|--------|-------------|-------------|
| **0dte_scalp** | Aggressive same-day OTM options. Growth mode sizing. | 60% profit target, 25% trailing stop, 25% hard stop, 0 DTE, OTM strikes |
| **swing** | Multi-day directional trades on confirmed trends. | 100% profit target, 35% trailing stop, 40% hard stop, 7-14 DTE, ATM strikes |
| **scalp** | Legacy scalp preset (maps to 0dte_scalp internally) | Same as 0dte_scalp |

---

## Profile Strategies

Each setup is evaluated against ALL active profiles. Profiles decide independently whether to enter.

| Profile | Name | Accepts | Regimes | Confidence | Key Rules |
|---------|------|---------|---------|-----------|-----------|
| Scalp 0DTE | `scalp_0dte` | momentum, compression, macro_trend | TRENDING, CHOPPY | 55% | 45min max hold, 0DTE only, OTM strikes |
| Swing (SPY) | `swing` | momentum, compression, macro_trend | TRENDING only | 68% | 3 day max hold, 2-5 DTE, no entries after 3 PM |
| TSLA Swing | `tsla_swing` | momentum, macro_trend | TRENDING only | 72% | 7 day max hold, 7-14 DTE, 50% hard stop, no entries after 1 PM |
| Momentum | `momentum` | momentum only | TRENDING only | 65% | 2hr max hold, direction must match regime |
| Mean Reversion | `mean_reversion` | mean_reversion only | CHOPPY, TRENDING | 60% | 3 day max hold, counter-trend only, no SPY entries after 2 PM |
| Catalyst | `catalyst` | catalyst only | Not HIGH_VOL | 72% | 4hr max hold, exits on stale data |

### Preset-to-Profile Mapping

| Preset | Active Profiles |
|--------|----------------|
| 0dte_scalp | scalp_0dte, momentum, mean_reversion, catalyst |
| swing | swing, momentum (+ tsla_swing for TSLA/NVDA/AAPL/etc) |

---

## Scanner Setup Types (5)

| Setup | What It Detects | Bars | Key Thresholds |
|-------|----------------|------|---------------|
| **Momentum** | Consistent directional move with volume | 8x 1-min | 5/8 directional bars, 0.20% move, vol > 1.0x avg |
| **Mean Reversion** | Extended RSI with reversal signal | 14-bar RSI | RSI > 65 or < 35, Bollinger Band position |
| **Compression Breakout** | Tight range breaking with volume | 15x 1-min | Range < 0.2%, breakout bar with 1.3x vol |
| **Catalyst** | Unusual options volume + sentiment | Sentiment + OI | Sentiment > 0.70, vol/OI ratio > 0.50 |
| **Macro Trend** | Strong 1-hour directional move | 4x 15-min | 0.5%+ move in 1 hour, 3/4 directional bars |

---

## Scoring Factors (7)

| Factor | Weight | Source |
|--------|--------|--------|
| Signal Clarity | 25% | Scanner setup score quality |
| Regime Fit | 20% | Setup-regime compatibility (learning layer adjustable) |
| IVR | 15% | Implied volatility rank |
| Institutional Flow | 15% | Options volume/OI ratio |
| Historical Performance | 15% | Profile's recent win rate (improves with data) |
| Sentiment | 5% | FinBERT (suppression-only: contradicting sentiment hurts, confirming = neutral) |
| Time of Day | 5% | Session favorability (learning layer adjustable) |

---

## Position Sizing

### Growth Mode (accounts under $25K)
- 15% of account per trade (vs 4% in normal mode)
- Confidence scales from 70% to 100% of growth risk (0.55 to 0.80 confidence)
- Capped at 25% of account per single trade
- Auto-disables above $25K
- Configurable per preset via `growth_mode` flag

### Normal Mode (accounts $25K+)
- 4% of account per trade
- High-conviction 0DTE multiplier: 2.5x at confidence >= 0.80, capped at $750

### PDT Gate (accounts under $25K)
- 0 day trades remaining: block all same-day entries
- 1 day trade remaining + confidence < 0.75: block (save last slot)
- 1 day trade remaining + confidence >= 0.75: allow full size
- daytrading_buying_power checked from Alpaca (not just daytrade_count)

### Survival Rules
- Day down 8%: halve all sizes
- Day down 15%: halt all entries
- Down 25% from starting balance: halt trading
- Exposure > 20% of account: block new entries

---

## Exit Logic (7 priorities)

| Priority | Rule | Description |
|----------|------|-------------|
| 1 | Thesis evaluation | Profile-specific: is the setup still active? |
| 2 | Trailing stop | Latching: once peak crosses profit_target, trails from peak. Exits on drawdown >= trailing_stop_pct |
| 3 | Time decay | Exit if held >80% of max time and not 20%+ profitable |
| 4 | Profit lock | 80% scale-out, breakeven stop after 50% peak (skipped when trailing active) |
| 5 | Hard stop | Exit at hard_stop_pct loss |
| 6 | Stale data | Exit if scanner unavailable for N cycles |
| 7 | Max hold time | Exit at max_hold_minutes |

### SPY Mean Reversion EOD
SPY mean_reversion positions force-close at 3:45 PM ET regardless of expiration (overnight gap risk).

---

## Contract Selection

- **0DTE Scalp (scalp_0dte):** OTM strikes for high contract count. Time-aware liquidity gate (5 vol first 30min, 20 next 30min, 50 after 1hr). SPY 0DTE: relaxed OI threshold (50 vs 200).
- **Swing/other:** ATM strikes for 0DTE, confidence-tier for multi-day.
- **All:** Limit orders at mid price, time_in_force="day".
- **Config-driven DTE:** min_dte/max_dte from DB profile config override hardcoded profile logic.

---

## Learning Layer

Two dimensions of adjustment, running every 20 closed trades:

### Confidence Threshold
- Negative expectancy: raise threshold +0.05 (be more selective)
- Strong positive expectancy (>15%): lower threshold -0.02 (take more trades)
- Auto-pause: win rate < 35% over 20 trades
- Bounds: floor 0.50, ceiling 0.85

### Regime Fit Overrides
- Groups trades by regime. If win rate < 40% in a regime with 5+ trades, reduce regime fit score by 0.10 (floored at -0.50).

### Time-of-Day Fit Overrides
- Groups trades by (setup_type, time_of_day). Same logic as regime fit. Learns "momentum at OPEN loses" separately from "momentum in general loses."

### Persistence
- Stored in `learning_state` table (profile_name, min_confidence, regime_fit_overrides, tod_fit_overrides)
- Loaded and applied at startup in `initialize()`
- Scorer applies override deltas to base regime_fit and TOD values

---

## Dynamic Cooldown

- **TRENDING_UP/DOWN:** 5 minute cooldown between entries (re-enter fast on trend days)
- **CHOPPY/other:** 30 minute cooldown (prevent overtrading on choppy days)
- Per-profile: cooldown on one profile doesn't block another
- Recorded on order submission (not on fill) to prevent multiple pending orders

---

## Trade Persistence

- DB INSERT happens in `on_filled_order()` (buy fill), not on order submission
- Prevents phantom trades from rejected orders
- Entry price is actual Alpaca fill price
- Exit: `confirm_fill()` writes pnl_dollars, pnl_pct, exit_reason, was_day_trade, hold_minutes
- Signal log `trade_id` linked back to v2_signal_logs on fill
- Scorer `record_trade_outcome()` called on exit for historical_perf factor

---

## Starting the Bot

1. Start ThetaData Terminal (wait for full load)
2. Double-click **Options Bot** desktop shortcut
3. Browser opens to `http://localhost:8000`
4. Profiles tab: create profiles with desired preset and symbol
5. Click Activate on each profile (starts trading subprocess automatically)

New profiles start in `ready` status. No ML model required.

### Startup Sequence (per subprocess)
1. Health check (Alpaca, ThetaData, VIX) with 30-minute retry for IV=0
2. Alpaca reconciliation (sync DB with broker)
3. Reload open positions from DB
4. Apply learning state (confidence overrides, regime/TOD fit)
5. Apply DB profile config (profit targets, stops, DTE)
6. Filter profiles by preset + symbol
7. Begin trading iterations

---

## Data Sources

| Source | What | Cost |
|--------|------|------|
| Alpaca Algo Trader Plus | Stock bars, order execution, account, positions | $99/month |
| ThetaData Standard | Options chains, Greeks, IV, OI, expirations | $80/month |
| Yahoo Finance | VIX level | Free |
| Hugging Face | FinBERT sentiment model | Free |

---

## File Structure

```
options-bot/
  main.py                    -- Entry point
  config.py                  -- Presets and constants
  start_bot.bat              -- Desktop shortcut

  strategies/v2_strategy.py  -- Orchestrator

  profiles/
    base_profile.py          -- Base class with apply_config, trailing stop, exit logic
    scalp_0dte.py            -- 0DTE scalp (any symbol)
    swing.py                 -- Multi-day swing (SPY/QQQ)
    tsla_swing.py            -- Volatile stock swing (TSLA/NVDA/etc)
    momentum.py              -- Momentum (trend-following)
    mean_reversion.py        -- Mean reversion (counter-trend)
    catalyst.py              -- Catalyst (sentiment + volume)

  scanner/
    scanner.py               -- 5 setup types per symbol
    setups.py                -- Scoring functions
    indicators.py            -- Technical indicators
    sentiment.py             -- FinBERT

  scoring/scorer.py          -- 7-factor weighted scorer with regime/TOD overrides
  selection/selector.py      -- Contract selection (OTM/ATM, DTE, liquidity)
  selection/filters.py       -- Liquidity gate (time-aware, SPY 0DTE relaxed)
  selection/expiration.py    -- DTE logic (config-driven)
  selection/ev.py            -- Expected value calculation
  sizing/sizer.py            -- Growth mode + normal sizing + PDT gate
  management/trade_manager.py -- Position monitoring, exits, stale cleanup
  management/eod.py          -- EOD force close
  learning/learner.py        -- Threshold + regime + TOD adjustment
  learning/storage.py        -- Learning state persistence
  market/context.py          -- Regime classification
  data/unified_client.py     -- Unified data access
  risk/risk_manager.py       -- Portfolio exposure

  backend/
    app.py                   -- FastAPI app
    database.py              -- SQLite schema + migrations
    routes/                  -- All API endpoints

  ui/src/
    pages/                   -- Dashboard, Profiles, Trades, SignalLogs, System
    components/              -- EquityCurve, ProfileForm, StatusBadge, etc

  scripts/
    daily_summary.py         -- Daily report
    reconcile_positions.py   -- DB vs Alpaca sync
```

---

## Known Limitations

1. **Windows CMD QuickEdit:** Clicking in the terminal can freeze the process. Registry key disables it but is not 100% reliable.
2. **Single machine:** No cloud deployment.
3. **Paper trading only:** Configured for Alpaca paper. Production requires key swap.
4. **Reconciliation gap:** Expired positions without Alpaca sell records default to $0 P&L (order_never_filled).
5. **Sentiment latency:** FinBERT processes cached headlines, not real-time news feeds.
6. **No SPX/NDX:** Alpaca doesn't offer index options. Only equity options (SPY, QQQ, TSLA, etc).
