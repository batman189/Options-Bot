# 27 — SINGLE-FILE ISSUES / BLOCKERS / BUGS SUMMARY

This is the consolidated Phase 1–7 list of actionable issues, blockers, and unresolved risks found during the Codex second-opinion audit.

## A) Confirmed or likely code issues (bugs / design risks)

1. **Frontend/backend config drift risk (MAX_TOTAL_POSITIONS hardcoded in UI)**
   - UI hardcodes `MAX_TOTAL_POSITIONS = 10` with a comment that it must match backend config.
   - If backend changes and UI is not updated, behavior and user expectations can diverge.
   - Severity: **Medium**.
   - Evidence: `ui/src/pages/Dashboard.tsx`.

2. **Backtest date-range validation gap in UI**
   - UI requires start/end dates but does not enforce `start <= end` before submit.
   - Invalid ranges can leak to backend and rely on backend-side rejection/handling.
   - Severity: **Low**.
   - Evidence: `ui/src/pages/ProfileDetail.tsx` backtest controls.

3. **Migration exception swallowing in DB setup (`except Exception: pass`)**
   - Broad exception swallowing can hide unexpected migration failures.
   - Can leave schema partially upgraded while startup appears healthy.
   - Severity: **Medium**.
   - Evidence: `backend/database.py` migration blocks.

4. **System status endpoint can present defaults despite subsystem check errors**
   - `/api/system/status` can return aggregate fields that look okay unless caller inspects error metadata.
   - May create false confidence in health dashboards.
   - Severity: **Medium**.
   - Evidence: `backend/routes/system.py` status behavior.

5. **Temporary process-state divergence during crash/restart windows**
   - In-memory registry, `system_state`, and persisted profile status may temporarily disagree under failure/restart timing.
   - Severity: **Low**.
   - Evidence: `backend/routes/trading.py` start/stop lifecycle handling.

6. **Training default mismatch (route defaults to 6 years)**
   - API train route applies `years=6` when no override is provided.
   - This can override expectations from scalp trainer’s internal 2-year default.
   - Severity: **Medium**.
   - Evidence: `backend/routes/models.py` + `ml/scalp_trainer.py`.

7. **Active-job slot can remain stuck on thread start failure**
   - `_active_jobs` is claimed before thread start; no rollback if thread creation/start fails early.
   - Can leave profile in apparent "in progress" state.
   - Severity: **Low**.
   - Evidence: `backend/routes/models.py` async training launch section.

8. **Inference model-type metadata drift at trade logging**
   - Logging derives model type from predictor class-name shortcuts (`scalp`, `swingclassifier`) which may not align with canonical DB model_type taxonomy.
   - Analytics by model family can be skewed.
   - Severity: **Medium**.
   - Evidence: `strategies/base_strategy.py` trade logging path.

9. **Predictor-load fallback may bypass intended model family semantics**
   - On predictor load error, strategy falls back to `XGBoostPredictor` using same model path.
   - If intended model family was non-XGBoost, behavior may silently differ from expected.
   - Severity: **Medium**.
   - Evidence: `strategies/base_strategy.py` predictor initialization.

10. **Model-type detection defaults to XGBoost on metadata lookup failure**
   - `_detect_model_type` fallback is `xgboost` when DB lookup fails.
   - Can misclassify inference path under metadata outages.
   - Severity: **Low**.
   - Evidence: `strategies/base_strategy.py` detect model type logic.

11. **Gate taxonomy ambiguity (`step_stopped_at` overloaded)**
   - Same step numbers represent multiple independent rejection reasons.
   - Step-only aggregates are ambiguous without reason stratification.
   - Severity: **Medium**.
   - Evidence: many `step_stopped_at` callsites in `strategies/base_strategy.py`.

12. **Step 12 doubles as success marker and step field value**
   - Entered-success is encoded via `step_stopped_at=12`, which can distort naive “kill by step” analysis.
   - Severity: **Medium**.
   - Evidence: `strategies/base_strategy.py` entered paths.

## B) Blockers / evidence gaps (audit confidence boundaries)

1. **No full runtime replay performed by Codex in this run**
   - Browser/curl/E2E interactions were not comprehensively replayed here.
   - Blocker type: **Audit evidence gap**.

2. **No fresh live crash/restart drill replayed by Codex**
   - Startup/shutdown/live-loop resilience not fully re-executed in this environment.
   - Blocker type: **Audit evidence gap**.

3. **No full training runtime replay for quantitative validation**
   - Training metrics and exact sample transitions are source-derived in this pass.
   - Blocker type: **Audit evidence gap**.

4. **No full inference runtime replay for output-path validation**
   - Inference outputs and downstream gate effects are source-derived in this pass.
   - Blocker type: **Audit evidence gap**.

5. **Missing local DB for gate-count reproduction**
   - Referenced runtime DB (`options-bot/db/options_bot.db`) absent in this snapshot.
   - Prevented independent replay of claimed historical gate kill-counts.
   - Blocker type: **Data artifact missing**.

6. **Final judgment bounded by absent fresh runtime artifacts**
   - Final confidence is high on structure, partial on operations.
   - Blocker type: **Final-audit boundary**.

## C) Contradictions identified versus prior Claude package

1. **Training default window contradiction**
   - Prior claim implied scalp default of 2 years.
   - Codex found API route default path sets 6 years unless explicitly overridden.

2. **Predictor output contract contradiction**
   - Prior claim described tuple output `(predicted_return, confidence)`.
   - Codex found predictor interface returns a single float (with classifier semantics encoded in that float).

3. **Gate step attribution contradiction (step 8 vs 9)**
   - Prior mapping for implied move / EV gates did not match static code placement in this snapshot.

4. **Runtime-proof framing mismatch**
   - Some prior PASS-style claims were not independently replayable by Codex in this environment.

## D) Net judgment from the consolidated issue set

- **Codebase audit state:** `PARTIAL-PASS` (strong structural coverage; runtime proof incomplete).
- **Claude AUDIT_PACKAGE:** `PARTIAL-PASS` (useful but contains non-trivial contradictions / non-replayable assertions).
- **Codex second-opinion package:** `PASS-WITH-BOUNDARIES` (clear contradiction tracking + explicit confidence limits).

## E) Priority remediation shortlist

1. Remove migration exception swallowing and emit explicit migration failure telemetry.
2. Normalize model_type taxonomy across predictor selection, logging, and analytics.
3. Split gate analytics keys into `(step_stopped_at, stop_reason)` and reserve success marker separately.
4. Add runtime verification scripts/checklists for status endpoints, training defaults, inference contracts, and gate counts.
5. Replace UI hardcoded constants with backend-fed config endpoint values.

