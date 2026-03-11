# 09. Dataflow Traces

## Trace 1: Profile Creation → Model Training → Trade Execution

### 1.1 Profile Creation Flow
```
UI: ProfileForm.tsx onClick("Create Profile")
  → POST /api/profiles (body: ProfileCreate{name, preset, symbols, config_overrides})
  → backend/routes/profiles.py:208 create_profile()
    → Validates preset ∈ PRESET_DEFAULTS (config.py:55)
    → Validates symbols list non-empty
    → config = PRESET_DEFAULTS[preset].copy() + body.config_overrides
    → profile_id = uuid4()
    → INSERT INTO profiles (id, name, preset, status='created', symbols, config, model_id=NULL, ...)
    → db.commit()
    → Returns ProfileResponse (id, name, preset, status, symbols, config, ...)
  → UI: React Query invalidates 'profiles' cache → list refresh
```

### 1.2 Model Training Flow
```
UI: ProfileDetail.tsx → TrainModelButton onClick
  → POST /api/models/{profile_id}/train (body: TrainRequest{force_full_retrain, model_type, years_of_data})
  → backend/routes/models.py:717 train_model_endpoint()
    → SELECT * FROM profiles WHERE id = ? (verify exists)
    → Extract symbol (first from JSON symbols list), preset, horizon from PRESET_DEFAULTS
    → Validate model_type ∈ PRESET_MODEL_TYPES[preset]
    → _check_theta_or_raise() — HTTP GET to Theta Terminal v3/stock/list/symbols (timeout 5s)
    → Claim job slot: _active_jobs.add(profile_id) with threading.Lock
    → Select training job function from job_targets dict by model_type:
        xgb_classifier → _scalp_train_job
        xgb_swing_classifier → _swing_classifier_train_job
        lgbm_classifier → _swing_classifier_train_job
        xgboost → _full_train_job
        lightgbm → _lgbm_train_job
        tft → _tft_train_job
        ensemble → _ensemble_train_job
    → threading.Thread(target=job_fn, args=(...), daemon=True).start()
    → Returns TrainingStatus(status="training", progress_pct=0)

  [Background thread: e.g. _scalp_train_job()]
    → _install_training_logger(profile_id) — adds TrainingLogHandler to "options-bot" logger
    → _set_profile_status(profile_id, "training") — UPDATE profiles SET status='training'
    → from ml.scalp_trainer import train_scalp_model
    → train_scalp_model(profile_id, symbol, horizon, years)
      → data/theta_provider.py: fetch 1-min bars via Theta Terminal REST API
      → ml/feature_engineering.py: compute technical indicators (RSI, MACD, Bollinger, ATR, OFI, etc.)
      → ml/scalp_features.py: compute scalp-specific features (ORB, VWAP, momentum clusters)
      → Build target: binary UP/DOWN based on 30-min forward return vs ±0.05% neutral band
      → Optuna hyperparameter optimization (30 trials, 300s timeout)
      → Walk-forward CV with TimeSeriesSplit
      → Train final XGBClassifier with best params
      → Isotonic calibration on holdout set
      → Save model to models/ directory
      → INSERT INTO models (id, profile_id, model_type='xgb_classifier', file_path, status='ready', metrics, ...)
      → UPDATE profiles SET model_id=<new_model_id>, status='ready'
      → Return result dict
    → _extract_and_persist_importance(model_id, model_type, model_path)
      → Load model from disk → get feature importance → UPDATE models SET metrics (top 30 features)
    → _remove_training_logger(handler)
    → _active_jobs.discard(profile_id) — release job slot
```

