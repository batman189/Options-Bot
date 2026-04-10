# Options Bot V2 - System Documentation

**Last updated:** 2026-04-10

---

## What This Bot Does

This is a rule-based options trading bot that:

1. Scans the market for setup patterns (momentum, mean reversion, catalyst) using technical indicators and sentiment analysis
2. Scores each setup through a 7-factor weighted scorer with regime awareness
3. Three independent profile strategies evaluate whether to enter based on their own confidence thresholds
4. Selects the optimal options contract (strike, expiration, direction) with EV and liquidity filters
5. Sizes positions using confidence-weighted risk management with PDT protection
6. Manages open positions with automated exits (profit targets, stop losses, time decay, EOD close)
7. Learns from results: a learning layer adjusts confidence thresholds every 20 closed trades based on expectancy
8. Logs every decision to the database for daily review

The bot runs locally on Windows with a React web UI for monitoring and control. Every trade decision is traceable through the signal log with the exact factor scores and rejection reason.

---

## V2 Architecture (Current)

V2 replaced the V1 12-step ML pipeline with a modular 10-phase design. There are no ML models in V2 - all decisions are rule-based through the scanner + scorer + profile system.

### Module Pipeline

Each trading iteration runs this sequence:

```
Step 1:  Market Context     - Classify regime (HIGH_VOLATILITY, TRENDING_UP/DOWN, CHOPPY)
Step 2:  Scanner            - Evaluate 4 setup types per symbol, score 0.0-1.0
Step 3:  Scorer             - Weight 7 factors into a confidence score
Step 4:  Profile Decision   - Each profile applies its own threshold + regime rules
Step 5:  Signal Log         - Write evaluation to v2_signal_logs (always, regardless of entry)
Step 6:  Contract Selection - Pick optimal strike/expiration with EV filter
Step 7:  Position Sizing    - Confidence-weighted sizing with PDT gate
Step 8:  Order Submission   - Submit to Alpaca (DB insert on fill confirmation only)
Step 9:  Trade Management   - Monitor open positions, compute unrealized P&L
Step 10: Exit Execution     - Submit exit orders for positions flagged by trade manager
```

### V2 Modules

| Module | File | Purpose |
|--------|------|---------|
| Data Client | `data/unified_client.py` | Unified access to Alpaca, ThetaData, Yahoo Finance |
| Market Context | `market/context.py` | Regime classification from VIX, SPY price action |
| Scanner | `scanner/scanner.py` | Evaluates momentum, mean_reversion, compression, catalyst setups |
| Scorer | `scoring/scorer.py` | 7-factor weighted scoring with regime adjustment |
| Profiles | `profiles/momentum.py`, `mean_reversion.py`, `catalyst.py` | Independent entry/exit strategies |
| Selector | `selection/selector.py` | Contract selection with EV, liquidity, moneyness filters |
| Sizer | `sizing/sizer.py` | Confidence-weighted position sizing |
| Trade Manager | `management/trade_manager.py` | Position monitoring, exit evaluation, P&L tracking |
| Learning Layer | `learning/learner.py` | Threshold adjustment based on trade expectancy |
| V2 Strategy | `strategies/v2_strategy.py` | Orchestrator - Lumibot Strategy subclass |

### Scoring Factors (7)

| Factor | Weight | Source |
|--------|--------|--------|
| Signal Clarity | 25% | Scanner setup score quality |
| Regime Fit | 20% | How well the setup matches current market regime |
| IVR | 15% | Implied volatility rank (options pricing) |
| Institutional Flow | 10% | Options volume/OI ratio for unusual activity |
| Historical Performance | 10% | Profile's recent win rate |
| Sentiment | 10% | FinBERT NLP on recent headlines |
| Time of Day | 10% | Market session (open/midday/close) favorability |

### Profile Strategies

| Profile | What It Trades | Regime Preference | Confidence Threshold |
|---------|---------------|-------------------|---------------------|
| Momentum | Trend-following breakouts | TRENDING_UP, TRENDING_DOWN | 65% |
| Mean Reversion | Oversold/overbought reversals | CHOPPY | 60% |
| Catalyst | Unusual options activity + sentiment | Any except HIGH_VOL | 72% |

---

## PDT Protection (Pattern Day Trading)

