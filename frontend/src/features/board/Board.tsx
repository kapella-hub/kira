import { useState, useCallback, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
  type DragStartEvent,
  type DragEndEvent,
  type DragOverEvent,
} from '@dnd-kit/core';
import { motion } from 'framer-motion';
import { Plus, Sparkles, Columns3 } from 'lucide-react';
import { useBoardData } from '@/hooks/useBoard.ts';
import { useSSE } from '@/hooks/useSSE.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { moveCard as apiMoveCard } from '@/api/cards.ts';
import { createColumn } from '@/api/boards.ts';
import { fetchTasks } from '@/api/tasks.ts';
import { useUIStore } from '@/stores/uiStore.ts';
import { KanbanColumn } from './Column.tsx';
import { KanbanCard } from './Card.tsx';
import { BoardHeader } from './BoardHeader.tsx';
import { CardDetail } from './CardDetail.tsx';
import { PlanProgressBanner } from './PlanProgressBanner.tsx';
import { Button } from '@/components/ui/Button.tsx';
import type { Card } from '@/types/board.ts';

export function Board() {
  const { id } = useParams<{ id: string }>();
  const { isLoading } = useBoardData(id);
  const { columns, cardsByColumn, moveCard, addColumn } = useBoardStore();
  const currentBoard = useBoardStore((s) => s.currentBoard);
  const setPlanTask = useBoardStore((s) => s.setPlanTask);
  const { addToast, openModal } = useUIStore();
  const [activeCard, setActiveCard] = useState<Card | null>(null);

  useSSE(id ?? null);

  // Check for active board_plan tasks on mount
  useEffect(() => {
    if (!id) return;
    fetchTasks(id).then((tasks) => {
      const active = tasks.find(
        (t) =>
          (t.task_type === 'board_plan' || t.task_type === 'card_gen') &&
          ['pending', 'claimed', 'running'].includes(t.status),
      );
      if (active) {
        setPlanTask({
          taskId: active.id,
          status: active.status as 'pending' | 'claimed' | 'running',
          progressText: active.progress_text || 'Generating board plan...',
        });
      }
    }).catch(() => { /* ignore */ });
  }, [id, setPlanTask]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    }),
  );

  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const { active } = event;
      if (active.data.current?.type === 'card') {
        setActiveCard(active.data.current.card as Card);
      }
    },
    [],
  );

  const handleDragOver = useCallback(
    (event: DragOverEvent) => {
      const { active, over } = event;
      if (!over || !active.data.current) return;

      const activeData = active.data.current;
      const overData = over.data.current;

      if (activeData.type !== 'card') return;
      const card = activeData.card as Card;

      let targetColumnId: string;
      let targetPosition: number;

      if (overData?.type === 'column') {
        targetColumnId = over.id as string;
        targetPosition = (cardsByColumn[targetColumnId] ?? []).length;
      } else if (overData?.type === 'card') {
        const overCard = overData.card as Card;
        targetColumnId = overCard.column_id;
        const targetCards = cardsByColumn[targetColumnId] ?? [];
        targetPosition = targetCards.findIndex((c) => c.id === overCard.id);
        if (targetPosition === -1) targetPosition = targetCards.length;
      } else {
        return;
      }

      if (card.column_id !== targetColumnId) {
        moveCard(card.id, card.column_id, targetColumnId, targetPosition);
      }
    },
    [cardsByColumn, moveCard],
  );

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const { active, over } = event;
      setActiveCard(null);

      if (!over || !active.data.current) return;
      const activeData = active.data.current;
      if (activeData.type !== 'card') return;

      const card = activeData.card as Card;
      const overData = over.data.current;

      let targetColumnId: string;
      let targetPosition: number;

      if (overData?.type === 'column') {
        targetColumnId = over.id as string;
        targetPosition = (cardsByColumn[targetColumnId] ?? []).length;
      } else if (overData?.type === 'card') {
        const overCard = overData.card as Card;
        targetColumnId = overCard.column_id;
        const targetCards = cardsByColumn[targetColumnId] ?? [];
        targetPosition = targetCards.findIndex((c) => c.id === overCard.id);
        if (targetPosition === -1) targetPosition = targetCards.length;
      } else {
        return;
      }

      try {
        await apiMoveCard(card.id, { column_id: targetColumnId, position: targetPosition });
      } catch {
        addToast('Failed to move card', 'error');
      }
    },
    [cardsByColumn, addToast],
  );

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <div className="h-12 border-b border-divider" />
        <div className="flex-1 flex gap-4 p-4 overflow-x-auto">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="w-[290px] shrink-0 space-y-3">
              <div className="skeleton h-6 w-24" />
              <div className="skeleton h-24 w-full rounded-lg" />
              <div className="skeleton h-20 w-full rounded-lg" />
              <div className="skeleton h-16 w-full rounded-lg" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!id) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-lg font-semibold text-text-primary mb-1">No board selected</p>
          <p className="text-sm text-text-secondary">
            Pick a board from the sidebar, or create a new one.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <BoardHeader />
      <PlanProgressBanner />

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
      >
        <div className="flex-1 flex gap-3 p-4 overflow-x-auto overflow-y-hidden">
          {columns.map((col) => (
            <motion.div key={col.id} layout className="h-full">
              <KanbanColumn column={col} cards={cardsByColumn[col.id] ?? []} />
            </motion.div>
          ))}

          {columns.length === 0 && (
            <div className="flex items-center justify-center w-full">
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                className="text-center max-w-sm"
              >
                <div className="mx-auto mb-4 w-12 h-12 rounded-xl bg-white/5 flex items-center justify-center">
                  <Columns3 size={24} className="text-text-muted" />
                </div>
                <p className="text-base font-semibold text-text-primary mb-1">No columns yet</p>
                <p className="text-sm text-text-secondary mb-6">
                  Get started by adding a column manually or let AI generate a board structure from a prompt.
                </p>
                <div className="flex items-center justify-center gap-3">
                  <Button
                    variant="secondary"
                    size="md"
                    onClick={async () => {
                      if (!currentBoard) return;
                      try {
                        const col = await createColumn(currentBoard.id, { name: 'New Column' });
                        addColumn(col);
                      } catch {
                        addToast('Failed to add column', 'error');
                      }
                    }}
                  >
                    <Plus size={14} />
                    Add Column
                  </Button>
                  <Button
                    variant="primary"
                    size="md"
                    onClick={() => openModal('generate-board-plan')}
                  >
                    <Sparkles size={14} />
                    Generate from Prompt
                  </Button>
                </div>
              </motion.div>
            </div>
          )}
        </div>

        <DragOverlay>
          {activeCard && <KanbanCard card={activeCard} overlay />}
        </DragOverlay>
      </DndContext>

      <CardDetail />
    </div>
  );
}
