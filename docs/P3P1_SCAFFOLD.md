# PHASE 3 PROMPT 1 — React UI Scaffold, API Client, Layout, Routing

## TASK
Create the complete React frontend scaffold inside `options-bot/ui/`. This includes the
Vite + React + TypeScript project, all dependencies, a typed API client covering every
backend endpoint, a persistent dark-terminal layout with sidebar navigation, and
placeholder page components for all 5 routes. At the end, `npm run dev` serves the
app at localhost:3000 with navigation working between all pages.

**DO NOT touch any backend files. Zero backend changes. The API is final.**

---

## READ FIRST

```bash
cd options-bot
# Confirm backend is accessible (should already be running or startable)
curl -s http://localhost:8000/api/system/health | python -m json.tool
# Read the schemas to understand exact response shapes
cat backend/schemas.py
```

---

## STEP 1 — Create the Vite project

```bash
cd options-bot
npm create vite@latest ui -- --template react-ts
cd ui
```

---

## STEP 2 — Install dependencies

```bash
npm install react-router-dom@6
npm install @tanstack/react-query@5
npm install recharts
npm install lucide-react
npm install -D tailwindcss@3 postcss autoprefixer
npx tailwindcss init -p
```

---

## STEP 3 — Configure Tailwind

**File: `options-bot/ui/tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Terminal dark palette
        base:    "#080c10",
        surface: "#0f1419",
        panel:   "#141c24",
        border:  "#1e2d3d",
        muted:   "#6b7a8d",
        text:    "#e8edf2",
        // Accent
        gold:    "#f0a500",
        "gold-dim": "#8a6000",
        // Status
        profit:  "#00d68f",
        loss:    "#ff4757",
        active:  "#1a6bff",
        // Profile status
        created:  "#6b7a8d",
        training: "#f0a500",
        ready:    "#00d68f",
        paused:   "#6b7a8d",
        error:    "#ff4757",
      },
      fontFamily: {
        sans:  ["'DM Sans'", "system-ui", "sans-serif"],
        mono:  ["'IBM Plex Mono'", "monospace"],
      },
      fontSize: {
        "2xs": "0.65rem",
      },
    },
  },
  plugins: [],
}
```

---

## STEP 4 — Global CSS

**File: `options-bot/ui/src/index.css`**

```css
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html, body, #root {
    height: 100%;
  }
  body {
    background-color: #080c10;
    color: #e8edf2;
    font-family: 'DM Sans', system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  /* Tabular numbers for all financial data */
  .num {
    font-family: 'IBM Plex Mono', monospace;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em;
  }
}

@layer components {
  /* Scrollbar styling */
  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: #0f1419; }
  ::-webkit-scrollbar-thumb { background: #1e2d3d; border-radius: 2px; }
  ::-webkit-scrollbar-thumb:hover { background: #2a3d52; }
}
```

---

## STEP 5 — TypeScript types matching backend schemas exactly

**File: `options-bot/ui/src/types/api.ts`**

