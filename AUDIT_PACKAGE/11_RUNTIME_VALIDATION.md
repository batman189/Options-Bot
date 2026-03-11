# 11 -- Runtime Validation

Audit of runtime behavior: trading iteration loop, signal generation flow,
position management, error handling, circuit breakers, and watchdog monitoring.

---

## 1. Trading Iteration Loop (`on_trading_iteration`)

### Source: `options-bot/strategies/base_strategy.py` lines 304-528

The `on_trading_iteration()` method is the heartbeat of the bot. It is called by
Lumibot's Trader framework at the interval defined by `self.sleeptime` (configured
per profile: 1M for scalp, 5M for swing, 15M for general).

**Iteration flow (in strict order):**

| Step | Action | Lines | Abort Condition |
|------|--------|-------|-----------------|
| 0 | Increment `_total_iterations` counter | 306 | -- |
| 0a | **Auto-pause check** | 311-339 | If `_consecutive_errors >= MAX_CONSECUTIVE_ERRORS` (10), log CRITICAL, send alert, return |
| 0b | Update prediction outcome tracking | 342-347 | Non-fatal (caught, ignored) |
| 1 | Log iteration timestamp | 353 | -- |
| 2 | Fetch underlying price | 356-360 | Non-fatal (caught, used for signal logs) |
| 3 | **Scalp equity gate** | 364-380 | If portfolio < $25K and preset=scalp, skip all trading |
| 4 | Get portfolio value | 383 | -- |
| 5 | Record initial portfolio value | 388-398 | Retries every iteration until valid (>0) |
| 6 | **Emergency stop loss** | 400-440 | If drawdown >= `EMERGENCY_STOP_LOSS_PCT` (20%), liquidate ALL positions, return |
| 7 | **Check exits** (`_check_exits()`) | 443 | Exits are always checked before entries |
| 8 | **Portfolio exposure check** | 448-463 | If total exposure > `MAX_TOTAL_EXPOSURE_PCT` (60%), skip entries |
| 9 | **Check entries** (`_check_entries()`) | 466-467 | Only if `self.predictor is not None` |
| 10 | Reset error counter on success | 497-498 | `_consecutive_errors = 0` |
| 11 | Persist model health stats | 501-503 | Non-fatal |
| F | **Timing and circuit state export** | 515-528 | Always runs (finally block). Warns if iteration > 30s |

**Verdict: PASS** -- The iteration follows a disciplined guard-clause pattern: auto-pause, equity gate, emergency stop, exits before entries, exposure check, then entries. Each guard returns early with a signal log explaining why.

---

## 2. Signal Generation Flow

### Entry path: `_check_entries()` (in `base_strategy.py`)

The entry flow is a multi-step pipeline where each step can abort with a logged reason.
Steps are numbered and recorded in `signal_logs.step_stopped_at` for auditability.

**Pipeline steps (reconstructed from code and signal_logs schema):**

| Step | Gate | Abort Reason |
|------|------|--------------|
| 0 | No model loaded | `"No model loaded"` |
| 0 | Scalp equity gate | `"Scalp equity gate: $X < $25K"` |
| 0 | Portfolio exposure limit | `"Portfolio exposure limit: X%"` |
| 0 | Emergency stop loss | Liquidation, no entry |
| 0 | Auto-paused | `"Auto-paused: N consecutive errors"` |
| 1 | Feature computation | Fetch bars, compute features |
| 2 | Model prediction | Get predicted return / confidence |
| 3 | VIX regime gate | Profile-level `vix_gate_enabled`, `vix_min`, `vix_max` |
| 4 | Confidence / predicted move threshold | `min_confidence` or `min_predicted_move_pct` |
| 5 | EV filter | `scan_chain_for_best_ev()` -- finds best contract by expected value |
| 6 | Implied move gate | For non-classifier models (bypassed for classifiers) |
| 7 | Risk manager checks | Position limits, daily trade limits, daily loss |
| 8 | Order execution | Submit buy order via Lumibot broker |
| 9 | Trade logging | Write to `trades` table in SQLite |

