# Full Codebase Audit Prompt (Updated 2026-03-04)

Copy everything below the line into a new AI session with full codebase access.

---

You are performing a **complete, exhaustive codebase audit** of an ML-driven options trading bot. Your deliverable is a **findings document** (`options-bot/docs/AUDIT_FINDINGS.md`) that catalogs every bug, dead code item, deprecation warning, and design concern — organized by severity with a prioritized fix order.

## Ground Rules

You are NOT allowed to:

- Fix anything during the audit. This is a READ-ONLY pass. Findings go in the document.
- Assume anything works because it "looks right"
- Skip a file, function, import, or route because it "seems standard"
- Say "this appears correct" without showing the specific lines you verified
- Summarize or gloss over any section
- Trust that any prior developer (human or AI) got anything right
- Use pattern-based search as a substitute for reading files top-to-bottom
- Mark a file as "verified clean" without having read every line

You ARE required to:

- Read every single file completely (not just the first 50 lines)
- Trace every import to its source and confirm the imported name exists
- Trace every function call to its definition and confirm the signature matches
- Trace every API route to its handler and confirm request/response schemas match
- Trace every UI button/action to the API call it makes and confirm the endpoint exists and accepts those parameters
- Trace every database query and confirm the table/column names match the schema
- Report bugs with exact file paths, line numbers, the buggy code, and why it's wrong
- Write ALL findings to the findings document BEFORE any fixes are attempted

## Technology Stack

- **Backend:** FastAPI + SQLite (aiosqlite for async, sqlite3 for sync paths), Python 3.13
- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + React Query (TanStack)
- **ML:** XGBoost, LightGBM, TFT (PyTorch Forecasting), Optuna, scikit-learn (Ridge meta-learner)
- **Trading:** Lumibot (Strategy base class) + ThetaData (options data) + Alpaca (stock data, broker)
- **Features:** 73 base + 5 swing + 4 general + 10 scalp features
- **Presets:** swing (default, XGBoost/TFT/LightGBM), general (XGBoost/TFT/LightGBM), scalp (XGBClassifier only)

## Complete Project Structure

