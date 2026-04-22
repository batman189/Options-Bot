# Bot Problems — Status Tracker

**Last updated:** 2026-04-17

## Issues FIXED since April 10

| Issue | Fix Date | What was done |
|-------|----------|---------------|
| Only buys puts | Apr 14 | Catalyst direction was correct (sentiment-driven). Added momentum/macro_trend setups that buy calls on bullish signals. |
| Market orders | Apr 14 | All orders now use limit prices (mid for entry, current price for exit). time_in_force="day". |
| PDT not working | Apr 14 | 3-level PDT gate: checks daytrading_buying_power, reserves last day trade for high confidence, catches Alpaca rejections. |
| No entry cooldown | Apr 14 | 30min cooldown in CHOPPY, 5min in TRENDING. Per-profile, recorded on submission. |
| No position cap | Apr 14 | Max 3 concurrent open positions (configurable). |
| Scanner finds nothing | Apr 14 | Momentum thresholds lowered (5/8 bars, 0.20% move). Mean reversion RSI 65/35. Added macro_trend (15-min bars). |
| Unrealized P&L wrong | Apr 10 | Uses option price, not stock price. |
| Trade records not written | Apr 7 | INSERT on fill confirmation only. Prevents phantom trades. |
| Signal logs empty | Apr 16 | Scanner rejections now logged with factor values and block reasons. |
| Crashes/freezes | Apr 8 | Registry key disables QuickEdit. ThetaData retry loop. Error state reset button. |
| Learning layer broken | Apr 14 | Fixed query (removed broken profiles join). Added TOD-aware bucketing. |
| Profit lock kills winners | Apr 17 | Profit lock (Priority 4) skipped when trailing stop is active. |
| Mean reversion accepts wrong setups | Apr 17 | All profiles now filter by setup_type in _profile_specific_entry_check. |
| Exit score lookup wrong | Apr 17 | Uses pos.setup_type instead of pos.profile.name. |
| SPY always CHOPPY | Apr 17 | TRENDING threshold lowered from 0.4% to 0.25% (30-min move). |

## Issues REMAINING

1. **No multi-timeframe confirmation.** The 1-minute scanner can't see daily trends. The macro_trend (15-min) helps but doesn't capture gap-and-run days where the move happens at open.

2. **Sentiment is weak.** FinBERT processes cached headlines, not real-time. TSLA often returns 0.000 sentiment when major news is happening. Sentiment is suppression-only (5% weight) until validated.

3. **No compounding.** The bot doesn't scale position size after wins within a session. The person who turned $700 into $70K compounded every win into the next trade. Our bot uses fixed % of account value per trade.

4. **Single-broker limitation.** Alpaca doesn't offer SPX/NDX index options. SPX options are cash-settled and PDT-exempt on some brokers — a major advantage our bot can't access.

5. **Reconciliation gap.** When Alpaca auto-closes positions with no order record (expiration, margin call), the cleanup marks them as order_never_filled at $0 P&L. The actual exit may have been at a non-zero value.

6. **Aggregator min_confidence is coarse.** Prompt 15 (2026-04-21) wired aggregator profiles (scalp_0dte / swing / tsla_swing) into the learning layer via their `accepted_setup_types`. `_apply_learning_state` currently uses Option 1 — `profile.min_confidence = max(state.min_confidence across accepted_setup_types)`. One cold setup_type drags the whole profile's entry threshold up, pushing it off its warmer setup_types too. Two follow-up options documented for when per-setup data exists:
   - **Option 2**: Move min_confidence enforcement into the scorer, keyed by `score_result.setup_type`. `BaseProfile.min_confidence` becomes a default; the scorer looks up the per-setup override at `score()` time.
   - **Option 3**: Aggregator profiles hold a `dict[setup_type -> min_confidence]`; `should_enter` selects based on `score_result.setup_type`. Requires touching `BaseProfile.should_enter`.
   Revisit when an aggregator has both a hot and a cold setup_type in prod — Option 1 is a holding pattern, not a permanent design.

7. **EV gate disabled — needs a real predicted-move forecast.** Prompt 17 Commit B (2026-04-21) disabled `apply_ev_validation` on the non-0DTE entry path. The prior input — `setup.score * 2` from [v2_strategy.py](../options-bot/strategies/v2_strategy.py) — was a dimensionless scanner fitness score being passed into [`selection/ev.py`](../options-bot/selection/ev.py), whose formula treats `predicted_move_pct` as a forward-move percentage. For a typical signal (setup.score=0.95), the EV gate was evaluating a fabricated 1.9% move — ~5x the actual observed move — so every non-0DTE trade clearing the EV filter was clearing it on fiction. Option A (chosen for this commit): pass `None`, skip EV, keep every other filter. Reinstatement options documented for when a real forecast exists:
   - **Option C.a — ATR-derived expected move.** Take the n-period Average True Range over the holding period's bar granularity, convert to %, pass as `predicted_move_pct`. Calibration-free but assumes realized volatility carries forward.
   - **Option C.b — IV-derived expected move.** For each candidate contract, compute expected move from the option's implied volatility, adjusted to the holding period (one-day IV ≈ annualized_IV / sqrt(252)). IV is forward-looking but priced-in; no edge over the market.
   - **Option C.c — ML forecast.** Separate predictor (not the scanner's fitness score) trained against realized moves. Requires labeled training data and a validation step against the current signal_log history.
   The compute_ev function at [selection/ev.py](../options-bot/selection/ev.py) is preserved so any of Options C.a/b/c can reinstate it by supplying a real `predicted_move_pct`. `SelectedContract.ev_pct` is now `Optional[float]` — `None` means "gate disabled"; `float` means "gate ran and this is the computed EV."
