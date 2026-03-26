# Architecture Overview — Options Bot v2

## Design Philosophy

The bot is a platform, not a single strategy. Users create profiles by selecting a strategy type and a symbol. Each strategy type has its own model, its own entry/exit logic, and its own training pipeline. The platform handles everything shared: data feeds, order execution, risk management, UI, and database.

---

## Strategy Types (Pre-built Templates)

Each strategy type is a complete package: model architecture, feature set, entry logic, exit logic, and default config. Users don't need to configure internals — they pick a type, pick a symbol, and train.

| Strategy Type | Description | Hold Time | Model Type | Options Used |
|---|---|---|---|---|
| **Momentum Scalp** | Detects and rides intraday directional moves | 5 min - 2 hours | Momentum classifier | ATM 0DTE calls/puts |
| **Swing** | Multi-day directional trades on sector/stock trends | 2 - 14 days | Direction classifier (daily) | ATM-to-slightly-OTM, 7-45 DTE |
| **Iron Condor** | Sells premium when market is range-bound | 0DTE - 7 days | Regime filter (trade/no-trade) | Multi-leg credit spreads |
| **OTM Gamma** | Buys cheap far-OTM for rare explosive moves | Minutes to hours | Gamma spike detector | Far OTM 0DTE |
| **Custom** | User-defined parameters, no preset logic | User-defined | Optional | User-defined |

Future strategy types can be added without changing the platform — just add a new strategy class and register it.

---

## User Flow: First Time Setup

### 1. User Opens Profiles Tab

Screen shows:
- Header: "Trading Profiles"
- If no profiles exist: empty state message "No profiles yet. Create your first profile to get started."
- If profiles exist: list of user's created profiles with status, P&L, etc.
- Button always visible: **"+ New Profile"**

No pre-populated profiles on fresh install. Strategy types are templates, not profiles — they only become profiles when a user creates one with a specific symbol.

### 2. User Clicks "+ New Profile"

A selection screen appears (modal, cards, or expandable list) showing the available strategy types. Each type shows a brief description so the user understands what it does:

```
┌─────────────────────────────────────────────────┐
│  Select a Strategy Type                         │
│                                                 │
│  [Momentum Scalp]                               │
│   Rides strong intraday moves on 0DTE options.  │
│   Best for: SPY, QQQ, high-volume tickers.      │
│                                                 │
│  [Swing]                                        │
│   Multi-day directional trades, 7-45 DTE.       │
│   Best for: TSLA, AAPL, individual stocks.      │
│                                                 │
│  [Iron Condor]                                  │
│   Sells premium in range-bound markets.         │
│   Best for: SPY, QQQ. Requires $25K+ account.   │
│                                                 │
│  [OTM Gamma]                                    │
│   Buys cheap far-OTM for rare explosive moves.  │
│   Best for: SPY, QQQ. Requires $10K+ account.   │
│                                                 │
│  [Custom]                                       │
│   Build your own with configurable parameters.  │
└─────────────────────────────────────────────────┘
```

### 3. User Selects a Strategy Type

The profile configuration page loads with:
- Strategy type locked (shows which type was selected)
- All default settings for that strategy pre-filled (stop loss, profit target, sizing, etc.)
- **Symbol field: empty, required** — user types in the ticker they want
- **Profile name: auto-generated** from type + symbol (e.g., "SPY Momentum Scalp"), editable
- Button: **"Create Profile"**

User enters symbol, optionally adjusts settings, clicks "Create Profile."

### 3. Data Check

After profile creation, the system checks data availability:

**Check 1: Historical bars (for model training)**
- Source: Alpaca (stocks/ETFs) or ThetaData (options data)
- Requirement varies by strategy type:
  - Momentum Scalp: 6 months of 1-min bars
  - Swing: 2 years of daily bars
  - Iron Condor: 6 months of 1-min bars + options chain snapshots
  - OTM Gamma: 3 months of 1-min bars + options chain
- If data is available: show green check, enable "Train Model" button
- If data needs fetching: show message "Fetching X months of historical data for [SYMBOL]. This may take a few minutes." with progress bar

