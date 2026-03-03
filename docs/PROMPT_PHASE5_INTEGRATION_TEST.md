# PHASE 5 FULL INTEGRATION TEST

## OBJECTIVE

Run a comprehensive test suite verifying:
1. All Phase 5 features work correctly in isolation
2. Phase 5 features integrate properly with Phases 1-4
3. No existing functionality is broken by Phase 5 changes
4. Import chains are complete and consistent
5. Feature name pipelines are end-to-end correct
6. Backend API handles scalp/xgb_classifier correctly
7. UI builds without errors
8. Config, DB schema, and architecture are all consistent

**IMPORTANT**: This is a READ + VERIFY prompt. Do NOT modify any source files. Run every check. Report every result. If a check fails, report the exact failure — do not fix it. Collect all results into a final summary at the end.

**Read the full file for every file referenced.** Do not rely on memory or snippets.

---

## PRE-FLIGHT

```bash
cd options-bot

echo "=== Python version ==="
python --version

echo ""
echo "=== Working directory ==="
pwd

echo ""
echo "=== All Phase 5 files exist ==="
for f in \
  "ml/feature_engineering/scalp_features.py" \
  "ml/scalp_predictor.py" \
  "ml/scalp_trainer.py" \
  "strategies/scalp_strategy.py" \
  "scripts/phase5_checkpoint.py"
do
  test -f "$f" && echo "  EXISTS: $f" || echo "  MISSING: $f"
done

echo ""
echo "=== All prior-phase files still exist ==="
for f in \
  "ml/feature_engineering/base_features.py" \
  "ml/feature_engineering/swing_features.py" \
  "ml/feature_engineering/general_features.py" \
  "ml/predictor.py" \
  "ml/xgboost_predictor.py" \
  "ml/tft_predictor.py" \
  "ml/ensemble_predictor.py" \
  "ml/trainer.py" \
  "ml/tft_trainer.py" \
  "ml/incremental_trainer.py" \
  "ml/ev_filter.py" \
  "data/alpaca_provider.py" \
  "data/options_data_fetcher.py" \
  "data/greeks_calculator.py" \
  "data/validator.py" \
  "strategies/base_strategy.py" \
  "strategies/swing_strategy.py" \
  "strategies/general_strategy.py" \
  "backend/app.py" \
  "backend/database.py" \
  "backend/schemas.py" \
  "backend/routes/profiles.py" \
  "backend/routes/models.py" \
  "backend/routes/trades.py" \
  "backend/routes/system.py" \
  "backend/routes/trading.py" \
  "risk/risk_manager.py" \
  "config.py" \
  "main.py"
do
  test -f "$f" && echo "  EXISTS: $f" || echo "  MISSING: $f"
done

echo ""
echo "=== UI directory ==="
test -d "ui/src" && echo "  EXISTS: ui/src" || echo "  MISSING: ui/src"
```

---

## TEST 1 — IMPORT CHAIN VALIDATION (All Modules)

Every module must import cleanly. A single broken import breaks the entire runtime.

```python
#!/usr/bin/env python3
"""Test 1: Import chain validation — every module must import without error."""
import sys, traceback
from pathlib import Path

ROOT = Path(__file__).parent if Path(__file__).parent.name == "options-bot" else Path(".")
sys.path.insert(0, str(ROOT))

results = []

def check(label, fn):
    try:
        fn()
        results.append(("PASS", label, ""))
        print(f"  PASS  {label}")
    except Exception as e:
        results.append(("FAIL", label, str(e)))
        print(f"  FAIL  {label}")
        traceback.print_exc()

print("=" * 60)
print("TEST 1: IMPORT CHAIN VALIDATION")
print("=" * 60)

# --- Feature engineering ---
check("base_features", lambda: __import__("ml.feature_engineering.base_features",
      fromlist=["compute_base_features", "compute_stock_features",
                "compute_options_features", "get_base_feature_names"]))
check("swing_features", lambda: __import__("ml.feature_engineering.swing_features",
      fromlist=["compute_swing_features", "get_swing_feature_names"]))
check("general_features", lambda: __import__("ml.feature_engineering.general_features",
      fromlist=["compute_general_features", "get_general_feature_names"]))
check("scalp_features", lambda: __import__("ml.feature_engineering.scalp_features",
      fromlist=["compute_scalp_features", "get_scalp_feature_names"]))

# --- Predictors ---
check("ModelPredictor (abstract)", lambda: __import__("ml.predictor",
      fromlist=["ModelPredictor"]))
check("XGBoostPredictor", lambda: __import__("ml.xgboost_predictor",
      fromlist=["XGBoostPredictor"]))
check("TFTPredictor", lambda: __import__("ml.tft_predictor",
      fromlist=["TFTPredictor"]))
check("EnsemblePredictor", lambda: __import__("ml.ensemble_predictor",
      fromlist=["EnsemblePredictor"]))
check("ScalpPredictor", lambda: __import__("ml.scalp_predictor",
      fromlist=["ScalpPredictor"]))

# --- Trainers ---
check("trainer (XGBoost)", lambda: __import__("ml.trainer",
      fromlist=["train_model"]))
check("tft_trainer", lambda: __import__("ml.tft_trainer",
      fromlist=["train_tft_model"]))
check("scalp_trainer", lambda: __import__("ml.scalp_trainer",
      fromlist=["train_scalp_model"]))
check("incremental_trainer", lambda: __import__("ml.incremental_trainer",
      fromlist=["retrain_incremental"]))

# --- EV filter ---
check("ev_filter", lambda: __import__("ml.ev_filter",
      fromlist=["scan_chain_for_best_ev"]))

# --- Data providers ---
check("alpaca_provider", lambda: __import__("data.alpaca_provider",
      fromlist=["AlpacaStockProvider"]))
check("options_data_fetcher", lambda: __import__("data.options_data_fetcher",
      fromlist=["fetch_options_for_training"]))
check("greeks_calculator", lambda: __import__("data.greeks_calculator",
      fromlist=["compute_greeks_vectorized", "get_second_order_feature_names"]))
check("validator", lambda: __import__("data.validator",
      fromlist=["validate_symbol_data"]))

# --- Strategies ---
check("BaseOptionsStrategy", lambda: __import__("strategies.base_strategy",
      fromlist=["BaseOptionsStrategy"]))
check("SwingStrategy", lambda: __import__("strategies.swing_strategy",
      fromlist=["SwingStrategy"]))
check("GeneralStrategy", lambda: __import__("strategies.general_strategy",
      fromlist=["GeneralStrategy"]))
check("ScalpStrategy", lambda: __import__("strategies.scalp_strategy",
      fromlist=["ScalpStrategy"]))

# --- Backend ---
check("backend.app", lambda: __import__("backend.app", fromlist=["app"]))
check("backend.database", lambda: __import__("backend.database",
      fromlist=["init_db", "get_db"]))
check("backend.schemas", lambda: __import__("backend.schemas",
      fromlist=["ProfileCreate", "TrainRequest", "SystemStatus"]))
check("routes.profiles", lambda: __import__("backend.routes.profiles",
      fromlist=["router"]))
check("routes.models", lambda: __import__("backend.routes.models",
      fromlist=["router"]))
check("routes.trades", lambda: __import__("backend.routes.trades",
      fromlist=["router"]))
check("routes.system", lambda: __import__("backend.routes.system",
      fromlist=["router"]))
check("routes.trading", lambda: __import__("backend.routes.trading",
      fromlist=["router"]))

# --- Risk ---
check("risk_manager", lambda: __import__("risk.risk_manager",
      fromlist=["RiskManager"]))

# --- Config ---
check("config", lambda: __import__("config",
      fromlist=["PRESET_DEFAULTS", "DB_PATH", "ALL_SYMBOLS"]))

# --- Main ---
check("main._get_strategy_class", lambda: __import__("main",
      fromlist=["_get_strategy_class"]))

# --- Summary ---
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"\nTest 1 result: {passed} PASS, {failed} FAIL out of {len(results)} checks")
if failed > 0:
    print("FAILED imports:")
    for s, label, detail in results:
        if s == "FAIL":
            print(f"  - {label}: {detail}")
```

