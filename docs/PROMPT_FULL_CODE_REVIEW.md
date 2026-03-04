# FULL CODEBASE AUDIT — Post-Phase 6 Final Review

## PRIME DIRECTIVE

You are performing a **zero-trust, exhaustive audit** of every file in this codebase. The single source of truth is `PROJECT_ARCHITECTURE.md` in the project root. Every file, function, constant, endpoint, button, input field, database query, feature name, and ML pipeline step must be verified against that document.

**YOU ARE NOT ALLOWED TO:**
- Say "this looks correct" or "this should work" without showing the exact line numbers you verified
- Skip any file, function, or section because it "seems standard"
- Assume any prior developer (human or AI) got anything right
- Skim a file — if it has 800 lines, you read all 800 lines
- Mark a file "clean" without having read every line
- Gloss over error handling — trace what happens when every external call fails
- Trust that variable names imply correct behavior
- Skip UI verification — every button must be traced to its API call
- Skip ML verification — every feature name must be traced end-to-end

**YOU ARE REQUIRED TO:**
- Read `PROJECT_ARCHITECTURE.md` FIRST, completely, before touching any code
- Read every file completely — beginning to end, every line
- Show your work: quote the specific line numbers you verified
- Report bugs with exact file path, line number, current code, and fix
- If you hit a context limit, say exactly where you stopped and resume from that point
- When you mark a file "verified clean" you are staking your credibility — act accordingly

---

## PHASE 0: Build the Ground Truth

Before reviewing any code, build your reference tables from `PROJECT_ARCHITECTURE.md`.

### 0A. Read PROJECT_ARCHITECTURE.md completely

Read the entire file. Extract and write down:

1. **Complete file list** from the Directory Structure section. This is the canonical list of files that should exist. Any file in the repo not on this list is UNAPPROVED. Any file on this list missing from the repo is MISSING.

2. **Database schema** — every table, every column, every type, every constraint from Section 5a.

3. **API contract** — every endpoint (method, path, request body, response model) from Section 5b.

4. **Pydantic schemas** — every model and every field from Section 5c.

5. **Config constants** — every preset default, every threshold, every limit from Sections 6, 12, and 9E.

6. **Entry logic steps 1–12** from Section 10.

7. **Exit rules** (profit target, stop loss, max hold, DTE floor, model override) from Section 10.

8. **Feature counts** — base (68), swing (73), general (73), scalp (78+) from Section 7.

9. **Risk limits** — PDT rules, profile limits, portfolio limits from Section 12.

**Output**: Write all 9 reference tables. These are your ground truth for every subsequent phase.

---

## PHASE 1: File Inventory Audit

### 1A. Files that SHOULD exist

For every file in the architecture's directory structure, verify it exists on disk:
```bash
find . -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.md" | sort
```

Compare against the architecture list. Report:
- MISSING: files in architecture but not on disk
- UNAPPROVED: files on disk but not in architecture
- PRESENT: files that match

### 1B. Files that should NOT exist

Flag any `.py`, `.ts`, `.tsx` file in the working directories that is NOT listed in the architecture. These are either undocumented additions or leftover debris.

---

## PHASE 2: Database Schema Trace

### 2A. Read `backend/database.py` completely

Extract every `CREATE TABLE` statement. List every table, every column, type, constraints. This becomes your **code-level schema**.

### 2B. Compare code schema vs architecture schema

For every table in the architecture (Section 5a), confirm the code has the identical columns in the identical order with the identical types. Flag ANY deviation — extra column, missing column, wrong type, wrong constraint.

### 2C. Migration audit

For every `ALTER TABLE` or migration block:
- Confirm it has a try/except guard
- Confirm the column being added matches what the architecture says

### 2D. Every SQL query in the entire codebase

Search every `.py` file for SQL strings (`SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE`). For EACH query:
- Confirm the table name exists in the schema
- Confirm every column name exists in that table
- Confirm `?` placeholder count matches parameter count
- Confirm column order in SELECT matches how results are unpacked
- Flag any string-formatting SQL (SQL injection risk)

```bash
grep -rn "SELECT\|INSERT\|UPDATE\|DELETE\|CREATE TABLE" --include="*.py" | grep -v __pycache__ | grep -v ".pyc"
```

