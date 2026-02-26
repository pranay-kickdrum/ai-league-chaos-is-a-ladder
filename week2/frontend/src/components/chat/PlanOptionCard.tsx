import { formatCurrency } from '../../lib/utils';
import type { PlanOption } from '../../types';
import { motion } from 'framer-motion';

interface PlanOptionCardProps {
  option: PlanOption;
  onSelect: (id: string) => void;
  isSelected?: boolean;
}

export default function PlanOptionCard({ option, onSelect, isSelected }: PlanOptionCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ scale: 1.01 }}
      onClick={() => onSelect(option.id)}
      className={`cursor-pointer rounded-xl p-4 border-2 transition-colors ${
        isSelected
          ? 'border-ocean bg-ocean/5'
          : 'border-slate-200 bg-white hover:border-ocean/40'
      }`}
    >
      <div className="flex items-start justify-between">
        <h4 className="font-semibold text-slate-800">{option.label}</h4>
        <span className="text-sm font-bold text-sunset whitespace-nowrap ml-2">
          {formatCurrency(option.estimated_total, option.currency)}
        </span>
      </div>
      <p className="text-sm text-slate-500 mt-1">{option.trade_offs}</p>
      {option.highlights?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {option.highlights.map((h, i) => (
            <span key={i} className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
              {h}
            </span>
          ))}
        </div>
      )}
    </motion.div>
  );
}
