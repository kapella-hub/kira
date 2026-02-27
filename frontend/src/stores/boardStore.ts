import { create } from 'zustand';
import type { Board, Column, Card } from '@/types/board.ts';

export interface PlanTaskState {
  taskId: string;
  status: 'pending' | 'claimed' | 'running' | 'completed' | 'failed';
  progressText: string;
  step?: number;
  totalSteps?: number;
  phase?: string;
}

interface BoardState {
  boards: Board[];
  currentBoard: Board | null;
  columns: Column[];
  cardsByColumn: Record<string, Card[]>;
  planTask: PlanTaskState | null;

  setBoards: (boards: Board[]) => void;
  setCurrentBoard: (board: Board) => void;
  setColumns: (columns: Column[]) => void;
  setCardsForColumn: (columnId: string, cards: Card[]) => void;

  // Optimistic updates
  addCard: (card: Card) => void;
  updateCard: (card: Card) => void;
  removeCard: (cardId: string) => void;
  moveCard: (cardId: string, fromColumnId: string, toColumnId: string, position: number) => void;

  addColumn: (column: Column) => void;
  updateColumn: (columnId: string, updates: Partial<Column>) => void;
  removeColumn: (columnId: string) => void;
  reorderColumns: (columnIds: string[]) => void;

  // Plan task tracking
  setPlanTask: (task: PlanTaskState | null) => void;
  updatePlanTaskStatus: (
    status: PlanTaskState['status'],
    progressText?: string,
    extra?: { step?: number; totalSteps?: number; phase?: string },
  ) => void;
}

/** Ensure card.labels is always a string[] (DB stores as JSON string). */
function normalizeCard(card: Card): Card {
  if (typeof card.labels === 'string') {
    try {
      card = { ...card, labels: JSON.parse(card.labels as string) };
    } catch {
      card = { ...card, labels: [] };
    }
  }
  return card;
}

export const useBoardStore = create<BoardState>((set) => ({
  boards: [],
  currentBoard: null,
  columns: [],
  cardsByColumn: {},
  planTask: null,

  setBoards: (boards) => set({ boards }),

  setCurrentBoard: (board) => {
    const columns = (board.columns ?? []).sort((a, b) => a.position - b.position);
    const cardsByColumn: Record<string, Card[]> = {};
    for (const col of columns) {
      cardsByColumn[col.id] = (col.cards ?? []).map(normalizeCard).sort((a, b) => a.position - b.position);
    }
    set({ currentBoard: board, columns, cardsByColumn, planTask: null });
  },

  setColumns: (columns) => set({ columns: columns.sort((a, b) => a.position - b.position) }),

  setCardsForColumn: (columnId, cards) =>
    set((state) => ({
      cardsByColumn: {
        ...state.cardsByColumn,
        [columnId]: cards.sort((a, b) => a.position - b.position),
      },
    })),

  addCard: (card) =>
    set((state) => {
      const c = normalizeCard(card);
      const existing = state.cardsByColumn[c.column_id] ?? [];
      return {
        cardsByColumn: {
          ...state.cardsByColumn,
          [c.column_id]: [...existing, c].sort((a, b) => a.position - b.position),
        },
      };
    }),

  updateCard: (card) =>
    set((state) => {
      const newMap = { ...state.cardsByColumn };
      for (const [colId, cards] of Object.entries(newMap)) {
        const idx = cards.findIndex((c) => c.id === card.id);
        if (idx !== -1) {
          const updated = [...cards];
          if (colId === card.column_id) {
            updated[idx] = card;
            newMap[colId] = updated;
          } else {
            updated.splice(idx, 1);
            newMap[colId] = updated;
            newMap[card.column_id] = [...(newMap[card.column_id] ?? []), card].sort(
              (a, b) => a.position - b.position,
            );
          }
          break;
        }
      }
      return { cardsByColumn: newMap };
    }),

  removeCard: (cardId) =>
    set((state) => {
      const newMap = { ...state.cardsByColumn };
      for (const [colId, cards] of Object.entries(newMap)) {
        const idx = cards.findIndex((c) => c.id === cardId);
        if (idx !== -1) {
          const updated = [...cards];
          updated.splice(idx, 1);
          newMap[colId] = updated;
          break;
        }
      }
      return { cardsByColumn: newMap };
    }),

  moveCard: (cardId, fromColumnId, toColumnId, position) =>
    set((state) => {
      const newMap = { ...state.cardsByColumn };
      const fromCards = [...(newMap[fromColumnId] ?? [])];
      const cardIdx = fromCards.findIndex((c) => c.id === cardId);
      if (cardIdx === -1) return state;

      const [card] = fromCards.splice(cardIdx, 1);
      const movedCard = { ...card, column_id: toColumnId, position };
      newMap[fromColumnId] = fromCards;

      const toCards = fromColumnId === toColumnId ? fromCards : [...(newMap[toColumnId] ?? [])];
      toCards.splice(position, 0, movedCard);
      toCards.forEach((c, i) => (c.position = i));
      newMap[toColumnId] = toCards;

      return { cardsByColumn: newMap };
    }),

  addColumn: (column) =>
    set((state) => ({
      columns: [...state.columns, column].sort((a, b) => a.position - b.position),
      cardsByColumn: { ...state.cardsByColumn, [column.id]: [] },
    })),

  updateColumn: (columnId, updates) =>
    set((state) => ({
      columns: state.columns.map((c) => (c.id === columnId ? { ...c, ...updates } : c)),
    })),

  removeColumn: (columnId) =>
    set((state) => {
      const { [columnId]: _removed, ...rest } = state.cardsByColumn;
      void _removed;
      return {
        columns: state.columns.filter((c) => c.id !== columnId),
        cardsByColumn: rest,
      };
    }),

  reorderColumns: (columnIds) =>
    set((state) => {
      const colMap = new Map(state.columns.map((c) => [c.id, c]));
      const reordered = columnIds
        .map((id, i) => {
          const col = colMap.get(id);
          return col ? { ...col, position: i } : null;
        })
        .filter((c): c is Column => c !== null);
      return { columns: reordered };
    }),

  setPlanTask: (task) => set({ planTask: task }),
  updatePlanTaskStatus: (status, progressText, extra) =>
    set((state) => {
      if (!state.planTask) return state;
      return {
        planTask: {
          ...state.planTask,
          status,
          ...(progressText !== undefined ? { progressText } : {}),
          ...(extra?.step !== undefined ? { step: extra.step } : {}),
          ...(extra?.totalSteps !== undefined ? { totalSteps: extra.totalSteps } : {}),
          ...(extra?.phase !== undefined ? { phase: extra.phase } : {}),
        },
      };
    }),
}));
