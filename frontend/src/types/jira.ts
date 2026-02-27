export interface JiraSyncConfig {
  server: string;
  username: string;
  token: string;
}

export interface JiraImportRequest {
  jql: string;
  board_id: string;
  column_id: string;
}

export interface JiraProject {
  key: string;
  name: string;
}

export interface SyncStatus {
  synced: number;
  created: number;
  updated: number;
  conflicts: number;
}

export interface JiraPushResult {
  jira_key: string;
  browse_url: string;
}
