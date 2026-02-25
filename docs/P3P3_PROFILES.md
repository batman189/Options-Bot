# PHASE 3 PROMPT 3 — Profiles Page (List, Create, Edit, Delete, Activate/Pause)

## TASK
Replace the placeholder `Profiles.tsx` with a fully functional profiles management page.
This is where the user creates profiles, trains models, and controls which profiles are active.

**Files to create or modify:**
1. `options-bot/ui/src/pages/Profiles.tsx` — main page (replace placeholder)
2. `options-bot/ui/src/components/ProfileForm.tsx` — create/edit form (new file)
3. `options-bot/ui/src/pages/ProfileDetail.tsx` — profile detail page (new file)

**Update routing in `App.tsx`** — wire `ProfileDetail` to `/profiles/:id`.

---

## READ FIRST

```bash
cd options-bot/ui
cat src/types/api.ts
cat src/api/client.ts
cat src/components/StatusBadge.tsx
cat src/components/PageHeader.tsx
cat src/components/Spinner.tsx
cat src/App.tsx
```

---

## FILE 1: `options-bot/ui/src/components/ProfileForm.tsx`

This is a modal form used for both Create and Edit. It is self-contained — receives
callbacks, manages its own local state, calls the API itself via mutations.

```tsx
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, Plus, Minus } from 'lucide-react';
import { api } from '../api/client';
import { Spinner } from './Spinner';
import type { Profile } from '../types/api';

interface Props {
  /** Pass existing profile to edit. Omit for create. */
  profile?: Profile;
  onClose: () => void;
}

const PRESETS = ['swing', 'general'] as const;

const PRESET_DESCRIPTIONS: Record<string, string> = {
  swing:   'Mean-reversion options trades. 7–45 DTE. Hold up to 7 days.',
  general: 'Trend-following options trades. 21–60 DTE. Hold up to 21 days.',
};

export function ProfileForm({ profile, onClose }: Props) {
  const qc = useQueryClient();
  const isEdit = !!profile;

  const [name, setName] = useState(profile?.name ?? '');
  const [preset, setPreset] = useState<string>(profile?.preset ?? 'swing');
  const [symbols, setSymbols] = useState<string[]>(profile?.symbols ?? ['TSLA']);
  const [symbolInput, setSymbolInput] = useState('');
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () => api.profiles.create({ name, preset, symbols }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profiles'] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const updateMutation = useMutation({
    mutationFn: () => api.profiles.update(profile!.id, { name, symbols }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profiles'] });
      qc.invalidateQueries({ queryKey: ['profile', profile!.id] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  function addSymbol() {
    const sym = symbolInput.trim().toUpperCase();
    if (!sym) return;
    if (symbols.includes(sym)) { setSymbolInput(''); return; }
    setSymbols([...symbols, sym]);
    setSymbolInput('');
  }

  function removeSymbol(sym: string) {
    if (symbols.length <= 1) return; // must have at least 1
    setSymbols(symbols.filter(s => s !== sym));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) { setError('Name is required.'); return; }
    if (symbols.length === 0) { setError('At least one symbol is required.'); return; }
    if (isEdit) updateMutation.mutate();
    else createMutation.mutate();
  }

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-md bg-surface border border-border rounded-xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-sm font-semibold text-text">
            {isEdit ? 'Edit Profile' : 'New Profile'}
          </h2>
          <button onClick={onClose} className="text-muted hover:text-text transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4">
          {/* Name */}
          <div>
            <label className="block text-xs text-muted mb-1.5">Profile Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. TSLA Swing"
              className="w-full bg-panel border border-border rounded px-3 py-2 text-sm text-text
                         placeholder:text-muted focus:outline-none focus:border-gold/50 transition-colors"
            />
          </div>

          {/* Preset — only on create */}
          {!isEdit && (
            <div>
              <label className="block text-xs text-muted mb-1.5">Strategy Preset</label>
              <div className="grid grid-cols-2 gap-2">
                {PRESETS.map(p => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPreset(p)}
                    className={`text-left px-3 py-2.5 rounded border transition-colors
                      ${preset === p
                        ? 'border-gold/40 bg-gold/5 text-text'
                        : 'border-border bg-panel text-muted hover:border-border/60'}`}
                  >
                    <div className="text-xs font-medium capitalize mb-0.5">{p}</div>
                    <div className="text-2xs text-muted leading-relaxed">
                      {PRESET_DESCRIPTIONS[p]}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Symbols */}
          <div>
            <label className="block text-xs text-muted mb-1.5">Symbols</label>
            <div className="flex flex-wrap gap-1.5 mb-2 min-h-[28px]">
              {symbols.map(sym => (
                <span key={sym} className="inline-flex items-center gap-1 font-mono text-xs
                                           bg-gold/5 border border-gold/20 text-gold
                                           px-2 py-0.5 rounded">
                  {sym}
                  <button
                    type="button"
                    onClick={() => removeSymbol(sym)}
                    className="text-gold/50 hover:text-loss transition-colors ml-0.5"
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={symbolInput}
                onChange={e => setSymbolInput(e.target.value.toUpperCase())}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSymbol(); } }}
                placeholder="e.g. NVDA"
                maxLength={5}
                className="flex-1 bg-panel border border-border rounded px-3 py-1.5 text-sm
                           text-text font-mono placeholder:text-muted
                           focus:outline-none focus:border-gold/50 transition-colors uppercase"
              />
              <button
                type="button"
                onClick={addSymbol}
                className="px-3 py-1.5 rounded border border-border bg-panel text-muted
                           hover:text-text hover:border-border/60 transition-colors"
              >
                <Plus size={14} />
              </button>
            </div>
            <p className="text-2xs text-muted mt-1">Press Enter or + to add. Minimum 1 symbol.</p>
          </div>

          {/* Error */}
          {error && (
            <div className="rounded border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded text-xs text-muted border border-border
                         hover:text-text hover:border-border/60 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="flex items-center gap-2 px-4 py-2 rounded text-xs font-medium
                         bg-gold/10 text-gold border border-gold/30
                         hover:bg-gold/20 disabled:opacity-50 transition-colors"
            >
              {isPending && <Spinner size="sm" />}
              {isEdit ? 'Save Changes' : 'Create Profile'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

---

## FILE 2: `options-bot/ui/src/pages/Profiles.tsx`

Full profiles list with create button, per-profile actions (activate, pause, edit, delete).

```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Plus, Play, Pause, Pencil, Trash2, ChevronRight,
  AlertTriangle, BrainCircuit,
} from 'lucide-react';
import { api } from '../api/client';
import { PageHeader } from '../components/PageHeader';
import { StatusBadge } from '../components/StatusBadge';
import { Spinner } from '../components/Spinner';
import { PnlCell } from '../components/PnlCell';
import { ProfileForm } from '../components/ProfileForm';
import type { Profile } from '../types/api';

