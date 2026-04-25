"""Export API routes — PDF and HTML download."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.export_service import render_itinerary_html, render_itinerary_pdf
from app.services.trip_service import get_trip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trips", tags=["export"])


@router.get("/{trip_id}/export/html")
async def export_html(
    trip_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Export trip itinerary as HTML."""
    trip = await get_trip(db, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    itinerary = trip.itinerary_json
    if isinstance(itinerary, str):
        itinerary = json.loads(itinerary)

    # Fallback: extract itinerary from state_json if dedicated column is empty
    if not itinerary and trip.state_json:
        full_state = json.loads(trip.state_json) if isinstance(trip.state_json, str) else trip.state_json
        itinerary = full_state.get("itinerary", {})

    if not itinerary:
        raise HTTPException(status_code=400, detail="No itinerary to export")

    budget = trip.budget_json
    if isinstance(budget, str):
        budget = json.loads(budget)

    # Fallback: extract budget from state_json
    if not budget and trip.state_json:
        full_state = json.loads(trip.state_json) if isinstance(trip.state_json, str) else trip.state_json
        budget = full_state.get("budget_breakdown", {})

    request_data = trip.request_json
    if isinstance(request_data, str):
        request_data = json.loads(request_data)

    context = {
        "trip_id": trip_id,
        "destination": request_data.get("destination", "") if isinstance(request_data, dict) else "",
        "duration_days": request_data.get("duration_days", 0) if isinstance(request_data, dict) else 0,
        "itinerary": itinerary,
        "budget": budget,
    }

    html = render_itinerary_html(context)
    return HTMLResponse(content=html)


@router.get("/{trip_id}/export/pdf")
async def export_pdf(
    trip_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Export trip itinerary as PDF."""
    trip = await get_trip(db, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    itinerary = trip.itinerary_json
    if isinstance(itinerary, str):
        itinerary = json.loads(itinerary)

    # Fallback: extract itinerary from state_json if dedicated column is empty
    if not itinerary and trip.state_json:
        full_state = json.loads(trip.state_json) if isinstance(trip.state_json, str) else trip.state_json
        itinerary = full_state.get("itinerary", {})

    if not itinerary:
        raise HTTPException(status_code=400, detail="No itinerary to export")

    budget = trip.budget_json
    if isinstance(budget, str):
        budget = json.loads(budget)

    # Fallback: extract budget from state_json
    if not budget and trip.state_json:
        full_state = json.loads(trip.state_json) if isinstance(trip.state_json, str) else trip.state_json
        budget = full_state.get("budget_breakdown", {})

    request_data = trip.request_json
    if isinstance(request_data, str):
        request_data = json.loads(request_data)

    context = {
        "trip_id": trip_id,
        "destination": request_data.get("destination", "") if isinstance(request_data, dict) else "",
        "duration_days": request_data.get("duration_days", 0) if isinstance(request_data, dict) else 0,
        "itinerary": itinerary,
        "budget": budget,
    }

    try:
        pdf_bytes = render_itinerary_pdf(context)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="trip_{trip_id[:8]}.pdf"',
            },
        )
    except Exception as e:
        logger.error("PDF generation failed: %s", e)
        raise HTTPException(status_code=500, detail="PDF generation failed. Try HTML export instead.")
