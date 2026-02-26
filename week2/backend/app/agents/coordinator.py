"""Coordinator Agent — Checkpoint management, price re-validation, orchestration helpers."""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.models.agent_state import TripState
from app.models.booking import BookingCart, BookingItem, MapMarker, MapRoute, TripPackage
from app.models.trip import TripRequest, TripStatus, CheckpointDecision
from app.services.sse_manager import sse_manager
from app.tools.flights import search_flights
from app.tools.hotels import search_hotels

logger = logging.getLogger(__name__)
settings = get_settings()

# Checkpoint ordering for resume logic
_CHECKPOINT_ORDER = {"cp1": 1, "cp2": 2, "cp3": 3}


def _should_skip_checkpoint(state: TripState, this_cp: str) -> bool:
    """Return True if this checkpoint should be skipped (already passed in a previous run)."""
    decision = state.get("checkpoint_decision", {})
    if not isinstance(decision, dict):
        return False
    decision_cp = decision.get("checkpoint", "")
    if not decision_cp:
        return False
    # Skip if the decision is for this checkpoint or any later one
    return _CHECKPOINT_ORDER.get(decision_cp, 0) >= _CHECKPOINT_ORDER.get(this_cp, 0)

# Minimum viable cost lookup (destination → per-day minimum in INR)
MIN_COST_PER_DAY: dict[str, float] = {
    "rishikesh": 2000,
    "goa": 3000,
    "manali": 2500,
    "jaipur": 2000,
    "coorg": 2500,
    "mumbai": 3500,
    "delhi": 3000,
    "bangalore": 3000,
    "kerala": 3000,
    "ladakh": 4000,
    "bangkok": 3500,
    "bali": 4000,
    "tokyo": 8000,
    "paris": 12000,
    "london": 12000,
    "new york": 15000,
    "dubai": 6000,
    "singapore": 7000,
}

DEFAULT_MIN_PER_DAY = 2500


def check_budget_feasibility(request: TripRequest) -> dict:
    """Check if budget is realistic for the destination, duration, and group size."""
    dest_lower = request.destination.lower().strip()
    min_per_day = MIN_COST_PER_DAY.get(dest_lower, DEFAULT_MIN_PER_DAY)
    traveler_count = max(request.traveler_count, 1)
    min_total = min_per_day * request.duration_days * traveler_count

    is_feasible = request.budget >= min_total
    group_note = f" for {traveler_count} travelers" if traveler_count > 1 else ""
    return {
        "is_feasible": is_feasible,
        "min_estimated": min_total,
        "budget": request.budget,
        "currency": request.currency,
        "traveler_count": traveler_count,
        "per_person_budget": round(request.budget / traveler_count, 2),
        "suggestion": None if is_feasible else (
            f"Budget of {request.currency} {request.budget} may be too low for "
            f"{request.duration_days} days in {request.destination}{group_note}. "
            f"Minimum estimated: {request.currency} {min_total}. "
            f"Consider increasing budget or reducing duration."
        ),
    }


