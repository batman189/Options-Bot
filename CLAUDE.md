# Project Rules

These rules exist because of repeated, documented failures. Each rule maps to a specific failure that cost weeks of debugging. See `docs/AUDIT_FAILURES_AND_RULES.md` for the full history. Violating any rule is not acceptable.

---

## Rule 1: Full Codebase Impact Check on EVERY Change

**Failure this prevents:** Every time a new preset, field, or function was added, downstream consumers were missed — `otm_scalp` missing from 13 `preset == "scalp"` checks, `_get_strategy_class` not mapping the new preset, frontend types not updated, training year defaults not updated. These all shipped to production broken.

**The rule:**

Before making ANY code change — edit, add, delete, rename, refactor:

1. Grep the entire codebase for every function, variable, import, type, field, constant, or preset value touched by the change.
2. Post the grep results in the chat BEFORE committing. If grep output is not visible before the commit, the rule was violated.
3. Fix all dependents as part of the same change, not after.
4. Run `python -c "import ast; ast.parse(...)"` on every modified Python file.
5. Run `npx tsc --noEmit` and `npm run build` for any frontend changes.

Example — adding a new preset `otm_scalp`:

```bash
grep -rn "preset.*==.*['\"]scalp['\"]" --include="*.py"
grep -rn "preset.*scalp" --include="*.tsx" --include="*.ts"
grep -rn "PRESET_MODEL_TYPES\|PRESET_DEFAULTS\|preset_year_defaults" --include="*.py"
grep -rn "_get_strategy_class" --include="*.py"
```

Every hit must be updated in the same commit. Not the next commit. Not after the user reports the error.

---

## Rule 2: Test Every Fix Before Claiming It Works

**Failure this prevents:** Unrealized P&L fix was declared "fixed" without restarting the bot and verifying the UI showed values. Incremental trainer fix was declared "fixed" without running a retrain — it crashed immediately with a new error (continuous target passed to classifier). The SPY model was rolled back with a guessed UUID that didn't match. These all required the user to discover the failure.

**The rule:**

1. Start the backend.
2. Trigger the specific action that was broken (API call, retrain, trade signal, etc.).
3. Check the actual output — logs, database values, API response, UI rendering.
4. Post the test results in the chat showing it works.
5. If you cannot test (market closed, bot not running), say explicitly: "I have not tested this — it needs testing when [condition]." Never say "fixed" without evidence.

---

## Rule 3: Auto-Commit and Push

After every set of code edits, automatically:

1. Stage the changed files.
2. Commit with a clear message describing what changed.
3. Push to origin.

Do this after each logical unit of work — don't wait for the user to ask.

---

## Rule 4: Never Assume External Systems Work

**Failure this prevents:** `get_greeks()` returned delta = 0 for every contract. This was assumed to work because the code looked correct. A single test call would have revealed the problem. The bot could never trade — for weeks — because of this unchecked assumption.

**The rule:**

1. Never assume an external API, library function, or SDK method returns what code comments say.
2. When auditing or debugging, check actual log output or make a test call to see real return values.
3. If `get_greeks()` should return delta ~0.50 for ATM options, verify it does — don't assume.
4. If `predict_proba()` should return calibrated probabilities, verify the actual output.

---

## Rule 5: Full Code Audit Requirements

**Failure this prevents:** Five separate "full audits" and "deep dives" were requested. All five were shallow — pattern matching, signature checking, checkmark tables. None traced real data through the pipeline. The classifier math impossibility (`confidence * avg_move = 0.02%` vs `straddle_cost = 5%`) survived all five audits because no one ever plugged in real numbers.

When asked to do a "full audit," "deep dive," "full review," or any similar request, ALL of the following are required:

### 5a: Numerical Pipeline Traces (minimum 3)

Trace at least 3 real or realistic signals through the ENTIRE entry pipeline (Steps 1-12). Each trace must show:

- Input values: symbol, price, features, VIX level
- Model output: raw probability, calibrated probability, signed confidence
- Value at EVERY gate/threshold: `value [operator] threshold -> PASS/FAIL`
- EV calculation with every intermediate: move, delta, gamma, expected_gain, theta_cost, premium, EV%
- Final outcome: trade placed or blocked at which step with which values

