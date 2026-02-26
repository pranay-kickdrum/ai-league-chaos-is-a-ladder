import { useCallback, useEffect } from 'react';
import { Download, FileText } from 'lucide-react';
import ChatPanel from '../components/chat/ChatPanel';
import ProgressStepper from '../components/progress/ProgressStepper';
import AgentLiveStatus from '../components/progress/AgentLiveStatus';
import ItineraryTimeline from '../components/itinerary/ItineraryTimeline';
import BudgetBreakdownComp from '../components/budget/BudgetBreakdown';
import BookingCartComp from '../components/booking/BookingCart';
import TripMap from '../components/map/TripMap';
import ResearchPreview from '../components/research/ResearchPreview';
import ErrorRecovery from '../components/common/ErrorRecovery';
import { useTrip } from '../hooks/useTrip';
import {
  createTrip,
  sendChatMessage,
  submitCheckpoint,
  requestReplan,
  getTrip,
  getExportPdfUrl,
  getExportHtmlUrl,
} from '../services/api';

interface TripPageProps {
  tripId?: string;
  onBack: () => void;
}

export default function TripPage({ tripId: initialTripId, onBack }: TripPageProps) {
  const { state, dispatch, setTripId, addUserMessage, addAssistantMessage, setRequest, reset } = useTrip();

  // Load existing trip if ID provided
  useEffect(() => {
    if (initialTripId) {
      setTripId(initialTripId);
      getTrip(initialTripId)
        .then((trip) => {
          if (trip?.request_json) {
            const req = typeof trip.request_json === 'string'
              ? JSON.parse(trip.request_json)
              : trip.request_json;
            setRequest(req);
          }
        })
        .catch(console.error);
    }
  }, [initialTripId, setTripId, setRequest]);

  const handleSend = useCallback(
    async (text: string) => {
      addUserMessage(text);

      try {
        if (!state.trip_id) {
          // First message — create trip
          const res = await createTrip(text);
          if (res.trip_id) {
            setTripId(res.trip_id);
          }
          if (res.status === 'needs_info') {
            addAssistantMessage(res.follow_up || 'Could you tell me more about your trip?');
          } else if (res.request) {
            setRequest(res.request);
            dispatch({ type: 'SET_STATUS', status: 'researching' });
            addAssistantMessage(
              `Great! Planning a ${res.request.duration_days}-day trip to ${res.request.destination}. Let me research the best options for you...`
            );
          }
        } else if (state.pending_replan) {
          // User is providing change feedback after clicking "Request Changes"
          dispatch({ type: 'SET_PENDING_REPLAN', pending: false });
          dispatch({ type: 'CLEAR_CHECKPOINT' });
          dispatch({ type: 'SET_STATUS', status: 'replanning' });
          addAssistantMessage(`Got it! Adjusting the plan: "${text}"...`);
          await requestReplan(state.trip_id, text);
        } else {
          // Follow-up message
          const res = await sendChatMessage(state.trip_id, text);
          if (res.status === 'needs_info') {
            addAssistantMessage(res.follow_up || 'Tell me more!');
          } else if (res.status === 'started' && res.request) {
            setRequest(res.request);
            dispatch({ type: 'SET_STATUS', status: 'researching' });
            addAssistantMessage('Perfect! Starting research now...');
          }
        }
      } catch (err: any) {
        addAssistantMessage(`Sorry, something went wrong: ${err.message}`);
      }
    },
    [state.trip_id, state.pending_replan, setTripId, addUserMessage, addAssistantMessage, setRequest, dispatch]
  );

  const handleCheckpointAction = useCallback(
    async (action: string) => {
      if (!state.trip_id || !state.checkpoint) return;
      const cpId = state.checkpoint.checkpoint_id;

      // Handle plan selection (CP1 now has plan options)
      if (action.startsWith('select_plan:')) {
        const planId = action.replace('select_plan:', '');
        await submitCheckpoint(state.trip_id, cpId, 'select', planId);
        dispatch({ type: 'CLEAR_CHECKPOINT' });
        addAssistantMessage(`Selected plan ${planId}. Reviewing budget allocation...`);
        return;
      }

      if (action === 'request_changes') {
        dispatch({ type: 'SET_PENDING_REPLAN', pending: true });
        addAssistantMessage('What would you like to change?');
        return;
      }

      try {
        const mappedAction = (action === 'approve_and_continue' || action === 'confirm_and_book') ? 'approve' : action;
        await submitCheckpoint(state.trip_id, cpId, mappedAction);
        dispatch({ type: 'CLEAR_CHECKPOINT' });
        addAssistantMessage(`Decision: ${action}. Continuing...`);
      } catch (err: any) {
        addAssistantMessage(`Error: ${err.message}`);
      }
    },
    [state.trip_id, state.checkpoint, addAssistantMessage, dispatch]
  );

  const isProcessing = ['researching', 'planning', 'verifying', 'finalizing', 'replanning'].includes(
    state.status
  );

  return (
    <div className="flex flex-col h-[calc(100vh-56px)]">
      {/* Progress stepper */}
      <ProgressStepper status={state.status} />

      {/* Main content — split layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left — Chat panel */}
        <div className="w-1/2 border-r border-slate-200 flex flex-col">
          <ChatPanel
            messages={state.chat_history}
            checkpoint={state.checkpoint}
            onSend={handleSend}
            onCheckpointAction={handleCheckpointAction}
            disabled={isProcessing}
          />
        </div>

        {/* Right — Live preview */}
        <div className="w-1/2 overflow-y-auto bg-slate-50 p-4 space-y-4">
          {/* Error state */}
          {state.status === 'error' && (
            <ErrorRecovery
              message={state.error || 'An error occurred'}
              onRetry={() => state.trip_id && handleSend('retry')}
              onGoBack={onBack}
            />
          )}

          {/* Live agent status — always at top */}
          <AgentLiveStatus
            currentStep={state.agent_step}
            completedAgents={state.completed_agents}
          />

          {/* Export buttons */}
          {state.status === 'complete' && state.trip_id && (
            <div className="flex gap-2">
              <a
                href={getExportPdfUrl(state.trip_id)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-4 py-2 bg-sunset text-white rounded-lg text-sm font-medium hover:bg-orange-600 transition"
              >
                <Download className="w-4 h-4" /> Download PDF
              </a>
              <a
                href={getExportHtmlUrl(state.trip_id)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 transition"
              >
                <FileText className="w-4 h-4" /> View HTML
              </a>
            </div>
          )}

          {/* Booking cart */}
          {state.booking_cart && (
            <BookingCartComp cart={state.booking_cart} />
          )}

          {/* Itinerary timeline */}
          {state.itinerary && (
            <ItineraryTimeline itinerary={state.itinerary} />
          )}

          {/* Budget */}
          {state.budget_breakdown && (
            <BudgetBreakdownComp
              budget={state.budget_breakdown}
              limit={state.request?.budget}
            />
          )}

          {/* Map */}
          <TripMap markers={state.markers ?? []} />

          {/* Research preview — earliest phase, shown at bottom */}
          {state.research && (
            <ResearchPreview
              research={state.research}
              currency={state.request?.currency}
            />
          )}
        </div>
      </div>
    </div>
  );
}
