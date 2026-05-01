# Phase 1a Followups

Tracks small known issues, intentional shortcuts, and orchestrator-level
responsibilities that will need attention before Phase 1a is considered
closed. Items in `ARCHITECTURE.md`'s deferred-items table are NOT
duplicated here — that table is for Phase 2 scoping. This file is for
Phase 1a polish and known TODOs.

Each entry: a short title, the source (commit hash or "pending" if from
a chat decision not yet committed), the issue, and a target window for
resolution.

## Code-level

### HARD_LOSS_PCT_DEFAULT not pulled from ProfileConfig
- **Source:** B4b (this commit)
- **Issue:** `SwingPreset` uses `HARD_LOSS_PCT_DEFAULT=0.60` as a class
  constant. ARCHITECTURE.md §4.1 specifies the value should be
  user-configurable in the range -40% to -80%. ProfileConfig should
  expose a `hard_loss_pct` field that `SwingPreset` reads via
  `self.config`.
- **Target:** before Phase 1b execution mode lands. Catching this
  in test would require executing trades to verify the default is
  respected, so it's safe to defer until then.

### Float-arithmetic boundary on liquidity spread gate
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

### Spread-gate float tolerance: swing vs 0DTE divergence
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

### Legacy script section 28 / 29.8d time-dependent flake
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

### Phase 1b execution wire-in — replace stubbed ProfileState fields
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
- **Target:** Phase 1b execution wire-in.

### proposed_contracts hardcoded to 1 in Phase 1a wire-in
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
- **Target:** Phase 1b execution wire-in.

### max_capital_deployed default in V2Strategy._build_profile_config
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

### "Loosened test assertion" pattern in chain_adapter test
- **Source:** f15e660
- **Issue:** `test_chain_adapter.py` asserts the substring `"2 -> 1"`
  in the SPY-Friday-filter info log message. The actual log message
  is `"reduced candidates 2 -> 1"`. The test was loosened to a
  substring match rather than the full message; a future change that
  drops the count format would still pass the test. Tighten the
  assertion to match the full message, or accept the looseness.
- **Target:** test-polish sweep before Phase 1a closure.

### Unused parameter `expiration_str` in build_option_contract
- **Source:** 012bc19
- **Issue:** `chain_adapter.build_option_contract` takes
  `expiration_str` as a parameter but doesn't read it inside the
  function body. The parameter exists to make call sites readable.
  Cosmetic; either remove or document why it's kept.
- **Target:** code-polish sweep before Phase 1a closure.

### pandas-market-calendars pin has no upper bound
- **Source:** 96c4077
- **Issue:** `requirements.txt` specifies
  `pandas-market-calendars>=4.4.0` with no upper. 5.3.0 is what
  currently resolves. If 6.x ships with breaking changes (likely
  possible given the major-version-jump pattern), a future fresh
  install could break market_calendar. Decide whether to pin `<6.0`
  now or after a 6.x release surfaces.
- **Target:** as needed, or before Phase 1b launch.

### 0DTE max-entries-today undercount risk
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

## Documentation

### §4.2 (0DTE Asymmetric) data-availability investigation pending
- **Source:** chat decision before B4
- **Issue:** §4.1 was over-specified twice (trend qualifier and
  momentum qualifier required data the codebase didn't have). §4.2
  may have similar issues. A pre-0DTE investigation pass — same
  pattern as the pre-swing pass that produced the data-dependencies
  report — should run before the 0DTE preset prompts start.
- **Target:** before 0DTE preset implementation begins.

### Markdown lint warnings (MD060) in ARCHITECTURE.md
- **Source:** 549b7a4 and subsequent doc commits
- **Issue:** Lines 12 and 45 of `ARCHITECTURE.md` have pre-existing
  MD060 (table-column-style) lint warnings. Untouched across all
  Phase 1a doc commits.
- **Target:** doc-polish sweep before Phase 1a closure.

### §3 stale "per-symbol parameter overrides" reference
- **Source:** continuity prompt
- **Issue:** `ARCHITECTURE.md` §3 contains a reference to "per-symbol
  parameter overrides" that does not match the implemented
  ProfileConfig (which has no such field). Symbols are just the list
  of tickers a profile trades; nothing more.
- **Target:** doc-polish sweep before Phase 1a closure.

## Orchestrator responsibilities (wire-in)

### thesis_break_streaks cleanup on position exit
- **Source:** B4a / B4b (this commit)
- **Issue:** `SwingPreset.evaluate_exit` clears
  `state.thesis_break_streaks` entries when its own triggers fire.
  But when a position exits for reasons OUTSIDE `evaluate_exit`
  (e.g. orchestrator-level position close, broker-side cancellation,
  manual intervention), the orchestrator must remove the `trade_id`
  entry from `state.thesis_break_streaks` to prevent stale streaks
  from haunting future trades.
- **Target:** wire-in prompt at end of Phase 1a.

### outcome_tracker.resolve_pending_outcomes scheduling
- **Source:** B5 (this commit)
- **Issue:** `outcome_tracker.resolve_pending_outcomes` is implemented
  but not scheduled. The wire-in must add a FastAPI startup task that
  calls it on a periodic loop (suggested interval: 5 minutes during
  RTH, 60 minutes outside). Without scheduling, pending outcomes never
  resolve. Note: the resolver is `async def` but its body uses sync
  sqlite3 — a sync DB call inside an async function blocks the event
  loop. Acceptable for Phase 1a's low outcome volume; revisit if the
  resolver runs in a high-concurrency context or if the FastAPI startup
  task hosts other async workloads.
- **Target:** wire-in prompt at end of Phase 1a.

### Outcome recording call site
- **Source:** B5 (this commit)
- **Issue:** `outcome_tracker.record_signal` is implemented but no caller
  exists. The wire-in orchestrator must call it for each EntryDecision
  where should_enter=True (and possibly also where should_enter=False
  for completeness — ARCHITECTURE.md §2 says "for each entry decision
  whether traded or not"). Generate a stable signal_id to link the
  decision to its 4 outcome rows.
- **Target:** wire-in prompt at end of Phase 1a.

### Discord notifier wire-in
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

## Design notes (memory only — no action)

### entry_iv not on Position
- **Source:** B2 design discussion
- **Issue:** `Position` dataclass has no `entry_iv` field. Adding it
  would cost an extra `get_greeks` call at entry time. Not
  actionable for any Phase 1a exit logic. May be useful for
  diagnostics later.
- **Target:** Phase 2 if it becomes useful.

### 0DTE direction source: scanner output, not prior-day-range break
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
