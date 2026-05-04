# Legacy Migration Audit Log

This file tracks every file moved from the active codebase to
`docs/legacy/`. Files here are preserved (not deleted) so they can
be referenced or recovered if needed.

## How to read this log

Each entry has one of three statuses:

- **PLANNED** — Move is scheduled per the architecture doc but
  has not been executed yet. The file is still in its original
  location and is still in active use.
- **MOVED** — File has been moved to `docs/legacy/`. Original
  location no longer contains this file. Imports updated.
- **PARTIAL** — Some content from the original file moved to
  legacy; other content remains in the active codebase. See
  entry details for what's where.

## How to add a new entry

When a rebuild prompt moves a file, the prompt MUST update the
relevant entry in this log:
1. Change status from PLANNED to MOVED (or PARTIAL).
2. Set the actual move date.
3. Add the commit hash if applicable.
4. Confirm Recovery notes still apply; revise if needed.

When a NEW file (not previously planned) needs to be moved,
add a new entry following the same format as the planned ones.

---

## Status Note (post Phase 4 deep verification, 2026-05-04)

Many entries below were originally labeled "deprecated" or "no
longer used" based on the architecture-doc migration plan. Phase 4
deep verification confirmed that several of those claims are
incorrect — the relevant constants and functions are in fact
**load-bearing through Phase 1b/2**:

- `EXECUTION_MODE` (config.py:44) is THE authoritative runtime
  source for new-pipeline mode resolution at
  v2_strategy.py:3047-3051. It is canonically required by the new
  pipeline and is NOT deprecated.
- `SHADOW_FILL_SLIPPAGE_PCT`, `MAX_RISK_PER_TRADE_PCT`,
  `DAY_DRAWDOWN_HALVE_PCT`, `GROWTH_MODE_RISK_PCT`,
  `HIGH_CONVICTION_MAX_DOLLARS`, `TOTAL_DRAWDOWN_HALT_PCT`,
  `MAX_EXPOSURE_PCT`, `MACRO_CATALYST_NUDGE_PER_POINT`,
  `MACRO_CATALYST_NUDGE_CAP` are all still actively read by sizer,
  shadow simulator, scorer, and risk modules at runtime.
- `score_mean_reversion`, `score_catalyst`, `score_macro_trend` in
  scanner/setups.py are still called unconditionally by
  `Scanner.scan` for any profile whose `accepted_setup_types`
  includes those keys. The active `MeanReversionProfile`,
  `CatalystProfile`, and `SwingProfile` classes exercise these
  paths.

This file's labels were aspirational; corrected entries below
reflect verified reality. **Move-to-legacy execution is not a
Phase 1 deliverable** — it's a Phase 2 cleanup that requires
weaning production importers first. The cross-audit lesson is
captured in `PHASE_1_FOLLOWUPS.md` under SA-final.

## Planned Moves (from Architecture Doc Section 7)

These entries reflect the migration plan as of 2026-04-26. They
will be updated to MOVED status as each rebuild prompt executes
its corresponding move. **Status indicators below were corrected
in SA-final (2026-05-04) per the deep-verification note above.**

---

### sizing/sizer.py

- **Status:** PLANNED
- **Original path:** options-bot/sizing/sizer.py
- **Target path:** docs/legacy/sizing/sizer.py
- **Reason:** Replaced with simple cap check in profile config
  (user-controlled sizing). The bot no longer makes sizing
  decisions; users specify max contracts, max concurrent
  positions, and max capital per profile, and the bot respects
  those caps.
- **Recovery:** Re-import requires re-introducing
  `MAX_RISK_PER_TRADE_PCT`, `DAY_DRAWDOWN_HALVE_PCT`,
  `GROWTH_MODE_RISK_PCT`, `HIGH_CONVICTION_MAX_DOLLARS`, and
  related constants from `docs/legacy/config_deprecated.py`.
  Also requires updating profile config schema to remove the
  user-cap fields and replacing them with the original halving
  inputs.
