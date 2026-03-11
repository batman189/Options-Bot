# 17. Frontend-Backend Bindings Audit

## API Client Bindings (ui/src/api/client.ts)

Every frontend API call mapped to its backend endpoint:

| ID | Frontend Call | Method | Backend Endpoint | Backend Handler | Schema Match | Verdict |
|----|-------------|--------|-----------------|-----------------|-------------|---------|
| FB-001 | api.profiles.list() | GET | /api/profiles | profiles.list_profiles | Profile[] ↔ list[ProfileResponse] | PASS |
| FB-002 | api.profiles.get(id) | GET | /api/profiles/{id} | profiles.get_profile | Profile ↔ ProfileResponse | PASS |
| FB-003 | api.profiles.create(body) | POST | /api/profiles | profiles.create_profile | ProfileCreate ↔ ProfileCreate | PASS |
| FB-004 | api.profiles.update(id, body) | PUT | /api/profiles/{id} | profiles.update_profile | ProfileUpdate ↔ ProfileUpdate | PASS |
| FB-005 | api.profiles.delete(id) | DELETE | /api/profiles/{id} | profiles.delete_profile | void ↔ 204 | PASS |
| FB-006 | api.profiles.activate(id) | POST | /api/profiles/{id}/activate | profiles.activate_profile | Profile ↔ ProfileResponse | PASS |
| FB-007 | api.profiles.pause(id) | POST | /api/profiles/{id}/pause | profiles.pause_profile | Profile ↔ ProfileResponse | PASS |
| FB-008 | api.models.train(id, type) | POST | /api/models/{id}/train | models.train_model_endpoint | TrainingStatus ↔ TrainingStatus | PASS |
| FB-009 | api.models.retrain(id) | POST | /api/models/{id}/retrain | models.retrain_model | TrainingStatus ↔ TrainingStatus | PASS |
| FB-010 | api.models.status(id) | GET | /api/models/{id}/status | models.get_training_status | TrainingStatus ↔ TrainingStatus | PASS |
| FB-011 | api.models.logs(id, limit) | GET | /api/models/{id}/logs | models.get_training_logs | TrainingLogEntry[] ↔ list[TrainingLogEntry] | PASS |
| FB-012 | api.models.clearLogs(id) | DELETE | /api/models/{id}/logs | models.clear_training_logs | {status:string} ↔ dict | PASS |
| FB-013 | api.models.importance(id) | GET | /api/models/{id}/importance | models.get_feature_importance | FeatureImportanceResponse ↔ dict | PASS |
| FB-014 | api.trades.list(params) | GET | /api/trades | trades.list_trades | Trade[] ↔ list[TradeResponse] | PASS |
| FB-015 | api.trades.active() | GET | /api/trades/active | trades.list_active_trades | Trade[] ↔ list[TradeResponse] | PASS |
| FB-016 | api.trades.stats(id?) | GET | /api/trades/stats | trades.get_trade_stats | TradeStats ↔ TradeStats | PASS |
| FB-017 | api.trades.exportUrl(id?) | GET | /api/trades/export | trades.export_trades | File download ↔ StreamingResponse | PASS |
| FB-018 | api.system.health() | GET | /api/system/health | system.health_check | HealthCheck ↔ HealthCheck | PASS |
| FB-019 | api.system.status() | GET | /api/system/status | system.get_system_status | SystemStatus ↔ SystemStatus | PASS |
| FB-020 | api.system.pdt() | GET | /api/system/pdt | system.get_pdt_status | PDTStatus ↔ PDTStatus | PASS |
| FB-021 | api.system.errors(limit) | GET | /api/system/errors | system.get_recent_errors | ErrorLogEntry[] ↔ list[ErrorLogEntry] | PASS |
| FB-022 | api.system.clearErrors() | DELETE | /api/system/errors | system.clear_error_logs | {status:string} ↔ dict | PASS |
| FB-023 | api.system.modelHealth() | GET | /api/system/model-health | system.get_model_health | ModelHealthResponse ↔ ModelHealthResponse | PASS |
| FB-024 | api.system.trainingQueue() | GET | /api/system/training-queue | system.get_training_queue_status | TrainingQueueStatus ↔ TrainingQueueStatus | PASS |
| FB-025 | api.backtest.run(id, body) | POST | /api/backtest/{id} | app.run_backtest_endpoint | BacktestResult ↔ BacktestResult | PASS |
| FB-026 | api.backtest.results(id) | GET | /api/backtest/{id}/results | app.get_backtest_results | BacktestResult ↔ BacktestResult | PASS |
| FB-027 | api.trading.status() | GET | /api/trading/status | trading.get_trading_status | TradingStatusResponse ↔ TradingStatusResponse | PASS |
| FB-028 | api.trading.start(ids) | POST | /api/trading/start | trading.start_trading | TradingStartResponse ↔ TradingStartResponse | PASS |
| FB-029 | api.trading.stop(ids?) | POST | /api/trading/stop | trading.stop_trading | TradingStopResponse ↔ TradingStopResponse | PASS |
| FB-030 | api.trading.restart(ids) | POST | /api/trading/restart | trading.restart_trading | TradingStartResponse ↔ TradingStartResponse | PASS |
| FB-031 | api.trading.startableProfiles() | GET | /api/trading/startable-profiles | trading.get_startable_profiles | StartableProfile[] ↔ list[dict] | PASS |
| FB-032 | api.signals.list(id, limit, since) | GET | /api/signals/{id} | signals.get_signal_logs | SignalLogEntry[] ↔ list[SignalLogEntry] | PASS |
| FB-033 | api.signals.exportUrl(id?) | GET | /api/signals/export | signals.export_signal_logs | File download ↔ StreamingResponse | PASS |

