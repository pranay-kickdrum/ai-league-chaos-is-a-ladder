"""Trip API routes — CRUD + SSE streaming + checkpoint submission."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.coordinator import check_budget_feasibility
from app.agents.graph import get_compiled_graph
from app.agents.intent_parser import parse_intent
from app.db.database import get_db
from app.models.agent_state import TripState
from app.models.trip import CheckpointDecision, TripRequest, TripStatus
from app.services.sse_manager import sse_manager
from app.services.trip_service import create_trip, get_trip, list_trips, update_trip_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.post("")
async def create_new_trip(
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """Create a new trip and start the LangGraph workflow."""
    trip_id = str(uuid.uuid4())

    # Parse the user message into a TripRequest
    user_message = body.get("message", "")
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

    # Build a minimal TripState so parse_intent can work
    intent_state: TripState = {
        "trip_id": trip_id,
        "request": {},
        "chat_history": [{"role": "user", "content": user_message}],
        "current_message": user_message,
        "status": TripStatus.GATHERING_INTENT,
        "research": {},
        "plan_options": [],
        "itinerary": {},
        "budget_breakdown": {},
        "verification_results": [],
        "booking_cart": {},
        "price_changes": [],
        "markers": [],
        "routes": [],
        "reasoning_log": [],
    }

    # Parse intent — mutates and returns state
    parsed_state = await parse_intent(intent_state)

    trip_request = parsed_state.get("request")
    if isinstance(trip_request, dict):
        from app.models.trip import TripRequest as TR
        try:
            trip_request = TR(**trip_request)
        except Exception:
            trip_request = None

    if trip_request is None or parsed_state.get("status") == TripStatus.GATHERING_INTENT:
        # Need more info — create trip in DB so follow-up /chat works
        await create_trip(db, trip_id, user_message)

        # Normalize request for JSON serialization
        req_for_json = {}
        raw_req = parsed_state.get("request", {})
        if hasattr(raw_req, "model_dump"):
            req_for_json = raw_req.model_dump(mode="json")
        elif isinstance(raw_req, dict):
            req_for_json = raw_req

        # Normalize chat_history — convert any pydantic objects to dicts
        chat_hist = []
        for m in parsed_state.get("chat_history", intent_state["chat_history"]):
            if isinstance(m, dict):
                chat_hist.append(m)
            elif hasattr(m, "model_dump"):
                chat_hist.append(m.model_dump())
            elif hasattr(m, "role") and hasattr(m, "content"):
                chat_hist.append({"role": m.role, "content": m.content})

        partial_state = {**intent_state, "request": req_for_json, "chat_history": chat_hist}
        await update_trip_state(db, trip_id, state_json=json.dumps(partial_state, default=str))

        last_msg = ""
        history = parsed_state.get("chat_history", [])
        if history:
            last = history[-1]
            last_msg = last.content if hasattr(last, "content") else last.get("content", "")
        return JSONResponse({
            "trip_id": trip_id,
            "status": "needs_info",
            "follow_up": last_msg,
            "parsed_so_far": trip_request.model_dump(mode="json") if hasattr(trip_request, "model_dump") else {},
        })

    # Check budget feasibility
    feasibility = check_budget_feasibility(trip_request)

    # Create trip in DB
    row = await create_trip(db, trip_id, trip_request)

    # Build initial state from parsed intent
    initial_state: TripState = {
        **parsed_state,
        "request": trip_request.model_dump(mode="json"),
        "status": TripStatus.RESEARCHING,
    }

    # Start the graph in background
    asyncio.create_task(_run_graph(trip_id, initial_state, db))

    return JSONResponse({
        "trip_id": trip_id,
        "status": "started",
        "request": trip_request.model_dump(mode="json"),
        "budget_feasibility": feasibility,
    })


async def _run_graph(trip_id: str, initial_state: TripState, db: AsyncSession):
    """Run the LangGraph workflow in background."""
    # Small delay to let frontend establish SSE connection
    await asyncio.sleep(1.0)
    try:
        graph = get_compiled_graph()
        # Run until we hit a checkpoint (awaiting_human = True)
        state = initial_state
        async for event in graph.astream(state):
            # LangGraph streams node outputs
            for node_name, node_output in event.items():
                if isinstance(node_output, dict):
                    state.update(node_output)
                    # If checkpoint reached, pause
                    if node_output.get("awaiting_human"):
                        logger.info("Trip %s paused at checkpoint", trip_id)
                        # Persist state (including itinerary/budget for export)
                        await update_trip_state(
                            db, trip_id,
                            status=state.get("status", ""),
                            last_checkpoint=state.get("last_checkpoint"),
                            state_json=json.dumps(state, default=str),
                            itinerary_json=json.dumps(state.get("itinerary", {}), default=str) if state.get("itinerary") else None,
                            budget_json=json.dumps(state.get("budget_breakdown", {}), default=str) if state.get("budget_breakdown") else None,
                        )
                        return
        # Graph completed — persist full state + itinerary/budget for export
        await update_trip_state(
            db, trip_id,
            status=state.get("status", ""),
            state_json=json.dumps(state, default=str),
            itinerary_json=json.dumps(state.get("itinerary", {}), default=str) if state.get("itinerary") else None,
            budget_json=json.dumps(state.get("budget_breakdown", {}), default=str) if state.get("budget_breakdown") else None,
        )
    except Exception as e:
        logger.exception("Graph execution failed for trip %s", trip_id)
        await sse_manager.emit_error(
            trip_id,
            f"Trip planning failed: {str(e)}",
            ["retry", "start_over"],
        )


@router.get("/{trip_id}")
async def get_trip_status(
    trip_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get current trip status and state."""
    trip = await get_trip(db, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.get("")
async def list_all_trips(
    db: AsyncSession = Depends(get_db),
):
    """List all trips (including samples)."""
    trips = await list_trips(db)
    return {"trips": trips}


@router.get("/{trip_id}/stream")
async def stream_events(trip_id: str, request: Request):
    """SSE endpoint — stream live updates for a trip."""
    async def event_generator():
        queue = sse_manager.subscribe(trip_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": event.get("type", "message"),
                        "data": json.dumps(event.get("data", {}), default=str),
                    }
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "keepalive", "data": "{}"}
        finally:
            sse_manager.unsubscribe(trip_id, queue)

    return EventSourceResponse(event_generator())


