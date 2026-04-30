# 17 — FRONTEND BACKEND BINDINGS (Phase 2 Independent)

- Total API-client bindings reviewed: **30**
- Direct route matches: **28 confirmed**
- URL-builder bindings (export URLs): **2 likely correct but not regex-expanded in auto-parser**

## Key confirmed bindings

| Client call | HTTP | Frontend path pattern | Backend handler | Status |
|---|---|---|---|---|
| `api.profiles.list/get/create/update/delete` | GET/POST/PUT/DELETE | `/api/profiles...` | `list_profiles`, `get_profile`, `create_profile`, `update_profile`, `delete_profile` | confirmed by Codex |
| `api.profiles.activate/pause` | POST | `/api/profiles/{id}/activate|pause` | `activate_profile`, `pause_profile` | confirmed by Codex |
| `api.models.train/retrain/status/logs/clearLogs/importance` | POST/GET/DELETE | `/api/models/{profileId}/...` | matching handlers in `backend/routes/models.py` | confirmed by Codex |
| `api.trades.active` | GET | `/api/trades/active` | `list_active_trades` | confirmed by Codex |
| `api.system.health/status/pdt/errors/clearErrors/modelHealth/trainingQueue` | GET/DELETE | `/api/system/...` | matching handlers in `backend/routes/system.py` | confirmed by Codex |
| `api.backtest.run/results` | POST/GET | `/api/backtest/{profileId}` and `/results` | `run_backtest_endpoint`, `get_backtest_results` | confirmed by Codex |
| `api.trading.status/start/stop/restart/startableProfiles` | GET/POST | `/api/trading/...` | matching handlers in `backend/routes/trading.py` | confirmed by Codex |

## Likely-correct URL builder bindings (not fully normalized by parser)

| Client call | URL builder | Backend route | Status |
|---|---|---|---|
| `api.trades.exportUrl(profileId?)` | ``/api/trades/export${profileId ? `?profile_id=${profileId}` : ''}`` | `GET /api/trades/export` | likely correct but not yet fully proven |
| `api.signals.exportUrl(profileId?)` | ``/api/signals/export${profileId ? `?profile_id=${profileId}` : ''}`` | `GET /api/signals/export` | likely correct but not yet fully proven |

## Contract findings
- No frontend call was found to an obviously missing backend route.
- No backend route mismatch found for method/path among the 28 directly matched client calls.

## Phase 5 consumer binding note
- UI `SignalLogs` and `Trades` consume backend fields (`predicted_return`, `entry_model_type`) but Phase 5 found possible model-type string drift at write time in strategy logging path.
- Contract wiring exists, but semantic consistency of model_type labels is likely-correct/not-fully-proven and tracked in bug ledger.
