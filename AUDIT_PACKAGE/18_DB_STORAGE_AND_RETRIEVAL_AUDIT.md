# 18. Database Storage and Retrieval Audit

## Database Location
- **Active DB**: `options-bot/db/options_bot.db` (all 8 tables, WAL mode)
- **Stale DB**: `options-bot/data/options_bot.db` (empty — 0 tables) — BUG-007
- **Config reference**: `config.py` → `DB_PATH = BASE_DIR / "db" / "options_bot.db"`

## Schema (from database.py lines 17-134)

### Table: profiles
| Column | Type | Constraints | Observed Values |
|--------|------|------------|-----------------|
| id | TEXT | PK | UUID format |
| name | TEXT | NOT NULL | "Spy Scalp", "TSLA Swing Test" |
| preset | TEXT | NOT NULL | "scalp", "swing" |
| status | TEXT | NOT NULL DEFAULT 'created' | "active" |
| symbols | TEXT | NOT NULL | JSON array: '["SPY"]', '["TSLA"]' |
| config | TEXT | NOT NULL | JSON object with trading params |
| model_id | TEXT | nullable | UUID FK to models.id |
| created_at | TEXT | NOT NULL | ISO datetime |
| updated_at | TEXT | NOT NULL | ISO datetime with TZ |
**Row count**: 2

### Table: models
| Column | Type | Constraints | Observed Values |
|--------|------|------------|-----------------|
| id | TEXT | PK | UUID format |
| profile_id | TEXT | NOT NULL | UUID FK to profiles.id |
| model_type | TEXT | NOT NULL | "xgb_classifier", "lgbm_classifier" |
| file_path | TEXT | NOT NULL | Absolute Windows paths |
| status | TEXT | NOT NULL | "ready" |
| training_started_at | TEXT | nullable | ISO datetime with TZ |
| training_completed_at | TEXT | nullable | ISO datetime with TZ |
| data_start_date | TEXT | nullable | "2020-02-10", "2024-02-09" |
| data_end_date | TEXT | nullable | "2026-03-10" |
| metrics | TEXT | nullable | JSON with acc, fold details, feature importance |
| feature_names | TEXT | nullable | JSON array of feature name strings |
| hyperparameters | TEXT | nullable | JSON with model params |
| created_at | TEXT | NOT NULL | ISO datetime with TZ |
**Row count**: 4 (2 with valid file_path, 2 orphaned — BUG-002)

### Table: trades
| Column | Type | Constraints | Observed Values |
|--------|------|------------|-----------------|
| id | TEXT | PK | UUID |
| profile_id | TEXT | NOT NULL | FK to profiles.id |
| symbol | TEXT | NOT NULL | "SPY" |
| direction | TEXT | NOT NULL | "PUT" |
| strike | REAL | NOT NULL | 666.0-680.0 |
| expiration | TEXT | NOT NULL | "2026-03-04", "2026-03-11" |
| quantity | INTEGER | NOT NULL | 7-15 |
| entry_price | REAL | nullable | 0.04-0.21 |
| entry_date | TEXT | nullable | ISO datetime |
| entry_underlying_price | REAL | nullable | 677.54-685.395 |
| entry_predicted_return | REAL | nullable | -1.2671 to -0.1773 |
| entry_ev_pct | REAL | nullable | 49.39-164.95 |
| entry_features | TEXT | nullable | JSON with ~88 feature values |
| entry_greeks | TEXT | nullable | JSON with delta/gamma/theta/vega/iv |
| entry_model_type | TEXT | nullable | "xgboost", "scalp" |
| exit_price | REAL | nullable | 0.0-0.26 |
| exit_date | TEXT | nullable | ISO datetime |
| exit_underlying_price | REAL | nullable | 677.585-684.755, NULL for expired |
| exit_reason | TEXT | nullable | "profit_target", "expired_worthless", "max_hold" |
| exit_features | TEXT | nullable | all NULL |
| exit_greeks | TEXT | nullable | JSON or NULL |
| pnl_dollars | REAL | nullable | -225.0, 0.0, 75.0 |
| pnl_pct | REAL | nullable | -100.0, 0.0, 23.8 |
| actual_return_pct | REAL | nullable | all NULL |
| hold_days | INTEGER | nullable | 0 |
| was_day_trade | INTEGER | DEFAULT 0 | 1 (all are day trades) |
| market_vix | REAL | nullable | all NULL |
| market_regime | TEXT | nullable | all NULL |
| status | TEXT | NOT NULL DEFAULT 'open' | "closed" |
| created_at | TEXT | NOT NULL | ISO datetime |
| updated_at | TEXT | NOT NULL | ISO datetime |
**Row count**: 3 (all closed, total PnL: -$150)

**ISSUE**: actual_return_pct is always NULL — never populated. This field was intended to store the actual underlying return for model validation. It's defined in the schema but no code writes to it.

