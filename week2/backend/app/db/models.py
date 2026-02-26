"""SQLAlchemy ORM models."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class TripRow(Base):
    """Persisted trip record."""

    __tablename__ = "trips"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    status = Column(String, default="gathering_intent")
    last_checkpoint = Column(String, nullable=True)
    is_sample = Column(Boolean, default=False)
    request_json = Column(Text, default="{}")
    state_json = Column(Text, default="{}")
    research_json = Column(Text, default="{}")
    itinerary_json = Column(Text, default="{}")
    budget_json = Column(Text, default="{}")