The bot enforces PDT rules for accounts under $25,000 equity. This is critical because Alpaca will reject orders that violate PDT, and repeated rejections waste API calls and create phantom trade records.

### How It Works

1. **Every iteration:** The bot queries Alpaca's `account.daytrade_count` to get the authoritative day trade count
2. **PDT locked state:** When `daytrade_count >= 3` AND `equity < $25,000`, the bot sets `_pdt_locked = True`
3. **Entry gate (Step 7):** If PDT-locked AND the contract is 0DTE (expires today), entry is BLOCKED. The bot cannot buy a 0DTE option it can't sell same-day without creating another day trade. Non-0DTE entries are allowed because the exit happens on a different day.
4. **Exit gate (Step 10):** If PDT-locked AND the position was entered today, exit is BLOCKED. The position is held overnight instead. Log message: "HOLD - PDT prevents same-day exit, holding overnight"
5. **Rejection catch:** If Alpaca returns error code 40310100 ("trade denied due to pattern day trading protection"), the bot sets `_pdt_locked = True` immediately and stops retrying. Both entry and exit order submissions catch this error.
6. **Reset:** The PDT lock resets each iteration when `daytrade_count` drops below 3 (Alpaca's rolling 5-day window)

### What This Prevents

- Buying 0DTE options that would be trapped (can't sell same day)
- Hammering Alpaca with hundreds of rejected orders (the April 9 incident: 284 rejections in 4 hours)
- Phantom trades in the database from orders that were submitted but rejected

---

## Trade Persistence

### Entry Flow

1. `_submit_entry_order()` creates the order and sends it to Alpaca via `submit_order()`
2. Trade metadata is stored in memory (`_trade_id_map`) but NOT written to the database yet
3. Only when Alpaca confirms the fill via `on_filled_order()` is the trade INSERT'ed into the database
4. The `entry_price` in the DB is the actual fill price from Alpaca, not the estimated mid price

This prevents phantom trades - if Alpaca rejects the order (PDT, insufficient funds, etc.), no DB record is created.

### Exit Flow

1. Trade manager's `run_cycle()` evaluates each position for exit conditions
2. If an exit is triggered, `pending_exit = True` is set on the position
3. `_submit_exit_order()` finds the matching broker position and submits a sell order
4. On fill, `on_filled_order()` calls `confirm_fill()` which:
   - Calculates real P&L from actual fill price
   - Sets `was_day_trade = 1` if entry and exit are same calendar day
   - Writes `pnl_dollars`, `pnl_pct`, `exit_reason`, `hold_minutes`
   - Clears `unrealized_pnl` columns
   - Updates status to `closed`

### Unrealized P&L

The trade manager writes `unrealized_pnl` and `unrealized_pnl_pct` to the trades table every cycle for open positions. This uses the **option price** (not the stock price) from Lumibot's `get_last_price()` with the full option asset (symbol, strike, expiration, right).

### Stale Trade Cleanup

`_cleanup_stale_trades()` runs at the start of every `run_cycle()`:

1. Finds trades WHERE `status = 'open' AND expiration < today`
2. Queries Alpaca order history (7-day window) for sell fills on those contracts
3. If Alpaca sold it: uses real fill price for P&L
4. If Alpaca has no sell AND no open position: marks as `order_never_filled` with $0 P&L
5. If Alpaca still holds the position: skips (does not close)

### Alpaca Reconciliation

`scripts/reconcile_positions.py` compares DB open trades against Alpaca positions:
- Run standalone: `python scripts/reconcile_positions.py` (dry run) or `--fix` (apply corrections)
- Also runs automatically at startup via `_reload_open_positions()`
- Catches: DB thinks trade is open but Alpaca already sold it, positions that expired, Alpaca positions not in DB

---

## Risk Management

| Control | What It Does | Implementation |
|---------|-------------|----------------|
| PDT enforcement | Blocks 0DTE entries when at day trade limit (accounts < $25K) | Alpaca `daytrade_count` checked every iteration |
| PDT exit hold | Holds positions overnight if selling would trigger PDT | Same-day entry check before exit submission |
| Position sizing | Confidence-weighted: 40% at min threshold, 100% at 0.50+ | `sizing/sizer.py` |
| Drawdown halving | Halve size if account down 10%+ from session start | Sizer step 3 |
| PDT halving | Halve size if < 2 day trades remaining and same-day trade | Sizer step 4 |
| EOD force close | Close all positions expiring today at 3:45 PM ET | `management/eod.py` |
| Portfolio exposure | Total open premium tracked via RiskManager | `risk/risk_manager.py` |

---

## Data Sources

| Source | What | Endpoint |
|--------|------|----------|
| Alpaca | Stock bars, order execution, account, positions | REST API + WebSocket |
| ThetaData | Options chains, Greeks, IV, open interest, expirations | Terminal v3 at localhost:25503 |
| Yahoo Finance | VIX level | `yfinance` library |
| Hugging Face | FinBERT sentiment model | ProsusAI/finbert (cached locally) |

### Nearest Expiration Handling

The scanner uses `get_nearest_expiration(symbol)` to find the closest valid options expiration for each symbol. SPY has daily expirations (Mon-Fri). TSLA only has weekly expirations (Fridays). The scanner does not hardcode today's date - it queries ThetaData's `option/list/expirations` endpoint and caches the result for 1 hour.

---

## Database Tables

| Table | Purpose | Written By |
|-------|---------|-----------|
| `trades` | All trade records (open and closed) | `on_filled_order()`, `confirm_fill()`, `_cleanup_stale_trades()` |
| `v2_signal_logs` | Every scorer evaluation with factor breakdown | `_log_v2_signal()` in v2_strategy.py |
| `context_snapshots` | Regime data written by trading subprocess | `_persist_context_snapshot()` (every 5 min or on change) |
| `scanner_snapshots` | Scanner scores per symbol per iteration | `_persist_scanner_snapshot()` (every iteration) |
| `profiles` | Profile configuration and status | Backend API |
| `learning_state` | Learning layer thresholds per profile | Learning layer |
| `system_state` | Trading process PIDs, watchdog state | Backend startup/shutdown |

---

## Starting the Bot

1. Start ThetaData Terminal (must be fully loaded before bot starts)
2. Double-click the **Options Bot** desktop shortcut (`start_bot.bat`)
3. Browser opens to `http://localhost:8000`
4. Go to Profiles tab - activate desired profiles
5. Go to System tab - Quick Start - select profiles - click Start

**Important:** Do not click inside the terminal window. Windows CMD QuickEdit mode can pause the entire process if you click in the window. If the terminal shows "Press any key to continue", the process has stopped - close and restart.

### What Happens on Startup

1. Backend starts FastAPI on port 8000
2. Database initialized/migrated
3. Stale profiles reset (error/active with no process -> ready)
4. When trading is started via UI, each profile spawns a subprocess
5. Each subprocess runs `V2Strategy.initialize()`:
   - Health check (Alpaca, ThetaData, VIX)
   - Retry up to 30 minutes if ThetaData returns IV=0 (pre-market)
   - Alpaca reconciliation (sync DB with broker positions)
   - Reload open trades from DB into trade manager
   - Log: "V2Strategy: reloaded N open positions from DB"

---

## Monitoring

### UI Pages

| Page | What It Shows |
|------|--------------|
| Dashboard | Portfolio value (from Alpaca), P&L, open positions, market regime, scanner scores |
| Profiles | All profiles with status, P&L, learning state, activate/pause/edit/delete |
| Trades | Full trade history: entry/exit prices, P&L, setup type, confidence, hold time, exit reason |
| Signal Logs | Every scorer evaluation with expandable 7-factor breakdown, filterable by profile/setup/decision |
| System | Trading process status, connection health, PDT counter, error log, learning state cards |

### Daily Summary Script

```
python scripts/daily_summary.py              # today
python scripts/daily_summary.py --date 2026-04-10
```

Also available as a download from the Signal Logs page ("Daily Summary" button).

### Reconciliation Script

```
python scripts/reconcile_positions.py         # dry run
python scripts/reconcile_positions.py --fix   # apply corrections
```

---

## Error Handling

### Profile Error States

When a trading subprocess crashes, the watchdog marks the profile as `error` and stores the crash reason (extracted from subprocess logs). The UI shows the error reason under the profile status badge. Use the **Reset Errors** button on the System page to clear error profiles back to `ready`.

### Auto-Restart

The watchdog thread monitors trading subprocesses. If one crashes, it:
1. Reads the subprocess log to find the error message
2. Stores the error in the profile's `error_reason` column
3. Auto-restarts up to 3 times with a 5-second delay between attempts
4. After 3 failures, marks the profile as `error` and stops retrying

### Common Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| ThetaData IV=0 | Terminal not warmed up | Bot retries every 60s for up to 30 min |
| ThetaData HTTP 478 | Invalid session / multiple terminals | Restart ThetaData Terminal |
| ThetaData NOT_FOUND | No options for symbol on requested date | Bot uses nearest valid expiration |
| Yahoo VIX empty | Yahoo Finance transient failure | Bot retries next iteration |
| PDT trade denied | Day trade limit exceeded | Bot locks all same-day orders until next day |
| Profile stuck in error | Subprocess crashed 3+ times | Click Reset Errors on System page |

---

## File Structure (V2)

```
options-bot/
  main.py                    -- Entry point, FastAPI + Lumibot launcher
  config.py                  -- All configuration constants
  start_bot.bat              -- Desktop shortcut target

  strategies/
    v2_strategy.py           -- V2 orchestrator (Lumibot Strategy subclass)

  data/
    unified_client.py        -- Unified data access (Alpaca + ThetaData + Yahoo)
    theta_snapshot.py         -- ThetaData v3 API client
    alpaca_provider.py       -- Alpaca stock/options data
    data_validation.py       -- Validation errors (DataValidationError, DataNotReadyError)

  market/
    context.py               -- Market regime classification

  scanner/
    scanner.py               -- Setup type evaluation (4 types)
    setups.py                -- Setup scoring functions
    indicators.py            -- Technical indicators
    sentiment.py             -- FinBERT headline sentiment

  scoring/
    scorer.py                -- 7-factor weighted scorer

  profiles/
    momentum.py              -- Momentum profile strategy
    mean_reversion.py        -- Mean reversion profile strategy
    catalyst.py              -- Catalyst profile strategy
    base_profile.py          -- Profile base class

  selection/
    selector.py              -- Contract selection with EV filter
    ev.py                    -- Expected value calculation
    filters.py               -- Liquidity and moneyness filters
    expiration.py            -- DTE handling

  sizing/
    sizer.py                 -- Confidence-weighted position sizing

  management/
    trade_manager.py         -- Position monitoring + exit evaluation + stale cleanup
    eod.py                   -- End-of-day force close logic

  learning/
    learner.py               -- Threshold adjustment (every 20 trades)
    storage.py               -- Learning state persistence

  backend/
    app.py                   -- FastAPI app, startup hooks
    database.py              -- SQLite schema + migrations
    schemas.py               -- Pydantic response models
    routes/
      trading.py             -- Start/stop trading, watchdog, reset errors
      profiles.py            -- Profile CRUD
      trades.py              -- Trade history + stats
      v2signals.py           -- V2 signal logs + CSV export
      context_api.py         -- Market regime (reads from DB)
      scanner_api.py         -- Scanner scores (reads from DB)
      learning.py            -- Learning state + resume
      system.py              -- Health, PDT, errors, status

  scripts/
    daily_summary.py         -- Plain text daily report
    reconcile_positions.py   -- DB vs Alpaca reconciliation
    backfill_today_trades.py -- Import Alpaca orders into DB

  ui/src/pages/
    Dashboard.tsx            -- Portfolio overview
    Profiles.tsx             -- Profile management
    ProfileDetail.tsx        -- Single profile deep dive
    Trades.tsx               -- Trade history
    SignalLogs.tsx            -- Signal decision log
    System.tsx               -- System health + process control
```

---

## Known Limitations

1. **Windows CMD QuickEdit:** Clicking in the terminal window can freeze the Python process. Do not interact with the terminal window while the bot is running.
2. **Single machine:** The bot runs on one Windows machine. No cloud deployment or multi-machine support.
3. **Paper trading only:** Currently configured for Alpaca paper trading. Production trading requires changing the API keys and removing the PAPER flag.
4. **No ML models in V2:** V2 uses rule-based scoring. The V1 ML models (XGBoost, LightGBM) still exist in the `ml/` directory but are not used by V2Strategy.
5. **Reconciliation gap:** When the bot can't find Alpaca sell orders for expired positions, it marks them as `expired_worthless` at -100%. The actual exit may have been at a small value, creating a P&L discrepancy.
