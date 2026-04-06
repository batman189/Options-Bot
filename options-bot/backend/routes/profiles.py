"""
Profile CRUD endpoints.
Phase 1: All endpoints fully functional against SQLite.
Matches PROJECT_ARCHITECTURE.md Section 5b — Profiles.
"""

import asyncio
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import aiosqlite

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import PRESET_DEFAULTS

from backend.database import get_db
from backend.schemas import ProfileCreate, ProfileUpdate, ProfileResponse, ModelSummary

logger = logging.getLogger("options-bot.routes.profiles")
router = APIRouter(prefix="/api/profiles", tags=["Profiles"])


@router.get("/strategy-types", tags=["Profiles"])
async def get_strategy_types():
    """Return all registered strategy types with metadata for the profile creation UI."""
    try:
        from strategies.registry import get_all_strategy_types
        return get_all_strategy_types()
    except ImportError:
        # Fallback: return legacy presets
        return [
            {"preset_name": k, "display_name": k.replace("_", " ").title(),
             "description": "", "category": "directional", "min_capital": 0,
             "valid_model_types": [], "default_config": v, "supports_symbols": ["ANY"],
             "is_intraday": True}
            for k, v in PRESET_DEFAULTS.items()
        ]


def _model_row_to_summary(model_row) -> ModelSummary:
    """Convert a model database row to a ModelSummary."""
    trained_at = model_row["training_completed_at"]
    data_start = model_row["data_start_date"] or "unknown"
    data_end = model_row["data_end_date"] or "unknown"
    metrics_raw = model_row["metrics"]
    metrics = json.loads(metrics_raw) if metrics_raw else {}

    age_days = 0
    if trained_at:
        try:
            trained_dt = datetime.fromisoformat(trained_at)
            age_days = (datetime.now(timezone.utc) - trained_dt).days
        except (ValueError, TypeError):
            age_days = 0

    return ModelSummary(
        id=model_row["id"],
        model_type=model_row["model_type"],
        status=model_row["status"],
        trained_at=trained_at,
        data_range=f"{data_start} to {data_end}",
        metrics=metrics,
        age_days=age_days,
    )


