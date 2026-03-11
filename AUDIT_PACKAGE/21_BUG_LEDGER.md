# 21 — Bug Ledger (Zero-Omission Audit)

Generated: 2026-03-11
Auditor: Claude Opus 4.6

---

## Summary

| ID       | Severity | Title                                          | Verdict     |
|----------|----------|-------------------------------------------------|-------------|
| BUG-001  | CRITICAL | 0DTE EV theta_cost is always zero               | CONFIRMED   |
| BUG-002  | HIGH     | Orphaned model DB records (missing .joblib)      | CONFIRMED   |
| BUG-003  | HIGH     | Spread filter is dead code                       | CONFIRMED   |
| BUG-004  | HIGH     | Signal logs: step_stopped_at=NULL for entries     | CONFIRMED   |
| BUG-005  | MEDIUM   | Fallback Greeks use rough hardcoded constants     | CONFIRMED   |
| BUG-006  | MEDIUM   | Live accuracy 31.6% vs training 62.7%            | CONFIRMED   |
| BUG-007  | LOW      | Duplicate empty DB file at data/options_bot.db    | CONFIRMED   |
| BUG-008  | LOW      | start_bot.bat opens browser before backend ready  | CONFIRMED   |
| BUG-009  | MEDIUM   | Feedback queue never consumed                     | CONFIRMED   |
| BUG-010  | MEDIUM   | Entry Greeks theta=0 vega=0 iv=0 on some trades   | CONFIRMED   |
| BUG-011  | HIGH     | actual_return_pct never written to trades table    | CONFIRMED   |

**11 / 11 CONFIRMED**

---

## BUG-001 (CRITICAL) — 0DTE EV theta_cost is always zero

**File:** `options-bot/ml/ev_filter.py`, lines 409-410

**Code:**
```python
hold_days_effective = min(max_hold_days, dte)   # line 409
theta_cost = abs(theta) * hold_days_effective * theta_accel  # line 410
```

