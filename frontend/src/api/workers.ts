import { get } from './client.ts';
import type { Worker } from '@/types/worker.ts';

export function fetchWorkers(): Promise<Worker[]> {
  return get<Worker[]>('/workers');
}
