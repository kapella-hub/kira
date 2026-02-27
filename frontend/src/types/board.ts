export type Priority = 'critical' | 'high' | 'medium' | 'low' | 'none';
export type JiraSyncStatus = '' | 'synced' | 'pending' | 'conflict' | 'error';
export type AgentStatus = '' | 'pending' | 'running' | 'completed' | 'failed';

export interface Board {
  id: string;
  name: string;
  description: string;
  owner_id: string;
  jira_project_key: string;
  jira_sync_enabled: boolean;
  jira_sync_jql: string;
  settings_json: string;
  created_at: string;
  updated_at: string;
  columns?: Column[];
}

export interface Column {
  id: string;
  board_id: string;
  name: string;
  position: number;
  wip_limit: number;
  color: string;
  collapsed: boolean;
  // Automation
  agent_type: string;
  agent_skill: string;
  agent_model: string;
  auto_run: boolean;
  on_success_column_id: string;
  on_failure_column_id: string;
  max_loop_count: number;
  prompt_template: string;
  created_at: string;
  cards?: Card[];
}

export interface Card {
  id: string;
  column_id: string;
  board_id: string;
  title: string;
  description: string;
  position: number;
  assignee_id: string;
  priority: Priority;
  labels: string[];
  due_date: string | null;
  jira_key: string;
  jira_sync_status: JiraSyncStatus;
  jira_last_synced: string | null;
  agent_status: AgentStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface CardComment {
  id: string;
  card_id: string;
  user_id: string;
  content: string;
  is_agent_output: boolean;
  created_at: string;
}

export interface CardActivity {
  id: string;
  card_id: string;
  user_id: string | null;
  action: string;
  details_json: string;
  created_at: string;
}

export interface CreateCardRequest {
  column_id: string;
  title: string;
  description?: string;
  priority?: Priority;
  labels?: string[];
  assignee_id?: string;
  due_date?: string | null;
}

export interface UpdateCardRequest {
  title?: string;
  description?: string;
  priority?: Priority;
  labels?: string[];
  assignee_id?: string | null;
  due_date?: string | null;
}

export interface MoveCardRequest {
  column_id: string;
  position: number;
}

export interface CreateColumnRequest {
  name: string;
  color?: string;
  wip_limit?: number;
}

export interface UpdateColumnRequest {
  name?: string;
  color?: string;
  wip_limit?: number;
  agent_type?: string;
  agent_skill?: string;
  agent_model?: string;
  auto_run?: boolean;
  on_success_column_id?: string;
  on_failure_column_id?: string;
  max_loop_count?: number;
  prompt_template?: string;
}
