# Full Codebase Audit — Findings Document
## Date: 2026-03-04
## Method: Read every file, trace every function/import/field/constant to source
## Scope: 80+ files across all layers (data, ML, strategies, backend, frontend, scripts)

Status: **COMPLETE**

---

## CRITICAL BUGS (5)

### C1. base_strategy.py:446-465 — Auto-pause never triggers for trading loop errors
The inner `try/except` at line 357 catches all errors from `_check_exits` and `_check_entries`, then falls through to line 464 which resets `_consecutive_errors = 0`. The outer `except` at line 467 (which increments the counter) is **unreachable** for core trading errors. The `MAX_CONSECUTIVE_ERRORS` auto-pause mechanism is completely broken — it will never trigger for errors in the trading logic.

**Impact:** Bot will never auto-pause on repeated failures. Could continue trading with broken state indefinitely.

### C2. scripts/walk_forward_backtest.py — Training ignores window dates
`_train_window()` calls `train_model()` with `years_of_data` for EVERY window. Inside `train_model()`, data is always fetched as `datetime.now() - timedelta(days=years_of_data * 365)` — the same range regardless of window. The per-window `window_start` and `train_end` dates are never passed to the training function. Every window trains on identical data, completely defeating the purpose of walk-forward validation.

**Impact:** Walk-forward backtest results are meaningless — all windows use the same model.

### C3. scripts/backtest.py — `run_backtest()` returns None (no return statement)
The function stores the Lumibot result in a local variable `result` but never returns it. Returns implicit `None`. Two callers depend on the return value:
- `backend/app.py:102`: `result = run_backtest(...)` — metrics extraction always yields `None`. Backtests appear to succeed in UI but show no metrics.
- `walk_forward_backtest.py:210`: Always returns empty `metrics = {}`.

Additionally, `sys.exit(1)` calls at lines 85, 188, 208 raise `SystemExit` (inherits from `BaseException`, not `Exception`). When called from `backend/app.py`'s background thread, this **crashes the entire FastAPI server**.

**Impact:** All backtest metrics are always empty. Server crashes on certain backtest errors.

### C4. ml/scalp_trainer.py:202,475 — `use_label_encoder=False` removed in XGBoost 2.0+
`XGBClassifier` is called with `use_label_encoder=False`, but `requirements.txt` requires `xgboost>=2.0.0` and this parameter was **removed** in XGBoost 2.0. This will cause `TypeError: __init__() got an unexpected keyword argument 'use_label_encoder'` at runtime. Affects both CV training (line 202) and final model training (line 475).

**Impact:** Scalp model training is completely broken at runtime.

### C5. ml/tft_predictor.py:366 — Unused import crashes TFT inference path
`from pytorch_forecasting.data import NaNLabelEncoder` is imported inside `_run_tft_inference()` but never used. If this import path doesn't exist in the installed pytorch-forecasting version (API was restructured in >=1.0.0), ALL TFT inference crashes because the import runs on every prediction call.

**Impact:** All TFT predictions may fail depending on pytorch-forecasting version.

---

## HIGH BUGS (6)

### H1. ml/trainer.py:424 — Hardcoded "5min" bar granularity for all presets
`bars_df = stock_provider.get_historical_bars(symbol, start_date, end_date, "5min")` — always uses `"5min"` regardless of preset. The `bar_granularity` variable is computed on line 406 but never used in the fetch call. If `train_model()` is called with `preset="scalp"`, it fetches 5-min bars instead of 1-min bars. All scalp features (designed for 1-min data) would be computed on wrong-resolution data.

**Mitigated by:** Scalp has a dedicated `scalp_trainer.py` that fetches 1-min bars correctly. But `trainer.py` does not guard against scalp preset being passed.

### H2. ml/tft_trainer.py — Saves wrong model checkpoint to disk
The TFT trainer saves the wrong model checkpoint. (Detail from ML predictor audit: the best checkpoint is not correctly selected before saving.)

**Impact:** TFT model files on disk may not correspond to the best training epoch.

### H3. scripts/backtest.py — Always uses SwingStrategy regardless of preset
Line 80 hard-codes `from strategies.swing_strategy import SwingStrategy`. If `preset="general"` or `preset="scalp"`, the backtest still runs `SwingStrategy`, not the correct strategy class. The `preset` parameter only affects the config dict, not the strategy class.

