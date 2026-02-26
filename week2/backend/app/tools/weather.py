"""OpenWeatherMap API wrapper."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.cache import cache_get, cache_set
from app.tools.resilience import resilient_api_call

logger = logging.getLogger(__name__)
settings = get_settings()

OWM_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"
OWM_GEO = "http://api.openweathermap.org/geo/1.0/direct"


@resilient_api_call("openweathermap")
async def _fetch_forecast(lat: float, lon: float) -> dict[str, Any]:
    params = {
        "lat": lat,
        "lon": lon,
        "appid": settings.OPENWEATHER_API_KEY,
        "units": "metric",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(OWM_FORECAST, params=params)
        resp.raise_for_status()
        return resp.json()


async def _geocode(city: str) -> tuple[float, float] | None:
    """Get lat/lon for a city name."""
    cached = cache_get("geocode", city=city)
    if cached is not None:
        return cached

    params = {"q": city, "limit": 1, "appid": settings.OPENWEATHER_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(OWM_GEO, params=params)
            resp.raise_for_status()
            results = resp.json()
            if results:
                coords = (results[0]["lat"], results[0]["lon"])
                cache_set("geocode", coords, city=city)
                return coords
    except Exception as e:
        logger.error("Geocode error for %s: %s", city, e)
    return None


async def get_weather(
    destination: str,
    start_date: str | None = None,
) -> dict[str, Any]:
    """Get 5-day weather forecast for a destination.

    Returns dict with daily summaries: {date: {temp, description, rain_prob}}.
    """
    cached = cache_get("weather", destination=destination)
    if cached is not None:
        return cached

    coords = await _geocode(destination)
    if not coords:
        return {"error": "Could not geocode destination", "data": {}}

    try:
        data = await _fetch_forecast(coords[0], coords[1])
    except Exception as e:
        logger.error("Weather fetch error: %s", e)
        return {"error": str(e), "data": {}}

    # Group by day
    daily: dict[str, dict[str, Any]] = {}
    for entry in data.get("list", []):
        dt_txt = entry.get("dt_txt", "")
        day = dt_txt[:10]
        if day not in daily:
            daily[day] = {
                "temp_min": entry["main"]["temp_min"],
                "temp_max": entry["main"]["temp_max"],
                "description": entry["weather"][0]["description"] if entry.get("weather") else "",
                "rain_prob": entry.get("pop", 0) * 100,
            }
        else:
            daily[day]["temp_min"] = min(daily[day]["temp_min"], entry["main"]["temp_min"])
            daily[day]["temp_max"] = max(daily[day]["temp_max"], entry["main"]["temp_max"])

    result = {"data": daily, "coords": {"lat": coords[0], "lon": coords[1]}}
    cache_set("weather", result, destination=destination)
    return result
