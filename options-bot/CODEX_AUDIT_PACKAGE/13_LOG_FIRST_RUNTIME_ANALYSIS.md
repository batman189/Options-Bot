# 13 — LOG-FIRST RUNTIME ANALYSIS (Phase 3)

## Approach
Static log-path audit from source (`logger.info/warning/error`) in backend runtime-critical paths.

## High-value log emitters
- `backend/app.py` logs startup/shutdown, orphan model cleanup, backtest lifecycle and parse failures.
- `backend/routes/trading.py` logs process start/stop/restart, watchdog crashes/restarts, restore outcomes.
- `backend/routes/system.py` logs status endpoint checks and warning-level failures in subsystems.
- `backend/database.py` logs schema init, migration actions, missing table detection.

## Reliability observations
1. Some failures are **logged but execution continues** with degraded/default response fields (notably `/api/system/status`).
2. Several migration and file-read branches use broad exception handling with minimal differentiation.
3. Process watchdog emits operational logs but does not expose full historical crash timeline via API.

## Evidence limitation
No fresh runtime log capture was generated in this phase; this document reflects source-level log-path analysis only.

## Phase 4 training-log path additions
- Training jobs install DB-backed log handler (`training_logs`) before job execution and remove it on completion/failure.
- Trainer modules emit explicit step checkpoints (`STEP 1..N`) enabling sample-transition reconstruction from logs when runtime evidence is captured.
- In this phase run, Codex did not execute fresh training jobs, so no new runtime log rows were generated.
