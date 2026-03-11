# 10. Model Training Audit

## Model Artifacts on Disk

### 1. ac3ff5ea_scalp_SPY_171859fb.joblib (634,240 bytes)
- **Type**: XGBClassifier (binary: UP/DOWN)
- **Profile**: Spy Scalp (ac3ff5ea)
- **DB Model ID**: 171859fb (active — referenced by profile model_id)
- **Features**: 88 (73 base + 15 scalp)
- **Training data**: 2024-02-09 to 2026-03-10 (16,877 samples after subsample stride=15)
- **Training time**: 104.7 seconds
- **Walk-forward CV accuracy**: 62.7% (5-fold, expanding window)
- **Fold details**:
  - Fold 1: 59.7% (2812 train/2812 val)
  - Fold 2: 62.3%
  - Fold 3: 60.8%
  - Fold 4: 65.5%
  - Fold 5: 65.1%
- **Subsample stride**: 15 bars (every 15th 1-minute bar)
- **Neutral band**: ±0.05% (moves within this band are excluded from training)
- **avg_30min_move**: 0.1108%
- **Class distribution**: 8004 DOWN, 8873 UP (52.6% UP — slight imbalance)
- **Calibrator**: IsotonicRegression (probability calibration)
- **Hyperparameters**: n_estimators=700, max_depth=7, learning_rate=0.063, subsample=0.756, colsample_bytree=0.657, reg_alpha=0.896, reg_lambda=2.454
- **Top features**: gap_from_prev_close (3.4%), intraday_return (2.0%), atm_put_vomma (2.0%), scalp_orb_distance (1.9%)

**LIVE PERFORMANCE**: 47.4% accuracy (9/19 correct) — BELOW 50% random baseline. **Model is degraded.**

### 2. ad48bf20_swing_cls_TSLA_ce4bfaf5.joblib (1,033,928 bytes)
- **Type**: LGBMClassifier (binary: UP/DOWN)
- **Profile**: TSLA Swing Test (ad48bf20)
- **DB Model ID**: ce4bfaf5 (active)
- **Features**: 78 (73 base + 5 swing)
- **Training data**: 2020-02-10 to 2026-03-10 (3,129 samples after subsample stride=78)
- **Training time**: 102.1 seconds
- **Walk-forward CV accuracy**: 78.7% (5-fold)
- **Fold details**:
  - Fold 1: 73.9% (521 train/521 val)
  - Fold 2: 75.6%
  - Fold 3: 81.2%
  - Fold 4: 82.0%
  - Fold 5: 81.0%
- **Subsample stride**: 78 bars (every 78th 5-min bar ≈ 1 per trading day)
- **Neutral band**: ±0.3% (much wider than scalp)
- **avg_daily_move**: 1.868%
- **Class distribution**: 1522 DOWN, 1607 UP (51.4% UP)
- **No calibrator** (unlike scalp model)
- **Top features**: gap_from_prev_close (1048), intraday_return (922), hour_of_day (402)

**LIVE PERFORMANCE**: 0/4 correct (0%) — insufficient data (need 10+ samples)

## Orphaned Model Records (DB only, no file on disk)

### 3. ac3ff5ea_scalp_SPY_8b4987ee.joblib (MISSING)
- **DB Model ID**: 8b4987ee, status=ready
- **Trained**: 2026-03-10 13:24-13:26 (110.7s)
- **Accuracy**: 61.7% (5-fold CV, 8431 samples, stride=30)
- **File does NOT exist on disk** — BUG-002

### 4. ac3ff5ea_scalp_SPY_385f4ea1.joblib (MISSING)
- **DB Model ID**: 385f4ea1, status=ready
- **Trained**: 2026-03-11 00:35-00:36 (68.7s)
- **Accuracy**: 61.5% (5-fold CV, 8439 samples, stride=30)
- **File does NOT exist on disk** — BUG-002

**NOTE**: Models 8b4987ee and 385f4ea1 were likely intermediate training runs whose files were overwritten or deleted when the final 171859fb model was retrained with stride=15 (16,877 samples vs 8,431). The training code may not clean up DB records for superseded models.

## Training Pipeline Observations

1. **Data**: Fetched from ThetaData via options_data_fetcher + Alpaca for intraday bars
2. **Feature engineering**: compute_base_features (73 features) + preset-specific features (scalp: 15, swing: 5)
3. **Target construction**: Binary UP/DOWN based on future return exceeding neutral_band
4. **Subsample stride**: Reduces autocorrelation in training data (stride=15 for scalp 1-min bars = every 15 minutes)
5. **Walk-forward CV**: Expanding window (no lookahead), correct temporal ordering
6. **Hyperparameter tuning**: Optuna optimization (evidenced by non-round hyperparameter values)
7. **Calibration**: Scalp model uses IsotonicRegression; swing model does not

## Potential Issues

1. **Feature leakage risk**: gap_from_prev_close and intraday_return are the top features. These are NOT leaked — they represent the current day's price action relative to previous close. However, they may be noisy for prediction since they describe the present state, not a causal predictor of future direction.

2. **Dead features**: vix_level, vix_term_structure, vix_change_5d were previously identified as 95% NaN. They are still in the feature list but XGBoost handles NaN natively (correct behavior — no imputation needed).

3. **Class imbalance**: Both models have slight UP bias (~52%). scale_pos_weight is set to ~1.02-1.12 in hyperparams — appropriate correction.

4. **Live vs CV accuracy gap**: Scalp model shows 62.7% CV vs 47.4% live — 15 percentage point drop. This could indicate overfitting, market regime change, or simply small live sample size (19 predictions).
