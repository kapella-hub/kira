import { Check, RefreshCw, AlertTriangle } from 'lucide-react';
import type { JiraSyncStatus } from '@/types/board.ts';
import clsx from 'clsx';

const statusConfig: Record<string, { icon: typeof Check; color: string; label: string }> = {
  synced: { icon: Check, color: 'text-success', label: 'Synced' },
  pending: { icon: RefreshCw, color: 'text-warning', label: 'Pending' },
  conflict: { icon: AlertTriangle, color: 'text-error', label: 'Conflict' },
  error: { icon: AlertTriangle, color: 'text-error', label: 'Error' },
};

export function JiraBadge({ status }: { status: JiraSyncStatus }) {
  if (!status) return null;
  const config = statusConfig[status];
  if (!config) return null;
  const Icon = config.icon;

  return (
    <span className={clsx('inline-flex items-center gap-0.5 text-[10px] font-medium', config.color)}>
      <Icon size={10} />
      {config.label}
    </span>
  );
}
