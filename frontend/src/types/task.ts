export type TaskType = 'agent_run' | 'jira_import' | 'jira_push' | 'jira_sync' | 'board_plan' | 'card_gen';
export type TaskStatus = 'pending' | 'claimed' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface Task {
  id: string;
  task_type: TaskType;
  board_id: string;
  card_id: string | null;
  created_by: string;
  assigned_to: string | null;
  agent_type: string;
  status: TaskStatus;
  priority: number;
  loop_count: number;
  max_loop_count: number;
  error_summary: string;
  progress_text: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
