import { useEffect, useRef, useCallback } from 'react';
import { useBoardStore } from '@/stores/boardStore.ts';
import type { SSEEvent } from '@/types/events.ts';
import type { AgentStatus } from '@/types/board.ts';
import type { Worker } from '@/types/worker.ts';

const MAX_RETRIES = 10;
const BASE_DELAY = 1000;

/**
 * Map task status to card agent_status.
 * The card's agent_status field tracks the most recent task state.
 */
function taskStatusToAgentStatus(taskStatus: string): AgentStatus {
  switch (taskStatus) {
    case 'pending':
    case 'claimed':
      return 'pending';
    case 'running':
      return 'running';
    case 'completed':
      return 'completed';
    case 'failed':
      return 'failed';
    default:
      return '';
  }
}

export function useSSE(boardId: string | null) {
  const esRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);
  const {
    addCard,
    updateCard,
    removeCard,
    moveCard,
    addColumn,
    reorderColumns,
  } = useBoardStore();

  const handleEvent = useCallback(
    (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as SSEEvent;
        switch (data.type) {
          case 'card_created':
            addCard(data.card);
            break;
          case 'card_updated':
            updateCard(data.card);
            break;
          case 'card_deleted':
            removeCard(data.card_id);
            break;
          case 'card_moved':
            moveCard(data.card_id, data.from_column, data.to_column, data.position);
            break;
          case 'column_created':
            addColumn(data.column);
            break;
          case 'column_reordered':
            reorderColumns(data.column_ids);
            break;

          // Task events - update card agent_status + track board_plan tasks
          case 'task_created':
          case 'task_claimed': {
            const task = data.task;
            if (task.card_id) {
              const agentStatus = taskStatusToAgentStatus(task.status);
              updateCardAgentStatus(task.card_id, agentStatus);
            }
            // Track board_plan / card_gen task for progress indicator
            if (task.task_type === 'board_plan' || task.task_type === 'card_gen') {
              const { setPlanTask } = useBoardStore.getState();
              const label = task.task_type === 'card_gen' ? 'cards' : 'board plan';
              setPlanTask({
                taskId: task.id,
                status: task.status === 'claimed' ? 'claimed' : 'pending',
                progressText: `Preparing to generate ${label}...`,
              });
            }
            break;
          }
          case 'task_progress': {
            if (data.task_id) {
              const { planTask, updatePlanTaskStatus } = useBoardStore.getState();
              if (planTask?.taskId === data.task_id) {
                updatePlanTaskStatus('running', data.progress_text || 'Generating...', {
                  step: data.step,
                  totalSteps: data.total_steps,
                  phase: data.phase,
                });
              }
            }
            break;
          }
          case 'task_completed': {
            const task = data.task;
            if (task.card_id) {
              updateCardAgentStatus(task.card_id, 'completed');
            }
            // board_plan with auto_generate_cards: show transition instead of clearing
            if (task.task_type === 'board_plan') {
              const { updatePlanTaskStatus } = useBoardStore.getState();
              updatePlanTaskStatus('running', 'Board created, now generating cards...');
              // The chained card_gen task_created event will update the banner
            } else if (task.task_type === 'card_gen') {
              const { setPlanTask } = useBoardStore.getState();
              setPlanTask(null);
            }
            break;
          }
          case 'task_failed': {
            const task = data.task;
            if (task.card_id) {
              updateCardAgentStatus(task.card_id, 'failed');
            }
            // Show failure in progress banner
            if (task.task_type === 'board_plan' || task.task_type === 'card_gen') {
              const { updatePlanTaskStatus } = useBoardStore.getState();
              const failLabel = task.task_type === 'card_gen' ? 'Card generation failed' : 'Plan generation failed';
              updatePlanTaskStatus('failed', task.error_summary || failLabel);
            }
            break;
          }
          case 'task_cancelled': {
            if (data.task.card_id) {
              updateCardAgentStatus(data.task.card_id, '');
            }
            if (data.task.task_type === 'board_plan' || data.task.task_type === 'card_gen') {
              const { setPlanTask } = useBoardStore.getState();
              setPlanTask(null);
            }
            break;
          }

          // Worker events - update via global callback
          case 'worker_online':
          case 'worker_offline': {
            const workerUpdate = (window as unknown as Record<string, unknown>).__workerStatusUpdate as
              | ((worker: Worker) => void)
              | undefined;
            if (workerUpdate) {
              workerUpdate(data.worker);
            }
            break;
          }

          case 'heartbeat':
            break;
        }
      } catch {
        // ignore parse errors
      }
    },
    [addCard, updateCard, removeCard, moveCard, addColumn, reorderColumns],
  );

  /**
   * Helper to update just the agent_status on a card already in the store.
   * We find the card across all columns, clone it with the new status, and
   * call updateCard to trigger a re-render.
   */
  function updateCardAgentStatus(cardId: string, agentStatus: AgentStatus) {
    const { cardsByColumn } = useBoardStore.getState();
    for (const cards of Object.values(cardsByColumn)) {
      const card = cards.find((c) => c.id === cardId);
      if (card) {
        updateCard({ ...card, agent_status: agentStatus });
        break;
      }
    }
  }

  const connect = useCallback(() => {
    if (!boardId) return;
    esRef.current?.close();

    const token = localStorage.getItem('token');
    const url = `/api/events/stream?board_id=${boardId}${token ? `&token=${token}` : ''}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = handleEvent;

    es.onopen = () => {
      retriesRef.current = 0;
    };

    es.onerror = () => {
      es.close();
      if (retriesRef.current < MAX_RETRIES) {
        const delay = BASE_DELAY * Math.pow(2, retriesRef.current);
        retriesRef.current++;
        setTimeout(connect, delay);
      }
    };
  }, [boardId, handleEvent]);

  useEffect(() => {
    connect();
    return () => {
      esRef.current?.close();
      esRef.current = null;
    };
  }, [connect]);
}
