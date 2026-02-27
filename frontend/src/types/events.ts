import type { Card, Column, CardComment } from './board.ts';
import type { Task } from './task.ts';
import type { Worker } from './worker.ts';

export type SSEEventType =
  | 'card_created'
  | 'card_moved'
  | 'card_updated'
  | 'card_deleted'
  | 'column_created'
  | 'column_reordered'
  | 'comment_added'
  | 'task_created'
  | 'task_claimed'
  | 'task_progress'
  | 'task_completed'
  | 'task_failed'
  | 'task_cancelled'
  | 'worker_online'
  | 'worker_offline'
  | 'jira_synced'
  | 'user_presence'
  | 'heartbeat';

export interface CardCreatedEvent {
  type: 'card_created';
  card: Card;
}

export interface CardMovedEvent {
  type: 'card_moved';
  card_id: string;
  from_column: string;
  to_column: string;
  position: number;
}

export interface CardUpdatedEvent {
  type: 'card_updated';
  card: Card;
}

export interface CardDeletedEvent {
  type: 'card_deleted';
  card_id: string;
}

export interface ColumnCreatedEvent {
  type: 'column_created';
  column: Column;
}

export interface ColumnReorderedEvent {
  type: 'column_reordered';
  column_ids: string[];
}

export interface CommentAddedEvent {
  type: 'comment_added';
  comment: CardComment;
}

export interface TaskCreatedEvent {
  type: 'task_created';
  task: Task;
}

export interface TaskClaimedEvent {
  type: 'task_claimed';
  task: Task;
}

export interface TaskProgressEvent {
  type: 'task_progress';
  task_id: string;
  progress_text: string;
  step?: number;
  total_steps?: number;
  phase?: string;
}

export interface TaskCompletedEvent {
  type: 'task_completed';
  task: Task;
}

export interface TaskFailedEvent {
  type: 'task_failed';
  task: Task;
}

export interface TaskCancelledEvent {
  type: 'task_cancelled';
  task: Task;
}

export interface WorkerOnlineEvent {
  type: 'worker_online';
  worker: Worker;
}

export interface WorkerOfflineEvent {
  type: 'worker_offline';
  worker: Worker;
}

export interface JiraSyncedEvent {
  type: 'jira_synced';
  card_id: string;
  jira_key: string;
  status: string;
}

export interface UserPresenceEvent {
  type: 'user_presence';
  user_id: string;
  action: string;
}

export interface HeartbeatEvent {
  type: 'heartbeat';
  timestamp: string;
}

export type SSEEvent =
  | CardCreatedEvent
  | CardMovedEvent
  | CardUpdatedEvent
  | CardDeletedEvent
  | ColumnCreatedEvent
  | ColumnReorderedEvent
  | CommentAddedEvent
  | TaskCreatedEvent
  | TaskClaimedEvent
  | TaskProgressEvent
  | TaskCompletedEvent
  | TaskFailedEvent
  | TaskCancelledEvent
  | WorkerOnlineEvent
  | WorkerOfflineEvent
  | JiraSyncedEvent
  | UserPresenceEvent
  | HeartbeatEvent;
