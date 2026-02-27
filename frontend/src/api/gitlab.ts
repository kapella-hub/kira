import { get, post } from './client.ts';
import type {
  GitLabProject,
  GitLabNamespace,
  GitLabCredentialsStatus,
  LinkProjectRequest,
  CreateProjectRequest,
  PushRequest,
} from '@/types/gitlab.ts';

export interface TaskRef {
  task_id: string;
  status: 'pending';
}

export function testGitLabConnection(): Promise<{ success: boolean; username: string; error: string }> {
  return post('/gitlab/test-connection');
}

export function fetchGitLabProjects(search?: string): Promise<GitLabProject[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : '';
  return get<GitLabProject[]>(`/gitlab/projects${query}`);
}

export function fetchGitLabNamespaces(): Promise<GitLabNamespace[]> {
  return get<GitLabNamespace[]>('/gitlab/namespaces');
}

export function saveGitLabCredentials(server: string, token: string): Promise<void> {
  return post('/gitlab/credentials', { server, token });
}

export function getGitLabStatus(): Promise<GitLabCredentialsStatus> {
  return get<GitLabCredentialsStatus>('/gitlab/status');
}

export function linkGitLabProject(data: LinkProjectRequest): Promise<void> {
  return post('/gitlab/link', data);
}

export function createGitLabProject(data: CreateProjectRequest): Promise<TaskRef> {
  return post<TaskRef>('/gitlab/projects', data);
}

export function pushToGitLab(cardId: string, data?: PushRequest): Promise<TaskRef> {
  return post<TaskRef>(`/gitlab/push/${cardId}`, data);
}
