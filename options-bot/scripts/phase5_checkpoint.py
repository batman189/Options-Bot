#!/usr/bin/env python3
"""
Phase 5 checkpoint verification script.
Matches PROJECT_ARCHITECTURE.md Section 14 — Phase 5 success criteria.

Checks:
    P5P1  Scalp features — file, imports, 10 features, base parameterization
    P5P2  Scalp classifier — predictor file, trainer file, signed confidence
    P5P3  Scalp strategy — strategy file, base_strategy scalp branches, main.py routing
    P5P4  UI — scalp preset in ProfileForm, xgb_classifier in ProfileDetail
    P5P5  Architecture — sections updated
    CONFIG  Scalp preset defaults match architecture
    DB    Trained scalp model metrics (if any exist)

Exit code: 0 if all checks pass (or only warnings), 1 if any FAIL.
"""

import sys
import json
import os
import subprocess
import sqlite3
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Setup paths ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

PASS = "  ✓  PASS"
FAIL = "  ✗  FAIL"
WARN = "  ⚠  WARN"
SKIP = "  —  SKIP"

results = []
fail_count = 0


def check(label: str, passed: bool, detail: str = "", warn_only: bool = False):
    global fail_count
    if passed:
        status = PASS
    elif warn_only:
        status = WARN
    else:
        status = FAIL
        fail_count += 1
    line = f"{status}  {label}"
    if detail:
        line += f"\n              {detail}"
    print(line)
    results.append((status, label, detail))


def section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


print("=" * 60)
print("  PHASE 5 CHECKPOINT — 0DTE Scalp Strategy")
print("=" * 60)


# ══════════════════════════════════════════════════════════════════
# P5P1 — Scalp Feature Engineering
# ══════════════════════════════════════════════════════════════════
section("P5P1 — Scalp Feature Engineering")

# File exists
p = ROOT / "ml" / "feature_engineering" / "scalp_features.py"
check("ml/feature_engineering/scalp_features.py exists", p.exists())

# Imports
try:
    from ml.feature_engineering.scalp_features import (
        compute_scalp_features, get_scalp_feature_names,
    )
    check("scalp_features imports cleanly", True)

    scalp_names = get_scalp_feature_names()
    check("10 scalp feature names returned", len(scalp_names) == 10,
          f"got {len(scalp_names)}: {scalp_names}")

    # All prefixed with scalp_
    all_prefixed = all(n.startswith("scalp_") for n in scalp_names)
    check("All scalp features prefixed 'scalp_'", all_prefixed)

except Exception as e:
    check("scalp_features imports cleanly", False, str(e))

# Base features parameterized with bars_per_day
try:
    from ml.feature_engineering.base_features import (
        compute_base_features, compute_stock_features, get_base_feature_names,
    )
    import inspect

    # Check bars_per_day parameter exists
    sig_base = inspect.signature(compute_base_features)
    check("compute_base_features has bars_per_day param",
          "bars_per_day" in sig_base.parameters,
          f"params: {list(sig_base.parameters.keys())}")

    sig_stock = inspect.signature(compute_stock_features)
    check("compute_stock_features has bars_per_day param",
          "bars_per_day" in sig_stock.parameters,
          f"params: {list(sig_stock.parameters.keys())}")

    # Default is 78 (backward compat)
    default_val = sig_base.parameters["bars_per_day"].default
    check("compute_base_features bars_per_day default=78",
          default_val == 78, f"got {default_val}")

    # Base feature count is 67 (put_call_oi_ratio removed — no OI in ThetaData EOD)
    base_names = get_base_feature_names()
    check("get_base_feature_names() returns 67", len(base_names) == 67,
          f"got {len(base_names)}")

except Exception as e:
    check("base_features parameterization", False, str(e))

# Total scalp features = 78 (68 base + 10 scalp)
try:
    total = len(get_base_feature_names()) + len(get_scalp_feature_names())
    check("Total scalp features = 77 (67 base + 10 scalp)",
          total == 77, f"got {total}")
