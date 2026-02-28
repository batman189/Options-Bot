# Full Codebase Audit Prompt

Copy everything below the line into a new AI session with full codebase access.

---

You are performing a **complete, exhaustive codebase audit** of an ML-driven options trading bot. Your job is to trace every single item in the codebase and verify it is correct. You are NOT allowed to:

- Assume anything works because it "looks right"
- Skip a file, function, import, or route because it "seems standard"
- Say "this appears correct" without showing the specific lines you verified
- Summarize or gloss over any section
- Trust that any prior developer (human or AI) got anything right

You ARE required to:

- Read every single file completely (not just the first 50 lines)
- Trace every import to its source and confirm the imported name exists
- Trace every function call to its definition and confirm the signature matches
- Trace every API route to its handler and confirm request/response schemas match
- Trace every UI button/action to the API call it makes and confirm the endpoint exists and accepts those parameters
- Trace every database query and confirm the table/column names match the schema
- Run `npx tsc --noEmit` for frontend and verify Python imports for backend after any fixes
- Report bugs with exact file paths, line numbers, the buggy code, and the fix

## Project Structure

```
options-bot/
├── backend/
│   ├── database.py          # SQLite schema, init_db(), get_db()
│   ├── db_log_handler.py    # DatabaseLogHandler, TrainingLogHandler
│   ├── schemas.py           # Pydantic response models
│   └── routes/
│       ├── profiles.py      # CRUD for trading profiles
│       ├── models.py        # Training jobs, model status, feature importance
│       ├── trades.py        # Trade history, stats
│       ├── system.py        # Health, status, PDT, errors
│       └── backtest.py      # Backtesting endpoints
├── ml/
│   ├── predictor.py         # Abstract ModelPredictor base class
│   ├── xgboost_predictor.py # XGBoostPredictor implementation
│   ├── tft_predictor.py     # TFTPredictor implementation
│   ├── ensemble_predictor.py# EnsemblePredictor (stacking meta-learner)
│   ├── trainer.py           # XGBoost training pipeline
│   ├── tft_trainer.py       # TFT training pipeline
│   ├── incremental_trainer.py # XGBoost warm-start retraining
│   ├── ev_filter.py         # Expected value options chain scanner
│   └── feature_engineering/
│       ├── base_features.py    # Core features (RSI, MACD, BB, etc.)
│       ├── swing_features.py   # Swing-specific features
│       └── general_features.py # General/scalp features
├── data/
│   ├── alpaca_fetcher.py    # Historical bar data from Alpaca
│   ├── options_data_fetcher.py # Options chain from ThetaData
│   └── greeks_calculator.py # Black-Scholes Greeks
├── strategies/
│   ├── base_strategy.py     # BaseOptionsStrategy (Lumibot Strategy subclass)
│   ├── swing_strategy.py    # SwingStrategy
│   └── general_strategy.py  # GeneralStrategy
├── risk/
│   └── risk_manager.py      # PDT, position sizing, exposure, trade logging
├── config.py                # All configuration constants
├── main.py                  # FastAPI app, Lumibot launcher
└── ui/
    └── src/
        ├── api/client.ts    # API client (all fetch calls)
        ├── types/api.ts     # TypeScript interfaces
        ├── pages/
        │   ├── Dashboard.tsx
        │   ├── Profiles.tsx
        │   ├── ProfileDetail.tsx
        │   ├── Trades.tsx
        │   └── System.tsx
        └── components/       # Shared UI components
```

## Audit Phases

Execute these phases IN ORDER. Do not skip ahead. Complete each phase fully before moving to the next. For each phase, output a structured report.

---

### PHASE 1: Database Schema Trace

1. Read `backend/database.py` completely.
2. Extract every `CREATE TABLE` statement. List every table and every column with its type and constraints.
3. For every `ALTER TABLE` migration, confirm it has a try/except guard for "column already exists".
4. This becomes your **ground truth schema**. Every SQL query in the entire codebase must match this schema exactly.

