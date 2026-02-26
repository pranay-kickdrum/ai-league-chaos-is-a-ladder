"""Google Places API wrapper for activities / things to do."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models.booking import ActivityOption
from app.services.cache import cache_get, cache_set
from app.tools.resilience import resilient_api_call

logger = logging.getLogger(__name__)
settings = get_settings()

PLACES_TEXT_SEARCH = "https://maps.googleapis.com/maps/api/place/textsearch/json"


@resilient_api_call("google_places_activities")
async def _search_activities_places(
    query: str,
) -> list[dict[str, Any]]:
    params = {
        "query": query,
        "key": settings.GOOGLE_PLACES_API_KEY,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(PLACES_TEXT_SEARCH, params=params)
        resp.raise_for_status()
        return resp.json().get("results", [])


async def search_activities(
    destination: str,
    queries: list[str],
    currency: str = "INR",
) -> list[ActivityOption]:
    """Search activities using multiple queries. Returns deduplicated results."""
    cached = cache_get("activities", destination=destination, queries=tuple(queries))
    if cached is not None:
        return cached

    seen_ids: set[str] = set()
    options: list[ActivityOption] = []

    for query in queries:
        full_query = f"{query} {destination}" if destination.lower() not in query.lower() else query
        try:
            raw = await _search_activities_places(full_query)
            for i, p in enumerate(raw[:5]):
                pid = p.get("place_id", "")
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                loc = p.get("geometry", {}).get("location", {})
                types_list = p.get('types', [])
                clean_types = [t.replace('_', ' ') for t in types_list[:3]
                               if t not in ('establishment', 'point_of_interest')]
                description = ', '.join(clean_types).capitalize() if clean_types else ''
                options.append(
                    ActivityOption(
                        id=f"act-{len(options)}",
                        name=p.get("name", ""),
                        description=description,
                        category=_infer_category(p.get("types", [])),
                        price=0,  # Places API doesn't give prices
                        currency=currency,
                        location=p.get("formatted_address", destination),
                        latitude=loc.get("lat"),
                        longitude=loc.get("lng"),
                        rating=p.get("rating", 0),
                        place_id=pid,
                        source="google_places",
                        is_verified=True,
                    )
                )
        except Exception as e:
            logger.error("Activity search error for '%s': %s", query, e)

    if options:
        cache_set("activities", options, destination=destination, queries=tuple(queries))
    return options


def _infer_category(types: list[str]) -> str:
    """Map Google Places types to our categories."""
    type_set = set(types)
    if type_set & {"hindu_temple", "church", "mosque", "place_of_worship"}:
        return "spiritual"
    if type_set & {"museum", "art_gallery"}:
        return "cultural"
    if type_set & {"amusement_park", "stadium"}:
        return "adventure"
    if type_set & {"park", "natural_feature"}:
        return "nature"
    if type_set & {"restaurant", "cafe", "bakery"}:
        return "food"
    if type_set & {"shopping_mall", "store"}:
        return "shopping"
    return "general"