except Exception as e:
    check("Total scalp features = 78", False, str(e))

# No duplicate feature names
try:
    all_names = get_base_feature_names() + get_scalp_feature_names()
    unique = set(all_names)
    check("No duplicate feature names", len(all_names) == len(unique),
          f"{len(all_names)} names, {len(unique)} unique")
except Exception as e:
    check("No duplicate feature names", False, str(e))


# ══════════════════════════════════════════════════════════════════
# P5P2 — Scalp Classifier (Predictor + Trainer)
# ══════════════════════════════════════════════════════════════════
section("P5P2 — Scalp Classifier")

# Predictor file
p = ROOT / "ml" / "scalp_predictor.py"
check("ml/scalp_predictor.py exists", p.exists())

try:
    from ml.scalp_predictor import ScalpPredictor, CLASS_DOWN, CLASS_NEUTRAL, CLASS_UP
    from ml.predictor import ModelPredictor

    check("ScalpPredictor imports cleanly", True)
    check("ScalpPredictor inherits ModelPredictor",
          issubclass(ScalpPredictor, ModelPredictor))
    check("CLASS_DOWN=0, CLASS_NEUTRAL=1, CLASS_UP=2",
          CLASS_DOWN == 0 and CLASS_NEUTRAL == 1 and CLASS_UP == 2,
          f"got {CLASS_DOWN}, {CLASS_NEUTRAL}, {CLASS_UP}")

    # Unloaded state
    sp = ScalpPredictor()
    check("Unloaded: get_feature_names() == []", sp.get_feature_names() == [])
    check("Unloaded: get_feature_importance() == {}", sp.get_feature_importance() == {})

    # predict raises without model
    try:
        sp.predict({})
        check("Unloaded: predict() raises RuntimeError", False, "Did not raise")
    except RuntimeError:
        check("Unloaded: predict() raises RuntimeError", True)
    except Exception as e:
        check("Unloaded: predict() raises RuntimeError", False, f"Wrong exception: {e}")

    # Signed confidence logic
    import numpy as np
    # UP with 72% confidence
    result = sp._proba_to_signed_confidence(np.array([0.13, 0.15, 0.72]))
    check("Signed confidence: UP → positive",
          result > 0 and abs(result - 0.72) < 0.01,
          f"got {result}")

    # DOWN with 65% confidence
    result = sp._proba_to_signed_confidence(np.array([0.65, 0.20, 0.15]))
    check("Signed confidence: DOWN → negative",
          result < 0 and abs(result + 0.65) < 0.01,
          f"got {result}")

    # NEUTRAL
    result = sp._proba_to_signed_confidence(np.array([0.20, 0.55, 0.25]))
    check("Signed confidence: NEUTRAL → 0.0", result == 0.0,
          f"got {result}")

except Exception as e:
    check("ScalpPredictor imports cleanly", False, str(e))

# Trainer file
p = ROOT / "ml" / "scalp_trainer.py"
check("ml/scalp_trainer.py exists", p.exists())

try:
    from ml.scalp_trainer import (
        train_scalp_model, _get_feature_names,
        CV_FOLDS, HORIZON_BARS, NEUTRAL_BAND_PCT,
        SUBSAMPLE_STRIDE, SCALP_BARS_PER_DAY, MIN_TRAINING_SAMPLES,
    )
    check("scalp_trainer imports cleanly", True)
    check("CV_FOLDS=5", CV_FOLDS == 5, f"got {CV_FOLDS}")
    check("HORIZON_BARS=30", HORIZON_BARS == 30, f"got {HORIZON_BARS}")
    check("NEUTRAL_BAND_PCT=0.05", NEUTRAL_BAND_PCT == 0.05, f"got {NEUTRAL_BAND_PCT}")
    check("SUBSAMPLE_STRIDE=30", SUBSAMPLE_STRIDE == 30, f"got {SUBSAMPLE_STRIDE}")
    check("SCALP_BARS_PER_DAY=390", SCALP_BARS_PER_DAY == 390, f"got {SCALP_BARS_PER_DAY}")
    check("MIN_TRAINING_SAMPLES=500", MIN_TRAINING_SAMPLES == 500,
          f"got {MIN_TRAINING_SAMPLES}")

    trainer_features = _get_feature_names()
    check("scalp_trainer _get_feature_names() returns 77",
          len(trainer_features) == 77, f"got {len(trainer_features)}")

