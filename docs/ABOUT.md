# Options Bot — System Overview

**Last updated:** 2026-03-28

This document describes what the bot does, how it works, and what each component is responsible for when the system is operating as expected.

---

## What This Bot Does

This is an ML-driven options trading bot that:

1. Uses trained machine learning models to predict short-term price direction for stocks (currently SPY and TSLA)
2. When the model is confident enough in a direction, scans the options chain for the contract with the highest expected value (EV)
3. Places the trade through Alpaca (paper trading) and manages the position with automated exit rules
4. Logs every decision — entries, rejections, exits — for analysis and model improvement
5. Supports multiple trading profiles running simultaneously, each with its own symbol, strategy, model, and configuration

The bot runs locally with a web UI for monitoring and control. It is not a black box — every trade decision is traceable through the signal log with the exact reason it was taken or rejected.

---

## Strategy Profiles

Each profile combines a symbol, a strategy preset, a trained ML model, and configuration parameters. Multiple profiles can run simultaneously on the same Alpaca account.

### Active Strategy Types

| Preset | What It Does | Timeframe | Example |
|--------|-------------|-----------|---------|
| **scalp** | 0DTE ATM options on SPY using 1-minute bar features. Enters when model confidence exceeds threshold, exits same day. | Seconds to hours | SPY PUT $634 entered at 27% confidence, $0.88 premium |
| **swing** | Multi-day directional trades on individual stocks. Uses daily trend features and options Greeks. Holds 1-7 days. | Days | TSLA CALL $345 entered at 45% confidence, held 3 days |
| **otm_scalp** | Far out-of-the-money 0DTE options for explosive gamma moves. Requires GEX trending regime. Cheap contracts ($0.05-$1.50). | Minutes to hours | SPY CALL $650 at $0.15, targeting 300%+ |
| **iron_condor** | Delta-neutral premium selling. Sells 16-delta iron condors when GEX indicates range-bound market. | Hours (0DTE) | SPY IC: sell $625P/$630P, sell $645C/$650C for $1.20 credit |
| **momentum_scalp** | Detects intraday momentum bursts using velocity/acceleration features on 1-min bars. | Minutes | SPY directional entry on 5-min momentum breakout |

### Current Live Profiles

| Profile | Symbol | Preset | Model | Status |
|---------|--------|--------|-------|--------|
| Spy Scalp | SPY | scalp | XGBoost binary classifier | Active |
| TSLA Swing Test | TSLA | swing | LightGBM binary classifier | Active |
| SPY OTM | SPY | otm_scalp | XGBoost binary classifier | Paused |
| SPY Iron Condor | SPY | iron_condor | XGBoost (regime filter) | Paused |

---

## How a Trade Happens (Entry Pipeline)

Every iteration (1 minute for scalp, 5 minutes for swing), the bot runs a 12-step sequential gate pipeline. A signal must pass every gate to become a trade. If any gate fails, the signal is logged with the step and reason, and the bot waits for the next iteration.

```
Step 0:    Capital gate          — Portfolio meets minimum equity requirement
Step 0a:   Emergency stop        — Portfolio hasn't drawn down > 20% from start
Step 0b:   Exposure limit        — Total open positions < 60% of portfolio
Step 1:    Get price             — Current underlying price available
Step 1.1:  Cooldown              — Enough time since last entry (10-30 min)
Step 1.5:  VIX gate              — Volatility index within tradeable range
Step 1.6:  GEX gate              — Gamma exposure regime check (OTM/IC only)
Step 2:    Historical bars       — Fetch 500-4000 bars for feature computation
Step 3-4:  Feature engineering   — Compute 48-78 technical + options features
Step 5:    ML prediction         — Model outputs signed confidence (-1.0 to +1.0)
Step 5.5:  VIX regime adjust     — Scale confidence by volatility regime (swing only)
Step 6:    Confidence threshold  — abs(confidence) >= min_confidence (0.22-0.30)
Step 8:    PDT check             — Day trade limit not exceeded
Step 8.1:  0DTE time cutoff      — No new 0DTE entries after 3:40 PM ET
Step 8.5:  Implied move gate     — Predicted move exceeds market-priced move (regression only)
Step 8.7:  Earnings blackout     — No earnings within hold window
Step 9:    EV chain scan         — Scan options chain, compute EV per contract, pick best
Step 9.5:  Liquidity gate        — Open interest > 100, volume > 50, tight spread
Step 9.7:  Portfolio delta       — Total portfolio delta within limits
Step 10:   Position sizing       — Risk manager approves quantity, confidence-weighted
Step 11:   Submit order          — Send to Alpaca
Step 12:   Log to database       — Record everything for analysis
```

### The EV Calculation (Step 9)

For each candidate contract in the options chain, the bot computes:

```
predicted_move = underlying_price * avg_daily_move% / 100
expected_gain  = |delta| * move + 0.5 * |gamma| * move^2
theta_cost     = |theta| * hold_days * acceleration_factor
EV%            = (expected_gain - theta_cost) / premium * 100
```

