"""SerpAPI Google Flights wrapper."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models.booking import FlightOption
from app.services.cache import cache_get, cache_set
from app.tools.resilience import CircuitOpenError, resilient_api_call

logger = logging.getLogger(__name__)
settings = get_settings()

SERPAPI_BASE = "https://serpapi.com/search.json"


@resilient_api_call("serpapi_flights")
async def _search_flights_serpapi(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    currency: str = "INR",
) -> list[dict[str, Any]]:
    """Raw SerpAPI Google Flights search."""
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure_date,
        "currency": currency,
        "hl": "en",
        "api_key": settings.SERPAPI_API_KEY,
    }
    if return_date:
        params["return_date"] = return_date

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(SERPAPI_BASE, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("best_flights", []) + data.get("other_flights", [])
    return results


async def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    currency: str = "INR",
) -> list[FlightOption]:
    """Search flights with cache + fallback."""
    if not departure_date:
        logger.info("Skipping flight search — no departure date provided")
        return []

    # Check cache
    cached = cache_get(
        "flights",
        origin=origin,
        destination=destination,
        date=departure_date,
    )
    if cached is not None:
        return cached

    options: list[FlightOption] = []

    try:
        raw = await _search_flights_serpapi(
            origin, destination, departure_date, return_date, currency
        )
        for i, flight in enumerate(raw[:10]):  # Cap at 10 results
            flights_list = flight.get("flights", [{}])
            first_leg = flights_list[0] if flights_list else {}
            price_val = flight.get("price", 0)

            options.append(
                FlightOption(
                    id=f"flight-serp-{i}",
                    mode="flight",
                    airline_or_operator=first_leg.get("airline", ""),
                    departure_time=first_leg.get("departure_airport", {}).get("time", ""),
                    arrival_time=first_leg.get("arrival_airport", {}).get("time", ""),
                    duration_minutes=flight.get("total_duration", 0),
                    from_location=origin,
                    to_location=destination,
                    price=price_val,
                    currency=currency,
                    booking_url=f"https://www.google.com/travel/flights?q=flights+from+{origin}+to+{destination}",
                    source="serpapi",
                    is_verified=True,
                )
            )
    except CircuitOpenError:
        logger.warning("SerpAPI flights circuit open — falling through to Amadeus")
    except Exception as e:
        logger.error("SerpAPI flights error: %s", e)

    # Cache if results found
    if options:
        cache_set(
            "flights",
            options,
            origin=origin,
            destination=destination,
            date=departure_date,
        )

    return options
