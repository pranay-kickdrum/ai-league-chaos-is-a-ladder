"""Re-planning Agent — LLM interprets change requests + heuristic delta computation."""

from __future__ import annotations

import json
import logging

from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.models.agent_state import TripState
from app.models.trip import TripRequest, TripStatus
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)
settings = get_settings()


async def _interpret_change_request(change_text: str, itinerary: dict) -> dict:
    """Use GPT-4o to interpret what the user wants to change."""
    llm = ChatOpenAI(
        model=settings.LLM_MODEL_REASONING,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.2,
    )

    days_summary = []
    for day in itinerary.get("days", []):
        acts = ", ".join(a.get("name", "") for a in day.get("activities", []))
        days_summary.append(f"Day {day.get('day_number')}: {acts}")

    prompt = f"""Analyze this traveler's change request and determine what needs to be modified in their itinerary.

Current itinerary:
{chr(10).join(days_summary)}

Selected hotel: {itinerary.get('selected_hotel', {}).get('name', 'N/A')}
Selected flight: {itinerary.get('selected_flight', {}).get('airline', 'N/A')}

Change request: "{change_text}"

Return a JSON object with:
{{
  "affected_days": [1, 2],       // which day numbers need changes (empty = all)
  "change_type": "swap_activity|change_hotel|change_flight|extend_trip|shorten_trip|reschedule|other",
  "needs_re_research": true/false,  // does this need fresh API calls?
  "specific_changes": [
    {{"day": 1, "remove": "Activity Name", "add_preference": "something relaxing"}},
  ],
  "reasoning": "Explanation of what we need to change and why"
}}

Return ONLY the JSON object."""

    try:
        response = await llm.ainvoke(prompt)
        return json.loads(response.content)
    except Exception as e:
        logger.error("Change request interpretation failed: %s", e)
        return {
            "affected_days": [],
            "change_type": "other",
            "needs_re_research": True,
            "specific_changes": [],
            "reasoning": f"Could not interpret change. Will re-plan from scratch. Error: {str(e)}",
        }


def _compute_delta(change_analysis: dict, itinerary: dict) -> dict:
    """Heuristic delta computation — determine minimal re-work needed."""
    delta = {
        "re_research_needed": change_analysis.get("needs_re_research", False),
        "days_to_replan": change_analysis.get("affected_days", []),
        "change_type": change_analysis.get("change_type", "other"),
        "activities_to_remove": [],
        "preferences_to_add": [],
        "hotel_change": False,
        "flight_change": False,
    }

    change_type = change_analysis.get("change_type", "")

    if change_type == "change_hotel":
        delta["hotel_change"] = True
        delta["re_research_needed"] = True

    elif change_type == "change_flight":
        delta["flight_change"] = True
        delta["re_research_needed"] = True

    elif change_type in ("extend_trip", "shorten_trip"):
        delta["re_research_needed"] = True
        delta["days_to_replan"] = list(range(1, len(itinerary.get("days", [])) + 1))

    for change in change_analysis.get("specific_changes", []):
        if change.get("remove"):
            delta["activities_to_remove"].append({
                "day": change.get("day"),
                "name": change["remove"],
            })
        if change.get("add_preference"):
            delta["preferences_to_add"].append({
                "day": change.get("day"),
                "preference": change["add_preference"],
            })

    return delta


async def replan(state: TripState) -> TripState:
    """Handle a re-planning request."""
    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    itinerary = state.get("itinerary", {})
    replan_request = state.get("replan_request", "")

    state["status"] = TripStatus.REPLANNING

    await sse_manager.emit_phase_update(trip_id, "replanning", "starting", "Analyzing your changes...")
    await sse_manager.emit_agent_thinking(trip_id, "replanner", f"Understanding: \"{replan_request}\"")

    # Step 1: LLM interprets the change
    change_analysis = await _interpret_change_request(replan_request, itinerary)

    await sse_manager.emit_agent_thinking(
        trip_id, "replanner",
        f"Change type: {change_analysis.get('change_type')}. "
        f"Affects days: {change_analysis.get('affected_days', 'all')}. "
        f"Reasoning: {change_analysis.get('reasoning', '')}"
    )

    # Step 2: Heuristic delta computation
    delta = _compute_delta(change_analysis, itinerary)

    # Step 3: Apply removals
    if isinstance(itinerary, dict) and delta["activities_to_remove"]:
        for removal in delta["activities_to_remove"]:
            day_num = removal.get("day")
            name = removal.get("name", "").lower()
            for day in itinerary.get("days", []):
                if day.get("day_number") == day_num:
                    day["activities"] = [
                        a for a in day.get("activities", [])
                        if a.get("name", "").lower() != name
                    ]

    state["replan_delta"] = delta
    state["replan_analysis"] = change_analysis

    # Signal what needs to happen next (graph routing will use these flags)
    if delta["re_research_needed"]:
        state["research_complete"] = False  # Will trigger re-research
        await sse_manager.emit_phase_update(
            trip_id, "replanning", "re-research",
            "Changes require fresh research. Re-running searches..."
        )
    else:
        state["planning_complete"] = False  # Will trigger re-planning only
        await sse_manager.emit_phase_update(
            trip_id, "replanning", "re-plan",
            "Adjusting the itinerary based on your changes..."
        )

    return state
