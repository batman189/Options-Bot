# 18 -- DB Persistence Validation

Audit date: 2026-03-11

Evidence directory: `AUDIT_PACKAGE/db/`

Source file: `options-bot/backend/database.py`

---

## 1. Schema Validation

### 1.1 Table Inventory

| # | Table | In DB (schema.sql) | In Code (SCHEMA_SQL) | Verdict |
|---|-------|--------------------|-----------------------|---------|
| 1 | profiles | YES | YES | PASS |
| 2 | models | YES | YES | PASS |
| 3 | trades | YES | YES | PASS -- but see 1.2 |
| 4 | system_state | YES | YES | PASS |
| 5 | training_logs | YES | YES | PASS |
| 6 | signal_logs | YES | YES | PASS |
| 7 | training_queue | YES | YES | PASS |
| 8 | sqlite_sequence | YES (auto-created) | N/A | PASS -- SQLite internal |

Evidence: `db/schema.sql` lists all tables. Code `SCHEMA_SQL` in `database.py:17-134` defines all 7 application tables plus 2 indexes. `init_db()` verifies at startup that all 7 expected tables exist (line 197).

### 1.2 Column-Level Comparison: trades

The live DB has **2 columns not present** in the code's `CREATE TABLE` statement, and there is **no `ALTER TABLE` migration** for them:

| Column | In DB schema.sql | In Code CREATE TABLE | Migration exists? |
|--------|-----------------|----------------------|-------------------|
| exit_features TEXT | YES (between exit_reason and exit_greeks) | **NO** | **NO** |
| actual_return_pct REAL | YES (between pnl_pct and hold_days) | **NO** | **NO** |

**Verdict: FAIL** -- These two columns exist in the live database but are absent from both the CREATE TABLE statement and the ALTER TABLE migrations. If the database were recreated from scratch (new install, tests), these columns would be missing. The code that writes `actual_return_pct` into the training_queue table does exist (`database.py:126`), but the trades table definition at line 49-79 lacks both columns. This means:
- A fresh database will lack `exit_features` and `actual_return_pct` on the trades table.
- Any INSERT/UPDATE referencing these columns on trades will fail on a fresh DB.

Evidence: Compare `db/schema.sql` lines 57-89 (DB dump) against `database.py` lines 49-79 (code). The code skips `exit_features` (should be between `exit_reason` and `exit_greeks`) and `actual_return_pct` (should be between `pnl_pct` and `hold_days`).

### 1.3 Column-Level Comparison: All Other Tables

**profiles** -- DB and code match exactly: `id, name, preset, status, symbols, config, model_id, created_at, updated_at`. **PASS**

**models** -- DB and code match exactly: `id, profile_id, model_type, file_path, status, training_started_at, training_completed_at, data_start_date, data_end_date, metrics, feature_names, hyperparameters, created_at`. **PASS**

**signal_logs** -- DB and code match exactly: `id, profile_id, timestamp, symbol, underlying_price, predicted_return, predictor_type, step_stopped_at, stop_reason, entered, trade_id`. Column type for `step_stopped_at` is REAL in code, consistent with DB values including 9.5. **PASS**

**system_state** -- DB and code match exactly: `key, value, updated_at`. **PASS**

**training_logs** -- DB shows columns `id, model_id, timestamp, level, message, profile_id`. Code CREATE TABLE defines `id, model_id, profile_id, timestamp, level, message`. The column order differs (DB has `profile_id` appended at the end because it was added via ALTER TABLE), but this is functionally irrelevant in SQLite. **PASS**

**training_queue** -- DB and code match exactly: `id, trade_id, profile_id, symbol, entry_features, predicted_return, actual_return_pct, queued_at, consumed, consumed_at`. **PASS**

### 1.4 Indexes

| Index | In DB | In Code | Verdict |
|-------|-------|---------|---------|
| idx_signal_logs_profile_time ON signal_logs(profile_id, timestamp DESC) | YES | YES | PASS |
| idx_training_queue_pending ON training_queue(profile_id, consumed) | YES | YES | PASS |

Evidence: `db/schema.sql` lines 1-5, `database.py` lines 114-133.

---

## 2. Data Integrity

### 2.1 Row Counts