async def checkpoint_1(state: TripState) -> TripState:
    """Checkpoint 1: Trip Understanding + Plan Direction — present parsed request + plan options."""
    if _should_skip_checkpoint(state, "cp1"):
        logger.info("Checkpoint 1: already passed, skipping")
        state["awaiting_human"] = False
        return state

    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    research = state.get("research", {})
    plan_options = state.get("plan_options", [])
    budget = state.get("budget_breakdown", {})
    itinerary = state.get("itinerary", {})
    feasibility = check_budget_feasibility(request)

    advisory = research.get("travel_advisory", {})
    is_intl = advisory.get("is_international", False)

    # Serialize research items for preview
    raw_flights = research.get("flights", [])
    raw_trains = research.get("trains", [])
    raw_buses = research.get("buses", [])
    raw_hotels = research.get("hotels", [])
    raw_activities = research.get("activities", [])
    flights_data = [f.model_dump(mode="json") if hasattr(f, "model_dump") else f for f in raw_flights]
    trains_data = [t.model_dump(mode="json") if hasattr(t, "model_dump") else t for t in raw_trains]
    buses_data = [b.model_dump(mode="json") if hasattr(b, "model_dump") else b for b in raw_buses]
    hotels_data = [h.model_dump(mode="json") if hasattr(h, "model_dump") else h for h in raw_hotels]
    activities_data = [a.model_dump(mode="json") if hasattr(a, "model_dump") else a for a in raw_activities]

    # Build trip understanding summary
    styles_str = ", ".join(s.value if hasattr(s, "value") else str(s) for s in (request.styles or []))
    trip_understanding = {
        "traveler_type": request.traveler_type.value if hasattr(request.traveler_type, "value") else str(request.traveler_type),
        "styles": styles_str or "General",
        "budget": request.budget,
        "currency": request.currency,
        "origin": request.origin,
        "destination": request.destination,
        "duration_days": request.duration_days,
        "start_date": str(request.start_date) if request.start_date else "Flexible",
        "end_date": str(request.end_date) if request.end_date else "Flexible",
        "traveler_count": request.traveler_count,
        "interests": request.interests,
    }

    checkpoint_data = {
        "type": "plan_direction",
        "checkpoint_id": "cp1",
        "trip_understanding": trip_understanding,
        "plan_options": plan_options,
        "budget_feasibility": feasibility,
        "research_summary": {
            "flights_found": len(raw_flights),
            "trains_found": len(raw_trains),
            "buses_found": len(raw_buses),
            "hotels_found": len(raw_hotels),
            "activities_found": len(raw_activities),
            "is_international": is_intl,
        },
        "research": {
            "flights": flights_data,
            "trains": trains_data,
            "buses": buses_data,
            "hotels": hotels_data,
            "activities": activities_data,
        },
        "options": ["select_plan", "request_changes", "cancel"],
    }

    if is_intl and advisory:
        checkpoint_data["travel_advisory"] = advisory

    state["status"] = TripStatus.CHECKPOINT_1
    state["last_checkpoint"] = "cp1"
    state["checkpoint_decision"] = {}  # Clear stale decision
    state["awaiting_human"] = True

    # Emit map markers from itinerary
    markers: list[dict] = []
    if isinstance(itinerary, dict):
        for day in itinerary.get("days", []):
            for act in day.get("activities", []):
                if act.get("latitude") and act.get("longitude"):
                    markers.append({
                        "name": act.get("name"),
                        "lat": act["latitude"],
                        "lng": act["longitude"],
                        "day": day.get("day_number"),
                        "type": act.get("category", "activity"),
                    })
    if markers:
        await sse_manager.emit_map_update(trip_id, markers, [])

    await sse_manager.emit_checkpoint(trip_id, checkpoint_data)
    await sse_manager.emit_itinerary_ready(trip_id, itinerary)
    await sse_manager.emit_agent_step(trip_id, "coordinator", "Awaiting your input", "Please review the plan options and select one", "waiting")
    return state


async def checkpoint_2(state: TripState) -> TripState:
    """Checkpoint 2: Budget Allocation Approval."""
    if _should_skip_checkpoint(state, "cp2"):
        logger.info("Checkpoint 2: already passed, skipping")
        state["awaiting_human"] = False
        return state

    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    budget = state.get("budget_breakdown", {})
    itinerary = state.get("itinerary", {})

    checkpoint_data = {
        "type": "budget_review",
        "checkpoint_id": "cp2",
        "budget_breakdown": budget,
        "options": ["approve_and_continue", "request_changes", "cancel"],
    }

    state["status"] = TripStatus.CHECKPOINT_2
    state["last_checkpoint"] = "cp2"
    state["checkpoint_decision"] = {}  # Clear stale decision
    state["awaiting_human"] = True

    # Emit budget update for right panel
    if budget:
        await sse_manager.emit_budget_update(trip_id, budget if isinstance(budget, dict) else budget)

    await sse_manager.emit_checkpoint(trip_id, checkpoint_data)
    await sse_manager.emit_agent_step(trip_id, "coordinator", "Awaiting budget approval", "Review and approve the budget breakdown", "waiting")
    return state