**ISSUE**: market_vix and market_regime are always NULL — also never populated.

**ISSUE**: exit_features is always NULL — no code captures features at exit time.

### Table: signal_logs
| Column | Type | Constraints | Observed Values |
|--------|------|------------|-----------------|
| id | INTEGER | PK AUTOINCREMENT | 3-1559 |
| profile_id | TEXT | NOT NULL | UUID |
| timestamp | TEXT | NOT NULL | ISO datetime with TZ |
| symbol | TEXT | NOT NULL | "SPY", "TSLA" |
| underlying_price | REAL | nullable | 414-685 |
| predicted_return | REAL | nullable | -1.28 to 0.29 |
| predictor_type | TEXT | nullable | "XGBoostPredictor", "ScalpPredictor", "SwingClassifierPredictor" |
| step_stopped_at | REAL | nullable | 0, 1, 6, 8.7, 9, 9.5, NULL (for entered trades) |
| stop_reason | TEXT | nullable | Various human-readable reasons |
| entered | INTEGER | DEFAULT 0 | 0 or 1 |
| trade_id | TEXT | nullable | UUID FK to trades.id |
**Row count**: 1557
**Index**: idx_signal_logs_profile_time ON (profile_id, timestamp DESC)

### Table: system_state
| Column | Type | Constraints | Observed Values |
|--------|------|------------|-----------------|
| key | TEXT | PK | "trading_<uuid>", "model_health_<uuid>" |
| value | TEXT | NOT NULL | JSON with PID/status or health metrics |
| updated_at | TEXT | NOT NULL | ISO datetime with TZ |
**Row count**: 4

### Table: training_logs
| Column | Type | Constraints | Observed Values |
|--------|------|------------|-----------------|
| id | INTEGER | PK AUTOINCREMENT | 4401-... |
| model_id | TEXT | NOT NULL | "training" (generic) or UUID |
| profile_id | TEXT | nullable (migration column) | UUID |
| timestamp | TEXT | NOT NULL | ISO datetime |
| level | TEXT | NOT NULL | "info", "warning", "error" |
| message | TEXT | NOT NULL | Training pipeline messages |
**Row count**: 2450

### Table: training_queue
| Column | Type | Constraints | Observed Values |
|--------|------|------------|-----------------|
| id | INTEGER | PK AUTOINCREMENT | 1-2 |
| trade_id | TEXT | NOT NULL | UUID FK to trades.id |
| profile_id | TEXT | NOT NULL | UUID |
| symbol | TEXT | NOT NULL | "SPY" |
| entry_features | TEXT | nullable | Full JSON feature snapshot |
| predicted_return | REAL | nullable | -1.267, -0.177 |
| actual_return_pct | REAL | nullable | 23.81, 0.0 (BUG-011: uses option PnL%, not underlying return) |
| queued_at | TEXT | NOT NULL | ISO datetime |
| consumed | INTEGER | DEFAULT 0 | 0 (BUG-009: never consumed) |
| consumed_at | TEXT | nullable | all NULL |
**Row count**: 2
**Index**: idx_training_queue_pending ON (profile_id, consumed)

## Indexes
1. `idx_signal_logs_profile_time` on signal_logs (profile_id, timestamp DESC) — correct for UI pagination
2. `idx_training_queue_pending` on training_queue (profile_id, consumed) — correct for consumption queries
3. No index on trades.profile_id — potential performance issue as trades grow

## Write Paths
1. **init_db()** (database.py:148) — CREATE TABLE IF NOT EXISTS + migrations
2. **Profile CRUD** — routes/profiles.py via aiosqlite
3. **Model training** — routes/models.py launches background thread that writes to models table
4. **Trade logging** — risk_manager.py:log_trade_open/log_trade_close via synchronous sqlite3
5. **Signal logging** — base_strategy.py:_write_signal_log via synchronous sqlite3
6. **System state** — routes/trading.py + base_strategy.py:_persist_health_to_db
7. **Training logs** — db_log_handler.py via synchronous sqlite3
8. **Feedback queue** — ml/feedback_queue.py:enqueue_completed_sample via synchronous sqlite3

## Concurrency Model
- Backend (FastAPI) uses aiosqlite with WAL mode
- Trading strategies run in separate processes, use synchronous sqlite3
- Both can write simultaneously — WAL mode handles this correctly for SQLite
- No connection pooling — each write opens/closes its own connection
- Potential: journal_mode=WAL is set in init_db() but trading processes don't set it — they inherit it from the DB file header (correct behavior for SQLite)

## Data Integrity Issues
1. No foreign key constraints enforced (SQLite FK pragma not enabled)
2. Orphaned model records (BUG-002)
3. actual_return_pct never populated in trades table
4. market_vix and market_regime never populated in trades table
5. Feedback queue actual_return_pct stores wrong metric (BUG-011)
6. signal_log IDs start at 3 (IDs 1-2 deleted or gap from early testing)
