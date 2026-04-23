# 20 — STARTUP / SHUTDOWN / LIVE LOOP AUDIT (Phase 3)

## Backend startup sequence (`backend/app.py` lifespan)
1. `init_db()` called.
2. Trading process registry restore from `system_state` (`restore_process_registry`).
3. Cleanup pass: profiles marked `active` without running process reset to `ready`.
4. Orphaned model-file records marked `orphaned`.
5. Trading watchdog thread started.

## Backend shutdown sequence
1. Watchdog stop event set.
2. FastAPI shutdown log emitted.

## Trading live-loop/process management (`backend/routes/trading.py`)
- In-memory `_processes` registry holds process metadata.
- Watchdog periodic cycle checks liveness, classifies crashed/stopped, updates profile DB status, optionally restarts.
- `start/stop/restart` endpoints mutate both process registry and DB status.

## Main entrypoint loop (`main.py`)
- Supports backend-only mode and trade mode.
- Installs signal handlers for graceful shutdown.
- Can launch backend in thread and trading loop(s) in same process depending on flags.

## Phase 3 judgment
- Startup/shutdown orchestration exists and is explicit.
- Runtime truth is eventually consistent across process registry / `system_state` / DB profile status; clients should not assume atomicity during transitions.
