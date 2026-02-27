import { get, post, patch, del } from './client.ts';
import type { Board, Column, CreateColumnRequest, UpdateColumnRequest } from '@/types/board.ts';

interface FullBoardResponse {
  board: Board;
  columns: Column[];
  members: { user_id: string; username: string; display_name: string; avatar_url: string; role: string }[];
}

export function fetchBoards(): Promise<Board[]> {
  return get<Board[]>('/boards');
}

export async function fetchBoard(id: string): Promise<Board> {
  const data = await get<FullBoardResponse>(`/boards/${id}`);
  // Merge columns into board so the store can access board.columns
  return { ...data.board, columns: data.columns } as Board;
}

export function createBoard(data: { name: string; description?: string }): Promise<Board> {
  return post<Board>('/boards', data);
}

export function updateBoard(id: string, data: { name?: string; description?: string }): Promise<Board> {
  return patch<Board>(`/boards/${id}`, data);
}

export function deleteBoard(id: string): Promise<void> {
  return del(`/boards/${id}`);
}

export function createColumn(boardId: string, data: CreateColumnRequest): Promise<Column> {
  return post<Column>(`/boards/${boardId}/columns`, data);
}

export function updateColumn(id: string, data: UpdateColumnRequest): Promise<Column> {
  return patch<Column>(`/columns/${id}`, data);
}

export function deleteColumn(id: string): Promise<void> {
  return del(`/columns/${id}`);
}

export function reorderColumns(boardId: string, columnIds: string[]): Promise<void> {
  return patch(`/boards/${boardId}/columns/reorder`, { column_ids: columnIds });
}

// --- Board generation (AI) ---

export interface GenerateBoardResponse {
  board_id: string;
  task_id: string;
}

export function generateBoard(data: { prompt: string; name?: string }): Promise<GenerateBoardResponse> {
  return post<GenerateBoardResponse>('/boards/generate', data);
}

export function generateBoardPlan(boardId: string, prompt: string): Promise<GenerateBoardResponse> {
  return post<GenerateBoardResponse>(`/boards/${boardId}/generate`, { prompt });
}

export function generateCards(
  boardId: string,
  prompt: string,
  columnId?: string,
): Promise<GenerateBoardResponse> {
  return post<GenerateBoardResponse>(`/boards/${boardId}/generate`, {
    prompt,
    column_id: columnId || '',
  });
}

// --- Board settings ---

export function fetchBoardSettings(boardId: string): Promise<Record<string, unknown>> {
  return get<Record<string, unknown>>(`/boards/${boardId}/settings`);
}

export function updateBoardSettings(
  boardId: string,
  settings: Record<string, unknown>,
): Promise<Board> {
  return patch<Board>(`/boards/${boardId}/settings`, settings);
}
