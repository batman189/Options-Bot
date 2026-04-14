# CLAUDE ZERO-OMISSION TERMINATION-GRADE AUDIT DIRECTIVE

## Purpose

You are performing a termination-grade, evidence-driven, zero-omission audit of this entire codebase and its live runtime surface.

This is not a summary review, static skim, lint pass, type-check pass, architectural opinion, or best-effort inspection.

You are required to prove behavior, not describe intent.

You are required to individually inventory, wire-map, test, document, explain, and validate **every single item that exists** in the codebase or runtime surface.

There is no category of item that may be skipped because it is small, trivial, previously reviewed, low risk, obvious, repetitive, implied, or already covered by a parent system.

If any item is omitted, collapsed into a summary, assumed, deferred, or left without individual evidence, the audit is wholly invalid.

---

## Mission-Critical Standard

Treat this audit as a final credibility test.

Your job is to produce a complete, adversarial, proof-backed audit package that makes it impossible to falsely claim that the bot was fully reviewed when it was not.

You are forbidden from substituting confidence for evidence.

You are forbidden from claiming completion based on partial coverage.

You are forbidden from presenting formatting theater as proof.

---

## Core Audit Principle

If it exists, it must be:

1. discovered  
2. listed  
3. wire-mapped  
4. tested  
5. documented  
6. explained  
7. validated with evidence  

If any one of those seven actions is missing for any item, the entire audit fails.

---

## Zero-Omission Enforcement Rule

This audit has a zero-omission standard.

There is no category of:

- trivial
- small
- already checked
- low risk
- not worth documenting
- implicitly covered
- non-critical
- previously audited
- too repetitive
- too minor to test
- too obvious to map
- too time-consuming
- out of scope
- assumed
- deferred

If it exists anywhere in the repository, startup path, runtime path, UI surface, API surface, config surface, storage surface, model surface, log surface, or external dependency surface, it must be individually recorded and validated.

Anything not explicitly audited is automatically a critical failure of the audit.

There is no partial pass.
There is no “complete except for a few items.”
There is no “unknown but acceptable.”
There is no “close enough.”
There is no “best effort complete.”

If you omit, collapse, skip, or fail to individually record any item that exists in the codebase or runtime surface, the audit is not partially wrong; it is wholly invalid.

---

## Non-Negotiable Rules

1. Do not claim anything is verified unless you provide hard evidence.
2. Do not use bare phrases like “looks correct,” “appears fine,” “seems safe,” “passes review,” “works as expected,” or green-check summaries without inline proof.
3. Do not stop at the first bug. Continue until the full audit package is complete.
4. Do not delegate core review work to sub-agents and then summarize their output as if you personally verified it.
5. Do not treat “code compiles,” “page loads,” “endpoint exists,” or “function exists” as proof of correctness.
6. If you cannot fully validate an item, you must still inventory it, wire-map it, test as far as possible, document the blocker, capture all available evidence, and mark the overall audit as failed.
7. Unsupported confidence is forbidden.
8. Runtime evidence outranks assumptions.
9. Logs outrank architecture narratives.
10. Numerical behavior must be shown numerically.
11. UI behavior must be shown through interaction evidence.
12. Endpoint behavior must be shown through executed request/response evidence.
13. Model usage must be shown through runtime load -> inference -> downstream consumption evidence.
14. Every important claim must include:
   - evidence ID
   - file path(s)
   - exact line number(s), where relevant
   - command or test executed
   - observed output
   - expected behavior
   - verdict
15. You are forbidden from producing a “final audit complete” statement until every required deliverable exists and every item has been individually recorded.
16. Any PASS verdict without evidence is invalid.
17. Any summary that replaces individual item coverage is invalid.
18. Any omission anywhere causes total audit failure.

---

## Audit Scope

Audit every single aspect of the project.

This includes, without exception:

