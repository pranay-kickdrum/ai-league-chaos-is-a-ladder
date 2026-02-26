"""Travel advisory / visa requirements wrapper."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.cache import cache_get, cache_set
from app.tools.resilience import resilient_api_call

logger = logging.getLogger(__name__)

# Country name → ISO code mapping (subset for common use)
COUNTRY_CODES: dict[str, str] = {
    "india": "IN", "japan": "JP", "thailand": "TH", "singapore": "SG",
    "indonesia": "ID", "malaysia": "MY", "vietnam": "VN", "nepal": "NP",
    "sri lanka": "LK", "maldives": "MV", "uae": "AE", "dubai": "AE",
    "usa": "US", "united states": "US", "uk": "GB", "united kingdom": "GB",
    "france": "FR", "germany": "DE", "italy": "IT", "spain": "ES",
    "australia": "AU", "new zealand": "NZ", "canada": "CA", "mexico": "MX",
    "brazil": "BR", "south korea": "KR", "china": "CN", "turkey": "TR",
    "egypt": "EG", "south africa": "ZA", "kenya": "KE", "morocco": "MA",
    "greece": "GR", "portugal": "PT", "switzerland": "CH", "austria": "AT",
    "netherlands": "NL", "belgium": "BE", "sweden": "SE", "norway": "NO",
    "denmark": "DK", "finland": "FI", "ireland": "IE", "russia": "RU",
}

# City → Country mapping (common destinations)
CITY_COUNTRY: dict[str, str] = {
    "delhi": "india", "mumbai": "india", "bangalore": "india", "chennai": "india",
    "kolkata": "india", "hyderabad": "india", "pune": "india", "jaipur": "india",
    "goa": "india", "rishikesh": "india", "coorg": "india", "manali": "india",
    "shimla": "india", "udaipur": "india", "varanasi": "india", "agra": "india",
    "tokyo": "japan", "osaka": "japan", "kyoto": "japan",
    "bangkok": "thailand", "phuket": "thailand", "chiang mai": "thailand",
    "bali": "indonesia", "singapore": "singapore",
    "kuala lumpur": "malaysia", "hanoi": "vietnam",
    "paris": "france", "london": "uk", "rome": "italy",
    "new york": "usa", "los angeles": "usa", "san francisco": "usa",
    "sydney": "australia", "melbourne": "australia",
    "dubai": "uae", "abu dhabi": "uae",
    "kathmandu": "nepal", "colombo": "sri lanka", "male": "maldives",
}


def _get_country(city_or_country: str) -> str | None:
    """Resolve a city or country name to a country name."""
    lower = city_or_country.lower().strip()
    if lower in COUNTRY_CODES:
        return lower
    return CITY_COUNTRY.get(lower)


def is_international(origin: str, destination: str) -> bool:
    """Check if a trip is international."""
    orig_country = _get_country(origin)
    dest_country = _get_country(destination)
    if orig_country is None or dest_country is None:
        return True  # Assume international if we can't determine
    return orig_country != dest_country


@resilient_api_call("travel_advisory")
async def _fetch_advisory(country_code: str) -> dict[str, Any]:
    """Fetch travel advisory from API."""
    url = f"https://www.travel-advisory.info/api?countrycode={country_code}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        country_data = data.get(country_code, {})
        advisory = country_data.get("advisory", {})
        return {
            "score": advisory.get("score", 0),
            "message": advisory.get("message", ""),
        }


async def get_travel_advisory(
    origin: str,
    destination: str,
) -> dict[str, Any]:
    """Get travel advisory + visa info for a destination."""
    if not is_international(origin, destination):
        return {"is_international": False, "advisory": None, "visa_info": None}

    cached = cache_get("advisory", origin=origin, destination=destination)
    if cached is not None:
        return cached

    dest_country = _get_country(destination)
    dest_code = COUNTRY_CODES.get(dest_country, "") if dest_country else ""

    result: dict[str, Any] = {
        "is_international": True,
        "destination_country": dest_country,
        "destination_code": dest_code,
        "advisory": None,
        "visa_info": "Please check visa requirements for your nationality.",
    }

    if dest_code:
        try:
            result["advisory"] = await _fetch_advisory(dest_code)
        except Exception as e:
            logger.error("Travel advisory error: %s", e)

    cache_set("advisory", result, origin=origin, destination=destination)
    return result