**Impact:** All backtests run the same strategy class. General and scalp backtests use wrong strategy.

### H4. ml/trainer.py — Missing bar_granularity in external callers of _prediction_horizon_to_bars
`incremental_trainer.py:363` and `ensemble_predictor.py:484` call `_prediction_horizon_to_bars(prediction_horizon)` without passing `bar_granularity`. Defaults to `"5min"`. For scalp profiles (1-min bars, 30-min horizon), this returns 6 bars instead of 30 — incorrect forward return targets.

**Mitigated by:** Scalp doesn't use ensemble. But incremental_trainer could be triggered for scalp.

### H5. ml/incremental_trainer.py:497-523 — Holdout evaluation on in-sample data
The holdout is the last 20% of `X_new`, but the model was trained on ALL of `X_new` (line 497-498). The holdout evaluation is on in-sample data, giving optimistically biased metrics. The holdout should be split BEFORE training.

**Impact:** Incremental retrain metrics are unreliable — model appears better than it is.

### H6. ml/ensemble_predictor.py:230-234 — Meta-learner shape mismatch when LightGBM fails
If meta-learner was trained with 3 inputs (xgb+tft+lgbm) but LightGBM fails at inference, the code passes only 2 inputs to `Ridge.predict()`, causing a shape mismatch `ValueError`. The guard on line 230 checks `coef_.shape[0] >= 3` but the fallback 2-input path will crash.

**Impact:** Ensemble predictions fail if LightGBM was part of training but unavailable at inference.

---

## MEDIUM BUGS (8)

### M1. base_strategy.py:777 — Hardcoded EST offset, breaks during EDT
Scalp same-day exit uses `datetime.timezone(datetime.timedelta(hours=-5))` (EST, UTC-5). During EDT (March–November, UTC-4), the 3:45 PM ET cutoff fires at the wrong time — either an hour early or late for ~7 months/year.

### M2. data/earnings_calendar.py — Earnings gate is non-functional
Uses `ca_types=earnings` in Alpaca corporate actions API, but Alpaca only supports `dividend`, `merger`, `spinoff`, `split`. The request always fails, the HTTPError handler caches an empty result, and the gate always returns "no earnings found." The code's own comment (line 138) acknowledges this. **The entire earnings blackout gate is a no-op.**

### M3. ml/regime_adjuster.py:52 — TypeError on None input
`if vix_level <= 0 or vix_level is None:` evaluates `None <= 0` first, raising `TypeError`. The `is None` check must come first. Currently masked by caller guard in base_strategy.py:1394 (`if vixy_price and vixy_price > 0:`), but the function's own guard is logically broken.

### M4. ml/trainer.py — CV metrics don't match final model
Walk-forward CV (step 5) uses hardcoded default hyperparameters. The final model (step 6) uses Optuna-tuned hyperparameters. The CV metrics stored in the DB reflect the default params, not the actual model's performance.

### M5. ml/trainer.py:671 — DB save failure silently ignored
If the async DB save fails, `_run_async` returns `None` and the pipeline reports `"status": "ready"`. The model file exists on disk but has no DB record. Profile status remains stuck at "training."

### M6. ml/xgboost_predictor.py:69-70 — NaN/Inf predictions silently return 0.0
When XGBoost returns NaN/Inf (extreme feature values), the predictor logs an error but returns `0.0`. This masks model failures and could produce 0.0 predictions that affect trading decisions.

### M7. database.py line 108 / schemas.py line 288 — step_stopped_at type mismatch
`signal_logs.step_stopped_at` is declared as `INTEGER` in DB schema but Pydantic schema expects `float`. Values like `8.7` (fractional step numbers) would be truncated by the INTEGER type. SQLite's loose typing means this "works" but the DB column type should be `REAL`.

### M8. backend/routes/profiles.py:285 — Profile delete leaves orphaned data
`delete_profile` does NOT clean up:
- `training_queue` rows for the deleted profile
- `system_state` rows (`backtest_{id}`, `model_health_{id}`, `trading_{id}`)

Orphaned records accumulate silently.

---

## LOW BUGS (7)

