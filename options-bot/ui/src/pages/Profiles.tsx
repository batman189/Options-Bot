import { PageHeader } from '../components/PageHeader';

export function Profiles() {
  return (
    <div>
      <PageHeader
        title="Profiles"
        subtitle="Manage trading profiles"
      />
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <p className="text-muted text-sm">Profile list and create/edit load in P3P3.</p>
      </div>
    </div>
  );
}
