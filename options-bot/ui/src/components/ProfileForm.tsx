import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { X, Plus, Lock } from 'lucide-react';
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

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="pt-2 pb-1 border-b border-border/40 text-2xs font-semibold uppercase tracking-wider text-muted/80">
      {children}
    </div>
  );
}

function ConfigToggle({
  label, value, onChange, hint,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
  hint: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-2xs text-muted">{label}</span>
        <button
          type="button"
          role="switch"
          aria-checked={value}
          onClick={() => onChange(!value)}
          className={`relative inline-flex h-4 w-8 shrink-0 cursor-pointer rounded-full
                      border transition-colors
                      ${value ? 'bg-gold/30 border-gold/50' : 'bg-border border-border'}`}
        >
          <span
            className={`inline-block h-3 w-3 transform rounded-full bg-gold shadow
                        transition-transform ${value ? 'translate-x-4' : 'translate-x-0.5'}`}
            style={{ marginTop: '1px' }}
          />
        </button>
      </div>
      <p className="text-2xs text-muted/60 mt-0.5">{hint}</p>
    </div>
  );
}

interface Props {
  /** Pass existing profile to edit. Omit for create. */
  profile?: Profile;
  onClose: () => void;
}

// No presets are hidden — V2 uses all of them
const LEGACY_PRESETS: string[] = [];