**Output format for each query:**
```
FILE: backend/routes/profiles.py:135
  QUERY: SELECT id, name, preset FROM profiles WHERE id = ?
  TABLE: profiles ✓
  COLUMNS: id ✓, name ✓, preset ✓
  PARAMS: 1 placeholder, 1 argument ✓
  UNPACK: row["id"], row["name"], row["preset"] ✓
```

---

## PHASE 3: Config Trace

### 3A. Read `config.py` completely

List every constant with its name, type, and value.

### 3B. Import trace

For every constant in config.py, search the entire codebase for where it is imported. Confirm:
- The import path is correct
- The variable name matches exactly
- The value is used correctly (not inverted, not wrong units)

Flag:
- Constants defined but never imported (dead code)
- Imports of config values that DO NOT exist in config.py (will crash)

### 3C. Preset defaults vs architecture

Compare every value in `PRESET_DEFAULTS` against Section 6 of the architecture. Every key, every value. Flag any mismatch.

### 3D. Phase 6 hardening constants

Verify ALL of these exist with correct values:
```
THETA_CB_FAILURE_THRESHOLD = 3
THETA_CB_RESET_TIMEOUT = 300
ALPACA_CB_FAILURE_THRESHOLD = 5
ALPACA_CB_RESET_TIMEOUT = 120
RETRY_BACKOFF_BASE = 2.0
RETRY_BACKOFF_MAX = 60.0
RETRY_MAX_ATTEMPTS = 3
MAX_CONSECUTIVE_ERRORS = 10
ITERATION_ERROR_RESET_ON_SUCCESS = True
WATCHDOG_POLL_INTERVAL_SECONDS = 30
WATCHDOG_AUTO_RESTART = True
WATCHDOG_MAX_RESTARTS = 3
WATCHDOG_RESTART_DELAY_SECONDS = 5
LOG_MAX_BYTES = 10_485_760
LOG_BACKUP_COUNT = 5
MODEL_HEALTH_WINDOW_SIZE = 50
MODEL_STALE_THRESHOLD_DAYS = 30
MODEL_DEGRADED_THRESHOLD = 0.45
MODEL_HEALTH_MIN_SAMPLES = 10
```

---

## PHASE 4: Backend Schema Trace (Pydantic ↔ DB ↔ TypeScript)

### 4A. Pydantic models

Read `backend/schemas.py` completely. List every model and every field with type.

### 4B. Pydantic ↔ Routes

For each Pydantic model, find which route(s) return it (check `response_model=`). Confirm the route actually constructs the model with all required fields.

### 4C. Pydantic ↔ Database

For each field in each Pydantic model that comes from the database, trace to the exact SQL query and confirm the column exists in Phase 2's schema.

### 4D. Pydantic ↔ TypeScript

Read `ui/src/types/api.ts` completely. For every Pydantic model with a TypeScript counterpart:
- Compare field-by-field: name match, type match
- Flag missing fields in either direction
- Flag type mismatches (e.g., Pydantic `float | None` but TS `number` without `| null`)

**Output format:**
```
SCHEMA: ProfileResponse (schemas.py)
  ROUTE: GET /api/profiles (profiles.py)
  TS TYPE: Profile (api.ts)
  
  id:              str → TEXT → string       ✓
  name:            str → TEXT → string       ✓
  model_summary:   ModelSummary|None → computed → ModelSummary|null  ✓
  trained_models:  list[ModelSummary] → computed → ✗ MISSING IN TS
```

---

## PHASE 5: API Route Trace — EVERY endpoint

For EVERY route handler in EVERY router file (`profiles.py`, `models.py`, `trades.py`, `system.py`, `trading.py`, plus any backtest routes):

### 5A. Route inventory

List every route: method, path, path params, query params, request body model, response model.

Compare against architecture Section 5b. Flag:
- Routes in code but not in architecture (unapproved)
- Routes in architecture but not in code (missing)
- Wrong HTTP method
- Wrong path
- Wrong response model

### 5B. Handler deep trace

For each handler function:

1. **DB queries**: Trace every query (Phase 2 rules apply)
2. **Function calls**: For every function called, trace to its definition. Confirm:
   - The function exists at the import path
   - Argument count and types match
   - Return type matches how result is used
3. **Error handling**: What happens when each external call fails? Is there a try/except? Does it return a proper HTTP error or crash?
4. **Async safety**: Confirm no blocking calls (`time.sleep`, `requests.get`, `sqlite3.connect`) in async handlers. Only `aiosqlite` and `httpx` (async) should be used in route handlers.
5. **Response construction**: Confirm all required Pydantic fields are provided
6. **Auth/validation**: Are path params validated? Are request body fields validated?