- **Date moved:** —
- **Commit:** —

---

### execution/shadow_simulator.py

- **Status:** PLANNED
- **Original path:** options-bot/execution/shadow_simulator.py
- **Target path:** docs/legacy/execution/shadow_simulator.py
- **Reason:** Shadow mode (simulating fills against real quotes
  without submitting orders) is no longer needed. New
  architecture uses signal-only mode (Discord notifications,
  no orders) and execution mode (real orders), neither of
  which requires fill simulation.
- **Recovery:** Re-import requires restoring `EXECUTION_MODE`
  config flag handling and the `execution_mode` column filter
  logic across the codebase. The simulator itself is
  self-contained and would work as-is.
- **Date moved:** —
- **Commit:** —

---

### management/trade_manager.py (exit lifecycle complexity)

- **Status:** PLANNED — PARTIAL move
- **Original path:** options-bot/management/trade_manager.py
- **Target path:** docs/legacy/management/trade_manager.py (full
  current version preserved for reference)
- **Reason:** The current trade_manager has accumulated
  significant complexity around Alpaca's async order lifecycle
  (`pending_exit_order_id`, `exit_retry_count`, stale-lock
  timeouts, canceled/error/filled callback chains). Phase 1a
  rebuilds a simpler version. The complex version returns in
  Phase 1b in reduced form.
- **Recovery:** The full current implementation is preserved
  in legacy. Phase 1b will draw from it selectively.
- **Date moved:** —
- **Commit:** —

---

### risk/risk_manager.py (most of it)

- **Status:** PLANNED
- **Original path:** options-bot/risk/risk_manager.py
- **Target path:** docs/legacy/risk/risk_manager.py
- **Reason:** PDT logic, position count limits, portfolio
  exposure checks. Some of this becomes the simple
  "fits within user caps" check in the new profile model;
  most is replaced or eliminated.
- **Recovery:** PDT-specific logic is preserved here for
  reference if the June 4 rule change requires fallback
  behavior.
- **Date moved:** —
- **Commit:** —

---

### macro/perplexity_client.py

- **Status:** PLANNED — PARTIAL move
- **Original path:** options-bot/macro/perplexity_client.py
- **Target path:** docs/legacy/macro/perplexity_client.py
- **Reason:** Perplexity API integration is being replaced
  with a cheaper economic calendar API for scheduled-event
  detection. Catalyst/regime parts of the macro layer are
  retired entirely (multi-factor scoring nudges don't help
  on these timescales).
- **Recovery:** The full Perplexity client is preserved here.
  If the calendar API replacement proves insufficient,
  Perplexity can be reinstated, but the catalyst/regime
  scoring nudges should NOT be reinstated without revisiting
  the architecture decision.
- **Date moved:** —
- **Commit:** —

---

### profiles/scalp_0dte.py

- **Status:** PLANNED
- **Original path:** options-bot/profiles/scalp_0dte.py
- **Target path:** docs/legacy/profiles/scalp_0dte.py
- **Reason:** Replaced by the new `0dte_asymmetric` (Version B)
  preset which is patient, catalyst-gated, and asymmetric
  rather than the high-frequency scalp pattern.
- **Recovery:** Re-import requires reactivating the
  pdt_locked / pdt_day_trades_exhausted block paths in
  v2_strategy and the `_profile_specific_entry_check` for
  scalp setup_types.
- **Date moved:** —
- **Commit:** —

---

### profiles/momentum.py

- **Status:** PLANNED
- **Original path:** options-bot/profiles/momentum.py
- **Target path:** docs/legacy/profiles/momentum.py
- **Reason:** The new `swing` preset incorporates momentum-style
  entry conditions as part of its AND gate. Standalone momentum
  profile is no longer needed.