async def checkpoint_3(state: TripState) -> TripState:
    """Checkpoint 3: Final review with price re-validation."""
    # If resuming with an existing decision for this checkpoint, pass through
    if _should_skip_checkpoint(state, "cp3"):
        logger.info("Checkpoint 3: already passed, skipping")
        state["awaiting_human"] = False
        return state

    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    itinerary = state.get("itinerary", {})
    budget = state.get("budget_breakdown", {})

    # Price re-validation
    await sse_manager.emit_phase_update(trip_id, "validation", "prices", "Re-checking prices...")
    await sse_manager.emit_agent_step(trip_id, "coordinator", "Re-validating prices", "Checking for price changes since research", "running")

    price_changes: list[dict] = []

    # Re-check flight price
    selected_flight = itinerary.get("selected_flight") if isinstance(itinerary, dict) else None
    if selected_flight:
        old_price = selected_flight.get("price", 0)
        try:
            fresh_flights = await search_flights(
                request.origin, request.destination,
                str(request.start_date) if request.start_date else "",
                str(request.end_date) if request.end_date else "",
                request.currency,
            )
            # Find same airline/route
            for f in fresh_flights:
                if hasattr(f, "model_dump"):
                    f = f.model_dump()
                if f.get("airline_or_operator") == selected_flight.get("airline_or_operator"):
                    new_price = f.get("price", old_price)
                    if abs(new_price - old_price) > 1:
                        change = {"item": "flight", "old_price": old_price, "new_price": new_price}
                        price_changes.append(change)
                        await sse_manager.emit_price_changed(trip_id, "flight", old_price, new_price)
                    break
        except Exception as e:
            logger.warning("Flight price revalidation failed: %s", e)

    # Re-check hotel price
    selected_hotel = itinerary.get("selected_hotel") if isinstance(itinerary, dict) else None
    if selected_hotel:
        old_price = selected_hotel.get("price_per_night", 0)
        try:
            fresh_hotels = await search_hotels(
                request.destination,
                str(request.start_date) if request.start_date else "",
                str(request.end_date) if request.end_date else "",
                request.duration_days - 1,
                request.currency,
            )
            for h in fresh_hotels:
                if hasattr(h, "model_dump"):
                    h = h.model_dump()
                if h.get("name") == selected_hotel.get("name"):
                    new_price = h.get("price_per_night", old_price)
                    if abs(new_price - old_price) > 1:
                        change = {"item": "hotel", "old_price": old_price, "new_price": new_price}
                        price_changes.append(change)
                        await sse_manager.emit_price_changed(trip_id, "hotel", old_price, new_price)
                    break
        except Exception as e:
            logger.warning("Hotel price revalidation failed: %s", e)

    state["price_changes"] = price_changes

    # Build map data
    markers: list[dict] = []
    routes: list[dict] = []

    if isinstance(itinerary, dict):
        for day in itinerary.get("days", []):
            for act in day.get("activities", []):
                if act.get("latitude") and act.get("longitude"):
                    markers.append({
                        "name": act.get("name"),
                        "lat": act["latitude"],
                        "lng": act["longitude"],
                        "day": day.get("day_number"),
                        "type": act.get("category", "activity"),
                    })

    state["markers"] = markers
    state["routes"] = routes

    await sse_manager.emit_map_update(trip_id, markers, routes)

    # Emit budget and itinerary so frontend renders them on the right panel
    if budget:
        budget_to_emit = budget if isinstance(budget, dict) else budget
        await sse_manager.emit_budget_update(trip_id, budget_to_emit)
    if itinerary:
        itinerary_to_emit = itinerary if isinstance(itinerary, dict) else itinerary
        await sse_manager.emit_itinerary_ready(trip_id, itinerary_to_emit)

    # Emit checkpoint
    # Build structured booking options for the booking cart UI
    booking_options: list[dict] = []

    # Travel option
    selected_flight = itinerary.get("selected_flight") if isinstance(itinerary, dict) else None
    if selected_flight:
        transport_mode = selected_flight.get("mode", "flight")
        transport_icon = {"flight": "plane", "train": "train", "bus": "bus"}.get(transport_mode, "plane")
        duration_mins = selected_flight.get("duration_minutes", 0)
        duration_str = f"{duration_mins // 60}h {duration_mins % 60}m" if duration_mins else ""
        booking_options.append({
            "category": "travel",
            "icon": transport_icon,
            "name": selected_flight.get("airline_or_operator", "Transport"),
            "route": f"{request.origin} → {request.destination}",
            "mode": transport_mode,
            "cost": selected_flight.get("price", 0),
            "currency": request.currency,
            "details": [
                d for d in [
                    f"Departure: {selected_flight.get('departure_time', '')}" if selected_flight.get("departure_time") else None,
                    f"Duration: {duration_str}" if duration_str else None,
                    f"Class: {selected_flight.get('class_type', '')}" if selected_flight.get("class_type") else None,
                ] if d
            ],
            "booking_url": selected_flight.get("booking_url", ""),
        })

    # Stay option
    selected_hotel = itinerary.get("selected_hotel") if isinstance(itinerary, dict) else None
    if selected_hotel:
        nights = max(request.duration_days - 1, 1)
        ppn = selected_hotel.get("price_per_night", 0)
        booking_options.append({
            "category": "stay",
            "icon": "hotel",
            "name": selected_hotel.get("name", "Hotel"),
            "cost_per_night": ppn,
            "nights": nights,
            "cost": ppn * nights,
            "currency": request.currency,
            "location": selected_hotel.get("location", ""),
            "rating": selected_hotel.get("rating"),
            "details": [
                d for d in [
                    f"₹{ppn:,.0f}/night × {nights} nights = ₹{ppn * nights:,.0f}" if ppn else None,
                    f"Location: {selected_hotel.get('location', '')}" if selected_hotel.get("location") else None,
                    f"Rating: {'⭐' * int(selected_hotel.get('rating', 0))} ({selected_hotel.get('rating', 'N/A')})" if selected_hotel.get("rating") else None,
                ] if d
            ],
            "booking_url": selected_hotel.get("booking_url", ""),
        })

    # Activity options — pick top bookable activities from itinerary
    if isinstance(itinerary, dict):
        seen_names: set[str] = set()
        for day in itinerary.get("days", []):
            for act in day.get("activities", []):
                act_name = act.get("name", "")
                if act_name and act_name not in seen_names and act.get("cost", 0) > 0:
                    seen_names.add(act_name)
                    booking_options.append({
                        "category": "activity",
                        "icon": "activity",
                        "name": act_name,
                        "cost": act.get("cost", 0),
                        "currency": request.currency,
                        "day": day.get("day_number"),
                        "details": [
                            d for d in [
                                act.get("description", ""),
                                f"Day {day.get('day_number')} • {act.get('time_slot', {}).get('start', '')}–{act.get('time_slot', {}).get('end', '')}" if act.get("time_slot") else None,
                                f"Category: {act.get('category', '')}" if act.get("category") else None,
                            ] if d
                        ],
                        "booking_url": act.get("booking_url", ""),
                        "place_id": act.get("place_id", ""),
                    })

    booking_total = sum(b.get("cost", 0) for b in booking_options)

    checkpoint_data = {
        "type": "final_review",
        "checkpoint_id": "cp3",
        "booking_options": booking_options,
        "booking_total": booking_total,
        "itinerary": itinerary,
        "budget_breakdown": budget,
        "verification_results": state.get("verification_results", []),
        "price_changes": price_changes,
        "options": ["confirm_and_book", "request_changes", "cancel"],
    }

    state["status"] = TripStatus.CHECKPOINT_3
    state["last_checkpoint"] = "cp3"
    state["checkpoint_decision"] = {}  # Clear stale decision
    state["awaiting_human"] = True

    await sse_manager.emit_checkpoint(trip_id, checkpoint_data)
    await sse_manager.emit_agent_step(trip_id, "coordinator", "Final review ready", "Confirm your bookings to proceed", "waiting")
    return state


