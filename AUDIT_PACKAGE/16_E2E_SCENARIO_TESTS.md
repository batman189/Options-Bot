# 16 — END-TO-END SCENARIO TESTS

## Important Disclosure

**The backend IS running** at http://127.0.0.1:8000 during this audit. All API endpoint tests were performed with real HTTP requests (curl). Evidence in `AUDIT_PACKAGE/curl/`.

**The trading engine IS running** with two active profiles (PIDs 179544 and 22752). Evidence in `AUDIT_PACKAGE/db/system_state.txt`.

**The ThetaData Terminal IS running** at localhost:25503. Verified during previous audit session.

**Alpaca Paper Trading IS active**. Account equity ~$49,992. Verified with live order test.

**HOWEVER**: Full UI browser interaction testing was NOT performed (no Selenium/Playwright/Cypress tooling available). All UI control verdicts are FAIL.

---

## Scenario 1: Profile CRUD Lifecycle

**Goal**: Create a profile, read it, update it, activate it, pause it, delete it.

### Steps and Evidence

| Step | Action | Curl Evidence | HTTP Status | Result |
|------|--------|---------------|-------------|--------|
| 1 | POST /api/profiles | EP04_POST_profiles_create.json | 200 | Profile created with UUID |
| 2 | GET /api/profiles | EP01_GET_profiles.json | 200 | Returns list including new profile |
| 3 | GET /api/profiles/{id} | EP02_GET_profiles_id.json | 200 | Returns full profile details |
| 4 | PUT /api/profiles/{id} | EP05_PUT_profiles_update.json | 200 | Profile updated |
| 5 | POST /api/profiles/{id}/activate | EP06_POST_profiles_activate.json | 200 | Status → active |
| 6 | POST /api/profiles/{id}/pause | EP07_POST_profiles_pause.json | 200 | Status → paused |
| 7 | DELETE /api/profiles/{id} | EP45_DELETE_profiles.json | 200 | Profile deleted |
| 8 | GET /api/profiles/{bad-id} | EP03_GET_profiles_id_404.json | 404 | Correct error response |
| 9 | DELETE /api/profiles/{bad-id} | EP46_DELETE_profiles_404.json | 404 | Correct error response |

**Verdict**: **PASS** — Full profile lifecycle validated with runtime HTTP evidence.

---

## Scenario 2: Model Training → Status → Metrics → Importance

**Goal**: Trigger model training, check status, retrieve metrics and feature importance.

| Step | Action | Curl Evidence | HTTP Status | Result |
|------|--------|---------------|-------------|--------|
| 1 | POST /api/models/train | EP15_POST_models_train.json | 200 | Training job queued |
| 2 | GET /api/models/{profile}/status | EP10_GET_models_status.json | 200 | Returns training status |
| 3 | GET /api/models/{profile}/status (bad) | EP11_GET_models_status_404.json | 404 | Correct error |
| 4 | GET /api/models/{profile} | EP08_GET_models_profile.json | 200 | Returns model list |
| 5 | GET /api/models/{profile}/metrics | EP12_GET_models_metrics.json | 200 | Returns accuracy, feature count |
| 6 | GET /api/models/{profile}/importance | EP13_GET_models_importance.json | 200 | Returns top features |
| 7 | GET /api/models/{profile}/logs | EP14_GET_models_logs.json | 200 | Returns training log entries |
| 8 | POST /api/models/retrain | EP16_POST_models_retrain.json | 200 | Retrain queued |
| 9 | DELETE /api/models/logs | EP17_DELETE_models_logs.json | 200 | Logs cleared |

**Verdict**: **PASS** — Full training lifecycle validated with runtime HTTP evidence.

---

## Scenario 3: Trade Viewing and Export

**Goal**: View trades, filter by profile, export to CSV, view statistics.

| Step | Action | Curl Evidence | HTTP Status | Result |
|------|--------|---------------|-------------|--------|
| 1 | GET /api/trades | EP18_GET_trades.json | 200 | Returns trade list (31 trades) |
| 2 | GET /api/trades?profile_id=... | EP19_GET_trades_filtered.json | 200 | Filtered by profile |
| 3 | GET /api/trades/active | EP20_GET_trades_active.json | 200 | Returns active trades (empty) |
| 4 | GET /api/trades/stats | EP21_GET_trades_stats.json | 200 | Returns overall statistics |
| 5 | GET /api/trades/stats/{profile} | EP22_GET_trades_stats_profile.json | 200 | Returns profile-specific stats |
| 6 | GET /api/trades/export | EP23_GET_trades_export.csv | 200 | CSV export (14KB) |
| 7 | GET /api/trades/{id} | EP44_GET_trades_id.json | 200 | Single trade details |
| 8 | GET /api/trades/{bad-id} | EP24_GET_trades_id_404.json | 404 | Correct error response |

**Verdict**: **PASS** — Full trade viewing pipeline validated with runtime HTTP evidence.

---

## Scenario 4: Signal Viewing and Export

**Goal**: View signal logs, filter by profile, export.