**Check 2: Live data feed**
- Verify ThetaData connection for real-time options chain
- Verify Alpaca connection for order execution
- If either is down: show warning with instructions

### 4. Model Training

User clicks "Train Model." Training runs with default hyperparameters for the strategy type. Progress is shown in the UI (same training log system we have now).

When complete:
- Model metrics displayed (accuracy, win rate from walk-forward CV, sample count)
- Profile status changes to "Ready"
- "Start Trading" button becomes available

### 5. Configuration (Optional)

Each profile has a Settings panel with the strategy-specific defaults pre-filled. Users can adjust:
- Position sizing (% of account)
- Max contracts
- Stop loss %
- Profit target %
- Trailing stop activation and trail %
- Cooldown between trades
- Max daily trades
- Trading hours window

Defaults are tuned per strategy type so most users won't need to change anything.

### 6. Start Trading

User clicks "Start Trading." The strategy runs with the trained model and configured settings. Signal logs, trade history, and P&L are tracked per profile.

---

## Architecture: How Strategy Types Plug In

```
Platform Layer (shared):
├── Data Feeds (Alpaca bars, ThetaData options chain, VIX)
├── Order Execution (Alpaca API — single-leg and multi-leg)
├── Risk Management (account-level limits, position tracking)
├── Database (profiles, trades, signal_logs, models, training_logs)
├── UI (React — profiles, dashboard, trades, signal logs, system)
└── Backend API (FastAPI — CRUD, trading control, model management)

Strategy Layer (per strategy type):
├── MomentumScalpStrategy(BaseStrategy)
│   ├── Features: momentum, volume, VWAP, acceleration
│   ├── Model: XGBoost momentum classifier
│   ├── Entry: momentum detection → confirmation → enter
│   └── Exit: trailing stop, momentum fade, time stop
│
├── SwingStrategy(BaseStrategy)
│   ├── Features: daily technicals, sentiment, sector momentum
│   ├── Model: LightGBM/XGBoost direction classifier
│   ├── Entry: daily signal with confidence threshold
│   └── Exit: trailing stop, reversal detection, DTE floor
│
├── IronCondorStrategy(BaseStrategy)
│   ├── Features: GEX, VIX regime, realized vs implied vol
│   ├── Model: Regime classifier (sell premium vs sit out)
│   ├── Entry: regime says safe → select strikes → place spread
│   └── Exit: profit target % of credit, stop at 1x credit, time
│
├── OTMGammaStrategy(BaseStrategy)
│   ├── Features: GEX, volume surge, IV spike detection
│   ├── Model: Gamma spike predictor
│   ├── Entry: GEX trending + volume surge → buy far OTM
│   └── Exit: trailing stop on spike, expire if no spike
│
└── CustomStrategy(BaseStrategy)
    ├── Features: user-selected from available feature sets
    ├── Model: user-selected type
    ├── Entry: configurable gates
    └── Exit: configurable rules
```

### BaseStrategy Provides:
- Portfolio value tracking
- Position sizing calculation
- Order submission (single-leg and multi-leg)
- Trade logging to database
- Signal logging to database
- Unrealized P&L tracking
- Account-level risk checks (max daily loss, max positions)
- Cooldown timer between entries
- Graceful shutdown handling

### Each Strategy Type Provides:
- Its own `_check_entries()` logic
- Its own `_check_exits()` logic
- Its own feature computation
- Its own model training pipeline
- Its own default configuration
- Registration in the strategy registry (so the platform knows about it)

---

## Data Flow

```
Market Data (ThetaData + Alpaca)
    │
    ▼
Feature Computation (per strategy type)
    │
    ▼
Model Prediction (trained model for this profile)
    │
    ▼
Entry Logic (strategy-specific gates and confirmation)
    │
    ▼
Risk Check (account-level: position limits, daily loss, sizing)
    │
    ▼
Order Execution (Alpaca API)
    │
    ▼
Trade Tracking (DB: entry logged, P&L updated each iteration)
    │
    ▼
Exit Logic (strategy-specific: trailing stop, time, momentum fade)
    │
    ▼
Exit Order (Alpaca API)
    │
    ▼
Trade Closed (DB: exit logged, P&L finalized, training queue updated)
```

