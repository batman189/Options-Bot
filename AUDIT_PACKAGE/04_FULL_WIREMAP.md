# 04 — FULL WIREMAP

## Summary

**Total wire entries**: 741
**Scope**: Python functions/classes/methods, frontend components/functions/handlers, routes, config constants, env vars, type bindings, UI controls, storage paths, startup/shutdown hooks, exported symbols
**Method**: AST extraction + regex cross-reference search across all source files + manual frontend/config extraction

---

### WIRE-0001: _shutdown_handler (function)
- **File**: options-bot/main.py:86-97
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0002: _print_startup_banner (function)
- **File**: options-bot/main.py:113-159
- **Called by**: options-bot/main.py:458
- **References**: 1 call sites

### WIRE-0003: _kill_existing_on_port (function)
- **File**: options-bot/main.py:162-181
- **Called by**: options-bot/main.py:192
- **References**: 1 call sites

### WIRE-0004: start_backend (function)
- **File**: options-bot/main.py:184-207
- **Called by**: options-bot/main.py:462
- **References**: 1 call sites

### WIRE-0005: load_profile_from_db (function)
- **File**: options-bot/main.py:210-282
- **Called by**: options-bot/main.py:491, options-bot/main.py:528
- **References**: 2 call sites

### WIRE-0006: _get_strategy_class (function)
- **File**: options-bot/main.py:285-306
- **Called by**: options-bot/main.py:331, options-bot/main.py:388, options-bot/strategies/scalp_strategy.py:26
- **References**: 3 call sites

### WIRE-0007: start_trading_single (function)
- **File**: options-bot/main.py:309-355
- **Called by**: options-bot/main.py:537, options-bot/main.py:575
- **References**: 2 call sites

### WIRE-0008: start_trading_multi (function)
- **File**: options-bot/main.py:358-422
- **Called by**: options-bot/main.py:512
- **References**: 1 call sites

### WIRE-0009: main (function)
- **File**: options-bot/main.py:425-584
- **Called by**: options-bot/main.py:588, options-bot/scripts/backtest.py:253, options-bot/scripts/backtest.py:288, options-bot/scripts/test_features.py:215, options-bot/scripts/test_features.py:240, options-bot/scripts/test_providers.py:155, options-bot/scripts/test_providers.py:179, options-bot/scripts/train_model.py:62, options-bot/scripts/train_model.py:115, options-bot/scripts/validate_data.py:649 ... (+3 more)
- **References**: 13 call sites

### WIRE-0010: _store_backtest_result (function)
- **File**: options-bot/backend/app.py:37-63
- **Called by**: options-bot/backend/app.py:85, options-bot/backend/app.py:167, options-bot/backend/app.py:175
- **References**: 3 call sites

### WIRE-0011: _backtest_job (function)
- **File**: options-bot/backend/app.py:66-185
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0012: lifespan (function)
- **File**: options-bot/backend/app.py:193-230
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0013: run_backtest_endpoint (function)
- **File**: options-bot/backend/app.py:271-359
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0014: get_backtest_results (function)
- **File**: options-bot/backend/app.py:363-409
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0015: get_db (function)
- **File**: options-bot/backend/database.py:137-145
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0016: init_db (function)
- **File**: options-bot/backend/database.py:148-203
- **Called by**: options-bot/backend/app.py:196
- **References**: 1 call sites

### WIRE-0017: DatabaseLogHandler (class)
- **File**: options-bot/backend/db_log_handler.py:18-47
- **Called by**: options-bot/main.py:68
- **References**: 1 call sites

### WIRE-0018: DatabaseLogHandler.__init__ (method)
- **File**: options-bot/backend/db_log_handler.py:24-26
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0019: DatabaseLogHandler.emit (method)
- **File**: options-bot/backend/db_log_handler.py:28-47
- **Called by**: options-bot/backend/db_log_handler.py:28, options-bot/backend/db_log_handler.py:65, options-bot/ui/dist/assets/index-D2vcLwuR.js:1, options-bot/ui/dist/assets/index-D2vcLwuR.js:8
- **References**: 4 call sites

### WIRE-0020: TrainingLogHandler (class)
- **File**: options-bot/backend/db_log_handler.py:50-86
- **Called by**: options-bot/backend/routes/models.py:45
- **References**: 1 call sites

### WIRE-0021: TrainingLogHandler.__init__ (method)
- **File**: options-bot/backend/db_log_handler.py:58-63
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0022: TrainingLogHandler.emit (method)
- **File**: options-bot/backend/db_log_handler.py:65-86
- **Called by**: options-bot/backend/db_log_handler.py:28, options-bot/backend/db_log_handler.py:65, options-bot/ui/dist/assets/index-D2vcLwuR.js:1, options-bot/ui/dist/assets/index-D2vcLwuR.js:8
- **References**: 4 call sites

### WIRE-0023: ProfileCreate (class)
- **File**: options-bot/backend/schemas.py:17-21
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0024: ProfileUpdate (class)
- **File**: options-bot/backend/schemas.py:23-26
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0025: ModelSummary (class)
- **File**: options-bot/backend/schemas.py:28-35
- **Called by**: options-bot/backend/routes/profiles.py:45
- **References**: 1 call sites

### WIRE-0026: ProfileResponse (class)
- **File**: options-bot/backend/schemas.py:37-50
- **Called by**: options-bot/backend/routes/profiles.py:77
- **References**: 1 call sites

### WIRE-0027: ModelResponse (class)
- **File**: options-bot/backend/schemas.py:57-70
- **Called by**: options-bot/backend/routes/models.py:696
- **References**: 1 call sites

### WIRE-0028: TrainRequest (class)
- **File**: options-bot/backend/schemas.py:72-76
- **Called by**: options-bot/backend/routes/models.py:728
- **References**: 1 call sites

### WIRE-0029: TrainingStatus (class)
- **File**: options-bot/backend/schemas.py:78-83
- **Called by**: options-bot/backend/routes/models.py:815, options-bot/backend/routes/models.py:885, options-bot/backend/routes/models.py:919, options-bot/backend/routes/models.py:939, options-bot/backend/routes/models.py:947
- **References**: 5 call sites

### WIRE-0030: ModelMetrics (class)
- **File**: options-bot/backend/schemas.py:85-96
- **Called by**: options-bot/backend/routes/models.py:975
- **References**: 1 call sites

### WIRE-0031: TrainingLogEntry (class)
- **File**: options-bot/backend/schemas.py:98-103
- **Called by**: options-bot/backend/routes/models.py:1077
- **References**: 1 call sites

### WIRE-0032: TradeResponse (class)
- **File**: options-bot/backend/schemas.py:110-132
- **Called by**: options-bot/backend/routes/trades.py:26
- **References**: 1 call sites

### WIRE-0033: TradeStats (class)
- **File**: options-bot/backend/schemas.py:134-145
- **Called by**: options-bot/backend/routes/trades.py:98
- **References**: 1 call sites

### WIRE-0034: SystemStatus (class)
- **File**: options-bot/backend/schemas.py:152-165
- **Called by**: options-bot/backend/routes/system.py:186
- **References**: 1 call sites

### WIRE-0035: HealthCheck (class)
- **File**: options-bot/backend/schemas.py:167-170
- **Called by**: options-bot/backend/routes/system.py:47
- **References**: 1 call sites

### WIRE-0036: PDTStatus (class)
- **File**: options-bot/backend/schemas.py:172-177
- **Called by**: options-bot/backend/routes/system.py:239
- **References**: 1 call sites

### WIRE-0037: ErrorLogEntry (class)
- **File**: options-bot/backend/schemas.py:179-183
- **Called by**: options-bot/backend/routes/system.py:302
- **References**: 1 call sites

### WIRE-0038: ModelHealthEntry (class)
- **File**: options-bot/backend/schemas.py:186-196
- **Called by**: options-bot/backend/routes/system.py:409
- **References**: 1 call sites

### WIRE-0039: ModelHealthResponse (class)
- **File**: options-bot/backend/schemas.py:199-203
- **Called by**: options-bot/backend/routes/system.py:439
- **References**: 1 call sites

### WIRE-0040: TrainingQueueStatus (class)
- **File**: options-bot/backend/schemas.py:210-214
- **Called by**: options-bot/backend/routes/system.py:475
- **References**: 1 call sites

### WIRE-0041: BacktestRequest (class)
- **File**: options-bot/backend/schemas.py:221-224
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0042: BacktestResult (class)
- **File**: options-bot/backend/schemas.py:226-241
- **Called by**: options-bot/backend/app.py:349, options-bot/backend/app.py:383, options-bot/backend/app.py:391, options-bot/backend/app.py:405
- **References**: 4 call sites

### WIRE-0043: TradingProcessInfo (class)
- **File**: options-bot/backend/schemas.py:248-255
- **Called by**: options-bot/backend/routes/trading.py:357, options-bot/backend/routes/trading.py:433, options-bot/backend/routes/trading.py:541
- **References**: 3 call sites

### WIRE-0044: TradingStatusResponse (class)
- **File**: options-bot/backend/schemas.py:257-260
- **Called by**: options-bot/backend/routes/trading.py:443
- **References**: 1 call sites

### WIRE-0045: TradingStartRequest (class)
- **File**: options-bot/backend/schemas.py:262-263
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0046: TradingStartResponse (class)
- **File**: options-bot/backend/schemas.py:265-267
- **Called by**: options-bot/backend/routes/trading.py:555
- **References**: 1 call sites

### WIRE-0047: TradingStopRequest (class)
- **File**: options-bot/backend/schemas.py:269-270
- **Called by**: options-bot/backend/routes/trading.py:638
- **References**: 1 call sites

### WIRE-0048: TradingStopResponse (class)
- **File**: options-bot/backend/schemas.py:272-274
- **Called by**: options-bot/backend/routes/trading.py:629
- **References**: 1 call sites

### WIRE-0049: SignalLogEntry (class)
- **File**: options-bot/backend/schemas.py:281-293
- **Called by**: options-bot/backend/routes/signals.py:26
- **References**: 1 call sites

### WIRE-0050: _install_training_logger (function)
- **File**: options-bot/backend/routes/models.py:40-48
- **Called by**: options-bot/backend/routes/models.py:257, options-bot/backend/routes/models.py:309, options-bot/backend/routes/models.py:362, options-bot/backend/routes/models.py:419, options-bot/backend/routes/models.py:529, options-bot/backend/routes/models.py:580, options-bot/backend/routes/models.py:632
- **References**: 7 call sites

### WIRE-0051: _remove_training_logger (function)
- **File**: options-bot/backend/routes/models.py:51-53
- **Called by**: options-bot/backend/routes/models.py:297, options-bot/backend/routes/models.py:351, options-bot/backend/routes/models.py:399, options-bot/backend/routes/models.py:517, options-bot/backend/routes/models.py:568, options-bot/backend/routes/models.py:620, options-bot/backend/routes/models.py:670
- **References**: 7 call sites

### WIRE-0052: _check_theta_or_raise (function)
- **File**: options-bot/backend/routes/models.py:60-104
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0053: _set_profile_status (function)
- **File**: options-bot/backend/routes/models.py:111-132
- **Called by**: options-bot/backend/routes/models.py:262, options-bot/backend/routes/models.py:289, options-bot/backend/routes/models.py:295, options-bot/backend/routes/models.py:314, options-bot/backend/routes/models.py:337, options-bot/backend/routes/models.py:343, options-bot/backend/routes/models.py:349, options-bot/backend/routes/models.py:367, options-bot/backend/routes/models.py:391, options-bot/backend/routes/models.py:397 ... (+16 more)
- **References**: 26 call sites

### WIRE-0054: _get_failure_status (function)
- **File**: options-bot/backend/routes/models.py:135-155
- **Called by**: options-bot/backend/routes/models.py:289, options-bot/backend/routes/models.py:295, options-bot/backend/routes/models.py:391, options-bot/backend/routes/models.py:397, options-bot/backend/routes/models.py:560, options-bot/backend/routes/models.py:566, options-bot/backend/routes/models.py:612, options-bot/backend/routes/models.py:618, options-bot/backend/routes/models.py:662, options-bot/backend/routes/models.py:668 ... (+1 more)
- **References**: 11 call sites

### WIRE-0055: _extract_and_persist_importance (function)
- **File**: options-bot/backend/routes/models.py:158-248
- **Called by**: options-bot/backend/routes/models.py:280, options-bot/backend/routes/models.py:384, options-bot/backend/routes/models.py:501, options-bot/backend/routes/models.py:551, options-bot/backend/routes/models.py:603, options-bot/backend/routes/models.py:653
- **References**: 6 call sites

### WIRE-0056: _full_train_job (function)
- **File**: options-bot/backend/routes/models.py:251-300
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0057: _incremental_retrain_job (function)
- **File**: options-bot/backend/routes/models.py:303-354
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0058: _tft_train_job (function)
- **File**: options-bot/backend/routes/models.py:357-402
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0059: _ensemble_train_job (function)
- **File**: options-bot/backend/routes/models.py:405-520
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0060: _lgbm_train_job (function)
- **File**: options-bot/backend/routes/models.py:523-571
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0061: _swing_classifier_train_job (function)
- **File**: options-bot/backend/routes/models.py:574-623
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0062: _scalp_train_job (function)
- **File**: options-bot/backend/routes/models.py:626-673
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0063: get_model (function)
- **File**: options-bot/backend/routes/models.py:684-710
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0064: train_model_endpoint (function)
- **File**: options-bot/backend/routes/models.py:717-825
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0065: retrain_model (function)
- **File**: options-bot/backend/routes/models.py:832-895
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0066: get_training_status (function)
- **File**: options-bot/backend/routes/models.py:902-953
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0067: get_model_metrics (function)
- **File**: options-bot/backend/routes/models.py:960-987
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0068: get_feature_importance (function)
- **File**: options-bot/backend/routes/models.py:994-1034
- **Called by**: options-bot/backend/routes/models.py:182, options-bot/backend/routes/models.py:187, options-bot/backend/routes/models.py:192, options-bot/backend/routes/models.py:197, options-bot/backend/routes/models.py:202, options-bot/backend/routes/models.py:207, options-bot/ml/ensemble_predictor.py:299, options-bot/ml/ensemble_predictor.py:311, options-bot/ml/ensemble_predictor.py:318, options-bot/ml/ensemble_predictor.py:319 ... (+10 more)
- **References**: 20 call sites

### WIRE-0069: clear_training_logs (function)
- **File**: options-bot/backend/routes/models.py:1041-1052
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0070: get_training_logs (function)
- **File**: options-bot/backend/routes/models.py:1056-1085
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0071: _model_row_to_summary (function)
- **File**: options-bot/backend/routes/profiles.py:29-53
- **Called by**: options-bot/backend/routes/profiles.py:66, options-bot/backend/routes/profiles.py:72
- **References**: 2 call sites

### WIRE-0072: _build_profile_response (function)
- **File**: options-bot/backend/routes/profiles.py:56-91
- **Called by**: options-bot/backend/routes/profiles.py:132, options-bot/backend/routes/profiles.py:162, options-bot/backend/routes/profiles.py:196, options-bot/backend/routes/profiles.py:241
- **References**: 4 call sites

### WIRE-0073: _get_trade_stats (function)
- **File**: options-bot/backend/routes/profiles.py:94-113
- **Called by**: options-bot/backend/routes/profiles.py:131, options-bot/backend/routes/profiles.py:161, options-bot/backend/routes/profiles.py:195
- **References**: 3 call sites

### WIRE-0074: _full_profile_response (function)
- **File**: options-bot/backend/routes/profiles.py:116-137
- **Called by**: options-bot/backend/routes/profiles.py:278, options-bot/backend/routes/profiles.py:385, options-bot/backend/routes/profiles.py:414
- **References**: 3 call sites

### WIRE-0075: list_profiles (function)
- **File**: options-bot/backend/routes/profiles.py:144-170
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0076: get_profile (function)
- **File**: options-bot/backend/routes/profiles.py:177-201
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0077: create_profile (function)
- **File**: options-bot/backend/routes/profiles.py:208-241
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0078: update_profile (function)
- **File**: options-bot/backend/routes/profiles.py:248-278
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0079: delete_profile (function)
- **File**: options-bot/backend/routes/profiles.py:285-355
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0080: activate_profile (function)
- **File**: options-bot/backend/routes/profiles.py:363-385
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0081: pause_profile (function)
- **File**: options-bot/backend/routes/profiles.py:392-414
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0082: _row_to_signal (function)
- **File**: options-bot/backend/routes/signals.py:24-38
- **Called by**: options-bot/backend/routes/signals.py:123
- **References**: 1 call sites

### WIRE-0083: export_signal_logs (function)
- **File**: options-bot/backend/routes/signals.py:46-85
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0084: get_signal_logs (function)
- **File**: options-bot/backend/routes/signals.py:92-123
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0085: _read_circuit_states (function)
- **File**: options-bot/backend/routes/system.py:25-38
- **Called by**: options-bot/backend/routes/system.py:180
- **References**: 1 call sites

### WIRE-0086: health_check (function)
- **File**: options-bot/backend/routes/system.py:45-51
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0087: get_system_status (function)
- **File**: options-bot/backend/routes/system.py:58-200
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0088: get_pdt_status (function)
- **File**: options-bot/backend/routes/system.py:207-245
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0089: clear_error_logs (function)
- **File**: options-bot/backend/routes/system.py:252-259
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0090: get_recent_errors (function)
- **File**: options-bot/backend/routes/system.py:266-312
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0091: get_model_health (function)
- **File**: options-bot/backend/routes/system.py:319-444
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0092: get_training_queue_status (function)
- **File**: options-bot/backend/routes/system.py:451-480
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0093: _row_to_trade (function)
- **File**: options-bot/backend/routes/trades.py:24-49
- **Called by**: options-bot/backend/routes/trades.py:63, options-bot/backend/routes/trades.py:182, options-bot/backend/routes/trades.py:196
- **References**: 3 call sites

### WIRE-0094: list_active_trades (function)
- **File**: options-bot/backend/routes/trades.py:56-63
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0095: get_trade_stats (function)
- **File**: options-bot/backend/routes/trades.py:70-110
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0096: export_trades (function)
- **File**: options-bot/backend/routes/trades.py:117-148
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0097: list_trades (function)
- **File**: options-bot/backend/routes/trades.py:155-182
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0098: get_trade (function)
- **File**: options-bot/backend/routes/trades.py:189-196
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0099: _is_process_alive (function)
- **File**: options-bot/backend/routes/trading.py:58-87
- **Called by**: options-bot/backend/routes/trading.py:187, options-bot/backend/routes/trading.py:349, options-bot/backend/routes/trading.py:385, options-bot/backend/routes/trading.py:468, options-bot/backend/routes/trading.py:602
- **References**: 5 call sites

### WIRE-0100: _get_python_exe (function)
- **File**: options-bot/backend/routes/trading.py:90-92
- **Called by**: options-bot/backend/routes/trading.py:270, options-bot/backend/routes/trading.py:493
- **References**: 2 call sites

### WIRE-0101: _get_main_py_path (function)
- **File**: options-bot/backend/routes/trading.py:95-97
- **Called by**: options-bot/backend/routes/trading.py:271, options-bot/backend/routes/trading.py:494
- **References**: 2 call sites

### WIRE-0102: _store_process_state (function)
- **File**: options-bot/backend/routes/trading.py:100-115
- **Called by**: options-bot/backend/routes/trading.py:298, options-bot/backend/routes/trading.py:528
- **References**: 2 call sites

### WIRE-0103: _clear_process_state (function)
- **File**: options-bot/backend/routes/trading.py:118-129
- **Called by**: options-bot/backend/routes/trading.py:211, options-bot/backend/routes/trading.py:397, options-bot/backend/routes/trading.py:423, options-bot/backend/routes/trading.py:612
- **References**: 4 call sites

### WIRE-0104: _watchdog_loop (function)
- **File**: options-bot/backend/routes/trading.py:136-165
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0105: _watchdog_check_once (function)
- **File**: options-bot/backend/routes/trading.py:168-247
- **Called by**: options-bot/backend/routes/trading.py:155
- **References**: 1 call sites

### WIRE-0106: _set_profile_status_sync (function)
- **File**: options-bot/backend/routes/trading.py:250-265
- **Called by**: options-bot/backend/routes/trading.py:214, options-bot/backend/routes/trading.py:305
- **References**: 2 call sites

### WIRE-0107: _watchdog_restart_profile (function)
- **File**: options-bot/backend/routes/trading.py:268-307
- **Called by**: options-bot/backend/routes/trading.py:242
- **References**: 1 call sites

### WIRE-0108: start_watchdog (function)
- **File**: options-bot/backend/routes/trading.py:310-324
- **Called by**: options-bot/backend/app.py:223
- **References**: 1 call sites

### WIRE-0109: stop_watchdog (function)
- **File**: options-bot/backend/routes/trading.py:327-331
- **Called by**: options-bot/backend/app.py:229
- **References**: 1 call sites

### WIRE-0110: _build_process_info (function)
- **File**: options-bot/backend/routes/trading.py:334-364
- **Called by**: options-bot/backend/routes/trading.py:414
- **References**: 1 call sites