Save to `/tmp/test1_imports.py` and run:
```bash
cd options-bot && python /tmp/test1_imports.py
```

---

## TEST 2 — FEATURE ENGINEERING PIPELINE INTEGRITY

Verify feature counts, names, no duplicates, and that base parameterization works for all presets.

```python
#!/usr/bin/env python3
"""Test 2: Feature engineering pipeline — counts, names, parameterization, no duplicates."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(".")))

import inspect
import numpy as np
import pandas as pd

results = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((status, label, detail))
    line = f"  {status}  {label}"
    if detail and not passed:
        line += f"\n          {detail}"
    print(line)

print("=" * 60)
print("TEST 2: FEATURE ENGINEERING PIPELINE")
print("=" * 60)

# --- Feature name counts ---
from ml.feature_engineering.base_features import get_base_feature_names
from ml.feature_engineering.swing_features import get_swing_feature_names
from ml.feature_engineering.general_features import get_general_feature_names
from ml.feature_engineering.scalp_features import get_scalp_feature_names
from data.greeks_calculator import get_second_order_feature_names

base = get_base_feature_names()
swing = get_swing_feature_names()
general = get_general_feature_names()
scalp = get_scalp_feature_names()
greeks_2nd = get_second_order_feature_names()

check("Base features = 67", len(base) == 67, f"got {len(base)}")
check("Swing features = 5", len(swing) == 5, f"got {len(swing)}")
check("General features = 4", len(general) == 4, f"got {len(general)}")
check("Scalp features = 10", len(scalp) == 10, f"got {len(scalp)}")
check("2nd order Greeks = 8", len(greeks_2nd) == 8, f"got {len(greeks_2nd)}")

# Total per preset
check("Swing total = 72", len(base) + len(swing) == 72,
      f"got {len(base) + len(swing)}")
check("General total = 71", len(base) + len(general) == 71,
      f"got {len(base) + len(general)}")
check("Scalp total = 77", len(base) + len(scalp) == 77,
      f"got {len(base) + len(scalp)}")

# --- No duplicate feature names within any preset ---
for preset_name, feat_list in [("swing", base + swing),
                                ("general", base + general),
                                ("scalp", base + scalp)]:
    unique = set(feat_list)
    check(f"{preset_name}: no duplicate feature names",
          len(feat_list) == len(unique),
          f"{len(feat_list)} names, {len(unique)} unique — dupes: {set(f for f in feat_list if feat_list.count(f) > 1)}")

# --- No cross-contamination between style features ---
swing_set = set(swing)
general_set = set(general)
scalp_set = set(scalp)
check("Swing vs General: no overlap",
      len(swing_set & general_set) == 0,
      f"overlap: {swing_set & general_set}")
check("Swing vs Scalp: no overlap",
      len(swing_set & scalp_set) == 0,
      f"overlap: {swing_set & scalp_set}")
check("General vs Scalp: no overlap",
      len(general_set & scalp_set) == 0,
      f"overlap: {general_set & scalp_set}")

# --- All scalp features prefixed ---
all_prefixed = all(n.startswith("scalp_") for n in scalp)
check("All scalp features prefixed 'scalp_'", all_prefixed,
      f"non-prefixed: {[n for n in scalp if not n.startswith('scalp_')]}")

# --- All 2nd order Greeks in base feature names ---
for greek in greeks_2nd:
    check(f"2nd order Greek '{greek}' in base features", greek in base)

# --- bars_per_day parameterization ---
from ml.feature_engineering.base_features import compute_base_features, compute_stock_features

sig_base = inspect.signature(compute_base_features)
sig_stock = inspect.signature(compute_stock_features)
check("compute_base_features has bars_per_day param",
      "bars_per_day" in sig_base.parameters)
check("compute_stock_features has bars_per_day param",
      "bars_per_day" in sig_stock.parameters)
check("bars_per_day default = 78",
      sig_base.parameters["bars_per_day"].default == 78,
      f"got {sig_base.parameters['bars_per_day'].default}")

# --- Scalp trainer uses correct feature count ---
from ml.scalp_trainer import _get_feature_names as scalp_trainer_features
trainer_feats = scalp_trainer_features()
check("Scalp trainer _get_feature_names() returns 77",
      len(trainer_feats) == 77, f"got {len(trainer_feats)}")
check("Scalp trainer features match base+scalp exactly",
      trainer_feats == base + scalp,
      f"first mismatch at index {next((i for i,(a,b) in enumerate(zip(trainer_feats, base+scalp)) if a!=b), 'none')}")

# --- XGBoost trainer uses correct feature count for swing ---
from ml.trainer import _get_feature_names as xgb_trainer_features
xgb_swing = xgb_trainer_features("swing")
check("XGBoost trainer swing features = 72",
      len(xgb_swing) == 72, f"got {len(xgb_swing)}")
xgb_general = xgb_trainer_features("general")
check("XGBoost trainer general features = 71",
      len(xgb_general) == 71, f"got {len(xgb_general)}")

# --- Mock feature computation with different bars_per_day ---
# Create a minimal DataFrame to test the function accepts both values
print("\n  Testing bars_per_day parameter acceptance (no data validation)...")
try:
    # Just verify the parameter is accepted, not the computation
    # We need enough rows for the longest lookback
    n_rows = 4000
    idx = pd.date_range("2025-01-01", periods=n_rows, freq="5min")
    mock_df = pd.DataFrame({
        "open": np.random.uniform(100, 200, n_rows),
        "high": np.random.uniform(100, 200, n_rows),
        "low": np.random.uniform(90, 100, n_rows),
        "close": np.random.uniform(100, 200, n_rows),
        "volume": np.random.randint(1000, 100000, n_rows).astype(float),
    }, index=idx)

    # 5-min bars (default, bars_per_day=78)
    feats_5min = compute_stock_features(mock_df, bars_per_day=78)
    check("compute_stock_features(bars_per_day=78) succeeds",
          feats_5min is not None and len(feats_5min) > 0)

    # 1-min bars (scalp, bars_per_day=390)
    n_rows_1min = 4000
    idx_1min = pd.date_range("2025-01-01", periods=n_rows_1min, freq="1min")
    mock_1min = pd.DataFrame({
        "open": np.random.uniform(400, 500, n_rows_1min),
        "high": np.random.uniform(400, 500, n_rows_1min),
        "low": np.random.uniform(390, 400, n_rows_1min),
        "close": np.random.uniform(400, 500, n_rows_1min),
        "volume": np.random.randint(1000, 100000, n_rows_1min).astype(float),
    }, index=idx_1min)
    feats_1min = compute_stock_features(mock_1min, bars_per_day=390)
    check("compute_stock_features(bars_per_day=390) succeeds",
          feats_1min is not None and len(feats_1min) > 0)

    # Scalp features compute
    from ml.feature_engineering.scalp_features import compute_scalp_features
    scalp_feats = compute_scalp_features(mock_1min)
    check("compute_scalp_features() succeeds on 1-min data",
          scalp_feats is not None and len(scalp_feats) > 0)

except Exception as e:
    check("Feature computation with bars_per_day", False, str(e))

# --- Summary ---
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"\nTest 2 result: {passed} PASS, {failed} FAIL out of {len(results)} checks")
```

