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


async def _interpret_change_request(change_text: str, itinerary: dict, current_request: dict) -> dict:
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

Current trip request:
- Destination: {current_request.get('destination', 'N/A')}
- Origin: {current_request.get('origin', 'N/A')}
- Duration: {current_request.get('duration_days', 'N/A')} days
- Budget: {current_request.get('budget', 'N/A')} {current_request.get('currency', 'INR')}
- Travelers: {current_request.get('traveler_count', 1)}
- Start date: {current_request.get('start_date', 'N/A')}

Current itinerary:
{chr(10).join(days_summary)}

Selected hotel: {itinerary.get('selected_hotel', {}).get('name', 'N/A')}
Selected transport: {itinerary.get('selected_flight', {}).get('airline_or_operator', 'N/A')} ({itinerary.get('selected_flight', {}).get('mode', 'flight')})

Change request: "{change_text}"

Return a JSON object with:
{{
  "affected_days": [1, 2],       // which day numbers need changes (empty = all)
  "change_type": "swap_activity|change_hotel|change_transport|prefer_transport_mode|extend_trip|shorten_trip|change_budget|change_destination|reschedule|other",
  "re_research_categories": [],   // which categories need fresh API calls: "transport", "hotels", "activities", "weather", "all". Empty array means no re-research needed.
  "transport_preference": null,   // if user prefers a transport mode: "flight", "train", "bus", or null
  "hotel_preference": null,       // if user prefers a specific hotel style: "budget", "luxury", etc., or null
  "request_modifications": {{
    "duration_days": null,        // new duration if changed, otherwise null
    "budget": null,               // new budget amount if changed, otherwise null
    "destination": null,          // new destination if changed, otherwise null
    "origin": null,               // new origin if changed, otherwise null
    "start_date": null,           // new start date (YYYY-MM-DD) if changed, otherwise null
    "traveler_count": null        // new traveler count if changed, otherwise null
  }},
  "specific_changes": [
    {{"day": 1, "remove": "Activity Name", "add_preference": "something relaxing"}},
  ],
  "reasoning": "Explanation of what we need to change and why"
}}