### WIRE-0111: restore_process_registry (function)
- **File**: options-bot/backend/routes/trading.py:371-399
- **Called by**: options-bot/backend/app.py:202
- **References**: 1 call sites

### WIRE-0112: get_trading_status (function)
- **File**: options-bot/backend/routes/trading.py:407-447
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0113: start_trading (function)
- **File**: options-bot/backend/routes/trading.py:451-555
- **Called by**: options-bot/backend/routes/trading.py:644
- **References**: 1 call sites

### WIRE-0114: stop_trading (function)
- **File**: options-bot/backend/routes/trading.py:559-629
- **Called by**: options-bot/backend/routes/trading.py:638
- **References**: 1 call sites

### WIRE-0115: restart_trading (function)
- **File**: options-bot/backend/routes/trading.py:633-644
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0116: get_startable_profiles (function)
- **File**: options-bot/backend/routes/trading.py:648-672
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0117: get_watchdog_stats (function)
- **File**: options-bot/backend/routes/trading.py:676-687
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0118: AlpacaStockProvider (class)
- **File**: options-bot/data/alpaca_provider.py:44-260
- **Called by**: options-bot/data/validator.py:333, options-bot/data/vix_provider.py:166, options-bot/ml/ensemble_predictor.py:443, options-bot/ml/incremental_trainer.py:359, options-bot/ml/lgbm_trainer.py:169, options-bot/ml/scalp_trainer.py:412, options-bot/ml/swing_classifier_trainer.py:465, options-bot/ml/tft_trainer.py:783, options-bot/ml/trainer.py:424, options-bot/scripts/diagnose_strategy.py:27 ... (+5 more)
- **References**: 15 call sites

### WIRE-0119: AlpacaStockProvider.__init__ (method)
- **File**: options-bot/data/alpaca_provider.py:47-56
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0120: AlpacaStockProvider._init_clients (method)
- **File**: options-bot/data/alpaca_provider.py:58-76
- **Called by**: options-bot/data/alpaca_provider.py:51, options-bot/data/alpaca_provider.py:58
- **References**: 2 call sites

### WIRE-0121: AlpacaStockProvider._timeframe_to_alpaca (method)
- **File**: options-bot/data/alpaca_provider.py:78-94
- **Called by**: options-bot/data/alpaca_provider.py:78, options-bot/data/alpaca_provider.py:127
- **References**: 2 call sites

### WIRE-0122: AlpacaStockProvider.get_historical_bars (method)
- **File**: options-bot/data/alpaca_provider.py:96-226
- **Called by**: options-bot/data/alpaca_provider.py:96, options-bot/data/provider.py:24, options-bot/data/validator.py:338, options-bot/data/vix_provider.py:177, options-bot/data/vix_provider.py:195, options-bot/ml/ensemble_predictor.py:446, options-bot/ml/incremental_trainer.py:360, options-bot/ml/lgbm_trainer.py:175, options-bot/ml/scalp_trainer.py:419, options-bot/ml/swing_classifier_trainer.py:471 ... (+9 more)
- **References**: 19 call sites

### WIRE-0123: AlpacaStockProvider.get_latest_price (method)
- **File**: options-bot/data/alpaca_provider.py:228-247
- **Called by**: options-bot/data/alpaca_provider.py:228, options-bot/data/provider.py:48, options-bot/scripts/test_providers.py:46
- **References**: 3 call sites

### WIRE-0124: AlpacaStockProvider.test_connection (method)
- **File**: options-bot/data/alpaca_provider.py:249-260
- **Called by**: options-bot/data/alpaca_provider.py:249, options-bot/data/provider.py:53, options-bot/data/provider.py:170, options-bot/data/theta_provider.py:478, options-bot/scripts/test_providers.py:40, options-bot/scripts/test_providers.py:94
- **References**: 6 call sites

### WIRE-0125: has_earnings_in_window (function)
- **File**: options-bot/data/earnings_calendar.py:22-79
- **Called by**: options-bot/strategies/base_strategy.py:1673
- **References**: 1 call sites

### WIRE-0126: _get_earnings_dates (function)
- **File**: options-bot/data/earnings_calendar.py:82-133
- **Called by**: options-bot/data/earnings_calendar.py:60
- **References**: 1 call sites

### WIRE-0127: _bs_d1_d2 (function)
- **File**: options-bot/data/greeks_calculator.py:42-67
- **Called by**: options-bot/data/greeks_calculator.py:109
- **References**: 1 call sites

### WIRE-0128: compute_greeks (function)
- **File**: options-bot/data/greeks_calculator.py:70-173
- **Called by**: options-bot/data/greeks_calculator.py:196, options-bot/data/options_data_fetcher.py:246, options-bot/data/options_data_fetcher.py:270
- **References**: 3 call sites

### WIRE-0129: compute_greeks_vectorized (function)
- **File**: options-bot/data/greeks_calculator.py:176-273
- **Called by**: options-bot/data/greeks_calculator.py:201, options-bot/ml/feature_engineering/base_features.py:396, options-bot/ml/feature_engineering/base_features.py:397
- **References**: 3 call sites

### WIRE-0130: _bs_price (function)
- **File**: options-bot/data/options_data_fetcher.py:50-61
- **Called by**: options-bot/data/options_data_fetcher.py:84
- **References**: 1 call sites

### WIRE-0131: _implied_vol (function)
- **File**: options-bot/data/options_data_fetcher.py:64-91
- **Called by**: options-bot/data/options_data_fetcher.py:239, options-bot/data/options_data_fetcher.py:266, options-bot/data/options_data_fetcher.py:296, options-bot/data/options_data_fetcher.py:306
- **References**: 4 call sites

### WIRE-0132: _third_friday (function)
- **File**: options-bot/data/options_data_fetcher.py:98-105
- **Called by**: options-bot/data/options_data_fetcher.py:115, options-bot/data/options_data_fetcher.py:119, options-bot/data/options_data_fetcher.py:121, options-bot/data/options_data_fetcher.py:456, options-bot/data/options_data_fetcher.py:458
- **References**: 5 call sites

### WIRE-0133: _pick_expiration_for_period (function)
- **File**: options-bot/data/options_data_fetcher.py:108-122
- **Called by**: options-bot/data/options_data_fetcher.py:440
- **References**: 1 call sites

### WIRE-0134: _fetch_eod_batch (function)
- **File**: options-bot/data/options_data_fetcher.py:129-175
- **Called by**: options-bot/data/options_data_fetcher.py:450, options-bot/data/options_data_fetcher.py:461
- **References**: 2 call sites

### WIRE-0135: _process_eod_day (function)
- **File**: options-bot/data/options_data_fetcher.py:182-321
- **Called by**: options-bot/data/options_data_fetcher.py:502
- **References**: 1 call sites

### WIRE-0136: fetch_options_for_training (function)
- **File**: options-bot/data/options_data_fetcher.py:328-547
- **Called by**: options-bot/ml/ensemble_predictor.py:475, options-bot/ml/scalp_trainer.py:71, options-bot/ml/swing_classifier_trainer.py:69, options-bot/ml/tft_trainer.py:155, options-bot/ml/trainer.py:103, options-bot/strategies/base_strategy.py:845, options-bot/strategies/base_strategy.py:1221
- **References**: 7 call sites

### WIRE-0137: StockDataProvider (class)
- **File**: options-bot/data/provider.py:20-55
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0138: StockDataProvider.get_historical_bars (method)
- **File**: options-bot/data/provider.py:24-45
- **Called by**: options-bot/data/alpaca_provider.py:96, options-bot/data/provider.py:24, options-bot/data/validator.py:338, options-bot/data/vix_provider.py:177, options-bot/data/vix_provider.py:195, options-bot/ml/ensemble_predictor.py:446, options-bot/ml/incremental_trainer.py:360, options-bot/ml/lgbm_trainer.py:175, options-bot/ml/scalp_trainer.py:419, options-bot/ml/swing_classifier_trainer.py:471 ... (+9 more)
- **References**: 19 call sites

### WIRE-0139: StockDataProvider.get_latest_price (method)
- **File**: options-bot/data/provider.py:48-50
- **Called by**: options-bot/data/alpaca_provider.py:228, options-bot/data/provider.py:48, options-bot/scripts/test_providers.py:46
- **References**: 3 call sites

### WIRE-0140: StockDataProvider.test_connection (method)
- **File**: options-bot/data/provider.py:53-55
- **Called by**: options-bot/data/alpaca_provider.py:249, options-bot/data/provider.py:53, options-bot/data/provider.py:170, options-bot/data/theta_provider.py:478, options-bot/scripts/test_providers.py:40, options-bot/scripts/test_providers.py:94
- **References**: 6 call sites

### WIRE-0141: OptionsDataProvider (class)
- **File**: options-bot/data/provider.py:58-172
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0142: OptionsDataProvider.get_expirations (method)
- **File**: options-bot/data/provider.py:62-69
- **Called by**: options-bot/data/provider.py:62, options-bot/data/theta_provider.py:165, options-bot/scripts/test_providers.py:100
- **References**: 3 call sites

### WIRE-0143: OptionsDataProvider.get_strikes (method)
- **File**: options-bot/data/provider.py:72-79
- **Called by**: options-bot/data/provider.py:72, options-bot/data/theta_provider.py:227, options-bot/scripts/test_providers.py:114
- **References**: 3 call sites

### WIRE-0144: OptionsDataProvider.get_historical_greeks (method)
- **File**: options-bot/data/provider.py:82-108
- **Called by**: options-bot/data/provider.py:82, options-bot/data/theta_provider.py:268, options-bot/scripts/test_providers.py:131
- **References**: 3 call sites

### WIRE-0145: OptionsDataProvider.get_historical_ohlc (method)
- **File**: options-bot/data/provider.py:111-128
- **Called by**: options-bot/data/provider.py:111, options-bot/data/theta_provider.py:336
- **References**: 2 call sites

### WIRE-0146: OptionsDataProvider.get_historical_eod (method)
- **File**: options-bot/data/provider.py:131-148
- **Called by**: options-bot/data/provider.py:131, options-bot/data/theta_provider.py:392
- **References**: 2 call sites

### WIRE-0147: OptionsDataProvider.get_bulk_greeks_eod (method)
- **File**: options-bot/data/provider.py:151-167
- **Called by**: options-bot/data/provider.py:151, options-bot/data/theta_provider.py:425, options-bot/scripts/test_providers.py:142
- **References**: 3 call sites

### WIRE-0148: OptionsDataProvider.test_connection (method)
- **File**: options-bot/data/provider.py:170-172
- **Called by**: options-bot/data/alpaca_provider.py:249, options-bot/data/provider.py:53, options-bot/data/provider.py:170, options-bot/data/theta_provider.py:478, options-bot/scripts/test_providers.py:40, options-bot/scripts/test_providers.py:94
- **References**: 6 call sites

### WIRE-0149: ThetaOptionsProvider (class)
- **File**: options-bot/data/theta_provider.py:46-502
- **Called by**: options-bot/scripts/test_providers.py:91
- **References**: 1 call sites

### WIRE-0150: ThetaOptionsProvider.__init__ (method)
- **File**: options-bot/data/theta_provider.py:49-51
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0151: ThetaOptionsProvider._request (method)
- **File**: options-bot/data/theta_provider.py:53-121
- **Called by**: options-bot/data/theta_provider.py:53, options-bot/data/theta_provider.py:170, options-bot/data/theta_provider.py:231, options-bot/data/theta_provider.py:285, options-bot/data/theta_provider.py:351, options-bot/data/theta_provider.py:407, options-bot/data/theta_provider.py:443
- **References**: 7 call sites

### WIRE-0152: ThetaOptionsProvider._parse_csv_response (method)
- **File**: options-bot/data/theta_provider.py:123-153
- **Called by**: options-bot/data/theta_provider.py:123, options-bot/data/theta_provider.py:179, options-bot/data/theta_provider.py:243, options-bot/data/theta_provider.py:300, options-bot/data/theta_provider.py:367, options-bot/data/theta_provider.py:423, options-bot/data/theta_provider.py:458
- **References**: 7 call sites

### WIRE-0153: ThetaOptionsProvider._format_date (method)
- **File**: options-bot/data/theta_provider.py:156-158
- **Called by**: options-bot/data/theta_provider.py:156, options-bot/data/theta_provider.py:235, options-bot/data/theta_provider.py:289, options-bot/data/theta_provider.py:292, options-bot/data/theta_provider.py:355, options-bot/data/theta_provider.py:358, options-bot/data/theta_provider.py:411, options-bot/data/theta_provider.py:414, options-bot/data/theta_provider.py:415, options-bot/data/theta_provider.py:447 ... (+1 more)
- **References**: 11 call sites

### WIRE-0154: ThetaOptionsProvider._format_strike (method)
- **File**: options-bot/data/theta_provider.py:161-163
- **Called by**: options-bot/data/theta_provider.py:161, options-bot/data/theta_provider.py:290, options-bot/data/theta_provider.py:356, options-bot/data/theta_provider.py:412
- **References**: 4 call sites

### WIRE-0155: ThetaOptionsProvider.get_expirations (method)
- **File**: options-bot/data/theta_provider.py:165-225
- **Called by**: options-bot/data/provider.py:62, options-bot/data/theta_provider.py:165, options-bot/scripts/test_providers.py:100
- **References**: 3 call sites

### WIRE-0156: ThetaOptionsProvider.get_strikes (method)
- **File**: options-bot/data/theta_provider.py:227-266
- **Called by**: options-bot/data/provider.py:72, options-bot/data/theta_provider.py:227, options-bot/scripts/test_providers.py:114
- **References**: 3 call sites

### WIRE-0157: ThetaOptionsProvider.get_historical_greeks (method)
- **File**: options-bot/data/theta_provider.py:268-334
- **Called by**: options-bot/data/provider.py:82, options-bot/data/theta_provider.py:268, options-bot/scripts/test_providers.py:131
- **References**: 3 call sites

### WIRE-0158: ThetaOptionsProvider.get_historical_ohlc (method)
- **File**: options-bot/data/theta_provider.py:336-390
- **Called by**: options-bot/data/provider.py:111, options-bot/data/theta_provider.py:336
- **References**: 2 call sites

### WIRE-0159: ThetaOptionsProvider.get_historical_eod (method)
- **File**: options-bot/data/theta_provider.py:392-423
- **Called by**: options-bot/data/provider.py:131, options-bot/data/theta_provider.py:392
- **References**: 2 call sites

### WIRE-0160: ThetaOptionsProvider.get_bulk_greeks_eod (method)
- **File**: options-bot/data/theta_provider.py:425-476
- **Called by**: options-bot/data/provider.py:151, options-bot/data/theta_provider.py:425, options-bot/scripts/test_providers.py:142
- **References**: 3 call sites

### WIRE-0161: ThetaOptionsProvider.test_connection (method)
- **File**: options-bot/data/theta_provider.py:478-502
- **Called by**: options-bot/data/alpaca_provider.py:249, options-bot/data/provider.py:53, options-bot/data/provider.py:170, options-bot/data/theta_provider.py:478, options-bot/scripts/test_providers.py:40, options-bot/scripts/test_providers.py:94
- **References**: 6 call sites

### WIRE-0162: _check_bar_count (function)
- **File**: options-bot/data/validator.py:63-75
- **Called by**: options-bot/data/validator.py:370
- **References**: 1 call sites

### WIRE-0163: _check_data_depth (function)
- **File**: options-bot/data/validator.py:78-106
- **Called by**: options-bot/data/validator.py:376
- **References**: 1 call sites

### WIRE-0164: _check_gaps (function)
- **File**: options-bot/data/validator.py:109-156
- **Called by**: options-bot/data/validator.py:382
- **References**: 1 call sites

### WIRE-0165: _check_ohlcv_quality (function)
- **File**: options-bot/data/validator.py:159-228
- **Called by**: options-bot/data/validator.py:391
- **References**: 1 call sites

### WIRE-0166: _check_daily_completeness (function)
- **File**: options-bot/data/validator.py:231-263
- **Called by**: options-bot/data/validator.py:397
- **References**: 1 call sites

### WIRE-0167: validate_symbol_data (function)
- **File**: options-bot/data/validator.py:266-433
- **Called by**: options-bot/data/validator.py:18, options-bot/data/validator.py:447, options-bot/data/validator.py:469
- **References**: 3 call sites

### WIRE-0168: validate_all_symbols (function)
- **File**: options-bot/data/validator.py:436-501
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0169: VIXProvider (class)
- **File**: options-bot/data/vix_provider.py:33-114
- **Called by**: options-bot/strategies/base_strategy.py:245
- **References**: 1 call sites

### WIRE-0170: VIXProvider.__init__ (method)
- **File**: options-bot/data/vix_provider.py:39-43
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0171: VIXProvider.get_current_vix (method)
- **File**: options-bot/data/vix_provider.py:45-114
- **Called by**: options-bot/data/vix_provider.py:45, options-bot/strategies/base_strategy.py:1081, options-bot/strategies/base_strategy.py:1397
- **References**: 3 call sites

### WIRE-0172: fetch_vix_daily_bars (function)
- **File**: options-bot/data/vix_provider.py:123-223
- **Called by**: options-bot/ml/ensemble_predictor.py:497, options-bot/ml/scalp_trainer.py:95, options-bot/ml/swing_classifier_trainer.py:93, options-bot/ml/tft_trainer.py:179, options-bot/ml/trainer.py:127, options-bot/strategies/base_strategy.py:860, options-bot/strategies/base_strategy.py:1236
- **References**: 7 call sites

### WIRE-0173: EnsemblePredictor (class)
- **File**: options-bot/ml/ensemble_predictor.py:35-789
- **Called by**: options-bot/backend/routes/models.py:191, options-bot/backend/routes/models.py:481, options-bot/ml/ensemble_predictor.py:41, options-bot/ml/ensemble_predictor.py:47, options-bot/strategies/base_strategy.py:150
- **References**: 5 call sites

### WIRE-0174: EnsemblePredictor.__init__ (method)
- **File**: options-bot/ml/ensemble_predictor.py:51-66
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0175: EnsemblePredictor.load (method)
- **File**: options-bot/ml/ensemble_predictor.py:72-120
- **Called by**: options-bot/ml/ensemble_predictor.py:66, options-bot/ml/ensemble_predictor.py:72, options-bot/ml/ensemble_predictor.py:87, options-bot/ml/ensemble_predictor.py:110, options-bot/ml/ensemble_predictor.py:187, options-bot/ml/ensemble_predictor.py:283, options-bot/ml/incremental_trainer.py:504, options-bot/ml/lgbm_predictor.py:29, options-bot/ml/lgbm_predictor.py:31, options-bot/ml/lgbm_predictor.py:34 ... (+26 more)
- **References**: 36 call sites

### WIRE-0176: EnsemblePredictor.save (method)
- **File**: options-bot/ml/ensemble_predictor.py:122-165
- **Called by**: options-bot/ml/ensemble_predictor.py:122, options-bot/ml/ensemble_predictor.py:710, options-bot/ml/incremental_trainer.py:620, options-bot/ml/lgbm_predictor.py:42, options-bot/ml/lgbm_trainer.py:285, options-bot/ml/scalp_predictor.py:67, options-bot/ml/scalp_trainer.py:698, options-bot/ml/swing_classifier_predictor.py:60, options-bot/ml/swing_classifier_trainer.py:845, options-bot/ml/tft_predictor.py:110 ... (+4 more)
- **References**: 14 call sites

### WIRE-0177: EnsemblePredictor.predict (method)
- **File**: options-bot/ml/ensemble_predictor.py:171-272
- **Called by**: options-bot/ml/ensemble_predictor.py:6, options-bot/ml/ensemble_predictor.py:48, options-bot/ml/ensemble_predictor.py:171, options-bot/ml/ensemble_predictor.py:176, options-bot/ml/ensemble_predictor.py:191, options-bot/ml/ensemble_predictor.py:205, options-bot/ml/ensemble_predictor.py:222, options-bot/ml/ensemble_predictor.py:261, options-bot/ml/ensemble_predictor.py:664, options-bot/ml/incremental_trainer.py:570 ... (+34 more)
- **References**: 44 call sites

### WIRE-0178: EnsemblePredictor.predict_batch (method)
- **File**: options-bot/ml/ensemble_predictor.py:274-289
- **Called by**: options-bot/ml/ensemble_predictor.py:274, options-bot/ml/ensemble_predictor.py:286, options-bot/ml/ensemble_predictor.py:289, options-bot/ml/ensemble_predictor.py:548, options-bot/ml/lgbm_predictor.py:76, options-bot/ml/predictor.py:30, options-bot/ml/scalp_predictor.py:128, options-bot/ml/swing_classifier_predictor.py:115, options-bot/ml/tft_predictor.py:237, options-bot/ml/tft_predictor.py:257 ... (+1 more)
- **References**: 11 call sites

### WIRE-0179: EnsemblePredictor.get_feature_names (method)
- **File**: options-bot/ml/ensemble_predictor.py:295-297
- **Called by**: options-bot/ml/ensemble_predictor.py:295, options-bot/ml/ensemble_predictor.py:423, options-bot/ml/ensemble_predictor.py:435, options-bot/ml/lgbm_predictor.py:85, options-bot/ml/predictor.py:43, options-bot/ml/scalp_predictor.py:159, options-bot/ml/swing_classifier_predictor.py:129, options-bot/ml/tft_predictor.py:289, options-bot/ml/xgboost_predictor.py:82, options-bot/scripts/diagnose_strategy.py:18 ... (+2 more)
- **References**: 12 call sites