**Problem:** When `dte=0` (0DTE options, the scalp model's entire universe), `min(max_hold_days, 0) = 0`, so `theta_cost = 0` regardless of the actual theta value. Theta decay is the largest cost component of short-dated options, and zeroing it out inflates EV by the full theta amount.

**Evidence:** Trade 8991d423 entered with `entry_ev_pct=164.9` on a $0.08 contract. A 165% EV on an 8-cent far-OTM 0DTE put is physically unrealistic. The artificially zero theta cost explains the inflated EV.

**Impact:** Every 0DTE trade gets its EV overstated. The EV filter cannot reject theta-expensive 0DTE contracts. The min_ev_pct gate becomes meaningless for 0DTE.

**Suggested fix:**
```python
# For 0DTE, theta cost should cover intraday decay.
# Theta is quoted per calendar day; use a fraction (e.g., 0.5 for half-day hold).
hold_days_effective = min(max_hold_days, dte) if dte > 0 else 0.5
```

**Verdict: CONFIRMED**

---

## BUG-002 (HIGH) — Orphaned model DB records (missing .joblib files)

**File:** Database `models` table; disk `options-bot/models/`

**Evidence from `AUDIT_PACKAGE/db/orphan_check.txt`:**
```
Model ID: 8b4987ee  profile_id: ac3ff5ea  file_on_disk: MISSING
Model ID: 385f4ea1  profile_id: ac3ff5ea  file_on_disk: MISSING

SUMMARY: 2 valid, 2 orphaned out of 4 total models
```

Two model records in the DB reference `.joblib` files that no longer exist on disk. These are old SPY scalp models that were superseded by retraining but never cleaned up.

**Problem:** The `models` table has no `ON DELETE CASCADE` or cleanup logic. When a new model is trained, the old model record stays in the DB with `status='ready'` even after its file is deleted. If any code (e.g., incremental trainer, model listing) tries to load one of these phantom records, it will fail.

**Impact:** Stale model records pollute the models list in the UI. Any attempt to load an orphaned model at runtime would raise a FileNotFoundError. The incremental trainer explicitly checks `Path(existing_model_path).exists()` and would return an error, but profile could be stuck referencing a dead model_id.

**Suggested fix:**
- Add a startup sweep in `init_db()` that marks models as `status='orphaned'` if their `file_path` does not exist on disk.
- When a new model is saved, set the previous model's status to `superseded`.

**Verdict: CONFIRMED**

---

## BUG-003 (HIGH) — Spread filter is dead code

**File:** `options-bot/ml/ev_filter.py`, lines 356-374

**Code:**
```python
bid = None          # line 356
ask = None          # line 357

if bid is not None and ask is not None and bid > 0 and ask > 0:  # line 359
    mid = (bid + ask) / 2.0            # NEVER REACHED
    spread_ratio = (ask - bid) / mid   # NEVER REACHED
    if spread_ratio > max_spread_pct:  # NEVER REACHED
        ...
        contracts_skipped_spread += 1
        continue
    premium = mid
else:
    # Quote unavailable - use last price already fetched
    premium = option_price             # ALWAYS TAKEN
```

**Problem:** `bid` and `ask` are hardcoded to `None` on lines 356-357. The `if` condition on line 359 can never be `True`. The entire spread filtering block is unreachable. Similarly, the `half_spread` calculation on lines 415-417 is also dead (same `bid`/`ask` are still `None`).

The code comment on line 355 acknowledges the issue: "Lumibot doesn't provide a get_quote() method, so bid/ask are not available in-scanner." However, the parameter `max_spread_pct` is still accepted and logged, giving the false impression that spread filtering is active.

**Impact:** Illiquid contracts with wide bid-ask spreads are never rejected by the EV scanner. The actual spread cost is always zero in EV calculations, overstating EV for illiquid options. A separate `liquidity_filter` post-scan exists but runs after EV scoring.

**Suggested fix:** Either implement bid/ask retrieval (e.g., via Alpaca snapshot API inline) or remove the dead code and the `max_spread_pct` parameter to avoid false confidence.

**Verdict: CONFIRMED**

---

## BUG-004 (HIGH) — Signal logs: step_stopped_at=NULL for entered trades

**File:** `options-bot/strategies/base_strategy.py`, lines 1998-2003

**Code:**
```python
self._write_signal_log(
    underlying_price=underlying_price,
    predicted_return=predicted_return,
    entered=True,
    trade_id=trade_id,
)
```

**Problem:** When a trade is successfully entered, `_write_signal_log` is called without `step_stopped_at` or `stop_reason`. These default to `None` per the function signature (line 1018-1019). The schema comment in `backend/schemas.py` line 290 says `"1-12 matching entry logic steps; None if entered"`, treating NULL as the success indicator.

**Evidence from `AUDIT_PACKAGE/db/gate_kill_queries.txt`:**
```
step_stopped_at  cnt
None  4       <-- These are the 4 entered trades
0  98
1  145
6  978
...
```

The 4 rows with `step_stopped_at=None` correspond exactly to the 4 rows with `entered=1`. So `None` is being used as a sentinel for "trade entered successfully."

**Impact:** Querying for "entries" requires checking `entered=1` rather than a positive step value. The `step_stopped_at` column is semantically ambiguous -- `None` means success rather than "unknown." This makes signal log analytics more fragile (a NULL could also mean the write failed partway). A final step value like `12` (matching "ENTRY STEP 12 OK" in the log) would be cleaner.

**Suggested fix:** Set `step_stopped_at=12` and `stop_reason="entered"` when a trade is placed. This makes every signal log row have an explicit step value.

**Verdict: CONFIRMED**

---

## BUG-005 (MEDIUM) — Fallback Greeks use rough hardcoded constants

**File:** `options-bot/ml/ev_filter.py`, lines 164-197 (`_estimate_delta`)

**Code:**
```python
def _estimate_delta(
    underlying_price, strike, dte, direction,
    risk_free_rate: float = 0.045,   # Hardcoded
    default_vol: float = 0.35,       # Hardcoded
) -> float:
```

Also lines 333-337 (fallback gamma/theta estimates):
```python
gamma = 0.015 if 0.95 <= moneyness <= 1.05 else 0.005
theta = -(underlying_price * 0.0007) if dte > 0 else 0.0
```

**Problem:**
- `risk_free_rate=0.045` is static. The Fed funds rate was ~4.5% in early 2025 but changes over time. This should pull from a live source or at least from config.
- `default_vol=0.35` is a single constant for all underlyings. SPY realized vol is typically 0.12-0.20; TSLA is 0.40-0.60. Using 0.35 for SPY overestimates vol by 75-190%, distorting the delta estimate.
- The gamma/theta fallbacks are rough constants that don't account for moneyness, vol, or DTE.
- When `dte=0`, theta fallback is `0.0` (same root cause as BUG-001 but in the fallback path).

**Impact:** When broker Greeks fail (which happened on trade 8991d423 where entry Greeks show theta=0, vega=0, iv=0), the fallback delta may be reasonable but gamma and theta are rough approximations. Combined with BUG-001, 0DTE fallback theta is always zero.

**Suggested fix:**
- Pull `risk_free_rate` from config or a treasury API.
- Use ATM IV from the options chain (already available as `atm_iv` feature) instead of hardcoded 0.35.
- For 0DTE theta fallback, use a fractional-day estimate instead of 0.0.

**Verdict: CONFIRMED**

---

## BUG-006 (MEDIUM) — Live accuracy 31.6% vs training 62.7%

**File:** N/A (operational metric)

**Evidence from `AUDIT_PACKAGE/curl/EP33_GET_system_model_health.json`:**
```json
{
  "profile_name": "Spy Scalp",
  "model_type": "xgb_classifier",
  "rolling_accuracy": 0.3158,
  "total_predictions": 19,
  "correct_predictions": 6,
  "status": "degraded"
}
```

Training walk-forward CV accuracy: 62.7% (from MEMORY.md).
Live rolling accuracy: 31.6% (6/19 correct) -- worse than coin flip.

**Problem:** The model performs significantly worse in live trading than in walk-forward cross-validation. Possible causes:
1. **Small sample size** -- 19 predictions is not statistically significant (95% CI at n=19: ~13%-55%). May resolve with more data.
2. **Regime shift** -- Model trained on historical data, deployed during a different market regime (VIX=31.75 on trade 8991d423).
3. **Feature distribution drift** -- Live features may be computed differently than training features (e.g., different bar counts, warm-up periods).
4. **BUG-001 interaction** -- The zero theta cost in EV may be causing entries on contracts that should have been rejected, leading to systematic losses.
5. **Label leakage in training** -- Walk-forward CV may still have information leakage through overlapping forward return windows.

**Impact:** The model is actively losing money in live trading. 4 trades, 1 win (profit target), 1 expired worthless (-100%), 1 flat, 1 backtest.

**Suggested fix:**
- Accumulate more live predictions before drawing conclusions (minimum 50-100).
- Compare live feature distributions to training distributions for drift detection.
- Fix BUG-001 first, as inflated 0DTE EV likely caused bad entries.
- Consider a paper-trading period before live deployment of retrained models.

**Verdict: CONFIRMED**

---

## BUG-007 (LOW) — Duplicate empty DB file at data/options_bot.db

**Files:**
- `options-bot/db/options_bot.db` -- Real database (7 tables, all data)
- `options-bot/data/options_bot.db` -- Empty/orphaned database file

**Evidence:**
```
$ ls -la options-bot/db/options_bot.db    # Real DB (has tables)
$ ls -la options-bot/data/options_bot.db  # Empty/orphan
```

Both files exist on disk. The config (`DB_PATH`) points to `db/options_bot.db`. The `data/` copy was likely created by an earlier version of the code or a stale import path.

**Impact:** Low. The empty file wastes negligible disk space but could confuse anyone inspecting the project structure. No code references the `data/` path.

**Suggested fix:** Delete `options-bot/data/options_bot.db`.

**Verdict: CONFIRMED**

---

## BUG-008 (LOW) — start_bot.bat opens browser before backend is ready

**File:** `options-bot/start_bot.bat`

**Code:**
```batch
@echo off
title Options Bot
cd /d "%~dp0"
start "" "http://localhost:8000"          # Opens browser IMMEDIATELY
timeout /t 3 /nobreak >nul               # Waits 3 seconds
start "" "http://localhost:8000/system"   # Opens ANOTHER browser tab
python main.py                            # THEN starts the backend
pause
```

**Problem:** Lines 4-6 open two browser tabs BEFORE `python main.py` (line 7) starts the FastAPI server. The user sees connection-refused errors in the browser. The 3-second timeout on line 5 is between the two browser opens, not between the browser and the server start.

**Impact:** Poor UX on startup. User must manually refresh after the backend finishes loading. Minor since the bot still functions once loaded.

**Suggested fix:**
```batch
@echo off
title Options Bot
cd /d "%~dp0"
start /B python main.py
echo Waiting for backend to start...
:wait_loop
timeout /t 2 /nobreak >nul
curl -s http://localhost:8000/api/health >nul 2>&1 && goto :ready
goto :wait_loop
:ready
start "" "http://localhost:8000"
pause
```

**Verdict: CONFIRMED**

---

## BUG-009 (MEDIUM) — Feedback queue never consumed

**File:** `options-bot/ml/feedback_queue.py` (producer), `options-bot/ml/incremental_trainer.py` (would-be consumer)

**Evidence from `AUDIT_PACKAGE/db/gate_kill_queries.txt`:**
```
consumed distribution (training_queue):
consumed  cnt
0  3
```

All 3 rows in `training_queue` have `consumed=0`. No code ever sets `consumed=1`.

**Analysis of the codebase:**
1. `feedback_queue.py` contains only `enqueue_completed_sample()` -- it writes rows but has no consume function.
2. `incremental_trainer.py` (`retrain_incremental()`) fetches new data directly from Alpaca, NOT from the training queue. It uses date ranges based on `model.data_end_date`, completely ignoring the queue.
3. `backend/routes/system.py` (`get_training_queue_status`) reads the queue count for UI display but never marks rows as consumed.
4. No code in the entire codebase ever executes `UPDATE training_queue SET consumed = 1`.
5. The `TRAINING_QUEUE_MIN_SAMPLES` config threshold is checked in the API response but no code triggers retraining when the threshold is reached.

**Impact:** The feedback loop described in the architecture is incomplete. Trade outcomes are enqueued but never used. The `training_queue` table grows indefinitely. The "Ready for retrain" indicator in the UI is decorative -- clicking it would not consume the queue.

**Suggested fix:**
- Add a `consume_pending_samples()` function to `feedback_queue.py`.
- Wire the incremental trainer to consume from the queue OR remove the queue entirely and rely on date-range-based retraining.
- Add a scheduled job or API endpoint that triggers retraining when `pending_count >= TRAINING_QUEUE_MIN_SAMPLES`.

**Verdict: CONFIRMED**

---

## BUG-010 (MEDIUM) — Entry Greeks theta=0 vega=0 iv=0 on some trades

**File:** `options-bot/ml/ev_filter.py`, lines 313-341 (Greeks retrieval + fallback)

**Evidence from `AUDIT_PACKAGE/db/table_trades.txt`, trade 8991d423:**
```json
"entry_greeks": {"delta": -0.1701, "gamma": 0.015, "theta": 0.0, "vega": 0, "iv": 0}
```

Note: `delta=-0.17` and `gamma=0.015` match the fallback values from `_estimate_delta()` and the hardcoded gamma constant, confirming the broker Greeks failed and the fallback path was taken.

**Code path (ev_filter.py lines 313-337):**
```python
delta = (getattr(greeks, "delta", 0) or 0) if greeks else 0   # Broker returned ~0
# ...
if abs(delta) < 0.05:                     # Triggered
    estimated_delta = _estimate_delta(...)  # Returns -0.17
    delta = estimated_delta
    gamma = 0.015 if 0.95 <= moneyness <= 1.05 else 0.005  # Hardcoded
    theta = -(underlying_price * 0.0007) if dte > 0 else 0.0  # dte=0, so theta=0.0!
```

The fallback path correctly estimates delta but:
- Sets `theta=0.0` for 0DTE (same root cause as BUG-001)
- Does NOT set `vega` or `iv` -- they remain at the broker's garbage values (0)
- The `entry_greeks` dict logged to the trades table preserves these zeros

**Impact:** Trade records show misleading Greeks. Any post-trade analysis relying on entry Greeks (e.g., theta decay attribution, vega exposure reporting) will be wrong for trades where the fallback path was taken.

**Suggested fix:**
- Add vega and IV estimation to the fallback path (vega ~ delta * underlying * sqrt(T) * 0.01; IV from ATM IV feature).
- Fix the `theta=0` for 0DTE in the fallback (fractional day).
- Log a flag in `entry_greeks` indicating fallback was used (e.g., `"fallback": true`).

**Verdict: CONFIRMED**

---

## BUG-011 (HIGH) — actual_return_pct never written to trades table

**File:** `options-bot/risk/risk_manager.py`, lines 589-604 (`log_trade_close`)

**Code:**
```python
await db.execute(
    """UPDATE trades SET
           exit_price = ?, exit_date = ?, exit_underlying_price = ?,
           exit_reason = ?, exit_greeks = ?,
           pnl_dollars = ?, pnl_pct = ?,
           hold_days = ?, was_day_trade = ?,
           status = 'closed', updated_at = ?
       WHERE id = ?""",
    (exit_price, now, exit_underlying_price,
     exit_reason, json.dumps(exit_greeks or {}),
     pnl_dollars, pnl_pct,
     hold_days, 1 if was_day_trade else 0,
     now, trade_id),
)
```

**Problem:** The `UPDATE` statement sets `pnl_pct` (option contract P&L %) but never sets `actual_return_pct` (underlying stock return %). The `actual_return_pct` column exists in the schema (confirmed in `backend/database.py` and visible in the DB dump) but is not included in the UPDATE.

**Evidence from `AUDIT_PACKAGE/db/table_trades.txt`:**
```
Row 1: actual_return_pct: None  (pnl_pct: 23.81)
Row 2: actual_return_pct: None  (pnl_pct: -100.0)
Row 3: actual_return_pct: None  (pnl_pct: 0.0)
Row 4: actual_return_pct: None  (pnl_pct: 0.705)
```

All 4 trades have `actual_return_pct=None`. Meanwhile, the feedback queue (`training_queue`) receives `actual_return_pct=pnl_pct` from `_execute_exit()` line 992 -- this is the OPTION P&L %, not the underlying return %.

**Impact:**
1. The `actual_return_pct` column in trades is permanently NULL, making it impossible to compare predicted vs actual underlying returns for model evaluation.
2. The training queue stores option P&L % (e.g., +23.8%, -100%) as `actual_return_pct`, which is semantically wrong. The model predicts underlying return % (e.g., -1.27%), but the feedback stores option leverage-amplified returns. If the queue were ever consumed for retraining, the target variable would be corrupted.

**Suggested fix:**
1. Calculate `actual_underlying_return_pct = (exit_underlying_price - entry_underlying_price) / entry_underlying_price * 100` in `_execute_exit()`.
2. Add `actual_return_pct = ?` to the `log_trade_close` UPDATE statement.
3. Pass `actual_underlying_return_pct` (not `pnl_pct`) to `enqueue_completed_sample()`.

**Verdict: CONFIRMED**

---

## Cross-Bug Interaction Map

Several bugs amplify each other:

```
BUG-001 (theta=0 for 0DTE) + BUG-003 (dead spread filter) + BUG-010 (fallback theta=0)
    --> Inflated EV on 0DTE options
    --> Entries on contracts that should have been rejected
    --> Contributes to BUG-006 (poor live accuracy)

BUG-011 (wrong actual_return_pct) + BUG-009 (queue never consumed)
    --> If queue is ever consumed, retraining targets will be corrupted
    --> Feedback loop is doubly broken: not consumed AND wrong values

BUG-002 (orphaned models) + no ON DELETE CASCADE
    --> Profile could reference a dead model_id after model files are cleaned up
```

## Priority Ranking for Fixes

1. **BUG-001** (CRITICAL) -- Directly causes money-losing trades on 0DTE
2. **BUG-011** (HIGH) -- Blocks correct feedback loop implementation
3. **BUG-003** (HIGH) -- Allows illiquid contract entries
4. **BUG-004** (HIGH) -- Breaks signal log analytics
5. **BUG-009** (MEDIUM) -- Feedback loop incomplete
6. **BUG-010** (MEDIUM) -- Incorrect entry Greeks
7. **BUG-005** (MEDIUM) -- Inaccurate fallback Greeks
8. **BUG-006** (MEDIUM) -- Symptom of BUG-001/003/010; may improve after fixes
9. **BUG-002** (HIGH) -- Stale DB records, potential runtime error
10. **BUG-008** (LOW) -- UX annoyance
11. **BUG-007** (LOW) -- Cosmetic
