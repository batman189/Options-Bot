import { useQuery } from '@tanstack/react-query';
import { AlertCircle, ExternalLink } from 'lucide-react';
import { api } from '../api/client';
import { Spinner } from './Spinner';
import type { MacroEvent, MacroCatalyst, MacroRegime } from '../types/api';

function ToneBadge({ tone }: { tone: MacroRegime['risk_tone'] }) {
  const map = {
    risk_on:  'bg-profit/10 text-profit border-profit/20',
    risk_off: 'bg-loss/10 text-loss border-loss/20',
    mixed:    'bg-gold/10 text-gold border-gold/20',
    unknown:  'bg-border text-muted border-border',
  };
  return (
    <span className={`text-2xs font-mono font-medium px-1.5 py-0.5 rounded border ${map[tone]}`}>
      {tone}
    </span>
  );
}

function ImpactBadge({ impact }: { impact: MacroEvent['impact_level'] }) {
  const map = {
    HIGH:   'bg-loss/10 text-loss border-loss/20',
    MEDIUM: 'bg-gold/10 text-gold border-gold/20',
    LOW:    'bg-border text-muted border-border',
  };
  return (
    <span className={`text-2xs font-mono font-medium px-1.5 py-0.5 rounded border ${map[impact]}`}>
      {impact}
    </span>
  );
}

function DirectionBadge({ dir }: { dir: MacroCatalyst['direction'] }) {
  const map = {
    bullish: 'bg-profit/10 text-profit border-profit/20',
    bearish: 'bg-loss/10 text-loss border-loss/20',
    neutral: 'bg-border text-muted border-border',
  };
  return (
    <span className={`text-2xs font-mono font-medium px-1.5 py-0.5 rounded border ${map[dir]}`}>
      {dir}
    </span>
  );
}

function formatCountdown(minutes_until: number): string {
  if (minutes_until < 0) return `${Math.abs(minutes_until)}m ago`;
  if (minutes_until < 60) return `in ${minutes_until}m`;
  const h = Math.floor(minutes_until / 60);
  const m = minutes_until % 60;
  return `in ${h}h${m ? `${m}m` : ''}`;
}

export function MacroPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['macro-state'],
    queryFn: () => api.macro.state(),
    refetchInterval: 30_000,
  });

  return (
    <div className="rounded-lg border border-border bg-surface overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertCircle size={14} className="text-muted" />
          <h3 className="text-sm text-text font-medium">Macro Awareness</h3>
          {data?.regime && <ToneBadge tone={data.regime.risk_tone} />}
          {data?.regime?.is_stale && (
            <span className="text-2xs text-muted italic">
              stale — using last known state
            </span>
          )}
        </div>
        {data && (
          <span className="text-2xs text-muted font-mono">
            {data.api_calls_today}/{data.api_cap} calls today
          </span>
        )}
      </div>

      {isLoading && (
        <div className="p-4 flex items-center gap-2 text-2xs text-muted">
          <Spinner size="sm" />
          loading macro state...
        </div>
      )}

      {!isLoading && data && (
        <div className="p-4 space-y-4">
          {/* Upcoming events */}
          <div>
            <div className="text-2xs text-muted uppercase tracking-wider mb-2">
              Upcoming events (next 24h)
            </div>
            {data.events.length === 0 ? (
              <div className="text-2xs text-muted/60">no scheduled events</div>
            ) : (
              <div className="space-y-1.5">
                {data.events.map((ev, i) => (
                  <div key={i} className="flex items-center gap-2 text-2xs">
                    <ImpactBadge impact={ev.impact_level} />
                    <span className="font-mono text-text min-w-[3ch]">{ev.symbol}</span>
                    <span className="font-medium text-text">{ev.event_type}</span>
                    <span className="text-muted font-mono">
                      {formatCountdown(ev.minutes_until)}
                    </span>
                    <a
                      href={ev.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-muted/60 hover:text-gold transition-colors ml-auto"
                      title={ev.source_url}
                    >
                      <ExternalLink size={10} />
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Active catalysts */}
          <div>
            <div className="text-2xs text-muted uppercase tracking-wider mb-2">
              Active catalysts
            </div>
            {data.catalysts.length === 0 ? (
              <div className="text-2xs text-muted/60">no active catalysts</div>
            ) : (
              <div className="space-y-1.5">
                {data.catalysts.map((c, i) => (
                  <div key={i} className="flex items-center gap-2 text-2xs">
                    <DirectionBadge dir={c.direction} />
                    <span className="font-mono text-text min-w-[3ch]">{c.symbol}</span>
                    <span className="text-muted">{c.catalyst_type}</span>
                    <span className="flex-1 text-text/80 truncate" title={c.summary}>
                      {c.summary}
                    </span>
                    <div className="h-1 w-8 bg-border rounded-full overflow-hidden">
                      <div
                        className={`h-full ${c.direction === 'bearish' ? 'bg-loss' : c.direction === 'bullish' ? 'bg-profit' : 'bg-muted'}`}
                        style={{ width: `${Math.round(c.severity * 100)}%` }}
                      />
                    </div>
                    <a
                      href={c.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-muted/60 hover:text-gold transition-colors"
                      title={c.source_url}
                    >
                      <ExternalLink size={10} />
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Risk tone details */}
          {data.regime && (
            <div>
              <div className="text-2xs text-muted uppercase tracking-wider mb-2">
                Risk tone
              </div>
              {data.regime.vix_context && (
                <div className="text-2xs text-text/80 mb-1.5">
                  {data.regime.vix_context}
                </div>
              )}
              {data.regime.major_themes.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {data.regime.major_themes.map((theme, i) => (
                    <span
                      key={i}
                      className="text-2xs bg-panel border border-border text-muted px-1.5 py-0.5 rounded"
                    >
                      {theme}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