### WIRE-0180: EnsemblePredictor.get_feature_importance (method)
- **File**: options-bot/ml/ensemble_predictor.py:299-348
- **Called by**: options-bot/backend/routes/models.py:182, options-bot/backend/routes/models.py:187, options-bot/backend/routes/models.py:192, options-bot/backend/routes/models.py:197, options-bot/backend/routes/models.py:202, options-bot/backend/routes/models.py:207, options-bot/backend/routes/models.py:994, options-bot/ml/ensemble_predictor.py:299, options-bot/ml/ensemble_predictor.py:311, options-bot/ml/ensemble_predictor.py:318 ... (+11 more)
- **References**: 21 call sites

### WIRE-0181: EnsemblePredictor.train_meta_learner (method)
- **File**: options-bot/ml/ensemble_predictor.py:354-789
- **Called by**: options-bot/backend/routes/models.py:482, options-bot/ml/ensemble_predictor.py:14, options-bot/ml/ensemble_predictor.py:42, options-bot/ml/ensemble_predictor.py:133, options-bot/ml/ensemble_predictor.py:279, options-bot/ml/ensemble_predictor.py:287, options-bot/ml/ensemble_predictor.py:354
- **References**: 7 call sites

### WIRE-0182: EVCandidate (class)
- **File**: options-bot/ml/ev_filter.py:27-41
- **Called by**: options-bot/ml/ev_filter.py:423
- **References**: 1 call sites

### WIRE-0183: get_implied_move_pct (function)
- **File**: options-bot/ml/ev_filter.py:44-161
- **Called by**: options-bot/strategies/base_strategy.py:1626
- **References**: 1 call sites

### WIRE-0184: _estimate_delta (function)
- **File**: options-bot/ml/ev_filter.py:164-197
- **Called by**: options-bot/ml/ev_filter.py:323
- **References**: 1 call sites

### WIRE-0185: scan_chain_for_best_ev (function)
- **File**: options-bot/ml/ev_filter.py:200-472
- **Called by**: options-bot/ml/liquidity_filter.py:5, options-bot/strategies/base_strategy.py:1746
- **References**: 2 call sites

### WIRE-0186: enqueue_completed_sample (function)
- **File**: options-bot/ml/feedback_queue.py:20-54
- **Called by**: options-bot/strategies/base_strategy.py:985
- **References**: 1 call sites

### WIRE-0187: _run_async (function)
- **File**: options-bot/ml/incremental_trainer.py:69-85
- **Called by**: options-bot/ml/incremental_trainer.py:113, options-bot/ml/incremental_trainer.py:141, options-bot/ml/incremental_trainer.py:205, options-bot/ml/lgbm_trainer.py:302, options-bot/ml/lgbm_trainer.py:362, options-bot/ml/scalp_trainer.py:743, options-bot/ml/scalp_trainer.py:824, options-bot/ml/swing_classifier_trainer.py:590, options-bot/ml/swing_classifier_trainer.py:633, options-bot/ml/trainer.py:633 ... (+9 more)
- **References**: 19 call sites

### WIRE-0188: _load_model_record (function)
- **File**: options-bot/ml/incremental_trainer.py:88-113
- **Called by**: options-bot/ml/incremental_trainer.py:296
- **References**: 1 call sites

### WIRE-0189: _get_profile_model_id (function)
- **File**: options-bot/ml/incremental_trainer.py:116-141
- **Called by**: options-bot/ml/incremental_trainer.py:290
- **References**: 1 call sites

### WIRE-0190: _save_incremental_model_to_db (function)
- **File**: options-bot/ml/incremental_trainer.py:144-242
- **Called by**: options-bot/ml/incremental_trainer.py:650
- **References**: 1 call sites

### WIRE-0191: retrain_incremental (function)
- **File**: options-bot/ml/incremental_trainer.py:245-711
- **Called by**: options-bot/backend/routes/models.py:318, options-bot/backend/routes/models.py:331
- **References**: 2 call sites

### WIRE-0192: LightGBMPredictor (class)
- **File**: options-bot/ml/lgbm_predictor.py:22-97
- **Called by**: options-bot/backend/routes/models.py:196, options-bot/ml/ensemble_predictor.py:55, options-bot/ml/ensemble_predictor.py:107, options-bot/ml/lgbm_trainer.py:283, options-bot/strategies/base_strategy.py:153
- **References**: 5 call sites

### WIRE-0193: LightGBMPredictor.__init__ (method)
- **File**: options-bot/ml/lgbm_predictor.py:25-29
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0194: LightGBMPredictor.load (method)
- **File**: options-bot/ml/lgbm_predictor.py:31-40
- **Called by**: options-bot/ml/ensemble_predictor.py:66, options-bot/ml/ensemble_predictor.py:72, options-bot/ml/ensemble_predictor.py:87, options-bot/ml/ensemble_predictor.py:110, options-bot/ml/ensemble_predictor.py:187, options-bot/ml/ensemble_predictor.py:283, options-bot/ml/incremental_trainer.py:504, options-bot/ml/lgbm_predictor.py:29, options-bot/ml/lgbm_predictor.py:31, options-bot/ml/lgbm_predictor.py:34 ... (+26 more)
- **References**: 36 call sites

### WIRE-0195: LightGBMPredictor.save (method)
- **File**: options-bot/ml/lgbm_predictor.py:42-51
- **Called by**: options-bot/ml/ensemble_predictor.py:122, options-bot/ml/ensemble_predictor.py:710, options-bot/ml/incremental_trainer.py:620, options-bot/ml/lgbm_predictor.py:42, options-bot/ml/lgbm_trainer.py:285, options-bot/ml/scalp_predictor.py:67, options-bot/ml/scalp_trainer.py:698, options-bot/ml/swing_classifier_predictor.py:60, options-bot/ml/swing_classifier_trainer.py:845, options-bot/ml/tft_predictor.py:110 ... (+4 more)
- **References**: 14 call sites

### WIRE-0196: LightGBMPredictor.set_model (method)
- **File**: options-bot/ml/lgbm_predictor.py:53-56
- **Called by**: options-bot/ml/incremental_trainer.py:619, options-bot/ml/lgbm_predictor.py:53, options-bot/ml/lgbm_trainer.py:284, options-bot/ml/scalp_predictor.py:92, options-bot/ml/scalp_trainer.py:697, options-bot/ml/swing_classifier_predictor.py:83, options-bot/ml/swing_classifier_trainer.py:844, options-bot/ml/trainer.py:612, options-bot/ml/xgboost_predictor.py:49
- **References**: 9 call sites

### WIRE-0197: LightGBMPredictor.predict (method)
- **File**: options-bot/ml/lgbm_predictor.py:58-74
- **Called by**: options-bot/ml/ensemble_predictor.py:6, options-bot/ml/ensemble_predictor.py:48, options-bot/ml/ensemble_predictor.py:171, options-bot/ml/ensemble_predictor.py:176, options-bot/ml/ensemble_predictor.py:191, options-bot/ml/ensemble_predictor.py:205, options-bot/ml/ensemble_predictor.py:222, options-bot/ml/ensemble_predictor.py:261, options-bot/ml/ensemble_predictor.py:664, options-bot/ml/incremental_trainer.py:570 ... (+34 more)
- **References**: 44 call sites

### WIRE-0198: LightGBMPredictor.predict_batch (method)
- **File**: options-bot/ml/lgbm_predictor.py:76-83
- **Called by**: options-bot/ml/ensemble_predictor.py:274, options-bot/ml/ensemble_predictor.py:286, options-bot/ml/ensemble_predictor.py:289, options-bot/ml/ensemble_predictor.py:548, options-bot/ml/lgbm_predictor.py:76, options-bot/ml/predictor.py:30, options-bot/ml/scalp_predictor.py:128, options-bot/ml/swing_classifier_predictor.py:115, options-bot/ml/tft_predictor.py:237, options-bot/ml/tft_predictor.py:257 ... (+1 more)
- **References**: 11 call sites

### WIRE-0199: LightGBMPredictor.get_feature_names (method)
- **File**: options-bot/ml/lgbm_predictor.py:85-87
- **Called by**: options-bot/ml/ensemble_predictor.py:295, options-bot/ml/ensemble_predictor.py:423, options-bot/ml/ensemble_predictor.py:435, options-bot/ml/lgbm_predictor.py:85, options-bot/ml/predictor.py:43, options-bot/ml/scalp_predictor.py:159, options-bot/ml/swing_classifier_predictor.py:129, options-bot/ml/tft_predictor.py:289, options-bot/ml/xgboost_predictor.py:82, options-bot/scripts/diagnose_strategy.py:18 ... (+2 more)
- **References**: 12 call sites

### WIRE-0200: LightGBMPredictor.get_feature_importance (method)
- **File**: options-bot/ml/lgbm_predictor.py:89-97
- **Called by**: options-bot/backend/routes/models.py:182, options-bot/backend/routes/models.py:187, options-bot/backend/routes/models.py:192, options-bot/backend/routes/models.py:197, options-bot/backend/routes/models.py:202, options-bot/backend/routes/models.py:207, options-bot/backend/routes/models.py:994, options-bot/ml/ensemble_predictor.py:299, options-bot/ml/ensemble_predictor.py:311, options-bot/ml/ensemble_predictor.py:318 ... (+11 more)
- **References**: 21 call sites

### WIRE-0201: _walk_forward_cv_lgbm (function)
- **File**: options-bot/ml/lgbm_trainer.py:37-117
- **Called by**: options-bot/ml/lgbm_trainer.py:245
- **References**: 1 call sites

### WIRE-0202: train_lgbm_model (function)
- **File**: options-bot/ml/lgbm_trainer.py:120-430
- **Called by**: options-bot/backend/routes/models.py:538
- **References**: 1 call sites

### WIRE-0203: LiquidityResult (class)
- **File**: options-bot/ml/liquidity_filter.py:20-25
- **Called by**: options-bot/ml/liquidity_filter.py:64, options-bot/ml/liquidity_filter.py:76, options-bot/ml/liquidity_filter.py:96, options-bot/ml/liquidity_filter.py:108, options-bot/ml/liquidity_filter.py:119
- **References**: 5 call sites

### WIRE-0204: check_liquidity (function)
- **File**: options-bot/ml/liquidity_filter.py:28-125
- **Called by**: options-bot/strategies/base_strategy.py:1801
- **References**: 1 call sites

### WIRE-0205: fetch_option_snapshot (function)
- **File**: options-bot/ml/liquidity_filter.py:128-190
- **Called by**: options-bot/strategies/base_strategy.py:1792
- **References**: 1 call sites

### WIRE-0206: ModelPredictor (class)
- **File**: options-bot/ml/predictor.py:12-50
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0207: ModelPredictor.predict (method)
- **File**: options-bot/ml/predictor.py:16-27
- **Called by**: options-bot/ml/ensemble_predictor.py:6, options-bot/ml/ensemble_predictor.py:48, options-bot/ml/ensemble_predictor.py:171, options-bot/ml/ensemble_predictor.py:176, options-bot/ml/ensemble_predictor.py:191, options-bot/ml/ensemble_predictor.py:205, options-bot/ml/ensemble_predictor.py:222, options-bot/ml/ensemble_predictor.py:261, options-bot/ml/ensemble_predictor.py:664, options-bot/ml/incremental_trainer.py:570 ... (+34 more)
- **References**: 44 call sites

### WIRE-0208: ModelPredictor.predict_batch (method)
- **File**: options-bot/ml/predictor.py:30-40
- **Called by**: options-bot/ml/ensemble_predictor.py:274, options-bot/ml/ensemble_predictor.py:286, options-bot/ml/ensemble_predictor.py:289, options-bot/ml/ensemble_predictor.py:548, options-bot/ml/lgbm_predictor.py:76, options-bot/ml/predictor.py:30, options-bot/ml/scalp_predictor.py:128, options-bot/ml/swing_classifier_predictor.py:115, options-bot/ml/tft_predictor.py:237, options-bot/ml/tft_predictor.py:257 ... (+1 more)
- **References**: 11 call sites

### WIRE-0209: ModelPredictor.get_feature_names (method)
- **File**: options-bot/ml/predictor.py:43-45
- **Called by**: options-bot/ml/ensemble_predictor.py:295, options-bot/ml/ensemble_predictor.py:423, options-bot/ml/ensemble_predictor.py:435, options-bot/ml/lgbm_predictor.py:85, options-bot/ml/predictor.py:43, options-bot/ml/scalp_predictor.py:159, options-bot/ml/swing_classifier_predictor.py:129, options-bot/ml/tft_predictor.py:289, options-bot/ml/xgboost_predictor.py:82, options-bot/scripts/diagnose_strategy.py:18 ... (+2 more)
- **References**: 12 call sites

### WIRE-0210: ModelPredictor.get_feature_importance (method)
- **File**: options-bot/ml/predictor.py:48-50
- **Called by**: options-bot/backend/routes/models.py:182, options-bot/backend/routes/models.py:187, options-bot/backend/routes/models.py:192, options-bot/backend/routes/models.py:197, options-bot/backend/routes/models.py:202, options-bot/backend/routes/models.py:207, options-bot/backend/routes/models.py:994, options-bot/ml/ensemble_predictor.py:299, options-bot/ml/ensemble_predictor.py:311, options-bot/ml/ensemble_predictor.py:318 ... (+11 more)
- **References**: 21 call sites

### WIRE-0211: adjust_prediction_confidence (function)
- **File**: options-bot/ml/regime_adjuster.py:37-83
- **Called by**: options-bot/strategies/base_strategy.py:1400
- **References**: 1 call sites

### WIRE-0212: ScalpPredictor (class)
- **File**: options-bot/ml/scalp_predictor.py:33-208
- **Called by**: options-bot/backend/routes/models.py:201, options-bot/ml/scalp_trainer.py:696, options-bot/strategies/base_strategy.py:156
- **References**: 3 call sites

### WIRE-0213: ScalpPredictor.__init__ (method)
- **File**: options-bot/ml/scalp_predictor.py:36-44
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0214: ScalpPredictor.load (method)
- **File**: options-bot/ml/scalp_predictor.py:46-65
- **Called by**: options-bot/ml/ensemble_predictor.py:66, options-bot/ml/ensemble_predictor.py:72, options-bot/ml/ensemble_predictor.py:87, options-bot/ml/ensemble_predictor.py:110, options-bot/ml/ensemble_predictor.py:187, options-bot/ml/ensemble_predictor.py:283, options-bot/ml/incremental_trainer.py:504, options-bot/ml/lgbm_predictor.py:29, options-bot/ml/lgbm_predictor.py:31, options-bot/ml/lgbm_predictor.py:34 ... (+26 more)
- **References**: 36 call sites

### WIRE-0215: ScalpPredictor.save (method)
- **File**: options-bot/ml/scalp_predictor.py:67-90
- **Called by**: options-bot/ml/ensemble_predictor.py:122, options-bot/ml/ensemble_predictor.py:710, options-bot/ml/incremental_trainer.py:620, options-bot/ml/lgbm_predictor.py:42, options-bot/ml/lgbm_trainer.py:285, options-bot/ml/scalp_predictor.py:67, options-bot/ml/scalp_trainer.py:698, options-bot/ml/swing_classifier_predictor.py:60, options-bot/ml/swing_classifier_trainer.py:845, options-bot/ml/tft_predictor.py:110 ... (+4 more)
- **References**: 14 call sites

### WIRE-0216: ScalpPredictor.set_model (method)
- **File**: options-bot/ml/scalp_predictor.py:92-95
- **Called by**: options-bot/ml/incremental_trainer.py:619, options-bot/ml/lgbm_predictor.py:53, options-bot/ml/lgbm_trainer.py:284, options-bot/ml/scalp_predictor.py:92, options-bot/ml/scalp_trainer.py:697, options-bot/ml/swing_classifier_predictor.py:83, options-bot/ml/swing_classifier_trainer.py:844, options-bot/ml/trainer.py:612, options-bot/ml/xgboost_predictor.py:49
- **References**: 9 call sites

### WIRE-0217: ScalpPredictor.predict (method)
- **File**: options-bot/ml/scalp_predictor.py:97-126
- **Called by**: options-bot/ml/ensemble_predictor.py:6, options-bot/ml/ensemble_predictor.py:48, options-bot/ml/ensemble_predictor.py:171, options-bot/ml/ensemble_predictor.py:176, options-bot/ml/ensemble_predictor.py:191, options-bot/ml/ensemble_predictor.py:205, options-bot/ml/ensemble_predictor.py:222, options-bot/ml/ensemble_predictor.py:261, options-bot/ml/ensemble_predictor.py:664, options-bot/ml/incremental_trainer.py:570 ... (+34 more)
- **References**: 44 call sites

### WIRE-0218: ScalpPredictor.predict_batch (method)
- **File**: options-bot/ml/scalp_predictor.py:128-146
- **Called by**: options-bot/ml/ensemble_predictor.py:274, options-bot/ml/ensemble_predictor.py:286, options-bot/ml/ensemble_predictor.py:289, options-bot/ml/ensemble_predictor.py:548, options-bot/ml/lgbm_predictor.py:76, options-bot/ml/predictor.py:30, options-bot/ml/scalp_predictor.py:128, options-bot/ml/swing_classifier_predictor.py:115, options-bot/ml/tft_predictor.py:237, options-bot/ml/tft_predictor.py:257 ... (+1 more)
- **References**: 11 call sites

### WIRE-0219: ScalpPredictor._calibrate_p_up (method)
- **File**: options-bot/ml/scalp_predictor.py:148-157
- **Called by**: options-bot/ml/scalp_predictor.py:148, options-bot/ml/scalp_predictor.py:192
- **References**: 2 call sites

### WIRE-0220: ScalpPredictor.get_feature_names (method)
- **File**: options-bot/ml/scalp_predictor.py:159-161
- **Called by**: options-bot/ml/ensemble_predictor.py:295, options-bot/ml/ensemble_predictor.py:423, options-bot/ml/ensemble_predictor.py:435, options-bot/ml/lgbm_predictor.py:85, options-bot/ml/predictor.py:43, options-bot/ml/scalp_predictor.py:159, options-bot/ml/swing_classifier_predictor.py:129, options-bot/ml/tft_predictor.py:289, options-bot/ml/xgboost_predictor.py:82, options-bot/scripts/diagnose_strategy.py:18 ... (+2 more)
- **References**: 12 call sites

### WIRE-0221: ScalpPredictor.get_feature_importance (method)
- **File**: options-bot/ml/scalp_predictor.py:163-168
- **Called by**: options-bot/backend/routes/models.py:182, options-bot/backend/routes/models.py:187, options-bot/backend/routes/models.py:192, options-bot/backend/routes/models.py:197, options-bot/backend/routes/models.py:202, options-bot/backend/routes/models.py:207, options-bot/backend/routes/models.py:994, options-bot/ml/ensemble_predictor.py:299, options-bot/ml/ensemble_predictor.py:311, options-bot/ml/ensemble_predictor.py:318 ... (+11 more)
- **References**: 21 call sites

### WIRE-0222: ScalpPredictor.get_avg_30min_move_pct (method)
- **File**: options-bot/ml/scalp_predictor.py:170-175
- **Called by**: options-bot/ml/scalp_predictor.py:170, options-bot/strategies/base_strategy.py:265, options-bot/strategies/base_strategy.py:270
- **References**: 3 call sites

### WIRE-0223: ScalpPredictor._binary_to_signed_confidence (method)
- **File**: options-bot/ml/scalp_predictor.py:177-193
- **Called by**: options-bot/ml/scalp_predictor.py:124, options-bot/ml/scalp_predictor.py:138, options-bot/ml/scalp_predictor.py:177, options-bot/ml/swing_classifier_predictor.py:113, options-bot/ml/swing_classifier_predictor.py:124, options-bot/ml/swing_classifier_predictor.py:147
- **References**: 6 call sites

### WIRE-0224: ScalpPredictor._legacy_proba_to_signed_confidence (method)
- **File**: options-bot/ml/scalp_predictor.py:195-208
- **Called by**: options-bot/ml/scalp_predictor.py:126, options-bot/ml/scalp_predictor.py:143, options-bot/ml/scalp_predictor.py:195
- **References**: 3 call sites

### WIRE-0225: _get_feature_names (function)
- **File**: options-bot/ml/scalp_trainer.py:56-58
- **Called by**: options-bot/ml/incremental_trainer.py:417, options-bot/ml/lgbm_trainer.py:161, options-bot/ml/scalp_trainer.py:106, options-bot/ml/scalp_trainer.py:402, options-bot/ml/scalp_trainer.py:871, options-bot/ml/swing_classifier_trainer.py:54, options-bot/ml/swing_classifier_trainer.py:104, options-bot/ml/swing_classifier_trainer.py:457, options-bot/ml/swing_classifier_trainer.py:937, options-bot/ml/tft_trainer.py:124 ... (+6 more)
- **References**: 16 call sites

