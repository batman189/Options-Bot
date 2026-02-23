"""
Profile CRUD endpoints.
Phase 1: All endpoints fully functional against SQLite.
Matches PROJECT_ARCHITECTURE.md Section 5b — Profiles.
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import PRESET_DEFAULTS

from backend.database import get_db
from backend.schemas import ProfileCreate, ProfileUpdate, ProfileResponse, ModelSummary

logger = logging.getLogger("options-bot.routes.profiles")
router = APIRouter(prefix="/api/profiles", tags=["Profiles"])


def _build_profile_response(row: aiosqlite.Row, model_row=None) -> ProfileResponse:
    """Convert a database row to a ProfileResponse."""
    model_summary = None
    if model_row and model_row["id"]:
        trained_at = model_row["training_completed_at"]
        data_start = model_row["data_start_date"] or "unknown"
        data_end = model_row["data_end_date"] or "unknown"
        metrics_raw = model_row["metrics"]
        metrics = json.loads(metrics_raw) if metrics_raw else {}

        age_days = 0
        if trained_at:
            try:
                trained_dt = datetime.fromisoformat(trained_at)
                age_days = (datetime.utcnow() - trained_dt).days
            except (ValueError, TypeError):
                age_days = 0

        model_summary = ModelSummary(
            id=model_row["id"],
            model_type=model_row["model_type"],
            status=model_row["status"],
            trained_at=trained_at,
            data_range=f"{data_start} to {data_end}",
            metrics=metrics,
            age_days=age_days,
        )

    return ProfileResponse(
        id=row["id"],
        name=row["name"],
        preset=row["preset"],
        status=row["status"],
        symbols=json.loads(row["symbols"]),
        config=json.loads(row["config"]),
        model_summary=model_summary,
        active_positions=0,  # Will be populated when trading is active
        total_pnl=0.0,       # Will be calculated from trades table
        created_at=row["created_at"],
        updated_at=row["updated_at"],
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
        responses.append(_build_profile_response(row, model_row))

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

    return _build_profile_response(row, model_row)


# -------------------------------------------------------------------------
# POST /api/profiles — Create new profile
# -------------------------------------------------------------------------
@router.post("", response_model=ProfileResponse, status_code=201)
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

    now = datetime.utcnow().isoformat()
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

    now = datetime.utcnow().isoformat()
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

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    return _build_profile_response(row)


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

    # Delete associated models
    await db.execute("DELETE FROM models WHERE profile_id = ?", (profile_id,))
    # Delete associated trades
    await db.execute("DELETE FROM trades WHERE profile_id = ?", (profile_id,))
    # Delete associated training logs
    await db.execute(
        "DELETE FROM training_logs WHERE model_id IN (SELECT id FROM models WHERE profile_id = ?)",
        (profile_id,),
    )
    # Delete the profile
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

    now = datetime.utcnow().isoformat()
    await db.execute(
        "UPDATE profiles SET status = 'active', updated_at = ? WHERE id = ?",
        (now, profile_id),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    return _build_profile_response(row)


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

    now = datetime.utcnow().isoformat()
    await db.execute(
        "UPDATE profiles SET status = 'paused', updated_at = ? WHERE id = ?",
        (now, profile_id),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cursor.fetchone()
    return _build_profile_response(row)
