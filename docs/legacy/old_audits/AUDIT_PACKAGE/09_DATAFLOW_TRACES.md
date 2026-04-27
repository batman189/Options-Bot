# 09 — DATAFLOW TRACES

## Trace 1: Market Data → Feature Computation → Prediction

### Source → Destination Chain

```
ThetaData Terminal (localhost:25503)
    ↓ HTTP GET /option/list/expirations, /option/list/strikes, /option/snapshot/quote
    ↓ (via data/theta_provider.py)
    ↓
Alpaca Paper Trading API (paper-api.alpaca.markets)
    ↓ REST API for bars, account, orders
    ↓ (via lumibot.brokers.alpaca)
    ↓
Lumibot Strategy.on_trading_iteration()
    ↓ (strategies/base_strategy.py)
    ↓
Feature Computation (ml/features.py)
    ↓ Input: 5-min bars (close, volume, vwap)
    ↓ Output: dict of 71-88 features
    ↓ Key features: return, rsi_14, macd_hist, atm_iv, scalp_orb_distance
    ↓
XGBoost Model Prediction (ml/predictor.py)
    ↓ Input: feature dict → numpy array
    ↓ Output: predicted_return, confidence
    ↓ Model file: models/ac3ff5ea-..._scalp_SPY_*.joblib
    ↓
Signal Log Entry (→ DB signal_logs table)
    ↓ Fields: profile_id, timestamp, symbol, underlying_price,
    ↓         predicted_return, step_stopped_at, stop_reason, entered, trade_id
    ↓
Pipeline Gates (step 0→1→6→8→9→9.5)
    ↓ Kill or Continue at each step
    ↓
EV Filter (ml/ev_filter.py)
    ↓ Input: predicted_return, underlying_price, chain data
    ↓ Output: EVCandidate (strike, expiration, direction, ev_pct)
    ↓
Trade Entry (→ Alpaca order API → DB trades table)
```

### Data Types at Each Boundary

| Boundary | Data Type | Format |
|----------|-----------|--------|
| ThetaData → Python | JSON over HTTP | `{"response": [...]}` |
| Alpaca → Lumibot | REST JSON | Bars, quotes, account data |
| Features → Model | numpy.ndarray | shape (1, n_features), float64 |
| Model → Pipeline | tuple | (predicted_return: float, confidence: float) |
| Pipeline → DB | SQL INSERT | signal_logs row |
| Pipeline → Broker | Lumibot Order | Asset, quantity, side |
| Broker → DB | SQL INSERT | trades row |

---

## Trace 2: User Request → API → DB → Response

### HTTP GET /api/trades

```
Browser (React fetch)
    ↓ GET http://localhost:8000/api/trades?limit=50
    ↓
FastAPI Router (backend/routes/trades.py)
    ↓ @router.get("/trades")
    ↓ async def get_trades(limit, offset, profile_id, status)
    ↓
Database Query (backend/database.py)
    ↓ aiosqlite.connect("db/options_bot.db")
    ↓ SELECT * FROM trades WHERE ... ORDER BY entry_date DESC LIMIT ?
    ↓
Response Serialization (backend/schemas.py)
    ↓ TradeResponse pydantic model
    ↓ JSON serialization with camelCase aliases
    ↓
HTTP Response → Browser
    ↓ Status 200, Content-Type: application/json
    ↓ Body: [{"id": "...", "profileId": "...", ...}]
    ↓
React State Update (ui/src/hooks/useTrades.ts)
    ↓ setTrades(response.data)
    ↓
DOM Render (ui/src/pages/Trades.tsx)
    ↓ Table rows with trade data
```

### Evidence

- Curl request: `AUDIT_PACKAGE/curl/EP18_GET_trades.json`
- Response size: 2,502 bytes
- Response contains 4 trade objects (at time of first capture)
- DB row count: 31 trades total

---

## Trace 3: Training Request → Background Job → Model File → DB

### HTTP POST /api/models/train

```
Browser (React fetch)
    ↓ POST http://localhost:8000/api/models/train
    ↓ Body: {"profile_id": "ac3ff5ea-..."}
    ↓
FastAPI Router (backend/routes/models.py)
    ↓ @router.post("/models/train")
    ↓ async def start_training(request)
    ↓
Training Queue Insert (→ DB training_queue table)
    ↓ INSERT INTO training_queue (profile_id, status, consumed)
    ↓
Background Thread (ml/trainer.py or ml/scalp_trainer.py)
    ↓ Thread picks up queue entry
    ↓ Sets consumed=1
    ↓
Alpaca Historical Data Fetch
    ↓ GET bars for SPY, 5min, 60+ days
    ↓ Returns DataFrame with OHLCV data
    ↓
Feature Engineering (ml/features.py)
    ↓ Compute all technical indicators
    ↓ Label: forward return > neutral_band → UP/DOWN
    ↓ Output: X (n_samples, n_features), y (n_samples,)
    ↓
XGBoost Training
    ↓ Walk-forward cross-validation
    ↓ Isotonic calibration
    ↓ Output: fitted XGBClassifier + calibrator
    ↓
Model Serialization
    ↓ joblib.dump(model_bundle, "models/{profile}_{preset}_{symbol}_{model_id}.joblib")
    ↓
DB Model Record
    ↓ INSERT INTO models (id, profile_id, model_type, status, accuracy, file_path, ...)
    ↓
Training Log
    ↓ INSERT INTO training_logs (profile_id, level, message, timestamp)
    ↓ Via TrainingLogHandler → DB
```

