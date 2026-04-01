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
    profile_name: str
    min_confidence: float
    regime_fit_overrides: dict
    paused_by_learning: bool
    last_adjustment: Optional[str]
    recent_adjustments: list[AdjustmentLogEntry]


class LearningStateResponse(BaseModel):
    profiles: list[ProfileLearningState]


class ResumeResponse(BaseModel):
    profile_name: str
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
            profiles.append(ProfileLearningState(
                profile_name=row["profile_name"],
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
    """Resume a profile that was auto-paused by the learning layer."""
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).parent.parent.parent / "db" / "options_bot.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM learning_state WHERE profile_name = ?", (profile_name,)
        ).fetchone()

        if row is None:
            conn.close()
            raise HTTPException(status_code=404, detail=f"No learning state for '{profile_name}'")

        if not row["paused_by_learning"]:
            conn.close()
            return ResumeResponse(
                profile_name=profile_name, paused_by_learning=False,
                message=f"Profile '{profile_name}' is not paused by learning layer",
            )

        now = datetime.now(timezone.utc).isoformat()
        log = json.loads(row["adjustment_log"] or "[]")
        log.append({"type": "manual_resume", "timestamp": now, "reason": "Resumed via UI"})

        conn.execute(
            """UPDATE learning_state SET paused_by_learning = 0,
               adjustment_log = ?, last_adjustment = ?, updated_at = ?
               WHERE profile_name = ?""",
            (json.dumps(log[-50:]), now, now, profile_name),
        )
        conn.commit()
        conn.close()

        logger.info(f"Learning: profile '{profile_name}' resumed via API")
        return ResumeResponse(
            profile_name=profile_name, paused_by_learning=False,
            message=f"Profile '{profile_name}' resumed successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"resume_profile failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Resume failed: {str(e)}")
