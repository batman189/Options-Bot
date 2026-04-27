# 03 — FILE-BY-FILE AUDIT (Python Source Files)

## Summary

**Total Python files**: 66
**Scope**: Every .py file in options-bot/ (excluding __pycache__, node_modules, ui/)
**Method**: AST parsing for symbols, docstring extraction, side-effect detection

---

### options-bot/config.py
- **Lines**: 270
- **Purpose**: Global configuration constants for options-bot.
- **Classes**: None
- **Functions**: None
- **Key imports**: dotenv, os, pathlib
- **Side effects**: None
- **Verdict**: PASS

### options-bot/main.py
- **Lines**: 589
- **Purpose**: Options Bot entry point.
- **Classes**: None
- **Functions**: _shutdown_handler, _print_startup_banner, _kill_existing_on_port, start_backend, load_profile_from_db, _get_strategy_class, start_trading_single, start_trading_multi, main, _load
- **Key imports**: aiosqlite, argparse, asyncio, backend.app, backend.db_log_handler, config, datetime, json
- **Side effects**: DB, network, logging
- **Verdict**: PASS

### options-bot/backend/__init__.py
- **Lines**: 1
- **Purpose**: No module docstring
- **Classes**: None
- **Functions**: None
- **Key imports**: None
- **Side effects**: None
- **Verdict**: PASS

### options-bot/backend/app.py
- **Lines**: 447
- **Purpose**: FastAPI application — entry point for the backend.
- **Classes**: None
- **Functions**: _store_backtest_result, _backtest_job, lifespan, run_backtest_endpoint, get_backtest_results, _save, serve_spa
- **Key imports**: aiosqlite, asyncio, backend.database, backend.routes, backend.schemas, config, contextlib, datetime
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/backend/database.py
- **Lines**: 204
- **Purpose**: SQLite database connection and schema management.
- **Classes**: None
- **Functions**: get_db, init_db
- **Key imports**: aiosqlite, config, logging, pathlib, sys
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/backend/db_log_handler.py
- **Lines**: 87
- **Purpose**: Custom logging handlers that write records to the training_logs SQLite table.
- **Classes**: DatabaseLogHandler, TrainingLogHandler
- **Functions**: __init__, emit, __init__, emit
- **Key imports**: datetime, logging, sqlite3, threading
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/backend/schemas.py
- **Lines**: 294
- **Purpose**: Pydantic request/response schemas.
- **Classes**: ProfileCreate, ProfileUpdate, ModelSummary, ProfileResponse, ModelResponse
- **Functions**: None
- **Key imports**: pydantic, typing
- **Side effects**: None
- **Verdict**: PASS

### options-bot/backend/routes/__init__.py
- **Lines**: 1
- **Purpose**: No module docstring
- **Classes**: None
- **Functions**: None
- **Key imports**: None
- **Side effects**: None
- **Verdict**: PASS

### options-bot/backend/routes/models.py
- **Lines**: 1086
- **Purpose**: Model training and status endpoints.
- **Classes**: None
- **Functions**: _install_training_logger, _remove_training_logger, _check_theta_or_raise, _set_profile_status, _get_failure_status, _extract_and_persist_importance, _full_train_job, _incremental_retrain_job, _tft_train_job, _ensemble_train_job
- **Key imports**: aiosqlite, asyncio, backend.database, backend.db_log_handler, backend.schemas, config, datetime, fastapi
- **Side effects**: DB, network, logging
- **Verdict**: PASS

### options-bot/backend/routes/profiles.py
- **Lines**: 415
- **Purpose**: Profile CRUD endpoints.
- **Classes**: None
- **Functions**: _model_row_to_summary, _build_profile_response, _get_trade_stats, _full_profile_response, list_profiles, get_profile, create_profile, update_profile, delete_profile, activate_profile
- **Key imports**: aiosqlite, asyncio, backend.database, backend.schemas, config, datetime, fastapi, json
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/backend/routes/signals.py
- **Lines**: 124
- **Purpose**: Signal decision log endpoints.
- **Classes**: None
- **Functions**: _row_to_signal, export_signal_logs, get_signal_logs
- **Key imports**: aiosqlite, backend.database, backend.schemas, csv, datetime, fastapi, fastapi.responses, io
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/backend/routes/system.py
- **Lines**: 481
- **Purpose**: System health and status endpoints.
- **Classes**: None
- **Functions**: _read_circuit_states, health_check, get_system_status, get_pdt_status, clear_error_logs, get_recent_errors, get_model_health, get_training_queue_status, _check_alpaca, _check_theta
- **Key imports**: aiosqlite, alpaca.trading.client, asyncio, backend.database, backend.schemas, config, datetime, fastapi
- **Side effects**: DB, network, logging
- **Verdict**: PASS

### options-bot/backend/routes/trades.py
- **Lines**: 197
- **Purpose**: Trade history endpoints.
- **Classes**: None
- **Functions**: _row_to_trade, list_active_trades, get_trade_stats, export_trades, list_trades, get_trade
- **Key imports**: aiosqlite, backend.database, backend.schemas, csv, fastapi, fastapi.responses, io, logging
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/backend/routes/trading.py
- **Lines**: 688
- **Purpose**: Trading process management endpoints.
- **Classes**: None
- **Functions**: _is_process_alive, _get_python_exe, _get_main_py_path, _store_process_state, _clear_process_state, _watchdog_loop, _watchdog_check_once, _set_profile_status_sync, _watchdog_restart_profile, start_watchdog
- **Key imports**: aiosqlite, asyncio, backend.database, backend.schemas, config, ctypes, ctypes.wintypes, datetime
- **Side effects**: DB, file_I/O, logging
- **Verdict**: PASS

### options-bot/data/__init__.py
- **Lines**: 1
- **Purpose**: No module docstring
- **Classes**: None
- **Functions**: None
- **Key imports**: None
- **Side effects**: None
- **Verdict**: PASS

### options-bot/data/alpaca_provider.py
- **Lines**: 261
- **Purpose**: Alpaca stock data provider implementation.
- **Classes**: AlpacaStockProvider
- **Functions**: __init__, _init_clients, _timeframe_to_alpaca, get_historical_bars, get_latest_price, test_connection
- **Key imports**: alpaca.data.historical, alpaca.data.requests, alpaca.data.timeframe, alpaca.trading.client, config, data.provider, datetime, logging
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/data/earnings_calendar.py
- **Lines**: 134
- **Purpose**: Earnings calendar checker using yfinance.
- **Classes**: None
- **Functions**: has_earnings_in_window, _get_earnings_dates
- **Key imports**: datetime, logging, time, typing, yfinance
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/data/greeks_calculator.py
- **Lines**: 273
- **Purpose**: Black-Scholes Greeks calculator for options features.
- **Classes**: None
- **Functions**: _bs_d1_d2, compute_greeks, compute_greeks_vectorized
- **Key imports**: config, logging, numpy, pathlib, scipy.stats, sys
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/data/options_data_fetcher.py
- **Lines**: 548
- **Purpose**: Historical options data fetcher for ML training.
- **Classes**: None
- **Functions**: _bs_price, _implied_vol, _third_friday, _pick_expiration_for_period, _fetch_eod_batch, _process_eod_day, fetch_options_for_training
- **Key imports**: collections, config, data.greeks_calculator, datetime, io, logging, numpy, pandas
- **Side effects**: network, logging
- **Verdict**: PASS

### options-bot/data/provider.py
- **Lines**: 173
- **Purpose**: Abstract DataProvider interface.
- **Classes**: StockDataProvider, OptionsDataProvider
- **Functions**: get_historical_bars, get_latest_price, test_connection, get_expirations, get_strikes, get_historical_greeks, get_historical_ohlc, get_historical_eod, get_bulk_greeks_eod, test_connection
- **Key imports**: abc, datetime, pandas, typing
- **Side effects**: None
- **Verdict**: PASS

### options-bot/data/theta_provider.py
- **Lines**: 503
- **Purpose**: Theta Data options data provider implementation.
- **Classes**: ThetaOptionsProvider
- **Functions**: __init__, _request, _parse_csv_response, _format_date, _format_strike, get_expirations, get_strikes, get_historical_greeks, get_historical_ohlc, get_historical_eod
- **Key imports**: config, data.provider, datetime, io, logging, pandas, pathlib, requests
- **Side effects**: network, logging
- **Verdict**: PASS

### options-bot/data/validator.py
- **Lines**: 502
- **Purpose**: Data integrity validator for training symbols.
- **Classes**: None
- **Functions**: _check_bar_count, _check_data_depth, _check_gaps, _check_ohlcv_quality, _check_daily_completeness, validate_symbol_data, validate_all_symbols
- **Key imports**: config, data.alpaca_provider, datetime, logging, numpy, pandas, pathlib, sys
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/data/vix_provider.py
- **Lines**: 224
- **Purpose**: VIX data provider — fetches current VIX level from Alpaca.
- **Classes**: VIXProvider
- **Functions**: fetch_vix_daily_bars, __init__, get_current_vix
- **Key imports**: alpaca.data.historical, alpaca.data.requests, alpaca.data.timeframe, config, data.alpaca_provider, datetime, logging, pandas
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/__init__.py
- **Lines**: 1
- **Purpose**: No module docstring
- **Classes**: None
- **Functions**: None
- **Key imports**: None
- **Side effects**: None
- **Verdict**: PASS

