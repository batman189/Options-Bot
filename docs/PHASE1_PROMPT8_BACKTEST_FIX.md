# PHASE 1 PROMPT 8 — Backtest Fix: Revert Daily Workaround, Use 5-Min Bars

## TASK
Fix the backtest to use 5-minute bars (matching the trained model and live trading) instead of the daily bar workaround. Revert ALL changes that Claude Code made to accommodate daily bars. Fix the silent failure in `_check_entries()` that hid the zero-trade problem.

**ROOT CAUSE**: Lumibot's `ThetaDataBacktesting` with `sleeptime="1D"` only loaded daily bars. The strategy called `get_historical_prices(timestep="5min")`, got `None` back, and the `try/except` silently swallowed the error → 0 trades for the entire year.

**FIX**: Change backtest sleeptime to `"5min"` so Lumibot loads minute data. This is slower (~30-60 min for 1 year) but tests the ACTUAL model with the ACTUAL features. Also improve error logging so silent failures never happen again.

---

## IMPORTANT: READ BEFORE CODING

Before making ANY changes, read the current state of these files to understand what was changed by the previous daily-bar workaround:

```bash
cat strategies/base_strategy.py
cat strategies/swing_strategy.py
cat ml/feature_engineering/base_features.py
cat ml/feature_engineering/swing_features.py
cat scripts/backtest.py
cat config.py
ls -la models/*.joblib
```

You need to identify and revert ALL daily-bar workaround changes. The daily-bar model that was retrained should be ignored — we use the original 5-min model.

---

## FILES TO MODIFY

1. `options-bot/scripts/backtest.py` — Change sleeptime from `"1D"` to `"5min"`
2. `options-bot/strategies/base_strategy.py` — Fix silent failure logging in `_check_entries()`
3. Revert ANY changes made to `base_features.py`, `swing_features.py`, `general_features.py`, `base_strategy.py`, or `swing_strategy.py` that were part of the daily-bar workaround

---

## CHANGE 1: `options-bot/scripts/backtest.py`

Find every occurrence of `sleeptime="1D"` and change to `sleeptime="5min"`.

Also find and change the log line that says `"Sleeptime:  1D (daily for backtest efficiency)"` to `"Sleeptime:  5min (matches live trading)"`.

Also find and change the config override `config["sleeptime"] = "1D"` to `config["sleeptime"] = "5min"`.

The relevant sections that MUST be updated:

### In the `run_backtest()` function header logging:
```python
    logger.info(f"  Sleeptime:  5min (matches live trading)")
```

### In the config override section:
```python
    config = PRESET_DEFAULTS.get(preset, PRESET_DEFAULTS["swing"]).copy()
    # Use 5min to match the trained model's feature resolution
    config["sleeptime"] = "5min"
```

### In the `run_backtest` / `backtest` method call:
```python
                sleeptime="5min",
```

This appears in TWO places (the `if has_run_backtest` branch and the `elif has_backtest` branch). Change BOTH.

---

## CHANGE 2: `options-bot/strategies/base_strategy.py`

The `_check_entries()` method has a try/except around `get_historical_prices()` that logs an error but doesn't make it clear that THIS is why no trades are happening. Replace the historical bars section with better logging:

Find this block in `_check_entries()`:
```python
        # Step 2: Get historical bars for feature computation
        try:
            bars_result = self.get_historical_prices(
                self._stock_asset, length=200, timestep="5min"
            )
            if bars_result is None or bars_result.df.empty:
                logger.warning("No historical bars available")
                return
            bars_df = bars_result.df
        except Exception as e:
            logger.error(f"Failed to get historical bars: {e}")
            return
```

Replace with:
```python
        # Step 2: Get historical bars for feature computation
        # Uses 5min bars — requires minute data in the data store.
        # In backtesting, the backtest sleeptime MUST be "5min" (not "1D")
        # or Lumibot won't load minute data and this will return None.
        try:
            bars_result = self.get_historical_prices(
                self._stock_asset, length=200, timestep="5min"
            )
        except Exception as e:
            logger.error(
                f"CRITICAL: get_historical_prices() raised an exception: {e}. "
                f"This usually means the data store has no minute data. "
                f"If backtesting, ensure sleeptime='5min' (not '1D').",
                exc_info=True,
            )
            return

        if bars_result is None:
            logger.error(
                "CRITICAL: get_historical_prices() returned None. "
                "No minute data available. If backtesting with ThetaData, "
                "the backtest sleeptime must be '5min' so Lumibot loads minute bars. "
                "Using sleeptime='1D' only loads daily bars and 5min requests will fail."
            )
            return

        if bars_result.df is None or bars_result.df.empty:
            logger.warning(
                "Historical bars returned but DataFrame is empty. "
                f"Requested 200 bars of 5min data for {self.symbol}."
            )
            return

        bars_df = bars_result.df
        logger.info(f"  Got {len(bars_df)} historical bars for feature computation")
```

---

## CHANGE 3: Revert Daily-Bar Workaround Changes

The previous Claude Code session made changes to accommodate daily bars. You MUST identify and revert ALL of them. Specifically, check for and revert:

### In `strategies/base_strategy.py`:
- If `timestep` was changed from `"5min"` to `"day"` anywhere, change it back to `"5min"`
- If there's any "auto-detect daily vs intraday" logic, REMOVE it — the strategy always uses 5min bars

