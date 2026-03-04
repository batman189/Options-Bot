# PROJECT ARCHITECTURE — Source of Truth

## Document Purpose

This is the SINGLE authoritative reference for the options-bot project architecture. Every code review, every evaluation, and every implementation must be compared against this document. NO deviation is permitted without explicit user approval, and every approved change MUST be recorded in the Revision Log below.

**If code does not match this document, the code is wrong.**
**If this document does not match an approved change, this document must be updated first.**

---

## Revision Log

| Rev | Date | Change | Approved By | Reason |
|-----|------|--------|-------------|--------|
| 1.0 | 2026-02-21 | Initial architecture established | User | New project creation from LUMIBOT_BUILD_SPEC.md |
| 2.0 | 2026-02-22 | Complete architecture rewrite incorporating research findings, multi-profile system, API contract, PDT constraints, TFT model architecture, 5-min bars, FastAPI backend, SQLite persistence | User | Third restart — addresses all prior failure modes |
| 3.0 | 2026-02-27 | Added `backend/routes/trading.py` subprocess manager; updated API contract with `/api/trading/*` endpoints; clarified that activate/pause update DB status only; added Trading schemas to Section 5c; added subprocess trading to Phase 2 deliverables | User | Code review found undocumented production file — approved as intentional |
| 4.0 | 2026-02-27 | Added `data/options_data_fetcher.py`; documented TFT trainer performance fixes (strided loaders, epoch logger, dynamic prediction index); documented `database.py` stale-training cleanup on startup; updated feature count to reflect 68 base features now fully populated; added options fetcher to training pipeline; added Phase 4.5 Signal Decision Log; updated Resolved Decisions table | User | Day of TFT training debugging — all changes from session approved |
| 5.0 | 2026-03-01 | Added Section 9A (Model Training Data Integrity): Theta Terminal requirement with two-layer gate (API pre-check + pipeline hard-fail), cache optimization, frontend error handling. Added Section 9B (Post-Training Feature Validation — Step 9). Added Section 9C (Model Validation Script). Added Section 9D (NaN/Inf Prevention). Added `scripts/validate_model.py` to directory structure. | User | Documenting training data safeguards and validation infrastructure |
| 6.0 | 2026-03-03 | Phase 5 completion: updated directory listing (phase5_checkpoint.py), preset table (min_confidence row), XGBoost Classifier section (full detail), feature tree (exact counts), Phase 5 → COMPLETE, success criteria (status column), Phase 5 decisions (6 entries) | User | Phase 5 fully implemented (P5P1–P5P5) |
| 7.1 | 2026-03-03 | Documentation accuracy audit: Fixed base feature count 68→67 (put_call_oi_ratio removed), general features 5→4, corrected all total counts (swing 72, general 71, scalp 77). Added `db_log_handler.py` and `signals.py` to directory structure. Added `/api/trading/restart` and `/api/trading/startable-profiles` to API contract. Un-commented signal_logs schema (Phase 4.5 is implemented). Marked Phase 4.5 COMPLETE. Removed stale Linux path from Section 18. | User | Pre-code-review doc accuracy pass |
| 7.0 | 2026-03-03 | Phase 6 Hardening: Added `utils/circuit_breaker.py` (circuit breaker pattern + exponential backoff). Added graceful shutdown signal handlers and RotatingFileHandler in `main.py`. Added trading process watchdog with auto-restart in `trading.py`. Added model health monitoring (rolling accuracy tracking in `base_strategy.py`, `/api/system/model-health` endpoint, Dashboard + ProfileDetail UI banners). Added deployment docs (`docs/DEPLOYMENT.md`, `docs/OPERATIONS.md`), `.env.example`, `scripts/startup_check.py`. Updated `config.py` with 17 hardening constants. Updated `backend/app.py` lifespan with watchdog start + stale profile cleanup. | User | Phase 6 completion — hardening for production paper trading |
| 8.0 | 2026-03-04 | 12-phase codebase audit: Fixed sleeptime format (Lumibot "5M"/"15M"/"1M"), swing prediction_horizon "5d"→"7d", added `data/vix_provider.py` + `utils/alerter.py` to directory, documented entry steps 1.5 (VIX gate) + 8.5 (implied move gate), added 7 new preset config keys, documented `SignalLogs.tsx` page + `/api/signals/export` endpoint, added `exit_reason` to TradingProcessInfo, added scalp EOD exit rule, documented 3 scripts. | Audit | Full 12-phase code audit — all deviations between doc and code reconciled |

---

## 1. PROJECT VISION

An ML-driven options trading bot built on the Lumibot framework that:

- Uses trained machine learning models to identify profitable options trades across multiple strategies (swing, scalping, general)
- Supports multiple **profiles**, each with its own symbol set, trading style, and independently trained model(s)
- Learns from its own trade outcomes through incremental retraining, getting smarter over time
- Uses **only real market data** — no synthetic or fake data anywhere, ever
- Operates through a **local web UI** for profile management, model health monitoring, and trade dashboards
- Uses Alpaca as broker (paper trading first, live when proven) and Theta Data for historical/real-time options data
- Is architected so that future capabilities (0DTE scalping, reinforcement learning, additional data sources) can be added without rebuilding existing systems

**North Star**: The bot should work toward operating at the level of a senior analyst with 20+ years of experience — recognizing market patterns, chart patterns, historical patterns, volatility regimes, and options pricing inefficiencies.

---

## 2. WHAT "DONE" LOOKS LIKE

The bot is "done" when ALL of the following are true:

### Core Functionality
- [ ] User can create a profile via the UI, selecting symbol(s), trading style preset, and configuration
- [ ] Creating a profile triggers model training on real historical data (6+ years where available)
- [ ] Each profile has its own independently trained model(s) appropriate to its trading style
- [ ] The bot executes trades autonomously based on model predictions and EV calculations
- [ ] The bot manages open positions (exits on profit targets, stop losses, time limits, DTE limits)
- [ ] The bot logs every decision with full reasoning (predicted return, EV score, Greeks values, exit reason)

### Data Integrity
- [ ] All training data comes from real market sources (Alpaca + Theta Data)
- [ ] All live data comes from real market sources
- [ ] No synthetic data, no simulated data, no placeholder data — anywhere
- [ ] Historical data uses 1-5 minute bars (not daily bars)
- [ ] At least 6 years of historical stock data used for training (Alpaca provides 10 years)
- [ ] At least 6 years of historical options data used where available (Theta Data Standard provides 8 years)

### ML Intelligence
- [ ] Models use every available data point correctly (price, volume, Greeks, IV, open interest, etc.)
- [ ] Models are appropriate for their trading style (different architectures for swing vs scalp)
- [ ] XGBoost handles tabular/snapshot features; TFT handles temporal/sequential patterns
- [ ] Ensemble (stacking) combines both model outputs for final prediction
- [ ] Directional accuracy exceeds 55% on out-of-sample data
- [ ] Models improve measurably after incremental retraining with new data

### Profile System
- [ ] Multiple profiles can run simultaneously
- [ ] Profiles can be created, configured, paused, resumed, and deleted from the UI
- [ ] Each profile's model can be retrained independently
- [ ] Incremental retraining updates the model with only the missing data (not full retrain)
- [ ] Profile presets automatically configure appropriate settings for the selected trading style

### UI Dashboard
- [ ] Profile creation/management interface
- [ ] Model health metrics per profile (age, last trained, data coverage, accuracy metrics)
- [ ] Trade history and P&L per profile
- [ ] Active positions with real-time status
- [ ] Retraining trigger (manual, per profile)
- [ ] System status (data connections, broker connection, any errors)

### Risk Management
- [ ] PDT rule tracked and enforced (3 day trades per 5 business days when equity < $25K)
- [ ] Configurable per-profile position sizing limits
- [ ] Configurable per-profile maximum portfolio exposure
- [ ] Hard DTE exit floor (never hold through expiration)
- [ ] Portfolio-level exposure cap across all profiles

