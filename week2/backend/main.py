"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.export import router as export_router
from app.api.trips import router as trips_router
from app.db.database import async_session, init_db
from app.db.seed import seed_sample_trips

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TripCraft API",
    description="AI-powered travel planning and booking agent",
    version="0.1.0",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(trips_router)
app.include_router(export_router)


@app.on_event("startup")
async def on_startup():
    """Initialize database and seed sample trips on startup."""
    logger.info("Starting TripCraft API...")
    await init_db()
    async with async_session() as session:
        await seed_sample_trips(session)
    logger.info("TripCraft API ready.")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "tripcraft"}