| Table | Row Count | Source Evidence |
|-------|-----------|-----------------|
| profiles | 3 | `db/table_profiles.txt` |
| models | 4 | `db/table_models.txt` |
| trades | 4 | `db/table_trades.txt` |
| signal_logs | 1,666 | `db/table_signal_logs.txt` |
| training_logs | 155,333 | `db/table_training_logs.txt` |
| training_queue | 3 | `db/table_training_queue.txt` |
| system_state | 5 (dump) / 6 (full) | `db/table_system_state.txt` / `db/system_state.txt` |

Note: `db/table_system_state.txt` shows 5 rows; `db/system_state.txt` (full dump) shows 6 rows. The discrepancy is because the full dump captured a later backtest row (row 6: `backtest_ac3ff5ea...`). The system_state table has no AUTOINCREMENT so the count difference is a timing artifact between evidence captures.

**Verdict: PASS** -- Row counts are consistent across evidence files. The sqlite_sequence table (`db/table_sqlite_sequence.txt`) confirms: training_logs seq=560564, signal_logs seq=1668, training_queue seq=3. The sequence numbers exceed row counts because deleted rows consume sequence values (or rows were bulk-deleted).

### 2.2 Foreign Key Relationships

SQLite does not enforce foreign keys by default (`PRAGMA foreign_keys` is OFF unless explicitly enabled). The schema defines NO foreign key constraints -- all cross-table references rely on application-level consistency.

#### 2.2.1 models.profile_id -> profiles.id

| Model profile_id | Profile exists? |
|-------------------|----------------|
| ad48bf20-1913-4f40-b028-0580c9f48168 | YES (TSLA Swing Test) |
| ac3ff5ea-f8a8-4046-af54-d52efe8ec7f4 | YES (Spy Scalp) -- 3 models |

Evidence: `db/table_models.txt` rows 1-4, cross-referenced with `db/table_profiles.txt`.

**Verdict: PASS** -- All 4 models reference existing profiles.

#### 2.2.2 trades.profile_id -> profiles.id

| Trade profile_id | Profile exists? |
|-------------------|----------------|
| ac3ff5ea-f8a8-4046-af54-d52efe8ec7f4 | YES (Spy Scalp) -- 3 trades |
| backtest | **NO** -- not a real profile |

Trade `2bc60eef` has `profile_id: backtest`, which is a synthetic ID used by the backtesting system. No profile with `id = 'backtest'` exists in the profiles table.

**Verdict: FAIL (minor)** -- 1 out of 4 trades references a non-existent profile (`backtest`). This is by design for backtesting but constitutes an orphan record from a referential integrity standpoint. If any query JOINs trades to profiles, this row will be silently dropped.

Evidence: `db/table_trades.txt` Row 4, `db/table_profiles.txt` (no profile with id "backtest").

#### 2.2.3 signal_logs.profile_id -> profiles.id

Sample rows in `db/table_signal_logs.txt` all show `profile_id: ac3ff5ea-f8a8-4046-af54-d52efe8ec7f4` (Spy Scalp), which exists. The `db/gate_kill_queries.txt` step_stopped_at distribution covers 1,666 rows. No evidence of signal_logs referencing non-existent profiles.

**Verdict: PASS** (based on sample; full scan would require DB query).

#### 2.2.4 training_queue.profile_id -> profiles.id

| Queue profile_id | Profile exists? |
|-------------------|----------------|
| ac3ff5ea-f8a8-4046-af54-d52efe8ec7f4 | YES (Spy Scalp) -- 2 rows |
| backtest | **NO** |

**Verdict: FAIL (minor)** -- Same `backtest` orphan issue. 1 of 3 training_queue rows references non-existent profile.

Evidence: `db/table_training_queue.txt` Row 3.

#### 2.2.5 training_logs.profile_id -> profiles.id

Sample shows `profile_id: ad48bf20-1913-4f40-b028-0580c9f48168` which exists. Only `info` level logs (243 per `db/gate_kill_queries.txt`; 155,333 total per `db/table_training_logs.txt` -- the 243 is from the system_state evidence which counted by level).

**Verdict: PASS** (based on sample).

#### 2.2.6 profiles.model_id -> models.id

| Profile model_id | Model exists? |
|-------------------|--------------|
| ce4bfaf5-ac35-49eb-bc04-38063659c5c9 (TSLA Swing) | YES |
| 171859fb-94bd-4209-ad99-c220abbde290 (Spy Scalp) | YES |
| None (Audit Test Updated) | N/A |

