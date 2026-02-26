"""Planner Agent — Heuristic scheduling + LLM narration."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.models.agent_state import TripState
from app.models.booking import (
    ActivityOption,
    BudgetBreakdown,
    FlightOption,
    HotelOption,
)
from app.models.itinerary import Activity, DayPlan, Itinerary, MealSuggestion, TimeSlot, TransportLeg
from app.models.trip import PlanOption, TripRequest, TripStatus, TravelStyle
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)
settings = get_settings()

# Budget allocation ratios by travel style
BUDGET_RATIOS: dict[str, dict[str, float]] = {
    "backpacking": {"transport": 0.15, "accommodation": 0.25, "food": 0.20, "activities": 0.25, "buffer": 0.15},
    "comfort": {"transport": 0.25, "accommodation": 0.30, "food": 0.15, "activities": 0.20, "buffer": 0.10},
    "luxury": {"transport": 0.20, "accommodation": 0.35, "food": 0.20, "activities": 0.15, "buffer": 0.10},
    "adventure": {"transport": 0.20, "accommodation": 0.20, "food": 0.15, "activities": 0.35, "buffer": 0.10},
    "default": {"transport": 0.20, "accommodation": 0.30, "food": 0.15, "activities": 0.25, "buffer": 0.10},
}


def _allocate_budget(total: float, style: str) -> dict[str, float]:
    """Split budget into categories by travel style."""
    ratios = BUDGET_RATIOS.get(style, BUDGET_RATIOS["default"])
    return {k: round(total * v, 2) for k, v in ratios.items()}


def _build_time_slots(day_index: int, activities: list[dict], start_hour: int = 9) -> list[Activity]:
    """Schedule activities into time slots using simple sequential allocation."""
    scheduled: list[Activity] = []
    current_hour = start_hour

    for act in activities:
        if current_hour >= 21:  # Don't schedule after 9 PM
            break

        duration_hours = act.get("duration_hours", 2)
        slot = TimeSlot(
            start=f"{current_hour:02d}:00",
            end=f"{current_hour + duration_hours:02d}:00",
        )
        activity = Activity(
            id=act.get("id", str(uuid.uuid4())[:8]),
            name=act.get("name", "Activity"),
            description=act.get("description", ""),
            time_slot=slot,
            category=act.get("category", "sightseeing"),
            cost=act.get("price", act.get("cost", 0)),
            currency=act.get("currency", "INR"),
            place_id=act.get("place_id"),
            research_result_id=act.get("id"),
            location=act.get("address", act.get("location", "")),
            latitude=act.get("latitude"),
            longitude=act.get("longitude"),
            booking_url=act.get("booking_url"),
            is_verified=bool(act.get("place_id")),
        )
        scheduled.append(activity)
        current_hour += duration_hours + 1  # 1-hour gap between activities

    return scheduled


def _select_transport(all_options: list[dict], budget_transport: float) -> dict | None:
    """Select best transport option across all modes within budget.

    Priority: cheapest affordable first, then shortest duration as tiebreaker.
    """
    if not all_options:
        return None
    affordable = [t for t in all_options if t.get("price", 0) <= budget_transport]
    if affordable:
        # Prefer shortest duration among affordable
        return min(affordable, key=lambda t: t.get("duration_minutes", 9999))
    # Return cheapest if none affordable
    return min(all_options, key=lambda t: t.get("price", float("inf")))


def _select_flight(flights: list[dict], budget_transport: float) -> dict | None:
    """Select best flight within transport budget (backward compat)."""
    return _select_transport(flights, budget_transport)


def _select_hotel(hotels: list[dict], budget_per_night: float) -> dict | None:
    """Select best hotel within nightly budget."""
    if not hotels:
        return None
    affordable = [h for h in hotels if h.get("price_per_night", 0) <= budget_per_night]
    if affordable:
        # Prefer highest rating among affordable
        return max(affordable, key=lambda h: h.get("rating", 0))
    return min(hotels, key=lambda h: h.get("price_per_night", float("inf")))


def _distribute_activities(activities: list[dict], num_days: int) -> list[list[dict]]:
    """Distribute activities across days, grouping by category proximity."""
    if not activities:
        return [[] for _ in range(num_days)]

    # Simple round-robin distribution
    days: list[list[dict]] = [[] for _ in range(num_days)]
    max_per_day = 3

    for i, act in enumerate(activities):
        day_idx = i % num_days
        if len(days[day_idx]) < max_per_day:
            days[day_idx].append(act)
        else:
            # Find day with least activities
            min_day = min(range(num_days), key=lambda d: len(days[d]))
            if len(days[min_day]) < max_per_day:
                days[min_day].append(act)

    return days


# Typical entry-fee ranges per category (INR). Used when API returns price=0.
_CATEGORY_COST_ESTIMATE: dict[str, tuple[float, float]] = {
    "spiritual": (0, 100),
    "cultural": (100, 500),
    "adventure": (500, 2000),
    "nature": (50, 300),
    "food": (200, 800),
    "shopping": (0, 0),
    "general": (100, 500),
}


def _estimate_activity_costs(
    activities: list[dict],
    budget_for_activities: float,
    currency: str = "INR",
) -> list[dict]:
    """Fill in missing activity prices using category heuristics and budget distribution.

    Strategy:
      1. Assign each zero-priced activity an estimated cost based on category.
      2. Scale all estimates so the total fits inside `budget_for_activities`.
    """
    if not activities:
        return activities

    # Exchange-rate multiplier for non-INR currencies (rough)
    fx = {"INR": 1, "USD": 0.012, "EUR": 0.011, "GBP": 0.0095, "AUD": 0.018}.get(currency, 1)

    enriched: list[dict] = []
    for act in activities:
        a = dict(act)  # shallow copy
        price = a.get("price", 0) or a.get("cost", 0) or 0
        if price <= 0:
            cat = a.get("category", "general")
            lo, hi = _CATEGORY_COST_ESTIMATE.get(cat, (100, 500))
            # Midpoint estimate, scaled for currency
            midpoint = (lo + hi) / 2
            price = round(midpoint * fx, 2) if fx < 1 else midpoint
        a["price"] = price
        enriched.append(a)

    # Scale so total ≤ budget (if budget > 0)
    raw_total = sum(a["price"] for a in enriched)
    if raw_total > 0 and budget_for_activities > 0 and raw_total != budget_for_activities:
        scale = budget_for_activities / raw_total
        # Only scale down, don't inflate beyond 1.5×
        if scale < 1.0 or scale > 1.5:
            scale = min(scale, 1.5)
        for a in enriched:
            a["price"] = round(a["price"] * scale, 2)

    return enriched


def _build_itinerary_heuristic(
    request: TripRequest,
    research: dict,
    budget_alloc: dict[str, float],
) -> tuple[Itinerary, BudgetBreakdown]:
    """Build a complete itinerary from research data using heuristics."""
    num_days = request.duration_days
    nights = max(num_days - 1, 1)
    currency = request.currency

    flights = research.get("flights", [])
    trains = research.get("trains", [])
    buses = research.get("buses", [])
    hotels = research.get("hotels", [])
    activities = research.get("activities", [])
    weather = research.get("weather", {})

    # Normalize to dicts if they're Pydantic models
    if flights and hasattr(flights[0], "model_dump"):
        flights = [f.model_dump() for f in flights]
    if trains and hasattr(trains[0], "model_dump"):
        trains = [t.model_dump() for t in trains]
    if buses and hasattr(buses[0], "model_dump"):
        buses = [b.model_dump() for b in buses]
    if hotels and hasattr(hotels[0], "model_dump"):
        hotels = [h.model_dump() for h in hotels]
    if activities and hasattr(activities[0], "model_dump"):
        activities = [a.model_dump() for a in activities]

    # Estimate activity costs (Google Places doesn't return prices)
    activities = _estimate_activity_costs(activities, budget_alloc["activities"], currency)

    # Traveler count — costs for flights/food scale per person
    traveler_count = max(getattr(request, 'traveler_count', 1), 1)

    # Combine all transport options and select best
    all_transport = flights + trains + buses
    selected_transport = _select_transport(all_transport, budget_alloc["transport"] / traveler_count)

    # Keep backward compat: selected_flight holds the chosen transport regardless of mode
    selected_flight = selected_transport
    selected_hotel = _select_hotel(hotels, budget_alloc["accommodation"] / nights)

    # Compute actual costs — transport is per-person, hotels are per-room
    transport_cost_pp = selected_transport.get("price", 0) if selected_transport else 0
    transport_cost = transport_cost_pp * traveler_count
    hotel_cost = (selected_hotel.get("price_per_night", 0) * nights) if selected_hotel else 0

    # Also keep references to best option per mode for alternatives display
    alt_flights = _select_transport(flights, budget_alloc["transport"] / traveler_count) if flights else None
    alt_trains = _select_transport(trains, budget_alloc["transport"] / traveler_count) if trains else None
    alt_buses = _select_transport(buses, budget_alloc["transport"] / traveler_count) if buses else None

    # Distribute activities
    day_activities = _distribute_activities(activities, num_days)

    # Build day plans
    day_plans: list[DayPlan] = []
    total_activity_cost = 0.0

    for day_idx in range(num_days):
        day_num = day_idx + 1
        day_acts = _build_time_slots(day_idx, day_activities[day_idx])
        day_cost = sum(a.cost for a in day_acts)
        total_activity_cost += day_cost

        # Weather info for this day
        day_weather_str = ""
        if weather and isinstance(weather, dict):
            daily_weather = weather.get("data", {})
            if isinstance(daily_weather, dict):
                day_keys = sorted(daily_weather.keys())
                if day_idx < len(day_keys):
                    w = daily_weather[day_keys[day_idx]]
                    desc = w.get("description", "")
                    temp_min = w.get("temp_min", "")
                    temp_max = w.get("temp_max", "")
                    rain = w.get("rain_prob", 0)
                    day_weather_str = f"{desc.capitalize()}, {temp_min:.0f}–{temp_max:.0f}°C"
                    if rain and rain > 20:
                        day_weather_str += f", {rain:.0f}% rain"

        day_plan = DayPlan(
            day_number=day_num,
            title=f"Day {day_num}",
            activities=day_acts,
            meals=[
                MealSuggestion(meal_type="breakfast", name="Local breakfast", cost_estimate=round(budget_alloc["food"] / num_days / 3, 2)),
                MealSuggestion(meal_type="lunch", name="Local restaurant", cost_estimate=round(budget_alloc["food"] / num_days / 3, 2)),
                MealSuggestion(meal_type="dinner", name="Local dinner", cost_estimate=round(budget_alloc["food"] / num_days / 3, 2)),
            ],
            day_cost=day_cost,
            weather_summary=day_weather_str,
        )
        day_plans.append(day_plan)

    # Build transport legs — outbound + return
    transport_legs: list[TransportLeg] = []
    transport_mode = selected_transport.get("mode", "flight") if selected_transport else "flight"
    if selected_transport:
        transport_legs.append(TransportLeg(
            mode=transport_mode,
            from_location=request.origin,
            to_location=request.destination,
            cost=transport_cost,
            currency=currency,
            booking_url=selected_transport.get("booking_url"),
            notes=f"{selected_transport.get('airline_or_operator', '')} {selected_transport.get('departure_time', '')} → {selected_transport.get('arrival_time', '')}".strip(),
            duration_minutes=selected_transport.get("duration_minutes", 0),
        ))
        # Return leg (same mode, same price)
        transport_legs.append(TransportLeg(
            mode=transport_mode,
            from_location=request.destination,
            to_location=request.origin,
            cost=transport_cost,
            currency=currency,
            booking_url=selected_transport.get("booking_url"),
            notes=f"Return {transport_mode}",
            duration_minutes=selected_transport.get("duration_minutes", 0),
        ))

    # Attach transport to first & last day plans
    if transport_legs and day_plans:
        day_plans[0].transport = [transport_legs[0]]
        if len(day_plans) > 1:
            day_plans[-1].transport = [transport_legs[1]]

    food_cost = budget_alloc["food"]
    buffer = budget_alloc["buffer"]

    budget = BudgetBreakdown(
        transport=transport_cost,
        accommodation=hotel_cost,
        food=food_cost,
        activities=total_activity_cost,
        buffer=buffer,
        currency=currency,
        traveler_count=traveler_count,
    )

    # Build transport alternatives dict for display
    transport_alternatives = {}
    if alt_flights and alt_flights != selected_transport:
        transport_alternatives["flight"] = alt_flights
    if alt_trains and alt_trains != selected_transport:
        transport_alternatives["train"] = alt_trains
    if alt_buses and alt_buses != selected_transport:
        transport_alternatives["bus"] = alt_buses

    itinerary = Itinerary(
        destination=request.destination,
        duration_days=num_days,
        days=day_plans,
        total_cost=budget.total,
        currency=currency,
        selected_flight=selected_transport,
        selected_hotel=selected_hotel,
        transport=transport_legs,
        transport_alternatives=transport_alternatives,
    )

    return itinerary, budget


async def _generate_plan_narratives(
    request: TripRequest,
    itinerary: Itinerary,
    budget: BudgetBreakdown,
    style_key: str = "default",
) -> list[PlanOption]:
    """Use LLM to generate plan option narratives."""
    llm = ChatOpenAI(
        model=settings.LLM_MODEL_NARRATION,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.7,
    )

    days_summary = []
    for day in itinerary.days:
        acts = ", ".join(a.name for a in day.activities)
        days_summary.append(f"Day {day.day_number}: {acts}")

    prompt = f"""You are a travel planner creating plan descriptions. Based on this itinerary:

