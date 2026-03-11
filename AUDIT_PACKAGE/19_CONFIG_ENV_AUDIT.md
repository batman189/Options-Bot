# 19. Config / Environment Audit

## .env File (NOT tracked in git — verified)
- `ALPACA_API_KEY` — present, paper trading key
- `ALPACA_API_SECRET` — present
- `ALPACA_PAPER=true` — paper mode confirmed
- `THETA_TERMINAL_HOST=127.0.0.1`
- `THETA_TERMINAL_PORT=25503`
- `THETADATA_USERNAME` — present
- `THETADATA_PASSWORD` — present (plaintext)
- `DATADOWNLOADER_SKIP_LOCAL_START=true` — prevents Lumibot from starting Theta Terminal

**Security**: .env is in .gitignore and confirmed NOT tracked by git. Credentials are in plaintext on the local filesystem — standard practice for local development.

## .env.example
Documents: ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER, THETADATA_USERNAME, THETADATA_PASSWORD, optional THETA_TERMINAL_HOST/PORT, LOG_LEVEL.

**Missing from .env.example**: `DATADOWNLOADER_SKIP_LOCAL_START` (used in actual .env but not documented)

## config.py (to be audited by agent — key constants from code references)
Referenced constants from base_strategy.py imports:
- `DB_PATH` — path to SQLite database
- `DTE_EXIT_FLOOR` — minimum DTE before forced exit
- `THETA_CB_FAILURE_THRESHOLD` — circuit breaker failure count
- `THETA_CB_RESET_TIMEOUT` — circuit breaker reset timeout
- `MAX_CONSECUTIVE_ERRORS` — auto-pause threshold
- `ITERATION_ERROR_RESET_ON_SUCCESS` — reset error count on success
- `MODEL_HEALTH_WINDOW_SIZE` — health monitoring window
- `MODEL_DEGRADED_THRESHOLD` — degraded model threshold
- `MODEL_HEALTH_MIN_SAMPLES` — minimum samples for health
- `PREDICTION_RESOLVE_MINUTES_SWING` / `_SCALP` — prediction outcome timing
- `MIN_OPEN_INTEREST` / `MIN_OPTION_VOLUME` — liquidity thresholds
- `EARNINGS_BLACKOUT_DAYS_BEFORE` / `_AFTER` — earnings blackout
- `ALPACA_API_KEY` / `ALPACA_API_SECRET` — loaded from .env
- `VIX_REGIME_ENABLED` and related VIX thresholds
- `PORTFOLIO_MAX_ABS_DELTA` — delta limit
- `PRESET_DEFAULTS` — default configs per preset
- `VERSION` — app version string
- `LOGS_DIR` — log directory path

## Profile Config (from DB)
### Spy Scalp (ac3ff5ea)
```json
{
  "min_dte": 0, "max_dte": 0, "sleeptime": "1M",
  "max_hold_days": 0, "prediction_horizon": "30min",
  "profit_target_pct": 20, "stop_loss_pct": 15,
  "min_predicted_move_pct": 0.3, "min_confidence": 0.1,
  "min_ev_pct": 3, "max_position_pct": 20, "max_contracts": 15,
  "max_concurrent_positions": 5, "max_daily_trades": 10,
  "max_daily_loss_pct": 10, "bar_granularity": "1min",
  "feature_set": "scalp", "model_type": "xgb_classifier",
  "requires_min_equity": 25000, "vix_min": 12.0, "vix_max": 50.0,
  "implied_move_gate_enabled": false
}
```
**ISSUE**: `max_hold_days: 0` combined with `min_dte: 0, max_dte: 0` means theta_cost is always 0 in EV filter (BUG-001).

### TSLA Swing Test (ad48bf20)
```json
{
  "min_dte": 7, "max_dte": 45, "sleeptime": "5M",
  "max_hold_days": 7, "prediction_horizon": "1d",
  "profit_target_pct": 50, "stop_loss_pct": 30,
  "min_predicted_move_pct": 0.3, "min_ev_pct": 10,
  "max_position_pct": 20, "max_contracts": 5,
  "max_concurrent_positions": 3, "max_daily_trades": 5,
  "max_daily_loss_pct": 10, "bar_granularity": "5min",
  "feature_set": "swing", "model_type": "xgboost",
  "requires_min_equity": 0, "vix_max": 45.0, "min_confidence": 0.15
}
```

## requirements.txt
- Core: lumibot>=4.4.50, alpaca-py>=0.43.0
- ML: xgboost>=2.0.0, scikit-learn>=1.4.0, lightgbm>=4.0.0, optuna>=3.5.0
- DL: torch>=2.0.0, pytorch-lightning>=2.0.0, pytorch-forecasting>=1.0.0
- Backend: fastapi>=0.110.0, uvicorn>=0.27.0, pydantic>=2.0.0, aiosqlite>=0.20.0
- Data: yfinance>=0.2.36, httpx>=0.27.0
- No pinned versions — uses >= for all packages (risk of breaking changes on upgrade)
- **Missing**: `thetadata` SDK not listed (uses direct REST API via requests/httpx)