@router.post("/{trip_id}/checkpoint")
async def submit_checkpoint(
    trip_id: str,
    body: CheckpointDecision,
    db: AsyncSession = Depends(get_db),
):
    """Submit a checkpoint decision to resume the workflow."""
    trip = await get_trip(db, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Load state
    state_json = trip.state_json
    if not state_json:
        raise HTTPException(status_code=400, detail="No state to resume")

    state: TripState = json.loads(state_json) if isinstance(state_json, str) else state_json
    state["checkpoint_decision"] = body.model_dump()
    state["awaiting_human"] = False

    # Resume graph
    asyncio.create_task(_run_graph(trip_id, state, db))

    return {"status": "resumed", "trip_id": trip_id}


@router.post("/{trip_id}/chat")
async def send_chat_message(
    trip_id: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """Send a chat message during guided conversation."""
    message = body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    trip = await get_trip(db, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    state_json = trip.state_json
    state: TripState = json.loads(state_json) if isinstance(state_json, str) and state_json else {}

    # Normalize chat_history — ensure all entries are dicts
    raw_history = state.get("chat_history", [])
    history: list[dict] = []
    for m in raw_history:
        if isinstance(m, dict) and "role" in m and "content" in m:
            history.append(m)
        elif hasattr(m, "role") and hasattr(m, "content"):
            history.append({"role": m.role, "content": m.content})
        # Skip malformed entries

    history.append({"role": "user", "content": message})

    # Re-parse with full history
    parse_state: TripState = {
        "trip_id": trip_id,
        "request": state.get("request", {}),
        "chat_history": history,
        "current_message": message,
        "status": TripStatus.GATHERING_INTENT,
    }
    parsed_state = await parse_intent(parse_state)
    trip_request = parsed_state.get("request")
    if isinstance(trip_request, dict):
        from app.models.trip import TripRequest as TR
        try:
            trip_request = TR(**trip_request)
        except Exception:
            trip_request = None

    if trip_request and parsed_state.get("status") != TripStatus.GATHERING_INTENT:
        # Build a full initial state with all required fields
        full_state: TripState = {
            "trip_id": trip_id,
            "request": trip_request.model_dump(mode="json"),
            "chat_history": history,
            "current_message": message,
            "status": TripStatus.RESEARCHING,
            "research": state.get("research", {}),
            "plan_options": state.get("plan_options", []),
            "itinerary": state.get("itinerary", {}),
            "budget_breakdown": state.get("budget_breakdown", {}),
            "verification_results": state.get("verification_results", []),
            "booking_cart": state.get("booking_cart", {}),
            "price_changes": state.get("price_changes", []),
            "markers": state.get("markers", []),
            "routes": state.get("routes", []),
            "reasoning_log": state.get("reasoning_log", []),
        }
        # Check budget feasibility
        feasibility = check_budget_feasibility(trip_request)
        # Start graph
        asyncio.create_task(_run_graph(trip_id, full_state, db))
        return {
            "status": "started",
            "request": trip_request.model_dump(mode="json"),
            "budget_feasibility": feasibility,
        }
    else:
        last_msg = ""
        chat_hist = parsed_state.get("chat_history", [])
        if chat_hist:
            last = chat_hist[-1]
            last_msg = last.content if hasattr(last, "content") else last.get("content", "")
        history.append({"role": "assistant", "content": last_msg or "Could you tell me more?"})

        # Persist the PARSED state (with updated request), not the old state
        req_for_save = {}
        raw_req = parsed_state.get("request", {})
        if hasattr(raw_req, "model_dump"):
            req_for_save = raw_req.model_dump(mode="json")
        elif isinstance(raw_req, dict):
            req_for_save = raw_req
        updated_state = {**state, "chat_history": history, "request": req_for_save}
        await update_trip_state(db, trip_id, state_json=json.dumps(updated_state, default=str))
        return {
            "status": "needs_info",
            "follow_up": last_msg or "Could you tell me more?",
            "chat_history": history,
        }


@router.post("/{trip_id}/replan")
async def trigger_replan(
    trip_id: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    """Trigger re-planning with a change request."""
    change_request = body.get("message", "")
    if not change_request:
        raise HTTPException(status_code=400, detail="Change request is required")

    trip = await get_trip(db, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    state_json = trip.state_json
    state: TripState = json.loads(state_json) if isinstance(state_json, str) and state_json else {}

    state["replan_request"] = change_request
    state["awaiting_human"] = False

    # Run replan node then continue graph
    from app.agents.replanner import replan as replan_fn
    state = await replan_fn(state)

    # Resume from appropriate point
    asyncio.create_task(_run_graph(trip_id, state, db))

    return {"status": "replanning", "trip_id": trip_id}