### options-bot/ml/ensemble_predictor.py
- **Lines**: 790
- **Purpose**: Ensemble (stacking) ModelPredictor.
- **Classes**: EnsemblePredictor
- **Functions**: __init__, load, save, predict, predict_batch, get_feature_names, get_feature_importance, train_meta_learner, _save_to_db
- **Key imports**: aiosqlite, asyncio, concurrent.futures, config, data.alpaca_provider, data.options_data_fetcher, data.vix_provider, datetime
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/ml/ev_filter.py
- **Lines**: 473
- **Purpose**: Expected Value filter for option contract selection.
- **Classes**: EVCandidate
- **Functions**: get_implied_move_pct, _estimate_delta, scan_chain_for_best_ev
- **Key imports**: dataclasses, datetime, logging, lumibot.entities, math, typing
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/feedback_queue.py
- **Lines**: 55
- **Purpose**: Closed-trade feedback queue for model retraining.
- **Classes**: None
- **Functions**: enqueue_completed_sample
- **Key imports**: datetime, json, logging, sqlite3, typing
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/ml/incremental_trainer.py
- **Lines**: 712
- **Purpose**: Incremental model retraining — update an existing model with new data only.
- **Classes**: None
- **Functions**: _run_async, _load_model_record, _get_profile_model_id, _save_incremental_model_to_db, retrain_incremental, _load, _load, _save
- **Key imports**: aiosqlite, asyncio, concurrent.futures, config, data.alpaca_provider, datetime, joblib, json
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/ml/lgbm_predictor.py
- **Lines**: 98
- **Purpose**: LightGBM ModelPredictor implementation.
- **Classes**: LightGBMPredictor
- **Functions**: __init__, load, save, set_model, predict, predict_batch, get_feature_names, get_feature_importance
- **Key imports**: joblib, logging, ml.predictor, numpy, pandas, pathlib, typing
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/lgbm_trainer.py
- **Lines**: 431
- **Purpose**: LightGBM training pipeline.
- **Classes**: None
- **Functions**: _walk_forward_cv_lgbm, train_lgbm_model, _run_async, _save_to_db
- **Key imports**: aiosqlite, asyncio, concurrent.futures, config, data.alpaca_provider, datetime, json, lightgbm
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/ml/liquidity_filter.py
- **Lines**: 191
- **Purpose**: Liquidity gate for options contracts.
- **Classes**: LiquidityResult
- **Functions**: check_liquidity, fetch_option_snapshot
- **Key imports**: alpaca.data.historical.option, alpaca.data.requests, dataclasses, logging, typing
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/predictor.py
- **Lines**: 51
- **Purpose**: Abstract ModelPredictor interface.
- **Classes**: ModelPredictor
- **Functions**: predict, predict_batch, get_feature_names, get_feature_importance
- **Key imports**: abc, pandas
- **Side effects**: None
- **Verdict**: PASS

### options-bot/ml/regime_adjuster.py
- **Lines**: 84
- **Purpose**: VIX regime-based confidence adjuster.
- **Classes**: None
- **Functions**: adjust_prediction_confidence
- **Key imports**: config, logging, pathlib, sys
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/scalp_predictor.py
- **Lines**: 209
- **Purpose**: Scalp XGBClassifier predictor — signed confidence output with isotonic calibration.
- **Classes**: ScalpPredictor
- **Functions**: __init__, load, save, set_model, predict, predict_batch, _calibrate_p_up, get_feature_names, get_feature_importance, get_avg_30min_move_pct
- **Key imports**: joblib, logging, ml.predictor, numpy, pandas, pathlib, typing
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/scalp_trainer.py
- **Lines**: 910
- **Purpose**: Scalp XGBClassifier training pipeline.
- **Classes**: None
- **Functions**: _get_feature_names, _compute_all_features, _calculate_binary_target, _subsample_strided, _optuna_optimize_classifier, _walk_forward_cv_classifier, train_scalp_model, _run_async, _save_to_db, objective
- **Key imports**: aiosqlite, asyncio, concurrent.futures, config, data.alpaca_provider, data.options_data_fetcher, data.vix_provider, datetime
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/ml/swing_classifier_predictor.py
- **Lines**: 160
- **Purpose**: Swing Classifier predictor — signed confidence output.
- **Classes**: SwingClassifierPredictor
- **Functions**: __init__, load, save, set_model, predict, predict_batch, get_feature_names, get_feature_importance, get_avg_daily_move_pct, _binary_to_signed_confidence
- **Key imports**: joblib, logging, ml.predictor, numpy, pandas, pathlib
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/swing_classifier_trainer.py
- **Lines**: 975
- **Purpose**: Swing/General XGBClassifier + LGBMClassifier training pipeline.
- **Classes**: None
- **Functions**: _get_feature_names, _compute_all_features, _calculate_binary_target, _subsample_strided, _optuna_optimize_xgb_classifier, _optuna_optimize_lgbm_classifier, _walk_forward_cv_classifier, _prepare_training_data, _save_to_db, train_swing_classifier_model
- **Key imports**: aiosqlite, asyncio, concurrent.futures, config, data.alpaca_provider, data.options_data_fetcher, data.vix_provider, datetime
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/ml/tft_predictor.py
- **Lines**: 502
- **Purpose**: TFT ModelPredictor implementation.
- **Classes**: TFTPredictor
- **Functions**: __init__, load, save, predict, predict_batch, get_feature_names, get_feature_importance, _build_inference_df, _run_tft_inference, _extract_variable_importance
- **Key imports**: joblib, json, logging, ml.predictor, numpy, pandas, pathlib, pytorch_forecasting
- **Side effects**: file_I/O, logging
- **Verdict**: PASS

### options-bot/ml/tft_trainer.py
- **Lines**: 1082
- **Purpose**: TFT (Temporal Fusion Transformer) training pipeline.
- **Classes**: EpochLogger
- **Functions**: _make_strided_loader, _make_epoch_logger, _get_feature_names, _compute_all_features, _prediction_horizon_to_bars, _build_sequence_df, _walk_forward_cv_tft, _build_timeseries_dataset, predict_dataset, _save_tft_model_to_db
- **Key imports**: aiosqlite, asyncio, concurrent.futures, config, data.alpaca_provider, data.options_data_fetcher, data.vix_provider, datetime
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/ml/trainer.py
- **Lines**: 812
- **Purpose**: XGBoost training pipeline.
- **Classes**: None
- **Functions**: _prediction_horizon_to_bars, _get_feature_names, _compute_all_features, _calculate_target, _optuna_optimize, _walk_forward_cv, train_model, _run_async, _save_to_db, objective
- **Key imports**: aiosqlite, asyncio, concurrent.futures, config, data.alpaca_provider, data.options_data_fetcher, data.vix_provider, datetime
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/ml/xgboost_predictor.py
- **Lines**: 92
- **Purpose**: XGBoost ModelPredictor implementation.
- **Classes**: XGBoostPredictor
- **Functions**: __init__, load, save, set_model, predict, predict_batch, get_feature_names, get_feature_importance
- **Key imports**: joblib, logging, ml.predictor, numpy, pandas, pathlib
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/feature_engineering/__init__.py
- **Lines**: 1
- **Purpose**: No module docstring
- **Classes**: None
- **Functions**: None
- **Key imports**: None
- **Side effects**: None
- **Verdict**: PASS

### options-bot/ml/feature_engineering/base_features.py
- **Lines**: 586
- **Purpose**: Base feature engineering — shared features across all profile types.
- **Classes**: None
- **Functions**: compute_stock_features, compute_options_features, compute_base_features, get_base_feature_names
- **Key imports**: config, data.greeks_calculator, logging, numpy, pandas, ta
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/feature_engineering/general_features.py
- **Lines**: 89
- **Purpose**: General-specific features — trend and longer-horizon indicators.
- **Classes**: None
- **Functions**: compute_general_features, get_general_feature_names
- **Key imports**: logging, numpy, pandas
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/feature_engineering/scalp_features.py
- **Lines**: 194
- **Purpose**: Scalp-specific features — intraday microstructure and momentum indicators.
- **Classes**: None
- **Functions**: compute_scalp_features, get_scalp_feature_names
- **Key imports**: logging, numpy, pandas
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/ml/feature_engineering/swing_features.py
- **Lines**: 98
- **Purpose**: Swing-specific features — mean-reversion indicators.
- **Classes**: None
- **Functions**: compute_swing_features, get_swing_feature_names
- **Key imports**: logging, numpy, pandas, ta
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/risk/__init__.py
- **Lines**: 1
- **Purpose**: No module docstring
- **Classes**: None
- **Functions**: None
- **Key imports**: None
- **Side effects**: None
- **Verdict**: PASS

### options-bot/risk/risk_manager.py
- **Lines**: 647
- **Purpose**: Risk manager — PDT tracking, position sizing, portfolio-level limits, trade logging.
- **Classes**: RiskManager
- **Functions**: __init__, _start_async_loop, _run_async, get_day_trade_count, check_pdt_limit, check_pdt, get_open_position_count, check_position_limits, _get_profile_open_count, check_portfolio_exposure
- **Key imports**: aiosqlite, asyncio, config, datetime, json, logging, pathlib, sys
- **Side effects**: DB, file_I/O, logging
- **Verdict**: PASS

