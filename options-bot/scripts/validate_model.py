"""
Validate a trained model's feature completeness and usage.

Usage:
    python scripts/validate_model.py                    # validate all models in DB
    python scripts/validate_model.py <model_path>       # validate a specific .joblib or TFT dir
    python scripts/validate_model.py --preset swing     # check against swing feature list

Reports:
    - Feature list completeness (expected vs actual)
    - Options feature coverage (27 options features)
    - Feature importance distribution (zero-importance features)
    - Flags models trained without Theta Terminal data
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import joblib
import numpy as np

from ml.feature_engineering.base_features import get_base_feature_names
from ml.feature_engineering.swing_features import get_swing_feature_names
from ml.feature_engineering.general_features import get_general_feature_names
from ml.feature_engineering.scalp_features import get_scalp_feature_names


OPTIONS_FEATURE_PREFIXES = (
    "atm_", "iv_", "rv_iv", "put_call",
    "theta_delta", "gamma_theta", "vega_theta",
)


def get_expected_features(preset: str) -> list[str]:
    base = get_base_feature_names()
    if preset == "swing":
        return base + get_swing_feature_names()
    elif preset == "general":
        return base + get_general_feature_names()
    elif preset == "scalp":
        return base + get_scalp_feature_names()
    return base


def validate_xgboost(model_path: str, preset: str = "swing"):
    """Validate an XGBoost .joblib model."""
    path = Path(model_path)
    if not path.exists():
        print(f"  ERROR: File not found: {path}")
        return False

    data = joblib.load(path)
    feature_names = data["feature_names"]
    model = data["model"]

    print(f"\n{'='*60}")
    print(f"XGBoost Model: {path.name}")
    print(f"{'='*60}")

    expected = get_expected_features(preset)
    return _validate_features(feature_names, expected, model=model)


def validate_tft(model_dir: str, preset: str = "swing"):
    """Validate a TFT model directory."""
    path = Path(model_dir)
    metadata_path = path / "metadata.json"

    if not metadata_path.exists():
        print(f"  ERROR: metadata.json not found in {path}")
        return False

    with open(metadata_path) as f:
        metadata = json.load(f)

    feature_names = metadata["feature_names"]

    print(f"\n{'='*60}")
    print(f"TFT Model: {path.name}")
    print(f"{'='*60}")

    expected = get_expected_features(preset)
    return _validate_features(feature_names, expected)


def validate_ensemble(model_path: str, preset: str = "swing"):
    """Validate an ensemble .joblib model."""
    path = Path(model_path)
    if not path.exists():
        print(f"  ERROR: File not found: {path}")
        return False

    data = joblib.load(path)
    feature_names = data["feature_names"]

    print(f"\n{'='*60}")
    print(f"Ensemble Model: {path.name}")
    print(f"{'='*60}")
    print(f"  XGB weight: {data.get('xgb_weight', '?'):.4f}")
    print(f"  TFT weight: {data.get('tft_weight', '?'):.4f}")
    print(f"  XGB path:   {data.get('xgb_model_path', '?')}")
    print(f"  TFT dir:    {data.get('tft_model_dir', '?')}")

    expected = get_expected_features(preset)
    return _validate_features(feature_names, expected)


def _validate_features(feature_names: list[str], expected: list[str], model=None) -> bool:
    """Core validation logic. Returns True if model passes."""
    passed = True

    # Feature completeness
    missing = [f for f in expected if f not in feature_names]
    extra = [f for f in feature_names if f not in expected]

    print(f"\n  Features: {len(feature_names)} (expected {len(expected)})")

    if missing:
        print(f"  FAIL — Missing {len(missing)} features:")
        for f in missing:
            print(f"    - {f}")
        passed = False
    else:
        print(f"  PASS — All expected features present")

    if extra:
        print(f"  NOTE — {len(extra)} extra features: {extra}")

    # Options feature coverage
    options_expected = [f for f in expected if f.startswith(OPTIONS_FEATURE_PREFIXES)]
    options_present = [f for f in options_expected if f in feature_names]
    options_missing = [f for f in options_expected if f not in feature_names]

    print(f"\n  Options features: {len(options_present)}/{len(options_expected)}")
    if options_missing:
        print(f"  FAIL — Missing options features (was Theta Terminal running?):")
        for f in options_missing:
            print(f"    - {f}")
        passed = False
    else:
        print(f"  PASS — All options features present")

    # Feature importance (XGBoost only)
    if model is not None and hasattr(model, "feature_importances_"):
        importance = dict(zip(feature_names, model.feature_importances_.tolist()))
        zero_imp = [f for f, v in importance.items() if v == 0.0]
        options_zero = [f for f in zero_imp if f.startswith(OPTIONS_FEATURE_PREFIXES)]

        print(f"\n  Zero-importance features: {len(zero_imp)}/{len(feature_names)}")
        if options_zero:
            print(f"  WARNING — {len(options_zero)} options features have zero importance:")
            for f in options_zero:
                print(f"    - {f}")
        if zero_imp and not options_zero:
            print(f"  INFO — Zero-importance features (non-options): {zero_imp[:5]}{'...' if len(zero_imp) > 5 else ''}")

        # Top 10
        top10 = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
        print(f"\n  Top 10 features:")
        for name, imp in top10:
            marker = " (options)" if name.startswith(OPTIONS_FEATURE_PREFIXES) else ""
            print(f"    {name}: {imp:.4f}{marker}")

    # Deprecated feature check
    if "general_sector_rel_strength" in feature_names:
        print(f"\n  WARNING — Model contains deprecated 'general_sector_rel_strength' (always NaN)")
        print(f"           This model was trained before the fix. Retrain recommended.")
        passed = False

    result = "PASS" if passed else "FAIL"
    print(f"\n  Result: {result}")
    print(f"{'='*60}")
    return passed


def validate_all_from_db():
    """Validate all models registered in the database."""
    import asyncio
    import aiosqlite
    from config import DB_PATH

    async def _query():
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, profile_id, model_type, file_path, feature_names "
                "FROM models WHERE status = 'ready' ORDER BY created_at DESC"
            )
            return await cursor.fetchall()

    rows = asyncio.run(_query())
    if not rows:
        print("No models found in database.")
        return

    print(f"Found {len(rows)} model(s) in database\n")
    all_passed = True

    for row in rows:
        model_type = row["model_type"]
        file_path = row["file_path"]
        # Determine preset from feature list
        feature_names = json.loads(row["feature_names"]) if row["feature_names"] else []
        preset = "swing" if any(f.startswith("swing_") for f in feature_names) else \
                 "general" if any(f.startswith("general_") for f in feature_names) else \
                 "scalp" if any(f.startswith("scalp_") for f in feature_names) else "base"

        try:
            if model_type in ("xgboost", "xgb_classifier", "lightgbm"):
                ok = validate_xgboost(file_path, preset)
            elif model_type == "tft":
                ok = validate_tft(file_path, preset)
            elif model_type == "ensemble":
                ok = validate_ensemble(file_path, preset)
            else:
                print(f"Unknown model type: {model_type}")
                ok = False
        except Exception as e:
            print(f"  ERROR validating {file_path}: {e}")
            ok = False

        if not ok:
            all_passed = False

    print(f"\n{'='*60}")
    print(f"Overall: {'ALL PASSED' if all_passed else 'SOME FAILED — retrain recommended'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    args = sys.argv[1:]

    preset = "swing"
    # Check for --preset flag
    if "--preset" in args:
        idx = args.index("--preset")
        if idx + 1 < len(args):
            preset = args[idx + 1]
            args = [a for i, a in enumerate(args) if i != idx and i != idx + 1]

    if not args:
        # No path given — validate all from DB
        validate_all_from_db()
    else:
        path = Path(args[0])
        if path.is_dir():
            validate_tft(str(path), preset)
        elif path.suffix == ".joblib":
            # Detect ensemble vs xgboost
            data = joblib.load(path)
            if "meta_learner" in data:
                validate_ensemble(str(path), preset)
            else:
                validate_xgboost(str(path), preset)
        else:
            print(f"Unknown model format: {path}")
            sys.exit(1)