### In `ml/feature_engineering/base_features.py`:
- If any "auto-detect bar frequency" or "daily bar adjustment" logic was added, REMOVE it
- The `BARS_PER_DAY = 78` constant must exist (78 five-min bars per 6.5-hour trading day)
- All lookback windows must use 5-min bar counts:
  - `ret_1hr` = 12 bars (not 1)
  - `ret_4hr` = 48 bars (not 1)
  - `ret_1d` = 78 bars (not 1)
  - `ret_5d` = 390 bars (not 5)
  - `ret_10d` = 780 bars (not 10)
  - `ret_20d` = 1560 bars (not 20)
  - All SMA/EMA/RSI/MACD/BB periods stay as originally written for 5-min bars

### In `ml/feature_engineering/swing_features.py`:
- Same — revert any daily bar accommodations

### In `ml/feature_engineering/general_features.py`:
- Same — revert any daily bar accommodations

### In `strategies/swing_strategy.py`:
- Should be a thin subclass that only inherits from `BaseOptionsStrategy` — revert any changes

### In `config.py`:
- Should NOT have been changed by the workaround, but verify

### Model file:
- The daily-bar retrained model should be IGNORED (do not delete it, just don't use it)
- The ORIGINAL 5-min model is the one whose filename contains `fa320eac` — verify it still exists:
  ```bash
  ls -la models/*fa320eac*.joblib
  ```
- If it was deleted or renamed, we need to retrain (see FALLBACK below)

---

## FALLBACK: If Original 5-Min Model Is Missing

If the original model file (`*fa320eac*.joblib`) was deleted, retrain it:

```bash
cd options-bot
python scripts/train_model.py --symbol TSLA --preset swing --years 2
```

Use the NEW model file path for the backtest command.

---

## VERIFICATION

After making all changes, run these checks IN ORDER:

```bash
cd options-bot

# 1. Verify sleeptime is 5min in backtest.py
echo "=== Check backtest.py sleeptime ==="
grep -n "sleeptime" scripts/backtest.py
# Expected: ALL occurrences should show "5min", NONE should show "1D"

# 2. Verify strategy uses 5min bars
echo ""
echo "=== Check strategy timestep ==="
grep -n "timestep" strategies/base_strategy.py
# Expected: timestep="5min" — NOT "day"

# 3. Verify feature engineering uses 5min lookbacks
echo ""
echo "=== Check feature lookback windows ==="
grep -n "BARS_PER_DAY" ml/feature_engineering/base_features.py
# Expected: BARS_PER_DAY = 78

# 4. Verify no daily-bar auto-detect logic exists
echo ""
echo "=== Check for daily bar workaround remnants ==="
grep -rn "daily\|auto.detect\|bar_freq\|is_daily\|timestep.*day" \
    ml/feature_engineering/ strategies/ --include="*.py"
# Expected: No matches (or only in comments/docstrings)

# 5. Verify original 5-min model exists
echo ""
echo "=== Check model files ==="
ls -la models/*.joblib
# Expected: The fa320eac model should be present

# 6. Verify imports still work
echo ""
echo "=== Test imports ==="
python -c "from strategies.swing_strategy import SwingStrategy; print('✅ SwingStrategy imports')"
python -c "from ml.feature_engineering.base_features import compute_base_features; print('✅ base_features imports')"
python -c "from scripts.backtest import run_backtest; print('✅ backtest imports')"

# 7. Verify Theta Terminal is running
echo ""
echo "=== Theta Terminal check ==="
python -c "
import requests
try:
    r = requests.get('http://localhost:25503/v2/list/roots/option', params={'sec': 'OPRA'}, timeout=5)
    print(f'✅ Theta Terminal running (status {r.status_code})')
except:
    print('❌ Theta Terminal NOT running')
"
```

---

## RUNNING THE BACKTEST

After verification passes:

```bash
cd options-bot

# Find the 5-min model
MODEL=$(ls models/*fa320eac*.joblib 2>/dev/null | head -1)
if [ -z "$MODEL" ]; then
    MODEL=$(ls models/*.joblib 2>/dev/null | head -1)
fi
echo "Using model: $MODEL"

# Run a SHORT test first (3 months) to verify it works
python scripts/backtest.py --model-path "$MODEL" --start 2025-01-01 --end 2025-03-31

# If that works and produces trades, run the full year
python scripts/backtest.py --model-path "$MODEL" --start 2025-01-01 --end 2025-12-31
```

**EXPECTED RUNTIME**: 
- 3 months: ~10-15 minutes
- 1 year: ~30-60 minutes

This is significantly slower than the "1D" approach but it's testing the REAL model with REAL features.

---

## WHAT SUCCESS LOOKS LIKE

1. All `sleeptime` references in backtest.py show `"5min"` — zero instances of `"1D"`
2. Strategy uses `timestep="5min"` — not `"day"`
3. Feature engineering uses `BARS_PER_DAY = 78` with 5-min lookback windows
4. No daily-bar workaround code remains anywhere
5. The 3-month test backtest produces **at least 1 trade** (confirms the pipeline works)
6. The full-year backtest produces a tearsheet with actual performance data
7. Console output shows `CRITICAL` log messages if bars are unavailable (not silent swallowing)

## WHAT FAILURE LOOKS LIKE

- **0 trades again**: If the 3-month test still shows 0 trades, check the logs for the new `CRITICAL` messages. They will tell you exactly what failed (no bars, no prediction, etc.)
- **Import errors**: A revert went too far or missed a dependency
- **Backtest crashes**: Theta Terminal may not have minute data for the requested period. Check Theta Terminal logs.
- **Model not found**: The original was deleted — retrain per FALLBACK section above

## DO NOT

- Do NOT keep any daily-bar workaround code
- Do NOT retrain a daily-bar model
- Do NOT change `sleeptime` back to `"1D"` for speed — correctness > speed
- Do NOT modify the feature list (65 features) — only revert lookback windows to 5-min values
- Do NOT add any new files or features
- Do NOT modify `config.py` preset defaults
