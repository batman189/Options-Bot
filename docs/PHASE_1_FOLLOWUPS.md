# Phase 1 Followups

Tracker for known issues, followups, and design decisions across
Phase 1a + 1b implementation.

**File history:** Originally created as `PHASE_1A_FOLLOWUPS.md`
during Phase 1a (commit 610a229). Renamed to `PHASE_1_FOLLOWUPS.md`
in the H2 housekeeping commit when the file's scope expanded to
include Phase 1b implementation followups (D1-D4) and the
operational-readiness arc (M1, M2). Earlier commit messages may
reference the prior name; the file content is the same lineage.

Two top-level sections:

- **Active** — issues, followups, and tracked items still awaiting
  work, deferred to Phase 2, or open for revisit.
- **Resolved** — historical record of items completed during
  Phase 1a / 1b / M-arc. Preserved for context and future audits.

## Active

### Code-level

#### HARD_LOSS_PCT_DEFAULT not pulled from ProfileConfig

- **Source:** B4b (this commit)
- **Issue:** `SwingPreset` uses `HARD_LOSS_PCT_DEFAULT=0.60` as a class
  constant. ARCHITECTURE.md §4.1 specifies the value should be
  user-configurable in the range -40% to -80%. ProfileConfig should
  expose a `hard_loss_pct` field that `SwingPreset` reads via
  `self.config`.
- **Target:** before Phase 1b execution mode lands. Catching this
  in test would require executing trades to verify the default is
  respected, so it's safe to defer until then.

#### Float-arithmetic boundary on liquidity spread gate

- **Source:** 0954124
- **Issue:** `SwingPreset.select_contract` checks
  `(ask - bid) / mid > 0.04` to reject contracts with spread above 4%
  of mid. IEEE float arithmetic can produce values trivially above
  0.04 (e.g. `0.04000000000000004`) for contracts that are exactly at
  the boundary. These get rejected. Real-world impact is negligible
  (a contract 0.0000000000004% over the limit is trivially over).
  Worth a comment in the implementation noting the float behavior, or
  a footnote in §4.1's spec.
- **Target:** doc-polish sweep before Phase 1a closure.

#### Spread-gate float tolerance: swing vs 0DTE divergence

- **Source:** C4c (this commit)
- **Issue:** ZeroDteAsymmetricPreset.select_contract applies a 1e-9
  tolerance to the `spread_pct ≤ MAX_SPREAD_PCT` comparison to
  handle IEEE-754 boundary cases (e.g. bid=0.96/ask=1.04/mid=1.00
  yields spread_pct=0.08000000000000007, which exceeds the 8%
  threshold without tolerance). The fix lands inline in the 0DTE
  implementation. SwingPreset's analogous 4% spread gate (commit
  0954124) does NOT apply this tolerance — its own followup entry
  above ("Float-arithmetic boundary on liquidity spread gate")
  documents the same issue but defers it on the basis of
  negligible real-world impact. The two presets now have
  inconsistent boundary handling. A polish sweep should align
  them: either add the same tolerance to swing, or remove it
  from 0DTE and accept the boundary-case rejections both there
  and in swing. The 0DTE choice was forced by C4c's test
  guideline (do not relax assertions) — the boundary test
  would otherwise have failed.
- **Target:** code-polish sweep before Phase 1a closure.

#### Legacy script section 28 / 29.8d time-dependent flake

