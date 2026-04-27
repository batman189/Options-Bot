#!/usr/bin/env python3
"""
Pre-flight startup check for options-bot.
Verifies all prerequisites before starting trading.

Run before starting the bot:
    python scripts/startup_check.py

Checks:
    1. Python version (3.10+)
    2. Required packages installed
    3. .env file exists and has required keys
    4. Database directory writable
    5. Models directory exists
    6. Disk space (>500 MB free)
    7. Alpaca API connection
    8. Theta Terminal connection (warn-only if not running)
    9. UI build exists

Exit code: 0 if all critical checks pass, 1 if any FAIL.
"""

import importlib
import os
import shutil
import sys
from pathlib import Path

# ── Setup ──────────────────────────────────────────────────────
# Ensure UTF-8 output on Windows (cp1252 can't handle ✓/✗/⚠/─)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PASS = "  ✓ PASS"
FAIL = "  ✗ FAIL"
WARN = "  ⚠ WARN"

results = []
fail_count = 0


def check(label: str, passed: bool, detail: str = "", warn_only: bool = False):
    global fail_count
    if passed:
        status = PASS
    elif warn_only:
        status = WARN
    else:
        status = FAIL
        fail_count += 1
    line = f"{status}  {label}"
    if detail:
        line += f"\n           {detail}"
    print(line)
    results.append((status, label, detail))


def section(title: str):
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


# ═══════════════════════════════════════════════════════════════
# Check 1: Python version
# ═══════════════════════════════════════════════════════════════
section("Python Environment")

v = sys.version_info
check(
    f"Python {v.major}.{v.minor}.{v.micro}",
    v.major == 3 and v.minor >= 10,
    f"Requires Python 3.10+. Current: {v.major}.{v.minor}.{v.micro}",
)


# ═══════════════════════════════════════════════════════════════
# Check 2: Required packages
# ═══════════════════════════════════════════════════════════════
section("Dependencies")

required_packages = [
    "lumibot", "alpaca", "xgboost", "sklearn", "pandas", "numpy",
    "scipy", "joblib", "ta", "fastapi", "uvicorn", "pydantic",
    "aiosqlite", "dotenv", "requests", "httpx",
    "torch", "pytorch_lightning", "pytorch_forecasting",
]

for pkg in required_packages:
    try:
        importlib.import_module(pkg)
        check(f"Package: {pkg}", True)
    except ImportError as e:
        check(f"Package: {pkg}", False, f"Not installed: {e}")


# ═══════════════════════════════════════════════════════════════
# Check 3: .env configuration
# ═══════════════════════════════════════════════════════════════
section("Configuration")

env_file = ROOT / ".env"
check(".env file exists", env_file.exists(), str(env_file))

if env_file.exists():
    from config import ALPACA_API_KEY, ALPACA_API_SECRET, THETA_USERNAME, THETA_PASSWORD

    check(
        "ALPACA_API_KEY set",
        bool(ALPACA_API_KEY) and ALPACA_API_KEY != "your_key_here",
        "Set in .env" if ALPACA_API_KEY and ALPACA_API_KEY != "your_key_here" else "Missing or placeholder",
    )
    check(
        "ALPACA_API_SECRET set",
        bool(ALPACA_API_SECRET) and ALPACA_API_SECRET != "your_secret_here",
        "Set in .env" if ALPACA_API_SECRET and ALPACA_API_SECRET != "your_secret_here" else "Missing or placeholder",
    )
    check(
        "THETADATA_USERNAME set",
        bool(THETA_USERNAME) and THETA_USERNAME != "your_email@example.com",
        "Set in .env" if THETA_USERNAME else "Missing — needed for training",
        warn_only=True,
    )
    check(
        "THETADATA_PASSWORD set",
        bool(THETA_PASSWORD) and THETA_PASSWORD != "your_password_here",
        "Set in .env" if THETA_PASSWORD else "Missing — needed for training",
        warn_only=True,
    )
else:
    check("ALPACA_API_KEY set", False, ".env file missing — copy .env.example to .env")
    check("ALPACA_API_SECRET set", False, ".env file missing")


# ═══════════════════════════════════════════════════════════════
# Check 4: File system
# ═══════════════════════════════════════════════════════════════
section("File System")

from config import DB_PATH, MODELS_DIR, LOGS_DIR

# DB directory writable
db_dir = DB_PATH.parent
db_dir.mkdir(parents=True, exist_ok=True)
check("Database directory writable", os.access(db_dir, os.W_OK), str(db_dir))

# Models directory
MODELS_DIR.mkdir(parents=True, exist_ok=True)
check("Models directory exists", MODELS_DIR.exists(), str(MODELS_DIR))

# Logs directory
LOGS_DIR.mkdir(parents=True, exist_ok=True)
check("Logs directory writable", os.access(LOGS_DIR, os.W_OK), str(LOGS_DIR))

# Disk space
disk = shutil.disk_usage(ROOT)
free_mb = disk.free / (1024 * 1024)
check(
    f"Disk space: {free_mb:.0f} MB free",
    free_mb > 500,
    f"Minimum 500 MB recommended. Free: {free_mb:.0f} MB",
)


