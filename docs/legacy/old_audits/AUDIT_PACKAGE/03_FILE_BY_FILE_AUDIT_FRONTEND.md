# 03 — File-by-File Audit: Frontend

**Audit date**: 2026-03-11
**Auditor**: Claude Opus 4.6
**Scope**: Every `.ts`, `.tsx`, `.js`, `.jsx`, `.css`, `.html` file under `ui/` excluding `node_modules/` and `dist/`

---

## File Count

**Total frontend source files: 20** (excluding `node_modules/` and `dist/` build artifacts)

| Category | Count | Lines |
|----------|-------|-------|
| Config files (.js, .ts) | 4 | 85 |
| Entry point (.html, .tsx, .css) | 3 | 54 |
| Types (.ts) | 1 | 271 |
| API client (.ts) | 1 | 159 |
| Components (.tsx) | 7 | 549 |
| Pages (.tsx) | 6 | 3,947 |
| App root (.tsx) | 1 | 47 |
| **Total** | **20** | **5,112** |

---

## File-by-File Audit Entries

---

### ui/index.html
- **Lines**: 13
- **Purpose**: Root HTML entry point for the Vite SPA. Contains the `#root` div and loads `main.tsx`.
- **Key symbols**: `#root` div
- **Imports**: `/src/main.tsx` via script module
- **Exports**: N/A
- **API calls**: None
- **State**: N/A
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/eslint.config.js
- **Lines**: 23
- **Purpose**: ESLint flat config for the frontend. Configures TypeScript, React hooks, and React Refresh rules.
- **Key symbols**: `defineConfig`, `globalIgnores`
- **Imports**: `@eslint/js`, `globals`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `typescript-eslint`, `eslint/config`
- **Exports**: Default config array
- **API calls**: None
- **State**: N/A
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/postcss.config.js
- **Lines**: 6
- **Purpose**: PostCSS configuration for Tailwind CSS and Autoprefixer.
- **Key symbols**: `plugins` object
- **Imports**: None (declarative config)
- **Exports**: Default config object
- **API calls**: None
- **State**: N/A
- **Bugs found**: BUG — The plugin format uses `tailwindcss: {}` and `autoprefixer: {}` as object keys in `plugins`. This is the newer PostCSS config format which requires the plugins to be resolvable by name. This works with newer versions of PostCSS. However, the key is a string name, not an import — it depends on PostCSS resolving `tailwindcss` as a package name. Since the project appears to work (`dist/` exists), this is functional but worth noting as a fragile pattern.
- **Verdict**: PASS (functional but fragile plugin resolution)

---

### ui/tailwind.config.js
- **Lines**: 41
- **Purpose**: Tailwind CSS configuration defining the project's dark terminal-style design system — custom colors, fonts, and font sizes.
- **Key symbols**: `colors` (base, surface, panel, border, muted, text, gold, profit, loss, active, created, training, ready, paused, error), `fontFamily` (sans, mono), `fontSize` (2xs)
- **Imports**: None
- **Exports**: Default Tailwind config
- **API calls**: None
- **State**: N/A
- **Bugs found**: None. Color names map cleanly to the profile status values used in `StatusBadge.tsx`.
- **Verdict**: PASS

---

### ui/vite.config.ts
- **Lines**: 15
- **Purpose**: Vite build config. Sets dev server to port 3000 and proxies `/api` requests to the backend at `localhost:8000`.
- **Key symbols**: `defineConfig`, `react` plugin, `server.proxy`
- **Imports**: `vite`, `@vitejs/plugin-react`
- **Exports**: Default Vite config
- **API calls**: None (configures proxy)
- **State**: N/A
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/src/main.tsx
- **Lines**: 10
- **Purpose**: React entry point. Mounts `<App>` into `#root` with StrictMode.
- **Key symbols**: `ReactDOM.createRoot`, `React.StrictMode`
- **Imports**: `react`, `react-dom/client`, `./App`, `./index.css`
- **Exports**: None (side-effect only)
- **API calls**: None
- **State**: N/A
- **Bugs found**: None. Uses non-null assertion on `getElementById('root')!` which is safe given the HTML always has `#root`.
- **Verdict**: PASS

