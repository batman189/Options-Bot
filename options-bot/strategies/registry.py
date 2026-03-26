"""
Strategy Registry — central mapping of strategy types to their classes and metadata.

Each strategy type is registered here with everything the platform needs:
- Strategy class (Lumibot Strategy subclass)
- Default config
- Valid model types
- UI description
- Capital requirements
- Feature set identifier
- Timing parameters (bars_per_day, is_intraday, lookback, etc.)

New strategy types are added by:
1. Creating a strategy class that extends BaseOptionsStrategy
2. Adding an entry to STRATEGY_TYPES below
3. No other files need to change
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StrategyTypeInfo:
    """Metadata for a registered strategy type."""
    preset_name: str                    # Key used in DB and config (e.g., "momentum_scalp")
    display_name: str                   # Human-readable name for UI (e.g., "Momentum Scalp")
    description: str                    # Brief description for profile creation UI
    strategy_module: str                # Python module path (e.g., "strategies.momentum_scalp_strategy")
    strategy_class_name: str            # Class name within the module (e.g., "MomentumScalpStrategy")
    default_config: dict                # Default configuration values
    valid_model_types: list[str]        # Allowed model types for this strategy
    feature_set: str                    # Feature set identifier ("momentum", "daily_swing", "scalp", etc.)
    min_capital: int                    # Minimum account equity to activate ($)
    is_intraday: bool                   # True = uses 1-min bars, False = daily bars
    bars_per_day: int                   # 390 for 1-min, 78 for 5-min, 1 for daily
    lookback_bars: int                  # How many bars to fetch for feature computation
    warmup_days: int                    # Days of warmup data needed before trading
    check_frequency: str                # How often to run ("1M" = every minute, "5M", "15M", "1D")
    category: str = "directional"       # Category for UI grouping: "directional", "premium_selling", "volatility"
    requires_options_data: bool = True  # Whether ThetaData options chain is needed
    supports_symbols: list[str] = field(default_factory=lambda: ["ANY"])  # "ANY" or specific tickers


# =============================================================================
# Strategy Type Definitions
# =============================================================================

STRATEGY_TYPES: dict[str, StrategyTypeInfo] = {}


def register_strategy(info: StrategyTypeInfo):
    """Register a strategy type. Called at module load time."""
    STRATEGY_TYPES[info.preset_name] = info


def get_strategy_class(preset_name: str):
    """
    Import and return the strategy class for the given preset name.
    Raises ValueError if preset is not registered.
    """
    if preset_name not in STRATEGY_TYPES:
        raise ValueError(
            f"Unknown strategy type '{preset_name}'. "
            f"Registered types: {list(STRATEGY_TYPES.keys())}"
        )
    info = STRATEGY_TYPES[preset_name]
    import importlib
    module = importlib.import_module(info.strategy_module)
    return getattr(module, info.strategy_class_name)


def get_strategy_info(preset_name: str) -> StrategyTypeInfo:
    """Get metadata for a registered strategy type."""
    if preset_name not in STRATEGY_TYPES:
        raise ValueError(f"Unknown strategy type '{preset_name}'")
    return STRATEGY_TYPES[preset_name]


def get_default_config(preset_name: str) -> dict:
    """Get default config for a strategy type."""
    return get_strategy_info(preset_name).default_config.copy()


def get_valid_model_types(preset_name: str) -> list[str]:
    """Get valid model types for a strategy type."""
    return get_strategy_info(preset_name).valid_model_types


def get_all_strategy_types() -> list[dict]:
    """
    Return all registered strategy types as dicts for the API.
    Used by GET /api/strategy-types endpoint.
    """
    result = []
    for name, info in STRATEGY_TYPES.items():
        result.append({
            "preset_name": info.preset_name,
            "display_name": info.display_name,
            "description": info.description,
            "category": info.category,
            "min_capital": info.min_capital,
            "valid_model_types": info.valid_model_types,
            "default_config": info.default_config,
            "supports_symbols": info.supports_symbols,
            "is_intraday": info.is_intraday,
        })
    return result


# =============================================================================
# Register all built-in strategy types
# =============================================================================

# --- Momentum Scalp (Profile 1) ---
register_strategy(StrategyTypeInfo(
    preset_name="momentum_scalp",
    display_name="Momentum Scalp",
    description="Detects and rides strong intraday directional moves on 0DTE options. Best for SPY, QQQ.",
    strategy_module="strategies.scalp_strategy",
    strategy_class_name="ScalpStrategy",
    default_config={
        "min_dte": 0,
        "max_dte": 0,
        "sleeptime": "30S",
        "max_hold_days": 1,
        "prediction_horizon": "30min",
        "profit_target_pct": 200,
        "stop_loss_pct": 15,
        "min_predicted_move_pct": 0.3,
        "min_confidence": 0.25,
        "entry_cooldown_minutes": 10,
        "min_ev_pct": 3,
        "max_position_pct": 25,
        "max_contracts": 10,
        "max_concurrent_positions": 1,
        "max_daily_trades": 3,
        "max_daily_loss_pct": 5,
        "bar_granularity": "1min",
        "feature_set": "momentum",
        "model_type": "xgb_classifier",
        "max_spread_pct": 0.12,
        "min_premium": 0.75,
        "moneyness_range_pct": 1.0,
        "prefer_atm": True,
        "requires_min_equity": 0,
        "vix_gate_enabled": True,
        "vix_min": 12.0,
        "vix_max": 50.0,
        "implied_move_gate_enabled": False,
        "underlying_reversal_pct": 1.0,
        "trailing_stop_activation_pct": 10,
        "trailing_stop_pct": 5,
    },
    valid_model_types=["xgb_classifier", "momentum_classifier"],
    feature_set="momentum",
    min_capital=5000,
    is_intraday=True,
    bars_per_day=390,
    lookback_bars=2000,
    warmup_days=10,
    check_frequency="30S",
    category="directional",
))

# --- Scalp (legacy — maps to same class as momentum_scalp for backward compat) ---
register_strategy(StrategyTypeInfo(
    preset_name="scalp",
    display_name="Scalp (Legacy)",
    description="Legacy 0DTE scalping profile. Use Momentum Scalp for new profiles.",
    strategy_module="strategies.scalp_strategy",
    strategy_class_name="ScalpStrategy",
    default_config={
        "min_dte": 0,
        "max_dte": 0,
        "sleeptime": "1M",
        "max_hold_days": 1,
        "prediction_horizon": "30min",
        "profit_target_pct": 80,
        "stop_loss_pct": 15,
        "min_predicted_move_pct": 0.3,
        "min_confidence": 0.25,
        "entry_cooldown_minutes": 10,
        "min_ev_pct": 3,
        "max_position_pct": 25,
        "max_contracts": 10,
        "max_concurrent_positions": 3,
        "max_daily_trades": 999,
        "max_daily_loss_pct": 10,
        "bar_granularity": "1min",
        "feature_set": "scalp",
        "model_type": "xgb_classifier",
        "max_spread_pct": 0.12,
        "min_premium": 0.75,
        "moneyness_range_pct": 1.0,
        "prefer_atm": True,
        "requires_min_equity": 0,
        "vix_gate_enabled": True,
        "vix_min": 12.0,
        "vix_max": 50.0,
        "implied_move_gate_enabled": False,
        "underlying_reversal_pct": 1.0,
        "trailing_stop_activation_pct": 10,
        "trailing_stop_pct": 5,
    },
    valid_model_types=["xgb_classifier"],
    feature_set="scalp",
    min_capital=5000,
    is_intraday=True,
    bars_per_day=390,
    lookback_bars=2000,
    warmup_days=10,
    check_frequency="1M",
    category="directional",
))

# --- OTM Scalp (legacy — backward compat) ---
register_strategy(StrategyTypeInfo(
    preset_name="otm_scalp",
    display_name="OTM Scalp (Legacy)",
    description="Legacy OTM 0DTE profile. Use OTM Gamma for new profiles.",
    strategy_module="strategies.scalp_strategy",
    strategy_class_name="ScalpStrategy",
    default_config={
        "min_dte": 0,
        "max_dte": 0,
        "sleeptime": "1M",
        "max_hold_days": 1,
        "prediction_horizon": "30min",
        "profit_target_pct": 300,
        "stop_loss_pct": 80,
        "min_predicted_move_pct": 0.3,
        "min_confidence": 0.30,
        "entry_cooldown_minutes": 60,
        "min_ev_pct": 1,
        "max_position_pct": 10,
        "max_contracts": 100,
        "max_concurrent_positions": 3,
        "max_daily_trades": 3,
        "max_daily_loss_pct": 20,
        "bar_granularity": "1min",
        "feature_set": "scalp",
        "model_type": "xgb_classifier",
        "max_spread_pct": 0.30,
        "min_premium": 0.03,
        "max_premium": 1.50,
        "moneyness_range_pct": 8.0,
        "prefer_atm": False,
        "requires_min_equity": 0,
        "vix_gate_enabled": True,
        "vix_min": 12.0,
        "vix_max": 50.0,
        "implied_move_gate_enabled": False,
        "underlying_reversal_pct": 1.0,
        "trailing_stop_activation_pct": 50,
        "trailing_stop_pct": 30,
    },
    valid_model_types=["xgb_classifier"],
    feature_set="scalp",
    min_capital=10000,
    is_intraday=True,
    bars_per_day=390,
    lookback_bars=2000,
    warmup_days=10,
    check_frequency="1M",
    category="volatility",
))

# --- Swing (Profile 2) ---
register_strategy(StrategyTypeInfo(
    preset_name="swing",
    display_name="Swing",
    description="Multi-day directional trades on sector/stock trends, 7-45 DTE. Best for TSLA, AAPL, individual stocks.",
    strategy_module="strategies.swing_strategy",
    strategy_class_name="SwingStrategy",
    default_config={
        "min_dte": 14,
        "max_dte": 45,
        "sleeptime": "5M",
        "max_hold_days": 10,
        "prediction_horizon": "10d",
        "profit_target_pct": 100,
        "stop_loss_pct": 12,
        "min_predicted_move_pct": 1.0,
        "min_confidence": 0.22,
        "entry_cooldown_minutes": 30,
        "min_ev_pct": 10,
        "max_position_pct": 30,
        "max_contracts": 5,
        "max_concurrent_positions": 1,
        "max_daily_trades": 999,
        "max_daily_loss_pct": 10,
        "bar_granularity": "5min",
        "feature_set": "swing",
        "model_type": "lgbm_classifier",
        "max_spread_pct": 0.12,
        "requires_min_equity": 0,
        "vix_gate_enabled": True,
        "vix_min": 15.0,
        "vix_max": 50.0,
        "implied_move_gate_enabled": False,
        "underlying_reversal_pct": 2.5,
        "underlying_trail_activation_pct": 2.0,  # Trailing activates when underlying moves 2% in your favor
        "underlying_trail_pct": 1.5,              # Exit if underlying pulls back 1.5% from peak
        "trailing_stop_activation_pct": 15,
        "trailing_stop_pct": 8,
    },
    valid_model_types=["xgb_swing_classifier", "lgbm_classifier"],
    feature_set="swing",
    min_capital=5000,
    is_intraday=False,
    bars_per_day=78,
    lookback_bars=4000,
    warmup_days=45,
    check_frequency="5M",
    category="directional",
))

# --- General (legacy — backward compat, maps to swing) ---
register_strategy(StrategyTypeInfo(
    preset_name="general",
    display_name="General (Legacy)",
    description="Legacy general-purpose profile. Use Swing for new profiles.",
    strategy_module="strategies.general_strategy",
    strategy_class_name="GeneralStrategy",
    default_config={
        "min_dte": 14,
        "max_dte": 60,
        "sleeptime": "15M",
        "max_hold_days": 14,
        "prediction_horizon": "10d",
        "profit_target_pct": 100,
        "stop_loss_pct": 12,
        "min_predicted_move_pct": 1.0,
        "min_confidence": 0.22,
        "entry_cooldown_minutes": 30,
        "min_ev_pct": 10,
        "max_position_pct": 30,
        "max_contracts": 5,
        "max_concurrent_positions": 3,
        "max_daily_trades": 999,
        "max_daily_loss_pct": 10,
        "bar_granularity": "5min",
        "feature_set": "general",
        "model_type": "lgbm_classifier",
        "max_spread_pct": 0.12,
        "requires_min_equity": 0,
        "vix_gate_enabled": True,
        "vix_min": 15.0,
        "vix_max": 35.0,
        "implied_move_gate_enabled": True,
        "implied_move_ratio_min": 0.80,
        "underlying_reversal_pct": 2.0,
        "trailing_stop_activation_pct": 15,
        "trailing_stop_pct": 8,
    },
    valid_model_types=["xgb_swing_classifier", "lgbm_classifier"],
    feature_set="general",
    min_capital=5000,
    is_intraday=False,
    bars_per_day=78,
    lookback_bars=4000,
    warmup_days=45,
    check_frequency="15M",
    category="directional",
))

# --- Iron Condor (Profile 3) ---
register_strategy(StrategyTypeInfo(
    preset_name="iron_condor",
    display_name="Iron Condor",
    description="Sells premium in range-bound markets with GEX regime filter. Requires $25K+ account.",
    strategy_module="strategies.iron_condor_strategy",
    strategy_class_name="IronCondorStrategy",
    default_config={
        "min_dte": 0,
        "max_dte": 0,
        "sleeptime": "5M",
        "max_hold_days": 1,
        "prediction_horizon": "30min",
        "min_confidence": 0.10,
        "entry_cooldown_minutes": 30,
        "max_position_pct": 5,
        "max_contracts": 10,
        "max_concurrent_positions": 3,
        "max_daily_trades": 5,
        "max_daily_loss_pct": 5,
        "bar_granularity": "1min",
        "feature_set": "scalp",
        "model_type": "xgb_classifier",
        "requires_min_equity": 25000,
        "vix_gate_enabled": False,
        "ic_target_delta": 0.16,
        "ic_spread_width": 3.0,
        "ic_profit_target_pct": 75,
        "ic_stop_multiplier": 1.0,
        "gex_cache_minutes": 5,
        "max_confidence_for_ic": 0.35,
    },
    valid_model_types=["xgb_classifier"],
    feature_set="scalp",
    min_capital=25000,
    is_intraday=True,
    bars_per_day=390,
    lookback_bars=2000,
    warmup_days=10,
    check_frequency="5M",
    category="premium_selling",
))

# --- OTM Gamma (Profile 4) ---
register_strategy(StrategyTypeInfo(
    preset_name="otm_gamma",
    display_name="OTM Gamma",
    description="Buys cheap far-OTM options for rare explosive gamma moves. Requires $10K+ account.",
    strategy_module="strategies.scalp_strategy",
    strategy_class_name="ScalpStrategy",
    default_config={
        "min_dte": 0,
        "max_dte": 0,
        "sleeptime": "1M",
        "max_hold_days": 1,
        "prediction_horizon": "30min",
        "profit_target_pct": 500,
        "stop_loss_pct": 100,
        "min_predicted_move_pct": 0.3,
        "min_confidence": 0.30,
        "entry_cooldown_minutes": 60,
        "min_ev_pct": 1,
        "max_position_pct": 10,
        "max_contracts": 100,
        "max_concurrent_positions": 1,
        "max_daily_trades": 3,
        "max_daily_loss_pct": 20,
        "bar_granularity": "1min",
        "feature_set": "scalp",
        "model_type": "xgb_classifier",
        "max_spread_pct": 0.30,
        "min_premium": 0.10,
        "max_premium": 0.50,
        "moneyness_range_pct": 2.0,
        "prefer_atm": False,
        "requires_min_equity": 0,
        "vix_gate_enabled": True,
        "vix_min": 12.0,
        "vix_max": 50.0,
        "implied_move_gate_enabled": False,
        "underlying_reversal_pct": 1.0,
        "trailing_stop_activation_pct": 100,
        "trailing_stop_pct": 30,
    },
    valid_model_types=["xgb_classifier"],
    feature_set="scalp",
    min_capital=10000,
    is_intraday=True,
    bars_per_day=390,
    lookback_bars=2000,
    warmup_days=10,
    check_frequency="1M",
    category="volatility",
))
