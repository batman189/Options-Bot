import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Download, ChevronUp, ChevronDown, ChevronsUpDown,
  Search, X, Filter,
} from 'lucide-react';
import { api } from '../api/client';
import { PageHeader } from '../components/PageHeader';
import { StatusBadge } from '../components/StatusBadge';
import { PnlCell } from '../components/PnlCell';
import { Spinner } from '../components/Spinner';
import type { Trade } from '../types/api';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type SortField =
  | 'entry_date' | 'symbol' | 'direction' | 'strike'
  | 'pnl_pct' | 'pnl_dollars' | 'hold_days' | 'exit_reason' | 'status';

type SortDir = 'asc' | 'desc';

interface Filters {
  profileId: string;
  symbol: string;
  status: string;
  direction: string;
  dateFrom: string;
  dateTo: string;
}

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function fmt(n: number | null, decimals = 2, prefix = '') {
  if (n === null) return '—';
  return `${prefix}${n.toFixed(decimals)}`;
}

function fmtDate(s: string | null) {
  if (!s) return '—';
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(s);
  const ts = hasTimezone ? s : s + 'Z';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
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
        <option value="">All Profiles</option>
        {profiles.map(p => (
          <option key={p.id} value={p.id}>{p.name}</option>
        ))}
      </select>

      {/* Symbol filter */}
      <div className="relative">
        <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" />
        <input
          type="text"
          value={filters.symbol}
          onChange={e => set('symbol', e.target.value.toUpperCase())}
          placeholder="Symbol"
          maxLength={5}
          className="pl-6 pr-2 py-1 bg-panel border border-border rounded text-xs text-text
                     font-mono placeholder:text-muted focus:outline-none focus:border-gold/50
                     transition-colors w-24"
        />
      </div>

      {/* Status filter */}
      <select
        value={filters.status}
        onChange={e => set('status', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text
                   focus:outline-none focus:border-gold/50 transition-colors"
      >
        <option value="">All Statuses</option>
        <option value="open">Open</option>
        <option value="closed">Closed</option>
        <option value="cancelled">Cancelled</option>
      </select>

      {/* Direction filter */}
      <select
        value={filters.direction}
        onChange={e => set('direction', e.target.value)}
        className="bg-panel border border-border rounded px-2 py-1 text-xs text-text
                   focus:outline-none focus:border-gold/50 transition-colors"
      >
        <option value="">All Directions</option>
        <option value="CALL">CALL</option>
        <option value="PUT">PUT</option>
        <option value="LONG">LONG</option>
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

      {/* Reset */}
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

function SummaryRow({ trades }: { trades: Trade[] }) {
  const closed = trades.filter(t => t.status === 'closed');
  const open = trades.filter(t => t.status === 'open');
  const wins = closed.filter(t => (t.pnl_dollars ?? 0) > 0);
  const totalPnl = closed.reduce((s, t) => s + (t.pnl_dollars ?? 0), 0);
  const winRate = closed.length > 0 ? wins.length / closed.length : null;

  return (
    <div className="grid grid-cols-5 gap-3 mb-4">
      {[
        { label: 'Showing', value: String(trades.length), sub: 'trades' },
        { label: 'Open', value: String(open.length), sub: 'positions' },
        { label: 'Closed', value: String(closed.length), sub: 'trades' },
        {
          label: 'Win Rate',
          value: winRate !== null ? `${(winRate * 100).toFixed(1)}%` : '—',
          sub: `${wins.length}W / ${closed.length - wins.length}L`,
          colored: winRate !== null,
          positive: winRate !== null && winRate >= 0.5,
        },
        {
          label: 'Total P&L',
          value: closed.length > 0
            ? `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(0)}`
            : '—',
          sub: 'closed only',
          colored: closed.length > 0,
          positive: totalPnl >= 0,
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
// Main Trade History page
// ─────────────────────────────────────────────

const EMPTY_FILTERS: Filters = {
  profileId: '', symbol: '', status: '', direction: '', dateFrom: '', dateTo: '',
};

export function Trades() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sortField, setSortField] = useState<SortField>('entry_date');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Fetch all trades — client-side filter/sort for responsiveness
  // API filter by profile_id only (reduces payload for multi-profile setups)
  const { data: trades, isLoading } = useQuery({
    queryKey: ['trades-all', filters.profileId],
    queryFn: () => api.trades.list({
      profile_id: filters.profileId || undefined,
      limit: 500,
    }),
    refetchInterval: 30_000,
  });

  // Fetch profile list for the filter dropdown
  const { data: profiles } = useQuery({
    queryKey: ['profiles'],
    queryFn: api.profiles.list,
  });

  // Client-side filter
  const filtered = useMemo(() => {
    if (!trades) return [];
    return trades.filter(t => {
      if (filters.symbol && !t.symbol.includes(filters.symbol)) return false;
      if (filters.status && t.status !== filters.status) return false;
      if (filters.direction && t.direction !== filters.direction) return false;
      if (filters.dateFrom && t.entry_date && t.entry_date < filters.dateFrom) return false;
      if (filters.dateTo && t.entry_date && t.entry_date > filters.dateTo + 'T23:59:59') return false;
      return true;
    });
  }, [trades, filters]);

  // Client-side sort
  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let av: string | number | null = null;
      let bv: string | number | null = null;

      switch (sortField) {
        case 'entry_date':    av = a.entry_date; bv = b.entry_date; break;
        case 'symbol':        av = a.symbol; bv = b.symbol; break;
        case 'direction':     av = a.direction; bv = b.direction; break;
        case 'strike':        av = a.strike; bv = b.strike; break;
        case 'pnl_pct':       av = a.pnl_pct; bv = b.pnl_pct; break;
        case 'pnl_dollars':   av = a.pnl_dollars; bv = b.pnl_dollars; break;
        case 'hold_days':     av = a.hold_days; bv = b.hold_days; break;
        case 'exit_reason':   av = a.exit_reason; bv = b.exit_reason; break;
        case 'status':        av = a.status; bv = b.status; break;
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

  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  // CSV export — calls backend which returns a file download
  function handleExport() {
    const url = api.trades.exportUrl(filters.profileId || undefined);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trades-export-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  }

  const profileList = (profiles ?? []).map(p => ({ id: p.id, name: p.name }));

  return (
    <div>
      <PageHeader
        title="Trade History"
        subtitle="All trades across all profiles"
        actions={
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs
                       border border-border text-muted hover:text-text hover:border-border/60
                       transition-colors"
          >
            <Download size={13} />
            Export CSV
          </button>
        }
      />

      {/* Filter bar */}
      <FilterBar
        filters={filters}
        profiles={profileList}
        onChange={setFilters}
        onReset={() => setFilters(EMPTY_FILTERS)}
        activeCount={activeFilterCount}
      />

      {/* Summary stats */}
      {!isLoading && <SummaryRow trades={sorted} />}

      {/* Table */}
      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-40">
            <Spinner size="lg" />
          </div>
        ) : sorted.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-sm text-muted">
              {activeFilterCount > 0 ? 'No trades match the current filters.' : 'No trades recorded yet.'}
            </p>
            {activeFilterCount > 0 && (
              <button
                onClick={() => setFilters(EMPTY_FILTERS)}
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
                  <ColHeader label="Date"       field="entry_date"  sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <ColHeader label="Symbol"     field="symbol"      sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <ColHeader label="Dir"        field="direction"   sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <ColHeader label="Strike"     field="strike"      sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">Exp</th>
                  <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">Qty</th>
                  <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">Entry $</th>
                  <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">Exit $</th>
                  <ColHeader label="P&L %"      field="pnl_pct"     sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <ColHeader label="P&L $"      field="pnl_dollars" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <ColHeader label="Hold"       field="hold_days"   sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">Pred %</th>
                  <th className="px-3 py-2.5 text-left text-2xs font-medium text-muted uppercase tracking-wider">EV %</th>
                  <ColHeader label="Exit Reason" field="exit_reason" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  <ColHeader label="Status"     field="status"      sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                </tr>
              </thead>
              <tbody>
                {sorted.map(trade => (
                  <tr
                    key={trade.id}
                    className="border-b border-border hover:bg-panel/50 transition-colors"
                  >
                    <td className="px-3 py-2 text-2xs font-mono text-muted whitespace-nowrap">
                      {fmtDate(trade.entry_date)}
                    </td>
                    <td className="px-3 py-2 text-xs font-mono font-medium text-gold">
                      {trade.symbol}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-2xs font-mono font-semibold ${
                        trade.direction === 'PUT' ? 'text-loss' : 'text-profit'
                      }`}>
                        {trade.direction}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-2xs num text-text">
                      ${trade.strike}
                    </td>
                    <td className="px-3 py-2 text-2xs font-mono text-muted whitespace-nowrap">
                      {trade.expiration}
                    </td>
                    <td className="px-3 py-2 text-2xs num text-text">
                      {trade.quantity}
                    </td>
                    <td className="px-3 py-2 text-2xs num text-muted">
                      {fmt(trade.entry_price, 2, '$')}
                    </td>
                    <td className="px-3 py-2 text-2xs num text-muted">
                      {fmt(trade.exit_price, 2, '$')}
                    </td>
                    <td className="px-3 py-2">
                      <PnlCell value={trade.pnl_pct} suffix="%" />
                    </td>
                    <td className="px-3 py-2">
                      <PnlCell value={trade.pnl_dollars} suffix=" USD" />
                    </td>
                    <td className="px-3 py-2 text-2xs num text-muted">
                      {trade.hold_days !== null ? `${trade.hold_days}d` : '—'}
                    </td>
                    <td className="px-3 py-2 text-2xs num text-muted">
                      {fmt(trade.predicted_return, 2)}
                      {trade.predicted_return !== null ? '%' : ''}
                    </td>
                    <td className="px-3 py-2 text-2xs num text-muted">
                      {fmt(trade.ev_at_entry, 1)}
                      {trade.ev_at_entry !== null ? '%' : ''}
                    </td>
                    <td className="px-3 py-2 text-2xs font-mono text-muted">
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

      {/* Row count footer */}
      {!isLoading && sorted.length > 0 && (
        <div className="mt-2 flex items-center justify-between text-2xs text-muted px-1">
          <span>
            {sorted.length} of {trades?.length ?? 0} trades
            {activeFilterCount > 0 ? ' (filtered)' : ''}
          </span>
          <span>Sorted by {sortField.replace('_', ' ')} {sortDir === 'desc' ? '↓' : '↑'}</span>
        </div>
      )}
    </div>
  );
}