### L1. base_strategy.py:509 — Circuit breaker OPEN alert never fires
`theta_state == "OPEN"` compares uppercase, but `CircuitState.OPEN.value` is `"open"` (lowercase). The alert for Theta Terminal circuit breaker opening is dead code.

### L2. base_strategy.py:1037-1057 — SQLite connection leak in _write_signal_log
Connection opened at line 1037, but if `con.execute()` raises, `con.close()` is never reached. Should use `try/finally` or `with` context manager.

### L3. base_strategy.py:228-232 — Theta circuit breaker initialized but never used
`_theta_circuit_breaker` is created but `can_execute()`, `record_success()`, `record_failure()` are never called. The breaker always reports "closed" with 0 failures. Provides no actual protection.

### L4. config.py:227-228 — OPTUNA_N_TRIALS/OPTUNA_TIMEOUT_SECONDS unused
These constants are defined in config.py but never imported by any Python file. `_optuna_optimize()` hardcodes the same values as function defaults. Changing config.py has no effect.

### L5. Frontend — bg-card/bg-hover CSS classes don't exist
`ProfileDetail.tsx` error state uses `bg-card` and `bg-hover` Tailwind classes that don't exist in the Tailwind config. Styling bug only.

### L6. app.py:239 vs system.py:49 — Version string mismatch
FastAPI app declares `version="0.3.0"` but health endpoint returns `version="0.2.0"`. Not centralized.

### L7. feedback_queue.py:38,65,95 — No SQLite lock timeout
Synchronous `sqlite3.connect()` without `timeout` parameter. If DB is locked by async backend, calls fail immediately rather than waiting. Could silently drop training queue samples.

---

## DEAD CODE (16 items)

| # | File | Item | Notes |
|---|------|------|-------|
| 1 | `ml/feedback_queue.py:59` | `get_pending_count()` | Zero callers. system.py queries DB directly. |
| 2 | `ml/feedback_queue.py:83` | `consume_queue()` | Zero callers. Built for future walk-forward trainer. |
| 3 | `risk/risk_manager.py:643` | `check_portfolio_delta_limit()` | Zero callers. base_strategy.py does inline delta check. |
| 4 | `base_strategy.py:527-572` | `_emergency_liquidate_all()` | Zero callers. Emergency stop uses inline liquidation. |
| 5 | `base_strategy.py:1968-1981` | `get_health_stats()` | Zero callers. |
| 6 | `data/alpaca_provider.py:249` | `get_circuit_breaker_stats()` | Zero callers. |
| 7 | `data/options_data_fetcher.py:93` | `_implied_vol_vectorized()` | Zero callers. |
| 8 | `data/greeks_calculator.py:271` | `get_second_order_feature_names()` | Zero callers. Names embedded in base_features.py. |
| 9 | `data/validator.py` (entire file) | `validate_symbol_data()`, `validate_all_symbols()` | Zero callers anywhere. Never wired into pipeline. |
| 10 | `data/theta_provider.py` (class) | `ThetaOptionsProvider` | Only used in test script. Production uses direct HTTP. |
| 11 | `ui/package.json` | `recharts` dependency | Never imported or used. |
| 12 | `ui/src/types/api.ts` | `ModelMetrics` type | Never imported. |
| 13 | `scripts/process_watchdog.py` | File deleted | Functionality moved to trading.py. |
| 14 | `scripts/checkpoint.py` | File deleted | checkpoints/ directory still exists. |
| 15 | `base_strategy.py:40` | `MODELS_DIR` import | Imported but never used. |
| 16 | Multiple files | Various unused imports | `Optional` in predictor.py, xgboost_predictor.py; `numpy` in vix_provider.py; `timedelta` in theta_provider.py; `Query` in profiles.py; `ast` in audit_verify.py; `time` in risk_manager.py |

---

## DEPRECATION WARNINGS (non-breaking, ~20+ occurrences)

`datetime.utcnow()` is deprecated in Python 3.12+ (project runs 3.13). Should use `datetime.now(timezone.utc)`. Found in:
- `backend/app.py:48`
- `backend/routes/models.py:120`
- `backend/routes/profiles.py:41,227,261,373,402`
- `backend/routes/system.py:48,340`
- `ml/feedback_queue.py:36,145`
- `ml/trainer.py:638-639`
- `risk/risk_manager.py:85,491,536,583`
- `data/validator.py:335`