**Output format:**
```
TABLE: profiles
  id TEXT PRIMARY KEY
  name TEXT NOT NULL
  symbol TEXT NOT NULL
  ...
```

---

### PHASE 2: Config Trace

1. Read `config.py` completely.
2. List every exported constant/variable with its type and default value.
3. For every constant, search the entire codebase for where it is imported. Confirm the import path and variable name match exactly.
4. Flag any constant that is defined but never imported anywhere.
5. Flag any import of a config value that does not exist in config.py.

**Output format:**
```
CONSTANT: DB_PATH (Path) = Path("options-bot/data/options_bot.db")
  Imported by: backend/database.py:5, risk/risk_manager.py:23, ml/trainer.py:31

CONSTANT: ALPACA_PAPER (bool) = env-based
  Imported by: main.py:228, backend/routes/system.py (via _check_alpaca)
```

---

### PHASE 3: Backend Schema Trace (Pydantic ↔ DB ↔ TypeScript)

1. Read `backend/schemas.py` completely. List every Pydantic model and every field with type.
2. For each Pydantic model, identify which route returns it (check `response_model=` in route decorators).
3. For each field in each Pydantic model, trace where the value comes from:
   - If from a DB query: confirm the column exists in the schema from Phase 1.
   - If computed: confirm the computation is correct.
4. Read `ui/src/types/api.ts` completely. List every TypeScript interface and every field with type.
5. For every Pydantic model that has a corresponding TypeScript interface, confirm field-by-field that names and types match.
6. Flag any field present in Pydantic but missing in TypeScript (or vice versa).
7. Flag any field type mismatch (e.g., Pydantic `float` but TypeScript `string`).

**Output format:**
```
SCHEMA: ProfileResponse (backend/schemas.py:45)
  ROUTE: GET /api/profiles/{id} (profiles.py:78)
  TYPESCRIPT: Profile (api.ts:23)

  Field: id (str) → DB: profiles.id (TEXT) → TS: id (string) ✓
  Field: status (str) → DB: profiles.status (TEXT) → TS: status (string) ✓
  Field: model_summary (ModelSummary | None) → COMPUTED → TS: model_summary?: ModelSummary ✓
  Field: trained_models (list[ModelSummary]) → COMPUTED → TS: trained_models (ModelSummary[]) ✓
  MISSING IN TS: [none]
  MISSING IN PYDANTIC: [none]
```

---

### PHASE 4: API Route Trace (Backend)

For EVERY route in EVERY router file (`profiles.py`, `models.py`, `trades.py`, `system.py`, `backtest.py`):

1. List the HTTP method, path, request parameters (path params, query params, request body), and response model.
2. Read the full handler function.
3. For every DB query in the handler:
   - Confirm table name exists (Phase 1).
   - Confirm every column name exists (Phase 1).
   - Confirm parameter count matches `?` placeholder count.
   - Confirm the query result is unpacked correctly (column order matches SELECT order).
4. For every function called from the handler, trace to its definition and confirm:
   - The function exists at the import path.
   - The argument count and types match.
   - The return type matches how the result is used.
5. For every Pydantic model constructed in the response, confirm all required fields are provided.
6. Check for common bugs:
   - `await` missing on async calls
   - Blocking sync calls in async handlers (requests.get, time.sleep, etc.)
   - Missing error handling on external API calls
   - SQL injection (string formatting instead of parameterized queries)

**Output format:**
```
ROUTE: POST /api/models/{profile_id}/train (models.py:120)
  Path params: profile_id (str)
  Body: { model_type: str }
  Response: TrainingStatus

  DB QUERIES:
    Line 135: SELECT * FROM profiles WHERE id = ? → profiles table ✓, 1 param ✓
    Line 142: UPDATE profiles SET status = 'training' WHERE id = ? → ✓

  FUNCTION CALLS:
    Line 150: _full_train_job(profile_id, ...) → defined at models.py:200 ✓
      - Runs in: threading.Thread ✓
      - Args match: ✓

  BUGS FOUND: [none]
```