### options-bot/scripts/audit_verify.py
- **Lines**: 280
- **Purpose**: Audit verification script — VERIFY ONLY, NO FIXES.
- **Classes**: None
- **Functions**: check, section
- **Key imports**: importlib.util, ml.feature_engineering.base_features, pathlib, sys
- **Side effects**: None
- **Verdict**: PASS

### options-bot/scripts/backtest.py
- **Lines**: 289
- **Purpose**: Backtest runner for options-bot strategies.
- **Classes**: None
- **Functions**: _setup_logging, run_backtest, main
- **Key imports**: argparse, config, datetime, logging, lumibot.backtesting, os, pathlib, strategies.general_strategy
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/scripts/diagnose_strategy.py
- **Lines**: 77
- **Purpose**: Quick diagnostic to test the strategy's entry logic without Lumibot.
- **Classes**: None
- **Functions**: None
- **Key imports**: config, data.alpaca_provider, datetime, logging, math, ml.feature_engineering.base_features, ml.feature_engineering.swing_features, ml.xgboost_predictor
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/scripts/startup_check.py
- **Lines**: 332
- **Purpose**: Pre-flight startup check for options-bot.
- **Classes**: None
- **Functions**: check, section
- **Key imports**: alpaca.trading.client, config, importlib, os, pathlib, requests, shutil, sqlite3
- **Side effects**: DB, network
- **Verdict**: PASS

### options-bot/scripts/test_features.py
- **Lines**: 241
- **Purpose**: Test script for feature engineering.
- **Classes**: None
- **Functions**: test_stock_features, test_swing_features, test_general_features, test_full_feature_count, main
- **Key imports**: data.alpaca_provider, datetime, logging, ml.feature_engineering.base_features, ml.feature_engineering.general_features, ml.feature_engineering.swing_features, numpy, pandas
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/scripts/test_providers.py
- **Lines**: 180
- **Purpose**: Test script for data providers.
- **Classes**: None
- **Functions**: test_alpaca_provider, test_theta_provider, main
- **Key imports**: data.alpaca_provider, data.theta_provider, datetime, logging, pathlib, sys
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/scripts/train_model.py
- **Lines**: 116
- **Purpose**: Standalone model training script.
- **Classes**: None
- **Functions**: get_profile_config, main, _load
- **Key imports**: aiosqlite, argparse, asyncio, config, json, logging, ml.trainer, pathlib
- **Side effects**: DB, logging
- **Verdict**: PASS

### options-bot/scripts/validate_data.py
- **Lines**: 677
- **Purpose**: Data Validation Script — Tests all data source connections.
- **Classes**: None
- **Functions**: record, test_alpaca_connection, test_alpaca_stock_bars, test_alpaca_options, test_theta_connection, test_theta_historical_options, test_theta_greeks, print_summary, main
- **Key imports**: alpaca.data.historical, alpaca.data.requests, alpaca.data.timeframe, alpaca.trading.client, alpaca.trading.requests, config, csv, datetime
- **Side effects**: network, logging
- **Verdict**: PASS

### options-bot/scripts/validate_model.py
- **Lines**: 262
- **Purpose**: Validate a trained model's feature completeness and usage.
- **Classes**: None
- **Functions**: get_expected_features, validate_xgboost, validate_tft, validate_ensemble, _validate_features, validate_all_from_db, _query
- **Key imports**: aiosqlite, asyncio, config, joblib, json, ml.feature_engineering.base_features, ml.feature_engineering.general_features, ml.feature_engineering.scalp_features
- **Side effects**: DB, file_I/O
- **Verdict**: PASS

### options-bot/scripts/walk_forward_backtest.py
- **Lines**: 325
- **Purpose**: Walk-forward backtest orchestrator.
- **Classes**: None
- **Functions**: run_walk_forward, _train_window, _backtest_window, _print_summary, _save_results_csv, main
- **Key imports**: argparse, config, csv, datetime, logging, math, ml.trainer, os
- **Side effects**: file_I/O, logging
- **Verdict**: PASS

### options-bot/strategies/__init__.py
- **Lines**: 1
- **Purpose**: No module docstring
- **Classes**: None
- **Functions**: None
- **Key imports**: None
- **Side effects**: None
- **Verdict**: PASS

### options-bot/strategies/base_strategy.py
- **Lines**: 2201
- **Purpose**: Base strategy class with shared logic for all profile types.
- **Classes**: BaseOptionsStrategy
- **Functions**: send_update_to_cloud, _normalize_sleeptime, initialize, _get_classifier_avg_move, _detect_model_type, on_trading_iteration, _export_circuit_state, _check_exits, _get_latest_features_for_override, _execute_exit
- **Key imports**: config, data.alpaca_provider, data.earnings_calendar, data.options_data_fetcher, data.vix_provider, datetime, json, logging
- **Side effects**: DB, file_I/O, logging
- **Verdict**: PASS

### options-bot/strategies/general_strategy.py
- **Lines**: 31
- **Purpose**: General trading strategy.
- **Classes**: GeneralStrategy
- **Functions**: None
- **Key imports**: logging, strategies.base_strategy
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/strategies/scalp_strategy.py
- **Lines**: 40
- **Purpose**: Scalp trading strategy — 0DTE options on SPY.
- **Classes**: ScalpStrategy
- **Functions**: None
- **Key imports**: logging, strategies.base_strategy
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/strategies/swing_strategy.py
- **Lines**: 30
- **Purpose**: Swing trading strategy.
- **Classes**: SwingStrategy
- **Functions**: None
- **Key imports**: logging, strategies.base_strategy
- **Side effects**: logging
- **Verdict**: PASS

### options-bot/utils/__init__.py
- **Lines**: 1
- **Purpose**: No module docstring
- **Classes**: None
- **Functions**: None
- **Key imports**: None
- **Side effects**: None
- **Verdict**: PASS

### options-bot/utils/alerter.py
- **Lines**: 108
- **Purpose**: Lightweight alert system for critical trading events.
- **Classes**: None
- **Functions**: send_alert, _send
- **Key imports**: config, json, logging, pathlib, sys, threading, time, typing
- **Side effects**: file_I/O, logging
- **Verdict**: PASS

### options-bot/utils/circuit_breaker.py
- **Lines**: 151
- **Purpose**: Circuit breaker pattern for external service calls.
- **Classes**: CircuitState, CircuitBreaker
- **Functions**: exponential_backoff, __init__, state, can_execute, record_success, record_failure, get_stats
- **Key imports**: enum, logging, random, threading, time
- **Side effects**: logging
- **Verdict**: PASS

# 03 — File-by-File Audit: Frontend

**Audit date**: 2026-03-11
**Auditor**: Claude Opus 4.6
**Scope**: Every `.ts`, `.tsx`, `.js`, `.jsx`, `.css`, `.html` file under `ui/` excluding `node_modules/` and `dist/`

---

## File Count

**Total frontend source files: 20** (excluding `node_modules/` and `dist/` build artifacts)

| Category | Count | Lines |
|----------|-------|-------|
| Config files (.js, .ts) | 4 | 85 |
| Entry point (.html, .tsx, .css) | 3 | 54 |
| Types (.ts) | 1 | 271 |
| API client (.ts) | 1 | 159 |
| Components (.tsx) | 7 | 549 |
| Pages (.tsx) | 6 | 3,947 |
| App root (.tsx) | 1 | 47 |
| **Total** | **20** | **5,112** |

---

## File-by-File Audit Entries

---

### ui/index.html
- **Lines**: 13
- **Purpose**: Root HTML entry point for the Vite SPA. Contains the `#root` div and loads `main.tsx`.
- **Key symbols**: `#root` div
- **Imports**: `/src/main.tsx` via script module
- **Exports**: N/A
- **API calls**: None
- **State**: N/A
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/eslint.config.js
- **Lines**: 23
- **Purpose**: ESLint flat config for the frontend. Configures TypeScript, React hooks, and React Refresh rules.
- **Key symbols**: `defineConfig`, `globalIgnores`
- **Imports**: `@eslint/js`, `globals`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `typescript-eslint`, `eslint/config`
- **Exports**: Default config array
- **API calls**: None
- **State**: N/A
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/postcss.config.js
- **Lines**: 6
- **Purpose**: PostCSS configuration for Tailwind CSS and Autoprefixer.
- **Key symbols**: `plugins` object
- **Imports**: None (declarative config)
- **Exports**: Default config object
- **API calls**: None
- **State**: N/A
- **Bugs found**: BUG — The plugin format uses `tailwindcss: {}` and `autoprefixer: {}` as object keys in `plugins`. This is the newer PostCSS config format which requires the plugins to be resolvable by name. This works with newer versions of PostCSS. However, the key is a string name, not an import — it depends on PostCSS resolving `tailwindcss` as a package name. Since the project appears to work (`dist/` exists), this is functional but worth noting as a fragile pattern.
- **Verdict**: PASS (functional but fragile plugin resolution)

---

### ui/tailwind.config.js
- **Lines**: 41
- **Purpose**: Tailwind CSS configuration defining the project's dark terminal-style design system — custom colors, fonts, and font sizes.
- **Key symbols**: `colors` (base, surface, panel, border, muted, text, gold, profit, loss, active, created, training, ready, paused, error), `fontFamily` (sans, mono), `fontSize` (2xs)
- **Imports**: None
- **Exports**: Default Tailwind config
- **API calls**: None
- **State**: N/A
- **Bugs found**: None. Color names map cleanly to the profile status values used in `StatusBadge.tsx`.
- **Verdict**: PASS

