"""Application configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings
from functools import lru_cache

# Resolve .env relative to this file's location (backend/.env)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Central config loaded from .env file."""

    # --- App ---
    APP_NAME: str = "TripCraft"
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # --- LLM (Tiered) ---
    OPENAI_API_KEY: str = ""
    LLM_MODEL_REASONING: str = "gpt-4o"       # intent parsing, re-planning
    LLM_MODEL_NARRATION: str = "gpt-4o-mini"   # narration, descriptions

    # --- SerpAPI ---
    SERPAPI_API_KEY: str = ""

    # --- Google ---
    GOOGLE_MAPS_API_KEY: str = ""
    GOOGLE_PLACES_API_KEY: str = ""

    # --- Amadeus ---
    AMADEUS_API_KEY: str = ""
    AMADEUS_API_SECRET: str = ""

    # --- Weather ---
    OPENWEATHER_API_KEY: str = ""

    # --- Currency ---
    EXCHANGERATE_API_KEY: str = ""

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./tripcraft.db"

    # --- Cache ---
    CACHE_TTL_SECONDS: int = 3600  # 1 hour
    CACHE_MAX_SIZE: int = 512

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
