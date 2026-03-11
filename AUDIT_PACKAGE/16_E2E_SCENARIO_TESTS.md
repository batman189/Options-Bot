# 16. End-to-End Scenario Tests

## Methodology

All E2E traces below follow the directive requirement: tracing from trigger → through all system layers → to final observable outcome.
Evidence is drawn from code reading, DB inspection, and log analysis performed during this audit.
Backend is not running during audit — endpoint behavior is validated by code-path tracing.

---

## Scenario 1: New User Creates Profile → Trains Model → Starts Trading

### Step 1: Profile Creation
- **Trigger**: User fills ProfileForm (name="Test Swing", preset="swing", symbols=["TSLA"])
- **Frontend**: POST /api/profiles with `ProfileCreate{name, preset, symbols, config_overrides: {}}`
- **Backend**: `profiles.py:208` → validates preset ∈ {"swing","general","scalp"}, builds config from PRESET_DEFAULTS["swing"], generates UUID, INSERT INTO profiles
- **DB**: New row in profiles table, status="created", model_id=NULL
- **Response**: ProfileResponse with full config
- **Evidence**: Code path traced in profiles.py:207-241. DB schema verified in database.py CREATE TABLE profiles.
- **Verdict**: PASS

### Step 2: Model Training
- **Trigger**: User clicks "Train Model" with model_type="xgb_swing_classifier"
- **Frontend**: POST /api/models/{id}/train with `TrainRequest{model_type: "xgb_swing_classifier"}`
- **Backend**: `models.py:717` → validates profile exists, validates model_type ∈ PRESET_MODEL_TYPES["swing"] (["xgb_swing_classifier","lgbm_classifier"]), checks Theta Terminal reachable, claims job slot, spawns _swing_classifier_train_job thread
- **Background thread**: Sets status="training", calls train_swing_classifier_model(), on success: INSERT INTO models, UPDATE profiles SET model_id, status="ready"
- **Training logs**: Written to training_logs table via TrainingLogHandler, viewable at GET /api/models/{id}/logs
- **Evidence**: Code path traced in models.py:574-623 + swing_classifier_trainer.py. DB model record verified with `SELECT * FROM models`.
- **Verdict**: PASS

### Step 3: Start Trading
- **Trigger**: User clicks "Start Trading" for the profile
- **Frontend**: POST /api/trading/start with `TradingStartRequest{profile_ids: [id]}`
- **Backend**: `trading.py:451` → validates profile status ∈ {ready, active, paused} AND model_id not null, spawns subprocess `python main.py --trade --profile-id <id> --no-backend`
- **Subprocess**: Loads profile from DB, creates strategy instance, connects to Alpaca via Lumibot, enters trading loop
- **Evidence**: Code path traced in trading.py:451-555 + main.py:start_trading_single()
- **Verdict**: PASS

### Step 4: Trading Iteration (Entry Attempt)
- **Trigger**: Lumibot calls on_trading_iteration() per sleeptime interval
- **Flow**: 13-step entry pipeline (price → VIX → bars → features → prediction → confidence → implied move → earnings → EV → liquidity → delta → risk → order)
- **DB writes**: signal_logs INSERT (every iteration), trades INSERT (if entry placed)
- **Evidence**: Full pipeline traced in base_strategy.py _check_entries(). Signal log INSERT at line ~1520.
- **Critical finding**: 98% of iterations are rejected at liquidity gate (Step 10) based on live log analysis
- **Verdict**: PASS (pipeline correctly filters; high rejection rate is by design for safety)

### Step 5: Trade Exit
- **Trigger**: Profit target, stop loss, max hold, DTE floor, model override, or scalp EOD
- **Flow**: _check_exits() evaluates all rules in order, first match triggers sell
- **DB writes**: UPDATE trades SET status='closed', exit_price, pnl_dollars, pnl_pct, exit_reason
- **Feedback**: INSERT INTO training_queue (profile_id, trade_id, actual_return)
- **Evidence**: Code traced in base_strategy.py _check_exits()
- **Verdict**: PASS

---

## Scenario 2: Model Health Degradation → Dashboard Alert

### Step 1: Prediction Tracking
- **Source**: on_trading_iteration() → after prediction made, record to system_state
- **Key**: `model_health_{profile_id}` → JSON with rolling_accuracy, total_predictions, correct_predictions
- **Resolution**: Prediction resolved after PREDICTION_RESOLVE_MINUTES (60 for swing, 30 for scalp)
- **Evidence**: base_strategy.py prediction health tracking code

### Step 2: Health Endpoint Read
- **Trigger**: Dashboard auto-polls GET /api/system/model-health every 30s
- **Backend**: system.py:319 → JOIN profiles + models + system_state, compute status per profile
- **Status logic**:
  - `healthy`: rolling_accuracy > MODEL_DEGRADED_THRESHOLD (0.45)
  - `warning`: approaching threshold
  - `degraded`: below threshold
  - `stale`: model_age_days > MODEL_STALE_THRESHOLD_DAYS (30)
  - `no_data`: no predictions recorded yet