```typescript
// ============================================================
// Types matching backend/schemas.py exactly.
// Field names must match the JSON keys returned by the API.
// ============================================================

export interface ModelSummary {
  id: string;
  model_type: string;
  status: string;
  trained_at: string | null;
  data_range: string;
  metrics: {
    mae?: number;
    rmse?: number;
    r2?: number;
    dir_acc?: number;
    [key: string]: number | undefined;
  };
  age_days: number;
}

export interface Profile {
  id: string;
  name: string;
  preset: 'swing' | 'general' | 'scalp';
  status: 'created' | 'training' | 'ready' | 'active' | 'paused' | 'error';
  symbols: string[];
  config: Record<string, unknown>;
  model_summary: ModelSummary | null;
  active_positions: number;
  total_pnl: number;
  created_at: string;
  updated_at: string;
}

export interface ProfileCreate {
  name: string;
  preset: string;
  symbols: string[];
  config_overrides?: Record<string, unknown>;
}

export interface ProfileUpdate {
  name?: string;
  symbols?: string[];
  config_overrides?: Record<string, unknown>;
}

export interface TrainingStatus {
  model_id: string | null;
  profile_id: string;
  status: 'idle' | 'training' | 'completed' | 'failed';
  progress_pct: number | null;
  message: string | null;
}

export interface ModelMetrics {
  model_id: string;
  profile_id: string;
  model_type: string;
  mae: number | null;
  rmse: number | null;
  r2: number | null;
  directional_accuracy: number | null;
  training_samples: number | null;
  feature_count: number | null;
  cv_folds: number | null;
}

export interface TrainingLogEntry {
  id: number;
  model_id: string;
  timestamp: string;
  level: 'info' | 'warning' | 'error';
  message: string;
}

export interface Trade {
  id: string;
  profile_id: string;
  symbol: string;
  direction: string;
  strike: number;
  expiration: string;
  quantity: number;
  entry_price: number | null;
  entry_date: string | null;
  exit_price: number | null;
  exit_date: string | null;
  pnl_dollars: number | null;
  pnl_pct: number | null;
  predicted_return: number | null;
  ev_at_entry: number | null;
  exit_reason: string | null;
  hold_days: number | null;
  status: 'open' | 'closed' | 'cancelled';
  was_day_trade: boolean;
  created_at: string;
  updated_at: string;
}

export interface TradeStats {
  total_trades: number;
  open_trades: number;
  closed_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number | null;
  total_pnl_dollars: number;
  avg_pnl_pct: number | null;
  best_trade_pct: number | null;
  worst_trade_pct: number | null;
  avg_hold_days: number | null;
}

export interface SystemStatus {
  alpaca_connected: boolean;
  alpaca_subscription: string;
  theta_terminal_connected: boolean;
  active_profiles: number;
  total_open_positions: number;
  pdt_day_trades_5d: number;
  pdt_limit: number;
  portfolio_value: number;
  uptime_seconds: number;
  last_error: string | null;
}

export interface HealthCheck {
  status: string;
  timestamp: string;
  version: string;
}

export interface PDTStatus {
  day_trades_5d: number;
  limit: number;
  remaining: number;
  equity: number;
  is_restricted: boolean;
}

export interface ErrorLogEntry {
  timestamp: string;
  level: string;
  message: string;
  source: string | null;
}

export interface BacktestRequest {
  start_date: string;
  end_date: string;
  initial_capital?: number;
}

export interface BacktestResult {
  profile_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  start_date: string | null;
  end_date: string | null;
  total_trades: number | null;
  sharpe_ratio: number | null;
  max_drawdown_pct: number | null;
  total_return_pct: number | null;
  win_rate: number | null;
  message: string | null;
}
```

---

## STEP 6 — API client

**File: `options-bot/ui/src/api/client.ts`**

```typescript
// ============================================================
// Typed API client for all backend endpoints.
// Base URL: http://localhost:8000
// All functions throw on non-2xx responses.
// ============================================================

import type {
  Profile, ProfileCreate, ProfileUpdate,
  TrainingStatus, ModelMetrics, TrainingLogEntry,
  Trade, TradeStats,
  SystemStatus, HealthCheck, PDTStatus, ErrorLogEntry,
  BacktestRequest, BacktestResult,
} from '../types/api';

const BASE = 'http://localhost:8000';

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API ${options?.method ?? 'GET'} ${path} → ${res.status}: ${body}`);
  }
  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// -------------------------