```
options-bot/
├── main.py                          # FastAPI app init, Lumibot launcher, CORS
├── config.py                        # All configuration constants, preset defaults
├── requirements.txt                 # Python dependencies
│
├── backend/
│   ├── __init__.py
│   ├── app.py                       # FastAPI app factory, lifespan, background tasks
│   ├── database.py                  # SQLite schema (SCHEMA_SQL), init_db(), get_db()
│   ├── schemas.py                   # Pydantic response models
│   ├── db_log_handler.py            # DatabaseLogHandler, TrainingLogHandler
│   └── routes/
│       ├── __init__.py
│       ├── profiles.py              # CRUD for trading profiles
│       ├── models.py                # Training jobs, model status, feature importance
│       ├── trades.py                # Trade history, stats, close trade
│       ├── signals.py               # Signal log queries
│       ├── system.py                # Health, status, PDT, errors, circuit breakers
│       ├── trading.py               # Start/stop trading, graceful shutdown
│       └── backtest.py              # (if exists) Backtesting endpoints
│
├── data/
│   ├── __init__.py
│   ├── provider.py                  # Abstract StockDataProvider base class
│   ├── alpaca_provider.py           # AlpacaStockProvider (bars, circuit breaker)
│   ├── theta_provider.py            # ThetaOptionsProvider (class, mostly unused)
│   ├── vix_provider.py              # VIXProvider + fetch_vix_daily_bars()
│   ├── options_data_fetcher.py      # ThetaData direct HTTP for options chains
│   ├── greeks_calculator.py         # Black-Scholes Greeks (vectorized + scalar)
│   ├── earnings_calendar.py         # Alpaca earnings check (blackout gate)
│   └── validator.py                 # Data validation (currently dead code)
│
├── ml/
│   ├── __init__.py
│   ├── predictor.py                 # Abstract ModelPredictor base class
│   ├── xgboost_predictor.py         # XGBoostPredictor (XGBRegressor)
│   ├── lgbm_predictor.py            # LightGBMPredictor
│   ├── tft_predictor.py             # TFTPredictor (PyTorch Forecasting)
│   ├── scalp_predictor.py           # ScalpPredictor (XGBClassifier)
│   ├── ensemble_predictor.py        # EnsemblePredictor (Ridge stacking meta-learner)
│   ├── trainer.py                   # XGBoost training pipeline (Optuna + CV)
│   ├── lgbm_trainer.py              # LightGBM training pipeline
│   ├── tft_trainer.py               # TFT training pipeline
│   ├── scalp_trainer.py             # Scalp (XGBClassifier) training pipeline
│   ├── incremental_trainer.py       # XGBoost warm-start retraining
│   ├── ev_filter.py                 # Expected value options chain scanner
│   ├── feedback_queue.py            # Training queue: enqueue/consume completed trades
│   ├── liquidity_filter.py          # OI/volume/spread gate for options
│   ├── regime_adjuster.py           # VIX regime confidence scaling
│   └── feature_engineering/
│       ├── __init__.py
│       ├── base_features.py         # 73 core features (RSI, MACD, BB, VIX, etc.)
│       ├── swing_features.py        # 5 swing-specific features
│       ├── general_features.py      # 4 general-specific features
│       └── scalp_features.py        # 10 scalp-specific features
│
├── strategies/
│   ├── __init__.py
│   ├── base_strategy.py             # BaseOptionsStrategy (Lumibot Strategy subclass, ~2000 lines)
│   ├── swing_strategy.py            # SwingStrategy (thin subclass)
│   ├── general_strategy.py          # GeneralStrategy (thin subclass)
│   └── scalp_strategy.py            # ScalpStrategy (thin subclass)
│
├── risk/
│   ├── __init__.py
│   └── risk_manager.py              # PDT, position sizing, exposure, Greeks, trade logging
│
├── utils/
│   ├── __init__.py
│   ├── circuit_breaker.py           # CircuitBreaker class (generic)
│   └── alerter.py                   # Multi-channel alert system
│
├── scripts/
│   ├── backtest.py                  # CLI backtest runner
│   ├── train_model.py               # CLI model training
│   ├── walk_forward_backtest.py     # Walk-forward validation orchestrator
│   ├── diagnose_strategy.py         # Strategy diagnostic tool
│   ├── validate_data.py             # Data validation script
│   ├── validate_model.py            # Model validation script
│   ├── test_features.py             # Feature computation test
│   ├── test_providers.py            # Data provider test
│   ├── startup_check.py             # Pre-launch system check
│   └── audit_verify.py              # Audit verification helper
│
└── ui/
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── tailwind.config.js
    └── src/
        ├── main.tsx                 # React entry point
        ├── App.tsx                  # Router setup
        ├── api/
        │   └── client.ts           # API client (all fetch calls)
        ├── types/
        │   └── api.ts              # TypeScript interfaces
        ├── components/
        │   ├── Layout.tsx           # App shell, sidebar navigation
        │   ├── StatusBadge.tsx      # Status indicator component
        │   ├── Spinner.tsx          # Loading spinner
        │   ├── PnlCell.tsx          # P&L display with color coding
        │   ├── ConnIndicator.tsx    # Connection status indicator
        │   ├── PageHeader.tsx       # Page header component
        │   └── ProfileForm.tsx      # Profile create/edit form
        └── pages/
            ├── Dashboard.tsx        # Overview, system health, stats
            ├── Profiles.tsx         # Profile list
            ├── ProfileDetail.tsx    # Single profile view, training, backtesting
            ├── Trades.tsx           # Trade history table
            ├── SignalLogs.tsx       # Signal pipeline step logs
            └── System.tsx           # System status, circuit breakers, alerts
```

**Total: 56 Python files + 15 TypeScript/TSX files = 71 managed code files**

---

## Audit Phases

Execute these phases IN ORDER. Do not skip ahead. Complete each phase fully before moving to the next. Write findings to `options-bot/docs/AUDIT_FINDINGS.md` as you go.