### Reliability
- [ ] Bot runs 24+ hours without crash during market hours
- [ ] Graceful handling of data outages (Theta Terminal down, Alpaca API issues)
- [ ] All errors logged with full context
- [ ] Automatic recovery from transient failures

---

## 3. DATA FOUNDATION (VERIFIED)

### Verified Data Sources (February 22, 2026)

#### Alpaca — Algo Trader Plus ($99/mo)

| Data Type | Granularity | History Depth | Real-time | Notes |
|-----------|-------------|---------------|-----------|-------|
| Stock OHLCV bars | 1-minute to daily | Since 2016 (~10 years) | Yes, all exchanges (SIP) | 10,000 API calls/min |
| Stock trades | Tick level | Since 2016 | Yes, via WebSocket | Unlimited symbols |
| Stock quotes | Tick level | Since 2016 | Yes, via WebSocket | Unlimited symbols |
| Options chains | Current | N/A | Yes (OPRA feed) | Full market coverage |
| Options trades | Tick level | Since Feb 2024 only (~2 years) | Yes | Limited history |
| Options quotes | Tick level | Since Feb 2024 only (~2 years) | Yes | 1000 WebSocket quotes |
| Order execution | N/A | N/A | Yes | Commission-free options |

**Verified**: Market data is identical between paper and live accounts — depends only on subscription plan, not account type.

#### Theta Data — Options Standard ($80/mo)

| Data Type | Granularity | History Depth | Real-time | Notes |
|-----------|-------------|---------------|-----------|-------|
| Options OHLCV | Tick level | ~8 years (since ~2018) | Yes | 2 threads |
| Options quotes (NBBO) | Tick level | ~8 years | Yes | 10K quote streams |
| Options trades | Tick level | ~8 years | Yes | 15K trade streams |
| Options open interest | Daily | ~8 years | Yes | Historical + snapshot |
| Implied Volatility | Tick level | ~8 years | Yes | Per-contract |
| 1st Order Greeks | Tick level | ~8 years | Yes | Delta, gamma, theta, vega, rho |
| EOD snapshots | Daily | ~8 years | Yes | Used by `options_data_fetcher.py` for training |

**2nd Order Greeks**: Computed ourselves via Black-Scholes (`data/greeks_calculator.py`). Upgrading to Theta Data Pro ($160/mo) requires no code changes.

#### Data Roles

| Role | Primary Source | Fallback |
|------|---------------|----------|
| Broker + Order Execution | Alpaca | N/A |
| Historical Stock Bars (training) | Alpaca (10yr, 1-min) | N/A |
| Historical Options Data (training) | Theta Data EOD via `options_data_fetcher.py` (8yr) | All-NaN fallback if Theta unavailable |
| Live Stock Prices | Alpaca (real-time SIP) | N/A |
| Live Options Prices | Alpaca (OPRA) + Theta Data | Dual source |
| Live Greeks + IV | Theta Data (1st order) | Lumibot Black-Scholes |
| Computed 2nd Order Greeks | Self-computed (Black-Scholes) | N/A |

**Total Monthly Data Cost: $179/mo** (Alpaca $99 + Theta Data $80)

---

## 4. SYSTEM ARCHITECTURE

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   LOCAL WEB UI (React)                        │
│  Profile Management | Model Dashboard | Trade History | Logs │
│  Runs at localhost:3000                                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API (localhost:8000)
┌──────────────────────────▼──────────────────────────────────┐
│                    BACKEND (FastAPI)                          │
│  Profile CRUD | Model Management | Trade Logging | Config    │
│  Swagger docs at localhost:8000/docs                         │
└───────┬──────────────┬──────────────────┬───────────────────┘
        │              │                  │
┌───────▼──────┐ ┌─────▼──────────┐ ┌────▼────────────────┐
│   SQLite     │ │  ML Pipeline   │ │  Lumibot Engine      │
│   Database   │ │                │ │                      │
│  Profiles    │ │  XGBoost       │ │  Strategy per Profile│
│  Models meta │ │  TFT           │ │  Order Management    │
│  Trade logs  │ │  Ensemble      │ │  Position Tracking   │
│  Signal logs │ │  Feature Eng   │ │  Risk Enforcement    │
│  Config      │ │  EV Filter     │ │  PDT Tracking        │
└──────────────┘ └────────────────┘ └──────────┬───────────┘
                                               │
                    ┌──────────────────────────┤
                    │                          │
          ┌─────────▼──────────┐    ┌──────────▼──────────┐
          │   Alpaca API       │    │  Theta Data Terminal │
          │   (Broker + Stock) │    │  (localhost:25503)   │
          └────────────────────┘    └─────────────────────┘
```

### Key Design Decisions

1. **Everything runs locally** — UI at localhost:3000, API at localhost:8000, Theta Terminal at localhost:25503.
2. **API contract defined in Phase 1** — All endpoints stubbed with Pydantic schemas before trading logic is built.
3. **SQLite for persistence** — Profiles, model metadata, trade logs, signal logs stored locally.
4. **Subprocess isolation for trading** — Each profile's bot runs as a separate OS process spawned by `backend/routes/trading.py`. One profile crashing cannot affect others or the backend.
5. **Options training data cached to parquet** — `options_data_fetcher.py` fetches Theta EOD data in monthly batches and caches to `data/cache/`. Subsequent retrains reuse cache; only missing date ranges are re-fetched.
6. **Model interface abstraction** — `ModelPredictor` interface means upgrading XGBoost → TFT → Ensemble never touches strategy code.
7. **Stale training cleanup** — `database.py` resets profiles stuck in `status='training'` on every startup (caused by process kills mid-training).

### Directory Structure

```
options-bot/
├── main.py                              # Entry point — starts backend + strategies
├── config.py                            # Global configuration constants
├── requirements.txt                     # Dependencies (includes scipy>=1.11.0)
├── .env                                 # API keys (gitignored)
│
├── backend/
│   ├── app.py                           # FastAPI application + lifespan
│   ├── routes/
│   │   ├── profiles.py                  # Profile CRUD endpoints
│   │   ├── models.py                    # Model training/status endpoints
│   │   ├── trades.py                    # Trade history endpoints
│   │   ├── system.py                    # System health endpoints (check_errors)
│   │   ├── trading.py                   # Trading process manager (start/stop/status)
│   │   └── signals.py                   # Signal log endpoint (Phase 4.5)
│   ├── database.py                      # SQLite schema + stale-training cleanup on startup
│   ├── schemas.py                       # Pydantic request/response models
│   └── db_log_handler.py               # Thread-aware logging handler for training jobs
│
├── data/
│   ├── provider.py                      # Abstract DataProvider interface
│   ├── alpaca_provider.py               # Alpaca stock data implementation
│   ├── theta_provider.py                # Theta Data options implementation
│   ├── validator.py                     # Verify data integrity, no gaps
│   ├── greeks_calculator.py             # Black-Scholes 2nd order Greeks
│   ├── options_data_fetcher.py          # Theta EOD fetcher for training (parquet cache)
│   ├── vix_provider.py                  # VIX (VIXY proxy) provider for volatility regime gating
│   └── cache/                           # Parquet cache for options training data (gitignored)
│       └── .gitkeep
│
├── strategies/
│   ├── base_strategy.py                 # Base class with shared logic
│   ├── swing_strategy.py                # Swing trading (7+ DTE)
│   ├── general_strategy.py             # General/opportunistic (21+ DTE)
│   ├── scalp_strategy.py                # 0DTE scalping (same-day exit, $25K gate) (Phase 5)
│
├── ml/
│   ├── predictor.py                     # Abstract ModelPredictor interface
│   ├── xgboost_predictor.py             # XGBoost implementation
│   ├── tft_predictor.py                 # TFT implementation
│   ├── ensemble_predictor.py            # Stacking ensemble (Ridge meta-learner)
│   ├── scalp_predictor.py               # XGBClassifier predictor (signed confidence) (Phase 5)
│   ├── scalp_trainer.py                 # Scalp classifier training pipeline (Phase 5)
│   ├── trainer.py                       # XGBoost training + options data wiring
│   ├── tft_trainer.py                   # TFT training — strided loaders, epoch logger
│   ├── incremental_trainer.py           # Incremental retraining + options data wiring
│   ├── ev_filter.py                     # Expected Value calculation
│   └── feature_engineering/
│       ├── base_features.py             # 67 base features (stock OHLCV + options Greeks/IV)
│       ├── swing_features.py            # +5 swing features (72 total)
│       ├── general_features.py          # +4 general features (71 total)
│       └── scalp_features.py            # +10 scalp features (77 total) (Phase 5)
│
├── risk/
│   └── risk_manager.py                  # PDT tracking + position sizing + portfolio limits
│
├── models/                              # Saved model files (gitignored)
│   └── .gitkeep
│
├── db/                                  # SQLite database file (gitignored)
│   └── .gitkeep
│
├── logs/                                # Log files (gitignored)
│   └── .gitkeep
│
├── ui/                                  # React frontend
│   └── src/
│       ├── api/client.ts                # Typed API client
│       ├── types/api.ts                 # TypeScript interfaces
│       └── pages/
│           ├── Dashboard.tsx
│           ├── Profiles.tsx
│           ├── ProfileDetail.tsx        # Model health, training, backtest, feature importance
│           ├── Trades.tsx
│           ├── SignalLogs.tsx           # Signal decision log viewer + CSV export
│           └── System.tsx               # Connection status + check_errors inline alert
│
├── utils/
│   ├── __init__.py                      # Package marker [P6]
│   ├── circuit_breaker.py               # Circuit breaker + exponential backoff [P6]
│   └── alerter.py                       # Webhook alert system (Discord/Slack/Pushover) [P6]
│
├── docs/
│   ├── DEPLOYMENT.md                    # Deployment guide (systemd, Windows) [P6]
│   └── OPERATIONS.md                    # Operations runbook [P6]
│
├── .env.example                         # Annotated environment template [P6]
│
└── scripts/
    ├── train_model.py                   # Standalone training script
    ├── backtest.py                      # Run backtests
    ├── validate_data.py                 # Test all data connections
    ├── validate_model.py                # CLI model validation (feature integrity, importance)
    ├── startup_check.py                 # Pre-flight verification [P6]
    ├── audit_verify.py                  # Audit findings verification (29 checks)
    ├── diagnose_strategy.py             # Strategy diagnostics (entry/exit logic tracing)
    ├── test_features.py                 # Feature engineering test/validation script
    └── test_providers.py                # Data provider connectivity test script
