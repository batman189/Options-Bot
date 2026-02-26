# PHASE 4 PROMPT 5 — Backend Ensemble Training Support

## CONTEXT

Phase 4 has three new model types (tft, ensemble) alongside the existing xgboost.
The backend currently only knows how to train xgboost. This prompt wires up the
full training pipeline for all three types and makes the strategy smart enough to
load whichever type is stored in the DB for a given profile.

## WHAT CHANGES — THREE FILES, TARGETED MODIFICATIONS

### 1. `backend/schemas.py`
- Add `model_type: Optional[str] = None` to `TrainRequest`
  (values: `"xgboost"` | `"tft"` | `"ensemble"` — default `"xgboost"`)
- Add `feature_importance: Optional[dict] = None` to `ModelMetrics`
  (needed by P4P6 UI to display feature importance panel)

### 2. `backend/routes/models.py`
- Add `_tft_train_job()` background function — mirrors `_full_train_job()` but calls `train_tft_model()`
- Add `_ensemble_train_job()` background function — finds existing XGB + TFT models for profile, calls `EnsemblePredictor.train_meta_learner()`
- Update `train_model_endpoint` to route to the correct job based on `body.model_type`
- After each training job completes, extract feature importance from the trained model and store it in the `metrics` JSON column in the DB (so `/metrics` endpoint returns it without needing to load the model again)
- Add `GET /api/models/{profile_id}/importance` endpoint that reads importance from the stored metrics JSON (fast — no model load required)

### 3. `strategies/base_strategy.py`
- Update `initialize()` to load the correct predictor class based on `model_type` stored in the DB
  - `"xgboost"` → `XGBoostPredictor(model_path)`
  - `"tft"` → `TFTPredictor(model_path)` (model_path is a directory)
  - `"ensemble"` → `EnsemblePredictor(model_path)`
  - Unknown / None → `XGBoostPredictor` (existing behavior, safe fallback)
- The strategy currently hardcodes `XGBoostPredictor` — this must change

---

## READ FIRST

```bash
cd options-bot

# Read both files in full before touching them
cat backend/schemas.py
cat backend/routes/models.py

# Understand the strategy's initialize() — specifically how model_path and predictor are set
grep -n "model_path\|predictor\|XGBoostPredictor\|initialize" strategies/base_strategy.py | head -40

# Understand TFT trainer entry point
grep -n "^def train_tft_model" ml/tft_trainer.py

# Understand Ensemble entry point
grep -n "^    def train_meta_learner" ml/ensemble_predictor.py

# Understand what model_type values exist in the DB
python -c "
import asyncio, aiosqlite
from config import DB_PATH
async def check():
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute('SELECT DISTINCT model_type FROM models')
        rows = await cursor.fetchall()
        print([r[0] for r in rows])
asyncio.run(check())
"
```

---

## FILE 1 CHANGES: `backend/schemas.py`

### Change 1a — Add `model_type` to `TrainRequest`

Find the `TrainRequest` class. It currently has `years_of_data` and `force_full_retrain`.
Add one field:

```python
class TrainRequest(BaseModel):
    """Optional overrides for training parameters."""
    years_of_data: Optional[int] = None
    force_full_retrain: bool = False
    model_type: Optional[str] = None  # 'xgboost' | 'tft' | 'ensemble' — default xgboost
```

### Change 1b — Add `feature_importance` to `ModelMetrics`

Find the `ModelMetrics` class and add one field after `cv_folds`:

```python
class ModelMetrics(BaseModel):
    model_id: str
    profile_id: str
    model_type: str
    mae: Optional[float] = None
    rmse: Optional[float] = None
    r2: Optional[float] = None
    directional_accuracy: Optional[float] = None
    training_samples: Optional[int] = None
    feature_count: Optional[int] = None
    cv_folds: Optional[int] = None
    feature_importance: Optional[dict] = None   # ADD THIS LINE
```

---

## FILE 2 CHANGES: `backend/routes/models.py`

