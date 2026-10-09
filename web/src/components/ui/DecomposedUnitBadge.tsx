import React from 'react';

interface DecomposedUnitBadgeProps {
  displayText?: string;
  baseQuantity: number;
  baseUnit: string;
}

export const DecomposedUnitBadge: React.FC<DecomposedUnitBadgeProps> = ({
  displayText,
  baseQuantity,
  baseUnit,
}) => {
  return (
    <div className="inline-flex flex-col items-end">
      <div className="font-mono font-bold text-emerald-400 text-sm flex items-center gap-1.5">
        <span>{displayText || `${baseQuantity} ${baseUnit}`}</span>
      </div>
      <div className="text-[10px] text-slate-400 font-mono">
        Base: {baseQuantity.toLocaleString()} {baseUnit}
      </div>
    </div>
  );
};
