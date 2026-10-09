import React from 'react';

interface CurrencyCellProps {
  amount: number | string;
  showSign?: boolean;
  highlight?: 'emerald' | 'amber' | 'red' | 'default';
  size?: 'sm' | 'base' | 'lg' | 'xl' | '2xl' | '3xl';
  decimals?: number;
}

export const CurrencyCell: React.FC<CurrencyCellProps> = ({
  amount,
  showSign = false,
  highlight = 'default',
  size = 'base',
  decimals = 2,
}) => {
  const num = Number(amount ?? 0);
  const formatted = Math.abs(num).toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  const sign = num < 0 ? '-' : (showSign && num > 0 ? '+' : '');

  const colorStyles = {
    emerald: 'text-emerald-400 font-bold',
    amber: 'text-amber-400 font-bold',
    red: 'text-red-400 font-bold',
    default: 'text-slate-100',
  };

  const sizeStyles = {
    sm: 'text-xs',
    base: 'text-sm',
    lg: 'text-base font-semibold',
    xl: 'text-lg font-bold',
    '2xl': 'text-xl font-black',
    '3xl': 'text-2xl font-black tracking-tight',
  };

  return (
    <span className={`font-mono tabular-nums ${colorStyles[highlight]} ${sizeStyles[size]}`}>
      {sign}₹{formatted}
    </span>
  );
};
