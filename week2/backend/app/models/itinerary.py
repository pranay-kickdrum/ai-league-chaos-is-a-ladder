"""Pydantic models for itinerary structures."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TimeSlot(BaseModel):
    """A time window within a day."""

    start: str  # "09:00"
    end: str  # "11:30"
    duration_minutes: int = 0


class Activity(BaseModel):
    """A single activity in the itinerary."""

    id: str
    name: str
    description: str = ""
    category: str = ""  # "adventure", "cultural", "food", "transport", "accommodation"
    time_slot: Optional[TimeSlot] = None
    location: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    cost: float = 0.0
    currency: str = "INR"
    booking_url: Optional[str] = None
    maps_url: Optional[str] = None
    place_id: Optional[str] = None  # Google Places ID for verification
    is_verified: bool = False
    is_optional: bool = False
    research_result_id: Optional[str] = None  # anti-hallucination: link to research data
    reasoning: str = ""  # "Why this activity?"
    tips: list[str] = Field(default_factory=list)


class TransportLeg(BaseModel):
    """Transport between two points."""

    mode: str  # "train", "flight", "bus", "taxi", "walk", "auto"
    from_location: str
    to_location: str
    duration_minutes: int = 0
    cost: float = 0.0
    currency: str = "INR"
    booking_url: Optional[str] = None
    notes: str = ""


class MealSuggestion(BaseModel):
    """A meal / restaurant suggestion."""

    meal_type: str  # "breakfast", "lunch", "dinner", "snack"
    name: str
    cuisine: str = ""
    cost_estimate: float = 0.0
    currency: str = "INR"
    location: str = ""
    maps_url: Optional[str] = None
    place_id: Optional[str] = None
    is_verified: bool = False


class DayPlan(BaseModel):
    """Itinerary for a single day."""

    day_number: int
    date: Optional[str] = None
    title: str = ""  # "Day 1 – Travel + Spiritual Evening"
    description: str = ""
    activities: list[Activity] = Field(default_factory=list)
    transport: list[TransportLeg] = Field(default_factory=list)
    meals: list[MealSuggestion] = Field(default_factory=list)
    accommodation: Optional[Activity] = None
    day_cost: float = 0.0
    weather_summary: str = ""
    notes: list[str] = Field(default_factory=list)


class Itinerary(BaseModel):
    """Complete day-by-day itinerary."""

    days: list[DayPlan] = Field(default_factory=list)
    total_cost: float = 0.0
    currency: str = "INR"
    destination: str = ""
    duration_days: int = 0
    summary: str = ""
    selected_flight: Optional[dict] = None  # selected transport (any mode)
    selected_hotel: Optional[dict] = None
    transport: list[TransportLeg] = Field(default_factory=list)
    transport_alternatives: Optional[dict] = None  # mode -> best option per mode