Destination: {request.destination}
Duration: {request.duration_days} days
Budget: {budget.currency} {request.budget}
Style: {', '.join(s.value for s in (request.styles or []))}

Schedule:
{chr(10).join(days_summary)}

Total cost: {budget.currency} {budget.total}

Generate 2 plan options as a JSON array. Each option has:
- "title": catchy 3-5 word title
- "description": 2-3 sentence summary highlighting key experiences
- "highlights": array of 3-4 one-line highlights
- "total_cost": the estimated total cost

Option 1: The main plan as described above.
Option 2: A budget-conscious variation (suggest specific cheaper alternatives).

Return ONLY the JSON array. Anti-hallucination rule: Only reference places that appear in the schedule above. Do not invent new places."""

    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3].strip()
        options_data = json.loads(content)
        options = []
        for i, opt in enumerate(options_data):
            options.append(PlanOption(
                id=f"plan_{i+1}",
                label=opt.get("title", f"Plan {i+1}"),
                style=style_key,
                estimated_total=opt.get("total_cost", budget.total),
                currency=budget.currency,
                highlights=opt.get("highlights", []),
                trade_offs=opt.get("description", ""),
            ))
        return options
    except Exception as e:
        logger.error("Plan narrative generation failed: %s", e)
        return [PlanOption(
            id="plan_1",
            label="Recommended Plan",
            style=style_key,
            estimated_total=budget.total,
            currency=budget.currency,
            highlights=[f"{len(itinerary.days)} days planned", f"Total: {budget.currency} {budget.total}"],
            trade_offs=f"A {request.duration_days}-day trip to {request.destination}",
        )]


async def _generate_day_descriptions(itinerary: Itinerary) -> Itinerary:
    """Use LLM to add rich descriptions to each day and activity."""
    llm = ChatOpenAI(
        model=settings.LLM_MODEL_NARRATION,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.6,
    )

    for day in itinerary.days:
        acts_list = [{"name": a.name, "time": a.time_slot.start, "category": a.category} for a in day.activities]

        prompt = f"""Generate a brief, engaging title and a 1-sentence description for this travel day.

