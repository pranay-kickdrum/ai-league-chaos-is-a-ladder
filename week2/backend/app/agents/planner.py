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


GROUND_DURATION_THRESHOLD_MINUTES = 720  # 12 hours — prefer flights over trains/buses longer than this


def _select_transport(all_options: list[dict], budget_transport: float) -> dict | None:
    """Select best transport option across all modes within budget.

    Rules:
      1. If a train or bus journey exceeds ~12 hours, prefer flights instead.
      2. Among remaining options: cheapest affordable first, then shortest duration
         as tiebreaker.
    """
    if not all_options:
        return None

    # Separate flights from ground transport
    flights = [t for t in all_options if t.get("mode") not in ("train", "bus")]
    ground = [t for t in all_options if t.get("mode") in ("train", "bus")]

    # Keep only ground options shorter than the threshold
    short_ground = [
        t for t in ground
        if t.get("duration_minutes", 9999) <= GROUND_DURATION_THRESHOLD_MINUTES
    ]
    long_ground = [
        t for t in ground
        if t.get("duration_minutes", 9999) > GROUND_DURATION_THRESHOLD_MINUTES
    ]
    if long_ground:
        logger.info(
            "Excluding %d ground-transport option(s) exceeding %d min: %s",
            len(long_ground),
            GROUND_DURATION_THRESHOLD_MINUTES,
            [(t.get("mode"), t.get("airline_or_operator"), t.get("duration_minutes")) for t in long_ground],
        )

    # Preferred pool: flights + short ground trips
    preferred = flights + short_ground

    affordable = [t for t in preferred if t.get("price", 0) <= budget_transport]
    if affordable:
        return min(affordable, key=lambda t: t.get("duration_minutes", 9999))

    # Nothing affordable in preferred pool — try all preferred regardless of budget
    if preferred:
        return min(preferred, key=lambda t: t.get("price", float("inf")))

    # Fallback: even long ground options are better than nothing
    return min(all_options, key=lambda t: t.get("price", float("inf")))


def _select_flight(flights: list[dict], budget_transport: float) -> dict | None:
    """Select best flight within transport budget (backward compat)."""
    return _select_transport(flights, budget_transport)


def _select_hotel(hotels: list[dict], budget_per_night: float) -> dict | None:
    """Select best hotel within nightly budget."""
    # Filter out hotels with no price data (price_per_night <= 0)
    priced = [h for h in hotels if h.get("price_per_night", 0) > 0]
    if not priced:
        return None
    affordable = [h for h in priced if h.get("price_per_night", 0) <= budget_per_night]
    if affordable:
        # Prefer highest rating among affordable
        return max(affordable, key=lambda h: h.get("rating", 0))
    return min(priced, key=lambda h: h.get("price_per_night", float("inf")))


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
    """Fill in missing activity prices using heuristics. Keeps LLM-estimated prices intact.

    Strategy:
      1. If an activity already has a price > 0 (e.g. from LLM enrichment), keep it.
      2. For zero-priced activities, estimate using category + price_level + rating
         to produce varied, realistic costs.
      3. Scale only the estimated prices if the total exceeds the budget.
    """
    if not activities:
        return activities

    # Exchange-rate multiplier for non-INR currencies (rough)
    fx = {"INR": 1, "USD": 0.012, "EUR": 0.011, "GBP": 0.0095, "AUD": 0.018}.get(currency, 1)

    enriched: list[dict] = []
    for act in activities:
        # Guard: skip non-dict items (e.g. strings from bad serialization)
        if isinstance(act, str):
            try:
                act = json.loads(act)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Skipping non-dict activity: %s", act[:80] if len(act) > 80 else act)
                continue
        if not isinstance(act, dict):
            continue
        a = dict(act)  # shallow copy
        price = a.get("price", 0) or a.get("cost", 0) or 0

        if price <= 0:
            # Use price_level (0-4) + rating + category for varied estimation
            cat = a.get("category", "general")
            lo, hi = _CATEGORY_COST_ESTIMATE.get(cat, (100, 500))

            price_level = a.get("price_level")  # 0-4 or None
            rating = a.get("rating", 0) or 0

            if price_level is not None and price_level >= 0:
                # Interpolate within range using price_level (0→lo, 4→hi)
                fraction = price_level / 4.0
            else:
                # Use rating as a proxy (0→lo, 5→hi)
                fraction = min(rating / 5.0, 1.0) if rating > 0 else 0.4

            # Name-based hash for deterministic variation within the range
            name_hash = sum(ord(c) for c in a.get("name", "")) % 100
            jitter = (name_hash - 50) / 100.0  # −0.5 to +0.49

            base_price = lo + (hi - lo) * fraction
            # Apply ±20% jitter for uniqueness
            base_price *= (1.0 + jitter * 0.4)
            base_price = max(base_price, lo)  # don't go below range floor

            price = round(base_price * fx, 0) if fx < 1 else round(base_price, 0)

        a["price"] = price
        enriched.append(a)

    # Scale only to keep total within budget, but don't flatten prices
    raw_total = sum(a["price"] for a in enriched)
    if raw_total > 0 and budget_for_activities > 0 and raw_total > budget_for_activities:
        scale = budget_for_activities / raw_total
        for a in enriched:
            a["price"] = round(a["price"] * scale, 2)

    return enriched


