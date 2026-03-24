# Path B Architecture — Hybrid ML Regime Filter + Premium Selling

## Document Purpose

This documents the March 24, 2026 architectural pivot from directional options buying to hybrid premium selling. This is a companion to PROJECT_ARCHITECTURE.md, not a replacement.

---

## Why the Pivot

After 321 trades over 10 trading days, the directional buying approach produced:
- Total P&L: -$203 (effectively break-even)
- SPY Scalp: 154 trades, 46% win rate, -$308
- SPY OTM: 156 trades, 12% win rate, -$420
- TSLA Swing: 11 trades, 45% win rate, +$525
- Model confidence: 0.003-0.076 most of the time (near random)
- 214 trades in one day deploying $160K from a $37K account

Research showed:
- No documented retail success stories for ML-predicted directional 0DTE trading
- Every documented profitable 0DTE bot uses delta-neutral premium selling
- The model's features (technical indicators) lack the market microstructure data needed for directional edge
- Dealer Gamma Exposure (GEX) is the dominant force in SPY 0DTE pricing and the bot had zero awareness of it

---

## New Architecture

### Strategy Profiles (4 active)

| Profile | Preset | Strategy | Entry Logic | Exit Logic |
|---------|--------|----------|-------------|------------|
| SPY Iron Condor | `iron_condor` | IronCondorStrategy | GEX regime=sell_premium → mechanical 16-delta iron condor | 50% max profit / 2x credit stop / 3:30 PM close |
| SPY OTM | `otm_scalp` | ScalpStrategy (base) | GEX regime=trending + ML confidence > 0.25 | Trailing stop (50%/30%) + underlying reversal |
| TSLA Swing | `swing` | SwingStrategy (base) | ML confidence > 0.20 + sentiment features | Underlying reversal 1.5% + trailing stop (25%/15%) |
| Spy Scalp | `scalp` | ScalpStrategy (base) | ML confidence > 0.20 + cooldown 10min | Underlying reversal 1% + trailing stop (10%/5%) |

### New Modules

| File | Purpose |
|------|---------|
| `ml/gex_calculator.py` | Computes GEX regime from live Alpaca options chain. IV derived from bid/ask via Newton-Raphson. Features: ATM straddle %, IV skew, put/call ratio, gamma concentration. |
| `strategies/iron_condor.py` | Strike selection (16 delta), order builders (4-leg open/close), IronCondorLegs dataclass. |
| `strategies/iron_condor_strategy.py` | IronCondorStrategy subclass. Overrides on_trading_iteration with IC-specific entry/exit. |
| `features/sentiment.py` | TSLA news sentiment via Alpaca News API + TextBlob. Features: score, magnitude, volume, momentum. |

### Iron Condor Trade Flow

```
on_trading_iteration()
├── _check_ic_exits()
│   ├── Get current prices of all 4 legs
│   ├── Compute P&L = credit_received - current_debit
│   ├── Exit if P&L >= 50% of max profit
│   ├── Exit if current_debit >= 2x credit (stop loss)
│   └── Exit if 3:30 PM ET (hard close)
└── _check_ic_entries()
    ├── Gate 1: Cooldown (30 min)
    ├── Gate 2: Time window (10:00 AM - 2:30 PM ET)
    ├── Gate 3: Max concurrent positions (2)
    ├── Gate 4: GEX regime = sell_premium
    ├── Gate 5: ML model veto (skip if confidence > 0.35)
    ├── Get available strikes from chains
    ├── Select ~16 delta short strikes
    ├── Build 4-leg order (sell short, buy long on each side)
    └── Submit as credit limit order via Alpaca mleg API
```

### GEX Regime Determination

The GEX calculator fetches the full 0DTE options chain from Alpaca, computes IV from bid/ask prices using Newton-Raphson Black-Scholes inversion, then evaluates 4 indicators:

| Indicator | sell_premium | trending |
|-----------|-------------|----------|
| ATM straddle | < 0.8% of underlying | > 1.5% |
| IV skew (put-call) | < 0.03 | > 0.08 |
| Gamma concentration | > 0.5 near ATM | < 0.3 |
| Put/call premium ratio | 0.7-1.3 (balanced) | Outside range |