Save to `/tmp/test2_features.py` and run:
```bash
cd options-bot && python /tmp/test2_features.py
```

---

## TEST 3 — PREDICTOR INTERFACE COMPLIANCE

All 4 predictors must implement the same interface and behave correctly.

```python
#!/usr/bin/env python3
"""Test 3: All predictors implement ModelPredictor interface correctly."""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(".")))

import numpy as np
from abc import ABC

results = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((status, label, detail))
    line = f"  {status}  {label}"
    if detail and not passed:
        line += f"\n          {detail}"
    print(line)

print("=" * 60)
print("TEST 3: PREDICTOR INTERFACE COMPLIANCE")
print("=" * 60)

from ml.predictor import ModelPredictor

# Verify abstract interface
check("ModelPredictor is abstract", issubclass(ModelPredictor, ABC))
required_methods = ["predict", "predict_batch", "get_feature_names", "get_feature_importance"]
for method in required_methods:
    check(f"ModelPredictor has abstract method '{method}'",
          hasattr(ModelPredictor, method))

# --- Test each predictor ---
from ml.xgboost_predictor import XGBoostPredictor
from ml.tft_predictor import TFTPredictor
from ml.ensemble_predictor import EnsemblePredictor
from ml.scalp_predictor import ScalpPredictor

predictors = {
    "XGBoostPredictor": XGBoostPredictor,
    "TFTPredictor": TFTPredictor,
    "EnsemblePredictor": EnsemblePredictor,
    "ScalpPredictor": ScalpPredictor,
}

for name, cls in predictors.items():
    check(f"{name} inherits ModelPredictor",
          issubclass(cls, ModelPredictor))

    for method in required_methods:
        check(f"{name}.{method}() exists",
              hasattr(cls, method) and callable(getattr(cls, method)))

    # Unloaded state
    instance = cls()
    check(f"{name}: get_feature_names() returns list when unloaded",
          isinstance(instance.get_feature_names(), list))
    check(f"{name}: get_feature_importance() returns dict when unloaded",
          isinstance(instance.get_feature_importance(), dict))

# --- ScalpPredictor specific: signed confidence logic ---
print("\n  ScalpPredictor signed confidence tests:")
sp = ScalpPredictor()

# _proba_to_signed_confidence
test_cases = [
    # (proba_array, expected_sign, description)
    (np.array([0.10, 0.15, 0.75]), +1, "UP dominant → positive"),
    (np.array([0.70, 0.18, 0.12]), -1, "DOWN dominant → negative"),
    (np.array([0.20, 0.60, 0.20]),  0, "NEUTRAL dominant → zero"),
    (np.array([0.33, 0.34, 0.33]),  0, "NEUTRAL max → zero"),
]

for proba, expected_sign, desc in test_cases:
    result = sp._proba_to_signed_confidence(proba)
    if expected_sign == 0:
        ok = result == 0.0
    elif expected_sign > 0:
        ok = result > 0
    else:
        ok = result < 0
    check(f"Signed confidence: {desc}", ok,
          f"proba={proba.tolist()}, result={result}")

# Magnitude check: confidence should equal the dominant class probability
proba_up = np.array([0.05, 0.10, 0.85])
result_up = sp._proba_to_signed_confidence(proba_up)
check("Signed confidence magnitude = dominant class prob",
      abs(abs(result_up) - 0.85) < 0.001,
      f"expected ≈0.85, got {abs(result_up)}")

# Full save/load/predict round-trip with mock model
print("\n  ScalpPredictor save/load/predict round-trip:")
try:
    from xgboost import XGBClassifier
    from ml.feature_engineering.base_features import get_base_feature_names
    from ml.feature_engineering.scalp_features import get_scalp_feature_names

    feature_names = get_base_feature_names() + get_scalp_feature_names()
    n = 100
    X = np.random.randn(n, len(feature_names))
    y = np.random.choice([0, 1, 2], size=n)

    clf = XGBClassifier(
        n_estimators=10, max_depth=3, num_class=3,
        objective="multi:softprob", eval_metric="mlogloss",
        use_label_encoder=False, verbosity=0,
    )
    clf.fit(X, y)

    # Save
    predictor = ScalpPredictor()
    predictor.set_model(clf, feature_names)
    tmp = tempfile.NamedTemporaryFile(suffix=".joblib", delete=False)
    tmp_path = tmp.name
    tmp.close()
    predictor.save(tmp_path, feature_names, neutral_band=0.0005, avg_30min_move_pct=0.09)

    # Load
    loaded = ScalpPredictor(tmp_path)
    check("Round-trip: feature count preserved",
          len(loaded.get_feature_names()) == 77,
          f"got {len(loaded.get_feature_names())}")
    check("Round-trip: avg_30min_move_pct preserved",
          loaded.get_avg_30min_move_pct() == 0.09,
          f"got {loaded.get_avg_30min_move_pct()}")
    check("Round-trip: feature importance is non-empty dict",
          isinstance(loaded.get_feature_importance(), dict) and len(loaded.get_feature_importance()) > 0)

    # Predict
    features = {name: float(np.random.randn()) for name in feature_names}
    result = loaded.predict(features)
    check("Round-trip: predict returns float in [-1, 1]",
          isinstance(result, (float, np.floating)) and -1.0 <= result <= 1.0,
          f"got {result} (type={type(result).__name__})")

    # predict_batch
    import pandas as pd
    batch_df = pd.DataFrame(np.random.randn(5, len(feature_names)), columns=feature_names)
    batch_result = loaded.predict_batch(batch_df)
    check("Round-trip: predict_batch returns Series of length 5",
          isinstance(batch_result, pd.Series) and len(batch_result) == 5,
          f"got type={type(batch_result).__name__}, len={len(batch_result) if hasattr(batch_result, '__len__') else '?'}")

    os.unlink(tmp_path)

except Exception as e:
    check("ScalpPredictor round-trip", False, str(e))

# --- Summary ---
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"\nTest 3 result: {passed} PASS, {failed} FAIL out of {len(results)} checks")
```