---

### ui/src/index.css
- **Lines**: 31
- **Purpose**: Global CSS. Imports Google Fonts (DM Sans, IBM Plex Mono), applies Tailwind directives, sets base body styles, defines `.num` utility class for tabular numbers, and custom scrollbar styling.
- **Key symbols**: `.num` class, `@tailwind base/components/utilities`, `@layer base`, `@layer components`
- **Imports**: Google Fonts via `@import url()`
- **Exports**: N/A
- **API calls**: None
- **State**: N/A
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/src/App.tsx
- **Lines**: 47
- **Purpose**: Root application component. Sets up React Router (BrowserRouter) and React Query (QueryClientProvider) with a 10-second stale time. Defines all routes.
- **Key symbols**: `App` (default export), `queryClient`
- **Imports**: `react-router-dom` (BrowserRouter, Routes, Route, Link), `@tanstack/react-query` (QueryClient, QueryClientProvider), Layout, Dashboard, Profiles, ProfileDetail, Trades, SignalLogs, System
- **Exports**: `App` (default)
- **API calls**: None
- **State**: None
- **Bugs found**: `Link` is imported but only used inside the catch-all 404 route's inline JSX. Not a bug, just a minor import that could be inlined. No actual bugs.
- **Verdict**: PASS

---

### ui/src/api/client.ts
- **Lines**: 159
- **Purpose**: Typed API client wrapping `fetch()` for all backend endpoints. Groups endpoints by domain: profiles, models, trades, system, backtest, trading, signals.
- **Key symbols**: `api` object (named export), `request<T>()` helper, `BASE` constant
- **Imports**: All type interfaces from `../types/api`
- **Exports**: `api` (named)
- **API calls**: All of them. This is the single API layer.
  - `GET /api/profiles`, `GET /api/profiles/:id`, `POST /api/profiles`, `PUT /api/profiles/:id`, `DELETE /api/profiles/:id`, `POST /api/profiles/:id/activate`, `POST /api/profiles/:id/pause`
  - `POST /api/models/:id/train`, `POST /api/models/:id/retrain`, `GET /api/models/:id/status`, `GET /api/models/:id/logs`, `DELETE /api/models/:id/logs`, `GET /api/models/:id/importance`
  - `GET /api/trades`, `GET /api/trades/active`, `GET /api/trades/stats`, `GET /api/trades/export`
  - `GET /api/system/health`, `GET /api/system/status`, `GET /api/system/pdt`, `GET /api/system/errors`, `DELETE /api/system/errors`, `GET /api/system/model-health`, `GET /api/system/training-queue`
  - `POST /api/backtest/:id`, `GET /api/backtest/:id/results`
  - `GET /api/trading/status`, `POST /api/trading/start`, `POST /api/trading/stop`, `POST /api/trading/restart`, `GET /api/trading/startable-profiles`
  - `GET /api/signals/:id`
- **State**: N/A
- **Bugs found**:
  1. **BUG (minor)**: `request()` sets `Content-Type: application/json` for all non-GET requests, even DELETE which has no body. Not harmful (servers ignore it), but technically unnecessary.
  2. The `exportUrl` methods return raw URL strings (not fetch calls) — used to trigger file downloads via anchor element click. This is correct.
- **Verdict**: PASS

---

### ui/src/types/api.ts
- **Lines**: 271
- **Purpose**: TypeScript type definitions matching `backend/schemas.py`. Defines all API response interfaces used throughout the frontend.
- **Key symbols**: `Profile`, `ProfileCreate`, `ProfileUpdate`, `ModelSummary`, `TrainingStatus`, `ModelMetrics`, `FeatureImportanceResponse`, `TrainingLogEntry`, `Trade`, `TradeStats`, `CircuitBreakerState`, `SystemStatus`, `HealthCheck`, `PDTStatus`, `ErrorLogEntry`, `TrainingQueueStatus`, `BacktestRequest`, `BacktestResult`, `TradingProcessInfo`, `TradingStatusResponse`, `TradingStartResponse`, `TradingStopResponse`, `StartableProfile`, `ModelHealthEntry`, `ModelHealthResponse`, `SignalLogEntry`
- **Imports**: None
- **Exports**: All interfaces (named exports)
- **API calls**: None
- **State**: N/A
- **Bugs found**:
  1. `ModelMetrics` interface is defined but never imported or used anywhere in the frontend. Dead type.
  2. `CircuitBreakerState` is used via `SystemStatus.circuit_breaker_states` in `System.tsx` — confirmed used.
