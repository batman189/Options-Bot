# 20. Startup / Shutdown / Live Loop Audit

## Startup Path (main.py → strategy)

### Entry Point: main.py
- Parses CLI args (profile ID, mode)
- Sets up logging (file + console, rotation)
- Calls `load_profile_from_db(profile_id)` to get profile config + model path
- Calls `start_trading_single(profile_data)` to launch Lumibot strategy

### Profile Loading (main.py → database)
1. Opens aiosqlite connection to DB_PATH
2. `SELECT * FROM profiles WHERE id = ?`
3. Parses config JSON, symbols JSON
4. `SELECT file_path FROM models WHERE id = ?` (using profile.model_id)
5. Returns profile dict with config, symbols, model_path

### Strategy Launch
1. Creates Alpaca broker connection (API key/secret from .env)
2. Determines strategy class from preset:
   - "scalp" → ScalpStrategy
   - "swing" → SwingStrategy
   - "general" → GeneralStrategy
3. Strategy.initialize() called by Lumibot:
   - Loads model via predictor class
   - Creates RiskManager
   - Sets up circuit breakers
   - Initializes VIX provider
   - Sets sleeptime from config
4. Lumibot starts its event loop, calling on_trading_iteration() every sleeptime

### Process Architecture
- Each profile runs as a **separate Python process** (not thread)
- main.py is invoked twice (once per profile) via the trading routes
- Evidence: Two PIDs in log (179544 and 22752), two sets of startup messages interleaved
- Both processes share the same log file (interleaved output)
- Both processes share the same SQLite DB (WAL mode handles concurrency)

### Startup Health Checks
```
Health: Alpaca: ✓ configured | Theta: ✓ connected | Database: ✓ exists
```
- Alpaca: Checks API key exists (not a live connectivity test)
- Theta: Makes GET request to localhost:25503 (ThetaData Terminal)
- Database: Checks file exists on disk

## Live Trading Loop

### on_trading_iteration() Flow (base_strategy.py:304-528)
```
1. Check auto-pause threshold (consecutive errors)
2. Update prediction outcomes (health monitoring)
3. Scalp equity gate ($25K check)
4. Emergency stop loss check (portfolio drawdown)
5. _check_exits() — evaluate all open positions
6. Portfolio exposure check
7. _check_entries() — ML pipeline (12 entry steps)
8. Persist model health stats
9. Export circuit breaker state
```

### Error Handling
- Inner try/except catches trading logic errors → increments consecutive_errors
- Outer try/except catches everything else → also increments
- On success: resets consecutive_errors to 0
- Auto-pause at MAX_CONSECUTIVE_ERRORS (from config)
- Signal log written for every iteration regardless of outcome

### Timing
- Scalp: 14-20 seconds per iteration (sleeptime=1M)
  - Feature compute: ~0.13s
  - Prediction: ~0.003s
  - EV scan: ~13s (bottleneck — scanning 175+ contracts via Lumibot)
  - Total iteration including waits: ~16s
- Swing: 5-minute iterations, timing not captured in recent logs

## Shutdown Path

### Normal Shutdown
- Lumibot handles SIGTERM/Ctrl+C
- base_strategy.py has no explicit on_shutdown() override
- Open positions are NOT automatically closed on shutdown
- Circuit breaker state file persists (JSON in logs directory)

### Backend Shutdown (app.py lifespan)
```python
yield  # app runs
trading.stop_watchdog()
logger.info("Backend shutting down.")
```

### Crash Recovery
- On backend restart: `restore_process_registry()` recovers PID info from system_state table
- Stale profiles (status='active' but no running process) reset to 'ready'
- Stale training profiles (status='training') reset to 'ready' or 'created'

## Process Watchdog (trading.py)
- Background thread monitors trading processes
- Checks if PIDs are still alive
- Updates system_state table with process status
- Detects crashed processes

## Issues Found

1. **No graceful position close on shutdown**: If the bot process is killed, open options positions remain open with no management. For 0DTE options, this could mean expiration while unmonitored.

2. **Interleaved logging from multiple processes**: Both profiles write to the same log file simultaneously, making log analysis difficult (messages from different profiles interleave).

3. **No health check for Alpaca connectivity**: The startup health check only verifies API key exists, not that the connection works. The websocket connection is established later.

4. **Backend disabled in trading mode**: Log shows "Backend: Disabled" for both trading processes — the FastAPI backend runs separately from trading processes.
