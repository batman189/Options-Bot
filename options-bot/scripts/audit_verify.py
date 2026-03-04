#!/usr/bin/env python3
"""
Audit verification script — VERIFY ONLY, NO FIXES.
Checks every finding from the 2026-03-04 codebase audit.
Run from the options-bot root directory:
    cd options-bot && python scripts/audit_verify.py

Exit code: 0 if no FAIL, 1 if any FAIL.
"""

import sys
import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

results = []
fail_count = 0

def check(label: str, passed: bool, detail: str = "", warn_only: bool = False):
    global fail_count
    if passed:
        status = "  PASS"
    elif warn_only:
        status = "  WARN"
    else:
        status = "  FAIL"
        fail_count += 1
    line = f"{status}  {label}"
    if detail:
        line += f"\n         {detail}"
    print(line)
    results.append((status.strip(), label, detail))

def section(title: str):
    print(f"\n{'-' * 65}")
    print(f"  {title}")
    print(f"{'-' * 65}")

# ══════════════════════════════════════════════════════════════════
# FINDING 1 (CRITICAL): SignalLogEntry defined in schemas.py
# signals.py does: from backend.schemas import SignalLogEntry
# If missing, entire backend crashes on startup with ImportError
# ══════════════════════════════════════════════════════════════════
section("FINDING 1 -- CRITICAL: SignalLogEntry in schemas.py")

schemas_path = ROOT / "backend" / "schemas.py"
check("backend/schemas.py exists", schemas_path.exists())

if schemas_path.exists():
    schemas_src = schemas_path.read_text(encoding="utf-8")
    has_class = "class SignalLogEntry" in schemas_src
    check(
        "SignalLogEntry class defined in backend/schemas.py",
        has_class,
        "IMPORT ERROR on startup: signals.py does `from backend.schemas import SignalLogEntry`"
        if not has_class else ""
    )
    if has_class:
        # Verify it has the required fields
        required_fields = [
            "profile_id", "timestamp", "symbol", "underlying_price",
            "predicted_return", "predictor_type", "step_stopped_at",
            "stop_reason", "entered", "trade_id"
        ]
        for field in required_fields:
            check(
                f"  SignalLogEntry has field: {field}",
                field in schemas_src,
                f"Field '{field}' missing from SignalLogEntry"
            )

# ══════════════════════════════════════════════════════════════════
# FINDING 2 (HIGH): DELETE /api/profiles/{id} cleans signal_logs
# ══════════════════════════════════════════════════════════════════
section("FINDING 2 -- HIGH: Profile DELETE cleans up signal_logs")

profiles_path = ROOT / "backend" / "routes" / "profiles.py"
check("backend/routes/profiles.py exists", profiles_path.exists())

if profiles_path.exists():
    profiles_src = profiles_path.read_text(encoding="utf-8")
    # Find the delete_profile function
    has_delete_fn = "async def delete_profile" in profiles_src
    check("delete_profile function exists", has_delete_fn)

    if has_delete_fn:
        # Extract just the delete function body to scope the check
        delete_start = profiles_src.find("async def delete_profile")
        # Find next function after delete_profile
        next_fn = profiles_src.find("\nasync def ", delete_start + 1)
        if next_fn == -1:
            next_fn = profiles_src.find("\ndef ", delete_start + 1)
        delete_body = profiles_src[delete_start:next_fn] if next_fn > 0 else profiles_src[delete_start:]

        cleans_signal_logs = "signal_logs" in delete_body
        check(
            "DELETE handler removes signal_logs for deleted profile",
            cleans_signal_logs,
            "Orphaned signal_logs accumulate forever when profiles are deleted.\n"
            "         Missing: DELETE FROM signal_logs WHERE profile_id = ?"
        )

# ══════════════════════════════════════════════════════════════════
# FINDING 3 (HIGH): _full_train_job restores correct status on failure
# When a profile has an existing model_id and training fails,
# status should go back to 'ready', not 'created'
# ══════════════════════════════════════════════════════════════════
section("FINDING 3 -- HIGH: _full_train_job correct failure status")

models_path = ROOT / "backend" / "routes" / "models.py"
check("backend/routes/models.py exists", models_path.exists())

if models_path.exists():
    models_src = models_path.read_text(encoding="utf-8")
    has_fn = "_full_train_job" in models_src

    check("_full_train_job function exists", has_fn)

    if has_fn:
        fn_start = models_src.find("def _full_train_job")
        # Find next function
        next_fn = models_src.find("\ndef ", fn_start + 1)
        fn_body = models_src[fn_start:next_fn] if next_fn > 0 else models_src[fn_start:]

        # Check: does the except block hard-code "created" OR does it check model_id first?
        # Bad pattern: _set_profile_status(profile_id, "created") in except block with no model check
        # Good pattern: checks model_id and uses 'ready' if one exists

        except_idx = fn_body.find("except Exception")
        if except_idx == -1:
            check(
                "_full_train_job has except block",
                False,
                "No except Exception found in _full_train_job"
            )
        else:
            except_body = fn_body[except_idx:except_idx + 500]
            # Good: uses _get_failure_status() which checks model_id
            # Bad: blindly hard-codes "created" with no model_id check
            uses_failure_helper = "_get_failure_status" in except_body
            blindly_sets_created = (
                '_set_profile_status(profile_id, "created")' in except_body
                and "model_id" not in except_body
                and '"ready"' not in except_body
            )
            check(
                "_full_train_job failure path checks model_id before resetting status",
                uses_failure_helper or not blindly_sets_created,
                "Blindly sets status='created' on failure even when profile has an existing\n"
                "         trained model. Profile will show 'not yet trained' despite valid model.\n"
                "         Fix: check model_id and set 'ready' if it exists, 'created' if not."
            )

