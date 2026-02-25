import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, BrainCircuit, RefreshCw, Play, Pause,
  TrendingUp, BarChart3,
} from 'lucide-react';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { Spinner } from '../components/Spinner';
import { PnlCell } from '../components/PnlCell';
import { ProfileForm } from '../components/ProfileForm';

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
