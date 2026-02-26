"""Pydantic models for booking items."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:
    from app.models.itinerary import Itinerary


class FlightOption(BaseModel):
    """A flight/train option."""

    id: str
    mode: str = "flight"  # "flight", "train", "bus"
    airline_or_operator: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    duration_minutes: int = 0
    from_location: str = ""
    to_location: str = ""
    price: float = 0.0
    currency: str = "INR"
    booking_url: str = ""
    source: str = ""  # "serpapi", "amadeus", "cached"
    is_verified: bool = False
    class_type: str = ""  # "economy", "business", "sleeper", "AC"


class HotelOption(BaseModel):
    """A hotel/stay option."""

    id: str
    name: str
    hotel_type: str = ""  # "hotel", "hostel", "resort", "homestay"
    rating: float = 0.0
    price_per_night: float = 0.0
    total_price: float = 0.0
    currency: str = "INR"
    location: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    amenities: list[str] = Field(default_factory=list)
    booking_url: str = ""
    image_url: str = ""
    place_id: Optional[str] = None
    source: str = ""
    is_verified: bool = False
    reasoning: str = ""


class ActivityOption(BaseModel):
    """A bookable activity."""

    id: str
    name: str
    description: str = ""
    category: str = ""
    price: float = 0.0
    currency: str = "INR"
    duration_minutes: int = 0
    booking_url: str = ""
    location: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rating: float = 0.0
    place_id: Optional[str] = None
    source: str = ""
    is_verified: bool = False


class BudgetBreakdown(BaseModel):
    """Budget allocation and tracking."""

    transport: float = 0.0
    accommodation: float = 0.0
    food: float = 0.0
    activities: float = 0.0
    buffer: float = 0.0
    currency: str = "INR"
    traveler_count: int = 1

    @computed_field
    @property
    def total(self) -> float:
        return (
            self.transport
            + self.accommodation
            + self.food
            + self.activities
            + self.buffer
        )

    @computed_field
    @property
    def per_person_total(self) -> float:
        count = max(self.traveler_count, 1)
        return round(self.total / count, 2) if count > 1 else self.total


class BookingItem(BaseModel):
    """A single item in the booking cart."""

    id: str
    category: str  # "flight", "hotel", "activity"
    name: str
    price: float
    currency: str = "INR"
    booking_url: str = ""
    is_booked: bool = False
    notes: str = ""


class BookingCart(BaseModel):
    """Complete booking cart for final checkout."""

    items: list[BookingItem] = Field(default_factory=list)
    total: float = 0.0
    currency: str = "INR"
    budget_limit: float = 0.0
    remaining: float = 0.0


class MapMarker(BaseModel):
    """A marker to display on the map."""

    label: str
    latitude: float
    longitude: float
    day_number: int = 0
    category: str = ""  # "stay", "activity", "food", "transport"
    color: str = ""


class MapRoute(BaseModel):
    """A route segment for the map."""

    from_lat: float
    from_lng: float
    to_lat: float
    to_lng: float
    day_number: int = 0
    mode: str = "driving"


class TripPackage(BaseModel):
    """Final complete trip output."""

    trip_id: str
    destination: str
    duration_days: int
    budget: float
    currency: str = "INR"
    style: str = ""
    itinerary: Any = None  # Itinerary object — avoids circular import
    budget_breakdown: Optional[BudgetBreakdown] = None
    booking_cart: Optional[BookingCart] = None
    markers: list[MapMarker] = Field(default_factory=list)
    routes: list[MapRoute] = Field(default_factory=list)
    reasoning_log: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
