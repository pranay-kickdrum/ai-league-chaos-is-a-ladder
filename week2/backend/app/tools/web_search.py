"""SerpAPI general web search (fallback for activities, tips, etc.)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.cache import cache_get, cache_set
from app.tools.resilience import resilient_api_call

logger = logging.getLogger(__name__)
settings = get_settings()

SERPAPI_BASE = "https://serpapi.com/search.json"


@resilient_api_call("serpapi_search")
async def _web_search(query: str) -> list[dict[str, Any]]:
    params = {
        "engine": "google",
        "q": query,
        "num": 10,
        "api_key": settings.SERPAPI_API_KEY,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(SERPAPI_BASE, params=params)
        resp.raise_for_status()
        return resp.json().get("organic_results", [])


async def web_search(query: str) -> list[dict[str, Any]]:
    """Search the web and return organic results."""
    cached = cache_get("web_search", query=query)
    if cached is not None:
        return cached

    try:
        results = await _web_search(query)
        simplified = [
            {
                "title": r.get("title", ""),
                "link": r.get("link", ""),
                "snippet": r.get("snippet", ""),
            }
            for r in results[:10]
        ]
        cache_set("web_search", simplified, query=query)
        return simplified
    except Exception as e:
        logger.error("Web search error: %s", e)
        return []