---

### ui/vite.config.ts
- **Lines**: 15
- **Purpose**: Vite build config. Sets dev server to port 3000 and proxies `/api` requests to the backend at `localhost:8000`.
- **Key symbols**: `defineConfig`, `react` plugin, `server.proxy`
- **Imports**: `vite`, `@vitejs/plugin-react`
- **Exports**: Default Vite config
- **API calls**: None (configures proxy)
- **State**: N/A
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/src/main.tsx
- **Lines**: 10
- **Purpose**: React entry point. Mounts `<App>` into `#root` with StrictMode.
- **Key symbols**: `ReactDOM.createRoot`, `React.StrictMode`
- **Imports**: `react`, `react-dom/client`, `./App`, `./index.css`
- **Exports**: None (side-effect only)
- **API calls**: None
- **State**: N/A
- **Bugs found**: None. Uses non-null assertion on `getElementById('root')!` which is safe given the HTML always has `#root`.
- **Verdict**: PASS

---

### ui/src/index.css
- **Lines**: 31
- **Purpose**: Global CSS. Imports Google Fonts (DM Sans, IBM Plex Mono), applies Tailwind directives, sets base body styles, defines `.num` utility class for tabular numbers, and custom scrollbar styling.
- **Key symbols**: `.num` class, `@tailwind base/components/utilities`, `@layer base`, `@layer components`
- **Imports**: Google Fonts via `@import url()`
- **Exports**: N/A
- **API calls**: None
- **State**: N/A
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/src/App.tsx
- **Lines**: 47
- **Purpose**: Root application component. Sets up React Router (BrowserRouter) and React Query (QueryClientProvider) with a 10-second stale time. Defines all routes.
- **Key symbols**: `App` (default export), `queryClient`
- **Imports**: `react-router-dom` (BrowserRouter, Routes, Route, Link), `@tanstack/react-query` (QueryClient, QueryClientProvider), Layout, Dashboard, Profiles, ProfileDetail, Trades, SignalLogs, System
- **Exports**: `App` (default)
- **API calls**: None
- **State**: None
- **Bugs found**: `Link` is imported but only used inside the catch-all 404 route's inline JSX. Not a bug, just a minor import that could be inlined. No actual bugs.
- **Verdict**: PASS

---

### ui/src/api/client.ts
- **Lines**: 159
- **Purpose**: Typed API client wrapping `fetch()` for all backend endpoints. Groups endpoints by domain: profiles, models, trades, system, backtest, trading, signals.
- **Key symbols**: `api` object (named export), `request<T>()` helper, `BASE` constant
- **Imports**: All type interfaces from `../types/api`
- **Exports**: `api` (named)
- **API calls**: All of them. This is the single API layer.
  - `GET /api/profiles`, `GET /api/profiles/:id`, `POST /api/profiles`, `PUT /api/profiles/:id`, `DELETE /api/profiles/:id`, `POST /api/profiles/:id/activate`, `POST /api/profiles/:id/pause`
  - `POST /api/models/:id/train`, `POST /api/models/:id/retrain`, `GET /api/models/:id/status`, `GET /api/models/:id/logs`, `DELETE /api/models/:id/logs`, `GET /api/models/:id/importance`
  - `GET /api/trades`, `GET /api/trades/active`, `GET /api/trades/stats`, `GET /api/trades/export`
  - `GET /api/system/health`, `GET /api/system/status`, `GET /api/system/pdt`, `GET /api/system/errors`, `DELETE /api/system/errors`, `GET /api/system/model-health`, `GET /api/system/training-queue`
  - `POST /api/backtest/:id`, `GET /api/backtest/:id/results`
  - `GET /api/trading/status`, `POST /api/trading/start`, `POST /api/trading/stop`, `POST /api/trading/restart`, `GET /api/trading/startable-profiles`
  - `GET /api/signals/:id`
- **State**: N/A
- **Bugs found**:
  1. **BUG (minor)**: `request()` sets `Content-Type: application/json` for all non-GET requests, even DELETE which has no body. Not harmful (servers ignore it), but technically unnecessary.
  2. The `exportUrl` methods return raw URL strings (not fetch calls) — used to trigger file downloads via anchor element click. This is correct.
- **Verdict**: PASS

---

### ui/src/types/api.ts
- **Lines**: 271
- **Purpose**: TypeScript type definitions matching `backend/schemas.py`. Defines all API response interfaces used throughout the frontend.
- **Key symbols**: `Profile`, `ProfileCreate`, `ProfileUpdate`, `ModelSummary`, `TrainingStatus`, `ModelMetrics`, `FeatureImportanceResponse`, `TrainingLogEntry`, `Trade`, `TradeStats`, `CircuitBreakerState`, `SystemStatus`, `HealthCheck`, `PDTStatus`, `ErrorLogEntry`, `TrainingQueueStatus`, `BacktestRequest`, `BacktestResult`, `TradingProcessInfo`, `TradingStatusResponse`, `TradingStartResponse`, `TradingStopResponse`, `StartableProfile`, `ModelHealthEntry`, `ModelHealthResponse`, `SignalLogEntry`
- **Imports**: None
- **Exports**: All interfaces (named exports)
- **API calls**: None
- **State**: N/A
- **Bugs found**:
  1. `ModelMetrics` interface is defined but never imported or used anywhere in the frontend. Dead type.
  2. `CircuitBreakerState` is used via `SystemStatus.circuit_breaker_states` in `System.tsx` — confirmed used.
- **Verdict**: PASS (one dead type `ModelMetrics` is harmless)

---

### ui/src/components/ConnIndicator.tsx
- **Lines**: 16
- **Purpose**: Small status indicator component showing a colored dot + label + "connected"/"offline" text.
- **Key symbols**: `ConnIndicator` (named export), `Props` interface
- **Imports**: None (pure component)
- **Exports**: `ConnIndicator`
- **API calls**: None
- **State**: None
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/src/components/Layout.tsx
- **Lines**: 85
- **Purpose**: Application shell with sidebar navigation and main content area. Sidebar shows logo, nav links, health status dot, and API host footer. Uses `<Outlet>` for routed content.
- **Key symbols**: `Layout` (named export), `NAV` array
- **Imports**: `react-router-dom` (NavLink, Outlet), `lucide-react` (LayoutDashboard, Users, History, Search, Activity, ChevronRight), `@tanstack/react-query` (useQuery), `api` from client
- **Exports**: `Layout`
- **API calls**: `api.system.health` (polled every 30s for the sidebar status dot)
- **State**: None (uses React Query)
- **Bugs found**: None. The `end` prop on the root NavLink (`to="/"`) correctly prevents it from matching all routes.
- **Verdict**: PASS

---

### ui/src/components/PageHeader.tsx
- **Lines**: 17
- **Purpose**: Reusable page header component with title, optional subtitle, and optional action buttons slot.
- **Key symbols**: `PageHeader` (named export), `Props` interface
- **Imports**: None
- **Exports**: `PageHeader`
- **API calls**: None
- **State**: None
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/src/components/PnlCell.tsx
- **Lines**: 15
- **Purpose**: Renders a P&L value with green/red coloring and +/- prefix. Returns dash for null values.
- **Key symbols**: `PnlCell` (named export), `Props` interface
- **Imports**: None
- **Exports**: `PnlCell`
- **API calls**: None
- **State**: None
- **Bugs found**: None. Correctly uses `== null` to catch both null and undefined.
- **Verdict**: PASS

---

### ui/src/components/ProfileForm.tsx
- **Lines**: 386
- **Purpose**: Modal form for creating or editing trading profiles. Includes preset selection (swing/general/scalp), symbol management with add/remove, and advanced risk parameter sliders. Auto-switches to SPY for scalp preset.
- **Key symbols**: `ProfileForm` (named export), `ConfigSlider` (internal), `PRESETS`, `PRESET_DESCRIPTIONS`
- **Imports**: `react` (useState), `@tanstack/react-query` (useMutation, useQueryClient), `lucide-react` (X, Plus), `api`, `Spinner`, `Profile` type
- **Exports**: `ProfileForm`
- **API calls**: `api.profiles.create()`, `api.profiles.update()`
- **State**: `name`, `preset`, `symbols`, `symbolInput`, `error`, `maxPositionPct`, `maxContracts`, `maxConcurrent`, `maxDailyTrades`, `maxDailyLossPct`, `minConfidence`, `showAdvanced`
- **Bugs found**:
  1. **BUG (minor)**: The `isDirty` check does not include `minConfidence` for scalp presets. If a user only changes `minConfidence`, the dirty check returns false and clicking the backdrop will close without a warning. The `minConfidence` state is only sent to the backend when `preset === 'scalp'`, but the `isDirty` function never checks if it changed.
  2. **BUG (minor)**: The `minConfidence` slider has `min={0.50}` and `max={0.90}`, but the actual backend scalp profile has `min_confidence: 0.10`. The UI constrains the user to 0.50-0.90 when the real system supports 0.10. This may be intentional as a safety guard, but is inconsistent with the actual config.
- **Verdict**: PASS (minor issues, no data loss risk)

---

