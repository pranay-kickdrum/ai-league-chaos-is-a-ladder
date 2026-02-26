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
from app.tools.activities import search_activities
from app.tools.flights import search_flights
from app.tools.flights_amadeus import search_flights_amadeus
from app.tools.ground_transport import search_trains, search_buses
from app.tools.hotels import search_hotels
from app.tools.iata import resolve_iata
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
    """Run parallel research across all sources."""
    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    # Clear replan_delta so the router won't re-trigger replan routing
    state["replan_delta"] = {}

    state["status"] = TripStatus.RESEARCHING

    await sse_manager.emit_phase_update(trip_id, "research", "starting", "Beginning research phase...")
    await sse_manager.emit_agent_step(trip_id, "researcher", "Analyzing your preferences", "Understanding travel style, budget & dates", "running")

    # Step 1: Generate search queries via LLM
    await sse_manager.emit_agent_thinking(trip_id, "researcher", "Generating search queries for your preferences...")
    queries = await _generate_search_queries(request)

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
            await sse_manager.emit_api_degraded(trip_id, "serpapi_flights", "amadeus")
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

    async def _fetch_advisory_task() -> dict:
        if is_international(request.origin, request.destination):
            await sse_manager.emit_phase_update(trip_id, "research", "advisory", "Checking travel advisories...")
            results = await get_travel_advisory(request.origin, request.destination)
            await sse_manager.emit_research_partial(trip_id, "advisory", results)
            return results
        return {"is_international": False}

    # Run all in parallel
    flight_task = asyncio.create_task(_search_flights_with_fallback())
    train_task = asyncio.create_task(_search_trains_task())
    bus_task = asyncio.create_task(_search_buses_task())
    hotel_task = asyncio.create_task(_search_hotels_task())
    activity_task = asyncio.create_task(_search_activities_task())
    weather_task = asyncio.create_task(_fetch_weather_task())
    advisory_task = asyncio.create_task(_fetch_advisory_task())

    # Gather results
    results = await asyncio.gather(
        flight_task, train_task, bus_task, hotel_task, activity_task, weather_task, advisory_task,
        return_exceptions=True,
    )

    # Helper: convert Pydantic models to dicts for clean JSON serialization
    def _to_dicts(items: list) -> list:
        return [item.model_dump() if hasattr(item, "model_dump") else item for item in items]

    # Process results
    if not isinstance(results[0], Exception):
        research_results["flights"] = _to_dicts(results[0])
    else:
        logger.error("Flight search failed: %s", results[0])

    if not isinstance(results[1], Exception):
        research_results["trains"] = _to_dicts(results[1])
    else:
        logger.error("Train search failed: %s", results[1])

    if not isinstance(results[2], Exception):
        research_results["buses"] = _to_dicts(results[2])
    else:
        logger.error("Bus search failed: %s", results[2])

    if not isinstance(results[3], Exception):
        research_results["hotels"] = _to_dicts(results[3])
    else:
        logger.error("Hotel search failed: %s", results[3])

    if not isinstance(results[4], Exception):
        research_results["activities"] = results[4]
    else:
        logger.error("Activity search failed: %s", results[4])

    if not isinstance(results[5], Exception):
        research_results["weather"] = results[5]
    else:
        logger.error("Weather fetch failed: %s", results[5])

    if not isinstance(results[6], Exception):
        research_results["travel_advisory"] = results[6]
    else:
        logger.error("Travel advisory failed: %s", results[6])

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