### Change 2a — Add helper: extract and persist feature importance

Add this function AFTER `_set_profile_status()` and BEFORE `_full_train_job()`:

```python
def _extract_and_persist_importance(model_id: str, model_type: str, model_path: str):
    """
    Load the trained model from disk, extract feature importance, and merge it
    into the metrics JSON already stored in the DB.

    Called from each training job after the trainer saves its DB record.
    Non-fatal: logs warning on failure, does not raise.

    Args:
        model_id: UUID of the model record to update
        model_type: 'xgboost', 'tft', or 'ensemble'
        model_path: Path to the model file or directory
    """
    import asyncio as _asyncio
    import aiosqlite as _aiosqlite
    import json as _json
    from config import DB_PATH as _DB_PATH

    try:
        importance = {}

        if model_type == "xgboost":
            from ml.xgboost_predictor import XGBoostPredictor
            p = XGBoostPredictor(model_path)
            importance = p.get_feature_importance()

        elif model_type == "tft":
            from ml.tft_predictor import TFTPredictor
            p = TFTPredictor(model_path)
            importance = p.get_feature_importance()

        elif model_type == "ensemble":
            from ml.ensemble_predictor import EnsemblePredictor
            p = EnsemblePredictor(model_path)
            importance = p.get_feature_importance()

        if not importance:
            logger.warning(
                f"_extract_and_persist_importance: empty importance for "
                f"model_id={model_id} type={model_type}"
            )
            return

        # Take top 30 by importance score to keep DB record manageable
        top_importance = dict(
            sorted(importance.items(), key=lambda x: x[1], reverse=True)[:30]
        )

        async def _update():
            async with _aiosqlite.connect(str(_DB_PATH)) as db:
                db.row_factory = _aiosqlite.Row
                cursor = await db.execute(
                    "SELECT metrics FROM models WHERE id = ?", (model_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    return
                existing = _json.loads(row["metrics"]) if row["metrics"] else {}
                existing["feature_importance"] = top_importance
                await db.execute(
                    "UPDATE models SET metrics = ? WHERE id = ?",
                    (_json.dumps(existing), model_id),
                )
                await db.commit()
                logger.info(
                    f"_extract_and_persist_importance: stored top {len(top_importance)} "
                    f"features for model_id={model_id}"
                )

        _asyncio.run(_update())

    except Exception as e:
        logger.warning(
            f"_extract_and_persist_importance: failed for model_id={model_id}: {e}",
            exc_info=True,
        )
```

### Change 2b — Update `_full_train_job()` to extract importance after training

Find the existing `_full_train_job()`. After the line:
```python
        # train_model() already updates profile status to 'ready' in DB
```

Add:
```python
            # Extract and persist feature importance into metrics JSON
            _extract_and_persist_importance(
                model_id=result["model_id"],
                model_type="xgboost",
                model_path=result["model_path"],
            )
```

So the successful path in `_full_train_job()` looks like:
```python
        if result.get("status") == "ready":
            logger.info(
                f"_full_train_job: completed for profile={profile_id} "
                f"model_id={result.get('model_id')} "
                f"dir_acc={result.get('metrics', {}).get('dir_acc', 'N/A')}"
            )
            # train_model() already updates profile status to 'ready' in DB
            _extract_and_persist_importance(
                model_id=result["model_id"],
                model_type="xgboost",
                model_path=result["model_path"],
            )
```

### Change 2c — Add `_tft_train_job()` background function

Add this function AFTER `_full_train_job()`:

```python
def _tft_train_job(profile_id: str, symbol: str, preset: str, horizon: str, years: int):
    """
    Background thread: run TFT training pipeline.
    Sets profile status to 'training' at start, 'ready' on success.
    """
    logger.info(
        f"_tft_train_job: starting for profile={profile_id} "
        f"symbol={symbol} preset={preset}"
    )
    _set_profile_status(profile_id, "training")

    try:
        from ml.tft_trainer import train_tft_model
        result = train_tft_model(
            profile_id=profile_id,
            symbol=symbol,
            preset=preset,
            prediction_horizon=horizon,
            years_of_data=years,
        )
        if result.get("status") == "ready":
            logger.info(
                f"_tft_train_job: completed for profile={profile_id} "
                f"model_id={result.get('model_id')} "
                f"dir_acc={result.get('metrics', {}).get('dir_acc', 'N/A')}"
            )
            _extract_and_persist_importance(
                model_id=result["model_id"],
                model_type="tft",
                model_path=result["model_dir"],
            )
        else:
            logger.error(f"_tft_train_job: unexpected result: {result}")
            _set_profile_status(profile_id, "created")
    except Exception as e:
        logger.error(
            f"_tft_train_job: exception for profile={profile_id}: {e}",
            exc_info=True,
        )
        _set_profile_status(profile_id, "created")
    finally:
        with _active_jobs_lock:
            _active_jobs.discard(profile_id)
        logger.info(f"_tft_train_job: job slot released for profile={profile_id}")
```

### Change 2d — Add `_ensemble_train_job()` background function

Add this function AFTER `_tft_train_job()`:

```python
def _ensemble_train_job(profile_id: str, symbol: str, preset: str, horizon: str, years: int):
    """
    Background thread: train ensemble meta-learner.

    Requires that BOTH an xgboost model AND a tft model already exist for this
    profile. Finds the most recent of each type from the models table.

    If either is missing, logs an error and sets status back to 'ready'.
    """
    import asyncio as _asyncio
    import aiosqlite as _aio
    import json as _json
    from config import DB_PATH as _DB_PATH

    logger.info(
        f"_ensemble_train_job: starting for profile={profile_id} "
        f"symbol={symbol} preset={preset}"
    )
    _set_profile_status(profile_id, "training")

    try:
        # Find the most recent xgboost and tft models for this profile
        async def _find_sub_models():
            async with _aio.connect(str(_DB_PATH)) as db:
                db.row_factory = _aio.Row

                xgb_cursor = await db.execute(
                    """SELECT file_path FROM models
                       WHERE profile_id = ? AND model_type = 'xgboost' AND status = 'ready'
                       ORDER BY created_at DESC LIMIT 1""",
                    (profile_id,),
                )
                xgb_row = await xgb_cursor.fetchone()

                tft_cursor = await db.execute(
                    """SELECT file_path FROM models
                       WHERE profile_id = ? AND model_type = 'tft' AND status = 'ready'
                       ORDER BY created_at DESC LIMIT 1""",
                    (profile_id,),
                )
                tft_row = await tft_cursor.fetchone()

                return (
                    xgb_row["file_path"] if xgb_row else None,
                    tft_row["file_path"] if tft_row else None,
                )

        xgb_path, tft_dir = _asyncio.run(_find_sub_models())

        if not xgb_path:
            msg = (
                f"_ensemble_train_job: no trained xgboost model found for profile "
                f"{profile_id}. Train xgboost first."
            )
            logger.error(msg)
            _set_profile_status(profile_id, "ready")
            with _active_jobs_lock:
                _active_jobs.discard(profile_id)
            return

        if not tft_dir:
            msg = (
                f"_ensemble_train_job: no trained TFT model found for profile "
                f"{profile_id}. Train TFT first."
            )
            logger.error(msg)
            _set_profile_status(profile_id, "ready")
            with _active_jobs_lock:
                _active_jobs.discard(profile_id)
            return

        logger.info(f"  XGBoost model: {xgb_path}")
        logger.info(f"  TFT model dir: {tft_dir}")

        from ml.ensemble_predictor import EnsemblePredictor
        predictor = EnsemblePredictor()
        result = predictor.train_meta_learner(
            profile_id=profile_id,
            symbol=symbol,
            preset=preset,
            xgb_model_path=xgb_path,
            tft_model_dir=tft_dir,
            prediction_horizon=horizon,
            years_of_data=years,
        )

        if result.get("status") == "ready":
            logger.info(
                f"_ensemble_train_job: completed for profile={profile_id} "
                f"model_id={result.get('model_id')} "
                f"xgb_weight={result.get('xgb_weight', 'N/A'):.3f} "
                f"tft_weight={result.get('tft_weight', 'N/A'):.3f}"
            )
            _extract_and_persist_importance(
                model_id=result["model_id"],
                model_type="ensemble",
                model_path=result["model_path"],
            )
        else:
            logger.error(f"_ensemble_train_job: unexpected result: {result}")
            _set_profile_status(profile_id, "ready")  # Restore ready (sub-models still exist)

    except Exception as e:
        logger.error(
            f"_ensemble_train_job: exception for profile={profile_id}: {e}",
            exc_info=True,
        )
        _set_profile_status(profile_id, "ready")
    finally:
        with _active_jobs_lock:
            _active_jobs.discard(profile_id)
        logger.info(f"_ensemble_train_job: job slot released for profile={profile_id}")
```