def _build_profile_response(
    row: aiosqlite.Row,
    model_row=None,
    all_model_rows=None,
    active_positions: int = 0,
    total_pnl: float = 0.0,
    realized_pnl: float = 0.0,
    unrealized_pnl: float = 0.0,
) -> ProfileResponse:
    """Convert a database row to a ProfileResponse."""
    model_summary = None
    if model_row and model_row["id"]:
        model_summary = _model_row_to_summary(model_row)

    trained_models = []
    if all_model_rows:
        for mrow in all_model_rows:
            if mrow["id"]:
                trained_models.append(_model_row_to_summary(mrow))

    from config import PRESET_MODEL_TYPES
    valid_model_types = PRESET_MODEL_TYPES.get(row["preset"], ["xgboost"])

    return ProfileResponse(
        id=row["id"],
        name=row["name"],
        preset=row["preset"],
        status=row["status"],
        error_reason=row["error_reason"] if "error_reason" in row.keys() else None,
        symbols=json.loads(row["symbols"]),
        config=json.loads(row["config"]),
        model_summary=model_summary,
        trained_models=trained_models,
        valid_model_types=valid_model_types,
        active_positions=active_positions,
        total_pnl=total_pnl,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _get_trade_stats(db: aiosqlite.Connection, profile_id: str) -> dict:
    """Query real active_positions and total_pnl for a profile from the trades table."""
    # Count open positions
    cursor = await db.execute(
        "SELECT COUNT(*) FROM trades WHERE profile_id = ? AND status = 'open'",
        (profile_id,),
    )
    row = await cursor.fetchone()
    active_positions = row[0] if row else 0

    # Sum P&L of closed trades (realized)
    cursor = await db.execute(
        """SELECT COALESCE(SUM(pnl_dollars), 0.0) FROM trades
           WHERE profile_id = ? AND status = 'closed' AND pnl_dollars IS NOT NULL""",
        (profile_id,),
    )
    row = await cursor.fetchone()
    realized_pnl = float(row[0]) if row else 0.0

    # Sum unrealized P&L of open trades
    cursor = await db.execute(
        """SELECT COALESCE(SUM(unrealized_pnl), 0.0) FROM trades
           WHERE profile_id = ? AND status = 'open' AND unrealized_pnl IS NOT NULL""",
        (profile_id,),
    )
    row = await cursor.fetchone()
    unrealized_pnl = float(row[0]) if row else 0.0

    total_pnl = realized_pnl + unrealized_pnl
    return {
        "active_positions": active_positions,
        "total_pnl": total_pnl,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
    }


async def _full_profile_response(db: aiosqlite.Connection, profile_id: str) -> ProfileResponse:
    """Fetch a profile row with all model rows and trade stats for a complete response."""
    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    model_row = None
    if row["model_id"]:
        mcursor = await db.execute("SELECT * FROM models WHERE id = ?", (row["model_id"],))
        model_row = await mcursor.fetchone()
    all_mcursor = await db.execute(
        "SELECT * FROM models WHERE profile_id = ? ORDER BY created_at DESC",
        (profile_id,),
    )
    all_model_rows = await all_mcursor.fetchall()
    stats = await _get_trade_stats(db, profile_id)
    return _build_profile_response(
        row, model_row,
        all_model_rows=all_model_rows,
        active_positions=stats["active_positions"],
        total_pnl=stats["total_pnl"],
        realized_pnl=stats["realized_pnl"],
        unrealized_pnl=stats["unrealized_pnl"],
    )


# -------------------------------------------------------------------------
# GET /api/profiles — List all profiles
# -------------------------------------------------------------------------
@router.get("", response_model=list[ProfileResponse])
async def list_profiles(db: aiosqlite.Connection = Depends(get_db)):
    """List all profiles with model summaries."""
    logger.info("GET /api/profiles — listing all profiles")
    cursor = await db.execute("SELECT * FROM profiles ORDER BY created_at DESC")
    rows = await cursor.fetchall()

    responses = []
    for row in rows:
        model_row = None
        if row["model_id"]:
            mcursor = await db.execute("SELECT * FROM models WHERE id = ?", (row["model_id"],))
            model_row = await mcursor.fetchone()
        all_mcursor = await db.execute(
            "SELECT * FROM models WHERE profile_id = ? ORDER BY created_at DESC",
            (row["id"],),
        )
        all_model_rows = await all_mcursor.fetchall()
        stats = await _get_trade_stats(db, row["id"])
        responses.append(_build_profile_response(
            row, model_row,
            all_model_rows=all_model_rows,
            active_positions=stats["active_positions"],
            total_pnl=stats["total_pnl"],
            realized_pnl=stats["realized_pnl"],
            unrealized_pnl=stats["unrealized_pnl"],
        ))

    logger.info(f"Returning {len(responses)} profiles")
    return responses


# -------------------------------------------------------------------------
# GET /api/profiles/{id} — Get single profile
# -------------------------------------------------------------------------
@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single profile with full model info."""
    logger.info(f"GET /api/profiles/{profile_id}")
    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    model_row = None
    if row["model_id"]:
        mcursor = await db.execute("SELECT * FROM models WHERE id = ?", (row["model_id"],))
        model_row = await mcursor.fetchone()
    all_mcursor = await db.execute(
        "SELECT * FROM models WHERE profile_id = ? ORDER BY created_at DESC",
        (profile_id,),
    )
    all_model_rows = await all_mcursor.fetchall()

    stats = await _get_trade_stats(db, profile_id)
    return _build_profile_response(
        row, model_row,
        all_model_rows=all_model_rows,
        active_positions=stats["active_positions"],
        total_pnl=stats["total_pnl"],
        realized_pnl=stats["realized_pnl"],
        unrealized_pnl=stats["unrealized_pnl"],
    )


# -------------------------------------------------------------------------
# POST /api/profiles — Create new profile
# -------------------------------------------------------------------------
@router.post("", response_model=ProfileResponse)
async def create_profile(body: ProfileCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new profile with preset defaults."""
    logger.info(f"POST /api/profiles — creating profile: {body.name} ({body.preset})")

    # Validate preset
    if body.preset not in PRESET_DEFAULTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preset '{body.preset}'. Must be one of: {list(PRESET_DEFAULTS.keys())}"
        )

    # Validate symbols
    if not body.symbols or len(body.symbols) == 0:
        raise HTTPException(status_code=400, detail="At least one symbol is required")

    # Build config from preset defaults + overrides
    config = dict(PRESET_DEFAULTS[body.preset])
    config.update(body.config_overrides)

    now = datetime.now(timezone.utc).isoformat()
    profile_id = str(uuid.uuid4())

    await db.execute(
        """INSERT INTO profiles (id, name, preset, status, symbols, config, model_id, created_at, updated_at)
           VALUES (?, ?, ?, 'created', ?, ?, NULL, ?, ?)""",
        (profile_id, body.name, body.preset, json.dumps(body.symbols), json.dumps(config), now, now),
    )
    await db.commit()

    logger.info(f"Profile created: {profile_id} ({body.name})")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    return _build_profile_response(row)