### WIRE-0226: _compute_all_features (function)
- **File**: options-bot/ml/scalp_trainer.py:61-112
- **Called by**: options-bot/ml/incremental_trainer.py:386, options-bot/ml/lgbm_trainer.py:197, options-bot/ml/scalp_trainer.py:450, options-bot/ml/swing_classifier_trainer.py:59, options-bot/ml/swing_classifier_trainer.py:493, options-bot/ml/tft_trainer.py:141, options-bot/ml/tft_trainer.py:813, options-bot/ml/trainer.py:93, options-bot/ml/trainer.py:456
- **References**: 9 call sites

### WIRE-0227: _calculate_binary_target (function)
- **File**: options-bot/ml/scalp_trainer.py:115-132
- **Called by**: options-bot/ml/scalp_trainer.py:468, options-bot/ml/swing_classifier_trainer.py:113, options-bot/ml/swing_classifier_trainer.py:505
- **References**: 3 call sites

### WIRE-0228: _subsample_strided (function)
- **File**: options-bot/ml/scalp_trainer.py:135-146
- **Called by**: options-bot/ml/scalp_trainer.py:492, options-bot/ml/swing_classifier_trainer.py:133, options-bot/ml/swing_classifier_trainer.py:529
- **References**: 3 call sites

### WIRE-0229: _optuna_optimize_classifier (function)
- **File**: options-bot/ml/scalp_trainer.py:149-232
- **Called by**: options-bot/ml/scalp_trainer.py:546
- **References**: 1 call sites

### WIRE-0230: _walk_forward_cv_classifier (function)
- **File**: options-bot/ml/scalp_trainer.py:235-362
- **Called by**: options-bot/ml/scalp_trainer.py:563, options-bot/ml/swing_classifier_trainer.py:301, options-bot/ml/swing_classifier_trainer.py:751
- **References**: 3 call sites

### WIRE-0231: train_scalp_model (function)
- **File**: options-bot/ml/scalp_trainer.py:365-909
- **Called by**: options-bot/backend/routes/models.py:641
- **References**: 1 call sites

### WIRE-0232: SwingClassifierPredictor (class)
- **File**: options-bot/ml/swing_classifier_predictor.py:31-159
- **Called by**: options-bot/backend/routes/models.py:206, options-bot/ml/swing_classifier_trainer.py:843, options-bot/strategies/base_strategy.py:159
- **References**: 3 call sites

### WIRE-0233: SwingClassifierPredictor.__init__ (method)
- **File**: options-bot/ml/swing_classifier_predictor.py:34-41
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0234: SwingClassifierPredictor.load (method)
- **File**: options-bot/ml/swing_classifier_predictor.py:43-58
- **Called by**: options-bot/ml/ensemble_predictor.py:66, options-bot/ml/ensemble_predictor.py:72, options-bot/ml/ensemble_predictor.py:87, options-bot/ml/ensemble_predictor.py:110, options-bot/ml/ensemble_predictor.py:187, options-bot/ml/ensemble_predictor.py:283, options-bot/ml/incremental_trainer.py:504, options-bot/ml/lgbm_predictor.py:29, options-bot/ml/lgbm_predictor.py:31, options-bot/ml/lgbm_predictor.py:34 ... (+26 more)
- **References**: 36 call sites

### WIRE-0235: SwingClassifierPredictor.save (method)
- **File**: options-bot/ml/swing_classifier_predictor.py:60-81
- **Called by**: options-bot/ml/ensemble_predictor.py:122, options-bot/ml/ensemble_predictor.py:710, options-bot/ml/incremental_trainer.py:620, options-bot/ml/lgbm_predictor.py:42, options-bot/ml/lgbm_trainer.py:285, options-bot/ml/scalp_predictor.py:67, options-bot/ml/scalp_trainer.py:698, options-bot/ml/swing_classifier_predictor.py:60, options-bot/ml/swing_classifier_trainer.py:845, options-bot/ml/tft_predictor.py:110 ... (+4 more)
- **References**: 14 call sites

### WIRE-0236: SwingClassifierPredictor.set_model (method)
- **File**: options-bot/ml/swing_classifier_predictor.py:83-86
- **Called by**: options-bot/ml/incremental_trainer.py:619, options-bot/ml/lgbm_predictor.py:53, options-bot/ml/lgbm_trainer.py:284, options-bot/ml/scalp_predictor.py:92, options-bot/ml/scalp_trainer.py:697, options-bot/ml/swing_classifier_predictor.py:83, options-bot/ml/swing_classifier_trainer.py:844, options-bot/ml/trainer.py:612, options-bot/ml/xgboost_predictor.py:49
- **References**: 9 call sites

### WIRE-0237: SwingClassifierPredictor.predict (method)
- **File**: options-bot/ml/swing_classifier_predictor.py:88-113
- **Called by**: options-bot/ml/ensemble_predictor.py:6, options-bot/ml/ensemble_predictor.py:48, options-bot/ml/ensemble_predictor.py:171, options-bot/ml/ensemble_predictor.py:176, options-bot/ml/ensemble_predictor.py:191, options-bot/ml/ensemble_predictor.py:205, options-bot/ml/ensemble_predictor.py:222, options-bot/ml/ensemble_predictor.py:261, options-bot/ml/ensemble_predictor.py:664, options-bot/ml/incremental_trainer.py:570 ... (+34 more)
- **References**: 44 call sites

### WIRE-0238: SwingClassifierPredictor.predict_batch (method)
- **File**: options-bot/ml/swing_classifier_predictor.py:115-127
- **Called by**: options-bot/ml/ensemble_predictor.py:274, options-bot/ml/ensemble_predictor.py:286, options-bot/ml/ensemble_predictor.py:289, options-bot/ml/ensemble_predictor.py:548, options-bot/ml/lgbm_predictor.py:76, options-bot/ml/predictor.py:30, options-bot/ml/scalp_predictor.py:128, options-bot/ml/swing_classifier_predictor.py:115, options-bot/ml/tft_predictor.py:237, options-bot/ml/tft_predictor.py:257 ... (+1 more)
- **References**: 11 call sites

### WIRE-0239: SwingClassifierPredictor.get_feature_names (method)
- **File**: options-bot/ml/swing_classifier_predictor.py:129-131
- **Called by**: options-bot/ml/ensemble_predictor.py:295, options-bot/ml/ensemble_predictor.py:423, options-bot/ml/ensemble_predictor.py:435, options-bot/ml/lgbm_predictor.py:85, options-bot/ml/predictor.py:43, options-bot/ml/scalp_predictor.py:159, options-bot/ml/swing_classifier_predictor.py:129, options-bot/ml/tft_predictor.py:289, options-bot/ml/xgboost_predictor.py:82, options-bot/scripts/diagnose_strategy.py:18 ... (+2 more)
- **References**: 12 call sites

### WIRE-0240: SwingClassifierPredictor.get_feature_importance (method)
- **File**: options-bot/ml/swing_classifier_predictor.py:133-138
- **Called by**: options-bot/backend/routes/models.py:182, options-bot/backend/routes/models.py:187, options-bot/backend/routes/models.py:192, options-bot/backend/routes/models.py:197, options-bot/backend/routes/models.py:202, options-bot/backend/routes/models.py:207, options-bot/backend/routes/models.py:994, options-bot/ml/ensemble_predictor.py:299, options-bot/ml/ensemble_predictor.py:311, options-bot/ml/ensemble_predictor.py:318 ... (+11 more)
- **References**: 21 call sites

### WIRE-0241: SwingClassifierPredictor.get_avg_daily_move_pct (method)
- **File**: options-bot/ml/swing_classifier_predictor.py:140-145
- **Called by**: options-bot/ml/swing_classifier_predictor.py:140, options-bot/strategies/base_strategy.py:265, options-bot/strategies/base_strategy.py:272
- **References**: 3 call sites

### WIRE-0242: SwingClassifierPredictor._binary_to_signed_confidence (method)
- **File**: options-bot/ml/swing_classifier_predictor.py:147-159
- **Called by**: options-bot/ml/scalp_predictor.py:124, options-bot/ml/scalp_predictor.py:138, options-bot/ml/scalp_predictor.py:177, options-bot/ml/swing_classifier_predictor.py:113, options-bot/ml/swing_classifier_predictor.py:124, options-bot/ml/swing_classifier_predictor.py:147
- **References**: 6 call sites

### WIRE-0243: _get_feature_names (function)
- **File**: options-bot/ml/swing_classifier_trainer.py:54-56
- **Called by**: options-bot/ml/incremental_trainer.py:417, options-bot/ml/lgbm_trainer.py:161, options-bot/ml/scalp_trainer.py:56, options-bot/ml/scalp_trainer.py:106, options-bot/ml/scalp_trainer.py:402, options-bot/ml/scalp_trainer.py:871, options-bot/ml/swing_classifier_trainer.py:104, options-bot/ml/swing_classifier_trainer.py:457, options-bot/ml/swing_classifier_trainer.py:937, options-bot/ml/tft_trainer.py:124 ... (+6 more)
- **References**: 16 call sites

### WIRE-0244: _compute_all_features (function)
- **File**: options-bot/ml/swing_classifier_trainer.py:59-110
- **Called by**: options-bot/ml/incremental_trainer.py:386, options-bot/ml/lgbm_trainer.py:197, options-bot/ml/scalp_trainer.py:61, options-bot/ml/scalp_trainer.py:450, options-bot/ml/swing_classifier_trainer.py:493, options-bot/ml/tft_trainer.py:141, options-bot/ml/tft_trainer.py:813, options-bot/ml/trainer.py:93, options-bot/ml/trainer.py:456
- **References**: 9 call sites

### WIRE-0245: _calculate_binary_target (function)
- **File**: options-bot/ml/swing_classifier_trainer.py:113-130
- **Called by**: options-bot/ml/scalp_trainer.py:115, options-bot/ml/scalp_trainer.py:468, options-bot/ml/swing_classifier_trainer.py:505
- **References**: 3 call sites

### WIRE-0246: _subsample_strided (function)
- **File**: options-bot/ml/swing_classifier_trainer.py:133-141
- **Called by**: options-bot/ml/scalp_trainer.py:135, options-bot/ml/scalp_trainer.py:492, options-bot/ml/swing_classifier_trainer.py:529
- **References**: 3 call sites

### WIRE-0247: _optuna_optimize_xgb_classifier (function)
- **File**: options-bot/ml/swing_classifier_trainer.py:144-220
- **Called by**: options-bot/ml/swing_classifier_trainer.py:736
- **References**: 1 call sites

### WIRE-0248: _optuna_optimize_lgbm_classifier (function)
- **File**: options-bot/ml/swing_classifier_trainer.py:223-298
- **Called by**: options-bot/ml/swing_classifier_trainer.py:730
- **References**: 1 call sites

### WIRE-0249: _walk_forward_cv_classifier (function)
- **File**: options-bot/ml/swing_classifier_trainer.py:301-444
- **Called by**: options-bot/ml/scalp_trainer.py:235, options-bot/ml/scalp_trainer.py:563, options-bot/ml/swing_classifier_trainer.py:751
- **References**: 3 call sites

### WIRE-0250: _prepare_training_data (function)
- **File**: options-bot/ml/swing_classifier_trainer.py:447-569
- **Called by**: options-bot/ml/swing_classifier_trainer.py:717
- **References**: 1 call sites

### WIRE-0251: _save_to_db (function)
- **File**: options-bot/ml/swing_classifier_trainer.py:572-669
- **Called by**: options-bot/ml/ensemble_predictor.py:729, options-bot/ml/ensemble_predictor.py:759, options-bot/ml/ensemble_predictor.py:763, options-bot/ml/lgbm_trainer.py:335, options-bot/ml/lgbm_trainer.py:362, options-bot/ml/scalp_trainer.py:795, options-bot/ml/scalp_trainer.py:824, options-bot/ml/swing_classifier_trainer.py:918, options-bot/ml/trainer.py:669, options-bot/ml/trainer.py:700
- **References**: 10 call sites

### WIRE-0252: train_swing_classifier_model (function)
- **File**: options-bot/ml/swing_classifier_trainer.py:672-974
- **Called by**: options-bot/backend/routes/models.py:590
- **References**: 1 call sites

### WIRE-0253: TFTPredictor (class)
- **File**: options-bot/ml/tft_predictor.py:37-501
- **Called by**: options-bot/backend/routes/models.py:186, options-bot/ml/ensemble_predictor.py:101, options-bot/ml/ensemble_predictor.py:428, options-bot/ml/tft_trainer.py:975, options-bot/strategies/base_strategy.py:147
- **References**: 5 call sites

### WIRE-0254: TFTPredictor.__init__ (method)
- **File**: options-bot/ml/tft_predictor.py:47-57
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0255: TFTPredictor.load (method)
- **File**: options-bot/ml/tft_predictor.py:63-108
- **Called by**: options-bot/ml/ensemble_predictor.py:66, options-bot/ml/ensemble_predictor.py:72, options-bot/ml/ensemble_predictor.py:87, options-bot/ml/ensemble_predictor.py:110, options-bot/ml/ensemble_predictor.py:187, options-bot/ml/ensemble_predictor.py:283, options-bot/ml/incremental_trainer.py:504, options-bot/ml/lgbm_predictor.py:29, options-bot/ml/lgbm_predictor.py:31, options-bot/ml/lgbm_predictor.py:34 ... (+26 more)
- **References**: 36 call sites

### WIRE-0256: TFTPredictor.save (method)
- **File**: options-bot/ml/tft_predictor.py:110-172
- **Called by**: options-bot/ml/ensemble_predictor.py:122, options-bot/ml/ensemble_predictor.py:710, options-bot/ml/incremental_trainer.py:620, options-bot/ml/lgbm_predictor.py:42, options-bot/ml/lgbm_trainer.py:285, options-bot/ml/scalp_predictor.py:67, options-bot/ml/scalp_trainer.py:698, options-bot/ml/swing_classifier_predictor.py:60, options-bot/ml/swing_classifier_trainer.py:845, options-bot/ml/tft_predictor.py:110 ... (+4 more)
- **References**: 14 call sites

### WIRE-0257: TFTPredictor.predict (method)
- **File**: options-bot/ml/tft_predictor.py:178-235
- **Called by**: options-bot/ml/ensemble_predictor.py:6, options-bot/ml/ensemble_predictor.py:48, options-bot/ml/ensemble_predictor.py:171, options-bot/ml/ensemble_predictor.py:176, options-bot/ml/ensemble_predictor.py:191, options-bot/ml/ensemble_predictor.py:205, options-bot/ml/ensemble_predictor.py:222, options-bot/ml/ensemble_predictor.py:261, options-bot/ml/ensemble_predictor.py:664, options-bot/ml/incremental_trainer.py:570 ... (+34 more)
- **References**: 44 call sites

### WIRE-0258: TFTPredictor.predict_batch (method)
- **File**: options-bot/ml/tft_predictor.py:237-283
- **Called by**: options-bot/ml/ensemble_predictor.py:274, options-bot/ml/ensemble_predictor.py:286, options-bot/ml/ensemble_predictor.py:289, options-bot/ml/ensemble_predictor.py:548, options-bot/ml/lgbm_predictor.py:76, options-bot/ml/predictor.py:30, options-bot/ml/scalp_predictor.py:128, options-bot/ml/swing_classifier_predictor.py:115, options-bot/ml/tft_predictor.py:237, options-bot/ml/tft_predictor.py:257 ... (+1 more)
- **References**: 11 call sites

### WIRE-0259: TFTPredictor.get_feature_names (method)
- **File**: options-bot/ml/tft_predictor.py:289-291
- **Called by**: options-bot/ml/ensemble_predictor.py:295, options-bot/ml/ensemble_predictor.py:423, options-bot/ml/ensemble_predictor.py:435, options-bot/ml/lgbm_predictor.py:85, options-bot/ml/predictor.py:43, options-bot/ml/scalp_predictor.py:159, options-bot/ml/swing_classifier_predictor.py:129, options-bot/ml/tft_predictor.py:289, options-bot/ml/xgboost_predictor.py:82, options-bot/scripts/diagnose_strategy.py:18 ... (+2 more)
- **References**: 12 call sites

### WIRE-0260: TFTPredictor.get_feature_importance (method)
- **File**: options-bot/ml/tft_predictor.py:293-329
- **Called by**: options-bot/backend/routes/models.py:182, options-bot/backend/routes/models.py:187, options-bot/backend/routes/models.py:192, options-bot/backend/routes/models.py:197, options-bot/backend/routes/models.py:202, options-bot/backend/routes/models.py:207, options-bot/backend/routes/models.py:994, options-bot/ml/ensemble_predictor.py:299, options-bot/ml/ensemble_predictor.py:311, options-bot/ml/ensemble_predictor.py:318 ... (+11 more)
- **References**: 21 call sites

### WIRE-0261: TFTPredictor._build_inference_df (method)
- **File**: options-bot/ml/tft_predictor.py:335-366
- **Called by**: options-bot/ml/tft_predictor.py:219, options-bot/ml/tft_predictor.py:313, options-bot/ml/tft_predictor.py:335
- **References**: 3 call sites

### WIRE-0262: TFTPredictor._run_tft_inference (method)
- **File**: options-bot/ml/tft_predictor.py:368-433
- **Called by**: options-bot/ml/tft_predictor.py:222, options-bot/ml/tft_predictor.py:368
- **References**: 2 call sites

### WIRE-0263: TFTPredictor._extract_variable_importance (method)
- **File**: options-bot/ml/tft_predictor.py:435-501
- **Called by**: options-bot/ml/tft_predictor.py:321, options-bot/ml/tft_predictor.py:435
- **References**: 2 call sites

### WIRE-0264: _make_strided_loader (function)
- **File**: options-bot/ml/tft_trainer.py:72-98
- **Called by**: options-bot/ml/tft_trainer.py:421, options-bot/ml/tft_trainer.py:422, options-bot/ml/tft_trainer.py:897
- **References**: 3 call sites

### WIRE-0265: _make_epoch_logger (function)
- **File**: options-bot/ml/tft_trainer.py:101-117
- **Called by**: options-bot/ml/tft_trainer.py:444, options-bot/ml/tft_trainer.py:919
- **References**: 2 call sites

### WIRE-0266: _get_feature_names (function)
- **File**: options-bot/ml/tft_trainer.py:124-138
- **Called by**: options-bot/ml/incremental_trainer.py:417, options-bot/ml/lgbm_trainer.py:161, options-bot/ml/scalp_trainer.py:56, options-bot/ml/scalp_trainer.py:106, options-bot/ml/scalp_trainer.py:402, options-bot/ml/scalp_trainer.py:871, options-bot/ml/swing_classifier_trainer.py:54, options-bot/ml/swing_classifier_trainer.py:104, options-bot/ml/swing_classifier_trainer.py:457, options-bot/ml/swing_classifier_trainer.py:937 ... (+6 more)
- **References**: 16 call sites

### WIRE-0267: _compute_all_features (function)
- **File**: options-bot/ml/tft_trainer.py:141-192
- **Called by**: options-bot/ml/incremental_trainer.py:386, options-bot/ml/lgbm_trainer.py:197, options-bot/ml/scalp_trainer.py:61, options-bot/ml/scalp_trainer.py:450, options-bot/ml/swing_classifier_trainer.py:59, options-bot/ml/swing_classifier_trainer.py:493, options-bot/ml/tft_trainer.py:813, options-bot/ml/trainer.py:93, options-bot/ml/trainer.py:456
- **References**: 9 call sites

### WIRE-0268: _prediction_horizon_to_bars (function)
- **File**: options-bot/ml/tft_trainer.py:195-223
- **Called by**: options-bot/ml/ensemble_predictor.py:524, options-bot/ml/incremental_trainer.py:405, options-bot/ml/lgbm_trainer.py:160, options-bot/ml/tft_trainer.py:771, options-bot/ml/trainer.py:48, options-bot/ml/trainer.py:413
- **References**: 6 call sites

### WIRE-0269: _build_sequence_df (function)
- **File**: options-bot/ml/tft_trainer.py:230-327
- **Called by**: options-bot/ml/ensemble_predictor.py:565, options-bot/ml/tft_trainer.py:351, options-bot/ml/tft_trainer.py:828
- **References**: 3 call sites

### WIRE-0270: _walk_forward_cv_tft (function)
- **File**: options-bot/ml/tft_trainer.py:334-542
- **Called by**: options-bot/ml/tft_trainer.py:865
- **References**: 1 call sites

### WIRE-0271: _build_timeseries_dataset (function)
- **File**: options-bot/ml/tft_trainer.py:545-585
- **Called by**: options-bot/ml/tft_trainer.py:413, options-bot/ml/tft_trainer.py:414, options-bot/ml/tft_trainer.py:620, options-bot/ml/tft_trainer.py:891
- **References**: 4 call sites

### WIRE-0272: predict_dataset (function)
- **File**: options-bot/ml/tft_trainer.py:592-655
- **Called by**: options-bot/ml/ensemble_predictor.py:373, options-bot/ml/tft_predictor.py:250, options-bot/ml/tft_predictor.py:258
- **References**: 3 call sites

### WIRE-0273: _save_tft_model_to_db (function)
- **File**: options-bot/ml/tft_trainer.py:662-717
- **Called by**: options-bot/ml/tft_trainer.py:1003
- **References**: 1 call sites