except Exception as e:
    check("scalp_trainer imports cleanly", False, str(e))

# Mock round-trip: train → save → load → predict
try:
    from xgboost import XGBClassifier
    import tempfile

    feature_names = get_base_feature_names() + get_scalp_feature_names()
    n = 100
    X_mock = np.random.randn(n, len(feature_names))
    y_mock = np.random.choice([0, 1, 2], size=n)

    clf = XGBClassifier(
        n_estimators=10, max_depth=3, num_class=3,
        objective="multi:softprob", eval_metric="mlogloss",
        use_label_encoder=False, verbosity=0,
    )
    clf.fit(X_mock, y_mock)

    predictor = ScalpPredictor()
    predictor.set_model(clf, feature_names)

    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        tmp_path = tmp.name

    predictor.save(tmp_path, feature_names,
                   neutral_band=0.0005, avg_30min_move_pct=0.08)

    loaded = ScalpPredictor(tmp_path)
    check("Save/load round-trip: feature count preserved",
          len(loaded.get_feature_names()) == 77)
    check("Save/load round-trip: avg_30min_move_pct preserved",
          loaded.get_avg_30min_move_pct() == 0.08)

    features = {name: float(np.random.randn()) for name in feature_names}
    result = loaded.predict(features)
    check("Save/load round-trip: predict returns float",
          isinstance(result, float) and -1.0 <= result <= 1.0,
          f"got {result} (type={type(result).__name__})")

    os.unlink(tmp_path)

except Exception as e:
    check("Mock round-trip (train → save → load → predict)", False, str(e))


# ══════════════════════════════════════════════════════════════════
# P5P3 — Scalp Strategy
# ══════════════════════════════════════════════════════════════════
section("P5P3 — Scalp Strategy")

# Strategy file
p = ROOT / "strategies" / "scalp_strategy.py"
check("strategies/scalp_strategy.py exists", p.exists())

try:
    from strategies.scalp_strategy import ScalpStrategy
    from strategies.base_strategy import BaseOptionsStrategy

    check("ScalpStrategy imports cleanly", True)
    check("ScalpStrategy inherits BaseOptionsStrategy",
          issubclass(ScalpStrategy, BaseOptionsStrategy))
    check("ScalpStrategy has on_trading_iteration",
          hasattr(ScalpStrategy, "on_trading_iteration"))
    check("ScalpStrategy has _check_exits",
          hasattr(ScalpStrategy, "_check_exits"))
    check("ScalpStrategy has _check_entries",
          hasattr(ScalpStrategy, "_check_entries"))

except Exception as e:
    check("ScalpStrategy imports cleanly", False, str(e))

# main.py routing
try:
    from main import _get_strategy_class

    cls = _get_strategy_class("scalp")
    check("main.py routes 'scalp' → ScalpStrategy",
          cls.__name__ == "ScalpStrategy",
          f"got {cls.__name__}")

    # Verify other presets still work
    check("main.py routes 'swing' → SwingStrategy",
          _get_strategy_class("swing").__name__ == "SwingStrategy")
    check("main.py routes 'general' → GeneralStrategy",
          _get_strategy_class("general").__name__ == "GeneralStrategy")

except Exception as e:
    check("main.py strategy routing", False, str(e))

