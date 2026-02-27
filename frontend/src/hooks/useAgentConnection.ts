import { useEffect, useRef } from 'react';
import { useAuthStore } from '@/stores/authStore.ts';
import { useAgentStore } from '@/stores/agentStore.ts';

/**
 * Manages agent WebSocket lifecycle tied to auth state.
 * - Connects on mount if authenticated
 * - Sends activate when connected + authenticated
 * - Deactivates on logout
 * - Re-activates on token change
 *
 * Call once at the top level of the authenticated view (Layout).
 */
export function useAgentConnection() {
  const token = useAuthStore((s) => s.token);
  const agentState = useAgentStore((s) => s.agentState);
  const connect = useAgentStore((s) => s.connect);
  const disconnect = useAgentStore((s) => s.disconnect);
  const sendActivate = useAgentStore((s) => s.sendActivate);
  const sendDeactivate = useAgentStore((s) => s.sendDeactivate);

  // Derive server URL from the page origin (same origin in production)
  const serverUrl = window.location.origin;

  // Track if we've ever been authenticated to distinguish mount from logout
  const wasAuthenticated = useRef(false);

  // Connect when authenticated, deactivate + disconnect on logout
  useEffect(() => {
    if (token) {
      wasAuthenticated.current = true;
      connect();
    } else if (wasAuthenticated.current) {
      sendDeactivate();
      disconnect();
    }
  }, [token, connect, disconnect, sendDeactivate]);

  // Send activate when agent reaches dormant state and we have a token.
  // Also re-activate if the agent transitions through deactivating (e.g. page
  // reload while previously active).
  useEffect(() => {
    if (token && (agentState === 'dormant' || agentState === 'deactivating')) {
      sendActivate(token, serverUrl);
    }
  }, [token, agentState, serverUrl, sendActivate]);

  // Cleanup reconnect timer on unmount
  useEffect(() => {
    return () => {
      const { _reconnectTimer } = useAgentStore.getState();
      if (_reconnectTimer) clearTimeout(_reconnectTimer);
    };
  }, []);
}