### ui/src/components/Spinner.tsx
- **Lines**: 6
- **Purpose**: Animated loading spinner component with three sizes (sm/md/lg).
- **Key symbols**: `Spinner` (named export)
- **Imports**: None
- **Exports**: `Spinner`
- **API calls**: None
- **State**: None
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/src/components/StatusBadge.tsx
- **Lines**: 24
- **Purpose**: Renders a colored badge for profile/trade status values. Maps status strings to Tailwind color classes.
- **Key symbols**: `StatusBadge` (named export), `STATUS_STYLES` lookup
- **Imports**: None
- **Exports**: `StatusBadge`
- **API calls**: None
- **State**: None
- **Bugs found**: None. Has a fallback style for unknown status values, which is good defensive coding.
- **Verdict**: PASS

---

### ui/src/pages/Dashboard.tsx
- **Lines**: 588
- **Purpose**: Main dashboard page showing portfolio summary (5 stat cards), PDT warning banner, model health banner, profile cards grid, and system status panel. Auto-refreshes every 30 seconds.
- **Key symbols**: `Dashboard` (named export), `StatCard`, `ProfileCard`, `StatusPanel` (internal components), `fmtDollars`, `fmtUptime`, `MAX_TOTAL_POSITIONS`
- **Imports**: `@tanstack/react-query`, `react-router-dom`, `lucide-react` (many icons), `api`, `StatusBadge`, `ConnIndicator`, `PnlCell`, `Spinner`, `PageHeader`, types (`Profile`, `SystemStatus`, `PDTStatus`, `ModelHealthResponse`, `TrainingQueueStatus`)
- **Exports**: `Dashboard`
- **API calls**: `api.profiles.list`, `api.system.status`, `api.system.pdt`, `api.trades.stats`, `api.system.modelHealth`, `api.system.trainingQueue`, `api.profiles.activate`, `api.profiles.pause`, `api.system.clearErrors`
- **State**: None (all via React Query)
- **Bugs found**:
  1. **BUG (hardcoded constant)**: `MAX_TOTAL_POSITIONS = 10` is hardcoded. Comment says "Must match MAX_TOTAL_POSITIONS in backend config.py". If the backend value changes, the frontend will show wrong limits. Should ideally come from the API.
  2. **BUG (minor)**: In `StatusPanel`, the timestamp parsing for `last_error_at` uses an inline IIFE with timezone detection. This same pattern is repeated in 4+ files. Should be a shared utility, but functionally correct.
  3. **Observation**: The model health banner hardcodes `52` as the accuracy threshold string: `below ${52}% threshold`. This works but reads oddly — should just be the literal string "52%".
- **Verdict**: PASS (hardcoded constant is a sync risk, not a runtime bug)

---

### ui/src/pages/Profiles.tsx
- **Lines**: 376
- **Purpose**: Profile list page with a table showing all profiles. Supports CRUD operations: create, edit, delete, activate, pause, and train. Has a delete confirmation dialog.
- **Key symbols**: `Profiles` (named export), `ProfileRow`, `DeleteDialog` (internal), state variables for modals and mutations
- **Imports**: `react` (useState), `react-router-dom` (useNavigate), `@tanstack/react-query`, `lucide-react`, `api`, `PageHeader`, `StatusBadge`, `Spinner`, `PnlCell`, `ProfileForm`, `Profile` type
- **Exports**: `Profiles`
- **API calls**: `api.profiles.list`, `api.profiles.activate`, `api.profiles.pause`, `api.models.train`, `api.profiles.delete`
- **State**: `showCreate`, `editProfile`, `deleteTarget`, `mutatingId`
- **Bugs found**:
  1. **BUG (minor)**: `paused` status uses `bg-training` color in the status legend (line 355), meaning paused and training show the same dot color. This is misleading — paused should be gray/muted, not gold.
  2. **BUG (minor)**: The `trainMutation` calls `api.models.train(id)` without specifying a model type, so it defaults to `'xgboost'`. For profiles where the default should be `xgb_classifier` (scalp), the user would need to go to ProfileDetail to pick the right type. Not a crash bug, but could lead to training the wrong model type from this page.
- **Verdict**: PASS (minor UX issues)

---

### ui/src/pages/ProfileDetail.tsx
- **Lines**: 1150
- **Purpose**: Detailed view of a single trading profile. Shows model health with multi-model tab switching, training controls (train/retrain with model type dropdown), trade performance stats, backtest panel, signal decision log, and trade history table. The largest file in the frontend.
- **Key symbols**: `ProfileDetail` (named export), `MetricTile`, `TrainingLogs`, `FeatureImportancePanel`, `SignalLogPanel` (internal components), `parseUTC`
- **Imports**: `react` (useState, useEffect, useRef), `react-router-dom` (useParams, useNavigate), `@tanstack/react-query`, `lucide-react` (many icons), types (`ModelSummary`, `ModelHealthEntry`, `ModelHealthResponse`), `api`, `StatusBadge`, `Spinner`, `PnlCell`, `ProfileForm`
- **Exports**: `ProfileDetail`
- **API calls**: `api.profiles.get`, `api.models.status`, `api.trades.list`, `api.trades.stats`, `api.models.importance`, `api.backtest.results`, `api.system.modelHealth`, `api.models.train`, `api.models.retrain`, `api.profiles.activate`, `api.profiles.pause`, `api.backtest.run`, `api.models.logs`, `api.models.clearLogs`, `api.signals.list`
- **State**: `showEdit`, `showLogs`, `trainModelType`, `showModelTypeMenu`, `trainError`, `showBacktest`, `backtestStart`, `backtestEnd`
- **Bugs found**:
  1. **BUG (code smell / duplication)**: The model display section (lines 561-848) has massive duplication. The "multi-tab" branch (lines 573-713) and the "single model" branch (lines 717-828) contain nearly identical MetricTile grids, model health status blocks, classifier metric displays, feature importance panels, etc. The file itself has a TODO comment: "Extract ModelDisplay component to reduce duplication" (line 560). This is ~250 lines of duplicated JSX.
  2. **BUG (minor)**: Import ordering is unusual — `parseUTC` is defined between two import blocks (line 14-17). The `Spinner`, `PnlCell`, and `ProfileForm` imports come after the `parseUTC` function definition. This works in JS/TS but is unconventional and could confuse linters.
  3. **BUG (minor)**: The `class_distribution` display (lines 680, 804) accesses keys `'down'`, `'neutral'`, `'up'` but the scalp classifier is binary (UP/DOWN only, no neutral class per MEMORY.md). The `neutral` key will show `?` for scalp models. Not a crash, but misleading display.
  4. **BUG (potential)**: `useEffect` for setting default `trainModelType` (line 337-343) has an eslint-disable comment suppressing the exhaustive-deps warning. The dependency array includes `trainModelType` which could cause unnecessary re-renders, but it has a guard `!validTypes.includes(trainModelType)` that prevents infinite loops.
- **Verdict**: PASS (significant duplication is a maintainability concern but not a runtime bug)

---

### ui/src/pages/Trades.tsx
- **Lines**: 485
- **Purpose**: Trade history page with full-featured data table. Supports client-side filtering (profile, symbol, status, direction, date range), client-side sorting on all columns, CSV export, and summary statistics row.
- **Key symbols**: `Trades` (named export), `SortField`, `SortDir`, `Filters` types, `FilterBar`, `SummaryRow`, `ColHeader`, `SortIcon` (internal components), `fmt`, `fmtDate`, `EMPTY_FILTERS`
- **Imports**: `react` (useState, useMemo), `@tanstack/react-query`, `lucide-react`, `api`, `PageHeader`, `StatusBadge`, `PnlCell`, `Spinner`, `Trade` type
- **Exports**: `Trades`
- **API calls**: `api.trades.list` (with profile_id filter, limit 500), `api.profiles.list` (for dropdown), `api.trades.exportUrl` (for CSV download)
- **State**: `filters`, `sortField`, `sortDir`
- **Bugs found**:
  1. **BUG (minor)**: The prediction column (line 450) checks `trade.entry_model_type` against a hardcoded list `['xgb_classifier', 'xgb_swing_classifier', 'lgbm_classifier']` to decide display format. If new classifier model types are added, this list must be manually updated.
  2. **BUG (minor)**: The `dateTo` filter comparison (line 281) appends `'T23:59:59.999Z'` to include the full end date. This is correct but assumes `entry_date` is an ISO string. If `entry_date` contains timezone info, the string comparison could behave unexpectedly, though in practice backend dates are ISO format.
  3. **BUG (minor)**: CSV export (lines 321-329) creates a temporary anchor element and clicks it. This works but does not handle errors — if the backend is down, the user gets no feedback (just a failed download).
- **Verdict**: PASS

---