// Profiles
// -------------------------
export const api = {
  profiles: {
    list: () =>
      request<Profile[]>('/api/profiles'),
    get: (id: string) =>
      request<Profile>(`/api/profiles/${id}`),
    create: (body: ProfileCreate) =>
      request<Profile>('/api/profiles', { method: 'POST', body: JSON.stringify(body) }),
    update: (id: string, body: ProfileUpdate) =>
      request<Profile>(`/api/profiles/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    delete: (id: string) =>
      request<void>(`/api/profiles/${id}`, { method: 'DELETE' }),
    activate: (id: string) =>
      request<Profile>(`/api/profiles/${id}/activate`, { method: 'POST' }),
    pause: (id: string) =>
      request<Profile>(`/api/profiles/${id}/pause`, { method: 'POST' }),
  },

  models: {
    get: (profileId: string) =>
      request<ModelMetrics>(`/api/models/${profileId}`),
    train: (profileId: string) =>
      request<TrainingStatus>(`/api/models/${profileId}/train`, { method: 'POST' }),
    retrain: (profileId: string) =>
      request<TrainingStatus>(`/api/models/${profileId}/retrain`, { method: 'POST' }),
    status: (profileId: string) =>
      request<TrainingStatus>(`/api/models/${profileId}/status`),
    metrics: (profileId: string) =>
      request<ModelMetrics>(`/api/models/${profileId}/metrics`),
    logs: (profileId: string, limit = 50) =>
      request<TrainingLogEntry[]>(`/api/models/${profileId}/logs?limit=${limit}`),
  },

  trades: {
    list: (params?: { profile_id?: string; status?: string; symbol?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.profile_id) q.set('profile_id', params.profile_id);
      if (params?.status) q.set('status', params.status);
      if (params?.symbol) q.set('symbol', params.symbol);
      if (params?.limit) q.set('limit', String(params.limit));
      return request<Trade[]>(`/api/trades${q.toString() ? `?${q}` : ''}`);
    },
    get: (id: string) =>
      request<Trade>(`/api/trades/${id}`),
    active: () =>
      request<Trade[]>('/api/trades/active'),
    stats: (profileId?: string) =>
      request<TradeStats>(`/api/trades/stats${profileId ? `?profile_id=${profileId}` : ''}`),
    exportUrl: (profileId?: string) =>
      `${BASE}/api/trades/export${profileId ? `?profile_id=${profileId}` : ''}`,
  },

  system: {
    health: () =>
      request<HealthCheck>('/api/system/health'),
    status: () =>
      request<SystemStatus>('/api/system/status'),
    pdt: () =>
      request<PDTStatus>('/api/system/pdt'),
    errors: (limit = 50) =>
      request<ErrorLogEntry[]>(`/api/system/errors?limit=${limit}`),
  },

  backtest: {
    run: (profileId: string, body: BacktestRequest) =>
      request<BacktestResult>(`/api/backtest/${profileId}`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    results: (profileId: string) =>
      request<BacktestResult>(`/api/backtest/${profileId}/results`),
  },
};
```

---

## STEP 7 — Shared UI components

### File: `options-bot/ui/src/components/StatusBadge.tsx`

```tsx
interface Props {
  status: string;
}

const STATUS_STYLES: Record<string, string> = {
  created:  'bg-created/10 text-created border-created/20',
  training: 'bg-training/10 text-training border-training/20',
  ready:    'bg-ready/10 text-ready border-ready/20',
  active:   'bg-active/10 text-active border-active/20',
  paused:   'bg-paused/10 text-paused border-paused/20',
  error:    'bg-error/10 text-error border-error/20',
  open:     'bg-active/10 text-active border-active/20',
  closed:   'bg-muted/10 text-muted border-muted/20',
};

export function StatusBadge({ status }: Props) {
  const style = STATUS_STYLES[status] ?? 'bg-muted/10 text-muted border-muted/20';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-2xs font-mono font-medium uppercase tracking-widest rounded border ${style}`}>
      {status}
    </span>
  );
}
```

### File: `options-bot/ui/src/components/Spinner.tsx`

```tsx
export function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sz = size === 'sm' ? 'h-4 w-4' : size === 'lg' ? 'h-8 w-8' : 'h-5 w-5';
  return (
    <div className={`${sz} animate-spin rounded-full border-2 border-border border-t-gold`} />
  );
}
```

### File: `options-bot/ui/src/components/PnlCell.tsx`

```tsx
interface Props {
  value: number | null;
  suffix?: string;
  className?: string;
}

export function PnlCell({ value, suffix = '', className = '' }: Props) {
  if (value === null) return <span className="text-muted num">—</span>;
  const positive = value >= 0;
  return (
    <span className={`num font-medium ${positive ? 'text-profit' : 'text-loss'} ${className}`}>
      {positive ? '+' : ''}{value.toFixed(2)}{suffix}
    </span>
  );
}
```

### File: `options-bot/ui/src/components/ConnIndicator.tsx`

```tsx
interface Props {
  connected: boolean;
  label: string;
}