```

Any file not listed here requires explicit approval before creation.

---

## 5. API CONTRACT & DATABASE SCHEMA

### 5a. Database Schema (SQLite)

```sql
-- Profiles
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    preset TEXT NOT NULL,                   -- 'swing', 'general', 'scalp'
    status TEXT NOT NULL DEFAULT 'created', -- 'created','training','ready','active','paused','error'
    symbols TEXT NOT NULL,                  -- JSON array
    config TEXT NOT NULL,                   -- JSON blob of all settings
    model_id TEXT,                          -- FK to models (NULL until trained)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Models
CREATE TABLE models (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    model_type TEXT NOT NULL,               -- 'xgboost', 'tft', 'ensemble'
    file_path TEXT NOT NULL,                -- .joblib path or directory path (TFT)
    status TEXT NOT NULL,                   -- 'training','ready','failed'
    training_started_at TEXT,
    training_completed_at TEXT,
    data_start_date TEXT,
    data_end_date TEXT,
    metrics TEXT,                           -- JSON: {mae, rmse, r2, dir_acc, feature_importance top-30}
    feature_names TEXT,                     -- JSON array
    hyperparameters TEXT,
    created_at TEXT NOT NULL
);

-- Trades
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,                -- 'CALL' or 'PUT'
    strike REAL NOT NULL,
    expiration TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price REAL, entry_date TEXT,
    entry_underlying_price REAL,
    entry_predicted_return REAL,
    entry_ev_pct REAL,
    entry_features TEXT,                    -- JSON: all feature values
    entry_greeks TEXT,                      -- JSON: {delta, gamma, theta, vega, iv}
    entry_model_type TEXT,                  -- Actual model type (xgboost/tft/ensemble)
    exit_price REAL, exit_date TEXT,
    exit_underlying_price REAL,
    exit_reason TEXT,                       -- 'profit_target','stop_loss','max_hold','dte_exit','model_override'
    exit_features TEXT, exit_greeks TEXT,
    pnl_dollars REAL, pnl_pct REAL,
    actual_return_pct REAL,
    hold_days INTEGER,
    was_day_trade INTEGER DEFAULT 0,
    market_vix REAL, market_regime TEXT,
    status TEXT NOT NULL DEFAULT 'open',    -- 'open','closed','cancelled'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- System state (PDT tracking, process PIDs, backtest results, etc.)
CREATE TABLE system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
-- Key patterns used:
--   'trading_<profile_id>'  → JSON {pid, started_at, profile_name}
--   'start_time'            → ISO datetime of backend startup
--   'last_error'            → most recent error string
--   'model_health_<profile_id>'  → JSON {rolling_accuracy, total_predictions, status, ...}

-- Training logs
CREATE TABLE training_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    profile_id TEXT,                        -- Added via migration; may be NULL in older rows
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,                    -- 'info','warning','error'
    message TEXT NOT NULL
);

-- Signal logs (Phase 4.5)
-- One row per trading iteration. Allows UI to show why the bot did or didn't trade.
CREATE TABLE signal_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    underlying_price REAL,
    predicted_return REAL,
    predictor_type TEXT,                -- 'xgboost','tft','ensemble','xgb_classifier'
    step_stopped_at INTEGER,            -- 1-12 matching entry logic steps; NULL if entered
    stop_reason TEXT,                   -- Human-readable: 'below threshold', 'PDT limit', etc.
    entered INTEGER DEFAULT 0,          -- 1 if trade was placed this iteration
    trade_id TEXT                       -- FK to trades if entered=1
);
CREATE INDEX idx_signal_logs_profile_time ON signal_logs (profile_id, timestamp DESC);
```

**Startup behavior** (`database.py`): On every backend start, `init_db()` resets profiles stuck in `status='training'`. Profiles with an existing `model_id` reset to `'ready'`; profiles without reset to `'created'`. Prevents permanent lock-out after Ctrl+C during training.

### 5b. API Endpoints

#### Profiles
| Method | Path | Description | Phase |
|--------|------|-------------|-------|
| GET | /api/profiles | List all profiles | 1 |
| GET | /api/profiles/{id} | Get single profile with model info | 1 |
| POST | /api/profiles | Create new profile | 1 |
| PUT | /api/profiles/{id} | Update profile config | 1 |
| DELETE | /api/profiles/{id} | Delete profile + models + training_logs | 1 |
| POST | /api/profiles/{id}/activate | Update DB status to 'active' only | 2 |
| POST | /api/profiles/{id}/pause | Update DB status to 'paused' only | 2 |

**Note**: `activate`/`pause` update DB status only — they do NOT start/stop processes. Use `/api/trading/start` and `/api/trading/stop` to control trading subprocesses.

#### Models
| Method | Path | Description | Phase |
|--------|------|-------------|-------|
| GET | /api/models/{profile_id} | Model info for a profile | 1 |
| POST | /api/models/{profile_id}/train | Trigger full training (body includes `model_type`) | 1 |
| POST | /api/models/{profile_id}/retrain | Trigger incremental retrain | 2 |
| GET | /api/models/{profile_id}/status | Training progress/status | 1 |
| GET | /api/models/{profile_id}/metrics | Performance metrics | 1 |
| GET | /api/models/{profile_id}/logs | Training log stream | 2 |
| GET | /api/models/{profile_id}/importance | Top-30 feature importance (from stored metrics) | 4 |

#### Trades
| Method | Path | Description | Phase |
|--------|------|-------------|-------|
| GET | /api/trades | List trades (filterable) | 1 |
| GET | /api/trades/{id} | Single trade with full context | 1 |
| GET | /api/trades/active | All open positions | 1 |
| GET | /api/trades/stats | Aggregated P&L stats | 2 |
| GET | /api/trades/export | CSV export | 2 |

#### System
| Method | Path | Description | Phase |
|--------|------|-------------|-------|
| GET | /api/system/status | All statuses + `check_errors` list | 1 |
| GET | /api/system/health | Simple health check | 1 |
| GET | /api/system/pdt | Current PDT count | 1 |
| GET | /api/system/errors | Persistent error log | 2 |
| GET | /api/system/model-health | Per-profile model health (accuracy, age, status) | 6 |

#### Backtesting
| Method | Path | Description | Phase |
|--------|------|-------------|-------|
| POST | /api/backtest/{profile_id} | Run backtest | 2 |
| GET | /api/backtest/{profile_id}/results | Results — status: `not_run\|running\|completed\|failed\|error` | 2 |

#### Trading Process Management
| Method | Path | Description | Phase |
|--------|------|-------------|-------|
| POST | /api/trading/start | Spawn subprocess(es) for profile IDs | 2 |
| POST | /api/trading/stop | Kill subprocess(es) | 2 |
| POST | /api/trading/restart | Stop then re-start subprocess(es) | 3 |
| GET | /api/trading/status | All tracked processes with PID and state | 2 |
| GET | /api/trading/startable-profiles | List profiles eligible to start (status=ready/paused) | 3 |
| GET | /api/trading/watchdog/stats | Watchdog health and restart counts | 6 |

**Implementation**: Each profile runs as `python main.py --trade --profile-id <id> --no-backend`. PIDs tracked in memory and `system_state` table. stdout/stderr → `DEVNULL` (prevents 64KB pipe buffer deadlock). Windows: `CREATE_NEW_PROCESS_GROUP`.

#### Signal Log (Phase 4.5)
| Method | Path | Description | Phase |
|--------|------|-------------|-------|
| GET | /api/signals/export | CSV export of signal logs (query params: profile_id, since, limit) | 4.5 |
| GET | /api/signals/{profile_id} | Recent signal log entries (default last 50) | 4.5 |

### 5c. Key Pydantic Schemas

```python
class ProfileCreate(BaseModel):
    name: str
    preset: str                      # 'swing', 'general', 'scalp'
    symbols: list[str]
    config_overrides: dict = {}

