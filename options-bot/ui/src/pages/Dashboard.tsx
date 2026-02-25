import { PageHeader } from '../components/PageHeader';

export function Dashboard() {
  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Overview of all profiles and system health"
      />
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <p className="text-muted text-sm">Dashboard widgets load in P3P2.</p>
      </div>
    </div>
  );
}