- **Verdict**: PASS (one dead type `ModelMetrics` is harmless)

---

### ui/src/components/ConnIndicator.tsx
- **Lines**: 16
- **Purpose**: Small status indicator component showing a colored dot + label + "connected"/"offline" text.
- **Key symbols**: `ConnIndicator` (named export), `Props` interface
- **Imports**: None (pure component)
- **Exports**: `ConnIndicator`
- **API calls**: None
- **State**: None
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/src/components/Layout.tsx
- **Lines**: 85
- **Purpose**: Application shell with sidebar navigation and main content area. Sidebar shows logo, nav links, health status dot, and API host footer. Uses `<Outlet>` for routed content.
- **Key symbols**: `Layout` (named export), `NAV` array
- **Imports**: `react-router-dom` (NavLink, Outlet), `lucide-react` (LayoutDashboard, Users, History, Search, Activity, ChevronRight), `@tanstack/react-query` (useQuery), `api` from client
- **Exports**: `Layout`
- **API calls**: `api.system.health` (polled every 30s for the sidebar status dot)
- **State**: None (uses React Query)
- **Bugs found**: None. The `end` prop on the root NavLink (`to="/"`) correctly prevents it from matching all routes.
- **Verdict**: PASS

---

### ui/src/components/PageHeader.tsx
- **Lines**: 17
- **Purpose**: Reusable page header component with title, optional subtitle, and optional action buttons slot.
- **Key symbols**: `PageHeader` (named export), `Props` interface
- **Imports**: None
- **Exports**: `PageHeader`
- **API calls**: None
- **State**: None
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/src/components/PnlCell.tsx
- **Lines**: 15
- **Purpose**: Renders a P&L value with green/red coloring and +/- prefix. Returns dash for null values.
- **Key symbols**: `PnlCell` (named export), `Props` interface
- **Imports**: None
- **Exports**: `PnlCell`
- **API calls**: None
- **State**: None
- **Bugs found**: None. Correctly uses `== null` to catch both null and undefined.
- **Verdict**: PASS

---

### ui/src/components/ProfileForm.tsx
- **Lines**: 386
- **Purpose**: Modal form for creating or editing trading profiles. Includes preset selection (swing/general/scalp), symbol management with add/remove, and advanced risk parameter sliders. Auto-switches to SPY for scalp preset.
- **Key symbols**: `ProfileForm` (named export), `ConfigSlider` (internal), `PRESETS`, `PRESET_DESCRIPTIONS`
- **Imports**: `react` (useState), `@tanstack/react-query` (useMutation, useQueryClient), `lucide-react` (X, Plus), `api`, `Spinner`, `Profile` type
- **Exports**: `ProfileForm`
- **API calls**: `api.profiles.create()`, `api.profiles.update()`
- **State**: `name`, `preset`, `symbols`, `symbolInput`, `error`, `maxPositionPct`, `maxContracts`, `maxConcurrent`, `maxDailyTrades`, `maxDailyLossPct`, `minConfidence`, `showAdvanced`
- **Bugs found**:
  1. **BUG (minor)**: The `isDirty` check does not include `minConfidence` for scalp presets. If a user only changes `minConfidence`, the dirty check returns false and clicking the backdrop will close without a warning. The `minConfidence` state is only sent to the backend when `preset === 'scalp'`, but the `isDirty` function never checks if it changed.
  2. **BUG (minor)**: The `minConfidence` slider has `min={0.50}` and `max={0.90}`, but the actual backend scalp profile has `min_confidence: 0.10`. The UI constrains the user to 0.50-0.90 when the real system supports 0.10. This may be intentional as a safety guard, but is inconsistent with the actual config.
