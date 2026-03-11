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
