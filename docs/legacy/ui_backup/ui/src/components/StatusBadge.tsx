interface Props {
  status: string;
}

const STATUS_STYLES: Record<string, string> = {
  created:  'bg-created/10 text-created border-created/20',
  training: 'bg-training/10 text-training border-training/20',
  ready:    'bg-ready/10 text-ready border-ready/20',
  active:   'bg-active/10 text-active border-active/20',
  paused:   'bg-paused/10 text-paused border-paused/20',
  error:    'bg-error/10 text-error border-error/20',
  open:     'bg-active/10 text-active border-active/20',
  closed:    'bg-muted/10 text-muted border-muted/20',
  cancelled: 'bg-muted/20 text-muted border-muted/30',
};

export function StatusBadge({ status }: Props) {
  const style = STATUS_STYLES[status] ?? 'bg-muted/10 text-muted border-muted/20';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-2xs font-mono font-medium uppercase tracking-widest rounded border ${style}`}>
      {status}
    </span>
  );
}
