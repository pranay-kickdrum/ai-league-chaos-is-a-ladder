"""Budget Optimizer Agent — Pure heuristic greedy algorithm."""

from __future__ import annotations

import logging
from typing import Any

from app.models.agent_state import TripState
from app.models.booking import BudgetBreakdown
from app.models.trip import TripRequest, TripStatus
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)


def _find_cheaper_alternative(activity: dict, all_activities: list[dict]) -> dict | None:
    """Find a cheaper activity in the same category."""
    category = activity.get("category", "")
    cost = activity.get("cost", 0)
    if cost <= 0:
        return None

    candidates = [
        a for a in all_activities
        if a.get("category") == category
        and 0 < a.get("cost", 0) < cost
        and a.get("name") != activity.get("name")
    ]
    if candidates:
        return max(candidates, key=lambda a: a.get("rating", 0))
    return None


def _optimize_budget(
    itinerary: dict,
    budget_limit: float,
    research: dict,
) -> tuple[dict, list[str], BudgetBreakdown]:
    """Greedy budget optimization: swap expensive items with cheaper alternatives."""
    reasoning_log: list[str] = []
    budget_data = itinerary.get("_budget", {})
    # Compute total from individual fields (total may be a computed field not in dict)
    current_total = (
        budget_data.get("transport", 0)
        + budget_data.get("accommodation", 0)
        + budget_data.get("food", 0)
        + budget_data.get("activities", 0)
        + budget_data.get("buffer", 0)
    ) if budget_data else 0

    # If already under budget, no optimization needed
    if current_total <= budget_limit:
        # Strip computed 'total' before constructing model (it's auto-computed)
        bd_kwargs = {k: v for k, v in budget_data.items() if k != "total"} if budget_data else {}
        bd = BudgetBreakdown(**bd_kwargs) if bd_kwargs else BudgetBreakdown(
            transport=0, accommodation=0, food=0, activities=0, buffer=0, currency="INR"
        )
        reasoning_log.append(f"Total cost ({current_total}) is within budget ({budget_limit}). No changes needed.")
        return itinerary, reasoning_log, bd

    over_budget = current_total - budget_limit
    reasoning_log.append(f"Over budget by {over_budget}. Starting optimization...")

    all_research_activities = research.get("activities", [])
    if all_research_activities and hasattr(all_research_activities[0], "model_dump"):
        all_research_activities = [a.model_dump() for a in all_research_activities]

    saved = 0.0
    days = itinerary.get("days", [])

    # Sort all activities across all days by cost (descending) for greedy replacement
    all_scheduled: list[tuple[int, int, dict]] = []
    for day_idx, day in enumerate(days):
        for act_idx, act in enumerate(day.get("activities", [])):
            if isinstance(act, dict) and act.get("cost", 0) > 0:
                all_scheduled.append((day_idx, act_idx, act))

    all_scheduled.sort(key=lambda x: x[2].get("cost", 0), reverse=True)

    for day_idx, act_idx, act in all_scheduled:
        if saved >= over_budget:
            break

        cheaper = _find_cheaper_alternative(act, all_research_activities)
        if cheaper:
            saving = act["cost"] - cheaper.get("cost", 0)
            old_name = act["name"]
            new_name = cheaper.get("name", "alternative")

            # Swap in itinerary
            days[day_idx]["activities"][act_idx] = {
                **days[day_idx]["activities"][act_idx],
                "name": cheaper.get("name"),
                "cost": cheaper.get("cost", 0),
                "description": cheaper.get("description", ""),
                "place_id": cheaper.get("place_id"),
                "address": cheaper.get("address", ""),
                "rating": cheaper.get("rating"),
                "booking_url": cheaper.get("booking_url"),
                "optimized": True,
            }

            saved += saving
            reasoning_log.append(
                f"Swapped '{old_name}' (cost: {act['cost']}) → '{new_name}' (cost: {cheaper.get('cost', 0)}). "
                f"Saved: {saving}"
            )

    # If still over budget, try reducing hotel
    if saved < over_budget:
        hotels = research.get("hotels", [])
        if hotels and hasattr(hotels[0], "model_dump"):
            hotels = [h.model_dump() for h in hotels]

        current_hotel = itinerary.get("selected_hotel")
        if current_hotel:
            current_price = current_hotel.get("price_per_night", 0)
            cheaper_hotels = [
                h for h in hotels
                if h.get("price_per_night", 0) < current_price and h.get("name") != current_hotel.get("name")
            ]
            if cheaper_hotels:
                best_alt = max(cheaper_hotels, key=lambda h: h.get("rating", 0))
                nights = max(len(days) - 1, 1)
                hotel_saving = (current_price - best_alt.get("price_per_night", 0)) * nights
                reasoning_log.append(
                    f"Switched hotel from '{current_hotel.get('name')}' ({current_price}/night) "
                    f"→ '{best_alt.get('name')}' ({best_alt.get('price_per_night', 0)}/night). "
                    f"Saved: {hotel_saving} over {nights} nights"
                )
                itinerary["selected_hotel"] = best_alt
                saved += hotel_saving

    # Recalculate totals
    total_activity_cost = sum(
        act.get("cost", 0)
        for day in days
        for act in day.get("activities", [])
    )
    flight_cost = itinerary.get("selected_flight", {}).get("price", 0) if itinerary.get("selected_flight") else 0
    hotel_cost = (
        itinerary.get("selected_hotel", {}).get("price_per_night", 0) * max(len(days) - 1, 1)
        if itinerary.get("selected_hotel") else 0
    )

    currency = budget_data.get("currency", "INR")
    bd = BudgetBreakdown(
        transport=flight_cost,
        accommodation=hotel_cost,
        food=budget_data.get("food", 0),
        activities=total_activity_cost,
        buffer=budget_data.get("buffer", 0),
        currency=currency,
    )

    itinerary["total_cost"] = bd.total
    reasoning_log.append(f"Final total: {currency} {bd.total} (saved {saved} total)")

    return itinerary, reasoning_log, bd


async def optimize(state: TripState) -> TripState:
    """Run budget optimization on the itinerary."""
    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    itinerary = state.get("itinerary", {})
    research = state.get("research", {})
    budget_data = state.get("budget_breakdown", {})

    # Attach budget data to itinerary for optimization
    if isinstance(itinerary, dict):
        itinerary["_budget"] = budget_data

    await sse_manager.emit_phase_update(trip_id, "optimization", "starting", "Optimizing budget...")
    await sse_manager.emit_agent_step(trip_id, "optimizer", "Checking budget fit", f"Target: {request.currency} {request.budget}", "running")
    await sse_manager.emit_agent_thinking(trip_id, "optimizer", "Checking if plan fits within budget...")

    optimized_itinerary, reasoning_log, new_budget = _optimize_budget(
        itinerary, request.budget, research
    )

    # Clean up temp field
    if isinstance(optimized_itinerary, dict):
        optimized_itinerary.pop("_budget", None)

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