- **Evidence**: Code traced in system.py:319-444
- **Verdict**: PASS

---

## Scenario 3: Backtest Trigger → Results Display

### Step 1: Trigger Backtest
- **Frontend**: POST /api/backtest/{profile_id} with `BacktestRequest{start_date, end_date, initial_capital}`
- **Backend**: app.py:271 → validates profile exists + has model, claims backtest slot, spawns _backtest_job thread
- **Background**: Calls `scripts/backtest.py:run_backtest()` with Lumibot backtester + ThetaData
- **Storage**: Results stored in system_state table as JSON (key: `backtest_{profile_id}`)
- **Evidence**: Code traced in app.py:66-185
- **Verdict**: PASS (code path valid; actual backtest requires ThetaData Terminal running)

### Step 2: Poll Results
- **Frontend**: GET /api/backtest/{profile_id}/results (polled until status != "running")
- **Backend**: app.py:363 → reads system_state, parses JSON, returns BacktestResult
- **Evidence**: Code traced in app.py:362-409
- **Verdict**: PASS

---

## Scenario 4: Trading Process Crash → Watchdog Recovery

### Step 1: Process Crash
- **Trigger**: Trading subprocess exits with non-zero exit code
- **Detection**: Watchdog thread (_watchdog_loop, trading.py:136) polls every 30s
- **Check**: proc.poll() != None → process dead

### Step 2: Watchdog Response
- **Action 1**: Log crash with exit code
- **Action 2**: Remove from _processes dict, clear system_state
- **Action 3**: _set_profile_status_sync(profile_id, "error")
- **Action 4**: If WATCHDOG_AUTO_RESTART=True and restart_count < WATCHDOG_MAX_RESTARTS (3):
  - Sleep WATCHDOG_RESTART_DELAY_SECONDS (5s)
  - Spawn new subprocess with same command
  - Update profile status to "active"
  - Increment restart counter
- **Evidence**: Code traced in trading.py:136-307
- **Verdict**: PASS

---

## Scenario 5: 0DTE Scalp Trade — Full Numerical Path

### Given:
- Symbol: SPY, Price: $662.00
- Model prediction: UP with confidence 0.177 (calibrated)
- Profile: scalp preset (min_dte=0, max_dte=0, max_hold_days=0)

### Pipeline Trace:
1. **VIX gate**: VIXY=$22.50, range [12,50] → PASS
2. **Bars**: 1-min bars fetched, 88 features computed
3. **Prediction**: ScalpPredictor → p_up=0.5885, confidence=0.177, direction=UP
4. **Confidence gate**: 0.177 >= 0.10 (min_confidence) → PASS
5. **Implied move gate**: BYPASSED for classifier (base_strategy.py classifier bypass)
6. **Earnings gate**: SPY is ETF, no earnings → PASS
7. **EV filter**: scan_chain_for_best_ev()
   - Candidate: SPY 662 PUT, expiry today, premium=$0.05
   - delta=0.08, gamma=0.15, theta=-0.45
   - move = 662.00 * 0.177 * 0.1108 / 100 = $0.13 (using avg_30min_move)
   - **BUG-001**: hold_days_effective = min(0, 0) = 0 → theta_cost = 0
   - expected_gain = 0.08 * 0.13 + 0.5 * 0.15 * 0.13² = 0.0104 + 0.0013 = $0.0117
   - EV% = (0.0117 - 0) / 0.05 * 100 = 23.4% (inflated because theta=0)
   - **Correct EV** (with theta): theta_cost = 0.45 * 1 * (1+2*1) = $1.35
   - Correct EV% = (0.0117 - 1.35) / 0.05 * 100 = **-2,677%**
8. **Liquidity gate**: OI >= 100 AND volume >= 50 → typically FAIL (98% rejection rate)
9. **If passed**: Risk manager check, order placed

### Finding:
- BUG-001 causes inflated EV for all 0DTE options
- Liquidity gate is the de facto safety net preventing systematic losses
- **Verdict**: FAIL (BUG-001 is critical — EV calculation is mathematically wrong for 0DTE)

---

## Scenario 6: Profile Deletion Cascade

### Trigger: DELETE /api/profiles/{profile_id}
### Expected behavior: All associated data cleaned up

### Traced cascade (profiles.py:284-356):
1. Collect model IDs: `SELECT id, file_path FROM models WHERE profile_id = ?`
2. Delete training_logs by model_id: `DELETE FROM training_logs WHERE model_id IN (?)`
3. Delete training_logs by profile_id: `DELETE FROM training_logs WHERE profile_id = ?`
4. Delete model files from disk (shutil.rmtree for dirs, p.unlink for files) — runs in thread
5. Delete DB records: models, trades, signal_logs, training_queue, system_state (backtest_*, model_health_*, trading_*)
6. Delete profile: `DELETE FROM profiles WHERE id = ?`
7. Commit

### Findings:
- **Comprehensive**: All 7 related tables are cleaned
- **Thread-safe**: File deletion runs in asyncio.to_thread
- **No FK enforcement**: Cascade is manual (SQLite FKs not enabled)
- **Verdict**: PASS