### 5C. Trading process manager deep trace

`backend/routes/trading.py` is the most complex router. Verify:
- Process spawning uses correct subprocess args
- PID tracking is thread-safe (locks used)
- Cross-platform compatibility (Windows vs Unix signal handling)
- Watchdog thread lifecycle (start, stop, poll interval)
- Auto-restart logic (max restarts, delay, counter reset)
- `_is_process_alive()` works on both Windows and Unix
- Stop logic: SIGTERM first, then SIGKILL after timeout (Unix) / taskkill (Windows)

---

## PHASE 6: UI Trace — EVERY page, EVERY button, EVERY input

### 6A. Read `ui/src/api/client.ts` completely

List every API function. For each one:
- What endpoint does it call (method + path)?
- Does that endpoint exist in the backend (Phase 5)?
- Do the request params match what the backend expects?
- Does the response type match the TypeScript interface?

### 6B. Dashboard.tsx — Full trace

Read the entire file. For every visible element:

1. **Stat cards**: What query fetches the data? What endpoint? What field from the response? Does the field exist in the Pydantic model?
2. **Profile cards**: What data populates them? What happens when you click Activate? Pause? Navigate to detail?
   - Trace Activate button → `onClick` → API call → backend handler → DB update → response
   - Trace Pause button → same full trace
3. **Status panel**: What data populates Alpaca/Theta/PDT indicators? Trace each back to the system status endpoint.
4. **Model health banner** (Phase 6): What query? What endpoint? What conditions show/hide it?

### 6C. Profiles.tsx — Full trace

1. **Profile list**: What query? How are status badges rendered?
2. **Create button** → What modal opens? What fields are collected? What API call on submit?
   - Trace: form fields → API request body → backend handler → DB insert → response
   - What preset options are available? Do they match config.py `PRESET_DEFAULTS`?
3. **Edit button** → Same trace
4. **Delete button** → Confirmation dialog? API call? Does backend cascade-delete models and trades?

### 6D. ProfileDetail.tsx — Full trace

This is the most complex page. Trace EVERY element:

1. **Model health tiles**: What data? What query? What fields (model type, accuracy, age, data range)?
2. **Train button**: What happens on click? What API call? What model type is sent?
   - Trace the split button: XGBoost / TFT / Ensemble each call `POST /api/models/{id}/train` with different `model_type`?
   - Does the Ensemble button check that both XGBoost and TFT exist?
3. **Training log stream**: What endpoint? What polling interval? How are log entries rendered?
4. **Feature importance panel**: What endpoint? How is data fetched and displayed?
5. **Backtest panel**: Date pickers → Run button → What API call? How are results displayed (Sharpe, drawdown, win rate)?
6. **Trade history table**: What endpoint? What filters?
7. **Activate/Pause buttons**: Same trace as Dashboard
8. **Live Accuracy tile** (Phase 6): What query? What endpoint? What field?
9. **Model health status banner** (Phase 6): What conditions trigger degraded/stale/healthy display?
10. **Config sliders** (if present): What parameters? What API call on save?

### 6E. Trades.tsx — Full trace

1. **Trade table**: What columns? Do they match the trades DB schema?
2. **Filters**: Profile, date range, symbol, outcome — What query params are sent?
3. **Sort**: Which columns are sortable? Does the API support sorting?
4. **CSV export**: What endpoint? What format?
5. **Pagination**: Does it exist? How is it implemented?

### 6F. System.tsx — Full trace

1. **Connection cards**: Alpaca, Theta, Backend — What data for each? What constitutes "connected"?
2. **PDT panel**: What data? Does it show remaining count correctly?
3. **Error log**: What endpoint? How are errors displayed?
4. **check_errors inline alert**: What triggers the AlertTriangle? Where does the data come from?

### 6G. TypeScript compilation

```bash
cd ui && npx tsc --noEmit 2>&1
```

Every error is a bug. List them all.

### 6H. Build verification

```bash
cd ui && npm run build 2>&1
```

Must succeed with 0 errors.

---

## PHASE 7: ML Pipeline — End-to-End Feature Trace

This is where silent bugs hide. A feature name mismatch between training and inference means the model gets garbage input at runtime and produces meaningless predictions with NO error.

### 7A. Feature engineering audit

