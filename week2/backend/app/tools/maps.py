"""Google Maps Directions + Distance Matrix wrapper."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.cache import cache_get, cache_set
from app.tools.resilience import resilient_api_call

logger = logging.getLogger(__name__)
settings = get_settings()

DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
DISTANCE_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


@resilient_api_call("google_maps")
async def get_directions(
    origin: str,
    destination: str,
    mode: str = "driving",
) -> dict[str, Any]:
    """Get directions between two points."""
    cached = cache_get("directions", origin=origin, destination=destination, mode=mode)
    if cached is not None:
        return cached

    params = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "key": settings.GOOGLE_MAPS_API_KEY,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(DIRECTIONS_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    routes = data.get("routes", [])
    if not routes:
        return {"error": "No route found", "duration_minutes": 0, "distance_km": 0}

    leg = routes[0].get("legs", [{}])[0]
    result = {
        "duration_minutes": leg.get("duration", {}).get("value", 0) // 60,
        "distance_km": round(leg.get("distance", {}).get("value", 0) / 1000, 1),
        "duration_text": leg.get("duration", {}).get("text", ""),
        "distance_text": leg.get("distance", {}).get("text", ""),
        "polyline": routes[0].get("overview_polyline", {}).get("points", ""),
    }
    cache_set("directions", result, origin=origin, destination=destination, mode=mode)
    return result


@resilient_api_call("google_maps")
async def get_distance_matrix(
    origins: list[str],
    destinations: list[str],
    mode: str = "driving",
) -> dict[str, Any]:
    """Get distance matrix between multiple points for route optimization."""
    cache_key_origins = tuple(sorted(origins))
    cache_key_dests = tuple(sorted(destinations))
    cached = cache_get("distance_matrix", origins=cache_key_origins, destinations=cache_key_dests)
    if cached is not None:
        return cached

    params = {
        "origins": "|".join(origins),
        "destinations": "|".join(destinations),
        "mode": mode,
        "key": settings.GOOGLE_MAPS_API_KEY,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(DISTANCE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    matrix: list[list[dict[str, int]]] = []
    for row in data.get("rows", []):
        row_data = []
        for elem in row.get("elements", []):
            row_data.append(
                {
                    "duration_minutes": elem.get("duration", {}).get("value", 0) // 60,
                    "distance_km": round(elem.get("distance", {}).get("value", 0) / 1000, 1),
                }
            )
        matrix.append(row_data)

    result = {"matrix": matrix, "origins": origins, "destinations": destinations}
    cache_set("distance_matrix", result, origins=cache_key_origins, destinations=cache_key_dests)
    return result