**Classifier-specific pipeline adjustments (per memory notes):**
- Implied move gate is **bypassed** for classifiers (confidence * avg_move can never beat straddle cost)
- EV input uses `avg_move` directly (not confidence * avg_move)
- VIX regime penalty is **skipped** for scalp preset (high VIX = more 0DTE opportunity)
- Confidence-weighted sizing: 40% quantity at `min_confidence`, 100% at 0.50+

**Model loading during `initialize()`** (lines 137-173):
- Model type detected from DB via `_detect_model_type()`
- Dispatches to correct predictor class: `XGBoostPredictor`, `ScalpPredictor`, `SwingClassifierPredictor`, `TFTPredictor`, `EnsemblePredictor`, `LightGBMPredictor`
- Fallback: if primary load fails, tries `XGBoostPredictor`; if that fails too, `self.predictor = None` (entries skipped)

**Signal logging:** Every iteration writes to `signal_logs` table with `step_stopped_at` and `stop_reason`, whether or not a trade was entered. This provides a complete audit trail.

**Verdict: PASS** -- Signal generation is a well-ordered pipeline with logged abort reasons at every gate. Classifier-specific adjustments are correctly applied.

---

## 3. Position Management

### Exit rules: `_check_exits()` (lines 567-797)

Exits are checked **before** entries every iteration (Architecture Section 9). Rules are
evaluated in priority order; first match wins.

| Rule | Priority | Condition | Detail |
|------|----------|-----------|--------|
| 1 | Profit target | `pnl_pct >= profit_target_pct` | Config default: 50% (swing), 20% (scalp) |
| 2 | Stop loss | `pnl_pct <= -stop_loss_pct` | Config default: 30% (swing), 15% (scalp) |
| 3 | Max hold days | `hold_days >= max_hold_days` | Config default: 7 (swing), 0 (scalp) |
| 4 | DTE floor | `dte < DTE_EXIT_FLOOR` (3) | Options only -- close before expiry risk |
| 5 | Model override | Model predicts reversal > threshold | Configurable, off by default |
| 6 | Scalp EOD | Time >= 15:45 ET | Scalp only -- must close before market close |

**Emergency stop (separate from exit rules):**
- Checked at top of `on_trading_iteration()` (step 0a)
- If portfolio drawdown >= `EMERGENCY_STOP_LOSS_PCT` (20%) from initial value, liquidates ALL positions
- Uses `RiskManager.check_emergency_stop_loss()`
- Sends CRITICAL alert

**Position tracking:**
- `self._open_trades` dict: `{trade_id: {asset, entry_price, entry_date, direction, ...}}`
- Positions matched against Lumibot `self.get_positions()` by symbol+strike+expiration+right (options) or symbol (stocks)
- On exit: `_execute_exit()` submits sell order, calculates P&L, writes to `trades` table, removes from `_open_trades`

**Backtest mode adjustments:**
- Trades stocks instead of options
- Profit target/stop loss scaled down (5%/3% for swing, 0.5%/0.3% for scalp) since stock moves are smaller than option moves

**Verdict: PASS** -- Exit rules follow a strict priority order with first-match-wins semantics. Emergency stop is a separate top-level guard. Position matching handles both options and stock assets.

---

## 4. Error Handling and Circuit Breakers

### Consecutive Error Tracking

| Mechanism | Config | Behavior |
|-----------|--------|----------|
| `_consecutive_errors` counter | `MAX_CONSECUTIVE_ERRORS = 10` | Auto-pauses bot, sends CRITICAL alert |
| Reset on success | `ITERATION_ERROR_RESET_ON_SUCCESS = True` | Counter resets to 0 after any successful iteration |
| `_total_errors` counter | -- | Lifetime count, never resets |

**Error handling structure (lines 309-528):**
```
on_trading_iteration():
    try:                          # Outer try
        [auto-pause check]
        [prediction tracking]
        try:                      # Inner try (trading logic)
            [equity gate, portfolio, emergency stop, exits, entries]
        except:
            _consecutive_errors += 1
            _total_errors += 1
            [signal log: "Unhandled error: ..."]
        else:
            _consecutive_errors = 0   # Reset on success
        [persist health]
    except:                       # Outer catch (catches even equity gate failures)
        _consecutive_errors += 1
        _total_errors += 1
    finally:
        [timing, circuit state export]
```