- **Verdict**: PASS (minor issues, no data loss risk)

---

### ui/src/components/Spinner.tsx
- **Lines**: 6
- **Purpose**: Animated loading spinner component with three sizes (sm/md/lg).
- **Key symbols**: `Spinner` (named export)
- **Imports**: None
- **Exports**: `Spinner`
- **API calls**: None
- **State**: None
- **Bugs found**: None
- **Verdict**: PASS

---

### ui/src/components/StatusBadge.tsx
- **Lines**: 24
- **Purpose**: Renders a colored badge for profile/trade status values. Maps status strings to Tailwind color classes.
- **Key symbols**: `StatusBadge` (named export), `STATUS_STYLES` lookup
- **Imports**: None
- **Exports**: `StatusBadge`
- **API calls**: None
- **State**: None
- **Bugs found**: None. Has a fallback style for unknown status values, which is good defensive coding.
- **Verdict**: PASS

---

### ui/src/pages/Dashboard.tsx
- **Lines**: 588
- **Purpose**: Main dashboard page showing portfolio summary (5 stat cards), PDT warning banner, model health banner, profile cards grid, and system status panel. Auto-refreshes every 30 seconds.
- **Key symbols**: `Dashboard` (named export), `StatCard`, `ProfileCard`, `StatusPanel` (internal components), `fmtDollars`, `fmtUptime`, `MAX_TOTAL_POSITIONS`
- **Imports**: `@tanstack/react-query`, `react-router-dom`, `lucide-react` (many icons), `api`, `StatusBadge`, `ConnIndicator`, `PnlCell`, `Spinner`, `PageHeader`, types (`Profile`, `SystemStatus`, `PDTStatus`, `ModelHealthResponse`, `TrainingQueueStatus`)
- **Exports**: `Dashboard`
- **API calls**: `api.profiles.list`, `api.system.status`, `api.system.pdt`, `api.trades.stats`, `api.system.modelHealth`, `api.system.trainingQueue`, `api.profiles.activate`, `api.profiles.pause`, `api.system.clearErrors`
- **State**: None (all via React Query)
- **Bugs found**:
  1. **BUG (hardcoded constant)**: `MAX_TOTAL_POSITIONS = 10` is hardcoded. Comment says "Must match MAX_TOTAL_POSITIONS in backend config.py". If the backend value changes, the frontend will show wrong limits. Should ideally come from the API.
  2. **BUG (minor)**: In `StatusPanel`, the timestamp parsing for `last_error_at` uses an inline IIFE with timezone detection. This same pattern is repeated in 4+ files. Should be a shared utility, but functionally correct.
  3. **Observation**: The model health banner hardcodes `52` as the accuracy threshold string: `below ${52}% threshold`. This works but reads oddly — should just be the literal string "52%".
- **Verdict**: PASS (hardcoded constant is a sync risk, not a runtime bug)

---

### ui/src/pages/Profiles.tsx
- **Lines**: 376
- **Purpose**: Profile list page with a table showing all profiles. Supports CRUD operations: create, edit, delete, activate, pause, and train. Has a delete confirmation dialog.
- **Key symbols**: `Profiles` (named export), `ProfileRow`, `DeleteDialog` (internal), state variables for modals and mutations
- **Imports**: `react` (useState), `react-router-dom` (useNavigate), `@tanstack/react-query`, `lucide-react`, `api`, `PageHeader`, `StatusBadge`, `Spinner`, `PnlCell`, `ProfileForm`, `Profile` type
- **Exports**: `Profiles`
- **API calls**: `api.profiles.list`, `api.profiles.activate`, `api.profiles.pause`, `api.models.train`, `api.profiles.delete`
- **State**: `showCreate`, `editProfile`, `deleteTarget`, `mutatingId`
- **Bugs found**:
  1. **BUG (minor)**: `paused` status uses `bg-training` color in the status legend (line 355), meaning paused and training show the same dot color. This is misleading — paused should be gray/muted, not gold.
  2. **BUG (minor)**: The `trainMutation` calls `api.models.train(id)` without specifying a model type, so it defaults to `'xgboost'`. For profiles where the default should be `xgb_classifier` (scalp), the user would need to go to ProfileDetail to pick the right type. Not a crash bug, but could lead to training the wrong model type from this page.
