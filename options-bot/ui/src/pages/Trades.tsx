import { PageHeader } from '../components/PageHeader';

export function Trades() {
  return (
    <div>
      <PageHeader
        title="Trade History"
        subtitle="All trades across all profiles"
      />
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <p className="text-muted text-sm">Trade table and filters load in P3P5.</p>
      </div>
    </div>
  );
}