# base_strategy.py scalp branches
try:
    source = (ROOT / "strategies" / "base_strategy.py").read_text()

    scalp_checks = {
        "scalp_eod exit rule": "scalp_eod" in source,
        "min_confidence threshold": "min_confidence" in source,
        "equity gate": "equity" in source.lower(),
        "ScalpPredictor import": "ScalpPredictor" in source,
        "bar_granularity in cache": "bar_granularity" in source,
        "avg_30min_move or get_avg_30min_move_pct": (
            "avg_30min_move" in source or "get_avg_30min_move_pct" in source
        ),
    }

    for name, found in scalp_checks.items():
        check(f"base_strategy scalp branch: {name}", found)

except Exception as e:
    check("base_strategy.py scalp branches", False, str(e))


# ══════════════════════════════════════════════════════════════════
# P5P4 — UI Scalp Preset
# ══════════════════════════════════════════════════════════════════
section("P5P4 — UI Scalp Preset")

ui_dir = ROOT / "ui"
if not ui_dir.exists():
    check("UI directory exists", False, "ui/ not found")
else:
    # ProfileForm — scalp preset
    pf_file = ui_dir / "src" / "components" / "ProfileForm.tsx"
    if pf_file.exists():
        content = pf_file.read_text()
        check("'scalp' in ProfileForm PRESETS", "'scalp'" in content or '"scalp"' in content)
        check("Scalp description in ProfileForm", "0DTE" in content or "scalp" in content.lower())
        check("min_confidence in ProfileForm",
              "min_confidence" in content or "minConfidence" in content)
    else:
        check("ProfileForm.tsx exists", False)

    # ProfileDetail — xgb_classifier
    pd_file = ui_dir / "src" / "pages" / "ProfileDetail.tsx"
    if pd_file.exists():
        content = pd_file.read_text()
        check("'xgb_classifier' in ProfileDetail model dropdown",
              "xgb_classifier" in content)
        check("Classifier metrics (acc_all) in ProfileDetail",
              "acc_all" in content)
    else:
        check("ProfileDetail.tsx exists", False)

    # Profiles page — scalp styling
    profiles_file = ui_dir / "src" / "pages" / "Profiles.tsx"
    if profiles_file.exists():
        content = profiles_file.read_text()
        check("Scalp preset styling in Profiles.tsx",
              "scalp" in content)
    else:
        check("Profiles.tsx exists", False)

    # Types — scalp in union
    types_file = ui_dir / "src" / "types" / "api.ts"
    if types_file.exists():
        content = types_file.read_text()
        check("'scalp' in api.ts Profile preset type",
              "'scalp'" in content or '"scalp"' in content)
    else:
        check("api.ts exists", False)

    # Build check
    result = subprocess.run(
        "npm run build",
        cwd=ui_dir,
        capture_output=True, text=True,
        shell=True,
    )
    check("npm run build succeeds", result.returncode == 0,
          result.stderr[-300:] if result.returncode != 0 else "")


# ══════════════════════════════════════════════════════════════════
# Backend — xgb_classifier routing
# ══════════════════════════════════════════════════════════════════
section("Backend — xgb_classifier Routing")

try:
    routes_source = (ROOT / "backend" / "routes" / "models.py").read_text()
    check("'xgb_classifier' in models.py validation",
          "xgb_classifier" in routes_source)
    check("'_scalp_train_job' in models.py",
          "_scalp_train_job" in routes_source)
    check("ScalpPredictor in _extract_and_persist_importance",
          "ScalpPredictor" in routes_source)
except Exception as e:
    check("Backend models.py scalp routing", False, str(e))

# Strategy model loading
try:
    strategy_source = (ROOT / "strategies" / "base_strategy.py").read_text()
    check("xgb_classifier branch in strategy model loading",
          "xgb_classifier" in strategy_source and "ScalpPredictor" in strategy_source)
except Exception as e:
    check("Strategy model loading", False, str(e))