### Change 2e — Update `train_model_endpoint` to route by model_type

In the existing `train_model_endpoint`, find where the training thread is spawned.
Currently it always does:
```python
    thread = threading.Thread(
        target=_full_train_job,
        args=(profile_id, symbol, preset, horizon, years),
        ...
    )
```

Replace THAT BLOCK (the thread creation and start, plus the return statement) with:

```python
    model_type = (body.model_type or "xgboost").lower()
    if model_type not in ("xgboost", "tft", "ensemble"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model_type '{model_type}'. Must be 'xgboost', 'tft', or 'ensemble'.",
        )

    # Select training job based on model type
    job_targets = {
        "xgboost":  (_full_train_job,      f"train-{profile_id[:8]}"),
        "tft":      (_tft_train_job,       f"tft-{profile_id[:8]}"),
        "ensemble": (_ensemble_train_job,  f"ens-{profile_id[:8]}"),
    }
    job_fn, thread_name = job_targets[model_type]

    logger.info(
        f"Spawning {model_type} training thread: profile={profile_id} "
        f"symbol={symbol} preset={preset} horizon={horizon} years={years}"
    )

    thread = threading.Thread(
        target=job_fn,
        args=(profile_id, symbol, preset, horizon, years),
        daemon=True,
        name=thread_name,
    )
    thread.start()

    type_durations = {
        "xgboost": "5–15 minutes",
        "tft": "20–60 minutes",
        "ensemble": "30–90 minutes (requires existing XGBoost + TFT models)",
    }

    return TrainingStatus(
        model_id=None,
        profile_id=profile_id,
        status="training",
        progress_pct=0.0,
        message=(
            f"{model_type.upper()} training started for {symbol} ({preset}, {years}yr). "
            f"Poll GET /api/models/{profile_id}/status for updates. "
            f"Typical duration: {type_durations[model_type]}."
        ),
    )
```

### Change 2f — Update `get_model_metrics` to include feature importance

Find the existing `get_model_metrics` endpoint. It currently returns a `ModelMetrics`
object. Update the return to include `feature_importance`:

```python
    metrics = json.loads(model_row["metrics"]) if model_row["metrics"] else {}
    features = json.loads(model_row["feature_names"]) if model_row["feature_names"] else []

    return ModelMetrics(
        model_id=model_row["id"],
        profile_id=profile_id,
        model_type=model_row["model_type"],
        mae=metrics.get("mae"),
        rmse=metrics.get("rmse"),
        r2=metrics.get("r2"),
        directional_accuracy=metrics.get("dir_acc"),
        training_samples=metrics.get("training_samples"),
        feature_count=len(features),
        cv_folds=metrics.get("cv_folds"),
        feature_importance=metrics.get("feature_importance"),  # ADD THIS LINE
    )
```

### Change 2g — Add `GET /api/models/{profile_id}/importance` endpoint

