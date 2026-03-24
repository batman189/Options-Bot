import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Download, ChevronUp, ChevronDown, ChevronsUpDown,
  Filter, X,
} from 'lucide-react';
import { api } from '../api/client';
import { PageHeader } from '../components/PageHeader';
import { Spinner } from '../components/Spinner';
import type { SignalLogEntry } from '../types/api';

// ─────────────────────────────────────────────
// Step name mapping (entry steps 1-12)
// ─────────────────────────────────────────────

const STEP_NAMES: Record<string, string> = {
  '0': 'Pre-check',
  '1': 'No price',
  '1.1': 'Cooldown',
  '1.5': 'VIX gate',
  '1.6': 'GEX regime',
  '2': 'Bars',
  '3': 'Features',
  '4': 'Options',
  '5': 'Prediction',
  '6': 'Threshold',
  '7': 'Direction',
  '8': 'PDT',
  '8.5': 'Implied move',
  '8.7': 'Earnings',
  '9': 'EV filter',
  '9.5': 'Liquidity',
  '9.7': 'Delta limit',
  '10': 'Position size',
  '11': 'Order',
  '12': 'DB log',
};

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type SortField =
  | 'timestamp' | 'symbol' | 'underlying_price'
  | 'predicted_return' | 'step_stopped_at' | 'entered';

type SortDir = 'asc' | 'desc';

interface Filters {
  profileId: string;
  entered: string;     // '' | 'yes' | 'no'
  dateFrom: string;
  dateTo: string;
}

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function fmt(n: number | null | undefined, decimals = 2, prefix = '') {
  if (n === null || n === undefined) return '—';
  return `${prefix}${n.toFixed(decimals)}`;
}

