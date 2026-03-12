# 23 — RISK ASSESSMENT

---

## CRITICAL Risks

### RISK-001: 0DTE Theta Cost = 0 Inflates EV (BUG-001) — RESOLVED

**Severity**: CRITICAL
**Component**: `ml/ev_filter.py`, EV calculation
**Description**: When DTE=0 (same-day expiry), the theta cost in the EV formula evaluated to zero because `min(max_hold_days, dte)` = `min(1, 0)` = 0.
**Status**: **FIXED** — `hold_days_effective` now floors at 30 minutes (`max(min(max_hold_days, dte), 30/1440)`) so 0DTE scalps always incur theta cost.

### RISK-002: Live Model Accuracy Far Below Training

**Severity**: CRITICAL
**Component**: Scalp model (ac3ff5ea profile)
**Description**: The scalp model shows 31.6% live accuracy (6/19 correct) vs 63.9% training walk-forward CV accuracy. This is worse than a coin flip.
**Impact**: The bot is making trades based on a model that performs worse than random in production. Real money is at risk.
**Evidence**: `AUDIT_PACKAGE/db/system_state.txt` → model_health_ac3ff5ea
**Likelihood**: Certain (measured from real trades)
**Mitigation**: Halt live trading until model is retrained with more data, or implement automatic model degradation halt

### RISK-003: No Feedback Loop (actual_return_pct Always None) — RESOLVED

**Severity**: CRITICAL
**Component**: Trade recording pipeline
**Description**: The `actual_return_pct` field in trades was always None and the training queue was never consumed.
**Status**: **FIXED** — BUG-011: `actual_return_pct` now computed as underlying stock return `(exit - entry) / entry * 100`. BUG-009: `consume_pending_samples()` function added to `feedback_queue.py`.

---

## HIGH Risks

### RISK-004: Empty Broker Greeks on 0DTE Options — RESOLVED

**Severity**: HIGH
**Component**: Alpaca/Lumibot broker integration
**Description**: Some 0DTE option contracts returned theta=0, vega=0, iv=0 from the broker. The fallback path did not estimate theta.
**Status**: **FIXED** (BUG-010) — When `abs(delta) >= 0.05` and `theta == 0` and `dte <= 7`, theta is now estimated as `-(underlying_price * 0.003)` for 0DTE or `-(underlying_price * 0.0007)` for longer DTE.

### RISK-005: No Position Size Limits Per Account

**Severity**: HIGH
**Component**: Trade entry logic
**Description**: The quantity calculation uses confidence-weighted sizing but there's no hard cap on position size relative to account equity. The equity gate ($25,000 minimum) only checks total equity, not per-trade exposure.
**Impact**: A single bad trade could represent a large fraction of account value
**Evidence**: Trade 89a74b5b: 15 contracts × $0.21 × 100 = $315 (0.6% of $50K); but if option premium were higher, no cap prevents larger positions
**Likelihood**: Moderate
**Mitigation**: Add max_position_pct config (e.g., max 5% of equity per trade)

### RISK-006: PDT Compliance Risk

**Severity**: HIGH
**Component**: Day trade tracking
**Description**: The system tracks day trades (`was_day_trade` field) but the PDT check may not prevent 4+ day trades in a 5-day window for accounts under $25K.
**Evidence**: 3 of 4 live trades are `was_day_trade=1`, all on the same day (2026-03-04 and 2026-03-11)
**Likelihood**: Moderate (account is above $25K currently)
**Mitigation**: Verify PDT enforcement logic in base_strategy.py; add hard block if day_trade_count >= 3 in rolling 5 days

---

## MEDIUM Risks

### RISK-007: No Circuit Breaker on Consecutive Losses

**Severity**: MEDIUM
**Component**: Trading strategy
**Description**: While there's an emergency stop loss (portfolio drawdown), there's no circuit breaker for consecutive losing trades.
**Impact**: The bot could make many small losing trades rapidly
**Evidence**: Trade 2 (b9e4d874) entered 2 minutes after Trade 1 — both on same day
**Likelihood**: Moderate
**Mitigation**: Add max_consecutive_losses config parameter

### RISK-008: Training Data Quality (NaN Features)

**Severity**: MEDIUM
**Component**: Feature engineering, model training
**Description**: 3 features (vix_level, vix_term_structure, vix_change_5d) are 95%+ NaN. While XGBoost handles NaN natively, these features contribute zero to the model.
**Evidence**: Training logs show "Zero-importance features (3): ['vix_level', 'vix_term_structure', 'vix_change_5d']"
**Likelihood**: Certain
**Mitigation**: Remove dead features or fix data source

### RISK-009: Duplicate/Stale DB File — RESOLVED

**Severity**: MEDIUM
**Component**: Data storage
**Description**: Two DB files existed: `data/options_bot.db` (empty) and `db/options_bot.db` (real).
**Status**: **FIXED** (BUG-007) — Empty `data/options_bot.db` deleted from disk.

### RISK-010: Spread Filter Dead Code — RESOLVED

**Severity**: MEDIUM
**Component**: `ml/ev_filter.py`
**Description**: Spread filtering logic existed but never triggered (bid/ask hardcoded to None).
**Status**: **FIXED** (BUG-003) — Dead spread filter code removed entirely. The separate `liquidity_filter` post-scan still operates.

---

## LOW Risks

### RISK-011: Startup Race Condition — RESOLVED

**Severity**: LOW
**Component**: `start_bot.bat`
**Description**: Browser opened before backend was ready to serve requests.
**Status**: **FIXED** (BUG-008) — `start_bot.bat` rewritten: Python runs in foreground, browser opens via background `cmd /c` with 5-second delay.

### RISK-012: No Log Rotation

**Severity**: LOW
**Component**: Backtest output files
**Description**: 185+ files accumulate in logs/ directory.
**Impact**: Disk space waste over time
**Likelihood**: Certain (grows with each backtest)
**Mitigation**: Add cleanup script or rotation policy

---

## Risk Summary

| Severity | Open | Resolved | IDs (Open) |
|----------|------|----------|------------|
| CRITICAL | 1 | 2 | RISK-002 |
| HIGH | 2 | 1 | RISK-005, RISK-006 |
| MEDIUM | 2 | 2 | RISK-007, RISK-008 |
| LOW | 1 | 1 | RISK-012 |
| **TOTAL** | **6 open** | **6 resolved** | |

Resolved: RISK-001, RISK-003, RISK-004, RISK-009, RISK-010, RISK-011

---

## Verdict

**PASS (conditional)** — 6 of 12 risks resolved via code fixes. 1 CRITICAL risk remains open (RISK-002: live model accuracy 31.6%). The system should not be used for live trading with real money until model accuracy is validated above 50% baseline on a larger sample (50+ predictions). All code-level bugs that inflated EV and broke the feedback loop have been fixed.