---

### PHASE 1: Database Schema Trace

1. Read `backend/database.py` completely.
2. Extract every `CREATE TABLE` statement. List every table and every column with its type and constraints.
3. For every `ALTER TABLE` migration, confirm it has a try/except guard for "column already exists."
4. This becomes your **ground truth schema**. Every SQL query in the entire codebase must match this schema exactly.

---

### PHASE 2: Config Trace

1. Read `config.py` completely.
2. List every exported constant/variable with its type and default value.
3. For every constant, search the entire codebase for where it is imported. Confirm the import path and variable name match exactly.
4. Flag any constant that is defined but never imported anywhere.
5. Flag any import of a config value that does not exist in config.py.

---

### PHASE 3: Backend Schema Trace (Pydantic <-> DB <-> TypeScript)

1. Read `backend/schemas.py` completely. List every Pydantic model and every field with type.
2. For each Pydantic model, identify which route returns it (check `response_model=` in route decorators).
3. For each field in each Pydantic model, trace where the value comes from:
   - If from a DB query: confirm the column exists in the schema from Phase 1.
   - If computed: confirm the computation is correct.
4. Read `ui/src/types/api.ts` completely. List every TypeScript interface and every field with type.
5. For every Pydantic model that has a corresponding TypeScript interface, confirm field-by-field that names and types match.
6. Flag any field present in Pydantic but missing in TypeScript (or vice versa).
7. Flag any field type mismatch (e.g., Pydantic `float` but TypeScript `string`).

---

### PHASE 4: API Route Trace (Backend)

For EVERY route in EVERY router file (`profiles.py`, `models.py`, `trades.py`, `signals.py`, `system.py`, `trading.py`):

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

---

### PHASE 5: API Client Trace (Frontend -> Backend)

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

---

### PHASE 6: UI Component Trace

For every page component (`Dashboard.tsx`, `Profiles.tsx`, `ProfileDetail.tsx`, `Trades.tsx`, `SignalLogs.tsx`, `System.tsx`):

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

For each ML training file (`trainer.py`, `lgbm_trainer.py`, `tft_trainer.py`, `scalp_trainer.py`, `incremental_trainer.py`):

1. Read the entire file.
2. For the main training function, trace every step:
   - Data fetching: confirm the function exists and returns the expected shape.
   - Feature computation: confirm feature function exists and column names match.
   - Target calculation: confirm the formula is mathematically correct.
   - Model training: confirm hyperparameters are valid for the model type and library version.
   - Cross-validation: confirm fold logic doesn't leak future data.
   - DB save: confirm the SQL matches the schema, and all fields are populated.
3. For `asyncio.run()` calls: confirm there is a fallback for "already running event loop" (background thread scenario).

For each predictor class (`xgboost_predictor.py`, `lgbm_predictor.py`, `tft_predictor.py`, `scalp_predictor.py`, `ensemble_predictor.py`):

4. Trace `predict()`: confirm feature ordering matches training.
5. Trace `load()`/`save()`: confirm serialization format matches.
6. Confirm the predictor interface matches `predictor.py` abstract base class.

For each filter/adjuster (`ev_filter.py`, `liquidity_filter.py`, `regime_adjuster.py`, `feedback_queue.py`):

7. Read the entire file.
8. Verify formulas are mathematically correct (EV calculation, spread adjustment, regime scaling).
9. Confirm data structures match what callers pass in.

---

### PHASE 8: Strategy + Risk Trace

1. Read `base_strategy.py` completely (~2000 lines). For every method:
   - Trace calls to Lumibot API methods. Confirm each method exists on `Strategy` base class.
   - Trace calls to `risk_manager`. Confirm method signatures match.
   - Trace calls to `predictor.predict()`. Confirm argument shape matches predictor interface.
   - Confirm exit logic P&L calculations are mathematically correct for both long and short positions.
   - Confirm the signal pipeline steps execute in documented order with correct gate logic.
   - Verify error handling: auto-pause counter, circuit breaker integration, timing instrumentation.
