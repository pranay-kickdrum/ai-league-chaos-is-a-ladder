/* SSE connection hook — subscribes to live trip updates. */

import { useCallback, useEffect, useRef } from 'react';
import { createSSEConnection } from '../services/api';
import type { SSEEvent } from '../types';

type EventHandler = (event: SSEEvent) => void;

const SSE_EVENT_TYPES = [
  'phase_update',
  'agent_thinking',
  'agent_step',
  'research_partial',
  'api_degraded',
  'price_changed',
  'checkpoint',
  'plan_ready',
  'itinerary_ready',
  'map_update',
  'budget_update',
  'error',
  'complete',
] as const;

export function useSSE(tripId: string | null, onEvent: EventHandler) {
  const sourceRef = useRef<EventSource | null>(null);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  const connect = useCallback(() => {
    if (!tripId) return;
    // Close any existing connection
    sourceRef.current?.close();

    const es = createSSEConnection(tripId);
    sourceRef.current = es;

    // Listen to all known event types
    for (const type of SSE_EVENT_TYPES) {
      es.addEventListener(type, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          handlerRef.current({ type, data });
        } catch {
          handlerRef.current({ type, data: e.data });
        }
      });
    }

    es.onerror = () => {
      // Auto-reconnect is built into EventSource, but log
      console.warn('[SSE] Connection error, will auto-reconnect');
    };
  }, [tripId]);

  useEffect(() => {
    connect();
    return () => {
      sourceRef.current?.close();
      sourceRef.current = null;
    };
  }, [connect]);

  const disconnect = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
  }, []);

  return { disconnect };
}
