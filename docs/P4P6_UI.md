# PHASE 4 PROMPT 6 — UI: Feature Importance, Model Type Selector, Config Overrides, Backtest Panel

## CONTEXT

This prompt closes the four UI gaps documented in `PHASE3_COMPLETION_REPORT.md`:

1. **Feature importance not displayed** — `GET /api/models/{id}/importance` now exists (P4P5). Add a horizontal bar chart panel to ProfileDetail below Model Health.
2. **Model type selector** — Train Model now routes to xgboost/tft/ensemble. The "Train Model" button needs a dropdown to pick type before triggering.
3. **Config overrides not in UI** — `ProfileForm` only exposes name/preset/symbols. Add a collapsible "Advanced" section with sliders/inputs for the 5 numeric risk params.
4. **Backtest UI not built** — Backend endpoints exist. Add a backtest panel on ProfileDetail.

## FILES TO MODIFY — FOUR TARGETED CHANGES

1. `ui/src/types/api.ts` — add `feature_importance` to `ModelMetrics`, add `FeatureImportanceResponse` type
2. `ui/src/api/client.ts` — add `models.importance()`, update `models.train()` to accept optional `model_type`
3. `ui/src/pages/ProfileDetail.tsx` — add feature importance panel, model type selector on train button, backtest panel
4. `ui/src/components/ProfileForm.tsx` — add collapsible Advanced config overrides section

---

## READ FIRST

```bash
cd options-bot/ui

# Read all four files in full before writing any code
cat src/types/api.ts
cat src/api/client.ts
cat src/pages/ProfileDetail.tsx
cat src/components/ProfileForm.tsx

# Understand what config keys are available from preset defaults
python3 -c "
import sys; sys.path.insert(0, '..')
from config import PRESET_DEFAULTS
for k,v in PRESET_DEFAULTS['swing'].items():
    print(f'  {k}: {v}')
"
```

---

## FILE 1 CHANGES: `ui/src/types/api.ts`

### Change 1a — Add `feature_importance` to `ModelMetrics`

Find `interface ModelMetrics` and add one field after `cv_folds`:

```typescript
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
  feature_importance: Record<string, number> | null;  // ADD THIS
}
```

### Change 1b — Add `FeatureImportanceResponse` type

Add this new interface AFTER `ModelMetrics`:

```typescript
export interface FeatureImportanceResponse {
  model_id: string;
  model_type: string;
  feature_importance: Record<string, number>;
}
```

---

## FILE 2 CHANGES: `ui/src/api/client.ts`

### Change 2a — Add `models.importance()` and update `models.train()`

In the `models:` block of the `api` object, make two changes:

1. Update `train` to accept an optional `model_type` parameter:
```typescript
    train: (profileId: string, modelType?: string) =>
      request<TrainingStatus>(`/api/models/${profileId}/train`, {
        method: 'POST',
        body: JSON.stringify({ model_type: modelType ?? 'xgboost' }),
      }),
```

2. Add `importance` after `logs`:
```typescript
    importance: (profileId: string) =>
      request<FeatureImportanceResponse>(`/api/models/${profileId}/importance`),
```

3. Add the `FeatureImportanceResponse` import — update the import line at the top of the file:
```typescript
import type {
  Profile, ProfileCreate, ProfileUpdate,
  TrainingStatus, ModelMetrics, TrainingLogEntry,
  Trade, TradeStats,
  SystemStatus, HealthCheck, PDTStatus, ErrorLogEntry,
  BacktestRequest, BacktestResult,
  FeatureImportanceResponse,   // ADD THIS
} from '../types/api';
```

---

## FILE 3 CHANGES: `ui/src/pages/ProfileDetail.tsx`

This file has the most changes. Read the complete file first. Then make the following additions:

### Change 3a — New state variables

In the `ProfileDetail` function body, find the existing state declarations:
```typescript
  const [showEdit, setShowEdit] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
```