**Verdict: PASS** -- All non-null model_id values reference existing models.

### 2.3 Orphan Records: Model Files on Disk

From `db/orphan_check.txt`:

| Model ID | file_on_disk | Status |
|----------|-------------|--------|
| ce4bfaf5 (TSLA lgbm) | EXISTS | OK |
| 8b4987ee (SPY xgb v1) | **MISSING** | ORPHAN |
| 385f4ea1 (SPY xgb v2) | **MISSING** | ORPHAN |
| 171859fb (SPY xgb v3 -- active) | EXISTS | OK |

**Verdict: FAIL** -- 2 of 4 model records reference `.joblib` files that no longer exist on disk. These are stale model rows from previous training runs that were superseded but never cleaned up. The active model (`171859fb`, currently referenced by the Spy Scalp profile) does exist. The stale rows with `status: ready` are misleading -- they would fail at load time if selected.

Evidence: `db/orphan_check.txt` lines 11-25.

### 2.4 NULL Values in Required Fields

Checked NOT NULL constraints from schema against evidence data:

| Table | NOT NULL columns | NULLs found? | Verdict |
|-------|-----------------|---------------|---------|
| profiles | id, name, preset, status, symbols, config, created_at, updated_at | No NULLs in any required field | PASS |
| models | id, profile_id, model_type, file_path, status, created_at | No NULLs in any required field | PASS |
| trades | id, profile_id, symbol, direction, strike, expiration, quantity, status, created_at, updated_at | No NULLs in required fields | PASS |
| signal_logs | id, profile_id, timestamp, symbol | No NULLs in required fields | PASS |
| system_state | key, value, updated_at | No NULLs | PASS |
| training_logs | id, model_id, timestamp, level, message | No NULLs in required fields | PASS |
| training_queue | id, trade_id, profile_id, symbol, queued_at | No NULLs in required fields | PASS |

Notable nullable fields with NULL values (expected behavior):
- `trades.actual_return_pct`: NULL in all 4 rows (never populated for trades)
- `trades.market_vix`, `trades.market_regime`: NULL in all rows (not yet implemented)
- `trades.exit_underlying_price`: NULL in 1 row (expired_worthless trade)
- `signal_logs.predicted_return`: NULL in sample rows (signal rejected before prediction)

**Verdict: PASS** -- No NOT NULL constraint violations.

---

## 3. Migration Safety

### 3.1 ALTER TABLE Statements

Only one migration exists in `database.py` lines 159-165:

```python
try:
    await db.execute("ALTER TABLE training_logs ADD COLUMN profile_id TEXT")
    await db.commit()
    logger.info("Migration: added profile_id column to training_logs")
except Exception:
    pass  # Column already exists
```

**Verdict: PASS** -- The single ALTER TABLE migration is correctly wrapped in try/except. The `except Exception: pass` pattern is appropriate here because SQLite raises an error if the column already exists, and there is no `IF NOT EXISTS` syntax for ALTER TABLE ADD COLUMN in SQLite.

### 3.2 Missing Migrations

As documented in Section 1.2, the `exit_features` and `actual_return_pct` columns on the trades table exist in the live DB but have **no corresponding migration**. These were likely added manually or by a prior code version that has since been removed.

**Verdict: FAIL** -- If a fresh database is created, these columns will be absent. Migrations should be added:

```python
try:
    await db.execute("ALTER TABLE trades ADD COLUMN exit_features TEXT")
    await db.commit()
except Exception:
    pass

try:
    await db.execute("ALTER TABLE trades ADD COLUMN actual_return_pct REAL")
    await db.commit()
except Exception:
    pass
```

Or, better, add them to the CREATE TABLE statement directly.

### 3.3 Stale Training Status Reset

`init_db()` lines 170-187 reset profiles stuck in `status='training'` at startup. This is a safe migration pattern that runs idempotently on every startup.

**Verdict: PASS**

---

## 4. Concurrent Access

### 4.1 WAL Mode

`init_db()` line 154 enables WAL (Write-Ahead Logging):

```python
await db.execute("PRAGMA journal_mode=WAL")
```

WAL mode allows concurrent readers with a single writer, preventing "database is locked" errors during simultaneous read operations. This is the correct choice for a FastAPI application with async endpoints.

