"""
Global configuration constants for options-bot.
All configurable values in one place. Profile-specific settings
are stored in the SQLite database as JSON blobs.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Paths
# =============================================================================
PROJECT_ROOT = Path(__file__).parent
DB_PATH = PROJECT_ROOT / "db" / "options_bot.db"
MODELS_DIR = PROJECT_ROOT / "models"
LOGS_DIR = PROJECT_ROOT / "logs"

# =============================================================================
# Alpaca
# =============================================================================
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
ALPACA_BASE_URL = "https://paper-api.alpaca.markets" if ALPACA_PAPER else "https://api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets"

# =============================================================================
# Theta Data Terminal
# =============================================================================
THETA_HOST = os.getenv("THETA_TERMINAL_HOST", "127.0.0.1")
THETA_PORT = int(os.getenv("THETA_TERMINAL_PORT", "25503"))
THETA_BASE_URL_V3 = f"http://{THETA_HOST}:{THETA_PORT}/v3"
THETA_BASE_URL_V2 = f"http://{THETA_HOST}:25510/v2"
THETA_USERNAME = os.getenv("THETADATA_USERNAME", "")
THETA_PASSWORD = os.getenv("THETADATA_PASSWORD", "")

# =============================================================================
# Backend
# =============================================================================
API_HOST = "127.0.0.1"
API_PORT = 8000

# =============================================================================
# Trading Symbols (validated for Phase 1)
# =============================================================================
PHASE1_SYMBOLS = ["TSLA"]
ALL_SYMBOLS = ["TSLA", "NVDA", "UNH", "SPY"]

# =============================================================================
# Profile Preset Defaults
# =============================================================================
PRESET_DEFAULTS = {
    "swing": {
        "min_dte": 7,
        "max_dte": 45,
        "sleeptime": "5M",
        "max_hold_days": 7,
        "prediction_horizon": "1d",   # 1-day forward return — 5-min features have strong signal at this horizon
        "profit_target_pct": 50,
        "stop_loss_pct": 30,
        "min_predicted_move_pct": 0.3,
        "min_confidence": 0.15,       # For classifier models: 0.15 = 57.5% directional probability
        "min_ev_pct": 10,
        "max_position_pct": 20,
        "max_contracts": 5,
        "max_concurrent_positions": 3,
        "max_daily_trades": 5,
        "max_daily_loss_pct": 10,
        "bar_granularity": "5min",
        "feature_set": "swing",
        "model_type": "ensemble",
        "max_spread_pct": 0.12,
        "model_override_min_reversal_pct": 0.5,
        "requires_min_equity": 0,
        "vix_gate_enabled": True,
        "vix_min": 15.0,
        "vix_max": 35.0,
        "implied_move_gate_enabled": True,
        "implied_move_ratio_min": 0.80,
    },
    "general": {
        "min_dte": 21,
        "max_dte": 60,
        "sleeptime": "15M",
        "max_hold_days": 14,
        "prediction_horizon": "10d",
        "profit_target_pct": 40,
        "stop_loss_pct": 25,
        "min_predicted_move_pct": 1.0,
        "min_confidence": 0.15,       # For classifier models: 0.15 = 57.5% directional probability
        "min_ev_pct": 10,
        "max_position_pct": 20,
        "max_contracts": 5,
        "max_concurrent_positions": 3,
        "max_daily_trades": 5,
        "max_daily_loss_pct": 10,
        "bar_granularity": "5min",
        "feature_set": "general",
        "model_type": "ensemble",
        "max_spread_pct": 0.12,
        "model_override_min_reversal_pct": 0.5,
        "requires_min_equity": 0,
        "vix_gate_enabled": True,
        "vix_min": 15.0,
        "vix_max": 35.0,
        "implied_move_gate_enabled": True,
        "implied_move_ratio_min": 0.80,
    },
    "scalp": {
        "min_dte": 0,
        "max_dte": 0,
        "sleeptime": "1M",
        "max_hold_days": 0,
        "prediction_horizon": "30min",
        "profit_target_pct": 20,
        "stop_loss_pct": 15,
        "min_predicted_move_pct": 0.3,
        "min_confidence": 0.10,
        "min_ev_pct": 5,
        "max_position_pct": 10,
        "max_contracts": 10,
        "max_concurrent_positions": 3,
        "max_daily_trades": 20,
        "max_daily_loss_pct": 10,
        "bar_granularity": "1min",
        "feature_set": "scalp",
        "model_type": "xgb_classifier",
        "max_spread_pct": 0.12,
        "model_override_min_reversal_pct": 0.5,
        "requires_min_equity": 25000,
        "vix_gate_enabled": True,
        "vix_min": 15.0,
        "vix_max": 35.0,
        "implied_move_gate_enabled": True,
        "implied_move_ratio_min": 0.80,
    },
}

# Valid model types per preset (used by frontend dropdown + backend validation)
# Regression models (xgboost, lightgbm, tft, ensemble) removed from swing/general —
# they predict near-zero returns due to MSE loss converging to conditional mean.
# Classification models predict direction with confidence, which is actionable.
PRESET_MODEL_TYPES = {
    "swing":   ["xgb_swing_classifier", "lgbm_classifier"],
    "general": ["xgb_swing_classifier", "lgbm_classifier"],
    "scalp":   ["xgb_classifier"],
}

# =============================================================================
# Risk-Free Rate (used in Black-Scholes Greeks and IV calculations)
# =============================================================================
RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.045"))  # Approximate Fed funds rate

# =============================================================================
# Liquidity Gate (options contract pre-trade filter)
# =============================================================================
MIN_OPEN_INTEREST = 100         # Minimum OI for the selected contract
MIN_OPTION_VOLUME = 50          # Minimum daily volume for the selected contract

# =============================================================================
# Earnings Calendar Gate
# =============================================================================
EARNINGS_BLACKOUT_DAYS_BEFORE = 2   # Skip entry if earnings within N days BEFORE entry
EARNINGS_BLACKOUT_DAYS_AFTER = 1    # Skip entry if earnings within N days AFTER hold window

# =============================================================================
# Feedback Loop / Training Queue
# =============================================================================
TRAINING_QUEUE_MIN_SAMPLES = 30     # Min completed trades before auto-retrain

# =============================================================================
# Portfolio Greeks Limits
# =============================================================================
PORTFOLIO_MAX_ABS_DELTA = 5.0       # Max absolute portfolio delta (sum across positions)
PORTFOLIO_MAX_ABS_VEGA = 500.0      # Max absolute portfolio vega

# =============================================================================
# Portfolio-Level Risk Limits (global, across all profiles)
# =============================================================================
MAX_TOTAL_EXPOSURE_PCT = 60
MAX_TOTAL_POSITIONS = 10
EMERGENCY_STOP_LOSS_PCT = 20
DTE_EXIT_FLOOR = 3                     # Close options with fewer than this many DTE

# =============================================================================
# Phase 6: Hardening constants
# =============================================================================

# Circuit breaker — Theta Terminal
THETA_CB_FAILURE_THRESHOLD = 3          # Failures before circuit opens
THETA_CB_RESET_TIMEOUT = 300            # Seconds before testing recovery (5 min)

# Circuit breaker — Alpaca
ALPACA_CB_FAILURE_THRESHOLD = 5         # Failures before circuit opens
ALPACA_CB_RESET_TIMEOUT = 120           # Seconds before testing recovery (2 min)

# Retry / backoff
RETRY_BACKOFF_BASE = 2.0               # Base for exponential backoff (seconds)
RETRY_BACKOFF_MAX = 60.0               # Maximum backoff delay (seconds)
RETRY_MAX_ATTEMPTS = 3                 # Default max retry attempts

# Trading loop resilience
MAX_CONSECUTIVE_ERRORS = 10            # Auto-pause after this many consecutive iteration errors
ITERATION_ERROR_RESET_ON_SUCCESS = True  # Reset error counter on successful iteration

# Watchdog — trading subprocess health monitor
WATCHDOG_POLL_INTERVAL_SECONDS = 30     # How often to check subprocess health
WATCHDOG_AUTO_RESTART = True            # Auto-restart crashed subprocesses
WATCHDOG_MAX_RESTARTS = 3              # Max consecutive auto-restarts per profile
WATCHDOG_RESTART_DELAY_SECONDS = 5     # Delay before restarting a crashed process

# Log rotation
LOG_MAX_BYTES = 10_485_760             # 10 MB per log file
LOG_BACKUP_COUNT = 5                   # Keep 5 rotated backups (50 MB total max)

# Model health monitoring
MODEL_HEALTH_WINDOW_SIZE = 50          # Rolling window of predictions to track
MODEL_STALE_THRESHOLD_DAYS = 30        # Alert if model older than this
MODEL_DEGRADED_THRESHOLD = 0.45        # Alert if rolling accuracy below this (45%)
MODEL_HEALTH_MIN_SAMPLES = 10          # Minimum predictions before computing accuracy
PREDICTION_RESOLVE_MINUTES_SWING = 60  # Minutes to wait before resolving swing predictions
PREDICTION_RESOLVE_MINUTES_SCALP = 30  # Minutes to wait before resolving scalp predictions

# =============================================================================
# Volatility Regime Gate (VIX)
# Using VIXY (VIX ETF) as proxy. Post-reverse-split: VIXY ≈ VIX (1:1 ratio).
# VIXY $15 ≈ VIX 15 (too low vol), VIXY $35 ≈ VIX 35 (too high vol)
# =============================================================================
VIX_MIN_GATE = float(os.getenv("VIX_MIN_GATE", "15.0"))   # Don't trade below this VIXY level
VIX_MAX_GATE = float(os.getenv("VIX_MAX_GATE", "35.0"))   # Don't trade above this VIXY level

# =============================================================================
# Phase C: ML Accuracy Improvements
# =============================================================================

# Optuna hyperparameter optimization
OPTUNA_N_TRIALS = 30                # Max Optuna trials per training run
OPTUNA_TIMEOUT_SECONDS = 300        # Max optimization time (5 min)

# VIX regime-adjusted confidence
VIX_REGIME_LOW_THRESHOLD = 18.0     # VIXY below this = low vol regime (post-reverse-split 1:1 with VIX)
VIX_REGIME_HIGH_THRESHOLD = 28.0    # VIXY above this = high vol regime
VIX_REGIME_LOW_MULTIPLIER = 1.1     # Confidence boost in low vol
VIX_REGIME_NORMAL_MULTIPLIER = 1.0  # No adjustment in normal vol
VIX_REGIME_HIGH_MULTIPLIER = 0.7    # Confidence reduction in high vol
VIX_REGIME_ENABLED = True           # Enable/disable regime adjustment

# VIX term structure tickers (ETF proxies — VIX9D/VIX3M not on Alpaca)
VIX_PROXY_SHORT_TICKER = "VIXY"     # Short-term VIX futures ETF
VIX_PROXY_MID_TICKER = "VIXM"      # Mid-term VIX futures ETF

# =============================================================================
# Alert System
# =============================================================================
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")  # Discord/Slack webhook URL

# =============================================================================
# Logging
# =============================================================================
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"

# =============================================================================
# Version
# =============================================================================
VERSION = "0.3.0"