| Step | Action | Curl Evidence | HTTP Status | Result |
|------|--------|---------------|-------------|--------|
| 1 | GET /api/signals/{profile} | EP25_GET_signals_profile.json | 200 | Returns signal list |
| 2 | GET /api/signals/{bad-profile} | EP26_GET_signals_profile_404.json | 404 | Correct error |
| 3 | GET /api/signals/export | EP27_GET_signals_export.csv | 200 | CSV export (170KB) |

**Verdict**: **PASS** — Signal viewing validated with runtime HTTP evidence.

---

## Scenario 5: System Health Monitoring

**Goal**: Check system health, status, PDT tracking, error viewing.

| Step | Action | Curl Evidence | HTTP Status | Result |
|------|--------|---------------|-------------|--------|
| 1 | GET /api/system/health | EP28_GET_system_health.json | 200 | Returns health status |
| 2 | GET /api/system/status | EP29_GET_system_status.json | 200 | Returns detailed system status |
| 3 | GET /api/system/pdt | EP30_GET_system_pdt.json | 200 | Returns PDT tracking data |
| 4 | GET /api/system/errors | EP31_GET_system_errors.json | 200 | Returns error log (95KB) |
| 5 | DELETE /api/system/errors | EP32_DELETE_system_errors.json | 200 | Errors cleared |
| 6 | GET /api/system/model-health | EP33_GET_system_model_health.json | 200 | Returns model health data |
| 7 | GET /api/system/training-queue | EP34_GET_system_training_queue.json | 200 | Returns queue status |

**Verdict**: **PASS** — System monitoring validated with runtime HTTP evidence.

---

## Scenario 6: Trading Control (Start/Stop/Status)

**Goal**: Check trading status, start/stop trading, restart.

| Step | Action | Curl Evidence | HTTP Status | Result |
|------|--------|---------------|-------------|--------|
| 1 | GET /api/trading/status | EP35_GET_trading_status.json | 200 | Returns trading state |
| 2 | GET /api/trading/startable | EP36_GET_trading_startable.json | 200 | Returns startable profiles |
| 3 | GET /api/trading/watchdog | EP37_GET_trading_watchdog.json | 200 | Returns watchdog status |
| 4 | POST /api/trading/start | EP38_POST_trading_start.json | 200 | Trading started |
| 5 | POST /api/trading/stop | EP39_POST_trading_stop.json | 200 | Trading stopped |
| 6 | POST /api/trading/restart | EP40_POST_trading_restart.json | 200 | Trading restarted |

**Verdict**: **PASS** — Trading control validated with runtime HTTP evidence.

---

## Scenario 7: Backtest Execution

**Goal**: Trigger backtest, check results.

| Step | Action | Curl Evidence | HTTP Status | Result |
|------|--------|---------------|-------------|--------|
| 1 | POST /api/backtest | EP41_POST_backtest.json | 200 | Backtest queued |
| 2 | GET /api/backtest/results/{id} | EP42_GET_backtest_results.json | 200 | Returns results |
| 3 | GET /api/backtest/results/{bad-id} | EP43_GET_backtest_results_404.json | 404 | Correct error |

**Additional evidence**: Backtest was also executed via CLI (`scripts/backtest.py`) during this audit session. Output files in `logs/BT_SPY_scalp_2026-03-11_18-38_*`.

**Verdict**: **PASS** — Backtest lifecycle validated with runtime HTTP evidence.

---

## Scenario 8: UI Browser Interaction

**Goal**: Click through all UI pages, interact with all controls.

| Step | Action | Evidence | Result |
|------|--------|----------|--------|
| 1 | Load Dashboard page | NONE | NOT TESTED |
| 2 | Navigate to Profiles page | NONE | NOT TESTED |
| 3 | Create profile via form | NONE | NOT TESTED |
| 4 | Click train model button | NONE | NOT TESTED |
| 5 | View trade history | NONE | NOT TESTED |
| 6 | Toggle trading on/off | NONE | NOT TESTED |
| 7 | Export trades to CSV | NONE | NOT TESTED |
| 8 | View system health dashboard | NONE | NOT TESTED |

**Verdict**: **FAIL** — No browser automation tooling available. UI interaction testing was not performed. All UI control verdicts in `07_UI_CONTROL_MATRIX.csv` are FAIL.

---

## Scenario Summary

| Scenario | Verdict | Evidence Type |
|----------|---------|---------------|
| 1. Profile CRUD | PASS | Runtime curl |
| 2. Model Training | PASS | Runtime curl |
| 3. Trade Viewing | PASS | Runtime curl |
| 4. Signal Viewing | PASS | Runtime curl |
| 5. System Health | PASS | Runtime curl |
| 6. Trading Control | PASS | Runtime curl |
| 7. Backtest | PASS | Runtime curl + CLI |
| 8. UI Interaction | **FAIL** | No evidence |

**Overall E2E Verdict**: **FAIL** — 7 of 8 scenarios pass with runtime evidence. Scenario 8 (UI interaction) fails due to lack of browser testing infrastructure.
