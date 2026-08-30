/**
 * Persistent WebSocket hook with auto-reconnect.
 *
 * Performance optimizations applied (vercel-react-best-practices):
 * - rerender-use-ref-transient-values: WS ref in useRef
 * - rerender-functional-setstate: functional state updates
 * - Effect cleanup prevents memory leaks
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import type { DashboardUpdate, WSMessage } from '../types/telemetry';

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

interface UseWebSocketReturn {
  data: DashboardUpdate | null;
  status: ConnectionStatus;
  sequence: number;
  reconnect: () => void;
}

const RECONNECT_DELAY = 3000;
const MAX_RECONNECT_DELAY = 30000;

export function useWebSocket(url: string): UseWebSocketReturn {
  const [data, setData] = useState<DashboardUpdate | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const [sequence, setSequence] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | undefined>();
  const reconnectDelayRef = useRef(RECONNECT_DELAY);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    // Cleanup existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    setStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setStatus('connected');
      reconnectDelayRef.current = RECONNECT_DELAY; // Reset delay on success
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const msg: WSMessage = JSON.parse(event.data);
        if (msg.type === 'update' && typeof msg.data === 'object') {
          setData(msg.data as DashboardUpdate);
          setSequence(msg.sequence);
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setStatus('disconnected');

      // Exponential backoff reconnect
      reconnectTimeoutRef.current = window.setTimeout(() => {
        reconnectDelayRef.current = Math.min(
          reconnectDelayRef.current * 1.5,
          MAX_RECONNECT_DELAY,
        );
        connect();
      }, reconnectDelayRef.current);
    };

    ws.onerror = () => {
      // onclose will fire after onerror
    };
  }, [url]);

  const reconnect = useCallback(() => {
    clearTimeout(reconnectTimeoutRef.current);
    reconnectDelayRef.current = RECONNECT_DELAY;
    connect();
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { data, status, sequence, reconnect };
}
