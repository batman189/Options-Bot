# 16 — E2E SCENARIO TESTS (Phase 2)

## Disclosure
Phase 2 in this run is **static contract/wiring verification only**. No live backend/browser execution evidence was generated in this phase.

## Static scenario checks

| Scenario | Evidence type | Status | Note |
|---|---|---|---|
| Profile CRUD UI wiring | Source trace | likely correct but not yet fully proven | API calls and handlers map correctly in code |
| Model train/retrain wiring | Source trace | likely correct but not yet fully proven | request payload and route names align |
| Trades filters/export wiring | Source trace | likely correct but not yet fully proven | export URL path present in backend |
| Signal logs filter/export wiring | Source trace | likely correct but not yet fully proven | merge path for all profiles is implemented |
| System quick-start controls | Source trace | likely correct but not yet fully proven | trading start/stop/restart handlers mapped |
| Backtest run/results wiring | Source trace | likely correct but not yet fully proven | run + poll endpoints mapped |

## Phase boundary
Runtime scenario execution comparison against Claude E2E runtime claims is recorded in `26_CLAUDE_VS_CODEX_DIFFS.md` as not-yet-reviewed/unsupported where applicable.
