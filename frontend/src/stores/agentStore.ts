import { create } from 'zustand';

export type AgentState =
  | 'disconnected'
  | 'connecting'
  | 'dormant'
  | 'activating'
  | 'active'
  | 'deactivating';

interface UpgradeAvailable {
  currentVersion: string;
  serverVersion: string;
  installUrl: string;
}

interface AgentStoreState {
  agentState: AgentState;
  workerId: string | null;
  runningTasks: number;
  error: string | null;
  upgradeAvailable: UpgradeAvailable | null;

  // Internal
  _ws: WebSocket | null;
  _sessionId: string;
  _reconnectTimer: ReturnType<typeof setTimeout> | null;
  _reconnectAttempts: number;
  _manualDisconnect: boolean;

  // Actions
  connect: () => void;
  disconnect: () => void;
  sendActivate: (token: string, serverUrl: string) => void;
  sendDeactivate: () => void;
}

const AGENT_WS_URL = 'ws://localhost:9820';

// Phase 1: fast reconnect (attempts 0–4) — 1s, 1.5s, 2.25s, 3.4s, 5s
const FAST_RECONNECT_BASE = 1000;
const FAST_RECONNECT_MULTIPLIER = 1.5;
const FAST_RECONNECT_COUNT = 5;

// Phase 2: slow poll (attempts 5+) — fixed 10s, unlimited
const SLOW_POLL_INTERVAL = 10000;

export const useAgentStore = create<AgentStoreState>((set, get) => ({
  agentState: 'disconnected',
  workerId: null,
  runningTasks: 0,
  error: null,
  upgradeAvailable: null,
  _ws: null,
  _sessionId: crypto.randomUUID(),
  _reconnectTimer: null,
  _reconnectAttempts: 0,
  _manualDisconnect: false,

  connect: () => {
    const { _ws } = get();
    if (_ws && _ws.readyState <= WebSocket.OPEN) return;

    set({ agentState: 'connecting', error: null, _manualDisconnect: false });

    try {
      const ws = new WebSocket(AGENT_WS_URL);

      ws.onopen = () => {
        set({ _ws: ws, _reconnectAttempts: 0 });
        // Don't set agentState here — wait for the status message from the agent
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(String(event.data));
          const messageType: string = data.type;

          if (messageType === 'status') {
            set({
              agentState: data.state as AgentState,
              workerId: data.worker_id ?? null,
              runningTasks: data.running_tasks ?? 0,
              error: null,
            });
          } else if (messageType === 'token_expired') {
            set({ error: 'Session expired', agentState: 'dormant' });
          } else if (messageType === 'upgrade_available') {
            set({
              upgradeAvailable: {
                currentVersion: data.current_version,
                serverVersion: data.server_version,
                installUrl: data.install_url,
              },
            });
          } else if (messageType === 'error') {
            set({ error: data.message });
          }
          // pong messages are silently consumed
        } catch {
          // Ignore parse errors from non-JSON messages
        }
      };

      ws.onclose = () => {
        set({ _ws: null });
        if (get()._manualDisconnect) return;

        const attempts = get()._reconnectAttempts;

        // Two-phase reconnect: fast first, then slow poll forever
        const delay =
          attempts < FAST_RECONNECT_COUNT
            ? FAST_RECONNECT_BASE * Math.pow(FAST_RECONNECT_MULTIPLIER, attempts)
            : SLOW_POLL_INTERVAL;

        const timer = setTimeout(() => {
          set({ _reconnectAttempts: attempts + 1 });
          get().connect();
        }, delay);
        set({ _reconnectTimer: timer, agentState: 'disconnected' });
      };

      ws.onerror = () => {
        // onclose fires after onerror — reconnect is handled there
      };

      set({ _ws: ws });
    } catch {
      set({ agentState: 'disconnected' });
    }
  },

  disconnect: () => {
    const { _ws, _reconnectTimer } = get();
    if (_reconnectTimer) clearTimeout(_reconnectTimer);
    set({
      _manualDisconnect: true,
      _reconnectTimer: null,
      _reconnectAttempts: 0,
      agentState: 'disconnected',
      workerId: null,
      runningTasks: 0,
      error: null,
    });
    if (_ws) _ws.close(1000, 'logout');
  },

  sendActivate: (token, serverUrl) => {
    const { _ws, _sessionId } = get();
    if (_ws?.readyState === WebSocket.OPEN) {
      _ws.send(
        JSON.stringify({
          type: 'activate',
          token,
          server_url: serverUrl,
          session_id: _sessionId,
        }),
      );
    }
  },

  sendDeactivate: () => {
    const { _ws, _sessionId } = get();
    if (_ws?.readyState === WebSocket.OPEN) {
      _ws.send(
        JSON.stringify({
          type: 'deactivate',
          session_id: _sessionId,
        }),
      );
    }
  },
}));