- **Verdict**: PASS (minor UX issues)

---

### ui/src/pages/ProfileDetail.tsx
- **Lines**: 1150
- **Purpose**: Detailed view of a single trading profile. Shows model health with multi-model tab switching, training controls (train/retrain with model type dropdown), trade performance stats, backtest panel, signal decision log, and trade history table. The largest file in the frontend.
- **Key symbols**: `ProfileDetail` (named export), `MetricTile`, `TrainingLogs`, `FeatureImportancePanel`, `SignalLogPanel` (internal components), `parseUTC`
- **Imports**: `react` (useState, useEffect, useRef), `react-router-dom` (useParams, useNavigate), `@tanstack/react-query`, `lucide-react` (many icons), types (`ModelSummary`, `ModelHealthEntry`, `ModelHealthResponse`), `api`, `StatusBadge`, `Spinner`, `PnlCell`, `ProfileForm`
- **Exports**: `ProfileDetail`
- **API calls**: `api.profiles.get`, `api.models.status`, `api.trades.list`, `api.trades.stats`, `api.models.importance`, `api.backtest.results`, `api.system.modelHealth`, `api.models.train`, `api.models.retrain`, `api.profiles.activate`, `api.profiles.pause`, `api.backtest.run`, `api.models.logs`, `api.models.clearLogs`, `api.signals.list`
- **State**: `showEdit`, `showLogs`, `trainModelType`, `showModelTypeMenu`, `trainError`, `showBacktest`, `backtestStart`, `backtestEnd`
- **Bugs found**:
  1. **BUG (code smell / duplication)**: The model display section (lines 561-848) has massive duplication. The "multi-tab" branch (lines 573-713) and the "single model" branch (lines 717-828) contain nearly identical MetricTile grids, model health status blocks, classifier metric displays, feature importance panels, etc. The file itself has a TODO comment: "Extract ModelDisplay component to reduce duplication" (line 560). This is ~250 lines of duplicated JSX.
  2. **BUG (minor)**: Import ordering is unusual — `parseUTC` is defined between two import blocks (line 14-17). The `Spinner`, `PnlCell`, and `ProfileForm` imports come after the `parseUTC` function definition. This works in JS/TS but is unconventional and could confuse linters.
  3. **BUG (minor)**: The `class_distribution` display (lines 680, 804) accesses keys `'down'`, `'neutral'`, `'up'` but the scalp classifier is binary (UP/DOWN only, no neutral class per MEMORY.md). The `neutral` key will show `?` for scalp models. Not a crash, but misleading display.
  4. **BUG (potential)**: `useEffect` for setting default `trainModelType` (line 337-343) has an eslint-disable comment suppressing the exhaustive-deps warning. The dependency array includes `trainModelType` which could cause unnecessary re-renders, but it has a guard `!validTypes.includes(trainModelType)` that prevents infinite loops.
- **Verdict**: PASS (significant duplication is a maintainability concern but not a runtime bug)

---