Add:
```typescript
  const [showEdit, setShowEdit] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [trainModelType, setTrainModelType] = useState<string>('xgboost');
  const [showModelTypeMenu, setShowModelTypeMenu] = useState(false);
  const [showBacktest, setShowBacktest] = useState(false);
  const [backtestStart, setBacktestStart] = useState('');
  const [backtestEnd, setBacktestEnd] = useState('');
```

### Change 3b — New queries

After the existing queries (after `stats` query), add:

```typescript
  const { data: importance } = useQuery({
    queryKey: ['model-importance', id],
    queryFn: () => api.models.importance(id!),
    enabled: !!id && !!profile?.model_summary,
    staleTime: 60_000,  // importance doesn't change unless model retrained
  });

  const { data: backtestResult, refetch: refetchBacktest } = useQuery({
    queryKey: ['backtest-result', id],
    queryFn: () => api.backtest.results(id!),
    enabled: !!id,
    refetchInterval: showBacktest ? 5_000 : false,
  });
```

### Change 3c — Update `trainMutation`

Find the existing `trainMutation`:
```typescript
  const trainMutation = useMutation({
    mutationFn: () => api.models.train(id!),
```

Replace with:
```typescript
  const trainMutation = useMutation({
    mutationFn: () => api.models.train(id!, trainModelType),
```

### Change 3d — Add backtest mutation

After `pauseMutation`, add:
```typescript
  const backtestMutation = useMutation({
    mutationFn: () => api.backtest.run(id!, {
      start_date: backtestStart,
      end_date: backtestEnd,
    }),
    onSuccess: () => {
      refetchBacktest();
    },
  });
```

### Change 3e — Add `FeatureImportancePanel` sub-component

Add this component function BEFORE the `ProfileDetail` function (alongside `MetricTile` and `TrainingLogs`):

```tsx
// ─────────────────────────────────────────────
// Feature importance panel
// ─────────────────────────────────────────────

function FeatureImportancePanel({ importance }: { importance: Record<string, number> }) {
  const entries = Object.entries(importance)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 15);  // top 15

  if (entries.length === 0) {
    return <p className="text-xs text-muted py-2">No importance data available.</p>;
  }

  const maxVal = entries[0][1];

  return (
    <div className="space-y-1.5">
      {entries.map(([feature, score]) => {
        const pct = maxVal > 0 ? (score / maxVal) * 100 : 0;
        return (
          <div key={feature} className="flex items-center gap-2">
            <div className="w-32 flex-shrink-0 text-2xs text-muted font-mono truncate" title={feature}>
              {feature}
            </div>
            <div className="flex-1 bg-panel rounded-full h-1.5 overflow-hidden">
              <div
                className="h-full bg-gold/60 rounded-full transition-all duration-300"
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="w-12 text-right text-2xs num text-muted">
              {(score * 100).toFixed(2)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

### Change 3f — Add model type selector to Train Model button

Find the "Train Model" button in the JSX. It currently looks like:
```tsx
              {canTrain && (
                <button
                  onClick={() => trainMutation.mutate()}
                  ...
                >
                  ...Train Model
                </button>
              )}
