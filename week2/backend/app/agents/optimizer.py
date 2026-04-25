"""Budget Optimizer Agent — LLM-powered smart optimization."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.models.agent_state import TripState
from app.models.booking import BudgetBreakdown
from app.models.trip import TripRequest, TripStatus
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)
settings = get_settings()


def _recalculate_budget(itinerary: dict, traveler_count: int = 1) -> BudgetBreakdown:
    """Accurately recalculate budget from the actual itinerary contents."""
    days = itinerary.get("days", [])
    nights = max(len(days) - 1, 1)
    currency = itinerary.get("currency", "INR")

    # Transport: from selected_flight (holds any transport mode)
    selected_transport = itinerary.get("selected_flight") or {}
    transport_price_pp = selected_transport.get("price", 0)
    transport_cost = transport_price_pp * traveler_count

    # Airport transfer: connecting transport from airport city to destination
    airport_transfer = itinerary.get("selected_airport_transfer") or {}
    transfer_price_pp = airport_transfer.get("price", 0)
    transport_cost += transfer_price_pp * traveler_count

    # Accommodation: from selected_hotel
    selected_hotel = itinerary.get("selected_hotel") or {}
    hotel_ppn = selected_hotel.get("price_per_night", 0)
    accommodation_cost = hotel_ppn * nights

    # Activities: sum actual costs from day plans (per-person), multiply by group size
    total_activity_cost_pp = 0.0
    for day in days:
        for act in day.get("activities", []):
            total_activity_cost_pp += act.get("cost", 0)
    total_activity_cost = total_activity_cost_pp * traveler_count

    # Food: sum meal cost_estimates from day plans
    total_food_cost = 0.0
    for day in days:
        for meal in day.get("meals", []):
            total_food_cost += meal.get("cost_estimate", 0)

    # Buffer: 10% of subtotal
    subtotal = transport_cost + accommodation_cost + total_food_cost + total_activity_cost
    buffer = round(subtotal * 0.10, 2)

    return BudgetBreakdown(
        transport=transport_cost,
        accommodation=accommodation_cost,
        food=total_food_cost,
        activities=total_activity_cost,
        buffer=buffer,
        currency=currency,
        traveler_count=traveler_count,
    )


async def _llm_optimize(
    itinerary: dict,
    budget_limit: float,
    currency: str,
    research: dict,
    current_budget: BudgetBreakdown,
) -> tuple[dict, list[str], BudgetBreakdown]:
    """Use LLM to make smart budget optimization decisions."""
    llm = ChatOpenAI(
        model=settings.LLM_MODEL_REASONING,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.2,
    )

    days = itinerary.get("days", [])
    over_budget = current_budget.total - budget_limit

    # Build context for LLM
    days_summary = []
    for day in days:
        acts = []
        for a in day.get("activities", []):
            acts.append(f"  - {a.get('name', '?')} ({currency} {a.get('cost', 0)}, category: {a.get('category', '?')})")
        transport_info = ""
        for t in day.get("transport", []):
            transport_info += f"\n  Transport: {t.get('mode', '?')} {t.get('from_location', '')}→{t.get('to_location', '')} ({currency} {t.get('cost', 0)})"
        meals_info = ""
        for m in day.get("meals", []):
            meals_info += f"\n  {m.get('meal_type', '?')}: {m.get('name', '?')} (~{currency} {m.get('cost_estimate', 0)})"
        days_summary.append(
            f"Day {day.get('day_number', '?')}:\n"
            + "\n".join(acts)
            + transport_info
            + meals_info
        )

    selected_hotel = itinerary.get("selected_hotel") or {}
    selected_transport = itinerary.get("selected_flight") or {}
    nights = max(len(days) - 1, 1)

    # Available alternatives from research
    alt_hotels = research.get("hotels", [])
    if alt_hotels and hasattr(alt_hotels[0], "model_dump"):
        alt_hotels = [h.model_dump() for h in alt_hotels]
    cheaper_hotels = [
        f"  - {h.get('name', '?')} ★{h.get('rating', 0)} — {currency} {h.get('price_per_night', 0)}/night"
        for h in sorted(alt_hotels, key=lambda h: h.get("price_per_night", 9999))[:5]
    ]

    alt_activities = research.get("activities", [])
    if alt_activities and hasattr(alt_activities[0], "model_dump"):
        alt_activities = [a.model_dump() for a in alt_activities]

    prompt = f"""You are a travel budget optimizer. The current itinerary is OVER BUDGET by {currency} {over_budget:.0f}.

