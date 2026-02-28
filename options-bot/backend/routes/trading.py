"""
Trading process management endpoints.
Start/stop/restart trading bot subprocesses from the UI.
Each profile runs as a separate subprocess: python main.py --trade --profile-id <id> --no-backend
Processes are tracked by PID in an in-memory registry + system_state table.
"""

import asyncio
import json
import logging
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import aiosqlite

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import DB_PATH

from backend.database import get_db
from backend.schemas import (
    TradingProcessInfo,
    TradingStatusResponse,
    TradingStartRequest,
    TradingStartResponse,
    TradingStopRequest,
    TradingStopResponse,
)

logger = logging.getLogger("options-bot.routes.trading")
router = APIRouter(prefix="/api/trading", tags=["Trading"])

# ---------------------------------------------------------------------------
# In-memory process registry
# ---------------------------------------------------------------------------

_processes: dict[str, dict] = {}  # profile_id -> { proc, pid, started_at, ... }
_processes_lock = threading.Lock()


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running (Windows-compatible)."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def _get_python_exe() -> str:
    """Get the path to the current Python interpreter."""
    return sys.executable


def _get_main_py_path() -> str:
    """Get the absolute path to main.py."""
    return str(Path(__file__).parent.parent.parent / "main.py")


def _store_process_state(profile_id: str, state: dict):
    """Persist process state to system_state table (synchronous sqlite3)."""
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO system_state (key, value, updated_at) VALUES (?, ?, ?)",
                (f"trading_{profile_id}", json.dumps(state), now),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"_store_process_state failed for {profile_id}: {e}")


def _clear_process_state(profile_id: str):
    """Remove process state from system_state table."""
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        try:
            conn.execute("DELETE FROM system_state WHERE key = ?", (f"trading_{profile_id}",))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"_clear_process_state failed for {profile_id}: {e}")


def _build_process_info(profile_id: str, entry: dict) -> TradingProcessInfo:
    """Build a TradingProcessInfo from a registry entry."""
    proc = entry.get("proc")
    pid = entry.get("pid")
    started_at = entry.get("started_at")
    profile_name = entry.get("profile_name", "Unknown")

    if proc is not None and pid is not None:
        if proc.poll() is None:
            status = "running"
            uptime = int(time.time() - entry.get("start_time", time.time()))
        else:
            exit_code = proc.poll()
            status = "crashed" if exit_code != 0 else "stopped"
            uptime = None
    elif pid is not None and _is_process_alive(pid):
        # Restored from DB — no Popen object but PID alive
        status = "running"
        uptime = int(time.time() - entry.get("start_time", time.time()))
    else:
        status = "stopped"
        uptime = None

    return TradingProcessInfo(
        profile_id=profile_id,
        profile_name=profile_name,
        pid=pid,
        status=status,
        started_at=started_at,
        uptime_seconds=uptime,
    )


# ---------------------------------------------------------------------------
# Startup: Restore registry from system_state
# ---------------------------------------------------------------------------

async def restore_process_registry(db: aiosqlite.Connection):
    """
    Called at backend startup. Reads system_state for trading_* entries.
    Re-registers live PIDs, cleans up dead ones.
    """
    cursor = await db.execute(
        "SELECT key, value FROM system_state WHERE key LIKE 'trading_%'"
    )
    rows = await cursor.fetchall()
    for row in rows:
        profile_id = row["key"].replace("trading_", "", 1)
        try:
            state = json.loads(row["value"])
            pid = state.get("pid")
            if pid and _is_process_alive(pid):
                logger.info(f"restore_process_registry: PID {pid} for '{state.get('profile_name', profile_id)}' still alive")
                with _processes_lock:
                    _processes[profile_id] = {
                        "proc": None,
                        "pid": pid,
                        "started_at": state.get("started_at"),
                        "start_time": time.time(),
                        "profile_name": state.get("profile_name", "Unknown"),
                    }
            else:
                logger.info(f"restore_process_registry: PID {pid} for {profile_id} dead, cleaning up")
                _clear_process_state(profile_id)
        except Exception as e:
            logger.error(f"restore_process_registry error for {profile_id}: {e}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", response_model=TradingStatusResponse)
async def get_trading_status(db: aiosqlite.Connection = Depends(get_db)):
    """Get status of all tracked trading processes."""
    infos = []
    stale_ids = []

    with _processes_lock:
        for profile_id, entry in list(_processes.items()):
            info = _build_process_info(profile_id, entry)
            infos.append(info)
            if info.status in ("stopped", "crashed"):
                stale_ids.append(profile_id)

    # Clean stale entries
    for pid in stale_ids:
        with _processes_lock:
            _processes.pop(pid, None)
        _clear_process_state(pid)

    # Also show profiles marked 'active' in DB but not running
    cursor = await db.execute(
        "SELECT id, name FROM profiles WHERE status = 'active'"
    )
    active_rows = await cursor.fetchall()
    tracked_ids = {info.profile_id for info in infos}
    for row in active_rows:
        if row["id"] not in tracked_ids:
            infos.append(TradingProcessInfo(
                profile_id=row["id"],
                profile_name=row["name"],
                status="stopped",
                exit_reason="Not running (marked active in DB but no process)",
            ))

    running = sum(1 for i in infos if i.status == "running")
    stopped = len(infos) - running

    return TradingStatusResponse(
        processes=infos,
        total_running=running,
        total_stopped=stopped,
    )


