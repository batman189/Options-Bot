"""Learning layer API endpoints — threshold state, adjustment history, resume."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("options-bot.routes.learning")
router = APIRouter(prefix="/api/learning", tags=["Learning"])


class AdjustmentLogEntry(BaseModel):
    type: str
    timestamp: str
    old: Optional[float] = None
    new: Optional[float] = None
    reason: str = ""
    regime: Optional[str] = None


class ProfileLearningState(BaseModel):
    # Prompt 26: the DB column `learning_state.profile_name` stores a
    # setup_type value (pre-Prompt-15 naming debt). The API field name
    # now reflects reality. DB column stays named profile_name to avoid
    # a migration; translation happens below in get_learning_state.
    setup_type: str
    min_confidence: float
    regime_fit_overrides: dict
    paused_by_learning: bool
    last_adjustment: Optional[str]
    recent_adjustments: list[AdjustmentLogEntry]


class LearningStateResponse(BaseModel):
    profiles: list[ProfileLearningState]


class ResumeResponse(BaseModel):
    # Prompt 26: same rename as ProfileLearningState.
    setup_type: str
    paused_by_learning: bool
    message: str


@router.get("/state", response_model=LearningStateResponse)
async def get_learning_state():
    """Return learning_state for all three profiles."""
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).parent.parent.parent / "db" / "options_bot.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM learning_state ORDER BY profile_name").fetchall()
        conn.close()

        profiles = []
        for row in rows:
            log = json.loads(row["adjustment_log"] or "[]")
            recent = log[-10:]  # Last 10 entries
            entries = []
            for e in recent:
                entries.append(AdjustmentLogEntry(
                    type=e.get("type", ""),
                    timestamp=e.get("timestamp", ""),
                    old=e.get("old"),
                    new=e.get("new"),
                    reason=e.get("reason", ""),
                    regime=e.get("regime"),
                ))
            # Translation layer (Prompt 26): learning_state.profile_name
            # column stores the setup_type value. DB column name stays;
            # API field reflects reality.
            profiles.append(ProfileLearningState(
                setup_type=row["profile_name"],
                min_confidence=row["min_confidence"],
                regime_fit_overrides=json.loads(row["regime_fit_overrides"] or "{}"),
                paused_by_learning=bool(row["paused_by_learning"]),
                last_adjustment=row["last_adjustment"],
                recent_adjustments=entries,
            ))

        return LearningStateResponse(profiles=profiles)

    except Exception as e:
        logger.error(f"get_learning_state failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Learning state unavailable: {str(e)}")


@router.post("/resume/{profile_name}", response_model=ResumeResponse)
async def resume_profile(profile_name: str):
    """Resume a setup_type that was auto-paused by the learning layer.

    The path parameter is named `profile_name` for URL stability —
    changing it to `{setup_type}` would break any saved bookmark or
    external caller. The VALUE it carries is actually a setup_type
    (pre-Prompt-15 naming debt); internally we alias it to make that
    clear. See Prompt 26. Response field renamed to setup_type.
    """
    setup_type = profile_name   # alias for readability
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).parent.parent.parent / "db" / "options_bot.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM learning_state WHERE profile_name = ?", (setup_type,)
        ).fetchone()

        if row is None:
            conn.close()
            raise HTTPException(
                status_code=404,
                detail=f"No learning state for setup_type '{setup_type}'",
            )

        if not row["paused_by_learning"]:
            conn.close()
            return ResumeResponse(
                setup_type=setup_type, paused_by_learning=False,
                message=f"Setup type '{setup_type}' is not paused by learning layer",
            )

        now = datetime.now(timezone.utc).isoformat()
        log = json.loads(row["adjustment_log"] or "[]")
        log.append({"type": "manual_resume", "timestamp": now, "reason": "Resumed via UI"})

        conn.execute(
            """UPDATE learning_state SET paused_by_learning = 0,
               adjustment_log = ?, last_adjustment = ?, updated_at = ?
               WHERE profile_name = ?""",
            (json.dumps(log[-50:]), now, now, setup_type),
        )
        conn.commit()
        conn.close()

        logger.info(f"Learning: setup_type '{setup_type}' resumed via API")
        return ResumeResponse(
            setup_type=setup_type, paused_by_learning=False,
            message=f"Setup type '{setup_type}' resumed successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"resume_profile failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Resume failed: {str(e)}")
