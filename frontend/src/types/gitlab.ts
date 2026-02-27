export interface GitLabProject {
  id: number;
  name: string;
  path_with_namespace: string;
  web_url: string;
  default_branch: string;
}

export interface GitLabNamespace {
  id: number;
  name: string;
  path: string;
  kind: 'user' | 'group';
}

export interface GitLabSettings {
  project_id: number;
  project_path: string;
  project_url: string;
  default_branch: string;
  mr_prefix: string;
  auto_push: boolean;
  push_on_complete: boolean;
}

export interface GitLabCredentialsStatus {
  configured: boolean;
  server: string;
}

export interface LinkProjectRequest {
  project_id: number;
  project_path: string;
  project_url: string;
  default_branch: string;
  auto_push: boolean;
  push_on_complete: boolean;
}

export interface CreateProjectRequest {
  name: string;
  namespace_id: number;
  visibility: 'private' | 'internal' | 'public';
  description?: string;
  auto_push: boolean;
  push_on_complete: boolean;
}

export interface PushRequest {
  branch?: string;
  commit_message?: string;
}
