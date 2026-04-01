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
  mutatingId: string | null;
  learningSummary: { activeCount: number; pausedCount: number; pausedNames: string[]; thresholdRange: string } | null;
}

function ProfileRow({
  profile, onEdit, onDelete, onActivate, onPause, mutatingId, learningSummary,
}: ProfileRowProps) {
  const navigate = useNavigate();
  const isMutating = mutatingId === profile.id;
  const canActivate = profile.status === 'ready' || profile.status === 'paused';
  const canPause = profile.status === 'active';
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
        <div className={`text-2xs font-mono uppercase tracking-wider mt-0.5 ${
          (profile.preset === 'scalp' || profile.preset === 'otm_scalp') ? 'text-gold' : 'text-muted'
        }`}>
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

      {/* Learning state summary */}
      <td className="px-4 py-3">
        {learningSummary ? (
          <div>
            <span className={`text-xs ${learningSummary.pausedCount > 0 ? 'text-loss' : 'text-profit'}`}>
              {learningSummary.pausedCount > 0
                ? `${learningSummary.pausedCount} paused`
                : `${learningSummary.activeCount} active`}
            </span>
            <div className="text-2xs text-muted">{learningSummary.thresholdRange} thresholds</div>
            {learningSummary.pausedNames.length > 0 && (
              <div className="text-2xs text-loss">{learningSummary.pausedNames.join(', ')} paused</div>
            )}
          </div>
        ) : (
          <span className="text-xs text-muted">—</span>
        )}
      </td>

      {/* P&L */}
      <td className="px-4 py-3">
        <PnlCell value={profile.total_pnl ?? 0} suffix=" USD" />
        <div className="text-2xs text-muted mt-0.5 space-x-2">
          <span>{profile.active_positions} open</span>
          {(profile.unrealized_pnl ?? 0) !== 0 && (
            <span className={`num ${(profile.unrealized_pnl ?? 0) >= 0 ? 'text-profit' : 'text-loss'}`}>
              ({(profile.unrealized_pnl ?? 0) >= 0 ? '+' : ''}{(profile.unrealized_pnl ?? 0).toFixed(2)} unreal)
            </span>
          )}
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

  const { data: learningState } = useQuery({
    queryKey: ['learning-state'],
    queryFn: api.learning.state,
    refetchInterval: 60_000,
    retry: false,
  });

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.profiles.activate(id),
    onMutate: (id: string) => { setMutatingId(id); },
    onSettled: () => { setMutatingId(null); qc.invalidateQueries({ queryKey: ['profiles'] }); },
  });

  const pauseMutation = useMutation({
    mutationFn: (id: string) => api.profiles.pause(id),
    onMutate: (id: string) => { setMutatingId(id); },
    onSettled: () => { setMutatingId(null); qc.invalidateQueries({ queryKey: ['profiles'] }); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.profiles.delete(id),
    onSuccess: () => {
      setDeleteTarget(null);
      qc.invalidateQueries({ queryKey: ['profiles'] });
    },
  });

  // Compute learning summary from learning state
  const learningSummary = learningState && learningState.profiles.length > 0 ? (() => {
    const ps = learningState.profiles;
    const active = ps.filter(p => !p.paused_by_learning);
    const paused = ps.filter(p => p.paused_by_learning);
    const confs = ps.map(p => Math.round(p.min_confidence * 100));
    const range = `${Math.min(...confs)}-${Math.max(...confs)}%`;
    return {
      activeCount: active.length,
      pausedCount: paused.length,
      pausedNames: paused.map(p => p.profile_name.replace(/_/g, ' ')),
      thresholdRange: range,
    };
  })() : null;

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
                {['Name', 'Status', 'Symbols', 'Learning', 'P&L', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-2xs font-medium
                                         text-muted uppercase tracking-wider">
                    {h === 'Actions' ? '' : h}
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
                  mutatingId={mutatingId}
                  learningSummary={learningSummary}
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
                s === 'error' ? 'bg-error' :
                s === 'created' ? 'bg-muted' :
                s === 'paused' ? 'bg-training' : 'bg-muted'
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