Also: `early_stopping_rounds` in XGBRegressor constructor (trainer.py:303) — deprecated in xgboost>=2.0.

---

## DESIGN OBSERVATIONS (not bugs, for awareness)

| # | Item | Notes |
|---|------|-------|
| 1 | Two Theta Terminal code paths | `theta_provider.py` (unused class) vs `options_data_fetcher.py` (direct HTTP). Production bypasses the provider abstraction. |
| 2 | Duplicate Black-Scholes | `options_data_fetcher.py._bs_price` and `greeks_calculator.py._bs_d1_d2` — two independent implementations. |
| 3 | Hardcoded risk-free rate | `r = 0.045` in `options_data_fetcher.py:42` and `base_features.py:380`. Not centralized in config.py. |
| 4 | No circuit breaker for Theta HTTP calls | `options_data_fetcher._fetch_eod_batch()` makes direct HTTP calls with no circuit breaker, despite config having `THETA_CB_*` constants. |
| 5 | `pytz` not in requirements.txt | Imported in base_strategy.py:781 (scalp timezone). Works via transitive dep from pandas/lumibot. |
| 6 | Stale docstring in base_strategy.py:19-21 | Claims subclasses must implement `get_prediction_horizon_bars()` and `get_feature_set_name()` — neither exists. |
| 7 | `alpaca_subscription` hardcoded | system.py:121 always returns `"algo_trader_plus"` — never actually queried from API. |
| 8 | Frontend `as any` casts | System.tsx circuit breaker section uses `as any` casts — reduces type safety. |
| 9 | Dashboard hardcoded thresholds | `45%` accuracy threshold and `/ 10` max positions — should come from config constants. |
| 10 | New AlpacaStockProvider per call | Every `fetch_vix_daily_bars()` call creates a new provider instance, losing circuit breaker state between calls. |

---

## VERIFIED CLEAN

- **All imports resolve** — zero broken imports across the entire codebase
- **All config constants exist** — every reference verified against config.py
- **All feature name counts match** — 73 base + 5 swing + 4 general + 10 scalp, verified between compute and get_*_feature_names()
- **All Pydantic schemas match frontend TypeScript types** — every field verified 1:1
- **All DB column references match SCHEMA_SQL** — zero column name mismatches
- **All API endpoints have matching frontend callers** — response shapes verified
- **All ML function signatures match their callers** — parameter counts and types verified (except noted bar_granularity omissions)

---

## FIX PRIORITY ORDER (recommended)

**Tier 1 — Live trading safety (fix before going live):**
1. **C1** — Error counter reset (auto-pause broken)
2. **L1** — Circuit breaker alert case mismatch (quick fix)
3. **L3** — Wire theta circuit breaker to actually gate calls
4. **M1** — EDT timezone fix (scalp EOD exit wrong half the year)
5. **M3** — regime_adjuster None guard order
6. **C4** — scalp_trainer use_label_encoder removal (scalp training broken)
7. **C5** — tft_predictor NaNLabelEncoder unused import (TFT inference risk)
8. **M6** — xgboost_predictor NaN/Inf silent 0.0 return

**Tier 2 — Backtest/training correctness:**
9. **C3** — backtest.py return statement + sys.exit → exception
10. **H3** — backtest.py strategy class selection
11. **H1** — trainer.py bar granularity (scalp safety)
12. **H5** — incremental_trainer holdout on in-sample data
13. **H6** — ensemble meta-learner shape mismatch
14. **M4** — CV metrics don't match final model
15. **M5** — trainer.py DB save failure silent

**Tier 3 — Data integrity / gates:**
16. **M2** — Earnings gate non-functional (find working API or remove)
17. **M7** — step_stopped_at column type (INTEGER → REAL)
18. **M8** — Profile delete orphaned data cleanup
19. **C2** — Walk-forward window dates

**Tier 4 — Dead code / deprecations / cleanup:**
20. All dead code items (16 total)
21. All datetime.utcnow() deprecations (~20 occurrences)
22. All unused imports
23. **L4** — OPTUNA config constants unused
24. **L6** — Version string mismatch
