import { useEffect, useState } from 'react';
import {
  Search,
  Map,
  CalendarCheck,
  DollarSign,
  ShieldCheck,
  Package,
  Pause,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import type { AgentStep } from '../../types';

/* ── Agent metadata ─────────────────── */

const AGENT_META: Record<string, { label: string; color: string; icon: typeof Search }> = {
  researcher: { label: 'Research Agent', color: '#0891B2', icon: Search },
  planner: { label: 'Planning Agent', color: '#7C3AED', icon: CalendarCheck },
  optimizer: { label: 'Budget Optimizer', color: '#F97316', icon: DollarSign },
  verifier: { label: 'Verification Agent', color: '#16A34A', icon: ShieldCheck },
  coordinator: { label: 'Coordinator', color: '#6366F1', icon: Map },
  finalizer: { label: 'Finalizer', color: '#EC4899', icon: Package },
};

const STATUS_ICON: Record<string, typeof CheckCircle2> = {
  running: Loader2,
  done: CheckCircle2,
  warning: AlertTriangle,
  waiting: Pause,
};

/* ── Elapsed timer ──────────────────── */

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const seconds = Math.max(0, Math.round((now - since) / 1000));
  return <span className="tabular-nums">{seconds}s</span>;
}

/* ── Main component ─────────────────── */

interface Props {
  currentStep?: AgentStep;
  completedAgents?: AgentStep[];
}

export default function AgentLiveStatus({ currentStep, completedAgents = [] }: Props) {
  const [showHistory, setShowHistory] = useState(false);

  if (!currentStep && completedAgents.length === 0) return null;

  const meta = currentStep ? AGENT_META[currentStep.agent] ?? AGENT_META.coordinator : null;
  const StatusIcon = currentStep ? STATUS_ICON[currentStep.status] ?? Loader2 : Loader2;

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      {/* ── Header ── */}
      <div className="px-4 py-2.5 border-b border-slate-100 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Agent Activity
        </span>
        {currentStep?.status === 'running' && (
          <span className="flex items-center gap-1 text-[11px] text-ocean font-medium">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-ocean opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-ocean" />
            </span>
            Live
          </span>
        )}
      </div>

      {/* ── Current step ── */}
      {currentStep && meta && (
        <div className="px-4 py-3">
          <div className="flex items-start gap-3">
            {/* Agent icon */}
            <div
              className="flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ backgroundColor: `${meta.color}14` }}
            >
              <meta.icon className="w-4.5 h-4.5" style={{ color: meta.color }} />
            </div>

            <div className="flex-1 min-w-0">
              {/* Agent name + elapsed */}
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold" style={{ color: meta.color }}>
                  {meta.label}
                </span>
                {currentStep.timestamp && currentStep.status === 'running' && (
                  <span className="text-[10px] text-slate-400">
                    <Elapsed since={currentStep.timestamp} />
                  </span>
                )}
              </div>

              {/* Step title */}
              <p className="text-sm font-medium text-slate-800 mt-0.5 leading-snug">
                {currentStep.step}
              </p>

              {/* Detail */}
              {currentStep.detail && (
                <p className="text-xs text-slate-500 mt-0.5">{currentStep.detail}</p>
              )}

              {/* Status indicator */}
              <div className="flex items-center gap-1.5 mt-2">
                <StatusIcon
                  className={`w-3.5 h-3.5 ${
                    currentStep.status === 'running'
                      ? 'animate-spin text-ocean'
                      : currentStep.status === 'done'
                        ? 'text-forest'
                        : currentStep.status === 'warning'
                          ? 'text-amber-500'
                          : 'text-slate-400'
                  }`}
                />
                <span
                  className={`text-[11px] font-medium capitalize ${
                    currentStep.status === 'running'
                      ? 'text-ocean'
                      : currentStep.status === 'done'
                        ? 'text-forest'
                        : currentStep.status === 'warning'
                          ? 'text-amber-500'
                          : 'text-slate-400'
                  }`}
                >
                  {currentStep.status === 'running'
                    ? 'Working...'
                    : currentStep.status === 'waiting'
                      ? 'Waiting for you'
                      : currentStep.status === 'done'
                        ? 'Complete'
                        : currentStep.status}
                </span>
              </div>

              {/* Substeps (completed items) */}
              {currentStep.substeps.length > 0 && (
                <div className="mt-2 space-y-1">
                  {currentStep.substeps.map((sub, i) => (
                    <div key={i} className="flex items-center gap-1.5">
                      <CheckCircle2 className="w-3 h-3 text-forest flex-shrink-0" />
                      <span className="text-[11px] text-slate-500">{sub}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Completed agents timeline ── */}
      {completedAgents.length > 0 && (
        <div className="border-t border-slate-100">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="w-full px-4 py-2 flex items-center justify-between text-[11px] text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <span>{completedAgents.length} completed step{completedAgents.length > 1 ? 's' : ''}</span>
            {showHistory ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>

          {showHistory && (
            <div className="px-4 pb-3 space-y-1.5">
              {completedAgents.map((step, i) => {
                const m = AGENT_META[step.agent] ?? AGENT_META.coordinator;
                return (
                  <div key={i} className="flex items-center gap-2.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-forest flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <span className="text-[11px] font-medium" style={{ color: m.color }}>
                        {m.label}
                      </span>
                      <span className="text-[11px] text-slate-400 ml-1.5">{step.step}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