- every file
- every directory-relevant file relationship
- every import
- every export
- every symbol
- every constant
- every enum
- every config value that affects behavior
- every function
- every method
- every class
- every constructor
- every callback
- every event handler
- every hook
- every utility
- every helper
- every parser
- every serializer
- every validator
- every middleware
- every route
- every route handler
- every UI component
- every visible UI element
- every button
- every input
- every dropdown
- every slider
- every checkbox
- every radio button
- every tab
- every modal
- every table
- every badge
- every label
- every text string the user can see
- every state update path
- every API call
- every request builder
- every response handler
- every DB read/write path
- every storage path
- every filesystem load/save path
- every model training step
- every dataset-building step
- every feature-engineering step
- every target-building step
- every model save path
- every model load path
- every inference path
- every gating/filtering rule
- every threshold
- every risk-control path
- every order-submission path
- every error-handling path
- every retry path
- every scheduler/background/live-loop path
- every startup path
- every shutdown path
- every logging path
- every external dependency call
- every returned field used from external systems
- every conditional branch that can alter behavior
- every environment variable that can alter behavior
- every hard-coded assumption that can alter behavior

Nothing is exempt.

---

## Absolute Wire-Map Requirement

Every executable element, referential element, configurable element, and user-visible element must be wire-mapped.

Not “every non-trivial function.”
Everything.

For every item, record:

- unique item ID
- exact name
- exact type
- exact file path
- exact line number span
- definition location
- import source, if applicable
- export target, if applicable
- called by
- referenced by
- downstream calls/references
- input contract
- output contract
- side effects
- state changes
- storage changes
- UI changes
- network/API effects
- expected purpose
- actual observed behavior
- evidence reference(s)
- verdict

No item may be grouped into “misc helpers,” “small utilities,” “shared components,” or similar buckets.

No item may be omitted because it appears simple.

No item may be declared implicitly covered by another item.

---

## No-Skip Rule

You are not allowed to decide that an item will not be audited.

Do not create categories such as:

- not audited
- skipped
- deferred
- out of scope
- assumed
- previously reviewed
- low priority
- too trivial
- too time-consuming
- not necessary
- already covered
- covered indirectly

If a single discovered item is not fully audited and individually recorded, the audit is invalid and must be marked:

**TOTAL FAILURE**

If you encounter a blocker preventing validation of an item, you must still:

1. list the item
2. fully wire-map the item
3. document the blocker
4. capture all available static and runtime evidence
5. continue auditing all remaining items
6. mark the overall audit as failed because full validation was not completed

A blocker does not excuse omission.
A blocker proves the audit is incomplete.
Incomplete means total failure.

Do not explain why something was not audited.
If anything is not audited, the audit fails in full.

---

## Evidence Standard

Every material claim must be backed by one or more of the following:

- exact code citation with line numbers
- command output
- runtime log excerpt
- HTTP request/response capture
- screenshot
- browser/network evidence
- DB query result
- filesystem artifact inspection
- serialized model artifact inspection
- numerical derivation
- stack trace
- test output
- direct UI interaction evidence

Acceptable proof must connect the claim to real observed behavior.

Descriptions without proof are invalid.

---

## Verdict Rules

Allowed per-item verdicts:

- PASS
- FAIL

There is no acceptable “not audited” state.
There is no acceptable “covered elsewhere” state.

If proof is incomplete, contradictory, blocked, or missing, the item must be treated as a FAIL for audit-completeness purposes.

Any PASS verdict without direct evidence is automatically converted to FAIL.

Any item missing from inventory is automatically converted to FAIL.

Any summary that prevents individual item accountability is automatically converted to FAIL.

---

## Banned Output Patterns

You may not write:

- “all looks good”
- “no obvious issues”
- “appears correct”
- “seems fine”
- “likely works”
- “probably fine”
- “end-to-end reviewed” without a full trace
- “model is used” without runtime proof
- “button works” without interaction proof
- “endpoint works” without executed request/response proof
- “math is correct” without shown arithmetic
- “representative examples”
- “high-priority paths only”
- “critical paths only”
- “non-trivial functions”
- “main functions”
- “key files”
- “etc.”
- “miscellaneous helpers”
- “covered by previous section”

