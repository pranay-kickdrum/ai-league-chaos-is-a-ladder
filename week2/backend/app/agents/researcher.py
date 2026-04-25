"""Research Agent — LLM query generation + parallel tool orchestration."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.models.agent_state import ResearchResults, TripState
from app.models.trip import TripRequest, TripStatus
from app.services.sse_manager import sse_manager
from app.tools.activities import search_activities, enrich_activity_prices
from app.tools.flights import search_flights
from app.tools.flights_amadeus import search_flights_amadeus
from app.tools.ground_transport import search_trains, search_buses
from app.tools.hotels import search_hotels
from app.tools.iata import resolve_iata, airport_city_for
from app.tools.mock_data import generate_mock_flights, generate_mock_hotels
from app.tools.travel_advisory import get_travel_advisory, is_international
from app.tools.weather import get_weather

logger = logging.getLogger(__name__)
settings = get_settings()


async def _generate_search_queries(request: TripRequest) -> list[str]:
    """Use LLM to generate specific search queries from user preferences."""
    llm = ChatOpenAI(
        model=settings.LLM_MODEL_NARRATION,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.3,
    )
    styles = ", ".join(s.value for s in request.styles) if request.styles else "general"
    interests = ", ".join(request.interests) if request.interests else "sightseeing"

    prompt = f"""Generate 5-8 specific search queries to find activities and things to do for this trip:
- Destination: {request.destination}
- Travel styles: {styles}
- Interests: {interests}
- Duration: {request.duration_days} days
- Traveler type: {request.traveler_type.value}

Return ONLY a JSON array of search query strings. Example:
["white water rafting Rishikesh", "yoga ashram Rishikesh", "Ganga Aarti timings Rishikesh"]

