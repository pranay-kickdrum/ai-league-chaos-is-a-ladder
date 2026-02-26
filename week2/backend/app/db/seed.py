"""Seed the database with pre-baked sample trips for demo reliability."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TripRow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sample trip data — full itinerary, budget, booking links
# ---------------------------------------------------------------------------

SAMPLE_TRIPS: list[dict] = [
    {
        "id": "sample-rishikesh-solo",
        "status": "ready",
        "last_checkpoint": "cp3",
        "is_sample": True,
        "request_json": json.dumps(
            {
                "destination": "Rishikesh",
                "origin": "Delhi",
                "duration_days": 4,
                "budget": 15000,
                "currency": "INR",
                "traveler_type": "solo",
                "traveler_count": 1,
                "styles": ["backpacking", "adventure", "spiritual"],
                "interests": ["adventure sports", "spiritual experiences"],
                "raw_input": "Plan a 4-day solo backpacking trip to Rishikesh under ₹15,000. I love adventure sports and spiritual experiences. Traveling from Delhi next weekend.",
            }
        ),
        "itinerary_json": json.dumps(
            {
                "destination": "Rishikesh",
                "duration_days": 4,
                "currency": "INR",
                "total_cost": 12500,
                "summary": "4-day solo backpacking trip blending adventure sports with spiritual experiences in Rishikesh.",
                "days": [
                    {
                        "day_number": 1,
                        "title": "Day 1 – Travel + Spiritual Evening",
                        "description": "Journey from Delhi to Rishikesh and soak in the spiritual vibes with an evening Ganga Aarti.",
                        "activities": [
                            {
                                "id": "a1",
                                "name": "Train Delhi → Haridwar",
                                "category": "transport",
                                "cost": 450,
                                "booking_url": "https://www.irctc.co.in/",
                                "is_verified": True,
                            },
                            {
                                "id": "a2",
                                "name": "Shared cab Haridwar → Rishikesh",
                                "category": "transport",
                                "cost": 250,
                                "is_verified": True,
                            },
                            {
                                "id": "a3",
                                "name": "Check-in Zostel Rishikesh",
                                "category": "accommodation",
                                "cost": 1200,
                                "booking_url": "https://www.zostel.com/",
                                "is_verified": True,
                            },
                            {
                                "id": "a4",
                                "name": "Ganga Aarti at Triveni Ghat",
                                "category": "cultural",
                                "cost": 0,
                                "maps_url": "https://maps.google.com/?q=Triveni+Ghat+Rishikesh",
                                "is_verified": True,
                            },
                        ],
                        "day_cost": 2200,
                    },
                    {
                        "day_number": 2,
                        "title": "Day 2 – Adventure Day",
                        "description": "Adrenaline-pumping white water rafting and optional cliff jumping.",
                        "activities": [
                            {
                                "id": "a5",
                                "name": "White Water Rafting (16km)",
                                "category": "adventure",
                                "cost": 1500,
                                "booking_url": "https://www.thrillophilia.com/",
                                "is_verified": True,
                            },
                            {
                                "id": "a6",
                                "name": "Cliff Jumping",
                                "category": "adventure",
                                "cost": 400,
                                "is_optional": True,
                                "is_verified": True,
                            },
                            {
                                "id": "a7",
                                "name": "Evening walk – Lakshman Jhula",
                                "category": "cultural",
                                "cost": 0,
                                "maps_url": "https://maps.google.com/?q=Lakshman+Jhula",
                                "is_verified": True,
                            },
                        ],
                        "day_cost": 2700,
                    },
                    {
                        "day_number": 3,
                        "title": "Day 3 – Trek + Culture",
                        "description": "A mix of nature trekking and cultural immersion.",
                        "activities": [
                            {
                                "id": "a8",
                                "name": "Neer Garh Waterfall Trek",
                                "category": "adventure",
                                "cost": 50,
                                "maps_url": "https://maps.google.com/?q=Neer+Garh+Waterfall",
                                "is_verified": True,
                            },
                            {
                                "id": "a9",
                                "name": "Beatles Ashram",
                                "category": "cultural",
                                "cost": 150,
                                "maps_url": "https://maps.google.com/?q=Beatles+Ashram",
                                "is_verified": True,
                            },
                            {
                                "id": "a10",
                                "name": "Evening Yoga at Parmarth Niketan",
                                "category": "spiritual",
                                "cost": 300,
                                "is_verified": True,
                            },
                        ],
                        "day_cost": 2600,
                    },
                    {
                        "day_number": 4,
                        "title": "Day 4 – Sunrise + Return",
                        "description": "Catch a breathtaking sunrise at Kunjapuri Temple before heading back to Delhi.",
                        "activities": [
                            {
                                "id": "a11",
                                "name": "Sunrise at Kunjapuri Temple",
                                "category": "spiritual",
                                "cost": 600,
                                "maps_url": "https://maps.google.com/?q=Kunjapuri+Temple",
                                "is_verified": True,
                            },
                            {
                                "id": "a12",
                                "name": "Return Rishikesh → Delhi",
                                "category": "transport",
                                "cost": 600,
                                "booking_url": "https://www.irctc.co.in/",
                                "is_verified": True,
                            },
                        ],
                        "day_cost": 2000,
                    },
                ],
            }
        ),
        "budget_json": json.dumps(
            {
                "travel": 1300,
                "stay": 3600,
                "food": 2500,
                "activities": 2400,
                "local_transport": 800,
                "entry_fees": 200,
                "buffer": 1700,
                "misc": 0,
                "currency": "INR",
            }
        ),
    },
    {
        "id": "sample-goa-family",
        "status": "ready",
        "last_checkpoint": "cp3",
        "is_sample": True,
        "request_json": json.dumps(
            {
                "destination": "Goa",
                "origin": "Mumbai",
                "duration_days": 5,
                "budget": 60000,
                "currency": "INR",
                "traveler_type": "family",
                "traveler_count": 4,
                "children_count": 2,
                "styles": ["comfort", "family"],
                "interests": ["beach", "water sports", "sightseeing"],
                "raw_input": "5-day family trip with 2 kids to Goa, comfort priority, budget ₹60,000 from Mumbai.",
            }
        ),
        "itinerary_json": json.dumps(
            {
                "destination": "Goa",
                "duration_days": 5,
                "currency": "INR",
                "total_cost": 52000,
                "summary": "5-day family vacation in Goa with kid-friendly beaches, water sports, and cultural sightseeing.",
                "days": [
                    {
                        "day_number": 1,
                        "title": "Day 1 – Arrival + Beach",
                        "description": "Fly in from Mumbai and unwind at Calangute Beach.",
                        "activities": [
                            {"id": "g1", "name": "Flight Mumbai → Goa", "category": "transport", "cost": 8000, "is_verified": True},
                            {"id": "g2", "name": "Check-in Resort", "category": "accommodation", "cost": 4000, "is_verified": True},
                            {"id": "g3", "name": "Calangute Beach", "category": "leisure", "cost": 0, "is_verified": True},
                        ],
                        "day_cost": 14000,
                    },
                    {
                        "day_number": 2,
                        "title": "Day 2 – Water Sports",
                        "description": "Family-friendly water sports at Baga Beach.",
                        "activities": [
                            {"id": "g4", "name": "Parasailing & Banana Ride", "category": "adventure", "cost": 3000, "is_verified": True},
                            {"id": "g5", "name": "Dolphin Watching Cruise", "category": "leisure", "cost": 2000, "is_verified": True},
                        ],
                        "day_cost": 8000,
                    },
                    {
                        "day_number": 3,
                        "title": "Day 3 – Heritage Tour",
                        "description": "Old Goa churches and Panjim stroll.",
                        "activities": [
                            {"id": "g6", "name": "Basilica of Bom Jesus", "category": "cultural", "cost": 0, "is_verified": True},
                            {"id": "g7", "name": "Panjim Latin Quarter walk", "category": "cultural", "cost": 0, "is_verified": True},
                        ],
                        "day_cost": 5000,
                    },
                    {
                        "day_number": 4,
                        "title": "Day 4 – South Goa",
                        "description": "Tranquil beaches and spice plantation.",
                        "activities": [
                            {"id": "g8", "name": "Palolem Beach", "category": "leisure", "cost": 0, "is_verified": True},
                            {"id": "g9", "name": "Spice Plantation Tour", "category": "cultural", "cost": 1500, "is_verified": True},
                        ],
                        "day_cost": 6000,
                    },
                    {
                        "day_number": 5,
                        "title": "Day 5 – Departure",
                        "description": "Morning at market and return flight.",
                        "activities": [
                            {"id": "g10", "name": "Mapusa Market", "category": "shopping", "cost": 1000, "is_verified": True},
                            {"id": "g11", "name": "Flight Goa → Mumbai", "category": "transport", "cost": 8000, "is_verified": True},
                        ],
                        "day_cost": 11000,
                    },
                ],
            }
        ),
        "budget_json": json.dumps(
            {
                "travel": 16000,
                "stay": 16000,
                "food": 10000,
                "activities": 6500,
                "local_transport": 3000,
                "entry_fees": 500,
                "buffer": 8000,
                "misc": 0,
                "currency": "INR",
            }
        ),
    },
    {
        "id": "sample-coorg-weekend",
        "status": "ready",
        "last_checkpoint": "cp3",
        "is_sample": True,
        "request_json": json.dumps(
            {
                "destination": "Coorg",
                "origin": "Bangalore",
                "duration_days": 2,
                "budget": 8000,
                "currency": "INR",
                "traveler_type": "solo",
                "traveler_count": 1,
                "styles": ["comfort"],
                "interests": ["nature", "coffee plantations", "trekking"],
                "raw_input": "2-day quick escape from Bangalore to Coorg under ₹8,000.",
            }
        ),
        "itinerary_json": json.dumps(
            {
                "destination": "Coorg",
                "duration_days": 2,
                "currency": "INR",
                "total_cost": 6500,
                "summary": "A relaxing 2-day weekend getaway to Coorg with coffee plantations and light trekking.",
                "days": [
                    {
                        "day_number": 1,
                        "title": "Day 1 – Drive + Explore",
                        "description": "Drive from Bangalore, visit Abbey Falls and coffee plantation.",
                        "activities": [
                            {"id": "c1", "name": "Drive Bangalore → Coorg", "category": "transport", "cost": 800, "is_verified": True},
                            {"id": "c2", "name": "Check-in Homestay", "category": "accommodation", "cost": 1500, "is_verified": True},
                            {"id": "c3", "name": "Abbey Falls", "category": "nature", "cost": 50, "is_verified": True},
                            {"id": "c4", "name": "Coffee Plantation Tour", "category": "cultural", "cost": 300, "is_verified": True},
                        ],
                        "day_cost": 3650,
                    },
                    {
                        "day_number": 2,
                        "title": "Day 2 – Trek + Return",
                        "description": "Morning trek at Tadiandamol, then return drive.",
                        "activities": [
                            {"id": "c5", "name": "Tadiandamol Trek", "category": "adventure", "cost": 200, "is_verified": True},
                            {"id": "c6", "name": "Raja's Seat viewpoint", "category": "nature", "cost": 50, "is_verified": True},
                            {"id": "c7", "name": "Drive Coorg → Bangalore", "category": "transport", "cost": 800, "is_verified": True},
                        ],
                        "day_cost": 2350,
                    },
                ],
            }
        ),
        "budget_json": json.dumps(
            {
                "travel": 1600,
                "stay": 1500,
                "food": 1200,
                "activities": 600,
                "local_transport": 400,
                "entry_fees": 100,
                "buffer": 1100,
                "misc": 0,
                "currency": "INR",
            }
        ),
    },
]


async def seed_sample_trips(session: AsyncSession) -> None:
    """Insert sample trips if they don't already exist."""
    for trip_data in SAMPLE_TRIPS:
        existing = await session.execute(
            select(TripRow).where(TripRow.id == trip_data["id"])
        )
        if existing.scalar_one_or_none() is None:
            row = TripRow(**trip_data)
            session.add(row)
            logger.info("Seeded sample trip: %s", trip_data["id"])

    await session.commit()
