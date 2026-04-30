# 10 — MODEL TRAINING AUDIT (Phase 4)

## Independent Phase 4 scope
- Full training pipelines: `ml/trainer.py`, `ml/scalp_trainer.py`, `ml/swing_classifier_trainer.py`, `ml/lgbm_trainer.py`, `ml/tft_trainer.py`, `ml/ensemble_predictor.py`.
- Trigger/orchestration: `backend/routes/models.py` train + retrain endpoints.

## Training entrypoints and dispatch
- `POST /api/models/{profile_id}/train` validates profile, model type, Theta reachability, and deduplicates active jobs before spawning model-specific training thread.
- Supported dispatch map in code: `xgboost`, `tft`, `ensemble`, `xgb_classifier`, `lightgbm`, `xgb_swing_classifier`, `lgbm_classifier`.
- `POST /api/models/{profile_id}/retrain` requires existing model, validates type against preset, checks Theta, and spawns incremental retrain thread.

## Pipeline structure (confirmed in source)
- Regressor pipelines (`trainer.py`, `lgbm_trainer.py`): fetch bars → compute features (Theta options + optional VIX) → forward-return target → prepare training set → CV → final fit → save model file → save DB record/update profile.
- Classifier pipelines (`scalp_trainer.py`, `swing_classifier_trainer.py`): same high-level flow plus binary targeting with neutral-band filtering and stride subsampling.
- TFT pipeline (`tft_trainer.py`): sequence dataset build + target scaling + 3-fold CV + final train + save model directory + DB record.
- Ensemble pipeline (`ensemble_predictor.py`): loads sub-models, recomputes features/target, aligns predictions, trains ridge meta-learner, saves model + DB row.

## Sample-count transition evidence (code-level)
- Generic regressor requires minimum training rows (`MIN_TRAINING_SAMPLES=200`) after target/feature filtering.
- Scalp/swing classifiers require `MIN_TRAINING_SAMPLES=500`, then perform neutral exclusion and strided subsampling (`15` scalp, `78` swing).
- TFT reduces training windows via strided/step subsampling with `MAX_TRAIN_WINDOWS=3000` guard.
- Incremental retrain appends `INCREMENTAL_N_ESTIMATORS=100` trees and versions output model with new model_id.

## Phase 4 findings
1. **Training can fail fast by design** when Theta/options data is unavailable (hard requirement in shared feature path).
2. **Data-reduction branches are substantial** (neutral-band drop + stride sampling) and can materially shrink effective sample count.
3. **Runtime success not proven in this phase**: this run audited source logic and contracts; no full end-to-end training job was executed by Codex here.