2. Read `risk_manager.py` completely. For every method:
   - Trace DB queries. Confirm they match the schema.
   - Confirm `_run_async()` results are guarded against `None` returns.
   - Confirm position sizing math is correct (no off-by-one, no impossible values).
   - Verify portfolio Greeks calculations if present.
3. Read each strategy subclass (`swing_strategy.py`, `general_strategy.py`, `scalp_strategy.py`):
   - Confirm they correctly inherit from `BaseOptionsStrategy`.
   - Verify any overrides are compatible with the base class interface.

---

### PHASE 9: Data Provider Trace

1. Read `alpaca_provider.py` completely:
   - Confirm API call patterns match Alpaca's API.
   - Confirm circuit breaker integration.
   - Confirm the returned DataFrame has the expected columns.
2. Read `options_data_fetcher.py` completely:
   - Confirm ThetaData API endpoints and parameters.
   - Confirm the returned data structure matches what `ev_filter.py` and `base_features.py` expect.
3. Read `greeks_calculator.py` completely:
   - Verify Black-Scholes formulas against standard references.
   - Confirm vectorized and scalar implementations are consistent.
4. Read `vix_provider.py` completely:
   - Confirm VIX ETF proxy tickers (VIXY/VIXM) and data fetching.
   - Confirm returned DataFrame structure matches what `base_features.py` expects for VIX features.
5. Read `earnings_calendar.py` completely:
   - Confirm the API used actually supports earnings data.
   - Confirm cache behavior and fail-open on errors.

---

### PHASE 10: Feature Engineering Trace

1. Read all feature files (`base_features.py`, `swing_features.py`, `general_features.py`, `scalp_features.py`).
2. Verify feature counts match expectations:
   - Base: 73 features
   - Swing: 5 features
   - General: 4 features
   - Scalp: 10 features
3. For each `compute_*_features()` function:
   - Confirm every column added to the DataFrame is listed in the corresponding `get_*_feature_names()`.
   - Confirm no name collisions between feature sets.
4. Trace the feature pipeline end-to-end:
   - `feature_engineering` output columns -> trainer stores `feature_names` -> predictor loads `feature_names` -> predictor uses `feature_names` -> strategy passes features dict.
   - Any mismatch = silent NaN predictions.

---

### PHASE 11: Scripts Trace

For each script file (`backtest.py`, `train_model.py`, `walk_forward_backtest.py`, `startup_check.py`, `diagnose_strategy.py`, `validate_data.py`, `validate_model.py`, `audit_verify.py`):

1. Read the entire file.
2. Confirm all imports resolve.
3. Confirm called functions exist and signatures match.
4. Check for `sys.exit()` calls that would kill the entire process when called from a thread.
5. Check that return values are actually returned (not stored in local variables and forgotten).

---

### PHASE 12: Cross-Cutting Verification

After all phases are complete, verify these cross-cutting concerns:

1. **Import chain completeness**: For every file, confirm every `from X import Y` resolves.
2. **Feature name consistency**: Feature names from engineering must exactly match predictor expectations at inference time.
3. **Type consistency end-to-end**: Pick 5 data values that flow from DB -> backend -> API -> frontend -> display. Trace the type at each stage.
4. **Null safety**: For every optional/nullable field, confirm both backend and frontend handle the null case.
5. **Concurrent safety**: Training jobs run in background threads. Confirm no shared mutable state is modified without locks. Confirm DB writes from threads use their own connections.
6. **Timezone handling**: All time comparisons should use consistent timezones. Watch for EST vs EDT hardcoding, `datetime.utcnow()` deprecation (Python 3.12+), naive vs aware datetime mixing.
7. **Library version compatibility**: Check for deprecated API usage vs `requirements.txt` version constraints (e.g., XGBoost 2.0 removed `use_label_encoder`, pytorch-forecasting API changes).
8. **Error propagation**: Verify that errors in inner try/except blocks don't prevent outer error handlers from triggering (nested exception swallowing pattern).

---

