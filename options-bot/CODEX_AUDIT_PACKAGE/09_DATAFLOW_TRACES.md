# 09 — DATAFLOW TRACES (Phase 2)

## Trace A — Profile activation from UI
1. User clicks Activate in Dashboard/Profiles/ProfileDetail.
2. Button handler triggers `api.profiles.activate(id)`.
3. API client sends `POST /api/profiles/{profile_id}/activate`.
4. Backend route `activate_profile` updates DB status.
5. Frontend mutation invalidates profile queries; new status re-renders badges/buttons.

## Trace B — Train model from profile detail
1. User clicks Train.
2. `trainMutation` calls `api.models.train(id, modelType)` with JSON `{ model_type }`.
3. API client sends `POST /api/models/{profile_id}/train`.
4. Backend enqueues/starts training and returns `TrainingStatus`.
5. UI polls status/logs and updates training panel and logs section.

## Trace C — Signal logs (all profiles)
1. Signal Logs page loads profiles via `api.profiles.list`.
2. If no specific profile selected, page calls `api.signals.list(profileId)` for each profile (Promise.all).
3. Results are flattened, sorted, sliced to latest 500.
4. Client-side filters/sort determine visible rows.

## Trace D — Backtest run + polling
1. User enters Start/End date and clicks Run on ProfileDetail.
2. `api.backtest.run` sends `POST /api/backtest/{id}`.
3. Backend starts thread and returns `status=running`.
4. UI poll (`api.backtest.results`) updates progress/result cards.

## Proven vs not proven
- Proven from source: handler and route wiring above.
- Not proven in Phase 2: runtime success of each call in this environment (no live execution performed in this phase).

## Trace E — Trading watchdog crash path
1. Watchdog snapshots `_processes` registry.
2. Dead/crashed process detected (`poll()` or PID liveness check).
3. Entry removed from in-memory registry and `system_state` process key removed.
4. Profile status updated in DB (`paused`/`error` depending on branch).
5. Optional auto-restart attempted when enabled by config.

## Trace F — `/api/system/status` degraded path
1. Endpoint initializes defaults for connectivity and counts.
2. DB/provider checks run; failures append messages into `check_errors`.
3. Response still returns 200 with fallback/default field values + collected `check_errors` context.

## Trace G — Training request to persisted artifact
1. UI triggers train endpoint with optional `model_type` / `years_of_data`.
2. Backend validates profile/model-type/theta and acquires `_active_jobs` slot.
3. Background trainer executes feature + target + CV + final fit pipeline.
4. Trainer saves model artifact (file or directory) and writes model metrics row to DB.
5. Profile status/model pointer updated; `_active_jobs` slot released in `finally`.

## Trace H — Model discovery and inference consumption
1. Strategy loads profile params including `model_path`.
2. `_detect_model_type()` reads current `models.model_type` via profile model pointer.
3. Strategy instantiates predictor class for detected type (or xgboost fallback path on errors).
4. Per iteration, predictor returns a single float value.
5. Strategy interprets value as either return magnitude (regressor) or signed confidence (classifier), then applies confidence/EV gates and logs to DB.