IMPORTANT RULES:
- If the user wants to shorten or extend the trip, set change_type appropriately and set request_modifications.duration_days.
- If the user prefers a specific transport mode (e.g. "I prefer flights", "take a train instead"), set change_type to "prefer_transport_mode", set transport_preference to the mode, and set re_research_categories to [] (empty — we already have the data, just need to re-plan with the preference).
- If the user wants to SEARCH for different transport options (e.g. "find cheaper flights"), set re_research_categories to ["transport"].
- If the user wants a different hotel, set re_research_categories to ["hotels"].
- If the user wants different activities, set re_research_categories to ["activities"].
- Only set re_research_categories to ["all"] if the destination, dates, or origin change.
- If the user mentions budget/cost concerns without changing destination/dates, set re_research_categories to [] (just re-plan with existing data).
Return ONLY the JSON object."""

    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3].strip()
        return json.loads(content)
    except Exception as e:
        logger.error("Change request interpretation failed: %s", e)
        return {
            "affected_days": [],
            "change_type": "other",
            "re_research_categories": ["all"],
            "transport_preference": None,
            "specific_changes": [],
            "reasoning": f"Could not interpret change. Will re-plan from scratch. Error: {str(e)}",
        }


# LLM may return plural or synonym forms; normalize to canonical mode values
_TRANSPORT_MODE_ALIASES: dict[str, str] = {
    "flight": "flight", "flights": "flight", "air": "flight", "plane": "flight",
    "train": "train", "trains": "train", "rail": "train", "railway": "train",
    "bus": "bus", "buses": "bus", "coach": "bus",
}


def _normalize_transport_mode(raw: str | None) -> str | None:
    if not raw:
        return None
    return _TRANSPORT_MODE_ALIASES.get(raw.lower().strip(), raw.lower().strip())


def _compute_delta(change_analysis: dict, itinerary: dict) -> dict:
    """Heuristic delta computation — determine minimal re-work needed."""
    re_research_cats = change_analysis.get("re_research_categories", [])
    # Backward compat: if LLM returned old-style needs_re_research=True without categories
    if not re_research_cats and change_analysis.get("needs_re_research"):
        re_research_cats = ["all"]

    delta = {
        "re_research_needed": bool(re_research_cats),
        "re_research_categories": re_research_cats,  # granular: ["transport"], ["hotels"], ["all"], etc.
        "days_to_replan": change_analysis.get("affected_days", []),
        "change_type": change_analysis.get("change_type", "other"),
        "activities_to_remove": [],
        "preferences_to_add": [],
        "hotel_change": False,
        "flight_change": False,
        "transport_preference": _normalize_transport_mode(change_analysis.get("transport_preference")),
        "hotel_preference": change_analysis.get("hotel_preference"),
    }

    change_type = change_analysis.get("change_type", "")

    if change_type == "change_hotel":
        delta["hotel_change"] = True
        if "hotels" not in re_research_cats and "all" not in re_research_cats:
            re_research_cats.append("hotels")
            delta["re_research_needed"] = True

    elif change_type in ("change_flight", "change_transport"):
        delta["flight_change"] = True
        if "transport" not in re_research_cats and "all" not in re_research_cats:
            re_research_cats.append("transport")
            delta["re_research_needed"] = True

    elif change_type == "prefer_transport_mode":
        # User just wants a different mode from existing options — no re-research needed
        delta["flight_change"] = True
        # Don't force re_research_needed — planner can handle with existing data

    elif change_type in ("extend_trip", "shorten_trip"):
        delta["days_to_replan"] = list(range(1, len(itinerary.get("days", [])) + 1))
        # Duration change: activities might need refresh, transport/hotel stay the same
        if not re_research_cats:
            re_research_cats = ["activities"]
            delta["re_research_needed"] = True

    elif change_type in ("change_destination"):
        # Destination change requires everything
        re_research_cats = ["all"]
        delta["re_research_needed"] = True
        delta["days_to_replan"] = list(range(1, len(itinerary.get("days", [])) + 1))

    elif change_type == "change_budget":
        # Budget change: just re-plan with existing data
        delta["days_to_replan"] = list(range(1, len(itinerary.get("days", [])) + 1))

    delta["re_research_categories"] = re_research_cats

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
        request_dict = request
        request = TripRequest(**request)
    else:
        request_dict = request.model_dump(mode="json") if hasattr(request, "model_dump") else {}

    itinerary = state.get("itinerary", {})
    replan_request = state.get("replan_request", "")

    state["status"] = TripStatus.REPLANNING

    await sse_manager.emit_phase_update(trip_id, "replanning", "starting", "Analyzing your changes...")
    await sse_manager.emit_agent_thinking(trip_id, "replanner", f"Understanding: \"{replan_request}\"")

    # Step 1: LLM interprets the change (with full request context)
    change_analysis = await _interpret_change_request(replan_request, itinerary, request_dict)

    await sse_manager.emit_agent_thinking(
        trip_id, "replanner",
        f"Change type: {change_analysis.get('change_type')}. "
        f"Affects days: {change_analysis.get('affected_days', 'all')}. "
        f"Reasoning: {change_analysis.get('reasoning', '')}"
    )

    # Step 2: Apply request modifications (duration, budget, destination, etc.)
    request_mods = change_analysis.get("request_modifications", {})
    if request_mods and isinstance(request_mods, dict):
        updated_request = request_dict.copy() if isinstance(request_dict, dict) else {}
        modified_fields = []
        for field, value in request_mods.items():
            if value is not None and field in updated_request:
                old_val = updated_request[field]
                updated_request[field] = value
                modified_fields.append(f"{field}: {old_val} → {value}")

        if modified_fields:
            # Update end_date if duration changed and start_date exists
            if "duration_days" in request_mods and request_mods["duration_days"] is not None:
                start_date = updated_request.get("start_date")
                if start_date:
                    from datetime import date, timedelta
                    if isinstance(start_date, str):
                        start_date = date.fromisoformat(start_date)
                    new_end = start_date + timedelta(days=int(request_mods["duration_days"]))
                    updated_request["end_date"] = str(new_end)
                    modified_fields.append(f"end_date: auto-adjusted to {new_end}")

            state["request"] = updated_request
            logger.info("Replanner updated request: %s", ", ".join(modified_fields))
            await sse_manager.emit_agent_thinking(
                trip_id, "replanner",
                f"Updated trip parameters: {', '.join(modified_fields)}"
            )

    # Step 3: Heuristic delta computation
    delta = _compute_delta(change_analysis, itinerary)

    # Step 4: Apply removals
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

    # Clear stale checkpoint decisions so checkpoints re-trigger on replan
    state["checkpoint_decision"] = {}
    state["last_checkpoint"] = ""

    # Signal what needs to happen next (graph routing will use these flags)
    if delta["re_research_needed"]:
        cats = delta.get("re_research_categories", ["all"])
        cat_label = ", ".join(cats) if "all" not in cats else "all categories"
        state["research_complete"] = False  # Will trigger re-research
        await sse_manager.emit_phase_update(
            trip_id, "replanning", "re-research",
            f"Re-searching {cat_label}..."
        )
    else:
        state["planning_complete"] = False  # Will trigger re-planning only
        pref = delta.get("transport_preference")
        detail = f" Prioritizing {pref}s." if pref else ""
        await sse_manager.emit_phase_update(
            trip_id, "replanning", "re-plan",
            f"Adjusting the itinerary based on your changes...{detail}"
        )

    return state
