# 11. Model Inference Audit

## Inference Pipeline (base_strategy.py → predictor → ev_filter)

### Step-by-step trace from live log:

#### 1. Feature Computation (Entry Step 2-4)
- **Source**: base_strategy.py lines 1107-1282
- **Input**: 500 bars of 1-min data (scalp) or 2000 bars of 5-min data (swing)
- **Process**: compute_base_features() → compute_scalp_features() or compute_swing_features()
- **Output**: DataFrame with 83-96 columns, last row used as feature vector
- **Evidence**: "Features computed — 500 rows, 96 columns" (scalp) or "2000 rows, 83 columns" (swing)
- **NaN handling**: Counts NaN features, rejects if >80%. Replace Inf with NaN. XGBoost handles NaN natively.

#### 2. Model Prediction (Entry Step 5)
- **Source**: base_strategy.py line 1347
- **Call**: `self.predictor.predict(latest_features, sequence=sequence_df)`
- **ScalpPredictor**: Returns signed confidence (-1 to +1). Positive = UP, negative = DOWN.
  - Applies isotonic calibration
  - Returns calibrated probability - 0.5, signed by direction
- **SwingClassifierPredictor**: Similar binary classifier output
- **Evidence**: "Predicted return=0.175%" (scalp) — 0.175 is the signed confidence (17.5%)

#### 3. VIX Regime Adjustment (Entry Step 5.5)
- **Source**: base_strategy.py lines 1388-1414
- **SKIPPED for scalp** (line 1392: `if VIX_REGIME_ENABLED and self.preset != "scalp"`)
- **Applied for swing**: Scales prediction by VIX regime multiplier
- **Evidence**: "Regime=high_vol VIXY=31.75 raw=-0.417% adjusted=-0.292%" (TSLA swing)

#### 4. Confidence Gate (Entry Step 6)
- **Source**: base_strategy.py lines 1417-1459
- **Classifier path**: `confidence = abs(predicted_return)` compared to `min_confidence`
- **Scalp**: min_confidence=0.10, so any prediction with |confidence| >= 0.10 passes
- **Swing**: min_confidence=0.15
- **Evidence**: "confidence 0.175 >= 0.1 threshold" (scalp passes)

#### 5. EV Calculation (Entry Step 9)
- **Source**: base_strategy.py lines 1703-1780, ev_filter.py lines 200-472
- **Classifier EV input**: Uses avg_move directly (NOT confidence * avg_move)
  - Scalp: avg_move = 0.1108%, signed by prediction direction
  - This means ALL scalp predictions use ±0.1108% as the predicted move for EV
- **EV Formula**: `(|delta| * move_$ + 0.5 * |gamma| * move_$² - |theta| * hold_days * accel) / premium * 100`
- **0DTE BUG (BUG-001)**: hold_days_effective = min(max_hold_days=0, dte=0) = 0 → theta_cost = 0

#### Numerical EV Trace for observed trade (SPY $662 PUT):
```
underlying_price = $677.54
predicted_return = -0.1108% (avg_move, signed negative for PUT)
move_dollars = 677.54 * 0.1108 / 100 = $0.7507

delta = -0.135 (fallback estimate — broker returned 0.000)
gamma = 0.015 (fallback constant for near-ATM)
theta = -(677.54 * 0.0007) = -$0.4743 (fallback estimate)
premium = $0.04

expected_gain = |0.135| * 0.7507 + 0.5 * 0.015 * 0.7507² = 0.1013 + 0.0042 = $0.1055
theta_cost = |0.4743| * min(0, 0) * 2.0 = $0.0000  ← BUG-001: always zero!
half_spread = $0.00 (bid/ask unavailable)

ev_pct = (0.1055 - 0.0 - 0.0) / 0.04 * 100 = 263.8%  ← Close to observed 262.8%
```
**The EV is dominated by the zero theta cost.** If theta were properly estimated for 0DTE (e.g., theta = -$2.60 per day as seen in trade #1's entry greeks), the EV would be deeply negative.

#### 6. Liquidity Gate (Entry Step 9.5)
- **Source**: base_strategy.py lines 1789-1835, ml/liquidity_filter.py
- **Process**: Fetches Alpaca options snapshot, checks OI, volume, spread
- **Evidence**: "Liquidity REJECT: daily_volume=1.0 < min=50" (98% of candidates)
- **This gate is the primary safety net preventing bad trades.**

#### 7. Confidence-Weighted Sizing (Entry Step 10)
- **Source**: base_strategy.py lines 1892-1920
- **Process**: Scales quantity from 40% (at min_confidence) to 100% (at 0.50+)
- **Evidence**: "Confidence-weighted sizing: conf=0.177 scale=0.52 qty=15→7" (today's trade)
- **Formula**: `scale = 0.4 + 0.6 * ((conf - min_conf) / (0.50 - min_conf))`

## Model Load Path
1. `base_strategy.py:initialize()` → `_detect_model_type()` queries DB for model_type
2. Model type determines predictor class:
   - "xgb_classifier" → ScalpPredictor
   - "lgbm_classifier" → SwingClassifierPredictor
   - "tft" → TFTPredictor
   - "ensemble" → EnsemblePredictor
   - default → XGBoostPredictor
3. Predictor loads .joblib file: model, feature_names, calibrator, metadata

## Critical Finding: EV Inflation for 0DTE
The entire 0DTE scalp strategy's EV calculation is fundamentally flawed because:
1. `max_hold_days=0` in config → `hold_days_effective=0` → `theta_cost=0`
2. All broker Greeks return 0.000 → fallback estimates are rough
3. Penny options ($0.01-$0.04) amplify any expected_gain into huge EV%
4. The liquidity filter is the ONLY thing preventing systematic losses

**Recommendation**: For 0DTE, theta_cost should use at minimum `hold_days_effective=1` (one intraday period) or calculate intraday theta decay based on actual time-to-expiry.
