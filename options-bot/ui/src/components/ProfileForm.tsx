import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, Plus } from 'lucide-react';
import { api } from '../api/client';
import { Spinner } from './Spinner';
import type { Profile } from '../types/api';

function ConfigSlider({
  label, value, onChange, min, max, step, unit, hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number; max: number; step: number;
  unit: string;
  hint: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-2xs text-muted">{label}</span>
        <span className="num text-2xs text-text font-medium">
          {value}{unit}
        </span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full h-1 bg-border rounded-full appearance-none cursor-pointer
                   [&::-webkit-slider-thumb]:appearance-none
                   [&::-webkit-slider-thumb]:w-3
                   [&::-webkit-slider-thumb]:h-3
                   [&::-webkit-slider-thumb]:rounded-full
                   [&::-webkit-slider-thumb]:bg-gold
                   [&::-webkit-slider-thumb]:cursor-pointer"
      />
      <p className="text-2xs text-muted/60 mt-0.5">{hint}</p>
    </div>
  );
}

interface Props {
  /** Pass existing profile to edit. Omit for create. */
  profile?: Profile;
  onClose: () => void;
}

const PRESETS = ['swing', 'general', 'scalp', 'otm_scalp', 'iron_condor'] as const;

const PRESET_DESCRIPTIONS: Record<string, string> = {
  swing:         'Mean-reversion options trades. 7-45 DTE. Hold up to 7 days.',
  general:       'Trend-following options trades. 21-60 DTE. Hold up to 21 days.',
  scalp:         '0DTE intraday scalping on SPY. 1-min bars. Same-day exit. Requires $25K+ equity.',
  otm_scalp:     '0DTE far OTM gamma scalping. Buys cheap contracts ($0.05-$1.50), targets 300%+ on directional moves.',
  iron_condor:   '0DTE iron condor premium selling. Sells credit spreads when GEX regime is favorable. Theta-positive.',
};