### WIRE-0274: train_tft_model (function)
- **File**: options-bot/ml/tft_trainer.py:724-1081
- **Called by**: options-bot/backend/routes/models.py:371
- **References**: 1 call sites

### WIRE-0275: _prediction_horizon_to_bars (function)
- **File**: options-bot/ml/trainer.py:48-77
- **Called by**: options-bot/ml/ensemble_predictor.py:524, options-bot/ml/incremental_trainer.py:405, options-bot/ml/lgbm_trainer.py:160, options-bot/ml/tft_trainer.py:195, options-bot/ml/tft_trainer.py:771, options-bot/ml/trainer.py:413
- **References**: 6 call sites

### WIRE-0276: _get_feature_names (function)
- **File**: options-bot/ml/trainer.py:80-90
- **Called by**: options-bot/ml/incremental_trainer.py:417, options-bot/ml/lgbm_trainer.py:161, options-bot/ml/scalp_trainer.py:56, options-bot/ml/scalp_trainer.py:106, options-bot/ml/scalp_trainer.py:402, options-bot/ml/scalp_trainer.py:871, options-bot/ml/swing_classifier_trainer.py:54, options-bot/ml/swing_classifier_trainer.py:104, options-bot/ml/swing_classifier_trainer.py:457, options-bot/ml/swing_classifier_trainer.py:937 ... (+6 more)
- **References**: 16 call sites

### WIRE-0277: _compute_all_features (function)
- **File**: options-bot/ml/trainer.py:93-151
- **Called by**: options-bot/ml/incremental_trainer.py:386, options-bot/ml/lgbm_trainer.py:197, options-bot/ml/scalp_trainer.py:61, options-bot/ml/scalp_trainer.py:450, options-bot/ml/swing_classifier_trainer.py:59, options-bot/ml/swing_classifier_trainer.py:493, options-bot/ml/tft_trainer.py:141, options-bot/ml/tft_trainer.py:813, options-bot/ml/trainer.py:456
- **References**: 9 call sites

### WIRE-0278: _calculate_target (function)
- **File**: options-bot/ml/trainer.py:154-161
- **Called by**: options-bot/ml/ensemble_predictor.py:527, options-bot/ml/incremental_trainer.py:420, options-bot/ml/lgbm_trainer.py:206, options-bot/ml/trainer.py:467
- **References**: 4 call sites

### WIRE-0279: _optuna_optimize (function)
- **File**: options-bot/ml/trainer.py:164-246
- **Called by**: options-bot/ml/trainer.py:555
- **References**: 1 call sites

### WIRE-0280: _walk_forward_cv (function)
- **File**: options-bot/ml/trainer.py:249-367
- **Called by**: options-bot/ml/tft_trainer.py:342, options-bot/ml/trainer.py:526
- **References**: 2 call sites

### WIRE-0281: train_model (function)
- **File**: options-bot/ml/trainer.py:370-811
- **Called by**: options-bot/backend/routes/models.py:266, options-bot/backend/routes/models.py:279, options-bot/ml/lgbm_trainer.py:132, options-bot/ml/tft_trainer.py:733, options-bot/scripts/train_model.py:95, options-bot/scripts/walk_forward_backtest.py:190
- **References**: 6 call sites

### WIRE-0282: XGBoostPredictor (class)
- **File**: options-bot/ml/xgboost_predictor.py:18-91
- **Called by**: options-bot/backend/routes/models.py:181, options-bot/ml/ensemble_predictor.py:100, options-bot/ml/ensemble_predictor.py:421, options-bot/ml/incremental_trainer.py:618, options-bot/ml/trainer.py:611, options-bot/scripts/diagnose_strategy.py:17, options-bot/strategies/base_strategy.py:162, options-bot/strategies/base_strategy.py:170
- **References**: 8 call sites

### WIRE-0283: XGBoostPredictor.__init__ (method)
- **File**: options-bot/ml/xgboost_predictor.py:21-25
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0284: XGBoostPredictor.load (method)
- **File**: options-bot/ml/xgboost_predictor.py:27-36
- **Called by**: options-bot/ml/ensemble_predictor.py:66, options-bot/ml/ensemble_predictor.py:72, options-bot/ml/ensemble_predictor.py:87, options-bot/ml/ensemble_predictor.py:110, options-bot/ml/ensemble_predictor.py:187, options-bot/ml/ensemble_predictor.py:283, options-bot/ml/incremental_trainer.py:504, options-bot/ml/lgbm_predictor.py:29, options-bot/ml/lgbm_predictor.py:31, options-bot/ml/lgbm_predictor.py:34 ... (+26 more)
- **References**: 36 call sites

### WIRE-0285: XGBoostPredictor.save (method)
- **File**: options-bot/ml/xgboost_predictor.py:38-47
- **Called by**: options-bot/ml/ensemble_predictor.py:122, options-bot/ml/ensemble_predictor.py:710, options-bot/ml/incremental_trainer.py:620, options-bot/ml/lgbm_predictor.py:42, options-bot/ml/lgbm_trainer.py:285, options-bot/ml/scalp_predictor.py:67, options-bot/ml/scalp_trainer.py:698, options-bot/ml/swing_classifier_predictor.py:60, options-bot/ml/swing_classifier_trainer.py:845, options-bot/ml/tft_predictor.py:110 ... (+4 more)
- **References**: 14 call sites

### WIRE-0286: XGBoostPredictor.set_model (method)
- **File**: options-bot/ml/xgboost_predictor.py:49-52
- **Called by**: options-bot/ml/incremental_trainer.py:619, options-bot/ml/lgbm_predictor.py:53, options-bot/ml/lgbm_trainer.py:284, options-bot/ml/scalp_predictor.py:92, options-bot/ml/scalp_trainer.py:697, options-bot/ml/swing_classifier_predictor.py:83, options-bot/ml/swing_classifier_trainer.py:844, options-bot/ml/trainer.py:612, options-bot/ml/xgboost_predictor.py:49
- **References**: 9 call sites

### WIRE-0287: XGBoostPredictor.predict (method)
- **File**: options-bot/ml/xgboost_predictor.py:54-70
- **Called by**: options-bot/ml/ensemble_predictor.py:6, options-bot/ml/ensemble_predictor.py:48, options-bot/ml/ensemble_predictor.py:171, options-bot/ml/ensemble_predictor.py:176, options-bot/ml/ensemble_predictor.py:191, options-bot/ml/ensemble_predictor.py:205, options-bot/ml/ensemble_predictor.py:222, options-bot/ml/ensemble_predictor.py:261, options-bot/ml/ensemble_predictor.py:664, options-bot/ml/incremental_trainer.py:570 ... (+34 more)
- **References**: 44 call sites

### WIRE-0288: XGBoostPredictor.predict_batch (method)
- **File**: options-bot/ml/xgboost_predictor.py:72-80
- **Called by**: options-bot/ml/ensemble_predictor.py:274, options-bot/ml/ensemble_predictor.py:286, options-bot/ml/ensemble_predictor.py:289, options-bot/ml/ensemble_predictor.py:548, options-bot/ml/lgbm_predictor.py:76, options-bot/ml/predictor.py:30, options-bot/ml/scalp_predictor.py:128, options-bot/ml/swing_classifier_predictor.py:115, options-bot/ml/tft_predictor.py:237, options-bot/ml/tft_predictor.py:257 ... (+1 more)
- **References**: 11 call sites

### WIRE-0289: XGBoostPredictor.get_feature_names (method)
- **File**: options-bot/ml/xgboost_predictor.py:82-84
- **Called by**: options-bot/ml/ensemble_predictor.py:295, options-bot/ml/ensemble_predictor.py:423, options-bot/ml/ensemble_predictor.py:435, options-bot/ml/lgbm_predictor.py:85, options-bot/ml/predictor.py:43, options-bot/ml/scalp_predictor.py:159, options-bot/ml/swing_classifier_predictor.py:129, options-bot/ml/tft_predictor.py:289, options-bot/ml/xgboost_predictor.py:82, options-bot/scripts/diagnose_strategy.py:18 ... (+2 more)
- **References**: 12 call sites

### WIRE-0290: XGBoostPredictor.get_feature_importance (method)
- **File**: options-bot/ml/xgboost_predictor.py:86-91
- **Called by**: options-bot/backend/routes/models.py:182, options-bot/backend/routes/models.py:187, options-bot/backend/routes/models.py:192, options-bot/backend/routes/models.py:197, options-bot/backend/routes/models.py:202, options-bot/backend/routes/models.py:207, options-bot/backend/routes/models.py:994, options-bot/ml/ensemble_predictor.py:299, options-bot/ml/ensemble_predictor.py:311, options-bot/ml/ensemble_predictor.py:318 ... (+11 more)
- **References**: 21 call sites

### WIRE-0291: compute_stock_features (function)
- **File**: options-bot/ml/feature_engineering/base_features.py:30-200
- **Called by**: options-bot/ml/feature_engineering/base_features.py:456, options-bot/scripts/test_features.py:56
- **References**: 2 call sites

### WIRE-0292: compute_options_features (function)
- **File**: options-bot/ml/feature_engineering/base_features.py:203-425
- **Called by**: options-bot/data/options_data_fetcher.py:7, options-bot/data/options_data_fetcher.py:190, options-bot/data/options_data_fetcher.py:347, options-bot/ml/feature_engineering/base_features.py:460
- **References**: 4 call sites

### WIRE-0293: compute_base_features (function)
- **File**: options-bot/ml/feature_engineering/base_features.py:428-546
- **Called by**: options-bot/data/vix_provider.py:131, options-bot/ml/ensemble_predictor.py:506, options-bot/ml/scalp_trainer.py:100, options-bot/ml/swing_classifier_trainer.py:98, options-bot/ml/tft_trainer.py:184, options-bot/ml/trainer.py:134, options-bot/ml/feature_engineering/base_features.py:14, options-bot/scripts/diagnose_strategy.py:39, options-bot/scripts/test_features.py:113, options-bot/scripts/test_features.py:151 ... (+2 more)
- **References**: 12 call sites

### WIRE-0294: get_base_feature_names (function)
- **File**: options-bot/ml/feature_engineering/base_features.py:549-585
- **Called by**: options-bot/ml/scalp_trainer.py:58, options-bot/ml/swing_classifier_trainer.py:56, options-bot/ml/tft_trainer.py:130, options-bot/ml/trainer.py:82, options-bot/scripts/audit_verify.py:223, options-bot/scripts/audit_verify.py:225, options-bot/scripts/audit_verify.py:235, options-bot/scripts/test_features.py:179, options-bot/scripts/validate_model.py:39
- **References**: 9 call sites

### WIRE-0295: compute_general_features (function)
- **File**: options-bot/ml/feature_engineering/general_features.py:17-78
- **Called by**: options-bot/ml/ensemble_predictor.py:510, options-bot/ml/tft_trainer.py:188, options-bot/ml/trainer.py:140, options-bot/scripts/test_features.py:152, options-bot/strategies/base_strategy.py:875, options-bot/strategies/base_strategy.py:1251
- **References**: 6 call sites

### WIRE-0296: get_general_feature_names (function)
- **File**: options-bot/ml/feature_engineering/general_features.py:81-88
- **Called by**: options-bot/ml/tft_trainer.py:134, options-bot/ml/trainer.py:86, options-bot/scripts/test_features.py:154, options-bot/scripts/test_features.py:181, options-bot/scripts/validate_model.py:43
- **References**: 5 call sites

### WIRE-0297: compute_scalp_features (function)
- **File**: options-bot/ml/feature_engineering/scalp_features.py:21-172
- **Called by**: options-bot/ml/scalp_trainer.py:103, options-bot/ml/tft_trainer.py:191, options-bot/ml/trainer.py:142, options-bot/strategies/base_strategy.py:878, options-bot/strategies/base_strategy.py:1254
- **References**: 5 call sites

### WIRE-0298: get_scalp_feature_names (function)
- **File**: options-bot/ml/feature_engineering/scalp_features.py:175-193
- **Called by**: options-bot/ml/scalp_trainer.py:58, options-bot/ml/tft_trainer.py:137, options-bot/ml/trainer.py:88, options-bot/scripts/validate_model.py:45
- **References**: 4 call sites

### WIRE-0299: compute_swing_features (function)
- **File**: options-bot/ml/feature_engineering/swing_features.py:17-86
- **Called by**: options-bot/ml/ensemble_predictor.py:508, options-bot/ml/swing_classifier_trainer.py:101, options-bot/ml/tft_trainer.py:186, options-bot/ml/trainer.py:138, options-bot/scripts/diagnose_strategy.py:40, options-bot/scripts/test_features.py:114, options-bot/strategies/base_strategy.py:872, options-bot/strategies/base_strategy.py:1248
- **References**: 8 call sites

### WIRE-0300: get_swing_feature_names (function)
- **File**: options-bot/ml/feature_engineering/swing_features.py:89-97
- **Called by**: options-bot/ml/swing_classifier_trainer.py:56, options-bot/ml/tft_trainer.py:132, options-bot/ml/trainer.py:84, options-bot/scripts/test_features.py:116, options-bot/scripts/test_features.py:180, options-bot/scripts/validate_model.py:41
- **References**: 6 call sites

### WIRE-0301: RiskManager (class)
- **File**: options-bot/risk/risk_manager.py:33-645
- **Called by**: options-bot/strategies/base_strategy.py:177
- **References**: 1 call sites

### WIRE-0302: RiskManager.__init__ (method)
- **File**: options-bot/risk/risk_manager.py:42-48
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0303: RiskManager._start_async_loop (method)
- **File**: options-bot/risk/risk_manager.py:54-60
- **Called by**: options-bot/risk/risk_manager.py:47, options-bot/risk/risk_manager.py:54
- **References**: 2 call sites

### WIRE-0304: RiskManager._run_async (method)
- **File**: options-bot/risk/risk_manager.py:62-69
- **Called by**: options-bot/ml/incremental_trainer.py:69, options-bot/ml/incremental_trainer.py:113, options-bot/ml/incremental_trainer.py:141, options-bot/ml/incremental_trainer.py:205, options-bot/ml/lgbm_trainer.py:302, options-bot/ml/lgbm_trainer.py:362, options-bot/ml/scalp_trainer.py:743, options-bot/ml/scalp_trainer.py:824, options-bot/ml/swing_classifier_trainer.py:590, options-bot/ml/swing_classifier_trainer.py:633 ... (+10 more)
- **References**: 20 call sites

### WIRE-0305: RiskManager.get_day_trade_count (method)
- **File**: options-bot/risk/risk_manager.py:76-106
- **Called by**: options-bot/risk/risk_manager.py:76, options-bot/risk/risk_manager.py:118
- **References**: 2 call sites

### WIRE-0306: RiskManager.check_pdt_limit (method)
- **File**: options-bot/risk/risk_manager.py:108-124
- **Called by**: options-bot/risk/risk_manager.py:108, options-bot/risk/risk_manager.py:130, options-bot/risk/risk_manager.py:139, options-bot/risk/risk_manager.py:458
- **References**: 4 call sites

### WIRE-0307: RiskManager.check_pdt (method)
- **File**: options-bot/risk/risk_manager.py:126-140
- **Called by**: options-bot/risk/risk_manager.py:126, options-bot/strategies/base_strategy.py:1593
- **References**: 2 call sites

### WIRE-0308: RiskManager.get_open_position_count (method)
- **File**: options-bot/risk/risk_manager.py:147-165
- **Called by**: options-bot/risk/risk_manager.py:147, options-bot/risk/risk_manager.py:184
- **References**: 2 call sites

### WIRE-0309: RiskManager.check_position_limits (method)
- **File**: options-bot/risk/risk_manager.py:167-204
- **Called by**: options-bot/risk/risk_manager.py:167, options-bot/risk/risk_manager.py:463
- **References**: 2 call sites

### WIRE-0310: RiskManager._get_profile_open_count (method)
- **File**: options-bot/risk/risk_manager.py:206-225
- **Called by**: options-bot/risk/risk_manager.py:191, options-bot/risk/risk_manager.py:206
- **References**: 2 call sites

### WIRE-0311: RiskManager.check_portfolio_exposure (method)
- **File**: options-bot/risk/risk_manager.py:232-301
- **Called by**: options-bot/risk/risk_manager.py:199, options-bot/risk/risk_manager.py:232, options-bot/strategies/base_strategy.py:449
- **References**: 3 call sites

### WIRE-0312: RiskManager.check_emergency_stop_loss (method)
- **File**: options-bot/risk/risk_manager.py:308-373
- **Called by**: options-bot/risk/risk_manager.py:308, options-bot/strategies/base_strategy.py:404
- **References**: 2 call sites

### WIRE-0313: RiskManager.calculate_position_size (method)
- **File**: options-bot/risk/risk_manager.py:380-432
- **Called by**: options-bot/risk/risk_manager.py:380, options-bot/risk/risk_manager.py:479
- **References**: 2 call sites

### WIRE-0314: RiskManager.check_can_open_position (method)
- **File**: options-bot/risk/risk_manager.py:438-489
- **Called by**: options-bot/risk/risk_manager.py:438, options-bot/strategies/base_strategy.py:1871
- **References**: 2 call sites

### WIRE-0315: RiskManager._get_profile_daily_trade_count (method)
- **File**: options-bot/risk/risk_manager.py:491-509
- **Called by**: options-bot/risk/risk_manager.py:469, options-bot/risk/risk_manager.py:491
- **References**: 2 call sites

### WIRE-0316: RiskManager.log_trade_open (method)
- **File**: options-bot/risk/risk_manager.py:516-565
- **Called by**: options-bot/risk/risk_manager.py:516, options-bot/strategies/base_strategy.py:1559, options-bot/strategies/base_strategy.py:1980
- **References**: 3 call sites

### WIRE-0317: RiskManager.log_trade_close (method)
- **File**: options-bot/risk/risk_manager.py:567-610
- **Called by**: options-bot/ml/feedback_queue.py:31, options-bot/risk/risk_manager.py:567, options-bot/strategies/base_strategy.py:970
- **References**: 3 call sites

### WIRE-0318: RiskManager.get_portfolio_greeks (method)
- **File**: options-bot/risk/risk_manager.py:616-645
- **Called by**: options-bot/risk/risk_manager.py:616, options-bot/strategies/base_strategy.py:1844
- **References**: 2 call sites

### WIRE-0319: check (function)
- **File**: options-bot/scripts/audit_verify.py:20-33
- **Called by**: options-bot/ml/regime_adjuster.py:10, options-bot/scripts/audit_verify.py:48, options-bot/scripts/audit_verify.py:53, options-bot/scripts/audit_verify.py:67, options-bot/scripts/audit_verify.py:79, options-bot/scripts/audit_verify.py:85, options-bot/scripts/audit_verify.py:97, options-bot/scripts/audit_verify.py:112, options-bot/scripts/audit_verify.py:118, options-bot/scripts/audit_verify.py:132 ... (+40 more)
- **References**: 50 call sites

### WIRE-0320: section (function)
- **File**: options-bot/scripts/audit_verify.py:35-38
- **Called by**: options-bot/scripts/audit_verify.py:45, options-bot/scripts/audit_verify.py:76, options-bot/scripts/audit_verify.py:109, options-bot/scripts/audit_verify.py:159, options-bot/scripts/audit_verify.py:186, options-bot/scripts/audit_verify.py:217, options-bot/scripts/audit_verify.py:240, options-bot/scripts/startup_check.py:62, options-bot/scripts/startup_check.py:71, options-bot/scripts/startup_check.py:84 ... (+7 more)
- **References**: 17 call sites

### WIRE-0321: _setup_logging (function)
- **File**: options-bot/scripts/backtest.py:39-60
- **Called by**: options-bot/scripts/backtest.py:287
- **References**: 1 call sites

### WIRE-0322: run_backtest (function)
- **File**: options-bot/scripts/backtest.py:63-250
- **Called by**: options-bot/backend/app.py:103, options-bot/scripts/backtest.py:155, options-bot/scripts/backtest.py:156, options-bot/scripts/backtest.py:276, options-bot/scripts/walk_forward_backtest.py:218
- **References**: 5 call sites

### WIRE-0323: main (function)
- **File**: options-bot/scripts/backtest.py:253-283
- **Called by**: options-bot/main.py:425, options-bot/main.py:588, options-bot/scripts/backtest.py:288, options-bot/scripts/test_features.py:215, options-bot/scripts/test_features.py:240, options-bot/scripts/test_providers.py:155, options-bot/scripts/test_providers.py:179, options-bot/scripts/train_model.py:62, options-bot/scripts/train_model.py:115, options-bot/scripts/validate_data.py:649 ... (+3 more)
- **References**: 13 call sites

### WIRE-0324: check (function)
- **File**: options-bot/scripts/startup_check.py:46-59
- **Called by**: options-bot/ml/regime_adjuster.py:10, options-bot/scripts/audit_verify.py:20, options-bot/scripts/audit_verify.py:48, options-bot/scripts/audit_verify.py:53, options-bot/scripts/audit_verify.py:67, options-bot/scripts/audit_verify.py:79, options-bot/scripts/audit_verify.py:85, options-bot/scripts/audit_verify.py:97, options-bot/scripts/audit_verify.py:112, options-bot/scripts/audit_verify.py:118 ... (+40 more)
- **References**: 50 call sites