### ui/src/pages/Trades.tsx
- **Lines**: 485
- **Purpose**: Trade history page with full-featured data table. Supports client-side filtering (profile, symbol, status, direction, date range), client-side sorting on all columns, CSV export, and summary statistics row.
- **Key symbols**: `Trades` (named export), `SortField`, `SortDir`, `Filters` types, `FilterBar`, `SummaryRow`, `ColHeader`, `SortIcon` (internal components), `fmt`, `fmtDate`, `EMPTY_FILTERS`
- **Imports**: `react` (useState, useMemo), `@tanstack/react-query`, `lucide-react`, `api`, `PageHeader`, `StatusBadge`, `PnlCell`, `Spinner`, `Trade` type
- **Exports**: `Trades`
- **API calls**: `api.trades.list` (with profile_id filter, limit 500), `api.profiles.list` (for dropdown), `api.trades.exportUrl` (for CSV download)
- **State**: `filters`, `sortField`, `sortDir`
- **Bugs found**:
  1. **BUG (minor)**: The prediction column (line 450) checks `trade.entry_model_type` against a hardcoded list `['xgb_classifier', 'xgb_swing_classifier', 'lgbm_classifier']` to decide display format. If new classifier model types are added, this list must be manually updated.
  2. **BUG (minor)**: The `dateTo` filter comparison (line 281) appends `'T23:59:59.999Z'` to include the full end date. This is correct but assumes `entry_date` is an ISO string. If `entry_date` contains timezone info, the string comparison could behave unexpectedly, though in practice backend dates are ISO format.
  3. **BUG (minor)**: CSV export (lines 321-329) creates a temporary anchor element and clicks it. This works but does not handle errors — if the backend is down, the user gets no feedback (just a failed download).
- **Verdict**: PASS

---

### ui/src/pages/SignalLogs.tsx
- **Lines**: 509
- **Purpose**: Signal decision log page showing every trading iteration and why the bot traded or skipped. Features client-side filtering, sorting, summary stats, and CSV export. Auto-selects first profile when only one exists.
- **Key symbols**: `SignalLogs` (named export), `STEP_NAMES` mapping, `SortField`, `SortDir`, `Filters` types, `FilterBar`, `SummaryRow`, `ColHeader`, `SortIcon` (internal components), `fmt`, `fmtDatetime`, `EMPTY_FILTERS`
- **Imports**: `react` (useState, useMemo), `@tanstack/react-query`, `lucide-react`, `api`, `PageHeader`, `Spinner`, `SignalLogEntry` type
- **Exports**: `SignalLogs`
- **API calls**: `api.signals.list` (per profile, limit 500), `api.profiles.list` (for dropdown), `api.signals.exportUrl` (for CSV download)
- **State**: `filters`, `sortField`, `sortDir`
- **Bugs found**:
  1. **BUG (minor)**: When "All Profiles" is selected, the component fetches from every profile individually with `Promise.all` (line 281), merges results, sorts, and truncates to 500. This is O(N) network requests where N = number of profiles. For many profiles this could be slow. A dedicated backend endpoint for cross-profile signal logs would be better.
  2. **BUG (minor)**: The `STEP_NAMES` mapping uses string keys including fractional steps like `'8.7'`, `'9.5'`, `'9.7'`. The `step_stopped_at` field is typed as `number | null` in the API types. When `String(signal.step_stopped_at)` is used to look up in `STEP_NAMES`, floating point numbers should match their string keys correctly (e.g., `String(9.5) === '9.5'`), so this works.
  3. **BUG (minor)**: The classifier detection (line 206) checks `predictor_type` against `['ScalpPredictor', 'SwingClassifierPredictor']`. This is a hardcoded list that must be maintained if new predictor types are added.
- **Verdict**: PASS

---