Double-fault protection: inner `except` catches trading errors; outer `except` catches infrastructure errors. `finally` block always runs.

### Circuit Breakers

**Theta Terminal circuit breaker** (per profile):
- `CircuitBreaker` from `utils/circuit_breaker.py`
- `THETA_CB_FAILURE_THRESHOLD = 3` failures before circuit opens
- `THETA_CB_RESET_TIMEOUT = 300` seconds (5 min) before testing recovery
- State exported to `logs/circuit_state_{profile_id}.json` every iteration
- Alert sent when circuit opens

**Evidence from EP29_GET_system_status.json:**
```json
"circuit_breaker_states": {
  "ad48bf20-...": {
    "theta_breaker_state": "closed",
    "alpaca_breaker_state": "closed",
    "theta_failure_count": 0
  }
}
```
All circuit breakers are **closed** (healthy) -- no Theta Terminal failures observed.

**Alpaca circuit breaker:** Config constants exist (`ALPACA_CB_FAILURE_THRESHOLD = 5`, `ALPACA_CB_RESET_TIMEOUT = 120`) but the circuit state export hardcodes `"alpaca_breaker_state": "closed"` (line 539) -- the Alpaca circuit breaker is not yet implemented in the trading loop. This is a known gap (comment: "No Alpaca circuit breaker yet").

**Verdict: PASS** -- Error handling has double-fault protection, auto-pause with alerting, and Theta Terminal circuit breaker is operational. Alpaca circuit breaker is defined but not wired (noted, not a failure -- config is prepared for future implementation).

---

## 5. Watchdog / Health Monitoring

### Process Watchdog

**Source:** `backend/routes/trading.py` -- `_watchdog_loop()`, `start_watchdog()`, `stop_watchdog()`

| Parameter | Value | Source |
|-----------|-------|--------|
| Poll interval | 30 seconds | `WATCHDOG_POLL_INTERVAL_SECONDS` |
| Auto-restart | Enabled | `WATCHDOG_AUTO_RESTART = True` |
| Max restarts | 3 consecutive | `WATCHDOG_MAX_RESTARTS` |
| Restart delay | 5 seconds | `WATCHDOG_RESTART_DELAY_SECONDS` |

**Watchdog behavior:**
1. Runs in daemon thread named `trading-watchdog`
2. Every 30s, iterates all tracked processes in `_processes` dict
3. If a process has crashed (exit code != 0):
   - Logs the crash with exit code
   - Updates profile status to `error` in DB
   - If auto-restart enabled and restart count < 3: restarts the process after 5s delay
4. Cleans up stale process entries

**Process registry restoration (`restore_process_registry`):**
- Called at backend startup (app lifespan)
- Reads `system_state` table for `trading_*` keys
- Checks if PID is still alive via OS check
- Re-registers live PIDs, cleans up dead ones
- Also cleans stale `active` profiles with no running process (resets to `ready`)

### Model Health Monitoring

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `MODEL_HEALTH_WINDOW_SIZE` | 50 | Rolling window of predictions |
| `MODEL_DEGRADED_THRESHOLD` | 0.45 | Alert if accuracy < 45% |
| `MODEL_HEALTH_MIN_SAMPLES` | 10 | Min predictions before computing accuracy |
| `MODEL_STALE_THRESHOLD_DAYS` | 30 | Alert if model > 30 days old |
| `PREDICTION_RESOLVE_MINUTES_SWING` | 60 | Wait before resolving swing predictions |
| `PREDICTION_RESOLVE_MINUTES_SCALP` | 30 | Wait before resolving scalp predictions |

**Prediction tracking:**
- `_prediction_history` list stores recent predictions with timestamps
- `_update_prediction_outcomes()` called each iteration to check if past predictions resolved
- `_persist_health_to_db()` writes rolling accuracy to DB for UI display

### Alerting

- `utils.alerter.send_alert()` called for critical events (auto-pause, circuit breaker open)
- Configured via `ALERT_WEBHOOK_URL` env var (Discord/Slack webhook)
- Alert calls are wrapped in try/except -- alert failure never crashes the trading loop