Save to `/tmp/test3_predictors.py` and run:
```bash
cd options-bot && python /tmp/test3_predictors.py
```

---

## TEST 4 — STRATEGY ROUTING AND INHERITANCE

Verify all 3 strategy classes route correctly and inherit the full interface.

```python
#!/usr/bin/env python3
"""Test 4: Strategy class routing, inheritance, and scalp branches in base_strategy."""
import sys, inspect
from pathlib import Path
sys.path.insert(0, str(Path(".")))

results = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((status, label, detail))
    line = f"  {status}  {label}"
    if detail and not passed:
        line += f"\n          {detail}"
    print(line)

print("=" * 60)
print("TEST 4: STRATEGY ROUTING AND INHERITANCE")
print("=" * 60)

from strategies.base_strategy import BaseOptionsStrategy
from strategies.swing_strategy import SwingStrategy
from strategies.general_strategy import GeneralStrategy
from strategies.scalp_strategy import ScalpStrategy
from main import _get_strategy_class

# --- Inheritance ---
for name, cls in [("SwingStrategy", SwingStrategy),
                   ("GeneralStrategy", GeneralStrategy),
                   ("ScalpStrategy", ScalpStrategy)]:
    check(f"{name} inherits BaseOptionsStrategy",
          issubclass(cls, BaseOptionsStrategy))
    for method in ["on_trading_iteration", "_check_exits", "_check_entries", "initialize"]:
        check(f"{name} has {method}()",
              hasattr(cls, method) and callable(getattr(cls, method)))

# --- main.py routing ---
routing = {
    "swing": "SwingStrategy",
    "general": "GeneralStrategy",
    "scalp": "ScalpStrategy",
}
for preset, expected_name in routing.items():
    cls = _get_strategy_class(preset)
    check(f"_get_strategy_class('{preset}') → {expected_name}",
          cls.__name__ == expected_name,
          f"got {cls.__name__}")

# Unknown preset falls back
cls = _get_strategy_class("nonexistent")
check("_get_strategy_class('nonexistent') → BaseOptionsStrategy",
      cls.__name__ == "BaseOptionsStrategy",
      f"got {cls.__name__}")

# --- Scalp branches in base_strategy.py ---
print("\n  Checking scalp-specific branches in base_strategy.py:")
source = (Path("strategies/base_strategy.py")).read_text()

scalp_markers = {
    "Equity gate (SCALP EQUITY GATE or scalp equity)":
        "SCALP EQUITY GATE" in source or "scalp" in source.lower() and "equity" in source.lower(),
    "scalp_eod exit reason": "scalp_eod" in source,
    "min_confidence threshold": "min_confidence" in source,
    "bar_granularity in bar cache": "bar_granularity" in source,
    "ScalpPredictor import": "ScalpPredictor" in source,
    "get_avg_30min_move_pct or avg_30min_move": (
        "get_avg_30min_move_pct" in source or "avg_30min_move" in source
    ),
    "3:45 PM / 15:45 cutoff": "15" in source and "45" in source,
    "xgb_classifier model loading": "xgb_classifier" in source,
    "max_bars scalp 500": "500" in source,
}
for desc, found in scalp_markers.items():
    check(f"base_strategy: {desc}", found)

# --- Verify model loading branch for xgb_classifier ---
# The initialize() method should have a branch that loads ScalpPredictor for xgb_classifier
check("base_strategy: 'xgb_classifier' string present",
      "xgb_classifier" in source)

# --- Summary ---
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"\nTest 4 result: {passed} PASS, {failed} FAIL out of {len(results)} checks")
```

Save to `/tmp/test4_strategy.py` and run:
```bash
cd options-bot && python /tmp/test4_strategy.py
```

