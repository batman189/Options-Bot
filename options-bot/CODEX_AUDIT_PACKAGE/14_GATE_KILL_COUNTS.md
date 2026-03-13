# 14 — GATE / KILL COUNTS (Phase 6)

## Evidence mode in this phase
- **Code-derived gate inventory only** from `strategies/base_strategy.py` and `ml/ev_filter.py`.
- No local runtime DB (`options-bot/db/options_bot.db`) exists in this snapshot, so kill **counts** are not reproducible by Codex in this run.

## Code-level gate map (independent)

| step_stopped_at | Gate family (source) | Kill condition shape |
|---:|---|---|
| 0 | Auto-pause / scalp equity / emergency paths | Early iteration safety blocks before model inference |
| 1 | Price/VIX gate | Price unavailable or volatility regime rejection |
| 2 | Historical bars availability | Insufficient/None/empty bars from data source |
| 4 | Feature pipeline quality | feature compute failure / empty features / >80% NaN |
| 5 | Predictor execution | prediction exception or NaN/Inf prediction |
| 6 | Confidence / min-move gate | low confidence (classifiers) or predicted move below threshold |
| 7 | Contract-chain availability path | no chain / no valid expirations pre-EV |
| 8 | Risk + implied-move checks | PDT/risk block and implied-move gate conditions |
| 8.7 | Earnings blackout gate | earnings date intersects hold window |
| 9 | EV scan + theta circuit breaker | circuit breaker open / EV scan error / no candidate meets EV |
| 9.5 | Liquidity gate | OI/volume/spread liquidity rejection |
| 9.7 | Portfolio Greeks gate | delta exposure constraint rejection |
| 10 | Composite risk check | PDT/position/exposure/daily-limit/sizing blocked |
| 12 | Success path marker | entered signal recorded (`entered=true`) |

## Machine-generated code evidence
- `json/phase6_gate_points.json` contains extracted `step_stopped_at` callsites and in-code occurrence counts per step value.
- These are **not runtime frequencies**; they are static callsite counts.

## Phase 6 judgment
- Gate topology is richer than a simple linear 0→1→6→8→9→9.5 flow.
- Some step values are overloaded across multiple branch reasons (not one gate = one reason).
- Runtime kill-count claims remain unproven by Codex in this run due missing local DB evidence.
