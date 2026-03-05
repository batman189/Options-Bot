import { useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import {
  RefreshCw, AlertTriangle, CheckCircle, Clock,
  Database, Wifi, Server, ShieldAlert, Activity,
  Play, Square, RotateCcw, Zap, Power,
} from 'lucide-react';
import { api } from '../api/client';
import { PageHeader } from '../components/PageHeader';
import { Spinner } from '../components/Spinner';
import type { ErrorLogEntry, TradingProcessInfo } from '../types/api';

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function fmtUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  return `${m}m ${s}s`;
}

function fmtDollars(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD',
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(n);
}

function fmtTimestamp(ts: string): string {
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(ts);
  const d = new Date(hasTimezone ? ts : ts + 'Z');
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

// ─────────────────────────────────────────────
// Connection card
// ─────────────────────────────────────────────

interface ConnectionCardProps {
  icon: React.ElementType;
  name: string;
  connected: boolean;
  detail?: string;
  sub?: string;
}

function ConnectionCard({ icon: Icon, name, connected, detail, sub }: ConnectionCardProps) {
  return (
    <div className={`
      rounded-lg border p-4 flex items-start gap-3
      ${connected ? 'border-profit/20 bg-profit/5' : 'border-loss/20 bg-loss/5'}
    `}>
      <div className={`
        h-9 w-9 rounded-lg flex items-center justify-center flex-shrink-0
        ${connected ? 'bg-profit/10' : 'bg-loss/10'}
      `}>
        <Icon size={16} className={connected ? 'text-profit' : 'text-loss'} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium text-text">{name}</span>
          <div className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full flex-shrink-0 ${
              connected
                ? 'bg-profit shadow-[0_0_6px_#00d68f]'
                : 'bg-loss'
            }`} />
            <span className={`text-xs font-mono ${connected ? 'text-profit' : 'text-loss'}`}>
              {connected ? 'connected' : 'offline'}
            </span>
          </div>
        </div>
        {detail && <p className="text-xs text-muted mt-0.5">{detail}</p>}
        {sub && <p className="text-2xs text-muted/60 font-mono mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Stat row for PDT panel
// ─────────────────────────────────────────────

function StatRow({ label, value, highlight }: {
  label: string;
  value: React.ReactNode;
  highlight?: 'warn' | 'good' | 'neutral';
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border last:border-0">
      <span className="text-xs text-muted">{label}</span>
      <span className={`num text-xs font-medium ${
        highlight === 'warn' ? 'text-loss' :
        highlight === 'good' ? 'text-profit' : 'text-text'
      }`}>
        {value}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────
// Error log entry row
// ─────────────────────────────────────────────

function ErrorRow({ entry }: { entry: ErrorLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const isError = entry.level === 'error';
  const isWarn = entry.level === 'warning';

  return (
    <div
      className={`border-b border-border last:border-0 px-4 py-2.5 cursor-pointer
                  hover:bg-panel/50 transition-colors`}
      onClick={() => setExpanded(v => !v)}
    >
      <div className="flex items-start gap-3">
        {/* Level indicator */}
        <span className={`flex-shrink-0 text-2xs font-mono font-semibold uppercase w-12 mt-0.5 ${
          isError ? 'text-loss' : isWarn ? 'text-training' : 'text-muted'
        }`}>
          {entry.level}
        </span>

        {/* Timestamp */}
        <span className="flex-shrink-0 text-2xs font-mono text-muted whitespace-nowrap mt-0.5">
          {fmtTimestamp(entry.timestamp)}
        </span>

        {/* Message */}
        <div className="flex-1 min-w-0">
          <p className={`text-xs leading-relaxed ${
            expanded ? '' : 'truncate'
          } ${isError ? 'text-loss' : isWarn ? 'text-training' : 'text-muted'}`}>
            {entry.message}
          </p>
          {entry.source && (
            <p className="text-2xs text-muted/60 font-mono mt-0.5">{entry.source}</p>
          )}
        </div>

        {/* Expand hint */}
        {entry.message.length > 80 && (
          <span className="flex-shrink-0 text-2xs text-muted/40 mt-0.5">
            {expanded ? '▲' : '▼'}
          </span>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Trading process row
// ─────────────────────────────────────────────

function TradingProcessRow({ process, onStop, onRestart, busy }: {
  process: TradingProcessInfo;
  onStop: () => void;
  onRestart: () => void;
  busy: boolean;
}) {
  const isRunning = process.status === 'running';
  const isCrashed = process.status === 'crashed';

  return (
    <div className="px-4 py-2.5 flex items-center justify-between hover:bg-panel/30 transition-colors">
      <div className="flex items-center gap-3 min-w-0">
        <span className={`h-2 w-2 rounded-full flex-shrink-0 ${
          isRunning ? 'bg-profit shadow-[0_0_6px_#00d68f] animate-pulse'
            : isCrashed ? 'bg-loss' : 'bg-muted'
        }`} />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-text truncate">{process.profile_name}</span>
            <span className={`text-2xs font-mono ${
              isRunning ? 'text-profit' : isCrashed ? 'text-loss' : 'text-muted'
            }`}>{process.status}</span>
          </div>
          <div className="flex items-center gap-2 text-2xs text-muted font-mono">
            {process.pid && <span>PID {process.pid}</span>}
            {process.uptime_seconds != null && <span>· {fmtUptime(process.uptime_seconds)}</span>}
            {process.started_at && <span>· started {fmtTimestamp(process.started_at)}</span>}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1.5 flex-shrink-0">
        {isRunning && (
          <>
            <button onClick={onRestart} disabled={busy} title="Restart"
              className="p-1.5 rounded text-muted hover:text-gold hover:bg-gold/10
                         disabled:opacity-50 transition-colors">
              <RotateCcw size={12} />
            </button>
            <button onClick={onStop} disabled={busy} title="Stop"
              className="p-1.5 rounded text-muted hover:text-loss hover:bg-loss/10
                         disabled:opacity-50 transition-colors">
              <Square size={12} />
            </button>
          </>
        )}
        {isCrashed && process.exit_reason && (
          <span className="text-2xs text-loss">{process.exit_reason}</span>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Main System Status page
// ─────────────────────────────────────────────

export function System() {
  const qc = useQueryClient();
  const [errorLimit, setErrorLimit] = useState(50);
  const [showQuickStart, setShowQuickStart] = useState(false);
  const [selectedProfiles, setSelectedProfiles] = useState<string[]>([]);

  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ['health'],
    queryFn: api.system.health,
    refetchInterval: 15_000,
    retry: false,
  });

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['system-status'],
    queryFn: api.system.status,
    refetchInterval: 15_000,
    retry: false,
  });

  const { data: pdt, isLoading: pdtLoading } = useQuery({
    queryKey: ['pdt'],
    queryFn: api.system.pdt,
    refetchInterval: 15_000,
    retry: false,
  });

  const { data: errors, isLoading: errorsLoading } = useQuery({
    queryKey: ['system-errors', errorLimit],
    queryFn: () => api.system.errors(errorLimit),
    refetchInterval: 15_000,
  });

  // Trading status + startable profiles
  const { data: tradingStatus, isLoading: tradingLoading } = useQuery({
    queryKey: ['trading-status'],
    queryFn: api.trading.status,
    refetchInterval: 5_000,
    retry: false,
  });

  const { data: startableProfiles } = useQuery({
    queryKey: ['startable-profiles'],
    queryFn: api.trading.startableProfiles,
    refetchInterval: 15_000,
  });

  const invalidateTrading = () => {
    qc.invalidateQueries({ queryKey: ['trading-status'] });
    qc.invalidateQueries({ queryKey: ['system-status'] });
    qc.invalidateQueries({ queryKey: ['startable-profiles'] });
  };

  const startMutation = useMutation({
    mutationFn: (ids: string[]) => api.trading.start(ids),
    onSuccess: () => {
      invalidateTrading();
      setShowQuickStart(false);
      setSelectedProfiles([]);
    },
  });

  const stopMutation = useMutation({
    mutationFn: (ids?: string[]) => api.trading.stop(ids),
    onSuccess: invalidateTrading,
  });

  const restartMutation = useMutation({
    mutationFn: (ids: string[]) => api.trading.restart(ids),
    onSuccess: invalidateTrading,
  });

  function handleRefresh() {
    qc.invalidateQueries({ queryKey: ['health'] });
    qc.invalidateQueries({ queryKey: ['system-status'] });
    qc.invalidateQueries({ queryKey: ['pdt'] });
    qc.invalidateQueries({ queryKey: ['system-errors'] });
    qc.invalidateQueries({ queryKey: ['trading-status'] });
    qc.invalidateQueries({ queryKey: ['startable-profiles'] });
  }

  const isLoading = healthLoading || statusLoading || pdtLoading;
  const errorCount = errors?.filter(e => e.level === 'error').length ?? 0;
  const warnCount = errors?.filter(e => e.level === 'warning').length ?? 0;

  return (
    <div className="space-y-5">
      <PageHeader
        title="System Status"
        subtitle="Connections, PDT tracking, uptime, error log"
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

      {/* ── Trading Control Panel ── */}
      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Power size={14} className="text-muted" />
              <span className="text-xs font-medium text-text">Trading Engine</span>
            </div>
            {tradingStatus && tradingStatus.total_running > 0 && (
              <span className="text-2xs font-mono bg-profit/10 text-profit border border-profit/20 px-1.5 py-0.5 rounded">
                {tradingStatus.total_running} running
              </span>
            )}
            {tradingLoading && <Spinner size="sm" />}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowQuickStart(v => !v)}
              disabled={startMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                         bg-profit/10 text-profit border border-profit/20
                         hover:bg-profit/20 disabled:opacity-50 transition-colors"
            >
              {startMutation.isPending ? <Spinner size="sm" /> : <Zap size={12} />}
              Quick Start
            </button>

            {tradingStatus && tradingStatus.total_running > 0 && (
              <button
                onClick={() => stopMutation.mutate(undefined)}
                disabled={stopMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                           bg-loss/10 text-loss border border-loss/20
                           hover:bg-loss/20 disabled:opacity-50 transition-colors"
              >
                {stopMutation.isPending ? <Spinner size="sm" /> : <Square size={12} />}
                Stop All
              </button>
            )}
          </div>
        </div>

        {/* Quick Start picker */}
        {showQuickStart && startableProfiles && (
          <div className="px-4 py-3 border-b border-border bg-panel/50">
            <div className="text-2xs text-muted uppercase tracking-wider mb-2">
              Select profiles to start
            </div>
            <div className="space-y-1.5 mb-3">
              {startableProfiles.filter(p => !p.is_running).length === 0 ? (
                <p className="text-xs text-muted">
                  No profiles available. All are either running or lack a trained model.
                </p>
              ) : (
                startableProfiles.filter(p => !p.is_running).map(p => (
                  <label key={p.id} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedProfiles.includes(p.id)}
                      onChange={e => {
                        if (e.target.checked) setSelectedProfiles(prev => [...prev, p.id]);
                        else setSelectedProfiles(prev => prev.filter(id => id !== p.id));
                      }}
                      className="rounded border-border"
                    />
                    <span className="text-xs text-text">{p.name}</span>
                    <span className="text-2xs text-muted font-mono uppercase">{p.preset}</span>
                    <span className="text-2xs text-muted font-mono">{p.symbols.join(', ')}</span>
                  </label>
                ))
              )}
            </div>
            {startableProfiles.filter(p => !p.is_running).length > 0 && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => startMutation.mutate(selectedProfiles)}
                  disabled={selectedProfiles.length === 0 || startMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                             bg-profit/10 text-profit border border-profit/20
                             hover:bg-profit/20 disabled:opacity-50 transition-colors"
                >
                  <Play size={11} />
                  Start {selectedProfiles.length} Profile{selectedProfiles.length !== 1 ? 's' : ''}
                </button>
                <button
                  onClick={() => {
                    setSelectedProfiles(startableProfiles.filter(p => !p.is_running).map(p => p.id));
                  }}
                  className="text-2xs text-muted hover:text-gold transition-colors"
                >
                  Select all
                </button>
                <button
                  onClick={() => setShowQuickStart(false)}
                  className="text-2xs text-muted hover:text-text transition-colors ml-auto"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        )}

        {/* Process list */}
        {tradingStatus && tradingStatus.processes.length > 0 ? (
          <div className="divide-y divide-border">
            {tradingStatus.processes.map(proc => (
              <TradingProcessRow
                key={proc.profile_id}
                process={proc}
                onStop={() => stopMutation.mutate([proc.profile_id])}
                onRestart={() => restartMutation.mutate([proc.profile_id])}
                busy={stopMutation.isPending || restartMutation.isPending}
              />
            ))}
          </div>
        ) : (
          <div className="py-8 text-center">
            <Power size={20} className="text-muted mx-auto mb-2" />
            <p className="text-xs text-muted">No trading processes.</p>
            <p className="text-2xs text-muted mt-1">
              Click <span className="text-profit">Quick Start</span> to launch trading.
            </p>
          </div>
        )}

        {/* Mutation error display */}
        {(startMutation.data?.errors?.length ?? 0) > 0 && (
          <div className="px-4 py-2.5 border-t border-loss/20 bg-loss/5">
            {startMutation.data!.errors.map((err, i) => (
              <p key={i} className="text-2xs text-loss font-mono">
                {err.message}
              </p>
            ))}
          </div>
        )}
      </div>

      {/* ── Live check errors (transient, from this status poll) ── */}
      {status?.check_errors && status.check_errors.length > 0 && (
        <div className="rounded-lg border border-loss/30 bg-loss/5 p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={14} className="text-loss" />
            <span className="text-xs font-medium text-loss">
              Status Check Errors ({status.check_errors.length})
            </span>
          </div>
          <div className="space-y-1">
            {status.check_errors.map((err, i) => (
              <p key={i} className="text-2xs font-mono text-muted">{err}</p>
            ))}
          </div>
          <p className="text-2xs text-muted mt-2">
            These errors occurred during this status poll. Shown values may be defaults.
          </p>
        </div>
      )}

      {/* ── Row 1: Connection cards ── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs font-medium uppercase tracking-wider text-muted">Connections</span>
          {isLoading && <Spinner size="sm" />}
        </div>
        <div className="grid grid-cols-3 gap-3">
          <ConnectionCard
            icon={Server}
            name="Backend API"
            connected={!!health}
            detail={health ? `v${health.version} · FastAPI` : 'Cannot reach localhost:8000'}
            sub={health ? `Last checked: ${fmtTimestamp(health.timestamp)}` : undefined}
          />
          <ConnectionCard
            icon={Wifi}
            name="Alpaca"
            connected={status?.alpaca_connected ?? false}
            detail={status?.alpaca_connected
              ? `${status.alpaca_subscription} · ${fmtDollars(status.portfolio_value)} equity`
              : 'Check API key and network'}
            sub="localhost:8000 → api.alpaca.markets"
          />
          <ConnectionCard
            icon={Database}
            name="Theta Terminal"
            connected={status?.theta_terminal_connected ?? false}
            detail={status?.theta_terminal_connected
              ? 'Options data available'
              : 'Start Theta Terminal on localhost:25503'}
            sub="localhost:25503"
          />
        </div>
      </div>

      {/* ── Circuit Breaker Status ── */}
      {status?.circuit_breaker_states && Object.keys(status.circuit_breaker_states).length > 0 && (
        <div className="rounded-lg border border-border bg-surface overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center gap-2">
            <Zap size={14} className="text-muted" />
            <span className="text-xs font-medium text-text">Circuit Breakers</span>
          </div>
          <div className="divide-y divide-border">
            {Object.entries(status.circuit_breaker_states).map(([profileId, cb]) => {
              const thetaState = cb.theta_breaker_state ?? 'unknown';
              const alpacaState = cb.alpaca_breaker_state ?? 'unknown';
              const thetaFails = cb.theta_failure_count ?? 0;
              const lastUpdated = cb.last_updated;
              const stateColor = (s: string) =>
                s === 'open' ? 'text-loss bg-loss/10 border-loss/20'
                : s === 'half_open' ? 'text-training bg-training/10 border-training/20'
                : 'text-profit bg-profit/10 border-profit/20';
              return (
                <div key={profileId} className="px-4 py-2.5 flex items-center justify-between">
                  <span className="text-xs text-muted font-mono truncate max-w-[200px]">
                    {profileId.slice(0, 8)}
                  </span>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5">
                      <span className="text-2xs text-muted">Theta:</span>
                      <span className={`text-2xs font-mono font-medium px-1.5 py-0.5 rounded border ${stateColor(thetaState)}`}>
                        {thetaState.toUpperCase()}
                      </span>
                      {thetaFails > 0 && (
                        <span className="text-2xs text-muted">({thetaFails} fails)</span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-2xs text-muted">Alpaca:</span>
                      <span className={`text-2xs font-mono font-medium px-1.5 py-0.5 rounded border ${stateColor(alpacaState)}`}>
                        {alpacaState.toUpperCase()}
                      </span>
                    </div>
                    {lastUpdated && (
                      <span className="text-2xs text-muted/60 font-mono">
                        {fmtTimestamp(lastUpdated)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Row 2: PDT + Portfolio + Uptime ── */}
      <div className="grid grid-cols-3 gap-4">

        {/* PDT tracking */}
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-center gap-2 mb-3">
            <ShieldAlert size={14} className="text-muted" />
            <span className="text-xs font-medium text-text">PDT Tracking</span>
            {pdtLoading && <Spinner size="sm" />}
          </div>

          {pdt ? (
            <>
              {/* Progress bar */}
              {pdt.is_restricted && (
                <div className="mb-4">
                  <div className="flex items-end justify-between mb-1.5">
                    <span className="text-2xs text-muted">Day trades (rolling 5 days)</span>
                    <span className={`num text-lg font-bold ${
                      pdt.remaining === 0 ? 'text-loss' :
                      pdt.remaining === 1 ? 'text-training' : 'text-text'
                    }`}>
                      {pdt.day_trades_5d} <span className="text-sm font-normal text-muted">/ 3</span>
                    </span>
                  </div>
                  <div className="w-full bg-panel rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all ${
                        pdt.remaining === 0 ? 'bg-loss' :
                        pdt.remaining === 1 ? 'bg-training' : 'bg-profit'
                      }`}
                      style={{ width: `${Math.min((pdt.day_trades_5d / 3) * 100, 100)}%` }}
                    />
                  </div>
                  {pdt.remaining === 0 && (
                    <div className="mt-2 flex items-center gap-1.5 text-2xs text-loss">
                      <AlertTriangle size={11} />
                      Day trade limit reached — new round-trips blocked
                    </div>
                  )}
                </div>
              )}

              <div>
                <StatRow
                  label="Account equity"
                  value={fmtDollars(pdt.equity)}
                  highlight={pdt.equity >= 25000 ? 'good' : 'neutral'}
                />
                <StatRow
                  label="PDT restriction"
                  value={pdt.is_restricted ? 'Active (< $25K)' : 'None (≥ $25K)'}
                  highlight={pdt.is_restricted ? 'warn' : 'good'}
                />
                <StatRow
                  label="Day trades used"
                  value={`${pdt.day_trades_5d} / ${pdt.is_restricted ? '3' : '∞'}`}
                  highlight={pdt.remaining === 0 ? 'warn' : 'neutral'}
                />
                <StatRow
                  label="Remaining"
                  value={pdt.is_restricted ? String(pdt.remaining) : 'Unlimited'}
                  highlight={
                    !pdt.is_restricted ? 'good' :
                    pdt.remaining === 0 ? 'warn' :
                    pdt.remaining === 1 ? 'warn' : 'neutral'
                  }
                />
              </div>
            </>
          ) : (
            <p className="text-xs text-muted text-center py-4">
              {pdtLoading ? 'Loading…' : 'Unable to fetch PDT status'}
            </p>
          )}
        </div>

        {/* Portfolio snapshot */}
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-center gap-2 mb-3">
            <Activity size={14} className="text-muted" />
            <span className="text-xs font-medium text-text">Portfolio Snapshot</span>
            {statusLoading && <Spinner size="sm" />}
          </div>

          {status ? (
            <div>
              <StatRow label="Portfolio value"    value={fmtDollars(status.portfolio_value)} />
              <StatRow label="Active profiles"    value={String(status.active_profiles)} />
              <StatRow
                label="Open positions"
                value={`${status.total_open_positions} / 10`}
                highlight={status.total_open_positions >= 10 ? 'warn' : 'neutral'}
              />
              <StatRow
                label="PDT day trades"
                value={`${status.pdt_day_trades_5d} / ${status.pdt_limit === 999999 ? '∞' : status.pdt_limit}`}
              />
              <StatRow
                label="Alpaca subscription"
                value={status.alpaca_subscription}
              />
            </div>
          ) : (
            <p className="text-xs text-muted text-center py-4">
              {statusLoading ? 'Loading…' : 'Backend offline'}
            </p>
          )}
        </div>

        {/* Uptime + health */}
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-center gap-2 mb-3">
            <Clock size={14} className="text-muted" />
            <span className="text-xs font-medium text-text">Runtime</span>
          </div>

          {status ? (
            <div>
              <div className="mb-4">
                <div className="text-2xs text-muted mb-1">Backend uptime</div>
                <div className="num text-2xl font-bold text-text">
                  {fmtUptime(status.uptime_seconds)}
                </div>
              </div>
              <StatRow label="API version"   value={health?.version ?? '—'} />
              <StatRow label="API host"      value="localhost:8000" />
              <StatRow label="Theta host"    value="localhost:25503" />
              {status.last_error ? (
                <div className="mt-3 rounded border border-loss/20 bg-loss/5 px-2.5 py-2">
                  <div className="flex items-center gap-1.5 mb-1">
                    <AlertTriangle size={11} className="text-loss" />
                    <span className="text-2xs text-loss font-medium">Last Error</span>
                  </div>
                  <p className="text-2xs font-mono text-muted leading-relaxed line-clamp-3">
                    {status.last_error}
                  </p>
                </div>
              ) : (
                <div className="mt-3 flex items-center gap-1.5 text-2xs text-profit">
                  <CheckCircle size={11} />
                  No recent errors
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted text-center py-4">
              {statusLoading ? 'Loading…' : 'Backend offline'}
            </p>
          )}
        </div>
      </div>

      {/* ── Row 3: Error log ── */}
      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className="text-muted" />
              <span className="text-xs font-medium text-text">Error Log</span>
            </div>
            {/* Counts */}
            {errors && errors.length > 0 && (
              <div className="flex items-center gap-2">
                {errorCount > 0 && (
                  <span className="text-2xs font-mono bg-loss/10 text-loss border border-loss/20 px-1.5 py-0.5 rounded">
                    {errorCount} error{errorCount !== 1 ? 's' : ''}
                  </span>
                )}
                {warnCount > 0 && (
                  <span className="text-2xs font-mono bg-training/10 text-training border border-training/20 px-1.5 py-0.5 rounded">
                    {warnCount} warning{warnCount !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {errorsLoading && <Spinner size="sm" />}
            {/* Limit selector */}
            <select
              value={errorLimit}
              onChange={e => setErrorLimit(Number(e.target.value))}
              className="bg-panel border border-border rounded px-2 py-1 text-2xs text-muted
                         focus:outline-none focus:border-gold/50 transition-colors"
            >
              <option value={25}>Last 25</option>
              <option value={50}>Last 50</option>
              <option value={100}>Last 100</option>
              <option value={200}>Last 200</option>
            </select>
          </div>
        </div>

        {errorsLoading && !errors ? (
          <div className="flex items-center justify-center h-24">
            <Spinner />
          </div>
        ) : !errors || errors.length === 0 ? (
          <div className="py-10 text-center">
            <CheckCircle size={20} className="text-profit mx-auto mb-2" />
            <p className="text-xs text-muted">No errors or warnings in the log.</p>
          </div>
        ) : (
          <div className="max-h-96 overflow-y-auto">
            {errors.map((entry, i) => (
              <ErrorRow key={i} entry={entry} />
            ))}
          </div>
        )}

        {/* Load more */}
        {errors && errors.length === errorLimit && (
          <div className="px-4 py-2.5 border-t border-border">
            <button
              onClick={() => setErrorLimit(l => l + 50)}
              className="text-xs text-muted hover:text-gold transition-colors"
            >
              Load more entries…
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