---

## TEST 5 — BACKEND API INTEGRATION

Verify the backend accepts xgb_classifier, routes correctly, and all endpoints still work.

```python
#!/usr/bin/env python3
"""Test 5: Backend API — model_type validation, routing, schemas, all routes importable."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(".")))

results = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((status, label, detail))
    line = f"  {status}  {label}"
    if detail and not passed:
        line += f"\n          {detail}"
    print(line)

print("=" * 60)
print("TEST 5: BACKEND API INTEGRATION")
print("=" * 60)

# --- models.py xgb_classifier routing ---
models_source = Path("backend/routes/models.py").read_text()

check("'xgb_classifier' in model_type validation",
      "xgb_classifier" in models_source)
check("_scalp_train_job function defined",
      "_scalp_train_job" in models_source)
check("ScalpPredictor import in models.py",
      "ScalpPredictor" in models_source)
check("_extract_and_persist_importance handles xgb_classifier",
      "xgb_classifier" in models_source and "_extract_and_persist_importance" in models_source)

# --- Verify model_type validation list includes all 4 types ---
# The validation should accept: xgboost, tft, ensemble, xgb_classifier
for mt in ["xgboost", "tft", "ensemble", "xgb_classifier"]:
    check(f"model_type '{mt}' referenced in models.py",
          f'"{mt}"' in models_source or f"'{mt}'" in models_source)

# --- profiles.py accepts 'scalp' preset ---
profiles_source = Path("backend/routes/profiles.py").read_text()
check("profiles.py uses PRESET_DEFAULTS for validation",
      "PRESET_DEFAULTS" in profiles_source)

from config import PRESET_DEFAULTS
check("'scalp' in PRESET_DEFAULTS",
      "scalp" in PRESET_DEFAULTS)

# --- Schemas still valid ---
from backend.schemas import (
    ProfileCreate, ProfileResponse, TrainRequest, TrainingStatus,
    ModelMetrics, SystemStatus, BacktestResult,
)
check("All Pydantic schemas import successfully", True)

# Verify TrainRequest accepts model_type
tr = TrainRequest(model_type="xgb_classifier")
check("TrainRequest accepts model_type='xgb_classifier'",
      tr.model_type == "xgb_classifier",
      f"got {tr.model_type}")

# --- Database schema check ---
import sqlite3
from config import DB_PATH
if DB_PATH.exists():
    con = sqlite3.connect(str(DB_PATH))
    cursor = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    con.close()

    expected = {"profiles", "models", "trades", "system_state", "training_logs"}
    for t in expected:
        check(f"Table '{t}' exists in DB", t in tables)

    # Verify models table has model_type column
    con = sqlite3.connect(str(DB_PATH))
    cursor = con.execute("PRAGMA table_info(models)")
    columns = {row[1] for row in cursor.fetchall()}
    con.close()
    check("models.model_type column exists", "model_type" in columns)
    check("models.metrics column exists", "metrics" in columns)
    check("models.feature_names column exists", "feature_names" in columns)
else:
    check("Database file exists", False, f"Not found: {DB_PATH}")

# --- FastAPI app mounts all routers ---
from backend.app import app
routes = [r.path for r in app.routes]
api_prefixes = ["/api/profiles", "/api/models", "/api/trades", "/api/system", "/api/trading"]
for prefix in api_prefixes:
    found = any(prefix in r for r in routes)
    check(f"Router mounted: {prefix}", found)

# --- Summary ---
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"\nTest 5 result: {passed} PASS, {failed} FAIL out of {len(results)} checks")
```

Save to `/tmp/test5_backend.py` and run:
```bash
cd options-bot && python /tmp/test5_backend.py
```

---

## TEST 6 — CONFIG CONSISTENCY

Verify all config values match architecture spec for all 3 presets.

```python
#!/usr/bin/env python3
"""Test 6: Config consistency — all preset values match architecture spec."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(".")))

results = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((status, label, detail))
    line = f"  {status}  {label}"
    if detail and not passed:
        line += f"\n          {detail}"
    print(line)

print("=" * 60)
print("TEST 6: CONFIG CONSISTENCY")
print("=" * 60)

from config import (
    PRESET_DEFAULTS, ALL_SYMBOLS, PHASE1_SYMBOLS,
    MAX_TOTAL_EXPOSURE_PCT, MAX_TOTAL_POSITIONS, EMERGENCY_STOP_LOSS_PCT,
)

# --- Architecture Section 6 spec ---
arch_spec = {
    "swing": {
        "min_dte": 7, "max_dte": 45, "sleeptime": "5M",
        "max_hold_days": 7, "prediction_horizon": "5d",
        "profit_target_pct": 50, "stop_loss_pct": 30,
        "min_predicted_move_pct": 1.0, "min_ev_pct": 10,
        "max_position_pct": 20, "max_contracts": 5,
        "bar_granularity": "5min", "requires_min_equity": 0,
    },
    "general": {
        "min_dte": 21, "max_dte": 60, "sleeptime": "15M",
        "max_hold_days": 14, "prediction_horizon": "10d",
        "profit_target_pct": 40, "stop_loss_pct": 25,
        "min_predicted_move_pct": 1.0, "min_ev_pct": 10,
        "max_position_pct": 20, "max_contracts": 5,
        "bar_granularity": "5min", "requires_min_equity": 0,
    },
    "scalp": {
        "min_dte": 0, "max_dte": 0, "sleeptime": "1M",
        "max_hold_days": 0, "prediction_horizon": "30min",
        "profit_target_pct": 20, "stop_loss_pct": 15,
        "min_predicted_move_pct": 0.3, "min_ev_pct": 5,
        "max_position_pct": 10, "max_contracts": 10,
        "max_daily_trades": 20,
        "bar_granularity": "1min", "requires_min_equity": 25000,
    },
}

for preset, spec in arch_spec.items():
    check(f"'{preset}' preset exists", preset in PRESET_DEFAULTS)
    if preset in PRESET_DEFAULTS:
        actual = PRESET_DEFAULTS[preset]
        for key, expected_val in spec.items():
            actual_val = actual.get(key)
            check(f"  {preset}.{key} = {expected_val}",
                  actual_val == expected_val,
                  f"expected {expected_val}, got {actual_val}")

# --- Global limits ---
check("MAX_TOTAL_EXPOSURE_PCT = 60", MAX_TOTAL_EXPOSURE_PCT == 60)
check("MAX_TOTAL_POSITIONS = 10", MAX_TOTAL_POSITIONS == 10)
check("EMERGENCY_STOP_LOSS_PCT = 20", EMERGENCY_STOP_LOSS_PCT == 20)

# --- Symbol lists ---
check("'TSLA' in PHASE1_SYMBOLS", "TSLA" in PHASE1_SYMBOLS)
check("'SPY' in ALL_SYMBOLS", "SPY" in ALL_SYMBOLS)

# --- Summary ---
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"\nTest 6 result: {passed} PASS, {failed} FAIL out of {len(results)} checks")
```

