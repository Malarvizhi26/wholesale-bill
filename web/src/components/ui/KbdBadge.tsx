import React from 'react';

interface KbdBadgeProps {
  children: React.ReactNode;
  variant?: 'emerald' | 'amber' | 'slate';
  size?: 'xs' | 'sm';
}

export const KbdBadge: React.FC<KbdBadgeProps> = ({ 
  children, 
  variant = 'emerald',
  size = 'xs' 
}) => {
  const variantStyles = {
    emerald: 'bg-slate-900 text-emerald-400 border-slate-700 hover:border-emerald-500/50',
    amber: 'bg-slate-900 text-amber-400 border-slate-700 hover:border-amber-500/50',
    slate: 'bg-slate-800 text-slate-300 border-slate-700 hover:border-slate-600',
  };

  const sizeStyles = {
    xs: 'px-1.5 py-0.5 text-[11px]',
    sm: 'px-2 py-1 text-xs',
  };

  return (
    <kbd className={`inline-flex items-center justify-center font-mono font-bold rounded border shadow-sm select-none transition-colors ${variantStyles[variant]} ${sizeStyles[size]}`}>
      {children}
    </kbd>
  );
};