You may not replace exhaustive coverage with selective coverage.

You may not replace evidence with narrative.

You may not replace direct observation with inference unless explicitly labeling that inference as insufficient and failing the audit accordingly.

---

## Anti-Evasion Rules

The following are forbidden and count as audit failure:

- summarizing groups of functions instead of listing each one
- summarizing groups of controls instead of listing each one
- claiming a file is covered because the folder was reviewed
- claiming a control is covered because the page was tested
- claiming a function is covered because a parent module was read
- claiming an endpoint is covered because a related endpoint was tested
- claiming a branch is covered because the happy path ran
- claiming math is covered without showing arithmetic
- claiming a model is used without tracing load -> inference -> downstream consumer
- claiming a UI action works without showing click/input -> handler -> API -> response -> UI update
- using “etc.” where full inventory is required
- using “representative examples” instead of exhaustive coverage
- using “most,” “main,” “key,” or “critical” to narrow scope
- omitting repeated-looking items
- collapsing duplicate-looking UI controls into one record
- collapsing similar functions into one record
- collapsing repeated endpoints into one family record
- using previous audit work as a substitute for current proof

This audit is exhaustive or it is a failure.

---

## Required Execution Order

You must follow this order:

1. Build a full repository manifest of every file.
2. Enumerate every symbol in every file.
3. Enumerate every import/export relationship.
4. Enumerate every endpoint.
5. Enumerate every UI component and every visible/interactable control.
6. Enumerate every config/env/storage/model/runtime artifact.
7. Read logs and runtime evidence before drawing conclusions.
8. Build complete wire maps for every item.
9. Execute endpoint tests.
10. Execute UI interaction validations.
11. Execute startup/runtime/training/inference validations.
12. Execute persistence/load/save validations.
13. Execute numerical pipeline traces.
14. Execute end-to-end scenario traces.
15. Populate the bug ledger.
16. Populate the failure ledger for any unvalidated item.
17. Perform a self-critique for unsupported claims.
18. Only then produce the executive summary.

Do not invert this order by writing conclusions first.

---

## Mandatory Output Package

Create an audit folder in the repository root:

```text
/AUDIT_PACKAGE/
  00_EXEC_SUMMARY.md
  01_REPO_MANIFEST.csv
  02_SYMBOL_INVENTORY.csv
  03_FILE_BY_FILE_AUDIT.md
  04_FULL_WIREMAP.md
  05_IMPORT_EXPORT_MATRIX.csv
  06_ENDPOINT_MATRIX.csv
  07_UI_CONTROL_MATRIX.csv
  08_UI_VISIBLE_TEXT_INVENTORY.csv
  09_DATAFLOW_TRACES.md
  10_MODEL_TRAINING_AUDIT.md
  11_MODEL_INFERENCE_AUDIT.md
  12_EXTERNAL_DEPENDENCY_VALIDATION.md
  13_LOG_FIRST_RUNTIME_ANALYSIS.md
  14_GATE_KILL_COUNTS.md
  15_NUMERICAL_PIPELINE_TRACES.md
  16_E2E_SCENARIO_TESTS.md
  17_FRONTEND_BACKEND_BINDINGS.md
  18_DB_STORAGE_AND_RETRIEVAL_AUDIT.md
  19_CONFIG_ENV_AUDIT.md
  20_STARTUP_SHUTDOWN_LIVE_LOOP_AUDIT.md
  21_BUG_LEDGER.csv
  22_FAILURE_LEDGER.csv
  23_REMAINING_RISKS_AND_UNKNOWNS.md
  24_FINAL_ACCEPTANCE_CHECKLIST.md
  /raw_evidence/
  /screenshots/
  /curl/
  /logs/
  /json/
  /network/
  /db/
  /artifacts/
  /diffs/