import React, { useState } from 'react';
import { KeyRound, X, CheckCircle2, AlertTriangle } from 'lucide-react';
import type { Language } from '../types';
import { api, isApiError, isNetworkError } from '../api/client';

interface OwnerPinDialogProps {
  language: Language;
  onClose: () => void;
}

const PIN_RE = /^\d{4,8}$/;

// Settings dialog: change the owner PIN used for credit-limit / floor-price overrides and review flags
export const OwnerPinDialog: React.FC<OwnerPinDialogProps> = ({ language, onClose }) => {
  const [currentPin, setCurrentPin] = useState('');
  const [newPin, setNewPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!PIN_RE.test(newPin)) {
      setError('New PIN must be 4 to 8 digits.');
      return;
    }
    if (newPin !== confirmPin) {
      setError('New PIN and confirmation do not match.');
      return;
    }
    setSaving(true);
    try {
      await api.changeOwnerPin(currentPin, newPin);
      setDone(true);
      setCurrentPin('');
      setNewPin('');
      setConfirmPin('');
    } catch (err: any) {
      if (isApiError(err, 403)) setError('Current PIN is wrong.');
      else if (isApiError(err, 429)) setError('Too many wrong PIN attempts. Wait a few minutes and try again.');
      else if (isApiError(err, 422)) setError(err.detail || 'New PIN must be 4 to 8 digits.');
      else if (isNetworkError(err)) setError('Server unreachable. PIN can only be changed while online.');
      else setError(err?.message || 'PIN change failed');
    } finally {
      setSaving(false);
    }
  };

  const digitsOnly = (v: string) => v.replace(/\D/g, '').slice(0, 8);

  return (
    <div
      className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[70] flex items-center justify-center p-4"
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
    >
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-sm w-full p-5 space-y-4 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="owner-pin-title">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <KeyRound className="w-5 h-5 text-amber-400" />
            <h3 id="owner-pin-title" className="font-bold text-white text-base">
              {language === 'ta' ? 'உரிமையாளர் PIN மாற்று' : 'Change Owner PIN'}
            </h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white" aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>

        {done ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-950/70 border border-emerald-800 text-emerald-300 text-xs font-semibold">
              <CheckCircle2 className="w-4 h-4" />
              <span>Owner PIN changed. Use the new PIN for overrides and review flags.</span>
            </div>
            <div className="flex justify-end">
              <button autoFocus onClick={onClose} className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold">
                Done
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3 text-xs">
            <div>
              <label htmlFor="pin-current" className="text-slate-300 font-semibold block mb-1">Current PIN</label>
              <input
                id="pin-current"
                type="password"
                inputMode="numeric"
                autoComplete="off"
                autoFocus
                required
                value={currentPin}
                onChange={(e) => setCurrentPin(digitsOnly(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-center font-mono tracking-widest text-white text-base focus:border-amber-500"
              />
            </div>
            <div>
              <label htmlFor="pin-new" className="text-slate-300 font-semibold block mb-1">New PIN (4-8 digits)</label>
              <input
                id="pin-new"
                type="password"
                inputMode="numeric"
                autoComplete="off"
                required
                value={newPin}
                onChange={(e) => setNewPin(digitsOnly(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-center font-mono tracking-widest text-white text-base focus:border-amber-500"
              />
            </div>
            <div>
              <label htmlFor="pin-confirm" className="text-slate-300 font-semibold block mb-1">Confirm New PIN</label>
              <input
                id="pin-confirm"
                type="password"
                inputMode="numeric"
                autoComplete="off"
                required
                value={confirmPin}
                onChange={(e) => setConfirmPin(digitsOnly(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-center font-mono tracking-widest text-white text-base focus:border-amber-500"
              />
            </div>

            {error && (
              <div role="alert" className="flex items-center gap-2 p-2.5 rounded-lg bg-red-950/70 border border-red-800 text-red-300 font-semibold">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={onClose} className="px-3 py-2 rounded-lg bg-slate-800 text-slate-300 font-semibold hover:bg-slate-700">
                Cancel
              </button>
              <button type="submit" disabled={saving} className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white font-bold">
                {saving ? 'Saving...' : 'Change PIN'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
