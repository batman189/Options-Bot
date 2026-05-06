# Options Bot — Architecture Document

**Last updated:** 2026-04-26
**Status:** Phase 1 design, approved for implementation

---

## 1. Vision and Scope

This is a personal options trading bot designed for one user. The user creates profiles; each profile is a mini-bot for a specific strategy on user-selected symbols. The bot generates signals continuously based on each profile's locked strategy logic. Signals are delivered as Discord notifications and/or executed as orders through Alpaca.

The user controls capital limits and safety blockers. The strategy itself is locked at the preset level — users select a preset, configure how much they're willing to risk, and the bot executes the preset's strategy on their selected symbols.

**Why this bot exists.** Mechanical execution of disciplined options strategies is a real edge that humans struggle to maintain consistently. AI can be more patient (sit through long flat periods), more disciplined (mechanical execution without emotion), and faster to react (no glance-at-phone latency). The bot does not predict markets better than the consensus already priced in. It executes a defined strategy with discipline.

**Out of scope, by design.** This is not a hedge fund. It is not promised to outperform the market. It is not a tax tool or accounting tool. It is a personal automation that takes specific kinds of trades when specific conditions align, and learns from outcomes over time.

---

## 2. Layered Architecture

The bot has six layers, each with a specific responsibility. Each layer should be reasoning about its own concern only and should not reach into other layers' state.

**Profile layer.** A profile is a saved configuration: which preset (strategy template), which symbols, how much capital, what user-controlled safety blockers. Multiple profiles run independently. Each profile is functionally a mini-bot. Profiles can be enabled/disabled individually.

**Scanner layer.** Continuously evaluates symbols against the active profiles' triggering setups. Outputs setup detections: "TSLA shows a swing-bullish setup at 14:32, score X." Read-only — does not decide trades, does not place orders. Cadence varies by profile (Version B scans aggressively during catalyst windows; swing scans every 60s).

**Decision layer.** Takes scanner output and the profile's locked strategy rules, produces concrete trade decisions: "Buy 1 TSLA $250C 9DTE at limit $4.20." Applies all entry condition checks (trend, momentum, liquidity, volatility, macro, time). Decisions either fire or are rejected with a logged reason.

**Trade layer.** Takes decisions and turns them into actions. In signal-only mode, hands off to the notification layer. In execution mode, submits orders to Alpaca and tracks fills/exits. The trade layer is the only layer that knows about brokers.

**Notification layer.** Sends Discord alerts on entry decisions, fill confirmations (when in execution mode), exits, and significant position events. Configurable per profile. Discord webhook URL set at profile or global level.

**Learning layer.** Tracks outcomes for every signal generated. For each entry decision (whether traded or not), records the contract details and evaluates outcomes at fixed time windows (1h, 4h, EOD, next-day). Surfaces per-setup-type accuracy stats. Does not auto-adjust strategy parameters — the user reviews stats and decides.

---

## 3. Profile Model

Profiles are preset-based with user-controlled safety blockers.

### Available presets (Phase 1)

| Preset | Description | Hold time | Trades/month (est.) |
|---|---|---|---|
| `swing` | Multi-day directional plays on liquid mid/large caps | 1-10 days | 4-12 |
| `0dte_asymmetric` | Patient lottery-ticket strategy on SPY/QQQ requiring catalyst alignment | Minutes to hours | 4-12 |

### User-configurable (in profile UI)

- Profile name
- Preset selection
- Symbols list
- Per-symbol parameter overrides (advanced toggle, optional) — **Phase 3+; not implemented in Phase 1**
- Mode: signal_only / execution
- Max contracts per trade
- Max concurrent positions in this profile
- Max total capital deployed in this profile
- Hard contract loss backstop percentage (where applicable per preset)
- Account-level circuit breaker toggle (default OFF)
- Account-level daily loss threshold % (only relevant when toggle is ON)
- Discord webhook URL (per-profile, or fall back to global default)
- Enabled / disabled

### Locked at preset level (not user-editable in Phase 1)

- Entry conditions (signals, qualifiers, gates)
- Strike selection logic (delta target, ATM/OTM preference)
- DTE window
- Trailing stop activation thresholds and trail widths
- Thesis break logic
- DTE floor
- Pre-event close logic
- Cooldowns

Future enhancement: settings menu allows editing preset parameters. Deferred to Phase 3.

---

## 4. Strategy Specifications

