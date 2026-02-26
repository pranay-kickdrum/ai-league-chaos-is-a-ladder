"""Verification Agent — Cross-reference places against Google Places API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models.agent_state import TripState
from app.models.trip import TripRequest, TripStatus
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)
settings = get_settings()


async def _verify_place(place_name: str, destination: str) -> dict:
    """Check if a place exists via Google Places Text Search."""
    query = f"{place_name} in {destination}"
    result = {"name": place_name, "verified": False, "place_id": None, "address": None}

    if not settings.GOOGLE_MAPS_API_KEY:
        return result

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query": query, "key": settings.GOOGLE_MAPS_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("results"):
                top = data["results"][0]
                result["verified"] = True
                result["place_id"] = top.get("place_id")
                result["address"] = top.get("formatted_address")
                result["rating"] = top.get("rating")
                result["lat"] = top.get("geometry", {}).get("location", {}).get("lat")
                result["lng"] = top.get("geometry", {}).get("location", {}).get("lng")
    except Exception as e:
        logger.warning("Place verification failed for %s: %s", place_name, e)

    return result


async def _check_url(url: str) -> bool:
    """HTTP HEAD to check if URL is live."""
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.head(url)
            return resp.status_code < 400
    except Exception:
        return False


async def verify(state: TripState) -> TripState:
    """Verify all places in itinerary against Google Places; flag unverified."""
    trip_id = state.get("trip_id", "")
    request = state.get("request")
    if isinstance(request, dict):
        request = TripRequest(**request)

    itinerary = state.get("itinerary", {})
    if isinstance(itinerary, dict):
        days = itinerary.get("days", [])
    else:
        days = itinerary.days if hasattr(itinerary, "days") else []

    state["status"] = TripStatus.VERIFYING

    await sse_manager.emit_phase_update(trip_id, "verification", "starting", "Verifying places and links...")
    await sse_manager.emit_agent_step(trip_id, "verifier", "Verifying places", "Cross-referencing with Google Places", "running")

    verification_results: list[dict] = []
    total_places = 0
    verified_count = 0

    for day in days:
        if isinstance(day, dict):
            activities = day.get("activities", [])
        else:
            activities = day.activities if hasattr(day, "activities") else []

        for act in activities:
            name = act.get("name", "") if isinstance(act, dict) else getattr(act, "name", "")
            place_id = act.get("place_id", None) if isinstance(act, dict) else getattr(act, "place_id", None)
            booking_url = act.get("booking_url", None) if isinstance(act, dict) else getattr(act, "booking_url", None)

            total_places += 1

            # Skip if already has a place_id from research
            if place_id:
                verified_count += 1
                verification_results.append({
                    "name": name, "verified": True, "place_id": place_id, "source": "research"
                })
                continue

            # Verify via Google Places
            result = await _verify_place(name, request.destination)
            if result["verified"]:
                verified_count += 1
                # Update the activity with verified place_id and coordinates
                if isinstance(act, dict):
                    act["place_id"] = result["place_id"]
                    act["is_verified"] = True
                    act["address"] = result.get("address", act.get("address", ""))
                    if result.get("lat") is not None:
                        act["latitude"] = result["lat"]
                    if result.get("lng") is not None:
                        act["longitude"] = result["lng"]
                    if result.get("rating") is not None and not act.get("rating"):
                        act["rating"] = result["rating"]

            result["source"] = "google_places_verification"
            verification_results.append(result)

            # Check booking URL
            if booking_url:
                url_ok = await _check_url(booking_url)
                if not url_ok:
                    logger.warning("Dead booking URL for %s: %s", name, booking_url)
                    # Replace with Google search fallback
                    fallback_url = f"https://www.google.com/search?q={name}+{request.destination}+book"
                    if isinstance(act, dict):
                        act["booking_url"] = fallback_url
                        act["booking_url_fallback"] = True

    # Also verify hotel
    hotel = (itinerary.get("selected_hotel") if isinstance(itinerary, dict) else
             getattr(itinerary, "selected_hotel", None))
    if hotel:
        hotel_name = hotel.get("name", "") if isinstance(hotel, dict) else getattr(hotel, "name", "")
        if hotel_name:
            total_places += 1
            hotel_result = await _verify_place(hotel_name, request.destination)
            if hotel_result["verified"]:
                verified_count += 1
            hotel_result["source"] = "hotel_verification"
            verification_results.append(hotel_result)

    state["verification_results"] = verification_results
    state["verification_complete"] = True

    pct = round(verified_count / max(total_places, 1) * 100)

    await sse_manager.emit_agent_step(
        trip_id, "verifier", "Verification complete",
        f"{verified_count}/{total_places} places confirmed ({pct}%)",
        "done",
        [r["name"] for r in verification_results if r.get("verified")][:5],
    )
    await sse_manager.emit_phase_update(
        trip_id, "verification", "complete",
        f"Verified {verified_count}/{total_places} places ({pct}%)"
    )
    await sse_manager.emit_agent_thinking(
        trip_id, "verifier",
        f"{verified_count} of {total_places} places confirmed via Google Places"
    )

    return state
