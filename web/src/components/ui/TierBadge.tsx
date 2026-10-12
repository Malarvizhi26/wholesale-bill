import React from 'react';

interface TierBadgeProps {
  code?: string | null;
  name?: string | null;
  className?: string;
}

// Price-list tier of a party (Retail / Contractor / Wholesale ...), as resolved by the server
export const TierBadge: React.FC<TierBadgeProps> = ({ code, name, className = '' }) => {
  if (!code && !name) return null;
  const c = (code || '').toUpperCase();
  const style =
    c === 'CONTRACTOR' ? 'bg-amber-950/70 text-amber-300 border-amber-700/70' :
    c === 'WHOLESALE' ? 'bg-sky-950/70 text-sky-300 border-sky-700/70' :
    'bg-slate-800 text-slate-300 border-slate-600';
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-mono font-bold uppercase tracking-wide ${style} ${className}`}
      title={name || code || ''}
    >
      {code || name}
    </span>
  );
};
