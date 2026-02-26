"""Mock/estimated data generators — used as final fallback when all APIs fail."""

from __future__ import annotations

import logging
from datetime import datetime

from app.models.booking import FlightOption, HotelOption

logger = logging.getLogger(__name__)


def generate_mock_flights(
    origin: str,
    destination: str,
    departure_date: str,
    currency: str = "INR",
) -> list[FlightOption]:
    """Return a set of estimated flight options when live APIs are unavailable."""
    logger.info("Generating mock flight data for %s → %s", origin, destination)

    dep_dt = departure_date or datetime.today().strftime("%Y-%m-%d")
    booking_url = (
        f"https://www.google.com/travel/flights?q=flights+from+{origin}+to+{destination}"
    )

    # Rough domestic INR price tiers
    price_base = 3500.0 if currency == "INR" else 50.0

    options = [
        FlightOption(
            id="mock-flight-0",
            mode="flight",
            airline_or_operator="IndiGo",
            departure_time=f"{dep_dt}T06:00:00",
            arrival_time=f"{dep_dt}T08:30:00",
            duration_minutes=150,
            from_location=origin,
            to_location=destination,
            price=round(price_base * 0.9, 0),
            currency=currency,
            booking_url=booking_url,
            source="mock",
            is_verified=False,
        ),
        FlightOption(
            id="mock-flight-1",
            mode="flight",
            airline_or_operator="Air India",
            departure_time=f"{dep_dt}T10:15:00",
            arrival_time=f"{dep_dt}T12:55:00",
            duration_minutes=160,
            from_location=origin,
            to_location=destination,
            price=round(price_base * 1.1, 0),
            currency=currency,
            booking_url=booking_url,
            source="mock",
            is_verified=False,
        ),
        FlightOption(
            id="mock-flight-2",
            mode="flight",
            airline_or_operator="SpiceJet",
            departure_time=f"{dep_dt}T14:30:00",
            arrival_time=f"{dep_dt}T17:00:00",
            duration_minutes=150,
            from_location=origin,
            to_location=destination,
            price=round(price_base * 0.8, 0),
            currency=currency,
            booking_url=booking_url,
            source="mock",
            is_verified=False,
        ),
    ]
    return options


def generate_mock_hotels(
    destination: str,
    check_in: str,
    nights: int = 1,
    currency: str = "INR",
) -> list[HotelOption]:
    """Return estimated hotel options when live APIs are unavailable."""
    logger.info("Generating mock hotel data for %s", destination)

    booking_url = f"https://www.google.com/travel/hotels/{destination.replace(' ', '+')}"
    price_base = 1500.0 if currency == "INR" else 25.0

    options = [
        HotelOption(
            id="mock-hotel-0",
            name=f"Budget Stay {destination}",
            hotel_type="guesthouse",
            rating=3.5,
            price_per_night=round(price_base * 0.6, 0),
            total_price=round(price_base * 0.6 * nights, 0),
            currency=currency,
            location=destination,
            amenities=["WiFi", "Breakfast"],
            booking_url=booking_url,
            source="mock",
            is_verified=False,
        ),
        HotelOption(
            id="mock-hotel-1",
            name=f"Comfort Inn {destination}",
            hotel_type="hotel",
            rating=4.0,
            price_per_night=round(price_base, 0),
            total_price=round(price_base * nights, 0),
            currency=currency,
            location=destination,
            amenities=["WiFi", "AC", "Breakfast", "Parking"],
            booking_url=booking_url,
            source="mock",
            is_verified=False,
        ),
        HotelOption(
            id="mock-hotel-2",
            name=f"Premium Resort {destination}",
            hotel_type="resort",
            rating=4.5,
            price_per_night=round(price_base * 2.0, 0),
            total_price=round(price_base * 2.0 * nights, 0),
            currency=currency,
            location=destination,
            amenities=["WiFi", "AC", "Pool", "Spa", "Restaurant"],
            booking_url=booking_url,
            source="mock",
            is_verified=False,
        ),
    ]
    return options