Day {day.day_number} activities: {json.dumps(acts_list, default=str)}

Return JSON: {{"title": "...", "description": "..."}}
Anti-hallucination rule: Only reference the activities listed above."""

        try:
            response = await llm.ainvoke(prompt)
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3].strip()
            data = json.loads(content)
            day.title = data.get("title", day.title)
            day.description = data.get("description")
        except Exception as e:
            logger.warning("Day description generation failed for day %d: %s", day.day_number, e)

    return itinerary


async def plan(state: TripState) -> TripState:
    """Generate itinerary from research data using heuristic scheduling + LLM narration."""
    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    # Clear replan_delta so the router won't re-trigger replan routing
    state.pop("replan_delta", None)

    research = state.get("research", {})
    state["status"] = TripStatus.PLANNING

    await sse_manager.emit_phase_update(trip_id, "planning", "starting", "Building your itinerary...")
    await sse_manager.emit_agent_step(trip_id, "planner", "Allocating budget", "Splitting budget across categories", "running")

    # Step 1: Heuristic budget allocation
    style_key = request.styles[0].value if request.styles else "default"
    budget_alloc = _allocate_budget(request.budget, style_key)

    await sse_manager.emit_agent_step(
        trip_id, "planner", "Scheduling activities",
        "Assigning activities to time slots",
        "running",
        [f"Budget split: {', '.join(f'{k} {v}' for k, v in budget_alloc.items())}"],
    )

    # Step 2: Build itinerary from research using heuristics
    await sse_manager.emit_phase_update(trip_id, "planning", "scheduling", "Scheduling activities...")
    itinerary, budget = _build_itinerary_heuristic(request, research, budget_alloc)

    # Step 3: LLM narration — generate day titles/descriptions
    await sse_manager.emit_agent_step(trip_id, "planner", "Writing descriptions", "Generating day-by-day narratives with AI", "running",
        ["Budget allocated", f"{len(itinerary.days)} days scheduled"])
    itinerary = await _generate_day_descriptions(itinerary)

    # Step 4: Generate plan options with narratives
    await sse_manager.emit_agent_step(trip_id, "planner", "Creating plan options", "Generating A/B/C plan variants", "running",
        ["Budget allocated", f"{len(itinerary.days)} days scheduled", "Day descriptions written"])
    plan_options = await _generate_plan_narratives(request, itinerary, budget, style_key)

    # Emit results
    await sse_manager.emit_budget_update(trip_id, budget.model_dump())
    await sse_manager.emit_plan_ready(trip_id, [o.model_dump() for o in plan_options])

    state["itinerary"] = itinerary.model_dump()
    state["budget_breakdown"] = budget.model_dump()
    state["plan_options"] = [o.model_dump() for o in plan_options]
    state["planning_complete"] = True

    await sse_manager.emit_agent_step(
        trip_id, "planner", "Planning complete",
        f"{len(plan_options)} plan options ready",
        "done",
        ["Budget allocated", f"{len(itinerary.days)} days scheduled", "Descriptions written", f"{len(plan_options)} options generated"],
    )
    await sse_manager.emit_phase_update(
        trip_id, "planning", "complete",
        f"Generated {len(plan_options)} plan options"
    )

    return state
