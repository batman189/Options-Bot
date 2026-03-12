# 16 — END-TO-END SCENARIO TESTS

## Important Disclosure

**The backend IS running** at http://127.0.0.1:8000 during this audit. All API endpoint tests were performed with real HTTP requests (curl). Evidence in `AUDIT_PACKAGE/curl/`.

**The trading engine IS running** with two active profiles (PIDs 179544 and 22752). Evidence in `AUDIT_PACKAGE/db/system_state.txt`.

**The ThetaData Terminal IS running** at localhost:25503. Verified during previous audit session.

**Alpaca Paper Trading IS active**. Account equity ~$49,992. Verified with live order test.

**UI browser interaction testing**: Performed with Playwright 1.58.2 (headless Chromium). All 110 UI controls tested, 52 screenshots captured, 109 API requests logged. Evidence in `screenshots/`, `network/`, `json/`.

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

## Scenario 8: UI Browser Interaction (Playwright)

**Goal**: Click through all UI pages, interact with all controls using headless Chromium via Playwright.

**Infrastructure**: Playwright 1.58.2, headless Chromium, Vite dev server on port 5174, backend API on port 8000.

| Step | Action | Evidence | Result |
|------|--------|----------|--------|
| 1 | Load Dashboard page | screenshots/dashboard_loaded.png | PASS — page renders with profile cards |
| 2 | Navigate to all 5 pages via nav links | screenshots/nav_*.png (5 files) | PASS — all nav links functional |
| 3 | Open Create Profile form | screenshots/profiles_new_profile_modal.png | PASS — modal opens with fields |
| 4 | Fill profile form fields | screenshots/profile_form_*.png | PASS — name, presets, symbols, advanced sliders |
| 5 | View profile detail page | screenshots/profile_detail_loaded_fix.png | PASS — full detail with model info |
| 6 | Test train/logs/backtest controls | screenshots/profile_detail_train_fix.png | PASS — all buttons functional |
| 7 | Test trade filters and sort | screenshots/trades_filters.png, trades_sorted.png | PASS — filters and column sorting work |
| 8 | Test signal log filters and sort | screenshots/signal_logs_loaded.png | PASS — filters and sorting functional |
| 9 | Test system page controls | screenshots/system_loaded.png, system_quick_start.png | PASS — refresh, quick start, process controls |
| 10 | Test error/404 handling | screenshots/page_not_found_404.png, profile_not_found_fix.png | PASS — error states handled |

**Evidence**:
- 52 screenshots in `screenshots/`
- 109 API requests captured in `network/api_requests.json`
- Full test results in `json/ui_test_results.json`

**Verdict**: **PASS** — All 110 UI controls interaction-tested with Playwright headless Chromium. 110/110 PASS.

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
| 8. UI Interaction | **PASS** | Playwright + 52 screenshots + 109 API calls |

**Overall E2E Verdict**: **PASS** — All 8 scenarios pass with runtime evidence. 110/110 UI controls tested via Playwright headless Chromium.
