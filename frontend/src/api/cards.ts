import { get, post, patch, del } from './client.ts';
import type {
  Card,
  CardComment,
  CreateCardRequest,
  UpdateCardRequest,
  MoveCardRequest,
} from '@/types/board.ts';

/** Ensure card.labels is always a string[] (backend stores as JSON string). */
function normalizeCard(card: Card): Card {
  if (typeof card.labels === 'string') {
    try {
      return { ...card, labels: JSON.parse(card.labels as string) };
    } catch {
      return { ...card, labels: [] };
    }
  }
  return card;
}

export async function fetchCard(id: string): Promise<Card> {
  const card = await get<Card>(`/cards/${id}`);
  return normalizeCard(card);
}

export async function createCard(data: CreateCardRequest): Promise<Card> {
  const payload = data.labels ? { ...data, labels: JSON.stringify(data.labels) } : data;
  const card = await post<Card>('/cards', payload);
  return normalizeCard(card);
}

export async function updateCard(id: string, data: UpdateCardRequest): Promise<Card> {
  const payload = data.labels ? { ...data, labels: JSON.stringify(data.labels) } : data;
  const card = await patch<Card>(`/cards/${id}`, payload);
  return normalizeCard(card);
}

export function deleteCard(id: string): Promise<void> {
  return del(`/cards/${id}`);
}

export async function moveCard(id: string, data: MoveCardRequest): Promise<Card> {
  const card = await post<Card>(`/cards/${id}/move`, data);
  return normalizeCard(card);
}

export function reorderCards(columnId: string, cardIds: string[]): Promise<void> {
  return post('/cards/reorder', { column_id: columnId, card_ids: cardIds });
}

export function fetchComments(cardId: string): Promise<CardComment[]> {
  return get<CardComment[]>(`/cards/${cardId}/comments`);
}

export function addComment(cardId: string, content: string): Promise<CardComment> {
  return post<CardComment>(`/cards/${cardId}/comments`, { content });
}

export function deleteComment(id: string): Promise<void> {
  return del(`/comments/${id}`);
}

export interface SearchResult {
  id: string;
  title: string;
  column_name: string;
  assignee_id: string;
  priority: string;
}

export function searchCards(query: string, boardId?: string): Promise<SearchResult[]> {
  const params = new URLSearchParams({ q: query });
  if (boardId) params.set('board_id', boardId);
  return get<SearchResult[]>(`/search?${params}`);
}
