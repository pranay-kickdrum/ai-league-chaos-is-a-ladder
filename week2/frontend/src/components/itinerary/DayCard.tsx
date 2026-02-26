import { motion } from 'framer-motion';
import { Cloud, Utensils, Plane, Train, Bus, ArrowRight } from 'lucide-react';
import { formatCurrency } from '../../lib/utils';
import ActivityItem from './ActivityItem';
import type { DayPlan } from '../../types';

interface DayCardProps {
  day: DayPlan;
  isExpanded: boolean;
  onToggle: () => void;
}

export default function DayCard({ day, isExpanded, onToggle }: DayCardProps) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white border border-slate-200 rounded-xl overflow-hidden"
    >
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition"
      >
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-ocean/10 text-ocean rounded-lg flex items-center justify-center text-sm font-bold">
            {day.day_number}
          </div>
          <div className="text-left">
            <h4 className="text-sm font-semibold text-slate-800">{day.title}</h4>
            {day.description && (
              <p className="text-xs text-slate-500">{day.description}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {day.weather_summary && (
            <span className="text-xs text-slate-400 flex items-center gap-1">
              <Cloud className="w-3.5 h-3.5" />
              {day.weather_summary}
            </span>
          )}
          <span className="text-xs font-medium text-sunset">
            {formatCurrency(day.day_cost ?? day.estimated_cost ?? 0)}
          </span>
          <span className="text-slate-400 text-xs">{isExpanded ? '▲' : '▼'}</span>
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className="px-4 pb-4 border-t border-slate-100"
        >
          {/* Transport legs (if any for this day) */}
          {day.transport && day.transport.length > 0 && (
            <div className="mt-3 pt-3 border-t border-slate-100">
              {day.transport.map((leg, i) => (
                <div key={i} className="flex items-center gap-2 bg-ocean/5 rounded-lg px-3 py-2 mb-2">
                  {leg.mode === 'train' ? <Train className="w-4 h-4 text-emerald-600" /> :
                   leg.mode === 'bus' ? <Bus className="w-4 h-4 text-amber-600" /> :
                   <Plane className="w-4 h-4 text-ocean" />}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-700 flex items-center gap-1">
                      {leg.from_location} <ArrowRight className="w-3 h-3" /> {leg.to_location}
                    </p>
                    {leg.notes && <p className="text-[11px] text-slate-500 truncate">{leg.notes}</p>}
                  </div>
                  {leg.cost > 0 && (
                    <span className="text-xs font-semibold text-sunset shrink-0">
                      {formatCurrency(leg.cost, leg.currency)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Activities timeline */}
          <div className="mt-3">
            {day.activities.map((act, i) => (
              <ActivityItem key={i} activity={act} />
            ))}
          </div>

          {/* Meals */}
          {day.meals.length > 0 && (
            <div className="mt-3 pt-3 border-t border-slate-100">
              <h5 className="text-xs font-medium text-slate-500 mb-2 flex items-center gap-1">
                <Utensils className="w-3 h-3" /> Meals
              </h5>
              <div className="flex gap-2">
                {day.meals.map((meal, i) => (
                  <div key={i} className="text-xs bg-sand/60 text-slate-600 px-2 py-1 rounded-lg">
                    <span className="capitalize font-medium">{meal.meal_type}</span>:{' '}
                    {meal.name || meal.suggestion || ''} ({formatCurrency(meal.cost_estimate ?? meal.estimated_cost ?? 0)})
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}