export function ProfileForm({ profile, onClose }: Props) {
  const qc = useQueryClient();
  const isEdit = !!profile;

  // Fetch strategy types from API
  const { data: strategyTypes = [] } = useQuery({
    queryKey: ['strategy-types'],
    queryFn: () => api.profiles.strategyTypes(),
    staleTime: 60_000,
  });

  // Filter: hide legacy presets from new profile creation, show all for edit
  const availableTypes = isEdit
    ? strategyTypes
    : strategyTypes.filter(t => !LEGACY_PRESETS.includes(t.preset_name));

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
    (profile?.config?.profit_target_pct as number) ?? (preset === '0dte_scalp' ? 60 : preset === 'swing' ? 100 : 50)
  );
  const [stopLoss, setStopLoss] = useState<number>(
    (profile?.config?.stop_loss_pct as number) ?? (preset === '0dte_scalp' ? 25 : preset === 'swing' ? 40 : 30)
  );
  const [trailingStop, setTrailingStop] = useState<number>(
    (profile?.config?.trailing_stop_pct as number) ?? (preset === '0dte_scalp' ? 25 : 35)
  );
  const [minDte, setMinDte] = useState<number>(
    (profile?.config?.min_dte as number) ?? (preset === '0dte_scalp' ? 0 : 7)
  );
  const [maxDte, setMaxDte] = useState<number>(
    (profile?.config?.max_dte as number) ?? (preset === '0dte_scalp' ? 0 : 14)
  );
  const [useOtmStrikes, setUseOtmStrikes] = useState<boolean>(
    (profile?.config?.use_otm_strikes as boolean) ?? (preset === '0dte_scalp' || preset === 'scalp')
  );
  const [growthMode, setGrowthMode] = useState<boolean>(
    (profile?.config?.growth_mode as boolean) ?? (preset === '0dte_scalp' || preset === 'scalp')
  );
  const [entryCooldownMinutes, setEntryCooldownMinutes] = useState<number>(
    (profile?.config?.entry_cooldown_minutes as number) ?? (preset === '0dte_scalp' ? 5 : preset === 'scalp' ? 10 : 30)
  );
  const [maxHoldMinutes, setMaxHoldMinutes] = useState<number>(
    (profile?.config?.max_hold_minutes as number) ?? (preset === '0dte_scalp' ? 45 : preset === 'swing' ? 10080 : 240)
  );

  // Entry gates
  const [minPredictedMovePct, setMinPredictedMovePct] = useState<number>(
    (profile?.config?.min_predicted_move_pct as number) ?? 0.5
  );
  const [minEvPct, setMinEvPct] = useState<number>(
    (profile?.config?.min_ev_pct as number) ?? 3
  );
  const [maxSpreadPct, setMaxSpreadPct] = useState<number>(
    (profile?.config?.max_spread_pct as number) ?? 0.15
  );
  const [requiresMinEquity, setRequiresMinEquity] = useState<number>(
    (profile?.config?.requires_min_equity as number) ?? 0
  );
  const [vixGateEnabled, setVixGateEnabled] = useState<boolean>(
    (profile?.config?.vix_gate_enabled as boolean) ?? true
  );
  const [vixMin, setVixMin] = useState<number>(
    (profile?.config?.vix_min as number) ?? 12
  );
  const [vixMax, setVixMax] = useState<number>(
    (profile?.config?.vix_max as number) ?? 50
  );
  const [impliedMoveGateEnabled, setImpliedMoveGateEnabled] = useState<boolean>(
    (profile?.config?.implied_move_gate_enabled as boolean) ?? false
  );
  const [impliedMoveRatioMin, setImpliedMoveRatioMin] = useState<number>(
    (profile?.config?.implied_move_ratio_min as number) ?? 0.8
  );
  const [gexGateEnabled, setGexGateEnabled] = useState<boolean>(
    (profile?.config?.gex_gate_enabled as boolean) ?? false
  );

  // Strike / contract selection
  const [minPremium, setMinPremium] = useState<number>(
    (profile?.config?.min_premium as number) ?? 0.05
  );
  const [maxPremium, setMaxPremium] = useState<number>(
    (profile?.config?.max_premium as number) ?? 0
  );
  const [moneynessRangePct, setMoneynessRangePct] = useState<number>(
    (profile?.config?.moneyness_range_pct as number) ?? 1.0
  );
  const [preferAtm, setPreferAtm] = useState<boolean>(
    (profile?.config?.prefer_atm as boolean) ?? false
  );

  // Exits
  const [trailingStopActivationPct, setTrailingStopActivationPct] = useState<number>(
    (profile?.config?.trailing_stop_activation_pct as number) ?? 15
  );
  const [underlyingReversalPct, setUnderlyingReversalPct] = useState<number>(
    (profile?.config?.underlying_reversal_pct as number) ?? 1.0
  );
  const [maxHoldDays, setMaxHoldDays] = useState<number>(
    (profile?.config?.max_hold_days as number) ?? 1
  );
  const [modelOverrideMinReversalPct, setModelOverrideMinReversalPct] = useState<number>(
    (profile?.config?.model_override_min_reversal_pct as number) ?? 0.5
  );

  // Iron Condor specific
  const [icTargetDelta, setIcTargetDelta] = useState<number>(
    (profile?.config?.ic_target_delta as number) ?? 0.16
  );
  const [icSpreadWidth, setIcSpreadWidth] = useState<number>(
    (profile?.config?.ic_spread_width as number) ?? 3.0
  );
  const [icProfitTargetPct, setIcProfitTargetPct] = useState<number>(
    (profile?.config?.ic_profit_target_pct as number) ?? 75
  );
  const [icStopMultiplier, setIcStopMultiplier] = useState<number>(
    (profile?.config?.ic_stop_multiplier as number) ?? 1.0
  );
  const [gexCacheMinutes, setGexCacheMinutes] = useState<number>(
    (profile?.config?.gex_cache_minutes as number) ?? 5
  );
  const [maxConfidenceForIc, setMaxConfidenceForIc] = useState<number>(
    (profile?.config?.max_confidence_for_ic as number) ?? 0.35
  );

  const [showAdvanced, setShowAdvanced] = useState(false);

  const configPayload = () => ({
    max_position_pct: maxPositionPct,
    max_contracts: maxContracts,
    max_concurrent_positions: maxConcurrent,
    max_daily_trades: maxDailyTrades,
    max_daily_loss_pct: maxDailyLossPct,
    profit_target_pct: profitTarget,
    stop_loss_pct: stopLoss,
    trailing_stop_pct: trailingStop,
    min_dte: minDte,
    max_dte: maxDte,
    min_confidence: minConfidence,
    use_otm_strikes: useOtmStrikes,
    growth_mode: growthMode,
    entry_cooldown_minutes: entryCooldownMinutes,
    max_hold_minutes: maxHoldMinutes,
    // Entry gates
    min_predicted_move_pct: minPredictedMovePct,
    min_ev_pct: minEvPct,
    max_spread_pct: maxSpreadPct,
    requires_min_equity: requiresMinEquity,
    vix_gate_enabled: vixGateEnabled,
    vix_min: vixMin,
    vix_max: vixMax,
    implied_move_gate_enabled: impliedMoveGateEnabled,
    implied_move_ratio_min: impliedMoveRatioMin,
    gex_gate_enabled: gexGateEnabled,
    // Strike / contract selection
    min_premium: minPremium,
    max_premium: maxPremium,
    moneyness_range_pct: moneynessRangePct,
    prefer_atm: preferAtm,
    // Exits
    trailing_stop_activation_pct: trailingStopActivationPct,
    underlying_reversal_pct: underlyingReversalPct,
    max_hold_days: maxHoldDays,
    model_override_min_reversal_pct: modelOverrideMinReversalPct,
    // Iron Condor
    ic_target_delta: icTargetDelta,
    ic_spread_width: icSpreadWidth,
    ic_profit_target_pct: icProfitTargetPct,
    ic_stop_multiplier: icStopMultiplier,
    gex_cache_minutes: gexCacheMinutes,
    max_confidence_for_ic: maxConfidenceForIc,
  });

  const createMutation = useMutation({
    mutationFn: () => api.profiles.create({
      name: name.trim(),
      preset,
      symbols,
      config_overrides: configPayload(),
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
      config_overrides: configPayload(),
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

  // Dirty = name, symbols, or ANY field in configPayload() changed from initial profile state
  const isDirty = (() => {
    if (name !== (profile?.name ?? '')) return true;
    if (JSON.stringify(symbols) !== JSON.stringify(profile?.symbols ?? ['TSLA'])) return true;
    const current = configPayload();
    const original = profile?.config ?? {};
    for (const k of Object.keys(current) as (keyof typeof current)[]) {
      if (original[k] !== undefined && original[k] !== current[k]) return true;
    }
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
      <div className="w-full max-w-md max-h-[90vh] bg-surface border border-border rounded-xl shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <h2 className="text-sm font-semibold text-text">
            {isEdit ? 'Edit Profile' : 'New Profile'}
          </h2>
          <button onClick={onClose} className="text-muted hover:text-text transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Form — scrollable */}
        <form id="profile-form" onSubmit={handleSubmit} className="px-5 py-4 space-y-4 overflow-y-auto">
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

          {/* Strategy Type — only on create */}
          {!isEdit && (
            <div>
              <label className="block text-xs text-muted mb-1.5">Strategy Type</label>
              <div className="grid grid-cols-2 gap-2">
                {availableTypes.map(t => {
                  return (
                    <button
                      key={t.preset_name}
                      type="button"
                      onClick={() => {
                        setPreset(t.preset_name);
                        // Auto-set symbol for SPY-focused strategies
                        if (t.is_intraday && symbols.length <= 1 && (symbols[0] === 'TSLA' || symbols.length === 0)) {
                          setSymbols(['SPY']);
                        }
                        // Clear error when switching type
                        setError(null);
                      }}
                      className={`text-left px-3 py-2.5 rounded border transition-colors relative
                        ${preset === t.preset_name
                          ? 'border-gold/40 bg-gold/5 text-text'
                          : 'border-border bg-panel text-muted hover:border-border/60'}`}
                    >
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-xs font-medium">{t.display_name}</span>
                        {t.min_capital > 5000 && (
                          <span className="flex items-center gap-0.5 text-2xs text-muted">
                            <Lock size={9} />
                            ${(t.min_capital / 1000).toFixed(0)}K
                          </span>
                        )}
                      </div>
                      <div className="text-2xs text-muted leading-relaxed">
                        {t.description}
                      </div>
                      {t.min_capital > 5000 && (
                        <div className="text-2xs text-gold/60 mt-1">
                          Min. ${t.min_capital.toLocaleString()} equity
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
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
              <div className="mt-3 space-y-4 p-3 bg-base rounded border border-border">
                <SectionHeading>Sizing & Limits</SectionHeading>
                <ConfigSlider label="Max Position Size" value={maxPositionPct} onChange={setMaxPositionPct}
                  min={5} max={50} step={5} unit="%" hint="Portfolio % per trade" />
                <ConfigSlider label="Max Contracts" value={maxContracts} onChange={setMaxContracts}
                  min={1} max={100} step={1} unit="" hint="Contracts per position" />
                <ConfigSlider label="Max Concurrent Positions" value={maxConcurrent} onChange={setMaxConcurrent}
                  min={1} max={50} step={1} unit="" hint="Open positions at once (soft limit)" />
                <ConfigSlider label="Max Daily Trades" value={maxDailyTrades} onChange={setMaxDailyTrades}
                  min={1} max={20} step={1} unit="" hint="New entries per day" />
                <ConfigSlider label="Max Daily Loss" value={maxDailyLossPct} onChange={setMaxDailyLossPct}
                  min={1} max={30} step={1} unit="%" hint="Daily P&L floor before pause" />
                <ConfigToggle label="Growth Mode" value={growthMode} onChange={setGrowthMode}
                  hint="Aggressive sizing for small accounts (< $25K). Skips conservative halving steps." />

                <SectionHeading>Exits</SectionHeading>
                <ConfigSlider label="Profit Target" value={profitTarget} onChange={setProfitTarget}
                  min={5} max={500} step={5} unit="%" hint="Auto-exit when position gains this %" />
                <ConfigSlider label="Stop Loss" value={stopLoss} onChange={setStopLoss}
                  min={5} max={100} step={5} unit="%" hint="Auto-exit when position loses this %" />
                <ConfigSlider label="Trailing Stop" value={trailingStop} onChange={setTrailingStop}
                  min={5} max={50} step={5} unit="%" hint="% pullback from peak before exiting a winner" />
                <ConfigSlider label="Trailing Stop Activation" value={trailingStopActivationPct} onChange={setTrailingStopActivationPct}
                  min={0} max={50} step={1} unit="%" hint="Gain % required before trailing stop becomes active" />
                <ConfigSlider label="Underlying Reversal Exit" value={underlyingReversalPct} onChange={setUnderlyingReversalPct}
                  min={0} max={5} step={0.1} unit="%" hint="Exit if underlying moves this % against trade direction" />
                <ConfigSlider label="Max Hold Time" value={maxHoldMinutes} onChange={setMaxHoldMinutes}
                  min={15} max={10080} step={15} unit=" min" hint="Max position hold before forced exit" />
                <ConfigSlider label="Max Hold Days" value={maxHoldDays} onChange={setMaxHoldDays}
                  min={0} max={30} step={1} unit=" d" hint="Day-level hold cap (swing/general presets)" />

                <SectionHeading>Entry Gates</SectionHeading>
                <ConfigSlider label="Min Confidence" value={minConfidence} onChange={setMinConfidence}
                  min={0.10} max={0.90} step={0.05} unit="" hint="Minimum scorer confidence to enter" />
                <ConfigSlider label="Min Predicted Move" value={minPredictedMovePct} onChange={setMinPredictedMovePct}
                  min={0} max={5} step={0.1} unit="%" hint="Model must predict at least this move % to enter" />
                <ConfigSlider label="Min EV" value={minEvPct} onChange={setMinEvPct}
                  min={0} max={30} step={1} unit="%" hint="Minimum expected value % to enter (bypassed for 0DTE scalp)" />
                <ConfigSlider label="Entry Cooldown" value={entryCooldownMinutes} onChange={setEntryCooldownMinutes}
                  min={0} max={60} step={1} unit=" min" hint="Minimum minutes between entries per profile" />
                <ConfigSlider label="Required Min Equity" value={requiresMinEquity} onChange={setRequiresMinEquity}
                  min={0} max={50000} step={1000} unit=" $" hint="Skip trades when equity is below this amount" />
                <ConfigToggle label="VIX Gate Enabled" value={vixGateEnabled} onChange={setVixGateEnabled}
                  hint="Require VIX within [min, max] before entering" />
                <ConfigSlider label="VIX Min" value={vixMin} onChange={setVixMin}
                  min={8} max={30} step={0.5} unit="" hint="Lower VIX bound for entry" />
                <ConfigSlider label="VIX Max" value={vixMax} onChange={setVixMax}
                  min={20} max={80} step={1} unit="" hint="Upper VIX bound for entry" />
                <ConfigToggle label="Implied Move Gate" value={impliedMoveGateEnabled} onChange={setImpliedMoveGateEnabled}
                  hint="Require predicted move >= implied move × ratio (bypassed for classifiers)" />
                <ConfigSlider label="Implied Move Ratio Min" value={impliedMoveRatioMin} onChange={setImpliedMoveRatioMin}
                  min={0} max={3} step={0.05} unit="" hint="Ratio of predicted-to-implied move required" />
                <ConfigToggle label="GEX Gate Enabled" value={gexGateEnabled} onChange={setGexGateEnabled}
                  hint="Require GEX regime = trending (otm_scalp only)" />
                <ConfigSlider label="Model Override Min Reversal" value={modelOverrideMinReversalPct} onChange={setModelOverrideMinReversalPct}
                  min={0} max={5} step={0.1} unit="%" hint="Min model-flagged reversal % to override trend" />

                <SectionHeading>Strike Selection</SectionHeading>
                <ConfigSlider label="Min DTE" value={minDte} onChange={setMinDte}
                  min={0} max={90} step={1} unit=" d" hint="Minimum days to expiration" />
                <ConfigSlider label="Max DTE" value={maxDte} onChange={setMaxDte}
                  min={0} max={120} step={1} unit=" d" hint="Maximum days to expiration" />
                <ConfigToggle label="Use OTM Strikes" value={useOtmStrikes} onChange={setUseOtmStrikes}
                  hint="Buy cheap OTM lotto tickets instead of ATM/ITM. Required for scalp_0dte thesis." />
                <ConfigToggle label="Prefer ATM" value={preferAtm} onChange={setPreferAtm}
                  hint="Pick nearest-ATM among EV-qualified contracts (scalp) vs highest-EV (otm_scalp)" />
                <ConfigSlider label="Moneyness Range" value={moneynessRangePct} onChange={setMoneynessRangePct}
                  min={0.25} max={10} step={0.25} unit="%" hint="Strike scan window around underlying" />
                <ConfigSlider label="Min Premium" value={minPremium} onChange={setMinPremium}
                  min={0} max={5} step={0.05} unit=" $" hint="Reject contracts priced below this" />
                <ConfigSlider label="Max Premium (0 = no cap)" value={maxPremium} onChange={setMaxPremium}
                  min={0} max={10} step={0.25} unit=" $" hint="Reject contracts priced above this (0 disables cap)" />
                <ConfigSlider label="Max Spread" value={maxSpreadPct} onChange={setMaxSpreadPct}
                  min={0.05} max={0.50} step={0.01} unit="" hint="Max bid-ask spread as fraction of mid (0.15 = 15%)" />

                {preset === 'iron_condor' && (
                  <>
                    <SectionHeading>Iron Condor</SectionHeading>
                    <ConfigSlider label="Target Delta" value={icTargetDelta} onChange={setIcTargetDelta}
                      min={0.05} max={0.35} step={0.01} unit="" hint="Short strike delta target" />
                    <ConfigSlider label="Spread Width" value={icSpreadWidth} onChange={setIcSpreadWidth}
                      min={1} max={10} step={0.5} unit=" $" hint="Spread width in dollars" />
                    <ConfigSlider label="IC Profit Target" value={icProfitTargetPct} onChange={setIcProfitTargetPct}
                      min={25} max={100} step={5} unit="%" hint="Close at this % of max profit" />
                    <ConfigSlider label="IC Stop Multiplier" value={icStopMultiplier} onChange={setIcStopMultiplier}
                      min={0.5} max={3} step={0.1} unit="×" hint="Stop at this multiple of credit received" />
                    <ConfigSlider label="GEX Cache Minutes" value={gexCacheMinutes} onChange={setGexCacheMinutes}
                      min={1} max={30} step={1} unit=" min" hint="How long to cache GEX snapshot" />
                    <ConfigSlider label="Max Confidence for IC" value={maxConfidenceForIc} onChange={setMaxConfidenceForIc}
                      min={0.10} max={0.90} step={0.05} unit="" hint="Skip IC when directional confidence exceeds this" />
                  </>
                )}
              </div>
            )}
          </div>

        </form>

        {/* Footer — fixed at bottom, never scrolls */}
        <div className="px-5 py-4 border-t border-border shrink-0">
          {error && (
            <div className="rounded border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss mb-3">
              {error}
            </div>
          )}
          <div className="flex justify-end gap-2">
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
              form="profile-form"
              disabled={isPending}
              className="flex items-center gap-2 px-4 py-2 rounded text-xs font-medium
                         bg-gold/10 text-gold border border-gold/30
                         hover:bg-gold/20 disabled:opacity-50 transition-colors"
            >
              {isPending && <Spinner size="sm" />}
              {isEdit ? 'Save Changes' : 'Create Profile'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
