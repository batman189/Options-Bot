"""Quick diagnostic to test the strategy's entry logic without Lumibot."""
import sys, logging, math
from pathlib import Path

# Add project root to sys.path — no setup.py/pyproject.toml in this project
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(name)s | %(levelname)s | %(message)s')
logger = logging.getLogger('diagnostic')

# Step 1: Load model (accept path as CLI argument, fall back to default)
from ml.xgboost_predictor import XGBoostPredictor
from config import PRESET_DEFAULTS

DEFAULT_MODEL_PATH = 'models/d6c9e6c0-c60d-4c88-a395-706329ad37fe_swing_TSLA_fa320eac.joblib'
model_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_PATH
predictor = XGBoostPredictor(model_path)
feature_names = predictor.get_feature_names()
print(f'\n=== MODEL INFO ===')
print(f'Model: {model_path}')
print(f'Features expected ({len(feature_names)}): {feature_names[:10]}...')
print(f'Last 5: {feature_names[-5:]}')

# Step 2: Get bars via Alpaca (simulating what Lumibot backtest would provide)
from data.alpaca_provider import AlpacaStockProvider
from datetime import datetime
provider = AlpacaStockProvider()
bars = provider.get_historical_bars('TSLA', datetime(2024, 6, 1), datetime(2025, 6, 1), timeframe='5min')
print(f'\n=== BARS INFO ===')
print(f'Bars shape: {bars.shape}')
print(f'Columns: {list(bars.columns)}')
print(f'Index type: {type(bars.index).__name__}')
print(f'Date range: {bars.index[0]} to {bars.index[-1]}')
print(f'Sample:\n{bars.tail(3)}')

# Step 3: Compute features
from ml.feature_engineering.base_features import compute_base_features
from ml.feature_engineering.swing_features import compute_swing_features
featured = compute_base_features(bars.copy())
featured = compute_swing_features(featured)
print(f'\n=== FEATURES INFO ===')
print(f'Featured shape: {featured.shape}')

# Step 4: Check feature alignment
latest = featured.iloc[-1].to_dict()
nan_count = sum(1 for v in latest.values() if isinstance(v, float) and math.isnan(v))
total = len(latest)
print(f'Total features: {total}, NaN count: {nan_count}')

model_features = set(feature_names)
computed_features = set(featured.columns) - {'open', 'high', 'low', 'close', 'volume'}
missing = model_features - computed_features
extra = computed_features - model_features
print(f'Model expects {len(model_features)} features')
print(f'Computed {len(computed_features)} features')
if missing:
    print(f'MISSING from computed (model needs): {missing}')
if extra:
    print(f'EXTRA in computed (model ignores): {extra}')

# Step 5: Try predictions across multiple dates
# Use min_ev_pct from config (swing preset default) instead of hardcoded threshold
min_ev_pct = PRESET_DEFAULTS.get("swing", {}).get("min_ev_pct", 10)
print(f'\n=== PREDICTIONS ACROSS LAST 20 TRADING DAYS (threshold={min_ev_pct}%) ===')
trade_count = 0
for i in range(-20, 0):
    row = featured.iloc[i].to_dict()
    pred = predictor.predict(row)
    dt = featured.index[i]
    would_trade = abs(pred) >= min_ev_pct
    if would_trade:
        trade_count += 1
    print(f'  {dt}: predicted={pred:+.4f}%, threshold={min_ev_pct}%, trade={"YES" if would_trade else "no"}')

print(f'\nWould have traded on {trade_count}/20 days')
print(f'\n=== DONE ===')