### 4.1 Swing Preset

**Strategy in plain language.** Take leveraged directional bets on multi-day price moves in liquid mid/large cap stocks. Buy NTM calls or puts when a clean directional setup confirms. Hold for days to weeks while the move develops. Exit on trailing stop, thesis break, or DTE running out. Avoid holding through scheduled high-impact events.

**Default symbols:** TSLA, NVDA, AMD, AAPL, MSFT, META

**Entry conditions (AND gate — all must be true).**

*Trend qualifier (one direction must be true):*

Phase 1a consumes the existing intraday scanner setup types and follows the legacy swing profile's choices: `momentum`, `compression_breakout`, and `macro_trend`. A bullish entry requires one of these setups firing in the bullish direction with a score above the configured minimum; a bearish entry requires the same in the bearish direction. The daily-EMA trend qualifier originally specified for this preset (20EMA > 50EMA on daily, price above 20EMA, close above prior 5-day high) is deferred to Phase 2, which will add a new `daily_trend` scanner setup type and update swing to consume it. Until then, swing's "trend" is whatever the scanner's intraday signals say it is — directionally consistent but coarser-grained than the daily-EMA approach.

*Momentum qualifier:*

Phase 1a relies on the scanner's setup score as the combined directional + momentum signal: an entry requires one of `momentum`, `compression_breakout`, or `macro_trend` firing in the intended direction at score ≥ the configured minimum. The daily-bar momentum qualifier originally specified for this preset (today's price move ≥ 1.0%, today's volume ≥ 1.2× the 20-day average, ≥3 of the last 5 daily bars closed in the trend direction) is deferred to Phase 2. Adding it requires a production-tested daily-bar fetch path that does not yet exist — `UnifiedDataClient` supports the `"1Day"` timeframe but no current caller exercises it. Phase 2 will add the daily-bar fetch path along with the `daily_trend` scanner setup type.

*Liquidity qualifier (per the option contract being purchased):*
- Bid-ask spread ≤ 4% of mid price
- Open interest ≥ 500
- Daily volume on the contract ≥ 100

*Volatility regime qualifier:*
- VIX between 13 and 30
- IVR (implied volatility rank, 0-100) on the underlying < 80

**Note: IVR cold-start.** The IVR data source for non-SPY symbols requires 20 days of cached daily IV before returning a value. When IVR is unavailable for a symbol (cold cache or data outage), the IVR<80 check is skipped and the entry decision records "IVR unavailable — check skipped" in its reason. The remaining volatility gate (VIX 13-30) continues to enforce. Phase 2 will add a nightly IV recorder to keep caches warm.

*Macro/event qualifier:*
- No HIGH-impact scheduled event within 48 hours: FOMC, CPI, NFP, FOMC member testimony, earnings on the symbol

**Strike and DTE selection.**

*Strike:* Near-the-money. For calls, closest strike at or above current underlying, walk up one strike if delta < 0.40. For puts, closest strike at or below, walk down if abs(delta) < 0.40. Target delta range: 0.40 to 0.55.

*DTE:* 7-14 days. Prefer 9-12 DTE. For SPY specifically, prefer Friday expirations (better liquidity).

**Exit logic (first condition to fire wins).**

| Exit | Trigger |
|---|---|
| Trailing stop | Activates at +30% gain on contract; trails at 35% below high-water |
| Hard contract loss | Default -60% from entry; user-configurable -40% to -80% |
| Thesis break | Scanner emits no qualifying setup for the entry direction (no momentum, compression_breakout, or macro_trend setup at score ≥ minimum) AND an opposite-direction setup at score ≥ 0.3 sustained for 2+ consecutive scan cycles (reversal must confirm across cycles to avoid single-cycle noise triggering exits) |
| DTE floor | Contract DTE drops to 3 |
| Pre-event close | HIGH-impact event scheduled within 24h; close before market close on prior day |

**Cooldowns.**
- Same-symbol cooldown: 3 trading days after exit before re-entering same symbol
- Per-profile cooldown: max 1 new position per trading day per profile

**Honest limitations.**
- Won't catch reversals (trend qualifier requires established trend)
- Won't fire often (1-4 entries per week typical)
- Won't profit from IV expansion alone
- Will whipsaw in choppy markets

