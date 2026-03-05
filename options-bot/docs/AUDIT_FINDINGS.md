# Full Codebase Audit — Findings Document

**Date:** 2026-03-04 (Re-audit after Tier 1-4 fixes)
**Auditor:** Claude Opus 4.6
**Scope:** Every file in the `options-bot/` directory — backend, frontend, ML pipeline, strategies, risk, data, scripts, utilities.
**Method:** Line-by-line read of every file, tracing imports, function calls, config references, DB schema references, and data flow.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 8 |
| HIGH | 24 |
| MEDIUM | 38 |
| LOW | 40 |
| **Total** | **110** |

---

## Tier 1 — CRITICAL (crash or wrong trades in production)

### C1. Predictor NaN/None return inconsistency crashes ensemble
**Files:** `ml/ensemble_predictor.py:196,222`, `ml/lgbm_predictor.py:72-73`, `ml/tft_predictor.py:228-229`

`XGBoostPredictor.predict()` returns `None` for NaN/Inf. `LightGBMPredictor` and `TFTPredictor` return `0.0` instead. In `ensemble_predictor.py:196`, `np.isnan(xgb_pred)` crashes with `TypeError` when `xgb_pred` is `None`. The `0.0` return from LightGBM/TFT is equally dangerous — it injects a false "no change" signal into the ensemble instead of excluding the faulty predictor.

**Fix:** All predictors return `None` for invalid predictions. Ensemble checks `pred is None` before `np.isnan()`.

### C2. `get_greeks()` return treated as dict but Lumibot returns a Greeks object
**Files:** `strategies/base_strategy.py:910`, `ml/ev_filter.py:278-282`

Lumibot's `get_greeks()` returns a `Greeks` namedtuple/object. Code calls `.get("delta")` which raises `AttributeError`. In `base_strategy.py`, the outer `try/except` silently swallows this — **exit Greeks are never recorded for any live trade**. In `ev_filter.py`, this means **no contract can be scored** unless the except catches it.

**Fix:** Use attribute access (`greeks.delta`, `greeks.gamma`, etc.) instead of `.get()`.

### C3. `strategy.get_quote()` does not exist in Lumibot API
**File:** `ml/ev_filter.py:302`

`get_quote(option_asset)` is called but Lumibot has no `get_quote()` method. The except clause catches the `AttributeError`, so it won't crash, but the in-scanner bid-ask spread filtering (lines 299-327) is **completely non-functional dead code**. Every contract falls through to `premium = get_last_price()`.

**Fix:** Use `get_last_price()` for bid/ask or fetch quotes via the broker's API directly.

### C4. `_get_exposure()` has no error handling — exposure silently reports 0%
**File:** `risk/risk_manager.py:251-262`

Unlike every other async DB function in the class, `_get_exposure()` has no `try/except`. On DB lock or corruption, `_run_async` returns `None`, which callers treat as `0.0` exposure — potentially **allowing trades that should be blocked by the exposure limit**.

**Fix:** Add `try/except` matching the pattern in other methods.

### C5. Alpaca options snapshot API call likely incorrect
**File:** `ml/liquidity_filter.py:149-165`

`OptionHistoricalDataClient.get_option_snapshot()` and `OptionSnapshotRequest` may not exist in the installed `alpaca-py` version. The `ImportError` catch silently returns all `None` values, meaning the snapshot-based liquidity check **silently fails every time**.

**Fix:** Verify correct `alpaca-py` API and update import paths.

### C6. Deprecated `datetime.utcnow()` — systemic across 10+ files
**Files:** `base_strategy.py:509`, `ensemble_predictor.py:700-701`, `lgbm_trainer.py:329-330`, `tft_trainer.py:681,751`, `scalp_trainer.py:560-561`, `incremental_trainer.py:168,232,294`, `data/validator.py:335`

Deprecated in Python 3.12+, returns naive datetimes inconsistent with `datetime.now(timezone.utc)` used elsewhere. Causes mixed naive/aware timestamps in the same DB tables.

**Fix:** Replace all with `datetime.now(timezone.utc)` and `datetime.fromtimestamp(ts, tz=timezone.utc)`.

### C7. `incremental_trainer.py:197-201` — DB save error silently swallowed
**File:** `ml/incremental_trainer.py:197-201`

`_run_async(_save_to_db())` does not check the return value or propagate errors. If the DB save fails, the model file exists on disk but has no DB record, and the profile status remains stuck at "training" forever. Same issue in `scalp_trainer.py:513-522` and `lgbm_trainer.py:358`.

**Fix:** Check return value and add synchronous fallback matching `trainer.py` pattern.

### C8. `feedback_queue.py:38-50` — SQLite connection leaked on exception
**File:** `ml/feedback_queue.py:38-50`