async def finalize(state: TripState) -> TripState:
    """Finalize the trip — build booking cart and compile package."""
    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    itinerary = state.get("itinerary", {})
    budget = state.get("budget_breakdown", {})

    state["status"] = TripStatus.FINALIZING

    await sse_manager.emit_phase_update(trip_id, "finalization", "starting", "Compiling your trip package...")
    await sse_manager.emit_agent_step(trip_id, "finalizer", "Compiling trip package", "Building booking cart & final itinerary", "running")

    # Build booking cart
    booking_items: list[dict] = []

    if isinstance(itinerary, dict):
        flight = itinerary.get("selected_flight")
        if flight:
            booking_items.append({
                "id": f"booking-flight-{trip_id[:8]}",
                "category": "flight",
                "name": f"Flight: {flight.get('airline_or_operator', 'Flight')} to {request.destination}",
                "price": flight.get("price", 0),
                "currency": request.currency,
                "booking_url": flight.get("booking_url", ""),
            })

        hotel = itinerary.get("selected_hotel")
        if hotel:
            nights = max(request.duration_days - 1, 1)
            booking_items.append({
                "id": f"booking-hotel-{trip_id[:8]}",
                "category": "hotel",
                "name": f"Hotel: {hotel.get('name', 'Hotel')} ({nights} nights)",
                "price": hotel.get("price_per_night", 0) * nights,
                "currency": request.currency,
                "booking_url": hotel.get("booking_url", ""),
            })

    booking_cart = {
        "items": booking_items,
        "total": sum(i.get("price", 0) for i in booking_items),
        "currency": request.currency,
    }

    state["booking_cart"] = booking_cart
    state["status"] = TripStatus.COMPLETE

    # Compile final package
    trip_package = {
        "trip_id": trip_id,
        "request": request.model_dump(mode="json") if hasattr(request, "model_dump") else request,
        "itinerary": itinerary,
        "budget_breakdown": budget,
        "booking_cart": booking_cart,
        "verification_results": state.get("verification_results", []),
        "reasoning_log": state.get("reasoning_log", []),
    }

    await sse_manager.emit_agent_step(trip_id, "finalizer", "Trip ready!", "Your complete trip package is ready", "done",
        [f"{len(booking_items)} bookings compiled"])
    await sse_manager.emit_complete(trip_id, trip_package)
    return state