**Expected behavior over a quarter.**
- 15-30 entries
- Win rate roughly 35-45% (cuts losses fast, lets winners run)
- Average winner: +60% to +120% on the contract
- Average loser: -40% to -55% on the contract
- Largest possible single loss: capped at -60% by user backstop (default)
- Net P&L: positive in trending markets, possibly slightly negative in pure chop

**Phase 2 enhancements.** Add a `daily_trend` scanner setup type emitting daily 20EMA/50EMA/5-day-high signals; add daily-bar fetch path for per-symbol daily momentum metrics (today's move %, today's vol vs 20-day average, 5-day directional bar count); add nightly IV recorder to keep non-SPY IVR caches warm; update swing's trend qualifier, momentum qualifier, thesis-break exit signal, and IVR check to consume them (replaces the Phase 1a intraday-only / cold-start-skipped versions).

### 4.2 0DTE Asymmetric Preset (Version B)

**Strategy in plain language.** Patient, asymmetric, low-position-count strategy on SPY/QQQ. Buy cheap OTM 0DTE calls or puts only when multiple high-conviction conditions align. Hold with no contract-price stop loss to preserve convexity. Exit via trailing stop after meaningful gain, thesis break, or hard time stop. Most days produce no entries. Most entries lose. The point is the rare 5x-20x trade that pays for many small losses.

**Default symbols:** SPY only. User can add QQQ. Nothing else recommended.

**Entry conditions.**

*Catalyst gate (ONE must be true within next 4 hours of market time):*

Phase 1a ships with three of the four catalyst paths originally specified for this preset. The opening-range-breakout path (current 5-min volume ≥ 3× the same-window 30-day average for SPY/QQQ) is deferred to Phase 2 — it requires per-time-of-day 30-day historical volume aggregates that the current data layer does not produce, and the deferral keeps Phase 1a within deadline. The remaining three catalyst paths cover scheduled events, post-earnings reactions, and volatility shocks:

- Scheduled HIGH-impact event: FOMC announcement, CPI release, NFP release, FOMC member testimony with prepared remarks.
- Post-earnings reaction on a Magnificent-7 stock (TSLA, NVDA, AAPL, MSFT, META, AMZN, GOOG) within 60 minutes of market open after a HIGH-impact earnings event on that symbol.
- VIX spiked ≥ 15% in the last 60 minutes. Phase 1a fetches VIX history via Yahoo `^VIX` 1-minute bars (yfinance, already a dependency used by `scoring/ivr.py` for SPY VIX history).

*Technical confirmation (must align with catalyst):*
- Price breaking out of prior day's range (above prior day high for calls, below for puts)
- Move is in the direction of the broader regime (price above 20EMA on 5-min for calls, below for puts)
- VWAP supports direction (price above session VWAP for calls, below for puts)
- Last 3 1-min bars all closed in trade direction

*Time gate:*
- Entries only between 9:35 AM ET and 1:30 PM ET

**Strike and DTE selection.**

*DTE:* 0DTE only.

*Strike:* OTM 0.5% to 1.5% from current underlying. Target delta range: 0.20 to 0.35.

Why this range: far OTM (>2% out) is the lottery-ticket pattern that loses on average per the data. Closer-OTM still cheap enough to fit small position size, but close enough that the directional move can push to deep ITM.

*Liquidity qualifier:*
- Bid-ask spread ≤ 8% of mid (0DTE spreads are naturally wider)
- Open interest ≥ 1000
- Daily volume on contract ≥ 500

**Exit logic.**

| Exit | Trigger |
|---|---|
| Trailing stop | Activates at +200% gain (contract has tripled); trails at 40% below high-water |
| Thesis break | Underlying reverses ≥ 0.5% against trade direction from entry, OR VWAP flips against direction |
| Hard time stop | 3:30 PM ET — close all regardless of P&L |
| Pre-event close | If scheduled event fires while position open, exit at -5 minutes from announcement (unless trailing-stop already active) |

**Phase 1a scope.** The 0DTE asymmetric preset runs in signal-only mode through Phase 1b; no positions are opened. Phase 1a ships `evaluate_entry` and `select_contract` per this spec but stubs `evaluate_exit` with `NotImplementedError`. Exit logic per the table above lands in Phase 2 when execution wires in (after the FINRA PDT rule lifts June 4, 2026).

**No contract-price stop loss.** Intentional. A -50% stop on a $50 contract just means losing $25 instead of $50, but forfeits the chance the contract rips to $500 in the last hour. Convexity is the point. Premium is sized so full loss is acceptable.

