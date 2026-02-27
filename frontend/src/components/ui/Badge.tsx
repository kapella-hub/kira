import clsx from 'clsx';
import type { Priority } from '@/types/board.ts';

const priorityColors: Record<Priority, string> = {
  critical: 'bg-priority-critical/15 text-priority-critical border-priority-critical/25',
  high: 'bg-priority-high/15 text-priority-high border-priority-high/25',
  medium: 'bg-priority-medium/15 text-priority-medium border-priority-medium/25',
  low: 'bg-priority-low/15 text-priority-low border-priority-low/25',
  none: 'bg-white/5 text-text-secondary border-white/10',
};

const priorityLabels: Record<Priority, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  none: 'None',
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border',
        priorityColors[priority],
      )}
    >
      {priorityLabels[priority]}
    </span>
  );
}

interface LabelChipProps {
  label: string;
  color?: string;
}

const chipColors = [
  'bg-indigo-400/15 text-indigo-300 border-indigo-400/25',
  'bg-emerald-400/15 text-emerald-300 border-emerald-400/25',
  'bg-amber-400/15 text-amber-300 border-amber-400/25',
  'bg-pink-400/15 text-pink-300 border-pink-400/25',
  'bg-cyan-400/15 text-cyan-300 border-cyan-400/25',
  'bg-violet-400/15 text-violet-300 border-violet-400/25',
];

function hashColor(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash) % chipColors.length;
}

export function LabelChip({ label }: LabelChipProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border',
        chipColors[hashColor(label)],
      )}
    >
      {label}
    </span>
  );
}
