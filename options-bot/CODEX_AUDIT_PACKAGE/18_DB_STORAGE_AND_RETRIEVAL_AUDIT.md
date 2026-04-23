# 18 — DB STORAGE AND RETRIEVAL AUDIT (Phase 3)

## Storage surface summary
- Core tables defined in `backend/database.py`: `profiles`, `models`, `trades`, `system_state`, `training_logs`, `signal_logs`, `training_queue`.
- Phase 3 SQL inventory generated at `db/phase3_sql_inventory.csv` (96 execute/executescript callsites).

## Route/storage mapping highlights
- Profiles routes: read/write `profiles` status and config fields.
- Models routes: read/write `models`, training log reads/deletes in `training_logs`.
- Trading routes: synchronize subprocess state to `system_state` and profile status in `profiles`.
- System routes: aggregate reads from `profiles`, `trades`, `training_logs`, `training_queue`, and model-health blobs from `system_state`.
- Backtest routes (`backend/app.py`): write/read `system_state` key `backtest_{profile_id}`.

## Risk findings
1. Migration exception swallowing in `database.init_db()` may hide unexpected DB errors.
2. Status APIs may return defaults after query/provider failures, requiring caller to inspect `check_errors` for reliability context.
3. Process state in memory + `system_state` + `profiles.status` can temporarily diverge during crash/restart windows.