export function ProfileForm({ profile, onClose }: Props) {
  const qc = useQueryClient();
  const isEdit = !!profile;

  const [name, setName] = useState(profile?.name ?? '');
  const [preset, setPreset] = useState<string>(profile?.preset ?? 'swing');
  const [symbols, setSymbols] = useState<string[]>(profile?.symbols ?? ['TSLA']);
  const [symbolInput, setSymbolInput] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Config overrides — numeric risk params
  const [maxPositionPct, setMaxPositionPct] = useState<number>(
    (profile?.config?.max_position_pct as number) ?? 20
  );
  const [maxContracts, setMaxContracts] = useState<number>(
    (profile?.config?.max_contracts as number) ?? 5
  );
  const [maxConcurrent, setMaxConcurrent] = useState<number>(
    (profile?.config?.max_concurrent_positions as number) ?? 3
  );
  const [maxDailyTrades, setMaxDailyTrades] = useState<number>(
    (profile?.config?.max_daily_trades as number) ?? 5
  );
  const [maxDailyLossPct, setMaxDailyLossPct] = useState<number>(
    (profile?.config?.max_daily_loss_pct as number) ?? 10
  );
  const [minConfidence, setMinConfidence] = useState<number>(
    (profile?.config?.min_confidence as number) ?? 0.60
  );
  const [profitTarget, setProfitTarget] = useState<number>(
    (profile?.config?.profit_target_pct as number) ?? (preset === 'scalp' ? 20 : preset === 'otm_scalp' ? 300 : 50)
  );
  const [stopLoss, setStopLoss] = useState<number>(
    (profile?.config?.stop_loss_pct as number) ?? (preset === 'scalp' ? 15 : preset === 'otm_scalp' ? 80 : 30)
  );
  const [showAdvanced, setShowAdvanced] = useState(false);

  const createMutation = useMutation({
    mutationFn: () => api.profiles.create({
      name: name.trim(),
      preset,
      symbols,
      config_overrides: {
        max_position_pct: maxPositionPct,
        max_contracts: maxContracts,
        max_concurrent_positions: maxConcurrent,
        max_daily_trades: maxDailyTrades,
        max_daily_loss_pct: maxDailyLossPct,
        profit_target_pct: profitTarget,
        stop_loss_pct: stopLoss,
        ...((preset === 'scalp' || preset === 'otm_scalp' || preset === 'iron_condor') ? { min_confidence: minConfidence } : {}),
      },
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profiles'] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const updateMutation = useMutation({
    mutationFn: () => api.profiles.update(profile!.id, {
      name: name.trim(),
      symbols,
      config_overrides: {
        max_position_pct: maxPositionPct,
        max_contracts: maxContracts,
        max_concurrent_positions: maxConcurrent,
        max_daily_trades: maxDailyTrades,
        max_daily_loss_pct: maxDailyLossPct,
        profit_target_pct: profitTarget,
        stop_loss_pct: stopLoss,
        ...((preset === 'scalp' || preset === 'otm_scalp' || preset === 'iron_condor') ? { min_confidence: minConfidence } : {}),
      },
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profiles'] });
      qc.invalidateQueries({ queryKey: ['profile', profile!.id] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  function addSymbol() {
    const sym = symbolInput.trim().toUpperCase();
    if (!sym) return;
    if (symbols.includes(sym)) { setSymbolInput(''); return; }
    setSymbols([...symbols, sym]);
    setSymbolInput('');
  }

  function removeSymbol(sym: string) {
    if (symbols.length <= 1) return; // must have at least 1
    setSymbols(symbols.filter(s => s !== sym));
  }

  // Check if form has been modified from initial state
  const isDirty = (() => {
    const origName = profile?.name ?? '';
    const origSymbols = profile?.symbols ?? ['TSLA'];
    if (name !== origName) return true;
    if (JSON.stringify(symbols) !== JSON.stringify(origSymbols)) return true;
    if (maxPositionPct !== ((profile?.config?.max_position_pct as number) ?? 20)) return true;
    if (maxContracts !== ((profile?.config?.max_contracts as number) ?? 5)) return true;
    if (maxConcurrent !== ((profile?.config?.max_concurrent_positions as number) ?? 3)) return true;
    if (maxDailyTrades !== ((profile?.config?.max_daily_trades as number) ?? 5)) return true;
    if (maxDailyLossPct !== ((profile?.config?.max_daily_loss_pct as number) ?? 10)) return true;
    return false;
  })();

  function handleBackdropClose() {
    if (isDirty) {
      if (!window.confirm('You have unsaved changes. Discard them?')) return;
    }
    onClose();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) { setError('Name is required.'); return; }
    if (symbols.length === 0) { setError('At least one symbol is required.'); return; }
    if (isEdit) updateMutation.mutate();
    else createMutation.mutate();
  }

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) handleBackdropClose(); }}
    >
      <div className="w-full max-w-md bg-surface border border-border rounded-xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-sm font-semibold text-text">
            {isEdit ? 'Edit Profile' : 'New Profile'}
          </h2>
          <button onClick={onClose} className="text-muted hover:text-text transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4">
          {/* Name */}
          <div>
            <label className="block text-xs text-muted mb-1.5">Profile Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. TSLA Swing"
              className="w-full bg-panel border border-border rounded px-3 py-2 text-sm text-text
                         placeholder:text-muted focus:outline-none focus:border-gold/50 transition-colors"
            />
          </div>

          {/* Preset — only on create */}
          {!isEdit && (
            <div>
              <label className="block text-xs text-muted mb-1.5">Strategy Preset</label>
              <div className="grid grid-cols-3 gap-2">
                {PRESETS.map(p => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => {
                      setPreset(p);
                      if ((p === 'scalp' || p === 'otm_scalp' || p === 'iron_condor') && symbols.length <= 1 && (symbols[0] === 'TSLA' || symbols.length === 0)) {
                        setSymbols(['SPY']);
                      }
                    }}
                    className={`text-left px-3 py-2.5 rounded border transition-colors
                      ${preset === p
                        ? 'border-gold/40 bg-gold/5 text-text'
                        : 'border-border bg-panel text-muted hover:border-border/60'}`}
                  >
                    <div className="text-xs font-medium capitalize mb-0.5">{p}</div>
                    <div className="text-2xs text-muted leading-relaxed">
                      {PRESET_DESCRIPTIONS[p]}
                    </div>
                  </button>
                ))}
              </div>
              {(preset === 'scalp' || preset === 'otm_scalp' || preset === 'iron_condor') && (
                <div className="mt-2 px-3 py-2 rounded bg-gold/5 border border-gold/20 text-2xs text-gold">
                  {preset === 'otm_scalp' ? 'OTM scalp' : 'Scalp'} requires $25,000+ portfolio equity for unlimited day trades (PDT rule).
                  Positions are auto-closed by 3:45 PM ET daily.
                </div>
              )}
            </div>
          )}

          {/* Symbols */}
          <div>
            <label className="block text-xs text-muted mb-1.5">Symbols</label>
            <div className="flex flex-wrap gap-1.5 mb-2 min-h-[28px]">
              {symbols.map(sym => (
                <span key={sym} className="inline-flex items-center gap-1 font-mono text-xs
                                           bg-gold/5 border border-gold/20 text-gold
                                           px-2 py-0.5 rounded">
                  {sym}
                  <button
                    type="button"
                    onClick={() => removeSymbol(sym)}
                    className="text-gold/50 hover:text-loss transition-colors ml-0.5"
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={symbolInput}
                onChange={e => setSymbolInput(e.target.value.toUpperCase())}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSymbol(); } }}
                placeholder="e.g. NVDA"
                maxLength={5}
                className="flex-1 bg-panel border border-border rounded px-3 py-1.5 text-sm
                           text-text font-mono placeholder:text-muted
                           focus:outline-none focus:border-gold/50 transition-colors uppercase"
              />
              <button
                type="button"
                onClick={addSymbol}
                className="px-3 py-1.5 rounded border border-border bg-panel text-muted
                           hover:text-text hover:border-border/60 transition-colors"
              >
                <Plus size={14} />
              </button>
            </div>
            <p className="text-2xs text-muted mt-1">Press Enter or + to add. Minimum 1 symbol.</p>
          </div>

          {/* Advanced config */}
          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced(v => !v)}
              className="flex items-center gap-1 text-xs text-muted hover:text-gold transition-colors"
            >
              <span>{showAdvanced ? '\u25BE' : '\u25B8'}</span>
              Advanced Risk Parameters
            </button>

            {showAdvanced && (
              <div className="mt-3 space-y-3 p-3 bg-base rounded border border-border">
                <ConfigSlider
                  label="Max Position Size"
                  value={maxPositionPct}
                  onChange={setMaxPositionPct}
                  min={5} max={50} step={5}
                  unit="%"
                  hint="Portfolio % per trade"
                />
                <ConfigSlider
                  label="Max Contracts"
                  value={maxContracts}
                  onChange={setMaxContracts}
                  min={1} max={20} step={1}
                  unit=""
                  hint="Contracts per position"
                />
                <ConfigSlider
                  label="Profit Target"
                  value={profitTarget}
                  onChange={setProfitTarget}
                  min={5} max={200} step={5}
                  unit="%"
                  hint="Auto-exit when position gains this %"
                />
                <ConfigSlider
                  label="Stop Loss"
                  value={stopLoss}
                  onChange={setStopLoss}
                  min={5} max={100} step={5}
                  unit="%"
                  hint="Auto-exit when position loses this %"
                />
                <ConfigSlider
                  label="Max Concurrent Positions"
                  value={maxConcurrent}
                  onChange={setMaxConcurrent}
                  min={1} max={50} step={1}
                  unit=""
                  hint="Open positions at once (soft limit)"
                />
                <ConfigSlider
                  label="Max Daily Trades"
                  value={maxDailyTrades}
                  onChange={setMaxDailyTrades}
                  min={1} max={20} step={1}
                  unit=""
                  hint="New entries per day"
                />
                <ConfigSlider
                  label="Max Daily Loss"
                  value={maxDailyLossPct}
                  onChange={setMaxDailyLossPct}
                  min={1} max={30} step={1}
                  unit="%"
                  hint="Daily P&L floor before pause"
                />
                {preset === 'scalp' && (
                  <ConfigSlider
                    label="Min Confidence"
                    value={minConfidence}
                    onChange={setMinConfidence}
                    min={0.50} max={0.90} step={0.05}
                    unit=""
                    hint="Minimum classifier confidence to enter trade (0.60 = 60%)"
                  />
                )}
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="rounded border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded text-xs text-muted border border-border
                         hover:text-text hover:border-border/60 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="flex items-center gap-2 px-4 py-2 rounded text-xs font-medium
                         bg-gold/10 text-gold border border-gold/30
                         hover:bg-gold/20 disabled:opacity-50 transition-colors"
            >
              {isPending && <Spinner size="sm" />}
              {isEdit ? 'Save Changes' : 'Create Profile'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
