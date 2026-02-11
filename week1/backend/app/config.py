"""Application configuration loaded from environment variables."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


# Find .env file - check multiple locations
def _find_env_file() -> Path | None:
    """Search for .env file in multiple locations."""
    candidates = [
        Path(".env"),  # Current directory
        Path(__file__).resolve().parent.parent / ".env",  # backend/.env
        Path(__file__).resolve().parent.parent.parent / ".env",  # week1/.env
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


_env_file = _find_env_file()

# Determine project root (week1/ directory)
# This file is at: week1/backend/app/config.py
_project_root = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # --- API Keys ---
    openai_api_key: str = ""
    tavily_api_key: str = ""

    # --- LLM ---
    llm_model: str = "gpt-4o"
    fast_llm_model: str = "gpt-4o-mini"

    # --- Embedding ---
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # --- ChromaDB ---
    # Use absolute path to always point to week1/data/chroma_db
    chroma_persist_dir: str = str(_project_root / "data" / "chroma_db")
    chroma_collection_name: str = "knowledge_base"

    # --- Retrieval ---
    dense_top_k: int = 20
    bm25_top_k: int = 20
    rerank_top_k: int = 5
    rrf_k: int = 60

    # --- Agentic ---
    max_retrieval_rounds: int = 3

    # --- Web search ---
    web_search_max_results: int = 5
    web_cache_ttl_seconds: int = 3600  # 1 hour

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {
        "env_file": str(_env_file) if _env_file else ".env",
        "env_file_encoding": "utf-8"
    }


settings = Settings()