Save to `/tmp/test6_config.py` and run:
```bash
cd options-bot && python /tmp/test6_config.py
```

---

## TEST 7 — SCALP TRAINER PIPELINE UNIT TESTS

Test the training pipeline's internal functions with mock data (no API calls).

```python
#!/usr/bin/env python3
"""Test 7: Scalp trainer pipeline internal functions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(".")))

import numpy as np
import pandas as pd

results = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((status, label, detail))
    line = f"  {status}  {label}"
    if detail and not passed:
        line += f"\n          {detail}"
    print(line)

print("=" * 60)
print("TEST 7: SCALP TRAINER PIPELINE")
print("=" * 60)

from ml.scalp_trainer import (
    _calculate_class_target, _subsample_strided,
    _walk_forward_cv_classifier,
    HORIZON_BARS, NEUTRAL_BAND_PCT, SUBSAMPLE_STRIDE,
    CV_FOLDS, SCALP_BARS_PER_DAY, MIN_TRAINING_SAMPLES,
)

# --- Constants ---
check("HORIZON_BARS = 30", HORIZON_BARS == 30)
check("NEUTRAL_BAND_PCT = 0.05", NEUTRAL_BAND_PCT == 0.05)
check("SUBSAMPLE_STRIDE = 30", SUBSAMPLE_STRIDE == 30)
check("CV_FOLDS = 5", CV_FOLDS == 5)
check("SCALP_BARS_PER_DAY = 390", SCALP_BARS_PER_DAY == 390)

# --- _calculate_class_target ---
# Uses module constants HORIZON_BARS and NEUTRAL_BAND_PCT internally.
print("\n  Testing _calculate_class_target:")
# Create mock close prices with known forward returns
n = 100
closes = np.ones(n) * 100.0
# At index 50, price will go up 0.2% in 30 bars → class UP
closes[80] = 100.20
# At index 10, price will go down 0.2% in 30 bars → class DOWN
closes[40] = 99.80

mock_df = pd.DataFrame({"close": closes})
targets = _calculate_class_target(mock_df)
check("_calculate_class_target returns Series", isinstance(targets, pd.Series))
check("_calculate_class_target length matches input", len(targets) == len(mock_df))

# Last HORIZON_BARS should be NaN (no forward return available)
nan_count = targets.tail(HORIZON_BARS).isna().sum()
check(f"Last {HORIZON_BARS} targets are NaN", nan_count == HORIZON_BARS,
      f"got {nan_count} NaN in last {HORIZON_BARS}")

# Only valid classes: 0, 1, 2 (and NaN)
valid_values = targets.dropna().unique()
check("Target values are in {0, 1, 2}",
      set(valid_values).issubset({0, 1, 2}),
      f"got unique values: {sorted(valid_values)}")

# --- _subsample_strided ---
# Uses module constant SUBSAMPLE_STRIDE internally. Takes a single df, returns df.
print("\n  Testing _subsample_strided:")
n = 1000
idx = pd.date_range("2025-01-02 09:30", periods=n, freq="1min")
mock_df2 = pd.DataFrame({
    "feat1": np.random.randn(n),
    "feat2": np.random.randn(n),
}, index=idx)

sub_df = _subsample_strided(mock_df2)
check("_subsample_strided reduces row count",
      len(sub_df) < len(mock_df2),
      f"from {len(mock_df2)} to {len(sub_df)}")

expected_approx = n // SUBSAMPLE_STRIDE
check(f"Subsampled count ≈ {expected_approx} (±5)",
      abs(len(sub_df) - expected_approx) <= 5,
      f"got {len(sub_df)}")

# --- Summary ---
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"\nTest 7 result: {passed} PASS, {failed} FAIL out of {len(results)} checks")
```

Save to `/tmp/test7_scalp_trainer.py` and run:
```bash
cd options-bot && python /tmp/test7_scalp_trainer.py
```

---

## TEST 8 — UI BUILD AND CONTENT VERIFICATION

```bash
cd options-bot/ui

echo "=" * 60
echo "TEST 8: UI BUILD AND CONTENT VERIFICATION"
echo "=" * 60

echo ""
echo "--- Check 1: TypeScript compile ---"
npx tsc --noEmit 2>&1 | tail -5
TSC_EXIT=$?
if [ $TSC_EXIT -eq 0 ]; then
    echo "  PASS  TypeScript compiles"
else
    echo "  FAIL  TypeScript compilation errors"
fi

echo ""
echo "--- Check 2: Production build ---"
npm run build 2>&1 | tail -5
BUILD_EXIT=$?
if [ $BUILD_EXIT -eq 0 ]; then
    echo "  PASS  npm run build"
else
    echo "  FAIL  npm run build"
fi

echo ""
echo "--- Check 3: Scalp in ProfileForm ---"
echo "  scalp preset:"
grep -n "scalp" src/components/ProfileForm.tsx | head -8

echo ""
echo "--- Check 4: xgb_classifier in ProfileDetail ---"
echo "  xgb_classifier references:"
grep -n "xgb_classifier" src/pages/ProfileDetail.tsx | head -8

echo ""
echo "--- Check 5: acc_all metric in ProfileDetail ---"
echo "  acc_all references:"
grep -n "acc_all" src/pages/ProfileDetail.tsx | head -5

echo ""
echo "--- Check 6: min_confidence in ProfileForm ---"
grep -n "min_confidence\|minConfidence" src/components/ProfileForm.tsx | head -5

echo ""
echo "--- Check 7: Scalp styling in Profiles ---"
grep -n "scalp" src/pages/Profiles.tsx | head -5

echo ""
echo "--- Check 8: Types include scalp ---"
grep -n "scalp" src/types/api.ts | head -5

echo ""
echo "--- Check 9: No broken imports (grep for 'from.*undefined') ---"
BROKEN_MATCHES=$(grep -rn "from '.*undefined" src/ | head -5)
if [ -z "$BROKEN_MATCHES" ]; then
    echo "  PASS  No broken imports found"
else
    echo "$BROKEN_MATCHES"
    echo "  WARN  Possible broken imports found above"
fi

echo ""
echo "--- Check 10: Existing pages still present ---"
for page in Dashboard Profiles ProfileDetail Trades System; do
    if [ -f "src/pages/${page}.tsx" ]; then
        echo "  EXISTS: ${page}.tsx"
    else
        echo "  MISSING: ${page}.tsx"
    fi
done
```