// ─────────────────────────────────────────────
// Confirm delete dialog
// ─────────────────────────────────────────────

interface DeleteDialogProps {
  profile: Profile;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}

function DeleteDialog({ profile, onConfirm, onCancel, isPending }: DeleteDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-sm bg-surface border border-border rounded-xl shadow-2xl p-5">
        <div className="flex items-start gap-3 mb-4">
          <div className="h-8 w-8 rounded-full bg-loss/10 border border-loss/20 flex items-center justify-center flex-shrink-0">
            <AlertTriangle size={15} className="text-loss" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text">Delete Profile</h3>
            <p className="text-xs text-muted mt-1 leading-relaxed">
              Delete <span className="text-text font-medium">{profile.name}</span>?
              This removes all trade history, the trained model file, and all associated data.
              This cannot be undone.
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 rounded text-xs text-muted border border-border
                       hover:text-text transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                       bg-loss/10 text-loss border border-loss/30
                       hover:bg-loss/20 disabled:opacity-50 transition-colors"
          >
            {isPending && <Spinner size="sm" />}
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Profile row
// ─────────────────────────────────────────────

interface ProfileRowProps {
  profile: Profile;
  onEdit: (p: Profile) => void;
  onDelete: (p: Profile) => void;
  onActivate: (id: string) => void;
  onPause: (id: string) => void;
  onTrain: (id: string) => void;
  mutatingId: string | null;
}

function ProfileRow({
  profile, onEdit, onDelete, onActivate, onPause, onTrain, mutatingId,
}: ProfileRowProps) {
  const navigate = useNavigate();
  const isMutating = mutatingId === profile.id;
  const canActivate = profile.status === 'ready' || profile.status === 'paused';
  const canPause = profile.status === 'active';
  const canTrain = profile.status === 'created' || profile.status === 'ready' || profile.status === 'error';
  const modelAge = profile.model_summary?.age_days;
  const dirAcc = profile.model_summary?.metrics?.dir_acc;

  return (
    <tr className="border-b border-border hover:bg-surface/50 transition-colors group">
      {/* Name + preset */}
      <td className="px-4 py-3">
        <button
          onClick={() => navigate(`/profiles/${profile.id}`)}
          className="text-sm font-medium text-text hover:text-gold transition-colors"
        >
          {profile.name}
        </button>
        <div className="text-2xs text-muted font-mono uppercase tracking-wider mt-0.5">
          {profile.preset}
        </div>
      </td>

      {/* Status */}
      <td className="px-4 py-3">
        <StatusBadge status={profile.status} />
      </td>

      {/* Symbols */}
      <td className="px-4 py-3">
        <div className="flex flex-wrap gap-1">
          {profile.symbols.map(s => (
            <span key={s} className="font-mono text-xs bg-gold/5 border border-gold/15 text-gold px-1.5 py-0.5 rounded">
              {s}
            </span>
          ))}
        </div>
      </td>

      {/* Model health */}
      <td className="px-4 py-3">
        {profile.model_summary ? (
          <div>
            <span className={`num text-xs ${
              dirAcc !== undefined && dirAcc >= 0.52 ? 'text-profit' : 'text-muted'
            }`}>
              {dirAcc !== undefined ? `${(dirAcc * 100).toFixed(1)}% acc` : '—'}
            </span>
            <div className="text-2xs text-muted font-mono">
              {modelAge !== undefined ? `${modelAge}d old` : ''}
              {' · '}{profile.model_summary.model_type}
            </div>
          </div>
        ) : (
          <span className="text-xs text-muted">No model</span>
        )}
      </td>

      {/* P&L */}
      <td className="px-4 py-3">
        <PnlCell value={profile.total_pnl} suffix=" USD" />
        <div className="text-2xs text-muted mt-0.5">
          {profile.active_positions} open
        </div>
      </td>

      {/* Actions */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {/* Activate */}
          {canActivate && (
            <button
              title="Activate"
              onClick={() => onActivate(profile.id)}
              disabled={isMutating}
              className="p-1.5 rounded hover:bg-active/10 text-muted hover:text-active
                         border border-transparent hover:border-active/20 transition-colors"
            >
              {isMutating ? <Spinner size="sm" /> : <Play size={13} />}
            </button>
          )}

          {/* Pause */}
          {canPause && (
            <button
              title="Pause"
              onClick={() => onPause(profile.id)}
              disabled={isMutating}
              className="p-1.5 rounded hover:bg-panel text-muted hover:text-text
                         border border-transparent hover:border-border transition-colors"
            >
              {isMutating ? <Spinner size="sm" /> : <Pause size={13} />}
            </button>
          )}

          {/* Train */}
          {canTrain && (
            <button
              title="Train model"
              onClick={() => onTrain(profile.id)}
              disabled={isMutating}
              className="p-1.5 rounded hover:bg-gold/5 text-muted hover:text-gold
                         border border-transparent hover:border-gold/20 transition-colors"
            >
              <BrainCircuit size={13} />
            </button>
          )}

          {/* Edit */}
          <button
            title="Edit"
            onClick={() => onEdit(profile)}
            className="p-1.5 rounded hover:bg-panel text-muted hover:text-text
                       border border-transparent hover:border-border transition-colors"
          >
            <Pencil size={13} />
          </button>

          {/* Detail */}
          <button
            title="Detail"
            onClick={() => navigate(`/profiles/${profile.id}`)}
            className="p-1.5 rounded hover:bg-panel text-muted hover:text-text
                       border border-transparent hover:border-border transition-colors"
          >
            <ChevronRight size={13} />
          </button>

          {/* Delete */}
          <button
            title="Delete"
            onClick={() => onDelete(profile)}
            className="p-1.5 rounded hover:bg-loss/10 text-muted hover:text-loss
                       border border-transparent hover:border-loss/20 transition-colors"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </td>
    </tr>
  );
}

// ─────────────────────────────────────────────
// Main Profiles page
// ─────────────────────────────────────────────

export function Profiles() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editProfile, setEditProfile] = useState<Profile | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Profile | null>(null);
  const [mutatingId, setMutatingId] = useState<string | null>(null);

  const { data: profiles, isLoading } = useQuery({
    queryKey: ['profiles'],
    queryFn: api.profiles.list,
    refetchInterval: 15_000,
  });

  const activateMutation = useMutation({
    mutationFn: (id: string) => { setMutatingId(id); return api.profiles.activate(id); },
    onSettled: () => { setMutatingId(null); qc.invalidateQueries({ queryKey: ['profiles'] }); },
  });

  const pauseMutation = useMutation({
    mutationFn: (id: string) => { setMutatingId(id); return api.profiles.pause(id); },
    onSettled: () => { setMutatingId(null); qc.invalidateQueries({ queryKey: ['profiles'] }); },
  });

  const trainMutation = useMutation({
    mutationFn: (id: string) => { setMutatingId(id); return api.models.train(id); },
    onSettled: () => { setMutatingId(null); qc.invalidateQueries({ queryKey: ['profiles'] }); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.profiles.delete(id),
    onSuccess: () => {
      setDeleteTarget(null);
      qc.invalidateQueries({ queryKey: ['profiles'] });
    },
  });

  return (
    <div>
      <PageHeader
        title="Profiles"
        subtitle="Create and manage trading profiles"
        actions={
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                       bg-gold/10 text-gold border border-gold/30
                       hover:bg-gold/20 transition-colors"
          >
            <Plus size={13} />
            New Profile
          </button>
        }
      />

      {/* Table */}
      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        {isLoading && !profiles ? (
          <div className="flex items-center justify-center h-32">
            <Spinner size="lg" />
          </div>
        ) : !profiles || profiles.length === 0 ? (
          <div className="py-16 text-center">
            <BrainCircuit size={28} className="text-muted mx-auto mb-3" />
            <p className="text-sm text-muted">No profiles yet.</p>
            <p className="text-xs text-muted mt-1 mb-4">
              Create a profile, train a model, then activate it to start trading.
            </p>
            <button
              onClick={() => setShowCreate(true)}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded text-xs font-medium
                         bg-gold/10 text-gold border border-gold/30 hover:bg-gold/20 transition-colors"
            >
              <Plus size={13} />
              Create First Profile
            </button>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                {['Name', 'Status', 'Symbols', 'Model', 'P&L', ''].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-2xs font-medium
                                         text-muted uppercase tracking-wider">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {profiles.map(profile => (
                <ProfileRow
                  key={profile.id}
                  profile={profile}
                  onEdit={setEditProfile}
                  onDelete={setDeleteTarget}
                  onActivate={id => activateMutation.mutate(id)}
                  onPause={id => pauseMutation.mutate(id)}
                  onTrain={id => trainMutation.mutate(id)}
                  mutatingId={mutatingId}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Status legend */}
      {profiles && profiles.length > 0 && (
        <div className="mt-3 flex items-center gap-4 text-2xs text-muted">
          <span className="font-medium">Status:</span>
          {['created', 'training', 'ready', 'active', 'paused', 'error'].map(s => (
            <span key={s} className="flex items-center gap-1">
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${
                s === 'active' ? 'bg-active' :
                s === 'ready' ? 'bg-ready' :
                s === 'training' ? 'bg-training' :
                s === 'error' ? 'bg-error' : 'bg-muted'
              }`} />
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Modals */}
      {showCreate && <ProfileForm onClose={() => setShowCreate(false)} />}
      {editProfile && <ProfileForm profile={editProfile} onClose={() => setEditProfile(null)} />}
      {deleteTarget && (
        <DeleteDialog
          profile={deleteTarget}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
          isPending={deleteMutation.isPending}
        />
      )}
    </div>
  );
}
```

---

## FILE 3: `options-bot/ui/src/pages/ProfileDetail.tsx`

Reached via `/profiles/:id`. Shows model health, retrain controls with live log
streaming, active positions, and trade history for this profile.

```tsx
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, BrainCircuit, RefreshCw, Play, Pause,
  TrendingUp, Clock, BarChart3, AlertTriangle,
} from 'lucide-react';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { Spinner } from '../components/Spinner';
import { PnlCell } from '../components/PnlCell';
import { ProfileForm } from '../components/ProfileForm';
import type { Profile } from '../types/api';

// ─────────────────────────────────────────────
// Metric tile
// ─────────────────────────────────────────────

function MetricTile({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="bg-panel rounded border border-border px-3 py-2.5">
      <div className="text-2xs text-muted uppercase tracking-wider mb-1">{label}</div>
      <div className={`num text-sm font-semibold ${
        good === true ? 'text-profit' : good === false ? 'text-loss' : 'text-text'
      }`}>
        {value}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Training log viewer
// ─────────────────────────────────────────────

function TrainingLogs({ profileId }: { profileId: string }) {
  const { data: logs, isLoading } = useQuery({
    queryKey: ['model-logs', profileId],
    queryFn: () => api.models.logs(profileId, 100),
    refetchInterval: 3_000,
  });

  if (isLoading) return <div className="flex justify-center py-4"><Spinner /></div>;
  if (!logs || logs.length === 0) {
    return <p className="text-xs text-muted py-4 text-center">No training logs yet.</p>;
  }

  return (
    <div className="font-mono text-2xs space-y-0.5 max-h-48 overflow-y-auto">
      {[...logs].reverse().map(log => (
        <div key={log.id} className={`flex gap-3 ${
          log.level === 'error' ? 'text-loss' :
          log.level === 'warning' ? 'text-training' : 'text-muted'
        }`}>
          <span className="flex-shrink-0 text-border">
            {new Date(log.timestamp).toLocaleTimeString()}
          </span>
          <span className={`flex-shrink-0 uppercase w-12 ${
            log.level === 'error' ? 'text-loss' :
            log.level === 'warning' ? 'text-training' : 'text-muted/50'
          }`}>
            {log.level}
          </span>
          <span className="text-muted leading-relaxed">{log.message}</span>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────
// Main ProfileDetail page
// ─────────────────────────────────────────────

export function ProfileDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showEdit, setShowEdit] = useState(false);
  const [showLogs, setShowLogs] = useState(false);

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ['profile', id],
    queryFn: () => api.profiles.get(id!),
    enabled: !!id,
    refetchInterval: 10_000,
  });

  const { data: trainingStatus } = useQuery({
    queryKey: ['model-status', id],
    queryFn: () => api.models.status(id!),
    enabled: !!id,
    refetchInterval: 5_000,
  });

  const { data: trades, isLoading: tradesLoading } = useQuery({
    queryKey: ['trades', id],
    queryFn: () => api.trades.list({ profile_id: id, limit: 50 }),
    enabled: !!id,
    refetchInterval: 15_000,
  });

  const { data: stats } = useQuery({
    queryKey: ['trade-stats', id],
    queryFn: () => api.trades.stats(id),
    enabled: !!id,
    refetchInterval: 15_000,
  });

  const trainMutation = useMutation({
    mutationFn: () => api.models.train(id!),
    onSuccess: () => {
      setShowLogs(true);
      qc.invalidateQueries({ queryKey: ['profile', id] });
      qc.invalidateQueries({ queryKey: ['model-status', id] });
    },
  });

  const retrainMutation = useMutation({
    mutationFn: () => api.models.retrain(id!),
    onSuccess: () => {
      setShowLogs(true);
      qc.invalidateQueries({ queryKey: ['profile', id] });
      qc.invalidateQueries({ queryKey: ['model-status', id] });
    },
  });

  const activateMutation = useMutation({
    mutationFn: () => api.profiles.activate(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profile', id] }),
  });

  const pauseMutation = useMutation({
    mutationFn: () => api.profiles.pause(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profile', id] }),
  });

  if (profileLoading || !profile) {
    return (
      <div className="flex items-center justify-center h-48">
        <Spinner size="lg" />
      </div>
    );
  }

  const model = profile.model_summary;
  const isTraining = trainingStatus?.status === 'training' || profile.status === 'training';
  const canTrain = ['created', 'ready', 'error'].includes(profile.status);
  const canRetrain = profile.status === 'ready' || profile.status === 'active';
  const canActivate = profile.status === 'ready' || profile.status === 'paused';
  const canPause = profile.status === 'active';

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <button
          onClick={() => navigate('/profiles')}
          className="flex items-center gap-1.5 text-xs text-muted hover:text-text mb-3 transition-colors"
        >
          <ArrowLeft size={13} />
          All Profiles
        </button>

        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-semibold text-text">{profile.name}</h1>
              <StatusBadge status={profile.status} />
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-muted">
              <span className="font-mono uppercase">{profile.preset}</span>
              <span>·</span>
              <span>{profile.symbols.join(', ')}</span>
              <span>·</span>
              <span>Created {new Date(profile.created_at).toLocaleDateString()}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowEdit(true)}
              className="px-3 py-1.5 rounded text-xs border border-border text-muted
                         hover:text-text hover:border-border/60 transition-colors"
            >
              Edit
            </button>
            {canActivate && (
              <button
                onClick={() => activateMutation.mutate()}
                disabled={activateMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                           bg-active/10 text-active border border-active/20
                           hover:bg-active/20 disabled:opacity-50 transition-colors"
              >
                {activateMutation.isPending ? <Spinner size="sm" /> : <Play size={12} />}
                Activate
              </button>
            )}
            {canPause && (
              <button
                onClick={() => pauseMutation.mutate()}
                disabled={pauseMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                           bg-panel text-muted border border-border
                           hover:text-text hover:border-border/60 disabled:opacity-50 transition-colors"
              >
                {pauseMutation.isPending ? <Spinner size="sm" /> : <Pause size={12} />}
                Pause
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Grid: Model health + Trade stats */}
      <div className="grid grid-cols-2 gap-4">

        {/* Model health */}
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <BrainCircuit size={15} className="text-muted" />
              <span className="text-xs font-medium text-text">Model Health</span>
            </div>
            <div className="flex items-center gap-2">
              {canRetrain && (
                <button
                  onClick={() => retrainMutation.mutate()}
                  disabled={isTraining || retrainMutation.isPending}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded text-2xs font-medium
                             bg-gold/5 text-gold border border-gold/20
                             hover:bg-gold/10 disabled:opacity-50 transition-colors"
                >
                  {retrainMutation.isPending ? <Spinner size="sm" /> : <RefreshCw size={11} />}
                  Update Model
                </button>
              )}
              {canTrain && (
                <button
                  onClick={() => trainMutation.mutate()}
                  disabled={isTraining || trainMutation.isPending}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded text-2xs font-medium
                             bg-gold/10 text-gold border border-gold/30
                             hover:bg-gold/20 disabled:opacity-50 transition-colors"
                >
                  {(isTraining || trainMutation.isPending) ? <Spinner size="sm" /> : <BrainCircuit size={11} />}
                  {isTraining ? 'Training…' : 'Train Model'}
                </button>
              )}
            </div>
          </div>

          {model ? (
            <>
              <div className="grid grid-cols-2 gap-2 mb-3">
                <MetricTile
                  label="Directional Acc."
                  value={model.metrics.dir_acc !== undefined
                    ? `${(model.metrics.dir_acc * 100).toFixed(1)}%` : '—'}
                  good={model.metrics.dir_acc !== undefined ? model.metrics.dir_acc >= 0.52 : undefined}
                />
                <MetricTile
                  label="MAE"
                  value={model.metrics.mae !== undefined
                    ? model.metrics.mae.toFixed(4) : '—'}
                />
                <MetricTile
                  label="Model Age"
                  value={`${model.age_days} days`}
                  good={model.age_days <= 30 ? true : model.age_days <= 90 ? undefined : false}
                />
                <MetricTile
                  label="Data Range"
                  value={model.data_range}
                />
              </div>
              <div className="flex items-center gap-3 text-2xs text-muted">
                <span className="font-mono">{model.model_type}</span>
                <span>·</span>
                <span>Trained {model.trained_at
                  ? new Date(model.trained_at).toLocaleDateString() : 'unknown'}</span>
                <StatusBadge status={model.status} />
              </div>
            </>
          ) : (
            <div className="py-6 text-center">
              <p className="text-xs text-muted">No trained model.</p>
              <p className="text-2xs text-muted mt-1">
                Click <span className="text-gold">Train Model</span> to begin.
                Requires Theta Terminal running.
              </p>
            </div>
          )}

          {/* Training status */}
          {isTraining && trainingStatus && (
            <div className="mt-3 rounded border border-gold/20 bg-gold/5 px-3 py-2">
              <div className="flex items-center gap-2 mb-1">
                <Spinner size="sm" />
                <span className="text-xs text-gold font-medium">Training in progress</span>
              </div>
              {trainingStatus.message && (
                <p className="text-2xs text-muted font-mono">{trainingStatus.message}</p>
              )}
            </div>
          )}

          {/* Toggle logs */}
          <button
            onClick={() => setShowLogs(v => !v)}
            className="mt-3 text-2xs text-muted hover:text-gold transition-colors"
          >
            {showLogs ? 'Hide' : 'Show'} training logs
          </button>
          {showLogs && (
            <div className="mt-2 rounded border border-border bg-base p-2">
              <TrainingLogs profileId={id!} />
            </div>
          )}
        </div>

        {/* Trade stats */}
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 size={15} className="text-muted" />
            <span className="text-xs font-medium text-text">Trade Performance</span>
          </div>

          {stats ? (
            <div className="grid grid-cols-2 gap-2">
              <MetricTile label="Total Trades" value={String(stats.total_trades)} />
              <MetricTile
                label="Win Rate"
                value={stats.win_rate !== null ? `${(stats.win_rate * 100).toFixed(1)}%` : '—'}
                good={stats.win_rate !== null ? stats.win_rate >= 0.5 : undefined}
              />
              <MetricTile
                label="Total P&L"
                value={stats.total_pnl_dollars >= 0
                  ? `+$${stats.total_pnl_dollars.toFixed(0)}`
                  : `-$${Math.abs(stats.total_pnl_dollars).toFixed(0)}`}
                good={stats.total_pnl_dollars >= 0}
              />
              <MetricTile
                label="Avg Hold"
                value={stats.avg_hold_days !== null ? `${stats.avg_hold_days.toFixed(1)}d` : '—'}
              />
              <MetricTile
                label="Best Trade"
                value={stats.best_trade_pct !== null ? `+${stats.best_trade_pct.toFixed(1)}%` : '—'}
                good={true}
              />
              <MetricTile
                label="Worst Trade"
                value={stats.worst_trade_pct !== null ? `${stats.worst_trade_pct.toFixed(1)}%` : '—'}
                good={false}
              />
            </div>
          ) : (
            <p className="text-xs text-muted text-center py-8">No trades yet.</p>
          )}
        </div>
      </div>

      {/* Trade history table */}
      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp size={14} className="text-muted" />
            <span className="text-xs font-medium text-text">Trades</span>
            {trades && (
              <span className="text-2xs text-muted">({trades.length})</span>
            )}
          </div>
          {tradesLoading && <Spinner size="sm" />}
        </div>

        {!trades || trades.length === 0 ? (
          <div className="py-10 text-center">
            <p className="text-xs text-muted">No trades recorded for this profile.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  {['Date', 'Symbol', 'Direction', 'Strike', 'Exp', 'Qty', 'Entry', 'Exit', 'P&L', 'Reason', 'Status'].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-2xs font-medium
                                           text-muted uppercase tracking-wider whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map(trade => (
                  <tr key={trade.id} className="border-b border-border hover:bg-panel/50 transition-colors">
                    <td className="px-3 py-2 text-2xs text-muted font-mono whitespace-nowrap">
                      {trade.entry_date ? new Date(trade.entry_date).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-3 py-2 text-xs font-mono font-medium text-gold">{trade.symbol}</td>
                    <td className="px-3 py-2">
                      <span className={`text-2xs font-mono font-medium uppercase ${
                        trade.direction === 'CALL' ? 'text-profit' : 'text-loss'
                      }`}>
                        {trade.direction}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-2xs num text-text">${trade.strike}</td>
                    <td className="px-3 py-2 text-2xs font-mono text-muted">{trade.expiration}</td>
                    <td className="px-3 py-2 text-2xs num text-text">{trade.quantity}</td>
                    <td className="px-3 py-2 text-2xs num text-muted">
                      {trade.entry_price !== null ? `$${trade.entry_price.toFixed(2)}` : '—'}
                    </td>
                    <td className="px-3 py-2 text-2xs num text-muted">
                      {trade.exit_price !== null ? `$${trade.exit_price.toFixed(2)}` : '—'}
                    </td>
                    <td className="px-3 py-2">
                      <PnlCell value={trade.pnl_pct} suffix="%" />
                    </td>
                    <td className="px-3 py-2 text-2xs text-muted font-mono">
                      {trade.exit_reason ?? '—'}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={trade.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showEdit && <ProfileForm profile={profile} onClose={() => setShowEdit(false)} />}
    </div>
  );
}
```

---

## FILE 4: Update `options-bot/ui/src/App.tsx`

Add `ProfileDetail` import and wire the `/profiles/:id` route to it.

Find in `App.tsx`:
```tsx
import { Profiles } from './pages/Profiles';
```
Add below it:
```tsx
import { ProfileDetail } from './pages/ProfileDetail';
```

Find:
```tsx
            <Route path="profiles" element={<Profiles />} />
            <Route path="profiles/:id" element={<Profiles />} />
```
Replace with:
```tsx
            <Route path="profiles" element={<Profiles />} />
            <Route path="profiles/:id" element={<ProfileDetail />} />
```

---

## VERIFICATION

```bash
cd options-bot/ui

# 1. Build must be clean
echo "=== Build check ==="
npm run build 2>&1
echo "Exit code: $?"

# 2. TypeScript strict check
echo ""
echo "=== TypeScript check ==="
npx tsc --noEmit 2>&1

# 3. Source files exist
echo ""
echo "=== File check ==="
for f in \
  src/pages/Profiles.tsx \
  src/pages/ProfileDetail.tsx \
  src/components/ProfileForm.tsx; do
  [ -f "$f" ] && echo "  OK  $f" || echo "  MISSING: $f"
done
```

Then open `http://localhost:3000/profiles` in the browser with the backend running and verify:

1. Profiles table loads with all profiles from the database
2. **New Profile** button opens the create modal
3. In create modal: selecting a preset shows the description, typing a symbol and pressing Enter adds it, X removes it, Submit creates the profile and closes the modal
4. **Edit** button (hover to reveal) opens the edit modal pre-filled with name and symbols
5. **Train Model** button (on `created`/`error` profiles) triggers training and shows spinner
6. **Activate** button only appears on `ready` / `paused` profiles
7. **Pause** button only appears on `active` profiles
8. **Delete** button opens confirmation dialog; confirming calls DELETE and removes the row
9. Clicking a profile name or the `›` chevron navigates to `/profiles/:id`
10. Profile detail page shows model health tiles, train/retrain buttons, trade stats grid, and trade history table

## SUCCESS CRITERIA

- `npm run build` exits 0
- All 3 new/modified files exist
- `/profiles` loads without runtime errors
- Create → Edit → Delete round-trip all work without page refresh
- `/profiles/:id` renders model health, trade stats, and trade history
- Train button triggers `POST /api/models/{id}/train` and shows "Training…" state
- Retrain button triggers `POST /api/models/{id}/retrain`

## FAILURE GUIDE

- **"ProfileForm is not exported"**: Confirm the file is at `src/components/ProfileForm.tsx` and uses `export function ProfileForm`.
- **Modal doesn't close on backdrop click**: The backdrop `onClick` checks `e.target === e.currentTarget` — ensure no extra wrapper div is intercepting clicks.
- **Activate returns 400**: Profile is not in `ready` or `paused` status. The button only renders when `canActivate` is true — if it's showing for wrong statuses, check the status value being returned by the API matches exactly `'ready'` or `'paused'` (lowercase).
- **Delete dialog doesn't dismiss after confirm**: `onSuccess` sets `deleteTarget` to null — ensure the mutation's `onSuccess` is wired correctly, not `onSettled`.
- **ProfileDetail shows blank**: Check `useParams` — `id` must be defined. If navigating from the Profiles table, confirm `navigate('/profiles/${profile.id}')` uses the correct profile id field.

## DO NOT

- Do NOT modify any backend files
- Do NOT add new npm dependencies
- Do NOT add a "Scalp" preset option — it is Phase 5 only, blocked by PDT
- Do NOT build backtest UI in this prompt — that belongs in ProfileDetail as a Phase 3 extension
- Do NOT add mock data anywhere
