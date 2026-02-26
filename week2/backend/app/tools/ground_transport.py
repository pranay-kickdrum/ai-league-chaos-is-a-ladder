"""Ground transport (train & bus) search using Google Maps Distance + heuristic pricing."""

from __future__ import annotations

import logging
from typing import Any

from app.models.booking import FlightOption
from app.services.cache import cache_get, cache_set
from app.tools.maps import get_directions

logger = logging.getLogger(__name__)

# ── Price-per-km heuristics (INR) ──────────────────────────────────────────────

_TRAIN_CLASSES: list[dict[str, Any]] = [
    {"class_type": "sleeper",    "label": "Sleeper Class",  "rate_per_km": 0.55, "speed_factor": 1.0},
    {"class_type": "AC 3-tier",  "label": "AC 3 Tier",      "rate_per_km": 1.20, "speed_factor": 0.95},
    {"class_type": "AC 2-tier",  "label": "AC 2 Tier",      "rate_per_km": 1.80, "speed_factor": 0.95},
    {"class_type": "AC chair",   "label": "AC Chair Car",    "rate_per_km": 1.10, "speed_factor": 0.70},
]

_BUS_CLASSES: list[dict[str, Any]] = [
    {"class_type": "ordinary",    "label": "State Bus",       "rate_per_km": 0.80, "speed_factor": 1.3},
    {"class_type": "semi-sleeper","label": "Semi-Sleeper",    "rate_per_km": 1.30, "speed_factor": 1.1},
    {"class_type": "AC sleeper",  "label": "Volvo AC Sleeper","rate_per_km": 2.00, "speed_factor": 1.0},
]

# Currency multipliers relative to INR
_FX: dict[str, float] = {
    "INR": 1.0, "USD": 0.012, "EUR": 0.011, "GBP": 0.0095, "AUD": 0.018,
}


def _fx(currency: str) -> float:
    return _FX.get(currency, 1.0)


async def _get_road_distance(origin: str, destination: str) -> dict[str, Any]:
    """Get driving distance & duration between two cities via Google Maps."""
    cached = cache_get("road_distance", origin=origin, destination=destination)
    if cached is not None:
        return cached

    try:
        result = await get_directions(origin, destination, mode="driving")
        if result and result.get("distance_km", 0) > 0:
            cache_set("road_distance", result, origin=origin, destination=destination)
            return result
    except Exception as e:
        logger.warning("Google Maps distance failed: %s", e)

    return {"distance_km": 0, "duration_minutes": 0}


async def search_trains(
    origin: str,
    destination: str,
    departure_date: str,
    currency: str = "INR",
) -> list[FlightOption]:
    """Generate train options based on distance heuristics.

    Uses Google Maps for road distance, and applies typical Indian Railways
    pricing per class.  Train distance is approximated as 1.1× road distance
    (rail routes are usually slightly longer).
    """
    cached = cache_get("trains", origin=origin, destination=destination, date=departure_date)
    if cached is not None:
        return cached

    road = await _get_road_distance(origin, destination)
    distance_km = road.get("distance_km", 0)
    road_duration = road.get("duration_minutes", 0)

    if distance_km <= 0:
        logger.info("No distance data for %s → %s; skipping trains", origin, destination)
        return []

    # Skip trains for very short (<50 km) or very long (>2500 km) distances
    if distance_km < 50 or distance_km > 2500:
        logger.info("Distance %.0f km not suitable for trains (%s → %s)", distance_km, origin, destination)
        return []

    rail_distance = distance_km * 1.1  # Rail routes ~10% longer
    fx = _fx(currency)

    # Typical train speed: 50-65 km/h average for Indian Railways
    base_speed_kmh = 55

    options: list[FlightOption] = []
    for i, cls in enumerate(_TRAIN_CLASSES):
        effective_speed = base_speed_kmh / cls["speed_factor"]
        duration = int(rail_distance / effective_speed * 60)
        price = round(rail_distance * cls["rate_per_km"] * fx, 0)

        # Time-based departure slots
        dep_hour = 6 + (i * 4)  # 06:00, 10:00, 14:00, 18:00
        arr_hours = duration / 60
        arr_hour = int((dep_hour + arr_hours) % 24)
        arr_min = int((arr_hours % 1) * 60)

        booking_url = f"https://www.irctc.co.in/nget/train-search?from={origin}&to={destination}&date={departure_date}"

        options.append(FlightOption(
            id=f"train-{i}",
            mode="train",
            airline_or_operator=f"Indian Railways — {cls['label']}",
            departure_time=f"{departure_date}T{dep_hour:02d}:00:00",
            arrival_time=f"{departure_date}T{arr_hour:02d}:{arr_min:02d}:00",
            duration_minutes=duration,
            from_location=origin,
            to_location=destination,
            price=price,
            currency=currency,
            booking_url=booking_url,
            source="estimated",
            is_verified=False,
            class_type=cls["class_type"],
        ))

    if options:
        cache_set("trains", options, origin=origin, destination=destination, date=departure_date)

    return options


async def search_buses(
    origin: str,
    destination: str,
    departure_date: str,
    currency: str = "INR",
) -> list[FlightOption]:
    """Generate bus options based on distance heuristics.

    Uses Google Maps for road distance and applies typical Indian bus
    pricing per class.
    """
    cached = cache_get("buses", origin=origin, destination=destination, date=departure_date)
    if cached is not None:
        return cached

    road = await _get_road_distance(origin, destination)
    distance_km = road.get("distance_km", 0)
    road_duration = road.get("duration_minutes", 0)

    if distance_km <= 0:
        logger.info("No distance data for %s → %s; skipping buses", origin, destination)
        return []

    # Skip buses for very long routes (>1200 km)
    if distance_km > 1200:
        logger.info("Distance %.0f km too long for buses (%s → %s)", distance_km, origin, destination)
        return []

    fx = _fx(currency)

    # Bus speed: ~40-55 km/h average
    base_speed_kmh = 45

    options: list[FlightOption] = []
    for i, cls in enumerate(_BUS_CLASSES):
        effective_speed = base_speed_kmh / cls["speed_factor"]
        duration = int(distance_km / effective_speed * 60)
        # Use actual road duration if available and reasonable
        if road_duration > 0:
            duration = max(duration, int(road_duration * cls["speed_factor"]))
        price = round(distance_km * cls["rate_per_km"] * fx, 0)

        # Departure slots
        dep_hour = 7 + (i * 5)  # 07:00, 12:00, 17:00
        arr_hours = duration / 60
        arr_hour = int((dep_hour + arr_hours) % 24)
        arr_min = int((arr_hours % 1) * 60)

        booking_url = f"https://www.redbus.in/bus-tickets/{origin.lower().replace(' ', '-')}-to-{destination.lower().replace(' ', '-')}"

        options.append(FlightOption(
            id=f"bus-{i}",
            mode="bus",
            airline_or_operator=cls["label"],
            departure_time=f"{departure_date}T{dep_hour:02d}:00:00",
            arrival_time=f"{departure_date}T{arr_hour:02d}:{arr_min:02d}:00",
            duration_minutes=duration,
            from_location=origin,
            to_location=destination,
            price=price,
            currency=currency,
            booking_url=booking_url,
            source="estimated",
            is_verified=False,
            class_type=cls["class_type"],
        ))

    if options:
        cache_set("buses", options, origin=origin, destination=destination, date=departure_date)

    return options
