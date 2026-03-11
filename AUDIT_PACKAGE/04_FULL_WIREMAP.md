# 04 FULL WIREMAP

Zero-omission symbol-level call graph for every module in the options-bot codebase.
For each key function/class: callers, callees, data read/written, side effects, state modified.

---

## Table of Contents

1. [Config Module](#1-config-module)
2. [Backend: FastAPI App](#2-backend-fastapi-app)
3. [Backend: Database](#3-backend-database)
4. [Backend: Routes — Profiles](#4-backend-routes--profiles)
5. [Backend: Routes — Models](#5-backend-routes--models)
6. [Backend: Routes — Trading](#6-backend-routes--trading)
7. [Backend: Routes — System](#7-backend-routes--system)
8. [Backend: Routes — Trades](#8-backend-routes--trades)
9. [Backend: Routes — Signals](#9-backend-routes--signals)
10. [Strategies: BaseOptionsStrategy](#10-strategies-baseoptionsstrategy)
11. [ML: Predictor (Abstract)](#11-ml-predictor-abstract)
12. [ML: XGBoostPredictor](#12-ml-xgboostpredictor)
13. [ML: ScalpPredictor](#13-ml-scalppredictor)
14. [ML: SwingClassifierPredictor](#14-ml-swingclassifierpredictor)
15. [ML: LightGBMPredictor](#15-ml-lightgbmpredictor)
16. [ML: EV Filter](#16-ml-ev-filter)
17. [ML: Liquidity Filter](#17-ml-liquidity-filter)
18. [ML: Regime Adjuster](#18-ml-regime-adjuster)
19. [ML: Trainer (XGBoost)](#19-ml-trainer-xgboost)
20. [ML: Scalp Trainer](#20-ml-scalp-trainer)
21. [ML: Swing Classifier Trainer](#21-ml-swing-classifier-trainer)
22. [ML: LightGBM Trainer](#22-ml-lightgbm-trainer)
23. [ML: Feedback Queue](#23-ml-feedback-queue)
24. [ML: Feature Engineering — Base Features](#24-ml-feature-engineering--base-features)
25. [ML: Feature Engineering — Scalp Features](#25-ml-feature-engineering--scalp-features)
26. [ML: Feature Engineering — Swing Features](#26-ml-feature-engineering--swing-features)
27. [ML: Feature Engineering — General Features](#27-ml-feature-engineering--general-features)
28. [Data: Provider (Abstract)](#28-data-provider-abstract)
29. [Data: Alpaca Provider](#29-data-alpaca-provider)
30. [Data: Theta Provider](#30-data-theta-provider)
31. [Data: VIX Provider](#31-data-vix-provider)
32. [Data: Options Data Fetcher](#32-data-options-data-fetcher)
33. [Risk: RiskManager](#33-risk-riskmanager)
34. [Utils: Circuit Breaker](#34-utils-circuit-breaker)
35. [Frontend: API Client](#35-frontend-api-client)
36. [Architectural Flow Traces](#36-architectural-flow-traces)

---

## 1. Config Module

**File:** `options-bot/config.py`

### Constants Defined

| Symbol | Consumers |
|--------|-----------|
| `PROJECT_ROOT`, `DB_PATH`, `MODELS_DIR`, `LOGS_DIR` | Every module (trainer, risk_manager, database, trading.py, system.py, app.py, options_data_fetcher) |
| `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_PAPER`, `ALPACA_BASE_URL`, `ALPACA_DATA_URL` | alpaca_provider, vix_provider, base_strategy, liquidity_filter, system.py, earnings_calendar |
| `THETA_HOST`, `THETA_PORT`, `THETA_BASE_URL_V3`, `THETA_BASE_URL_V2` | theta_provider, options_data_fetcher, models.py (_check_theta_or_raise) |
| `PRESET_DEFAULTS` | profiles.py (create), trainer.py, scalp_trainer.py, swing_classifier_trainer.py, base_strategy.py, models.py |
| `PRESET_MODEL_TYPES` | profiles.py (_build_profile_response), models.py (train_model_endpoint validation) |
| `RISK_FREE_RATE` | base_features.py (greeks_calculator), options_data_fetcher.py (BS IV solver), ev_filter.py (_estimate_delta) |
| `MIN_OPEN_INTEREST`, `MIN_OPTION_VOLUME` | base_strategy.py (Step 9.5 liquidity gate) |
| `EARNINGS_BLACKOUT_DAYS_BEFORE/AFTER` | base_strategy.py (Step 8.7 earnings gate) |
| `MAX_TOTAL_EXPOSURE_PCT`, `MAX_TOTAL_POSITIONS`, `EMERGENCY_STOP_LOSS_PCT`, `DTE_EXIT_FLOOR` | risk_manager.py, base_strategy.py |
| `THETA_CB_*`, `ALPACA_CB_*`, `RETRY_*` | base_strategy.py (circuit breakers), alpaca_provider.py |
| `MAX_CONSECUTIVE_ERRORS`, `ITERATION_ERROR_RESET_ON_SUCCESS` | base_strategy.py (auto-pause) |
| `WATCHDOG_*` | trading.py (watchdog thread) |
| `MODEL_HEALTH_*`, `PREDICTION_RESOLVE_MINUTES_*` | base_strategy.py (prediction health tracking) |
| `VIX_REGIME_*` | regime_adjuster.py, base_strategy.py (Step 5.5) |
| `VIX_PROXY_SHORT_TICKER`, `VIX_PROXY_MID_TICKER` | vix_provider.py (fetch_vix_daily_bars) |
| `PORTFOLIO_MAX_ABS_DELTA`, `PORTFOLIO_MAX_ABS_VEGA` | base_strategy.py (Step 9.7) |
| `OPTUNA_N_TRIALS`, `OPTUNA_TIMEOUT_SECONDS` | trainer.py, scalp_trainer.py, swing_classifier_trainer.py, lgbm_trainer.py |
| `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`, `LOG_LEVEL`, `LOG_FORMAT` | main.py logging setup |
| `VERSION` | app.py, system.py health endpoint |

**Side effects:** `load_dotenv()` called at import time. All env vars read once at module load.

---

## 2. Backend: FastAPI App

**File:** `options-bot/backend/app.py`

### `lifespan(app)` (async context manager)
- **Callers:** FastAPI framework on startup/shutdown
- **Calls:**
  - `init_db()` — schema creation
  - `trading.restore_process_registry(db)` — re-registers surviving PIDs
  - DB query: `SELECT id, name FROM profiles WHERE status = 'active'` — cleans stale profiles
  - `trading.start_watchdog()` — starts watchdog thread
  - `trading.stop_watchdog()` — on shutdown
- **State modified:** DB profiles table (stale active -> ready), in-memory `_processes` registry
- **Side effects:** Logs startup/shutdown

### `app` (FastAPI instance)
- **Routers included:** profiles, models, trades, system, trading, signals, backtest_router
- **CORS:** localhost:3000, localhost:8000
- **Static files:** Mounts `ui/dist/assets/`, serves SPA via catch-all `/{full_path:path}`

### `_backtest_job(...)` (background thread)
- **Callers:** `run_backtest_endpoint` (POST /api/backtest/{id})
- **Calls:** `scripts.backtest.run_backtest()`, `_store_backtest_result()`
- **Reads:** profiles table, models table (for file_path)
- **Writes:** system_state table (backtest_{profile_id})
- **State modified:** `_active_backtests` set

---

## 3. Backend: Database

**File:** `options-bot/backend/database.py`

### `init_db()` (async)
- **Callers:** `app.py` lifespan
- **Calls:** `PRAGMA journal_mode=WAL`, `executescript(SCHEMA_SQL)`, migration ALTERs
- **Writes:** Creates/migrates 7 tables: profiles, models, trades, system_state, training_logs, signal_logs, training_queue
- **Side effects:** Resets stuck training profiles (training -> ready/created)

### `get_db()` (async generator, FastAPI dependency)
- **Callers:** Every route handler via `Depends(get_db)`
- **Returns:** `aiosqlite.Connection` with `row_factory = aiosqlite.Row`
- **Side effects:** Opens/closes connection per request

### DB Schema (7 tables)

| Table | Primary Key | Foreign Keys (logical) | Written By | Read By |
|-------|-------------|----------------------|------------|---------|
| `profiles` | `id TEXT` | `model_id -> models.id` | profiles.py CRUD, models.py (_set_profile_status), trading.py (start/stop/watchdog) | profiles.py, models.py, trading.py, system.py, app.py |
| `models` | `id TEXT` | `profile_id -> profiles.id` | trainer.py, scalp_trainer.py, swing_classifier_trainer.py, lgbm_trainer.py, models.py (_extract_and_persist_importance) | models.py, profiles.py, base_strategy.py (_detect_model_type) |
| `trades` | `id TEXT` | `profile_id -> profiles.id` | risk_manager.py (log_trade_open, log_trade_close) | trades.py routes, system.py (PDT count, positions), profiles.py (_get_trade_stats), risk_manager.py (position counts, exposure) |
| `system_state` | `key TEXT` | — | trading.py (_store_process_state), app.py (_store_backtest_result), base_strategy.py (_persist_health_to_db) | trading.py (restore_process_registry), app.py (get_backtest_results), system.py (model-health) |
| `training_logs` | `id INTEGER` | `model_id`, `profile_id` | db_log_handler.py (TrainingLogHandler) | models.py (get_training_logs) |
| `signal_logs` | `id INTEGER` | `profile_id` | base_strategy.py (_write_signal_log) | signals.py routes |
| `training_queue` | `id INTEGER` | `trade_id`, `profile_id` | feedback_queue.py (enqueue_completed_sample) | incremental_trainer.py, system.py (training-queue status) |

---

## 4. Backend: Routes -- Profiles

**File:** `options-bot/backend/routes/profiles.py`
**Router prefix:** `/api/profiles`

### `list_profiles()` — GET /api/profiles
- **Calls:** DB SELECT profiles, models, trades (via `_get_trade_stats`)
- **Returns:** `list[ProfileResponse]` with model summaries, trade stats, valid_model_types

### `get_profile(profile_id)` — GET /api/profiles/{id}
- **Calls:** DB SELECT profiles, models, trades

### `create_profile(body)` — POST /api/profiles
- **Reads:** `PRESET_DEFAULTS` for config initialization
- **Writes:** INSERT INTO profiles
- **Validation:** preset must be in PRESET_DEFAULTS, at least one symbol required

### `update_profile(profile_id, body)` — PUT /api/profiles/{id}
- **Writes:** UPDATE profiles (name, symbols, config)
- **Behavior:** Merges config_overrides into existing config (not replace)

### `delete_profile(profile_id)` — DELETE /api/profiles/{id}
- **Writes:** DELETE from training_logs, models (and disk files), trades, signal_logs, training_queue, system_state, profiles
- **Side effects:** `shutil.rmtree` / `unlink` on model files

### `activate_profile(profile_id)` — POST /api/profiles/{id}/activate
- **Writes:** UPDATE profiles SET status='active'
- **Validation:** Must be 'ready' or 'paused'

### `pause_profile(profile_id)` — POST /api/profiles/{id}/pause
- **Writes:** UPDATE profiles SET status='paused'
- **Validation:** Must be 'active'

### `_build_profile_response(row, model_row, ...)`
- **Calls:** `_model_row_to_summary()`, `PRESET_MODEL_TYPES` from config
- **Returns:** `ProfileResponse` with trained_models list, valid_model_types

---

## 5. Backend: Routes -- Models

**File:** `options-bot/backend/routes/models.py`
**Router prefix:** `/api/models`

### `train_model_endpoint(profile_id, body)` — POST /api/models/{id}/train
- **Callers:** Frontend api.models.train()
- **Calls:**
  - `_check_theta_or_raise()` — pre-check Theta Terminal connectivity
  - Spawns background thread per model_type:
    - `_full_train_job` -> `ml.trainer.train_model()`
    - `_tft_train_job` -> `ml.tft_trainer.train_tft_model()`
    - `_ensemble_train_job` -> `ml.ensemble_predictor.EnsemblePredictor.train_meta_learner()`
    - `_scalp_train_job` -> `ml.scalp_trainer.train_scalp_model()`
    - `_lgbm_train_job` -> `ml.lgbm_trainer.train_lgbm_model()`
    - `_swing_classifier_train_job` -> `ml.swing_classifier_trainer.train_swing_classifier_model()`
- **State modified:** `_active_jobs` set (prevents duplicate training)
- **Validation:** model_type must be in `PRESET_MODEL_TYPES[preset]`
- **Side effects:** Each training thread calls `_install_training_logger` (adds DB log handler), `_set_profile_status('training')`, and on completion calls `_extract_and_persist_importance`

### `retrain_model(profile_id)` — POST /api/models/{id}/retrain
- **Calls:** `_incremental_retrain_job` -> `ml.incremental_trainer.retrain_incremental()`
- **Requires:** Existing trained model (model_id set)

### `get_training_status(profile_id)` — GET /api/models/{id}/status
- **Reads:** `_active_jobs` (in-memory), profiles table, models table
- **Maps:** DB status 'ready' -> frontend 'completed'

### `get_model_metrics(profile_id)` — GET /api/models/{id}/metrics
- **Reads:** models table (metrics JSON, feature_names JSON)

### `get_feature_importance(profile_id)` — GET /api/models/{id}/importance
- **Reads:** models.metrics JSON -> feature_importance key

### `get_training_logs(profile_id)` — GET /api/models/{id}/logs
- **Reads:** training_logs table

### `_extract_and_persist_importance(model_id, model_type, model_path)`
- **Callers:** Every _*_train_job on success
- **Calls:** Loads predictor class from disk, calls `get_feature_importance()`
- **Writes:** UPDATE models SET metrics (merges feature_importance into existing JSON)

### `_install_training_logger(profile_id)` / `_remove_training_logger(handler)`
- **Calls:** `TrainingLogHandler(DB_PATH, profile_id)` — thread-filtered handler
- **Side effects:** Attaches/detaches handler to `options-bot` logger

---

## 6. Backend: Routes -- Trading

**File:** `options-bot/backend/routes/trading.py`
**Router prefix:** `/api/trading`

### Module-level State
- `_processes: dict[str, dict]` — in-memory registry {profile_id -> {proc, pid, started_at, ...}}
- `_processes_lock` — threading.Lock
- `_watchdog_thread`, `_watchdog_running` — watchdog lifecycle
- `_restart_counts: dict[str, int]` — consecutive restart count per profile

### `start_trading(body)` — POST /api/trading/start
- **Callers:** Frontend api.trading.start()
- **Calls:**
  - DB: SELECT profiles (validate exists, status, model_id)
  - `subprocess.Popen([python, main.py, --trade, --profile-id, id, --no-backend])`
  - `_store_process_state()` — persists PID to system_state
  - DB: UPDATE profiles SET status='active'
- **State modified:** `_processes` registry, `_restart_counts` (cleared)
- **Side effects:** Spawns OS subprocess, CREATE_NEW_PROCESS_GROUP on Windows

### `stop_trading(body)` — POST /api/trading/stop
- **Calls:**
  - `proc.terminate()` / `proc.kill()` or `taskkill /PID /T /F` on Windows
  - `_clear_process_state()` — removes from system_state
  - DB: UPDATE profiles SET status='paused'
- **State modified:** `_processes` registry (removed)

### `restart_trading(body)` — POST /api/trading/restart
- **Calls:** `stop_trading()` then `start_trading()` with 1s delay

### `get_trading_status()` — GET /api/trading/status
- **Reads:** `_processes` registry, profiles table (active profiles not in registry)
- **Side effects:** Cleans stale entries (stopped/crashed)

### `get_startable_profiles()` — GET /api/trading/startable-profiles
- **Reads:** profiles table (status in ready/active/paused AND model_id NOT NULL)

### Watchdog System

#### `start_watchdog()` / `stop_watchdog()`
- **Callers:** `app.py` lifespan (startup/shutdown)
- **State modified:** `_watchdog_running` flag, starts daemon thread

#### `_watchdog_loop()` -> `_watchdog_check_once()`
- **Reads:** `_processes` snapshot
- **For each dead process:**
  - Calls `_clear_process_state()`, `_set_profile_status_sync(profile_id, "error")`
  - If auto-restart enabled and count < WATCHDOG_MAX_RESTARTS: `_watchdog_restart_profile()`
- **Healthy process:** Resets restart counter to 0

#### `_watchdog_restart_profile(profile_id, profile_name)`
- **Calls:** `subprocess.Popen(...)`, `_store_process_state()`, `_set_profile_status_sync("active")`

#### `restore_process_registry(db)` (async)
- **Callers:** `app.py` lifespan
- **Reads:** system_state WHERE key LIKE 'trading_%'
- **For each entry:** Checks `_is_process_alive(pid)`, re-registers live PIDs, cleans dead ones

---

## 7. Backend: Routes -- System

**File:** `options-bot/backend/routes/system.py`
**Router prefix:** `/api/system`

### `health_check()` — GET /api/system/health
- **Returns:** `{status: "ok", timestamp, version}`

### `get_system_status()` — GET /api/system/status
- **Calls:**
  - DB: COUNT profiles WHERE active, COUNT trades WHERE open, COUNT day trades in 7d
  - `_check_alpaca()` — TradingClient.get_account() in thread
  - `_check_theta()` — requests.get(THETA_BASE_URL_V3/stock/list/symbols) in thread
  - `_read_circuit_states()` — reads JSON files from LOGS_DIR
- **Reads:** circuit_state_{profile_id}.json files

### `get_pdt_status()` — GET /api/system/pdt
- **Reads:** trades table (day trades in last 7 days), Alpaca account equity

### `get_errors()` — GET /api/system/errors
- **Reads:** training_logs WHERE level IN ('ERROR', 'WARNING')

### `get_model_health()` — GET /api/system/model-health
- **Reads:** system_state WHERE key LIKE 'model_health_%'

### `get_training_queue()` — GET /api/system/training-queue
- **Reads:** training_queue table (grouped by profile_id, consumed vs pending)

---

## 8. Backend: Routes -- Trades

**File:** `options-bot/backend/routes/trades.py`
**Router prefix:** `/api/trades`

### Endpoints
- `GET /api/trades` — list trades with optional filters (profile_id, status, symbol, limit)
- `GET /api/trades/active` — trades WHERE status='open'
- `GET /api/trades/stats` — aggregate stats (total, wins, losses, P&L sum)
- `GET /api/trades/export` — CSV export

All read from `trades` table only.

---

## 9. Backend: Routes -- Signals

**File:** `options-bot/backend/routes/signals.py`
**Router prefix:** `/api/signals`

### Endpoints
- `GET /api/signals/{profile_id}` — list signal_logs with optional limit/since
- `GET /api/signals/export` — CSV export

All read from `signal_logs` table only.

---

## 10. Strategies: BaseOptionsStrategy

**File:** `options-bot/strategies/base_strategy.py`
**Parent class:** `lumibot.strategies.Strategy`

This is the most critical file. Every trading decision flows through here.

### `initialize()`
- **Callers:** Lumibot framework (once at startup)
- **Calls:**
  - `_detect_model_type()` -> DB query (profiles JOIN models)
  - Loads predictor: XGBoostPredictor, ScalpPredictor, SwingClassifierPredictor, LightGBMPredictor, TFTPredictor, or EnsemblePredictor
  - `RiskManager()` — initializes async event loop thread
  - `VIXProvider()` — initializes VIX cache
  - `CircuitBreaker(name="theta_...")` — Theta circuit breaker
  - In backtest mode: `AlpacaStockProvider().get_historical_bars()` — pre-fetches bars
- **State initialized:**
  - `self.predictor` — ML model
  - `self.risk_mgr` — risk manager with DB access
  - `self._open_trades` — dict of active trade tracking
  - `self._vix_provider` — VIX data
  - `self._cached_bars` — backtest bar cache
  - `self._theta_circuit_breaker` — resilience
  - `self._prediction_history` — health monitoring list
  - `self._consecutive_errors` / `_total_errors` / `_total_iterations`
  - `self._cached_options_daily_df` / `_cached_options_date` — daily options cache

### `on_trading_iteration()`
- **Callers:** Lumibot framework (every sleeptime interval)
- **Flow:**
  1. Auto-pause check (consecutive_errors >= MAX_CONSECUTIVE_ERRORS)
  2. `_update_prediction_outcomes(current_price)` — health tracking
  3. Scalp equity gate ($25K check)
  4. Record `_initial_portfolio_value` on first valid iteration
  5. **Step 0a:** `risk_mgr.check_emergency_stop_loss()` — liquidates all if drawdown >= 20%
  6. **Step 1:** `_check_exits()` — exit logic
  7. **Step 0b:** `risk_mgr.check_portfolio_exposure()` — blocks entries if > 60%
  8. **Step 2:** `_check_entries()` — entry logic (if predictor loaded)
  9. `_persist_health_to_db()` — saves prediction stats to system_state
  10. `_export_circuit_state()` — writes JSON to LOGS_DIR
- **Error handling:** Double try/except, resets `_consecutive_errors` on success
- **Side effects:** Modifies DB (trades, signal_logs, system_state), submits orders, writes log files

### `_check_exits()`
- **Callers:** `on_trading_iteration()` Step 1
- **Calls:**
  - `self.get_positions()` — Lumibot broker positions
  - `self.get_last_price(asset)` — current option/stock price
  - `self.get_last_price(self._stock_asset)` — underlying price
  - For model override exit: `_get_latest_features_for_override()` -> `self.predictor.predict()`
- **Exit rules evaluated (first match wins):**
  1. Profit target: `pnl_pct >= profit_target_pct`
  2. Stop loss: `pnl_pct <= -stop_loss_pct`
  3. Max hold: `hold_days >= max_hold_days`
  4. DTE floor: `dte < DTE_EXIT_FLOOR` (options only)
  5. Model override: predictor now predicts reversal > threshold (configurable)
  6. Scalp EOD: 3:45 PM ET cutoff (scalp preset only)
- **On exit:** Calls `_execute_exit()`

### `_execute_exit(...)`
- **Calls:**
  - `self.create_order()` + `self.submit_order()` — Lumibot order
  - `self.get_greeks(asset)` — exit Greeks
  - `self.risk_mgr.log_trade_close(...)` — DB write
  - `ml.feedback_queue.enqueue_completed_sample(...)` — training queue
- **State modified:** Removes from `self._open_trades`
- **Writes:** trades table (UPDATE status='closed'), training_queue table (INSERT)

### `_check_entries()`
- **Callers:** `on_trading_iteration()` Step 2
- **Full entry pipeline (13 steps):**

| Step | Action | Calls | Gate/Filter |
|------|--------|-------|-------------|
| 1 | Get underlying price | `self.get_last_price(self._stock_asset)` | Fail if None |
| 1.5 | VIX regime gate | `self._vix_provider.get_current_vix()` | Skip if VIXY outside [vix_min, vix_max] |
| 2 | Get historical bars | Backtest: slice `_cached_bars`. Live: `self.get_historical_prices()` | Fail if < 50 bars |
| 3+4 | Compute features | `compute_base_features()` + preset-specific features. Options via `fetch_options_for_training()` (cached daily). VIX via `fetch_vix_daily_bars()` | Fail if empty or >80% NaN |
| 5 | ML prediction | `self.predictor.predict(features, sequence=sequence_df)` | Fail if NaN/Inf |
| 5.5 | VIX regime adjust | `adjust_prediction_confidence()` (SKIP for scalp) | Scales prediction magnitude |
| 6 | Threshold check | Classifier: `abs(pred) >= min_confidence`. Regression: `abs(pred) >= min_predicted_move_pct` | Skip if below |
| 7 | Direction + backtest path | If backtest: trade stock directly, skip to Step 12 | Long-only in backtest |
| 8 | PDT check | `risk_mgr.check_pdt(portfolio_value)` | Block if 3+ day trades and equity < $25K |
| 8.5 | Implied move gate | `get_implied_move_pct()` (SKIP for classifiers) | Skip if predicted < ratio * implied |
| 8.7 | Earnings gate | `has_earnings_in_window()` | Skip if earnings in hold window |
| 9 | EV filter scan | `scan_chain_for_best_ev()` gated by Theta circuit breaker | Skip if no contract meets EV |
| 9.5 | Liquidity gate | `fetch_option_snapshot()` + `check_liquidity()` | Reject if low OI/volume/wide spread |
| 9.7 | Portfolio delta limit | `risk_mgr.get_portfolio_greeks()` | Reject if abs(delta) > 5.0 |
| 10 | Position sizing | `risk_mgr.check_can_open_position()` + confidence-weighted scaling for classifiers | Block if risk checks fail |
| 11 | Submit order | `self.create_order()` + `self.submit_order()` (buy_to_open) | — |
| 12 | Log trade | `risk_mgr.log_trade_open()`, `_write_signal_log(entered=True)` | — |

### `_write_signal_log(...)`
- **Callers:** Every code path in `_check_entries()`, `on_trading_iteration()` early exits
- **Writes:** signal_logs table (sync sqlite3, not aiosqlite)
- **Data:** profile_id, timestamp, symbol, underlying_price, predicted_return, predictor_type, step_stopped_at, stop_reason, entered, trade_id

### `_record_prediction(predicted_return, current_price)`
- **Callers:** `_check_entries()` after Step 5
- **State modified:** `self._prediction_history` list (max MODEL_HEALTH_WINDOW_SIZE entries)

### `_update_prediction_outcomes(current_price)`
- **Callers:** `on_trading_iteration()` (early, before trading logic)
- **Reads:** `self._prediction_history`
- **State modified:** Sets `actual_direction` on resolved predictions

### `_persist_health_to_db()`
- **Callers:** `on_trading_iteration()` (end, in finally-like block)
- **Writes:** system_state table (key=`model_health_{profile_id}`)

### `_export_circuit_state()`
- **Callers:** `on_trading_iteration()` (finally block)
- **Writes:** `LOGS_DIR/circuit_state_{profile_id}.json`
- **Side effects:** Sends alert via `utils.alerter.send_alert()` when Theta breaker opens

### `_get_classifier_avg_move()`
- **Callers:** Step 8.5 and Step 9 in `_check_entries()`
- **Calls:** `ScalpPredictor.get_avg_30min_move_pct()` or `SwingClassifierPredictor.get_avg_daily_move_pct()`

### `_detect_model_type()`
- **Callers:** `initialize()`, Step 6 in `_check_entries()` (fallback)
- **Reads:** DB query: models JOIN profiles WHERE profiles.id = self.profile_id
- **Returns:** String model_type (e.g., "xgb_classifier", "xgb_swing_classifier")

### `_normalize_sleeptime(raw)` (static)
- **Callers:** `initialize()`
- **Returns:** Normalized Lumibot sleeptime string (e.g., "5M", "1M")

### Lumibot Lifecycle Hooks
- `on_filled_order()` — logs fill
- `on_canceled_order()` — logs cancellation
- `on_bot_crash(error)` — logs crash
- `before_market_opens()` / `after_market_closes()` — informational logging
- `send_update_to_cloud()` — overridden to no-op (no LumiWealth)

---

## 11. ML: Predictor (Abstract)

**File:** `options-bot/ml/predictor.py`

### `ModelPredictor` (ABC)
- **Methods:** `predict(features, sequence)`, `predict_batch(features_df)`, `get_feature_names()`, `get_feature_importance()`
- **Implementors:** XGBoostPredictor, ScalpPredictor, SwingClassifierPredictor, LightGBMPredictor, TFTPredictor, EnsemblePredictor

---

## 12. ML: XGBoostPredictor

**File:** `options-bot/ml/xgboost_predictor.py`

### `XGBoostPredictor(ModelPredictor)`
- **Callers:** `base_strategy.py` initialize (default/fallback), `models.py` _extract_and_persist_importance
- **`load(model_path)`:** `joblib.load()` -> extracts `model` + `feature_names`
- **`save(model_path, feature_names)`:** `joblib.dump({"model", "feature_names"})`
- **`predict(features, sequence=None)`:** Builds numpy array in feature order, calls `self._model.predict(X)[0]`
- **`predict_batch(features_df)`:** Reindexes columns, calls `self._model.predict(X)`
- **Data format:** `{"model": XGBRegressor, "feature_names": list[str]}`
- **Returns:** float (predicted forward return %)

---

## 13. ML: ScalpPredictor

**File:** `options-bot/ml/scalp_predictor.py`

### `ScalpPredictor(ModelPredictor)`
- **Callers:** `base_strategy.py` initialize (when model_type == "xgb_classifier")
- **`load(model_path)`:** Extracts model, feature_names, neutral_band, avg_30min_move_pct, calibrator, detects binary vs 3-class
- **`predict(features)`:** Calls `predict_proba(X)[0]`, applies `_calibrate_p_up()` (isotonic), then `_binary_to_signed_confidence()`
- **Returns:** Signed float: +0.72 = 72% confident UP, -0.65 = 65% confident DOWN
- **Conversion formula:** `confidence = (calibrated_p_up - 0.5) * 2.0`
- **`get_avg_30min_move_pct()`:** Returns training-time average 30-min absolute return
- **Data format:** `{"model": XGBClassifier, "feature_names": list, "neutral_band": float, "avg_30min_move_pct": float, "calibrator": IsotonicRegression|None, "binary_classifier": True}`

---

## 14. ML: SwingClassifierPredictor

**File:** `options-bot/ml/swing_classifier_predictor.py`

### `SwingClassifierPredictor(ModelPredictor)`
- **Callers:** `base_strategy.py` initialize (when model_type in ["xgb_swing_classifier", "lgbm_classifier"])
- **`predict(features)`:** Same signed confidence pattern as ScalpPredictor but NO isotonic calibration
- **`get_avg_daily_move_pct()`:** Returns training-time average daily absolute return
- **Data format:** `{"model": XGBClassifier|LGBMClassifier, "feature_names": list, "neutral_band": float, "avg_daily_move_pct": float, "model_type": str}`

---

## 15. ML: LightGBMPredictor

**File:** `options-bot/ml/lgbm_predictor.py`

### `LightGBMPredictor(ModelPredictor)`
- **Callers:** `base_strategy.py` initialize (when model_type == "lightgbm")
- **Same interface as XGBoostPredictor** — regression model, returns predicted return %
- **Data format:** `{"model": LGBMRegressor, "feature_names": list}`

---

## 16. ML: EV Filter

**File:** `options-bot/ml/ev_filter.py`

### `scan_chain_for_best_ev(strategy, symbol, predicted_return_pct, ...)`
- **Callers:** `base_strategy.py` Step 9
- **Calls:**
  - `strategy.get_chains(stock_asset)` — Lumibot -> Alpaca option chains
  - `strategy.get_greeks(option_asset)` — Lumibot Black-Scholes
  - `_estimate_delta(...)` — fallback when broker Greeks are bad (abs(delta) < 0.05)
  - `strategy.get_last_price(option_asset)` — option premium
- **EV formula:**
  - `expected_gain = |delta| * move + 0.5 * |gamma| * move^2`
  - `theta_cost = |theta| * hold_days * theta_accel`
  - `EV% = (expected_gain - theta_cost - half_spread) / premium * 100`
- **Returns:** `EVCandidate` (best by EV%) or None
- **Filters:** DTE range, moneyness range (+-5%), minimum EV%, spread ratio

### `get_implied_move_pct(strategy, symbol, underlying_price, ...)`
- **Callers:** `base_strategy.py` Step 8.5
- **Calls:** `strategy.get_chains()`, `strategy.get_last_price()` for ATM call + put
- **Returns:** `straddle_cost / underlying_price * 100` (implied move %)

### `_estimate_delta(underlying_price, strike, dte, direction, ...)`
- **Callers:** `scan_chain_for_best_ev()` (fallback)
- **Uses:** Simplified Black-Scholes N(d1) with Abramowitz & Stegun CDF approximation

---

## 17. ML: Liquidity Filter

**File:** `options-bot/ml/liquidity_filter.py`

### `check_liquidity(open_interest, daily_volume, bid_price, ask_price, ...)`
- **Callers:** `base_strategy.py` Step 9.5
- **Checks:** OI >= min_oi, volume >= min_volume, spread_pct <= max_spread_pct
- **Returns:** `LiquidityResult(passed, open_interest, daily_volume, bid_ask_spread_pct, reject_reason)`

### `fetch_option_snapshot(symbol, expiration, strike, right, api_key, api_secret, ...)`
- **Callers:** `base_strategy.py` Step 9.5
- **Calls:** `alpaca.data.historical.option.OptionHistoricalDataClient.get_option_snapshot()`
- **Builds OCC symbol:** e.g., `SPY260311C00560000`
- **Returns:** `{"open_interest", "volume", "bid", "ask"}`

---

## 18. ML: Regime Adjuster

**File:** `options-bot/ml/regime_adjuster.py`

### `adjust_prediction_confidence(predicted_return, vix_level, ...)`
- **Callers:** `base_strategy.py` Step 5.5 (SKIP for scalp)
- **Reads:** VIX regime thresholds from config.py
- **Logic:**
  - VIXY < 18 (low vol): multiply by 1.1
  - VIXY 18-28 (normal): multiply by 1.0
  - VIXY > 28 (high vol): multiply by 0.7
- **Returns:** `(adjusted_return, regime_name)`

---

## 19. ML: Trainer (XGBoost)

**File:** `options-bot/ml/trainer.py`

### `train_model(profile_id, symbol, preset, prediction_horizon, years_of_data)`
- **Callers:** `models.py` `_full_train_job` (background thread)
- **Pipeline:**
  1. `AlpacaStockProvider().get_historical_bars()` — fetch stock bars
  2. `_compute_all_features(bars_df, preset)` which calls:
     - `fetch_options_for_training()` — Theta Terminal options data
     - `fetch_vix_daily_bars()` — VIX features
     - `compute_base_features()` + preset-specific features
  3. Calculate forward return target
  4. Optuna hyperparameter optimization (optional, OPTUNA_N_TRIALS trials)
  5. Walk-forward CV (5 folds, expanding window)
  6. Train final XGBRegressor on all data
  7. `XGBoostPredictor.save()` — writes .joblib
  8. DB: INSERT INTO models, UPDATE profiles (model_id, status='ready')
- **Returns:** `{"status": "ready", "model_id", "model_path", "metrics"}`
- **Writes:** models table, profiles table, model .joblib file

---

## 20. ML: Scalp Trainer

**File:** `options-bot/ml/scalp_trainer.py`

### `train_scalp_model(profile_id, symbol, prediction_horizon, years_of_data)`
- **Callers:** `models.py` `_scalp_train_job` (background thread)
- **Pipeline:**
  1. `AlpacaStockProvider().get_historical_bars(timeframe="1min")` — 1-minute bars
  2. `_compute_all_features(bars_df)` — base_features(bars_per_day=390) + scalp_features
  3. `_calculate_binary_target()` — 30-min forward return, filter neutral band (+-0.05%)
  4. Subsample every 15 bars (SUBSAMPLE_STRIDE)
  5. Optuna: optimize balanced accuracy
  6. Walk-forward CV (5 folds)
  7. Isotonic calibration on hold-out fold
  8. Train final XGBClassifier
  9. `ScalpPredictor.save()` — writes .joblib with calibrator
  10. DB: INSERT models, UPDATE profiles
- **Constants:** NEUTRAL_BAND_PCT=0.05, HORIZON_BARS=30, SUBSAMPLE_STRIDE=15, SCALP_BARS_PER_DAY=390
- **Returns:** `{"status": "ready", "model_id", "model_path", "metrics"}`

---

## 21. ML: Swing Classifier Trainer

**File:** `options-bot/ml/swing_classifier_trainer.py`

### `train_swing_classifier_model(profile_id, symbol, prediction_horizon, years_of_data, model_type)`
- **Callers:** `models.py` `_swing_classifier_train_job` (background thread)
- **Supports:** `model_type="xgb_swing_classifier"` (XGBClassifier) or `"lgbm_classifier"` (LGBMClassifier)
- **Pipeline:** Similar to scalp but uses 5-min bars, 1-day forward return, swing/general features
- **Saves via:** `SwingClassifierPredictor.save()`

---

## 22. ML: LightGBM Trainer

**File:** `options-bot/ml/lgbm_trainer.py`

### `train_lgbm_model(profile_id, symbol, preset, prediction_horizon, years_of_data)`
- **Callers:** `models.py` `_lgbm_train_job` (background thread)
- **Pipeline:** Same as XGBoost trainer but uses LGBMRegressor
- **Saves via:** `LightGBMPredictor.save()`

---

## 23. ML: Feedback Queue

**File:** `options-bot/ml/feedback_queue.py`

### `enqueue_completed_sample(db_path, trade_id, profile_id, symbol, entry_features, predicted_return, actual_return_pct)`
- **Callers:** `base_strategy.py` `_execute_exit()` (on every trade close)
- **Writes:** INSERT INTO training_queue
- **Consumed by:** `incremental_trainer.py`

---

## 24. ML: Feature Engineering -- Base Features

**File:** `options-bot/ml/feature_engineering/base_features.py`

### `compute_base_features(bars_df, options_daily_df=None, vix_daily_df=None, bars_per_day=78)`
- **Callers:** `base_strategy.py` Steps 3-4, all trainers (`_compute_all_features`)
- **Calls:**
  - `compute_stock_features(df, bars_per_day)` — 44 stock features from OHLCV
  - `compute_options_features(df, options_daily_df)` — ~18 options features (IV, skew, term structure, put-call ratio, OI, Greeks)
  - `compute_vix_features(df, vix_daily_df)` — 3 VIX features (level, term structure, change_5d)
  - `compute_greeks_vectorized()` — Black-Scholes Greeks calculation
- **Returns:** DataFrame with all base features added as columns

### `compute_stock_features(df, bars_per_day)` — ~44 features
- Price returns (8): ret_5min through ret_20d
- Moving average ratios (8): sma_ratio_10..200, ema_ratio_9..50
- Volatility (6): rvol_1hr through rvol_20d
- Oscillators (6): rsi_14, rsi_7, macd_*, adx_14
- Bands (5): bb_*, atr_14_pct
- Volume (3): vol_ratio_20, obv_slope, vwap_dev
- Price position (2): dist_20d_high/low
- Intraday (3): intraday_return, gap_from_prev_close, last_hour_momentum
- Time (3): day_of_week, hour_of_day, minutes_to_close

### `get_base_feature_names()` — returns list of ~73 base feature name strings

---

## 25. ML: Feature Engineering -- Scalp Features

**File:** `options-bot/ml/feature_engineering/scalp_features.py`

### `compute_scalp_features(df)` — adds 15 features
- **Callers:** `base_strategy.py` (scalp preset), `scalp_trainer.py`
- **Features:**
  1. scalp_momentum_1min, 2. scalp_momentum_5min
  3. scalp_orb_distance (opening range breakout)
  4. scalp_vwap_slope, 5. scalp_volume_surge
  6. scalp_spread_proxy, 7. scalp_microstructure_imbalance
  8. scalp_time_bucket (30-min buckets 0-12)
  9. scalp_gamma_exposure_est
  10. scalp_intraday_range_pos
  11-14. scalp_ofi_5, ofi_15, ofi_cumulative, ofi_acceleration (order flow)
  15. scalp_volume_delta

### `get_scalp_feature_names()` — returns list of 15 feature name strings

---

## 26. ML: Feature Engineering -- Swing Features

**File:** `options-bot/ml/feature_engineering/swing_features.py`

### `compute_swing_features(df)` — adds 5 features
- **Callers:** `base_strategy.py` (swing preset), `trainer.py`, `swing_classifier_trainer.py`
- **Features:**
  1. swing_dist_sma_20d (requires 1560 bars warmup)
  2. swing_bb_extreme
  3. swing_rsi_ob_os_duration
  4. swing_mean_rev_zscore
  5. swing_prior_bounce_magnitude

### `get_swing_feature_names()` — returns 5 names

---

## 27. ML: Feature Engineering -- General Features

**File:** `options-bot/ml/feature_engineering/general_features.py`

### `compute_general_features(df)` — adds 4 features
- **Callers:** `base_strategy.py` (general preset), `trainer.py`
- **Features:**
  1. general_trend_slope_50d (requires 3900 bars warmup)
  2. general_momentum_long
  3. general_trend_consistency
  4. general_vol_regime

### `get_general_feature_names()` — returns 4 names

---

## 28. Data: Provider (Abstract)

**File:** `options-bot/data/provider.py`

### `StockDataProvider` (ABC)
- **Methods:** `get_historical_bars()`, `get_latest_price()`, `test_connection()`
- **Implementors:** `AlpacaStockProvider`

### `OptionsDataProvider` (ABC)
- **Methods:** `get_expirations()`, `get_strikes()`, `get_historical_greeks()`, `get_historical_ohlc()`, `get_historical_eod()`, `get_bulk_greeks_eod()`, `test_connection()`
- **Implementors:** `ThetaOptionsProvider`

---

## 29. Data: Alpaca Provider

**File:** `options-bot/data/alpaca_provider.py`

### `AlpacaStockProvider(StockDataProvider)`
- **Callers:** All trainers (fetch historical bars), `base_strategy.py` (backtest bar pre-fetch), `vix_provider.py` (fetch_vix_daily_bars)
- **`get_historical_bars(symbol, start, end, timeframe)`:**
  - Calls `StockHistoricalDataClient.get_stock_bars()` with pagination (max 10K bars/request)
  - Supports: 1min, 5min, 15min, 1h, 1d
  - Circuit breaker + exponential backoff on failures
- **`get_latest_price(symbol)`:** Via `StockHistoricalDataClient`
- **`test_connection()`:** Via `TradingClient.get_account()`
- **State:** Internal `CircuitBreaker` instance

---

## 30. Data: Theta Provider

**File:** `options-bot/data/theta_provider.py`

### `ThetaOptionsProvider(OptionsDataProvider)`
- **Callers:** `options_data_fetcher.py` (training data), system.py (connectivity check)
- **`_request(endpoint, params)`:** REST GET to `THETA_BASE_URL_V3` with retry (3x, 2s delay, 60s timeout)
- **`get_expirations(symbol)`:** `/stock/option/expirations`
- **`get_strikes(symbol, expiration)`:** `/stock/option/strikes`
- **`get_historical_greeks(symbol, ...)`:** `/stock/option/greeks/first_order` — divides rho/vega by 100
- **`get_historical_eod(symbol, ...)`:** `/stock/option/eod` — parses CSV response
- **`get_bulk_greeks_eod(symbol, expiration, trade_date)`:** `/stock/option/greeks/first_order` (bulk)
- **`test_connection()`:** `/stock/list/symbols`
- **Response handling:** Auto-detects JSON vs CSV responses

---

## 31. Data: VIX Provider

**File:** `options-bot/data/vix_provider.py`

### `VIXProvider` (class)
- **Callers:** `base_strategy.py` (Step 1.5 VIX gate, Step 5.5 regime adjust)
- **`get_current_vix()`:**
  - Caches for 300s (VIX_CACHE_TTL_SECONDS)
  - Calls `StockHistoricalDataClient.get_stock_bars("VIXY", 5-day range, daily)`
  - Returns latest VIXY close price
  - None on failure (fail-open)

### `fetch_vix_daily_bars(start, end)` (module-level function)
- **Callers:** All trainers, `base_strategy.py` (feature computation)
- **Calls:** `AlpacaStockProvider.get_historical_bars()` for VIXY + VIXM (daily)
- **Returns:** DataFrame with vixy_close, vixm_close columns
- **Caching:** Module-level cache, refreshes once per calendar day

---

## 32. Data: Options Data Fetcher

**File:** `options-bot/data/options_data_fetcher.py`

### `fetch_options_for_training(symbol, bars_df, min_dte, max_dte)`
- **Callers:** All trainers (`_compute_all_features`), `base_strategy.py` (feature computation in entries + exits)
- **Pipeline:**
  1. Extract daily close prices from bars_df to determine ATM strikes
  2. Group trading days into monthly batches
  3. Pick monthly expiration (~30 DTE from mid-period)
  4. Fetch bulk EOD data from Theta Terminal (all strikes, calls + puts)
  5. Extract ATM data, compute IV via Black-Scholes bisection (`_implied_vol()`)
  6. Compute IV skew from OTM put/call IV
  7. Cache results to parquet (`CACHE_DIR`)
- **Calls:** `requests.get(THETA_BASE_URL_V3/stock/option/eod, ...)` directly (not via ThetaOptionsProvider)
- **Returns:** DataFrame with daily options features (IV, skew, OI, volume, etc.)
- **Contains:** Full Black-Scholes implementation (`_bs_price`, `_implied_vol`)

---

## 33. Risk: RiskManager

**File:** `options-bot/risk/risk_manager.py`

### `RiskManager`
- **Callers:** `base_strategy.py` (all risk checks and trade logging)
- **Architecture:** Bridges sync Lumibot with async aiosqlite via dedicated event loop thread

### `check_pdt(equity)` -> `check_pdt_limit(equity)`
- **Reads:** trades table (day trades in last 7 days WHERE was_day_trade=1)
- **Returns:** `{"allowed": bool, "message": str}`
- **Logic:** If equity >= $25K, PDT not applicable. Otherwise, block if 3+ day trades.

### `check_position_limits(profile_config, portfolio_value, profile_id)`
- **Reads:** trades table (open positions count — global and per-profile)
- **Calls:** `check_portfolio_exposure(portfolio_value)` (Phase 2)
- **Checks:** Total open < MAX_TOTAL_POSITIONS (10), profile open < max_concurrent_positions

### `check_portfolio_exposure(portfolio_value)`
- **Reads:** trades table (SUM entry_price * quantity * 100 WHERE open)
- **Returns:** `{"allowed": bool, "exposure_pct": float, ...}`
- **Threshold:** MAX_TOTAL_EXPOSURE_PCT = 60%

### `check_emergency_stop_loss(current, initial)`
- **Returns:** `{"triggered": bool, "drawdown_pct": float, ...}`
- **Threshold:** EMERGENCY_STOP_LOSS_PCT = 20%
- **Side effect:** Sends CRITICAL alert via `utils.alerter.send_alert()` when triggered

### `calculate_position_size(portfolio_value, option_price, profile_config)`
- **Logic:** `min(max_dollars / (option_price * 100), max_contracts_config)`
- **Returns:** int (number of contracts, 0 if unaffordable)

### `check_can_open_position(profile_id, profile_config, portfolio_value, option_price)`
- **Calls:** `check_pdt_limit()`, `check_position_limits()`, `_get_profile_daily_trade_count()`, `calculate_position_size()`
- **Returns:** `{"allowed": bool, "quantity": int, "reasons": list[str]}`

### `log_trade_open(...)`
- **Writes:** INSERT INTO trades (18 fields including JSON features and Greeks)

### `log_trade_close(...)`
- **Writes:** UPDATE trades SET exit fields, pnl, status='closed'

### `get_portfolio_greeks(open_positions)`
- **Callers:** `base_strategy.py` Step 9.7
- **Returns:** `{"total_delta", "total_gamma", "total_theta", "total_vega", "position_count"}`

---

## 34. Utils: Circuit Breaker

**File:** `options-bot/utils/circuit_breaker.py`

### `CircuitBreaker`
- **Callers:** `base_strategy.py` (Theta circuit breaker), `alpaca_provider.py` (Alpaca circuit breaker)
- **States:** CLOSED -> OPEN (after failure_threshold failures) -> HALF_OPEN (after reset_timeout) -> CLOSED (on success)
- **Methods:**
  - `can_execute()` — returns True if CLOSED or HALF_OPEN (allows one test call)
  - `record_success()` — resets to CLOSED
  - `record_failure()` — increments failure_count, transitions to OPEN if threshold hit
- **Thread-safe:** Uses `threading.Lock`

### `exponential_backoff(attempt, base, max_delay)`
- **Callers:** `alpaca_provider.py` retry loop
- **Returns:** `min(base * 2^attempt, max_delay)` seconds

---

## 35. Frontend: API Client

**File:** `options-bot/ui/src/api/client.ts`

### `api` object — typed fetch wrapper for all backend endpoints

| Namespace | Methods | Backend Routes |
|-----------|---------|----------------|
| `api.profiles` | list, get, create, update, delete, activate, pause | /api/profiles/* |
| `api.models` | train(profileId, modelType), retrain, status, logs, clearLogs, importance | /api/models/* |
| `api.trades` | list, active, stats, exportUrl | /api/trades/* |
| `api.system` | health, status, pdt, errors, clearErrors, modelHealth, trainingQueue | /api/system/* |
| `api.backtest` | run, results | /api/backtest/* |
| `api.trading` | status, start, stop, restart, startableProfiles | /api/trading/* |
| `api.signals` | list, exportUrl | /api/signals/* |

### `request<T>(path, options)` — base fetch function
- Adds `Content-Type: application/json` for non-GET
- Throws on non-2xx
- Returns `undefined` for 204 No Content
- Uses Vite proxy (BASE = '') to route /api -> localhost:8000

---

## 36. Architectural Flow Traces

### Flow 1: Trading Pipeline (on_trading_iteration)

```
Lumibot framework
  -> BaseOptionsStrategy.on_trading_iteration()
       -> Auto-pause check (consecutive_errors >= 10)
       -> _update_prediction_outcomes(current_price)  [health tracking]
       -> Scalp equity gate ($25K)
       -> Record _initial_portfolio_value
       -> Step 0a: risk_mgr.check_emergency_stop_loss()
            -> DB: trades table (exposure calc)
            -> If triggered: liquidate all via create_order/submit_order
       -> Step 1: _check_exits()
            -> Lumibot: get_positions()
            -> For each position: get_last_price(), eval 6 exit rules
            -> _execute_exit() -> create_order/submit_order
                 -> risk_mgr.log_trade_close() -> DB: UPDATE trades
                 -> feedback_queue.enqueue_completed_sample() -> DB: INSERT training_queue
       -> Step 0b: risk_mgr.check_portfolio_exposure()
            -> DB: trades table (SUM exposure)
       -> Step 2: _check_entries()
            -> [13 steps documented in Section 10]
            -> Final: create_order/submit_order -> risk_mgr.log_trade_open() -> DB: INSERT trades
       -> _persist_health_to_db() -> DB: system_state
       -> _export_circuit_state() -> LOGS_DIR/circuit_state_*.json
```

### Flow 2: Model Training

```
Frontend: api.models.train(profileId, modelType)
  -> POST /api/models/{id}/train
       -> _check_theta_or_raise() [Theta Terminal connectivity pre-check]
       -> _active_jobs.add(profile_id) [prevent duplicate]
       -> threading.Thread(target=_*_train_job).start()
            -> _install_training_logger(profile_id) [DB log handler]
            -> _set_profile_status(profile_id, "training") -> DB: UPDATE profiles
            -> train_model() / train_scalp_model() / train_swing_classifier_model():
                 -> AlpacaStockProvider().get_historical_bars() [stock bars]
                 -> fetch_options_for_training() -> Theta Terminal REST [options data]
                 -> fetch_vix_daily_bars() -> Alpaca [VIX data]
                 -> compute_base_features() + preset features [feature engineering]
                 -> Forward return target calculation
                 -> Optuna hyperparameter optimization
                 -> Walk-forward CV (5 folds)
                 -> Train final model (XGBRegressor/XGBClassifier/LGBMClassifier)
                 -> predictor.save() [.joblib to MODELS_DIR]
                 -> DB: INSERT INTO models, UPDATE profiles (model_id, status='ready')
            -> _extract_and_persist_importance() -> DB: UPDATE models.metrics
            -> _remove_training_logger(handler)
            -> _active_jobs.discard(profile_id)
```

### Flow 3: Model Inference (Live Entry)

```
_check_entries() Step 5:
  -> self.predictor.predict(latest_features, sequence=sequence_df)
       -> XGBoostPredictor: model.predict(X)[0] -> float (return %)
       -> ScalpPredictor: model.predict_proba(X)[0]
            -> _calibrate_p_up(raw_p_up) [isotonic regression if available]
            -> _binary_to_signed_confidence(proba) -> signed float (-1 to +1)
       -> SwingClassifierPredictor: model.predict_proba(X)[0]
            -> _binary_to_signed_confidence(proba) -> signed float
       -> LightGBMPredictor: model.predict(X)[0] -> float (return %)
  -> Step 5.5: adjust_prediction_confidence() [VIX regime, skip for scalp]
  -> Step 6: Threshold gate (min_confidence for classifiers, min_predicted_move_pct for regression)
  -> Step 9: scan_chain_for_best_ev()
       -> For classifiers: ev_predicted_return = avg_move * direction_sign
       -> strategy.get_chains() -> option chain from Alpaca
       -> strategy.get_greeks() -> Black-Scholes (with _estimate_delta fallback)
       -> EV calculation: delta-gamma approximation with theta acceleration
  -> Step 9.5: fetch_option_snapshot() + check_liquidity()
       -> Alpaca options snapshot API for OI/volume/spread
```

### Flow 4: Data Flow

```
TRAINING DATA:
  AlpacaStockProvider -> get_historical_bars(symbol, start, end, timeframe)
       -> Alpaca REST API -> stock OHLCV bars (5min or 1min)
  ThetaOptionsProvider / options_data_fetcher -> Theta Terminal V3 REST
       -> /stock/option/eod -> historical options EOD data
       -> Black-Scholes IV solver -> implied volatility
  VIXProvider -> fetch_vix_daily_bars()
       -> Alpaca REST API -> VIXY + VIXM daily bars

LIVE DATA (via Lumibot):
  strategy.get_last_price() -> Alpaca live quote
  strategy.get_historical_prices() -> Alpaca historical bars (data store)
  strategy.get_chains() -> Alpaca option chains
  strategy.get_greeks() -> Lumibot Black-Scholes calculation
  VIXProvider.get_current_vix() -> Alpaca daily bar for VIXY
```

### Flow 5: Frontend -> API -> Backend -> DB Round Trips

```
Dashboard.tsx:
  useEffect -> api.system.health()     -> GET /api/system/health      -> HealthCheck response
  useEffect -> api.system.status()     -> GET /api/system/status      -> DB: profiles, trades counts
  useEffect -> api.profiles.list()     -> GET /api/profiles            -> DB: profiles, models, trades
  useEffect -> api.trades.active()     -> GET /api/trades/active       -> DB: trades WHERE open
  useEffect -> api.trades.stats()      -> GET /api/trades/stats        -> DB: trades aggregate
  useEffect -> api.trading.status()    -> GET /api/trading/status      -> In-memory _processes + DB profiles

Profiles page:
  Create   -> api.profiles.create()    -> POST /api/profiles           -> DB: INSERT profiles
  Edit     -> api.profiles.update()    -> PUT /api/profiles/{id}       -> DB: UPDATE profiles
  Delete   -> api.profiles.delete()    -> DELETE /api/profiles/{id}    -> DB: DELETE cascade
  Train    -> api.models.train()       -> POST /api/models/{id}/train  -> Background thread
  Poll     -> api.models.status()      -> GET /api/models/{id}/status  -> _active_jobs + DB

System.tsx:
  useEffect -> api.system.status()        -> External: Alpaca + Theta connectivity tests
  useEffect -> api.system.modelHealth()   -> DB: system_state (model_health_*)
  useEffect -> api.system.trainingQueue() -> DB: training_queue counts
  useEffect -> api.system.pdt()           -> DB: trades + Alpaca account equity
```

### Flow 6: Process Management

```
START:
  Frontend -> api.trading.start([profileId])
    -> POST /api/trading/start
         -> DB: SELECT profiles (validate)
         -> subprocess.Popen([python, main.py, --trade, --profile-id, id, --no-backend])
         -> _processes[profile_id] = {proc, pid, started_at, ...}
         -> _store_process_state() -> DB: system_state (trading_{id})
         -> DB: UPDATE profiles SET status='active'

WATCHDOG (continuous background thread):
  _watchdog_loop() [every WATCHDOG_POLL_INTERVAL_SECONDS=30s]:
    For each tracked process:
      If proc.poll() is not None (dead):
        -> _clear_process_state() -> DB: DELETE system_state
        -> _set_profile_status_sync("error") -> DB: UPDATE profiles
        -> If auto-restart enabled and count < 3:
             -> time.sleep(WATCHDOG_RESTART_DELAY_SECONDS=5)
             -> _watchdog_restart_profile() -> subprocess.Popen(...)
             -> _store_process_state() -> DB: system_state
             -> _set_profile_status_sync("active") -> DB: UPDATE profiles
      If alive:
        -> Reset restart counter to 0

STOP:
  Frontend -> api.trading.stop([profileId])
    -> POST /api/trading/stop
         -> proc.terminate() -> proc.wait(10) -> proc.kill() if needed
         -> OR taskkill /PID /T /F on Windows
         -> _clear_process_state() -> DB: DELETE system_state
         -> DB: UPDATE profiles SET status='paused'

RESTART:
  Frontend -> api.trading.restart([profileId])
    -> stop_trading() + asyncio.sleep(1) + start_trading()

BACKEND STARTUP (restore):
  lifespan() -> restore_process_registry(db)
    -> DB: SELECT system_state WHERE key LIKE 'trading_%'
    -> For each: _is_process_alive(pid) -> re-register or cleanup
    -> Clean stale 'active' profiles with no running process -> set 'ready'
```

---

## Cross-Module Dependency Summary

### Most-Connected Symbols (by caller count)

| Symbol | Module | Caller Count | Callers |
|--------|--------|-------------|---------|
| `DB_PATH` | config.py | 12+ | database, risk_manager, trading, models, system, trainer, scalp_trainer, app, base_strategy, feedback_queue, options_data_fetcher, db_log_handler |
| `compute_base_features()` | base_features.py | 6 | base_strategy (entries + exits + override), trainer, scalp_trainer, swing_classifier_trainer, lgbm_trainer |
| `scan_chain_for_best_ev()` | ev_filter.py | 1 | base_strategy Step 9 |
| `RiskManager` | risk_manager.py | 1 instance | base_strategy (PDT, positions, exposure, sizing, trade logging) |
| `check_liquidity()` | liquidity_filter.py | 1 | base_strategy Step 9.5 |
| `VIXProvider.get_current_vix()` | vix_provider.py | 2 call sites | base_strategy Steps 1.5 and 5.5 |
| `fetch_vix_daily_bars()` | vix_provider.py | 4+ | all trainers, base_strategy feature computation |
| `fetch_options_for_training()` | options_data_fetcher.py | 4+ | all trainers, base_strategy feature computation |
| `PRESET_DEFAULTS` | config.py | 8+ | profiles.py, all trainers, base_strategy, models.py |

### External Service Dependencies

| Service | Used By | Connection Method | Failure Mode |
|---------|---------|-------------------|-------------|
| Alpaca Trading API | trading (orders), system (account), risk (PDT) | Lumibot broker, TradingClient | Fatal for trading |
| Alpaca Data API | alpaca_provider (bars), vix_provider, liquidity_filter | StockHistoricalDataClient, OptionHistoricalDataClient | Circuit breaker, fail-open for features |
| Theta Terminal V3 | theta_provider, options_data_fetcher | REST GET localhost:25503 | Required for training, circuit breaker for live |
| SQLite | All modules | aiosqlite (async) + sqlite3 (sync) | WAL mode for concurrency |

---

*Generated for zero-omission audit. Every function, class, and data flow traced from source files.*
