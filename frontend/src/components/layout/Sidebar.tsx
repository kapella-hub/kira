import { useState, useRef, useEffect, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  Plus,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  MoreHorizontal,
  Trash2,
} from 'lucide-react';
import { useBoards } from '@/hooks/useBoard.ts';
import { createBoard, deleteBoard } from '@/api/boards.ts';
import { useUIStore } from '@/stores/uiStore.ts';
import { useBoardStore } from '@/stores/boardStore.ts';
import { useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';

/** Get initials from a board name (up to 2 characters). */
function getBoardInitials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

const initialBgColors = [
  'bg-indigo-500/25',
  'bg-emerald-500/25',
  'bg-amber-500/25',
  'bg-pink-500/25',
  'bg-cyan-500/25',
  'bg-violet-500/25',
];

function hashColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return initialBgColors[Math.abs(hash) % initialBgColors.length];
}

export function Sidebar() {
  const { id: activeBoardId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: boards } = useBoards();
  const { sidebarCollapsed, toggleSidebar, addToast, openModal } = useUIStore();
  const cardsByColumn = useBoardStore((s) => s.cardsByColumn);
  const currentBoard = useBoardStore((s) => s.currentBoard);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [menuBoardId, setMenuBoardId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Count active (pending/running) tasks for the currently loaded board
  const activeBoardTaskCount = useMemo(() => {
    let count = 0;
    for (const cards of Object.values(cardsByColumn)) {
      for (const card of cards) {
        if (card.agent_status === 'pending' || card.agent_status === 'running') {
          count++;
        }
      }
    }
    return count;
  }, [cardsByColumn]);

  // Map: boardId -> active task count. We only have detailed card data for the
  // current board, so only that board gets a badge.
  const taskCountByBoard = useMemo(() => {
    const map: Record<string, number> = {};
    if (currentBoard && activeBoardTaskCount > 0) {
      map[currentBoard.id] = activeBoardTaskCount;
    }
    return map;
  }, [currentBoard, activeBoardTaskCount]);

  useEffect(() => {
    if (!menuBoardId) return;
    function handler(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuBoardId(null);
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuBoardId]);

  async function handleDelete(boardId: string) {
    try {
      await deleteBoard(boardId);
      await queryClient.invalidateQueries({ queryKey: ['boards'] });
      if (activeBoardId === boardId) {
        const remaining = boards?.filter((b) => b.id !== boardId);
        navigate(remaining?.length ? `/boards/${remaining[0].id}` : '/');
      }
      addToast('Board deleted', 'success');
    } catch {
      addToast('Failed to delete board', 'error');
    }
    setConfirmDelete(null);
    setMenuBoardId(null);
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    try {
      const board = await createBoard({ name: newName.trim() });
      await queryClient.invalidateQueries({ queryKey: ['boards'] });
      navigate(`/boards/${board.id}`);
      setCreating(false);
      setNewName('');
    } catch {
      addToast('Failed to create board', 'error');
    }
  }

  const boardCount = boards?.length ?? 0;

  return (
    <motion.aside
      animate={{ width: sidebarCollapsed ? 48 : 240 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className="h-full glass-surface border-r border-divider flex flex-col shrink-0 overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-divider">
        {!sidebarCollapsed && (
          <span className="text-sm font-semibold text-text-primary tracking-tight">
            Kira Board
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="p-1 rounded hover:bg-white/5 text-text-secondary transition-colors"
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {sidebarCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>

      {/* Board list */}
      <nav className="flex-1 py-2 overflow-y-auto">
        {!sidebarCollapsed && (
          <div className="flex items-center justify-between px-3 py-1.5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              Boards
            </p>
            {boardCount > 0 && (
              <span className="text-[10px] font-medium text-text-muted tabular-nums">
                {boardCount}
              </span>
            )}
          </div>
        )}

        {boards?.map((board) => {
          const isActive = board.id === activeBoardId;
          const taskCount = taskCountByBoard[board.id] ?? 0;

          return (
            <div key={board.id} className="relative group">
              <button
                onClick={() => navigate(`/boards/${board.id}`)}
                title={sidebarCollapsed ? board.name : undefined}
                className={clsx(
                  'w-full flex items-center gap-2 px-3 py-1.5 text-sm transition-colors',
                  isActive
                    ? 'bg-accent/10 text-accent'
                    : 'text-text-secondary hover:text-text-primary hover:bg-white/3',
                )}
              >
                {sidebarCollapsed ? (
                  /* Collapsed: show board initial avatar */
                  <div
                    className={clsx(
                      'w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-semibold shrink-0',
                      isActive ? 'bg-accent/20 text-accent' : `${hashColor(board.name)} text-text-primary`,
                    )}
                  >
                    {getBoardInitials(board.name)}
                  </div>
                ) : (
                  <>
                    <LayoutDashboard size={14} className="shrink-0" />
                    <span className="truncate flex-1 text-left">{board.name}</span>
                    {taskCount > 0 && (
                      <span
                        className="ml-auto inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold bg-accent/15 text-accent tabular-nums"
                        title={`${taskCount} active task${taskCount !== 1 ? 's' : ''}`}
                      >
                        {taskCount}
                      </span>
                    )}
                  </>
                )}
              </button>

              {/* Context menu (expanded only) */}
              {!sidebarCollapsed && (
                <div
                  className="absolute right-1 top-1/2 -translate-y-1/2"
                  ref={menuBoardId === board.id ? menuRef : undefined}
                >
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuBoardId(menuBoardId === board.id ? null : board.id);
                    }}
                    className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-white/10 text-text-muted hover:text-text-primary transition-all"
                    aria-label={`Board options for ${board.name}`}
                  >
                    <MoreHorizontal size={14} />
                  </button>
                  <AnimatePresence>
                    {menuBoardId === board.id && (
                      <motion.div
                        initial={{ opacity: 0, y: -4, scale: 0.98 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: -4, scale: 0.98 }}
                        transition={{ duration: 0.12 }}
                        className="absolute right-0 z-50 mt-1 min-w-[140px] rounded-lg glass shadow-xl py-1"
                      >
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmDelete(board.id);
                            setMenuBoardId(null);
                          }}
                          className="w-full text-left px-3 py-1.5 text-sm text-error hover:bg-error/10 flex items-center gap-2 transition-colors"
                        >
                          <Trash2 size={13} />
                          Delete
                        </button>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Action buttons */}
      {!sidebarCollapsed && (
        <div className="p-3 border-t border-divider">
          {creating ? (
            <div className="flex flex-col gap-2">
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreate();
                  if (e.key === 'Escape') {
                    setCreating(false);
                    setNewName('');
                  }
                }}
                placeholder="Board name..."
                className="glass-input rounded-md px-2 py-1 text-xs text-text-primary placeholder:text-text-muted w-full"
                autoFocus
              />
              <div className="flex gap-1.5">
                <button
                  onClick={handleCreate}
                  className="flex-1 text-xs px-2 py-1 rounded bg-accent/80 hover:bg-accent text-white transition-colors"
                >
                  Create
                </button>
                <button
                  onClick={() => {
                    setCreating(false);
                    setNewName('');
                  }}
                  className="text-xs px-2 py-1 rounded hover:bg-white/5 text-text-secondary transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-1">
              {/* Generate from Prompt - prominent CTA */}
              <button
                onClick={() => openModal('generate-board')}
                className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs font-medium text-white bg-accent/15 hover:bg-accent/25 border border-accent/20 hover:border-accent/35 transition-all group"
              >
                <Sparkles
                  size={14}
                  className="text-accent group-hover:text-accent-hover transition-colors"
                />
                <span className="text-accent group-hover:text-accent-hover transition-colors">
                  Generate from Prompt
                </span>
              </button>
              <button
                onClick={() => setCreating(true)}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-xs text-text-secondary hover:text-text-primary hover:bg-white/5 transition-colors"
              >
                <Plus size={14} />
                New Board
              </button>
            </div>
          )}
        </div>
      )}

      {/* Collapsed action buttons */}
      {sidebarCollapsed && (
        <div className="p-1.5 border-t border-divider flex flex-col items-center gap-1">
          <button
            onClick={() => openModal('generate-board')}
            className="p-1.5 rounded-md text-accent hover:bg-accent/10 transition-colors"
            title="Generate from Prompt"
            aria-label="Generate board from prompt"
          >
            <Sparkles size={16} />
          </button>
          <button
            onClick={() => {
              // Expand sidebar first so user can type the board name
              toggleSidebar();
              setTimeout(() => setCreating(true), 250);
            }}
            className="p-1.5 rounded-md text-text-secondary hover:text-text-primary hover:bg-white/5 transition-colors"
            title="New Board"
            aria-label="Create new board"
          >
            <Plus size={16} />
          </button>
        </div>
      )}

      {/* Delete confirmation dialog */}
      <AnimatePresence>
        {confirmDelete && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50"
            onClick={() => setConfirmDelete(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="glass rounded-xl p-5 shadow-2xl w-[340px]"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="text-sm font-semibold text-text-primary mb-2">Delete board?</h3>
              <p className="text-xs text-text-secondary mb-4">
                This will permanently delete the board, all its columns, cards, and tasks. This
                action cannot be undone.
              </p>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setConfirmDelete(null)}
                  className="px-3 py-1.5 text-xs rounded-md hover:bg-white/5 text-text-secondary transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleDelete(confirmDelete)}
                  className="px-3 py-1.5 text-xs rounded-md bg-error/80 hover:bg-error text-white transition-colors"
                >
                  Delete
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.aside>
  );
}