- **Recovery:** Re-import requires updating `PRESET_PROFILE_MAP`
  in profiles/__init__.py to re-include momentum.
- **Date moved:** —
- **Commit:** —

---

### profiles/mean_reversion.py

- **Status:** PLANNED
- **Original path:** options-bot/profiles/mean_reversion.py
- **Target path:** docs/legacy/profiles/mean_reversion.py
- **Reason:** Mean reversion strategy is not part of Phase 1
  presets. Could become a Phase 3+ preset if needed.
- **Recovery:** Same as momentum — update PRESET_PROFILE_MAP
  and PROFILE_ACCEPTED_SETUP_TYPES if reinstated.
- **Date moved:** —
- **Commit:** —

---

### profiles/catalyst.py

- **Status:** PLANNED
- **Original path:** options-bot/profiles/catalyst.py
- **Target path:** docs/legacy/profiles/catalyst.py
- **Reason:** Catalyst-style entries are now part of Version B's
  catalyst gate, not a standalone profile. The FinBERT-based
  sentiment threshold approach is retired.
- **Recovery:** Re-import requires reactivating FinBERT-related
  scoring factors and the catalyst-specific profile entry check.
- **Date moved:** —
- **Commit:** —

---

### profiles/tsla_swing.py

- **Status:** PLANNED
- **Original path:** options-bot/profiles/tsla_swing.py
- **Target path:** docs/legacy/profiles/tsla_swing.py
- **Reason:** Per-symbol parameter overrides in the new profile
  model replace the need for symbol-specific profile classes.
  TSLA-specific tuning becomes data, not code.
- **Recovery:** Re-import only needed if per-symbol overrides
  prove insufficient for highly volatile single names.
- **Date moved:** —
- **Commit:** —

---

### scanner/setups.py — score_mean_reversion, score_catalyst, score_macro_trend

- **Status:** PLANNED — Phase 2 prerequisite: wean importers first
- **Original path:** options-bot/scanner/setups.py (specific
  functions only; module stays in active use)
- **Target path:** docs/legacy/scanner/setups_retired.py
  (only the retired functions, extracted into a separate file)
- **Reason (corrected post-Phase-4 deep verification):** This
  entry was originally written assuming these three scorers were
  retired. Phase 4 deep verification (2026-05-04) confirmed the
  opposite — all three are still called unconditionally by
  `Scanner.scan` at scanner/scanner.py:112, 130, 137 for any
  profile whose `accepted_setup_types` includes those keys. The
  active legacy profile classes (`MeanReversionProfile`,
  `CatalystProfile`, and the legacy `SwingProfile.accepted_setup_types`)
  collectively guarantee those calls fire. Retiring them would
  require profile changes first.

  `score_momentum` and `score_compression_breakout` are kept
  and used by the new presets. `score_orb` (Opening Range
  Breakout) is correctly deferred to Phase 2 per
  ARCHITECTURE.md §6 line 314 — see PHASE_1_FOLLOWUPS.md
  "score_orb function deferred to Phase 2 (per §6)".
- **Recovery:** N/A while functions remain in active use. If
  Phase 2 weans the importers (e.g., legacy profiles retired),
  functions are intact and self-contained and can be moved
  cleanly.
- **Date moved:** —
- **Commit:** —

---

### config.py — deprecated constants