## Known Bug Patterns to Check For

These patterns were found in previous audits. Verify they are either fixed or still present:

1. **Error counter bypass**: Inner try/except resets error counter, making outer auto-pause unreachable.
2. **Function returns None**: Function stores result in local variable but has no `return` statement.
3. **Hardcoded bar granularity**: Functions that should use preset-specific granularity but always use "5min".
4. **Wrong strategy class in backtest**: Backtest always imports one strategy class regardless of preset.
5. **Walk-forward ignoring window dates**: Training function fetches data relative to `datetime.now()` instead of window boundaries.
6. **Holdout on in-sample data**: Model trained on ALL data, then "holdout" evaluation on subset of training data.
7. **Meta-learner shape mismatch**: Trained with N inputs but inference provides fewer when a learner fails.
8. **EDT/EST hardcoding**: Using fixed UTC offset instead of timezone-aware datetime.
9. **Case-sensitive string comparison**: Comparing uppercase string to lowercase enum value.
10. **Deprecated library parameters**: Using removed/deprecated kwargs for current library versions.
11. **sys.exit() in threads**: `sys.exit()` in a function that gets called from a background thread kills the whole process.
12. **SQLite connection leaks**: Connection opened but not closed in exception paths (missing try/finally or context manager).

---

## Findings Document Format

Create `options-bot/docs/AUDIT_FINDINGS.md` with this structure:

```markdown
# Full Codebase Audit — Findings Document
## Date: [today's date]
## Method: Read every file, trace every function/import/field/constant to source
## Scope: [N] files across all layers

Status: **COMPLETE**

---

## CRITICAL BUGS ([count])

### C1. file.py:line — Short description
[Detailed explanation of what's wrong, why it's wrong, and the impact.]

**Impact:** [What happens at runtime because of this bug]

---

## HIGH BUGS ([count])

### H1. file.py:line — Short description
...

---

## MEDIUM BUGS ([count])

### M1. file.py:line — Short description
...

---

## LOW BUGS ([count])

### L1. file.py:line — Short description
...

---

## DEAD CODE ([count] items)

| # | File | Item | Notes |
|---|------|------|-------|
| 1 | file.py:line | function_name() | Zero callers |

---

## DEPRECATION WARNINGS ([count])

[List with file:line references]

---

## DESIGN OBSERVATIONS (not bugs, for awareness)

| # | Item | Notes |
|---|------|-------|
| 1 | Description | Context |

---

## VERIFIED CLEAN

- [List every file verified to have zero bugs, along with what was checked]

---

## FIX PRIORITY ORDER (recommended)

**Tier 1 — Live trading safety (fix before going live):**
1. **C1** — description

**Tier 2 — Backtest/training correctness:**
...

**Tier 3 — Data integrity / gates:**
...

**Tier 4 — Dead code / deprecations / cleanup:**
...
```

---

## Critical Rules

**RULE 1 — FINDINGS ONLY**: Do not fix any code during the audit. Write everything to the findings document. Fixes come after the audit is complete and reviewed.

**RULE 2 — READ EVERY LINE**: If a file has 500 lines, you read all 500. If you hit a context limit, say so and resume from where you left off. Do NOT summarize or skip sections.

**RULE 3 — TRACE, DON'T ASSUME**: If you find yourself writing "this looks correct" or "this should work" without having traced the SPECIFIC line numbers and cross-referenced them against the source of truth (schema, config, API spec), STOP. Go back and do the actual trace.

**RULE 4 — VERIFIED CLEAN MEANS VERIFIED**: When you report a file as "verified clean," you are staking your credibility on it. If a bug is later found in a file you marked clean, it means you failed the audit.

**RULE 5 — COMPLETE BEFORE FIXES**: The entire findings document must be written and reviewed BEFORE any fixes are attempted. This prevents partial-fix sessions that leave some bugs unfound.

**RULE 6 — PRIORITIZE CORRECTLY**: Anything that affects live trading safety is Tier 1. Anything that produces wrong ML results is Tier 2. Everything else is Tier 3+.
