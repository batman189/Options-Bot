# 12. External Dependency Validation

## Python Dependencies (requirements.txt)

| ID | Package | Version Pin | Purpose | Used By | Runtime Critical | Verdict |
|----|---------|-------------|---------|---------|-----------------|---------|
| DEP-001 | lumibot | >=4.4.50 | Trading framework (Strategy base class, backtesting) | strategies/base_strategy.py, scripts/backtest.py | YES | PASS — core framework, strategy inherits from Strategy |
| DEP-002 | alpaca-py | >=0.43.0 | Brokerage API (orders, account, positions) | base_strategy.py (via Lumibot), system.py, trading.py | YES | PASS — used for account checks, order execution via Lumibot |
| DEP-003 | xgboost | >=2.0.0 | ML model training and inference (XGBClassifier) | ml/trainer.py, ml/scalp_trainer.py, ml/xgboost_predictor.py, ml/scalp_predictor.py | YES | PASS — primary ML engine |
| DEP-004 | scikit-learn | >=1.4.0 | ML utilities (train_test_split, metrics, calibration) | ml/trainer.py, ml/scalp_trainer.py, ml/swing_classifier_trainer.py | YES | PASS — cross-validation, isotonic calibration |
| DEP-005 | pandas | >=2.0.0 | Data manipulation | Used across ml/, data/, strategies/ | YES | PASS |
| DEP-006 | numpy | >=1.24.0 | Numerical operations | Used across ml/, strategies/, ev_filter.py | YES | PASS |
| DEP-007 | scipy | >=1.11.0 | Scientific computing (norm.cdf for Black-Scholes) | ml/ev_filter.py line 340 (_estimate_delta) | YES | PASS — used for B-S delta fallback |
| DEP-008 | joblib | >=1.3.0 | Model serialization (save/load .xgb files) | ml/xgboost_predictor.py, ml/scalp_predictor.py | YES | PASS |
| DEP-009 | ta | >=0.11.0 | Technical analysis indicators | ml/feature_engineering.py | YES | PASS — RSI, MACD, Bollinger, ATR, etc. |
| DEP-010 | fastapi | >=0.110.0 | Backend REST API framework | backend/app.py, all backend/routes/*.py | YES | PASS |
| DEP-011 | uvicorn | >=0.27.0 | ASGI server for FastAPI | main.py (uvicorn.run) | YES | PASS |
| DEP-012 | pydantic | >=2.0.0 | Request/response validation schemas | backend/schemas.py | YES | PASS |
| DEP-013 | aiosqlite | >=0.20.0 | Async SQLite driver | backend/database.py, all route files | YES | PASS |
| DEP-014 | python-dotenv | >=1.0.0 | Load .env file | config.py line 10 (load_dotenv()) | YES | PASS |
| DEP-015 | requests | >=2.31.0 | HTTP client (Theta Terminal, earnings calendar) | data/theta_provider.py, data/earnings_calendar.py, routes/models.py | YES | PASS |
| DEP-016 | httpx | >=0.27.0 | Async HTTP client | Not directly imported in audited code | NO | FAIL — declared but not imported anywhere in current codebase. Unused dependency. |
| DEP-017 | yfinance | >=0.2.36 | Yahoo Finance data (earnings dates) | data/earnings_calendar.py | YES | PASS |
| DEP-018 | lightgbm | >=4.0.0 | LightGBM model training | ml/lgbm_trainer.py, ml/lgbm_predictor.py, ml/swing_classifier_trainer.py | YES | PASS |
| DEP-019 | optuna | >=3.5.0 | Hyperparameter optimization | ml/scalp_trainer.py, ml/swing_classifier_trainer.py | YES | PASS |
| DEP-020 | torch | >=2.0.0 | PyTorch deep learning | ml/tft_trainer.py, ml/tft_predictor.py | PARTIAL | PASS — TFT model training uses it; not used in active scalp/swing classifiers |
| DEP-021 | pytorch-lightning | >=2.0.0 | PyTorch training framework | ml/tft_trainer.py | PARTIAL | PASS — same as torch |
| DEP-022 | pytorch-forecasting | >=1.0.0 | Temporal Fusion Transformer | ml/tft_trainer.py, ml/tft_predictor.py | PARTIAL | PASS — same as torch |
| DEP-023 | tensorboard | >=2.14.0 | Training visualization | Not directly imported — used by pytorch-lightning internally | NO | PASS — transitive dependency for TFT training |

## Frontend Dependencies (package.json)

| ID | Package | Version | Purpose | Used By | Verdict |
|----|---------|---------|---------|---------|---------|
| FE-001 | react | ^19.2.0 | UI framework | All .tsx files | PASS |
| FE-002 | react-dom | ^19.2.0 | React DOM renderer | main.tsx | PASS |
| FE-003 | react-router-dom | ^6.30.3 | Client-side routing | App.tsx, all page components | PASS |
| FE-004 | @tanstack/react-query | ^5.90.21 | Data fetching/caching | All page components (useQuery, useMutation) | PASS |
| FE-005 | lucide-react | ^0.575.0 | Icon library | Various components (Activity, AlertTriangle, etc.) | PASS |

## External Services (Runtime)

| ID | Service | Protocol | Config Location | Required | Status |
|----|---------|----------|----------------|----------|--------|
| SVC-001 | Alpaca Markets API | HTTPS REST | .env (ALPACA_API_KEY, ALPACA_API_SECRET) | YES — order execution, account data | PASS — connected and verified via system/status endpoint |
| SVC-002 | ThetaData Terminal | HTTP localhost:25503 (v3) / :25510 (v2) | .env (THETA_TERMINAL_HOST, THETA_TERMINAL_PORT) | YES — options chain, historical bars | PASS — pre-check before training, circuit breaker for runtime |
| SVC-003 | Yahoo Finance | HTTPS (via yfinance) | None (public API) | PARTIAL — earnings calendar only | PASS — used by data/earnings_calendar.py |
| SVC-004 | Discord/Slack Webhook | HTTPS | .env (ALERT_WEBHOOK_URL) | NO — alert system, currently empty | PASS — feature exists but optional |

## Unused Dependency Finding

**BUG-012**: `httpx>=0.27.0` is declared in requirements.txt but never imported in the codebase.
- Evidence: `grep -r "import httpx" options-bot/` returns no results
- Impact: LOW — unnecessary installation, no runtime effect
- Recommendation: Remove from requirements.txt

## Summary

- **Total Python dependencies**: 23
- **Unused**: 1 (httpx)
- **Runtime-critical**: 17
- **Partial use**: 3 (torch/pytorch-lightning/pytorch-forecasting — only for TFT model type)
- **Total frontend dependencies**: 5 (all actively used)
- **External services**: 4 (2 required, 1 partial, 1 optional)
