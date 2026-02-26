"""Pydantic models for trip requests and responses."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TravelStyle(str, Enum):
    BACKPACKING = "backpacking"
    COMFORT = "comfort"
    LUXURY = "luxury"
    ADVENTURE = "adventure"
    SPIRITUAL = "spiritual"
    CULTURAL = "cultural"
    FAMILY = "family"
    ROMANTIC = "romantic"


class TravelerType(str, Enum):
    SOLO = "solo"
    COUPLE = "couple"
    FAMILY = "family"
    GROUP = "group"


class TripRequest(BaseModel):
    """Structured trip request parsed from user input."""

    destination: str = ""
    origin: str = ""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_days: int = 0
    budget: float = 0.0
    currency: str = "INR"
    traveler_type: TravelerType = TravelerType.SOLO
    traveler_count: int = 1
    children_count: int = 0
    styles: list[TravelStyle] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    raw_input: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(
            self.destination
            and self.origin
            and self.duration_days > 0
            and self.budget > 0
        )

    @property
    def is_international(self) -> bool:
        # Simple heuristic — proper implementation uses country lookup
        domestic_pairs = {
            ("india", "india"),
            ("us", "us"),
            ("usa", "usa"),
        }
        orig = self.origin.lower().strip()
        dest = self.destination.lower().strip()
        # If both are Indian cities, not international
        return not any(
            orig in pair and dest in pair for pair in domestic_pairs
        )


class PlanOption(BaseModel):
    """One of 2-3 plan options presented to the user."""

    id: str
    label: str  # e.g., "A: Balanced Adventure + Spiritual"
    style: str
    estimated_total: float
    currency: str = "INR"
    highlights: list[str] = Field(default_factory=list)
    trade_offs: str = ""  # "Cheaper but more travel time"
    is_recommended: bool = False


class TripStatus(str, Enum):
    GATHERING_INTENT = "gathering_intent"
    CHECKPOINT_1 = "checkpoint_1"
    RESEARCHING = "researching"
    PLANNING = "planning"
    CHECKPOINT_2 = "checkpoint_2"
    DETAILING = "detailing"
    VERIFYING = "verifying"
    OPTIMIZING = "optimizing"
    CHECKPOINT_3 = "checkpoint_3"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    READY = "ready"
    REPLANNING = "replanning"
    ERROR = "error"


class TripSummary(BaseModel):
    """Lightweight trip summary for list views."""

    id: str
    destination: str
    duration_days: int
    budget: float
    currency: str = "INR"
    status: TripStatus
    style: str = ""
    is_sample: bool = False
    created_at: str = ""


class ChatMessage(BaseModel):
    """A single chat message."""

    role: str  # "user" | "assistant" | "system"
    content: str
    metadata: Optional[dict] = None


class CheckpointDecision(BaseModel):
    """User's decision at a checkpoint."""

    checkpoint: str  # "cp1" | "cp2" | "cp3"
    action: str  # "approve" | "modify" | "select"
    selected_option_id: Optional[str] = None
    modifications: Optional[dict] = None