- **Status:** PLANNED — Phase 2 prerequisite: wean importers first
- **Original path:** options-bot/config.py (specific constants)
- **Target path:** docs/legacy/config_deprecated.py
- **Reason (corrected post-Phase-4 deep verification):** This
  entry was originally written assuming these constants were no
  longer used. Phase 4 deep verification (2026-05-04) confirmed
  the opposite — every constant listed below is still actively
  read by production code at runtime. None can be moved without
  first weaning the importers.

  **Sizer constants** (`MAX_RISK_PER_TRADE_PCT`,
  `DAY_DRAWDOWN_HALVE_PCT`, `GROWTH_MODE_RISK_PCT`,
  `HIGH_CONVICTION_MAX_DOLLARS`, `TOTAL_DRAWDOWN_HALT_PCT`,
  `MAX_EXPOSURE_PCT`): all defined and referenced inside
  sizing/sizer.py. `MAX_EXPOSURE_PCT` has an assertion at
  sizer.py:63 cross-checking it against config.py.

  **Mode constants:** `EXECUTION_MODE` is THE authoritative
  runtime source for new-pipeline mode resolution at
  v2_strategy.py:3047-3051 — explicitly NOT deprecated; this
  constant is canonically required by the new pipeline.
  `SHADOW_FILL_SLIPPAGE_PCT` is read by execution/shadow_simulator.

  **Macro nudge constants** (`MACRO_CATALYST_NUDGE_PER_POINT`,
  `MACRO_CATALYST_NUDGE_CAP`): read by scoring/scorer.py for
  catalyst-aware decisions.
- **Recovery:** N/A while constants remain in active use. If
  Phase 2 weans the importers, constants would be preserved in
  config_deprecated.py with comments explaining what each
  controlled.
- **Date moved:** —
- **Commit:** —

---

### Test sections in tests/test_pipeline_trace.py

- **Status:** PLANNED — PARTIAL move
- **Original path:** options-bot/tests/test_pipeline_trace.py
  (specific sections only)
- **Target path:** docs/legacy/tests/test_legacy_sections.py
- **Reason:** Test sections for sizer halvings (Section 5,
  Section 17), shadow mode (Section 15.1_shadow and the
  mode-fixture sweep), growth mode, and tests for the
  retired profile classes / setup scorers / macro catalyst
  nudging are moved to legacy alongside the code they test.
- **Recovery:** Tests are extracted as standalone runnable
  module that can be re-merged into `test_pipeline_trace.py`
  if any of the retired features are reinstated.
- **Date moved:** —
- **Commit:** —

---

## Migration Status Summary

Status indicators corrected post-Phase-4 deep verification
(2026-05-04). All entries in production tree; none physically
moved. Phase 4 deep verification confirmed 14 of 15 items are
load-bearing (active production importers) — moving them
requires weaning importers first, which is Phase 2 work.

| Item | Status |
|---|---|
| sizing/sizer.py | PLANNED — load-bearing (sizer) |
| execution/shadow_simulator.py | PLANNED — load-bearing (shadow mode) |
| management/trade_manager.py | PLANNED (PARTIAL) — load-bearing (legacy lifecycle) |
| risk/risk_manager.py | PLANNED — load-bearing (PDT logic + exposure) |
| macro/perplexity_client.py | PLANNED (PARTIAL) — load-bearing (macro worker) |
| profiles/scalp_0dte.py | PLANNED — load-bearing (active profile) |
| profiles/momentum.py | PLANNED — load-bearing (active profile) |
| profiles/mean_reversion.py | PLANNED — load-bearing (active profile) |
| profiles/catalyst.py | PLANNED — load-bearing (active profile) |
| profiles/tsla_swing.py | PLANNED — load-bearing (active profile) |
| scanner/setups.py (retired functions) | PLANNED — load-bearing (still called by Scanner.scan) |
| config.py (deprecated constants) | PLANNED — load-bearing (EXECUTION_MODE is authoritative) |
| tests/test_pipeline_trace.py (legacy sections) | PLANNED — file-only (no production importers) |

**Legend:**

- **PLANNED**: Migration scheduled, not yet executed. File still
  in active use.
- **MOVED**: File migrated to legacy. Active codebase no longer
  references original location.
- **PARTIAL**: Mixed migration — some content moved, some retained.
  See entry details.
- **load-bearing**: Production code imports from this file at
  runtime. Cannot be moved without first weaning the importers.
- **file-only**: No production importers. Could be physically
  moved without breaking anything (Phase 2 cleanup).
