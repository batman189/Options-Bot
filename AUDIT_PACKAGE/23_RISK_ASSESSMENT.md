# 23 — RISK ASSESSMENT

---

## CRITICAL Risks

### RISK-001: 0DTE Theta Cost = 0 Inflates EV (BUG-001)

**Severity**: CRITICAL
**Component**: `ml/ev_filter.py`, EV calculation
**Description**: When DTE=0 (same-day expiry), the theta cost in the EV formula evaluates to zero because `min(max_hold_days, dte)` = `min(1, 0)` = 0. This means the bot calculates EV as if theta decay is free on 0DTE options.
**Impact**: The scalp model (0DTE SPY options) enters trades with inflated EV — e.g., EV=164.9% when it should be much lower after accounting for rapid theta decay. This leads to overaggressive trade entry.
**Evidence**: Trade 8991d423 in `15_NUMERICAL_PIPELINE_TRACES.md` Trace 3
**Likelihood**: Certain (every 0DTE trade is affected)
**Mitigation**: Replace `min(max_hold_days, dte)` with `min(max_hold_days, max(dte, hold_minutes/1440))` to account for intraday theta

### RISK-002: Live Model Accuracy Far Below Training

**Severity**: CRITICAL
**Component**: Scalp model (ac3ff5ea profile)
**Description**: The scalp model shows 31.6% live accuracy (6/19 correct) vs 63.9% training walk-forward CV accuracy. This is worse than a coin flip.
**Impact**: The bot is making trades based on a model that performs worse than random in production. Real money is at risk.
**Evidence**: `AUDIT_PACKAGE/db/system_state.txt` → model_health_ac3ff5ea
**Likelihood**: Certain (measured from real trades)
**Mitigation**: Halt live trading until model is retrained with more data, or implement automatic model degradation halt

### RISK-003: No Feedback Loop (actual_return_pct Always None)

**Severity**: CRITICAL
**Component**: Trade recording pipeline
**Description**: The `actual_return_pct` field in trades is always None. The system cannot compute whether the model's predicted direction was correct for any given trade.
**Impact**: Without feedback, the model health monitoring relies on approximations. The training queue's consumed=0 (BUG-009) means retraining with real outcome data never happens.
**Evidence**: `AUDIT_PACKAGE/db/table_trades.txt` — all 31 trades have actual_return_pct=None
**Likelihood**: Certain
**Mitigation**: Implement actual_return_pct calculation based on underlying price change over prediction horizon

---

## HIGH Risks

### RISK-004: Empty Broker Greeks on 0DTE Options

**Severity**: HIGH
**Component**: Alpaca/Lumibot broker integration
**Description**: Some 0DTE option contracts return theta=0, vega=0, iv=0 from the broker. The fallback `_estimate_delta()` provides a delta estimate but cannot fix theta/vega/iv.
**Impact**: EV calculation uses garbage Greeks, leading to unreliable trade selection. Combined with RISK-001, this double-inflates EV.
**Evidence**: Trade 8991d423 entry_greeks: `{"theta": 0.0, "vega": 0, "iv": 0}`
**Likelihood**: Frequent (occurs on deep OTM 0DTE options)
**Mitigation**: If theta=0 on 0DTE, either reject the contract or estimate theta from time_value/dte

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

### RISK-009: Duplicate/Stale DB File

**Severity**: MEDIUM
**Component**: Data storage
**Description**: Two DB files exist: `data/options_bot.db` (empty, 0 tables) and `db/options_bot.db` (real, 8 tables). If code or config ever references the wrong path, operations silently fail or use empty data.
**Evidence**: Both files exist; only `db/options_bot.db` has tables
**Likelihood**: Low (current code uses correct path)
**Mitigation**: Delete the empty `data/options_bot.db`

### RISK-010: Spread Filter Dead Code

**Severity**: MEDIUM
**Component**: `ml/ev_filter.py`
**Description**: Spread filtering logic exists but never triggers, allowing trades on illiquid options with wide bid-ask spreads.
**Impact**: Real execution slippage from wide spreads not accounted for in EV
**Likelihood**: Moderate (some 0DTE deep OTM options have very wide spreads)
**Mitigation**: Fix spread filter logic to actually reject contracts above max_spread_pct

---

## LOW Risks

### RISK-011: Startup Race Condition

**Severity**: LOW
**Component**: `start_bot.bat`
**Description**: Browser opens before backend is ready to serve requests.
**Impact**: User sees error page briefly; refreshing fixes it.
**Likelihood**: Certain (on every cold start)
**Mitigation**: Add health check wait in start_bot.bat before opening browser

### RISK-012: No Log Rotation

**Severity**: LOW
**Component**: Backtest output files
**Description**: 185+ files accumulate in logs/ directory.
**Impact**: Disk space waste over time
**Likelihood**: Certain (grows with each backtest)
**Mitigation**: Add cleanup script or rotation policy

---

## Risk Summary

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 3 | RISK-001, RISK-002, RISK-003 |
| HIGH | 3 | RISK-004, RISK-005, RISK-006 |
| MEDIUM | 4 | RISK-007, RISK-008, RISK-009, RISK-010 |
| LOW | 2 | RISK-011, RISK-012 |
| **TOTAL** | **12** | |

---

## Verdict

**FAIL** — 3 CRITICAL risks identified that directly impact trading safety and financial outcomes. The system should not be used for live trading with real money until at minimum RISK-001, RISK-002, and RISK-003 are resolved.
