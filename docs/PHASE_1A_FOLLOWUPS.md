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