### ui/src/pages/SignalLogs.tsx
- **Lines**: 509
- **Purpose**: Signal decision log page showing every trading iteration and why the bot traded or skipped. Features client-side filtering, sorting, summary stats, and CSV export. Auto-selects first profile when only one exists.
- **Key symbols**: `SignalLogs` (named export), `STEP_NAMES` mapping, `SortField`, `SortDir`, `Filters` types, `FilterBar`, `SummaryRow`, `ColHeader`, `SortIcon` (internal components), `fmt`, `fmtDatetime`, `EMPTY_FILTERS`
- **Imports**: `react` (useState, useMemo), `@tanstack/react-query`, `lucide-react`, `api`, `PageHeader`, `Spinner`, `SignalLogEntry` type
- **Exports**: `SignalLogs`
- **API calls**: `api.signals.list` (per profile, limit 500), `api.profiles.list` (for dropdown), `api.signals.exportUrl` (for CSV download)
- **State**: `filters`, `sortField`, `sortDir`
- **Bugs found**:
  1. **BUG (minor)**: When "All Profiles" is selected, the component fetches from every profile individually with `Promise.all` (line 281), merges results, sorts, and truncates to 500. This is O(N) network requests where N = number of profiles. For many profiles this could be slow. A dedicated backend endpoint for cross-profile signal logs would be better.
  2. **BUG (minor)**: The `STEP_NAMES` mapping uses string keys including fractional steps like `'8.7'`, `'9.5'`, `'9.7'`. The `step_stopped_at` field is typed as `number | null` in the API types. When `String(signal.step_stopped_at)` is used to look up in `STEP_NAMES`, floating point numbers should match their string keys correctly (e.g., `String(9.5) === '9.5'`), so this works.
  3. **BUG (minor)**: The classifier detection (line 206) checks `predictor_type` against `['ScalpPredictor', 'SwingClassifierPredictor']`. This is a hardcoded list that must be maintained if new predictor types are added.
- **Verdict**: PASS

---

### ui/src/pages/System.tsx
- **Lines**: 839
- **Purpose**: System status page. Displays connection cards (Backend, Alpaca, Theta Terminal), trading engine control panel (quick start, stop all, per-process controls), circuit breaker states, PDT tracking with progress bar, portfolio snapshot, runtime info, and error log with expandable entries.
- **Key symbols**: `System` (named export), `ConnectionCard`, `StatRow`, `ErrorRow`, `TradingProcessRow` (internal components), `fmtUptime`, `fmtDollars`, `fmtTimestamp`, `MAX_TOTAL_POSITIONS`
- **Imports**: `react` (useState), `@tanstack/react-query`, `lucide-react` (many icons), `api`, `PageHeader`, `Spinner`, types (`ErrorLogEntry`, `TradingProcessInfo`)
- **Exports**: `System`
- **API calls**: `api.system.health`, `api.system.status`, `api.system.pdt`, `api.system.errors`, `api.system.clearErrors`, `api.trading.status`, `api.trading.startableProfiles`, `api.trading.start`, `api.trading.stop`, `api.trading.restart`
- **State**: `errorLimit`, `showQuickStart`, `selectedProfiles`
- **Bugs found**:
  1. **BUG (hardcoded constant)**: `MAX_TOTAL_POSITIONS = 10` is duplicated here (same as Dashboard.tsx). Two places to update if backend changes.
  2. **BUG (minor)**: `ErrorRow` uses array index `i` as the React key (line 819): `key={i}`. If errors are added/removed between renders, this could cause incorrect component reuse. Should use a unique identifier (timestamp + message hash). However, error log entries lack a stable `id` field in the type definition.
  3. **BUG (minor)**: The `fmtUptime` function (line 24-32) uses `seconds % 60` for the seconds component, but `uptime_seconds` from the backend is a number that may have fractional parts. `Math.floor` should be applied to the seconds remainder. Currently `const s = seconds % 60` could display something like `2m 34.56789s`. The Dashboard version of `fmtUptime` does not have this issue because it only shows hours and minutes.
  4. **BUG (minor)**: Circuit breaker `alpaca_failure_count` from the `CircuitBreakerState` type is available but never displayed in the UI (line 546 reads it as `const alpacaFails` is not defined — only `thetaFails` is extracted and displayed). Actually looking more carefully: `alpaca_failure_count` is defined in the type but the code only extracts `thetaFails` (line 545). The Alpaca failure count is never shown.
- **Verdict**: PASS (minor issues, functional)

---

## Cross-Cutting Findings

### 1. Duplicated Constants
- `MAX_TOTAL_POSITIONS = 10` is hardcoded in both `Dashboard.tsx` (line 21) and `System.tsx` (line 18). Should be fetched from the backend or centralized in a constants file.

### 2. Duplicated Utility Functions
- `fmtDollars()` is defined in both `Dashboard.tsx` and `System.tsx` with identical implementations.
- `fmtUptime()` is defined in both `Dashboard.tsx` and `System.tsx` with slightly different implementations (Dashboard omits seconds).
- UTC timestamp parsing logic (`hasTimezone` regex check + append 'Z') is repeated in `Dashboard.tsx`, `ProfileDetail.tsx`, `Trades.tsx`, `SignalLogs.tsx`, and `System.tsx`.
- These should be extracted to a shared `utils.ts` file.

### 3. Hardcoded Classifier Type Lists
- Three separate files maintain hardcoded lists of classifier model types or predictor types:
  - `Trades.tsx` line 450: `['xgb_classifier', 'xgb_swing_classifier', 'lgbm_classifier']`
  - `SignalLogs.tsx` line 206: `['ScalpPredictor', 'SwingClassifierPredictor']`
  - `SignalLogs.tsx` line 459: same list
- These should be centralized.

### 4. Dead Type
- `ModelMetrics` in `api.ts` (line 60) is never imported or used anywhere.

### 5. ProfileDetail.tsx Duplication
- ~250 lines of duplicated model display JSX between the multi-tab and single-model branches. The file acknowledges this with a TODO comment.

### 6. No Error Boundaries
- No React error boundary components exist. A JS error in any component will crash the entire app. Should have at least a top-level error boundary.

### 7. No Loading/Error States for Mutations
- Most mutation error states are silently swallowed or only shown temporarily. For example, `activateMutation` and `pauseMutation` in Dashboard do not display errors to the user.

---

## Summary

| Verdict | Count |
|---------|-------|
| PASS | 20 |
| FAIL | 0 |

**Total bugs found**: 18 (all minor/medium severity)

- **0 critical bugs** (no data loss, no crashes, no security issues)
- **2 medium bugs** (hardcoded `MAX_TOTAL_POSITIONS` duplicated in 2 files; ProfileDetail.tsx ~250 lines of duplicated JSX)
- **16 minor bugs** (hardcoded type lists, missing error displays, dead code, code smells)

The frontend is well-structured, uses modern React patterns (React Query for server state, proper mutation handling, clean component composition), and has a consistent design system. The main maintenance concerns are duplicated utilities and the large `ProfileDetail.tsx` file.

# 03 — FILE-BY-FILE AUDIT (Other Files)

## Summary

**Total non-source files**: 255
**Scope**: Every file in repo except .py (covered in Python audit) and ui/src/ (covered in frontend audit)
**Excludes**: .git/, node_modules/, __pycache__/, AUDIT_PACKAGE/

---

### .gitignore
- **Size**: 692 bytes
- **Type**: other
- **Purpose**: Git ignore patterns
- **Contains secrets**: NO
- **Verdict**: PASS

### CLAUDE.md
- **Size**: 302 bytes
- **Type**: documentation
- **Purpose**: Claude Code project instructions
- **Contains secrets**: NO
- **Verdict**: PASS

### .claude/settings.local.json
- **Size**: 64 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### .vscode/settings.json
- **Size**: 42 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### docs/AUDIT_FAILURES_AND_RULES.md
- **Size**: 17,718 bytes
- **Type**: documentation
- **Purpose**: Documentation
- **Contains secrets**: NO
- **Verdict**: PASS

### docs/CLAUDE_ZERO_OMISSION_TERMINATION_GRADE_AUDIT_DIRECTIVE.md
- **Size**: 13,529 bytes
- **Type**: documentation
- **Purpose**: Documentation
- **Contains secrets**: NO
- **Verdict**: PASS

### docs/FORMAL_REJECTION_MEMO_AUDIT_PACKAGE.md
- **Size**: 10,893 bytes
- **Type**: documentation
- **Purpose**: Documentation
- **Contains secrets**: NO
- **Verdict**: PASS

### docs/PROJECT_ARCHITECTURE.md
- **Size**: 65,867 bytes
- **Type**: documentation
- **Purpose**: Documentation
- **Contains secrets**: NO
- **Verdict**: PASS

### docs/UPDATED_PROMPT.md
- **Size**: 24,440 bytes
- **Type**: documentation
- **Purpose**: Documentation
- **Contains secrets**: NO
- **Verdict**: PASS