class ProfileResponse(BaseModel):
    id: str; name: str; preset: str; status: str
    symbols: list[str]; config: dict
    model_summary: ModelSummary | None
    trained_models: list[ModelSummary] = []  # All trained models for this profile
    active_positions: int; total_pnl: float
    created_at: str; updated_at: str

class ModelSummary(BaseModel):
    id: str; model_type: str; status: str
    trained_at: str | None
    data_range: str                  # "2020-01-01 to 2026-02-22"
    metrics: dict                    # {mae, rmse, r2, dir_acc}
    age_days: int

class TrainRequest(BaseModel):
    years_of_data: int = 6
    force_full_retrain: bool = False
    model_type: str | None = None    # 'xgboost' | 'tft' | 'ensemble' — default 'xgboost'

class ModelMetrics(BaseModel):
    model_id: str; profile_id: str; model_type: str
    mae: float | None; rmse: float | None
    r2: float | None; directional_accuracy: float | None
    training_samples: int | None; feature_count: int | None
    cv_folds: int | None
    feature_importance: dict | None  # top-30 {feature_name: importance_score}

class SystemStatus(BaseModel):
    alpaca_connected: bool
    alpaca_subscription: str         # 'basic' or 'algo_trader_plus'
    theta_terminal_connected: bool
    active_profiles: int; total_open_positions: int
    pdt_day_trades_5d: int; pdt_limit: int
    portfolio_value: float; uptime_seconds: int
    last_error: str | None
    check_errors: list[str] = []     # Transient errors from this status poll
    circuit_breaker_states: dict = {}  # profile_id -> {theta_state, alpaca_state, ...}

class BacktestResult(BaseModel):
    profile_id: str
    status: str                      # 'not_run' | 'running' | 'completed' | 'failed' | 'error'
    start_date: str | None; end_date: str | None
    total_trades: int | None; sharpe_ratio: float | None
    max_drawdown_pct: float | None; total_return_pct: float | None
    win_rate: float | None; message: str | None

class TradingProcessInfo(BaseModel):
    profile_id: str; profile_name: str; pid: int | None
    status: str                      # 'running' | 'stopped' | 'crashed'
    started_at: str | None; uptime_seconds: int | None; exit_reason: str | None

class TradingStartRequest(BaseModel):
    profile_ids: list[str]

class TradingStartResponse(BaseModel):
    started: list[TradingProcessInfo]
    errors: list[dict]

class TradingStopRequest(BaseModel):
    profile_ids: list[str] | None    # None = stop all

class TradingStopResponse(BaseModel):
    stopped: list[str]; errors: list[dict]

# Phase 4.5 — Signal Decision Log
class SignalLogEntry(BaseModel):
    id: int; profile_id: str; timestamp: str; symbol: str
    underlying_price: float | None; predicted_return: float | None
    predictor_type: str | None
    step_stopped_at: int | None    # None if trade was entered
    stop_reason: str | None
    entered: bool; trade_id: str | None

# Phase 6 — Model Health Monitoring
class ModelHealthEntry(BaseModel):
    profile_id: str; profile_name: str; model_type: str
    rolling_accuracy: float | None; total_predictions: int; correct_predictions: int
    status: str                      # 'healthy','warning','degraded','insufficient_data','stale','no_data'
    message: str; model_age_days: int | None; updated_at: str | None

class ModelHealthResponse(BaseModel):
    profiles: list[ModelHealthEntry]
    any_degraded: bool; any_stale: bool; summary: str
```

---

## 6. PROFILE SYSTEM

### Preset Configurations

| Setting | Swing | General | Scalp (Phase 5) |
|---------|-------|---------|-----------------|
| min_dte | 7 | 21 | 0 |
| max_dte | 45 | 60 | 0 |
| sleeptime | "5M" | "15M" | "1M" |
| max_hold_days | 7 | 14 | 0 (same day) |
| prediction_horizon | "7d" | "10d" | "30min" |
| profit_target_pct | 50 | 40 | 20 |
| stop_loss_pct | 30 | 25 | 15 |
| min_predicted_move_pct | 1.0 | 1.0 | 0.3 |
| min_ev_pct | 10 | 10 | 5 |
| max_position_pct | 20 | 20 | 10 |
| max_contracts | 5 | 5 | 10 |
| bar_granularity | "5min" | "5min" | "1min" |
| min_confidence | N/A | N/A | 0.60 |
| model_type | "ensemble" | "ensemble" | xgb_classifier |
| requires_min_equity | 0 | 0 | 25000 |
| vix_gate_enabled | true | true | false |
| vix_min | 2.0 | 2.0 | N/A |
| vix_max | 8.0 | 8.0 | N/A |
| implied_move_gate_enabled | true | true | false |
| implied_move_ratio_min | 0.5 | 0.5 | N/A |
| max_spread_pct | 15 | 15 | 10 |
| model_override_min_reversal_pct | 2.0 | 2.0 | N/A |

**Note**: `sleeptime` uses Lumibot's time format: "5M" = 5 minutes, "15M" = 15 minutes, "1M" = 1 minute. VIX gate uses VIXY (ETF proxy) thresholds — VIXY price ≈ VIX/5.

### Profile Lifecycle

```
CREATE → CONFIGURE → TRAIN → [CHECKPOINT] → BACKTEST → ACTIVATE → MONITOR → RETRAIN
                                                             ↓
                                                        PAUSE / DELETE