# -------------------------------------------------------------------------
# PUT /api/profiles/{id} — Update profile config
# -------------------------------------------------------------------------
@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str,
    body: ProfileUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update profile settings."""
    logger.info(f"PUT /api/profiles/{profile_id}")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    now = datetime.now(timezone.utc).isoformat()
    updates = {"updated_at": now}

    if body.name is not None:
        updates["name"] = body.name
    if body.symbols is not None:
        updates["symbols"] = json.dumps(body.symbols)
    if body.config_overrides is not None:
        current_config = json.loads(row["config"])
        current_config.update(body.config_overrides)
        updates["config"] = json.dumps(current_config)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [profile_id]
    await db.execute(f"UPDATE profiles SET {set_clause} WHERE id = ?", values)
    await db.commit()

    return await _full_profile_response(db, profile_id)


# -------------------------------------------------------------------------
# DELETE /api/profiles/{id} — Delete profile + model files
# -------------------------------------------------------------------------
@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a profile and associated model files."""
    logger.info(f"DELETE /api/profiles/{profile_id}")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    # Step 1: Collect model IDs BEFORE deleting models
    model_cursor = await db.execute(
        "SELECT id, file_path FROM models WHERE profile_id = ?", (profile_id,)
    )
    model_rows = await model_cursor.fetchall()
    model_ids = [mrow["id"] for mrow in model_rows]

    # Step 2: Delete training_logs first (while model IDs are still known)
    if model_ids:
        placeholders = ",".join("?" * len(model_ids))
        await db.execute(
            f"DELETE FROM training_logs WHERE model_id IN ({placeholders})",
            model_ids,
        )
        logger.info(
            f"Deleted training_logs for {len(model_ids)} model(s) "
            f"under profile {profile_id}"
        )
    # Also clean up training logs stored with profile_id directly
    # (TrainingLogHandler uses model_id='training' with profile_id=<uuid>,
    #  which won't be matched by the model_id IN (...) query above)
    await db.execute(
        "DELETE FROM training_logs WHERE profile_id = ?",
        (profile_id,),
    )

    # Step 3: Delete model files from disk (in thread to avoid blocking event loop)
    import shutil
    from pathlib import Path as _Path

    def _delete_model_files():
        for mrow in model_rows:
            if mrow["file_path"]:
                p = _Path(mrow["file_path"])
                try:
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                        logger.info(f"Deleted model directory: {p}")
                    elif p.exists():
                        p.unlink()
                        logger.info(f"Deleted model file: {p}")
                except Exception as e:
                    logger.warning(f"Could not delete model file {p}: {e}")

    await asyncio.to_thread(_delete_model_files)

    # Step 4: Delete model records and all associated data
    await db.execute("DELETE FROM models WHERE profile_id = ?", (profile_id,))
    await db.execute("DELETE FROM trades WHERE profile_id = ?", (profile_id,))
    await db.execute("DELETE FROM signal_logs WHERE profile_id = ?", (profile_id,))
    # Clean up training queue entries (M8 fix — prevent orphaned data)
    await db.execute("DELETE FROM training_queue WHERE profile_id = ?", (profile_id,))
    # Clean up system state entries (backtest_, model_health_, trading_ prefixed keys)
    await db.execute(
        "DELETE FROM system_state WHERE key LIKE ? OR key LIKE ? OR key LIKE ?",
        (f"backtest_{profile_id}%", f"model_health_{profile_id}%", f"trading_{profile_id}%"),
    )
    # Delete the profile itself
    await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    await db.commit()

    logger.info(f"Profile deleted: {profile_id}")
    # 204 No Content — no response body


# -------------------------------------------------------------------------
# POST /api/profiles/{id}/activate — Phase 2 stub
# -------------------------------------------------------------------------
@router.post("/{profile_id}/activate", response_model=ProfileResponse)
async def activate_profile(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Start trading this profile. Phase 2 — currently updates status only."""
    logger.info(f"POST /api/profiles/{profile_id}/activate")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    if row["status"] not in ("ready", "paused"):
        raise HTTPException(
            status_code=400,
            detail=f"Profile must be in 'ready' or 'paused' status to activate. Current: {row['status']}"
        )

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE profiles SET status = 'active', updated_at = ? WHERE id = ?",
        (now, profile_id),
    )
    await db.commit()

    return await _full_profile_response(db, profile_id)


# -------------------------------------------------------------------------
# POST /api/profiles/{id}/pause — Phase 2 stub
# -------------------------------------------------------------------------
@router.post("/{profile_id}/pause", response_model=ProfileResponse)
async def pause_profile(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Pause trading this profile. Phase 2 — currently updates status only."""
    logger.info(f"POST /api/profiles/{profile_id}/pause")

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    if row["status"] != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Profile must be 'active' to pause. Current: {row['status']}"
        )

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE profiles SET status = 'paused', updated_at = ? WHERE id = ?",
        (now, profile_id),
    )
    await db.commit()

    return await _full_profile_response(db, profile_id)
