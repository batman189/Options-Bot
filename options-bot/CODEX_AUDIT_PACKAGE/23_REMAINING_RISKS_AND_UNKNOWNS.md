# 23 — REMAINING RISKS AND UNKNOWNS (Phase 7)

## High-priority unresolved risks
1. **Runtime evidence gaps remain material**
   - Codex did not replay full runtime E2E/browser/curl/training/inference scenarios in this environment.
   - Several prior claims (especially exact kill-counts and performance metrics) remain unverified by Codex runtime replay.

2. **Gate analytics ambiguity risk**
   - `step_stopped_at` is overloaded across multiple branch reasons and includes entered marker step `12`.
   - Any downstream KPI relying on step-only aggregation is likely lossy/misleading without `stop_reason` stratification.

3. **Model-type metadata consistency risk**
   - Trade logging uses class-name derived model labels that may drift from canonical DB model type taxonomy.
   - Analytics slices by model type can be skewed.

4. **Fail-open and fallback behavior can mask degraded operation**
   - System/status endpoints and several strategy gates allow continuation under data/provider failure conditions.
   - This improves availability but can reduce observability of degraded model/data quality.

## Medium-priority unknowns
- Exact current runtime distribution of gate kills in the present snapshot (local DB missing).
- Current real-world calibration quality / drift of classifier confidence in live operation.
- Process watchdog behavior under sustained crash/restart loops in production-like conditions.

## What would resolve these unknowns
- Fresh runtime replay package in current snapshot with:
  - DB dumps (`signal_logs`, `trades`, `system_state`),
  - end-to-end API/browser traces,
  - training + inference run logs,
  - reproducible SQL for gate counts and stop_reason breakdown.
