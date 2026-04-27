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

## Planned Moves (from Architecture Doc Section 7)

These entries reflect the migration plan as of 2026-04-26. They
will be updated to MOVED status as each rebuild prompt executes
its corresponding move.

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

- **Status:** PLANNED — PARTIAL move
- **Original path:** options-bot/scanner/setups.py (specific
  functions only; module stays in active use)
- **Target path:** docs/legacy/scanner/setups_retired.py
  (only the retired functions, extracted into a separate file)
- **Reason:** `score_momentum` and `score_compression_breakout`
  are kept and used by the new presets. The other three setup
  scorers (`score_mean_reversion`, `score_catalyst`,
  `score_macro_trend`) are retired. A new `score_orb`
  (Opening Range Breakout) function will be added to the
  active `setups.py`.
- **Recovery:** Functions are intact and self-contained; can
  be re-imported back into `scanner/setups.py` without
  modification. Tests for them are also moved to legacy.
- **Date moved:** —
- **Commit:** —

---

### config.py — deprecated constants

- **Status:** PLANNED — PARTIAL move
- **Original path:** options-bot/config.py (specific constants)
- **Target path:** docs/legacy/config_deprecated.py
- **Reason:** Sizer-related constants
  (`MAX_RISK_PER_TRADE_PCT`, `DAY_DRAWDOWN_HALVE_PCT`,
  `GROWTH_MODE_RISK_PCT`, `HIGH_CONVICTION_MAX_DOLLARS`,
  `TOTAL_DRAWDOWN_HALT_PCT`, `MAX_EXPOSURE_PCT`), shadow-mode
  constants (`EXECUTION_MODE`, `SHADOW_FILL_SLIPPAGE_PCT`),
  and macro nudge constants
  (`MACRO_CATALYST_NUDGE_PER_POINT`, `MACRO_CATALYST_NUDGE_CAP`)
  are no longer used.
- **Recovery:** Constants preserved verbatim in
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

| Item | Status |
|---|---|
| sizing/sizer.py | PLANNED |
| execution/shadow_simulator.py | PLANNED |
| management/trade_manager.py | PLANNED (PARTIAL) |
| risk/risk_manager.py | PLANNED |
| macro/perplexity_client.py | PLANNED (PARTIAL) |
| profiles/scalp_0dte.py | PLANNED |
| profiles/momentum.py | PLANNED |
| profiles/mean_reversion.py | PLANNED |
| profiles/catalyst.py | PLANNED |
| profiles/tsla_swing.py | PLANNED |
| scanner/setups.py (retired functions) | PLANNED (PARTIAL) |
| config.py (deprecated constants) | PLANNED (PARTIAL) |
| tests/test_pipeline_trace.py (legacy sections) | PLANNED (PARTIAL) |

**Legend:**
- **PLANNED**: Migration scheduled, not yet executed. File still
  in active use.
- **MOVED**: File migrated to legacy. Active codebase no longer
  references original location.
- **PARTIAL**: Mixed migration — some content moved, some retained.
  See entry details.