export function ConnIndicator({ connected, label }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-2 w-2 rounded-full ${connected ? 'bg-profit shadow-[0_0_6px_#00d68f]' : 'bg-loss'}`} />
      <span className="text-sm text-text">{label}</span>
      <span className={`text-xs ${connected ? 'text-profit' : 'text-loss'}`}>
        {connected ? 'connected' : 'offline'}
      </span>
    </div>
  );
}
```

### File: `options-bot/ui/src/components/PageHeader.tsx`

```tsx
interface Props {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtitle, actions }: Props) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-xl font-semibold text-text tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
```

---

## STEP 8 — Layout (sidebar + main content)

### File: `options-bot/ui/src/components/Layout.tsx`

```tsx
import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard, Users, History, Activity, ChevronRight,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

const NAV = [
  { to: '/',           icon: LayoutDashboard, label: 'Dashboard'     },
  { to: '/profiles',   icon: Users,            label: 'Profiles'      },
  { to: '/trades',     icon: History,          label: 'Trade History' },
  { to: '/system',     icon: Activity,         label: 'System Status' },
];

export function Layout() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: api.system.health,
    refetchInterval: 30_000,
    retry: false,
  });

  return (
    <div className="flex h-full min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-surface border-r border-border flex flex-col">
        {/* Logo */}
        <div className="px-5 pt-6 pb-5 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded bg-gold/10 border border-gold/30 flex items-center justify-center">
              <span className="text-gold font-mono text-xs font-bold">OB</span>
            </div>
            <span className="font-semibold text-text tracking-tight">OptionsBot</span>
          </div>
          <div className="mt-2 flex items-center gap-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${health ? 'bg-profit' : 'bg-muted'}`} />
            <span className="text-2xs text-muted font-mono">
              {health ? `v${health.version} — online` : 'connecting...'}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-4 space-y-0.5">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors group
                ${isActive
                  ? 'bg-gold/10 text-gold border border-gold/20'
                  : 'text-muted hover:text-text hover:bg-panel border border-transparent'}`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={15} className={isActive ? 'text-gold' : 'text-muted group-hover:text-text'} />
                  <span>{label}</span>
                  {isActive && <ChevronRight size={12} className="ml-auto text-gold/50" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-border">
          <p className="text-2xs text-muted font-mono">
            API: localhost:8000
          </p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-auto bg-base">
        <div className="flex-1 p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
```

---

## STEP 9 — Placeholder page components

Create these 4 files. Each is a real placeholder — styled, with page title,
explaining what comes in the next prompt. Not blank screens.

### File: `options-bot/ui/src/pages/Dashboard.tsx`

```tsx
import { PageHeader } from '../components/PageHeader';

export function Dashboard() {
  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Overview of all profiles and system health"
      />
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <p className="text-muted text-sm">Dashboard widgets load in P3P2.</p>
      </div>
    </div>
  );
}
```

### File: `options-bot/ui/src/pages/Profiles.tsx`

```tsx
import { PageHeader } from '../components/PageHeader';

export function Profiles() {
  return (
    <div>
      <PageHeader
        title="Profiles"
        subtitle="Manage trading profiles"
      />
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <p className="text-muted text-sm">Profile list and create/edit load in P3P3.</p>
      </div>
    </div>
  );
}
```

### File: `options-bot/ui/src/pages/Trades.tsx`

```tsx
import { PageHeader } from '../components/PageHeader';

export function Trades() {
  return (
    <div>
      <PageHeader
        title="Trade History"
        subtitle="All trades across all profiles"
      />
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <p className="text-muted text-sm">Trade table and filters load in P3P5.</p>
      </div>
    </div>
  );
}
```

### File: `options-bot/ui/src/pages/System.tsx`

```tsx
import { PageHeader } from '../components/PageHeader';

export function System() {
  return (
    <div>
      <PageHeader
        title="System Status"
        subtitle="Connections, PDT tracking, error log"
      />
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <p className="text-muted text-sm">System status panels load in P3P6.</p>
      </div>
    </div>
  );
}
```

---

## STEP 10 — App root with React Query + Router

