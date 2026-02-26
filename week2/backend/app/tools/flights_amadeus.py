"""Amadeus API fallback for flight search."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings
from app.models.booking import FlightOption
from app.services.cache import cache_get, cache_set
from app.tools.resilience import CircuitOpenError, resilient_api_call

logger = logging.getLogger(__name__)
settings = get_settings()

_access_token: str | None = None
_token_expires_at: float = 0.0


async def _get_amadeus_token(force_refresh: bool = False) -> str:
    """Obtain OAuth token from Amadeus, refreshing when expired."""
    global _access_token, _token_expires_at

    # Return cached token if still valid (with 60s safety margin)
    if _access_token and not force_refresh and time.time() < (_token_expires_at - 60):
        return _access_token

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://test.api.amadeus.com/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.AMADEUS_API_KEY,
                "client_secret": settings.AMADEUS_API_SECRET,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        _access_token = data["access_token"]
        # Amadeus returns expires_in in seconds (typically 1799)
        _token_expires_at = time.time() + data.get("expires_in", 1799)
        logger.info("Amadeus token refreshed, expires in %ds", data.get("expires_in", 1799))
        return _access_token


@resilient_api_call("amadeus_flights")
async def _search_amadeus(
    origin: str,
    destination: str,
    departure_date: str,
    adults: int = 1,
    currency: str = "INR",
) -> list[dict[str, Any]]:
    """Raw Amadeus flight offers search with automatic token refresh on 401."""
    token = await _get_amadeus_token()
    params = {
        "originLocationCode": origin,
        "destinationLocationCode": destination,
        "departureDate": departure_date,
        "adults": adults,
        "currencyCode": currency,
        "max": 10,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://test.api.amadeus.com/v2/shopping/flight-offers",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        # If 401, force-refresh token and retry once
        if resp.status_code == 401:
            logger.warning("Amadeus 401 — refreshing token and retrying")
            token = await _get_amadeus_token(force_refresh=True)
            resp = await client.get(
                "https://test.api.amadeus.com/v2/shopping/flight-offers",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        resp.raise_for_status()
        return resp.json().get("data", [])


async def search_flights_amadeus(
    origin: str,
    destination: str,
    departure_date: str,
    adults: int = 1,
    currency: str = "INR",
) -> list[FlightOption]:
    """Amadeus flight search with cache."""
    if not departure_date:
        logger.info("Skipping Amadeus flight search — no departure date provided")
        return []

    cached = cache_get(
        "flights_amadeus",
        origin=origin,
        destination=destination,
        date=departure_date,
    )
    if cached is not None:
        return cached

    options: list[FlightOption] = []
    try:
        raw = await _search_amadeus(origin, destination, departure_date, adults, currency)
        for i, offer in enumerate(raw[:10]):
            price = float(offer.get("price", {}).get("total", 0))
            segments = (
                offer.get("itineraries", [{}])[0].get("segments", [{}])
                if offer.get("itineraries")
                else [{}]
            )
            first_seg = segments[0] if segments else {}
            carrier = first_seg.get("carrierCode", "")
            dep_time = first_seg.get("departure", {}).get("at", "")
            arr_time = first_seg.get("arrival", {}).get("at", "")
            duration_str = offer.get("itineraries", [{}])[0].get("duration", "")

            # Parse ISO duration PT2H30M -> minutes
            dur_mins = 0
            if "H" in duration_str:
                h_part = duration_str.split("H")[0].replace("PT", "")
                dur_mins += int(h_part) * 60 if h_part.isdigit() else 0
            if "M" in duration_str:
                m_part = duration_str.split("M")[0].split("H")[-1].replace("PT", "")
                dur_mins += int(m_part) if m_part.isdigit() else 0

            options.append(
                FlightOption(
                    id=f"flight-amadeus-{i}",
                    mode="flight",
                    airline_or_operator=carrier,
                    departure_time=dep_time,
                    arrival_time=arr_time,
                    duration_minutes=dur_mins,
                    from_location=origin,
                    to_location=destination,
                    price=price,
                    currency=currency,
                    booking_url=f"https://www.google.com/travel/flights?q=flights+from+{origin}+to+{destination}",
                    source="amadeus",
                    is_verified=True,
                )
            )
    except CircuitOpenError:
        logger.warning("Amadeus circuit open")
    except Exception as e:
        logger.error("Amadeus flights error: %s", e)

    if options:
        cache_set(
            "flights_amadeus",
            options,
            origin=origin,
            destination=destination,
            date=departure_date,
        )
    return options