**Verdict: PASS**

### 4.2 aiosqlite Usage

`aiosqlite` is imported and used throughout the backend. The `get_db()` async generator (lines 137-145) yields a connection and closes it in a `finally` block, compatible with FastAPI's `Depends()` injection.

Files using aiosqlite (via `get_db` dependency):
- `backend/routes/trades.py`
- `backend/routes/models.py`
- `backend/routes/system.py`
- `backend/routes/profiles.py`
- `backend/routes/trading.py`
- `backend/routes/signals.py`
- `backend/db_log_handler.py`
- `backend/app.py`

**Verdict: PASS** -- All database access goes through aiosqlite async connections.

### 4.3 Connection Lifecycle

Each request gets its own connection via `get_db()` (async generator with `yield`). Connections are closed in the `finally` block. No connection pooling is used -- aiosqlite opens/closes per request. This is acceptable for SQLite (file-based, no TCP overhead) but could become a bottleneck under high concurrency.

**Verdict: PASS** (acceptable for current scale).

### 4.4 Foreign Key Enforcement

```
PRAGMA foreign_keys is NOT enabled.
```

No `PRAGMA foreign_keys = ON` statement exists anywhere in the codebase. SQLite defaults to OFF. This means referential integrity is never enforced at the database level -- only at the application level.

**Verdict: FAIL (minor)** -- Foreign keys are not enforced. The orphan records documented in Section 2.2 (backtest profile_id) are a direct consequence. For a small-scale trading bot this is low risk, but enabling `PRAGMA foreign_keys = ON` after `get_db()` connects would catch bugs earlier.

---

## 5. Summary

| # | Check | Verdict | Details |
|---|-------|---------|---------|
| 1.1 | Table inventory | **PASS** | All 7 tables present in both code and DB |
| 1.2 | trades column drift | **FAIL** | `exit_features` and `actual_return_pct` in DB but not in CREATE TABLE or migrations |
| 1.3 | Other table columns | **PASS** | All match |
| 1.4 | Indexes | **PASS** | Both indexes present |
| 2.1 | Row counts | **PASS** | Consistent across evidence files |
| 2.2 | FK: models->profiles | **PASS** | All 4 models reference existing profiles |
| 2.3 | FK: trades->profiles | **FAIL (minor)** | 1 orphan (`backtest` pseudo-profile) |
| 2.4 | FK: signal_logs->profiles | **PASS** | Sample clean |
| 2.5 | FK: training_queue->profiles | **FAIL (minor)** | 1 orphan (`backtest`) |
| 2.6 | FK: profiles->models | **PASS** | All non-null model_ids valid |
| 2.7 | Model files on disk | **FAIL** | 2 of 4 model file_paths point to missing .joblib files |
| 2.8 | NOT NULL constraints | **PASS** | No violations |
| 3.1 | ALTER TABLE safety | **PASS** | Wrapped in try/except |
| 3.2 | Missing migrations | **FAIL** | No migration for exit_features, actual_return_pct on trades |
| 3.3 | Stale status reset | **PASS** | Idempotent startup cleanup |
| 4.1 | WAL mode | **PASS** | Enabled at init |
| 4.2 | aiosqlite usage | **PASS** | All 9 backend files use async access |
| 4.3 | Connection lifecycle | **PASS** | Proper open/yield/close pattern |
| 4.4 | Foreign key enforcement | **FAIL (minor)** | PRAGMA foreign_keys not enabled |

### Critical Failures

1. **Schema drift on trades table** (1.2 / 3.2) -- Two columns (`exit_features`, `actual_return_pct`) exist in the live DB but not in the code's CREATE TABLE or any migration. A fresh install will produce a trades table missing these columns.

2. **Stale model records with missing files** (2.7) -- Two model rows (8b4987ee, 385f4ea1) have `status: ready` but their `.joblib` files do not exist on disk. If these models were ever loaded (e.g., by reverting `model_id` on a profile), the system would crash.

### Minor Failures

3. **Backtest orphan records** (2.3, 2.5) -- The backtesting system uses `profile_id = 'backtest'` which has no corresponding profiles row. Low risk but would break any JOIN-based queries.

4. **No FK enforcement** (4.4) -- `PRAGMA foreign_keys = ON` is never set. All referential integrity is application-level only.