Show the actual math line by line. Not "Step 9 PASS." The actual calculation:
`move = 409.13 * 1.87 / 100 = $7.65, delta = 0.510, expected_gain = 0.510 * 7.65 + 0.5 * 0.015 * 7.65^2 = 3.90 + 0.44 = $4.34, theta_cost = 0.286 * 7 * 1.25 = $2.50, premium = $11.20, EV = (4.34 - 2.50) / 11.20 * 100 = 16.4% > 10% -> PASS`

### 5b: External Dependency Verification

Verify what external APIs actually return with real test calls or real log output for: `get_greeks()`, `get_chains()`, `get_last_price()`, `predict_proba()`, VIX data fetch. Show the actual returned values, not what the code expects them to be.

### 5c: Gate-by-Gate Kill Count

Parse signal_logs from the database or log files. Produce a table showing how many signals reached each gate and how many were killed. If any gate kills 100% of signals, that gate is broken — regardless of what the code looks like.

```
Step 1 (Price):      500 reached, 0 killed, 500 passed
Step 5 (Prediction): 500 reached, 120 killed, 380 passed
Step 6 (Threshold):  380 reached, 200 killed, 180 passed
Step 9 (EV filter):  180 reached, 180 killed, 0 passed  <- BROKEN
```

### 5d: No Bare Checkmarks

The output "PASS" or "SAFE" or any checkmark is BANNED unless followed by the specific calculation, grep result, or test output that proves it. A bare checkmark is meaningless and dishonest.

**Wrong:** `Exit logic: SAFE -- does not use predicted_return`
**Right:** `Exit logic: SAFE -- profit_target check uses pnl_pct (line 652: if pnl_pct >= profit_target). Verified by grep: "predicted_return" appears 0 times in _check_exits(). Grep output: [actual output]`

### 5e: Logs First, Code Second

When the bot has been running, the PRIMARY source of truth is the logs and signal_logs database. Read actual output FIRST. If logs show zero trades across 500 iterations, start from the logs to find where signals die. Do not start from the code and assume it works.

### 5f: Skepticism Section Required

Every audit MUST include a section titled "What Could Still Be Wrong" listing at least 5 things the audit could not verify or areas of remaining risk. An audit that claims everything is perfect is lying.

### 5g: Minimum Output

A full audit must produce at minimum 50 pages of detailed trace output organized as:
- Section A: Numerical pipeline traces (3-5 pages each, minimum 3 traces)
- Section B: External dependency verification (1-2 pages each)
- Section C: Gate kill count analysis (2-3 pages)
- Section D: Code path traces for each entry step (15-20 pages)
- Section E: Exit logic verification (5-7 pages)
- Section F: Frontend/backend data flow trace (3-5 pages)
- Section G: What could still be wrong (1-2 pages)

If it takes under 45 minutes, corners were cut.

### 5h: Acceptance Criteria

The audit is complete ONLY when:
1. All 3+ numerical traces show a signal reaching Step 12 (order placed) OR clearly identify the specific blocker with a fix
2. All external dependency tests show actual return values (not assumptions)
3. Gate kill count table has no gate killing 100% of signals
4. Every "PASS" or "SAFE" has supporting calculation inline
5. "What Could Still Be Wrong" section exists with substantive entries
6. Document is at least 50 pages
7. Andrew or a reviewing AI confirms the traces are mathematically correct

---

## Rule 6: Pre-Commit Dry Run

**Failure this prevents:** The March 10 fix addressed the implied move gate and EV input but didn't catch the Greeks bug because the new EV input was never run through the chain scan with real data. One bug was fixed, another was left because the fix was never traced end-to-end.

Before declaring any fix complete, take a real failed signal from the logs and trace it through the fixed code with actual numbers. Show:
- "Signal #X failed at Step Y with value Z"
- "After this fix, the value would be W, which passes/fails the threshold"

---

## Rule 7: Never Suppress Warnings Without Fixing Root Cause

Hiding errors is dishonest. If something produces a warning or error, fix the cause.

---

## Rule 8: DB Profile Configs Override config.py

Changing PRESET_DEFAULTS in config.py does NOT affect existing profiles. You MUST update the database directly when changing settings for existing profiles. Always update both.

---

## Rule 9: Restart Backend After Code Changes

Python processes keep old code in memory. After any code change, the bot must be restarted. Always remind the user to restart. Training jobs use the code loaded at backend startup.
