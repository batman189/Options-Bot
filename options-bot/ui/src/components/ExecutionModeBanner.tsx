// Shadow Mode banner — renders an unmissable strip above the main
// content when the backend reports EXECUTION_MODE=shadow. The worst
// failure mode this guards against is an operator thinking they're
// live-trading while in shadow (or vice versa). The banner is
// deliberately loud: full-width, high-contrast amber, always
// visible at the top of every page.
//
// Mode is immutable for the process lifetime — the query uses
// Infinity staleTime and does NOT refetch. To see a mode change,
// the operator must reload the page after restarting the backend.

import { useQuery } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { api } from '../api/client';

export function ExecutionModeBanner() {
  const { data } = useQuery({
    queryKey: ['execution', 'mode'],
    queryFn: api.execution.mode,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  });

  if (!data || data.mode !== 'shadow') return null;

  return (
    <div
      role="alert"
      className="w-full bg-amber-600 text-white border-b-2 border-amber-800 py-2 px-6 flex items-center gap-3 shadow-lg"
    >
      <AlertTriangle size={20} className="flex-shrink-0" />
      <div className="flex-1">
        <span className="font-bold text-sm tracking-wide uppercase">
          SHADOW MODE
        </span>
        <span className="ml-3 text-sm">
          Orders are simulated locally against live quotes. NO trades
          are being submitted to Alpaca.
          {data.slippage_pct > 0 && (
            <span className="ml-2 opacity-90">
              Slippage: {data.slippage_pct.toFixed(2)}%.
            </span>
          )}
        </span>
      </div>
      <span className="font-mono text-xs px-2 py-0.5 bg-amber-900/40 rounded border border-amber-800">
        EXECUTION_MODE=shadow
      </span>
    </div>
  );
}
