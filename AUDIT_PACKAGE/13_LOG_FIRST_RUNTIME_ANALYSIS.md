# 13. Log-First Runtime Analysis

## Latest Runtime Session: 2026-03-11 09:59:57

### Startup Sequence (Evidence: live_20260311_095957.log)
1. **09:59:57.671** — Log file created, version banner: "OPTIONS BOT v0.3.0 — Phase 6 Hardened"
2. **09:59:57.672** — Two processes started: PID 179544 (Spy Scalp) and PID 22752 (TSLA Swing Test)
3. **09:59:57.987** — ThetaData Terminal connection confirmed at 127.0.0.1:25503
4. **09:59:58.017** — Health check: Alpaca ✓, Theta ✓, Database ✓
5. **09:59:58.018** — Profile ad48bf20 loaded: TSLA Swing Test, model=ce4bfaf5 (swing_cls_TSLA)
6. **09:59:58.052** — Profile ac3ff5ea loaded: Spy Scalp, model=171859fb (scalp_SPY)
7. **10:00:07.824** — Lumibot .env loaded, Alpaca websocket streams started
8. **10:00:08.031** — Connected to Alpaca paper trading stream (trade_updates)
9. **10:00:08.879** — Strategy class determined: preset=scalp → ScalpStrategy

### Trading Iteration Pattern
- **Scalp (SPY)**: 1-minute iterations (sleeptime="1M")
- **Swing (TSLA)**: 5-minute iterations (sleeptime="5M")
- **Iteration count today**: 49 iterations observed for scalp in the log tail

### Entry Decision Flow (Evidence: 924 "ENTRY STEP" messages)

#### Typical Scalp Iteration (10:01:02 — 10:01:32):
```
10:01:02.561 ENTRY STEP 1 OK: SPY price=$679.31
10:01:03.507 ENTRY STEP 1.5 OK: Volatility regime acceptable (VIXY=31.75)
10:01:05.027 ENTRY STEP 2 OK: Got 500 bars from Lumibot data store
10:01:06.920 ENTRY STEP 4 OK: Features computed — 2000 rows, 83 columns [BUG: says 2000 but should be 500 for scalp]
10:01:18.064 ENTRY STEP 5 OK: Predicted return=0.175%
10:01:18.064 ENTRY STEP 6 OK: confidence 0.175 >= 0.1 threshold
10:01:18.099 ENTRY STEP 8.5 SKIP (N/A): Implied move gate not applicable for classifier
10:01:18.293 ENTRY STEP 8.7 OK: No earnings in hold window
10:01:18.295 ENTRY STEP 9: Classifier EV input: avg_move=0.1108% x sign=+1 = +0.1108%
10:01:31.220 ENTRY STEP 9 OK: CALL $692.0 exp=2026-03-11 EV=1246.2% premium=$0.01
10:01:32.024 ENTRY STEP 9.5 SKIP: Liquidity reject — daily_volume=1.0 < min=50
```

**Key Observations**:
- EV scan takes ~13 seconds (13.0s from step 9 to completion) — SLOW
- Bot consistently finds CALL $692 when SPY is $679 — that's $13 OTM (1.9%)
- EV of 1246% on a $0.01 option is unrealistic — BUG-001 (theta=0 for 0DTE)
- Liquidity filter saves the bot from entering bad trades (volume=1)

### Signal Log Distribution (DB Evidence)

| Stop Step | Stop Reason | Count |
|-----------|-------------|-------|
| 6 | confidence < 0.6 threshold | 164 |
| 0 | Scalp equity gate: <$25K | 63+35=98 |
| 9 | No contract meets EV threshold | 39 |
| 9.5 | Liquidity reject (volume < 50) | 34 |
| 6 | Various confidence < 0.1 | ~150 |
| 1 | VIX gate outside range | 25 |

**164 rejections at "confidence < 0.6"** — This is from the TSLA Swing profile (min_confidence=0.15 in DB, but signal logs show "0.6 threshold"). This indicates the swing profile was running with a different min_confidence at some point (likely before the DB config was updated).

### Trade Outcomes (3 Total Trades)

| Trade | Direction | Entry | Exit | PnL | Reason |
|-------|-----------|-------|------|-----|--------|
| 89a74b5b | PUT $680 0DTE | $0.21 | $0.26 | +$75 (+24%) | profit_target |
| b9e4d874 | PUT $678 0DTE | $0.15 | $0.00 | -$225 (-100%) | expired_worthless |
| 8991d423 | PUT $666 0DTE | $0.08 | $0.08 | $0.00 (0%) | max_hold |

**Net PnL: -$150.00** across 3 trades.

### Performance Timing
- Total iteration time: typically 14-20 seconds for scalp (unacceptable for 1M sleeptime)
- EV scan is the bottleneck: ~13 seconds scanning 175+ contracts
- Feature computation: ~0.12 seconds
- Prediction: ~0.003 seconds

**ISSUE**: With 1-minute sleeptime and 14-20 second iteration, the bot uses 25-33% of its time budget on each iteration. Market conditions can change significantly in this time.

### Greeks Fallback Evidence
```
11:23:08,607 | Greeks fallback: 660.0 PUT — broker delta=0.0000, estimated delta=-0.102
11:23:08,692 | Greeks fallback: 661.0 PUT — broker delta=0.0000, estimated delta=-0.118
... (50 more contracts)
11:23:14,964 | Greeks fallback: 707.0 PUT — broker delta=0.0000, estimated delta=-0.994
```
**ALL broker deltas are 0.0000** for the entire PUT chain. The fallback Black-Scholes estimator is doing ALL the work. Broker Greeks are completely non-functional for this data.

### Circuit Breaker States
- Theta circuit breaker: CLOSED (no failures logged)
- Alpaca circuit breaker: not implemented ("closed" hardcoded)
- No auto-pause events (consecutive errors = 0)

### Model Health
- **Scalp**: 9/19 correct (47.4%) — status "warning"
- **Swing**: 0/4 correct — status "insufficient_data" (need 10+ samples)