### 1.3 Trade Execution Flow
```
UI: TradingPage.tsx → StartTradingButton onClick
  → POST /api/trading/start (body: TradingStartRequest{profile_ids})
  → backend/routes/trading.py:451 start_trading()
    → For each profile_id:
      → Validate: not already running (check _processes dict + PID alive)
      → SELECT * FROM profiles WHERE id = ? (verify status ∈ {ready, active, paused}, model_id not null)
      → subprocess.Popen([python, main.py, --trade, --profile-id, <id>, --no-backend])
      → Store in _processes dict (proc, pid, started_at, profile_name)
      → _store_process_state(profile_id, {pid, started_at}) — INSERT INTO system_state
      → UPDATE profiles SET status='active'
    → start_watchdog() — background thread polling every 30s

  [Trading subprocess: main.py --trade --profile-id <id> --no-backend]
    → main.py: argparse, setup logging (console + rotating file + DB handler)
    → load_profile_from_db(profile_id) — SELECT from profiles, models tables
    → Import strategy class: SwingStrategy or GeneralStrategy (both inherit BaseOptionsStrategy)
    → Lumibot Strategy.run(broker=Alpaca, sleeptime=config.sleeptime)

  [Each trading iteration: BaseOptionsStrategy.on_trading_iteration()]
    → Step 0: Emergency stop loss check (portfolio drawdown >= 20%)
    → _check_exits() for all open positions:
      → Rule 1: Profit target (e.g. >= 50% for swing)
      → Rule 2: Stop loss (e.g. >= 30% for swing)
      → Rule 3: Max hold days exceeded
      → Rule 4: DTE floor (< 3 DTE for non-scalp)
      → Rule 5: Model override exit (predicted reversal >= 0.5%)
      → Rule 6: Scalp EOD close (sell all 0DTE before 3:50 PM ET)
    → _check_entries() for each symbol:
      → Step 1: Get underlying price (strategy.get_last_price)
      → Step 2: VIX gate (VIXProvider → Alpaca VIXY price → check within [vix_min, vix_max])
      → Step 3: Fetch historical bars (Lumibot get_historical_prices)
      → Step 4: Compute features (feature_engineering.py + scalp_features.py)
      → Step 5: Model prediction (XGBoostPredictor/ScalpPredictor/SwingClassifierPredictor.predict)
      → Step 6: Confidence gate (predicted_confidence >= min_confidence)
      → Step 7: Implied move gate (get_implied_move_pct vs min predicted move) [BYPASSED for classifiers]
      → Step 8: Earnings blackout gate (yfinance earnings dates)
      → Step 9: EV filter (scan_chain_for_best_ev → delta-gamma-theta EV calculation)
      → Step 10: Liquidity gate (OI >= 100, volume >= 50)
      → Step 11: Portfolio delta limit (abs(portfolio_delta) < 5.0)
      → Step 12: Risk manager check (RiskManager.can_open_position)
      → Step 13: Place order via Lumibot strategy.create_order()
      → Log signal to signal_logs table (entered=True/False, step_stopped_at, stop_reason)
      → If entered: INSERT INTO trades (status='open', ...)
```

## Trace 2: Frontend Data Fetch → Display Cycle

### 2.1 Dashboard Load
```
DashboardPage.tsx mount
  → useQuery('system-status', GET /api/system/status, refetchInterval=30s)
    → system.py: check Alpaca (TradingClient.get_account), Theta (HTTP GET), DB queries
    → Returns SystemStatus{alpaca_connected, theta_connected, portfolio_value, pdt, ...}
  → useQuery('trade-stats', GET /api/trades/stats)
    → trades.py: SELECT * FROM trades → compute win_rate, total_pnl, avg_hold_days
  → useQuery('active-trades', GET /api/trades/active)
    → trades.py: SELECT * FROM trades WHERE status='open'
  → useQuery('model-health', GET /api/system/model-health)
    → system.py: JOIN profiles + models + system_state → per-profile health entries
  → Display: StatusCards, TradeTable, ModelHealthPanel
```

### 2.2 Profile Detail Load
```
ProfileDetailPage.tsx mount (route: /profiles/:id)
  → useQuery('profile-{id}', GET /api/profiles/{id})
  → useQuery('model-{id}', GET /api/models/{id})
  → useQuery('training-status-{id}', GET /api/models/{id}/status, refetchInterval=5s when training)
  → useQuery('signals-{id}', GET /api/signals/{id}?limit=50)
  → useQuery('profile-trades', GET /api/trades?profile_id={id})
  → Display: ProfileHeader, ModelCard, TrainingLogs, SignalLogTable, TradesTable
```

## Trace 3: Model Prediction Data Flow

