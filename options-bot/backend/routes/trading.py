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
from config import (
    DB_PATH,
    WATCHDOG_POLL_INTERVAL_SECONDS,
    WATCHDOG_AUTO_RESTART,
    WATCHDOG_MAX_RESTARTS,
    WATCHDOG_RESTART_DELAY_SECONDS,
)

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

# Watchdog state
_watchdog_thread: threading.Thread | None = None
_watchdog_running = False
_restart_counts: dict[str, int] = {}  # profile_id -> consecutive restart count
_restart_counts_lock = threading.Lock()


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running (cross-platform)."""
    if pid is None or pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            import ctypes
            import ctypes.wintypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.wintypes.DWORD()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return False
            finally:
                kernel32.CloseHandle(handle)
        else:
            # Unix/Linux/macOS: os.kill with signal 0 checks existence
            import os
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
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


# ---------------------------------------------------------------------------
# Process watchdog — monitors subprocess health, auto-restarts on crash
# ---------------------------------------------------------------------------

def _watchdog_loop():
    """
    Background thread that periodically checks all tracked subprocesses.
    If a process has crashed (exit code != 0), it:
        1. Logs the crash with exit code
        2. Updates the profile status to 'error'
        3. Optionally auto-restarts (up to WATCHDOG_MAX_RESTARTS times)
        4. Cleans up stale process entries

    Runs every WATCHDOG_POLL_INTERVAL_SECONDS until _watchdog_running is False.
    """
    global _watchdog_running
    logger.info(
        f"Watchdog started: poll interval={WATCHDOG_POLL_INTERVAL_SECONDS}s, "
        f"auto_restart={WATCHDOG_AUTO_RESTART}, max_restarts={WATCHDOG_MAX_RESTARTS}"
    )

    while _watchdog_running:
        try:
            _watchdog_check_once()
        except Exception as e:
            logger.error(f"Watchdog error: {e}", exc_info=True)

        # Sleep in small increments so shutdown is responsive
        for _ in range(WATCHDOG_POLL_INTERVAL_SECONDS):
            if not _watchdog_running:
                break
            time.sleep(1)

    logger.info("Watchdog stopped.")


def _watchdog_check_once():
    """Single watchdog check cycle — inspect all tracked processes."""
    with _processes_lock:
        snapshot = list(_processes.items())

    for profile_id, entry in snapshot:
        proc = entry.get("proc")
        pid = entry.get("pid")
        profile_name = entry.get("profile_name", "Unknown")

        # Determine if process is dead
        is_dead = False
        exit_code = None

        if proc is not None:
            exit_code = proc.poll()
            if exit_code is not None:
                is_dead = True
        elif pid is not None:
            if not _is_process_alive(pid):
                is_dead = True
                exit_code = -1  # Unknown exit code for restored processes

        if not is_dead:
            # Process is healthy — reset restart counter
            with _restart_counts_lock:
                if profile_id in _restart_counts and _restart_counts[profile_id] > 0:
                    logger.info(
                        f"Watchdog: '{profile_name}' (PID={pid}) healthy — "
                        f"resetting restart counter"
                    )
                    _restart_counts[profile_id] = 0
            continue

        # ── Process is dead ───────────────────────────────────────────
        logger.warning(
            f"Watchdog: '{profile_name}' (PID={pid}) has exited "
            f"(exit_code={exit_code})"
        )

        # Clean up from registry
        with _processes_lock:
            _processes.pop(profile_id, None)
        _clear_process_state(profile_id)

        # Update profile status to 'error'
        _set_profile_status_sync(profile_id, "error")

        # Auto-restart if enabled and under the limit
        if not WATCHDOG_AUTO_RESTART:
            logger.info(f"Watchdog: auto-restart disabled — '{profile_name}' left in error state")
            continue

        with _restart_counts_lock:
            count = _restart_counts.get(profile_id, 0)
            if count >= WATCHDOG_MAX_RESTARTS:
                logger.error(
                    f"Watchdog: '{profile_name}' has crashed {count} times — "
                    f"NOT restarting (max={WATCHDOG_MAX_RESTARTS}). "
                    f"Manual restart required."
                )
                continue
            _restart_counts[profile_id] = count + 1
            attempt = count + 1

        logger.info(
            f"Watchdog: auto-restarting '{profile_name}' "
            f"(attempt {attempt}/{WATCHDOG_MAX_RESTARTS}) "
            f"in {WATCHDOG_RESTART_DELAY_SECONDS}s..."
        )
        time.sleep(WATCHDOG_RESTART_DELAY_SECONDS)

        # Attempt restart
        try:
            _watchdog_restart_profile(profile_id, profile_name)
        except Exception as e:
            logger.error(
                f"Watchdog: failed to restart '{profile_name}': {e}",
                exc_info=True,
            )


def _set_profile_status_sync(profile_id: str, status: str):
    """Synchronously update profile status (used by watchdog thread)."""
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE profiles SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, profile_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"_set_profile_status_sync failed for {profile_id}: {e}")


def _watchdog_restart_profile(profile_id: str, profile_name: str):
    """Restart a single trading subprocess (synchronous, called from watchdog thread)."""
    python_exe = _get_python_exe()
    main_py = _get_main_py_path()
    cmd = [python_exe, main_py, "--trade", "--profile-id", profile_id, "--no-backend"]

    logger.info(f"Watchdog restart: spawning {' '.join(cmd)}")

    kwargs = {
        "cwd": str(Path(main_py).parent),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(cmd, **kwargs)

    now_str = datetime.now(timezone.utc).isoformat()
    entry = {
        "proc": proc,
        "pid": proc.pid,
        "started_at": now_str,
        "start_time": time.time(),
        "profile_name": profile_name,
    }

    with _processes_lock:
        _processes[profile_id] = entry

    _store_process_state(profile_id, {
        "pid": proc.pid,
        "started_at": now_str,
        "profile_name": profile_name,
    })

    # Update profile status back to active
    _set_profile_status_sync(profile_id, "active")

    logger.info(f"Watchdog: '{profile_name}' restarted (PID={proc.pid})")


def start_watchdog():
    """Start the watchdog background thread. Safe to call multiple times."""
    global _watchdog_thread, _watchdog_running
    if _watchdog_running:
        logger.debug("Watchdog already running")
        return

    _watchdog_running = True
    _watchdog_thread = threading.Thread(
        target=_watchdog_loop,
        daemon=True,
        name="trading-watchdog",
    )
    _watchdog_thread.start()
    logger.info("Trading process watchdog thread started")


def stop_watchdog():
    """Stop the watchdog background thread."""
    global _watchdog_running
    _watchdog_running = False
    logger.info("Watchdog stop requested")


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
            kwargs = {
                "cwd": str(Path(main_py).parent),
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            proc = subprocess.Popen(cmd, **kwargs)

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

            # Reset watchdog restart counter on manual start
            with _restart_counts_lock:
                _restart_counts.pop(profile_id, None)

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
                # Restored from DB, no Popen handle — kill by PID
                if sys.platform == "win32":
                    await asyncio.to_thread(
                        subprocess.run,
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        capture_output=True,
                    )
                else:
                    import os as _os
                    import signal as _signal
                    try:
                        _os.kill(pid, _signal.SIGTERM)
                        await asyncio.sleep(2)
                        if _is_process_alive(pid):
                            _os.kill(pid, _signal.SIGKILL)
                    except ProcessLookupError:
                        pass
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


@router.get("/watchdog/stats")
async def get_watchdog_stats():
    """Return current watchdog status and restart counters."""
    with _restart_counts_lock:
        counts_snapshot = dict(_restart_counts)

    return {
        "running": _watchdog_running,
        "poll_interval_seconds": WATCHDOG_POLL_INTERVAL_SECONDS,
        "auto_restart": WATCHDOG_AUTO_RESTART,
        "max_restarts": WATCHDOG_MAX_RESTARTS,
        "restart_counts": counts_snapshot,
    }