Add this new endpoint AFTER the `get_model_metrics` endpoint:

```python
# -------------------------------------------------------------------------
# GET /api/models/{profile_id}/importance — Feature importance
# -------------------------------------------------------------------------
@router.get("/{profile_id}/importance")
async def get_feature_importance(
    profile_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Get feature importance for a profile's most recent model.

    Returns the top features by importance score, stored in the metrics JSON
    during training. Does NOT load the model file — reads from DB only.

    Returns:
        Dict with keys:
            model_id: str
            model_type: str
            feature_importance: dict (feature_name -> score, top 30)
        Or 404 if no model exists.
        Or empty feature_importance dict if importance not yet extracted.
    """
    logger.info(f"GET /api/models/{profile_id}/importance")

    cursor = await db.execute(
        "SELECT id, model_type, metrics FROM models "
        "WHERE profile_id = ? AND status = 'ready' "
        "ORDER BY created_at DESC LIMIT 1",
        (profile_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No ready model found for profile {profile_id}",
        )

    metrics = json.loads(row["metrics"]) if row["metrics"] else {}
    importance = metrics.get("feature_importance", {})

    return {
        "model_id": row["id"],
        "model_type": row["model_type"],
        "feature_importance": importance,
    }
```

---

## FILE 3 CHANGES: `strategies/base_strategy.py`

### Change 3a — Smart predictor loading in `initialize()`

Read the current `initialize()` method. Find the ML model loading block:
```python
        # Load ML model
        self.predictor = None
        if self.model_path:
            try:
                logger.info(f"  Loading model from: {self.model_path}")
                self.predictor = XGBoostPredictor(self.model_path)
                logger.info(f"  Model loaded: {self.model_path}")
            except Exception as e:
                logger.error(f"  Failed to load model: {e}", exc_info=True)
```

Replace with:
```python
        # Load ML model — detect type from DB to load correct predictor class
        self.predictor = None
        if self.model_path:
            try:
                model_type = self._detect_model_type()
                logger.info(
                    f"  Loading {model_type} model from: {self.model_path}"
                )
                if model_type == "tft":
                    from ml.tft_predictor import TFTPredictor
                    self.predictor = TFTPredictor(self.model_path)
                elif model_type == "ensemble":
                    from ml.ensemble_predictor import EnsemblePredictor
                    self.predictor = EnsemblePredictor(self.model_path)
                else:
                    # Default: xgboost (covers 'xgboost' and any unknown type)
                    self.predictor = XGBoostPredictor(self.model_path)
                logger.info(
                    f"  Predictor loaded: {type(self.predictor).__name__}"
                )
            except Exception as e:
                logger.error(f"  Failed to load model: {e}", exc_info=True)
                # Fall back to XGBoost as last resort
                try:
                    self.predictor = XGBoostPredictor(self.model_path)
                    logger.warning("  Fell back to XGBoostPredictor after load error")
                except Exception as e2:
                    logger.error(f"  XGBoost fallback also failed: {e2}")
```

### Change 3b — Add `_detect_model_type()` helper method

Add this method to `BaseOptionsStrategy`, placed BEFORE `initialize()` or just after it
(as a private helper method in the class body):

```python
    def _detect_model_type(self) -> str:
        """
        Query the DB to find what model_type is stored for this profile's
        current model. Returns 'xgboost' as default if anything fails.

        This is called during initialize() to determine which predictor class
        to instantiate. Avoids hardcoding XGBoostPredictor everywhere.
        """
        import asyncio as _asyncio
        import aiosqlite as _aio

        async def _query():
            try:
                async with _aio.connect(str(DB_PATH)) as db:
                    db.row_factory = _aio.Row
                    cursor = await db.execute(
                        """SELECT m.model_type
                           FROM models m
                           JOIN profiles p ON p.model_id = m.id
                           WHERE p.id = ?
                           LIMIT 1""",
                        (self.profile_id,),
                    )
                    row = await cursor.fetchone()
                    return row["model_type"] if row else "xgboost"
            except Exception as e:
                logger.warning(f"_detect_model_type: DB query failed: {e}")
                return "xgboost"

        try:
            return _asyncio.run(_query())
        except Exception as e:
            logger.warning(f"_detect_model_type: asyncio.run failed: {e}")
            return "xgboost"
```