Only contracts with EV above the minimum threshold (3% for scalp, 5% for swing) qualify. Among qualified contracts, the one with the highest EV is selected.

---

## How a Trade Exits

Exit rules are checked every iteration, before entry logic runs. First matching rule wins.

| Priority | Rule | What It Does |
|----------|------|-------------|
| 1 | Profit target | Close when option P&L >= target (50-100% depending on preset) |
| 2 | Trailing stop | Once option gains 10-15%, track peak and exit if it drops 5-8% from peak |
| 3 | Underlying reversal | Exit if underlying moves 1-2.5% against trade direction from entry |
| 4 | Underlying trailing stop | Track underlying high-water mark, exit on pullback (swing) |
| 5 | Stop loss | Hard stop at 15-20% loss on the option |
| 6 | Max hold days | Close after 1-7 days (prevents theta bleed) |
| 7 | DTE floor | Close if < 3 days to expiration (avoids gamma risk near expiry) |
| 8 | Model override | Exit if model now predicts reversal with conviction (if enabled) |
| 9 | Scalp EOD | Force close all 0DTE positions at 3:45 PM ET |

Additionally, a stale trade cleanup runs every iteration to close DB records for options that expired or are no longer held at the broker.

---

## The ML Models

### Model Types

All active models are **binary classifiers** (UP vs DOWN). They output a probability of the stock going up, which is converted to signed confidence:

```
confidence = (p_up - 0.5) * 2.0

Examples:
  p_up = 0.75 -> confidence = +0.50  (50% confident UP -> buy CALL)
  p_up = 0.35 -> confidence = -0.30  (30% confident DOWN -> buy PUT)
  p_up = 0.52 -> confidence = +0.04  (near random -> no trade)
```

| Model | Used By | Algorithm | Training Data |
|-------|---------|-----------|---------------|
| SPY scalp classifier | Spy Scalp, SPY OTM, SPY Iron Condor | XGBoost (binary) | 16,877 samples from 1-min bars, isotonic calibration |
| TSLA swing classifier | TSLA Swing Test | LightGBM (binary) | 3,129 samples from 5-min bars, walk-forward CV |

### Feature Engineering

Each prediction uses 48-78 features computed from recent price bars and options data:

**Base technical features (48):** Returns at multiple timeframes (5min to 20d), moving average ratios, realized volatility, RSI, MACD, ADX, Bollinger Bands, ATR, volume ratios, OBV, VWAP deviation, price position relative to 20d range, intraday momentum, time-of-day, VIX level/term structure.

**Options/Greeks features (25, for swing):** ATM implied volatility, IV skew, IV rank, put/call volume ratio, ATM call/put Greeks (delta, theta, gamma, vega), 2nd-order Greeks (vanna, vomma, charm, speed), Greek ratios, bid-ask spreads.

**Strategy-specific features:**
- Swing (+5): Distance from 20d SMA, Bollinger extreme, RSI overbought/oversold duration, mean reversion z-score, prior bounce detection
- Scalp (+15): 1-min/5-min momentum, ORB distance, VWAP slope, volume surge, microstructure imbalance, time bucket, gamma exposure estimate, order flow imbalance
- Momentum (+25): Multi-timeframe velocity/acceleration, volume delta, VWAP structure, consecutive bars, candle body ratio

### Training

Models are trained on historical data from Alpaca (stock bars) and Theta Data (options chains). Training uses walk-forward cross-validation — the model is trained on data up to time T and tested on data from T to T+N, repeatedly moving the window forward. This prevents lookahead bias.

Incremental retraining adds 50 new trees to an existing model using recent data, preserving learned patterns while adapting to new market conditions.

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend | FastAPI + Python 3.13 | API server, trading logic, ML pipeline |
| Frontend | React + TypeScript + Vite + Tailwind | Web UI (localhost:5173 dev / served from backend in prod) |
| Database | SQLite (aiosqlite) | Profiles, models, trades, signal logs, training logs |
| Trading Engine | Lumibot | Strategy execution framework, order management, position tracking |
| Broker | Alpaca | Order execution, portfolio management, market data (paper trading) |
| Options Data | Theta Data Terminal | Historical options chains, Greeks, IV for model training |
| ML | XGBoost, LightGBM, scikit-learn | Binary classifiers with isotonic calibration |

**Monthly data costs:** Alpaca Algo Trader Plus ($99) + Theta Data Standard ($80) = $179/month

---

## UI Pages

| Page | What It Shows |
|------|--------------|
| **Dashboard** | Portfolio value, open positions, total P&L, win rate, system health, model status, PDT count |
| **Profiles** | All profiles with status, create/edit/delete, activate/pause, trigger training |
| **Profile Detail** | Single profile deep dive: model metrics, training logs, feature importance, recent signals, trades |
| **Trades** | Full trade history with P&L, sortable/filterable, CSV export |
| **Signal Logs** | Every entry decision: what the model predicted, which gate stopped it, why |
| **System** | Connection status (Alpaca, Theta, DB), trading processes, circuit breakers, error log |

---

## Risk Management