def _build_itinerary_heuristic(
    request: TripRequest,
    research: dict,
    budget_alloc: dict[str, float],
    transport_preference: str | None = None,
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

    logger.debug("Planner research: keys=%s, flights=%d, trains=%d, buses=%d, hotels=%d, activities=%d",
                 list(research.keys()), len(flights), len(trains), len(buses), len(hotels), len(activities))

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

    # Traveler count — costs for flights/food scale per person
    traveler_count = max(getattr(request, 'traveler_count', 1), 1)

    # Estimate activity costs (Google Places doesn't return prices)
    # budget_for_activities is for the whole group; activity prices are per-person
    # so pass per-person budget to the estimator for proper scaling
    activities = _estimate_activity_costs(activities, budget_alloc["activities"] / traveler_count, currency)

    # Combine all transport options and select best
    all_transport = flights + trains + buses
    logger.debug("Planner transport: count=%d, budget=%s, travelers=%d, preference=%s",
                 len(all_transport), budget_alloc["transport"], traveler_count, transport_preference)

    # Normalize transport preference: LLM may return "flights" instead of "flight"
    if transport_preference:
        _tp_aliases = {
            "flights": "flight", "air": "flight", "plane": "flight",
            "trains": "train", "rail": "train", "railway": "train",
            "buses": "bus", "coach": "bus",
        }
        transport_preference = _tp_aliases.get(transport_preference.lower(), transport_preference.lower())

    # If user has a transport preference, filter to that mode first
    if transport_preference:
        preferred_options = [t for t in all_transport if t.get("mode") == transport_preference]
        if preferred_options:
            selected_transport = _select_transport(preferred_options, budget_alloc["transport"] / traveler_count)
            logger.info("Using preferred %s transport: %s", transport_preference,
                       selected_transport.get("airline_or_operator") if selected_transport else "none")
        else:
            logger.warning("No %s options found, falling back to all transport", transport_preference)
            selected_transport = _select_transport(all_transport, budget_alloc["transport"] / traveler_count)
    else:
        selected_transport = _select_transport(all_transport, budget_alloc["transport"] / traveler_count)

    # Keep backward compat: selected_flight holds the chosen transport regardless of mode
    selected_flight = selected_transport
    selected_hotel = _select_hotel(hotels, budget_alloc["accommodation"] / nights)

    # Compute actual costs — transport is per-person, hotels are per-room
    transport_cost_pp = selected_transport.get("price", 0) if selected_transport else 0
    transport_cost = transport_cost_pp * traveler_count
    hotel_cost = (selected_hotel.get("price_per_night", 0) * nights) if selected_hotel else 0

    # Airport transfer: if flight selected and airport is in a different city,
    # pick the best connecting transport (train/bus) from airport city to destination
    airport_transfers = research.get("airport_transfers", [])
    airport_city = research.get("airport_city", "")
    selected_airport_transfer = None
    airport_transfer_cost = 0.0
    if airport_transfers and hasattr(airport_transfers[0], "model_dump"):
        airport_transfers = [t.model_dump() for t in airport_transfers]

    if airport_city and airport_transfers and selected_transport and selected_transport.get("mode") == "flight":
        # Select cheapest transfer option
        priced_transfers = [t for t in airport_transfers if t.get("price", 0) > 0]
        if priced_transfers:
            selected_airport_transfer = min(priced_transfers, key=lambda t: t.get("price", float("inf")))
            # Transfer price is round-trip per person already (ground_transport doubles)
            airport_transfer_cost = selected_airport_transfer.get("price", 0) * traveler_count
            transport_cost += airport_transfer_cost
            logger.info("Airport transfer %s → %s: %s %s (₹%s pp)",
                        airport_city, request.destination,
                        selected_airport_transfer.get("mode"),
                        selected_airport_transfer.get("airline_or_operator", ""),
                        selected_airport_transfer.get("price", 0))

    logger.debug("Planner selection: transport=%s cost=%s, hotel=%s cost=%s, airport_transfer=%s",
                 selected_transport.get("mode") if selected_transport else None, transport_cost,
                 selected_hotel.get("name") if selected_hotel else None, hotel_cost,
                 f"{airport_city}→{request.destination}" if selected_airport_transfer else "none")

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
        # Outbound main leg
        transport_legs.append(TransportLeg(
            mode=transport_mode,
            from_location=request.origin,
            to_location=airport_city if selected_airport_transfer else request.destination,
            cost=transport_cost_pp * traveler_count,
            currency=currency,
            booking_url=selected_transport.get("booking_url"),
            notes=f"{selected_transport.get('airline_or_operator', '')} {selected_transport.get('departure_time', '')} → {selected_transport.get('arrival_time', '')}".strip(),
            duration_minutes=selected_transport.get("duration_minutes", 0),
        ))
        # Outbound airport transfer (if needed)
        if selected_airport_transfer:
            transfer_mode = selected_airport_transfer.get("mode", "bus")
            transfer_pp = selected_airport_transfer.get("price", 0)
            transport_legs.append(TransportLeg(
                mode=transfer_mode,
                from_location=airport_city,
                to_location=request.destination,
                cost=transfer_pp * traveler_count / 2,  # price is round-trip, halve for one-way
                currency=currency,
                booking_url=selected_airport_transfer.get("booking_url"),
                notes=f"{selected_airport_transfer.get('airline_or_operator', '')} — Airport transfer".strip(),
                duration_minutes=selected_airport_transfer.get("duration_minutes", 0),
            ))
        # Return airport transfer (if needed)
        if selected_airport_transfer:
            transport_legs.append(TransportLeg(
                mode=transfer_mode,
                from_location=request.destination,
                to_location=airport_city,
                cost=transfer_pp * traveler_count / 2,
                currency=currency,
                booking_url=selected_airport_transfer.get("booking_url"),
                notes=f"Return transfer to {airport_city} airport",
                duration_minutes=selected_airport_transfer.get("duration_minutes", 0),
            ))
        # Return main leg
        transport_legs.append(TransportLeg(
            mode=transport_mode,
            from_location=airport_city if selected_airport_transfer else request.destination,
            to_location=request.origin,
            cost=transport_cost_pp * traveler_count,
            currency=currency,
            booking_url=selected_transport.get("booking_url"),
            notes=f"Return {transport_mode}",
            duration_minutes=selected_transport.get("duration_minutes", 0),
        ))

    # Attach transport to first & last day plans
    if transport_legs and day_plans:
        if selected_airport_transfer:
            # Legs: [flight_out, transfer_out, transfer_return, flight_return]
            day_plans[0].transport = transport_legs[:2]
            if len(day_plans) > 1:
                day_plans[-1].transport = transport_legs[2:]
        else:
            # Legs: [outbound, return]
            day_plans[0].transport = [transport_legs[0]]
            if len(day_plans) > 1 and len(transport_legs) > 1:
                day_plans[-1].transport = [transport_legs[1]]

    food_cost = budget_alloc["food"]
    buffer = budget_alloc["buffer"]

    # Activity costs in day plans are per-person; total for group = pp × travelers
    total_activity_cost_group = total_activity_cost * traveler_count

    budget = BudgetBreakdown(
        transport=transport_cost,
        accommodation=hotel_cost,
        food=food_cost,
        activities=total_activity_cost_group,
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
        selected_airport_transfer=selected_airport_transfer,
        airport_city=airport_city,
        transport=transport_legs,
        transport_alternatives=transport_alternatives,
    )

    return itinerary, budget


def _transport_name_with_stops(transport: dict | None) -> str | None:
    """Build a transport name label with stops info for flights."""
    if not transport:
        return None
    name = transport.get("airline_or_operator") or transport.get("class_type") or ""
    if not name:
        return None
    if transport.get("mode") == "flight":
        stops = transport.get("stops", 0)
        stops_label = "Non-stop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
        return f"{name} ({stops_label})"
    return name


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
        # Extract transport/hotel info from itinerary
        sel_transport = itinerary.selected_flight or {}
        sel_hotel = itinerary.selected_hotel or {}
        sel_transfer = itinerary.selected_airport_transfer or {}
        transport_mode = sel_transport.get("mode", "flight") if sel_transport else None
        transport_name = _transport_name_with_stops(sel_transport)
        hotel_name = sel_hotel.get("name") if sel_hotel else None
        airport_transfer_str = None
        if sel_transfer and itinerary.airport_city:
            transfer_mode = sel_transfer.get("mode", "bus").title()
            transfer_op = sel_transfer.get("airline_or_operator", "")
            airport_transfer_str = f"{transfer_mode} from {itinerary.airport_city} → {itinerary.destination}"
            if transfer_op:
                airport_transfer_str = f"{transfer_op} ({transfer_mode}) — {itinerary.airport_city} → {itinerary.destination}"

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
                transport_mode=transport_mode,
                transport_name=transport_name,
                hotel_name=hotel_name,
                airport_transfer=airport_transfer_str,
            ))
        return options
    except Exception as e:
        logger.error("Plan narrative generation failed: %s", e)
        sel_transport = itinerary.selected_flight or {}
        sel_hotel = itinerary.selected_hotel or {}
        sel_transfer = itinerary.selected_airport_transfer or {}
        airport_transfer_str = None
        if sel_transfer and itinerary.airport_city:
            airport_transfer_str = f"{sel_transfer.get('mode', 'bus').title()} from {itinerary.airport_city} → {itinerary.destination}"
        return [PlanOption(
            id="plan_1",
            label="Recommended Plan",
            style=style_key,
            estimated_total=budget.total,
            currency=budget.currency,
            highlights=[f"{len(itinerary.days)} days planned", f"Total: {budget.currency} {budget.total}"],
            trade_offs=f"A {request.duration_days}-day trip to {request.destination}",
            transport_mode=sel_transport.get("mode", "flight") if sel_transport else None,
            transport_name=_transport_name_with_stops(sel_transport),
            hotel_name=sel_hotel.get("name") if sel_hotel else None,
            airport_transfer=airport_transfer_str,
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

    # Clear replan_delta after reading transport_preference
    replan_delta = state.get("replan_delta", {})
    transport_preference = replan_delta.get("transport_preference") if isinstance(replan_delta, dict) else None
    state["replan_delta"] = {}

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
    itinerary, budget = _build_itinerary_heuristic(request, research, budget_alloc, transport_preference)

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
