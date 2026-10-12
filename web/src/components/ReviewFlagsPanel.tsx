import React, { useCallback, useEffect, useState } from 'react';
import { ShieldAlert, RefreshCw, CheckCircle2, AlertTriangle, WifiOff, ArrowRight } from 'lucide-react';
import type { Language, ReviewFlag } from '../types';
import { api, isApiError, isNetworkError } from '../api/client';

interface ReviewFlagsPanelProps {
  language: Language;
  // compact = Dashboard card (open count + newest few); otherwise the full review screen
  compact?: boolean;
  onOpenFull?: () => void;
}

const FLAG_LABEL: Record<string, string> = {
  NEGATIVE_STOCK_WARNING: 'Negative stock',
  CREDIT_LIMIT_EXCEEDED: 'Credit limit exceeded',
  BELOW_FLOOR_PRICE: 'Below floor price',
};

const flagStyle = (t: string) =>
  t === 'CREDIT_LIMIT_EXCEEDED' ? 'bg-red-950/70 text-red-300 border-red-800' :
  t === 'BELOW_FLOOR_PRICE' ? 'bg-amber-950/70 text-amber-300 border-amber-800' :
  'bg-orange-950/70 text-orange-300 border-orange-800';

const fmtTime = (iso?: string | null) => {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
};