Return ONLY the JSON array, no explanation."""

    try:
        response = await llm.ainvoke(prompt)
        import json
        import re as _re

        content = response.content.strip()
        # Strip optional markdown code fences (```json ... ``` or ``` ... ```)
        content = _re.sub(r"^```[a-z]*\n?", "", content)
        content = _re.sub(r"\n?```$", "", content)
        queries = json.loads(content.strip())
        if isinstance(queries, list):
            return queries[:8]
    except Exception as e:
        logger.error("Query generation failed: %s", e)

    # Fallback: generate basic queries from styles
    fallback = [f"{s.value} things to do in {request.destination}" for s in (request.styles or [])]
    fallback.append(f"top attractions {request.destination}")
    fallback.append(f"best restaurants {request.destination}")
    return fallback


async def research(state: TripState) -> TripState:
    """Run parallel research across all sources.

    Supports partial re-research: if replan_delta.re_research_categories is set,
    only re-search those categories and preserve existing data for the rest.
    Categories: "transport" (flights+trains+buses), "hotels", "activities", "weather", "all"
    """
    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    # Determine which categories to re-search
    replan_delta = state.get("replan_delta", {})
    re_categories = set(replan_delta.get("re_research_categories", [])) if isinstance(replan_delta, dict) else set()
    is_partial = bool(re_categories) and "all" not in re_categories
    existing_research = state.get("research", {}) if is_partial else {}

    # Preserve transport_preference for the planner (research clears replan_delta)
    transport_pref = replan_delta.get("transport_preference") if isinstance(replan_delta, dict) else None

    # Clear replan_delta so the router won't re-trigger replan routing,
    # but keep transport_preference so planner can use it
    state["replan_delta"] = {"transport_preference": transport_pref} if transport_pref else {}

    state["status"] = TripStatus.RESEARCHING

    if is_partial:
        cat_label = ", ".join(sorted(re_categories))
        await sse_manager.emit_phase_update(trip_id, "research", "starting", f"Re-searching {cat_label}...")
        await sse_manager.emit_agent_step(trip_id, "researcher", "Partial re-search", f"Updating {cat_label} only", "running")
    else:
        await sse_manager.emit_phase_update(trip_id, "research", "starting", "Beginning research phase...")
        await sse_manager.emit_agent_step(trip_id, "researcher", "Analyzing your preferences", "Understanding travel style, budget & dates", "running")

    # Step 1: Generate search queries via LLM (only needed for activities)
    need_activities = not is_partial or "activities" in re_categories
    if need_activities:
        await sse_manager.emit_agent_thinking(trip_id, "researcher", "Generating search queries for your preferences...")
        queries = await _generate_search_queries(request)
    else:
        queries = existing_research.get("search_queries", [])

    if not is_partial:
        await sse_manager.emit_agent_step(
            trip_id, "researcher", "Searching travel options",
            f"Running {len(queries)} search queries in parallel",
        "running",
        [f"Generated {len(queries)} search queries"],
    )

    # Step 2: Parallel execution of all research tasks
    # Default to 7 days from today if no start date was provided
    default_start = date.today() + timedelta(days=7)
    departure = str(request.start_date) if request.start_date else str(default_start)
    nights = max(request.duration_days - 1, 1)
    if request.end_date:
        return_date = str(request.end_date)
    elif request.start_date:
        return_date = str(request.start_date + timedelta(days=nights))
    else:
        return_date = str(default_start + timedelta(days=nights))
    check_out = return_date

    # Resolve city names to IATA airport codes for flight APIs
    origin_iata = resolve_iata(request.origin)
    destination_iata = resolve_iata(request.destination)

    # Detect if destination airport is in a different city (e.g. Munnar → COK in Kochi)
    dest_airport_city = airport_city_for(request.destination)
    if dest_airport_city:
        logger.info("Airport city for %s is %s — will search connecting transport",
                     request.destination, dest_airport_city)

    research_results: ResearchResults = {
        "flights": [],
        "trains": [],
        "buses": [],
        "hotels": [],
        "activities": [],
        "weather": {},
        "routes": {},
        "travel_advisory": {},
        "search_queries": queries,
        "airport_transfers": [],
        "airport_city": dest_airport_city or "",
    }

    # Launch all tasks in parallel
    tasks: dict[str, asyncio.Task] = {}

    async def _search_flights_with_fallback() -> list:
        """Flights with SerpAPI → Amadeus → mock fallback."""
        await sse_manager.emit_agent_step(trip_id, "researcher", "Searching flights", f"{request.origin} → {request.destination}", "running")
        await sse_manager.emit_phase_update(trip_id, "research", "flights", "Searching flights...")
        results = await search_flights(
            origin_iata, destination_iata, departure, return_date, request.currency
        )
        if not results:
            await sse_manager.emit_api_degraded(trip_id, "serpapi_flights", "amadeus",
                                                f"no flights found for {origin_iata}→{destination_iata}")
            results = await search_flights_amadeus(
                origin_iata, destination_iata, departure,
                request.traveler_count, request.currency,
            )
        if not results:
            logger.warning("All flight APIs returned empty; using mock data")
            results = generate_mock_flights(origin_iata, destination_iata, departure, request.currency)
        await sse_manager.emit_research_partial(trip_id, "flights", [f.model_dump() for f in results])
        return results

    async def _search_hotels_task() -> list:
        await sse_manager.emit_agent_step(trip_id, "researcher", "Searching hotels", f"Finding stays in {request.destination}", "running")
        await sse_manager.emit_phase_update(trip_id, "research", "hotels", "Searching hotels...")
        results = await search_hotels(
            request.destination, departure, check_out, nights, request.currency
        )
        if not results:
            logger.warning("All hotel APIs returned empty; using mock data")
            results = generate_mock_hotels(request.destination, departure, nights, request.currency)
        await sse_manager.emit_research_partial(trip_id, "hotels", [h.model_dump() for h in results])
        return results

    async def _search_activities_task() -> list:
        await sse_manager.emit_agent_step(trip_id, "researcher", "Searching activities", f"Discovering things to do in {request.destination}", "running")
        await sse_manager.emit_phase_update(trip_id, "research", "activities", "Searching activities...")
        results = await search_activities(request.destination, queries, request.currency)
        # Enrich with realistic prices via LLM
        if results:
            await sse_manager.emit_agent_thinking(trip_id, "researcher", "Estimating activity prices...")
            results = await enrich_activity_prices(results, request.destination, request.currency)
        await sse_manager.emit_research_partial(trip_id, "activities", [a.model_dump() for a in results])
        return results

    async def _fetch_weather_task() -> dict:
        await sse_manager.emit_agent_step(trip_id, "researcher", "Checking weather", f"Forecast for {request.destination}", "running")
        await sse_manager.emit_phase_update(trip_id, "research", "weather", "Checking weather...")
        results = await get_weather(request.destination, departure)
        await sse_manager.emit_research_partial(trip_id, "weather", results)
        return results

    async def _search_trains_task() -> list:
        await sse_manager.emit_agent_step(trip_id, "researcher", "Searching trains", f"{request.origin} → {request.destination}", "running")
        await sse_manager.emit_phase_update(trip_id, "research", "trains", "Searching train options...")
        results = await search_trains(request.origin, request.destination, departure, request.currency)
        if results:
            await sse_manager.emit_research_partial(trip_id, "trains", [t.model_dump() for t in results])
        return results

    async def _search_buses_task() -> list:
        await sse_manager.emit_agent_step(trip_id, "researcher", "Searching buses", f"{request.origin} → {request.destination}", "running")
        await sse_manager.emit_phase_update(trip_id, "research", "buses", "Searching bus options...")
        results = await search_buses(request.origin, request.destination, departure, request.currency)
        if results:
            await sse_manager.emit_research_partial(trip_id, "buses", [b.model_dump() for b in results])
        return results

    async def _search_airport_transfers_task() -> list:
        """Search train/bus options from airport city to destination (last mile)."""
        if not dest_airport_city:
            return []
        await sse_manager.emit_agent_step(
            trip_id, "researcher", "Searching airport transfers",
            f"{dest_airport_city} → {request.destination}", "running",
        )
        trains = await search_trains(dest_airport_city, request.destination, departure, request.currency)
        buses = await search_buses(dest_airport_city, request.destination, departure, request.currency)
        results = trains + buses
        if results:
            await sse_manager.emit_research_partial(
                trip_id, "airport_transfers",
                [t.model_dump() for t in results],
            )
        logger.info("Airport transfers %s → %s: %d options",
                     dest_airport_city, request.destination, len(results))
        return results

    async def _fetch_advisory_task() -> dict:
        if is_international(request.origin, request.destination):
            await sse_manager.emit_phase_update(trip_id, "research", "advisory", "Checking travel advisories...")
            results = await get_travel_advisory(request.origin, request.destination)
            await sse_manager.emit_research_partial(trip_id, "advisory", results)
            return results
        return {"is_international": False}

    # Determine which categories to search
    need_transport = not is_partial or "transport" in re_categories
    need_hotels = not is_partial or "hotels" in re_categories
    need_weather = not is_partial or "weather" in re_categories

    # Helper: convert Pydantic models to dicts for clean JSON serialization
    def _to_dicts(items: list) -> list:
        return [item.model_dump() if hasattr(item, "model_dump") else item for item in items]

    # Run needed tasks in parallel
    pending_tasks: dict[str, asyncio.Task] = {}

    if need_transport:
        pending_tasks["flights"] = asyncio.create_task(_search_flights_with_fallback())
        pending_tasks["trains"] = asyncio.create_task(_search_trains_task())
        pending_tasks["buses"] = asyncio.create_task(_search_buses_task())
        if dest_airport_city:
            pending_tasks["airport_transfers"] = asyncio.create_task(_search_airport_transfers_task())
    if need_hotels:
        pending_tasks["hotels"] = asyncio.create_task(_search_hotels_task())
    if need_activities:
        pending_tasks["activities"] = asyncio.create_task(_search_activities_task())
    if need_weather:
        pending_tasks["weather"] = asyncio.create_task(_fetch_weather_task())
    if not is_partial:
        pending_tasks["advisory"] = asyncio.create_task(_fetch_advisory_task())

    # Gather results
    task_keys = list(pending_tasks.keys())
    task_results = await asyncio.gather(*pending_tasks.values(), return_exceptions=True)
    gathered = dict(zip(task_keys, task_results))

    # Start with existing research (for partial) or fresh empty results
    research_results: ResearchResults = {
        "flights": existing_research.get("flights", []),
        "trains": existing_research.get("trains", []),
        "buses": existing_research.get("buses", []),
        "hotels": existing_research.get("hotels", []),
        "activities": existing_research.get("activities", []),
        "weather": existing_research.get("weather", {}),
        "routes": existing_research.get("routes", {}),
        "travel_advisory": existing_research.get("travel_advisory", {}),
        "search_queries": queries,
        "airport_transfers": existing_research.get("airport_transfers", []),
        "airport_city": dest_airport_city or existing_research.get("airport_city", ""),
    }

    # Process gathered results
    for key, result in gathered.items():
        if isinstance(result, Exception):
            logger.error("%s search failed: %s", key, result)
            continue
        if key in ("flights", "trains", "buses", "hotels", "activities", "airport_transfers"):
            research_results[key] = _to_dicts(result)
        elif key in ("weather", "advisory"):
            target_key = "travel_advisory" if key == "advisory" else key
            research_results[target_key] = result

    state["research"] = research_results
    state["research_complete"] = True

    n_flights = len(research_results.get('flights', []))
    n_trains = len(research_results.get('trains', []))
    n_buses = len(research_results.get('buses', []))
    n_hotels = len(research_results.get('hotels', []))
    n_activities = len(research_results.get('activities', []))
    transport_parts = []
    if n_flights:
        transport_parts.append(f"{n_flights} flights")
    if n_trains:
        transport_parts.append(f"{n_trains} trains")
    if n_buses:
        transport_parts.append(f"{n_buses} buses")
    transport_summary = ", ".join(transport_parts) or "0 transport options"
    await sse_manager.emit_agent_step(
        trip_id, "researcher", "Research complete",
        f"Found {transport_summary}, {n_hotels} hotels, {n_activities} activities",
        "done",
        [transport_summary, f"{n_hotels} hotels", f"{n_activities} activities"],
    )
    await sse_manager.emit_phase_update(
        trip_id, "research", "complete",
        f"Found {transport_summary}, {n_hotels} hotels, {n_activities} activities"
    )

    return state
