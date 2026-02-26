/* Trip state management hook — aggregates SSE events into unified state. */

import { useCallback, useReducer, useRef } from 'react';
import type {
  AgentStep,
  BudgetBreakdown,
  ChatMessage,
  CheckpointData,
  Itinerary,
  MapMarker,
  PlanOption,
  PriceChange,
  ResearchData,
  SSEEvent,
  TripRequest,
  TripState,
  TripStatusType,
} from '../types';
import { useSSE } from './useSSE';

/* ── Reducer ────────────────────────────── */

type Action =
  | { type: 'SET_TRIP_ID'; tripId: string }
  | { type: 'SET_STATUS'; status: TripStatusType }
  | { type: 'SET_REQUEST'; request: TripRequest }
  | { type: 'ADD_CHAT'; message: ChatMessage }
  | { type: 'SET_CHECKPOINT'; checkpoint: CheckpointData }
  | { type: 'CLEAR_CHECKPOINT' }
  | { type: 'SET_PLAN_OPTIONS'; options: PlanOption[] }
  | { type: 'SET_ITINERARY'; itinerary: Itinerary }
  | { type: 'SET_BUDGET'; budget: BudgetBreakdown }
  | { type: 'SET_MARKERS'; markers: MapMarker[] }
  | { type: 'ADD_REASONING'; entry: string }
  | { type: 'ADD_PRICE_CHANGE'; change: PriceChange }
  | { type: 'SET_AGENT_STEP'; step: AgentStep }
  | { type: 'SET_PENDING_REPLAN'; pending: boolean }
  | { type: 'SET_ERROR'; message: string }
  | { type: 'PARTIAL_RESEARCH'; source: string; data: any }
  | { type: 'SET_RESEARCH'; research: ResearchData }
  | { type: 'COMPLETE'; data: any }
  | { type: 'RESET' };

const initialState: TripState = {
  trip_id: '',
  status: 'collecting_preferences',
  chat_history: [],
};