```

---

## 7. ML MODEL ARCHITECTURE

### XGBoost (Phases 1-3 baseline, still used in ensemble)

| Parameter | Value |
|-----------|-------|
| Algorithm | XGBRegressor |
| Target | Forward return % (regression) |
| Training data | 6+ years of 5-min OHLCV + Theta EOD options |
| Cross-validation | 5-fold walk-forward expanding window |
| Primary metric | MAE |

### TFT (Phase 4)

| Parameter | Value |
|-----------|-------|
| Library | pytorch-forecasting |
| Encoder length | 60 bars (~1 trading day) |
| Training windows | Capped at `MAX_TRAIN_WINDOWS=3000` via `torch.utils.data.Subset` with stride |
| Validation windows | Also capped via strided loader (same `MAX_TRAIN_WINDOWS`) |
| Loss function | MAE (not QuantileLoss) |
| Prediction index | `min(3, pred.shape[2] - 1)` — dynamic, handles both loss shapes |
| Epoch logging | Custom Lightning callback writes loss/val_loss to training_logs after each epoch |

**Why strided loaders**: Raw TFT dataset from 6yr × 280K 5-min bars produces ~280K overlapping windows. Each epoch iterated all of them: 27+ minutes per epoch. Striding to 3K windows brings each epoch to ~3.5 minutes.

### Ensemble (Phase 4)

Meta-learner: Ridge regression (alpha=0.1). Inputs: xgb prediction, tft prediction. Linear combination is correct for 2-input meta-learning — complex meta-learners overfit badly with only 2 features.

```
features dict  ──→  XGBoostPredictor.predict()  ──→  xgb_pred  ─┐
                                                                   ├──→ Ridge ──→ final_pred
sequence df    ──→  TFTPredictor.predict()       ──→  tft_pred  ─┘
```

Degraded mode: if `sequence` is None or too short, `EnsemblePredictor` falls back to XGBoost-only prediction. This means live trading always works even if the sequence window isn't available — TFT/ensemble activates when full sequence data is present.

### XGBoost Classifier (Phase 5 — Scalp Only)

`model_type = "xgb_classifier"` — stored in DB and used for routing in backend and UI.

| Parameter | Value |
|-----------|-------|
| Algorithm | XGBClassifier (3-class: DOWN/NEUTRAL/UP) |
| Target | Direction class from 30-min forward return |
| Neutral band | ±0.05% (returns in this range → NEUTRAL) |
| Training data | 2 years of 1-min OHLCV + Theta EOD options |
| Bar granularity | 1-min (390 bars/day) |
| Subsampling | Every 30th bar (non-overlapping 30-min targets) |
| Cross-validation | 5-fold walk-forward expanding window |
| Primary metric | Directional accuracy (UP/DOWN classes only) |
| Inference output | Signed confidence: +0.72 = 72% UP, -0.65 = 65% DOWN, 0.0 = NEUTRAL |
| Hyperparameters | n_estimators=300, max_depth=5, learning_rate=0.05, objective=multi:softprob |
| Inference | < 1ms (XGBoost native) |

**Why classifier instead of regressor for scalp**: At 30-minute horizons, return magnitude is noisy.
Direction accuracy matters more than magnitude accuracy for 0DTE options where gamma amplifies
any correct directional call. The classifier's predict_proba() provides a natural confidence filter,
replacing min_predicted_move_pct with a probability threshold.

**Signed confidence output**: ScalpPredictor.predict() returns a float where:
- Positive = bullish, negative = bearish
- Magnitude = confidence (0.0 to 1.0)
- Example: +0.72 means 72% confident price goes up in next 30 minutes
- Strategy uses |confidence| >= min_confidence threshold (replaces min_predicted_move_pct)
- For EV calculation: estimated_return = confidence × avg_30min_move × direction_sign

### Model Interface

```python
class ModelPredictor(ABC):
    @abstractmethod
    def predict(self, features: dict, sequence: pd.DataFrame = None) -> float:
        """Return predicted forward return %."""

class XGBoostPredictor(ModelPredictor):    # uses features dict; sequence ignored
class TFTPredictor(ModelPredictor):        # uses sequence (60 bars); features ignored
class EnsemblePredictor(ModelPredictor):   # uses both; degrades gracefully without sequence
```

**Live sequence building** (`base_strategy._check_entries`, Step 5): For TFT/Ensemble predictors, `featured_df` from Step 4 is reused — last 60 rows selected via `predictor.get_feature_names()`. No new data fetch needed. Falls back to snapshot-only if < 60 bars available.

### Model Save Formats

| Type | Format | `file_path` in DB |
|------|--------|-------------------|
| xgboost | `{model_id}.joblib` | path to .joblib file |
| tft | `{model_id}_tft_*/` directory | path to directory (model.pt + metadata.json) |
| ensemble | `{model_id}_ensemble.joblib` | path to .joblib (contains sub-model paths) |

---

## 8. FEATURE ENGINEERING

### Overview

```
BaseFeatures (67 features)
    ├── SwingFeatures  (+5 = 72 total)
    ├── GeneralFeatures (+4 = 71 total)
    └── ScalpFeatures  (+10 = 77 total, Phase 5)
```

### Base Features (67)

| Group | Count | Features |
|-------|-------|---------|
| Price Returns | 8 | 5min, 15min, 1hr, 4hr, 1d, 5d, 10d, 20d |
| Moving Averages | 8 | SMA ratios 10/20/50/100/200; EMA ratios 9/21/50 |
| Volatility | 6 | Realized vol 1hr/4hr/1d/5d/10d/20d annualized |
| Oscillators | 6 | RSI-14, RSI-7, MACD line/signal/histogram, ADX-14 |
| Bands | 5 | BB upper/lower ratio, bandwidth, %B, ATR-14 % |
| Volume | 3 | Volume/SMA-20, OBV slope, VWAP deviation |
| Price Position | 2 | Distance to 20d high, 20d low |
| Time | 3 | Day of week, hour of day, minutes to close |
| Options 1st Order Greeks | 18 | ATM IV, IV skew, IV rank 20d, RV-IV spread, put/call vol ratio, ATM call/put delta/theta/gamma/vega (8), theta/delta ratio, gamma/theta ratio, vega/theta ratio, ATM call/put bid-ask spread % (2) |
| Options 2nd Order Greeks | 8 | ATM call/put: vanna, vomma, charm, speed |

**Options data source during training** (`data/options_data_fetcher.py`): Fetches Theta Terminal V3 EOD data in monthly batches → solves IV via Black-Scholes bisection from midpoint prices → computes all Greeks → caches to `data/cache/{symbol}_options.parquet`. All four trainers call `fetch_options_for_training()` at feature computation start.

**⚠️ Silent failure warning**: If Theta Terminal is not running when training starts, the fetcher fails silently (logs a warning, returns None) and training continues with all options features as NaN — functionally a 47-feature model. **Always verify Theta Terminal is connected before triggering any training job.** To confirm options data was used: check training logs for `"Options data fetch failed"`, or check feature importances — `atm_iv`, `iv_rank_20d`, `put_call_volume_ratio` should show non-zero importance if options data was ingested.

### Style-Specific Features

**Swing** (+5, 72 total): Distance from 20-day SMA, BB position extremes, RSI over/oversold duration, mean-reversion z-score, prior bounce magnitude

**General** (+4, 71 total): 50-day trend slope, longer-term momentum, trend consistency score, volatility regime indicator

**Scalp (Phase 5)** (+10, 77 total): 1-min momentum, 5-min momentum, opening range breakout distance,
VWAP slope, 1-min volume surge, bid-ask spread proxy, microstructure imbalance, time-of-day bucket,
gamma exposure estimate, intraday range position

### Feature Count Integrity

`get_base_feature_names()` must return exactly **67** names. `get_swing_feature_names()` must return exactly **5**. `get_general_feature_names()` must return exactly **4**. `get_scalp_feature_names()` must return exactly **10**. These lists drive column selection in all four trainers — a mismatch silently drops features.

```bash
python -c "
from ml.feature_engineering.base_features import get_base_feature_names
from ml.feature_engineering.swing_features import get_swing_feature_names
from ml.feature_engineering.general_features import get_general_feature_names
from ml.feature_engineering.scalp_features import get_scalp_feature_names
print('Base:', len(get_base_feature_names()))       # must be 67
print('Swing:', len(get_swing_feature_names()))     # must be 5
print('General:', len(get_general_feature_names())) # must be 4
print('Scalp:', len(get_scalp_feature_names()))     # must be 10
"
```

---

## 9. TRAINING PIPELINE

### Options Data Fetcher Flow

```
fetch_options_for_training(symbol, bars_df, min_dte, max_dte)
    ├── Extract trading days from bars_df index
    ├── Load cache: data/cache/{symbol}_options_{min_dte}_{max_dte}.parquet
    ├── Identify uncached days
    ├── Group by month → monthly batches
    ├── Per batch:
    │   ├── Pick monthly expiration (~30 DTE from mid-month)
    │   ├── Fetch Theta EOD bulk data (all strikes, both sides)
    │   ├── Extract ATM strike per day
    │   ├── Solve IV via Black-Scholes bisection (midpoint price)
    │   ├── Compute IV skew (OTM put IV / OTM call IV)
    │   └── Compute all 1st + 2nd order Greeks
    ├── Merge with cache → save updated parquet
    └── Return aligned daily DataFrame