### Evidence

- Curl: `AUDIT_PACKAGE/curl/EP15_POST_models_train.json`
- DB models: 4 ready models (see `AUDIT_PACKAGE/db/table_models.txt`)
- Training logs: 489 entries (see `AUDIT_PACKAGE/logs/training_logs_dump.txt`)
- Model files: 2 .joblib files in `models/` directory

---

## Trace 4: Trading Start → Strategy Process → Live Trading Loop

```
Browser or API
    ↓ POST /api/trading/start
    ↓ Body: {"profile_id": "ac3ff5ea-..."}
    ↓
FastAPI Handler (backend/routes/trading.py)
    ↓ Spawns subprocess or thread
    ↓ Updates system_state: {"pid": 179544, "started_at": "..."}
    ↓
Lumibot Strategy.__init__()
    ↓ Loads model from file_path in DB
    ↓ Initializes position tracking
    ↓ Connects to Alpaca broker
    ↓
Lumibot Event Loop
    ↓ Calls on_trading_iteration() on each bar
    ↓
on_trading_iteration() (strategies/base_strategy.py)
    ├── _check_emergency_stop()
    ├── _check_exits() for open positions
    ├── _get_features()
    ├── _get_prediction()
    ├── Gate checks (VIX, confidence, etc.)
    ├── scan_chain_for_best_ev()
    ├── _enter_trade()
    └── _log_signal()
```

### Evidence

- System state: `AUDIT_PACKAGE/db/system_state.txt` shows 2 active trading processes
- Trading status: `AUDIT_PACKAGE/curl/EP35_GET_trading_status.json`
- Signal logs: 1705 entries from live trading

---

## Trace 5: Trade Exit → PnL Calculation → DB Update

```
on_trading_iteration() detects exit condition
    ↓
_check_exits() (strategies/base_strategy.py)
    ├── Profit target: current_price >= entry_price * (1 + profit_target_pct/100)
    ├── Stop loss: current_price <= entry_price * (1 - stop_loss_pct/100)
    ├── Max hold: (now - entry_date).minutes >= max_hold_minutes
    ├── DTE floor: days_to_expiry < dte_exit_floor
    └── Model override: model predicts opposite direction
    ↓
strategy.sell_all() or strategy.sell()
    ↓ Sends market order to Alpaca
    ↓
PnL Calculation
    ↓ pnl_dollars = quantity * (exit_price - entry_price) * 100  (options)
    ↓ pnl_pct = (exit_price - entry_price) / entry_price * 100
    ↓
DB Update
    ↓ UPDATE trades SET exit_price=?, exit_date=?, exit_reason=?,
    ↓   pnl_dollars=?, pnl_pct=?, status='closed' WHERE id=?
    ↓
Signal Log Update (for entered trades)
    ↓ No update — signal_logs are immutable after creation
    ↓ (BUG-004: step_stopped_at remains NULL for entered trades)
```

### Evidence

- Trade exits: See `AUDIT_PACKAGE/db/table_trades.txt`
- Exit reasons distribution: profit_target=12, max_hold=10, expired_worthless=5, stop_loss=4
- PnL verified in `AUDIT_PACKAGE/15_NUMERICAL_PIPELINE_TRACES.md`

---

## Cross-Cutting Data Flows

### Configuration Flow

```
config.py → PRESET_DEFAULTS dict
    ↓ (read at import time)
    ↓
DB profiles.config column (JSON)
    ↓ (overrides config.py for existing profiles)
    ↓
Strategy.__init__() reads from parameters dict
    ↓ (config merged at startup)
```

**Important**: DB profile config takes precedence over config.py. Changing PRESET_DEFAULTS does not affect existing profiles.

### Error Flow

```
Exception in any pipeline step
    ↓
try/except in on_trading_iteration()
    ↓ Logs error, increments consecutive_errors counter
    ↓
If consecutive_errors >= MAX_CONSECUTIVE_ERRORS (default 5)
    ↓ Strategy enters "circuit breaker" mode
    ↓ Skips trading iterations until reset
    ↓
On next successful iteration
    ↓ consecutive_errors = 0 (if ITERATION_ERROR_RESET_ON_SUCCESS)
```

---

## Verdict

**PASS** — Five complete dataflow traces documented with evidence references. All data boundaries, types, and transformations are identified.
