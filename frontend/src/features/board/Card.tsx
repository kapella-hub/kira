import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { motion } from 'framer-motion';
import { Clock, ExternalLink, Lock } from 'lucide-react';
import clsx from 'clsx';
import type { Card as CardType, AgentStatus } from '@/types/board.ts';
import { LabelChip } from '@/components/ui/Badge.tsx';
import { Avatar } from '@/components/ui/Avatar.tsx';
import { useUIStore } from '@/stores/uiStore.ts';

const priorityBorder: Record<string, string> = {
  critical: 'border-l-priority-critical',
  high: 'border-l-priority-high',
  medium: 'border-l-priority-medium',
  low: 'border-l-priority-low',
  none: 'border-l-transparent',
};

/** Small colored dot indicating agent execution status. */
const agentDotStyle: Record<Exclude<AgentStatus, ''>, string> = {
  completed: 'bg-success',
  running: 'bg-warning animate-pulse',
  failed: 'bg-error',
  pending: 'bg-accent animate-pulse',
};

function isOverdue(date: string | null): boolean {
  if (!date) return false;
  return new Date(date) < new Date();
}

interface CardProps {
  card: CardType;
  overlay?: boolean;
}

export function KanbanCard({ card, overlay }: CardProps) {
  const openSlideOver = useUIStore((s) => s.openSlideOver);
  const isLocked = card.agent_status === 'pending' || card.agent_status === 'running';
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: card.id,
    data: { type: 'card', card },
    disabled: isLocked,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const hasFooter = card.due_date || card.jira_key || card.assignee_id;
  const visibleLabels = card.labels.slice(0, 2);
  const extraLabelCount = card.labels.length - 2;

  return (
    <motion.div
      ref={setNodeRef}
      style={style}
      layout={!isDragging}
      layoutId={overlay ? undefined : card.id}
      {...attributes}
      {...listeners}
      onClick={() => openSlideOver(card.id)}
      title={isLocked ? 'Card is locked while agent is working' : undefined}
      className={clsx(
        'rounded-lg border border-card-border',
        'bg-card hover:bg-card-hover hover:border-card-border-hover',
        'border-l-[3px] px-3 py-2.5 group/card transition-[background,border-color] duration-150',
        priorityBorder[card.priority] ?? 'border-l-transparent',
        isDragging && 'opacity-30',
        overlay && 'shadow-2xl shadow-black/40 rotate-1 scale-[1.02]',
        isLocked ? 'cursor-default opacity-80' : 'cursor-grab active:cursor-grabbing',
      )}
    >
      {/* Row 1: Title + agent dot */}
      <div className="flex items-start gap-2">
        <p className="text-sm font-medium text-text-primary leading-snug line-clamp-2 flex-1">
          {card.title}
        </p>
        {card.agent_status && (
          <div className="flex items-center gap-1 mt-1 shrink-0">
            {isLocked && <Lock size={12} className="text-amber-400" />}
            <span
              className={clsx(
                'h-2 w-2 rounded-full',
                agentDotStyle[card.agent_status],
              )}
              title={`Agent: ${card.agent_status}`}
            />
          </div>
        )}
      </div>

      {/* Row 2: Labels (max 2) */}
      {visibleLabels.length > 0 && (
        <div className="flex items-center gap-1 mt-2">
          {visibleLabels.map((l) => (
            <LabelChip key={l} label={l} />
          ))}
          {extraLabelCount > 0 && (
            <span className="text-[10px] text-text-muted leading-none">
              +{extraLabelCount}
            </span>
          )}
        </div>
      )}

      {/* Row 3: Footer metadata + avatar */}
      {hasFooter && (
        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-2">
            {card.jira_key && (
              <span className="inline-flex items-center gap-0.5 text-[10px] text-jira font-medium">
                <ExternalLink size={9} />
                {card.jira_key}
              </span>
            )}

            {card.due_date && (
              <span
                className={clsx(
                  'inline-flex items-center gap-0.5 text-[10px]',
                  isOverdue(card.due_date) ? 'text-error' : 'text-text-muted',
                )}
              >
                <Clock size={9} />
                {new Date(card.due_date).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                })}
              </span>
            )}
          </div>

          {card.assignee_id && (
            <Avatar name={card.assignee_id} size="sm" />
          )}
        </div>
      )}
    </motion.div>
  );
}
