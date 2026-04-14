# 17 — FRONTEND-BACKEND BINDINGS

See detailed CSV at `17_FRONTEND_BACKEND_BINDINGS.csv` (33 bindings, all PASS).

## Summary

Every API call in `ui/src/api/client.ts` was traced to its backend handler. All frontend TypeScript types in `ui/src/types/api.ts` compared field-by-field against backend Pydantic schemas.

- **33 bindings mapped** (B-01 through B-33)
- **All 33 PASS** — types match between frontend and backend
- **2 loose backend schemas** (dict instead of Pydantic model) but structurally compatible

## UI Interaction Evidence

Runtime UI testing with Playwright confirmed that all frontend components successfully:
1. Fetch data from backend endpoints (109 API requests captured during test)
2. Render responses correctly (52 screenshots in `screenshots/`)
3. Handle error states (404 pages, missing profiles, conditional controls)

Network evidence: `network/api_requests.json` (109 API calls during UI testing)

## Evidence

Detailed per-binding validation in `17_FRONTEND_BACKEND_BINDINGS.csv`.
UI interaction evidence in `screenshots/` and `network/` directories.