---

### PHASE 5: API Client Trace (Frontend → Backend)

1. Read `ui/src/api/client.ts` completely.
2. For every API function defined:
   - Confirm the URL path matches an actual backend route (Phase 4).
   - Confirm the HTTP method matches.
   - Confirm the request body shape matches what the backend expects.
   - Confirm the response type matches the Pydantic response model.
3. Search all `.tsx` files for every usage of `api.*` calls.
4. For each call site, confirm:
   - Arguments passed match the client function signature.
   - The response data is used correctly (accessing fields that exist on the response type).
   - Error states are handled (loading, error, empty).

**Output format:**
```
CLIENT FN: api.models.train(profileId, modelType?)
  URL: POST /api/models/${profileId}/train
  Body: { model_type: modelType ?? 'xgboost' }
  Response type: TrainingStatus
  Backend route: POST /api/models/{profile_id}/train (models.py:120) ✓
  Method match: ✓
  Body match: ✓

  CALL SITES:
    ProfileDetail.tsx:171 → api.models.train(id!, trainModelType) ✓
    Profiles.tsx:256 → api.models.train(id) → defaults to 'xgboost' ⚠️ (no model type selector)
```

---

### PHASE 6: UI Component Trace

For every page component (`Dashboard.tsx`, `Profiles.tsx`, `ProfileDetail.tsx`, `Trades.tsx`, `System.tsx`):

1. List every `useQuery` and `useMutation` hook. For each:
   - Confirm the query key is unique and consistent.
   - Confirm the query function calls the correct API client method.
   - Confirm `enabled` conditions are correct (not too permissive or restrictive).
   - Confirm `onSuccess`/`onError` callbacks invalidate the right query keys.
2. List every user-interactive element (buttons, forms, dropdowns, links). For each:
   - Trace the click handler to the mutation or navigation it triggers.
   - Confirm the mutation sends the correct data.
   - Confirm loading/disabled states are shown during mutations.
3. List every piece of data displayed. For each:
   - Trace back to the query that fetches it.
   - Confirm the field name matches the TypeScript type.
   - Confirm null/undefined fallbacks exist for optional fields (use `?? defaultValue`).
4. Check for common React bugs:
   - Missing `key` props on mapped elements
   - Stale closures in callbacks
   - Infinite re-render loops
   - Missing dependency array items in useEffect

---

### PHASE 7: ML Pipeline Trace

For each ML file (`trainer.py`, `tft_trainer.py`, `incremental_trainer.py`, `ensemble_predictor.py`):

1. Read the entire file.
2. For the main training function, trace every step:
   - Data fetching: confirm the function exists and returns the expected shape.
   - Feature computation: confirm feature function exists and column names match.
   - Target calculation: confirm the formula is mathematically correct.
   - Model training: confirm hyperparameters are valid for the model type.
   - Cross-validation: confirm fold logic doesn't leak future data.
   - DB save: confirm the SQL matches the schema, and all fields are populated.
3. For `asyncio.run()` calls: confirm there is a fallback for "already running event loop" (background thread scenario).
4. For predictor classes (`xgboost_predictor.py`, `tft_predictor.py`, `ensemble_predictor.py`):
   - Trace `predict()`: confirm feature ordering matches training.
   - Trace `load()`/`save()`: confirm serialization format matches.
   - Trace `predict_batch()`: confirm index alignment.

---

### PHASE 8: Strategy + Risk Trace

1. Read `base_strategy.py` completely. For every method:
   - Trace calls to Lumibot API methods. Confirm each method exists on `Strategy` base class. Check the Lumibot docs/source if uncertain — do NOT assume.
   - Trace calls to `risk_manager`. Confirm method signatures match.
   - Trace calls to `predictor.predict()`. Confirm argument shape matches predictor interface.
   - Confirm exit logic P&L calculations are mathematically correct for both long and short positions.