export const ReviewFlagsPanel: React.FC<ReviewFlagsPanelProps> = ({ language, compact = false, onOpenFull }) => {
  const [status, setStatus] = useState<'OPEN' | 'RESOLVED' | 'ALL'>('OPEN');
  const [flags, setFlags] = useState<ReviewFlag[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [pin, setPin] = useState('');
  const [notes, setNotes] = useState('');
  const [rowError, setRowError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setFlags(await api.getReviewFlags(compact ? 'OPEN' : status, compact ? 50 : 200));
      setError(null);
    } catch (err: any) {
      setError(isNetworkError(err) ? 'offline' : (err?.message || 'Failed to load review flags'));
    } finally {
      setLoading(false);
    }
  }, [status, compact]);

  useEffect(() => {
    load();
  }, [load]);

  const startResolve = (id: string) => {
    setResolvingId(id);
    setPin('');
    setNotes('');
    setRowError(null);
  };

  const handleResolve = async (e: React.FormEvent, flag: ReviewFlag) => {
    e.preventDefault();
    if (!pin) return;
    setSubmitting(true);
    setRowError(null);
    try {
      const updated = await api.resolveReviewFlag(flag.id, pin, notes.trim() || undefined);
      setFlags(prev => status === 'OPEN' || compact
        ? prev.filter(f => f.id !== flag.id)
        : prev.map(f => (f.id === flag.id ? updated : f)));
      setResolvingId(null);
      setPin('');
      setNotes('');
    } catch (err: any) {
      if (isApiError(err, 403)) setRowError('Wrong owner PIN.');
      else if (isApiError(err, 429)) setRowError('Too many wrong PIN attempts. Wait a few minutes.');
      else if (isApiError(err, 409)) {
        setRowError('Already resolved.');
        load();
      } else if (isApiError(err, 404)) {
        setRowError('Flag no longer exists.');
        load();
      } else if (isNetworkError(err)) setRowError('Server unreachable.');
      else setRowError(err?.message || 'Resolve failed');
    } finally {
      setSubmitting(false);
    }
  };

  const openFlags = flags.filter(f => f.status === 'OPEN');
  const shown = compact ? openFlags.slice(0, 4) : flags;

  return (
    <div className="hardware-card p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-700 pb-2.5">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-amber-400" />
          <h3 className="font-bold text-white text-sm">
            {language === 'ta' ? 'உரிமையாளர் மதிப்பாய்வு' : 'Owner Review Flags'}
          </h3>
          <span className={`text-[11px] font-mono px-2 py-0.5 rounded-full font-bold border ${
            openFlags.length > 0 ? 'bg-amber-950 text-amber-300 border-amber-800' : 'bg-emerald-950 text-emerald-300 border-emerald-800'
          }`}>
            {compact || status === 'OPEN' ? `${openFlags.length} open` : `${flags.length} shown`}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {!compact && (
            <div className="flex bg-slate-900 p-0.5 rounded-lg border border-slate-700" role="group" aria-label="Flag status filter">
              {(['OPEN', 'RESOLVED', 'ALL'] as const).map(s => (
                <button
                  key={s}
                  onClick={() => setStatus(s)}
                  aria-pressed={status === s}
                  className={`px-2.5 py-1 rounded-md font-bold ${status === s ? 'bg-amber-600 text-white' : 'text-slate-400 hover:text-white'}`}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          <button onClick={load} disabled={loading} className="text-slate-400 hover:text-white flex items-center gap-1" aria-label="Refresh review flags">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {compact && onOpenFull && (
            <button onClick={onOpenFull} className="text-amber-300 hover:text-amber-200 font-semibold flex items-center gap-1">
              <span>Review all</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {error === 'offline' ? (
        <div className="flex items-center gap-2 text-xs text-amber-300"><WifiOff className="w-4 h-4" /> Server unreachable - flags load when back online.</div>
      ) : error ? (
        <div className="text-xs text-red-300">{error}</div>
      ) : shown.length === 0 ? (
        <div className="text-center p-5 text-slate-500 text-xs flex flex-col items-center gap-1.5">
          <CheckCircle2 className="w-6 h-6 text-emerald-500" />
          <span>{status === 'RESOLVED' && !compact ? 'No resolved flags yet.' : 'Nothing waiting for owner review.'}</span>
        </div>
      ) : (
        <ul className="space-y-2">
          {shown.map(f => (
            <li key={f.id} className="p-3 rounded-xl bg-slate-900 border border-slate-700/70 text-xs space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className={`px-1.5 py-0.5 rounded border text-[10px] font-mono font-bold ${flagStyle(f.alert_type)}`}>
                    {FLAG_LABEL[f.alert_type] || f.alert_type}
                  </span>
                  <span className="font-mono font-bold text-white">{f.reference_doc_number}</span>
                  {f.is_offline_created && (
                    <span className="px-1.5 py-0.5 rounded border border-slate-600 text-[10px] font-mono text-slate-300">OFFLINE BILL</span>
                  )}
                  {f.owner_override && (
                    <span className="px-1.5 py-0.5 rounded border border-emerald-800 text-[10px] font-mono text-emerald-300">OWNER APPROVED</span>
                  )}
                </div>
                <span className="text-[11px] text-slate-400 font-mono">{fmtTime(f.created_at)}</span>
              </div>
              <div className="text-slate-300">{f.message}</div>
              {f.status === 'RESOLVED' ? (
                <div className="text-[11px] text-emerald-400">
                  Resolved {fmtTime(f.resolved_at)}{f.resolution_notes ? ` - ${f.resolution_notes}` : ''}
                </div>
              ) : resolvingId === f.id ? (
                <form onSubmit={(e) => handleResolve(e, f)} className="flex flex-wrap items-center gap-2 pt-1">
                  <label className="sr-only" htmlFor={`pin-${f.id}`}>Owner PIN</label>
                  <input
                    id={`pin-${f.id}`}
                    type="password"
                    inputMode="numeric"
                    autoComplete="off"
                    autoFocus
                    placeholder="Owner PIN"
                    value={pin}
                    onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 8))}
                    className="w-28 bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 font-mono tracking-widest text-white focus:border-amber-500"
                  />
                  <label className="sr-only" htmlFor={`notes-${f.id}`}>Resolution notes</label>
                  <input
                    id={`notes-${f.id}`}
                    type="text"
                    placeholder="Notes (optional)"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="flex-1 min-w-[140px] bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-white"
                  />
                  <button type="submit" disabled={submitting || !pin} className="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold">
                    {submitting ? 'Saving...' : 'Resolve'}
                  </button>
                  <button type="button" onClick={() => setResolvingId(null)} className="px-2 py-1 rounded-lg bg-slate-800 text-slate-300">
                    Cancel
                  </button>
                  {rowError && (
                    <span role="alert" className="w-full flex items-center gap-1 text-red-300 font-semibold">
                      <AlertTriangle className="w-3.5 h-3.5" /> {rowError}
                    </span>
                  )}
                </form>
              ) : (
                <button onClick={() => startResolve(f.id)} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-200 font-semibold">
                  Resolve with owner PIN
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {compact && openFlags.length > shown.length && (
        <div className="text-[11px] text-slate-400 text-right">+{openFlags.length - shown.length} more</div>
      )}
    </div>
  );
};
