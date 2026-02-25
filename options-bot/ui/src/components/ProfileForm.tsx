import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, Plus } from 'lucide-react';
import { api } from '../api/client';
import { Spinner } from './Spinner';
import type { Profile } from '../types/api';

interface Props {
  /** Pass existing profile to edit. Omit for create. */
  profile?: Profile;
  onClose: () => void;
}

const PRESETS = ['swing', 'general'] as const;

const PRESET_DESCRIPTIONS: Record<string, string> = {
  swing:   'Mean-reversion options trades. 7–45 DTE. Hold up to 7 days.',
  general: 'Trend-following options trades. 21–60 DTE. Hold up to 21 days.',
};

export function ProfileForm({ profile, onClose }: Props) {
  const qc = useQueryClient();
  const isEdit = !!profile;

  const [name, setName] = useState(profile?.name ?? '');
  const [preset, setPreset] = useState<string>(profile?.preset ?? 'swing');
  const [symbols, setSymbols] = useState<string[]>(profile?.symbols ?? ['TSLA']);
  const [symbolInput, setSymbolInput] = useState('');
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () => api.profiles.create({ name, preset, symbols }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profiles'] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const updateMutation = useMutation({
    mutationFn: () => api.profiles.update(profile!.id, { name, symbols }),
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
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
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
              <div className="grid grid-cols-2 gap-2">
                {PRESETS.map(p => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPreset(p)}
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
