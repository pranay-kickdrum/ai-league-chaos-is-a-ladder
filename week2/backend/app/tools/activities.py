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
                        price=0,  # Prices enriched later via LLM
                        currency=currency,
                        location=p.get("formatted_address", destination),
                        latitude=loc.get("lat"),
                        longitude=loc.get("lng"),
                        rating=p.get("rating", 0),
                        price_level=p.get("price_level"),  # 0-4 from Google Places
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


async def enrich_activity_prices(
    activities: list[ActivityOption],
    destination: str,
    currency: str = "INR",
) -> list[ActivityOption]:
    """Use LLM to estimate realistic entry/ticket prices for activities.

    Batches all activities into a single LLM call for efficiency.
    Falls back to heuristic pricing if the LLM call fails.
    """
    if not activities:
        return activities

    cached = cache_get("activity_prices", destination=destination, ids=tuple(a.id for a in activities))
    if cached is not None:
        return cached

    import json as _json
    import re as _re

    from langchain_openai import ChatOpenAI
    from app.config import get_settings

    _settings = get_settings()

    activity_list = "\n".join(
        f"- {a.name} (category: {a.category}, rating: {a.rating}, "
        f"price_level: {a.price_level if a.price_level is not None else 'unknown'})"
        for a in activities
    )

    prompt = f"""You are a travel cost expert. Estimate realistic entry fees / ticket prices for these activities in {destination} in {currency}.

Activities:
{activity_list}

Rules:
- Return a JSON array of objects with "name" and "price" (number).
- Prices should be realistic 2024-2026 prices in {currency}.
- Free activities (temples, beaches, ghats, public parks) should have price 0.
- Adventure activities (rafting, bungee, paragliding) are typically expensive.
- Museums and cultural sites have modest entry fees.
- Each activity should have a DIFFERENT price based on what it actually costs.
- For {currency}, use whole numbers (no decimals).

Return ONLY the JSON array, no explanation."""

    try:
        llm = ChatOpenAI(
            model=_settings.LLM_MODEL_NARRATION,
            api_key=_settings.OPENAI_API_KEY,
            temperature=0.2,
        )
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        # Strip markdown code fences
        content = _re.sub(r"^```[a-z]*\n?", "", content)
        content = _re.sub(r"\n?```$", "", content)
        prices = _json.loads(content.strip())

        if isinstance(prices, list):
            # Build a name→price lookup (case-insensitive)
            price_map: dict[str, float] = {}
            for p in prices:
                name = p.get("name", "").strip().lower()
                price_val = p.get("price", 0)
                if isinstance(price_val, (int, float)) and price_val >= 0:
                    price_map[name] = float(price_val)

            enriched: list[ActivityOption] = []
            for act in activities:
                matched_price = price_map.get(act.name.strip().lower())
                if matched_price is not None:
                    act = act.model_copy(update={"price": matched_price, "source": "llm_estimated"})
                enriched.append(act)

            logger.info("LLM price enrichment: matched %d/%d activities for %s",
                        sum(1 for a in enriched if a.source == "llm_estimated"), len(activities), destination)

            if enriched:
                cache_set("activity_prices", enriched, destination=destination, ids=tuple(a.id for a in activities))
            return enriched

    except Exception as e:
        logger.warning("LLM price enrichment failed for %s: %s — falling back to heuristics", destination, e)

    return activities