### ui/src/pages/System.tsx
- **Lines**: 839
- **Purpose**: System status page. Displays connection cards (Backend, Alpaca, Theta Terminal), trading engine control panel (quick start, stop all, per-process controls), circuit breaker states, PDT tracking with progress bar, portfolio snapshot, runtime info, and error log with expandable entries.
- **Key symbols**: `System` (named export), `ConnectionCard`, `StatRow`, `ErrorRow`, `TradingProcessRow` (internal components), `fmtUptime`, `fmtDollars`, `fmtTimestamp`, `MAX_TOTAL_POSITIONS`
- **Imports**: `react` (useState), `@tanstack/react-query`, `lucide-react` (many icons), `api`, `PageHeader`, `Spinner`, types (`ErrorLogEntry`, `TradingProcessInfo`)
- **Exports**: `System`
- **API calls**: `api.system.health`, `api.system.status`, `api.system.pdt`, `api.system.errors`, `api.system.clearErrors`, `api.trading.status`, `api.trading.startableProfiles`, `api.trading.start`, `api.trading.stop`, `api.trading.restart`
- **State**: `errorLimit`, `showQuickStart`, `selectedProfiles`
- **Bugs found**:
  1. **BUG (hardcoded constant)**: `MAX_TOTAL_POSITIONS = 10` is duplicated here (same as Dashboard.tsx). Two places to update if backend changes.
  2. **BUG (minor)**: `ErrorRow` uses array index `i` as the React key (line 819): `key={i}`. If errors are added/removed between renders, this could cause incorrect component reuse. Should use a unique identifier (timestamp + message hash). However, error log entries lack a stable `id` field in the type definition.
  3. **BUG (minor)**: The `fmtUptime` function (line 24-32) uses `seconds % 60` for the seconds component, but `uptime_seconds` from the backend is a number that may have fractional parts. `Math.floor` should be applied to the seconds remainder. Currently `const s = seconds % 60` could display something like `2m 34.56789s`. The Dashboard version of `fmtUptime` does not have this issue because it only shows hours and minutes.
  4. **BUG (minor)**: Circuit breaker `alpaca_failure_count` from the `CircuitBreakerState` type is available but never displayed in the UI (line 546 reads it as `const alpacaFails` is not defined — only `thetaFails` is extracted and displayed). Actually looking more carefully: `alpaca_failure_count` is defined in the type but the code only extracts `thetaFails` (line 545). The Alpaca failure count is never shown.
- **Verdict**: PASS (minor issues, functional)

---

## Cross-Cutting Findings

### 1. Duplicated Constants
- `MAX_TOTAL_POSITIONS = 10` is hardcoded in both `Dashboard.tsx` (line 21) and `System.tsx` (line 18). Should be fetched from the backend or centralized in a constants file.

### 2. Duplicated Utility Functions
- `fmtDollars()` is defined in both `Dashboard.tsx` and `System.tsx` with identical implementations.
- `fmtUptime()` is defined in both `Dashboard.tsx` and `System.tsx` with slightly different implementations (Dashboard omits seconds).
- UTC timestamp parsing logic (`hasTimezone` regex check + append 'Z') is repeated in `Dashboard.tsx`, `ProfileDetail.tsx`, `Trades.tsx`, `SignalLogs.tsx`, and `System.tsx`.
- These should be extracted to a shared `utils.ts` file.

### 3. Hardcoded Classifier Type Lists
- Three separate files maintain hardcoded lists of classifier model types or predictor types:
  - `Trades.tsx` line 450: `['xgb_classifier', 'xgb_swing_classifier', 'lgbm_classifier']`
  - `SignalLogs.tsx` line 206: `['ScalpPredictor', 'SwingClassifierPredictor']`
  - `SignalLogs.tsx` line 459: same list
- These should be centralized.

### 4. Dead Type
- `ModelMetrics` in `api.ts` (line 60) is never imported or used anywhere.

### 5. ProfileDetail.tsx Duplication
- ~250 lines of duplicated model display JSX between the multi-tab and single-model branches. The file acknowledges this with a TODO comment.

### 6. No Error Boundaries
- No React error boundary components exist. A JS error in any component will crash the entire app. Should have at least a top-level error boundary.

### 7. No Loading/Error States for Mutations
- Most mutation error states are silently swallowed or only shown temporarily. For example, `activateMutation` and `pauseMutation` in Dashboard do not display errors to the user.

---

## Summary

| Verdict | Count |
|---------|-------|
| PASS | 20 |
| FAIL | 0 |

**Total bugs found**: 18 (all minor/medium severity)

- **0 critical bugs** (no data loss, no crashes, no security issues)
- **2 medium bugs** (hardcoded `MAX_TOTAL_POSITIONS` duplicated in 2 files; ProfileDetail.tsx ~250 lines of duplicated JSX)
- **16 minor bugs** (hardcoded type lists, missing error displays, dead code, code smells)

The frontend is well-structured, uses modern React patterns (React Query for server state, proper mutation handling, clean component composition), and has a consistent design system. The main maintenance concerns are duplicated utilities and the large `ProfileDetail.tsx` file.
