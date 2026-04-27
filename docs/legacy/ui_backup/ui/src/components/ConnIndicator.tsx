interface Props {
  connected: boolean;
  label: string;
}

export function ConnIndicator({ connected, label }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-2 w-2 rounded-full ${connected ? 'bg-profit shadow-[0_0_6px_#00d68f]' : 'bg-loss'}`} />
      <span className="text-sm text-text">{label}</span>
      <span className={`text-xs ${connected ? 'text-profit' : 'text-loss'}`}>
        {connected ? 'connected' : 'offline'}
      </span>
    </div>
  );
}
