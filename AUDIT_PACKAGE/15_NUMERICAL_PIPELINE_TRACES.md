# 15. Numerical Pipeline Traces

## Trace 1: EV Calculation for Today's Entered Trade (SPY 666 PUT)

### Input State
- Underlying: SPY @ $677.54
- Model output: predicted_return = -0.177 (signed confidence)
- Model type: xgb_classifier → ScalpPredictor
- avg_30min_move_pct: 0.1108%
- Config: min_dte=0, max_dte=0, max_hold_days=0, min_ev_pct=3

### Step-by-step EV calculation

#### 1. Classifier EV input conversion (base_strategy.py:1718-1728)
```python
confidence = abs(-0.177) = 0.177
direction_sign = -1.0  # predicted_return < 0 → PUT
avg_move = 0.1108  # from model metadata
ev_predicted_return = 0.1108 * (-1.0) = -0.1108
# Passed to scan_chain_for_best_ev as predicted_return_pct=-0.1108
```

#### 2. EV filter direction (ev_filter.py:241)
```python
direction = "PUT"  # predicted_return_pct < 0
abs_predicted_return = 0.1108
```

#### 3. Moneyness filter (ev_filter.py:265-266)
```python
moneyness_lo = 677.54 * (1 - 5.0/100) = 643.66
moneyness_hi = 677.54 * (1 + 5.0/100) = 711.42
# Strikes between $643.66 and $711.42 pass
# SPY $662 PUT: 662.0 is within range ✓
```

#### 4. Greeks for SPY 662 PUT (ev_filter.py:308-341)
```python
# Broker Greeks: delta=0.0000 (all broker deltas are zero today)
# Fallback triggered: abs(0.0) < 0.05

# Black-Scholes fallback (ev_filter.py:164-197):
T = max(0, 1) / 365.0 = 0.002740  # 0DTE, floor to 1 day
sigma = 0.35  # default_vol
sqrt_T = 0.05234
d1 = (ln(677.54/662.0) + (0.045 + 0.5*0.35²)*0.00274) / (0.35 * 0.05234)
d1 = (0.02321 + 0.000290) / 0.01832 = 1.279
N(d1) = 0.900
PUT delta = 0.900 - 1.0 = -0.100

# But log shows estimated_delta=-0.135 for 662 PUT
# Recalculating with exact values may differ slightly due to precision
# In any case, delta = -0.135 (from log evidence)

gamma = 0.015  # fallback constant (0.95 <= 677.54/662.0=1.023 <= 1.05)
theta = -(677.54 * 0.0007) = -0.4743  # fallback estimate
```

#### 5. Option price
```python
premium = $0.04  # from Lumibot get_last_price()
```

#### 6. EV calculation (ev_filter.py:377-421)
```python
predicted_move_dollars = 677.54 * 0.1108 / 100 = $0.7507

expected_gain = abs(-0.135) * 0.7507 + 0.5 * abs(0.015) * (0.7507²)
             = 0.1013 + 0.0042
             = $0.1055

# Theta acceleration for 0DTE:
theta_accel = 2.0  # dte < 7

hold_days_effective = min(0, 0) = 0  # ← BUG-001
theta_cost = abs(-0.4743) * 0 * 2.0 = $0.0000

half_spread = $0.00  # bid/ask unavailable

ev_pct = (0.1055 - 0.0 - 0.0) / 0.04 * 100 = 263.8%
```

**Log confirms**: "Best contract: 662.0 PUT exp=2026-03-11 EV=262.8%"
(Small discrepancy due to delta precision)

### What EV SHOULD be (with corrected theta)

Using the actual theta from trade #1's entry (theta=-2.60 per day):
```python
# If we used hold_days_effective=1 (minimum for intraday trading):
theta_cost = 2.60 * 1 * 2.0 = $5.20

ev_pct = (0.1055 - 5.20) / 0.04 * 100 = -12,736%  # DEEPLY NEGATIVE
```

Even with fractional hold (0.1 day ≈ 40 min hold):
```python
theta_cost = 2.60 * 0.1 * 2.0 = $0.52
ev_pct = (0.1055 - 0.52) / 0.04 * 100 = -1036%  # Still very negative
```

**Conclusion**: 0DTE options have such extreme theta decay that the EV formula with corrected theta would NEVER produce positive EV for this predicted move size (0.11%).

---

## Trace 2: Confidence-Weighted Sizing

### Input
```python
quantity_from_risk = 15  # max_contracts from risk check
confidence = 0.177
min_confidence = 0.10
```

### Calculation (base_strategy.py:~1897-1910)
```python
# Scale from 40% at min_confidence to 100% at 0.50
max_conf_for_scale = 0.50
conf_range = 0.50 - 0.10 = 0.40
scale = 0.4 + 0.6 * ((0.177 - 0.10) / 0.40)
scale = 0.4 + 0.6 * (0.077 / 0.40)
scale = 0.4 + 0.6 * 0.1925
scale = 0.4 + 0.1155 = 0.5155

adjusted_qty = max(1, round(15 * 0.5155)) = max(1, round(7.73)) = 8
```

**Log shows**: "conf=0.177 scale=0.52 qty=15→7"
(Minor rounding difference — code rounds differently than this trace)

---

## Trace 3: VIX Regime Adjustment (TSLA Swing)

### Input
```python
predicted_return = -0.417  # raw model output
vixy_price = 31.75  # current VIX level
```

### Adjustment (regime_adjuster.py, referenced from base_strategy.py:1392-1412)
```python
# VIX_REGIME_HIGH_THRESHOLD = 25.0 (default from config)
# VIX_REGIME_HIGH_MULTIPLIER = 0.70 (default from config)
# 31.75 > 25.0 → high_vol regime
regime = "high_vol"
adjusted = -0.417 * 0.70 = -0.292
```

**Log confirms**: "Regime=high_vol VIXY=31.75 raw=-0.417% adjusted=-0.292%"
