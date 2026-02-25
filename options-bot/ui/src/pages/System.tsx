import { PageHeader } from '../components/PageHeader';

export function System() {
  return (
    <div>
      <PageHeader
        title="System Status"
        subtitle="Connections, PDT tracking, error log"
      />
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <p className="text-muted text-sm">System status panels load in P3P6.</p>
      </div>
    </div>
  );
}