function fmtDatetime(s: string | null) {
  if (!s) return '—';
  // If the timestamp already has timezone info (Z, +HH:MM, or -HH:MM offset), use as-is.
  // Otherwise append Z to treat as UTC.
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(s);
  const ts = hasTimezone ? s : s + 'Z';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

// ─────────────────────────────────────────────
// Sort icon
// ─────────────────────────────────────────────

function SortIcon({ field, active, dir }: { field: string; active: string; dir: SortDir }) {
  if (field !== active) return <ChevronsUpDown size={12} className="text-border" />;
  return dir === 'asc'
    ? <ChevronUp size={12} className="text-gold" />
    : <ChevronDown size={12} className="text-gold" />;
}

// ─────────────────────────────────────────────
// Column header with sort
// ─────────────────────────────────────────────

interface ColHeaderProps {
  label: string;
  field: SortField;
  sortField: SortField;
  sortDir: SortDir;
  onSort: (f: SortField) => void;
  className?: string;
}

function ColHeader({ label, field, sortField, sortDir, onSort, className = '' }: ColHeaderProps) {
  return (
    <th
      className={`px-3 py-2.5 text-left cursor-pointer select-none group ${className}`}
      onClick={() => onSort(field)}
    >
      <div className="flex items-center gap-1 text-2xs font-medium text-muted uppercase tracking-wider
                      group-hover:text-text transition-colors">
        {label}
        <SortIcon field={field} active={sortField} dir={sortDir} />
      </div>
    </th>
  );
}

// ─────────────────────────────────────────────
// Filter bar
// ─────────────────────────────────────────────

interface FilterBarProps {
  filters: Filters;
  profiles: { id: string; name: string }[];
  onChange: (f: Filters) => void;
  onReset: () => void;
  activeCount: number;
}

function FilterBar({ filters, profiles, onChange, onReset, activeCount }: FilterBarProps) {
  const set = (key: keyof Filters, val: string) => onChange({ ...filters, [key]: val });

  return (
    <div className="flex flex-wrap items-center gap-2 p-3 rounded-lg border border-border bg-surface mb-4">
      <Filter size={13} className="text-muted flex-shrink-0" />

      {/* Profile filter */}
      <select
        value={filters.profileId}
        onChange={e => set('profileId', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text
                   focus:outline-none focus:border-gold/50 transition-colors"
      >
        {profiles.length === 0 && <option value="">No profiles</option>}
        {profiles.length > 1 && <option value="">All Profiles</option>}
        {profiles.map(p => (
          <option key={p.id} value={p.id}>{p.name}</option>
        ))}
      </select>

      {/* Entered filter */}
      <select
        value={filters.entered}
        onChange={e => set('entered', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text
                   focus:outline-none focus:border-gold/50 transition-colors"
      >
        <option value="">All Decisions</option>
        <option value="yes">Entered</option>
        <option value="no">Skipped</option>
      </select>

      {/* Date from */}
      <input
        type="date"
        value={filters.dateFrom}
        onChange={e => set('dateFrom', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text
                   focus:outline-none focus:border-gold/50 transition-colors"
      />
      <span className="text-2xs text-muted">to</span>
      <input
        type="date"
        value={filters.dateTo}
        onChange={e => set('dateTo', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text
                   focus:outline-none focus:border-gold/50 transition-colors"
      />

      {/* Reset — only count non-profileId filters */}
      {activeCount > 0 && (
        <button
          onClick={onReset}
          className="flex items-center gap-1 px-2 py-1 rounded text-2xs text-muted
                     border border-border hover:text-loss hover:border-loss/30 transition-colors"
        >
          <X size={11} />
          Reset ({activeCount})
        </button>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Summary stats row
// ─────────────────────────────────────────────

function SummaryRow({ signals }: { signals: SignalLogEntry[] }) {
  const total = signals.length;
  const entered = signals.filter(s => s.entered);
  const skipped = signals.filter(s => !s.entered);
  const entryPct = total > 0 ? (entered.length / total) * 100 : 0;
  const returns = signals
    .map(s => s.predicted_return)
    .filter((r): r is number => r !== null && r !== undefined);
  const avgReturn = returns.length > 0
    ? returns.reduce((a, b) => a + b, 0) / returns.length
    : null;
  // Detect if signals are from classifier models (confidence -1..+1 vs return %)
  const isClassifier = signals.some(s =>
    ['ScalpPredictor', 'SwingClassifierPredictor'].includes(s.predictor_type ?? '')
  );

  return (
    <div className="grid grid-cols-4 gap-3 mb-4">
      {[
        { label: 'Total Signals', value: String(total), sub: 'iterations' },
        {
          label: 'Entered',
          value: `${entered.length}`,
          sub: `${entryPct.toFixed(1)}% entry rate`,
          colored: entered.length > 0,
          positive: true,
        },
        { label: 'Skipped', value: String(skipped.length), sub: 'no trade' },
        {
          label: isClassifier ? 'Avg Confidence' : 'Avg Predicted',
          value: avgReturn !== null
            ? isClassifier
              ? `${avgReturn >= 0 ? '+' : ''}${(avgReturn * 100).toFixed(0)}%`
              : `${avgReturn >= 0 ? '+' : ''}${avgReturn.toFixed(2)}%`
            : '—',
          sub: `${returns.length} predictions`,
          colored: avgReturn !== null,
          positive: avgReturn !== null && avgReturn >= 0,
        },
      ].map(({ label, value, sub, colored, positive }) => (
        <div key={label} className="rounded border border-border bg-surface px-3 py-2">
          <div className="text-2xs text-muted uppercase tracking-wider mb-0.5">{label}</div>
          <div className={`num text-sm font-semibold ${
            colored ? (positive ? 'text-profit' : 'text-loss') : 'text-text'
          }`}>
            {value}
          </div>
          {sub && <div className="text-2xs text-muted">{sub}</div>}
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────
// Main Signal Logs page
// ─────────────────────────────────────────────

const EMPTY_FILTERS: Filters = {
  profileId: '', entered: '', dateFrom: '', dateTo: '',
};

export function SignalLogs() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sortField, setSortField] = useState<SortField>('timestamp');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Fetch profile list for the filter dropdown
  const { data: profiles, isLoading: profilesLoading } = useQuery({
    queryKey: ['profiles'],
    queryFn: api.profiles.list,
  });

  // When "All Profiles" is selected (empty string), activeProfileId stays empty.
  // Default to first profile only if no profiles dropdown selection has been made yet.
  const activeProfileId = filters.profileId || (profiles && profiles.length === 1 ? profiles[0].id : filters.profileId);

  // Fetch signal logs — when a single profile is selected, fetch from that profile.
  // When "All Profiles" is selected, fetch from each profile and merge.
  const { data: signals, isLoading } = useQuery({
    queryKey: ['signal-logs', activeProfileId || 'all', profiles?.map(p => p.id)],
    queryFn: async () => {
      if (activeProfileId) {
        return api.signals.list(activeProfileId, 500);
      }
      // "All Profiles" — fetch from each and merge
      if (!profiles || profiles.length === 0) return [];
      const results = await Promise.all(
        profiles.map(p => api.signals.list(p.id, 500).catch(() => [] as SignalLogEntry[]))
      );
      return results.flat().sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, 500);
    },
    enabled: !!activeProfileId || (profiles ?? []).length > 0,
    refetchInterval: 10_000,
  });

  // Client-side filter
  const filtered = useMemo(() => {
    if (!signals) return [];
    return signals.filter(s => {
      if (filters.entered === 'yes' && !s.entered) return false;
      if (filters.entered === 'no' && s.entered) return false;
      if (filters.dateFrom && s.timestamp < filters.dateFrom) return false;
      if (filters.dateTo && s.timestamp > filters.dateTo + 'T23:59:59.999Z') return false;
      return true;
    });
  }, [signals, filters]);

  // Client-side sort
  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let av: string | number | boolean | null = null;
      let bv: string | number | boolean | null = null;

      switch (sortField) {
        case 'timestamp':        av = a.timestamp; bv = b.timestamp; break;
        case 'symbol':           av = a.symbol; bv = b.symbol; break;
        case 'underlying_price': av = a.underlying_price; bv = b.underlying_price; break;
        case 'predicted_return': av = a.predicted_return; bv = b.predicted_return; break;
        case 'step_stopped_at':  av = a.step_stopped_at; bv = b.step_stopped_at; break;
        case 'entered':          av = a.entered ? 1 : 0; bv = b.entered ? 1 : 0; break;
      }

      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;

      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [filtered, sortField, sortDir]);

  function handleSort(field: SortField) {
    if (field === sortField) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('desc'); }
  }

  // Count active filters (exclude profileId since it's always set)
  const activeFilterCount = [filters.entered, filters.dateFrom, filters.dateTo]
    .filter(Boolean).length;

  function handleReset() {
    setFilters({ ...EMPTY_FILTERS, profileId: filters.profileId });
  }

  function handleExport() {
    const url = api.signals.exportUrl(activeProfileId || undefined);
    const a = document.createElement('a');
    a.href = url;
    a.download = `signal-logs-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  const profileList = (profiles ?? []).map(p => ({ id: p.id, name: p.name }));

  return (
    <div>
      <PageHeader
        title="Signal Logs"
        subtitle="Every trading iteration decision — why the bot traded or didn't"
        actions={
          <button
            onClick={handleExport}
            disabled={!signals || signals.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs
                       border border-border text-muted hover:text-text hover:border-border/60
                       transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Download size={13} />
            Export CSV
          </button>
        }
      />

      {/* Filter bar */}
      <FilterBar
        filters={{ ...filters, profileId: activeProfileId }}
        profiles={profileList}
        onChange={f => setFilters(f)}
        onReset={handleReset}
        activeCount={activeFilterCount}
      />

      {/* Summary stats */}
      {!isLoading && signals && <SummaryRow signals={sorted} />}

      {/* Profiles still loading */}
      {profilesLoading && (
        <div className="flex items-center justify-center h-40">
          <Spinner size="lg" />
        </div>
      )}

      {/* No profiles exist (only after profiles query has resolved) */}
      {!profilesLoading && (profiles ?? []).length === 0 && (
        <div className="rounded-lg border border-border bg-surface py-16 text-center">
          <p className="text-sm text-muted">No profiles found. Create a profile to see signal logs.</p>
        </div>
      )}

      {/* Table */}
      {!profilesLoading && (profiles ?? []).length > 0 && (
        <div className="rounded-lg border border-border bg-surface overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center h-40">
              <Spinner size="lg" />
            </div>
          ) : sorted.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-sm text-muted">
                {activeFilterCount > 0
                  ? 'No signals match the current filters.'
                  : 'No signal logs recorded yet. Start trading to see decisions here.'}
              </p>
              {activeFilterCount > 0 && (
                <button
                  onClick={handleReset}
                  className="mt-2 text-xs text-gold hover:text-gold/80 transition-colors"
                >
                  Clear filters
                </button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <ColHeader label="Time"      field="timestamp"        sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <ColHeader label="Symbol"    field="symbol"           sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <ColHeader label="Price"     field="underlying_price" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <ColHeader label="Predicted"  field="predicted_return" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">Predictor</th>
                    <ColHeader label="Stopped At" field="step_stopped_at" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">Reason</th>
                    <ColHeader label="Entered"    field="entered"         sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">Trade ID</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map(signal => (
                    <tr
                      key={signal.id}
                      className={`border-b border-border hover:bg-panel/50 transition-colors ${
                        signal.entered ? 'bg-profit/[0.03]' : ''
                      }`}
                    >
                      <td className="px-3 py-2 text-2xs font-mono text-muted whitespace-nowrap">
                        {fmtDatetime(signal.timestamp)}
                      </td>
                      <td className="px-3 py-2 text-xs font-mono font-medium text-gold">
                        {signal.symbol}
                      </td>
                      <td className="px-3 py-2 text-2xs num text-text">
                        {fmt(signal.underlying_price, 2, '$')}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`text-2xs num font-medium ${
                          signal.predicted_return !== null && signal.predicted_return !== undefined
                            ? signal.predicted_return >= 0 ? 'text-profit' : 'text-loss'
                            : 'text-muted'
                        }`}>
                          {signal.predicted_return !== null && signal.predicted_return !== undefined
                            ? ['ScalpPredictor', 'SwingClassifierPredictor'].includes(signal.predictor_type ?? '')
                              ? `${signal.predicted_return >= 0 ? '+' : ''}${(signal.predicted_return * 100).toFixed(0)}% conf`
                              : `${signal.predicted_return >= 0 ? '+' : ''}${signal.predicted_return.toFixed(2)}%`
                            : '—'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-2xs font-mono text-muted">
                        {signal.predictor_type ?? '—'}
                      </td>
                      <td className="px-3 py-2 text-2xs font-mono text-muted">
                        {signal.step_stopped_at !== null && signal.step_stopped_at !== undefined
                          ? `${signal.step_stopped_at}. ${STEP_NAMES[String(signal.step_stopped_at)] ?? '?'}`
                          : signal.entered ? '✓ All passed' : '—'}
                      </td>
                      <td className="px-3 py-2 text-2xs text-muted max-w-[240px] truncate" title={signal.stop_reason ?? ''}>
                        {signal.stop_reason ?? (signal.entered ? 'Trade entered' : '—')}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`inline-block px-1.5 py-0.5 rounded text-2xs font-medium ${
                          signal.entered
                            ? 'bg-profit/10 text-profit border border-profit/20'
                            : 'bg-panel text-muted border border-border'
                        }`}>
                          {signal.entered ? 'YES' : 'NO'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-2xs font-mono text-muted">
                        {signal.trade_id ? signal.trade_id.slice(0, 8) + '...' : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Row count footer */}
      {!isLoading && sorted.length > 0 && (
        <div className="mt-2 flex items-center justify-between text-2xs text-muted px-1">
          <span>
            {sorted.length} of {signals?.length ?? 0} signals
            {activeFilterCount > 0 ? ' (filtered)' : ''}
          </span>
          <span>Sorted by {sortField.replace(/_/g, ' ')} {sortDir === 'desc' ? '↓' : '↑'}</span>
        </div>
      )}
    </div>
  );
}