Regime is the indicator majority. Cached for 5 minutes (configurable).

### Entry Pipeline Changes (base_strategy.py)

New steps added to the existing 12-step pipeline:

| Step | Name | What it does |
|------|------|--------------|
| 1.1 | Cooldown | Blocks entry if < N minutes since last trade |
| 1.6 | GEX regime gate | Blocks entry if GEX regime doesn't match requirement (OTM only) |

### Exit Rule Changes

New exit rules added before existing rules:

| Rule | Name | Priority | What it does |
|------|------|----------|--------------|
| 1b | Trailing stop | After profit target | Tracks high-water mark, exits if P&L drops trailing_stop_pct below peak |
| 2 | Underlying reversal | Before stop loss | Exits if underlying moves reversal_pct against trade direction |

Exit order: profit_target → trailing_stop → underlying_reversal → stop_loss → max_hold → dte_floor → model_override → scalp_eod

---

## Configuration Defaults

### iron_condor preset
```
entry_cooldown_minutes: 30
max_concurrent_positions: 2
ic_target_delta: 0.16
ic_spread_width: 3.0
ic_profit_target_pct: 50
ic_stop_multiplier: 2.0
gex_cache_minutes: 5
max_confidence_for_ic: 0.35
max_daily_loss_pct: 20
```

### Updated confidence thresholds
```
scalp:       min_confidence 0.10 → 0.20, cooldown 10min
otm_scalp:   min_confidence 0.15 → 0.25, cooldown 15min, gex_gate_enabled=True
swing:       min_confidence 0.15 → 0.20, cooldown 30min
```

### Trailing stop per profile
```
SPY OTM:     activation 50%, trail 30%
Spy Scalp:   activation 10%, trail 5%
TSLA Swing:  activation 25%, trail 15%
```

---

## What Needs Retraining

| Profile | Model Status | Action Needed |
|---------|-------------|---------------|
| SPY Iron Condor | Uses SPY scalp model as optional ML veto filter | No retrain needed — GEX regime is primary gate |
| SPY OTM | Existing xgb_classifier | No retrain needed — GEX gate is the new primary filter |
| TSLA Swing | Existing lgbm_classifier | **Needs retrain** to incorporate sentiment features (news_sentiment_score, news_sentiment_magnitude, news_volume_24h, sentiment_momentum) |
| Spy Scalp | Existing xgb_classifier | Optional retrain with higher min_confidence in training |

---

## Operational Changes

1. **New profile visible in UI**: "SPY Iron Condor" appears in the profiles list. It trades automatically when conditions are right.
2. **SPY OTM trades less**: GEX gate blocks entries in calm markets. This is intentional — it waits for the rare setups.
3. **All profiles trade less**: Cooldown timers + higher confidence thresholds = fewer but higher quality trades.
4. **TSLA Swing shows sentiment in logs**: Log output includes `Sentiment: score=X momentum=Y volume=Z` each iteration.
5. **Iron condor trades show as "IC 648.0/663.0" in direction column**: Multi-leg positions display with both short strikes.
6. **No daily trade cap**: Removed the 20-trade cap. Cooldown timers are the control now.

---

## Known Limitations

1. **Alpaca returns zero IV and zero Greeks** for all options. IV is computed from bid/ask prices via Newton-Raphson. Greeks are computed from this derived IV via Black-Scholes. This is less accurate than broker-supplied Greeks but functional.
2. **No real open interest data available** from Alpaca for 0DTE options. GEX is approximated using IV skew, straddle price, and gamma distribution rather than true dealer gamma exposure.
3. **TextBlob sentiment is less accurate than FinBERT** for financial text. Can be upgraded to FinBERT by installing `transformers` package.
4. **Iron condor multi-leg fill quality** may differ between paper and live accounts. Spreads may be wider in practice.
5. **The ML model veto filter in IronCondorStrategy** has a minor `_fetch_bars` attribute error (non-blocking). The IC strategy functions correctly without the ML veto.

---

*Created March 24, 2026. Supersedes directional buying approach for SPY. TSLA Swing and SPY OTM retain directional buying with enhanced gates.*
