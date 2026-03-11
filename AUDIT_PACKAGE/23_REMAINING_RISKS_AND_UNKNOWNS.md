# 23. Remaining Risks and Unknowns

## CRITICAL Risks

### RISK-001: 0DTE EV Calculation Ignores Theta Decay (BUG-001)
- **File**: ml/ev_filter.py:186
- **Impact**: All 0DTE scalp EV calculations produce inflated values because `hold_days_effective = min(0, 0) = 0` → theta_cost = 0
- **Current mitigant**: Liquidity gate rejects 98% of candidates (independently discovered safety net)
- **If liquidity gate passes**: Bot would trade on inflated EV, likely resulting in systematic losses on penny options
- **Recommendation**: Use `hold_days_effective = max(1, min(max_hold_days, dte))` as floor

### RISK-002: No Graceful Position Close on 0DTE Shutdown
- **File**: main.py, base_strategy.py
- **Impact**: If the trading process crashes or is killed after market hours, 0DTE options expire worthless with no close attempt
- **Current mitigant**: Scalp EOD rule (Rule 6 in _check_exits) closes positions before 3:50 PM ET — but only if the process is running
- **Recommendation**: Add pre-shutdown hook that market-sells all 0DTE positions

### RISK-003: SQLite Concurrent Write Contention
- **Impact**: Multiple trading subprocesses + backend + training threads all write to the same SQLite DB
- **Evidence**: WAL mode is enabled (database.py), which helps, but SQLite still has a single-writer lock
- **Under load**: Could cause "database is locked" errors during high-frequency iterations
- **Current mitigant**: Mostly low-frequency writes (signal logs once per iteration, ~1-5 min intervals)
- **Recommendation**: Monitor for "database is locked" errors in production; consider PostgreSQL if scaling

### RISK-004: No Authentication or Authorization
- **Impact**: All API endpoints are publicly accessible on localhost:8000. No auth tokens, API keys, or session management.
- **Current mitigant**: Runs on localhost only (API_HOST = "127.0.0.1")
- **Risk scenario**: If exposed to network (firewall misconfiguration, port forwarding), anyone can create profiles, start trading, delete data
- **Recommendation**: Add API key middleware if ever deployed beyond localhost

## HIGH Risks

### RISK-005: Orphaned Model Records in Database (BUG-002)
- **Evidence**: 2 of 4 model records in DB reference file paths that don't exist on disk
- **Impact**: If a profile's model_id points to a missing file, the trading subprocess will crash on startup when trying to load the model
- **Recommendation**: Add startup validation that checks model file_path existence

### RISK-006: Training Queue Never Consumed (BUG-006)
- **Evidence**: training_queue table has 0 rows; trade close code writes to it, but no automated consumer exists
- **Impact**: Incremental retraining must be triggered manually from UI. Models never auto-improve from live trade feedback.
- **Recommendation**: Implement scheduled consumer that triggers retrain when pending_count >= TRAINING_QUEUE_MIN_SAMPLES

### RISK-007: Spread Filter Dead Code (BUG-003)
- **File**: ml/ev_filter.py
- **Evidence**: `bid=None, ask=None` hardcoded in contract iteration → spread always computed as 0
- **Impact**: Spread cost is never deducted from EV, meaning illiquid contracts with wide spreads are not penalized
- **Recommendation**: Extract real bid/ask from broker option chain data

### RISK-008: VIX Proxy Accuracy
- **Evidence**: System uses VIXY ETF price as VIX proxy (config.py:252-253)
- **Impact**: VIXY tracks VIX futures, not spot VIX. During contango/backwardation, VIXY diverges significantly from actual VIX level
- **Current state**: Post-reverse-split VIXY ≈ VIX (approximately 1:1), but this is not guaranteed
- **Recommendation**: Add a check for VIXY/VIX divergence or use actual VIX data source

## MEDIUM Risks

### RISK-009: start_bot.bat Opens Browser Before Backend Ready (BUG-008)
- **Evidence**: `start http://localhost:8000` is first line in start_bot.bat, before `python main.py`
- **Impact**: User sees a connection error page, must manually refresh
- **Recommendation**: Add a delay or poll loop before opening browser

### RISK-010: No Foreign Key Enforcement in SQLite
- **Evidence**: database.py schema uses `profile_id TEXT NOT NULL` but no FK constraints, and `PRAGMA foreign_keys` is not set
- **Impact**: Manual cascade delete (profiles.py:284-356) is the only referential integrity mechanism. A code bug could create orphaned records.
- **Recommendation**: Enable `PRAGMA foreign_keys = ON` and add FK constraints

### RISK-011: sys.path.insert(0) Used Throughout
- **Evidence**: Almost every backend module does `sys.path.insert(0, str(Path(__file__).parent.parent))` for imports
- **Impact**: Fragile import resolution that depends on file layout. Could break if files are moved.
- **Recommendation**: Use proper package structure with __init__.py files and pip install -e .

### RISK-012: Thread-Safety of _active_jobs and _processes
- **Evidence**: Both use threading.Lock for access, but the lock patterns are acquire-check-release-then-act, which allows TOCTOU races
- **Impact**: Low probability — concurrent HTTP requests to train/start the same profile could bypass duplicate detection
- **Recommendation**: Use atomic check-and-claim within the lock scope (already mostly done, but verify edge cases)

## LOW Risks

### RISK-013: Hardcoded MAX_TOTAL_POSITIONS in Frontend
- **Evidence**: Dashboard.tsx:21 `const MAX_TOTAL_POSITIONS = 10` with comment "Must match backend config.py"
- **Impact**: If backend config changes, frontend display becomes inaccurate
- **Recommendation**: Return this value from the system status endpoint

### RISK-014: httpx Unused Dependency
- **Evidence**: requirements.txt includes `httpx>=0.27.0` but no code imports it
- **Impact**: Unnecessary package installation, trivial disk/memory waste
- **Recommendation**: Remove from requirements.txt

### RISK-015: Model Degradation Threshold Hardcoded in Frontend
- **Evidence**: Dashboard.tsx:524 hardcodes `52` for degradation threshold display
- **Impact**: Backend uses MODEL_DEGRADED_THRESHOLD = 0.45 (45%). Frontend displays "below 52% threshold" — misleading
- **Recommendation**: Return threshold from model-health endpoint or fix hardcoded value

## Unknowns (Cannot Validate Without Runtime)

### UNK-001: Actual Lumibot Order Execution
- **What**: Whether Lumibot correctly places and fills options orders on Alpaca
- **Why**: Requires live or paper trading session to validate
- **Blocked by**: No active trading session during audit

### UNK-002: ThetaData Terminal Response Format
- **What**: Whether ThetaData Terminal v3 API responses match the parsing code in theta_provider.py
- **Why**: Terminal not running during audit
- **Blocked by**: No live ThetaData Terminal connection

### UNK-003: Backtest Module Functionality
- **What**: Whether scripts/backtest.py run_backtest() produces valid results
- **Why**: Requires ThetaData Terminal + historical data
- **Blocked by**: No terminal, no runtime validation

### UNK-004: Isotonic Calibration Accuracy
- **What**: Whether isotonic calibration improves or worsens prediction reliability in live trading
- **Why**: Only 19 resolved predictions in DB (insufficient sample size)
- **Blocked by**: Insufficient live trading history
