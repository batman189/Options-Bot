# 17 — FRONTEND-BACKEND BINDINGS

See detailed CSV at `17_FRONTEND_BACKEND_BINDINGS.csv` (33 bindings, all PASS).

## Summary

Every API call in `ui/src/api/client.ts` was traced to its backend handler. All frontend TypeScript types in `ui/src/types/api.ts` compared field-by-field against backend Pydantic schemas.

- **33 bindings mapped** (B-01 through B-33)
- **All 33 PASS** — types match between frontend and backend
- **2 loose backend schemas** (dict instead of Pydantic model) but structurally compatible

## Evidence

Detailed per-binding validation in `17_FRONTEND_BACKEND_BINDINGS.csv`.
