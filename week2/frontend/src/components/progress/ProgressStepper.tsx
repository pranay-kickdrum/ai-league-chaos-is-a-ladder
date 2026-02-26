import { motion } from 'framer-motion';
import { Check } from 'lucide-react';
import { getPhaseLabel } from '../../lib/utils';
import type { TripStatusType } from '../../types';

const PHASES: TripStatusType[] = [
  'collecting_preferences',
  'researching',
  'planning',
  'verifying',
  'finalizing',
  'complete',
];

function phaseIndex(status: TripStatusType): number {
  // Map checkpoint statuses to their parent phase
  const map: Record<string, number> = {
    collecting_preferences: 0,
    researching: 1,
    planning: 2,
    checkpoint_1: 2,  // CP1 now appears after planning
    checkpoint_2: 2,  // CP2 (budget) is still in planning phase
    verifying: 3,
    checkpoint_3: 3,
    finalizing: 4,
    complete: 5,
    replanning: 2,
    error: -1,
  };
  return map[status] ?? 0;
}

interface ProgressStepperProps {
  status: TripStatusType;
}

export default function ProgressStepper({ status }: ProgressStepperProps) {
  const current = phaseIndex(status);

  return (
    <div className="bg-white border-b border-slate-200 px-6 py-3">
      <div className="flex items-center justify-center gap-1 max-w-2xl mx-auto">
        {PHASES.map((phase, i) => {
          const isDone = i < current;
          const isActive = i === current;

          return (
            <div key={phase} className="flex items-center">
              {i > 0 && (
                <div
                  className={`w-8 h-0.5 mx-1 transition-colors duration-300 ${
                    isDone ? 'bg-forest' : 'bg-slate-200'
                  }`}
                />
              )}
              <motion.div
                className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors duration-300 ${
                  isDone
                    ? 'bg-green-100 text-forest'
                    : isActive
                    ? 'bg-ocean/10 text-ocean border border-ocean/30'
                    : 'bg-slate-100 text-slate-400'
                }`}
                animate={isActive ? { scale: [1, 1.02, 1] } : {}}
                transition={{ repeat: Infinity, duration: 2 }}
              >
                {isDone ? (
                  <Check className="w-3.5 h-3.5" />
                ) : (
                  <span className="w-4 h-4 rounded-full border border-current flex items-center justify-center text-[10px]">
                    {i + 1}
                  </span>
                )}
                <span className="hidden sm:inline">{getPhaseLabel(phase)}</span>
              </motion.div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