### WIRE-0325: section (function)
- **File**: options-bot/scripts/startup_check.py:62-65
- **Called by**: options-bot/scripts/audit_verify.py:35, options-bot/scripts/audit_verify.py:45, options-bot/scripts/audit_verify.py:76, options-bot/scripts/audit_verify.py:109, options-bot/scripts/audit_verify.py:159, options-bot/scripts/audit_verify.py:186, options-bot/scripts/audit_verify.py:217, options-bot/scripts/audit_verify.py:240, options-bot/scripts/startup_check.py:71, options-bot/scripts/startup_check.py:84 ... (+7 more)
- **References**: 17 call sites

### WIRE-0326: test_stock_features (function)
- **File**: options-bot/scripts/test_features.py:32-88
- **Called by**: options-bot/scripts/test_features.py:221
- **References**: 1 call sites

### WIRE-0327: test_swing_features (function)
- **File**: options-bot/scripts/test_features.py:91-127
- **Called by**: options-bot/scripts/test_features.py:222
- **References**: 1 call sites

### WIRE-0328: test_general_features (function)
- **File**: options-bot/scripts/test_features.py:130-165
- **Called by**: options-bot/scripts/test_features.py:223
- **References**: 1 call sites

### WIRE-0329: test_full_feature_count (function)
- **File**: options-bot/scripts/test_features.py:168-212
- **Called by**: options-bot/scripts/test_features.py:220
- **References**: 1 call sites

### WIRE-0330: main (function)
- **File**: options-bot/scripts/test_features.py:215-236
- **Called by**: options-bot/main.py:425, options-bot/main.py:588, options-bot/scripts/backtest.py:253, options-bot/scripts/backtest.py:288, options-bot/scripts/test_features.py:240, options-bot/scripts/test_providers.py:155, options-bot/scripts/test_providers.py:179, options-bot/scripts/train_model.py:62, options-bot/scripts/train_model.py:115, options-bot/scripts/validate_data.py:649 ... (+3 more)
- **References**: 13 call sites

### WIRE-0331: test_alpaca_provider (function)
- **File**: options-bot/scripts/test_providers.py:29-79
- **Called by**: options-bot/scripts/test_providers.py:160
- **References**: 1 call sites

### WIRE-0332: test_theta_provider (function)
- **File**: options-bot/scripts/test_providers.py:82-152
- **Called by**: options-bot/scripts/test_providers.py:161
- **References**: 1 call sites

### WIRE-0333: main (function)
- **File**: options-bot/scripts/test_providers.py:155-175
- **Called by**: options-bot/main.py:425, options-bot/main.py:588, options-bot/scripts/backtest.py:253, options-bot/scripts/backtest.py:288, options-bot/scripts/test_features.py:215, options-bot/scripts/test_features.py:240, options-bot/scripts/test_providers.py:179, options-bot/scripts/train_model.py:62, options-bot/scripts/train_model.py:115, options-bot/scripts/validate_data.py:649 ... (+3 more)
- **References**: 13 call sites

### WIRE-0334: get_profile_config (function)
- **File**: options-bot/scripts/train_model.py:37-59
- **Called by**: options-bot/scripts/train_model.py:74
- **References**: 1 call sites

### WIRE-0335: main (function)
- **File**: options-bot/scripts/train_model.py:62-111
- **Called by**: options-bot/main.py:425, options-bot/main.py:588, options-bot/scripts/backtest.py:253, options-bot/scripts/backtest.py:288, options-bot/scripts/test_features.py:215, options-bot/scripts/test_features.py:240, options-bot/scripts/test_providers.py:155, options-bot/scripts/test_providers.py:179, options-bot/scripts/train_model.py:115, options-bot/scripts/validate_data.py:649 ... (+3 more)
- **References**: 13 call sites

### WIRE-0336: record (function)
- **File**: options-bot/scripts/validate_data.py:51-56
- **Called by**: options-bot/ml/incremental_trainer.py:407, options-bot/scripts/validate_data.py:73, options-bot/scripts/validate_data.py:82, options-bot/scripts/validate_data.py:92, options-bot/scripts/validate_data.py:101, options-bot/scripts/validate_data.py:104, options-bot/scripts/validate_data.py:142, options-bot/scripts/validate_data.py:150, options-bot/scripts/validate_data.py:166, options-bot/scripts/validate_data.py:187 ... (+30 more)
- **References**: 40 call sites

### WIRE-0337: test_alpaca_connection (function)
- **File**: options-bot/scripts/validate_data.py:62-105
- **Called by**: options-bot/scripts/validate_data.py:656
- **References**: 1 call sites

### WIRE-0338: test_alpaca_stock_bars (function)
- **File**: options-bot/scripts/validate_data.py:111-195
- **Called by**: options-bot/scripts/validate_data.py:659
- **References**: 1 call sites

### WIRE-0339: test_alpaca_options (function)
- **File**: options-bot/scripts/validate_data.py:201-246
- **Called by**: options-bot/scripts/validate_data.py:660
- **References**: 1 call sites

### WIRE-0340: test_theta_connection (function)
- **File**: options-bot/scripts/validate_data.py:252-335
- **Called by**: options-bot/scripts/validate_data.py:664
- **References**: 1 call sites

### WIRE-0341: test_theta_historical_options (function)
- **File**: options-bot/scripts/validate_data.py:341-487
- **Called by**: options-bot/scripts/validate_data.py:667
- **References**: 1 call sites

### WIRE-0342: test_theta_greeks (function)
- **File**: options-bot/scripts/validate_data.py:493-596
- **Called by**: options-bot/scripts/validate_data.py:668
- **References**: 1 call sites

### WIRE-0343: print_summary (function)
- **File**: options-bot/scripts/validate_data.py:602-643
- **Called by**: options-bot/scripts/validate_data.py:672
- **References**: 1 call sites

### WIRE-0344: main (function)
- **File**: options-bot/scripts/validate_data.py:649-672
- **Called by**: options-bot/main.py:425, options-bot/main.py:588, options-bot/scripts/backtest.py:253, options-bot/scripts/backtest.py:288, options-bot/scripts/test_features.py:215, options-bot/scripts/test_features.py:240, options-bot/scripts/test_providers.py:155, options-bot/scripts/test_providers.py:179, options-bot/scripts/train_model.py:62, options-bot/scripts/train_model.py:115 ... (+3 more)
- **References**: 13 call sites

### WIRE-0345: get_expected_features (function)
- **File**: options-bot/scripts/validate_model.py:38-46
- **Called by**: options-bot/scripts/validate_model.py:64, options-bot/scripts/validate_model.py:86, options-bot/scripts/validate_model.py:108
- **References**: 3 call sites

### WIRE-0346: validate_xgboost (function)
- **File**: options-bot/scripts/validate_model.py:49-65
- **Called by**: options-bot/scripts/validate_model.py:214, options-bot/scripts/validate_model.py:258
- **References**: 2 call sites

### WIRE-0347: validate_tft (function)
- **File**: options-bot/scripts/validate_model.py:68-87
- **Called by**: options-bot/scripts/validate_model.py:216, options-bot/scripts/validate_model.py:251
- **References**: 2 call sites

### WIRE-0348: validate_ensemble (function)
- **File**: options-bot/scripts/validate_model.py:90-109
- **Called by**: options-bot/scripts/validate_model.py:218, options-bot/scripts/validate_model.py:256
- **References**: 2 call sites

### WIRE-0349: _validate_features (function)
- **File**: options-bot/scripts/validate_model.py:112-177
- **Called by**: options-bot/scripts/validate_model.py:65, options-bot/scripts/validate_model.py:87, options-bot/scripts/validate_model.py:109
- **References**: 3 call sites

### WIRE-0350: validate_all_from_db (function)
- **File**: options-bot/scripts/validate_model.py:180-231
- **Called by**: options-bot/scripts/validate_model.py:247
- **References**: 1 call sites

### WIRE-0351: run_walk_forward (function)
- **File**: options-bot/scripts/walk_forward_backtest.py:51-169
- **Called by**: options-bot/scripts/walk_forward_backtest.py:309
- **References**: 1 call sites

### WIRE-0352: _train_window (function)
- **File**: options-bot/scripts/walk_forward_backtest.py:172-201
- **Called by**: options-bot/scripts/walk_forward_backtest.py:129
- **References**: 1 call sites

### WIRE-0353: _backtest_window (function)
- **File**: options-bot/scripts/walk_forward_backtest.py:204-241
- **Called by**: options-bot/scripts/walk_forward_backtest.py:147
- **References**: 1 call sites

### WIRE-0354: _print_summary (function)
- **File**: options-bot/scripts/walk_forward_backtest.py:244-268
- **Called by**: options-bot/scripts/walk_forward_backtest.py:164
- **References**: 1 call sites

### WIRE-0355: _save_results_csv (function)
- **File**: options-bot/scripts/walk_forward_backtest.py:271-288
- **Called by**: options-bot/scripts/walk_forward_backtest.py:167
- **References**: 1 call sites

### WIRE-0356: main (function)
- **File**: options-bot/scripts/walk_forward_backtest.py:291-320
- **Called by**: options-bot/main.py:425, options-bot/main.py:588, options-bot/scripts/backtest.py:253, options-bot/scripts/backtest.py:288, options-bot/scripts/test_features.py:215, options-bot/scripts/test_features.py:240, options-bot/scripts/test_providers.py:155, options-bot/scripts/test_providers.py:179, options-bot/scripts/train_model.py:62, options-bot/scripts/train_model.py:115 ... (+3 more)
- **References**: 13 call sites

### WIRE-0357: BaseOptionsStrategy (class)
- **File**: options-bot/strategies/base_strategy.py:67-2201
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0358: BaseOptionsStrategy.send_update_to_cloud (method)
- **File**: options-bot/strategies/base_strategy.py:83-85
- **Called by**: options-bot/strategies/base_strategy.py:83
- **References**: 1 call sites

### WIRE-0359: BaseOptionsStrategy._normalize_sleeptime (method)
- **File**: options-bot/strategies/base_strategy.py:88-114
- **Called by**: options-bot/strategies/base_strategy.py:88, options-bot/strategies/base_strategy.py:129
- **References**: 2 call sites

### WIRE-0360: BaseOptionsStrategy.initialize (method)
- **File**: options-bot/strategies/base_strategy.py:116-261
- **Called by**: options-bot/strategies/base_strategy.py:116, options-bot/strategies/base_strategy.py:118, options-bot/strategies/base_strategy.py:280
- **References**: 3 call sites

### WIRE-0361: BaseOptionsStrategy._get_classifier_avg_move (method)
- **File**: options-bot/strategies/base_strategy.py:263-273
- **Called by**: options-bot/strategies/base_strategy.py:263, options-bot/strategies/base_strategy.py:1637, options-bot/strategies/base_strategy.py:1721
- **References**: 3 call sites

### WIRE-0362: BaseOptionsStrategy._detect_model_type (method)
- **File**: options-bot/strategies/base_strategy.py:275-302
- **Called by**: options-bot/strategies/base_strategy.py:140, options-bot/strategies/base_strategy.py:275, options-bot/strategies/base_strategy.py:1026, options-bot/strategies/base_strategy.py:1419
- **References**: 4 call sites

### WIRE-0363: BaseOptionsStrategy.on_trading_iteration (method)
- **File**: options-bot/strategies/base_strategy.py:304-528
- **Called by**: options-bot/strategies/base_strategy.py:6, options-bot/strategies/base_strategy.py:304, options-bot/strategies/base_strategy.py:350
- **References**: 3 call sites

### WIRE-0364: BaseOptionsStrategy._export_circuit_state (method)
- **File**: options-bot/strategies/base_strategy.py:530-558
- **Called by**: options-bot/strategies/base_strategy.py:528, options-bot/strategies/base_strategy.py:530
- **References**: 2 call sites

### WIRE-0365: BaseOptionsStrategy._check_exits (method)
- **File**: options-bot/strategies/base_strategy.py:567-797
- **Called by**: options-bot/strategies/base_strategy.py:8, options-bot/strategies/base_strategy.py:443, options-bot/strategies/base_strategy.py:567
- **References**: 3 call sites

### WIRE-0366: BaseOptionsStrategy._get_latest_features_for_override (method)
- **File**: options-bot/strategies/base_strategy.py:799-889
- **Called by**: options-bot/strategies/base_strategy.py:693, options-bot/strategies/base_strategy.py:799
- **References**: 2 call sites

### WIRE-0367: BaseOptionsStrategy._execute_exit (method)
- **File**: options-bot/strategies/base_strategy.py:891-1006
- **Called by**: options-bot/ml/feedback_queue.py:31, options-bot/strategies/base_strategy.py:787, options-bot/strategies/base_strategy.py:891
- **References**: 3 call sites

### WIRE-0368: BaseOptionsStrategy._write_signal_log (method)
- **File**: options-bot/strategies/base_strategy.py:1014-1056
- **Called by**: options-bot/strategies/base_strategy.py:333, options-bot/strategies/base_strategy.py:373, options-bot/strategies/base_strategy.py:456, options-bot/strategies/base_strategy.py:471, options-bot/strategies/base_strategy.py:488, options-bot/strategies/base_strategy.py:1014, options-bot/strategies/base_strategy.py:1072, options-bot/strategies/base_strategy.py:1091, options-bot/strategies/base_strategy.py:1117, options-bot/strategies/base_strategy.py:1154 ... (+24 more)
- **References**: 34 call sites

### WIRE-0369: BaseOptionsStrategy._check_entries (method)
- **File**: options-bot/strategies/base_strategy.py:1063-2010
- **Called by**: options-bot/strategies/base_strategy.py:467, options-bot/strategies/base_strategy.py:1011, options-bot/strategies/base_strategy.py:1063, options-bot/strategies/base_strategy.py:2044
- **References**: 4 call sites

### WIRE-0370: BaseOptionsStrategy.on_filled_order (method)
- **File**: options-bot/strategies/base_strategy.py:2016-2020
- **Called by**: options-bot/strategies/base_strategy.py:2016
- **References**: 1 call sites

### WIRE-0371: BaseOptionsStrategy.on_canceled_order (method)
- **File**: options-bot/strategies/base_strategy.py:2022-2024
- **Called by**: options-bot/strategies/base_strategy.py:2022
- **References**: 1 call sites

### WIRE-0372: BaseOptionsStrategy.on_bot_crash (method)
- **File**: options-bot/strategies/base_strategy.py:2026-2028
- **Called by**: options-bot/strategies/base_strategy.py:2026
- **References**: 1 call sites

### WIRE-0373: BaseOptionsStrategy.before_market_opens (method)
- **File**: options-bot/strategies/base_strategy.py:2030-2032
- **Called by**: options-bot/strategies/base_strategy.py:2030
- **References**: 1 call sites

### WIRE-0374: BaseOptionsStrategy.after_market_closes (method)
- **File**: options-bot/strategies/base_strategy.py:2034-2039
- **Called by**: options-bot/strategies/base_strategy.py:2034
- **References**: 1 call sites

### WIRE-0375: BaseOptionsStrategy._record_prediction (method)
- **File**: options-bot/strategies/base_strategy.py:2041-2065
- **Called by**: options-bot/strategies/base_strategy.py:1379, options-bot/strategies/base_strategy.py:2041
- **References**: 2 call sites

### WIRE-0376: BaseOptionsStrategy._update_prediction_outcomes (method)
- **File**: options-bot/strategies/base_strategy.py:2067-2112
- **Called by**: options-bot/strategies/base_strategy.py:345, options-bot/strategies/base_strategy.py:2067
- **References**: 2 call sites

### WIRE-0377: BaseOptionsStrategy._compute_rolling_accuracy (method)
- **File**: options-bot/strategies/base_strategy.py:2114-2159
- **Called by**: options-bot/strategies/base_strategy.py:2114, options-bot/strategies/base_strategy.py:2173
- **References**: 2 call sites

### WIRE-0378: BaseOptionsStrategy._persist_health_to_db (method)
- **File**: options-bot/strategies/base_strategy.py:2161-2194
- **Called by**: options-bot/strategies/base_strategy.py:502, options-bot/strategies/base_strategy.py:2161
- **References**: 2 call sites

### WIRE-0379: BaseOptionsStrategy.trace_stats (method)
- **File**: options-bot/strategies/base_strategy.py:2196-2201
- **Called by**: options-bot/strategies/base_strategy.py:2196
- **References**: 1 call sites

### WIRE-0380: GeneralStrategy (class)
- **File**: options-bot/strategies/general_strategy.py:28-30
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0381: ScalpStrategy (class)
- **File**: options-bot/strategies/scalp_strategy.py:37-39
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0382: SwingStrategy (class)
- **File**: options-bot/strategies/swing_strategy.py:27-29
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0383: send_alert (function)
- **File**: options-bot/utils/alerter.py:27-107
- **Called by**: options-bot/risk/risk_manager.py:354, options-bot/strategies/base_strategy.py:320, options-bot/strategies/base_strategy.py:550, options-bot/utils/alerter.py:10
- **References**: 4 call sites

### WIRE-0384: CircuitState (class)
- **File**: options-bot/utils/circuit_breaker.py:32-35
- **Called by**: None found
- **References**: 0 call sites

### WIRE-0385: CircuitBreaker (class)
- **File**: options-bot/utils/circuit_breaker.py:38-138
- **Called by**: options-bot/data/alpaca_provider.py:52, options-bot/strategies/base_strategy.py:237, options-bot/utils/circuit_breaker.py:11
- **References**: 3 call sites

### WIRE-0386: CircuitBreaker.__init__ (method)
- **File**: options-bot/utils/circuit_breaker.py:41-61
- **Called by**: options-bot/backend/db_log_handler.py:24, options-bot/backend/db_log_handler.py:25, options-bot/backend/db_log_handler.py:58, options-bot/backend/db_log_handler.py:59, options-bot/data/alpaca_provider.py:47, options-bot/data/theta_provider.py:49, options-bot/data/vix_provider.py:39, options-bot/ml/ensemble_predictor.py:51, options-bot/ml/lgbm_predictor.py:25, options-bot/ml/scalp_predictor.py:36 ... (+5 more)
- **References**: 15 call sites

### WIRE-0387: CircuitBreaker.state (method)
- **File**: options-bot/utils/circuit_breaker.py:64-74
- **Called by**: options-bot/utils/circuit_breaker.py:64
- **References**: 1 call sites

### WIRE-0388: CircuitBreaker.can_execute (method)
- **File**: options-bot/utils/circuit_breaker.py:76-89
- **Called by**: options-bot/data/alpaca_provider.py:108, options-bot/strategies/base_strategy.py:1732, options-bot/utils/circuit_breaker.py:13, options-bot/utils/circuit_breaker.py:76
- **References**: 4 call sites

### WIRE-0389: CircuitBreaker.record_success (method)
- **File**: options-bot/utils/circuit_breaker.py:91-103
- **Called by**: options-bot/data/alpaca_provider.py:171, options-bot/strategies/base_strategy.py:1757, options-bot/utils/circuit_breaker.py:16, options-bot/utils/circuit_breaker.py:91
- **References**: 4 call sites

### WIRE-0390: CircuitBreaker.record_failure (method)
- **File**: options-bot/utils/circuit_breaker.py:105-125
- **Called by**: options-bot/data/alpaca_provider.py:205, options-bot/strategies/base_strategy.py:1759, options-bot/utils/circuit_breaker.py:18, options-bot/utils/circuit_breaker.py:105
- **References**: 4 call sites

### WIRE-0391: CircuitBreaker.get_stats (method)
- **File**: options-bot/utils/circuit_breaker.py:127-138
- **Called by**: options-bot/utils/circuit_breaker.py:127
- **References**: 1 call sites

### WIRE-0392: exponential_backoff (function)
- **File**: options-bot/utils/circuit_breaker.py:141-150
- **Called by**: options-bot/data/alpaca_provider.py:199
- **References**: 1 call sites

---

## EXPANDED WIREMAP — Non-Python Coverage


---

## Frontend Functions, Components & Event Handlers