- **Source:** observed during C4c (this commit)
- **Issue:** `tests/test_pipeline_trace.py` reports 14 failures
  in sections 28 (CycleLog exit-cadence machinery) and 29.8d
  (quote-overwrite logic) on some runs but not others, against
  identical code. Stash-isolation against bare f4e2b05 (the
  pre-C4c commit) reproduces the same 14 failures, so the flake
  is not C4c-related. Failure descriptions ("within-interval
  skip", "past-interval evaluate", "last_checked updated to
  ~now", "log volume across 5 cycles") indicate the cadence
  tests are sensitive to wall-clock timing — likely calling
  `time.time()` or comparing against real-clock thresholds and
  occasionally crossing an interval boundary mid-test. The
  legacy suite reported 691 passed earlier in the same session
  but began reporting 677/14 partway through. Same code, same
  machine, different result — clock-dependent test design, not
  a code regression.
- **Target:** Phase 1a closure / legacy-script tightening.
  Either fix the offending tests to mock time or accept that
  legacy script's cadence section is flaky and exclude it from
  the gating count.

#### Retire test_pipeline_trace.py startup gate

- **Source:** M1 (this commit)
- **Issue:** main.py:476-489 ran `tests/test_pipeline_trace.py`
  as a subprocess at every startup (parent process AND every
  spawned trading subprocess) and called `sys.exit(1)` on
  non-zero return. The script validated the legacy trade
  lifecycle (TradeManager.run_cycle interval gates, retry
  ladders, on_canceled/error callbacks). Three reasons for
  disabling:
    1. Sections 28 + 29.8d use wall-clock comparisons in their
       assertions (see "Legacy script section 28 / 29.8d
       time-dependent flake" entry above). The flake fires
       stochastically; standalone runs report 678/14 some runs
       and 692/0 others on identical code. With the gate active,
       a flake → subprocess exit → watchdog 3× restart → profile
       in error status mid-iteration.
    2. The new BasePreset pipeline bypasses the tested legacy
       code via D3/D4 isinstance branches in on_filled_order
       and a parallel exit loop in
       _run_new_preset_exit_iteration. For Phase 1b's
       swing-on-new-pipeline run, the gate tested code that
       does not execute.
    3. The 748-test pytest suite covers relevant new-pipeline
       behavior; legacy paths still in scope are largely
       duplicated.
  M1 (this commit) comments out the gate. The script itself
  remains in tests/ for operator convenience (can be run
  manually to verify legacy paths if needed).
- **Target:** Phase 2 cleanup. Three options:
    (a) Rewrite sections 28 + 29.8d with mocked time as proper
        pytest tests; integrate the rest of the script's
        sections into pytest as well.
    (b) Delete `tests/test_pipeline_trace.py` if pytest
        coverage is verifiably duplicating its assertions.
        Audit required first.
    (c) Keep the script as a manual smoke test (no startup
        gate); rely on pytest for CI.
  Decision should be made before any future startup-gate
  re-enable.

#### limit_price uses chain-build estimated_premium in D3 (no re-fetch)

- **Source:** D3 (this commit)
- **Issue:** _submit_new_pipeline_entry computes limit_price as
  round(contract.estimated_premium, 2) where estimated_premium
  is the bid/ask midpoint from chain_adapter at chain-build
  time. No fresh quote fetch at submission. The staleness
  window is milliseconds-to-seconds (chain build → contract
  selection → submission); for swing's multi-day hold this is
  negligible. Phase 2 should consider re-fetching bid/ask at
  submission time for tighter pricing, especially under fast-
  moving markets.
- **Target:** Phase 2 polish.

#### on_filled_order uses hardcoded DB path (test isolation)

- **Source:** D3 (this commit) — surfaced
- **Issue:** on_filled_order opens its own sqlite3 connection at
  v2:1212 against `Path(__file__).parent.parent / "db" /
  "options_bot.db"` — a hardcoded production-DB path that bypasses
  the DB_PATH monkeypatch tests use to redirect to a tmp DB. This
  makes it hard to write tests that assert on the trades INSERT
  side-effect from on_filled_order — the row goes to the production
  DB instead of the test fixture's tmp DB. D3 dropped one such
  test (test_on_filled_order_inserts_trade_for_basepreset_too) and
  relied on indirect coverage via test_on_filled_order_pdt_mark
  (which asserts on in-memory state, not DB rows). The same
  hardcoded-path pattern appears at v2:1177, v2:1794, v2:1827,
  v2:1878 — all should switch to config.DB_PATH for test
  isolation. Several legacy tests (test_pipeline_trace.py) likely
  do write to production DB during test runs already; this is a
  known cross-cutting issue.
- **Target:** Phase 1b validation runbook (D5) or Phase 2 cleanup.

#### on_filled_order BasePreset bypass — TradeManager.add_position

- **Source:** D3 (this commit)
- **Issue:** New-pipeline trades skip TradeManager.add_position
  via isinstance(profile, BasePreset) check. The trades INSERT
  still runs, so D4's exit loop can read open positions from
  the trades DB. ManagedPosition is legacy-only; new pipeline
  doesn't use it. v2_signal_logs UPDATE matches 0 rows for
  new-pipeline trades (no _log_v2_signal upstream) — quiet
  no-op. _scorer.record_trade_outcome on SELL fills will fire
  for new-pipeline trades too; whether the legacy scorer can
  handle BasePreset trades correctly is a Phase 1b validation
  question.
- **Target:** Phase 1b validation runbook (D5).

#### Confidence input divergence in D2 — setup.score vs scored.capped_score

- **Source:** D2 (this commit)
- **Issue:** D2's sizer.calculate(...) call passes
  confidence=setup.score directly. The legacy path passes
  confidence=scored.capped_score, which is setup.score after the
  Scorer class applies regime caps and macro nudges. The new
  pipeline doesn't run the Scorer for confidence — D2 keeps the
  leaf surface small. Effect: the new pipeline's sizer is
  regime-blind for confidence input. In adversarial regimes,
  this means D2's swing sizes might be larger than the legacy
  sizer would produce. Phase 2 should either wire the Scorer
  into the new pipeline or move regime-cap logic up to
  evaluate_entry in BasePreset.
- **Target:** Phase 2.

#### open_positions list-padding in _build_live_profile_state

- **Source:** D1 (this commit)
- **Issue:** _build_live_profile_state passes open_positions as
  [None] * open_count to build_profile_state, which converts via
  len(). The list contents are placeholder-only. The adapter's
  `open_positions: list` signature could be tightened to accept
  `current_open_positions: int` directly (a 2-line change to
  orchestration/adapters.py + its tests). Deferred from D1 to
  keep the leaf surface small.
- **Target:** Phase 2 polish.

#### max_capital_deployed default in V2Strategy._build_profile_config

- **Source:** C5b (this commit)
- **Issue:** V2Strategy._build_profile_config defaults
  max_capital_deployed to $5,000 if absent from the JSON config
  dict. ProfileConfig requires it explicitly, but legacy DB rows
  created before profile_config.py landed may not have the field.
  The default is appropriate for the Alpaca paper account context
  but should be enforced at the profile creation API endpoint
  (not silently defaulted at orchestrator startup). Migration
  of legacy rows to populate this field is the cleanest fix.
- **Target:** profile creation API hardening (Phase 1b or
  Phase 1a closure).

#### Outcome resolver cadence is fixed at 5 minutes

- **Source:** C5c (this commit)
- **Issue:** OUTCOME_RESOLVER_INTERVAL_SECONDS defaults to 300
  (5 min). The original spec for the resolver scheduling
  followup suggested splitting "5 min RTH / 60 min off-hours."
  C5c ships the simpler fixed cadence; off-hours runs at the
  same 5-min cadence as RTH, which is wasteful but harmless
  (the resolver short-circuits when no rows are ripe). Phase 2
  should add an is_market_open_now() helper and switch the
  cadence based on its return value.
- **Target:** Phase 2 polish.

#### Outcome resolver lifespan-test coverage scope

- **Source:** C5c (this commit)
- **Issue:** The new tests at test_outcome_resolver.py mock
  UnifiedDataClient, asyncio.run, and the resolver function to
  assert on call patterns and state-flag flips. They do not
  verify the actual end-to-end lifespan integration with a
  running FastAPI TestClient that drives the real resolver
  against a real (or in-memory) DB. The integration test
  surface is light because the codebase has no precedent for
  lifespan testing (verified in pre-C5c verification, task 7).
  A more thorough integration test should land before live
  trading begins to verify outcome rows actually transition
  through pending→evaluated under realistic conditions.
- **Target:** Phase 1b execution wire-in.

#### "Loosened test assertion" pattern in chain_adapter test

- **Source:** f15e660
- **Issue:** `test_chain_adapter.py` asserts the substring `"2 -> 1"`
  in the SPY-Friday-filter info log message. The actual log message
  is `"reduced candidates 2 -> 1"`. The test was loosened to a
  substring match rather than the full message; a future change that
  drops the count format would still pass the test. Tighten the
  assertion to match the full message, or accept the looseness.
- **Target:** test-polish sweep before Phase 1a closure.

#### Unused parameter `expiration_str` in build_option_contract

- **Source:** 012bc19
- **Issue:** `chain_adapter.build_option_contract` takes
  `expiration_str` as a parameter but doesn't read it inside the
  function body. The parameter exists to make call sites readable.
  Cosmetic; either remove or document why it's kept.
- **Target:** code-polish sweep before Phase 1a closure.

#### pandas-market-calendars pin has no upper bound

- **Source:** 96c4077
- **Issue:** `requirements.txt` specifies
  `pandas-market-calendars>=4.4.0` with no upper. 5.3.0 is what
  currently resolves. If 6.x ships with breaking changes (likely
  possible given the major-version-jump pattern), a future fresh
  install could break market_calendar. Decide whether to pin `<6.0`
  now or after a 6.x release surfaces.
- **Target:** as needed, or before Phase 1b launch.

#### 0DTE max-entries-today undercount risk

- **Source:** C4b (this commit)
- **Issue:** `ZeroDteAsymmetricPreset`'s "max 2 entries per day"
  cooldown counts entries by walking
  `state.recent_entries_by_symbol_direction.values()` and filtering
  by today's ET date. The dict only retains the most-recent timestamp
  per `(symbol, direction)` key, so the count is "distinct keys hit
  today", not raw entries. Two bullish entries on SPY at 10:00 and
  11:30 ET (after the 60-min same-direction cooldown clears) collapse
  to a single dict entry, so a third entry on a different key would
  be permitted while the §4.2 per-day cap should already be hit.
  Acceptable for Phase 1a (signal-only mode, no real entries fire);
  the orchestrator wire-in must track entries via a separate counter
  (e.g. `ProfileState.todays_entry_count`) before live trading begins.
- **Target:** wire-in prompt at end of Phase 1a, or before live
  trading lands in Phase 1b/2.

#### Swing same-symbol cooldown + 1-per-day cap missing (Phase 2 wire-in)

- **Source:** Phase 4 deep verification (this commit)
- **Issue:** §4.1 spec describes a 3-day same-symbol entry cooldown
  and a 1-per-day-per-profile cap for swing.
  `SwingPreset.evaluate_entry` ([swing_preset.py:115-222](options-bot/profiles/swing_preset.py#L115))
  currently applies 6 gates (setup type, score, direction, VIX, IVR,
  macro) but does NOT enforce these per-symbol time gates.
  `ProfileState.recent_entries_by_symbol_direction` and
  `recent_exits_by_symbol` ([base_preset.py:128-137](options-bot/profiles/base_preset.py#L128))
  carry the relevant fields, but no SwingPreset code reads them.
  `ZeroDteAsymmetricPreset` has the parallel pattern at
  [zero_dte_asymmetric.py:221-231](options-bot/profiles/zero_dte_asymmetric.py#L221)
  (60-min same-direction cooldown) — swing just doesn't have the
  equivalent.

  Two-part fix needed:
  - (a) `SwingPreset` adds `COOLDOWN_DAYS=3` and
    `MAX_ENTRIES_PER_DAY=1` constants + a
    `_check_cooldowns(symbol, state)` helper modeled on the 0DTE
    pattern (~30 lines preset code).
  - (b) Orchestrator must populate `_recent_exits_by_symbol` on
    exit fills. Currently initialized at
    [v2_strategy.py:282](options-bot/strategies/v2_strategy.py#L282)
    but never written anywhere in production code (verified —
    only init + read sites exist; zero write sites). Without (b),
    the swing 3-day gate is no-op at runtime even after preset
    code is in place.

  For Monday's signal_only run: not a blocker because signal-only
  mode emits a row to `signal_outcomes` per signal and doesn't
  repeatedly evaluate the same setup-decision. Still, duplicate
  signals on the same TSLA setup are possible if the scanner
  re-detects between iterations; follow-up data analysis must
  dedupe.
- **Target:** Phase 2 — wire in alongside any live execution work.
  ~50 lines code + 2-3 tests.

#### 0DTE P&L-conditional halt missing (Phase 2 paired with evaluate_exit)

- **Source:** Phase 4 deep verification (this commit)
- **Issue:** §4.2 spec says "If both [0DTE trades] lose, profile is
  done for the day." Code at
  [zero_dte_asymmetric.py:211-219](options-bot/profiles/zero_dte_asymmetric.py#L211)
  implements only a count-based cap (max 2 entries/day). No code
  anywhere queries `trades WHERE DATE(exit_date)=today AND
  pnl_dollars<0`. `ProfileState.today_account_pnl_pct` is an
  account-wide percent (not loser-count); it doesn't express the
  spec's loser-count gate.

  Implementing this gate requires both the trades-table query and
  a way to know today's exit P&Ls have settled — which depends on
  `evaluate_exit` being implemented for 0DTE (currently
  `NotImplementedError` in
  [zero_dte_asymmetric.py:765-782](options-bot/profiles/zero_dte_asymmetric.py#L765)).
  Premature to add now (no live exits to halt off of); 0DTE is
  signal_only through Phase 1b per the `resolve_preset_mode` 0DTE
  hardcode at [adapters.py:131-132](options-bot/orchestration/adapters.py#L131).
- **Target:** Phase 2, paired with 0DTE `evaluate_exit`
  implementation.

#### unrealized_pnl / unrealized_pnl_pct intentionally not populated for new-pipeline trades

- **Source:** Phase 4 deep verification (this commit; supersedes
  prior J.5 finding)
- **Issue:** Two related observations:
  1. `_handle_new_pipeline_exit_fill` (D4) at
     [v2_strategy.py:2745-2767](options-bot/strategies/v2_strategy.py#L2745)
     writes 9 columns on close; legacy `confirm_fill` at
     [trade_manager.py:367-371](options-bot/management/trade_manager.py#L367)
     writes 12 (extras: `setup_type` / `confidence_score` refresh +
     `unrealized_pnl=NULL` / `unrealized_pnl_pct=NULL`).
  2. Open-trade `unrealized_pnl` writes happen ONLY in
     `trade_manager.run_cycle` at
     [trade_manager.py:198-213](options-bot/management/trade_manager.py#L198),
     iterating `self._positions`. New-pipeline trades are kept OUT
     of `_positions` by D3's isinstance bypass — so
     `unrealized_pnl` is never populated for new-pipeline open
     trades anywhere.

  The dashboard query at
  [profiles.py:194](options-bot/backend/routes/profiles.py#L194)
  filters `WHERE status='open' AND unrealized_pnl IS NOT NULL` —
  new-pipeline rows correctly contribute 0 (because the filter
  excludes them, not because they show $0).

  Operational consequence: the close-time gap is moot — since the
  column is always NULL throughout the trade's lifecycle, "set to
  NULL on close" is a no-op. The Phase 4 audit's J.5 framing
  characterized this as a UI bug; that framing was incorrect (UI
  shows $0 because no row contributes, not because of stale
  values).

  For Phase 2, a ~10-line addition inside
  `_run_new_preset_exit_iteration` could populate `unrealized_pnl`
  on each per-cycle quote fetch (the data is already there).
- **Target:** Phase 2 enhancement.

### Documentation

#### §4.2 (0DTE Asymmetric) data-availability investigation pending

- **Source:** chat decision before B4
- **Issue:** §4.1 was over-specified twice (trend qualifier and
  momentum qualifier required data the codebase didn't have). §4.2
  may have similar issues. A pre-0DTE investigation pass — same
  pattern as the pre-swing pass that produced the data-dependencies
  report — should run before the 0DTE preset prompts start.
- **Target:** before 0DTE preset implementation begins.

#### Markdown lint warnings (MD060) in ARCHITECTURE.md

- **Source:** 549b7a4 and subsequent doc commits
- **Issue:** Lines 12 and 45 of `ARCHITECTURE.md` have pre-existing
  MD060 (table-column-style) lint warnings. Untouched across all
  Phase 1a doc commits.
- **Target:** doc-polish sweep before Phase 1a closure.

#### §3 stale "per-symbol parameter overrides" reference

- **Source:** continuity prompt
- **Issue:** `ARCHITECTURE.md` §3 contains a reference to "per-symbol
  parameter overrides" that does not match the implemented
  ProfileConfig (which has no such field). Symbols are just the list
  of tickers a profile trades; nothing more.
- **Target:** doc-polish sweep before Phase 1a closure.

### Orchestrator responsibilities (wire-in)

#### Discord notifier wire-in

- **Source:** B6 (this commit)
- **Issue:** `notifications/discord.send_entry_alert` is implemented
  but no caller exists. The wire-in orchestrator must call it for
  each EntryDecision(should_enter=True) emitted by the new presets,
  passing profile_config from the active profile and the signal_id
  that links the alert to its outcome rows. ARCHITECTURE.md §32 also
  specifies fill confirmations, exits, and significant position
  events as future notification types — those land in Phase 1b
  execution wiring.
- **Target:** wire-in prompt at end of Phase 1a.

#### Position reconstruction stubs ContractSelection fields

- **Source:** D4 (this commit)
- **Issue:** `_build_position_from_trade_row` reconstructs a frozen
  Position from the trades-row columns, which carry only entry-time
  artifacts (entry_price, quantity, strike, direction, expiration,
  entry_underlying_price). The Position's nested ContractSelection
  has additional fields the trades schema does not persist:
  - target_delta: stubbed to 0.0 (entry-time delta target was a
    preset class constant; SwingPreset.evaluate_exit does NOT read
    this field, verified in swing_preset.py:351-481)
  - estimated_premium: stubbed to entry_price (close enough for any
    future evaluate_exit reader; current implementations don't
    read it either)
  - dte: computed live from `(expiration - date.today()).days`,
    not the entry-time value

  If a future preset's evaluate_exit reads target_delta or
  estimated_premium, the stubs become incorrect. Long-term fix:
  persist target_delta + estimated_premium on the trades row and
  read them back in the Position reconstruction.
- **Target:** Phase 2 if any new evaluate_exit consumer reads
  these fields. Until then, the stubs are documented and safe.

#### Peak premium not persisted across subprocess restart

- **Source:** D4 (this commit)
- **Issue:** `self._peak_premium_by_trade_id` is in-memory only.
  On subprocess restart the dict is empty; `_build_position_from_trade_row`
  re-seeds peak from the entry premium and ratchets up via current_quote.
  A position that ran up to 2x entry, restarted, and then ran back to
  1.5x entry would show peak=1.5x (the higher of seed=entry and
  current=1.5x) — stale-state-aware but trailing-stop-conservative.
  The drawdown_from_peak computation in SwingPreset.evaluate_exit
  uses (peak - current) / peak, so an under-counted peak only
  delays the trailing stop firing (it does not falsely fire it).
  The bias is acceptable: under-restrict trailing exits over
  over-restrict.
  Long-term fix: persist peak_premium_per_share on trades or in a
  parallel position_state table, refresh on every cycle.
- **Target:** Phase 2 if backtest data shows peak loss across
  restarts is causing meaningful exit-quality regression.

#### date.today() in evaluate_exit / `_build_position` uses local timezone

- **Source:** D4 (this commit)
- **Issue:** `SwingPreset.evaluate_exit` calls `date.today()`
  (swing_preset.py:458) for the DTE-floor check, and
  `_build_position_from_trade_row` does the same to compute the
  reconstructed `dte`. Python's `date.today()` returns the local
  timezone's date; on a server in non-ET timezone (e.g. UTC server
  used as the bot host before midnight ET), the date may diverge
  from the trading day by ±1 day. Result: DTE counted off by one
  near midnight UTC. ZoneInfo("America/New_York") would be the
  correct anchor for trading-day arithmetic.
- **Target:** swing_preset.py polish sweep before Phase 1a closure.
  Tracked here so D4's `_build_position_from_trade_row` inherits the
  same caveat — the stub `dte` field is computed identically and
  is unused by current evaluate_exit consumers, so the divergence
  has no functional impact today.

### Design notes (memory only — no action)

#### entry_iv not on Position

- **Source:** B2 design discussion
- **Issue:** `Position` dataclass has no `entry_iv` field. Adding it
  would cost an extra `get_greeks` call at entry time. Not
  actionable for any Phase 1a exit logic. May be useful for
  diagnostics later.
- **Target:** Phase 2 if it becomes useful.

#### 0DTE direction source: scanner output, not prior-day-range break

- **Source:** dd26335 (C4b)
- **Issue:** §4.2's "Price breaking out of prior day's range (above
  prior day high for calls, below for puts)" is listed under
  "Technical confirmation (must align with catalyst)" as one of four
  bullets. The spec phrases all four as confirmations that must
  align with an externally-determined direction but does not say
  which signal determines that direction. The implementation chose
  `scanner_output.direction` as the directional source (matching
  SwingPreset's pattern); the prior-day break is consumed as a
  confirmation gate that must align with the already-known
  direction. An alternative reading would have the prior-day break
  itself determine direction (price-action-driven). Both produce
  the same accept/reject outcome on disagreement (no entry), but
  the audit reason differs and Phase 2 outcome analysis may want
  to revisit which interpretation produces better signal quality
  once outcome data accrues. The design choice is documented in
  `profiles/zero_dte_asymmetric.py` module docstring step 3 and
  in the class docstring; this entry surfaces it for review-pass
  visibility.
- **Target:** memory only — no action unless Phase 2 outcome data
  suggests one interpretation outperforms the other.

#### ProfileConfig.mode field is advisory at runtime (config.EXECUTION_MODE is authoritative)

- **Source:** Phase 4 deep verification (this commit)
- **Issue:** `ProfileConfig.mode` field at
  [profile_config.py:71-79](options-bot/profiles/profile_config.py#L71)
  is set during construction
  ([v2_strategy.py:398-415](options-bot/strategies/v2_strategy.py#L398)
  routes `EXECUTION_MODE` through `mode_map` to populate it) and
  validated by `_warn_on_execution_mode` at
  [profile_config.py:187-197](options-bot/profiles/profile_config.py#L187)
  (log side-effect only). No production code reads `.mode` and
  branches on it.

  The runtime decision for execution mode happens at
  [v2_strategy.py:3047-3051](options-bot/strategies/v2_strategy.py#L3047):
  `effective_mode = resolve_preset_mode(preset.name, config.EXECUTION_MODE)`
  where `resolve_preset_mode`
  ([adapters.py:110-133](options-bot/orchestration/adapters.py#L110))
  takes the global env-var string, NOT `ProfileConfig`. The 0DTE
  signal_only forcing happens inside `resolve_preset_mode` based on
  preset NAME, not `ProfileConfig.mode`.

  Spec implies per-profile mode toggle works; reality is that
  `ProfileConfig.mode` is shape-only. Phase 3+ would wire
  per-profile override if/when needed.

  For Monday: confirm operator sets `EXECUTION_MODE=signal_only`
  in `.env`. Per-profile `.mode` override is dead code.
- **Target:** Phase 3+ if per-profile override is wanted; OR
  document permanently as advisory if env-var-authoritative is the
  design intent.

#### score_orb function deferred to Phase 2 (per §6)

- **Source:** Phase 4 deep verification (this commit)
- **Issue:** ARCHITECTURE.md §7 references retiring legacy scorers
  and adding `score_orb` (Opening Range Breakout). §6 line 314
  lists ORB as Phase-2 work. There is no code definition of
  `score_orb` anywhere; the spec is internally consistent (§7
  mentions it as future addition; §6 defers it to Phase 2).

  Without this followup, future readers may grep for `score_orb`,
  find zero hits, and panic — repeating the Phase 4 audit's
  pattern of treating the absence as a defect when it's a
  correctly-tracked deferral.

  No action needed; this entry exists to preempt future
  confusion.
- **Target:** Phase 2 ORB catalyst implementation.

## Resolved

### Phase 1a closure (C5b, C5c)

#### Outcome recording call site

- **Source:** B5 (this commit)
- **Issue:** `outcome_tracker.record_signal` is implemented but no caller
  exists. The wire-in orchestrator must call it for each EntryDecision
  where should_enter=True (and possibly also where should_enter=False
  for completeness — ARCHITECTURE.md §2 says "for each entry decision
  whether traded or not"). Generate a stable signal_id to link the
  decision to its 4 outcome rows.
- **Target:** Resolved in C5b — `record_signal` IS wired at
  `v2_strategy.py:3141` inside the signal_only branch of
  `_run_new_preset_iteration`. Pre-Monday audit Section A flagged
  this entry as stale; updated for accuracy.

#### outcome_tracker.resolve_pending_outcomes scheduling

- **Source:** B5 (this commit)
- **Issue:** `outcome_tracker.resolve_pending_outcomes` is implemented
  but not scheduled. The wire-in must add a FastAPI startup task that
  calls it on a periodic loop (suggested interval: 5 minutes during
  RTH, 60 minutes outside). Without scheduling, pending outcomes never
  resolve. C5c (this commit) adds the periodic resolver. The resolver
  is `async def` but C5c runs it inside a daemon thread via
  asyncio.run() per tick — each tick uses a fresh ephemeral event
  loop, so the resolver's sync sqlite3 body and sync chain fetches
  do not block any FastAPI event loop. The async signature is
  preserved for any future caller that prefers asyncio.create_task
  or asyncio.to_thread, but the threading approach is the active
  pattern.
- **Target:** Resolved in C5c (this commit) — keeping the entry for
  historical context and as a pointer to the threading-vs-asyncio
  choice for future contributors.

### Phase 1b D1-D4

#### Phase 1b execution wire-in — replace stubbed ProfileState fields

- **Source:** C5b (this commit)
- **Issue:** V2Strategy._run_new_preset_iteration stubs four
  ProfileState fields with safe defaults appropriate for Phase 1a
  signal_only mode but incorrect once execution wires in:
  - current_open_positions: 0 (should be DB count of open trades
    matching execution_mode)
  - current_capital_deployed: 0.0 (should be Σ(entry_price ×
    quantity × 100) over open trades)
  - today_account_pnl_pct: 0.0 (should be (pv - day_start_value)
    / day_start_value)
  - last_exit_at: None (should aggregate from
    self._last_exit_reason or DB exits-today query)
  The signal_only path is unaffected — these values gate the
  cap_check, which approves anything up to max_capital_deployed
  against a zero baseline. Phase 1b execution wire-in must replace
  these with real computations before live trading begins.
  D1 (this commit) replaces the stubs with self._build_live_profile_state
  which queries the trades table for open-position count and
  capital-deployed sum, computes today_account_pnl_pct from
  self.get_portfolio_value() against self._day_start_value, and
  pulls last_exit_at from MAX(exit_date) over closed trades for
  the profile.
- **Target:** Resolved in D1 (this commit) — all four stubbed
  fields now pull from live subprocess and DB state.

#### _day_start_value cross-day reset added in D1

- **Source:** D1 (this commit)
- **Issue:** Subprocess _day_start_value was set lazily on first
  iteration but never reset across calendar days. A subprocess
  running across midnight ET would compute today_account_pnl_pct
  against yesterday's baseline. D1 adds a check at the top of
  on_trading_iteration: if the ET date has rolled over since
  the last tick, reset _day_start_value to 0.0 (the lazy init
  reseeds it from current pv). This affects sizer.calculate
  (D2 — wires sizing) and the new pipeline's ProfileState (D1).
  The legacy pipeline also benefits incidentally — its sizer
  call at v2:836-846 also reads self._day_start_value.
- **Target:** Resolved in D1 (this commit).

#### D1 test fixture extension — C5b stub under-specified for live ProfileState

- **Source:** D1 (this commit)
- **Issue:** D1's _build_live_profile_state introduces two new
  dependencies (get_portfolio_value, DB_PATH) that the C5b
  _build_v2_stub fixture in test_v2_strategy_new_pipeline.py was
  not configured for. C5b tests passed because the previous
  stubbed ProfileState path made no external calls. D1 extended
  _build_v2_stub minimally to provide the new dependencies; C5b
  test assertions are unchanged because the empty test DB
  produces the same zero values the literal stubs produced.
  The lesson: when a refactor changes the dependency surface of
  a previously-tested code path, existing tests need their
  fixtures extended even if their assertions stay valid. The
  scope constraint "no other test file changes" should be read
  as "no behavioral changes to existing tests' assertions" not
  "no edits at all."
- **Target:** Resolved in D1 (this commit) — kept for
  cross-leaf prompt-writing reference.

#### proposed_contracts hardcoded to 1 in Phase 1a wire-in

- **Source:** C5b (this commit)
- **Issue:** V2Strategy._run_new_preset_iteration passes
  proposed_contracts=1 to preset.can_enter for all signals. The
  legacy sizer (size_calculate at v2:693-701) handles this for
  legacy presets but is not wired into the new pipeline. For
  Phase 1a signal_only, "1 contract" is a reasonable demonstrative
  value that propagates through to send_entry_alert. Phase 1b
  execution wire-in should compute proposed_contracts from
  ProfileConfig.max_capital_deployed and the contract's
  estimated_premium (analogous to the legacy sizer's path), or
  wire size_calculate into the new pipeline.
  D2 (this commit) wires sizer.calculate(...) into the
  non-signal_only branch with the PDT _pdt_locked gate.
  signal_only path retains the 1 hardcode.
- **Target:** Resolved in D2 (this commit) for non-signal_only
  modes. signal_only mode retains proposed_contracts=1 since
  outcome rows don't need a real size.

#### test_config_signal_only EXECUTION_MODE pollution

- **Source:** D2 (this commit)
- **Issue:** test_config_signal_only.py's validation-failure
  tests (test_execution_mode_empty_raises_value_error,
  test_execution_mode_invalid_raises_value_error) call
  importlib.reload on config with an invalid env var value.
  config.py:40 assigns the invalid value to EXECUTION_MODE
  BEFORE config.py:41 raises ValueError, leaving the
  module-level constant polluted after the test. Tests
  that ran later and reached resolve_preset_mode without
  explicit env patching would receive the polluted value
  and fail. Pre-D2, the call ordering in
  _run_new_preset_iteration meant cap_check ran first and
  most rejected paths returned before resolve_preset_mode;
  the pollution was masked. D2's sizing reorder surfaced
  it. Fixed at root via an autouse fixture in
  test_config_signal_only.py that snapshots and restores
  config.EXECUTION_MODE around each test. Defensive env
  patch added to test_cap_check_rejection_blocks_emission
  in test_v2_strategy_new_pipeline.py (the one test that
  reaches resolve_preset_mode without an existing patch
  under D2's reordered flow).
- **Target:** Resolved in D2 (this commit).

#### C5b test renames + assertion updates in D3

- **Source:** D3 (this commit)
- **Issue:** Pre-D3, test_live_mode_swing_logs_warning_skips_emission
  and test_shadow_mode_swing_skips_emission asserted that
  neither submit_order nor send_entry_alert were called for
  non-signal_only modes. D3 makes both fire. Tests renamed to
  test_live_mode_swing_submits_order_and_alerts /
  test_shadow_mode_swing_submits_order_and_alerts; assertions
  updated to verify positive behavior (submit_order called,
  send_entry_alert called with mode=live/shadow, record_signal
  still NOT called). The rename matches D3's actual behavior;
  the test bodies still gate the same code path.
- **Target:** Resolved in D3 (this commit).

#### Behavior-change leaves require evolving prior-leaf test assertions

- **Source:** D3 (this commit)
- **Issue:** When a leaf changes behavior at a code path that
  earlier leaves' tests assert against, those tests need to
  evolve. D1's "no behavioral changes to existing tests'
  assertions" rule applied because D1 was strictly additive.
  D2 and D3 changed actual behavior at the live/shadow code
  paths, so the C5b and D2 tests covering those paths needed
  assertion updates (rename + replace not_called with positive
  assertions). The accidental-pass condition surfaced in D3's
  test_live_mode_runs_full_d2_path / test_shadow_mode_runs_full_d2_path —
  where missing D3 mocks caused AttributeError exceptions to
  satisfy send.assert_not_called() for the wrong reason — was
  genuine test-quality debt that D3 cleaned up. Going forward,
  D4+ leaves should expect the same pattern: each behavior
  change to a code path means earlier leaves' tests covering
  that path may need rename + positive assertions, not just
  fixture extensions.
- **Target:** Resolved in D3 (this commit) — recorded for
  cross-leaf prompt-writing reference.

#### thesis_break_streaks cleanup on position exit

- **Source:** B4a / B4b (this commit)
- **Issue:** `SwingPreset.evaluate_exit` clears
  `state.thesis_break_streaks` entries when its own triggers fire.
  But when a position exits for reasons OUTSIDE `evaluate_exit`
  (e.g. orchestrator-level position close, broker-side cancellation,
  manual intervention), the orchestrator must remove the `trade_id`
  entry from `state.thesis_break_streaks` to prevent stale streaks
  from haunting future trades.
- **Target:** Resolved in D4 (this commit). The new-pipeline exit
  fill handler (`_handle_new_pipeline_exit_fill`) pops the trade_id
  from `self._thesis_break_streaks` unconditionally on every closed
  trade. SwingPreset.evaluate_exit already pops on its own trigger
  fires; the orchestrator-side pop covers cancels-then-fills, broker
  cleanup, and the case where the exit fires for a non-thesis_break
  reason that does not touch the streaks dict.

#### Pre-D4 trades cannot use the new-pipeline exit loop

- **Source:** D4 (this commit)
- **Issue:** `_run_new_preset_exit_iteration` filters open trades
  with `WHERE entry_underlying_price IS NOT NULL AND > 0`. Trades
  inserted before the D4 retrofit landed (D3 entries that did not
  capture `chain.underlying_price`, plus any pre-D3 legacy trades)
  carry NULL in this column and are therefore skipped by the new
  exit loop. They remain managed by the legacy TradeManager path
  via `_trade_manager.run_cycle` / `_submit_exit_order`, which
  itself only knows about positions reloaded into
  `_trade_manager._positions` at startup. Result: a pre-D4 trade
  that the new pipeline opened but never had `entry_underlying_price`
  populated falls into a gap — the new loop skips it, the legacy
  loop never registered it. Mitigation: the BasePreset isinstance
  bypass in `on_filled_order` was added in D3 specifically to keep
  new-pipeline trades out of `_trade_manager._positions`, so any
  pre-D4 new-pipeline trade is unmanaged. Operators must close any
  pre-D4 new-pipeline trades manually OR backfill
  `entry_underlying_price` via DB migration before D4 ships to live.
- **Target:** Resolved by operator action (no live new-pipeline
  trades exist yet — D3 landed before this commit but production
  EXECUTION_MODE is signal_only through Phase 1b; live execution
  begins after this D4 commit). Document referenced for paper-trading
  cleanup if needed.

### M-arc (M1, M2)

#### was_day_trade uses ET timezone (M2)

- **Source:** M2 (this commit)
- **Issue:** `_handle_new_pipeline_exit_fill` computed
  `was_day_trade` from UTC date comparison
  (`entry_time.date() == now_utc.date()`), diverging from
  legacy `trade_manager.py:367` which uses ET via
  `get_et_now()`. PDT day-trade counter feeds off this column;
  UTC vs ET divergence misclassifies pre/post-market entries
  that cross UTC midnight but stay within the same ET day. For
  RTH-only swing entries the dates align, so this was a
  correctness fix not a Monday-blocker.
- **Target:** Resolved in M2 (this commit). Replaced UTC date
  comparison with ZoneInfo("America/New_York") date comparison
  on both endpoints.

#### Pre-Monday audit Section F.4/F.6 findings were incorrect (M2)

- **Source:** M2 (this commit, surfaced during pre-implementation
  verification)
- **Issue:** The pre-Monday-launch audit (run prior to M1 commit)
  flagged two SHOULD-FIX items:
  - F.4: "_build_position_from_trade_row not wrapped in
    try/except in exit loop"
  - F.6: "Quote=0 not filtered before Position construction"

  Both findings were incorrect. The existing v2_strategy.py code
  already has both protections:
  - v2:2889-2899: try/except around
    `_build_position_from_trade_row` in
    `_run_new_preset_exit_iteration`'s per-row loop, with
    continue-on-exception logging at error level
  - v2:2878-2884: quote guard `if current_quote is None or
    current_quote <= 0: continue` placed immediately after
    `get_last_price`, before `_build_position_from_trade_row`
  M2 verified both protections via direct code read at the
  pre-implementation stage and added explicit tests to lock in
  the existing behavior.
- **Lesson:** Future audits should trace each "X is missing"
  claim to specific line numbers confirming absence, rather
  than inferring from spot-checks. The pattern of pre-prompt
  verification by the implementing agent caught this audit
  error before it caused harm.
- **Target:** Resolved in M2 (this commit) — kept for
  cross-audit reference.

#### Pinned existing S3/S4 behavior in tests (M2)

- **Source:** M2 (this commit)
- **Issue:** The per-row `try/except` guard at v2:2889-2899
  (S3) and the quote `<= 0` skip at v2:2878-2884 (S4) were
  thinly tested before M2 — only `None`-quote and
  zero-underlying-price cases had explicit coverage. M2 adds
  five lock-in tests (TestS3PerRowExceptionHandling x3,
  TestS4QuoteGuardZeroAndPositive x2) so any future regression
  to those guards fails CI.
- **Target:** Resolved in M2 (this commit).

### SA-final (Phase 4 reconciliation)

#### Phase 4 audit C/D.2/J.5/score_orb findings were incorrect (post-Monday-arc verification)

- **Source:** SA-final (this commit, surfaced during Phase 4 deep
  verification)
- **Issue:** The Phase 4 scope-alignment audit (run before this
  verification) reached for synthesis without verifying claims at
  the line level. 5 of its 9 REAL DRIFT findings collapsed on
  direct code read:
  - **C/D.2 "UI ProfileForm hardcodes legacy presets" — WRONG.**
    [ProfileForm.tsx:91](options-bot/ui/src/components/ProfileForm.tsx#L91)
    has `LEGACY_PRESETS: string[] = []` explicitly empty. Strategy
    types fetched from `/api/profiles/strategy-types`. Default
    selected preset at line 111 is `'swing'`. Swing creation via
    UI works today. The legacy strings (`'0dte_scalp'`,
    `'mean_reversion'`, `'iron_condor'`) ARE in the file but as
    PRESET-DEFAULT FALLBACK ternaries, not the dropdown.
  - **C "End-to-end blocked by HARD_LOSS_PCT, signal_only forcing,
    UI gap" — WRONG on all three:**
    - [v2_strategy.py:2803](options-bot/strategies/v2_strategy.py#L2803)
      forces signal_only for 0DTE only, not swing (the comment
      describes the 0DTE NotImplementedError handling)
    - `resolve_preset_mode` at
      [adapters.py:131-132](options-bot/orchestration/adapters.py#L131)
      hardcodes 0DTE only; swing respects `EXECUTION_MODE`
    - `HARD_LOSS_PCT_DEFAULT=0.60`; ProfileConfig defaults to
      `60.0` — already aligned; non-blocker for live
    - UI gap was wrong (see above)
  - **§7 D.1 score_orb "missing as defect" — WRONG.** Spec defers
    to Phase 2 per §6 line 314; not a defect.
  - **§7 D.1 interpretation that move-to-legacy is straightforward —
    WRONG.** 14/15 items are load-bearing (e.g. `EXECUTION_MODE`
    constant is the authoritative runtime source for new-pipeline
    mode resolution at v2:3047-3051). MOVED.md is incorrect about
    which constants are deprecated; corrected in this commit.
  - **J.5 unrealized_pnl gap "UI shows stale values" — WRONG.**
    Column is never populated for new-pipeline trades anywhere;
    close-time NULL write is no-op. UI shows $0 because filter
    excludes the row, not because the column has a stale value.
- **Lesson:** This is the SECOND documented case of the
  "audit synthesis without line-level verification produces false
  positives" pattern. M2's F.4/F.6 was the first (see entry
  above in M-arc bucket). Future audits MUST trace each "X is
  missing" or "X is broken" claim to specific line numbers and
  verbatim code reads BEFORE writing synthesis or proposing fixes.
  The Phase 4 audit's intent (compare spec to code) was sound;
  the methodology (high-level walk + plausibility inference) was
  unsound. Promote this from "lesson" to "process" in any future
  audit prompt: verification-before-synthesis is non-negotiable.
- **Target:** Resolved in SA-final (this commit) — recorded as
  cross-audit reference.

### FIX-2 (resolver retry-on-tick)

#### Outcome resolver UnifiedDataClient lifecycle

- **Source:** C5c (originally tracked) / FIX-2 (resolved)
- **Issue:** Pre-FIX-2 `start_outcome_resolver_loop()` constructed a
  UnifiedDataClient at lifespan startup. If the health check failed,
  the resolver thread did not start and outcomes accumulated until
  the next restart with a healthy client. The resolver did NOT
  attempt reconnect or graceful client replacement mid-lifespan.

  This was hit every day in production: the operator's daily pattern
  is start-bot-pre-market-open, kill-bot-after-close. ThetaData IV=0
  before market open raises `DataNotReadyError` from health_check;
  the entire lifespan ran without a resolver thread. Today's run
  (2026-05-05) lost 72 outcome rows (captured in pending state, will
  resolve on the next restart only).
- **Target:** Resolved in FIX-2 (this commit). New behavior:
  - `start_outcome_resolver_loop` always spawns the thread (unless
    Python's threading subsystem itself fails — extremely rare).
    On health-check failure, the thread spawns in a "waiting" state
    with `_resolver_client = None`.
  - `_resolver_loop` checks `_resolver_client` at the top of each
    tick. If `None`, calls `_try_initialize_client` to retry. On
    success, stores the client and logs INFO state-transition; on
    failure, logs DEBUG and sleeps until the next tick.
  - When ThetaData populates ~5 min after market open, the next
    5-minute resolver tick reconnects and the resolver becomes
    operational mid-lifespan. No operator timing dance required.
  Tests added: `test_loop_attempts_reconnect_when_client_is_none`,
  `test_loop_continues_retrying_when_reconnect_fails`,
  `test_loop_transitions_from_waiting_to_active_on_reconnect`.
  Tests #3/#4 in test_outcome_resolver.py renamed to assert new
  behavior (waiting-state spawn instead of fail-and-give-up). Phase 2
  polish (richer exception taxonomy distinguishing
  `DataNotReadyError` from `DataConnectionError`, exponential
  backoff on persistent failures) deferred.