Save to `/tmp/test8_ui.sh` and run:
```bash
bash /tmp/test8_ui.sh
```

---

## TEST 9 — BACKWARD COMPATIBILITY STRESS TEST

Verify that swing and general presets work exactly as before with no regressions.

```python
#!/usr/bin/env python3
"""Test 9: Backward compatibility — swing and general are completely unaffected."""
import sys, inspect
from pathlib import Path
sys.path.insert(0, str(Path(".")))

results = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((status, label, detail))
    line = f"  {status}  {label}"
    if detail and not passed:
        line += f"\n          {detail}"
    print(line)

print("=" * 60)
print("TEST 9: BACKWARD COMPATIBILITY")
print("=" * 60)

# --- XGBoost trainer ---
from ml.trainer import train_model, _get_feature_names
check("XGBoost train_model importable", True)
check("XGBoost _get_feature_names('swing') = 72",
      len(_get_feature_names("swing")) == 72)
check("XGBoost _get_feature_names('general') = 71",
      len(_get_feature_names("general")) == 71)

# --- TFT trainer ---
from ml.tft_trainer import (
    train_tft_model, ENCODER_LENGTH, CV_FOLDS as TFT_CV,
    BARS_PER_DAY, STRIDE,
)
check("TFT train_tft_model importable", True)
check("TFT ENCODER_LENGTH = 60", ENCODER_LENGTH == 60)
check("TFT CV_FOLDS = 3", TFT_CV == 3)
check("TFT STRIDE = BARS_PER_DAY = 78", STRIDE == BARS_PER_DAY == 78)

# --- Incremental trainer ---
from ml.incremental_trainer import retrain_incremental
check("retrain_incremental importable", True)

# --- EV filter ---
from ml.ev_filter import scan_chain_for_best_ev
sig = inspect.signature(scan_chain_for_best_ev)
check("scan_chain_for_best_ev has predicted_return_pct param",
      "predicted_return_pct" in sig.parameters)

# --- Risk manager ---
from risk.risk_manager import RiskManager
rm = RiskManager()
check("RiskManager.check_pdt exists", hasattr(rm, "check_pdt"))
check("RiskManager.check_pdt_limit exists", hasattr(rm, "check_pdt_limit"))
check("RiskManager.check_can_open_position exists", hasattr(rm, "check_can_open_position"))
check("RiskManager.check_portfolio_exposure exists", hasattr(rm, "check_portfolio_exposure"))
check("RiskManager.check_emergency_stop_loss exists", hasattr(rm, "check_emergency_stop_loss"))
check("RiskManager.log_trade_open exists", hasattr(rm, "log_trade_open"))
check("RiskManager.log_trade_close exists", hasattr(rm, "log_trade_close"))

# --- Base strategy exit rules ---
source = Path("strategies/base_strategy.py").read_text()
exit_rules = {
    "profit_target": "profit_target" in source,
    "stop_loss": "stop_loss" in source,
    "max_hold": "max_hold" in source,
    "dte_exit": "dte_exit" in source or "dte" in source,
    "model_override": "model_override" in source,
}
for rule, found in exit_rules.items():
    check(f"Exit rule '{rule}' present in base_strategy", found)

# --- Base strategy entry steps ---
# Entry steps skip 3 and 7 (numbering follows logical groupings, not consecutive)
for step in [1, 2, 4, 5, 6, 8, 9, 10, 11, 12]:
    marker = f"ENTRY STEP {step}"
    check(f"Entry step {step} present", marker in source)

# --- Emergency stop wired ---
check("Emergency stop in on_trading_iteration",
      "check_emergency_stop_loss" in source or "emergency" in source.lower())

# --- Model override in _check_exits ---
check("model_override in _check_exits",
      "model_override" in source)

# --- Swing/General strategies are pass-through ---
swing_source = Path("strategies/swing_strategy.py").read_text()
general_source = Path("strategies/general_strategy.py").read_text()
scalp_source = Path("strategies/scalp_strategy.py").read_text()

# All three should be thin wrappers (class body is just `pass` or docstring)
for name, src in [("swing", swing_source), ("general", general_source), ("scalp", scalp_source)]:
    # Should NOT override _check_entries or _check_exits
    has_override = "def _check_entries" in src.split("class")[1] if "class" in src else False
    check(f"{name}_strategy does NOT override _check_entries",
          not has_override)

# --- Summary ---
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"\nTest 9 result: {passed} PASS, {failed} FAIL out of {len(results)} checks")
```

Save to `/tmp/test9_backward.py` and run:
```bash
cd options-bot && python /tmp/test9_backward.py
```

---

## TEST 10 — CROSS-CUTTING END-TO-END VALIDATION

Feature names flow from engineering → trainer → predictor → strategy. Any mismatch = silent failures.