# ══════════════════════════════════════════════════════════════════
# CONFIG — Scalp Preset Defaults
# ══════════════════════════════════════════════════════════════════
section("Config — Scalp Preset Defaults")

try:
    from config import PRESET_DEFAULTS, ALL_SYMBOLS

    scalp = PRESET_DEFAULTS.get("scalp")
    check("'scalp' preset exists in PRESET_DEFAULTS", scalp is not None)

    if scalp:
        config_checks = {
            "min_dte=0": scalp.get("min_dte") == 0,
            "max_dte=0": scalp.get("max_dte") == 0,
            "sleeptime='1M'": scalp.get("sleeptime") == "1M",
            "max_hold_days=0": scalp.get("max_hold_days") == 0,
            "prediction_horizon='30min'": scalp.get("prediction_horizon") == "30min",
            "profit_target_pct=20": scalp.get("profit_target_pct") == 20,
            "stop_loss_pct=15": scalp.get("stop_loss_pct") == 15,
            "max_position_pct=10": scalp.get("max_position_pct") == 10,
            "max_contracts=10": scalp.get("max_contracts") == 10,
            "max_daily_trades=20": scalp.get("max_daily_trades") == 20,
            "bar_granularity='1min'": scalp.get("bar_granularity") == "1min",
            "feature_set='scalp'": scalp.get("feature_set") == "scalp",
            "requires_min_equity=25000": scalp.get("requires_min_equity") == 25000,
        }
        for label, passed in config_checks.items():
            check(f"scalp.{label}", passed,
                  f"actual: {scalp.get(label.split('=')[0].strip())}" if not passed else "")

    check("'SPY' in ALL_SYMBOLS", "SPY" in ALL_SYMBOLS,
          f"ALL_SYMBOLS={ALL_SYMBOLS}")

except Exception as e:
    check("Config scalp preset", False, str(e))


# ══════════════════════════════════════════════════════════════════
# Architecture Compliance — Required Files
# ══════════════════════════════════════════════════════════════════
section("Architecture Compliance — Required Files")

required_files = [
    # Phase 5 new files
    "ml/scalp_predictor.py",
    "ml/scalp_trainer.py",
    "ml/feature_engineering/scalp_features.py",
    "strategies/scalp_strategy.py",
    # Existing files that must still exist
    "ml/trainer.py",
    "ml/xgboost_predictor.py",
    "ml/predictor.py",
    "ml/tft_predictor.py",
    "ml/tft_trainer.py",
    "ml/ensemble_predictor.py",
    "ml/feature_engineering/base_features.py",
    "ml/feature_engineering/swing_features.py",
    "ml/feature_engineering/general_features.py",
    "ml/ev_filter.py",
    "strategies/base_strategy.py",
    "strategies/swing_strategy.py",
    "strategies/general_strategy.py",
    "backend/app.py",
    "backend/routes/models.py",
    "backend/routes/profiles.py",
    "config.py",
    "main.py",
]

for rel_path in required_files:
    p = ROOT / rel_path
    check(rel_path, p.exists())


# ══════════════════════════════════════════════════════════════════
# DB — Trained Scalp Model (if any)
# ══════════════════════════════════════════════════════════════════
section("DB — Trained Scalp Model Metrics (if any)")

