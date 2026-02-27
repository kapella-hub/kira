import { Fragment } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AlertCircle,
  Brain,
  Columns3,
  Search,
  Sparkles,
  SquarePlus,
  Workflow,
  X,
  Check,
} from 'lucide-react';
import { useBoardStore } from '@/stores/boardStore.ts';
import type { PlanTaskState } from '@/stores/boardStore.ts';

const PHASE_ICONS: Record<string, typeof Sparkles> = {
  analyzing: Search,
  pending: Search,
  thinking: Brain,
  structuring: Columns3,
  creating: SquarePlus,
  wiring: Workflow,
};

function getPhaseIcon(phase?: string) {
  return PHASE_ICONS[phase ?? ''] ?? Sparkles;
}

function PhaseIcon({ phase }: { phase?: string }) {
  const Icon = getPhaseIcon(phase);
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={phase ?? 'default'}
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.8 }}
        transition={{ duration: 0.2 }}
        className="shrink-0"
      >
        <Icon size={16} className="text-accent animate-pulse" />
      </motion.div>
    </AnimatePresence>
  );
}

function StepIndicators({ step, totalSteps }: { step: number; totalSteps: number }) {
  return (
    <div className="flex items-center gap-0.5 shrink-0">
      {Array.from({ length: totalSteps }, (_, i) => {
        const stepNum = i + 1;
        const isCompleted = stepNum < step;
        const isActive = stepNum === step;
        return (
          <Fragment key={i}>
            {i > 0 && (
              <div
                className={`w-5 h-0.5 transition-colors duration-300 ${
                  isCompleted ? 'bg-accent' : 'bg-white/8'
                }`}
              />
            )}
            <motion.div
              className={`relative flex items-center justify-center rounded-full transition-colors duration-300 ${
                isCompleted
                  ? 'w-3.5 h-3.5 bg-accent'
                  : isActive
                    ? 'w-2.5 h-2.5 bg-accent animate-step-glow'
                    : 'w-2 h-2 bg-white/10'
              }`}
              animate={
                isCompleted
                  ? { scale: [1, 1.3, 1] }
                  : undefined
              }
              transition={{ duration: 0.3 }}
            >
              {isCompleted && <Check size={8} className="text-bg" strokeWidth={3} />}
            </motion.div>
          </Fragment>
        );
      })}
    </div>
  );
}

function IndeterminateBanner({ planTask, onDismiss }: { planTask: PlanTaskState; onDismiss: () => void }) {
  return (
    <div className="relative border-b border-accent/20">
      <div className="flex items-center gap-3 px-4 py-2">
        <Sparkles size={14} className="text-accent animate-pulse shrink-0" />
        <p className="flex-1 text-xs text-text-secondary truncate">
          {planTask.progressText || 'Generating board plan...'}
        </p>
        <button
          onClick={onDismiss}
          className="p-1 rounded hover:bg-white/5 text-text-muted hover:text-text-primary transition-colors"
          aria-label="Dismiss progress"
        >
          <X size={14} />
        </button>
      </div>
      <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-white/5 overflow-hidden">
        <div className="h-full bg-accent rounded-full animate-progress-indeterminate" />
      </div>
    </div>
  );
}

function ErrorBanner({ planTask, onDismiss }: { planTask: PlanTaskState; onDismiss: () => void }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b bg-error/10 border-error/20">
      <AlertCircle size={14} className="text-error shrink-0" />
      <p className="flex-1 text-xs text-error truncate">
        {planTask.progressText || 'Plan generation failed'}
      </p>
      <button
        onClick={onDismiss}
        className="p-1 rounded hover:bg-white/5 text-text-muted hover:text-text-primary transition-colors"
        aria-label="Dismiss error"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function PlanProgressBanner() {
  const planTask = useBoardStore((s) => s.planTask);
  const setPlanTask = useBoardStore((s) => s.setPlanTask);

  const dismiss = () => setPlanTask(null);

  return (
    <AnimatePresence>
      {planTask && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="overflow-hidden"
        >
          {planTask.status === 'failed' ? (
            <ErrorBanner planTask={planTask} onDismiss={dismiss} />
          ) : planTask.step != null && planTask.totalSteps != null ? (
            <div className="border-b border-accent/20">
              <div className="flex items-center gap-4 px-4 py-2.5 bg-accent/[0.03]">
                <PhaseIcon phase={planTask.phase} />
                <StepIndicators step={planTask.step} totalSteps={planTask.totalSteps} />
                <p className="flex-1 text-xs text-text-secondary truncate min-w-0">
                  {planTask.progressText}
                </p>
                <button
                  onClick={dismiss}
                  className="p-1 rounded hover:bg-white/5 text-text-muted hover:text-text-primary transition-colors shrink-0"
                  aria-label="Dismiss progress"
                >
                  <X size={14} />
                </button>
              </div>
              <div className="h-0.5 bg-white/5">
                <motion.div
                  className="h-full bg-accent"
                  initial={false}
                  animate={{ width: `${(planTask.step / planTask.totalSteps) * 100}%` }}
                  transition={{ duration: 0.5, ease: 'easeOut' }}
                />
              </div>
            </div>
          ) : (
            <IndeterminateBanner planTask={planTask} onDismiss={dismiss} />
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