```
on_trading_iteration() → _check_entries()
  → underlying_price = strategy.get_last_price(Asset(symbol))     [Alpaca/Lumibot]
  → bars_df = strategy.get_historical_prices(symbol, length, "minute")  [Lumibot → broker data]

  → features_df = compute_features(bars_df, feature_set_name)
    → feature_engineering.py: add_technical_indicators(df)
      → RSI(14), MACD(12,26,9), Bollinger(20,2), ATR(14), OBV, VWAP
      → Volume ratios, price momentum (5/10/20 bar), gaps
      → Returns df with ~73 feature columns
    → If scalp: scalp_features.py: add_scalp_features(df)
      → ORB (opening range breakout), VWAP distance, momentum clusters
      → Time bucket (market open/mid/close), intraday return
      → Returns df with ~88 feature columns

  → predictor.predict(features_df)
    → XGBoostPredictor/ScalpPredictor/SwingClassifierPredictor
    → Load model: joblib.load(model_path) → XGBClassifier
    → model.predict_proba(X) → [[p_down, p_up], ...]
    → For classifier: direction = "UP" if p_up > 0.5 else "DOWN"
    → confidence = abs(p_up - 0.5) * 2  (maps 0.5-1.0 → 0.0-1.0)
    → If isotonic calibrator exists: calibrate(confidence)
    → Return {"predicted_return": ±avg_move, "confidence": calibrated_conf, "direction": dir}

  → ev_filter.scan_chain_for_best_ev(strategy, symbol, underlying_price, predicted_return, ...)
    → Iterate expirations in [min_dte, max_dte] range
    → For each expiration: iterate strikes near ATM
    → For each (strike, expiration):
      → Get option chain from Lumibot/broker
      → Extract Greeks: delta, gamma, theta, vega, IV
      → If broker Greeks missing → _estimate_delta() via Black-Scholes (scipy.stats.norm)
      → Calculate EV:
          move = underlying_price * |predicted_return| / 100
          expected_gain = |delta| * move + 0.5 * |gamma| * move²
          hold_days_effective = min(max_hold_days, dte)
          theta_accel = 1.0 + 2.0 * max(0, 1 - dte/7)
          theta_cost = |theta| * hold_days_effective * theta_accel
          EV% = (expected_gain - theta_cost) / premium * 100
      → Score candidate: EVCandidate dataclass
    → Return best EVCandidate (highest EV% above min_ev_pct threshold)
    → Also returns implied_move_pct (ATM straddle cost / underlying_price * 100)
```

## Trace 4: Trade Close → Feedback Loop

```
_check_exits() → exit triggered (e.g. profit target hit)
  → strategy.sell_all(position) via Lumibot
  → UPDATE trades SET status='closed', exit_price=?, exit_date=?, pnl_dollars=?, pnl_pct=?, exit_reason=?, hold_days=?
  → was_day_trade = (entry_date == exit_date)
  → If was_day_trade: UPDATE trades SET was_day_trade=1

  → Feedback queue: INSERT INTO training_queue (profile_id, trade_id, actual_return, queued_at, consumed=0)
    [NOTE: Currently non-functional — trade close code writes to training_queue but
     no automated consumer exists. Incremental retrain must be triggered manually
     via POST /api/models/{id}/retrain from the UI.]
```

## Trace 5: Database Read/Write Paths

### Writes (all SQLite via aiosqlite WAL mode):
| Writer | Table | Operation | Source |
|--------|-------|-----------|--------|
| create_profile | profiles | INSERT | Backend API |
| update_profile | profiles | UPDATE | Backend API |
| delete_profile | profiles, models, trades, signal_logs, training_queue, system_state | DELETE | Backend API |
| train_model | models | INSERT | Background thread |
| train_model | profiles | UPDATE (model_id, status) | Background thread |
| on_trading_iteration | trades | INSERT (open) | Trading subprocess |
| _check_exits | trades | UPDATE (close) | Trading subprocess |
| _check_entries | signal_logs | INSERT | Trading subprocess |
| TrainingLogHandler | training_logs | INSERT | Background thread |
| _store_process_state | system_state | INSERT/REPLACE | Backend (trading routes) |
| _store_backtest_result | system_state | INSERT/REPLACE | Background thread |
| health tracking | system_state | INSERT/REPLACE (model_health_*) | Trading subprocess |

### Reads:
| Reader | Table(s) | Source |
|--------|----------|--------|
| list_profiles | profiles + models + trades | Backend API |
| get_system_status | profiles + trades + training_logs + system_state | Backend API |
| get_model_health | profiles + models + system_state | Backend API |
| get_signal_logs | signal_logs | Backend API |
| load_profile_from_db | profiles + models | Trading subprocess startup |

### Concurrent Access Pattern:
- Backend (FastAPI) uses aiosqlite (async)
- Trading subprocesses use sqlite3 (sync, direct connections)
- Background training threads use asyncio.run(aiosqlite.connect()) — new event loop per call
- SQLite WAL mode enables concurrent readers + single writer
- No explicit locking beyond SQLite's internal locks
- **Risk**: Multiple subprocesses writing to same DB can cause "database is locked" under load