`sqlite3.connect()` opens at line 38, `con.close()` at line 50. If `con.execute()` or `con.commit()` raises, the connection is never closed. Over time, this leaks file handles.

**Fix:** Use `with sqlite3.connect(...) as con:` context manager.

---

## Tier 2 — HIGH (incorrect behavior or data loss)

### H1. Model health tracking evaluates predictions after minutes instead of hours/days
**File:** `strategies/base_strategy.py:1970-1998`

`_update_prediction_outcomes()` resolves predictions on the very next iteration (5 min for swing, 1 min for scalp) instead of waiting for the actual prediction horizon (1 day for swing, 10 days for general, 30 min for scalp). Health metrics will be essentially random noise, not real predictive accuracy. Could trigger false degradation alerts.

### H2. `lgbm_trainer.py:173` — Hardcoded "5min" ignores computed `bar_granularity`
Line 157 correctly computes `bar_granularity` from preset config, but line 173 hardcodes `"5min"` in the `get_historical_bars()` call. If used for a scalp preset, wrong bar resolution.

### H3. `lgbm_trainer.py:84` — Directional accuracy inflated by zero-valued predictions
`np.sign(preds) == np.sign(y_test)` counts zero-zero pairs as correct. XGBoost trainer uses `(y_test > 0) vs (preds > 0)` — inconsistent methodology.

### H4. `ensemble_predictor.py:294-335` — `get_feature_importance()` ignores LightGBM
When ensemble has 3 learners, feature importance only blends XGBoost and TFT weights. LightGBM importance is completely ignored.

### H5. `tft_predictor.py:432` — Returns 0.0 if dataloader is empty
If no batches yielded (empty dataset), returns `0.0` silently instead of signaling error.

### H6. `ensemble_predictor.py:246` — Renormalization adds full intercept incorrectly
When LightGBM unavailable with 3-input meta-learner, the intercept (fitted with original weights) is added to renormalized weighted sum, producing biased predictions.

### H7. `theta_provider.py:374` — `"vol"` substring match corrupts data
Column rename `"vol" in cl` matches `implied_volatility`, `volatility`, etc., renaming them to `"volume"`.

### H8. `base_strategy.py:1960,2065` — Naive `datetime.now()` in prediction tracking
Produces local-time timestamps while everything else uses UTC. Impossible to correlate predictions with trades across DST transitions.

### H9. `risk_manager.py:84,119` — PDT window documented as "5 days" but query uses 7 calendar days
Code works (7 calendar days approximates 5 business days) but log messages and docstrings say "5 days", creating confusion. On holiday weeks, may undercount.

### H10. `base_strategy.py:590-596` — Short direction P&L code is dead for options
`direction == "short"` P&L branch at lines 593-594 never executes because all options use `direction: "long"`. Dead code.

### H11. `base_strategy.py:692` — Model override exit defaults to "CALL" for backtest stock trades
`_open_trades` for backtest stocks don't have a `"right"` key, so it defaults to `"CALL"`. Works by accident for long-only but fragile.

### H12. `diagnose_strategy.py:12` — Hardcoded UUID model path
Script is unusable by anyone who hasn't trained the exact model with that UUID.

### H13. `base_features.py:472` — VIX date alignment uses UTC dates while other features use Eastern
Bars between 7-11:59 PM Eastern get next day's UTC date, causing one-day VIX feature misalignment.

### H14. `base_features.py:479,484,490` — VIX features silently all-NaN if column names change
`DataFrame.get()` returns empty Series on missing column; `.map()` produces all NaN without warning.

### H15. `base_features.py:327-333` — Merge could produce row count mismatch
If options data has duplicate dates, merge produces more rows than original index, crashing on index reassignment.

### H16. `main.py:117` — Hardcoded `"v0.3.0"` instead of VERSION constant
Already fixed VERSION in `config.py`, `app.py`, `system.py` — but `main.py` still hardcodes it.

### H17. `risk_manager.py:66-68` — `log_trade_open`/`log_trade_close` don't check `_run_async` return
If async DB operation fails, trade is opened/closed without a DB record. No retry or fallback.

### H18. `trainer.py:697` — False-positive error logging
`_save_to_db()` returns `None` on success, triggering error path that logs "Model saved to disk but DB insert failed" on every successful training run.

### H19. `options_data_fetcher.py:42` — Risk-free rate hardcoded in 3 places
`0.045` appears in `options_data_fetcher.py:42`, `base_features.py:380`, `greeks_calculator.py:199`. Should be one config constant.

### H20. `Dashboard.tsx:488` — Hardcoded degradation threshold `45`
The literal `45` doesn't match the `52%` threshold used in ProfileDetail.tsx:657 or the actual backend config.

### H21. `App.tsx:33` — No 404 catch-all route
Navigating to unknown URLs renders blank content area with no error indication.

