# 19 — CONFIG/ENV AUDIT

See detailed CSV at `19_CONFIG_ENV_STORAGE_INVENTORY.csv` (96 items).

## Summary

- **59 config variables** (CFG-001 through CFG-059): Every variable in config.py
- **12 environment variables** (ENV-001 through ENV-012): All os.getenv calls
- **1 database file** (DB-001): options-bot/db/options_bot.db
- **3 log paths** (LOG-001 through LOG-003)
- **6 storage paths** (STOR-001 through STOR-006)
- **10 model artifacts** (MDL-001 through MDL-010)
- **5 runtime artifacts** (RTA-001 through RTA-005)

## Failures

- CFG-008 (THETA_BASE_URL_V2): Port 25510 hardcoded instead of env var

## Evidence

Detailed per-item validation in `19_CONFIG_ENV_STORAGE_INVENTORY.csv`.