# ══════════════════════════════════════════════════════════════════
# FINDING 4 (MEDIUM): ev_filter.py uses correct Lumibot Greeks key
# Lumibot get_greeks() likely returns "iv" not "implied_volatility"
# ══════════════════════════════════════════════════════════════════
section("FINDING 4 -- MEDIUM: ev_filter.py Lumibot IV key name")

ev_path = ROOT / "ml" / "ev_filter.py"
check("ml/ev_filter.py exists", ev_path.exists())

if ev_path.exists():
    ev_src = ev_path.read_text(encoding="utf-8")

    uses_implied_volatility = 'greeks.get("implied_volatility"' in ev_src
    uses_iv_key = 'greeks.get("iv"' in ev_src
    uses_both = uses_implied_volatility and uses_iv_key

    check(
        'ev_filter.py uses correct Lumibot IV key "iv" (not just "implied_volatility")',
        uses_iv_key or uses_both,
        'Only "implied_volatility" found. Lumibot get_greeks() returns key "iv".\n'
        '         EVCandidate.implied_volatility will always be 0.\n'
        '         (Non-critical: IV not used in EV formula, only stored in dataclass)'
        if not (uses_iv_key or uses_both) else "",
        warn_only=True
    )

# ══════════════════════════════════════════════════════════════════
# FINDING 5 (MEDIUM): PDT window — 7 calendar days vs 5 business days
# Architecture Section 11 says "last 5 business days"
# Code uses timedelta(days=7) (7 calendar days)
# ══════════════════════════════════════════════════════════════════
section("FINDING 5 -- MEDIUM: PDT day trade window (7 calendar vs 5 business days)")

risk_path = ROOT / "risk" / "risk_manager.py"
check("risk/risk_manager.py exists", risk_path.exists())

if risk_path.exists():
    risk_src = risk_path.read_text(encoding="utf-8")

    uses_7_days = "timedelta(days=7)" in risk_src
    uses_5_days = "timedelta(days=5)" in risk_src

    check(
        "PDT cutoff uses timedelta(days=7) [ARCHITECTURE says 5 business days -- deviation]",
        uses_7_days,
        "timedelta(days=7) confirmed -- over-conservative but not dangerous.\n"
        "         Architecture Section 11 specifies '5 business days'.\n"
        "         Requires user approval to update architecture OR fix to business days.",
        warn_only=True
    )

    check(
        "PDT cutoff does NOT use timedelta(days=5) (which would be calendar days, less than spec)",
        not uses_5_days,
        "timedelta(days=5) found -- this is 5 CALENDAR days, less than the required\n"
        "         5 BUSINESS days. Could allow 4th day trade on Mondays (weekend gap)."
    )

# ══════════════════════════════════════════════════════════════════
# FINDING 6 (LOW): Base feature count must be 67 (not 68)
# After Rev 7.1, put_call_oi_ratio was removed
# ══════════════════════════════════════════════════════════════════
section("FINDING 6 -- LOW: base feature count (67 after Rev 7.1)")

# Verify the actual current feature count matches 73
# 67 original + 3 VIX (Phase C) + 3 intraday momentum = 73
try:
    from ml.feature_engineering.base_features import get_base_feature_names
    base_names = get_base_feature_names()
    check(
        f"get_base_feature_names() returns 73 (actual: {len(base_names)})",
        len(base_names) == 73,
        f"Got {len(base_names)}. Expected 73: 67 base + 3 VIX + 3 intraday momentum."
    )
    check(
        "put_call_oi_ratio NOT in base feature names (was removed in Rev 7.1)",
        "put_call_oi_ratio" not in base_names,
        "put_call_oi_ratio still present -- should have been removed in Rev 7.1"
    )
except Exception as e:
    check("get_base_feature_names() imports successfully", False, str(e))

# ══════════════════════════════════════════════════════════════════
# BONUS: Verify signals.py import of SignalLogEntry actually resolves
# ══════════════════════════════════════════════════════════════════
section("BONUS -- Import chain: signals.py -> schemas.SignalLogEntry")

signals_path = ROOT / "backend" / "routes" / "signals.py"
check("backend/routes/signals.py exists", signals_path.exists())

if signals_path.exists():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "backend.schemas", ROOT / "backend" / "schemas.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        has_attr = hasattr(mod, "SignalLogEntry")
        check(
            "SignalLogEntry is importable from backend.schemas at runtime",
            has_attr,
            "ImportError will crash backend on startup. Add SignalLogEntry to schemas.py."
        )
    except Exception as e:
        check("backend/schemas.py loads without error", False, str(e))

# ══════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════
print(f"\n{'=' * 65}")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
warned = sum(1 for s, _, _ in results if s == "WARN")
total = len(results)
print(f"  AUDIT VERIFICATION COMPLETE")
print(f"  {passed} PASS  |  {failed} FAIL  |  {warned} WARN  |  {total} total checks")

if failed == 0:
    print("  All critical and high findings verified clean.")
else:
    print(f"  {failed} finding(s) confirmed present — review FAIL lines above.")

print(f"{'=' * 65}\n")
sys.exit(0 if fail_count == 0 else 1)
