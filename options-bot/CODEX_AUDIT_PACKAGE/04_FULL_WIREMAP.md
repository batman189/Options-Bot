# 04 — FULL WIREMAP (Phase 2)

## Scope in this phase
Frontend controls/pages to API client bindings and backend route handlers.

## UI page → API client → backend route map

| UI surface | Frontend handler/query | API client call | HTTP | Backend handler |
|---|---|---|---|---|
| Dashboard refresh | `handleRefresh` invalidates query cache | (react-query refetch) | n/a | n/a |
| Dashboard activate/pause buttons | `activateMutation` / `pauseMutation` | `api.profiles.activate/pause` | POST | `activate_profile` / `pause_profile` |
| Dashboard clear error | `clearErrorsMutation` | `api.system.clearErrors` | DELETE | `clear_errors` |
| Profiles table activate/pause/train/delete | row action callbacks | `api.profiles.activate/pause`, `api.models.train`, `api.profiles.delete` | POST/DELETE | route handlers in `backend/routes/profiles.py` and `models.py` |
| Profile form submit | `handleSubmit` | `api.profiles.create` or `api.profiles.update` | POST/PUT | `create_profile` / `update_profile` |
| Profile detail train/retrain | `trainMutation` / `retrainMutation` | `api.models.train/retrain` | POST | `train_model_endpoint` / `retrain_model` |
| Profile detail backtest run | `backtestMutation` | `api.backtest.run` | POST | `run_backtest_endpoint` |
| Profile detail backtest poll | react-query polling | `api.backtest.results` | GET | `get_backtest_results` |
| Profile detail clear logs | inline click handler | `api.models.clearLogs` | DELETE | `clear_training_logs` |
| System quick start/stop/restart | mutation handlers | `api.trading.start/stop/restart` | POST | `start_trading` / `stop_trading` / `restart_trading` |
| Trades page export | `handleExport` | `api.trades.exportUrl` | GET URL | `export_trades_csv` |
| Signal Logs export | `handleExport` | `api.signals.exportUrl` | GET URL | `export_signal_logs` |

## UI-state effects observed in code
- Query-driven pages (`Dashboard`, `System`, `Trades`, `SignalLogs`, `ProfileDetail`) refresh using react-query invalidation or intervals.
- Mutations generally invalidate related query keys after success.
- Some actions are conditionally visible by profile status (activate/pause/train controls).

## Phase 3 backend route → service/storage expansion

| Route family | Handler layer | Service/helper path | Storage / side-effect |
|---|---|---|---|
| `/api/trading/*` | `backend/routes/trading.py` | subprocess + watchdog helpers (`_watchdog_cycle`, `_restart_profile_process`) | updates `profiles.status`, persists process state in `system_state`, OS process spawn/kill |
| `/api/system/*` | `backend/routes/system.py` | provider checks via thread offload, circuit-state file reads | multi-table reads + external connectivity checks |
| `/api/models/*` | `backend/routes/models.py` | trainer/predictor orchestration paths | writes `models` / `training_logs`, updates profile readiness |
| `/api/backtest/*` | `backend/app.py` backtest router | `_backtest_job` thread + `_store_backtest_result` | `system_state` writes keyed by profile |

## Phase 4 training wire expansion

| API route | Job function | Trainer entrypoint | Artifact output |
|---|---|---|---|
| `POST /api/models/{id}/train` | model-type dispatch in `routes/models.py` | `train_model` / `train_scalp_model` / `train_swing_classifier_model` / `train_lgbm_model` / `train_tft_model` / `train_meta_learner` | model file/dir + DB model row + profile model_id/status |
| `POST /api/models/{id}/retrain` | `_incremental_retrain_job` | `retrain_incremental` | versioned incremental model + DB row + profile update |
| `GET /api/models/{id}/status` | status resolver | DB + active-job set | training/completed/failed status payload |

## Phase 5 inference wire expansion

| Source | Inference step | Consumer |
|---|---|---|
| `profiles.model_id` + `models.model_type` | predictor class selection in strategy initialize | live iteration prediction path |
| `predictor.predict(features, sequence?)` | single numeric output (regression return or signed classifier confidence) | step-6 confidence gate, EV conversion for classifiers, trade entry decision |
| prediction result + selected contract | DB writes via `risk_mgr.log_trade_open` and `signal_logs` writes | UI `Trades` / `SignalLogs` pages |