try:
    from config import DB_PATH
    db_path = str(DB_PATH)

    if not Path(db_path).exists():
        check("Database exists", False, f"Not found: {db_path}")
    else:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row

        # Check for xgb_classifier models
        cursor = con.execute(
            "SELECT id, profile_id, status, metrics FROM models "
            "WHERE model_type = 'xgb_classifier' ORDER BY created_at DESC LIMIT 1"
        )
        row = cursor.fetchone()

        if row:
            metrics = json.loads(row["metrics"]) if row["metrics"] else {}
            dir_acc = metrics.get("dir_acc", 0)
            acc_all = metrics.get("acc_all", 0)
            samples = metrics.get("training_samples", 0)

            check("Scalp model exists in DB", True,
                  f"model_id={row['id'][:8]}... status={row['status']}")
            check("Scalp model status = 'ready'", row["status"] == "ready",
                  f"got '{row['status']}'")
            check(f"Directional accuracy > 0.52",
                  dir_acc > 0.52,
                  f"dir_acc={dir_acc:.4f}",
                  warn_only=True)
            check(f"Overall accuracy > 0.33 (above random)",
                  acc_all > 0.33,
                  f"acc_all={acc_all:.4f}",
                  warn_only=True)
            check(f"Training samples >= 500",
                  samples >= 500,
                  f"samples={samples}",
                  warn_only=True)

            # Class distribution
            class_dist = metrics.get("class_distribution")
            if class_dist:
                print(f"              Class distribution: "
                      f"DOWN={class_dist.get('down', '?')} "
                      f"NEUTRAL={class_dist.get('neutral', '?')} "
                      f"UP={class_dist.get('up', '?')}")
        else:
            check("Scalp model exists in DB", False,
                  "No xgb_classifier model found — train one to resolve",
                  warn_only=True)

        con.close()

except Exception as e:
    check("DB scalp model check", False, str(e))


# ══════════════════════════════════════════════════════════════════
# Backward Compatibility — Swing/General Unchanged
# ══════════════════════════════════════════════════════════════════
section("Backward Compatibility")

try:
    # Swing features still work
    from ml.feature_engineering.swing_features import get_swing_feature_names
    swing_total = len(get_base_feature_names()) + len(get_swing_feature_names())
    check("Swing total features = 72 (67 base + 5 swing)", swing_total == 72,
          f"got {swing_total}")

    # General features still work
    from ml.feature_engineering.general_features import get_general_feature_names
    general_total = len(get_base_feature_names()) + len(get_general_feature_names())
    check("General total features = 71 (67 base + 4 general)", general_total == 71,
          f"got {general_total}")

    # XGBoostPredictor still works
    from ml.xgboost_predictor import XGBoostPredictor
    check("XGBoostPredictor still imports", True)

    # TFTPredictor still works
    from ml.tft_predictor import TFTPredictor
    check("TFTPredictor still imports", True)

    # EnsemblePredictor still works
    from ml.ensemble_predictor import EnsemblePredictor
    check("EnsemblePredictor still imports", True)

    # Strategy classes all exist
    from strategies.swing_strategy import SwingStrategy
    from strategies.general_strategy import GeneralStrategy
    check("SwingStrategy still imports", True)
    check("GeneralStrategy still imports", True)

except Exception as e:
    check("Backward compatibility", False, str(e))


# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════
section("SUMMARY")

total = len(results)
passed = sum(1 for s, _, _ in results if "PASS" in s)
warned = sum(1 for s, _, _ in results if "WARN" in s)
failed = sum(1 for s, _, _ in results if "FAIL" in s)

print(f"\n  Total checks : {total}")
print(f"  Passed       : {passed}")
print(f"  Warnings     : {warned}  (need trained scalp model to resolve)")
print(f"  Failed       : {failed}")

if failed == 0:
    print(f"\n  ✓ Phase 5 checkpoint PASSED ({warned} warnings)")
    if warned > 0:
        print(f"    Warnings are expected if a scalp model has not been trained yet.")
        print(f"    To resolve:")
        print(f"      1. Start the UI and create a new profile with 'scalp' preset on SPY")
        print(f"      2. Click Train → xgb_classifier")
        print(f"      3. Wait for training to complete (~10 min for 2 years of 1-min data)")
        print(f"      4. Re-run this checkpoint")
else:
    print(f"\n  ✗ Phase 5 checkpoint FAILED — {failed} check(s) require fixes")
    print(f"\n  Failed checks:")
    for s, label, detail in results:
        if "FAIL" in s:
            print(f"    • {label}")
            if detail:
                print(f"      {detail}")

print()
sys.exit(1 if fail_count > 0 else 0)
