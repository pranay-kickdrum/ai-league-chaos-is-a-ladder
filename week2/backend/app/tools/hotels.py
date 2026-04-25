"""SerpAPI Hotels + Google Places hotel search wrapper."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models.booking import HotelOption
from app.services.cache import cache_get, cache_set
from app.tools.resilience import CircuitOpenError, resilient_api_call

logger = logging.getLogger(__name__)
settings = get_settings()

SERPAPI_BASE = "https://serpapi.com/search.json"


@resilient_api_call("serpapi_hotels")
async def _search_hotels_serpapi(
    destination: str,
    check_in: str,
    check_out: str,
    currency: str = "INR",
) -> list[dict[str, Any]]:
    params = {
        "engine": "google_hotels",
        "q": f"hotels in {destination}",
        "check_in_date": check_in,
        "check_out_date": check_out,
        "currency": currency,
        "hl": "en",
        "api_key": settings.SERPAPI_API_KEY,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(SERPAPI_BASE, params=params)
        resp.raise_for_status()
        return resp.json().get("properties", [])


@resilient_api_call("google_places_hotels")
async def _search_hotels_places(
    destination: str,
) -> list[dict[str, Any]]:
    """Fallback: Google Places text search for hotels."""
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": f"hotels in {destination}",
        "type": "lodging",
        "key": settings.GOOGLE_PLACES_API_KEY,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json().get("results", [])


async def search_hotels(
    destination: str,
    check_in: str,
    check_out: str,
    nights: int = 1,
    currency: str = "INR",
) -> list[HotelOption]:
    """Search hotels: SerpAPI → Google Places → cache."""
    if not check_in or not check_out:
        logger.info("Skipping hotel search — no check-in/check-out dates provided")
        return []

    cached = cache_get("hotels", destination=destination, check_in=check_in)
    if cached is not None:
        return cached

    options: list[HotelOption] = []

    # Primary: SerpAPI
    try:
        raw = await _search_hotels_serpapi(destination, check_in, check_out, currency)
        for i, h in enumerate(raw[:10]):
            rate = h.get("rate_per_night", {})
            # Prefer the clean numeric field; fall back to string parsing
            price = rate.get("extracted_lowest") or 0
            if not price:
                raw_str = str(rate.get("lowest", "0")).replace(",", "").replace("₹", "").replace("$", "")
                try:
                    price = float(raw_str) if raw_str else 0
                except ValueError:
                    price = 0
            options.append(
                HotelOption(
                    id=f"hotel-serp-{i}",
                    name=h.get("name", ""),
                    hotel_type=h.get("type", "hotel"),
                    rating=h.get("overall_rating", 0),
                    price_per_night=price,
                    total_price=price * nights,
                    currency=currency,
                    location=h.get("location", destination),
                    latitude=h.get("gps_coordinates", {}).get("latitude"),
                    longitude=h.get("gps_coordinates", {}).get("longitude"),
                    amenities=h.get("amenities", [])[:5],
                    booking_url=h.get("link", f"https://www.google.com/travel/hotels/{destination}"),
                    image_url=h.get("images", [{}])[0].get("thumbnail", "") if h.get("images") else "",
                    source="serpapi",
                    is_verified=True,
                )
            )
    except (CircuitOpenError, Exception) as e:
        logger.warning("SerpAPI hotels fallback: %s", e)

    # Fallback: Google Places
    if not options:
        try:
            raw = await _search_hotels_places(destination)
            for i, p in enumerate(raw[:10]):
                loc = p.get("geometry", {}).get("location", {})
                options.append(
                    HotelOption(
                        id=f"hotel-places-{i}",
                        name=p.get("name", ""),
                        hotel_type="hotel",
                        rating=p.get("rating", 0),
                        price_per_night=0,  # Places API doesn't give prices
                        total_price=0,
                        currency=currency,
                        location=p.get("formatted_address", destination),
                        latitude=loc.get("lat"),
                        longitude=loc.get("lng"),
                        place_id=p.get("place_id"),
                        booking_url=f"https://www.google.com/travel/hotels/{destination}",
                        source="google_places",
                        is_verified=True,
                    )
                )
        except Exception as e:
            logger.error("Google Places hotels error: %s", e)

    if options:
        cache_set("hotels", options, destination=destination, check_in=check_in)
    return options