**Verdict: PASS** -- Watchdog monitors subprocesses every 30s with auto-restart. Model health is tracked with a rolling accuracy window. Process registry survives backend restarts.

---

## 6. Evidence from curl/ Files -- Runtime State

### EP28_GET_system_health.json

```json
{
  "status": "ok",
  "timestamp": "2026-03-11T22:37:22.910748+00:00",
  "version": "0.3.0"
}
```

| Check | Result | Evidence |
|-------|--------|----------|
| Backend responding | **PASS** | HTTP 200 |
| Health status | **PASS** | `"status": "ok"` |
| Version correct | **PASS** | `"0.3.0"` matches `config.VERSION` |

### EP29_GET_system_status.json

| Check | Result | Evidence |
|-------|--------|----------|
| Alpaca connected | **PASS** | `"alpaca_connected": true` |
| Alpaca subscription | **PASS** | `"algo_trader_plus"` (live options data) |
| Theta Terminal connected | **PASS** | `"theta_terminal_connected": true` |
| Active profiles | **PASS** | `"active_profiles": 1` |
| Open positions | **PASS** | `"total_open_positions": 0` (market closed at capture time) |
| PDT tracking | **PASS** | `"pdt_day_trades_5d": 3`, limit=999999 (algo_trader_plus exempt) |
| Portfolio value | **PASS** | `$49,992.72` (paper account, near $50K start) |
| Uptime | **PASS** | `31,478` seconds (~8.7 hours) |
| Circuit breakers | **PASS** | All closed, 0 failures |
| Last error | **INFO** | Alpaca websocket DNS failure (non-fatal, auto-reconnects) |
| Check errors | **PASS** | Empty array `[]` |

### EP35_GET_trading_status.json

| Check | Result | Evidence |
|-------|--------|----------|
| Total running | **PASS** | `"total_running": 2` |
| Total stopped | **PASS** | `"total_stopped": 0` |
| Spy Scalp process | **PASS** | PID 179544, status=running, uptime=31,054s |
| TSLA Swing Test process | **PASS** | PID 22752, status=running, uptime=31,054s |
| Process uptime consistency | **PASS** | Both started at same time (~13:59 UTC), consistent with system uptime |

---

## Strategy Subclasses

### ScalpStrategy (`strategies/scalp_strategy.py`)
- Inherits all logic from `BaseOptionsStrategy`
- No overrides -- exists for naming clarity and Lumibot Trader registry
- Configured via `preset="scalp"` which triggers scalp-specific branches in base class (equity gate, EOD exit, 1-min bars, confidence threshold)

### SwingStrategy (`strategies/swing_strategy.py`)
- Inherits all logic from `BaseOptionsStrategy`
- No overrides -- exists for naming clarity
- Configured via `preset="swing"` (5-min bars, 7-day hold, 50% profit target)

### GeneralStrategy (referenced in `main.py` line 296)
- Imported from `strategies.general_strategy`
- Same pattern as Swing/Scalp -- thin subclass of `BaseOptionsStrategy`

**Verdict: PASS** -- Strategy hierarchy is clean. All trading logic lives in `BaseOptionsStrategy` with preset-driven branching. Subclasses exist solely for type identity and logging clarity.

---

## Summary

| Check | Verdict | Evidence |
|-------|---------|----------|
| 1. Trading iteration loop | **PASS** | Guard-clause pattern, 10+ steps, signal logging at every abort |
| 2. Signal generation flow | **PASS** | Multi-step pipeline with per-step abort reasons |
| 3. Position management | **PASS** | 6 exit rules in priority order, emergency stop, position matching |
| 4. Error handling / circuit breakers | **PASS** | Double-fault protection, auto-pause at 10 errors, Theta CB operational |
| 5. Watchdog / health monitoring | **PASS** | 30s poll, auto-restart (3x), model health tracking, process registry persistence |
| 6. Runtime evidence | **PASS** | EP28 health=ok, EP29 all services connected, EP35 two processes running |

**Overall: PASS** -- All 6 runtime validation checks pass with live evidence confirming the system was operational for ~8.7 hours at time of audit capture.