---

## Model Training Pipeline

Each strategy type registers a trainer function:

```
Strategy Type     →  Trainer Function          →  Predictor Class
Momentum Scalp    →  train_momentum_model()    →  MomentumPredictor
Swing             →  train_swing_model()       →  SwingClassifierPredictor
Iron Condor       →  train_regime_model()      →  RegimePredictor
OTM Gamma         →  train_gamma_model()       →  GammaPredictor
Custom            →  train_custom_model()      →  XGBoostPredictor (generic)
```

Training is triggered from the UI via "Train Model" button. The backend:
1. Fetches historical data for the symbol
2. Computes features using the strategy's feature set
3. Constructs labels using the strategy's labeling logic
4. Trains the model with walk-forward cross-validation
5. Calibrates probabilities (isotonic regression)
6. Saves model + metadata to disk and database
7. Updates the profile's model reference

Incremental retraining ("Update Model" button) adds new trees to the existing model using data since last training date. Same pipeline, just appends instead of retraining from scratch.

---

## What Changes From Current Codebase

| Component | Current | New |
|---|---|---|
| Strategy selection | Preset string ("scalp", "swing") | Strategy type class registration |
| Feature computation | One shared feature set with `if preset == "scalp"` branches | Each strategy type has its own feature module |
| Model training | Separate trainer files with duplicated logic | Trainer registry — shared infrastructure, strategy-specific labels/features |
| Entry logic | Single `_check_entries()` with preset branches | Each strategy overrides `_check_entries()` |
| Exit logic | Single `_check_exits()` with preset branches | Each strategy overrides `_check_exits()` |
| Profile creation UI | Hardcoded preset dropdown | Dynamic dropdown from registered strategy types |
| Configuration | `PRESET_DEFAULTS` dict in config.py | Each strategy type defines its own defaults |

### What Stays The Same

- React UI layout (Dashboard, Profiles, Trades, Signal Logs, System)
- FastAPI backend structure
- SQLite database schema (profiles, trades, signal_logs, models, training_logs)
- Alpaca order execution
- ThetaData data feed
- Training log system
- Signal log system
- Model file format (joblib)

---

## Implementation Order

We will plan and document each strategy type individually before writing any code. The order:

1. **Profile 1: Momentum Scalp** (SPY example — the Reddit trader strategy) — DOCUMENTED
2. **Profile 2: Swing** (TSLA example — multi-day directional) — NEXT
3. **Profile 3: Iron Condor** (premium selling with regime filter) — already partially built
4. **Profile 4: OTM Gamma** (rare explosive plays) — already partially built
5. **Platform changes** (strategy registry, UI updates, shared infrastructure)

Each document will specify: entry logic, exit logic, features, model training, configuration defaults, risk management, success/failure criteria.

No code changes until all documents are reviewed and approved.

---

## Open Questions for Discussion

1. **Should profiles share a model?** If two profiles use "Momentum Scalp" on SPY, do they share one model or train separately? Recommendation: one model per symbol per strategy type, shared across profiles that use the same combination.

2. **Account-level vs profile-level risk?** Currently each profile has its own max_daily_loss. Should there be an account-level cap that applies across all profiles? Recommendation: both. Profile-level limits plus an account-level "circuit breaker" that stops everything.

3. **Multi-symbol profiles?** The current system allows a profile to have multiple symbols. Should we keep that or enforce one symbol per profile? Recommendation: one symbol per profile for simplicity. Users create multiple profiles if they want multiple symbols.

4. **The "Custom" strategy type** — how much flexibility? Should it expose all available features and let users pick, or is it just a blank slate with configurable gates? This can be deferred.

5. **Migration path** — do we rebuild from scratch or refactor the existing codebase? Recommendation: refactor. The platform layer (DB, API, UI, order execution) is solid. We replace the strategy layer and model training pipeline.
