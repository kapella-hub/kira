import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Trash2,
  Send,
  ExternalLink,
  Bot,
  XCircle,
  CheckCircle,
  AlertCircle,
  Loader2,
  Clock,
  Gitlab,
  X,
  Plus,
  ChevronDown,
  Lock,
} from 'lucide-react';
import { SlideOver } from '@/components/ui/SlideOver.tsx';
import { Button } from '@/components/ui/Button.tsx';
import { Input } from '@/components/ui/Input.tsx';
import { PriorityBadge, LabelChip } from '@/components/ui/Badge.tsx';
import { Avatar } from '@/components/ui/Avatar.tsx';
import { TaskStatusBadge } from './TaskStatusBadge.tsx';
import { useUIStore } from '@/stores/uiStore.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { fetchCard, fetchComments, addComment, updateCard, deleteCard } from '@/api/cards.ts';
import { fetchCardTasks, cancelTask } from '@/api/tasks.ts';
import { pushToJira } from '@/api/jira.ts';
import { pushToGitLab } from '@/api/gitlab.ts';
import type { Priority, CardComment } from '@/types/board.ts';
import type { Task, TaskStatus } from '@/types/task.ts';
import type { GitLabSettings } from '@/types/gitlab.ts';
import clsx from 'clsx';

const PRIORITIES: Priority[] = ['critical', 'high', 'medium', 'low', 'none'];

/** Common label suggestions for the "add label" input autocomplete. */
const COMMON_LABELS = [
  'bug',
  'feature',
  'enhancement',
  'documentation',
  'refactor',
  'design',
  'testing',
  'infra',
  'urgent',
  'tech-debt',
];

const taskStatusIcons: Record<TaskStatus, typeof CheckCircle> = {
  pending: Clock,
  claimed: Loader2,
  running: Loader2,
  completed: CheckCircle,
  failed: AlertCircle,
  cancelled: XCircle,
};

const taskStatusColors: Record<TaskStatus, string> = {
  pending: 'text-amber-400',
  claimed: 'text-accent',
  running: 'text-accent',
  completed: 'text-success',
  failed: 'text-error',
  cancelled: 'text-text-muted',
};