```

Replace the entire `{canTrain && (...)}` block with:
```tsx
              {canTrain && (
                <div className="relative flex items-center">
                  <button
                    onClick={() => trainMutation.mutate()}
                    disabled={isTraining || trainMutation.isPending}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-l text-2xs font-medium
                               bg-gold/10 text-gold border border-gold/30 border-r-0
                               hover:bg-gold/20 disabled:opacity-50 transition-colors"
                  >
                    {(isTraining || trainMutation.isPending) ? <Spinner size="sm" /> : <BrainCircuit size={11} />}
                    {isTraining ? 'Training…' : `Train ${trainModelType.toUpperCase()}`}
                  </button>
                  <button
                    onClick={() => setShowModelTypeMenu(v => !v)}
                    disabled={isTraining || trainMutation.isPending}
                    className="flex items-center px-1.5 py-1 rounded-r text-2xs font-medium
                               bg-gold/10 text-gold border border-gold/30
                               hover:bg-gold/20 disabled:opacity-50 transition-colors"
                    title="Select model type"
                  >
                    <ChevronDown size={10} />
                  </button>
                  {showModelTypeMenu && (
                    <div className="absolute right-0 top-full mt-1 z-10 bg-surface border border-border
                                    rounded shadow-lg py-1 min-w-28">
                      {(['xgboost', 'tft', 'ensemble'] as const).map(type => (
                        <button
                          key={type}
                          onClick={() => { setTrainModelType(type); setShowModelTypeMenu(false); }}
                          className={`w-full text-left px-3 py-1.5 text-2xs font-mono transition-colors
                            ${trainModelType === type
                              ? 'text-gold bg-gold/10'
                              : 'text-muted hover:text-text hover:bg-panel'}`}
                        >
                          {type}
                          {type === 'ensemble' && (
                            <span className="ml-1 text-muted/50">(needs xgb+tft)</span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
```

Add `ChevronDown` to the lucide-react import at the top of the file.

### Change 3g — Add feature importance panel (below the Model Health card's metric tiles)

In the Model Health card, find the closing of the metric tiles section:
```tsx
              <div className="flex items-center gap-3 text-2xs text-muted">
                <span className="font-mono">{model.model_type}</span>
                ...
              </div>
```

After that line (still inside the `model ? (...)` branch), add:

```tsx
              {/* Feature importance */}
              {importance?.feature_importance && Object.keys(importance.feature_importance).length > 0 && (
                <details className="mt-3">
                  <summary className="text-2xs text-muted cursor-pointer hover:text-text transition-colors select-none">
                    Feature Importance (top 15)
                  </summary>
                  <div className="mt-2">
                    <FeatureImportancePanel importance={importance.feature_importance} />
                  </div>
                </details>
              )}
```

### Change 3h — Add backtest panel

After the entire "Model health" card (the closing `</div>` of the model health card, which is inside the 2-column grid), add a new full-width backtest section BELOW the grid:

```tsx
      {/* Backtest panel */}
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <BarChart3 size={15} className="text-muted" />
            <span className="text-xs font-medium text-text">Backtest</span>
            {backtestResult?.status === 'completed' && (
              <span className="text-2xs text-muted">
                · {backtestResult.start_date} → {backtestResult.end_date}
              </span>
            )}
          </div>
          <button
            onClick={() => setShowBacktest(v => !v)}
            className="text-2xs text-muted hover:text-gold transition-colors"
          >
            {showBacktest ? 'Collapse' : 'Run Backtest'}
          </button>
        </div>

        {/* Backtest results summary (always visible if completed) */}
        {backtestResult && backtestResult.status === 'completed' && (
          <div className="grid grid-cols-4 gap-2 mb-3">
            <MetricTile
              label="Total Return"
              value={backtestResult.total_return_pct != null
                ? `${backtestResult.total_return_pct.toFixed(1)}%` : '—'}
              good={backtestResult.total_return_pct != null
                ? backtestResult.total_return_pct > 0 : undefined}
            />
            <MetricTile
              label="Sharpe Ratio"
              value={backtestResult.sharpe_ratio != null
                ? backtestResult.sharpe_ratio.toFixed(2) : '—'}
              good={backtestResult.sharpe_ratio != null
                ? backtestResult.sharpe_ratio > 0.8 : undefined}
            />
            <MetricTile
              label="Max Drawdown"
              value={backtestResult.max_drawdown_pct != null
                ? `${backtestResult.max_drawdown_pct.toFixed(1)}%` : '—'}
              good={backtestResult.max_drawdown_pct != null
                ? backtestResult.max_drawdown_pct > -25 : undefined}
            />
            <MetricTile
              label="Trades"
              value={backtestResult.total_trades != null
                ? String(backtestResult.total_trades) : '—'}
            />
          </div>
        )}

        {backtestResult?.status === 'running' && (
          <div className="flex items-center gap-2 text-2xs text-muted mb-3">
            <Spinner size="sm" />
            <span>Backtest running… this may take several minutes.</span>
          </div>
        )}

        {backtestResult?.status === 'failed' && (
          <p className="text-2xs text-loss mb-3">{backtestResult.message}</p>
        )}

        {/* Run panel */}
        {showBacktest && (
          <div className="border-t border-border pt-3 mt-1">
            <div className="flex items-end gap-3">
              <div>
                <label className="block text-2xs text-muted mb-1">Start Date</label>
                <input
                  type="date"
                  value={backtestStart}
                  onChange={e => setBacktestStart(e.target.value)}
                  className="bg-panel border border-border rounded px-2 py-1 text-xs text-text
                             focus:outline-none focus:border-gold/50 transition-colors"
                />
              </div>
              <div>
                <label className="block text-2xs text-muted mb-1">End Date</label>
                <input
                  type="date"
                  value={backtestEnd}
                  onChange={e => setBacktestEnd(e.target.value)}
                  className="bg-panel border border-border rounded px-2 py-1 text-xs text-text
                             focus:outline-none focus:border-gold/50 transition-colors"
                />
              </div>
              <button
                onClick={() => backtestMutation.mutate()}
                disabled={!backtestStart || !backtestEnd || backtestMutation.isPending
                          || backtestResult?.status === 'running'}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                           bg-gold/10 text-gold border border-gold/30
                           hover:bg-gold/20 disabled:opacity-50 transition-colors"
              >
                {backtestMutation.isPending ? <Spinner size="sm" /> : <BarChart3 size={11} />}
                Run
              </button>
            </div>
            <p className="text-2xs text-muted mt-2">
              Requires Theta Terminal running. Backtests trade stock (not options) to validate directional accuracy.
            </p>
          </div>
        )}

        {!backtestResult || backtestResult.status === 'not_run' ? (
          <p className="text-2xs text-muted">No backtest run yet. Click "Run Backtest" to start.</p>
        ) : null}
      </div>
```

---

## FILE 4 CHANGES: `ui/src/components/ProfileForm.tsx`

### Change 4a — Add config state

In `ProfileForm`, find the existing state declarations. After `setSymbols`, add:

```typescript
  // Config overrides — numeric risk params
  const [maxPositionPct, setMaxPositionPct] = useState<number>(
    (profile?.config?.max_position_pct as number) ?? 20
  );
  const [maxContracts, setMaxContracts] = useState<number>(
    (profile?.config?.max_contracts as number) ?? 5
  );
  const [maxConcurrent, setMaxConcurrent] = useState<number>(
    (profile?.config?.max_concurrent_positions as number) ?? 3
  );
  const [maxDailyTrades, setMaxDailyTrades] = useState<number>(
    (profile?.config?.max_daily_trades as number) ?? 5
  );
  const [maxDailyLossPct, setMaxDailyLossPct] = useState<number>(
    (profile?.config?.max_daily_loss_pct as number) ?? 10
  );
  const [showAdvanced, setShowAdvanced] = useState(false);
```

### Change 4b — Include config_overrides in form submission

Find the `createMutation` and `updateMutation` calls. In `createMutation`, find where it calls `api.profiles.create`:

```typescript
  const createMutation = useMutation({
    mutationFn: () => api.profiles.create({
      name: name.trim(),
      preset,
      symbols,
    }),
```

Update to include `config_overrides`:
```typescript
  const createMutation = useMutation({
    mutationFn: () => api.profiles.create({
      name: name.trim(),
      preset,
      symbols,
      config_overrides: {
        max_position_pct: maxPositionPct,
        max_contracts: maxContracts,
        max_concurrent_positions: maxConcurrent,
        max_daily_trades: maxDailyTrades,
        max_daily_loss_pct: maxDailyLossPct,
      },
    }),
```

For `updateMutation`, find `api.profiles.update` and add `config_overrides`:
```typescript
  const updateMutation = useMutation({
    mutationFn: () => api.profiles.update(profile!.id, {
      name: name.trim(),
      symbols,
      config_overrides: {
        max_position_pct: maxPositionPct,
        max_contracts: maxContracts,
        max_concurrent_positions: maxConcurrent,
        max_daily_trades: maxDailyTrades,
        max_daily_loss_pct: maxDailyLossPct,
      },
    }),
```

### Change 4c — Add Advanced section to the form JSX

In the form JSX, after the symbols section (and before the submit button), add:

```tsx
          {/* Advanced config */}
          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced(v => !v)}
              className="flex items-center gap-1 text-xs text-muted hover:text-gold transition-colors"
            >
              <span>{showAdvanced ? '▾' : '▸'}</span>
              Advanced Risk Parameters
            </button>

            {showAdvanced && (
              <div className="mt-3 space-y-3 p-3 bg-base rounded border border-border">
                <ConfigSlider
                  label="Max Position Size"
                  value={maxPositionPct}
                  onChange={setMaxPositionPct}
                  min={5} max={50} step={5}
                  unit="%"
                  hint="Portfolio % per trade"
                />
                <ConfigSlider
                  label="Max Contracts"
                  value={maxContracts}
                  onChange={setMaxContracts}
                  min={1} max={20} step={1}
                  unit=""
                  hint="Contracts per position"
                />
                <ConfigSlider
                  label="Max Concurrent Positions"
                  value={maxConcurrent}
                  onChange={setMaxConcurrent}
                  min={1} max={10} step={1}
                  unit=""
                  hint="Open positions at once"
                />
                <ConfigSlider
                  label="Max Daily Trades"
                  value={maxDailyTrades}
                  onChange={setMaxDailyTrades}
                  min={1} max={20} step={1}
                  unit=""
                  hint="New entries per day"
                />
                <ConfigSlider
                  label="Max Daily Loss"
                  value={maxDailyLossPct}
                  onChange={setMaxDailyLossPct}
                  min={1} max={30} step={1}
                  unit="%"
                  hint="Daily P&L floor before pause"
                />
              </div>
            )}
          </div>
```

### Change 4d — Add `ConfigSlider` sub-component

Add this helper component at the TOP of `ProfileForm.tsx`, BEFORE the `ProfileForm` function:

```tsx
function ConfigSlider({
  label, value, onChange, min, max, step, unit, hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number; max: number; step: number;
  unit: string;
  hint: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-2xs text-muted">{label}</span>
        <span className="num text-2xs text-text font-medium">
          {value}{unit}
        </span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full h-1 bg-border rounded-full appearance-none cursor-pointer
                   [&::-webkit-slider-thumb]:appearance-none
                   [&::-webkit-slider-thumb]:w-3
                   [&::-webkit-slider-thumb]:h-3
                   [&::-webkit-slider-thumb]:rounded-full
                   [&::-webkit-slider-thumb]:bg-gold
                   [&::-webkit-slider-thumb]:cursor-pointer"
      />
      <p className="text-2xs text-muted/60 mt-0.5">{hint}</p>
    </div>
  );
}
```

---

## VERIFICATION

```bash
cd options-bot/ui

# 1. TypeScript compiles without errors
echo "=== TypeScript compile check ==="
npx tsc --noEmit 2>&1 | head -30
echo "Exit code: $?"

# 2. Check FeatureImportanceResponse is in types
echo ""
echo "=== FeatureImportanceResponse type exists ==="
grep -n "FeatureImportanceResponse" src/types/api.ts
grep -n "FeatureImportanceResponse" src/api/client.ts

# 3. Check feature_importance field added to ModelMetrics type
echo ""
echo "=== feature_importance in ModelMetrics ==="
grep -n "feature_importance" src/types/api.ts

# 4. Check api.models.importance exists
echo ""
echo "=== api.models.importance() ==="
grep -n "importance" src/api/client.ts

# 5. Check models.train() accepts modelType parameter
echo ""
echo "=== api.models.train() signature ==="
grep -A3 "train:" src/api/client.ts | head -10

# 6. Check ProfileDetail has new features
echo ""
echo "=== ProfileDetail new features ==="
grep -n "trainModelType\|showModelTypeMenu\|backtestStart\|FeatureImportancePanel\|ChevronDown" src/pages/ProfileDetail.tsx

# 7. Check ProfileForm has config state
echo ""
echo "=== ProfileForm config state ==="
grep -n "maxPositionPct\|showAdvanced\|ConfigSlider" src/components/ProfileForm.tsx

# 8. Build check (catches runtime issues TypeScript misses)
echo ""
echo "=== Build check ==="
npm run build 2>&1 | tail -20
```

---

## SUCCESS CRITERIA

- `npx tsc --noEmit` exits 0 — zero TypeScript errors
- `npm run build` succeeds — no bundler errors
- `FeatureImportanceResponse` interface exists in `types/api.ts`
- `ModelMetrics.feature_importance` field exists as `Record<string, number> | null`
- `api.models.importance(profileId)` function exists in `client.ts`
- `api.models.train(profileId, modelType?)` accepts optional second argument
- `ProfileDetail` has state vars `trainModelType`, `showModelTypeMenu`, `backtestStart`, `backtestEnd`
- `ProfileDetail` imports `ChevronDown` from lucide-react
- `FeatureImportancePanel` component exists and renders horizontal bars
- Backtest panel renders with date inputs and Run button
- `ProfileForm` has `ConfigSlider` component and `showAdvanced` toggle state
- `config_overrides` included in both `createMutation` and `updateMutation` calls

## FAILURE GUIDE

- **`Property 'importance' does not exist on type`**: The `api.models` object needs the `importance` method. Check that it was added inside the `models:` block (not at the top level of `api`).
- **`ChevronDown` not found**: Confirm it's added to the lucide-react import line at the top of `ProfileDetail.tsx`. Common miss — the import line is at the top of the file and easy to overlook when making changes in the middle.
- **Backtest `api.backtest` not found**: Check `client.ts` — `api.backtest` already exists from Phase 3 (it has `run` and `results`). If missing, the Phase 3 work was incomplete. Add it: `backtest: { run: (id, body) => request(...), results: (id) => request(...) }`.
- **`profile?.config?.max_position_pct` type error**: The `config` field is typed as `Record<string, unknown>`. Cast explicitly: `(profile?.config?.max_position_pct as number) ?? 20`. This is already in the prompt but verify the cast is present.
- **Slider thumb not styled**: The `[&::-webkit-slider-thumb]` classes require Tailwind's JIT mode which is the default in Vite + Tailwind v3. If the slider appears unstyled, add a fallback `accent-gold` class to the range input element.
- **`<details>` / `<summary>` feature importance collapsed by default**: This is intentional — feature importance is secondary info. The `<details>` element is collapsed by default. Add `open` attribute if you want it expanded by default.

## DO NOT

- Do NOT add a new page for backtest — it belongs as a panel on ProfileDetail per the architecture
- Do NOT add the importance fetch to the Dashboard page — it's profile-specific
- Do NOT change the train button's existing XGBoost behavior — model type defaults to `'xgboost'` so existing users see no change until they open the dropdown
- Do NOT remove the existing "Update Model" (incremental retrain) button — it stays unchanged
- Do NOT add WebSocket or SSE — polling is already used throughout the UI and is sufficient
- Do NOT modify `App.tsx` or any other files — only the four listed files change
- Do NOT style the range input with arbitrary Tailwind values — the `[&::-webkit-slider-thumb]` pseudo-element selectors shown are valid Tailwind v3 JIT syntax
