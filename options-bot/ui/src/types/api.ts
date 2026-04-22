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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    [key: string]: any;
  };
  age_days: number;
}

export interface StrategyType {
  preset_name: string;
  display_name: string;
  description: string;
  category: string;
  min_capital: number;
  valid_model_types: string[];
  default_config: Record<string, unknown>;
  supports_symbols: string[];
  is_intraday: boolean;
}

export interface Profile {
  id: string;
  name: string;
  preset: string;
  status: 'created' | 'training' | 'ready' | 'active' | 'paused' | 'error';
  error_reason?: string | null;
  symbols: string[];
  config: Record<string, unknown>;
  model_summary: ModelSummary | null;
  trained_models: ModelSummary[];
  valid_model_types: string[];
  active_positions: number;
  total_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  created_at: string;
  updated_at: string;
  // Prompt 26: pre-joined learning state for this profile's accepted
  // setup_types. Empty object = no learning_state rows yet. Used by
  // ProfileDetail's per-profile panel and Dashboard's per-card summary.
  learning_state_by_setup_type?: Record<string, LearningStateEntry>;
  // Prompt 26: full list of setup_types this profile accepts. UI
  // uses length as the denominator in "N of M setup types adjusted"
  // headers so the count is truthful even before any learning_state
  // row has been written.
  accepted_setup_types?: string[];
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
  entry_model_type: string | null;
  exit_reason: string | null;
  hold_days: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  status: 'open' | 'closed' | 'cancelled';
  was_day_trade: boolean;
  created_at: string;
  updated_at: string;
  setup_type: string | null;
  confidence_score: number | null;
  hold_minutes: number | null;
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

export interface CircuitBreakerState {
  theta_breaker_state: string;
  alpaca_breaker_state: string;
  theta_failure_count: number;
  alpaca_failure_count: number;
  last_updated: string;
}

export interface SystemStatus {
  alpaca_connected: boolean;
  alpaca_subscription: string;
  theta_terminal_connected: boolean;
  active_profiles: number;
  total_open_positions: number;
  max_total_positions: number;
  pdt_day_trades_5d: number;
  pdt_limit: number;
  portfolio_value: number;
  uptime_seconds: number;
  last_error: string | null;
  last_error_at: string | null;
  check_errors: string[];
  circuit_breaker_states: Record<string, CircuitBreakerState>;
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

export interface TrainingQueueStatus {
  pending_count: number;
  min_samples_for_retrain: number;
  ready_for_retrain: boolean;
  oldest_pending_at: string | null;
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

// Phase 6 — Model Health Monitoring
export interface ModelHealthEntry {
  profile_id: string;
  profile_name: string;
  model_type: string;
  rolling_accuracy: number | null;
  total_predictions: number;
  correct_predictions: number;
  status: 'healthy' | 'warning' | 'degraded' | 'insufficient_data' | 'stale' | 'no_data' | 'unknown';
  message: string;
  model_age_days: number | null;
  updated_at: string | null;
}

export interface ModelHealthResponse {
  profiles: ModelHealthEntry[];
  any_degraded: boolean;
  any_stale: boolean;
  summary: string;
}

// Phase 4.5 — Signal Decision Log
export interface SignalLogEntry {
  id: number;
  profile_id: string;
  timestamp: string;
  symbol: string;
  underlying_price: number | null;
  predicted_return: number | null;
  predictor_type: string | null;
  step_stopped_at: number | null;   // 1-12 matching entry logic; null if entered
  stop_reason: string | null;
  entered: boolean;
  trade_id: string | null;
}

// V2 Signal Decision Log — scorer evaluations with full factor breakdown
export interface V2SignalLogEntry {
  id: number;
  timestamp: string;
  profile_name: string;
  symbol: string;
  setup_type: string | null;
  setup_score: number | null;
  confidence_score: number | null;
  raw_score: number | null;
  regime: string | null;
  regime_reason: string | null;
  time_of_day: string | null;
  signal_clarity: number | null;
  regime_fit: number | null;
  ivr: number | null;
  // institutional_flow removed in Prompt 25. Column still exists in
  // the DB for historical rows but the API no longer exposes it.
  historical_perf: number | null;
  sentiment: number | null;
  time_of_day_score: number | null;
  threshold_label: string | null;
  entered: boolean;
  trade_id: string | null;
  block_reason: string | null;
}

// Learning Layer State
// Prompt 26: field renamed from profile_name -> setup_type. The DB
// column stores a setup_type value (Bug B rename), the API field now
// reflects reality. DB column stays named profile_name for stability.
export interface ProfileLearningState {
  setup_type: string;
  min_confidence: number;
  regime_fit_overrides: Record<string, number>;
  paused_by_learning: boolean;
  last_adjustment: string | null;
  recent_adjustments: Array<{
    type: string;
    timestamp: string;
    old: number | string | null;
    new: number | string | null;
    reason: string;
  }>;
}

export interface LearningStateResponse {
  profiles: ProfileLearningState[];
}

export interface ResumeResponse {
  // Prompt 26: same rename as ProfileLearningState.
  setup_type: string;
  paused_by_learning: boolean;
  message: string;
}

// Prompt 26: per-profile learning state scoped to the profile's
// accepted_setup_types. Keyed by setup_type. See ProfileResponse.
export interface LearningStateEntry {
  setup_type: string;
  min_confidence: number;
  regime_fit_overrides: Record<string, number>;
  paused_by_learning: boolean;
  last_adjustment: string | null;
}

// Prompt 27 Commit A: UI filter dropdown options. Single source of
// truth is the profile class attributes (profiles.__init__.py),
// exposed via /api/meta/filter-options.
export interface FilterOptions {
  setup_types: string[];
  profile_names: string[];
}

// Market Context
export interface RegimeResponse {
  regime: string | null;
  time_of_day: string | null;
  timestamp: string | null;
  spy_30min_move_pct: number | null;
  spy_60min_range_pct: number | null;
  spy_30min_reversals: number | null;
  spy_volume_ratio: number | null;
  vix_level: number | null;
  vix_intraday_change_pct: number | null;
  regime_reason: string | null;
  available: boolean;
}

// Scanner
export interface SetupDetail {
  setup_type: string;
  score: number;
  direction: string;
  reason: string;
}

export interface SymbolScanResult {
  symbol: string;
  best_setup: string | null;
  best_score: number;
  setups: SetupDetail[];
}

export interface ScannerResponse {
  timestamp: string | null;
  regime: string | null;
  active_setups: SymbolScanResult[];
}

// Equity Curve
export interface EquityCurvePoint {
  timestamp: string;
  pnl_dollars: number;
  cumulative_pnl: number;
  symbol: string;
  setup_type: string | null;
}

export interface EquityCurveResponse {
  points: EquityCurvePoint[];
  total_pnl: number;
  trade_count: number;
}

// Macro awareness layer — matches backend/schemas.py Macro*Response
export interface MacroEvent {
  symbol: string;
  event_type: string;
  event_time_et: string;
  impact_level: 'HIGH' | 'MEDIUM' | 'LOW';
  source_url: string;
  fetched_at: string;
  minutes_until: number;
}

export interface MacroCatalyst {
  symbol: string;
  catalyst_type: string;
  direction: 'bullish' | 'bearish' | 'neutral';
  severity: number;
  summary: string;
  source_url: string;
  expires_at: string;
  fetched_at: string;
}

export interface MacroRegime {
  risk_tone: 'risk_on' | 'risk_off' | 'mixed' | 'unknown';
  vix_context: string | null;
  major_themes: string[];
  fetched_at: string;
  is_stale: boolean;
}

export interface MacroStateResponse {
  events: MacroEvent[];
  catalysts: MacroCatalyst[];
  regime: MacroRegime | null;
  api_calls_today: number;
  api_cap: number;
}
