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
        "prediction_horizon": "5d",
        "profit_target_pct": 50,
        "stop_loss_pct": 30,
        "min_predicted_move_pct": 1.0,
        "min_ev_pct": 10,
        "max_position_pct": 20,
        "max_contracts": 5,
        "max_concurrent_positions": 3,
        "max_daily_trades": 5,
        "max_daily_loss_pct": 10,
        "bar_granularity": "5min",
        "feature_set": "swing",
        "model_type": "xgboost",
        "requires_min_equity": 0,
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
        "min_ev_pct": 10,
        "max_position_pct": 20,
        "max_contracts": 5,
        "max_concurrent_positions": 3,
        "max_daily_trades": 5,
        "max_daily_loss_pct": 10,
        "bar_granularity": "5min",
        "feature_set": "general",
        "model_type": "xgboost",
        "requires_min_equity": 0,
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
        "min_confidence": 0.60,
        "min_ev_pct": 5,
        "max_position_pct": 10,
        "max_contracts": 10,
        "max_concurrent_positions": 3,
        "max_daily_trades": 20,
        "max_daily_loss_pct": 10,
        "bar_granularity": "1min",
        "feature_set": "scalp",
        "model_type": "xgb_classifier",
        "requires_min_equity": 25000,
    },
}

# =============================================================================
# Portfolio-Level Risk Limits (global, across all profiles)
# =============================================================================
MAX_TOTAL_EXPOSURE_PCT = 60
MAX_TOTAL_POSITIONS = 10
EMERGENCY_STOP_LOSS_PCT = 20

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

# =============================================================================
# Logging
# =============================================================================
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
