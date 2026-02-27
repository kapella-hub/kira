import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { motion, AnimatePresence } from 'framer-motion';
import { MoreHorizontal, Bot, ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import type { Column as ColumnType, Card as CardType } from '@/types/board.ts';
import { KanbanCard } from './Card.tsx';
import { NewCard } from './NewCard.tsx';
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown.tsx';
import { deleteColumn, updateColumn } from '@/api/boards.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { useUIStore } from '@/stores/uiStore.ts';
import { useState } from 'react';

interface ColumnProps {
  column: ColumnType;
  cards: CardType[];
}

export function KanbanColumn({ column, cards }: ColumnProps) {
  const { removeColumn, updateColumn: updateColStore } = useBoardStore();
  const { addToast, openModal } = useUIStore();
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(column.name);
  const [collapsed, setCollapsed] = useState(column.collapsed ?? false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { setNodeRef, isOver } = useDroppable({
    id: column.id,
    data: { type: 'column', column },
  });

  const overWip = column.wip_limit > 0 && cards.length > column.wip_limit;
  const atWip = column.wip_limit > 0 && cards.length === column.wip_limit;
  const hasAutomation = !!column.agent_type;

  async function handleDelete() {
    try {
      await deleteColumn(column.id);
      removeColumn(column.id);
      addToast('Column deleted', 'success');
    } catch {
      addToast('Failed to delete column', 'error');
    }
    setConfirmDelete(false);
  }

  async function handleRename() {
    if (editName.trim() && editName.trim() !== column.name) {
      try {
        await updateColumn(column.id, { name: editName.trim() });
        updateColStore(column.id, { name: editName.trim() });
      } catch {
        addToast('Failed to rename column', 'error');
      }
    }
    setEditing(false);
  }

  function toggleCollapse() {
    if (editing) return;
    setCollapsed((prev) => !prev);
  }

  return (
    <div
      className={clsx(
        'flex flex-col shrink-0 h-full rounded-xl transition-shadow duration-300',
        collapsed ? 'w-[48px]' : 'w-[290px]',
        hasAutomation && 'column-automated',
      )}
    >
      {/* Column header */}
      <div
        className={clsx(
          'flex items-center justify-between px-2 py-2 mb-1 group/header',
          !editing && 'cursor-pointer',
        )}
        onClick={toggleCollapse}
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        aria-label={`${column.name} column, ${cards.length} cards${collapsed ? ', collapsed' : ''}`}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggleCollapse();
          }
        }}
      >
        {collapsed ? (
          /* Collapsed: vertical layout with name rotated */
          <div className="flex flex-col items-center gap-2 w-full py-1">
            <div className="flex items-center gap-1">
              <ChevronRight size={12} className="text-text-muted shrink-0" />
              <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: column.color }} />
            </div>
            <span
              className={clsx(
                'text-[10px] font-medium px-1.5 py-0.5 rounded-full',
                overWip
                  ? 'bg-error/15 text-error'
                  : atWip
                    ? 'bg-warning/15 text-warning'
                    : 'bg-white/5 text-text-muted',
              )}
            >
              {cards.length}
            </span>
            <span
              className="text-xs font-semibold text-text-primary whitespace-nowrap"
              style={{ writingMode: 'vertical-lr' }}
            >
              {column.name}
            </span>
          </div>
        ) : (
          /* Expanded header */
          <>
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: column.color }} />
              {editing ? (
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => {
                    e.stopPropagation();
                    if (e.key === 'Enter') handleRename();
                    if (e.key === 'Escape') {
                      setEditing(false);
                      setEditName(column.name);
                    }
                  }}
                  onBlur={handleRename}
                  onClick={(e) => e.stopPropagation()}
                  className="bg-transparent text-sm font-semibold text-text-primary outline-none border-b border-accent w-full"
                  autoFocus
                />
              ) : (
                <h3
                  className="text-sm font-semibold text-text-primary truncate"
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    setEditing(true);
                  }}
                  title="Double-click to rename"
                >
                  {column.name}
                </h3>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              {/* Card count badge */}
              <span
                className={clsx(
                  'text-[10px] font-medium px-1.5 py-0.5 rounded-full',
                  overWip
                    ? 'bg-error/15 text-error'
                    : atWip
                      ? 'bg-warning/15 text-warning'
                      : 'bg-white/5 text-text-muted',
                )}
              >
                {cards.length}
                {column.wip_limit > 0 && `/${column.wip_limit}`}
              </span>

              {/* Settings dropdown - visible on hover */}
              <div
                className="opacity-0 group-hover/header:opacity-100 transition-opacity"
                onClick={(e) => e.stopPropagation()}
              >
                <Dropdown
                  align="right"
                  trigger={
                    <button
                      className="p-1 rounded hover:bg-white/5 text-text-muted transition-colors"
                      aria-label={`${column.name} column options`}
                    >
                      <MoreHorizontal size={14} />
                    </button>
                  }
                >
                  <DropdownItem onClick={() => setEditing(true)}>Rename</DropdownItem>
                  <DropdownItem onClick={() => openModal('column-config', { columnId: column.id })}>
                    Configure automation
                  </DropdownItem>
                  <DropdownItem destructive onClick={() => setConfirmDelete(true)}>
                    Delete column
                  </DropdownItem>
                </Dropdown>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Agent type badge - shown below header when expanded and auto_run is enabled */}
      {!collapsed && hasAutomation && column.auto_run && (
        <div className="px-2 -mt-1 mb-1">
          <span
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] text-accent/70"
            title={`Auto-run: ${column.agent_type}`}
          >
            <Bot size={9} />
            auto: {column.agent_type}
          </span>
        </div>
      )}

      {/* Cards container - hidden when collapsed */}
      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="flex-1 flex flex-col min-h-0"
          >
            <div
              ref={setNodeRef}
              className={clsx(
                'flex-1 overflow-y-auto rounded-lg p-1.5 transition-colors duration-150 group',
                isOver && 'bg-accent/5 ring-1 ring-accent/20',
              )}
            >
              <SortableContext items={cards.map((c) => c.id)} strategy={verticalListSortingStrategy}>
                <div className="flex flex-col gap-1.5">
                  {cards.map((card) => (
                    <KanbanCard key={card.id} card={card} />
                  ))}
                </div>
              </SortableContext>

              {cards.length === 0 && !isOver && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex flex-col items-center justify-center py-8 text-center"
                >
                  <p className="text-xs text-text-muted">
                    {hasAutomation && column.auto_run
                      ? 'Drop cards here to trigger agent'
                      : 'No cards yet'}
                  </p>
                </motion.div>
              )}
            </div>

            {/* Add card */}
            <div className="px-1 py-1.5">
              <NewCard columnId={column.id} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Delete confirmation dialog */}
      <AnimatePresence>
        {confirmDelete && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50"
            onClick={() => setConfirmDelete(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="glass rounded-xl p-5 shadow-2xl w-[340px]"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="text-sm font-semibold text-text-primary mb-2">Delete column?</h3>
              <p className="text-xs text-text-secondary mb-4">
                This will permanently delete the &quot;{column.name}&quot; column and all {cards.length}{' '}
                {cards.length === 1 ? 'card' : 'cards'} in it. This action cannot be undone.
              </p>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="px-3 py-1.5 text-xs rounded-md hover:bg-white/5 text-text-secondary transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  className="px-3 py-1.5 text-xs rounded-md bg-error/80 hover:bg-error text-white transition-colors"
                >
                  Delete
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
