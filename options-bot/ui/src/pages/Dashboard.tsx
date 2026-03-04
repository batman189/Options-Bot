import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  TrendingUp, TrendingDown, Briefcase, Activity,
  AlertTriangle, Pause, Play, RefreshCw, ChevronRight,
  Zap, Clock, Database,
} from 'lucide-react';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { ConnIndicator } from '../components/ConnIndicator';
import { PnlCell } from '../components/PnlCell';
import { Spinner } from '../components/Spinner';
import { PageHeader } from '../components/PageHeader';
import type { Profile, SystemStatus, PDTStatus, ModelHealthResponse, TrainingQueueStatus } from '../types/api';

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function fmtDollars(n: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n);
}

function fmtUptime(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

// ─────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: React.ReactNode;
  sub?: string;
  icon: React.ElementType;
  accent?: boolean;
  warn?: boolean;
}

function StatCard({ label, value, sub, icon: Icon, accent, warn }: StatCardProps) {
  return (
    <div className={`
      rounded-lg border bg-surface p-4 flex flex-col gap-3
      ${warn ? 'border-loss/40 bg-loss/5' : accent ? 'border-gold/20' : 'border-border'}
    `}>
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted font-medium uppercase tracking-wider">{label}</span>
        <div className={`
          h-7 w-7 rounded flex items-center justify-center
          ${warn ? 'bg-loss/10' : accent ? 'bg-gold/10' : 'bg-panel'}
        `}>
          <Icon size={14} className={warn ? 'text-loss' : accent ? 'text-gold' : 'text-muted'} />
        </div>
      </div>
      <div>
        <div className={`text-xl font-semibold num ${warn ? 'text-loss' : 'text-text'}`}>
          {value}
        </div>
        {sub && <div className="text-xs text-muted mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

interface ProfileCardProps {
  profile: Profile;
  onActivate: (id: string) => void;
  onPause: (id: string) => void;
  activating: boolean;
  pausing: boolean;
}

function ProfileCard({ profile, onActivate, onPause, activating, pausing }: ProfileCardProps) {
  const navigate = useNavigate();
  const canActivate = profile.status === 'ready' || profile.status === 'paused';
  const canPause = profile.status === 'active';
  const modelReady = profile.model_summary?.status === 'ready';
  const dirAcc = profile.model_summary?.metrics?.dir_acc;

  return (
    <div className="rounded-lg border border-border bg-surface hover:border-border/80 transition-colors">
      {/* Card header */}
      <div className="px-4 pt-4 pb-3 border-b border-border flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate(`/profiles/${profile.id}`)}
              className="text-sm font-semibold text-text hover:text-gold truncate transition-colors"
            >
              {profile.name}
            </button>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <StatusBadge status={profile.status} />
            <span className="text-2xs text-muted font-mono uppercase tracking-wider">
              {profile.preset}
            </span>
          </div>
        </div>

        {/* Activate / Pause button */}
        <div className="flex-shrink-0">
          {canActivate && (
            <button
              onClick={() => onActivate(profile.id)}
              disabled={activating}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium
                         bg-active/10 text-active border border-active/20
                         hover:bg-active/20 disabled:opacity-50 transition-colors"
            >
              {activating ? <Spinner size="sm" /> : <Play size={11} />}
              Activate
            </button>
          )}
          {canPause && (
            <button
              onClick={() => onPause(profile.id)}
              disabled={pausing}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium
                         bg-muted/10 text-muted border border-muted/20
                         hover:bg-panel hover:text-text disabled:opacity-50 transition-colors"
            >
              {pausing ? <Spinner size="sm" /> : <Pause size={11} />}
              Pause
            </button>
          )}
        </div>
      </div>

      {/* Card body */}
      <div className="px-4 py-3 grid grid-cols-3 gap-3">
        {/* Symbols */}
        <div>
          <div className="text-2xs text-muted uppercase tracking-wider mb-1">Symbols</div>
          <div className="flex flex-wrap gap-1">
            {profile.symbols.map(sym => (
              <span key={sym} className="font-mono text-xs text-gold bg-gold/5 border border-gold/15 px-1.5 py-0.5 rounded">
                {sym}
              </span>
            ))}
          </div>
        </div>

        {/* P&L */}
        <div>
          <div className="text-2xs text-muted uppercase tracking-wider mb-1">Total P&L</div>
          <PnlCell value={profile.total_pnl} suffix=" USD" className="text-sm" />
        </div>

        {/* Positions */}
        <div>
          <div className="text-2xs text-muted uppercase tracking-wider mb-1">Open</div>
          <span className="num text-sm text-text font-medium">{profile.active_positions}</span>
        </div>
      </div>

      {/* Model health row */}
      <div className="px-4 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {modelReady ? (
            <>
              <span className={`text-xs num ${
                dirAcc !== undefined && dirAcc >= 0.52 ? 'text-profit' : 'text-muted'
              }`}>
                {dirAcc !== undefined ? `${(dirAcc * 100).toFixed(1)}% dir.acc` : 'No metrics'}
              </span>
              {profile.model_summary && (
                <span className="text-2xs text-muted font-mono">
                  {profile.model_summary.age_days}d old
                </span>
              )}
            </>
          ) : (
            <span className="text-xs text-muted">
              {profile.model_summary ? `Model ${profile.model_summary.status}` : 'No model trained'}
            </span>
          )}
        </div>
        <button
          onClick={() => navigate(`/profiles/${profile.id}`)}
          className="text-2xs text-muted hover:text-gold flex items-center gap-0.5 transition-colors"
        >
          Detail <ChevronRight size={10} />
        </button>
      </div>
    </div>
  );
}

interface StatusPanelProps {
  status: SystemStatus | undefined;
  pdt: PDTStatus | undefined;
  statusLoading: boolean;
}

function StatusPanel({ status, pdt, statusLoading }: StatusPanelProps) {
  return (
    <div className="rounded-lg border border-border bg-surface flex flex-col h-full">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-muted">System</span>
        {statusLoading && <Spinner size="sm" />}
      </div>

      <div className="px-4 py-3 space-y-3 flex-1">
        {/* Connections */}
        <div className="space-y-2">
          <ConnIndicator
            connected={status?.alpaca_connected ?? false}
            label="Alpaca"
          />
          <ConnIndicator
            connected={status?.theta_terminal_connected ?? false}
            label="Theta Terminal"
          />
          <ConnIndicator
            connected={status !== undefined}
            label="Backend API"
          />
        </div>

        <div className="border-t border-border pt-3 space-y-2">
          {/* Portfolio value */}
          {status && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted">Portfolio</span>
              <span className="num text-xs text-text">{fmtDollars(status.portfolio_value)}</span>
            </div>
          )}

          {/* Active profiles */}
          {status && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted">Active profiles</span>
              <span className="num text-xs text-text">{status.active_profiles}</span>
            </div>
          )}

          {/* Open positions */}
          {status && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted">Open positions</span>
              <span className="num text-xs text-text">{status.total_open_positions} / 10</span>
            </div>
          )}

          {/* Uptime */}
          {status && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted flex items-center gap-1">
                <Clock size={10} /> Uptime
              </span>
              <span className="num text-xs text-text">{fmtUptime(status.uptime_seconds)}</span>
            </div>
          )}
        </div>

        {/* PDT Counter */}
        {pdt && (
          <div className={`border-t border-border pt-3`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted font-medium">PDT Day Trades</span>
              <span className={`num text-xs font-semibold ${
                pdt.is_restricted && pdt.remaining === 0 ? 'text-loss' :
                pdt.is_restricted && pdt.remaining === 1 ? 'text-training' : 'text-text'
              }`}>
                {pdt.day_trades_5d} / {pdt.is_restricted ? '3' : '∞'}
              </span>
            </div>
            {pdt.is_restricted && (
              <div className="w-full bg-panel rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full transition-all ${
                    pdt.remaining === 0 ? 'bg-loss' :
                    pdt.remaining === 1 ? 'bg-training' : 'bg-profit'
                  }`}
                  style={{ width: `${Math.min((pdt.day_trades_5d / 3) * 100, 100)}%` }}
                />
              </div>
            )}
            {pdt.is_restricted && (
              <p className="text-2xs text-muted mt-1.5">
                {pdt.remaining} remaining · rolling 5 days
              </p>
            )}
            {!pdt.is_restricted && (
              <p className="text-2xs text-profit mt-1">
                Unlimited (equity ≥ $25K)
              </p>
            )}
          </div>
        )}

        {/* Last error */}
        {status?.last_error && (
          <div className="border-t border-border pt-3">
            <div className="flex items-center gap-1.5 mb-1">
              <AlertTriangle size={11} className="text-loss" />
              <span className="text-2xs text-loss font-medium">Last Error</span>
            </div>
            <p className="text-2xs text-muted font-mono leading-relaxed line-clamp-3">
              {status.last_error}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Main Dashboard component
// ─────────────────────────────────────────────

export function Dashboard() {
  const qc = useQueryClient();

  // Data queries — all auto-refresh every 30s
  const { data: profiles, isLoading: profilesLoading } = useQuery({
    queryKey: ['profiles'],
    queryFn: api.profiles.list,
    refetchInterval: 30_000,
  });

  const { data: systemStatus, isLoading: statusLoading } = useQuery({
    queryKey: ['system-status'],
    queryFn: api.system.status,
    refetchInterval: 30_000,
    retry: false,
  });

  const { data: pdt } = useQuery({
    queryKey: ['pdt'],
    queryFn: api.system.pdt,
    refetchInterval: 30_000,
    retry: false,
  });

  const { data: tradeStats } = useQuery({
    queryKey: ['trade-stats'],
    queryFn: () => api.trades.stats(),
    refetchInterval: 30_000,
  });

  const { data: modelHealth } = useQuery<ModelHealthResponse>({
    queryKey: ['model-health'],
    queryFn: () => api.system.modelHealth(),
    refetchInterval: 30_000,
  });

  const { data: trainingQueue } = useQuery<TrainingQueueStatus>({
    queryKey: ['training-queue'],
    queryFn: () => api.system.trainingQueue(),
    refetchInterval: 30_000,
    retry: false,
  });

  // Mutations
  const activateMutation = useMutation({
    mutationFn: (id: string) => api.profiles.activate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profiles'] }),
  });

  const pauseMutation = useMutation({
    mutationFn: (id: string) => api.profiles.pause(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profiles'] }),
  });

  // Derived values
  const totalPnl = tradeStats?.total_pnl_dollars ?? 0;
  const totalPositions = systemStatus?.total_open_positions ?? 0;
  const activeProfiles = systemStatus?.active_profiles ?? 0;
  const portfolioValue = systemStatus?.portfolio_value ?? 0;

  const pdtRestricted = pdt?.is_restricted && (pdt?.remaining ?? 3) === 0;

  function handleRefresh() {
    qc.invalidateQueries({ queryKey: ['profiles'] });
    qc.invalidateQueries({ queryKey: ['system-status'] });
    qc.invalidateQueries({ queryKey: ['pdt'] });
    qc.invalidateQueries({ queryKey: ['trade-stats'] });
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Dashboard"
        subtitle="Live overview — refreshes every 30 seconds"
        actions={
          <button
            onClick={handleRefresh}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs text-muted
                       border border-border hover:text-text hover:border-border/60 transition-colors"
          >
            <RefreshCw size={12} />
            Refresh
          </button>
        }
      />

      {/* ── BAND 1: Portfolio summary stats ── */}
      <div className="grid grid-cols-5 gap-3">
        <StatCard
          label="Portfolio Value"
          value={fmtDollars(portfolioValue)}
          sub="Alpaca paper account"
          icon={Database}
          accent
        />
        <StatCard
          label="Total P&L"
          value={<PnlCell value={totalPnl} suffix=" USD" />}
          sub={`${tradeStats?.closed_trades ?? 0} closed trades`}
          icon={totalPnl >= 0 ? TrendingUp : TrendingDown}
        />
        <StatCard
          label="Open Positions"
          value={`${totalPositions} / 10`}
          sub={`${activeProfiles} active profile${activeProfiles !== 1 ? 's' : ''}`}
          icon={Briefcase}
        />
        <StatCard
          label="Win Rate"
          value={
            tradeStats?.win_rate !== null && tradeStats?.win_rate !== undefined
              ? `${(tradeStats.win_rate * 100).toFixed(1)}%`
              : '—'
          }
          sub={`${tradeStats?.win_count ?? 0}W / ${tradeStats?.loss_count ?? 0}L`}
          icon={Activity}
        />
        <StatCard
          label="Training Queue"
          value={`${trainingQueue?.pending_count ?? 0} / ${trainingQueue?.min_samples_for_retrain ?? 30}`}
          sub={trainingQueue?.ready_for_retrain ? 'Ready to retrain' : 'Collecting samples'}
          icon={Zap}
          warn={trainingQueue?.ready_for_retrain}
        />
      </div>

      {/* ── BAND 2: PDT warning (only if restricted and at limit) ── */}
      {pdtRestricted && (
        <div className="rounded-lg border border-loss/30 bg-loss/5 px-4 py-3 flex items-center gap-3">
          <AlertTriangle size={16} className="text-loss flex-shrink-0" />
          <div>
            <span className="text-sm font-medium text-loss">PDT Limit Reached</span>
            <span className="text-sm text-muted ml-2">
              3 of 3 day trades used in the last 5 days.
              New same-day round-trip orders are blocked until the rolling window clears.
            </span>
          </div>
        </div>
      )}

      {/* ── MODEL HEALTH BANNER ── */}
      {modelHealth && (modelHealth.any_degraded || modelHealth.any_stale) && (
        <div className={`rounded-lg border px-4 py-3 mb-4 ${
          modelHealth.any_degraded
            ? 'border-loss/30 bg-loss/5'
            : 'border-training/30 bg-training/5'
        }`}>
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle size={14} className={
              modelHealth.any_degraded ? 'text-loss' : 'text-training'
            } />
            <span className={`text-xs font-semibold ${
              modelHealth.any_degraded ? 'text-loss' : 'text-training'
            }`}>
              {modelHealth.any_degraded ? 'Model Degradation Detected' : 'Model Health Warning'}
            </span>
          </div>
          <div className="space-y-1">
            {modelHealth.profiles
              .filter(p => p.status === 'degraded' || p.status === 'stale')
              .map(p => (
                <div key={p.profile_id} className="text-2xs text-muted">
                  <span className="font-semibold text-text">{p.profile_name}</span>
                  {' — '}
                  {p.status === 'degraded' && p.rolling_accuracy !== null
                    ? `${(p.rolling_accuracy * 100).toFixed(1)}% accuracy (below ${45}% threshold)`
                    : p.status === 'stale'
                    ? `Model is ${p.model_age_days} days old`
                    : p.message}
                </div>
              ))}
          </div>
        </div>
      )}

      {/* ── BANDS 3 + 4: Profile grid + status panel ── */}
      <div className="grid grid-cols-[1fr_240px] gap-4 items-start">

        {/* Profile cards */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium uppercase tracking-wider text-muted">
              Profiles ({profiles?.length ?? 0})
            </span>
            {profilesLoading && <Spinner size="sm" />}
          </div>

          {profilesLoading && !profiles && (
            <div className="flex items-center justify-center h-40">
              <Spinner size="lg" />
            </div>
          )}

          {!profilesLoading && (!profiles || profiles.length === 0) && (
            <div className="rounded-lg border border-dashed border-border bg-surface p-10 text-center">
              <Zap size={24} className="text-muted mx-auto mb-3" />
              <p className="text-sm text-muted">No profiles yet.</p>
              <p className="text-xs text-muted mt-1">
                Go to <span className="text-gold">Profiles</span> to create your first one.
              </p>
            </div>
          )}

          {profiles && profiles.length > 0 && (
            <div className="grid grid-cols-2 gap-3">
              {profiles.map(profile => (
                <ProfileCard
                  key={profile.id}
                  profile={profile}
                  onActivate={(id) => activateMutation.mutate(id)}
                  onPause={(id) => pauseMutation.mutate(id)}
                  activating={activateMutation.isPending && activateMutation.variables === profile.id}
                  pausing={pauseMutation.isPending && pauseMutation.variables === profile.id}
                />
              ))}
            </div>
          )}
        </div>

        {/* Status panel */}
        <StatusPanel
          status={systemStatus}
          pdt={pdt}
          statusLoading={statusLoading}
        />
      </div>
    </div>
  );
}
