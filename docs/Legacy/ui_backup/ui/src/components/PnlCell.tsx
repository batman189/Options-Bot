interface Props {
  value: number | null;
  suffix?: string;
  className?: string;
}

export function PnlCell({ value, suffix = '', className = '' }: Props) {
  if (value == null) return <span className="text-muted num">—</span>;
  const positive = value >= 0;
  return (
    <span className={`num font-medium ${positive ? 'text-profit' : 'text-loss'} ${className}`}>
      {positive ? '+' : ''}{value.toFixed(2)}{suffix}
    </span>
  );
}
