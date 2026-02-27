import { get, post, patch } from './client.ts';
import type {
  JiraSyncConfig,
  JiraImportRequest,
  JiraProject,
  JiraPushResult,
} from '@/types/jira.ts';

export interface TaskRef {
  task_id: string;
  status: 'pending';
}

export function testJiraConnection(): Promise<{ success: boolean; user: string }> {
  return post('/jira/test-connection');
}

export function importFromJira(data: JiraImportRequest): Promise<TaskRef> {
  return post<TaskRef>('/jira/import', data);
}

export function pushToJira(cardId: string): Promise<JiraPushResult | TaskRef> {
  return post<JiraPushResult | TaskRef>(`/jira/push/${cardId}`);
}

export function syncBoard(boardId: string): Promise<TaskRef> {
  return post<TaskRef>(`/jira/sync/${boardId}`);
}

export function fetchJiraProjects(): Promise<JiraProject[]> {
  return get<JiraProject[]>('/jira/projects');
}

export function updateJiraCredentials(config: JiraSyncConfig): Promise<void> {
  return patch('/users/me/jira', config);
}
