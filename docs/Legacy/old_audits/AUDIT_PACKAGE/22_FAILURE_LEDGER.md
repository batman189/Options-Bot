# 22 — FAILURE LEDGER

This ledger documents every item in this audit package that received a FAIL verdict, with the specific reason.

---

## API Endpoint Failures

None — all 46 endpoint tests returned valid HTTP responses. See `06_ENDPOINT_MATRIX.csv`.

---

## UI Control Failures

**ALL UI controls are FAIL** — no browser interaction testing was performed.

| Failure ID | Item | Reason |
|-----------|------|--------|
| FAIL-UI-ALL | All controls in 07_UI_CONTROL_MATRIX.csv | No Selenium/Playwright/Cypress tooling available. Cannot click-test, type-test, or submit-test any UI control. |

**Impact**: The audit cannot validate that UI controls function correctly in a browser. API endpoints behind those controls were validated via curl, but the frontend rendering and JavaScript event handling were not tested.

---

## Bug Failures

| Failure ID | Severity | Bug | Impact |
|-----------|----------|-----|--------|
| FAIL-BUG-001 | CRITICAL | 0DTE EV theta=0 | Options expiring today have zero theta cost in EV calculation, inflating EV and causing overaggressive entry |
| FAIL-BUG-002 | HIGH | Orphaned model DB records | Models referencing deleted profiles remain in DB |
| FAIL-BUG-003 | HIGH | Spread filter dead code | Spread filtering logic never executes |
| FAIL-BUG-004 | HIGH | signal_logs step_stopped_at=None for entered trades | Cannot trace which step a successful signal reached |
| FAIL-BUG-005 | MEDIUM | Fallback Greeks rough constants | Black-Scholes fallback uses hardcoded vol=0.35, rate=0.045 |
| FAIL-BUG-006 | MEDIUM | Live accuracy 31.6% vs training 63.9% | Model severely underperforms in production |
| FAIL-BUG-007 | LOW | Duplicate empty DB file | `data/options_bot.db` is empty (0 tables), real DB is at `db/options_bot.db` |
| FAIL-BUG-008 | LOW | start_bot.bat browser opens before backend ready | Race condition in startup script |
| FAIL-BUG-009 | MEDIUM | Feedback queue never consumed | 29 training_queue entries with consumed=0 |
| FAIL-BUG-010 | MEDIUM | Entry Greeks theta=0 vega=0 iv=0 | Broker returns garbage Greeks for some 0DTE contracts |
| FAIL-BUG-011 | HIGH | actual_return_pct always None | Feedback loop cannot compute real vs predicted accuracy per trade |

---

## Log Infrastructure Failures

| Failure ID | Item | Reason |
|-----------|------|--------|
| FAIL-LOG-001 | No persistent application log file | Console output lost on restart |
| FAIL-LOG-002 | No log level segregation | All training_logs are level=info, no DEBUG/WARNING/ERROR |
| FAIL-LOG-003 | No log rotation | 185+ backtest output files accumulating |

---

## Data Integrity Failures

| Failure ID | Item | Reason |
|-----------|------|--------|
| FAIL-DATA-001 | actual_return_pct always None | No trade has the actual underlying return recorded |
| FAIL-DATA-002 | market_vix always None | VIX not recorded on trades |
| FAIL-DATA-003 | market_regime always None | Market regime not recorded on trades |
| FAIL-DATA-004 | exit_features always None | No exit-time features recorded |

---

## Model Performance Failures

| Failure ID | Item | Reason |
|-----------|------|--------|
| FAIL-MODEL-001 | Scalp model live accuracy 31.6% | 6/19 correct, well below 50% random baseline |
| FAIL-MODEL-002 | Swing model accuracy 51.4% | 19/37 correct, barely above random |
| FAIL-MODEL-003 | 3 zero-importance features | vix_level, vix_term_structure, vix_change_5d are dead features |

---

## Summary

| Category | PASS | FAIL | Total |
|----------|------|------|-------|
| API Endpoints | 46 | 0 | 46 |
| UI Controls | 0 | ALL | ALL |
| Bugs | 0 | 11 | 11 |
| Log Infrastructure | 1 | 3 | 4 |
| Data Integrity | 0 | 4 | 4 |
| Model Performance | 0 | 3 | 3 |

**Total FAIL items**: 11 bugs + all UI controls + 3 log issues + 4 data issues + 3 model issues = **21+ distinct failures**