CURRENT BUDGET BREAKDOWN:
- Transport: {currency} {current_budget.transport} ({selected_transport.get('airline_or_operator', 'N/A')} {selected_transport.get('mode', 'N/A')})
- Accommodation: {currency} {current_budget.accommodation} ({selected_hotel.get('name', 'N/A')} @ {selected_hotel.get('price_per_night', 0)}/night × {nights} nights)
- Food: {currency} {current_budget.food}
- Activities: {currency} {current_budget.activities}
- Buffer: {currency} {current_budget.buffer}
- TOTAL: {currency} {current_budget.total}
- BUDGET LIMIT: {currency} {budget_limit}

ITINERARY:
{chr(10).join(days_summary)}

CHEAPER HOTEL OPTIONS:
{chr(10).join(cheaper_hotels) if cheaper_hotels else "None available"}

Return a JSON object with your optimization decisions:
{{
  "reasoning": ["step-by-step reasoning for each change"],
  "changes": {{
    "swap_hotel": {{"name": "...", "price_per_night": N}} or null,
    "remove_activities": ["activity name to remove", ...],
    "reduce_food_budget_per_meal": N or null,
    "reduce_buffer_to": N or null
  }}
}}

Rules:
- Only make changes that save enough to get under budget
- Prefer removing expensive low-rated activities over cheap highly-rated ones
- Switching to a cheaper hotel with good rating (≥3.5) is acceptable
- Do NOT remove all activities — keep at least 2 per day
- Food can be reduced but not below {currency} {150 if currency == 'INR' else 5}/meal
- Buffer should be at least 5% of total
- Return ONLY valid JSON, no explanation outside it."""

    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        content = re.sub(r"^```[a-z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
        decisions = json.loads(content.strip())

        reasoning_log: list[str] = decisions.get("reasoning", [])
        changes = decisions.get("changes", {})

        # Apply hotel swap
        if changes.get("swap_hotel"):
            new_hotel_info = changes["swap_hotel"]
            target_name = new_hotel_info.get("name", "").lower()
            # Find matching hotel in research
            matched = None
            for h in alt_hotels:
                if h.get("name", "").lower() == target_name:
                    matched = h
                    break
            if not matched:
                # Fuzzy match — pick the one with matching price
                target_price = new_hotel_info.get("price_per_night", 0)
                for h in alt_hotels:
                    if abs(h.get("price_per_night", 0) - target_price) < 100:
                        matched = h
                        break
            if matched:
                old_name = selected_hotel.get("name", "?")
                itinerary["selected_hotel"] = matched
                reasoning_log.append(f"Switched hotel: {old_name} → {matched.get('name', '?')}")

        # Apply activity removals
        remove_names = set(n.lower() for n in (changes.get("remove_activities") or []))
        if remove_names:
            for day in days:
                day["activities"] = [
                    a for a in day.get("activities", [])
                    if a.get("name", "").lower() not in remove_names
                ]
                # Recalculate day cost
                day["day_cost"] = sum(a.get("cost", 0) for a in day.get("activities", []))
            reasoning_log.append(f"Removed {len(remove_names)} expensive activities")

        # Apply food reduction
        new_meal_cost = changes.get("reduce_food_budget_per_meal")
        if new_meal_cost and isinstance(new_meal_cost, (int, float)):
            for day in days:
                for meal in day.get("meals", []):
                    meal["cost_estimate"] = new_meal_cost
            reasoning_log.append(f"Reduced meal budget to {currency} {new_meal_cost}/meal")

        # Apply buffer reduction
        new_buffer = changes.get("reduce_buffer_to")

        # Recalculate budget from modified itinerary
        traveler_count = current_budget.traveler_count or 1
        new_bd = _recalculate_budget(itinerary, traveler_count)

        # Override buffer if LLM specified
        if new_buffer and isinstance(new_buffer, (int, float)):
            new_bd = BudgetBreakdown(
                transport=new_bd.transport,
                accommodation=new_bd.accommodation,
                food=new_bd.food,
                activities=new_bd.activities,
                buffer=new_buffer,
                currency=new_bd.currency,
                traveler_count=new_bd.traveler_count,
            )

        itinerary["total_cost"] = new_bd.total
        reasoning_log.append(f"Final optimized total: {currency} {new_bd.total}")

        return itinerary, reasoning_log, new_bd

    except Exception as e:
        logger.error("LLM optimization failed: %s — falling back to recalculation", e)
        # Fallback: just recalculate accurately without changes
        bd = _recalculate_budget(itinerary, current_budget.traveler_count or 1)
        itinerary["total_cost"] = bd.total
        return itinerary, [f"LLM optimization unavailable; recalculated totals: {currency} {bd.total}"], bd


async def optimize(state: TripState) -> TripState:
    """Run budget optimization on the itinerary."""
    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    itinerary = state.get("itinerary", {})
    research = state.get("research", {})

    traveler_count = max(getattr(request, "traveler_count", 1), 1)

    await sse_manager.emit_phase_update(trip_id, "optimization", "starting", "Optimizing budget...")
    await sse_manager.emit_agent_step(trip_id, "optimizer", "Analyzing budget", f"Target: {request.currency} {request.budget}", "running")
    await sse_manager.emit_agent_thinking(trip_id, "optimizer", "Recalculating actual costs from itinerary...")

    # Step 1: Accurately recalculate budget from itinerary contents
    accurate_budget = _recalculate_budget(itinerary, traveler_count)
    logger.info(
        "Optimizer recalc: transport=%s, accommodation=%s, food=%s, activities=%s, buffer=%s, total=%s (limit=%s)",
        accurate_budget.transport, accurate_budget.accommodation, accurate_budget.food,
        accurate_budget.activities, accurate_budget.buffer, accurate_budget.total, request.budget,
    )

    # Step 2: Check if optimization is needed
    if accurate_budget.total <= request.budget:
        reasoning_log = [
            f"Total cost ({request.currency} {accurate_budget.total}) is within budget ({request.currency} {request.budget}). No optimization needed."
        ]
        itinerary["total_cost"] = accurate_budget.total
        state["itinerary"] = itinerary
        state["budget_breakdown"] = accurate_budget.model_dump()
        state["reasoning_log"] = reasoning_log
        state["optimization_complete"] = True

        await sse_manager.emit_agent_thinking(trip_id, "optimizer", reasoning_log[0])
        await sse_manager.emit_agent_step(
            trip_id, "optimizer", "Budget OK",
            f"Total: {request.currency} {accurate_budget.total} (within {request.currency} {request.budget})",
            "done", reasoning_log,
        )
        await sse_manager.emit_budget_update(trip_id, accurate_budget.model_dump())
        await sse_manager.emit_phase_update(trip_id, "optimization", "complete", "Budget optimization done")
        return state

    # Step 3: Over budget — use LLM for smart optimization
    await sse_manager.emit_agent_thinking(
        trip_id, "optimizer",
        f"Over budget by {request.currency} {accurate_budget.total - request.budget:.0f}. Using AI to find smart savings..."
    )

    optimized_itinerary, reasoning_log, new_budget = await _llm_optimize(
        itinerary, request.budget, request.currency, research, accurate_budget,
    )

    state["itinerary"] = optimized_itinerary
    state["budget_breakdown"] = new_budget.model_dump()
    state["reasoning_log"] = reasoning_log
    state["optimization_complete"] = True

    for entry in reasoning_log:
        await sse_manager.emit_agent_thinking(trip_id, "optimizer", entry)

    await sse_manager.emit_agent_step(
        trip_id, "optimizer", "Optimization complete",
        f"Final total: {new_budget.currency} {new_budget.total}",
        "done",
        reasoning_log[:4],
    )
    await sse_manager.emit_budget_update(trip_id, new_budget.model_dump())
    await sse_manager.emit_phase_update(trip_id, "optimization", "complete", "Budget optimization done")

    return state