Read EACH file completely:
- `ml/feature_engineering/base_features.py`
- `ml/feature_engineering/swing_features.py`
- `ml/feature_engineering/general_features.py`
- `ml/feature_engineering/scalp_features.py`

For each file:
1. List every feature name produced (column name added to DataFrame)
2. List the function that produces it
3. Verify `get_*_feature_names()` returns EXACTLY the same names as the compute function adds
4. Count total features: base=68, swing=base+5=73, general=base+5=73, scalp=base+10=78

**CRITICAL**: The names returned by `get_base_feature_names()` must EXACTLY match the column names added by `compute_base_features()`. Same for swing, general, scalp. Any mismatch = silent prediction failure.

### 7B. Training pipeline trace — XGBoost

Read `ml/trainer.py` completely. Trace the full pipeline:

1. Data fetch: What bars? What timeframe? What date range?
2. Options data: When is it fetched? How is it cached? What happens if Theta is down?
3. Feature computation: Which feature functions are called? In what order?
4. Target variable: What is being predicted? How is it computed?
5. NaN handling: How are NaN rows handled? What's the drop threshold?
6. Walk-forward CV: How many folds? What's the split logic?
7. Model fitting: What XGBoost params? Are they the same as architecture Section 8?
8. Feature names stored: After training, what feature names are saved? Do they match 7A?
9. Metrics: What metrics are computed? How are they stored in DB?
10. Model file: What format? Where saved? How named?

### 7C. Training pipeline trace — TFT

Read `ml/tft_trainer.py` completely. Same questions as 7B plus:

1. Encoder length: What is it? Is it consistent between training and inference?
2. Stride: What value? Does it match `BARS_PER_DAY`?
3. TimeSeriesDataSet construction: Are feature names correct? Is the target correct?
4. Training loop: Epochs, learning rate, early stopping?
5. Model save: What directory structure? What files?

### 7D. Training pipeline trace — Ensemble

Read `ml/ensemble_predictor.py` completely:

1. How are XGBoost and TFT predictions combined?
2. What is the meta-learner? Ridge regression?
3. Degraded mode: If TFT is missing, does it fall back to XGBoost-only? How?
4. Feature names: Does ensemble use the same features as its sub-models?

### 7E. Inference trace

For each predictor type (XGBoost, TFT, Ensemble):

1. Read the `predict()` method completely
2. What input does it expect? (feature dict? DataFrame?)
3. How does it use feature names? Does it reorder columns to match training order?
4. What does it return? (float? dict?)
5. How does the strategy call it? (trace from `base_strategy._check_entries()` Step 5)

### 7F. Feature consistency end-to-end

Pick ONE feature (e.g., `rsi_14`) and trace it completely:
```
compute_base_features() adds column "rsi_14" to DataFrame
  → get_base_feature_names() includes "rsi_14"
  → trainer.py uses get_base_feature_names() to select columns
  → XGBoost trains with "rsi_14" in position N
  → model.joblib stores feature_names including "rsi_14"
  → xgboost_predictor.load() reads feature_names
  → xgboost_predictor.predict() expects "rsi_14" in input dict
  → base_strategy._check_entries() computes features with "rsi_14"
  → passes to predictor.predict()
```

Do this trace for AT LEAST 5 features from different feature groups (base, options, swing-specific, scalp-specific, Greek). Any break in the chain = CRITICAL bug.

### 7G. Scalp-specific verification

Read `ml/scalp_predictor.py`, `ml/scalp_trainer.py`, `strategies/scalp_strategy.py`:

1. Does scalp use 1-minute bars? Architecture says yes.
2. Does scalp enforce same-day exit? Architecture says yes.
3. Does scalp block activation when equity < $25K? Architecture says yes.
4. Are scalp features computed from 1-min bars?
5. Is the scalp model separate from swing/general?

---

## PHASE 8: Strategy Logic Trace

### 8A. Entry logic — 12 steps

Read `base_strategy._check_entries()` completely. Trace each of the 12 steps from architecture Section 10:

| Step | Architecture says | Code does | Match? |
|------|-------------------|-----------|--------|
| 1 | Get current price | ??? | ? |
| 2 | Get 200 historical 5-min bars | ??? | ? |
| 3 | Get options data (Theta) | ??? | ? |
| 4 | Compute features (base + style) | ??? | ? |
| 5 | ML predict | ??? | ? |
| 6 | |predicted_return| < threshold | ??? | ? |
| 7 | Direction: CALL if positive, PUT if negative | ??? | ? |
| 8 | check_pdt(equity) | ??? | ? |
| 9 | scan_chain_for_best_ev() | ??? | ? |
| 10 | check_can_open_position() | ??? | ? |
| 11 | Submit order | ??? | ? |
| 12 | Log to trades table | ??? | ? |

