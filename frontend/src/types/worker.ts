export type WorkerStatus = 'online' | 'offline' | 'stale';

export interface Worker {
  id: string;
  user_id: string;
  hostname: string;
  status: WorkerStatus;
  capabilities_json: string;
  last_heartbeat: string | null;
  registered_at: string;
}