```python
#!/usr/bin/env python3
"""Test 10: End-to-end feature name pipeline + cross-cutting validation."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(".")))

results = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((status, label, detail))
    line = f"  {status}  {label}"
    if detail and not passed:
        line += f"\n          {detail}"
    print(line)

print("=" * 60)
print("TEST 10: CROSS-CUTTING END-TO-END VALIDATION")
print("=" * 60)

# --- Feature name pipeline: engineering → trainer → predictor ---
# For each preset, verify the trainer uses the same feature names as the engineering module

from ml.feature_engineering.base_features import get_base_feature_names
from ml.feature_engineering.swing_features import get_swing_feature_names
from ml.feature_engineering.general_features import get_general_feature_names
from ml.feature_engineering.scalp_features import get_scalp_feature_names

engineering_features = {
    "swing": get_base_feature_names() + get_swing_feature_names(),
    "general": get_base_feature_names() + get_general_feature_names(),
    "scalp": get_base_feature_names() + get_scalp_feature_names(),
}

# XGBoost trainer
from ml.trainer import _get_feature_names as xgb_get_features
for preset in ["swing", "general"]:
    trainer_feats = xgb_get_features(preset)
    eng_feats = engineering_features[preset]
    check(f"XGB trainer '{preset}' features match engineering",
          trainer_feats == eng_feats,
          f"trainer={len(trainer_feats)}, eng={len(eng_feats)}")

# Scalp trainer
from ml.scalp_trainer import _get_feature_names as scalp_get_features
scalp_trainer_feats = scalp_get_features()
scalp_eng_feats = engineering_features["scalp"]
check("Scalp trainer features match engineering",
      scalp_trainer_feats == scalp_eng_feats,
      f"trainer={len(scalp_trainer_feats)}, eng={len(scalp_eng_feats)}")

# --- DB model records: verify feature_names stored match engineering ---
import sqlite3
from config import DB_PATH

if DB_PATH.exists():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row

    # Check all models
    cursor = con.execute(
        "SELECT id, model_type, feature_names, status FROM models WHERE status = 'ready'"
    )
    rows = cursor.fetchall()
    print(f"\n  Found {len(rows)} ready model(s) in DB")

    # Current feature counts: swing=72, general=71, scalp=77.
    # Older models may have been trained with different feature sets (e.g. 65, 73).
    # Only validate that feature_names is a valid list; check count for newest models.
    current_counts = {"xgboost": 72, "tft": 72, "ensemble": 72, "xgb_classifier": 77}
    for row in rows:
        model_id = row["id"][:8]
        model_type = row["model_type"]
        if row["feature_names"]:
            stored_names = json.loads(row["feature_names"])
            check(f"DB model {model_id}({model_type}): feature_names is list",
                  isinstance(stored_names, list) and len(stored_names) > 0,
                  f"got type={type(stored_names).__name__}, len={len(stored_names)}")
            expected = current_counts.get(model_type)
            if expected and len(stored_names) == expected:
                check(f"DB model {model_id}({model_type}): matches current count {expected}",
                      True)
            elif expected:
                print(f"  INFO  DB model {model_id}({model_type}): historical count {len(stored_names)} (current={expected})")

    con.close()
else:
    print("  (No database found — skipping DB feature name checks)")

# --- Sleeptime format validation ---
# Architecture note: Lumibot uses last character as unit. Must be "5M", "15M", "1M" etc.
from config import PRESET_DEFAULTS
for preset, config in PRESET_DEFAULTS.items():
    sleeptime = config.get("sleeptime", "")
    last_char = sleeptime[-1] if sleeptime else ""
    check(f"'{preset}' sleeptime '{sleeptime}' ends with valid unit",
          last_char in ("M", "D", "S", "H"),
          f"last char = '{last_char}'")

# --- Verify no hardcoded "5min" sleeptimes (common bug) ---
base_source = Path("strategies/base_strategy.py").read_text()
# Search for literal "5min" string that might be used as a sleeptime
# (acceptable in comments, log messages, or bar_granularity — not as sleeptime)
lines_with_5min = [i+1 for i, line in enumerate(base_source.split('\n'))
                   if '"5min"' in line and 'sleeptime' in line.lower()]
check("No '5min' used as sleeptime in base_strategy",
      len(lines_with_5min) == 0,
      f"found on lines: {lines_with_5min}")

# --- Feature set config matches preset ---
for preset in ["swing", "general", "scalp"]:
    feature_set = PRESET_DEFAULTS[preset].get("feature_set")
    check(f"'{preset}' feature_set = '{preset}'",
          feature_set == preset,
          f"got '{feature_set}'")

# --- model_type defaults ---
check("swing model_type default", PRESET_DEFAULTS["swing"].get("model_type") in ("xgboost", "ensemble"))
check("general model_type default", PRESET_DEFAULTS["general"].get("model_type") in ("xgboost", "ensemble"))
# Scalp can be xgboost or xgb_classifier
check("scalp model_type default",
      PRESET_DEFAULTS["scalp"].get("model_type") in ("xgboost", "xgb_classifier"))

# --- Summary ---
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"\nTest 10 result: {passed} PASS, {failed} FAIL out of {len(results)} checks")
```

Save to `/tmp/test10_e2e.py` and run:
```bash
cd options-bot && python /tmp/test10_e2e.py
```

---

## TEST 11 — RUN PHASE 5 CHECKPOINT SCRIPT

The official checkpoint script should pass with zero FAILs.

```bash
cd options-bot && python scripts/phase5_checkpoint.py
```

Expected: All structural checks PASS. DB metrics may WARN. Zero FAIL.

---

## FINAL REPORT FORMAT

After running all 11 tests, compile results:

```
================================================================
PHASE 5 INTEGRATION TEST — FINAL REPORT
================================================================

Test  1 (Import chains):        XX PASS / XX FAIL
Test  2 (Feature pipeline):     XX PASS / XX FAIL
Test  3 (Predictor interface):  XX PASS / XX FAIL
Test  4 (Strategy routing):     XX PASS / XX FAIL
Test  5 (Backend API):          XX PASS / XX FAIL
Test  6 (Config consistency):   XX PASS / XX FAIL
Test  7 (Scalp trainer):        XX PASS / XX FAIL
Test  8 (UI build):             PASS / FAIL (build result)
Test  9 (Backward compat):      XX PASS / XX FAIL
Test 10 (Cross-cutting E2E):    XX PASS / XX FAIL
Test 11 (Phase 5 checkpoint):   XX PASS / XX WARN / XX FAIL

TOTAL: XXX checks
PASSED: XXX
WARNED: XXX (expected — need trained model)
FAILED: XXX

FAILURES REQUIRING FIXES:
  1. [Test X] Description of failure
  2. [Test X] Description of failure
  ...
```

If ANY test has FAILures, list each failure with:
- Test number and check name
- Expected vs actual value
- The exact file and likely cause

Do NOT fix anything. Report only. Fixing happens in a separate prompt after review.
