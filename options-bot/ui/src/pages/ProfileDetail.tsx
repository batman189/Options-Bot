import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, BrainCircuit, RefreshCw, Play, Pause,
  TrendingUp, BarChart3, ChevronDown, CheckCircle, Trash2,
} from 'lucide-react';
import type { ModelSummary, ModelHealthEntry, ModelHealthResponse } from '../types/api';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';

/** Parse a UTC ISO timestamp from the backend (which omits the Z suffix). */
function parseUTC(ts: string): Date {
  return new Date(ts.endsWith('Z') || ts.includes('+') ? ts : ts + 'Z');
}
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
            {parseUTC(log.timestamp).toLocaleTimeString()}
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

// ─────────────────────────────────────────────
// Signal log panel (Phase 4.5)
// ─────────────────────────────────────────────

function SignalLogPanel({ profileId }: { profileId: string }) {
  const { data: signals, isLoading } = useQuery({
    queryKey: ['signals', profileId],
    queryFn: () => api.signals.list(profileId, 50),
    refetchInterval: 30_000,
  });

  if (isLoading) return <div className="flex justify-center py-4"><Spinner size="sm" /></div>;

  if (!signals || signals.length === 0) {
    return (
      <div className="text-muted text-xs py-4 text-center">
        No signal log entries yet. Start trading to see iteration decisions.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border">
            {['Time', 'Price', 'Predicted', 'Step', 'Reason', 'Entered'].map(h => (
              <th key={h} className="px-3 py-2 text-left text-2xs font-medium
                                     text-muted uppercase tracking-wider whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {signals.map((sig) => (
            <tr key={sig.id} className="border-b border-border hover:bg-panel/50 transition-colors">
              <td className="px-3 py-2 text-2xs font-mono text-muted whitespace-nowrap">
                {parseUTC(sig.timestamp).toLocaleString()}
              </td>
              <td className="px-3 py-2 text-2xs num text-text">
                {sig.underlying_price != null ? `$${sig.underlying_price.toFixed(2)}` : '—'}
              </td>
              <td className="px-3 py-2 text-2xs num">
                {sig.predicted_return != null ? (
                  <span className={sig.predicted_return >= 0 ? 'text-profit' : 'text-loss'}>
                    {sig.predicted_return >= 0 ? '+' : ''}{sig.predicted_return.toFixed(3)}%
                  </span>
                ) : '—'}
              </td>
              <td className="px-3 py-2 text-2xs text-center">
                {sig.entered ? (
                  <span className="text-profit font-bold">OK</span>
                ) : (
                  <span className="text-loss font-mono">{sig.step_stopped_at ?? '?'}</span>
                )}
              </td>
              <td className="px-3 py-2 text-2xs text-muted max-w-xs truncate" title={sig.stop_reason ?? ''}>
                {sig.entered ? (
                  <span className="text-profit">Trade entered</span>
                ) : (
                  sig.stop_reason ?? '—'
                )}
              </td>
              <td className="px-3 py-2 text-center">
                {sig.entered ? (
                  <span className="inline-block w-2 h-2 rounded-full bg-profit" />
                ) : (
                  <span className="inline-block w-2 h-2 rounded-full bg-loss" />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
  const [trainModelType, setTrainModelType] = useState<string>('xgboost');
  const [showModelTypeMenu, setShowModelTypeMenu] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [showBacktest, setShowBacktest] = useState(false);
  const [backtestStart, setBacktestStart] = useState('');
  const [backtestEnd, setBacktestEnd] = useState('');

  const { data: profile, isLoading: profileLoading, isError: profileError } = useQuery({
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

  const { data: importance } = useQuery({
    queryKey: ['model-importance', id],
    queryFn: () => api.models.importance(id!),
    enabled: !!id && (!!profile?.model_summary || (profile?.trained_models?.length ?? 0) > 0),
    staleTime: 60_000,
  });

  const { data: backtestResult, refetch: refetchBacktest } = useQuery({
    queryKey: ['backtest-result', id],
    queryFn: () => api.backtest.results(id!),
    enabled: !!id,
    refetchInterval: showBacktest ? 5_000 : false,
  });

  const { data: modelHealth } = useQuery({
    queryKey: ['model-health'],
    queryFn: () => api.system.modelHealth(),
    refetchInterval: 30_000,
    select: (data: ModelHealthResponse) =>
      data.profiles.find((p: ModelHealthEntry) => p.profile_id === id),
  });

  const trainMutation = useMutation({
    mutationFn: () => api.models.train(id!, trainModelType),
    onSuccess: () => {
      setShowLogs(true);
      qc.invalidateQueries({ queryKey: ['profiles'] });
      qc.invalidateQueries({ queryKey: ['profile', id] });
      qc.invalidateQueries({ queryKey: ['model-status', id] });
      qc.invalidateQueries({ queryKey: ['trade-stats', id] });
      qc.invalidateQueries({ queryKey: ['model-importance', id] });
    },
    onError: (e: Error) => {
      try {
        const body = e.message.split(': ').slice(1).join(': ');
        const parsed = JSON.parse(body);
        window.alert(parsed.detail ?? e.message);
      } catch {
        window.alert(e.message);
      }
    },
  });

  const retrainMutation = useMutation({
    mutationFn: () => api.models.retrain(id!),
    onSuccess: () => {
      setShowLogs(true);
      qc.invalidateQueries({ queryKey: ['profiles'] });
      qc.invalidateQueries({ queryKey: ['profile', id] });
      qc.invalidateQueries({ queryKey: ['model-status', id] });
      qc.invalidateQueries({ queryKey: ['trade-stats', id] });
      qc.invalidateQueries({ queryKey: ['model-importance', id] });
    },
    onError: (e: Error) => {
      try {
        const body = e.message.split(': ').slice(1).join(': ');
        const parsed = JSON.parse(body);
        window.alert(parsed.detail ?? e.message);
      } catch {
        window.alert(e.message);
      }
    },
  });

  const activateMutation = useMutation({
    mutationFn: () => api.profiles.activate(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profiles'] });
      qc.invalidateQueries({ queryKey: ['profile', id] });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: () => api.profiles.pause(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profiles'] });
      qc.invalidateQueries({ queryKey: ['profile', id] });
    },
  });

  const backtestMutation = useMutation({
    mutationFn: () => api.backtest.run(id!, {
      start_date: backtestStart,
      end_date: backtestEnd,
    }),
    onSuccess: () => {
      refetchBacktest();
    },
  });

  // Close model-type dropdown on outside click
  useEffect(() => {
    if (!showModelTypeMenu) return;
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowModelTypeMenu(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showModelTypeMenu]);

  if (profileError) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="text-center">
          <p className="text-loss text-lg mb-2">Profile not found</p>
          <p className="text-muted text-sm mb-4">The requested profile does not exist or was deleted.</p>
          <button
            onClick={() => window.history.back()}
            className="px-4 py-2 bg-card border border-border rounded text-sm hover:bg-hover"
          >
            Go Back
          </button>
        </div>
      </div>
    );
  }

  if (profileLoading || !profile) {
    return (
      <div className="flex items-center justify-center h-48">
        <Spinner size="lg" />
      </div>
    );
  }

  const model = profile.model_summary;
  // Build effective models list: prefer trained_models, fall back to model_summary
  const effectiveModels: ModelSummary[] =
    (profile.trained_models ?? []).length > 0
      ? profile.trained_models
      : model
        ? [model]
        : [];
  const isTraining = trainingStatus?.status === 'training' || profile.status === 'training';
  const canTrain = ['created', 'ready', 'active', 'paused', 'error'].includes(profile.status);
  const canRetrain = profile.status === 'ready' || profile.status === 'active' || profile.status === 'paused';
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
              <span>Created {parseUTC(profile.created_at).toLocaleDateString()}</span>
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

      {/* Scalp equity gate warning */}
      {profile.preset === 'scalp' && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-gold/5 border border-gold/20">
          <div className="flex items-center gap-2 text-xs text-gold">
            <span className="text-base">⚡</span>
            <span className="font-medium">Scalp Mode — 0DTE SPY</span>
          </div>
          <p className="text-2xs text-gold/70 mt-1">
            Requires $25K+ equity. Positions auto-close at 3:45 PM ET.
            Uses XGBoost Classifier with confidence-based entries.
          </p>
        </div>
      )}

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
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-2xs font-medium
                             disabled:opacity-50 transition-colors ${
                    isTraining
                      ? 'bg-gold/5 text-gold border border-gold/20 hover:bg-gold/10'
                      : 'bg-profit/5 text-profit border border-profit/20 hover:bg-profit/10'
                  }`}
                >
                  {retrainMutation.isPending ? <Spinner size="sm" /> : <RefreshCw size={11} />}
                  Update Model
                </button>
              )}
              {canTrain && (
                <div ref={dropdownRef} className="relative flex items-center">
                  <button
                    onClick={() => trainMutation.mutate()}
                    disabled={isTraining || trainMutation.isPending}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-l text-2xs font-medium
                               border-r-0 disabled:opacity-50 transition-colors ${
                      isTraining
                        ? 'bg-gold/10 text-gold border border-gold/30 hover:bg-gold/20'
                        : model
                          ? 'bg-profit/10 text-profit border border-profit/30 hover:bg-profit/20'
                          : 'bg-gold/10 text-gold border border-gold/30 hover:bg-gold/20'
                    }`}
                  >
                    {(isTraining || trainMutation.isPending) ? <Spinner size="sm" /> : <BrainCircuit size={11} />}
                    {isTraining ? 'Training…' : `Train ${trainModelType.toUpperCase()}`}
                  </button>
                  <button
                    onClick={() => setShowModelTypeMenu(v => !v)}
                    disabled={isTraining || trainMutation.isPending}
                    className={`flex items-center px-1.5 py-1 rounded-r text-2xs font-medium
                               disabled:opacity-50 transition-colors ${
                      isTraining
                        ? 'bg-gold/10 text-gold border border-gold/30 hover:bg-gold/20'
                        : model
                          ? 'bg-profit/10 text-profit border border-profit/30 hover:bg-profit/20'
                          : 'bg-gold/10 text-gold border border-gold/30 hover:bg-gold/20'
                    }`}
                    title="Select model type"
                  >
                    <ChevronDown size={10} />
                  </button>
                  {showModelTypeMenu && (
                    <div className="absolute right-0 top-full mt-1 z-10 bg-surface border border-border
                                    rounded shadow-lg py-1 min-w-28">
                      {(['xgboost', 'tft', 'ensemble', 'xgb_classifier', 'lightgbm'] as const).map(type => {
                        const hasType = effectiveModels.some(m => m.model_type === type && m.status === 'ready');
                        return (
                          <button
                            key={type}
                            onClick={() => { setTrainModelType(type); setShowModelTypeMenu(false); }}
                            className={`w-full text-left px-3 py-1.5 text-2xs font-mono transition-colors
                              ${trainModelType === type
                                ? 'text-gold bg-gold/10'
                                : 'text-muted hover:text-text hover:bg-panel'}`}
                          >
                            {type}
                            {hasType && <CheckCircle size={9} className="inline ml-1 text-profit" />}
                            {type === 'ensemble' && !hasType && (
                              <span className="ml-1 text-muted/50">(needs xgb+tft)</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Model info display — driven by trainModelType (dropdown selection) */}
          {(() => {
            // Build lookup of trained models by type
            const modelsByType = effectiveModels.reduce<Record<string, ModelSummary>>((acc, m) => {
              if (!acc[m.model_type] || new Date(m.trained_at ?? 0) > new Date(acc[m.model_type].trained_at ?? 0)) {
                acc[m.model_type] = m;
              }
              return acc;
            }, {});
            const displayModel = modelsByType[trainModelType];

            // Show tabs when multiple model types are trained
            const tabKeys = Object.keys(modelsByType);
            if (tabKeys.length > 1) {
              return (
                <>
                  <div className="flex gap-1 mb-3 border-b border-border pb-2">
                    {tabKeys.map(type => (
                      <button
                        key={type}
                        onClick={() => setTrainModelType(type)}
                        className={`px-2.5 py-1 rounded text-2xs font-mono transition-colors ${
                          trainModelType === type
                            ? 'bg-gold/10 text-gold border border-gold/20'
                            : 'text-muted hover:text-text hover:bg-panel'
                        }`}
                      >
                        {type.toUpperCase()}
                        {model && model.id === modelsByType[type].id && (
                          <span className="ml-1 text-profit text-[9px]">(active)</span>
                        )}
                      </button>
                    ))}
                  </div>
                  {displayModel ? (
                    <>
                      <div className="grid grid-cols-2 gap-2 mb-3">
                        <MetricTile
                          label="Directional Acc."
                          value={displayModel.metrics.dir_acc !== undefined
                            ? `${(displayModel.metrics.dir_acc * 100).toFixed(1)}%` : '—'}
                          good={displayModel.metrics.dir_acc !== undefined ? displayModel.metrics.dir_acc >= 0.52 : undefined}
                        />
                        {displayModel.model_type === 'xgb_classifier' ? (
                          <MetricTile
                            label="Accuracy (All)"
                            value={displayModel.metrics.acc_all !== undefined
                              ? `${(displayModel.metrics.acc_all * 100).toFixed(1)}%` : '—'}
                            good={displayModel.metrics.acc_all !== undefined ? displayModel.metrics.acc_all >= 0.40 : undefined}
                          />
                        ) : (
                          <MetricTile
                            label="MAE"
                            value={displayModel.metrics.mae !== undefined
                              ? displayModel.metrics.mae.toFixed(4) : '—'}
                          />
                        )}
                        <MetricTile
                          label="Model Age"
                          value={`${displayModel.age_days} days`}
                          good={displayModel.age_days <= 30 ? true : displayModel.age_days <= 90 ? undefined : false}
                        />
                        <MetricTile
                          label="Data Range"
                          value={displayModel.data_range}
                        />
                        {modelHealth && modelHealth.rolling_accuracy !== null && (
                          <MetricTile
                            label="Live Accuracy"
                            value={`${(modelHealth.rolling_accuracy * 100).toFixed(1)}%`}
                            good={
                              modelHealth.status === 'healthy' ? true
                              : modelHealth.status === 'degraded' ? false
                              : undefined
                            }
                          />
                        )}
                      </div>
                      {/* Live model health status */}
                      {modelHealth && modelHealth.status !== 'no_data' && (
                        <div className={`rounded border px-3 py-2 mb-3 text-2xs ${
                          modelHealth.status === 'degraded'
                            ? 'border-loss/20 bg-loss/5 text-loss'
                            : modelHealth.status === 'stale'
                            ? 'border-training/20 bg-training/5 text-training'
                            : modelHealth.status === 'healthy'
                            ? 'border-profit/20 bg-profit/5 text-profit'
                            : 'border-border bg-panel text-muted'
                        }`}>
                          {modelHealth.status === 'degraded' && (
                            <span>Model accuracy has dropped to {modelHealth.rolling_accuracy !== null
                              ? `${(modelHealth.rolling_accuracy * 100).toFixed(1)}%` : '—'
                            } — consider retraining</span>
                          )}
                          {modelHealth.status === 'stale' && (
                            <span>Model is {modelHealth.model_age_days} days old — consider retraining</span>
                          )}
                          {modelHealth.status === 'healthy' && (
                            <span>Model healthy — {modelHealth.correct_predictions}/{modelHealth.total_predictions} correct predictions</span>
                          )}
                          {modelHealth.status === 'warning' && (
                            <span>Model accuracy is {modelHealth.rolling_accuracy !== null
                              ? `${(modelHealth.rolling_accuracy * 100).toFixed(1)}%` : '—'
                            } — below 52% target</span>
                          )}
                          {modelHealth.status === 'insufficient_data' && (
                            <span>Collecting predictions... ({modelHealth.total_predictions}/10 minimum)</span>
                          )}
                        </div>
                      )}
                      {displayModel.model_type === 'xgb_classifier' && displayModel.metrics && (
                        <div className="mt-2 mb-2 flex flex-wrap gap-2 text-2xs">
                          {displayModel.metrics.avg_30min_move_pct !== undefined && (
                            <span className="bg-panel px-2 py-0.5 rounded border border-border">
                              Avg 30min move: {displayModel.metrics.avg_30min_move_pct.toFixed(3)}%
                            </span>
                          )}
                          {displayModel.metrics.class_distribution && (
                            <span className="bg-panel px-2 py-0.5 rounded border border-border">
                              Classes: ↓{(displayModel.metrics.class_distribution as any).down ?? '?'} · ={(displayModel.metrics.class_distribution as any).neutral ?? '?'} · ↑{(displayModel.metrics.class_distribution as any).up ?? '?'}
                            </span>
                          )}
                        </div>
                      )}
                      <div className="flex items-center gap-3 text-2xs text-muted">
                        <span className="font-mono">{displayModel.model_type}</span>
                        <span>·</span>
                        <span>Trained {displayModel.trained_at
                          ? parseUTC(displayModel.trained_at).toLocaleDateString() : 'unknown'}</span>
                        <StatusBadge status={displayModel.status} />
                      </div>
                      {importance?.feature_importance && Object.keys(importance.feature_importance).length > 0 && importance.model_type === trainModelType && (
                        <details className="mt-3">
                          <summary className="text-2xs text-muted cursor-pointer hover:text-text transition-colors select-none">
                            Feature Importance (top 15)
                          </summary>
                          <div className="mt-2">
                            <FeatureImportancePanel importance={importance.feature_importance} />
                          </div>
                        </details>
                      )}
                    </>
                  ) : !isTraining && (
                    <div className="py-4 text-center">
                      <p className="text-xs text-muted">{trainModelType.toUpperCase()} not trained yet.</p>
                      <p className="text-2xs text-muted mt-1">
                        Click <span className="text-gold">Train {trainModelType.toUpperCase()}</span> to begin.
                        {trainModelType === 'ensemble' && ' Requires both XGBoost and TFT models.'}
                      </p>
                    </div>
                  )}
                </>
              );
            }

            // Single or no trained models — show the selected type's info or "not trained"
            if (displayModel) {
              return (
                <>
                  <div className="grid grid-cols-2 gap-2 mb-3">
                    <MetricTile
                      label="Directional Acc."
                      value={displayModel.metrics.dir_acc !== undefined
                        ? `${(displayModel.metrics.dir_acc * 100).toFixed(1)}%` : '—'}
                      good={displayModel.metrics.dir_acc !== undefined ? displayModel.metrics.dir_acc >= 0.52 : undefined}
                    />
                    {displayModel.model_type === 'xgb_classifier' ? (
                      <MetricTile
                        label="Accuracy (All)"
                        value={displayModel.metrics.acc_all !== undefined
                          ? `${(displayModel.metrics.acc_all * 100).toFixed(1)}%` : '—'}
                        good={displayModel.metrics.acc_all !== undefined ? displayModel.metrics.acc_all >= 0.40 : undefined}
                      />
                    ) : (
                      <MetricTile
                        label="MAE"
                        value={displayModel.metrics.mae !== undefined
                          ? displayModel.metrics.mae.toFixed(4) : '—'}
                      />
                    )}
                    <MetricTile
                      label="Model Age"
                      value={`${displayModel.age_days} days`}
                      good={displayModel.age_days <= 30 ? true : displayModel.age_days <= 90 ? undefined : false}
                    />
                    <MetricTile
                      label="Data Range"
                      value={displayModel.data_range}
                    />
                    {modelHealth && modelHealth.rolling_accuracy !== null && (
                      <MetricTile
                        label="Live Accuracy"
                        value={`${(modelHealth.rolling_accuracy * 100).toFixed(1)}%`}
                        good={
                          modelHealth.status === 'healthy' ? true
                          : modelHealth.status === 'degraded' ? false
                          : undefined
                        }
                      />
                    )}
                  </div>
                  {/* Live model health status */}
                  {modelHealth && modelHealth.status !== 'no_data' && (
                    <div className={`rounded border px-3 py-2 mb-3 text-2xs ${
                      modelHealth.status === 'degraded'
                        ? 'border-loss/20 bg-loss/5 text-loss'
                        : modelHealth.status === 'stale'
                        ? 'border-training/20 bg-training/5 text-training'
                        : modelHealth.status === 'healthy'
                        ? 'border-profit/20 bg-profit/5 text-profit'
                        : 'border-border bg-panel text-muted'
                    }`}>
                      {modelHealth.status === 'degraded' && (
                        <span>Model accuracy has dropped to {modelHealth.rolling_accuracy !== null
                          ? `${(modelHealth.rolling_accuracy * 100).toFixed(1)}%` : '—'
                        } — consider retraining</span>
                      )}
                      {modelHealth.status === 'stale' && (
                        <span>Model is {modelHealth.model_age_days} days old — consider retraining</span>
                      )}
                      {modelHealth.status === 'healthy' && (
                        <span>Model healthy — {modelHealth.correct_predictions}/{modelHealth.total_predictions} correct predictions</span>
                      )}
                      {modelHealth.status === 'warning' && (
                        <span>Model accuracy is {modelHealth.rolling_accuracy !== null
                          ? `${(modelHealth.rolling_accuracy * 100).toFixed(1)}%` : '—'
                        } — below 52% target</span>
                      )}
                      {modelHealth.status === 'insufficient_data' && (
                        <span>Collecting predictions... ({modelHealth.total_predictions}/10 minimum)</span>
                      )}
                    </div>
                  )}
                  {displayModel.model_type === 'xgb_classifier' && displayModel.metrics && (
                    <div className="mt-2 mb-2 flex flex-wrap gap-2 text-2xs">
                      {displayModel.metrics.avg_30min_move_pct !== undefined && (
                        <span className="bg-panel px-2 py-0.5 rounded border border-border">
                          Avg 30min move: {displayModel.metrics.avg_30min_move_pct.toFixed(3)}%
                        </span>
                      )}
                      {displayModel.metrics.class_distribution && (
                        <span className="bg-panel px-2 py-0.5 rounded border border-border">
                          Classes: ↓{(displayModel.metrics.class_distribution as any).down ?? '?'} · ={(displayModel.metrics.class_distribution as any).neutral ?? '?'} · ↑{(displayModel.metrics.class_distribution as any).up ?? '?'}
                        </span>
                      )}
                    </div>
                  )}
                  <div className="flex items-center gap-3 text-2xs text-muted">
                    <span className="font-mono">{displayModel.model_type}</span>
                    <span>·</span>
                    <span>Trained {displayModel.trained_at
                      ? parseUTC(displayModel.trained_at).toLocaleDateString() : 'unknown'}</span>
                    <StatusBadge status={displayModel.status} />
                  </div>
                  {importance?.feature_importance && Object.keys(importance.feature_importance).length > 0 && importance.model_type === trainModelType && (
                    <details className="mt-3">
                      <summary className="text-2xs text-muted cursor-pointer hover:text-text transition-colors select-none">
                        Feature Importance (top 15)
                      </summary>
                      <div className="mt-2">
                        <FeatureImportancePanel importance={importance.feature_importance} />
                      </div>
                    </details>
                  )}
                </>
              );
            }

            // No model for the selected type
            if (!isTraining) {
              return (
                <div className="py-6 text-center">
                  <p className="text-xs text-muted">
                    {effectiveModels.length === 0
                      ? 'No trained model.'
                      : `${trainModelType.toUpperCase()} not trained yet.`}
                  </p>
                  <p className="text-2xs text-muted mt-1">
                    Click <span className="text-gold">Train {trainModelType.toUpperCase()}</span> to begin.
                    {trainModelType === 'ensemble' && ' Requires both XGBoost and TFT models.'}
                    {effectiveModels.length === 0 && ' Requires Theta Terminal running.'}
                  </p>
                </div>
              );
            }
            return null;
          })()}

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

          {/* Toggle logs + clear */}
          <div className="mt-3 flex items-center gap-3">
            <button
              onClick={() => setShowLogs(v => !v)}
              className="text-2xs text-muted hover:text-gold transition-colors"
            >
              {showLogs ? 'Hide' : 'Show'} training logs
            </button>
            {showLogs && (
              <button
                onClick={() => {
                  api.models.clearLogs(id!).then(() => {
                    qc.invalidateQueries({ queryKey: ['model-logs', id] });
                  }).catch(() => { /* silently ignore clear-logs failures */ });
                }}
                className="text-2xs text-muted hover:text-loss transition-colors flex items-center gap-1"
              >
                <Trash2 size={10} />
                Clear logs
              </button>
            )}
          </div>
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
                value={stats.best_trade_pct !== null
                  ? `${stats.best_trade_pct >= 0 ? '+' : ''}${stats.best_trade_pct.toFixed(1)}%`
                  : '—'}
                good={stats.best_trade_pct !== null ? stats.best_trade_pct > 0 : undefined}
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

      {/* Signal Decision Log — Phase 4.5 */}
      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <span className="text-xs font-medium text-text">Signal Decision Log</span>
          <span className="text-2xs text-muted ml-2">
            Last 50 iterations — why the bot traded or didn't
          </span>
        </div>
        <SignalLogPanel profileId={id!} />
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
                      {trade.entry_date ? parseUTC(trade.entry_date).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-3 py-2 text-xs font-mono font-medium text-gold">{trade.symbol}</td>
                    <td className="px-3 py-2">
                      <span className={`text-2xs font-mono font-medium uppercase ${
                        trade.direction === 'PUT' ? 'text-loss' : 'text-profit'
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
