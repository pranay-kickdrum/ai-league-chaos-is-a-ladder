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

    # --- Data Freshness (Phase 2) ---
    # TTL (in days) for different content types
    ttl_news_articles: int = 30
    ttl_wikipedia: int = 90
    ttl_fact_checks: int = 0  # Never expire (historical record)
    ttl_government_data: int = 180

    # Update intervals
    rss_feed_check_hours: int = 24  # Check daily
    wikipedia_update_days: int = 7  # Update weekly
    cleanup_check_hours: int = 24  # Daily cleanup

    # RSS feeds to monitor
    rss_feeds: list[str] = [
        "https://feeds.reuters.com/reuters/topNews",
        "https://www.ap.org/rss",
        "https://feeds.bbci.co.uk/news/rss.xml",
    ]

    # Top Wikipedia topics to monitor (political/current events)
    wikipedia_topics: list[str] = [
        "Joe_Biden", "Donald_Trump", "Climate_change", "COVID-19_pandemic",
        "Artificial_intelligence", "Ukraine", "Israel", "Gaza_Strip",
        "United_States_Congress", "Supreme_Court_of_the_United_States",
        "Federal_Reserve", "Inflation", "Recession", "Immigration",
        "Gun_control", "Abortion_in_the_United_States", "2024_United_States_presidential_election",
        "United_States_Department_of_Justice", "Federal_Bureau_of_Investigation",
        "Central_Intelligence_Agency", "North_Korea", "China", "Russia",
        "European_Union", "NATO", "World_Health_Organization",
        "Climate_change_mitigation", "Renewable_energy", "Electric_vehicle",
        "Social_media", "Misinformation", "Fake_news", "Fact-checking",
        "United_States_economy", "Stock_market", "Cryptocurrency",
        "Medicare_(United_States)", "Social_Security_(United_States)",
        "Student_loans_in_the_United_States", "Healthcare_in_the_United_States",
        "United_States_foreign_policy", "War_in_Afghanistan_(2001–2021)",
        "Iraq_War", "Syrian_civil_war", "Terrorism", "Cybersecurity",
        "Data_privacy", "Surveillance", "Whistleblower", "Edward_Snowden",
        "Julian_Assange", "WikiLeaks", "Freedom_of_speech", "Censorship"
    ]

    # Data health monitoring
    max_data_staleness_hours: int = 48  # Alert if newest data > 48 hours old
    min_sources_per_category: int = 100  # Alert if any category has < 100 sources

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {
        "env_file": str(_env_file) if _env_file else ".env",
        "env_file_encoding": "utf-8"
    }


settings = Settings()
