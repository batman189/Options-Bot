# 13 — LOG EVIDENCE

## Evidence Sources

| Source | Location | Size |
|--------|----------|------|
| Training logs (DB) | `AUDIT_PACKAGE/logs/training_logs_dump.txt` | 572 rows |
| Backtest trades | `AUDIT_PACKAGE/logs/backtest_trades.csv` | Lumibot output |
| Backtest tearsheet | `AUDIT_PACKAGE/logs/backtest_tearsheet.csv` | Lumibot output |
| Backtest settings | `AUDIT_PACKAGE/logs/backtest_settings.json` | Lumibot config |
| Signal logs (DB) | `AUDIT_PACKAGE/db/table_signal_logs.txt` | 1705 rows |
| System state (DB) | `AUDIT_PACKAGE/db/system_state.txt` | 6 entries |

**Note**: The application does not write to traditional log files (no .log files found in logs/ directory). All logging goes to:
1. `training_logs` DB table (for training operations)
2. `signal_logs` DB table (for signal/trade pipeline)
3. Console stdout (not persisted)
4. Lumibot output files in `logs/` directory (185 files from backtests)

---

## Training Log Evidence

**Source**: `training_logs` table, 489 total rows (at time of DB evidence capture; 572 at time of dump)

### Sample Training Session (Scalp Model, 2026-03-11)

```
SCALP TRAINING COMPLETE in 600s
======================================================================
  Model ID:  0e9fd3c0-9396-4e52-9c03-f4f003279413
  Model:     options-bot/models/ac3ff5ea-..._scalp_SPY_0e9fd3c0.joblib
  Samples:   54284
  DirAcc:    0.6384
  BalAcc:    0.6394
  Avg move:  0.1379%
======================================================================
```

**Evidence**: `AUDIT_PACKAGE/logs/training_logs_dump.txt` rows 550-572

### Key Training Log Findings

1. **Feature validation step**: Logs confirm 88 features expected and 88 actual
2. **Zero-importance features**: `['vix_level', 'vix_term_structure', 'vix_change_5d']` — 3 features have zero importance (95%+ NaN)
3. **Isotonic calibration**: Applied after training (confirmed in log output)
4. **Model storage**: Confirmed model file path written to DB

---

## Signal Log Evidence

**Source**: `signal_logs` table, 1705 rows

### Pipeline Step Distribution

| Step | Meaning | Count | Evidence |
|------|---------|-------|----------|
| 0 | Market hours check | 98 | step_stopped_at=0 |
| 1 | VIX gate | 145 | step_stopped_at=1 |
| 6 | Confidence threshold | 990 | step_stopped_at=6 |
| 8 | EV/contract filter | 279 | step_stopped_at=8 |
| 9 | Implied move gate | 40 | step_stopped_at=9 |
| 9.5 | Liquidity gate | 122 | step_stopped_at=9.5 |
| NULL | Entered trade | 31 | entered=1 |

**Full breakdown**: See `AUDIT_PACKAGE/14_GATE_KILL_COUNTS.md`

### Sample Signal Log Entry (Kill)

```
id: 3
profile_id: ac3ff5ea-f8a8-4046-af54-d52efe8ec7f4
timestamp: 2026-03-04T11:15:05
symbol: SPY
underlying_price: 684.705
predicted_return: None
step_stopped_at: 1
stop_reason: VIX gate: VIXY=28.55 outside [3.0,7.0]
entered: 0
trade_id: None
```

### Sample Signal Log Entry (Entry)

```
id: 78
profile_id: ac3ff5ea-f8a8-4046-af54-d52efe8ec7f4
timestamp: 2026-03-04T12:31:14
symbol: SPY
underlying_price: 685.395
predicted_return: -1.267
step_stopped_at: None
stop_reason: None
entered: 1
trade_id: 89a74b5b-f598-4f16-8506-cde40e3fa47b
```

**BUG-004 confirmed**: Entered signals have step_stopped_at=None and stop_reason=None.

---

## System State Evidence

**Source**: `system_state` table, 6 rows

| Key | Value Summary |
|-----|---------------|
| trading_ac3ff5ea... | PID 179544, started 2026-03-11T13:59:57, "Spy Scalp" |
| trading_ad48bf20... | PID 22752, started 2026-03-11T13:59:57, "TSLA Swing Test" |
| model_health_ad48bf20... | 51.4% accuracy (19/37), status=warning |
| model_health_ac3ff5ea... | 31.6% accuracy (6/19), status=degraded |
| model_health_backtest | 0 predictions, status=insufficient_data |
| backtest_ac3ff5ea... | completed, 2025-01-01 to 2025-03-01 |

**Key finding**: Scalp model health shows 31.6% live accuracy vs 63.9% training accuracy — confirms **BUG-006**.

---

## Backtest Log Evidence

**Source**: `logs/` directory, 185 files from Lumibot backtests

### Most Recent Backtest (BT_SPY_scalp_2026-03-11_18-38)

Files present:
- `_indicators.csv` — Technical indicators per bar
- `_indicators.html` — Indicator visualization
- `_indicators.parquet` — Binary indicator data
- `_settings.json` — Backtest configuration
- `_tearsheet.csv` — Performance metrics
- `_trade_events.csv` — Trade entry/exit events
- `_trades.csv` — Trade list
- `_trades.parquet` — Binary trade data

**Evidence copied to**: `AUDIT_PACKAGE/logs/backtest_*.{csv,json}`

---

## Log Infrastructure Analysis

| Aspect | Finding | Verdict |
|--------|---------|---------|
| Training logs stored in DB | Yes, via TrainingLogHandler | PASS |
| Signal logs stored in DB | Yes, via base_strategy.py | PASS |
| Console output persisted | No — stdout is ephemeral | FAIL |
| Application error log file | No dedicated error log | FAIL |
| Log rotation | Not implemented | FAIL |
| Log levels | Only INFO in training_logs | FAIL (no DEBUG/WARNING/ERROR segregation) |
| Structured logging | Partial — DB is structured, console is not | PASS (partial) |

---

## Verdict

**FAIL** — Log evidence is available but incomplete:
- Training and signal logs are properly persisted in DB ✓
- Backtest output files exist and contain valid data ✓
- **No persistent application log files** — console output is lost on restart
- **No error-level log segregation** — all training_logs are level=info
- **No log rotation** for backtest output files (185 files accumulating)
