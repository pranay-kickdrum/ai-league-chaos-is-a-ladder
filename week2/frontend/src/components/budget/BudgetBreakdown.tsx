import { formatCurrency } from '../../lib/utils';
import type { BudgetBreakdown as BudgetType } from '../../types';

interface BudgetBreakdownProps {
  budget: BudgetType;
  limit?: number;
}

const COLORS: Record<string, string> = {
  transport: 'bg-ocean',
  accommodation: 'bg-sunset',
  food: 'bg-forest',
  activities: 'bg-purple-500',
  buffer: 'bg-slate-300',
};

const LABELS: Record<string, string> = {
  transport: 'Transport',
  accommodation: 'Accommodation',
  food: 'Food',
  activities: 'Activities',
  buffer: 'Buffer',
};

export default function BudgetBreakdown({ budget, limit }: BudgetBreakdownProps) {
  const total =
    budget.total ??
    budget.transport + budget.accommodation + budget.food + budget.activities + budget.buffer;
  const categories = ['transport', 'accommodation', 'food', 'activities', 'buffer'] as const;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-slate-700 mb-3">Budget Breakdown</h3>

      {/* Group info */}
      {budget.traveler_count && budget.traveler_count > 1 && (
        <div className="bg-ocean/5 border border-ocean/10 rounded-lg px-3 py-1.5 mb-3 text-xs text-ocean font-medium flex justify-between items-center">
          <span>👥 {budget.traveler_count} travelers</span>
          <span>
            {formatCurrency(budget.per_person_total ?? Math.round(total / budget.traveler_count), budget.currency)} per person
          </span>
        </div>
      )}

      {/* Total bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-slate-500">Total</span>
          <span className="font-bold text-slate-800">
            {formatCurrency(total, budget.currency)}
            {limit ? ` / ${formatCurrency(limit, budget.currency)}` : ''}
          </span>
        </div>
        <div className="h-3 bg-slate-100 rounded-full overflow-hidden flex">
          {categories.map((cat) => {
            const value = budget[cat];
            const pct = total > 0 ? (value / total) * 100 : 0;
            return pct > 0 ? (
              <div
                key={cat}
                className={`h-full ${COLORS[cat]} transition-all duration-500`}
                style={{ width: `${pct}%` }}
                title={`${LABELS[cat]}: ${formatCurrency(value, budget.currency)}`}
              />
            ) : null;
          })}
        </div>
        {limit && total > limit && (
          <p className="text-xs text-red-500 mt-1">
            ⚠️ Over budget by {formatCurrency(total - limit, budget.currency)}
          </p>
        )}
      </div>

      {/* Legend */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {categories.map((cat) => {
          const value = budget[cat];
          const pct = total > 0 ? Math.round((value / total) * 100) : 0;
          return (
            <div key={cat} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <div className={`w-2.5 h-2.5 rounded-sm ${COLORS[cat]}`} />
                <span className="text-slate-600">{LABELS[cat]}</span>
              </div>
              <span className="text-slate-800 font-medium">
                {formatCurrency(value, budget.currency)}{' '}
                <span className="text-slate-400">({pct}%)</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