For each step, show the exact code line(s) and confirm behavior matches architecture.

### 8B. Exit logic — 5 rules

Read `base_strategy._check_exits()` completely. Verify each rule:

| Rule | Architecture says | Code does | Match? |
|------|-------------------|-----------|--------|
| Profit target | Position up ≥ target % | ??? | ? |
| Stop loss | Position down ≥ loss % | ??? | ? |
| Max holding | Held ≥ max_hold_days | ??? | ? |
| DTE floor | DTE < 3 | ??? | ? |
| Model override | Predicts reversal | ??? | ? |

Confirm: exits checked BEFORE entries. First match wins.

### 8C. Backtest mode

How does the strategy behave differently in backtest vs live?
- Does it trade stocks instead of options in backtest?
- Is the min_move threshold different?
- Does it skip Theta calls?

### 8D. Phase 6 hardening in strategy

Verify:
- `on_trading_iteration()` body is wrapped in try/except
- Consecutive error counter exists and increments
- Auto-pause at MAX_CONSECUTIVE_ERRORS
- Counter resets on successful iteration
- Timing instrumentation exists for major steps
- Slow iteration warning (>10s)
- Prediction recording for health monitoring
- Outcome tracking (_update_prediction_outcomes)
- Health persistence (_persist_health_to_db)
- All health tracking wrapped in try/except: pass (non-fatal)

---

## PHASE 9: Risk Manager Trace

### 9A. Read `risk/risk_manager.py` completely

### 9B. Method contract verification

From architecture Section 10:

| Method | Returns | Used by |
|--------|---------|---------|
| check_pdt(equity) | {"allowed": bool, "message": str} | Entry Step 8 |
| check_pdt_limit(equity) | (bool, str) tuple | Internal |
| check_can_open_position(profile_id, config, portfolio_value, option_price) | {"allowed": bool, "quantity": int, "reasons": list} | Entry Step 10 |
| check_portfolio_exposure() | ??? | on_trading_iteration |
| check_emergency_stop_loss() | ??? | on_trading_iteration |

Verify BOTH check_pdt and check_pdt_limit exist (architecture says "do not remove either").

### 9C. PDT logic

- Equity < $25K: max 3 day trades per rolling 5 business days
- Equity ≥ $25K: unlimited
- How are day trades counted? How is the rolling window computed?

### 9D. Position limits

Verify these limits are enforced:
- max_position_pct: 20%
- max_contracts: 5
- max_concurrent_positions: 3
- max_daily_trades: 5
- max_daily_loss_pct: 10%
- max_total_exposure_pct: 60% (global)
- max_total_positions: 10 (global)
- emergency_stop_loss_pct: 20% (global)

### 9E. Trade logging

How are trades logged to the database? Does the INSERT statement match the trades table schema?

---

## PHASE 10: Data Provider Trace

### 10A. Read `data/alpaca_provider.py` completely

- API endpoint correctness (Alpaca SDK calls)
- Timezone handling (market hours, UTC vs Eastern)
- Retry logic with exponential backoff (Phase 6)
- Circuit breaker integration (Phase 6)
- Returned DataFrame column names

### 10B. Read `data/theta_provider.py` completely

- API endpoint correctness (Theta Data V3)
- Response parsing (CSV format)
- Greeks extraction
- Error handling when Theta Terminal is down

### 10C. Read `data/options_data_fetcher.py` completely

- Parquet cache logic
- Monthly batch fetching
- Date range gap detection
- Returned data structure vs what ev_filter and base_features expect

### 10D. Read `data/greeks_calculator.py` completely

- Black-Scholes formulas — verify against standard references
- 2nd order Greeks: vanna, vomma, charm, speed
- `get_second_order_feature_names()` must return exactly 8 names
- Those 8 names must match what `base_features.py` appends

---

## PHASE 11: Circuit Breaker + Hardening Trace (Phase 6)

### 11A. Read `utils/circuit_breaker.py` completely

- State machine: CLOSED → OPEN → HALF_OPEN → CLOSED
- Thread safety (Lock used on all state mutations)
- exponential_backoff formula correctness
- Jitter range (±25%)
- Max delay cap