### WIRE-0393: App (react_component)
- **File**: options-bot/ui/src/App.tsx:21-21
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0394: BASE (react_component)
- **File**: options-bot/ui/src/api/client.ts:21-21
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0395: api (exported_function)
- **File**: options-bot/ui/src/api/client.ts:48-48
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0396: list (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:50-50
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0397: get (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:52-52
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0398: create (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:54-54
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0399: update (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:56-56
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0400: delete (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:58-58
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0401: activate (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:60-60
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0402: pause (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:62-62
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0403: train (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:67-67
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0404: retrain (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:72-72
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0405: status (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:74-74
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0406: logs (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:76-76
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0407: clearLogs (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:78-78
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0408: importance (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:80-80
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0409: list (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:85-85
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0410: active (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:93-93
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0411: stats (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:95-95
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0412: exportUrl (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:97-97
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0413: health (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:102-102
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0414: status (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:104-104
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0415: pdt (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:106-106
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0416: errors (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:108-108
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0417: clearErrors (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:110-110
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0418: modelHealth (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:112-112
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0419: trainingQueue (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:114-114
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0420: run (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:119-119
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0421: results (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:124-124
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0422: status (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:129-129
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0423: start (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:131-131
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0424: stop (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:136-136
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0425: restart (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:141-141
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0426: startableProfiles (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:146-146
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0427: list (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:151-151
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0428: exportUrl (api_client_method)
- **File**: options-bot/ui/src/api/client.ts:156-156
- **Called by**: React components via api.*
- **References**: 0 call sites

### WIRE-0429: ConnIndicator (react_component)
- **File**: options-bot/ui/src/components/ConnIndicator.tsx:6-6
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0430: NAV (react_component)
- **File**: options-bot/ui/src/components/Layout.tsx:8-8
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0431: Layout (react_component)
- **File**: options-bot/ui/src/components/Layout.tsx:16-16
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0432: PageHeader (react_component)
- **File**: options-bot/ui/src/components/PageHeader.tsx:7-7
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0433: PnlCell (react_component)
- **File**: options-bot/ui/src/components/PnlCell.tsx:7-7
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0434: ConfigSlider (react_component)
- **File**: options-bot/ui/src/components/ProfileForm.tsx:8-8
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0435: PRESETS (react_component)
- **File**: options-bot/ui/src/components/ProfileForm.tsx:50-50
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0436: PRESET_DESCRIPTIONS (react_component)
- **File**: options-bot/ui/src/components/ProfileForm.tsx:52-52
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0437: ProfileForm (react_component)
- **File**: options-bot/ui/src/components/ProfileForm.tsx:58-58
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0438: Spinner (react_component)
- **File**: options-bot/ui/src/components/Spinner.tsx:1-1
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0439: STATUS_STYLES (react_component)
- **File**: options-bot/ui/src/components/StatusBadge.tsx:5-5
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0440: StatusBadge (react_component)
- **File**: options-bot/ui/src/components/StatusBadge.tsx:17-17
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0441: MAX_TOTAL_POSITIONS (react_component)
- **File**: options-bot/ui/src/pages/Dashboard.tsx:21-21
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0442: StatCard (react_component)
- **File**: options-bot/ui/src/pages/Dashboard.tsx:56-56
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0443: ProfileCard (react_component)
- **File**: options-bot/ui/src/pages/Dashboard.tsx:89-89
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0444: StatusPanel (react_component)
- **File**: options-bot/ui/src/pages/Dashboard.tsx:214-214
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0445: Dashboard (react_component)
- **File**: options-bot/ui/src/pages/Dashboard.tsx:353-353
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0446: MetricTile (react_component)
- **File**: options-bot/ui/src/pages/ProfileDetail.tsx:26-26
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0447: TrainingLogs (react_component)
- **File**: options-bot/ui/src/pages/ProfileDetail.tsx:43-43
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0448: FeatureImportancePanel (react_component)
- **File**: options-bot/ui/src/pages/ProfileDetail.tsx:82-82
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0449: SignalLogPanel (react_component)
- **File**: options-bot/ui/src/pages/ProfileDetail.tsx:122-122
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0450: ProfileDetail (react_component)
- **File**: options-bot/ui/src/pages/ProfileDetail.tsx:201-201
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0451: DeleteDialog (react_component)
- **File**: options-bot/ui/src/pages/Profiles.tsx:27-27
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0452: ProfileRow (react_component)
- **File**: options-bot/ui/src/pages/Profiles.tsx:82-82
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0453: Profiles (react_component)
- **File**: options-bot/ui/src/pages/Profiles.tsx:234-234
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0454: STEP_NAMES (react_component)
- **File**: options-bot/ui/src/pages/SignalLogs.tsx:16-16
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0455: SortIcon (react_component)
- **File**: options-bot/ui/src/pages/SignalLogs.tsx:78-78
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0456: ColHeader (react_component)
- **File**: options-bot/ui/src/pages/SignalLogs.tsx:98-98
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0457: FilterBar (react_component)
- **File**: options-bot/ui/src/pages/SignalLogs.tsx:125-125
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0458: SummaryRow (react_component)
- **File**: options-bot/ui/src/pages/SignalLogs.tsx:194-194
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0459: EMPTY_FILTERS (react_component)
- **File**: options-bot/ui/src/pages/SignalLogs.tsx:252-252
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0460: SignalLogs (react_component)
- **File**: options-bot/ui/src/pages/SignalLogs.tsx:256-256
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0461: MAX_TOTAL_POSITIONS (react_component)
- **File**: options-bot/ui/src/pages/System.tsx:18-18
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0462: ConnectionCard (react_component)
- **File**: options-bot/ui/src/pages/System.tsx:62-62
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0463: StatRow (react_component)
- **File**: options-bot/ui/src/pages/System.tsx:99-99
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0464: ErrorRow (react_component)
- **File**: options-bot/ui/src/pages/System.tsx:121-121
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0465: TradingProcessRow (react_component)
- **File**: options-bot/ui/src/pages/System.tsx:172-172
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0466: System (react_component)
- **File**: options-bot/ui/src/pages/System.tsx:230-230
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0467: SortIcon (react_component)
- **File**: options-bot/ui/src/pages/Trades.tsx:55-55
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0468: ColHeader (react_component)
- **File**: options-bot/ui/src/pages/Trades.tsx:75-75
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0469: FilterBar (react_component)
- **File**: options-bot/ui/src/pages/Trades.tsx:102-102
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0470: SummaryRow (react_component)
- **File**: options-bot/ui/src/pages/Trades.tsx:199-199
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0471: EMPTY_FILTERS (react_component)
- **File**: options-bot/ui/src/pages/Trades.tsx:247-247
- **Called by**: imported in other .tsx files
- **References**: 0 call sites

### WIRE-0472: Trades (react_component)
- **File**: options-bot/ui/src/pages/Trades.tsx:251-251
- **Called by**: imported in other .tsx files
- **References**: 0 call sites


---

## Configuration Constants

### WIRE-0473: PROJECT_ROOT (config_constant)
- **File**: options-bot/config.py:16-16
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0474: DB_PATH (config_constant)
- **File**: options-bot/config.py:17-17
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0475: MODELS_DIR (config_constant)
- **File**: options-bot/config.py:18-18
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0476: LOGS_DIR (config_constant)
- **File**: options-bot/config.py:19-19
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0477: ALPACA_API_KEY (config_constant)
- **File**: options-bot/config.py:24-24
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0478: ALPACA_API_SECRET (config_constant)
- **File**: options-bot/config.py:25-25
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0479: ALPACA_PAPER (config_constant)
- **File**: options-bot/config.py:26-26
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0480: ALPACA_BASE_URL (config_constant)
- **File**: options-bot/config.py:27-27
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0481: ALPACA_DATA_URL (config_constant)
- **File**: options-bot/config.py:28-28
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0482: THETA_HOST (config_constant)
- **File**: options-bot/config.py:33-33
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0483: THETA_PORT (config_constant)
- **File**: options-bot/config.py:34-34
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0484: THETA_BASE_URL_V3 (config_constant)
- **File**: options-bot/config.py:35-35
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0485: THETA_BASE_URL_V2 (config_constant)
- **File**: options-bot/config.py:36-36
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0486: THETA_USERNAME (config_constant)
- **File**: options-bot/config.py:37-37
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0487: THETA_PASSWORD (config_constant)
- **File**: options-bot/config.py:38-38
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0488: API_HOST (config_constant)
- **File**: options-bot/config.py:43-43
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0489: API_PORT (config_constant)
- **File**: options-bot/config.py:44-44
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0490: PHASE1_SYMBOLS (config_constant)
- **File**: options-bot/config.py:49-49
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0491: ALL_SYMBOLS (config_constant)
- **File**: options-bot/config.py:50-50
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0492: PRESET_DEFAULTS (config_constant)
- **File**: options-bot/config.py:55-55
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0493: PRESET_MODEL_TYPES (config_constant)
- **File**: options-bot/config.py:146-146
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0494: RISK_FREE_RATE (config_constant)
- **File**: options-bot/config.py:155-155
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0495: MIN_OPEN_INTEREST (config_constant)
- **File**: options-bot/config.py:160-160
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0496: MIN_OPTION_VOLUME (config_constant)
- **File**: options-bot/config.py:161-161
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0497: EARNINGS_BLACKOUT_DAYS_BEFORE (config_constant)
- **File**: options-bot/config.py:166-166
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0498: EARNINGS_BLACKOUT_DAYS_AFTER (config_constant)
- **File**: options-bot/config.py:167-167
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0499: TRAINING_QUEUE_MIN_SAMPLES (config_constant)
- **File**: options-bot/config.py:172-172
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0500: PORTFOLIO_MAX_ABS_DELTA (config_constant)
- **File**: options-bot/config.py:177-177
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0501: PORTFOLIO_MAX_ABS_VEGA (config_constant)
- **File**: options-bot/config.py:178-178
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0502: MAX_TOTAL_EXPOSURE_PCT (config_constant)
- **File**: options-bot/config.py:183-183
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0503: MAX_TOTAL_POSITIONS (config_constant)
- **File**: options-bot/config.py:184-184
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0504: EMERGENCY_STOP_LOSS_PCT (config_constant)
- **File**: options-bot/config.py:185-185
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0505: DTE_EXIT_FLOOR (config_constant)
- **File**: options-bot/config.py:186-186
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0506: THETA_CB_FAILURE_THRESHOLD (config_constant)
- **File**: options-bot/config.py:193-193
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0507: THETA_CB_RESET_TIMEOUT (config_constant)
- **File**: options-bot/config.py:194-194
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0508: ALPACA_CB_FAILURE_THRESHOLD (config_constant)
- **File**: options-bot/config.py:197-197
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0509: ALPACA_CB_RESET_TIMEOUT (config_constant)
- **File**: options-bot/config.py:198-198
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0510: RETRY_BACKOFF_BASE (config_constant)
- **File**: options-bot/config.py:201-201
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0511: RETRY_BACKOFF_MAX (config_constant)
- **File**: options-bot/config.py:202-202
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0512: RETRY_MAX_ATTEMPTS (config_constant)
- **File**: options-bot/config.py:203-203
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0513: MAX_CONSECUTIVE_ERRORS (config_constant)
- **File**: options-bot/config.py:206-206
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0514: ITERATION_ERROR_RESET_ON_SUCCESS (config_constant)
- **File**: options-bot/config.py:207-207
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0515: WATCHDOG_POLL_INTERVAL_SECONDS (config_constant)
- **File**: options-bot/config.py:210-210
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0516: WATCHDOG_AUTO_RESTART (config_constant)
- **File**: options-bot/config.py:211-211
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0517: WATCHDOG_MAX_RESTARTS (config_constant)
- **File**: options-bot/config.py:212-212
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0518: WATCHDOG_RESTART_DELAY_SECONDS (config_constant)
- **File**: options-bot/config.py:213-213
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0519: LOG_MAX_BYTES (config_constant)
- **File**: options-bot/config.py:216-216
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0520: LOG_BACKUP_COUNT (config_constant)
- **File**: options-bot/config.py:217-217
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0521: MODEL_HEALTH_WINDOW_SIZE (config_constant)
- **File**: options-bot/config.py:220-220
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0522: MODEL_STALE_THRESHOLD_DAYS (config_constant)
- **File**: options-bot/config.py:221-221
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0523: MODEL_DEGRADED_THRESHOLD (config_constant)
- **File**: options-bot/config.py:222-222
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0524: MODEL_HEALTH_MIN_SAMPLES (config_constant)
- **File**: options-bot/config.py:223-223
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0525: PREDICTION_RESOLVE_MINUTES_SWING (config_constant)
- **File**: options-bot/config.py:224-224
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0526: PREDICTION_RESOLVE_MINUTES_SCALP (config_constant)
- **File**: options-bot/config.py:225-225
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0527: VIX_MIN_GATE (config_constant)
- **File**: options-bot/config.py:232-232
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0528: VIX_MAX_GATE (config_constant)
- **File**: options-bot/config.py:233-233
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0529: OPTUNA_N_TRIALS (config_constant)
- **File**: options-bot/config.py:240-240
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0530: OPTUNA_TIMEOUT_SECONDS (config_constant)
- **File**: options-bot/config.py:241-241
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0531: VIX_REGIME_LOW_THRESHOLD (config_constant)
- **File**: options-bot/config.py:244-244
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0532: VIX_REGIME_HIGH_THRESHOLD (config_constant)
- **File**: options-bot/config.py:245-245
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0533: VIX_REGIME_LOW_MULTIPLIER (config_constant)
- **File**: options-bot/config.py:246-246
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0534: VIX_REGIME_NORMAL_MULTIPLIER (config_constant)
- **File**: options-bot/config.py:247-247
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0535: VIX_REGIME_HIGH_MULTIPLIER (config_constant)
- **File**: options-bot/config.py:248-248
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0536: VIX_REGIME_ENABLED (config_constant)
- **File**: options-bot/config.py:249-249
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0537: VIX_PROXY_SHORT_TICKER (config_constant)
- **File**: options-bot/config.py:252-252
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0538: VIX_PROXY_MID_TICKER (config_constant)
- **File**: options-bot/config.py:253-253
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0539: ALERT_WEBHOOK_URL (config_constant)
- **File**: options-bot/config.py:258-258
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0540: LOG_LEVEL (config_constant)
- **File**: options-bot/config.py:263-263
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0541: LOG_FORMAT (config_constant)
- **File**: options-bot/config.py:264-264
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites

### WIRE-0542: VERSION (config_constant)
- **File**: options-bot/config.py:269-269
- **Called by**: imported by strategies, backend, ML modules
- **References**: 0 call sites


---

## Environment Variables

### WIRE-0543: ALPACA_API_KEY (env_variable)
- **File**: options-bot/config.py:24-24
- **Called by**: os.getenv at startup
- **References**: 0 call sites

### WIRE-0544: ALPACA_API_SECRET (env_variable)
- **File**: options-bot/config.py:25-25
- **Called by**: os.getenv at startup
- **References**: 0 call sites

### WIRE-0545: ALPACA_PAPER (env_variable)
- **File**: options-bot/config.py:26-26
- **Called by**: os.getenv at startup
- **References**: 0 call sites

### WIRE-0546: THETA_TERMINAL_HOST (env_variable)
- **File**: options-bot/config.py:33-33
- **Called by**: os.getenv at startup
- **References**: 0 call sites

### WIRE-0547: THETA_TERMINAL_PORT (env_variable)
- **File**: options-bot/config.py:34-34
- **Called by**: os.getenv at startup
- **References**: 0 call sites

### WIRE-0548: THETADATA_USERNAME (env_variable)
- **File**: options-bot/config.py:37-37
- **Called by**: os.getenv at startup
- **References**: 0 call sites

### WIRE-0549: THETADATA_PASSWORD (env_variable)
- **File**: options-bot/config.py:38-38
- **Called by**: os.getenv at startup
- **References**: 0 call sites

### WIRE-0550: RISK_FREE_RATE (env_variable)
- **File**: options-bot/config.py:155-155
- **Called by**: os.getenv at startup
- **References**: 0 call sites

### WIRE-0551: VIX_MIN_GATE (env_variable)
- **File**: options-bot/config.py:232-232
- **Called by**: os.getenv at startup
- **References**: 0 call sites

### WIRE-0552: VIX_MAX_GATE (env_variable)
- **File**: options-bot/config.py:233-233
- **Called by**: os.getenv at startup
- **References**: 0 call sites

### WIRE-0553: ALERT_WEBHOOK_URL (env_variable)
- **File**: options-bot/config.py:258-258
- **Called by**: os.getenv at startup
- **References**: 0 call sites


---

## Route Registrations

### WIRE-0554: GET /{full_path:path} (fastapi_route)
- **File**: options-bot/backend/app.py:429-429
- **Called by**: HTTP client, frontend api/client.ts
- **References**: 0 call sites

### WIRE-0555: Route: / (react_route)
- **File**: options-bot/ui/src/App.tsx:26-26
- **Called by**: React Router, nav links in Layout.tsx
- **References**: 0 call sites

### WIRE-0556: Route: profiles (react_route)
- **File**: options-bot/ui/src/App.tsx:28-28
- **Called by**: React Router, nav links in Layout.tsx
- **References**: 0 call sites

### WIRE-0557: Route: profiles/:id (react_route)
- **File**: options-bot/ui/src/App.tsx:29-29
- **Called by**: React Router, nav links in Layout.tsx
- **References**: 0 call sites

### WIRE-0558: Route: trades (react_route)
- **File**: options-bot/ui/src/App.tsx:30-30
- **Called by**: React Router, nav links in Layout.tsx
- **References**: 0 call sites

### WIRE-0559: Route: signals (react_route)
- **File**: options-bot/ui/src/App.tsx:31-31
- **Called by**: React Router, nav links in Layout.tsx
- **References**: 0 call sites

### WIRE-0560: Route: system (react_route)
- **File**: options-bot/ui/src/App.tsx:32-32
- **Called by**: React Router, nav links in Layout.tsx
- **References**: 0 call sites

### WIRE-0561: Route: * (react_route)
- **File**: options-bot/ui/src/App.tsx:33-33
- **Called by**: React Router, nav links in Layout.tsx
- **References**: 0 call sites


---

## UI Controls (from runtime testing)

### WIRE-0562: UI-007: Refresh (ui_control (button))
- **File**: pages/Dashboard.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0563: UI-008: Profile Name (navigate) (ui_control (button))
- **File**: pages/Dashboard.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0564: UI-009: Activate (profile card) (ui_control (button))
- **File**: pages/Dashboard.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0565: UI-010: Pause (profile card) (ui_control (button))
- **File**: pages/Dashboard.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0566: UI-011: Detail (profile card) (ui_control (button))
- **File**: pages/Dashboard.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0567: UI-012: Clear error (X icon) (ui_control (button))
- **File**: pages/Dashboard.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0568: UI-002: Dashboard (nav) (ui_control (link))
- **File**: components/Layout.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0569: UI-003: Profiles (nav) (ui_control (link))
- **File**: components/Layout.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0570: UI-004: Trade History (nav) (ui_control (link))
- **File**: components/Layout.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0571: UI-005: Signal Logs (nav) (ui_control (link))
- **File**: components/Layout.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0572: UI-006: System Status (nav) (ui_control (link))
- **File**: components/Layout.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0573: UI-013: New Profile (ui_control (button))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0574: UI-026: Profile Name (text) (ui_control (input))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0575: UI-027: Preset: swing (ui_control (button))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0576: UI-028: Preset: general (ui_control (button))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0577: UI-029: Preset: scalp (ui_control (button))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0578: UI-031: Symbol input (text) (ui_control (input))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0579: UI-032: Add symbol (+) (ui_control (button))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0580: UI-030: Remove symbol (X per tag) (ui_control (button))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0581: UI-033: Advanced Risk Parameters (toggle) (ui_control (button))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0582: UI-034: Max Position Size (ui_control (slider))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0583: UI-035: Max Contracts (ui_control (slider))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0584: UI-036: Max Concurrent (ui_control (slider))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0585: UI-037: Max Daily Trades (ui_control (slider))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0586: UI-038: Max Daily Loss (ui_control (slider))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0587: UI-039: Min Confidence (ui_control (slider))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0588: UI-040: Cancel (form) (ui_control (button))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0589: UI-041: Create Profile / Save Changes (ui_control (button))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0590: UI-022: Create Profile Form (ui_control (modal))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0591: UI-025: Profile form (submit) (ui_control (form))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0592: UI-015: Profile Name (row navigate) (ui_control (button))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0593: UI-016: Activate (row) (ui_control (button))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0594: UI-017: Pause (row) (ui_control (button))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0595: UI-018: Train model (row) (ui_control (button))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0596: UI-019: Edit (row) (ui_control (button))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0597: UI-020: Detail (row) (ui_control (button))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0598: UI-021: Delete (row) (ui_control (button))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0599: UI-023: Edit Profile Form (ui_control (modal))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0600: UI-024: Close modal (X icon) (ui_control (button))
- **File**: components/ProfileForm.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0601: UI-042: Delete Profile Dialog (ui_control (modal))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0602: UI-043: Cancel (delete dialog) (ui_control (button))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0603: UI-044: Delete (confirm) (ui_control (button))
- **File**: pages/Profiles.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0604: UI-045: Go Back (profile not found) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0605: UI-046: All Profiles (back arrow) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0606: UI-047: Edit (profile detail header) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0607: UI-048: Activate (profile detail) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0608: UI-049: Pause (profile detail) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0609: UI-050: Update Model (retrain) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0610: UI-051: Train (split button main) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0611: UI-052: Model type dropdown toggle (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0612: UI-053: Model type selector menu (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0613: UI-054: Model type option (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0614: UI-055: Model type tab (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0615: UI-056: Feature Importance (multi-model) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0616: UI-057: Feature Importance (single model) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0617: UI-058: Dismiss train error (X) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0618: UI-059: Show/Hide training logs (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0619: UI-060: Clear logs (trash icon) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0620: UI-061: Run Backtest / Collapse toggle (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0621: UI-062: Backtest Start Date (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0622: UI-063: Backtest End Date (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0623: UI-064: Run (backtest) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0624: UI-065: Edit Profile (from detail) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0625: UI-045: Go Back (profile not found) (ui_control (button))
- **File**: pages/ProfileDetail.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0626: UI-001: Back to Dashboard (ui_control (link))
- **File**: App.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0627: UI-080: Export CSV (Trades) (ui_control (button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0628: UI-081: Profile filter (Trades) (ui_control (select))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0629: UI-082: Symbol filter (Trades) (ui_control (input))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0630: UI-083: Status filter (Trades) (ui_control (select))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0631: UI-084: Direction filter (Trades) (ui_control (select))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0632: UI-085: Date from filter (Trades) (ui_control (input))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0633: UI-086: Date to filter (Trades) (ui_control (input))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0634: UI-087: Reset filters (Trades) (ui_control (button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0635: UI-088: Sort by Date (Trades) (ui_control (th-button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0636: UI-089: Sort by Symbol (Trades) (ui_control (th-button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0637: UI-090: Sort by Dir (Trades) (ui_control (th-button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0638: UI-091: Sort by Strike (Trades) (ui_control (th-button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0639: UI-092: Sort by P&L (Trades) (ui_control (th-button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0640: UI-093: Sort by P&L (Trades) (ui_control (th-button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0641: UI-094: Sort by Hold (Trades) (ui_control (th-button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0642: UI-095: Sort by Exit (Trades) (ui_control (th-button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0643: UI-096: Sort by Status (Trades) (ui_control (th-button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0644: UI-097: Clear filters (no results Trades) (ui_control (button))
- **File**: pages/Trades.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0645: UI-098: Export CSV (Signal Logs) (ui_control (button))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0646: UI-099: Profile filter (Signal Logs) (ui_control (select))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0647: UI-100: Entered filter (Signal Logs) (ui_control (select))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0648: UI-101: Date from filter (Signal Logs) (ui_control (input))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0649: UI-102: Date to filter (Signal Logs) (ui_control (input))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0650: UI-103: Reset filters (Signal Logs) (ui_control (button))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0651: UI-104: Sort by Time (Signal Logs) (ui_control (th-button))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0652: UI-105: Sort by Symbol (Signal Logs) (ui_control (th-button))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0653: UI-106: Sort by Price (Signal Logs) (ui_control (th-button))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0654: UI-107: Sort by Predicted (Signal Logs) (ui_control (th-button))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0655: UI-108: Sort by Stopped (Signal Logs) (ui_control (th-button))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0656: UI-109: Sort by Entered (Signal Logs) (ui_control (th-button))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0657: UI-110: Clear filters (no results Signal Logs) (ui_control (button))
- **File**: pages/SignalLogs.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0658: UI-066: Refresh (System page) (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0659: UI-067: Quick Start (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0660: UI-069: Profile selection checkbox (ui_control (checkbox))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0661: UI-070: Start N Profiles (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0662: UI-071: Select all (quick start) (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0663: UI-072: Cancel (quick start) (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0664: UI-068: Stop All (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0665: UI-073: Restart (trading process) (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0666: UI-074: Stop (trading process) (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0667: UI-075: Clear error logs (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0668: UI-076: Error limit selector (ui_control (select))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0669: UI-077: Load more entries (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0670: UI-078: Clear error (X icon in Runtime panel) (ui_control (button))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites

### WIRE-0671: UI-079: Error row (expand/collapse) (ui_control (div))
- **File**: pages/System.tsx:0-0
- **Called by**: user interaction, Playwright tested
- **References**: 0 call sites


---

## Storage Load/Save Paths

### WIRE-0672: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/main.py:223-223
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0673: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/app.py:48-48
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0674: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/app.py:200-200
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0675: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/app.py:293-293
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0676: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/app.py:374-374
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0677: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/database.py:140-140
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0678: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/database.py:152-152
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0679: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/database.py:159-159
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0680: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/database.py:170-170
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0681: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/database.py:190-190
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0682: DB connect: self._db_path, timeout=5 (db_connection)
- **File**: options-bot/backend/db_log_handler.py:34-34
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0683: DB connect: self._db_path, timeout=5 (db_connection)
- **File**: options-bot/backend/db_log_handler.py:73-73
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0684: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/routes/models.py:119-119
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0685: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/routes/models.py:144-144
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0686: DB connect: str(_DB_PATH (db_connection)
- **File**: options-bot/backend/routes/models.py:222-222
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0687: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/routes/trading.py:104-104
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0688: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/routes/trading.py:122-122
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0689: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/backend/routes/trading.py:254-254
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0690: joblib.load: model_path (model_load)
- **File**: options-bot/ml/ensemble_predictor.py:87-87
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0691: joblib.dump: data (model_save)
- **File**: options-bot/ml/ensemble_predictor.py:156-156
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0692: DB connect: db_path, timeout=10 (db_connection)
- **File**: options-bot/ml/feedback_queue.py:38-38
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0693: DB connect: db_path (db_connection)
- **File**: options-bot/ml/incremental_trainer.py:99-99
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0694: DB connect: db_path (db_connection)
- **File**: options-bot/ml/incremental_trainer.py:125-125
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0695: DB connect: db_path (db_connection)
- **File**: options-bot/ml/incremental_trainer.py:170-170
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0696: DB connect: db_path, timeout=10 (db_connection)
- **File**: options-bot/ml/incremental_trainer.py:216-216
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0697: joblib.load: existing_model_path (model_load)
- **File**: options-bot/ml/incremental_trainer.py:504-504
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0698: joblib.load: model_path (model_load)
- **File**: options-bot/ml/lgbm_predictor.py:34-34
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0699: joblib.dump: {"model": self._model (model_save)
- **File**: options-bot/ml/lgbm_predictor.py:46-46
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0700: DB connect: db_path (db_connection)
- **File**: options-bot/ml/lgbm_trainer.py:336-336
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0701: DB connect: db_path, timeout=10 (db_connection)
- **File**: options-bot/ml/lgbm_trainer.py:372-372
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0702: joblib.load: model_path (model_load)
- **File**: options-bot/ml/scalp_predictor.py:49-49
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0703: joblib.dump: {
                "model": self._model (model_save)
- **File**: options-bot/ml/scalp_predictor.py:73-73
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0704: DB connect: db_path (db_connection)
- **File**: options-bot/ml/scalp_trainer.py:798-798
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0705: DB connect: db_path, timeout=10 (db_connection)
- **File**: options-bot/ml/scalp_trainer.py:836-836
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0706: joblib.load: model_path (model_load)
- **File**: options-bot/ml/swing_classifier_predictor.py:46-46
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0707: joblib.dump: {
                "model": self._model (model_save)
- **File**: options-bot/ml/swing_classifier_predictor.py:66-66
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0708: DB connect: db_path (db_connection)
- **File**: options-bot/ml/swing_classifier_trainer.py:607-607
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0709: DB connect: db_path, timeout=10 (db_connection)
- **File**: options-bot/ml/swing_classifier_trainer.py:643-643
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0710: DB connect: db_path (db_connection)
- **File**: options-bot/ml/tft_trainer.py:682-682
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0711: DB connect: db_path (db_connection)
- **File**: options-bot/ml/trainer.py:670-670
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0712: DB connect: db_path, timeout=10 (db_connection)
- **File**: options-bot/ml/trainer.py:710-710
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0713: joblib.load: model_path (model_load)
- **File**: options-bot/ml/xgboost_predictor.py:30-30
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0714: joblib.dump: {"model": self._model (model_save)
- **File**: options-bot/ml/xgboost_predictor.py:42-42
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0715: DB connect: self._db_path (db_connection)
- **File**: options-bot/risk/risk_manager.py:86-86
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0716: DB connect: self._db_path (db_connection)
- **File**: options-bot/risk/risk_manager.py:153-153
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0717: DB connect: self._db_path (db_connection)
- **File**: options-bot/risk/risk_manager.py:212-212
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0718: DB connect: self._db_path (db_connection)
- **File**: options-bot/risk/risk_manager.py:254-254
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0719: DB connect: self._db_path (db_connection)
- **File**: options-bot/risk/risk_manager.py:496-496
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0720: DB connect: self._db_path (db_connection)
- **File**: options-bot/risk/risk_manager.py:541-541
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0721: DB connect: self._db_path (db_connection)
- **File**: options-bot/risk/risk_manager.py:588-588
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0722: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/scripts/startup_check.py:267-267
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0723: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/scripts/startup_check.py:281-281
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0724: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/scripts/train_model.py:43-43
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0725: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/scripts/validate_model.py:187-187
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0726: joblib.load: path (model_load)
- **File**: options-bot/scripts/validate_model.py:56-56
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0727: joblib.load: path (model_load)
- **File**: options-bot/scripts/validate_model.py:97-97
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0728: joblib.load: path (model_load)
- **File**: options-bot/scripts/validate_model.py:254-254
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0729: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/strategies/base_strategy.py:285-285
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0730: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/strategies/base_strategy.py:1033-1033
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0731: DB connect: str(DB_PATH (db_connection)
- **File**: options-bot/strategies/base_strategy.py:2180-2180
- **Called by**: N/A
- **References**: 0 call sites


---

## Logging Paths

### WIRE-0732: Logger: main.py (logger)
- **File**: options-bot/main.py:43-43
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0733: Logger: options-bot.main (logger)
- **File**: options-bot/main.py:73-73
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0734: Logger: options-bot.backend (logger)
- **File**: options-bot/backend/app.py:26-26
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0735: Logger: options-bot.database (logger)
- **File**: options-bot/backend/database.py:14-14
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0736: Logger: options-bot.routes.models (logger)
- **File**: options-bot/backend/routes/models.py:27-27
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0737: Logger: options-bot (logger)
- **File**: options-bot/backend/routes/models.py:47-47
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0738: Logger: options-bot (logger)
- **File**: options-bot/backend/routes/models.py:53-53
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0739: Logger: options-bot.routes.profiles (logger)
- **File**: options-bot/backend/routes/profiles.py:25-25
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0740: Logger: options-bot.routes.signals (logger)
- **File**: options-bot/backend/routes/signals.py:20-20
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0741: Logger: options-bot.routes.system (logger)
- **File**: options-bot/backend/routes/system.py:19-19
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0742: Logger: options-bot.routes.trades (logger)
- **File**: options-bot/backend/routes/trades.py:20-20
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0743: Logger: options-bot.routes.trading (logger)
- **File**: options-bot/backend/routes/trading.py:41-41
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0744: Logger: options-bot.data.alpaca (logger)
- **File**: options-bot/data/alpaca_provider.py:35-35
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0745: Logger: options-bot.data.earnings_calendar (logger)
- **File**: options-bot/data/earnings_calendar.py:15-15
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0746: Logger: options-bot.data.greeks (logger)
- **File**: options-bot/data/greeks_calculator.py:39-39
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0747: Logger: options-bot.data.options_fetcher (logger)
- **File**: options-bot/data/options_data_fetcher.py:38-38
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0748: Logger: options-bot.data.theta (logger)
- **File**: options-bot/data/theta_provider.py:35-35
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0749: Logger: options-bot.data.validator (logger)
- **File**: options-bot/data/validator.py:37-37
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0750: Logger: options-bot.data.vix_provider (logger)
- **File**: options-bot/data/vix_provider.py:26-26
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0751: Logger: options-bot.ml.ensemble (logger)
- **File**: options-bot/ml/ensemble_predictor.py:32-32
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0752: Logger: options-bot.ml.ev_filter (logger)
- **File**: options-bot/ml/ev_filter.py:23-23
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0753: Logger: options-bot.ml.feedback_queue (logger)
- **File**: options-bot/ml/feedback_queue.py:17-17
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0754: Logger: options-bot.ml.incremental_trainer (logger)
- **File**: options-bot/ml/incremental_trainer.py:55-55
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0755: Logger: options-bot.ml.lgbm (logger)
- **File**: options-bot/ml/lgbm_predictor.py:19-19
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0756: Logger: options-bot.ml.lgbm_trainer (logger)
- **File**: options-bot/ml/lgbm_trainer.py:34-34
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0757: Logger: options-bot.ml.liquidity_filter (logger)
- **File**: options-bot/ml/liquidity_filter.py:16-16
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0758: Logger: options-bot.ml.regime_adjuster (logger)
- **File**: options-bot/ml/regime_adjuster.py:26-26
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0759: Logger: options-bot.ml.scalp_predictor (logger)
- **File**: options-bot/ml/scalp_predictor.py:26-26
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0760: Logger: options-bot.ml.scalp_trainer (logger)
- **File**: options-bot/ml/scalp_trainer.py:45-45
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0761: Logger: options-bot.ml.swing_classifier_predictor (logger)
- **File**: options-bot/ml/swing_classifier_predictor.py:24-24
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0762: Logger: options-bot.ml.swing_classifier_trainer (logger)
- **File**: options-bot/ml/swing_classifier_trainer.py:43-43
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0763: Logger: options-bot.ml.tft (logger)
- **File**: options-bot/ml/tft_predictor.py:29-29
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0764: Logger: options-bot.ml.tft_trainer (logger)
- **File**: options-bot/ml/tft_trainer.py:47-47
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0765: Logger: options-bot.ml.trainer (logger)
- **File**: options-bot/ml/trainer.py:39-39
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0766: Logger: options-bot.ml.xgboost (logger)
- **File**: options-bot/ml/xgboost_predictor.py:15-15
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0767: Logger: options-bot.features.base (logger)
- **File**: options-bot/ml/feature_engineering/base_features.py:24-24
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0768: Logger: options-bot.features.general (logger)
- **File**: options-bot/ml/feature_engineering/general_features.py:12-12
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0769: Logger: options-bot.features.scalp (logger)
- **File**: options-bot/ml/feature_engineering/scalp_features.py:15-15
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0770: Logger: options-bot.features.swing (logger)
- **File**: options-bot/ml/feature_engineering/swing_features.py:12-12
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0771: Logger: options-bot.risk_manager (logger)
- **File**: options-bot/risk/risk_manager.py:30-30
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0772: Logger: options-bot.backtest (logger)
- **File**: options-bot/scripts/backtest.py:36-36
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0773: Logger: backtest.py (logger)
- **File**: options-bot/scripts/backtest.py:45-45
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0774: Logger: diagnostic (logger)
- **File**: options-bot/scripts/diagnose_strategy.py:9-9
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0775: Logger: test_features (logger)
- **File**: options-bot/scripts/test_features.py:29-29
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0776: Logger: test_providers (logger)
- **File**: options-bot/scripts/test_providers.py:26-26
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0777: Logger: train_model (logger)
- **File**: options-bot/scripts/train_model.py:34-34
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0778: Logger: validate_data (logger)
- **File**: options-bot/scripts/validate_data.py:42-42
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0779: Logger: walk_forward_backtest.py (logger)
- **File**: options-bot/scripts/walk_forward_backtest.py:42-42
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0780: Logger: options-bot.walk_forward (logger)
- **File**: options-bot/scripts/walk_forward_backtest.py:48-48
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0781: Logger: options-bot.strategy.base (logger)
- **File**: options-bot/strategies/base_strategy.py:64-64
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0782: Logger: options-bot.strategy.general (logger)
- **File**: options-bot/strategies/general_strategy.py:25-25
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0783: Logger: options-bot.strategy.scalp (logger)
- **File**: options-bot/strategies/scalp_strategy.py:34-34
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0784: Logger: options-bot.strategy.swing (logger)
- **File**: options-bot/strategies/swing_strategy.py:24-24
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0785: Logger: options-bot.utils.alerter (logger)
- **File**: options-bot/utils/alerter.py:24-24
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0786: Logger: options-bot.circuit_breaker (logger)
- **File**: options-bot/utils/circuit_breaker.py:29-29
- **Called by**: N/A
- **References**: 0 call sites


---

## Behavior-Affecting Constants & Preset Defaults

### WIRE-0787: PHASE1_SYMBOLS (constant_list)
- **File**: options-bot/config.py:49-49
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0788: ALL_SYMBOLS (constant_list)
- **File**: options-bot/config.py:50-50
- **Called by**: N/A
- **References**: 0 call sites


---

## Request/Response Field Bindings (TypeScript types ↔ Backend schemas)

### WIRE-0789: ModelSummary (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:6-6
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0790: Profile (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:23-23
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0791: ProfileCreate (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:39-39
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0792: ProfileUpdate (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:46-46
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0793: TrainingStatus (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:52-52
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0794: ModelMetrics (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:60-60
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0795: FeatureImportanceResponse (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:74-74
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0796: TrainingLogEntry (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:80-80
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0797: Trade (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:88-88
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0798: TradeStats (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:113-113
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0799: CircuitBreakerState (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:127-127
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0800: SystemStatus (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:135-135
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0801: HealthCheck (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:151-151
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0802: PDTStatus (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:157-157
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0803: ErrorLogEntry (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:165-165
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0804: TrainingQueueStatus (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:172-172
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0805: BacktestRequest (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:179-179
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0806: BacktestResult (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:185-185
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0807: TradingProcessInfo (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:202-202
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0808: TradingStatusResponse (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:212-212
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0809: TradingStartResponse (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:218-218
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0810: TradingStopResponse (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:223-223
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0811: StartableProfile (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:228-228
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0812: ModelHealthEntry (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:238-238
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0813: ModelHealthResponse (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:251-251
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0814: SignalLogEntry (typescript_type)
- **File**: options-bot/ui/src/types/api.ts:259-259
- **Called by**: frontend components, matched to backend Pydantic schemas
- **References**: 0 call sites

### WIRE-0815: ProfileCreate (pydantic_schema)
- **File**: options-bot/backend/schemas.py:17-17
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0816: ProfileUpdate (pydantic_schema)
- **File**: options-bot/backend/schemas.py:23-23
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0817: ModelSummary (pydantic_schema)
- **File**: options-bot/backend/schemas.py:28-28
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0818: ProfileResponse (pydantic_schema)
- **File**: options-bot/backend/schemas.py:37-37
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0819: ModelResponse (pydantic_schema)
- **File**: options-bot/backend/schemas.py:57-57
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0820: TrainRequest (pydantic_schema)
- **File**: options-bot/backend/schemas.py:72-72
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0821: TrainingStatus (pydantic_schema)
- **File**: options-bot/backend/schemas.py:78-78
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0822: ModelMetrics (pydantic_schema)
- **File**: options-bot/backend/schemas.py:85-85
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0823: TrainingLogEntry (pydantic_schema)
- **File**: options-bot/backend/schemas.py:98-98
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0824: TradeResponse (pydantic_schema)
- **File**: options-bot/backend/schemas.py:110-110
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0825: TradeStats (pydantic_schema)
- **File**: options-bot/backend/schemas.py:134-134
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0826: SystemStatus (pydantic_schema)
- **File**: options-bot/backend/schemas.py:152-152
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0827: HealthCheck (pydantic_schema)
- **File**: options-bot/backend/schemas.py:167-167
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0828: PDTStatus (pydantic_schema)
- **File**: options-bot/backend/schemas.py:172-172
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0829: ErrorLogEntry (pydantic_schema)
- **File**: options-bot/backend/schemas.py:179-179
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0830: ModelHealthEntry (pydantic_schema)
- **File**: options-bot/backend/schemas.py:186-186
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0831: ModelHealthResponse (pydantic_schema)
- **File**: options-bot/backend/schemas.py:199-199
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0832: TrainingQueueStatus (pydantic_schema)
- **File**: options-bot/backend/schemas.py:210-210
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0833: BacktestRequest (pydantic_schema)
- **File**: options-bot/backend/schemas.py:221-221
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0834: BacktestResult (pydantic_schema)
- **File**: options-bot/backend/schemas.py:226-226
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0835: TradingProcessInfo (pydantic_schema)
- **File**: options-bot/backend/schemas.py:248-248
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0836: TradingStatusResponse (pydantic_schema)
- **File**: options-bot/backend/schemas.py:257-257
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0837: TradingStartRequest (pydantic_schema)
- **File**: options-bot/backend/schemas.py:262-262
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0838: TradingStartResponse (pydantic_schema)
- **File**: options-bot/backend/schemas.py:265-265
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0839: TradingStopRequest (pydantic_schema)
- **File**: options-bot/backend/schemas.py:269-269
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0840: TradingStopResponse (pydantic_schema)
- **File**: options-bot/backend/schemas.py:272-272
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites

### WIRE-0841: SignalLogEntry (pydantic_schema)
- **File**: options-bot/backend/schemas.py:281-281
- **Called by**: backend route handlers, serialized to JSON for frontend
- **References**: 0 call sites


---

## Startup/Shutdown/Live-Loop Hooks

### WIRE-0842: SIGINT (signal_handler)
- **File**: options-bot/main.py:102-102
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0843: SIGTERM (signal_handler)
- **File**: options-bot/main.py:103-103
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0844: SIGBREAK (signal_handler)
- **File**: options-bot/main.py:108-108
- **Called by**: N/A
- **References**: 0 call sites

### WIRE-0845: lifespan (lifecycle_function)
- **File**: options-bot/backend/app.py:193-193
- **Called by**: N/A
- **References**: 0 call sites


---

## Expansion Summary

**Original Python-only entries**: 392
**New expanded entries**: 453
**Total wire entries**: 845
**Coverage**: Python functions/classes/methods, frontend components/hooks/handlers, config constants, environment variables, FastAPI routes, React routes, UI controls, DB connections, model load/save, loggers, TypeScript types, Pydantic schemas, lifecycle hooks, behavior-affecting constants
