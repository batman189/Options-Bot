"""
Pydantic request/response schemas.
These define the API contract. Matches PROJECT_ARCHITECTURE.md Section 5c.

RULE: If the UI needs a field, it MUST be defined here FIRST.
If this file needs to change during Phase 3, that is a Phase 1 defect.
"""

from pydantic import BaseModel
from typing import Optional


# =============================================================================
# Profile Schemas
# =============================================================================

class ProfileCreate(BaseModel):
    name: str
    preset: str  # 'swing', 'general', 'scalp'
    symbols: list[str]
    config_overrides: dict = {}

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    symbols: Optional[list[str]] = None
    config_overrides: Optional[dict] = None

class ModelSummary(BaseModel):
    id: str
    model_type: str
    status: str
    trained_at: Optional[str] = None
    data_range: str
    metrics: dict
    age_days: int

class ProfileResponse(BaseModel):
    id: str
    name: str
    preset: str
    status: str
    symbols: list[str]
    config: dict
    model_summary: Optional[ModelSummary] = None
    active_positions: int
    total_pnl: float
    created_at: str
    updated_at: str


# =============================================================================
# Model Schemas
# =============================================================================

class ModelResponse(BaseModel):
    id: str
    profile_id: str
    model_type: str
    file_path: str
    status: str
    training_started_at: Optional[str] = None
    training_completed_at: Optional[str] = None
    data_start_date: Optional[str] = None
    data_end_date: Optional[str] = None
    metrics: Optional[dict] = None
    feature_names: Optional[list[str]] = None
    hyperparameters: Optional[dict] = None
    created_at: str

class TrainRequest(BaseModel):
    """Optional overrides for training parameters."""
    force_full_retrain: bool = False
    model_type: Optional[str] = None  # 'xgboost' | 'tft' | 'ensemble' — default xgboost

class TrainingStatus(BaseModel):
    model_id: Optional[str] = None
    profile_id: str
    status: str  # 'idle', 'training', 'completed', 'failed'
    progress_pct: Optional[float] = None
    message: Optional[str] = None

class ModelMetrics(BaseModel):
    model_id: str
    profile_id: str
    model_type: str
    mae: Optional[float] = None
    rmse: Optional[float] = None
    r2: Optional[float] = None
    directional_accuracy: Optional[float] = None
    training_samples: Optional[int] = None
    feature_count: Optional[int] = None
    cv_folds: Optional[int] = None
    feature_importance: Optional[dict] = None

class TrainingLogEntry(BaseModel):
    id: int
    model_id: str
    timestamp: str
    level: str
    message: str


# =============================================================================
# Trade Schemas
# =============================================================================

class TradeResponse(BaseModel):
    id: str
    profile_id: str
    symbol: str
    direction: str
    strike: float
    expiration: str
    quantity: int
    entry_price: Optional[float] = None
    entry_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    pnl_dollars: Optional[float] = None
    pnl_pct: Optional[float] = None
    predicted_return: Optional[float] = None
    ev_at_entry: Optional[float] = None
    exit_reason: Optional[str] = None
    hold_days: Optional[int] = None
    status: str
    was_day_trade: bool
    created_at: str
    updated_at: str

class TradeStats(BaseModel):
    total_trades: int
    open_trades: int
    closed_trades: int
    win_count: int
    loss_count: int
    win_rate: Optional[float] = None
    total_pnl_dollars: float
    avg_pnl_pct: Optional[float] = None
    best_trade_pct: Optional[float] = None
    worst_trade_pct: Optional[float] = None
    avg_hold_days: Optional[float] = None


# =============================================================================
# System Schemas
# =============================================================================

class SystemStatus(BaseModel):
    alpaca_connected: bool
    alpaca_subscription: str
    theta_terminal_connected: bool
    active_profiles: int
    total_open_positions: int
    pdt_day_trades_5d: int
    pdt_limit: int
    portfolio_value: float
    uptime_seconds: int
    last_error: Optional[str] = None

class HealthCheck(BaseModel):
    status: str
    timestamp: str
    version: str

class PDTStatus(BaseModel):
    day_trades_5d: int
    limit: int
    remaining: int
    equity: float
    is_restricted: bool

class ErrorLogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    source: Optional[str] = None


# =============================================================================
# Backtest Schemas (Phase 2 — stubbed)
# =============================================================================

class BacktestRequest(BaseModel):
    start_date: str
    end_date: str
    initial_capital: float = 25000.0

class BacktestResult(BaseModel):
    profile_id: str
    status: str  # 'pending', 'running', 'completed', 'failed'
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total_trades: Optional[int] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    total_return_pct: Optional[float] = None
    win_rate: Optional[float] = None
    message: Optional[str] = None


# =============================================================================
# Trading Control Schemas
# =============================================================================

class TradingProcessInfo(BaseModel):
    profile_id: str
    profile_name: str
    pid: Optional[int] = None
    status: str  # 'stopped', 'starting', 'running', 'stopping', 'crashed'
    started_at: Optional[str] = None
    uptime_seconds: Optional[int] = None
    exit_reason: Optional[str] = None

class TradingStatusResponse(BaseModel):
    processes: list[TradingProcessInfo]
    total_running: int
    total_stopped: int

class TradingStartRequest(BaseModel):
    profile_ids: list[str]

class TradingStartResponse(BaseModel):
    started: list[TradingProcessInfo]
    errors: list[dict]

class TradingStopRequest(BaseModel):
    profile_ids: Optional[list[str]] = None  # None = stop all

class TradingStopResponse(BaseModel):
    stopped: list[str]
    errors: list[dict]