| Control | What It Does | Default |
|---------|-------------|---------|
| PDT enforcement | Blocks entries if 3+ day trades in 5 business days (when equity < $25K) | Auto |
| Position limits | Max 10 total open positions across all profiles | 10 |
| Portfolio exposure | Total open option value cannot exceed 60% of portfolio | 60% |
| Emergency stop | Halt all trading if portfolio drops 20% from session start | 20% |
| Per-profile sizing | Each profile limited to 5-30% of portfolio per trade | Varies |
| Max contracts | Hard cap on contracts per trade (5-100 depending on preset) | Varies |
| DTE floor | Close positions with < 3 days to expiration | 3 days |
| Earnings blackout | Skip entries if earnings within 2 days before or 1 day after hold window | 2d/1d |
| Liquidity gate | Reject contracts with OI < 100 or volume < 50 | 100/50 |
| Portfolio delta | Block entries if total portfolio delta would exceed 5.0 | 5.0 |

---

## Directory Structure

```
options-bot/
  main.py                    — FastAPI server + Lumibot launcher
  config.py                  — All configuration constants and preset defaults
  requirements.txt           — Python dependencies

  backend/
    app.py                   — FastAPI app factory, lifespan hooks
    database.py              — SQLite schema, init_db(), migrations
    schemas.py               — Pydantic response models
    routes/
      profiles.py            — Profile CRUD + training triggers
      trading.py             — Start/stop trading subprocesses
      trades.py              — Trade history + stats
      signals.py             — Signal log queries + export
      models.py              — Model status, training, health
      system.py              — Health checks, circuit breakers, errors

  strategies/
    base_strategy.py         — Core entry pipeline (12 steps) + exit logic (9 rules)
    swing_strategy.py        — Swing preset subclass
    scalp_strategy.py        — Scalp preset subclass
    general_strategy.py      — General preset subclass
    iron_condor_strategy.py  — Iron condor premium selling
    iron_condor.py           — IC strike selection + order builders
    registry.py              — Strategy type registration

  ml/
    feature_engineering/
      base_features.py       — 48 base technical features
      swing_features.py      — 15 swing-specific features
      scalp_features.py      — 15 scalp-specific features
      general_features.py    — 4 general-specific features
      momentum_features.py   — 25 momentum-specific features
    scalp_trainer.py         — XGBoost binary classifier training
    swing_classifier_trainer.py  — Swing classifier (XGB/LGBM) training
    momentum_trainer.py      — Momentum classifier training
    incremental_trainer.py   — Online learning (add trees to existing model)
    scalp_predictor.py       — Scalp inference (signed confidence)
    swing_classifier_predictor.py — Swing inference (signed confidence)
    momentum_predictor.py    — Momentum inference
    ev_filter.py             — EV calculation + chain scanning
    liquidity_filter.py      — OI/volume/spread checks
    gex_calculator.py        — Gamma exposure regime detection
    regime_adjuster.py       — VIX-based confidence scaling

  data/
    alpaca_provider.py       — Stock bar fetcher (Alpaca)
    options_data_fetcher.py  — Options chain fetcher (Theta Data)
    vix_provider.py          — VIX/VIXY price provider
    earnings_calendar.py     — Earnings date lookup
    greeks_calculator.py     — Black-Scholes Greeks (vectorized)

  risk/
    risk_manager.py          — PDT, sizing, exposure, emergency stop, trade logging

  ui/
    src/pages/
      Dashboard.tsx          — System overview
      Profiles.tsx           — Profile management
      ProfileDetail.tsx      — Single profile deep dive
      Trades.tsx             — Trade history
      SignalLogs.tsx         — Signal decision log
      System.tsx             — System health + process control

  docs/                      — Project documentation
  models/                    — Trained model artifacts (.joblib)
  logs/                      — Runtime logs
  db/                        — SQLite database
```

---

## Typical Trading Day

When everything is working correctly, a typical trading day looks like this:

**Pre-market (before 9:30 AM ET):**
- Backend is running at localhost:8000
- UI accessible at localhost:5173 (or served from backend)
- Theta Data Terminal running at localhost:25503
- Profiles are activated via the UI or API

**Market open (9:30 AM):**
- Each active profile starts its trading loop (every 1 or 5 minutes depending on preset)
- First ~10 minutes: feature warmup (building up enough bars for indicators)
- Models begin generating predictions
- Most signals are rejected at Step 6 (confidence too low) — this is normal
- The bot is selective by design: only 1-5% of signals should result in trades

**During the day:**
- Dashboard shows live portfolio value, open positions, unrealized P&L
- Signal log fills with every iteration's decision (entered or rejected at which step)
- When a high-confidence signal passes all gates, a trade is placed
- Open positions are monitored every iteration for exit conditions
- Trailing stops lock in gains; underlying reversal cuts losers early

**Near close (3:40-4:00 PM ET):**
- 0DTE entry cutoff at 3:40 PM (no new scalp entries)
- 0DTE exit at 3:45 PM (force close all scalp positions)
- Swing positions remain open overnight

**After hours:**
- Signal logs can be exported for analysis
- Models can be retrained with new data
- Configuration can be adjusted based on the day's performance
