# 15 — NUMERICAL PIPELINE TRACES (Phase 4)

## Trace 1 — Regression target math (`ml/trainer.py` / `ml/lgbm_trainer.py`)
- Forward return target:
  - `target_pct = ((close[t+h] / close[t]) - 1) * 100`
- Sample availability effect:
  - Last `h` bars have no forward target and are dropped.

## Trace 2 — Classifier target construction (`ml/scalp_trainer.py` / `ml/swing_classifier_trainer.py`)
- Compute forward return percentage.
- Apply neutral band:
  - if return < `-band`: class 0
  - if return > `+band`: class 1
  - else: `NaN` (neutral)
- Drop neutral rows, then subsample by stride:
  - scalp stride = 15
  - swing stride = 78

## Trace 3 — Incremental retraining (`ml/incremental_trainer.py`)
- Builds new-data feature/target frame, filters rows, then warm-start fits XGBoost with prior booster.
- Adds exactly `INCREMENTAL_N_ESTIMATORS = 100` trees in configured path.
- Produces new versioned model artifact and DB row, then updates profile model pointer.

## Trace 4 — TFT window reduction (`ml/tft_trainer.py`)
- Sequence windows generated from continuous bars, then loader caps effective window count through step-based subsampling and `MAX_TRAIN_WINDOWS` guard.
- Numerical implication: optimization/runtime is bounded, but representative coverage depends on subsampling step.

## Proven vs not proven
- Proven: formulas and thresholds above from source.
- Not proven in this phase: empirical sample counts and fold metrics on this environment at runtime.

## Trace 5 — Inference value semantics
- Regressors: `predicted_return` is direct forward-return percent estimate.
- Classifiers: predictor output is signed confidence in `[-1,1]`.
  - downstream confidence gate uses `abs(predicted_return)`.
  - EV path converts classifier output to signed `avg_move` magnitude once confidence gate is passed.
- This mixed semantic requires consumers to branch by model type when interpreting `predicted_return`.

## Phase 6 numerical traces

### Trace 6 — Implied-move gate arithmetic
- Gate compares predicted move magnitude to implied-move ratio threshold:
  - `abs_predicted_pct < implied_move_ratio_min * implied_move_pct` ⇒ reject.

### Trace 7 — EV contract scoring (`ml/ev_filter.py`)
- Predicted move dollars: `move = underlying_price * abs(predicted_return_pct) / 100`
- Expected gain: `abs(delta)*move + 0.5*abs(gamma)*move^2`
- Theta hold-days floor: `hold_days_effective = max(min(max_hold_days, dte), 30/1440)`
- Theta cost: `abs(theta) * hold_days_effective * theta_accel`
- EV%: `((expected_gain - theta_cost) / premium) * 100`

### Trace 8 — Confidence-weighted sizing (classifier path)
- For classifier models after risk check:
  - `scale = 0.4 + 0.6 * min((conf - min_conf) / (0.50 - min_conf), 1.0)`
  - `scaled_qty = max(1, int(base_qty * scale))`
- This reduces position size near confidence threshold and reaches full size at confidence ≥ 0.50.