### docs/signal-logs-2026-03-09 (1).csv
- **Size**: 24,281 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### docs/signal-logs-2026-03-09.csv
- **Size**: 129,763 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/.env
- **Size**: 580 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/.env.example
- **Size**: 1,475 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/requirements.txt
- **Size**: 552 bytes
- **Type**: documentation
- **Purpose**: documentation file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/start_bot.bat
- **Size**: 163 bytes
- **Type**: script
- **Purpose**: Windows batch script
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=0-step=48.ckpt
- **Size**: 12,007,022 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=1-step=96.ckpt
- **Size**: 12,628,650 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=10-step=517.ckpt
- **Size**: 12,007,278 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=10-step=528.ckpt
- **Size**: 12,007,726 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=12-step=611.ckpt
- **Size**: 12,007,790 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=13-step=658.ckpt
- **Size**: 11,883,426 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=13-step=672.ckpt
- **Size**: 12,007,662 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=14-step=705-v1.ckpt
- **Size**: 12,007,726 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=14-step=705.ckpt
- **Size**: 12,007,790 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=14-step=720.ckpt
- **Size**: 11,883,426 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=16-step=816.ckpt
- **Size**: 12,007,662 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=17-step=864-v1.ckpt
- **Size**: 12,628,650 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=17-step=864.ckpt
- **Size**: 12,007,150 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=19-step=960.ckpt
- **Size**: 12,628,778 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=20-step=1008-v1.ckpt
- **Size**: 12,007,662 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=20-step=1008.ckpt
- **Size**: 12,007,150 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=22-step=1104.ckpt
- **Size**: 12,628,778 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=24-step=1200.ckpt
- **Size**: 12,007,150 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=4-step=5475.ckpt
- **Size**: 12,007,086 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=7-step=384.ckpt
- **Size**: 11,883,426 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=8-step=432.ckpt
- **Size**: 12,007,662 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=9-step=470.ckpt
- **Size**: 12,007,790 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=9-step=480-v1.ckpt
- **Size**: 12,007,726 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=9-step=480-v2.ckpt
- **Size**: 12,007,662 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/checkpoints/epoch=9-step=480.ckpt
- **Size**: 12,007,662 bytes
- **Type**: model
- **Purpose**: model file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/data/options_bot.db
- **Size**: 0 bytes
- **Type**: data
- **Purpose**: SQLite database
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/data/cache/SPY_options_daily.parquet
- **Size**: 179,205 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/data/cache/SPY_options_daily_dte0-0.parquet
- **Size**: 182,114 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/data/cache/TSLA_options_daily.parquet
- **Size**: 185,446 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/data/cache/TSLA_options_daily_dte7-45.parquet
- **Size**: 185,548 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/db/.gitkeep
- **Size**: 0 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/db/options_bot.db
- **Size**: 809,410,560 bytes
- **Type**: data
- **Purpose**: SQLite database
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/docs/AUDIT_FINDINGS.md
- **Size**: 18,194 bytes
- **Type**: documentation
- **Purpose**: Documentation
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/docs/DEPLOYMENT.md
- **Size**: 6,182 bytes
- **Type**: documentation
- **Purpose**: Documentation
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/docs/OPERATIONS.md
- **Size**: 3,930 bytes
- **Type**: documentation
- **Purpose**: Documentation
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/.gitkeep
- **Size**: 0 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_15-16_p5Rvy9_indicators.csv
- **Size**: 86 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_15-16_p5Rvy9_indicators.html
- **Size**: 4,850,953 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_15-16_p5Rvy9_indicators.parquet
- **Size**: 5,832 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_15-16_p5Rvy9_settings.json
- **Size**: 2,447 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_15-16_p5Rvy9_tearsheet.csv
- **Size**: 1,438 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_15-16_p5Rvy9_trade_events.csv
- **Size**: 621 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_15-16_p5Rvy9_trade_events.parquet
- **Size**: 11,921 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_15-16_p5Rvy9_trades.csv
- **Size**: 621 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_15-16_p5Rvy9_trades.parquet
- **Size**: 11,921 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_18-38_rO6kJI_indicators.csv
- **Size**: 86 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_18-38_rO6kJI_indicators.html
- **Size**: 4,850,953 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_18-38_rO6kJI_indicators.parquet
- **Size**: 5,832 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_18-38_rO6kJI_settings.json
- **Size**: 2,493 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_18-38_rO6kJI_tearsheet.csv
- **Size**: 1,500 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_18-38_rO6kJI_trade_events.csv
- **Size**: 10,953 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_18-38_rO6kJI_trade_events.parquet
- **Size**: 12,871 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_18-38_rO6kJI_trades.csv
- **Size**: 10,953 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_SPY_scalp_2026-03-11_18-38_rO6kJI_trades.parquet
- **Size**: 12,871 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-23_18-25_vebC5d_indicators.csv
- **Size**: 86 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-23_18-25_vebC5d_indicators.html
- **Size**: 4,850,954 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-23_18-25_vebC5d_indicators.parquet
- **Size**: 5,832 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-23_18-25_vebC5d_settings.json
- **Size**: 2,151 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-23_18-25_vebC5d_trade_events.csv
- **Size**: 221 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-23_18-25_vebC5d_trade_events.parquet
- **Size**: 9,336 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-23_18-25_vebC5d_trades.csv
- **Size**: 221 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-23_18-25_vebC5d_trades.parquet
- **Size**: 9,336 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_12-51_kSm03I_indicators.csv
- **Size**: 86 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_12-51_kSm03I_indicators.html
- **Size**: 4,850,954 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_12-51_kSm03I_indicators.parquet
- **Size**: 5,832 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_12-51_kSm03I_settings.json
- **Size**: 2,218 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_12-51_kSm03I_tearsheet.csv
- **Size**: 1,510 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_12-51_kSm03I_trade_events.csv
- **Size**: 3,294 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_12-51_kSm03I_trade_events.parquet
- **Size**: 12,209 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_12-51_kSm03I_trades.csv
- **Size**: 3,294 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_12-51_kSm03I_trades.parquet
- **Size**: 12,209 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_16-32_xwpGbP_indicators.csv
- **Size**: 86 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_16-32_xwpGbP_indicators.html
- **Size**: 4,850,954 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_16-32_xwpGbP_indicators.parquet
- **Size**: 5,832 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_16-32_xwpGbP_settings.json
- **Size**: 2,220 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_16-32_xwpGbP_tearsheet.csv
- **Size**: 1,521 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_16-32_xwpGbP_trade_events.csv
- **Size**: 20,873 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_16-32_xwpGbP_trade_events.parquet
- **Size**: 13,810 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_16-32_xwpGbP_trades.csv
- **Size**: 20,873 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/BT_TSLA_swing_2026-02-24_16-32_xwpGbP_trades.parquet
- **Size**: 13,810 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_SPY_scalp_20260311_151635.csv
- **Size**: 1,204 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_SPY_scalp_20260311_151635.html
- **Size**: 453,502 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_SPY_scalp_20260311_151635.parquet
- **Size**: 4,302 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_SPY_scalp_20260311_183811.csv
- **Size**: 16,042 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_SPY_scalp_20260311_183811.html
- **Size**: 475,370 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_SPY_scalp_20260311_183811.parquet
- **Size**: 6,066 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260223_182520.csv
- **Size**: 49,895 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260223_182520.html
- **Size**: 320 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260223_182520.parquet
- **Size**: 10,320 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260224_111348.csv
- **Size**: 145 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260224_111348.parquet
- **Size**: 3,974 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260224_125109.csv
- **Size**: 61,498 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260224_125109.html
- **Size**: 503,677 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260224_125109.parquet
- **Size**: 11,393 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260224_163211.csv
- **Size**: 97,567 bytes
- **Type**: data
- **Purpose**: Data export or backtest output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260224_163211.html
- **Size**: 543,819 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_TSLA_swing_20260224_163211.parquet
- **Size**: 14,938 bytes
- **Type**: data
- **Purpose**: Options data cache
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260224_100110.log
- **Size**: 20,019 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260224_105719.log
- **Size**: 155 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260224_111345.log
- **Size**: 27,510 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260224_112252.log
- **Size**: 65,677 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260224_115303.log
- **Size**: 155 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260224_122407.log
- **Size**: 71,323 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260224_125059.log
- **Size**: 1,220,668 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260224_151616.log
- **Size**: 108,596 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260224_160726.log
- **Size**: 36,663 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260224_163207.log
- **Size**: 1,570,009 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260227_221929.log
- **Size**: 155 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260311_151602.log
- **Size**: 22,003 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/backtest_debug_20260311_151628.log
- **Size**: 722,055 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/circuit_state_ac3ff5ea-f8a8-4046-af54-d52efe8ec7f4.json
- **Size**: 247 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/circuit_state_ad48bf20-1913-4f40-b028-0580c9f48168.json
- **Size**: 247 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/circuit_state_backtest.json
- **Size**: 219 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_032738.log
- **Size**: 12,140 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_033257.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_033422.log
- **Size**: 424,996 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_033516.log
- **Size**: 116,546 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_035744.log
- **Size**: 483,465 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_084213.log
- **Size**: 73,923 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_085620.log
- **Size**: 230,704 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_092728.log
- **Size**: 690,182 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_094912.log
- **Size**: 1,443,785 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_103847.log
- **Size**: 3,202,604 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_142609.log
- **Size**: 3,098,639 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_180341.log
- **Size**: 281,774 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_190128.log
- **Size**: 3,050,562 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_221932.log
- **Size**: 141,528 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260227_222036.log
- **Size**: 76,940,717 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260228_094706.log
- **Size**: 16,674,604 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260228_124112.log
- **Size**: 3,836,566 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260228_132645.log
- **Size**: 41,370,926 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260301_201228.log
- **Size**: 13,715 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260301_201720.log
- **Size**: 79,002,064 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260302_111748.log
- **Size**: 80,290 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260302_121321.log
- **Size**: 477,995 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260302_125345.log
- **Size**: 2,176,965 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260302_221819.log
- **Size**: 4,428 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260302_221852.log
- **Size**: 4,604 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_091951.log
- **Size**: 916 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_093042.log
- **Size**: 915 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_115416.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_115458.log
- **Size**: 634 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_121738.log
- **Size**: 916 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_131621.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_131702.log
- **Size**: 634 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_135646.log
- **Size**: 915 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_153033.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_171702.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_171711.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_171721.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_183026.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_184414.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_184441.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_184453.log
- **Size**: 916 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_195015.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_195512.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260303_200106.log
- **Size**: 135 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_022015.log
- **Size**: 6,476,599 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_022015.log.1
- **Size**: 10,485,549 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_022015.log.2
- **Size**: 10,485,547 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_022015.log.3
- **Size**: 10,485,681 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_111344.log
- **Size**: 3,548,514 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_122837.log
- **Size**: 280,140 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_122859.log
- **Size**: 171,373 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_123609.log
- **Size**: 19,715 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_124427.log
- **Size**: 159,501 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_125932.log
- **Size**: 203,260 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_130644.log
- **Size**: 233,651 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_130735.log
- **Size**: 347,739 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_133631.log
- **Size**: 168,157 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_133658.log
- **Size**: 122,893 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_135424.log
- **Size**: 129,461 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_135448.log
- **Size**: 150,103 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_142159.log
- **Size**: 148,709 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_142239.log
- **Size**: 206,014 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_154431.log
- **Size**: 2,059,895 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_154758.log
- **Size**: 529,510 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_212206.log
- **Size**: 2,609,417 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_212206.log.1
- **Size**: 10,485,708 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_212206.log.2
- **Size**: 10,485,709 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_212206.log.3
- **Size**: 10,485,748 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_212206.log.4
- **Size**: 10,485,643 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260304_212206.log.5
- **Size**: 10,485,742 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_095027.log
- **Size**: 358,723 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_105516.log
- **Size**: 476,964 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_110230.log
- **Size**: 399,201 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_113337.log
- **Size**: 418,087 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_113429.log
- **Size**: 144,688 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_115522.log
- **Size**: 375,206 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_115706.log
- **Size**: 3,519,382 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_133756.log
- **Size**: 221,630 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_151049.log
- **Size**: 750,821 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_160326.log
- **Size**: 129,594 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_161215.log
- **Size**: 48,139 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260305_164107.log
- **Size**: 49,533 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260306_091720.log
- **Size**: 157,529 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260306_091751.log
- **Size**: 83,927 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260306_092401.log
- **Size**: 183,040 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260306_093411.log
- **Size**: 518,958 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260306_100231.log
- **Size**: 522,625 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260306_100244.log
- **Size**: 617,891 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260309_094722.log
- **Size**: 235,965 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260309_094744.log
- **Size**: 1,727,689 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260309_114220.log
- **Size**: 403,425 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260309_114452.log
- **Size**: 7,311,729 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260309_114452.log.2
- **Size**: 10,487,062 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260309_114452.log.5
- **Size**: 10,486,387 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260310_093450.log
- **Size**: 96,289 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260310_093503.log
- **Size**: 1,284,337 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260310_105137.log
- **Size**: 242,590 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260310_105152.log
- **Size**: 2,942,606 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260310_105152.log.2
- **Size**: 10,484,770 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260310_105152.log.5
- **Size**: 10,487,447 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260311_083526.log
- **Size**: 149,691 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260311_083544.log
- **Size**: 734,309 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260311_094202.log
- **Size**: 240,792 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260311_094222.log
- **Size**: 212,217 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260311_095244.log
- **Size**: 1,779,544 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260311_095957.log
- **Size**: 7,132,064 bytes
- **Type**: other
- **Purpose**: Application log file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260311_095957.log.1
- **Size**: 10,483,906 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/logs/live_20260311_095957.log.5
- **Size**: 10,487,734 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/models/.gitkeep
- **Size**: 0 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/models/ac3ff5ea-f8a8-4046-af54-d52efe8ec7f4_scalp_SPY_0e9fd3c0.joblib
- **Size**: 3,414,424 bytes
- **Type**: model
- **Purpose**: Trained ML model artifact
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/models/ac3ff5ea-f8a8-4046-af54-d52efe8ec7f4_scalp_SPY_171859fb.joblib
- **Size**: 634,240 bytes
- **Type**: model
- **Purpose**: Trained ML model artifact
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/models/ad48bf20-1913-4f40-b028-0580c9f48168_swing_cls_TSLA_ce4bfaf5.joblib
- **Size**: 1,033,928 bytes
- **Type**: model
- **Purpose**: Trained ML model artifact
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/.gitignore
- **Size**: 253 bytes
- **Type**: other
- **Purpose**: Git ignore patterns
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/README.md
- **Size**: 2,555 bytes
- **Type**: documentation
- **Purpose**: Project documentation
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/eslint.config.js
- **Size**: 616 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/index.html
- **Size**: 592 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/package-lock.json
- **Size**: 162,069 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/package.json
- **Size**: 898 bytes
- **Type**: config
- **Purpose**: NPM package configuration
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/postcss.config.js
- **Size**: 80 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/tailwind.config.js
- **Size**: 951 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/tsconfig.app.json
- **Size**: 732 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/tsconfig.json
- **Size**: 119 bytes
- **Type**: config
- **Purpose**: TypeScript compiler configuration
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/tsconfig.node.json
- **Size**: 653 bytes
- **Type**: config
- **Purpose**: Configuration or data file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/vite.config.ts
- **Size**: 283 bytes
- **Type**: other
- **Purpose**: Vite build configuration
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/dist/index.html
- **Size**: 690 bytes
- **Type**: build
- **Purpose**: Backtest tearsheet or build output
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/dist/assets/index-D2vcLwuR.js
- **Size**: 368,452 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