function reducer(state: TripState, action: Action): TripState {
  switch (action.type) {
    case 'SET_TRIP_ID':
      return { ...state, trip_id: action.tripId };
    case 'SET_STATUS':
      return { ...state, status: action.status };
    case 'SET_REQUEST':
      return { ...state, request: action.request };
    case 'ADD_CHAT':
      return { ...state, chat_history: [...state.chat_history, action.message] };
    case 'SET_CHECKPOINT':
      return { ...state, checkpoint: action.checkpoint };
    case 'CLEAR_CHECKPOINT':
      return { ...state, checkpoint: undefined };
    case 'SET_PLAN_OPTIONS':
      return { ...state, plan_options: action.options };
    case 'SET_ITINERARY':
      return { ...state, itinerary: action.itinerary };
    case 'SET_BUDGET':
      return { ...state, budget_breakdown: action.budget };
    case 'SET_MARKERS':
      return { ...state, markers: action.markers };
    case 'ADD_REASONING':
      return { ...state, reasoning_log: [...(state.reasoning_log ?? []), action.entry] };
    case 'ADD_PRICE_CHANGE':
      return { ...state, price_changes: [...(state.price_changes ?? []), action.change] };
    case 'SET_AGENT_STEP': {
      const incoming = action.step;
      const prev = state.agent_step;
      // If previous agent finished (status=done) and differs from new agent, archive it
      const completed = [...(state.completed_agents ?? [])];
      if (prev && prev.status === 'done' && prev.agent !== incoming.agent) {
        completed.push(prev);
      }
      // Also archive if previous was a different agent but not done (new agent took over)
      if (prev && prev.agent !== incoming.agent && prev.status !== 'done') {
        completed.push({ ...prev, status: 'done' });
      }
      return { ...state, agent_step: incoming, completed_agents: completed };
    }
    case 'SET_PENDING_REPLAN':
      return { ...state, pending_replan: action.pending };
    case 'SET_ERROR':
      return { ...state, status: 'error', error: action.message };
    case 'PARTIAL_RESEARCH': {
      const prev = state.research ?? { flights: [], trains: [], buses: [], hotels: [], activities: [] };
      const updated = { ...prev };
      if (action.source === 'flights') updated.flights = action.data ?? [];
      else if (action.source === 'trains') updated.trains = action.data ?? [];
      else if (action.source === 'buses') updated.buses = action.data ?? [];
      else if (action.source === 'hotels') updated.hotels = action.data ?? [];
      else if (action.source === 'activities') updated.activities = action.data ?? [];
      return { ...state, research: updated };
    }
    case 'SET_RESEARCH':
      return { ...state, research: action.research };
    case 'COMPLETE':
      return { ...state, status: 'complete' };
    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

/* ── Hook ────────────────────────────── */

export function useTrip() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const tripIdRef = useRef<string | null>(state.trip_id || null);

  const handleSSEEvent = useCallback((event: SSEEvent) => {
    const { type, data } = event;

    switch (type) {
      case 'phase_update':
        dispatch({ type: 'ADD_CHAT', message: { role: 'system', content: data.detail || `${data.phase}: ${data.step}` } });
        // Map phase to status
        if (data.phase === 'research') dispatch({ type: 'SET_STATUS', status: 'researching' });
        else if (data.phase === 'planning') dispatch({ type: 'SET_STATUS', status: 'planning' });
        else if (data.phase === 'verification') dispatch({ type: 'SET_STATUS', status: 'verifying' });
        else if (data.phase === 'optimization') dispatch({ type: 'SET_STATUS', status: 'planning' });
        else if (data.phase === 'finalization') dispatch({ type: 'SET_STATUS', status: 'finalizing' });
        break;

      case 'agent_thinking':
        dispatch({ type: 'ADD_REASONING', entry: `[${data.agent}] ${data.thought}` });
        break;

      case 'agent_step':
        dispatch({
          type: 'SET_AGENT_STEP',
          step: { ...data, timestamp: Date.now() },
        });
        break;

      case 'research_partial':
        dispatch({ type: 'PARTIAL_RESEARCH', source: data.source, data: data.data });
        dispatch({ type: 'ADD_CHAT', message: { role: 'system', content: `Found ${data.source} results` } });
        break;

      case 'api_degraded':
        dispatch({ type: 'ADD_CHAT', message: { role: 'system', content: `⚠️ ${data.source} unavailable, using ${data.fallback_used}` } });
        break;

      case 'price_changed':
        dispatch({ type: 'ADD_PRICE_CHANGE', change: data });
        break;

      case 'checkpoint':
        dispatch({ type: 'SET_CHECKPOINT', checkpoint: data });
        if (data.checkpoint_id === 'cp1') dispatch({ type: 'SET_STATUS', status: 'checkpoint_1' });
        else if (data.checkpoint_id === 'cp2') dispatch({ type: 'SET_STATUS', status: 'checkpoint_2' });
        else if (data.checkpoint_id === 'cp3') dispatch({ type: 'SET_STATUS', status: 'checkpoint_3' });
        // Extract data from checkpoint
        if (data.itinerary) dispatch({ type: 'SET_ITINERARY', itinerary: data.itinerary });
        if (data.budget_breakdown) dispatch({ type: 'SET_BUDGET', budget: data.budget_breakdown });
        if (data.research) dispatch({ type: 'SET_RESEARCH', research: data.research });
        if (data.plan_options) dispatch({ type: 'SET_PLAN_OPTIONS', options: data.plan_options });
        break;

      case 'plan_ready':
        dispatch({ type: 'SET_PLAN_OPTIONS', options: data.options ?? data });
        break;

      case 'itinerary_ready':
        dispatch({ type: 'SET_ITINERARY', itinerary: data.itinerary ?? data });
        break;

      case 'map_update':
        dispatch({ type: 'SET_MARKERS', markers: data.markers || [] });
        break;

      case 'budget_update':
        dispatch({ type: 'SET_BUDGET', budget: data.breakdown ?? data });
        break;

      case 'error':
        dispatch({ type: 'SET_ERROR', message: data.message });
        break;

      case 'complete':
        dispatch({ type: 'COMPLETE', data });
        break;
    }
  }, []);

  // Connect SSE when we have a trip ID
  useSSE(state.trip_id || null, handleSSEEvent);

  const setTripId = useCallback((id: string) => {
    tripIdRef.current = id;
    dispatch({ type: 'SET_TRIP_ID', tripId: id });
  }, []);

  const addUserMessage = useCallback((content: string) => {
    dispatch({ type: 'ADD_CHAT', message: { role: 'user', content } });
  }, []);

  const addAssistantMessage = useCallback((content: string) => {
    dispatch({ type: 'ADD_CHAT', message: { role: 'assistant', content } });
  }, []);

  const setRequest = useCallback((request: TripRequest) => {
    dispatch({ type: 'SET_REQUEST', request });
  }, []);

  const reset = useCallback(() => {
    dispatch({ type: 'RESET' });
  }, []);

  return {
    state,
    dispatch,
    setTripId,
    addUserMessage,
    addAssistantMessage,
    setRequest,
    reset,
  };
}
