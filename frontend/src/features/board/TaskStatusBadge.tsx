import { Check, X, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import type { AgentStatus } from '@/types/board.ts';

interface TaskStatusBadgeProps {
  status: AgentStatus;
  loopCount?: number;
  progressText?: string;
  compact?: boolean;
}

const statusConfig: Record<Exclude<AgentStatus, ''>, {
  label: string;
  color: string;
  bgColor: string;
  borderColor: string;
}> = {
  pending: {
    label: 'Pending',
    color: 'text-amber-400',
    bgColor: 'bg-amber-400/10',
    borderColor: 'border-amber-400/20',
  },
  running: {
    label: 'Running',
    color: 'text-accent',
    bgColor: 'bg-accent/10',
    borderColor: 'border-accent/20',
  },
  completed: {
    label: 'Done',
    color: 'text-success',
    bgColor: 'bg-success/10',
    borderColor: 'border-success/20',
  },
  failed: {
    label: 'Failed',
    color: 'text-error',
    bgColor: 'bg-error/10',
    borderColor: 'border-error/20',
  },
};

export function TaskStatusBadge({ status, loopCount, progressText, compact }: TaskStatusBadgeProps) {
  if (!status) return null;

  const config = statusConfig[status];
  if (!config) return null;

  return (
    <div
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border',
        config.bgColor,
        config.borderColor,
        compact ? 'px-1.5 py-0.5' : 'px-2 py-0.5',
      )}
    >
      {/* Status icon */}
      {status === 'pending' && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-amber-400" />
        </span>
      )}
      {status === 'running' && (
        <Loader2 size={compact ? 9 : 10} className={clsx(config.color, 'animate-spin')} />
      )}
      {status === 'completed' && (
        <Check size={compact ? 9 : 10} className={config.color} />
      )}
      {status === 'failed' && (
        <X size={compact ? 9 : 10} className={config.color} />
      )}

      {/* Label */}
      {!compact && (
        <span className={clsx('text-[10px] font-medium', config.color)}>
          {progressText && status === 'running' ? progressText : config.label}
        </span>
      )}

      {/* Loop count */}
      {loopCount != null && loopCount > 0 && (
        <span className={clsx('text-[9px] font-mono', config.color)}>
          x{loopCount}
        </span>
      )}
    </div>
  );
}
