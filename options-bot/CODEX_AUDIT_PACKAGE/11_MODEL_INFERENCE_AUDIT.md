# 11 — MODEL INFERENCE AUDIT (Phase 5)

## Independent scope
- Predictor interfaces and concrete predictor implementations in `ml/*predictor.py`.
- Runtime inference use in `strategies/base_strategy.py`.
- Model loading/discovery path from DB profile model pointer.

## Inference architecture (source-confirmed)
1. Strategy startup loads `model_path` from parameters.
2. `_detect_model_type()` queries DB (`profiles.model_id -> models.model_type`) to choose predictor class.
3. Predictor loads serialized artifact (`.joblib` or TFT model dir wrapper).
4. Each iteration computes latest features and optional sequence frame for TFT/Ensemble.
5. Strategy calls `self.predictor.predict(features, sequence=...)` and routes result through gates.
6. Trade/signal logging records prediction and selected model type metadata.

## Key technical findings
- `ModelPredictor.predict(...)` contract returns **single float**, not tuple.
- Classifier predictors encode direction+confidence into one signed value (`[-1,1]`), then downstream gates use `abs(predicted_return)` for confidence checks.
- TFT/Ensemble paths attempt sequence-based inference; if sequence build fails, strategy proceeds with snapshot-only mode per predictor fallback logic.
- Ensemble predictor includes graceful degradation to XGBoost-only when TFT/LGBM sub-models are unavailable.

## Phase 5 risk findings
1. **Model-type metadata mismatch at trade logging**
   - Strategy writes `entry_model_type` using predictor class-name normalization (e.g., `scalp`, `swingclassifier`) while comments claim DB-model-type compatibility; this can diverge from canonical model_type values (`xgb_classifier`, `xgb_swing_classifier`, `lgbm_classifier`).
2. **Inference fallback bypass risk**
   - If selected predictor load fails at initialize, strategy falls back to `XGBoostPredictor` with the same model path, potentially bypassing intended model family semantics.
3. **Model discovery fallback risk**
   - `_detect_model_type()` defaults to `xgboost` on DB query failure, biasing to regressor inference path when metadata read fails.

## Evidence boundary
- This phase audited source-level inference and consumption paths.
- No live inference replay was executed by Codex in this run.