2. Read `risk_manager.py` completely. For every method:
   - Trace DB queries. Confirm they match the schema.
   - Confirm `_run_async()` results are guarded against `None` returns.
   - Confirm position sizing math is correct (no off-by-one, no impossible values).
3. Read `ev_filter.py` completely:
   - Verify the EV formula: `expected_gain` is the option price INCREASE (not total value). Premium is the entry cost. Theta cost is time decay. EV% = (gain - theta_cost) / premium * 100. Confirm this is what the code does.
   - Verify that option chain data structures match what `options_data_fetcher.py` returns.

---

### PHASE 9: Data Provider Trace

1. Read `alpaca_fetcher.py` completely:
   - Confirm API endpoints and parameters match Alpaca's API.
   - Confirm timezone handling (market hours, UTC vs Eastern).
   - Confirm the returned DataFrame has the expected columns.
2. Read `options_data_fetcher.py` completely:
   - Confirm ThetaData API endpoints and parameters.
   - Confirm the returned data structure matches what `ev_filter.py` and `base_features.py` expect.
3. Read `greeks_calculator.py` completely:
   - Verify Black-Scholes formulas against standard references.
   - Confirm compute_greeks_vectorized matches compute_greeks for the same inputs.
   - Confirm feature names returned by `get_second_order_feature_names()` match what `base_features.py` adds to the DataFrame.

---

### PHASE 10: Cross-Cutting Verification

After all phases are complete, verify these cross-cutting concerns:

1. **Import chain completeness**: For every file, confirm every `from X import Y` resolves. Run `python -c "from <module> import <name>"` mentally for each.
2. **Feature name consistency**: The feature names used during training (from `feature_engineering/*.py`) must exactly match the feature names the predictor expects at inference time. Trace: feature_engineering output columns → trainer stores feature_names → predictor.load() reads feature_names → predictor.predict() uses feature_names → strategy passes features dict. Any mismatch = silent NaN predictions.
3. **Type consistency end-to-end**: Pick 5 data values that flow from DB → backend → API → frontend → display. Trace the type at each stage. Example: `profile.status` (TEXT in DB → str in Python → str in JSON → string in TypeScript → rendered in JSX).
4. **Null safety**: For every optional/nullable field, confirm both backend and frontend handle the null case. Backend: `if row[0] else default`. Frontend: `value ?? fallback`.
5. **Concurrent safety**: Training jobs run in background threads. Confirm no shared mutable state is modified without locks. Confirm DB writes from threads use their own connections (not shared).

---

## Output Requirements

After completing all 10 phases, produce a final summary:

```
## BUGS FOUND

### CRITICAL (will crash at runtime)
1. [file:line] Description — current code — fix

### HIGH (wrong behavior, data corruption, or silent failures)
1. [file:line] Description — current code — fix

### MEDIUM (degraded UX, performance issues, edge cases)
1. [file:line] Description — current code — fix

### LOW (style, naming, minor inconsistencies)
1. [file:line] Description

## VERIFIED CLEAN
List every file you read and confirmed has zero bugs.
```

**CRITICAL RULE**: If you find yourself writing "this looks correct" or "this should work" without having traced the SPECIFIC line numbers and cross-referenced them against the source of truth (schema, config, API spec), STOP. Go back and do the actual trace. The entire point of this audit is to eliminate "should" and replace it with "does, and here's the proof."

**CRITICAL RULE**: You must read EVERY line of EVERY file listed in the project structure above. If a file has 500 lines, you read all 500. If you hit a context limit, say so and resume from where you left off. Do NOT summarize or skip sections.

**CRITICAL RULE**: When you report a file as "verified clean", you are staking your credibility on it. If a bug is later found in a file you marked clean, it means you failed the audit. Act accordingly.