### H22. `package.json:18` — `recharts` dependency unused
~400KB added to production bundle for zero benefit.

### H23. `ProfileDetail.tsx:338` — Missing `trainModelType` in useEffect dependency array
Stale closure: effect reads `trainModelType` but doesn't re-run when it changes.

### H24. `StatusBadge.tsx:5-14` — Missing `cancelled` status style
Cancelled trades get the same style as unknown status — no visual distinction.

---

## Tier 3 — MEDIUM (code smell, maintenance issue, edge case bug)

### M1. `swing_features.py:56-60` — RSI duration feature mathematically wrong
Uses cumsum-groupby-cumcount that measures "consecutive bars in zone", not "bars since zone" as the comment and feature name claim.

### M2. `ensemble_predictor.py:491` — `compute_base_features()` called without `bars_per_day`
Meta-learner training uses default `bars_per_day` which may differ from sub-model training value (78 vs 390).

### M3. `scalp_trainer.py:474` — `use_label_encoder=False` is dead parameter in XGBoost 3.0.5
Deprecated in XGBoost 1.6, removed in 2.0. Silently ignored but confusing.

### M4. `trainer.py:489` — `SettingWithCopyWarning` on `train_df[f] = np.nan`
`train_df` may be a view from `dropna()`. Same issue in `lgbm_trainer.py:220`.

### M5. `trainer.py:424` — `datetime.now()` without timezone in `data_end_override` fallback
Mixes naive and potentially aware datetimes.

### M6. `scalp_trainer.py:415` — Stricter NaN handling than XGBoost trainer (undocumented)
Uses `X.notna().all(axis=1)` vs trainer.py's `X.notna().any(axis=1)`.

### M7. `theta_provider.py:71` — CSV detection heuristic misclassifies JSON as CSV
`',' in resp.text.split('\n')[0]` matches JSON responses.

### M8. `options_data_fetcher.py:467` — `.str[:10]` assumes ISO date string format for `created` column

### M9. `general_features.py:44` — `general_momentum_long` can explode to extreme values (no clipping)

### M10. `general_features.py:33` — 50-day SMA needs 3 months of data before producing non-NaN values

### M11. `walk_forward_backtest.py:228-236` — Relies on private Lumibot `_strategy._strategy_tracker` attribute

### M12. `walk_forward_backtest.py:77-80` — Integer division can lose days at end of backtest range

### M13. `lgbm_trainer.py:119-126` — Missing `data_end_override` parameter (incompatible with walk-forward)

### M14. `base_strategy.py:1294-1296` — Dead code TypeError fallback for `predict()` without `sequence`

### M15. `base_strategy.py:647` — DTE floor hardcoded to 3 days instead of config constant

### M16. `base_strategy.py:1499` — Model type name derivation via string manipulation is fragile

### M17. `base_strategy.py:369` — Emergency stop loss permanently disabled if first portfolio value is 0

### M18. `risk_manager.py:252` — Exposure query mixes backtest stock and live option positions

### M19. `base_strategy.py:1451` — `int()` truncation vs `math.floor()` for stock quantity

### M20. `base_strategy.py:1549,1599` — `max_hold` variable read twice from same config

### M21. `liquidity_filter.py:60-61` — Mixed fail-open/fail-closed behavior for OI checks

### M22. `base_features.py:146` — Timezone localization assumes tz-naive = UTC

### M23. `base_features.py:218` — Docstring references `atm_call_bid_ask_pct` but code uses `atm_call_spread_pct`

### M24. `tft_trainer.py:104` — `pl_module` parameter name misleading (receives module, not instance)

### M25. `incremental_trainer.py:531` — `.values` drops feature names, may cause XGBoost warning

### M26. `base_strategy.py:507` — Accesses private `_failure_count` attribute; should use `get_stats()`

### M27. `base_strategy.py:1475-1484` — Backtest stock trades missing keys that option trades have

### M28. `Trades.tsx:281` — Date comparison fragile with timezone suffixes (`'T23:59:59'` < `'Z'`)
Same in `SignalLogs.tsx:276`.

### M29. `Profiles.tsx:248-253` — Setting state inside `mutationFn` (should be `onMutate`)

### M30. `ProfileDetail.tsx:555-840` — Massive duplicated model display code block

### M31. `ProfileDetail.tsx:263-302` — `window.alert()` for training errors (should be toast/inline)

### M32. `ProfileDetail.tsx:920-921` — "Worst Trade" always shows `good={false}` even if positive

### M33. `ProfileDetail.tsx:358` — `window.history.back()` instead of React Router `navigate(-1)`

### M34. `ProfileDetail.tsx:866-868` — Clear logs error silently swallowed

### M35. `System.tsx:527-531` — Unnecessary `(cb as any)` casts bypass typed `CircuitBreakerState`

