"""Trip service — orchestrates trip creation, state persistence, CRUD."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TripRow
from app.models.trip import ChatMessage, CheckpointDecision, TripRequest, TripStatus, TripSummary

logger = logging.getLogger(__name__)


async def create_trip(session: AsyncSession, trip_id: str, request: TripRequest | str = "") -> TripRow:
    """Create a new trip record."""
    if isinstance(request, TripRequest):
        request_data = request.model_dump(mode="json")
    elif isinstance(request, str):
        request_data = {"raw_input": request}
    else:
        request_data = {"raw_input": str(request)}
    row = TripRow(
        id=trip_id,
        status=TripStatus.GATHERING_INTENT.value,
        request_json=json.dumps(request_data, default=str),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_trip(session: AsyncSession, trip_id: str) -> TripRow | None:
    """Fetch a trip by id."""
    result = await session.execute(select(TripRow).where(TripRow.id == trip_id))
    return result.scalar_one_or_none()


async def list_trips(session: AsyncSession, include_samples: bool = True) -> list[TripSummary]:
    """List all trips as summaries."""
    query = select(TripRow).order_by(TripRow.created_at.desc())
    if not include_samples:
        query = query.where(TripRow.is_sample == False)  # noqa: E712
    result = await session.execute(query)
    rows = result.scalars().all()

    summaries = []
    for row in rows:
        req = json.loads(row.request_json) if row.request_json else {}
        summaries.append(
            TripSummary(
                id=row.id,
                destination=req.get("destination", ""),
                duration_days=req.get("duration_days", 0),
                budget=req.get("budget", 0),
                currency=req.get("currency", "INR"),
                status=TripStatus(row.status) if row.status else TripStatus.GATHERING_INTENT,
                style=", ".join(req.get("styles", [])),
                is_sample=row.is_sample or False,
                created_at=str(row.created_at or ""),
            )
        )
    return summaries


async def update_trip_state(
    session: AsyncSession,
    trip_id: str,
    *,
    status: str | None = None,
    last_checkpoint: str | None = None,
    request_json: str | None = None,
    state_json: str | None = None,
    research_json: str | None = None,
    itinerary_json: str | None = None,
    budget_json: str | None = None,
) -> None:
    """Update specific fields of a trip."""
    row = await get_trip(session, trip_id)
    if row is None:
        logger.error("Trip %s not found for update", trip_id)
        return

    if status is not None:
        row.status = status
    if last_checkpoint is not None:
        row.last_checkpoint = last_checkpoint
    if request_json is not None:
        row.request_json = request_json
    if state_json is not None:
        row.state_json = state_json
    if research_json is not None:
        row.research_json = research_json
    if itinerary_json is not None:
        row.itinerary_json = itinerary_json
    if budget_json is not None:
        row.budget_json = budget_json

    row.updated_at = datetime.now(timezone.utc)
    await session.commit()


async def get_trip_full(session: AsyncSession, trip_id: str) -> dict | None:
    """Get full trip data as dict."""
    row = await get_trip(session, trip_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "status": row.status,
        "last_checkpoint": row.last_checkpoint,
        "is_sample": row.is_sample,
        "request": json.loads(row.request_json) if row.request_json else {},
        "state": json.loads(row.state_json) if row.state_json else {},
        "research": json.loads(row.research_json) if row.research_json else {},
        "itinerary": json.loads(row.itinerary_json) if row.itinerary_json else {},
        "budget": json.loads(row.budget_json) if row.budget_json else {},
        "created_at": str(row.created_at or ""),
        "updated_at": str(row.updated_at or ""),
    }