---

## VERIFICATION

```bash
cd options-bot

# 1. Schema changes
echo "=== Schema changes ==="
python -c "
from backend.schemas import TrainRequest, ModelMetrics
import inspect

# TrainRequest has model_type
req = TrainRequest()
assert hasattr(req, 'model_type'), 'TrainRequest missing model_type'
assert req.model_type is None, 'model_type default must be None'
print(f'  OK  TrainRequest.model_type (default={req.model_type!r})')

# TrainRequest with model_type
req2 = TrainRequest(model_type='tft')
assert req2.model_type == 'tft'
print(f'  OK  TrainRequest(model_type=\"tft\") works')

# ModelMetrics has feature_importance
m = ModelMetrics(model_id='x', profile_id='y', model_type='xgboost')
assert hasattr(m, 'feature_importance'), 'ModelMetrics missing feature_importance'
assert m.feature_importance is None, 'feature_importance default must be None'
print(f'  OK  ModelMetrics.feature_importance (default={m.feature_importance!r})')

print('  Schema changes PASS')
"

# 2. Backend imports cleanly
echo ""
echo "=== Backend imports ==="
python -c "
import sys
sys.path.insert(0, '.')
from backend.routes.models import (
    _full_train_job, _tft_train_job, _ensemble_train_job,
    _extract_and_persist_importance, router,
)
print('  OK  All new functions importable from models.py')
"

# 3. New job functions exist and have correct signatures
echo ""
echo "=== New job function signatures ==="
python -c "
import inspect
from backend.routes.models import _tft_train_job, _ensemble_train_job, _extract_and_persist_importance

sig_tft = inspect.signature(_tft_train_job)
print(f'  _tft_train_job params: {list(sig_tft.parameters)}')
assert list(sig_tft.parameters) == ['profile_id', 'symbol', 'preset', 'horizon', 'years'], \
    f'Wrong params: {list(sig_tft.parameters)}'

sig_ens = inspect.signature(_ensemble_train_job)
print(f'  _ensemble_train_job params: {list(sig_ens.parameters)}')
assert list(sig_ens.parameters) == ['profile_id', 'symbol', 'preset', 'horizon', 'years'], \
    f'Wrong params: {list(sig_ens.parameters)}'

sig_imp = inspect.signature(_extract_and_persist_importance)
print(f'  _extract_and_persist_importance params: {list(sig_imp.parameters)}')
assert 'model_id' in sig_imp.parameters
assert 'model_type' in sig_imp.parameters
assert 'model_path' in sig_imp.parameters

print('  Function signatures PASS')
"

# 4. /importance endpoint registered
echo ""
echo "=== /importance endpoint registered ==="
python -c "
from backend.routes.models import router
routes = [r.path for r in router.routes]
print(f'  Routes: {routes}')
assert any('importance' in r for r in routes), 'Missing /importance route'
print('  OK  /importance endpoint registered')
"

# 5. /train endpoint accepts model_type
echo ""
echo "=== /train endpoint routing logic ==="
python -c "
import inspect
from backend.routes import models as m
src = inspect.getsource(m.train_model_endpoint)
assert 'model_type' in src, '/train endpoint must read model_type from body'
assert '_tft_train_job' in src, '/train must reference _tft_train_job'
assert '_ensemble_train_job' in src, '/train must reference _ensemble_train_job'
print('  OK  /train endpoint routes to tft and ensemble jobs')
"

# 6. Strategy _detect_model_type exists
echo ""
echo "=== Strategy smart loading ==="
python -c "
import inspect
from strategies.base_strategy import BaseOptionsStrategy

assert hasattr(BaseOptionsStrategy, '_detect_model_type'), \
    'Missing _detect_model_type method'
print('  OK  _detect_model_type method exists')

src = inspect.getsource(BaseOptionsStrategy.initialize)
assert 'TFTPredictor' in src, 'initialize() must import TFTPredictor'
assert 'EnsemblePredictor' in src, 'initialize() must import EnsemblePredictor'
assert '_detect_model_type' in src, 'initialize() must call _detect_model_type()'
print('  OK  initialize() references TFTPredictor, EnsemblePredictor, _detect_model_type')
print('  Strategy smart loading PASS')
"

# 7. FastAPI app starts without error
echo ""
echo "=== FastAPI app startup ==="
python -c "
import sys
sys.path.insert(0, '.')
from backend.app import app
routes = [r.path for r in app.routes]
model_routes = [r for r in routes if '/api/models' in r]
print(f'  Model routes registered: {model_routes}')
assert any('importance' in r for r in model_routes), 'Missing importance route in app'
print('  OK  FastAPI app starts and importance route is registered')
"
```