@router.post("/start", response_model=TradingStartResponse)
async def start_trading(body: TradingStartRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Spawn trading subprocess(es) for the given profile IDs."""
    logger.info(f"POST /api/trading/start profile_ids={body.profile_ids}")

    started = []
    errors = []

    for profile_id in body.profile_ids:
        # Check not already running
        with _processes_lock:
            if profile_id in _processes:
                existing = _processes[profile_id]
                proc = existing.get("proc")
                pid = existing.get("pid")
                if proc and proc.poll() is None:
                    errors.append({"profile_id": profile_id, "message": "Already running"})
                    continue
                if pid and _is_process_alive(pid):
                    errors.append({"profile_id": profile_id, "message": "Already running"})
                    continue

        # Validate profile
        cursor = await db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
        row = await cursor.fetchone()
        if not row:
            errors.append({"profile_id": profile_id, "message": "Profile not found"})
            continue
        if row["status"] not in ("ready", "active", "paused"):
            errors.append({
                "profile_id": profile_id,
                "message": f"Profile status is '{row['status']}' — must be ready, active, or paused",
            })
            continue
        if not row["model_id"]:
            errors.append({
                "profile_id": profile_id,
                "message": "No trained model. Train a model first.",
            })
            continue

        # Spawn subprocess
        try:
            python_exe = _get_python_exe()
            main_py = _get_main_py_path()
            cmd = [python_exe, main_py, "--trade", "--profile-id", profile_id, "--no-backend"]
            logger.info(f"Spawning: {' '.join(cmd)}")

            # Redirect stdout/stderr to DEVNULL to prevent pipe buffer deadlock.
            # Trading subprocesses log to rotating file via logging config in main.py.
            # Using PIPE without a consumer thread risks blocking the trading loop
            # when the 64KB OS pipe buffer fills (e.g. during active trading sessions).
            proc = subprocess.Popen(
                cmd,
                cwd=str(Path(main_py).parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )

            now_str = datetime.now(timezone.utc).isoformat()
            entry = {
                "proc": proc,
                "pid": proc.pid,
                "started_at": now_str,
                "start_time": time.time(),
                "profile_name": row["name"],
            }

            with _processes_lock:
                _processes[profile_id] = entry

            _store_process_state(profile_id, {
                "pid": proc.pid,
                "started_at": now_str,
                "profile_name": row["name"],
            })

            # Update profile status to active
            await db.execute(
                "UPDATE profiles SET status = 'active', updated_at = ? WHERE id = ?",
                (now_str, profile_id),
            )
            await db.commit()

            info = TradingProcessInfo(
                profile_id=profile_id,
                profile_name=row["name"],
                pid=proc.pid,
                status="running",
                started_at=now_str,
            )
            started.append(info)
            logger.info(f"Started trading for '{row['name']}' (PID={proc.pid})")

        except Exception as e:
            logger.error(f"Failed to start trading for {profile_id}: {e}", exc_info=True)
            errors.append({"profile_id": profile_id, "message": str(e)})

    return TradingStartResponse(started=started, errors=errors)


@router.post("/stop", response_model=TradingStopResponse)
async def stop_trading(body: TradingStopRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Stop trading subprocess(es). If profile_ids is None, stops all."""
    logger.info(f"POST /api/trading/stop profile_ids={body.profile_ids}")

    stopped_ids = []
    errors = []

    with _processes_lock:
        target_ids = body.profile_ids if body.profile_ids else list(_processes.keys())

    for profile_id in target_ids:
        with _processes_lock:
            entry = _processes.get(profile_id)

        if not entry:
            errors.append({"profile_id": profile_id, "message": "No running process found"})
            continue

        proc = entry.get("proc")
        pid = entry.get("pid")

        try:
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            elif pid is not None:
                # Restored from DB, no Popen handle — use taskkill on Windows
                await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                )
            else:
                errors.append({"profile_id": profile_id, "message": "No PID or process handle"})
                continue

            with _processes_lock:
                _processes.pop(profile_id, None)
            _clear_process_state(profile_id)

            # Update profile status to paused
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "UPDATE profiles SET status = 'paused', updated_at = ? WHERE id = ?",
                (now_str, profile_id),
            )
            await db.commit()

            stopped_ids.append(profile_id)
            logger.info(f"Stopped trading for {profile_id} (PID={pid})")

        except Exception as e:
            logger.error(f"Failed to stop {profile_id}: {e}", exc_info=True)
            errors.append({"profile_id": profile_id, "message": str(e)})

    return TradingStopResponse(stopped=stopped_ids, errors=errors)


@router.post("/restart", response_model=TradingStartResponse)
async def restart_trading(body: TradingStartRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Restart trading for the given profiles: stop then start."""
    logger.info(f"POST /api/trading/restart profile_ids={body.profile_ids}")

    # Stop first
    await stop_trading(TradingStopRequest(profile_ids=body.profile_ids), db)

    # Brief delay for process cleanup
    await asyncio.sleep(1)

    # Start
    return await start_trading(body, db)


@router.get("/startable-profiles")
async def get_startable_profiles(db: aiosqlite.Connection = Depends(get_db)):
    """Return profiles that can be started (have model, status ready/active/paused)."""
    cursor = await db.execute(
        """SELECT p.id, p.name, p.preset, p.status, p.symbols, p.model_id
           FROM profiles p
           WHERE p.status IN ('ready', 'active', 'paused')
           AND p.model_id IS NOT NULL
           ORDER BY p.name"""
    )
    rows = await cursor.fetchall()

    with _processes_lock:
        running_ids = set(_processes.keys())

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "name": row["name"],
            "preset": row["preset"],
            "status": row["status"],
            "symbols": json.loads(row["symbols"]),
            "is_running": row["id"] in running_ids,
        })
    return results