export function CardDetail() {
  const { slideOverCardId, closeSlideOver, addToast } = useUIStore();
  const { updateCard: updateCardStore, removeCard } = useBoardStore();
  const board = useBoardStore((s) => s.currentBoard);
  const queryClient = useQueryClient();

  const gitlabSettings = useMemo<GitLabSettings | null>(() => {
    if (!board?.settings_json) return null;
    try {
      const parsed = JSON.parse(board.settings_json);
      return parsed?.gitlab ?? null;
    } catch {
      return null;
    }
  }, [board?.settings_json]);

  const { data: card } = useQuery({
    queryKey: ['card', slideOverCardId],
    queryFn: () => fetchCard(slideOverCardId!),
    enabled: !!slideOverCardId,
  });

  const { data: comments } = useQuery({
    queryKey: ['comments', slideOverCardId],
    queryFn: () => fetchComments(slideOverCardId!),
    enabled: !!slideOverCardId,
  });

  const { data: tasks } = useQuery({
    queryKey: ['card-tasks', slideOverCardId],
    queryFn: () => fetchCardTasks(slideOverCardId!),
    enabled: !!slideOverCardId,
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActive = data?.some(
        (t: Task) => t.status === 'running' || t.status === 'pending' || t.status === 'claimed',
      );
      return hasActive ? 3000 : false;
    },
  });

  // --- Local form state ---
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<Priority>('medium');
  const [labels, setLabels] = useState<string[]>([]);
  const [commentText, setCommentText] = useState('');

  // Priority dropdown
  const [priorityOpen, setPriorityOpen] = useState(false);
  const priorityRef = useRef<HTMLDivElement>(null);

  // Label editing
  const [labelInput, setLabelInput] = useState('');
  const [labelInputFocused, setLabelInputFocused] = useState(false);
  const labelInputRef = useRef<HTMLInputElement>(null);

  // Sync server data into local state when card loads/changes
  useEffect(() => {
    if (card) {
      setTitle(card.title);
      setDescription(card.description);
      setPriority(card.priority);
      setLabels(card.labels);
    }
  }, [card]);

  // Close priority dropdown on outside click
  useEffect(() => {
    if (!priorityOpen) return;
    function onClickOutside(e: MouseEvent) {
      if (priorityRef.current && !priorityRef.current.contains(e.target as Node)) {
        setPriorityOpen(false);
      }
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [priorityOpen]);

  // --- Persist helpers (auto-save on blur / immediate for priority & labels) ---

  const persistField = useCallback(
    async (updates: Record<string, unknown>) => {
      if (!card) return;
      try {
        const updated = await updateCard(card.id, updates);
        updateCardStore(updated);
      } catch {
        addToast('Failed to update card', 'error');
      }
    },
    [card, updateCardStore, addToast],
  );

  function handleTitleBlur() {
    const trimmed = title.trim();
    if (card && trimmed && trimmed !== card.title) {
      persistField({ title: trimmed });
    }
  }

  function handleDescriptionBlur() {
    const trimmed = description.trim();
    if (card && trimmed !== card.description) {
      persistField({ description: trimmed });
    }
  }

  async function handlePriorityChange(p: Priority) {
    setPriority(p);
    setPriorityOpen(false);
    await persistField({ priority: p });
  }

  async function handleRemoveLabel(label: string) {
    const next = labels.filter((l) => l !== label);
    setLabels(next);
    await persistField({ labels: next });
  }

  async function handleAddLabel(label: string) {
    const trimmed = label.trim().toLowerCase();
    if (!trimmed || labels.includes(trimmed)) return;
    const next = [...labels, trimmed];
    setLabels(next);
    setLabelInput('');
    await persistField({ labels: next });
  }

  // Label suggestions: filter COMMON_LABELS that are not already applied and match input
  const labelSuggestions = useMemo(() => {
    if (!labelInput.trim()) return [];
    const q = labelInput.trim().toLowerCase();
    return COMMON_LABELS.filter((l) => l.includes(q) && !labels.includes(l)).slice(0, 5);
  }, [labelInput, labels]);

  // --- Delete ---
  async function handleDelete() {
    if (!card) return;
    try {
      await deleteCard(card.id);
      removeCard(card.id);
      closeSlideOver();
      addToast('Card deleted', 'success');
    } catch {
      addToast('Failed to delete card', 'error');
    }
  }

  // --- Comment ---
  async function handleComment() {
    if (!card || !commentText.trim()) return;
    try {
      await addComment(card.id, commentText.trim());
      setCommentText('');
      await queryClient.invalidateQueries({ queryKey: ['comments', card.id] });
    } catch {
      addToast('Failed to add comment', 'error');
    }
  }

  // --- Integrations ---
  async function handlePushJira() {
    if (!card) return;
    try {
      const result = await pushToJira(card.id);
      if ('task_id' in result) {
        addToast('Jira push queued', 'success');
      } else {
        addToast(`Pushed to Jira: ${result.jira_key}`, 'success');
      }
    } catch {
      addToast('Failed to push to Jira', 'error');
    }
  }

  async function handlePushGitLab() {
    if (!card) return;
    try {
      const result = await pushToGitLab(card.id);
      addToast(`GitLab push queued (task ${result.task_id})`, 'success');
    } catch {
      addToast('Failed to push to GitLab', 'error');
    }
  }

  async function handleCancelTask(taskId: string) {
    try {
      await cancelTask(taskId);
      addToast('Task cancelled', 'info');
      await queryClient.invalidateQueries({ queryKey: ['card-tasks', slideOverCardId] });
    } catch {
      addToast('Failed to cancel task', 'error');
    }
  }

  const isLocked = card?.agent_status === 'pending' || card?.agent_status === 'running';

  return (
    <SlideOver open={!!slideOverCardId} onClose={closeSlideOver} title="Card Detail">
      {card ? (
        <div className="flex flex-col h-full">
          {isLocked && (
            <div className="flex items-center gap-2 px-4 py-2 bg-amber-500/10 border-b border-amber-500/20">
              <Lock size={13} className="text-amber-400" />
              <span className="text-xs text-amber-300">
                This card is locked while an agent is working on it
              </span>
            </div>
          )}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            {/* ---- Metadata bar ---- */}
            <div className="flex items-center gap-3 flex-wrap">
              {/* Priority dropdown */}
              <div className="relative" ref={priorityRef}>
                <button
                  onClick={() => !isLocked && setPriorityOpen(!priorityOpen)}
                  disabled={isLocked}
                  className={clsx(
                    'inline-flex items-center gap-1 rounded-md transition-colors',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
                    isLocked
                      ? 'opacity-50 cursor-not-allowed'
                      : 'hover:bg-white/5',
                  )}
                  aria-label="Change priority"
                  aria-expanded={priorityOpen}
                >
                  <PriorityBadge priority={priority} />
                  <ChevronDown
                    size={11}
                    className={clsx(
                      'text-text-muted transition-transform',
                      priorityOpen && 'rotate-180',
                    )}
                  />
                </button>

                {priorityOpen && (
                  <div className="absolute left-0 top-full mt-1 z-10 py-1 rounded-lg glass border border-card-border-hover shadow-xl min-w-[120px]">
                    {PRIORITIES.map((p) => (
                      <button
                        key={p}
                        onClick={() => handlePriorityChange(p)}
                        className={clsx(
                          'w-full flex items-center gap-2 px-2.5 py-1.5 text-left transition-colors',
                          'hover:bg-white/5',
                          priority === p && 'bg-white/5',
                        )}
                      >
                        <PriorityBadge priority={p} />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Assignee chip */}
              {card.assignee_id && (
                <div className="flex items-center gap-1.5">
                  <Avatar name={card.assignee_id} size="sm" />
                  <span className="text-xs text-text-secondary">{card.assignee_id}</span>
                </div>
              )}

              {/* Due date chip */}
              {card.due_date && (
                <span
                  className={clsx(
                    'inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-md',
                    'bg-white/5 border border-white/8',
                    new Date(card.due_date) < new Date()
                      ? 'text-error'
                      : 'text-text-secondary',
                  )}
                >
                  <Clock size={11} />
                  {new Date(card.due_date).toLocaleDateString(undefined, {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                  })}
                </span>
              )}

              {/* Agent status badge */}
              {card.agent_status && (
                <TaskStatusBadge status={card.agent_status} />
              )}
            </div>

            <div className="border-t border-divider" />

            {/* ---- Title ---- */}
            <div>
              <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-1 block">
                Title
              </label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onBlur={handleTitleBlur}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                }}
                disabled={isLocked}
                className={clsx(
                  'w-full bg-transparent text-base font-semibold text-text-primary border-b border-transparent outline-none pb-1 transition-colors',
                  isLocked
                    ? 'opacity-50 cursor-not-allowed'
                    : 'hover:border-divider focus:border-accent',
                )}
              />
            </div>

            {/* ---- Description ---- */}
            <div>
              <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-1 block">
                Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onBlur={handleDescriptionBlur}
                rows={4}
                disabled={isLocked}
                className={clsx(
                  'w-full glass-input rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted resize-none',
                  isLocked && 'opacity-50 cursor-not-allowed',
                )}
                placeholder="Add a description..."
              />
            </div>

            {/* ---- Labels (editable) ---- */}
            <div>
              <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-2 block">
                Labels
              </label>
              <div className="flex flex-wrap items-center gap-1.5">
                {labels.map((l) => (
                  <span
                    key={l}
                    className="inline-flex items-center gap-1 group/label"
                  >
                    <LabelChip label={l} />
                    {!isLocked && (
                      <button
                        onClick={() => handleRemoveLabel(l)}
                        className="opacity-0 group-hover/label:opacity-100 transition-opacity p-0.5 rounded hover:bg-white/10 text-text-muted hover:text-error -ml-0.5"
                        aria-label={`Remove label ${l}`}
                      >
                        <X size={10} />
                      </button>
                    )}
                  </span>
                ))}

                {/* Add label input */}
                {!isLocked && (
                <div className="relative">
                  <div className="inline-flex items-center gap-1 glass-input rounded-md pl-1.5 pr-2 py-0.5">
                    <Plus size={10} className="text-text-muted shrink-0" />
                    <input
                      ref={labelInputRef}
                      value={labelInput}
                      onChange={(e) => setLabelInput(e.target.value)}
                      onFocus={() => setLabelInputFocused(true)}
                      onBlur={() => {
                        // Delay so click on suggestion registers
                        setTimeout(() => setLabelInputFocused(false), 150);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          handleAddLabel(labelInput);
                        }
                        if (e.key === 'Escape') {
                          setLabelInput('');
                          labelInputRef.current?.blur();
                        }
                      }}
                      placeholder="Add label"
                      className="bg-transparent text-[11px] text-text-primary placeholder:text-text-muted outline-none w-16 focus:w-24 transition-[width] duration-150"
                    />
                  </div>

                  {/* Suggestions dropdown */}
                  {labelInputFocused && labelSuggestions.length > 0 && (
                    <div className="absolute left-0 top-full mt-1 z-10 py-1 rounded-lg glass border border-card-border-hover shadow-xl min-w-[120px]">
                      {labelSuggestions.map((s) => (
                        <button
                          key={s}
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => handleAddLabel(s)}
                          className="w-full text-left px-2.5 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-white/5 transition-colors"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                )}
              </div>
            </div>

            {/* ---- Integrations section ---- */}
            <div className="border-t border-divider pt-4 space-y-4">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                Integrations
              </h4>

              {/* Jira */}
              <div className="flex items-center gap-2">
                {card.jira_key ? (
                  <>
                    <span className="text-sm text-jira font-medium">{card.jira_key}</span>
                    <span
                      className={clsx(
                        'text-[10px] px-1.5 py-0.5 rounded',
                        card.jira_sync_status === 'synced' && 'bg-success/15 text-success',
                        card.jira_sync_status === 'pending' && 'bg-warning/15 text-warning',
                        card.jira_sync_status === 'conflict' && 'bg-error/15 text-error',
                      )}
                    >
                      {card.jira_sync_status || 'Not synced'}
                    </span>
                  </>
                ) : (
                  <Button variant="ghost" size="sm" onClick={handlePushJira}>
                    <ExternalLink size={13} />
                    Push to Jira
                  </Button>
                )}
              </div>

              {/* GitLab */}
              {gitlabSettings && (
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="sm" onClick={handlePushGitLab}>
                    <Gitlab size={13} />
                    Push to GitLab
                  </Button>
                  <a
                    href={gitlabSettings.project_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-text-secondary hover:text-accent transition-colors inline-flex items-center gap-1"
                  >
                    {gitlabSettings.project_path}
                    <ExternalLink size={10} />
                  </a>
                </div>
              )}
            </div>

            {/* ---- Task History ---- */}
            <div className="border-t border-divider pt-4">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-3">
                Task History ({tasks?.length ?? 0})
              </h4>
              <div className="space-y-2">
                {tasks?.map((task: Task) => {
                  const StatusIcon = taskStatusIcons[task.status];
                  const isActive =
                    task.status === 'running' ||
                    task.status === 'pending' ||
                    task.status === 'claimed';
                  return (
                    <div
                      key={task.id}
                      className="flex items-center gap-3 p-2.5 rounded-lg glass transition-all"
                    >
                      <StatusIcon
                        size={14}
                        className={clsx(
                          taskStatusColors[task.status],
                          (task.status === 'running' || task.status === 'claimed') &&
                            'animate-spin',
                        )}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <Bot size={10} className="text-accent shrink-0" />
                          <p className="text-sm font-medium text-text-primary capitalize">
                            {task.agent_type || task.task_type}
                          </p>
                          {task.loop_count > 0 && (
                            <span className="text-[9px] font-mono text-warning px-1 py-0.5 rounded bg-warning/10">
                              loop {task.loop_count}/{task.max_loop_count}
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-text-muted mt-0.5">
                          {task.started_at
                            ? new Date(task.started_at).toLocaleString()
                            : new Date(task.created_at).toLocaleString()}
                          {task.error_summary && (
                            <span className="text-error ml-1">
                              &middot; {task.error_summary}
                            </span>
                          )}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          className={clsx(
                            'text-[10px] font-medium capitalize',
                            taskStatusColors[task.status],
                          )}
                        >
                          {task.status}
                        </span>
                        {isActive && (
                          <button
                            onClick={() => handleCancelTask(task.id)}
                            className="p-1 rounded hover:bg-white/5 text-text-muted hover:text-error transition-colors"
                            aria-label="Cancel task"
                          >
                            <XCircle size={13} />
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
                {tasks?.length === 0 && (
                  <p className="text-xs text-text-muted text-center py-3">No tasks yet</p>
                )}
                {!tasks && (
                  <div className="space-y-2">
                    <div className="skeleton h-10 w-full rounded-lg" />
                    <div className="skeleton h-10 w-full rounded-lg" />
                  </div>
                )}
              </div>
            </div>

            {/* ---- Comments ---- */}
            <div className="border-t border-divider pt-4">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted mb-3">
                Comments ({comments?.length ?? 0})
              </h4>
              <div className="space-y-3">
                {comments?.map((c: CardComment) => (
                  <div key={c.id} className="flex gap-2">
                    {c.is_agent_output ? (
                      <div className="w-5 h-5 rounded-full bg-accent/20 flex items-center justify-center shrink-0 mt-0.5">
                        <Bot size={10} className="text-accent" />
                      </div>
                    ) : (
                      <Avatar name={c.user_id} size="sm" className="mt-0.5" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-text-primary">
                          {c.is_agent_output ? 'Agent' : c.user_id}
                        </span>
                        <span className="text-[10px] text-text-muted">
                          {new Date(c.created_at).toLocaleString()}
                        </span>
                        {c.is_agent_output && (
                          <span className="text-[10px] px-1 py-0.5 rounded bg-accent/10 text-accent">
                            Agent
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-text-secondary mt-0.5 whitespace-pre-wrap">
                        {c.content}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Add comment */}
              <div className="flex gap-2 mt-3">
                <Input
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleComment();
                    }
                  }}
                  placeholder="Write a comment..."
                  className="flex-1"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleComment}
                  disabled={!commentText.trim()}
                >
                  <Send size={13} />
                </Button>
              </div>
            </div>
          </div>

          {/* Footer action: delete only (save is auto) */}
          <div className="flex items-center justify-between p-4 border-t border-divider shrink-0">
            {isLocked ? (
              <div />
            ) : (
              <Button variant="danger" size="sm" onClick={handleDelete}>
                <Trash2 size={13} />
                Delete
              </Button>
            )}
            <span className="text-[11px] text-text-muted">
              {isLocked ? 'Editing disabled while agent is working' : 'Changes save automatically'}
            </span>
          </div>
        </div>
      ) : (
        <div className="p-5 space-y-3">
          <div className="skeleton h-6 w-3/4" />
          <div className="skeleton h-20 w-full" />
          <div className="skeleton h-4 w-1/2" />
        </div>
      )}
    </SlideOver>
  );
}