### 11B. Circuit breaker integration points

Where is CircuitBreaker instantiated? Where is it checked? Trace each:
- `data/alpaca_provider.py` — circuit breaker for bar fetching
- `strategies/base_strategy.py` — circuit breaker for Theta calls (or documented why not needed)

### 11C. Watchdog thread

Read `backend/routes/trading.py` watchdog code:
- Thread lifecycle (start_watchdog/stop_watchdog)
- Poll loop timing
- Process health detection
- Auto-restart logic (max 3, delay 5s, counter reset)
- Cross-platform process alive check

### 11D. Graceful shutdown

Read `main.py` signal handling:
- SIGINT/SIGTERM handlers
- _shutting_down flag
- All loops check the flag
- Second signal forces exit
- Shutdown summary logged

### 11E. Log rotation

- RotatingFileHandler (not FileHandler)
- Max 10MB per file
- 5 backup files
- LOG_MAX_BYTES and LOG_BACKUP_COUNT from config

### 11F. Model health monitoring

In `base_strategy.py`:
- _record_prediction called after Step 5
- _update_prediction_outcomes called each iteration
- _compute_rolling_accuracy window size matches config
- _persist_health_to_db writes at most once per minute
- All health code wrapped in try/except (non-fatal)

In `backend/routes/system.py`:
- /model-health endpoint reads from system_state table
- Combines live accuracy with model age
- Returns correct status codes (healthy/warning/degraded/stale/no_data)

---

## PHASE 12: EV Filter + Options Chain Trace

### 12A. Read `ml/ev_filter.py` completely

- EV formula: `EV% = (expected_gain - theta_cost) / premium * 100`
- What is `expected_gain`? Option price increase (not total value)
- What is `theta_cost`? Time decay over expected holding period
- Chain scanning: How are strikes filtered? What DTE range?
- Error handling: What happens if Theta is down? Must return None, not crash.

### 12B. How is EV filter called from strategy?

Trace: `_check_entries()` Step 9 → `scan_chain_for_best_ev()` → what args? → what return value? → how is it used to submit the order?

---

## PHASE 13: main.py Trace

### 13A. Read `main.py` completely

- Argument parsing: all flags (--trade, --profile-id, --profile-ids, --symbol, --preset, --no-backend)
- Backend startup: FastAPI + uvicorn
- Trading subprocess spawning
- Strategy class routing (`_get_strategy_class`)
- Signal handlers (Phase 6)
- Startup banner (Phase 6)
- RotatingFileHandler (Phase 6)

### 13B. Strategy class routing

Verify `_get_strategy_class(preset)` returns:
- "swing" → SwingStrategy
- "general" → GeneralStrategy
- "scalp" → ScalpStrategy

### 13C. Subprocess command construction

When `trading.py` spawns a trading subprocess, what command does it run? Trace the full Popen call. Confirm the args are correct.

---

## PHASE 14: Cross-Cutting Verification

### 14A. Import chain completeness

For every `.py` file, verify every `from X import Y` resolves. No ImportErrors at runtime.

```bash
python -c "
import importlib, pkgutil, sys
sys.path.insert(0, '.')
for f in ['config', 'main', 'backend.app', 'backend.database', 'backend.schemas',
          'backend.routes.profiles', 'backend.routes.models', 'backend.routes.trades',
          'backend.routes.system', 'backend.routes.trading',
          'data.provider', 'data.alpaca_provider', 'data.theta_provider',
          'data.greeks_calculator', 'data.options_data_fetcher',
          'ml.predictor', 'ml.xgboost_predictor', 'ml.tft_predictor',
          'ml.ensemble_predictor', 'ml.trainer', 'ml.tft_trainer',
          'ml.incremental_trainer', 'ml.ev_filter',
          'ml.scalp_predictor', 'ml.scalp_trainer',
          'ml.feature_engineering.base_features',
          'ml.feature_engineering.swing_features',
          'ml.feature_engineering.general_features',
          'ml.feature_engineering.scalp_features',
          'risk.risk_manager',
          'strategies.base_strategy', 'strategies.swing_strategy',
          'strategies.general_strategy', 'strategies.scalp_strategy',
          'utils.circuit_breaker']:
    try:
        importlib.import_module(f)
        print(f'  OK: {f}')
    except Exception as e:
        print(f'  FAIL: {f} — {e}')
"
```

### 14B. Type consistency end-to-end