**Cooldowns.**
- Per-profile: max 2 entries per trading day. If both lose, profile is done for the day.
- Symbol: 60 minutes between same-direction entries on same symbol.

**Honest limitations.**
- Most days produce no entries (catalyst gate doesn't fire on calm days)
- Most entries will lose (base rate is unfavorable)
- Asymmetric thesis depends on rare big winners
- Slippage and bid-ask spreads will eat returns
- Catalyst gate may be wrong (4 catalyst types may miss real opportunities or trigger on noise)
- Strategy will not be optimal at launch — needs outcome data to refine

**Expected behavior over a quarter.**
- 8-25 entries (varies enormously with market)
- Win rate roughly 20-30%
- Most losers: -100% (full premium loss)
- Average winner: +150% to +400% on the contract
- Rare home run (1-2 per quarter if lucky): +500% to +2000%
- Net P&L: highly variable, -20% to +80% of capital deployed
- Largest possible single loss: user's max-capital-per-trade setting

**Phase 2 enhancements.** Add per-time-of-day 30-day historical SPY/QQQ 5-minute volume aggregates (the data infrastructure for the ORB catalyst path) and re-enable the opening-range-breakout catalyst. Implement `evaluate_exit` per the exit-logic table above (trailing stop, thesis break, hard time stop, pre-event close) alongside Phase 2 execution wiring.

---

## 5. UI Surface

The UI is browser-based, served by the FastAPI backend. Existing UI scaffold (React + Tailwind) is preserved.

### Pages (Phase 1)

| Page | Purpose |
|---|---|
| Dashboard | At-a-glance health: profiles running, recent signals, today's outcomes, account state |
| Profiles list | All profiles with preset, symbols, status, today's signal/outcome counts |
| Profile detail | Full configuration, signal history, outcome accuracy stats, position list |
| Trades | Historical trade list (when execution mode is enabled) with filtering |
| Signals | All signal log entries, including rejected signals with block reasons |
| System | Backend status, system configuration, account state |

### Profile configuration form

Phase 1 form has approximately these fields:

- Profile name
- Preset (dropdown: swing / 0dte_asymmetric)
- Mode (radio: signal_only / execution)
- Symbols list (chip input)
- Per-symbol overrides (collapsed advanced section)
- Max contracts per trade
- Max concurrent positions
- Max total capital deployed
- Hard contract loss backstop % (only shown for swing)
- Account-level circuit breaker (toggle + threshold)
- Discord webhook URL (optional, falls back to global)
- Enabled toggle

### Future enhancements (Phase 3+)

- Tooltip help system: hover over `?` icon next to any field for inline explanation and warnings
- Preset editing: advanced users can fork a preset and modify locked parameters
- Multi-account broker configuration: select Alpaca account per profile

---

## 6. Roadmap and Deferred Items

### Phase 1a — Build (target ~10 days)

1. Move deprecated files to `docs/legacy/` with `MOVED.md` audit log
2. Implement new profile model: preset-locked strategy, user-controlled safety blockers
3. Implement swing preset against simplified scanner infrastructure
4. Implement 0DTE Version B preset
5. Implement Discord notifier and signal-only mode
6. Implement simplified outcome tracker
7. Update UI to match new profile config schema (preserve existing scaffold)
8. Both presets running in signal-only mode

### Phase 1b — Swing execution live (target ~3 days, immediately after 1a)

1. Wire up swing execution mode against Alpaca
2. Re-enable necessary trade lifecycle pieces (entry, fill confirmation, exit)
3. Validate end-to-end: signal → decision → order → fill → tracked exit
4. Swing profile starts placing real trades

Version B remains in signal-only mode through Phase 1b. Version B fires Discord alerts during this window so user can manually execute on a non-PDT-restricted broker if they choose.

### Phase 2 — Version B execution (June 4, 2026 at earliest)

PDT rule lifts on June 4. Version B can execute on Alpaca after that date.

1. Enable execution mode for Version B
2. Validate first live Version B trades supervised
3. Tune preset parameters based on observed signal-only data from Phase 1

### Phase 3 — Polish and expansion (deferred)

- Multi-Alpaca-account support
- Preset editing in UI settings
- Tooltip help system across all fields
- Additional presets: iron condor, calendar spread, butterfly, more event-driven variants
- Smoothed contract-price trailing stop (Option C — replaces wider trail)
- Expanded news options for learning: real-time event detection beyond scheduled calendar, sentiment analysis on event reactions, historical event-pattern matching

### Explicitly deferred (with reason)

| Item | Why deferred |
|---|---|
| Multi-Alpaca-account at MVP | Premature complexity before single-account is proven |
| Smoothed price trailing stop (Option C) | Wider trail (Option B) is sufficient for v1; add smoothing if real data shows whipsaw |
| Tooltip help in v1 UI | Requires UI plumbing; defer to Phase 3 polish pass |
| Preset editing | Requires validation infra to prevent broken configs; defer until real data shows which params matter |
| Catalyst nudging in scoring | Multi-factor scoring doesn't help on these timescales per the literature |
| Auto-pause / threshold adjustment learning | Replaced with simpler outcome tracking; user reviews stats, not auto-adjustment |
| Daily-EMA trend qualifier, daily-bar momentum qualifier, thesis-break signal, and nightly IV recorder for swing | Requires new scanner setup type emitting daily 20EMA/50EMA/5-day-high signals, a production-tested daily-bar fetch path supplying per-symbol daily move %, daily volume vs 20-day average, and last-5-bar directional count, and a nightly job that calls `record_daily_iv()` per default symbol. Deferred from §4.1 due to Phase 1a deadline; swing currently consumes intraday momentum + compression + macro_trend setup types as the combined directional + momentum signal, and skips the IVR check when the cache is cold. |
| ORB catalyst path and Phase 2 0DTE exit logic | Requires per-5-min-window 30-day historical SPY/QQQ volume aggregates AND Phase 2 execution-mode wiring. Phase 1a 0DTE asymmetric ships with 3 of 4 catalyst paths (scheduled events, Mag-7 earnings, VIX spike) and a stubbed `evaluate_exit`. The fourth catalyst (ORB) and the full exit logic from §4.2 land in Phase 2. |

---

## 7. Reuse Decisions

Files moved to `docs/legacy/<original_path>/` are preserved with full audit log in `docs/legacy/MOVED.md`. No deletions in Phase 1.

### Keep (mostly as-is)

- `scanner/scanner.py` and `scanner/indicators.py`
- `data/` integrations (Alpaca, ThetaData, unified client)
- `market/context.py` (regime + time-of-day)
- `backend/database.py` and most backend routes
- Most of the React UI scaffold (Layout, Dashboard, Trades, Signals, System pages)
- `main.py` cycle loop
- `config.py` (with deprecated constants moved to `docs/legacy/config_deprecated.py`)

### Replace

- `profiles/` — collapse to 2 preset classes plus base class
- `learning/learner.py` and `learning/storage.py` — replaced with simpler outcome tracker
- `scoring/scorer.py` — entry-condition evaluator, not weighted score
- `ProfileForm.tsx` — fewer fields matching new config schema
- `scanner/setups.py` — keep momentum, compression_breakout, and macro_trend (used by swing's Phase 1a accepted_setup_types per §4.1). Retire mean_reversion and catalyst (no Phase 1a consumer). The ORB scanner setup is deferred to Phase 2 along with the §4.2 ORB catalyst path (see deferred-items table).

### Move to legacy (with audit log entry)

- `sizing/sizer.py` (replaced with simple cap check)
- `execution/shadow_simulator.py` (no longer needed)
- `management/trade_manager.py` exit lifecycle complexity (simpler version returns in Phase 1b)
- Most of `risk/risk_manager.py`
- `macro/perplexity_client.py` (replaced with calendar API)
- 5 of 6 hardcoded profile classes (`scalp_0dte`, `momentum`, `mean_reversion`, `catalyst`, `tsla_swing`)
- Sizer-related, shadow-mode, growth-mode test sections

### Add (new code)

- Discord notifier module
- Outcome tracker module
- 0DTE Version B preset class
- Per-symbol parameter overrides in profile config
- Mode toggle (signal_only / execution)

### Audit log format

Each entry in `docs/legacy/MOVED.md` follows this structure:

    ## sizing/sizer.py → docs/legacy/sizing/sizer.py
    - Date: 2026-04-XX
    - Reason: Replaced with simple cap check in profile config (user-controlled sizing)
    - Recovery: Re-import requires updating profile config schema and
      re-introducing drawdown halving constants from
      docs/legacy/config_deprecated.py

The four-space indent above is intentional — it renders as a code block in Markdown without requiring fenced code, so the example doesn't conflict with this document's own fenced sections.

---

## 8. Non-Goals

The bot will NOT:

- Predict market direction better than consensus pricing on liquid instruments
- Trade instruments other than options
- Trade brokers other than Alpaca (Phase 1-2)
- Auto-allocate capital across profiles
- Provide tax reporting or accounting features
- Replace human judgment on strategy choice (user picks the preset)
- Promise specific returns
- Run during overnight or pre-market sessions
- Require manual intervention during the trading day under normal conditions

---

## 9. Known Limitations

### Strategic

- The scanner only sees what we tell it to scan. Setups outside coded patterns are invisible.
- The catalyst gate for 0DTE Version B relies on a calendar of scheduled events. Unscheduled catalysts (breaking news, geopolitical shocks) may not trigger.
- Both presets are directional. Volatility-only plays (long straddles, calendar spreads) are not currently supported.
- Position sizing is user-controlled with hard caps. The bot will not adjust size based on conviction.

### Operational

- Bot cannot trade during PDT-locked windows on $5k Alpaca accounts pre-June 4, 2026. Signal-only mode and swing execution (multi-day holds) bypass this.
- ThetaData feed outages cause graceful degradation: signals continue based on Alpaca underlying data, but contract pricing may be stale.
- Backend startup runs the full pipeline test suite (10-30 second restart latency).
- Learning data quality depends on having enough signals to evaluate. Per-setup-type accuracy stats need 30+ signals to be meaningful.

### Architectural

- Single Alpaca account in Phase 1-2.
- Two presets in Phase 1. More presets are added by writing new preset classes (not user-customizable).
- Profile cannot mix presets within itself. To run two strategies simultaneously, create two profiles.
- 0DTE Version B requires a Phase 2 catalyst calendar source. Without it, the catalyst gate doesn't fire.

---

## 10. Success Criteria

### 30 days after Phase 1a launch

- Bot has run continuously for 30 days without unrecovered crashes
- At least 1 swing profile and 1 Version B profile configured and active
- Discord notifications fired ≥ 20 times across both profiles combined
- Outcome tracker has captured ≥ 20 signal outcomes
- User has reviewed outcome data and has an opinion on signal quality
- Phase 1b complete: swing profile is executing real trades on Alpaca
- Account-level circuit breaker behavior validated if enabled

### 90 days after Phase 1a launch

- 50+ signal outcomes captured across both profiles
- Per-setup-type accuracy stats are statistically meaningful (>30 samples per setup type)
- User has decided whether Version B catalyst gate fires correctly based on data
- Phase 2 enabled (June 4 PDT rule lift): Version B executing live trades
- At least one swing trade reached the +30% trailing stop threshold (proves trailing logic in production)

### 365 days after Phase 1a launch

- Bot has run through multiple market regimes
- Either: bot has demonstrated profitable signal generation across enough trades to justify continued investment, OR user has concluded the strategy needs revision based on data
- Architecture has not required structural changes (additions are fine; foundational changes signal Phase 1 design was wrong)
- At least one Version B trade has hit the +200% trailing-stop threshold (proves the asymmetric thesis is reachable)
- User can articulate what the bot does well and what it does poorly, with data backing both claims

---

## Appendix A: Glossary

| Term | Definition |
|---|---|
| ATM | At-the-money: option strike near current underlying price |
| NTM | Near-the-money: option strike within 1-2 strikes of current underlying |
| OTM | Out-of-the-money: option strike that has no intrinsic value |
| ITM | In-the-money: option strike with intrinsic value |
| 0DTE | Zero days to expiration |
| DTE | Days to expiration |
| Delta | Option's price sensitivity to underlying price (~0 to ~1.0 for calls) |
| Theta | Option's value decay over time |
| Gamma | Rate of change of delta |
| IVR | Implied volatility rank (0-100, percentile of IV vs. its own history) |
| ORB | Opening range breakout |
| VWAP | Volume-weighted average price |
| PDT | Pattern day trader (FINRA rule limiting accounts under $25k) |
| Trailing stop | Exit that follows price favorably, locks in gain on reversal |
| Thesis break | Exit triggered when entry conditions invalidate |
| Catalyst gate | Required market condition for Version B entries |

---

## Appendix B: Document History

- 2026-04-26: Initial draft, Phase 1 design approved for implementation
