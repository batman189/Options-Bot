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