Pick 5 data values that flow from DB → backend → API → frontend → display. Trace the type at each stage:

1. `profile.status`: TEXT → str → JSON string → TypeScript string → StatusBadge component
2. `trade.pnl_pct`: REAL → float → JSON number → TypeScript number → PnlCell component
3. `model.metrics.dir_acc`: TEXT(JSON) → dict → JSON object → TypeScript dict → MetricTile
4. `system_status.portfolio_value`: computed float → JSON number → TypeScript number → stat card
5. `model_health.rolling_accuracy`: TEXT(JSON) → float|None → JSON number|null → TS number|null → Live Accuracy tile

### 14C. Null safety

For every optional/nullable field in the Pydantic models, confirm:
- Backend handles None (doesn't crash on missing data)
- Frontend handles null/undefined (uses `??`, `?.`, or conditional rendering)

### 14D. Concurrent safety

- Training jobs run in background threads. Are DB connections per-thread (not shared)?
- Trading processes are subprocesses. Is PID registry access locked?
- Watchdog thread: does it use locks when modifying shared state?
- Model health persistence from strategy: uses its own sqlite3.connect (not shared)?

### 14E. Error propagation

For each external service call (Alpaca API, Theta Terminal, DB write):
- What happens on timeout?
- What happens on connection refused?
- What happens on invalid response?
- Does the error propagate as an HTTP 500, or is it caught and handled?

---

## OUTPUT REQUIREMENTS

After completing ALL 14 phases, produce this exact output structure:

```
## BUGS FOUND

### CRITICAL (will crash at runtime)
1. [file:line] Description
   Current: <exact current code>
   Fix: <exact fix>

### HIGH (wrong behavior, data corruption, silent failures)
1. [file:line] Description
   Current: <exact current code>
   Fix: <exact fix>

### MEDIUM (degraded UX, performance, edge cases)
1. [file:line] Description
   Current: <exact current code>
   Fix: <exact fix>

### LOW (style, naming, minor inconsistencies)
1. [file:line] Description

### ARCHITECTURE DEVIATIONS
1. [file] Deviation from PROJECT_ARCHITECTURE.md Section X
   Architecture says: <quote>
   Code does: <what it actually does>
   Severity: MUST FIX / SHOULD FIX / NOTE

## VERIFIED CLEAN
List EVERY file you read completely and confirmed has zero bugs.
Only list a file here if you read every single line.

## FILES NOT REVIEWED
List any files you could not review (context limit, etc.)
State where you stopped and why.
```

---

## ENFORCEMENT RULES

These rules override everything else:

1. **NO HAND-WAVING**: Every claim of "correct" must cite the specific line number. "Lines 45-52 implement check_pdt returning dict with 'allowed' and 'message' keys, matching architecture Section 10" — not "check_pdt looks correct".

2. **NO ASSUMPTIONS**: If you can't verify something because you'd need to run the code, say so. Don't assume it works.

3. **NO SKIPPING**: If a file is 1000 lines, you read 1000 lines. If you need to pause for context, say "PAUSING at file X line Y, will resume" and continue in the next response.

4. **NO GUESSING**: If you're unsure whether a function exists at an import path, you trace to the file and check. You don't guess.

5. **ARCHITECTURE IS LAW**: If the code does something different from PROJECT_ARCHITECTURE.md, the code is wrong. Period. The only exception is if the architecture itself has an error, in which case you flag it as "ARCHITECTURE BUG" with explanation.

6. **EVERY BUTTON GETS TRACED**: Every onClick, every form submit, every mutation — traced from UI element → API call → backend handler → DB query → response → UI update. No exceptions.

7. **EVERY FEATURE NAME GETS TRACED**: From compute function → get_names function → trainer → model file → predictor → strategy. A single name mismatch is a CRITICAL bug.

8. **SEVERITY IS HONEST**: Don't inflate minor issues to CRITICAL. Don't deflate actual crashes to LOW. A missing import is CRITICAL. A style inconsistency is LOW. A wrong feature name is CRITICAL. A missing tooltip is LOW.

9. **SHOW LINE NUMBERS**: Every finding must include the exact file path and line number(s). "Somewhere in base_strategy.py" is not acceptable.

10. **COMPLETE OR INCOMPLETE**: Either you reviewed a file completely or you didn't. There is no "mostly reviewed". If you skipped lines 200-400, the file goes in "FILES NOT REVIEWED" with the gap noted.