### File: `options-bot/ui/src/App.tsx`

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Profiles } from './pages/Profiles';
import { Trades } from './pages/Trades';
import { System } from './pages/System';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,       // 10s — data is fresh for 10s
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="profiles" element={<Profiles />} />
            <Route path="profiles/:id" element={<Profiles />} />
            <Route path="trades" element={<Trades />} />
            <Route path="system" element={<System />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

### File: `options-bot/ui/src/main.tsx`

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

---

## STEP 11 — Update index.html

**File: `options-bot/ui/index.html`**

Replace the entire file with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>OptionsBot</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%23080c10'/><text x='5' y='22' font-family='monospace' font-size='16' font-weight='bold' fill='%23f0a500'>OB</text></svg>" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

---

## STEP 12 — Vite config (proxy the API to avoid CORS issues in dev)

**File: `options-bot/ui/vite.config.ts`**

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

**IMPORTANT**: Because of the Vite proxy, change the BASE URL in the API client from
`http://localhost:8000` to an empty string so requests go through the proxy:

In `options-bot/ui/src/api/client.ts`, change line:
```typescript
const BASE = 'http://localhost:8000';
```
to:
```typescript
const BASE = '';
```

This means in development, `fetch('/api/system/health')` proxies through Vite to
`http://localhost:8000/api/system/health`. CORS is handled by the proxy, not the browser.

---

## VERIFICATION

Run each check in order. All must pass before declaring P3P1 complete.

```bash
cd options-bot/ui

# 1. Build check — no TypeScript errors
echo "=== Build check ==="
npm run build 2>&1
echo "Exit code: $?"

# 2. Confirm dev server starts on port 3000
echo ""
echo "=== Starting dev server ==="
npm run dev &
DEV_PID=$!
sleep 5

# 3. Test the app is reachable
echo ""
echo "=== HTTP reachability ==="
curl -s -o /dev/null -w "localhost:3000 HTTP: %{http_code}\n" http://localhost:3000
curl -s -o /dev/null -w "localhost:3000/ HTTP: %{http_code}\n" http://localhost:3000/

# 4. Test API proxy works (backend must be running at 8000)
echo ""
echo "=== API proxy check ==="
curl -s -o /dev/null -w "Proxy /api/system/health HTTP: %{http_code}\n" http://localhost:3000/api/system/health

# 5. Check all source files exist
echo ""
echo "=== Source file check ==="
for f in \
  src/types/api.ts \
  src/api/client.ts \
  src/components/Layout.tsx \
  src/components/StatusBadge.tsx \
  src/components/Spinner.tsx \
  src/components/PnlCell.tsx \
  src/components/ConnIndicator.tsx \
  src/components/PageHeader.tsx \
  src/pages/Dashboard.tsx \
  src/pages/Profiles.tsx \
  src/pages/Trades.tsx \
  src/pages/System.tsx \
  src/App.tsx \
  src/main.tsx \
  src/index.css \
  tailwind.config.js \
  vite.config.ts; do
  [ -f "$f" ] && echo "  OK  $f" || echo "  MISSING: $f"
done

# 6. Cleanup
kill $DEV_PID 2>/dev/null
echo ""
echo "=== Done ==="
```

---

## SUCCESS CRITERIA

1. `npm run build` exits with code 0 — no TypeScript errors, no missing imports
2. `npm run dev` starts on port 3000 — no console errors on startup
3. `http://localhost:3000` loads the dark terminal layout with sidebar
4. All 4 nav links navigate without 404 (Dashboard, Profiles, Trade History, System Status)
5. Active nav item is highlighted in gold
6. API proxy: `http://localhost:3000/api/system/health` returns `{"status":"ok",...}`
7. All 15 source files exist (verified by check above)

## FAILURE GUIDE

- **TypeScript errors on build**: Read the error — it will name the file and line. Most common cause is a missing import or wrong type name. Check `types/api.ts` matches the field name the component tries to use.
- **Port 3000 already in use**: `kill $(lsof -ti:3000)` then retry.
- **API proxy 502**: Backend is not running at port 8000. Start it with `cd options-bot && python main.py` in a separate terminal before testing the proxy.
- **Tailwind classes not applying**: Confirm `tailwind.config.js` `content` paths include `./src/**/*.{js,ts,jsx,tsx}` and `index.css` has the three `@tailwind` directives.
- **`lucide-react` import error**: Run `npm install lucide-react` again in the `ui/` directory.

## DO NOT

- Do NOT modify any file outside `options-bot/ui/`
- Do NOT change `backend/app.py` CORS config
- Do NOT add dependencies not listed in Step 2
- Do NOT build any page content yet — placeholders only in this prompt
- Do NOT use `http://localhost:8000` in API client calls — use the proxy (`BASE = ''`)
