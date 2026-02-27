// ============================================================
// Types matching backend/schemas.py exactly.
// Field names must match the JSON keys returned by the API.
// ============================================================

export interface ModelSummary {
  id: string;
  model_type: string;
  status: string;
  trained_at: string | null;
  data_range: string;
  metrics: {
    mae?: number;
    rmse?: number;
    r2?: number;
    dir_acc?: number;
    [key: string]: number | undefined;
  };
  age_days: number;
}

export interface Profile {
  id: string;
  name: string;
  preset: 'swing' | 'general' | 'scalp';
  status: 'created' | 'training' | 'ready' | 'active' | 'paused' | 'error';
  symbols: string[];
  config: Record<string, unknown>;
  model_summary: ModelSummary | null;
  trained_models: ModelSummary[];
  active_positions: number;
  total_pnl: number;
  created_at: string;
  updated_at: string;
}

export interface ProfileCreate {
  name: string;
  preset: string;
  symbols: string[];
  config_overrides?: Record<string, unknown>;
}

export interface ProfileUpdate {
  name?: string;
  symbols?: string[];
  config_overrides?: Record<string, unknown>;
}

export interface TrainingStatus {
  model_id: string | null;
  profile_id: string;
  status: 'idle' | 'training' | 'completed' | 'failed';
  progress_pct: number | null;
  message: string | null;
}

export interface ModelMetrics {
  model_id: string;
  profile_id: string;
  model_type: string;
  mae: number | null;
  rmse: number | null;
  r2: number | null;
  directional_accuracy: number | null;
  training_samples: number | null;
  feature_count: number | null;
  cv_folds: number | null;
  feature_importance: Record<string, number> | null;
}

export interface FeatureImportanceResponse {
  model_id: string;
  model_type: string;
  feature_importance: Record<string, number>;
}

export interface TrainingLogEntry {
  id: number;
  model_id: string;
  timestamp: string;
  level: 'info' | 'warning' | 'error';
  message: string;
}

export interface Trade {
  id: string;
  profile_id: string;
  symbol: string;
  direction: string;
  strike: number;
  expiration: string;
  quantity: number;
  entry_price: number | null;
  entry_date: string | null;
  exit_price: number | null;
  exit_date: string | null;
  pnl_dollars: number | null;
  pnl_pct: number | null;
  predicted_return: number | null;
  ev_at_entry: number | null;
  exit_reason: string | null;
  hold_days: number | null;
  status: 'open' | 'closed' | 'cancelled';
  was_day_trade: boolean;
  created_at: string;
  updated_at: string;
}

export interface TradeStats {
  total_trades: number;
  open_trades: number;
  closed_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number | null;
  total_pnl_dollars: number;
  avg_pnl_pct: number | null;
  best_trade_pct: number | null;
  worst_trade_pct: number | null;
  avg_hold_days: number | null;
}

export interface SystemStatus {
  alpaca_connected: boolean;
  alpaca_subscription: string;
  theta_terminal_connected: boolean;
  active_profiles: number;
  total_open_positions: number;
  pdt_day_trades_5d: number;
  pdt_limit: number;
  portfolio_value: number;
  uptime_seconds: number;
  last_error: string | null;
  check_errors: string[];
}

export interface HealthCheck {
  status: string;
  timestamp: string;
  version: string;
}

export interface PDTStatus {
  day_trades_5d: number;
  limit: number;
  remaining: number;
  equity: number;
  is_restricted: boolean;
}

export interface ErrorLogEntry {
  timestamp: string;
  level: string;
  message: string;
  source: string | null;
}

export interface BacktestRequest {
  start_date: string;
  end_date: string;
  initial_capital?: number;
}

export interface BacktestResult {
  profile_id: string;
  status: 'not_run' | 'running' | 'completed' | 'failed' | 'error';
  start_date: string | null;
  end_date: string | null;
  total_trades: number | null;
  sharpe_ratio: number | null;
  max_drawdown_pct: number | null;
  total_return_pct: number | null;
  win_rate: number | null;
  message: string | null;
}

// =============================================================
// Trading Controls
// =============================================================

export interface TradingProcessInfo {
  profile_id: string;
  profile_name: string;
  pid: number | null;
  status: 'stopped' | 'starting' | 'running' | 'stopping' | 'crashed';
  started_at: string | null;
  uptime_seconds: number | null;
  exit_reason: string | null;
}

export interface TradingStatusResponse {
  processes: TradingProcessInfo[];
  total_running: number;
  total_stopped: number;
}

export interface TradingStartResponse {
  started: TradingProcessInfo[];
  errors: Array<{ profile_id: string; message: string }>;
}

export interface TradingStopResponse {
  stopped: string[];
  errors: Array<{ profile_id: string; message: string }>;
}

export interface StartableProfile {
  id: string;
  name: string;
  preset: string;
  status: string;
  symbols: string[];
  is_running: boolean;
}
