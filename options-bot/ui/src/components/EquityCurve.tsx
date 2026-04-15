import { useQuery } from '@tanstack/react-query';
import {
  ComposedChart, Line, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine, Cell,
} from 'recharts';
import { api } from '../api/client';
import { Spinner } from './Spinner';

function fmtDate(s: string) {
  const d = new Date(s.endsWith('Z') ? s : s + 'Z');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-panel border border-border rounded px-3 py-2 text-xs">
      <div className="text-muted mb-1">{String(d.timestamp ?? '').slice(0, 16)}</div>
      <div className="font-mono">{String(d.symbol)} <span className="text-muted">{String(d.setup_type)}</span></div>
      <div className={Number(d.pnl_dollars) >= 0 ? 'text-profit' : 'text-loss'}>
        Trade: ${Number(d.pnl_dollars).toFixed(2)}
      </div>
      <div className="text-text font-medium">Total: ${Number(d.cumulative_pnl).toFixed(2)}</div>
    </div>
  );
}

export function EquityCurve() {
  const { data, isLoading } = useQuery({
    queryKey: ['equity-curve'],
    queryFn: () => api.trades.equityCurve(30),
    refetchInterval: 60_000,
  });

  if (isLoading) return <div className="flex justify-center py-8"><Spinner size="lg" /></div>;
  if (!data || data.points.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-surface px-4 py-8 text-center">
        <p className="text-sm text-muted">No closed trades yet. The equity curve appears after the first trade closes.</p>
      </div>
    );
  }

  const chartData = data.points.map(p => ({
    ...p,
    date: fmtDate(p.timestamp),
    barColor: p.pnl_dollars >= 0 ? 'var(--color-profit)' : 'var(--color-loss)',
  }));

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text">Equity Curve</h3>
        <span className={`text-sm font-mono font-semibold ${data.total_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
          ${data.total_pnl.toFixed(2)} ({data.trade_count} trades)
        </span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.3} />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--color-muted)' }} />
          <YAxis tick={{ fontSize: 10, fill: 'var(--color-muted)' }} tickFormatter={v => `$${v}`} />
          <ReferenceLine y={0} stroke="var(--color-border)" />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="pnl_dollars" opacity={0.5}>
            {chartData.map((entry, idx) => (
              <Cell key={idx} fill={entry.pnl_dollars >= 0 ? '#22c55e' : '#ef4444'} />
            ))}
          </Bar>
          <Line type="monotone" dataKey="cumulative_pnl" stroke="var(--color-profit)"
            strokeWidth={2} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
