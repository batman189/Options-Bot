# Phase 1+3 Config/Env Audit (Independent)

## Discovered runtime-affecting config/env tokens (baseline)

(Phase 1 token inventory retained; Phase 3 additions focus on backend branching)

## Phase 3 config-driven backend branches
- `WATCHDOG_POLL_INTERVAL_SECONDS` / `WATCHDOG_AUTO_RESTART` influence trading watchdog cadence and auto-restart behavior (`backend/routes/trading.py`, `config.py`).
- `DB_PATH` controls sqlite location for app lifespan init, route dependencies, and process-state persistence.
- `MODEL_STALE_THRESHOLD_DAYS` drives `/api/system/model-health` stale-status overrides.
- `TRAINING_QUEUE_MIN_SAMPLES` drives `/api/system/training-queue` readiness gate.
- Alpaca/Theta config values affect `/api/system/status` connectivity checks and can force default/degraded responses on failures.

## Config risk note
Frontend `Dashboard` hardcodes `MAX_TOTAL_POSITIONS = 10` with comment indicating backend coupling; this can drift if backend config changes.