### M36. `SignalLogs.tsx:139-142` — No "All Profiles" option (inconsistent with Trades page)

### M37. `Dashboard.tsx:251,426`, `System.tsx:661` — Hardcoded "/ 10" max positions

### M38. `Dashboard.tsx:465` — `mb-4` + parent `gap-5` creates inconsistent spacing

---

## Tier 4 — LOW (style, minor improvement)

### L1. `swing_strategy.py`, `general_strategy.py`, `scalp_strategy.py` — Unused `logger` variable
### L2. `base_strategy.py:91` — Inline `import re` in method (unnecessary lazy import)
### L3. `base_strategy.py:256` — Inline `import sqlite3` in method
### L4. `base_strategy.py:498` — Redundant `import json as _json` (already imported at top)
### L5. `risk_manager.py:41` — Type hint should be `Optional[Path]`
### L6. `base_strategy.py:189` — `_cached_5min_bars` name misleading for scalp (holds 1-min bars)
### L7. `base_strategy.py:821` — Hardcoded `bars_per_day` values (390 and 78)
### L8. `base_strategy.py:1482-1484` — Backtest trades don't store `entry_features` in `_open_trades`
### L9. `base_strategy.py:1967-1968` — Prediction history trimming jump from 100 to 50 entries
### L10. Multiple files — `sys.path.insert(0, ...)` pattern throughout codebase
### L11. `trainer.py:37` — Logger name `options-bot.ml.trainer` uses hyphens (unconventional)
### L12. `scalp_trainer.py:332` — Returns `"error"` status vs trainer.py's `"failed"`
### L13. `ensemble_predictor.py:617-619` — Meta-learner trains on 2 inputs only (XGB+TFT), not 3
### L14. `incremental_trainer.py:372` — Unnecessary `import json as _json` alias
### L15. `scalp_trainer.py:563` — `db.row_factory = aiosqlite.Row` set but never used (no SELECT)
### L16. `tft_predictor.py:267-283` — `predict_batch` pads with zeros, producing meaningless predictions
### L17. `alpaca_provider.py:73` — `paper=True` hardcoded, ignores `ALPACA_PAPER` config
### L18. `theta_provider.py:368` — `"high"` substring match can hit `high_ask`, `high_bid` columns
### L19. `vix_provider.py:71,134` — New Alpaca client created on every non-cached fetch
### L20. `options_data_fetcher.py:381` — Cache key ignores DTE parameters
### L21. `options_data_fetcher.py:41` — Timeout (30s) inconsistent with theta_provider.py (60s)
### L22. `base_features.py:44` — Comment says "~25" stock features; actual count is ~44
### L23. `backtest.py:39` — Debug log file created as import side effect
### L24. `backtest.py:96-98` — Default dates hardcoded to 2025
### L25. `diagnose_strategy.py:64` — Hardcoded threshold 1.0% vs config 0.3%
### L26. `alerter.py:83` — Discord-only payload format; Slack would not work
### L27. `alerter.py:103` — `send_alert` returns True before delivery confirmed
### L28. `earnings_calendar.py:28-30` — Dead parameters kept for backward compatibility
### L29. `regime_adjuster.py:19-25` — Default constants duplicate config.py values
### L30. `scalp_features.py:106-108` — Pre-market bars lumped into first time bucket
### L31. `client.ts:31` — Content-Type: application/json sent for GET requests
### L32. `SignalLogs.tsx:472` — `replace('_', ' ')` only replaces first underscore
### L33. `ProfileDetail.tsx:671-673` — `class_distribution` accessed as `any` (metrics type too narrow)
### L34. `ProfileDetail.tsx:42-75` — `TrainingLogs` polls every 3s regardless of training state
### L35. `Trades.tsx:322` — CSV export `<a>` element never appended to DOM (some browsers need it)
### L36. `Profiles.tsx:350` — `created` and `paused` statuses fall through to `bg-muted` instead of named colors
### L37. `SignalLogs.tsx:16-33` — Floating-point keys in `STEP_NAMES` (fragile equality)
### L38. `ProfileForm.tsx:159` — Clicking backdrop closes modal with unsaved changes (no warning)
### L39. `PnlCell.tsx:8` — `value === null` check misses `undefined` (should be `value == null`)
### L40. `theta_provider.py:37-38` — Hardcoded retry constants should use config.py

---

## Recommended Fix Order

**Priority 1 — Fix before live trading (C1-C8, H1-H6):**
These bugs will cause crashes, wrong trades, or data loss in production.

**Priority 2 — Fix before next release (H7-H24, M1-M6):**
Incorrect behavior, stale data, or misleading metrics.

**Priority 3 — Clean up (M7-M38, L1-L40):**
Code quality, maintenance, and UX improvements.