## Type Schema Audit (ui/src/types/api.ts ↔ backend/schemas.py)

### Field-by-Field Comparison

| Schema | Frontend Type | Backend Schema | Fields Match | Missing in FE | Missing in BE | Verdict |
|--------|-------------|---------------|-------------|---------------|---------------|---------|
| Profile | Profile | ProfileResponse | YES | — | — | PASS |
| ModelSummary | ModelSummary | ModelSummary | YES | — | — | PASS |
| TrainingStatus | TrainingStatus | TrainingStatus | YES | — | — | PASS |
| TrainingLogEntry | TrainingLogEntry | TrainingLogEntry | YES | — | — | PASS |
| Trade | Trade | TradeResponse | YES | — | — | PASS |
| TradeStats | TradeStats | TradeStats | YES | — | — | PASS |
| SystemStatus | SystemStatus | SystemStatus | YES | — | — | PASS |
| HealthCheck | HealthCheck | HealthCheck | YES | — | — | PASS |
| PDTStatus | PDTStatus | PDTStatus | YES | — | — | PASS |
| ErrorLogEntry | ErrorLogEntry | ErrorLogEntry | YES | — | — | PASS |
| BacktestResult | BacktestResult | BacktestResult | YES | — | — | PASS |
| TradingProcessInfo | TradingProcessInfo | TradingProcessInfo | YES | — | — | PASS |
| TradingStatusResponse | TradingStatusResponse | TradingStatusResponse | YES | — | — | PASS |
| TradingStartResponse | TradingStartResponse | TradingStartResponse | YES | — | — | PASS |
| TradingStopResponse | TradingStopResponse | TradingStopResponse | YES | — | — | PASS |
| ModelHealthEntry | ModelHealthEntry | ModelHealthEntry | YES | — | — | PASS |
| ModelHealthResponse | ModelHealthResponse | ModelHealthResponse | YES | — | — | PASS |
| SignalLogEntry | SignalLogEntry | SignalLogEntry | YES | — | — | PASS |
| TrainingQueueStatus | TrainingQueueStatus | TrainingQueueStatus | YES | — | — | PASS |

### Additional FE-only types (no backend schema):
- `CircuitBreakerState` — used within SystemStatus.circuit_breaker_states, backend sends dict
- `StartableProfile` — backend returns untyped list[dict], FE defines typed interface
- `FeatureImportanceResponse` — backend returns untyped dict, FE defines typed interface
- `ProfileCreate`, `ProfileUpdate`, `BacktestRequest` — request body types, match backend Pydantic models

## React Router ↔ Backend SPA Serving

| Route | Page Component | Backend Handling |
|-------|---------------|------------------|
| / | Dashboard | serve_spa() → index.html |
| /profiles | Profiles | serve_spa() → index.html |
| /profiles/:id | ProfileDetail | serve_spa() → index.html |
| /trades | Trades | serve_spa() → index.html |
| /signals | SignalLogs | serve_spa() → index.html |
| /system | System | serve_spa() → index.html |
| /* | 404 (inline) | serve_spa() → index.html |

**SPA Fallback**: app.py:430 `serve_spa()` returns index.html for all non-API, non-static routes. React Router handles client-side routing.

## Polling Intervals

| Page | Query Key | Interval | Evidence |
|------|-----------|----------|----------|
| Dashboard | profiles | 30s | Dashboard.tsx:361 |
| Dashboard | system-status | 30s | Dashboard.tsx:367 |
| Dashboard | pdt | 30s | Dashboard.tsx:373 |
| Dashboard | trade-stats | 30s | Dashboard.tsx:380 |
| Dashboard | model-health | 30s | Dashboard.tsx:386 |
| Dashboard | training-queue | 30s | Dashboard.tsx:393 |
| Profiles | profiles | 15s | Profiles.tsx:244 |
| Trades | trades-all | 30s | Trades.tsx:264 |
| ProfileDetail | training-status | 5s (when training) | ProfileDetail.tsx (conditional) |

## Null Safety / Fallback Analysis

All frontend code uses `?? defaultValue` pattern for nullable fields. Evidence:
- `status?.alpaca_connected ?? false` (Dashboard.tsx:226)
- `status?.portfolio_value ?? 0` (Dashboard.tsx:416)
- `tradeStats?.win_rate !== null && tradeStats?.win_rate !== undefined` (Dashboard.tsx:468)
- `trade.pnl_pct` with PnlCell handling null (Trades.tsx:440)
- `profile.model_summary?.metrics?.dir_acc` (Dashboard.tsx:94)

**Verdict**: PASS — consistent null-safe access throughout