```

### Training Job Routing (`backend/routes/models.py`)

`model_type` validation happens **before** `_active_jobs.add()` — invalid type returns 400 without claiming the job slot. Three job functions: `_full_train_job` (XGBoost), `_tft_train_job` (TFT), `_ensemble_train_job` (Ensemble). Each runs in a daemon thread. Each has a `finally:` block that calls `_active_jobs.discard(profile_id)`.

### 9A. Model Training Data Integrity — Theta Terminal Requirement

Model training requires Theta Terminal to be running. Options data (27 features: IV, Greeks, skew, spreads, 2nd-order Greeks) is mandatory — training will not proceed without it.

**Two-layer gate:**

1. **API pre-check** — Before spawning the training thread, the `/train` and `/retrain` endpoints test Theta Terminal connectivity via `GET /v3/stock/list/symbols` (5s timeout). Returns HTTP 503 with actionable error message if unreachable. This runs before claiming the job slot, so the user gets instant feedback and can retry immediately after starting Theta Terminal.

2. **Pipeline hard-fail** — Inside `_compute_all_features()` (in `trainer.py`, `tft_trainer.py`, and `ensemble_predictor.py`), if `fetch_options_for_training()` returns None or throws, a `RuntimeError` is raised instead of continuing without options data. This catches race conditions where Theta goes down between the API check and the actual fetch.

**Cache optimization** — `fetch_options_for_training()` checks the local parquet cache (`data/cache/{symbol}_options_daily.parquet`) before testing Theta connectivity. If all trading days are cached, data is returned without contacting Theta. The connectivity test only runs when there are uncached days that need fetching.

**Frontend error handling** — Both `trainMutation` and `retrainMutation` in `ProfileDetail.tsx` have `onError` handlers that parse the 503 response detail and display it via `window.alert()`.

### 9B. Post-Training Feature Validation (Step 9)

After model training completes (both XGBoost and TFT pipelines), Step 9 validates the trained model's feature integrity before returning success. This appears in the training logs visible in the UI.

**Checks performed:**

1. **Feature completeness** — Compares the model's feature list against `_get_feature_names(preset)`. Logs any missing or extra features.
2. **Options feature coverage** — Specifically checks all 27 options features (prefixed `atm_`, `iv_`, `rv_iv_`, `put_call_`, `theta_delta_`, `gamma_theta_`, `vega_theta_`). Warns if any are missing.
3. **Zero-importance features (XGBoost only)** — Reports features where XGBoost assigned zero importance, with specific callout for options features at zero importance (indicates the model didn't learn from them).
4. **NaN coverage** — Checks what percentage of training rows had NaN for each feature. Warns on any feature exceeding 50% NaN.
5. **Deprecated features** — Flags `general_sector_rel_strength` if present (removed placeholder that was always NaN).

### 9C. Model Validation Script

`scripts/validate_model.py` — CLI tool for validating saved models.

```bash
python scripts/validate_model.py                          # validate all models in DB
python scripts/validate_model.py models/some.joblib       # validate specific XGBoost/ensemble
python scripts/validate_model.py models/tft_dir/          # validate specific TFT model
python scripts/validate_model.py --preset general <path>  # check against general feature list
```

Automatically detects model type (XGBoost, TFT, ensemble) from file format. For XGBoost models, includes full feature importance analysis. Reports PASS/FAIL per model and overall.

### 9D. NaN/Inf Prevention

**Feature engineering** — All division operations in `base_features.py` (13 operations) and `swing_features.py` (3 operations) use `.replace(0, np.nan)` on denominators to prevent Inf from division-by-zero.

**Predictors** — All three predictors (`xgboost_predictor.py`, `tft_predictor.py`, `ensemble_predictor.py`) validate predictions for NaN/Inf before returning. NaN/Inf predictions return 0.0 with an error log. The ensemble predictor additionally validates each sub-prediction and falls back to XGBoost-only if TFT returns NaN/Inf.

**Strategy** — `base_strategy.py` validates predictions at two points:

1. **Entry path** — Skips entry if prediction is NaN/Inf, or if >80% of features are NaN. Replaces any Inf values in the feature dict with NaN before passing to the predictor.
2. **Exit path** — Skips the model override reversal check if the override prediction is NaN/Inf.

**TFT trainer** — NaN row dropping checks all feature columns (not just the first 5) when filtering rows where every feature is NaN.

### 9E. Phase 6 Hardening Infrastructure

**Circuit breaker** (`utils/circuit_breaker.py`): Reusable pattern for external service calls. Three states: CLOSED (normal), OPEN (fail-fast, no calls), HALF_OPEN (one test call). Used by `base_strategy.py` for Theta calls and `alpaca_provider.py` for Alpaca calls. Thread-safe with `threading.Lock`.

| Parameter | Theta | Alpaca |
|-----------|-------|--------|
| Failure threshold | 3 | 5 |
| Reset timeout | 300s (5 min) | 120s (2 min) |

**Crash-proof trading loop** (`base_strategy.py`): Entire `on_trading_iteration()` body wrapped in try/except. Catches all exceptions, logs full traceback, increments consecutive error counter. Auto-pauses after 10 consecutive errors (requires manual restart). Counter resets on any successful iteration.

**Exponential backoff** (`utils/circuit_breaker.py`): `exponential_backoff(attempt)` returns 2^attempt seconds with ±25% jitter, capped at 60s. Used by `alpaca_provider.py` retry loop.

**Graceful shutdown** (`main.py`): SIGTERM/SIGINT handlers set `_shutting_down` flag. All keep-alive loops check the flag every 1 second. Second signal forces `os._exit(1)`. Shutdown summary logged with reason and uptime.

**Trading process watchdog** (`backend/routes/trading.py`): Background thread polls subprocess health every 30 seconds. Detects crashed processes, updates profile status to 'error', auto-restarts up to 3 times with 5-second delay. Restart counter resets when process is healthy. Stats exposed via `GET /api/trading/watchdog/stats`.

**Log rotation** (`main.py`): `RotatingFileHandler` replaces `FileHandler`. 10 MB max per file, 5 backups kept (50 MB total ceiling).

**Model health monitoring** (`base_strategy.py` + `backend/routes/system.py`):
- Each prediction recorded with direction + price at prediction time
- Outcomes resolved next iteration by comparing current price
- Rolling accuracy computed over last 50 non-neutral predictions
- Persisted to `system_state` table (key: `model_health_{profile_id}`) at most once per minute
- `GET /api/system/model-health` returns per-profile health with status: healthy/warning/degraded/stale/no_data
- Dashboard shows alert banner for degraded (<45% accuracy) or stale (>30 days) models
- ProfileDetail shows Live Accuracy tile and colored status banner

**Startup check** (`scripts/startup_check.py`): Pre-flight script verifying Python version, packages, .env config, DB, disk space, Alpaca connection, Theta connection, UI build. Advisory only — does not block startup.

---

## 10. TRADING LOGIC

### Entry Logic (per profile, per iteration)

| Step | Action | Skip condition |
|------|--------|----------------|
| 1 | Get current price (Alpaca) | Price unavailable → return |
| 1.5 | VIX gate (VIXY proxy via `VIXProvider`) | VIXY below `vix_min` or above `vix_max` → skip (configurable, disabled for scalp) |
| 2 | Get 200 historical 5-min bars | No bars → return |
| 3 | Get options data (Theta) | Theta circuit breaker open → NaN features |
| 4 | Compute features (base + style) | Computation error → return |
| 5 | ML predict: `predict(features, sequence=sequence_df)` | Exception → return |
| 6 | \|predicted_return\| < threshold | Skip (logged) |
| 7 | Direction: CALL if positive, PUT if negative | — |
| 8 | `risk_mgr.check_pdt(equity)` + `check_can_open_position()` | Not allowed → skip |
| 8.5 | Implied move gate: `get_implied_move_pct()` | Predicted return < `implied_move_ratio_min * implied_move` → skip (configurable) |
| 9 | Scan chain: `scan_chain_for_best_ev()` | No valid contract → skip |
| 10 | `risk_mgr.check_can_open_position(...)` — position sizing | Not allowed or qty=0 → skip |
| 11 | Submit order via Lumibot | — |
| 12 | Log to trades table with `entry_model_type` sourced from `type(self.predictor).__name__` | — |

**Signal logging**: Every skip records `step_stopped_at` and `stop_reason` to the `signal_logs` table via `_write_signal_log()`. Steps 1.5 and 8.5 are logged but not stored as fractional — the signal_logs `step_stopped_at` column uses integers 1-12.

### Exit Logic (checked before entries, first match wins)

| Rule | Condition | Action |
|------|-----------|--------|
| Profit Target | Position up ≥ target % | sell_to_close |
| Stop Loss | Position down ≥ loss % | sell_to_close |
| Max Holding | Held ≥ max_hold_days | sell_to_close |
| DTE Floor | DTE < 3 | sell_to_close |
| Model Override | Model predicts reversal ≥ `model_override_min_reversal_pct` | sell_to_close |
| Scalp EOD | Scalp preset + time ≥ 15:45 ET | sell_to_close (forced end-of-day) |

**Backtest path**: Stock trades use reduced thresholds (5% profit / 3% stop) since stock moves are smaller than options. Live path uses the full options thresholds from the preset config.

### RiskManager Method Contract

| Method | Returns | Caller |
|--------|---------|--------|
| `check_pdt(equity)` | `{"allowed": bool, "message": str}` | Entry Step 8 |
| `check_pdt_limit(equity)` | `(bool, str)` tuple | Internal, checkpoint script |
| `check_can_open_position(profile_id, config, portfolio_value, option_price)` | `{"allowed": bool, "quantity": int, "reasons": list}` | Entry Step 10 |

**Both `check_pdt` and `check_pdt_limit` must exist.** `check_pdt` is the dict-returning wrapper; `check_pdt_limit` is the original tuple-returning implementation. Do not remove either.

---

## 11. UI REQUIREMENTS

### Pages

**Dashboard**: Total P&L, active positions, PDT counter (prominent when equity < $25K), system status tiles, profile summary cards

**Profiles**: List with status badges, create/edit/delete/pause/resume. Pause/resume call `/api/trading/stop` and `/api/trading/start`.

**Profile Detail**:
- Model health tiles (model type, accuracy, feature count, data range, age)
- Split train button (XGBoost / TFT / Ensemble)
- Training log stream (live)
- Feature importance panel (collapsible, top 15, horizontal bars)
- Backtest panel (date pickers, run button, Sharpe/max drawdown/win rate/trade count)
- Trade history for this profile
- Signal log panel (Phase 4.5): last N iterations showing step stopped, reason, whether entered

**Trades**: Full history, filterable by profile/date/symbol/outcome, 9 sortable columns, CSV export

**Signal Logs** (`/signals`): Per-profile signal decision log showing every trading iteration. Filterable by entered/skipped and date range. Displays step name mapping (1-12), predicted return, predictor type, stop reason. CSV export via `GET /api/signals/export`. Auto-refresh every 30s.

**System**: Alpaca + Theta connection status, PDT tracking details, trading engine controls (quick start/stop/restart per profile), circuit breaker states, persistent error log, inline `check_errors` alert (AlertTriangle indicator) when any status check fails this poll

---

## 12. RISK MANAGEMENT

### PDT Enforcement

| Equity | Limit | Behavior |
|--------|-------|---------|
| < $25K | 3 day trades per rolling 5 business days | `check_pdt()` returns `allowed: false` |
| ≥ $25K | Unlimited | No restriction |

Scalp profiles blocked from activation when equity < $25K. UI shows equity gate warning.

### Profile Limits (configurable per profile)

max_position_pct: 20% | max_contracts: 5 | max_concurrent_positions: 3 | max_daily_trades: 5 | max_daily_loss_pct: 10%

### Portfolio Limits (global)

max_total_exposure_pct: 60% | max_total_positions: 10 | emergency_stop_loss_pct: 20% (liquidates all, pauses all)

---

## 13. PHASED BUILD PLAN

### Phase 1 ✅ COMPLETE
Single TSLA swing profile, XGBoost, EV filter, paper trading, full API stubbed, SQLite schema.

### Phase 2 ✅ COMPLETE
Multiple simultaneous profiles, incremental retraining, all endpoints functional, trading subprocess manager.

### Phase 3 ✅ COMPLETE
React frontend, all 5 pages, full CRUD from UI, training progress stream, type-safe API client.

### Phase 4 ✅ STRUCTURALLY COMPLETE — Training Gates Pending

**Completed deliverables**:
- `ml/tft_predictor.py` and `ml/tft_trainer.py` with all performance fixes
- `ml/ensemble_predictor.py` (Ridge meta-learner)
- `data/options_data_fetcher.py` — 26 options features now real data (not NaN)
- `data/greeks_calculator.py` — 2nd order Greeks (vanna/vomma/charm/speed)
- Backend routing for xgboost/tft/ensemble training jobs (`models.py`)
- Feature importance endpoint (`/importance`), stored in metrics JSON
- `database.py` stale-training cleanup on startup
- All 10 code review findings resolved (F1–F10)
- UI: model type selector, feature importance panel, backtest panel, config sliders
- Theta Terminal connectivity gate (API pre-check + pipeline hard-fail)
- Post-training feature validation (Step 9)
- `scripts/validate_model.py` CLI validation tool
- NaN/Inf prevention across feature engineering, predictors, and strategy

**Pending gates (require training + market data)**:
- TFT training completing (in progress)
- Ensemble training (after TFT)
- Phase 4 checkpoint re-run
- Directional accuracy > 55% (XGBoost currently 50.7%)
- Backtest Sharpe > 0.8

**On the accuracy number not moving**: XGBoost treats 100%-NaN columns as zero-importance and effectively ignores them, so it already learned a model from the 47 non-NaN features. Retraining with real options data gives it new inputs, but headline accuracy may not shift much if (a) Theta Terminal wasn't running during the retrain (check logs for `"Options data fetch failed"`), or (b) options features don't add signal for 5-day TSLA return prediction at this level. The diagnostic is feature importance — `atm_iv`, `iv_rank_20d`, `put_call_volume_ratio` must show non-zero scores to confirm options data was ingested. Ensemble accuracy is the number that matters most.

---

### Phase 4.5 ✅ COMPLETE

Signal Decision Log — makes the bot fully debuggable from the UI without touching log files.

1. ✅ `signal_logs` table — in `database.py` schema. One row per trading iteration.
2. ✅ `base_strategy.py` writes signal log — after every iteration (entered=1 or step_stopped_at=N).
3. ✅ `GET /api/signals/{profile_id}` — returns last 50 entries. Route file `backend/routes/signals.py`.
4. ✅ Signal log panel in `ProfileDetail.tsx` — timestamp, price, predicted return, step stopped, reason, entered status.

---

### Phase 5 ✅ COMPLETE

0DTE scalp strategy on SPY. XGBoost Classifier with signed confidence output. 1-min bars, 10 scalp features, same-day exit enforcement, $25K equity gate. UI scalp preset with classifier metrics display.

1. ✅ Scalp feature set (10 features, 1-min bars) — P5P1
2. ✅ Scalp classifier (XGBClassifier, signed confidence output) — P5P2
3. ✅ Scalp strategy (ScalpStrategy, 9 base_strategy changes) — P5P3
4. ✅ UI scalp preset (ProfileForm, ProfileDetail, Profiles) — P5P4
5. ✅ Architecture update + checkpoint script — P5P5

---

### Phase 6 ✅ COMPLETE
Hardening: Circuit breaker pattern for Theta/Alpaca calls, crash-proof trading loop with auto-pause, exponential backoff retries, graceful SIGTERM/SIGINT shutdown, trading process watchdog with auto-restart (3 attempts), log rotation (10MB/5 backups), model degradation alerts (rolling accuracy tracking), deployment docs + operations runbook, pre-flight startup check script.

---

## 14. SUCCESS CRITERIA PER PHASE

### Phase 4
| Metric | Target | Status |
|--------|--------|--------|
| Ensemble vs XGBoost | Improves 2+ metrics | Pending |
| Directional accuracy | > 55% | 50.7% (XGBoost) |
| Backtest Sharpe | > 0.8 | Pending |

### Phase 4.5
| Metric | Target | Status |
|--------|--------|--------|
| Signal log written every iteration | Yes | ✓ Built |
| Last 50 iterations visible in UI | Yes | ✓ Built |
| Step + reason visible for every skip | Yes | ✓ Built |

### Phase 5

| Metric | Target | Status |
|--------|--------|--------|
| Scalp backtest trades | > 10 | Pending (requires trained model) |
| Positive expectancy | Win rate × avg win > loss rate × avg loss | Pending |
| Paper stability | 5+ trading days | Pending |
| Classifier directional accuracy | > 52% | Pending (requires training) |

### Phase 6
| Metric | Target | Status |
|--------|--------|--------|
| Error recovery | Auto-recovers from transient failures | ✓ Built — circuit breaker + watchdog + auto-restart |
| Continuous uptime | 1 week without intervention | PENDING — requires live paper trading validation |

---

## 15. WHAT THIS PROJECT IS NOT

- NOT using real money until paper proves profitable
- NOT a high-frequency system (minimum 1-minute intervals)
- NOT cloud-hosted — runs locally
- NOT using synthetic/fake data — ever
- NOT using daily bars — 5-minute minimum
- NOT a single-model system — ensemble (XGBoost + TFT) from Phase 4
- NOT a sentiment/NLP system (future consideration)
- NOT using reinforcement learning at launch (infrastructure supports it)

---

## 16. CAPITAL & REGULATORY CONSTRAINTS

| Constraint | Value | Impact |
|-----------|-------|--------|
| Paper trading balance | $25,000 | Development/testing |
| Planned live starting capital | $5,000 | PDT rule applies |
| PDT rule (equity < $25K) | Max 3 day trades per 5 business days | Swing/general OK, scalping blocked |
| Scalping minimum equity | $25,000 | Regulatory, not software |
| Alpaca subscription | Algo Trader Plus ($99/mo) | Active |
| Theta Data subscription | Options Standard ($80/mo) | Active |
| Total monthly data cost | $179/mo | |

---

## 17. RESOLVED DECISIONS

| Decision | Answer | Date |
|----------|--------|------|
| Hosting | Everything local, no Render | Feb 22, 2026 |
| Theta Terminal | Auto-connect, user starts manually | Feb 22, 2026 |
| Multiple machines | No, single machine only | Feb 22, 2026 |
| SQLite vs Postgres | SQLite (single machine, no server) | Feb 22, 2026 |
| Paper balance | $25K for testing | Feb 22, 2026 |
| Live starting capital | $5K with PDT awareness | Feb 22, 2026 |
| 0DTE scalping | Phase 5, requires $25K+ equity | Feb 22, 2026 |
| Temporal model | TFT via pytorch-forecasting | Feb 22, 2026 |
| 2nd order Greeks | Self-computed via Black-Scholes | Feb 22, 2026 |
| Model target | Regression (return %), NOT classification | Feb 22, 2026 |
| Data granularity | 5-minute bars for training (not daily) | Feb 22, 2026 |
| API contract timing | Defined Phase 1, prevents Phase 3 pain | Feb 22, 2026 |
| Trading process model | Subprocess per profile (trading.py) | Feb 27, 2026 |
| Subprocess output | DEVNULL — prevents pipe buffer deadlock | Feb 27, 2026 |
| TFT training windows | Capped at MAX_TRAIN_WINDOWS=3000 via strided Subset | Feb 27, 2026 |
| TFT loss function | MAE — prediction index dynamic: `min(3, pred.shape[2]-1)` | Feb 27, 2026 |
| Options training data | Theta EOD via options_data_fetcher.py, parquet cache | Feb 27, 2026 |
| Stale training cleanup | database.py resets stuck 'training' profiles on every startup | Feb 27, 2026 |
| Meta-learner | Ridge regression (alpha=0.1) — not neural net, not XGBoost | Feb 27, 2026 |
| Theta Terminal for training | Mandatory — two-layer gate (API pre-check + pipeline hard-fail) | Mar 1, 2026 |
| Training data validation | Post-training Step 9 validates features, NaN coverage, importance | Mar 1, 2026 |
| NaN/Inf handling | Prevented at feature eng (13+3 division guards), predictors, strategy | Mar 1, 2026 |
| Scalp model type | XGBoost Classifier (XGBClassifier) — signed confidence output | Mar 2, 2026 |
| Scalp symbol | SPY (0DTE, daily expirations) | Mar 2, 2026 |
| Scalp predictor interface | predict() returns signed float: +0.65 = 65% confident bullish, -0.72 = 72% confident bearish | Mar 2, 2026 |
| Scalp bar granularity | 1-min bars for training and live; base_features accepts bars_per_day param | Mar 2, 2026 |
| Scalp 3-class target | DOWN/NEUTRAL/UP with ±0.05% neutral band — prevents forcing direction on noise | Mar 2, 2026 |
| Scalp stride-30 subsampling | Non-overlapping 30-min target windows reduce autocorrelation (~2,600 samples/yr) | Mar 2, 2026 |
| Scalp same-day exit | Force close at 3:45 PM ET — 15 min buffer before market close for 0DTE | Mar 3, 2026 |
| Scalp $25K equity gate | PDT rule requires $25K+ for unlimited day trades; checked every iteration | Mar 3, 2026 |
| Scalp stock thresholds | Backtest uses 0.5%/0.3% profit/stop (vs 5.0%/3.0% for swing) | Mar 3, 2026 |
| Why circuit breaker over simple retry | Retry alone can't detect sustained outages. Circuit breaker avoids wasting time on calls that will fail, allows fast degradation, and self-heals after reset timeout. | Mar 3, 2026 |
| Why 50-prediction rolling window for health | Balances responsiveness with noise reduction. 50 samples covers ~2-3 trading days for swing (enough to detect real degradation vs noise). | Mar 3, 2026 |
| Why persist health to system_state vs new table | system_state already exists, is key-value, requires no migration. Health data is small (<1KB per profile), updated at most once per minute. | Mar 3, 2026 |
| Why watchdog auto-restart limit of 3 | Prevents infinite restart loops when a systemic error (missing model, corrupted DB) crashes the process immediately. After 3 failures, requires human investigation. | Mar 3, 2026 |
| Why RotatingFileHandler over TimedRotatingFileHandler | Size-based rotation is more predictable for disk planning. Time-based can create huge files during active trading days. 10MB × 5 = 50MB ceiling is easy to reason about. | Mar 3, 2026 |

---

## 18. VERIFIED LUMIBOT API SIGNATURES

Verified against Lumibot v4.4.50. See LUMIBOT_BUILD_SPEC.md for complete reference.

---

*This document is the source of truth. All evaluations and code reviews must reference it. No changes without user approval + revision log entry.*
