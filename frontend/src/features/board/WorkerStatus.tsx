import { useState, useEffect, useCallback, useRef } from 'react';
import { Cpu } from 'lucide-react';
import { fetchWorkers } from '@/api/workers.ts';
import type { Worker } from '@/types/worker.ts';
import clsx from 'clsx';

const POLL_INTERVAL = 30_000;

export function WorkerStatus() {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [showTooltip, setShowTooltip] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const poll = useCallback(async () => {
    try {
      const data = await fetchWorkers();
      setWorkers(data);
    } catch {
      // Silently fail - workers endpoint may not be available
    }
  }, []);

  useEffect(() => {
    poll();
    const interval = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [poll]);

  // Close tooltip on outside click
  useEffect(() => {
    if (!showTooltip) return;
    function handler(e: MouseEvent) {
      if (tooltipRef.current && !tooltipRef.current.contains(e.target as Node)) {
        setShowTooltip(false);
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showTooltip]);

  const onlineWorkers = workers.filter((w) => w.status === 'online');
  const hasOnline = onlineWorkers.length > 0;

  // Expose worker update method for SSE events
  const updateWorker = useCallback((worker: Worker) => {
    setWorkers((prev) => {
      const idx = prev.findIndex((w) => w.id === worker.id);
      if (idx !== -1) {
        const updated = [...prev];
        updated[idx] = worker;
        return updated;
      }
      return [...prev, worker];
    });
  }, []);

  // Store in a ref so SSE handler can access it
  useEffect(() => {
    (window as unknown as Record<string, unknown>).__workerStatusUpdate = updateWorker;
    return () => {
      delete (window as unknown as Record<string, unknown>).__workerStatusUpdate;
    };
  }, [updateWorker]);

  if (workers.length === 0) return null;

  return (
    <div className="relative" ref={tooltipRef}>
      <button
        onClick={() => setShowTooltip((s) => !s)}
        className={clsx(
          'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-colors',
          'glass glass-hover cursor-pointer',
        )}
        aria-label={`${onlineWorkers.length} worker${onlineWorkers.length !== 1 ? 's' : ''} online`}
      >
        <span className="relative flex h-2 w-2">
          {hasOnline && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-50" />
          )}
          <span
            className={clsx(
              'relative inline-flex rounded-full h-2 w-2',
              hasOnline ? 'bg-success' : 'bg-text-muted',
            )}
          />
        </span>
        <Cpu size={12} className="text-text-secondary" />
        <span className="text-text-secondary hidden sm:inline">
          {onlineWorkers.length}/{workers.length}
        </span>
      </button>

      {/* Tooltip dropdown */}
      {showTooltip && (
        <div className="absolute right-0 mt-1 z-50 min-w-[220px] rounded-lg glass shadow-xl py-2 px-1">
          <p className="text-[10px] font-medium uppercase tracking-wider text-text-muted px-2 pb-1.5">
            Workers
          </p>
          {workers.map((worker) => (
            <div
              key={worker.id}
              className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-white/3 transition-colors"
            >
              <span
                className={clsx(
                  'flex h-1.5 w-1.5 rounded-full shrink-0',
                  worker.status === 'online' && 'bg-success',
                  worker.status === 'offline' && 'bg-text-muted',
                  worker.status === 'stale' && 'bg-warning',
                )}
              />
              <div className="flex-1 min-w-0">
                <p className="text-xs text-text-primary truncate">{worker.hostname}</p>
                <p className="text-[10px] text-text-muted truncate">
                  {worker.user_id}
                  {worker.last_heartbeat && (
                    <> &middot; {formatRelative(worker.last_heartbeat)}</>
                  )}
                </p>
              </div>
              <span
                className={clsx(
                  'text-[10px] font-medium capitalize',
                  worker.status === 'online' && 'text-success',
                  worker.status === 'offline' && 'text-text-muted',
                  worker.status === 'stale' && 'text-warning',
                )}
              >
                {worker.status}
              </span>
            </div>
          ))}
          {workers.length === 0 && (
            <p className="text-xs text-text-muted text-center py-2">No workers registered</p>
          )}
        </div>
      )}
    </div>
  );
}

function formatRelative(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}