# ═══════════════════════════════════════════════════════════════
# Check 5: Alpaca connection
# ═══════════════════════════════════════════════════════════════
section("Alpaca Connection")

try:
    from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER

    if ALPACA_API_KEY and ALPACA_API_KEY != "your_key_here":
        from alpaca.trading.client import TradingClient
        import time

        start = time.time()
        client = TradingClient(ALPACA_API_KEY, ALPACA_API_SECRET, paper=ALPACA_PAPER)
        account = client.get_account()
        elapsed = time.time() - start

        check(
            "Alpaca API connected",
            True,
            f"Equity: ${float(account.equity):,.2f} | "
            f"Paper: {ALPACA_PAPER} | "
            f"Latency: {elapsed*1000:.0f}ms",
        )

        equity = float(account.equity)
        check(
            f"Account equity: ${equity:,.2f}",
            equity > 0,
            "Zero equity — fund paper account at https://app.alpaca.markets" if equity == 0 else "",
            warn_only=True,
        )

        # Check PDT status
        pdt_count = int(account.daytrade_count) if hasattr(account, 'daytrade_count') else 0
        pdt_ok = equity >= 25000 or pdt_count < 3
        check(
            f"PDT status: {pdt_count}/3 day trades",
            pdt_ok,
            "At PDT limit — no more day trades until rolling window clears" if not pdt_ok else "",
            warn_only=True,
        )
    else:
        check("Alpaca API connected", False, "API key not configured")

except Exception as e:
    check("Alpaca API connected", False, f"Connection failed: {type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════════
# Check 6: Theta Terminal connection
# ═══════════════════════════════════════════════════════════════
section("Theta Terminal")

try:
    import requests
    from config import THETA_BASE_URL_V3

    resp = requests.get(f"{THETA_BASE_URL_V3}/stock/list/symbols", timeout=5)
    check(
        "Theta Terminal V3 connected",
        resp.status_code == 200,
        f"Status: {resp.status_code} at {THETA_BASE_URL_V3}",
        warn_only=True,
    )
except requests.exceptions.ConnectionError:
    check(
        "Theta Terminal V3 connected",
        False,
        "Not running — needed for model training. Start: java -jar ThetaTerminalv3.jar",
        warn_only=True,
    )
except Exception as e:
    check("Theta Terminal V3 connected", False, f"Error: {e}", warn_only=True)


# ═══════════════════════════════════════════════════════════════
# Check 7: UI build
# ═══════════════════════════════════════════════════════════════
section("UI")

ui_dist = ROOT / "ui" / "dist"
check(
    "UI production build exists",
    ui_dist.exists() and any(ui_dist.iterdir()) if ui_dist.exists() else False,
    f"{'Found at ' + str(ui_dist) if ui_dist.exists() else 'Run: cd ui && npm run build'}",
    warn_only=True,
)


# ═══════════════════════════════════════════════════════════════
# Check 8: Database
# ═══════════════════════════════════════════════════════════════
section("Database")

if DB_PATH.exists():
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        expected = {"profiles", "models", "trades", "system_state", "training_logs"}
        missing = expected - set(tables)
        check(
            f"Database tables: {len(tables)} found",
            not missing,
            f"Missing: {missing}" if missing else f"Tables: {', '.join(sorted(tables))}",
        )

        # Count profiles
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        cursor = conn.execute("SELECT COUNT(*) FROM profiles")
        profile_count = cursor.fetchone()[0]
        cursor = conn.execute("SELECT COUNT(*) FROM models WHERE status = 'ready'")
        model_count = cursor.fetchone()[0]
        conn.close()

        check(
            f"Profiles: {profile_count}, Trained models: {model_count}",
            True,
            "Create a profile and train a model from the UI to start trading" if profile_count == 0 else "",
            warn_only=True,
        )

    except Exception as e:
        check("Database readable", False, str(e))
else:
    check(
        "Database exists",
        True,  # Not a failure — will be created on first run
        "Will be created on first backend start",
        warn_only=True,
    )


# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
section("SUMMARY")

total = len(results)
passed = sum(1 for s, _, _ in results if "PASS" in s)
warned = sum(1 for s, _, _ in results if "WARN" in s)
failed = sum(1 for s, _, _ in results if "FAIL" in s)

print(f"\n  Total checks : {total}")
print(f"  Passed       : {passed}")
print(f"  Warnings     : {warned}")
print(f"  Failed       : {failed}")

if failed == 0:
    print(f"\n  ✓ Pre-flight check PASSED ({warned} warnings)")
    if warned > 0:
        print("    Warnings are non-fatal but should be addressed for full functionality.")
    print("\n  Ready to start: python main.py")
else:
    print(f"\n  ✗ Pre-flight check FAILED — {failed} critical issue(s)")
    print("\n  Fix the FAIL items above before starting the bot.")

print()
sys.exit(1 if fail_count > 0 else 0)