---

## SUCCESS CRITERIA

- `TrainRequest` has `model_type: Optional[str] = None`
- `ModelMetrics` has `feature_importance: Optional[dict] = None`
- `_tft_train_job()` exists in `models.py`, matching signature `(profile_id, symbol, preset, horizon, years)`
- `_ensemble_train_job()` exists in `models.py`, matching same signature
- `_extract_and_persist_importance()` exists and accepts `(model_id, model_type, model_path)`
- `/api/models/{profile_id}/importance` endpoint is registered
- `train_model_endpoint` routes to correct job based on `body.model_type`
- Invalid `model_type` returns 400
- `BaseOptionsStrategy` has `_detect_model_type()` method
- `initialize()` calls `_detect_model_type()` and instantiates the correct predictor class
- FastAPI app starts without import errors

## FAILURE GUIDE

- **`ImportError: cannot import name '_full_train_job'`**: These functions are module-level, not class methods. Confirm no accidental indentation that would make them methods of a class.
- **`asyncio.run()` inside `_detect_model_type()` fails with "Event loop already running"**: Lumibot runs its own event loop. If `asyncio.run()` conflicts, replace with a synchronous SQLite call using the `sqlite3` stdlib module directly (not `aiosqlite`).
- **`_ensemble_train_job` fails "no xgboost model found"**: The query checks `model_type = 'xgboost'` and `status = 'ready'`. If the existing TSLA model has `model_type = 'xgboost'` but status is something else, the query returns nothing. Verify status in DB: `sqlite3 db/options_bot.db "SELECT model_type, status FROM models WHERE profile_id='...'"`
- **`/importance` returns empty dict**: `_extract_and_persist_importance` merges importance into the existing metrics JSON. If this ran before the metrics row existed, it would silently return. Confirm the training job completed (`status='ready'`) before testing the importance endpoint.
- **Strategy `initialize()` event loop conflict**: Lumibot may already have an event loop running when `initialize()` is called. In that case, use `sqlite3` directly for `_detect_model_type()` instead of `aiosqlite` + `asyncio.run()`.

## DO NOT

- Do NOT modify `ml/trainer.py`, `ml/tft_trainer.py`, or `ml/ensemble_predictor.py`
- Do NOT add the TFT or ensemble imports at the top of `base_strategy.py` — import them locally inside the `if` block in `initialize()` to avoid loading PyTorch at startup when it's not needed
- Do NOT store the full importance dict (could be 73 keys) — cap at top 30 to keep DB records manageable
- Do NOT make `_ensemble_train_job` fail hard if sub-models are missing — set status back to `'ready'` and return, leaving existing models intact
- Do NOT add `model_type` to the architecture's API contract without a revision log entry — this change is internal to the existing `/train` endpoint's request body, not a new endpoint, so no revision needed