### options-bot/ui/dist/assets/index-yx7CmhFF.css
- **Size**: 21,362 bytes
- **Type**: other
- **Purpose**: other file
- **Contains secrets**: NO
- **Verdict**: PASS

---

### options-bot/__pycache__/config.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/config.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/__pycache__/main.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/main.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/__pycache__/__init__.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/__init__.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/__pycache__/app.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/app.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/__pycache__/database.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/database.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/__pycache__/db_log_handler.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/db_log_handler.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/__pycache__/schemas.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/schemas.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/routes/__pycache__/__init__.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/routes/__init__.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/routes/__pycache__/models.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/routes/models.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/routes/__pycache__/profiles.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/routes/profiles.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/routes/__pycache__/signals.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/routes/signals.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/routes/__pycache__/system.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/routes/system.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/routes/__pycache__/trades.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/routes/trades.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/backend/routes/__pycache__/trading.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/backend/routes/trading.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/data/__pycache__/__init__.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/data/__init__.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/data/__pycache__/alpaca_provider.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/data/alpaca_provider.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/data/__pycache__/earnings_calendar.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/data/earnings_calendar.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/data/__pycache__/greeks_calculator.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/data/greeks_calculator.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/data/__pycache__/options_data_fetcher.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/data/options_data_fetcher.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/data/__pycache__/provider.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/data/provider.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/data/__pycache__/theta_provider.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/data/theta_provider.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/data/__pycache__/validator.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/data/validator.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/data/__pycache__/vix_provider.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/data/vix_provider.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/__init__.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/__init__.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/ensemble_predictor.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/ensemble_predictor.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/ev_filter.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/ev_filter.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/feedback_queue.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/feedback_queue.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/incremental_trainer.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/incremental_trainer.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/lgbm_predictor.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/lgbm_predictor.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/lgbm_trainer.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/lgbm_trainer.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/liquidity_filter.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/liquidity_filter.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/predictor.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/predictor.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/regime_adjuster.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/regime_adjuster.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/scalp_predictor.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/scalp_predictor.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/scalp_trainer.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/scalp_trainer.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/swing_classifier_predictor.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/swing_classifier_predictor.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/swing_classifier_trainer.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/swing_classifier_trainer.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/tft_predictor.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/tft_predictor.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/tft_trainer.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/tft_trainer.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/trainer.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/trainer.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/__pycache__/xgboost_predictor.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/xgboost_predictor.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/feature_engineering/__pycache__/__init__.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/feature_engineering/__init__.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/feature_engineering/__pycache__/base_features.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/feature_engineering/base_features.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/feature_engineering/__pycache__/general_features.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/feature_engineering/general_features.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/feature_engineering/__pycache__/scalp_features.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/feature_engineering/scalp_features.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/ml/feature_engineering/__pycache__/swing_features.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/ml/feature_engineering/swing_features.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/risk/__pycache__/__init__.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/risk/__init__.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/risk/__pycache__/risk_manager.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/risk/risk_manager.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/audit_verify.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/audit_verify.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/backtest.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/backtest.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/diagnose_strategy.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/diagnose_strategy.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/phase6_checkpoint.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/phase6_checkpoint.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/startup_check.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/startup_check.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/test_features.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/test_features.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/test_providers.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/test_providers.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/train_model.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/train_model.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/validate_data.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/validate_data.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/validate_model.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/validate_model.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/scripts/__pycache__/walk_forward_backtest.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/scripts/walk_forward_backtest.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/strategies/__pycache__/__init__.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/strategies/__init__.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/strategies/__pycache__/base_strategy.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/strategies/base_strategy.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/strategies/__pycache__/general_strategy.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/strategies/general_strategy.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/strategies/__pycache__/scalp_strategy.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/strategies/scalp_strategy.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/strategies/__pycache__/swing_strategy.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/strategies/swing_strategy.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/utils/__pycache__/__init__.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/utils/__init__.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/utils/__pycache__/alerter.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/utils/alerter.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)

---

### options-bot/utils/__pycache__/circuit_breaker.cpython-313.pyc
- **Size**: compiled bytecode
- **Type**: __pycache__ artifact
- **Purpose**: Python bytecode cache of `options-bot/utils/circuit_breaker.py`. Auto-generated by Python interpreter, not source code.
- **Contains secrets**: NO
- **Auditable content**: NO — binary bytecode compiled from audited source file
- **Verdict**: PASS (build artifact of already-audited source)
