import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, Play, Pause, TrendingUp, BarChart3,
  AlertTriangle, Brain, ChevronRight, Radar, Zap,
} from 'lucide-react';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { PnlCell } from '../components/PnlCell';
import { Spinner } from '../components/Spinner';
import { ProfileForm } from '../components/ProfileForm';
import type { V2SignalLogEntry } from '../types/api';

/** Parse a UTC ISO timestamp from the backend (which may omit the Z suffix). */
function parseUTC(ts: string): Date {
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(ts);
  return new Date(hasTimezone ? ts : ts + 'Z');
}

function fmtTimestamp(ts: string): string {
  const d = parseUTC(ts);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ─────────────────────────────────────────────
// MetricTile (kept from V1)
// ─────────────────────────────────────────────

function MetricTile({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="bg-panel rounded border border-border px-3 py-2.5">
      <div className="text-2xs text-muted uppercase tracking-wider mb-1">{label}</div>
      <div className={`num text-sm font-semibold ${
        good === true ? 'text-profit' : good === false ? 'text-loss' : 'text-text'
      }`}>{value}</div>
    </div>
  );
}

function setupBadgeCls(t: string | null): string {
  if (t === 'momentum') return 'bg-blue-500/15 text-blue-400';
  if (t === 'mean_reversion') return 'bg-purple-500/15 text-purple-400';
  if (t === 'catalyst') return 'bg-orange-500/15 text-orange-400';
  return 'bg-border/30 text-muted';
}

function pctColor(v: number | null): string {
  if (v === null) return 'text-muted';
  if (v >= 0.65) return 'text-profit';
  if (v >= 0.50) return 'text-gold';
  return 'text-muted';
}

function regimeBadgeCls(r: string | null): string {
  if (r === 'HIGH_VOLATILITY') return 'bg-red-500/15 text-red-400';
  if (r === 'TRENDING_UP') return 'bg-profit/15 text-profit';
  if (r === 'TRENDING_DOWN') return 'bg-loss/15 text-loss';
  return 'bg-border/30 text-muted';
}

function regimeShort(r: string | null): string {
  if (r === 'HIGH_VOLATILITY') return 'HIGH VOL';
  if (r === 'TRENDING_UP') return 'TREND \u2191';
  if (r === 'TRENDING_DOWN') return 'TREND \u2193';
  if (r === 'CHOPPY') return 'CHOPPY';
  return '\u2014';
}

function FactorBar({ name, value }: { name: string; value: number | null }) {
  const pct = value !== null ? Math.round(value * 100) : null;
  return (
    <div className="flex items-center gap-2">
      <span className="text-2xs text-muted w-28 shrink-0">{name}</span>
      {pct !== null ? (
        <>
          <div className="flex-1 h-1.5 bg-border/30 rounded-full overflow-hidden">
            <div className="h-full bg-gold/60 rounded-full" style={{ width: `${Math.min(pct, 100)}%` }} />
          </div>
          <span className="text-2xs num text-text w-10 text-right">{pct}%</span>
        </>
      ) : (
        <>
          <div className="flex-1 h-1.5 bg-border/10 rounded-full" />
          <span className="text-2xs text-muted/50 w-10 text-right italic">n/a</span>
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Main ProfileDetail
// ─────────────────────────────────────────────

export function ProfileDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showEdit, setShowEdit] = useState(false);
  const [expandedSignalId, setExpandedSignalId] = useState<number | null>(null);

  const { data: profile, isLoading: profileLoading, isError: profileError } = useQuery({
    queryKey: ['profile', id],
    queryFn: () => api.profiles.get(id!),
    enabled: !!id,
    refetchInterval: 10_000,
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

  // V2: Learning state
  const { data: learningState } = useQuery({
    queryKey: ['learning-state'],
    queryFn: api.learning.state,
    refetchInterval: 60_000,
    retry: false,
  });

  const { data: v2Signals } = useQuery({
    queryKey: ['v2-signals-detail'],
    queryFn: () => api.v2signals.list({ limit: 50 }),
    refetchInterval: 30_000,
  });

  const activateMutation = useMutation({
    mutationFn: (pid: string) => api.profiles.activate(pid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profile', id] }),
  });

  const pauseMutation = useMutation({
    mutationFn: (pid: string) => api.profiles.pause(pid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profile', id] }),
  });

  const resumeMutation = useMutation({
    mutationFn: (name: string) => api.learning.resume(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['learning-state'] }),
  });

  // Loading / error states
  if (profileLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (profileError || !profile) {
    return (
      <div className="text-center py-20">
        <p className="text-sm text-muted">Profile not found or failed to load.</p>
        <button onClick={() => navigate('/profiles')}
          className="mt-3 text-xs text-gold hover:text-gold/80 transition-colors">
          Back to Profiles
        </button>
      </div>
    );
  }

  const canActivate = profile.status === 'ready' || profile.status === 'paused';
  const canPause = profile.status === 'active';

  // Collect all adjustment log entries across profiles
  const allAdjustments = learningState?.profiles
    .flatMap(p => p.recent_adjustments.map(a => ({ ...a, profile_name: p.profile_name })))
    .filter(a => a.type !== 'initial')
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
    .slice(0, 10) ?? [];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <button onClick={() => navigate('/profiles')}
          className="flex items-center gap-1.5 text-xs text-muted hover:text-text mb-3 transition-colors">
          <ArrowLeft size={13} /> All Profiles
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
            <button onClick={() => setShowEdit(true)}
              className="px-3 py-1.5 rounded text-xs border border-border text-muted
                         hover:text-text hover:border-border/60 transition-colors">
              Edit
            </button>
            {canActivate && (
              <button onClick={() => activateMutation.mutate(id!)}
                disabled={activateMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                           bg-active/10 text-active border border-active/20 hover:bg-active/20
                           disabled:opacity-50 transition-colors">
                {activateMutation.isPending ? <Spinner size="sm" /> : <Play size={11} />} Activate
              </button>
            )}
            {canPause && (
              <button onClick={() => pauseMutation.mutate(id!)}
                disabled={pauseMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                           bg-muted/10 text-muted border border-muted/20 hover:bg-panel hover:text-text
                           disabled:opacity-50 transition-colors">
                {pauseMutation.isPending ? <Spinner size="sm" /> : <Pause size={11} />} Pause
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Scalp equity gate warning */}
      {profile.preset === 'scalp' && (profile.config as any)?.requires_min_equity > 0 && (
        <div className="rounded-lg border border-training/30 bg-training/5 px-4 py-3 flex items-center gap-3">
          <AlertTriangle size={14} className="text-training flex-shrink-0" />
          <span className="text-xs text-muted">
            This profile requires <span className="text-text font-medium">
              ${((profile.config as any).requires_min_equity ?? 0).toLocaleString()}
            </span> minimum equity.
          </span>
        </div>
      )}
      {profile.preset === '0dte_scalp' && (
        <div className="rounded-lg border border-gold/30 bg-gold/5 px-4 py-3 flex items-center gap-3">
          <Zap size={14} className="text-gold flex-shrink-0" />
          <span className="text-xs text-muted">
            Growth mode active — 15% risk per trade while account is under $25,000.
            Switches to standard 4% sizing automatically above $25K.
          </span>
        </div>
      )}

      {/* ── Learning Layer + Trade Stats grid ── */}
      <div className="grid grid-cols-[1fr_300px] gap-4">
        {/* Learning Layer */}
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-center gap-2 mb-1">
            <Brain size={15} className="text-muted" />
            <span className="text-xs font-medium text-text">Learning Layer</span>
          </div>
          <p className="text-2xs text-muted mb-4">Adaptive thresholds — updated automatically after every 20 trades</p>

          {learningState && learningState.profiles.length > 0 ? (
            <>
              {/* Profile cards */}
              <div className="grid grid-cols-3 gap-3 mb-4">
                {learningState.profiles.map(p => (
                  <div key={p.profile_name} className="rounded border border-border bg-panel p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-text">
                        {p.profile_name.charAt(0).toUpperCase() + p.profile_name.slice(1).replace(/_/g, ' ')}
                      </span>
                      {p.paused_by_learning ? (
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] font-mono font-medium px-1 py-0.5 rounded bg-loss/10 text-loss border border-loss/20">
                            PAUSED
                          </span>
                          <button onClick={() => resumeMutation.mutate(p.profile_name)}
                            disabled={resumeMutation.isPending}
                            className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-profit/10 text-profit border border-profit/20
                                       hover:bg-profit/20 disabled:opacity-50 transition-colors">
                            Resume
                          </button>
                        </div>
                      ) : (
                        <span className="text-[10px] font-mono font-medium px-1 py-0.5 rounded bg-profit/10 text-profit border border-profit/20">
                          ACTIVE
                        </span>
                      )}
                    </div>
                    <div className="num text-lg font-bold text-text">
                      {(p.min_confidence * 100).toFixed(0)}%
                      <span className="text-xs font-normal text-muted ml-1">threshold</span>
                    </div>
                    {p.last_adjustment && (
                      <p className="text-2xs text-muted mt-1">Last: {fmtTimestamp(p.last_adjustment)}</p>
                    )}
                  </div>
                ))}
              </div>

              {/* Adjustment log table */}
              {allAdjustments.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-border">
                        {['Time', 'Profile', 'Type', 'Old', 'New', 'Reason'].map(h => (
                          <th key={h} className="px-2 py-1.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {allAdjustments.map((a, i) => (
                        <tr key={i} className="border-b border-border/50">
                          <td className="px-2 py-1.5 text-2xs font-mono text-muted whitespace-nowrap">{fmtTimestamp(a.timestamp)}</td>
                          <td className="px-2 py-1.5 text-2xs text-text">{(a as any).profile_name?.replace(/_/g, ' ')}</td>
                          <td className="px-2 py-1.5 text-2xs font-mono text-muted">{a.type}</td>
                          <td className="px-2 py-1.5 text-2xs num text-muted">{a.old ?? '—'}</td>
                          <td className="px-2 py-1.5 text-2xs num text-text">{a.new ?? '—'}</td>
                          <td className="px-2 py-1.5 text-2xs text-muted truncate max-w-[200px]" title={a.reason}>{a.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-muted text-center py-4">
                  No adjustments yet — learning layer activates after the first 20 closed trades
                </p>
              )}
            </>
          ) : (
            <p className="text-xs text-muted text-center py-8">Learning state not available</p>
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
              <MetricTile label="Win Rate"
                value={stats.win_rate !== null ? `${(stats.win_rate * 100).toFixed(1)}%` : '—'}
                good={stats.win_rate !== null ? stats.win_rate >= 0.5 : undefined} />
              <MetricTile label="Total P&L"
                value={stats.total_pnl_dollars >= 0 ? `+$${stats.total_pnl_dollars.toFixed(0)}` : `-$${Math.abs(stats.total_pnl_dollars).toFixed(0)}`}
                good={stats.total_pnl_dollars >= 0} />
              <MetricTile label="Avg Hold"
                value={stats.avg_hold_days !== null ? `${stats.avg_hold_days.toFixed(1)}d` : '—'} />
              <MetricTile label="Best Trade"
                value={stats.best_trade_pct !== null ? `${stats.best_trade_pct >= 0 ? '+' : ''}${stats.best_trade_pct.toFixed(1)}%` : '—'}
                good={stats.best_trade_pct !== null ? stats.best_trade_pct > 0 : undefined} />
              <MetricTile label="Worst Trade"
                value={stats.worst_trade_pct !== null ? `${stats.worst_trade_pct.toFixed(1)}%` : '—'}
                good={(stats.worst_trade_pct ?? 0) >= 0} />
            </div>
          ) : (
            <p className="text-xs text-muted text-center py-8">No trades yet.</p>
          )}
        </div>
      </div>

      {/* Signal Decisions (V2) */}
      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <Radar size={14} className="text-muted" />
          <span className="text-xs font-medium text-text">Signal Decisions</span>
          <span className="text-2xs text-muted">Last 50 evaluations across all profiles</span>
        </div>
        {!v2Signals || v2Signals.length === 0 ? (
          <div className="py-10 text-center">
            <p className="text-xs text-muted">No signal decisions recorded yet. Start trading to see decisions here.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="w-6" />
                  {['Time', 'Profile', 'Symbol', 'Setup', 'Confidence', 'Regime', 'Decision'].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-2xs font-medium text-muted uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {v2Signals.map((sig: V2SignalLogEntry) => {
                  const isExp = expandedSignalId === sig.id;
                  return (
                    <>
                      <tr key={sig.id} onClick={() => setExpandedSignalId(isExp ? null : sig.id)}
                        className={`border-b border-border hover:bg-panel/50 transition-colors cursor-pointer ${sig.entered ? 'bg-profit/[0.03]' : ''}`}>
                        <td className="px-1 py-2 text-center">
                          <ChevronRight size={12} className={`text-muted transition-transform ${isExp ? 'rotate-90' : ''}`} />
                        </td>
                        <td className="px-3 py-2 text-2xs font-mono text-muted whitespace-nowrap">{fmtTimestamp(sig.timestamp)}</td>
                        <td className="px-3 py-2 text-2xs text-text">{sig.profile_name.charAt(0).toUpperCase() + sig.profile_name.slice(1).replace(/_/g, ' ')}</td>
                        <td className="px-3 py-2 text-xs font-mono font-medium text-gold">{sig.symbol}</td>
                        <td className="px-3 py-2">
                          {sig.setup_type ? (
                            <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${setupBadgeCls(sig.setup_type)}`}>
                              {sig.setup_type.replace('_', ' ')}
                            </span>
                          ) : <span className="text-2xs text-muted">{'\u2014'}</span>}
                        </td>
                        <td className={`px-3 py-2 text-2xs num font-medium ${pctColor(sig.confidence_score)}`}>
                          {sig.confidence_score !== null ? `${(sig.confidence_score * 100).toFixed(0)}%` : '\u2014'}
                        </td>
                        <td className="px-3 py-2">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${regimeBadgeCls(sig.regime)}`}>
                            {regimeShort(sig.regime)}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          {sig.entered ? (
                            <span className="inline-block px-1.5 py-0.5 rounded text-2xs font-medium bg-profit/10 text-profit border border-profit/20">YES</span>
                          ) : (
                            <span className="text-2xs text-muted max-w-[180px] truncate inline-block" title={sig.block_reason ?? ''}>{sig.block_reason ?? 'NO'}</span>
                          )}
                        </td>
                      </tr>
                      {isExp && (
                        <tr key={`${sig.id}-detail`} className="border-b border-border bg-panel/30">
                          <td colSpan={8} className="px-6 py-3">
                            <div className="grid grid-cols-2 gap-x-8 gap-y-2 max-w-2xl">
                              <FactorBar name="Signal Clarity" value={sig.signal_clarity} />
                              <FactorBar name="Regime Fit" value={sig.regime_fit} />
                              <FactorBar name="IVR" value={sig.ivr} />
                              <FactorBar name="Institutional Flow" value={sig.institutional_flow} />
                              <FactorBar name="Historical Perf" value={sig.historical_perf} />
                              <FactorBar name="Sentiment" value={sig.sentiment} />
                              <FactorBar name="Time of Day" value={sig.time_of_day_score} />
                            </div>
                            <div className="mt-3 flex flex-wrap gap-4 text-2xs text-muted">
                              <span>Raw: <span className="text-text font-medium">{sig.raw_score !== null ? `${(sig.raw_score * 100).toFixed(1)}%` : '\u2014'}</span></span>
                              <span>Capped: <span className="text-text font-medium">{sig.confidence_score !== null ? `${(sig.confidence_score * 100).toFixed(1)}%` : '\u2014'}</span></span>
                              <span>Threshold: <span className="text-text font-medium">{sig.threshold_label ?? '\u2014'}</span></span>
                              <span>Regime: <span className="text-text font-medium">{sig.regime_reason ?? '\u2014'}</span></span>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Trade history table */}
      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp size={14} className="text-muted" />
            <span className="text-xs font-medium text-text">Trades</span>
            {trades && <span className="text-2xs text-muted">({trades.length})</span>}
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
                  {['Date', 'Symbol', 'Dir', 'Setup', 'Strike', 'Exp', 'Qty', 'Entry', 'Exit', 'P&L', 'Hold', 'Reason', 'Status'].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-2xs font-medium text-muted uppercase tracking-wider whitespace-nowrap">{h}</th>
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
                      }`}>{trade.direction}</span>
                    </td>
                    <td className="px-3 py-2">
                      {trade.setup_type ? (
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${setupBadgeCls(trade.setup_type)}`}>
                          {trade.setup_type.replace('_', ' ')}
                        </span>
                      ) : <span className="text-2xs text-muted">{'\u2014'}</span>}
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
                    <td className="px-3 py-2"><PnlCell value={trade.pnl_pct} suffix="%" /></td>
                    <td className="px-3 py-2 text-2xs num text-muted">
                      {trade.hold_minutes !== null
                        ? trade.hold_minutes < 1440 ? `${trade.hold_minutes}m` : `${Math.round(trade.hold_minutes / 1440)}d`
                        : trade.hold_days !== null ? `${trade.hold_days}d` : '—'}
                    </td>
                    <td className="px-3 py-2 text-2xs text-muted font-mono">{trade.exit_reason ?? '—'}</td>
                    <td className="px-3 py-2"><StatusBadge status={trade.status} /></td>
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
