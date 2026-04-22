import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Download, ChevronUp, ChevronDown, ChevronsUpDown,
  Filter, X, ChevronRight, FileText,
} from 'lucide-react';
import { api } from '../api/client';
import { PageHeader } from '../components/PageHeader';
import { Spinner } from '../components/Spinner';
import type { V2SignalLogEntry } from '../types/api';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type SortField = 'timestamp' | 'symbol' | 'profile_name' | 'confidence_score' | 'setup_type' | 'entered';
type SortDir = 'asc' | 'desc';

interface Filters {
  profileName: string;
  symbol: string;
  entered: string;
  setupType: string;
  dateFrom: string;
  dateTo: string;
}

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function fmtDatetime(s: string | null) {
  if (!s) return '—';
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(s);
  const ts = hasTimezone ? s : s + 'Z';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function capitalize(s: string | null) {
  if (!s) return '—';
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ');
}

function pctColor(v: number | null): string {
  if (v === null) return 'text-muted';
  if (v >= 0.65) return 'text-profit';
  if (v >= 0.50) return 'text-gold';
  return 'text-muted';
}

function setupBadge(t: string | null) {
  if (!t) return 'bg-border/30 text-muted';
  if (t === 'momentum') return 'bg-blue-500/15 text-blue-400';
  if (t === 'mean_reversion') return 'bg-purple-500/15 text-purple-400';
  if (t === 'catalyst') return 'bg-orange-500/15 text-orange-400';
  return 'bg-border/30 text-muted';
}

function regimeBadge(r: string | null) {
  if (!r) return { cls: 'bg-border/30 text-muted', label: '—' };
  if (r === 'HIGH_VOLATILITY') return { cls: 'bg-red-500/15 text-red-400', label: 'HIGH VOL' };
  if (r === 'TRENDING_UP') return { cls: 'bg-profit/15 text-profit', label: 'TREND ↑' };
  if (r === 'TRENDING_DOWN') return { cls: 'bg-loss/15 text-loss', label: 'TREND ↓' };
  if (r === 'CHOPPY') return { cls: 'bg-border/30 text-muted', label: 'CHOPPY' };
  return { cls: 'bg-border/30 text-muted', label: r };
}

// ─────────────────────────────────────────────
// Sort icon + Column header (reused from V1)
// ─────────────────────────────────────────────

function SortIcon({ field, active, dir }: { field: string; active: string; dir: SortDir }) {
  if (field !== active) return <ChevronsUpDown size={12} className="text-border" />;
  return dir === 'asc'
    ? <ChevronUp size={12} className="text-gold" />
    : <ChevronDown size={12} className="text-gold" />;
}

interface ColHeaderProps {
  label: string;
  field: SortField;
  sortField: SortField;
  sortDir: SortDir;
  onSort: (f: SortField) => void;
}

function ColHeader({ label, field, sortField, sortDir, onSort }: ColHeaderProps) {
  return (
    <th
      className="px-3 py-2.5 text-left cursor-pointer select-none group"
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
// Factor bar (for expanded row)
// ─────────────────────────────────────────────

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
// Filter bar
// ─────────────────────────────────────────────

interface FilterBarProps {
  filters: Filters;
  onChange: (f: Filters) => void;
  onReset: () => void;
  activeCount: number;
}

function FilterBar({ filters, onChange, onReset, activeCount }: FilterBarProps) {
  const set = (key: keyof Filters, val: string) => onChange({ ...filters, [key]: val });

  return (
    <div className="flex flex-wrap items-center gap-2 p-3 rounded-lg border border-border bg-surface mb-4">
      <Filter size={13} className="text-muted flex-shrink-0" />

      <select value={filters.profileName} onChange={e => set('profileName', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text focus:outline-none focus:border-gold/50 transition-colors">
        <option value="">All Profiles</option>
        <option value="momentum">Momentum</option>
        <option value="mean_reversion">Mean Reversion</option>
        <option value="catalyst">Catalyst</option>
      </select>

      <input type="text" value={filters.symbol} onChange={e => set('symbol', e.target.value.toUpperCase())}
        placeholder="Symbol" maxLength={5}
        className="px-2 py-1 bg-panel border border-border rounded text-xs text-text font-mono placeholder:text-muted focus:outline-none focus:border-gold/50 transition-colors w-20" />

      <select value={filters.setupType} onChange={e => set('setupType', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text focus:outline-none focus:border-gold/50 transition-colors">
        <option value="">All Types</option>
        <option value="momentum">Momentum</option>
        <option value="mean_reversion">Mean Reversion</option>
        <option value="catalyst">Catalyst</option>
      </select>

      <select value={filters.entered} onChange={e => set('entered', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text focus:outline-none focus:border-gold/50 transition-colors">
        <option value="">All Decisions</option>
        <option value="yes">Entered</option>
        <option value="no">Skipped</option>
      </select>

      <input type="date" value={filters.dateFrom} onChange={e => set('dateFrom', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text focus:outline-none focus:border-gold/50 transition-colors" />
      <span className="text-2xs text-muted">to</span>
      <input type="date" value={filters.dateTo} onChange={e => set('dateTo', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text focus:outline-none focus:border-gold/50 transition-colors" />

      {activeCount > 0 && (
        <button onClick={onReset}
          className="flex items-center gap-1 px-2 py-1 rounded text-2xs text-muted border border-border hover:text-loss hover:border-loss/30 transition-colors">
          <X size={11} /> Reset ({activeCount})
        </button>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Summary stats row
// ─────────────────────────────────────────────

function SummaryRow({ signals }: { signals: V2SignalLogEntry[] }) {
  const total = signals.length;
  const entered = signals.filter(s => s.entered);
  const entryPct = total > 0 ? (entered.length / total) * 100 : 0;
  const confs = signals.map(s => s.confidence_score).filter((c): c is number => c !== null);
  const avgConf = confs.length > 0 ? confs.reduce((a, b) => a + b, 0) / confs.length : null;

  // Most active setup type
  const setupCounts: Record<string, number> = {};
  signals.forEach(s => { if (s.setup_type) setupCounts[s.setup_type] = (setupCounts[s.setup_type] || 0) + 1; });
  const topSetup = Object.entries(setupCounts).sort((a, b) => b[1] - a[1])[0];

  return (
    <div className="grid grid-cols-4 gap-3 mb-4">
      {[
        { label: 'Total Signals', value: String(total), sub: 'evaluations' },
        {
          label: 'Entered', value: `${entered.length}`,
          sub: `${entryPct.toFixed(1)}% entry rate`,
          colored: entered.length > 0, positive: true,
        },
        {
          label: 'Avg Confidence',
          value: avgConf !== null ? `${(avgConf * 100).toFixed(0)}%` : '—',
          sub: `${confs.length} scored`,
          colored: avgConf !== null, positive: avgConf !== null && avgConf >= 0.5,
        },
        {
          label: 'Top Setup',
          value: topSetup ? capitalize(topSetup[0]) : '—',
          sub: topSetup ? `${topSetup[1]} signals` : 'no data',
        },
      ].map(({ label, value, sub, colored, positive }) => (
        <div key={label} className="rounded border border-border bg-surface px-3 py-2">
          <div className="text-2xs text-muted uppercase tracking-wider mb-0.5">{label}</div>
          <div className={`num text-sm font-semibold ${colored ? (positive ? 'text-profit' : 'text-loss') : 'text-text'}`}>{value}</div>
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
  profileName: '', symbol: '', entered: '', setupType: '', dateFrom: '', dateTo: '',
};

export function SignalLogs() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sortField, setSortField] = useState<SortField>('timestamp');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const { data: signals, isLoading } = useQuery({
    queryKey: ['v2-signal-logs', filters.profileName, filters.symbol,
               filters.entered === 'yes' ? 1 : filters.entered === 'no' ? 0 : undefined],
    queryFn: () => api.v2signals.list({
      profile_name: filters.profileName || undefined,
      symbol: filters.symbol || undefined,
      entered: filters.entered === 'yes' ? 1 : filters.entered === 'no' ? 0 : undefined,
      limit: 500,
    }),
    refetchInterval: 10_000,
  });

  const filtered = useMemo(() => {
    if (!signals) return [];
    return signals.filter(s => {
      if (filters.setupType && s.setup_type !== filters.setupType) return false;
      if (filters.dateFrom && s.timestamp < filters.dateFrom) return false;
      if (filters.dateTo && s.timestamp > filters.dateTo + 'T23:59:59.999Z') return false;
      return true;
    });
  }, [signals, filters]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let av: string | number | boolean | null = null;
      let bv: string | number | boolean | null = null;
      switch (sortField) {
        case 'timestamp':        av = a.timestamp; bv = b.timestamp; break;
        case 'symbol':           av = a.symbol; bv = b.symbol; break;
        case 'profile_name':     av = a.profile_name; bv = b.profile_name; break;
        case 'confidence_score': av = a.confidence_score; bv = b.confidence_score; break;
        case 'setup_type':       av = a.setup_type; bv = b.setup_type; break;
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

  const activeFilterCount = [filters.profileName, filters.symbol, filters.entered, filters.setupType, filters.dateFrom, filters.dateTo].filter(Boolean).length;

  return (
    <div>
      <PageHeader
        title="Signal Logs"
        subtitle="Every V2 scorer evaluation — why the bot traded or didn't"
        actions={
          <div className="flex items-center gap-2">
            <a
              href={api.v2signals.dailySummaryUrl()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                         bg-panel text-text border border-border
                         hover:bg-surface hover:border-gold/30 transition-colors no-underline"
            >
              <FileText size={13} /> Daily Summary
            </a>
            <a
              href={api.v2signals.exportUrl({
                profile_name: filters.profileName || undefined,
                symbol: filters.symbol || undefined,
                entered: filters.entered === 'yes' ? 1 : filters.entered === 'no' ? 0 : undefined,
              })}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
                         bg-gold/10 text-gold border border-gold/30
                         hover:bg-gold/20 transition-colors no-underline"
            >
              <Download size={13} /> Export CSV
            </a>
          </div>
        }
      />

      <FilterBar
        filters={filters}
        onChange={setFilters}
        onReset={() => setFilters(EMPTY_FILTERS)}
        activeCount={activeFilterCount}
      />

      {!isLoading && signals && <SummaryRow signals={sorted} />}

      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-40"><Spinner size="lg" /></div>
        ) : sorted.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-sm text-muted">
              {activeFilterCount > 0 ? 'No signals match the current filters.' : 'No V2 signal logs yet. Run the bot to generate evaluations.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="w-6" />
                  <ColHeader label="Time"       field="timestamp"        sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <ColHeader label="Symbol"     field="symbol"           sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <ColHeader label="Profile"    field="profile_name"     sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <ColHeader label="Setup"      field="setup_type"       sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <ColHeader label="Confidence" field="confidence_score" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">Regime</th>
                  <ColHeader label="Decision"   field="entered"          sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">Trade ID</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map(sig => {
                  const isExpanded = expandedId === sig.id;
                  const rb = regimeBadge(sig.regime);
                  return (
                    <>
                      <tr
                        key={sig.id}
                        onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                        className={`border-b border-border hover:bg-panel/50 transition-colors cursor-pointer ${
                          sig.entered ? 'bg-profit/[0.03]' : ''
                        }`}
                      >
                        <td className="px-1 py-2 text-center">
                          <ChevronRight size={12} className={`text-muted transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                        </td>
                        <td className="px-3 py-2 text-2xs font-mono text-muted whitespace-nowrap">{fmtDatetime(sig.timestamp)}</td>
                        <td className="px-3 py-2 text-xs font-mono font-medium text-gold">{sig.symbol}</td>
                        <td className="px-3 py-2 text-2xs text-text">{capitalize(sig.profile_name)}</td>
                        <td className="px-3 py-2">
                          {sig.setup_type ? (
                            <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${setupBadge(sig.setup_type)}`}>
                              {sig.setup_type.replace('_', ' ')}
                            </span>
                          ) : <span className="text-2xs text-muted">—</span>}
                        </td>
                        <td className={`px-3 py-2 text-2xs num font-medium ${pctColor(sig.confidence_score)}`}>
                          {sig.confidence_score !== null ? `${(sig.confidence_score * 100).toFixed(0)}%` : '—'}
                        </td>
                        <td className="px-3 py-2">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${rb.cls}`}>{rb.label}</span>
                        </td>
                        <td className="px-3 py-2">
                          {sig.entered ? (
                            <span className="inline-block px-1.5 py-0.5 rounded text-2xs font-medium bg-profit/10 text-profit border border-profit/20">YES</span>
                          ) : (
                            <span className="text-2xs text-muted max-w-[200px] truncate inline-block" title={sig.block_reason ?? ''}>
                              {sig.block_reason ?? 'NO'}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-2xs font-mono text-muted">
                          {sig.trade_id ? sig.trade_id.slice(0, 8) + '...' : '—'}
                        </td>
                      </tr>

                      {/* Expanded factor detail row */}
                      {isExpanded && (
                        <tr key={`${sig.id}-detail`} className="border-b border-border bg-panel/30">
                          <td colSpan={9} className="px-6 py-3">
                            <div className="grid grid-cols-2 gap-x-8 gap-y-2 max-w-2xl">
                              <FactorBar name="Signal Clarity" value={sig.signal_clarity} />
                              <FactorBar name="Regime Fit" value={sig.regime_fit} />
                              <FactorBar name="IVR" value={sig.ivr} />
                              {/* Institutional Flow removed in Prompt 25 — factor never implemented. */}
                              <FactorBar name="Historical Perf" value={sig.historical_perf} />
                              <FactorBar name="Sentiment" value={sig.sentiment} />
                              <FactorBar name="Time of Day" value={sig.time_of_day_score} />
                            </div>
                            <div className="mt-3 flex flex-wrap gap-4 text-2xs text-muted">
                              <span>Raw score: <span className="text-text font-medium">{sig.raw_score !== null ? `${(sig.raw_score * 100).toFixed(1)}%` : '—'}</span></span>
                              <span>Capped: <span className="text-text font-medium">{sig.confidence_score !== null ? `${(sig.confidence_score * 100).toFixed(1)}%` : '—'}</span></span>
                              <span>Threshold: <span className="text-text font-medium">{sig.threshold_label ?? '—'}</span></span>
                              <span>Regime: <span className="text-text font-medium">{sig.regime_reason ?? '—'}</span></span>
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

      {!isLoading && sorted.length > 0 && (
        <div className="mt-2 flex items-center justify-between text-2xs text-muted px-1">
          <span>{sorted.length} of {signals?.length ?? 0} signals{activeFilterCount > 0 ? ' (filtered)' : ''}</span>
          <span>Sorted by {sortField.replace(/_/g, ' ')} {sortDir === 'desc' ? '↓' : '↑'}</span>
        </div>
      )}
    </div>
  );
}
