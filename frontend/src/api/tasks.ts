import { get, post } from './client.ts';
import type { Task } from '@/types/task.ts';

export function fetchTasks(boardId: string, status?: string): Promise<Task[]> {
  const params = new URLSearchParams({ board_id: boardId });
  if (status) params.set('status', status);
  return get<Task[]>(`/tasks?${params}`);
}

export function fetchCardTasks(cardId: string): Promise<Task[]> {
  return get<Task[]>(`/tasks?card_id=${cardId}`);
}

export function cancelTask(taskId: string): Promise<void> {
  return post(`/tasks/${taskId}/cancel`);
}
