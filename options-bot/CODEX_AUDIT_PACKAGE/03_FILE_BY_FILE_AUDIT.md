# 03 — FILE BY FILE AUDIT (Phase 3)

## Backend route files audited

| File | Primary responsibility | Storage touchpoints | Risk notes |
|---|---|---|---|
| `backend/app.py` | FastAPI app wiring, lifespan startup/shutdown, backtest thread orchestration | `profiles`, `models`, `system_state` via sqlite in lifespan/backtest routes | Background thread result persistence uses sync `asyncio.run` wrapper; failures logged but not surfaced to caller. |
| `backend/routes/profiles.py` | Profile CRUD + activate/pause state transitions | `profiles` table reads/updates | Status transitions depend on current DB state; no global transaction across related side effects. |
| `backend/routes/models.py` | Train/retrain/status/metrics/logs/importance | `models`, `profiles`, `training_logs` | Large route file with mixed concerns (training orchestration + DB responses) increases change risk. |
| `backend/routes/trades.py` | Trade list/stats/export/detail | `trades` table | Query/filter behavior mostly DB-driven; CSV export route is GET URL endpoint used directly by UI. |
| `backend/routes/signals.py` | Signal log list + CSV export | `signal_logs` | "All profiles" behavior is in frontend aggregation, not backend endpoint. |
| `backend/routes/system.py` | health/status/pdt/errors/model-health/training-queue | `profiles`, `trades`, `training_logs`, `system_state`, `training_queue` | Multiple checks downgrade to defaults on exceptions and only report in `check_errors`. |
| `backend/routes/trading.py` | subprocess lifecycle API + watchdog + registry restore | `profiles`, `system_state` + subprocess state | Process health model is eventually consistent; DB status may briefly diverge from process truth. |
| `backend/database.py` | schema init + migrations + stale training reset | all core tables | Migration blocks swallow broad exceptions (`except Exception: pass`), potentially hiding non-"already exists" failures. |
| `main.py` | process entrypoint, backend launch option, trading loops | profile/model reads from DB in loader paths | Startup includes signal handling + optional backend thread; operational complexity concentrated here. |

## Dead-route / mismatch scan outcome
- No clearly dead registered API route found in Phase 3 static scan.
- Catch-all SPA route `/{full_path:path}` is conditionally registered only when `ui/dist` exists.
